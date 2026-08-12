"""Transactional, permission-checked mutations for the two canonical DAGs."""

from __future__ import annotations

import json
import sqlite3
import uuid
from collections import deque
from dataclasses import dataclass, field
from typing import Any

from cloudra.dag.models import (
    AddEdge,
    AddLink,
    AddNode,
    AttachRef,
    CoverageContract,
    DagEdge,
    DagNode,
    DependencyEdge,
    ElementaryStepEdge,
    GraphActor,
    GraphKind,
    GraphOperation,
    GraphRef,
    GraphSnapshot,
    MutationBatch,
    MutationResult,
    OccurrenceNode,
    RemoveEdge,
    SetCoverageContract,
    UpdateEdge,
    UpdateNode,
    WaiveGate,
    parse_dag_edge,
    parse_dag_node,
    parse_graph_operation,
)
from cloudra.dag.store import (
    DagCorruptionError,
    DagStore,
    _assemble_refs,
    _canonical_json,
    _load_graph_bindings,
)
from cloudra.persistence.database import retry_on_locked


class _Rejected(ValueError):
    def __init__(self, code: str, reason: str):
        super().__init__(reason)
        self.code = code
        self.reason = reason


@dataclass
class _GraphState:
    graph_id: str
    kind: GraphKind
    revision: int
    metadata: dict[str, Any]
    nodes: dict[str, DagNode] = field(default_factory=dict)
    edges: dict[str, DagEdge] = field(default_factory=dict)
    node_created: dict[str, int] = field(default_factory=dict)
    edge_created: dict[str, int] = field(default_factory=dict)


_MODEL_UPDATE_FIELDS = {
    "status",
    "priority",
    "label",
    "annotations",
    "reason",
    "blocked_reason",
    "evidence_level",
    "supersedes",
    "required",
}
_IMMUTABLE_UPDATE_FIELDS = {
    "node_id",
    "edge_id",
    "source_node_id",
    "target_node_id",
    "node_type",
    "edge_type",
    "refs",
}
_MODEL_ACTORS = {GraphActor.SUPERVISOR, GraphActor.AGENT}
_MODEL_SETTABLE_EVIDENCE_LEVELS = {"proposed", "rejected", "inconclusive"}
# process 图 status 的规范词表（与 models.ProcessStatusValue 同义）：
# frontier/blockers 投影只认这些值。词表外的 status 在 add 路径由 schema
# Literal 拒绝；update 路径的 changes 是自由字典，由这里校验并报出词表，
# 让模型一步自纠。不做同义词归一化——迁就错误拼写只会让它继续扩散。
_PROCESS_STATUS_VALUES = {
    "proposed",
    "ready",
    "running",
    "succeeded",
    "failed",
    "blocked",
    "skipped",
    "superseded",
}


def _normalize_process_status(value: Any) -> str:
    if isinstance(value, str) and value.strip().lower() in _PROCESS_STATUS_VALUES:
        return value.strip().lower()
    raise _Rejected(
        "invalid_status",
        f"unknown process status {value!r}; allowed: {sorted(_PROCESS_STATUS_VALUES)}",
    )
_DERIVED_EVIDENCE_FIELDS = {
    "saddle_supported",
    "short_irc_supported",
    "endpoint_a_minimum_supported",
    "endpoint_b_minimum_supported",
    "endpoint_direction_consistent",
    "endpoint_identity_matched",
    "thermochemistry_supported",
}


def _contains_key(value: Any, forbidden: str) -> bool:
    if isinstance(value, dict):
        return forbidden in value or any(
            _contains_key(item, forbidden) for item in value.values()
        )
    if isinstance(value, list):
        return any(_contains_key(item, forbidden) for item in value)
    return False


def _operation_freeform(operation: GraphOperation) -> dict[str, Any]:
    """op 里模型可自由书写的部分（changes/metadata），供 overall_complete 守卫扫描。"""
    if isinstance(operation, (UpdateNode, UpdateEdge)):
        return operation.changes
    if isinstance(operation, AddNode):
        return operation.node.metadata
    if isinstance(operation, AddEdge):
        return operation.edge.metadata
    if isinstance(operation, AddLink):
        return operation.payload
    return {}


class DagEngine:
    def __init__(self, store: DagStore):
        self.store = store

    def snapshot(self) -> GraphSnapshot:
        return self.store.load_snapshot()

    def history(self, *, limit: int = 100) -> list[dict[str, Any]]:
        with self.store.db.connect() as con:
            rows = con.execute(
                """
                SELECT mutation_id, session_id, actor_type, actor_id, rationale,
                       base_revisions, resulting_revisions, operations, accepted,
                       rejection_code, rejection_reason, created_at
                FROM dag_mutations ORDER BY created_at DESC, rowid DESC LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [
            {
                "mutation_id": row[0],
                "session_id": row[1],
                "actor": row[2],
                "actor_id": row[3],
                "rationale": row[4],
                "base_revisions": json.loads(row[5]),
                "resulting_revisions": json.loads(row[6]),
                "operations": json.loads(row[7]),
                "accepted": bool(row[8]),
                "rejection_code": row[9],
                "rejection_reason": row[10],
                "created_at": row[11],
            }
            for row in rows
        ]

    def rebuild_materialized(self) -> GraphSnapshot:
        """Replay accepted mutations into fresh in-memory state, then swap atomically."""

        def operation() -> None:
            with self.store.db.connect() as con:
                con.execute("BEGIN IMMEDIATE")
                graph_rows = con.execute(
                    "SELECT graph_id, graph_kind, revision, metadata FROM dag_graphs"
                ).fetchall()
                if {row[1] for row in graph_rows} != {"process", "delivery"}:
                    raise DagCorruptionError("the canonical graph pair is incomplete")
                existing_revisions = {row[1]: row[2] for row in graph_rows}
                states = {
                    GraphKind(row[1]): _GraphState(
                        graph_id=row[0],
                        kind=GraphKind(row[1]),
                        revision=0,
                        metadata=json.loads(row[3]),
                    )
                    for row in graph_rows
                }
                links: dict[str, Any] = {"dirty": False, "items": {}}
                con.execute(
                    """
                    UPDATE dag_coverage
                    SET revision = 0, coverage = '{}', updated_at = datetime('now')
                    """
                )
                rows = con.execute(
                    """
                    SELECT actor_type, actor_id, base_revisions, resulting_revisions, operations
                    FROM dag_mutations WHERE accepted = 1 ORDER BY rowid
                    """
                ).fetchall()
                if not rows and any(existing_revisions.values()):
                    raise DagCorruptionError(
                        "materialized revisions are nonzero but the accepted journal is empty"
                    )
                try:
                    for raw_actor, raw_actor_id, raw_base, raw_result, raw_operations in rows:
                        base = json.loads(raw_base)
                        expected_base = {
                            kind.value: state.revision for kind, state in states.items()
                        }
                        if base != expected_base:
                            raise DagCorruptionError(
                                f"journal base revision mismatch: {base} != {expected_base}"
                            )
                        actor = GraphActor(raw_actor)
                        touched: set[GraphKind] = set()
                        for raw_operation in json.loads(raw_operations):
                            self._apply_operation(
                                con,
                                states,
                                links,
                                touched,
                                actor,
                                raw_actor_id,
                                parse_graph_operation(raw_operation),
                            )
                        for state in states.values():
                            self._validate_structure(con, state)
                        calculated = dict(expected_base)
                        for kind in touched:
                            states[kind].revision += 1
                            calculated[kind.value] = states[kind].revision
                        recorded = json.loads(raw_result)
                        if recorded != calculated:
                            raise DagCorruptionError(
                                f"journal resulting revision mismatch: {recorded} != {calculated}"
                            )
                except DagCorruptionError:
                    raise
                except (TypeError, ValueError, json.JSONDecodeError, _Rejected) as exc:
                    raise DagCorruptionError(f"mutation journal cannot be replayed: {exc}") from exc

                for state in states.values():
                    self._validate_structure(con, state)
                    self._write_graph(con, state)
                self._write_links(
                    con,
                    links["items"],
                    max((state.revision for state in states.values()), default=0),
                )

        retry_on_locked(operation)
        return self.snapshot()

    def apply_batch(self, batch: MutationBatch) -> MutationResult:
        mutation_id = "mut_" + uuid.uuid4().hex
        try:
            revisions = retry_on_locked(
                lambda: self._apply_transaction(mutation_id, batch)
            )
        except _Rejected as exc:
            # except 块退出后 exc 会被解释器删除，先绑定到普通局部变量，
            # 供 retry_on_locked 的重试闭包安全引用
            rejection = exc
            revisions = self.store.load_bundle().revisions
            retry_on_locked(
                lambda: self._record_rejection(mutation_id, batch, revisions, rejection)
            )
            return MutationResult(
                accepted=False,
                mutation_id=mutation_id,
                revisions=revisions,
                rejection_code=exc.code,
                rejection_reason=exc.reason,
            )
        return MutationResult(
            accepted=True,
            mutation_id=mutation_id,
            revisions=revisions,
        )

    @staticmethod
    def _batch_target_graphs(batch: MutationBatch) -> set[GraphKind]:
        """批次实际触及的图集合——base revision 只校验这些图。

        与 ``_apply_operation`` 的 touch 规则保持一致：waive_gate /
        set_coverage_contract 触及 delivery，add_link 跨两张图，其余按
        operation.graph（节点/边操作的 graph 在类型层即必填）。
        """
        targets: set[GraphKind] = set()
        for operation in batch.operations:
            if isinstance(operation, (WaiveGate, SetCoverageContract)):
                targets.add(GraphKind.DELIVERY)
            elif isinstance(operation, AddLink):
                targets.update({GraphKind.PROCESS, GraphKind.DELIVERY})
            else:
                targets.add(operation.graph)
        return targets

    def _apply_transaction(
        self,
        mutation_id: str,
        batch: MutationBatch,
    ) -> dict[str, int]:
        with self.store.db.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            states = self._load_states(con)
            current = {kind.value: state.revision for kind, state in states.items()}
            # 按图校验：harness 观察每次工具调用都会推进 process revision，
            # 若要求 delivery-only 批次携带最新 process 版本，Coordinator 的
            # 机理变更将永远无法通过（自己的每次 view/mutate 都在抬高 process）。
            stale = [
                kind.value
                for kind in self._batch_target_graphs(batch)
                if batch.base_revisions.get(kind.value) != current[kind.value]
            ]
            if stale:
                raise _Rejected(
                    "stale_revision",
                    f"expected revisions {current}, received {batch.base_revisions}"
                    f" (stale graphs: {sorted(stale)})"
                    "; re-view the graph and resubmit the same batch "
                    "(omit base_revisions to let the harness pin and retry automatically)",
                )

            links = self._load_links(con)
            # 删边必须给理由：删除要能在变更日志里被人读懂，空 rationale 的
            # remove_edge 批次直接拒绝。理由是否成立由 Supervisor/用户判断。
            if (
                any(op.op == "remove_edge" for op in batch.operations)
                and not batch.rationale.strip()
            ):
                raise _Rejected(
                    "rationale_required",
                    "remove_edge requires a non-empty rationale explaining the deletion",
                )
            touched: set[GraphKind] = set()
            for operation in batch.operations:
                self._apply_operation(
                    con, states, links, touched, batch.actor, batch.actor_id, operation
                )

            for state in states.values():
                self._validate_structure(con, state)

            resulting = dict(current)
            for kind in touched:
                state = states[kind]
                state.revision += 1
                resulting[kind.value] = state.revision
                self._write_graph(con, state)
            if links["dirty"]:
                self._write_links(con, links["items"], max(resulting.values()))

            self._insert_journal(
                con,
                mutation_id=mutation_id,
                batch=batch,
                base_revisions=current,
                resulting_revisions=resulting,
                accepted=True,
            )
            return resulting

    def _load_states(self, con: sqlite3.Connection) -> dict[GraphKind, _GraphState]:
        graph_rows = con.execute(
            "SELECT graph_id, graph_kind, revision, metadata FROM dag_graphs"
        ).fetchall()
        states: dict[GraphKind, _GraphState] = {}
        for graph_id, raw_kind, revision, metadata in graph_rows:
            kind = GraphKind(raw_kind)
            states[kind] = _GraphState(
                graph_id=graph_id,
                kind=kind,
                revision=revision,
                metadata=json.loads(metadata),
            )
        if set(states) != {GraphKind.PROCESS, GraphKind.DELIVERY}:
            raise _Rejected("graph_missing", "the canonical graph pair is incomplete")

        for state in states.values():
            bindings = _load_graph_bindings(con, state.graph_id)
            for row in con.execute(
                """
                SELECT node_id, node_type, label, refs, payload, created_revision
                FROM dag_nodes WHERE graph_id = ?
                """,
                (state.graph_id,),
            ).fetchall():
                node = parse_dag_node({
                    "node_id": row[0],
                    "node_type": row[1],
                    "label": row[2],
                    "refs": _assemble_refs(
                        json.loads(row[3]), bindings.get(("node", row[0]), [])
                    ),
                    **json.loads(row[4]),
                })
                state.nodes[node.node_id] = node
                state.node_created[node.node_id] = row[5]
            for row in con.execute(
                """
                SELECT edge_id, source_node_id, target_node_id, edge_type,
                       label, refs, payload, created_revision
                FROM dag_edges WHERE graph_id = ?
                """,
                (state.graph_id,),
            ).fetchall():
                edge = parse_dag_edge({
                    "edge_id": row[0],
                    "source_node_id": row[1],
                    "target_node_id": row[2],
                    "edge_type": row[3],
                    "label": row[4],
                    "refs": _assemble_refs(
                        json.loads(row[5]), bindings.get(("edge", row[0]), [])
                    ),
                    **json.loads(row[6]),
                })
                state.edges[edge.edge_id] = edge
                state.edge_created[edge.edge_id] = row[7]
        return states

    @staticmethod
    def _load_links(con: sqlite3.Connection) -> dict[str, Any]:
        rows = con.execute(
            """
            SELECT link_id, process_node_id, delivery_element_type,
                   delivery_element_id, payload, created_revision
            FROM dag_links
            """
        ).fetchall()
        return {
            "dirty": False,
            "items": {
                row[0]: {
                    "link_id": row[0],
                    "process_node_id": row[1],
                    "delivery_element_type": row[2],
                    "delivery_element_id": row[3],
                    "payload": json.loads(row[4]),
                    "created_revision": row[5],
                }
                for row in rows
            },
        }

    def _apply_operation(
        self,
        con: sqlite3.Connection,
        states: dict[GraphKind, _GraphState],
        links: dict[str, Any],
        touched: set[GraphKind],
        actor: GraphActor,
        actor_id: str,
        operation: GraphOperation,
    ) -> None:
        if isinstance(operation, WaiveGate):
            if actor is not GraphActor.USER:
                raise _Rejected("actor_forbidden", "only the user may waive a coverage gate")
            waiver = operation.waiver
            contract = self._load_contract(con, states[GraphKind.DELIVERY].graph_id)
            if waiver not in contract.waivers:
                contract = contract.model_copy(
                    update={"waivers": [*contract.waivers, waiver]}
                )
                self._write_contract(
                    con,
                    states[GraphKind.DELIVERY].graph_id,
                    states[GraphKind.DELIVERY].revision + 1,
                    contract,
                )
            touched.add(GraphKind.DELIVERY)
            return
        if isinstance(operation, SetCoverageContract):
            proposed = operation.contract
            current = self._load_contract(con, states[GraphKind.DELIVERY].graph_id)
            if actor is not GraphActor.USER and not self._coverage_not_weaker(
                current, proposed
            ):
                raise _Rejected(
                    "actor_forbidden",
                    "only the user may remove or lower a coverage requirement",
                )
            self._write_contract(
                con,
                states[GraphKind.DELIVERY].graph_id,
                states[GraphKind.DELIVERY].revision + 1,
                proposed,
            )
            touched.add(GraphKind.DELIVERY)
            return
        if isinstance(operation, AddLink):
            # 跨图簿记，对两个 model actor 都开放，不参与按图分权
            self._add_link(states, links, operation)
            touched.update({GraphKind.PROCESS, GraphKind.DELIVERY})
            return
        state = states[operation.graph]

        # 按图分权：机理 DAG 由 Coordinator 设计，流程 DAG 由 Supervisor 维护。
        # 子 agent 对指派给自己的 process 节点有受限的回报权限
        # （见 _check_agent_process_access）。
        if actor is GraphActor.SUPERVISOR and state.kind is GraphKind.DELIVERY:
            raise _Rejected(
                "actor_forbidden",
                "the supervisor is read-only on the delivery DAG",
            )
        if actor is GraphActor.AGENT and state.kind is GraphKind.PROCESS:
            self._check_agent_process_access(state, actor_id, operation)

        if isinstance(operation, (AddNode, AddEdge)):
            self._check_element_graph_kind(state.kind, operation)
        if (
            actor is not GraphActor.HARNESS
            and state.kind is GraphKind.DELIVERY
            and isinstance(operation, (AddNode, AddEdge))
        ):
            # 证据派生保护：模型只能以 proposed/rejected/inconclusive 创建
            # delivery 元素，派生证据位与更高级别由 harness 确定性写入
            element = operation.node if isinstance(operation, AddNode) else operation.edge
            derived_in_metadata = set(element.metadata) & _DERIVED_EVIDENCE_FIELDS
            derived_flags = (
                {key for key in _DERIVED_EVIDENCE_FIELDS if getattr(element, key, None) is True}
                if isinstance(element, ElementaryStepEdge)
                else set()
            )
            level = getattr(element, "evidence_level", "proposed")
            if (
                level not in _MODEL_SETTABLE_EVIDENCE_LEVELS
                or derived_in_metadata
                or derived_flags
            ):
                raise _Rejected(
                    "actor_forbidden",
                    "only deterministic harness adapters may create evidence-derived claims",
                )

        if _contains_key(_operation_freeform(operation), "overall_complete"):
            code = "actor_forbidden" if actor is GraphActor.SUPERVISOR else "invalid_operation"
            raise _Rejected(code, "overall completion is derived, never set by a mutation")

        if isinstance(operation, AddNode):
            node = operation.node
            if node.node_id in state.nodes:
                raise _Rejected("duplicate_id", f"node {node.node_id!r} already exists")
            state.nodes[node.node_id] = node
            state.node_created[node.node_id] = state.revision + 1
            touched.add(state.kind)
            return
        if isinstance(operation, AddEdge):
            edge = operation.edge
            if edge.edge_id in state.edges:
                raise _Rejected("duplicate_id", f"edge {edge.edge_id!r} already exists")
            state.edges[edge.edge_id] = edge
            state.edge_created[edge.edge_id] = state.revision + 1
            touched.add(state.kind)
            return
        if isinstance(operation, RemoveEdge):
            self._remove_edge(state, operation)
            touched.add(state.kind)
            return
        if isinstance(operation, (UpdateNode, UpdateEdge)):
            self._apply_update(state, actor, operation)
            touched.add(state.kind)
            return
        if isinstance(operation, AttachRef):
            self._attach_ref(con, state, operation)
            touched.add(state.kind)
            return
        raise _Rejected(  # 判别联合已穷尽，这里只是防御
            "invalid_operation",
            f"unsupported operation {operation.op}",
        )

    @staticmethod
    def _check_element_graph_kind(
        kind: GraphKind, operation: "AddNode | AddEdge"
    ) -> None:
        """图-类型匹配：词表与图种类绑定，是类型系统之外的跨元素规则，由引擎把守。"""
        if isinstance(operation, AddNode):
            element = operation.node
            process_types = "planned|observed_tool_call"
            ok = (
                isinstance(element, OccurrenceNode)
                if kind is GraphKind.DELIVERY
                else not isinstance(element, OccurrenceNode)
            )
            type_name = element.node_type
        else:
            element = operation.edge
            process_types = "dependency"
            ok = (
                isinstance(element, ElementaryStepEdge)
                if kind is GraphKind.DELIVERY
                else isinstance(element, DependencyEdge)
            )
            type_name = element.edge_type
        if not ok:
            expected = (
                "occurrence/elementary_step"
                if kind is GraphKind.DELIVERY
                else process_types
            )
            raise _Rejected(
                "invalid_operation",
                f"{type_name!r} does not belong on the {kind.value} graph; "
                f"expected {expected}",
            )

    @staticmethod
    def _check_agent_process_access(
        state: "_GraphState", actor_id: str, operation: GraphOperation
    ) -> None:
        """agent（Coordinator/子 agent）对 process 图的受限权限。

        - remove_edge：删边一律由 Supervisor 执行。请求连同 rationale 记入
          变更日志（拒绝也是日志），harness 随后唤醒 Supervisor 复核——理由
          充分由它代为删除。
        - update_node / attach_ref：只允许落在 payload.assignee 等于自己的
          节点上，且 update 只能写状态回报字段（status/reason/blocked_reason/
          annotations），让子 agent 完成任务后即时管理自己负责的部分。
        - 其余结构性操作（add_node/add_edge/update_edge 等）不开放。
        """
        if isinstance(operation, RemoveEdge):
            raise _Rejected(
                "edge_removal_requires_supervisor",
                "process edges are added/removed by the supervisor; this request and "
                "its rationale have been journaled and the supervisor will be woken "
                "to review it",
            )
        if isinstance(operation, (UpdateNode, AttachRef)):
            target_id = (
                operation.node_id
                if isinstance(operation, UpdateNode)
                else operation.target_id
            )
            node = state.nodes.get(target_id)
            if node is not None and getattr(node, "assignee", None) == actor_id:
                if isinstance(operation, UpdateNode):
                    changes = operation.changes
                    allowed = {"status", "reason", "blocked_reason", "annotations"}
                    if not set(changes) <= allowed:
                        raise _Rejected(
                            "actor_forbidden",
                            "an agent may only report status/reason/blocked_reason/"
                            "annotations on its assigned process nodes",
                        )
                return
            assignee = getattr(node, "assignee", None) if node is not None else None
            raise _Rejected(
                "actor_forbidden",
                f"process node is not assigned to this agent (current assignee: "
                f"{assignee or 'unassigned'}); the process DAG is maintained by the "
                "supervisor — if it needs changes, state them in your report/rationale "
                "and the supervisor will act on them",
            )
        raise _Rejected(
            "actor_forbidden",
            "agents are read-only on the process DAG except for their assigned nodes",
        )

    @staticmethod
    def _load_contract(con: sqlite3.Connection, graph_id: str) -> CoverageContract:
        row = con.execute(
            "SELECT coverage FROM dag_coverage WHERE graph_id = ?",
            (graph_id,),
        ).fetchone()
        if row is None or not row[0] or json.loads(row[0]) == {}:
            return CoverageContract.mechanism_default()
        try:
            return CoverageContract.model_validate_json(row[0])
        except ValueError as exc:
            raise _Rejected("coverage_corrupt", f"invalid persisted contract: {exc}") from exc

    @staticmethod
    def _write_contract(
        con: sqlite3.Connection,
        graph_id: str,
        revision: int,
        contract: CoverageContract,
    ) -> None:
        con.execute(
            """
            INSERT INTO dag_coverage(graph_id, revision, coverage, updated_at)
            VALUES (?, ?, ?, datetime('now'))
            ON CONFLICT(graph_id) DO UPDATE SET
                revision=excluded.revision,
                coverage=excluded.coverage,
                updated_at=excluded.updated_at
            """,
            (graph_id, revision, _canonical_json(contract.model_dump(mode="json"))),
        )

    @staticmethod
    def _coverage_not_weaker(
        current: CoverageContract,
        proposed: CoverageContract,
    ) -> bool:
        ranks = {
            "proposed": 0,
            "structure_supported": 1,
            "saddle_supported": 2,
            "endpoint_supported": 3,
            "thermo_annotated": 4,
        }
        if ranks.get(proposed.required_node_level, -1) < ranks.get(
            current.required_node_level, 10_000
        ):
            return False
        if ranks.get(proposed.required_edge_level, -1) < ranks.get(
            current.required_edge_level, 10_000
        ):
            return False
        if current.require_branch_disposition and not proposed.require_branch_disposition:
            return False
        if current.require_thermochemistry and not proposed.require_thermochemistry:
            return False
        return proposed.waivers == current.waivers

    def _apply_update(
        self,
        state: _GraphState,
        actor: GraphActor,
        operation: "UpdateNode | UpdateEdge",
    ) -> None:
        is_node = isinstance(operation, UpdateNode)
        id_key = "node_id" if is_node else "edge_id"
        element_id = operation.node_id if is_node else operation.edge_id
        changes = operation.changes
        elements = state.nodes if is_node else state.edges
        if element_id not in elements:
            raise _Rejected("missing_target", f"{id_key} {element_id!r} does not exist")
        if not changes:
            raise _Rejected(
                "invalid_operation",
                "update requires non-empty changes, e.g. "
                f'{{"op": "{operation.op}", ..., "changes": {{"label": ..., "<field>": ...}}}}',
            )
        forbidden = set(changes) & _IMMUTABLE_UPDATE_FIELDS
        if forbidden:
            code = "actor_forbidden" if actor is GraphActor.SUPERVISOR else "immutable_field"
            raise _Rejected(code, f"immutable graph fields cannot change: {sorted(forbidden)}")
        if actor in _MODEL_ACTORS and not set(changes) <= _MODEL_UPDATE_FIELDS:
            # 点名违规字段并给出白名单，否则模型只能盲目重试烧轮次。
            extras = sorted(set(changes) - _MODEL_UPDATE_FIELDS)
            raise _Rejected(
                "actor_forbidden",
                f"model update exceeds its mutable fields: {extras}; "
                f"allowed: {sorted(_MODEL_UPDATE_FIELDS)} "
                "(free-form notes belong in 'annotations')",
            )
        if actor in _MODEL_ACTORS and changes.get("required") is False:
            raise _Rejected("actor_forbidden", "a model cannot lower a requirement")
        if actor is not GraphActor.HARNESS and "evidence_level" in changes:
            if changes["evidence_level"] not in {"proposed", "rejected", "inconclusive"}:
                raise _Rejected(
                    "actor_forbidden",
                    "only deterministic harness adapters may promote an evidence-derived level",
                )
        if state.kind is GraphKind.PROCESS and "status" in changes:
            changes = {**changes, "status": _normalize_process_status(changes["status"])}
        _canonical_json(changes)
        current = elements[element_id]
        serialized = current.model_dump(mode="json", exclude={"payload"})
        metadata = dict(serialized.get("metadata") or {})
        for key, value in changes.items():
            if key in type(current).model_fields:
                serialized[key] = value
            else:
                # 自由扩展位：模型白名单外的键已在上面被拦，走到这里的
                # 未知键来自 harness/用户，并入 metadata 保留。
                metadata[key] = value
        serialized["metadata"] = metadata
        elements[element_id] = (
            parse_dag_node(serialized) if is_node else parse_dag_edge(serialized)
        )

    @staticmethod
    def _remove_edge(state: _GraphState, operation: RemoveEdge) -> None:
        # 删边已完全放开（两张图、任意端点状态），但批次必须带 rationale
        # （在 _apply_transaction 入口强制），被删的边留在变更日志里供审计。
        # agent 对 process 图的删边请求在 _check_agent_process_access 被拦下，
        # 转交 Supervisor 复核后由它代为执行，因此到得了这里的调用都已授权。
        if operation.edge_id not in state.edges:
            raise _Rejected("missing_target", f"edge {operation.edge_id!r} does not exist")
        del state.edges[operation.edge_id]
        state.edge_created.pop(operation.edge_id, None)

    @staticmethod
    def _attach_ref(
        con: sqlite3.Connection, state: _GraphState, operation: AttachRef
    ) -> None:
        ref = operation.ref
        elements = state.nodes if operation.target_type == "node" else state.edges
        if operation.target_id not in elements:
            raise _Rejected(
                "missing_target", f"target {operation.target_id!r} does not exist"
            )
        current = elements[operation.target_id]
        if ref in current.refs:
            return
        serialized = current.model_dump(mode="json", exclude={"payload"})
        serialized["refs"] = [
            item.model_dump(mode="json") for item in [*current.refs, ref]
        ]
        updated = (
            parse_dag_node(serialized)
            if operation.target_type == "node"
            else parse_dag_edge(serialized)
        )
        elements[operation.target_id] = updated
        # 双写：内联 refs 列随 _write_graph 物化重写，关联表在同一事务里记账。
        # 此处 revision 尚未推进，resulting revision = state.revision + 1。
        DagEngine._insert_evidence_binding(
            con,
            state.graph_id,
            operation.target_type,
            operation.target_id,
            ref.ref_id,
            evidence_role=operation.evidence_role,
            derived_level=getattr(updated, "evidence_level", None),
            revision=state.revision + 1,
        )

    @staticmethod
    def _add_link(
        states: dict[GraphKind, _GraphState],
        links: dict[str, Any],
        operation: AddLink,
    ) -> None:
        if operation.link_id in links["items"]:
            raise _Rejected("duplicate_id", f"link {operation.link_id!r} already exists")
        if operation.process_node_id not in states[GraphKind.PROCESS].nodes:
            raise _Rejected("dangling_link", "process link target does not exist")
        delivery = states[GraphKind.DELIVERY]
        collection = (
            delivery.nodes
            if operation.delivery_element_type == "node"
            else delivery.edges
        )
        if operation.delivery_element_id not in collection:
            raise _Rejected("dangling_link", "delivery link target does not exist")
        links["items"][operation.link_id] = {
            "link_id": operation.link_id,
            "process_node_id": operation.process_node_id,
            "delivery_element_type": operation.delivery_element_type,
            "delivery_element_id": operation.delivery_element_id,
            "payload": operation.payload,
            "created_revision": max(state.revision for state in states.values()) + 1,
        }
        links["dirty"] = True

    def _validate_structure(self, con: sqlite3.Connection, state: _GraphState) -> None:
        for edge in state.edges.values():
            if edge.source_node_id not in state.nodes or edge.target_node_id not in state.nodes:
                raise _Rejected("dangling_edge", f"edge {edge.edge_id!r} has a missing endpoint")
        for node in state.nodes.values():
            for ref in node.refs:
                self._validate_ref(con, ref)
        for edge in state.edges.values():
            for ref in edge.refs:
                self._validate_ref(con, ref)
        self._validate_acyclic(state)

    @staticmethod
    def _validate_ref(con: sqlite3.Connection, ref: GraphRef) -> None:
        if ref.ref_type == "species":
            row = con.execute(
                "SELECT 1 FROM dag_species WHERE species_id = ?", (ref.ref_id,)
            ).fetchone()
        elif ref.ref_type == "tool_result":
            row = con.execute(
                "SELECT content_hash FROM dag_evidence WHERE evidence_id = ?", (ref.ref_id,)
            ).fetchone()
            if row is not None and (not ref.content_hash or ref.content_hash != row[0]):
                row = None
        elif ref.ref_type == "artifact":
            row = con.execute(
                "SELECT sha256 FROM artifacts WHERE artifact_id = ?", (ref.ref_id,)
            ).fetchone()
            if row is not None and (
                not ref.content_hash or ref.content_hash not in {row[0], f"sha256:{row[0]}"}
            ):
                row = None
        elif ref.ref_type == "compute_job":
            try:
                job_id = int(ref.ref_id)
            except (TypeError, ValueError):
                row = None
            else:
                row = con.execute("SELECT 1 FROM compute_jobs WHERE id = ?", (job_id,)).fetchone()
        else:  # GraphRef validation should make this unreachable.
            row = None
        if row is None:
            raise _Rejected(
                "invalid_reference",
                f"{ref.ref_type} reference {ref.ref_id!r} does not resolve",
            )

    @staticmethod
    def _validate_acyclic(state: _GraphState) -> None:
        indegree = {node_id: 0 for node_id in state.nodes}
        outgoing: dict[str, list[str]] = {node_id: [] for node_id in state.nodes}
        for edge in state.edges.values():
            indegree[edge.target_node_id] += 1
            outgoing[edge.source_node_id].append(edge.target_node_id)
        ready = deque(node_id for node_id, degree in indegree.items() if degree == 0)
        visited = 0
        while ready:
            node_id = ready.popleft()
            visited += 1
            for target in outgoing[node_id]:
                indegree[target] -= 1
                if indegree[target] == 0:
                    ready.append(target)
        if visited != len(state.nodes):
            raise _Rejected("cycle", f"{state.kind.value} graph would contain a cycle")

    # payload 列 = 显式字段（含默认值）+ metadata 的 JSON；身份列（id/type/label/refs）
    # 各有专列。读取侧 parse_dag_node/parse_dag_edge 对新旧形状双兼容。
    _PAYLOAD_COLUMN_EXCLUDE = {"node_id", "edge_id", "source_node_id", "target_node_id",
                               "node_type", "edge_type", "label", "refs", "payload"}

    @staticmethod
    def _payload_column(element: "DagNode | DagEdge") -> str:
        return _canonical_json(
            element.model_dump(mode="json", exclude=DagEngine._PAYLOAD_COLUMN_EXCLUDE)
        )

    @staticmethod
    def _insert_evidence_binding(
        con: sqlite3.Connection,
        graph_id: str,
        target_type: str,
        target_id: str,
        evidence_id: str,
        *,
        evidence_role: "str | None",
        derived_level: "str | None",
        revision: int,
    ) -> None:
        # 关联表记账的唯一入口；INSERT OR IGNORE 保留先写入的
        # evidence_role 与原始 created_revision（_attach_ref 先于对账）。
        con.execute(
            """
            INSERT OR IGNORE INTO dag_evidence_bindings(
                graph_id, target_type, target_id, evidence_id,
                evidence_role, derived_level, created_revision
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                graph_id,
                target_type,
                target_id,
                evidence_id,
                evidence_role,
                derived_level,
                revision,
            ),
        )

    @staticmethod
    def _write_graph(con: sqlite3.Connection, state: _GraphState) -> None:
        con.execute("DELETE FROM dag_edges WHERE graph_id = ?", (state.graph_id,))
        con.execute("DELETE FROM dag_nodes WHERE graph_id = ?", (state.graph_id,))
        for node in state.nodes.values():
            con.execute(
                """
                INSERT INTO dag_nodes(
                    graph_id, node_id, node_type, label, refs, payload,
                    created_revision, updated_revision
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    state.graph_id,
                    node.node_id,
                    node.node_type,
                    node.label,
                    _canonical_json([ref.model_dump(mode="json") for ref in node.refs]),
                    DagEngine._payload_column(node),
                    state.node_created[node.node_id],
                    state.revision,
                ),
            )
        for edge in state.edges.values():
            con.execute(
                """
                INSERT INTO dag_edges(
                    graph_id, edge_id, source_node_id, target_node_id, edge_type,
                    label, refs, payload, created_revision, updated_revision
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    state.graph_id,
                    edge.edge_id,
                    edge.source_node_id,
                    edge.target_node_id,
                    edge.edge_type,
                    edge.label,
                    _canonical_json([ref.model_dump(mode="json") for ref in edge.refs]),
                    DagEngine._payload_column(edge),
                    state.edge_created[edge.edge_id],
                    state.revision,
                ),
            )
        # 关联表对账：refs 只增不减，唯一需要清理的是元素被删除
        # （remove_edge）后留下的孤儿绑定；INSERT OR IGNORE 保留
        # _attach_ref 已写入的 evidence_role 与原始 created_revision。
        con.execute(
            """
            DELETE FROM dag_evidence_bindings
            WHERE graph_id = ? AND (
                (target_type = 'node' AND target_id NOT IN (
                    SELECT node_id FROM dag_nodes WHERE graph_id = ?))
                OR (target_type = 'edge' AND target_id NOT IN (
                    SELECT edge_id FROM dag_edges WHERE graph_id = ?))
            )
            """,
            (state.graph_id, state.graph_id, state.graph_id),
        )
        for node in state.nodes.values():
            for ref in node.refs:
                DagEngine._insert_evidence_binding(
                    con,
                    state.graph_id,
                    "node",
                    node.node_id,
                    ref.ref_id,
                    evidence_role=None,
                    derived_level=getattr(node, "evidence_level", None),
                    revision=state.revision,
                )
        for edge in state.edges.values():
            for ref in edge.refs:
                DagEngine._insert_evidence_binding(
                    con,
                    state.graph_id,
                    "edge",
                    edge.edge_id,
                    ref.ref_id,
                    evidence_role=None,
                    derived_level=getattr(edge, "evidence_level", None),
                    revision=state.revision,
                )
        con.execute(
            "UPDATE dag_graphs SET revision = ?, updated_at = datetime('now') WHERE graph_id = ?",
            (state.revision, state.graph_id),
        )

    @staticmethod
    def _write_links(con: sqlite3.Connection, links: dict[str, dict[str, Any]], revision: int) -> None:
        con.execute("DELETE FROM dag_links")
        for link in links.values():
            con.execute(
                """
                INSERT INTO dag_links(
                    link_id, process_node_id, delivery_element_type,
                    delivery_element_id, payload, created_revision
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    link["link_id"],
                    link["process_node_id"],
                    link["delivery_element_type"],
                    link["delivery_element_id"],
                    _canonical_json(link.get("payload", {})),
                    link.get("created_revision", revision),
                ),
            )

    def _record_rejection(
        self,
        mutation_id: str,
        batch: MutationBatch,
        revisions: dict[str, int],
        rejection: _Rejected,
    ) -> None:
        with self.store.db.connect() as con:
            self._insert_journal(
                con,
                mutation_id=mutation_id,
                batch=batch,
                base_revisions=batch.base_revisions,
                resulting_revisions=revisions,
                accepted=False,
                rejection=rejection,
            )

    def _insert_journal(
        self,
        con: sqlite3.Connection,
        *,
        mutation_id: str,
        batch: MutationBatch,
        base_revisions: dict[str, int],
        resulting_revisions: dict[str, int],
        accepted: bool,
        rejection: _Rejected | None = None,
    ) -> None:
        bundle = self.store.load_bundle() if not con.in_transaction else None
        graph_id = (
            next(
                (
                    self.store._GRAPH_IDS[operation.graph]
                    for operation in batch.operations
                    if operation.graph is not None
                ),
                self.store._GRAPH_IDS[GraphKind.PROCESS],
            )
            if bundle is None
            else bundle.process_graph_id
        )
        graph_kind = next(
            (operation.graph for operation in batch.operations if operation.graph is not None),
            GraphKind.PROCESS,
        )
        con.execute(
            """
            INSERT INTO dag_mutations(
                mutation_id, graph_id, base_revision, resulting_revision,
                actor_type, actor_id, session_id, rationale, base_revisions,
                resulting_revisions, operations, accepted, rejection_code,
                rejection_reason, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
            """,
            (
                mutation_id,
                graph_id,
                base_revisions.get(graph_kind.value, 0),
                resulting_revisions.get(graph_kind.value, 0),
                batch.actor.value,
                batch.actor_id,
                batch.session_id,
                batch.rationale,
                _canonical_json(base_revisions),
                _canonical_json(resulting_revisions),
                _canonical_json([
                    # 排除 computed payload 投影（视图派生物），journal 只存权威字段
                    operation.model_dump(
                        mode="json", exclude={"node": {"payload"}, "edge": {"payload"}}
                    )
                    for operation in batch.operations
                ]),
                int(accepted),
                rejection.code if rejection else None,
                rejection.reason if rejection else None,
            ),
        )
