"""Transactional, permission-checked mutations for the two canonical DAGs."""

from __future__ import annotations

import difflib
import json
import os
import sqlite3
import uuid
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Literal

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
    MechanismDraft,
    MutationBatch,
    MutationResult,
    OccurrenceNode,
    RemoveEdge,
    RemoveNode,
    SetCoverageContract,
    SpeciesNode,
    StageKind,
    StageState,
    StageStatus,
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
    _read_element_stages,
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
_DERIVED_EVIDENCE_FIELDS = {
    "saddle_supported",
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


def apply_stage_verdict(
    stages: list[StageState],
    *,
    stage_kind: StageKind,
    verdict: Literal["agree", "disagree", "skip", "not_applicable"],
    reason: str = "",
    ref: GraphRef | None = None,
    tool_succeeded: bool = False,
    allow_out_of_order: bool = False,
) -> list[StageState]:
    """单阶段绑定的确定性守卫，返回更新后的阶段列表（不改动输入）。

    - disagree ⇒ rejected（reason 必填，清 ref）
    - skip ⇒ skipped（reason 必填，清 ref）
    - not_applicable ⇒ not_applicable（reason 必填，清 ref）——该槽对此
      元素不成立（无能垒步无 TS、单分子步无 endpoint_b 络合物）；语义上
      是完成态，与 skipped 的"主动放弃"区分开
    - agree ⇒ tool_succeeded 且带 ref。legacy/contract_version=1 项目保持
      顺序门禁：前面所有**必需**阶段 supported/skipped/not_applicable 才
      supported（stage_out_of_order），rejected 阶段可被后来的 agree 重绑
      （D2）。contract_version=2（allow_out_of_order=True）允许证据乱序到
      达/绑定；缺失的依赖由 requirements 层计算，不再拒绝绑定本身。
      ts_guess 只推进它自己那个阶段，永远不能充抵 ts_opt/frequency；它是
      advisory 阶段，即使存量契约把它落库为 required=True 也不构成顺序
      门禁的 blocker。
    """
    index = next(
        (i for i, stage in enumerate(stages) if stage.kind == stage_kind), None
    )
    if index is None:
        raise _Rejected(
            "stage_not_declared",
            f"stage {stage_kind.value!r} is not in this element's stage contract; "
            "the Coordinator declares stages when proposing the mechanism",
        )
    target = stages[index]
    if verdict in ("disagree", "skip", "not_applicable"):
        if not reason.strip():
            raise _Rejected(
                "reason_required",
                f"a {verdict!r} verdict requires a non-empty reason",
            )
        status = {
            "disagree": StageStatus.REJECTED,
            "skip": StageStatus.SKIPPED,
            "not_applicable": StageStatus.NOT_APPLICABLE,
        }[verdict]
        updated = target.model_copy(
            update={"status": status, "reason": reason, "ref": None}
        )
        return [*stages[:index], updated, *stages[index + 1:]]
    if not tool_succeeded:
        raise _Rejected(
            "tool_not_succeeded",
            "only a succeeded tool call can support a stage",
        )
    if ref is None:
        raise _Rejected(
            "missing_ref",
            "an agree verdict requires the evidence ref being bound",
        )
    if not allow_out_of_order:
        blockers = [
            stage.kind.value
            for stage in stages[:index]
            if stage.required
            # ts_guess 语义上永远是 advisory 阶段（models.StageKind），从不
            # 充抵也不前置卡 ts_opt/frequency；存量 v1 契约可能仍把它落库
            # 为 required=True，这里按语义排除而不是信任落库值。
            and stage.kind is not StageKind.TS_GUESS
            and stage.status
            not in {
                StageStatus.SUPPORTED,
                StageStatus.SKIPPED,
                StageStatus.NOT_APPLICABLE,
            }
        ]
        if blockers:
            raise _Rejected(
                "stage_out_of_order",
                "previous required stages must be supported, skipped, or not_applicable first: "
                + ", ".join(blockers),
            )
    updated = target.model_copy(
        update={"status": StageStatus.SUPPORTED, "reason": "", "ref": ref}
    )
    return [*stages[:index], updated, *stages[index + 1:]]


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


def _is_legacy_process_op(operation: GraphOperation) -> bool:
    """旧 process 图 op（含 add_link 跨图簿记）：只读重放时 no-op。"""
    if isinstance(operation, AddLink):
        return True
    return getattr(operation, "graph", None) is GraphKind.PROCESS


def _legacy_process_op_graphs(operation: GraphOperation) -> set[GraphKind]:
    """旧 op 写入时的 touch 口径——重放必须按同一口径推进 revision，
    journal 的 base/resulting 校验才通过。"""
    if isinstance(operation, AddLink):
        return {GraphKind.PROCESS, GraphKind.DELIVERY}
    return {GraphKind.PROCESS}


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
                    ignored_legacy = 0
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
                            parsed = parse_graph_operation(raw_operation)
                            if _is_legacy_process_op(parsed):
                                # Phase 4：process 图已删除。旧 journal 的 process
                                # op（含 add_link）重放为 no-op，但 revision 推进
                                # 口径与写入时一致，日志校验才能通过。
                                ignored_legacy += 1
                                touched.update(_legacy_process_op_graphs(parsed))
                                continue
                            self._apply_operation(
                                con,
                                states,
                                links,
                                touched,
                                actor,
                                raw_actor_id,
                                parsed,
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
                if ignored_legacy:
                    # 留痕：本次重放吞掉的旧 process op 数量。operations 为空、
                    # base==resulting==最终版本——下次重放校验该行时自洽。
                    final = {
                        kind.value: state.revision for kind, state in states.items()
                    }
                    con.execute(
                        """
                        INSERT INTO dag_mutations(
                            mutation_id, graph_id, base_revision, resulting_revision,
                            actor_type, actor_id, session_id, rationale, base_revisions,
                            resulting_revisions, operations, accepted, created_at
                        ) VALUES (?, ?, ?, ?, 'harness', 'dag-replay', '', ?, ?, ?, '[]', 1,
                                  datetime('now'))
                        """,
                        (
                            "mut_" + uuid.uuid4().hex,
                            states[GraphKind.DELIVERY].graph_id,
                            final["delivery"],
                            final["delivery"],
                            f"ignored_legacy_process_op: {ignored_legacy} legacy process "
                            "operations no-op'd during replay (process graph removed)",
                            _canonical_json(final),
                            _canonical_json(final),
                        ),
                    )

        retry_on_locked(operation)
        return self.snapshot()

    def apply_batch(self, batch: MutationBatch) -> MutationResult:
        result, _draft_id = self._apply_batch(batch)
        return result

    def apply_draft_batch(
        self, batch: MutationBatch, draft: MechanismDraft, *, actor_id: str
    ) -> tuple[MutationResult, str | None]:
        """Write candidate graph, mutation journal and draft in one transaction."""
        return self._apply_batch(batch, draft=draft, draft_actor_id=actor_id)

    def _apply_batch(
        self,
        batch: MutationBatch,
        *,
        draft: MechanismDraft | None = None,
        draft_actor_id: str = "",
    ) -> tuple[MutationResult, str | None]:
        mutation_id = "mut_" + uuid.uuid4().hex
        draft_id = "draft_" + uuid.uuid4().hex if draft is not None else None
        try:
            revisions = retry_on_locked(
                lambda: self._apply_transaction(
                    mutation_id, batch,
                    draft=(draft_id, draft, draft_actor_id) if draft_id and draft else None,
                )
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
            ), None
        return MutationResult(
            accepted=True,
            mutation_id=mutation_id,
            revisions=revisions,
        ), draft_id

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
        draft: tuple[str, MechanismDraft, str] | None = None,
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
            # 删边/删节点必须给理由：删除要能在变更日志里被人读懂，空
            # rationale 的删除批次直接拒绝。理由是否成立由 Supervisor/用户判断。
            if any(
                op.op in ("remove_edge", "remove_node") for op in batch.operations
            ) and not batch.rationale.strip():
                raise _Rejected(
                    "rationale_required",
                    "deletion requires a non-empty rationale explaining the removal",
                )
            touched: set[GraphKind] = set()
            for operation in batch.operations:
                self._apply_operation(
                    con, states, links, touched, batch.actor, batch.actor_id, operation
                )

            for state in states.values():
                self._validate_structure(con, state)

            # 删除收敛审查待办（同一事务）：被删目标上的 pending CallReview →
            # ignored + call_verdict 通知（target_deleted，告知提交者）；定向到
            # 被删目标的 queued 结构化请求 → superseded。历史裁决与证据行保留。
            self._converge_deleted_reviews(
                con, self._collect_deleted_targets(batch), batch.rationale
            )

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
            if draft is not None:
                self.store._insert_draft(con, draft[0], draft[1], draft[2])
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
            is_delivery = state.kind is GraphKind.DELIVERY
            for row in con.execute(
                """
                SELECT node_id, node_type, label, refs, payload, stages, created_revision
                FROM dag_nodes WHERE graph_id = ?
                """,
                (state.graph_id,),
            ).fetchall():
                payload = json.loads(row[4])
                data = {
                    "node_id": row[0],
                    "node_type": row[1],
                    "label": row[2],
                    "name": row[2],
                    "refs": _assemble_refs(
                        json.loads(row[3]), bindings.get(("node", row[0]), [])
                    ),
                    **payload,
                }
                if is_delivery:
                    data["stages"] = _read_element_stages(payload, row[5], is_edge=False)
                node = parse_dag_node(data)
                state.nodes[node.node_id] = node
                state.node_created[node.node_id] = row[6]
            for row in con.execute(
                """
                SELECT edge_id, source_node_id, target_node_id, edge_type,
                       label, refs, payload, stages, created_revision
                FROM dag_edges WHERE graph_id = ?
                """,
                (state.graph_id,),
            ).fetchall():
                payload = json.loads(row[6])
                data = {
                    "edge_id": row[0],
                    "source_node_id": row[1],
                    "target_node_id": row[2],
                    "edge_type": row[3],
                    "label": row[4],
                    "name": row[4],
                    "refs": _assemble_refs(
                        json.loads(row[5]), bindings.get(("edge", row[0]), [])
                    ),
                    **payload,
                }
                if is_delivery:
                    data["stages"] = _read_element_stages(payload, row[7], is_edge=True)
                edge = parse_dag_edge(data)
                state.edges[edge.edge_id] = edge
                state.edge_created[edge.edge_id] = row[8]
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

    @staticmethod
    def _collect_deleted_targets(batch: MutationBatch) -> list[tuple[str, str]]:
        """本批次实际删除的 delivery 元素：``(target_type, target_id)``。"""
        deleted: list[tuple[str, str]] = []
        for operation in batch.operations:
            if isinstance(operation, RemoveNode) and operation.graph is GraphKind.DELIVERY:
                deleted.append(("node", operation.node_id))
            elif isinstance(operation, RemoveEdge) and operation.graph is GraphKind.DELIVERY:
                deleted.append(("edge", operation.edge_id))
        return deleted

    def _converge_deleted_reviews(
        self,
        con: sqlite3.Connection,
        deleted: list[tuple[str, str]],
        rationale: str,
    ) -> None:
        """删除后收敛待审项（与图删除同一事务）。

        - pending CallReview 且 ``suggested_target_id`` 指向被删目标 → ``ignored``
          （复用既有终态；reason 区分"目标已删除"与科学驳回），并同事务落一条
          ``call_verdict`` 通知（verdict="target_deleted"）告知提交者。审查历史行
          不删除，原始 claim / evidence_id 保留在行内。
        - queued 结构化 ReviewRequest 且 ``target_ids`` 含被删目标 → ``superseded``
          （复用既有终态），退出待办。裁决按目标 ID 关联：同名新建节点是新 ID，
          不会继承旧裁决。
        """
        for target_type, target_id in deleted:
            review_rows = con.execute(
                "SELECT review_id, caller_session_id, suggested_stage, claim "
                "FROM dag_call_reviews WHERE suggested_target_id = ? AND state = 'pending'",
                (target_id,),
            ).fetchall()
            for review_id, caller_session_id, suggested_stage, claim in review_rows:
                con.execute(
                    "UPDATE dag_call_reviews SET state = 'ignored' WHERE review_id = ?",
                    (review_id,),
                )
                self.store._insert_notification(
                    con,
                    kind="call_verdict",
                    subject_id=review_id,
                    recipient_session_id=str(caller_session_id or ""),
                    payload={
                        "verdict": "target_deleted",
                        "target_id": target_id,
                        "target_type": target_type,
                        "stage_kind": suggested_stage or "",
                        "reason": (rationale or "").strip(),
                        "claim": claim or "",
                    },
                )
            request_rows = con.execute(
                "SELECT request_id, target_ids FROM dag_review_requests "
                "WHERE state = 'queued'"
            ).fetchall()
            for request_id, target_ids_json in request_rows:
                try:
                    target_ids = json.loads(target_ids_json)
                except ValueError:
                    continue
                if target_id in target_ids:
                    con.execute(
                        "UPDATE dag_review_requests SET state = 'superseded', "
                        "updated_at = datetime('now') WHERE request_id = ?",
                        (request_id,),
                    )

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
            raise _Rejected(
                "process_graph_removed",
                "cross-graph links are gone with the process graph; evidence binds "
                "to delivery elements directly through stage binds",
            )
        if operation.graph is GraphKind.PROCESS:
            raise _Rejected(
                "process_graph_removed",
                "the process graph was removed (delivery-only orchestration); "
                "there is no scheduling frontier — run the work and let evidence "
                "bind to delivery stages",
            )
        state = states[operation.graph]

        # 按图分权：机理 DAG 由 Coordinator 设计，Supervisor 对 delivery 只读。
        if actor is GraphActor.SUPERVISOR and state.kind is GraphKind.DELIVERY:
            raise _Rejected(
                "actor_forbidden",
                "the supervisor is read-only on the delivery DAG",
            )

        if isinstance(operation, (AddNode, AddEdge)):
            self._check_element_graph_kind(state.kind, operation)
        if (
            actor is not GraphActor.HARNESS
            and state.kind is GraphKind.DELIVERY
            and isinstance(operation, (AddNode, AddEdge))
        ):
            # 证据派生保护：模型只能以 proposed/rejected/inconclusive 创建
            # delivery 元素，派生证据位与更高级别由 harness 确定性写入；
            # 阶段契约同理——模型只能声明 pending 阶段，阶段状态/ref 由
            # harness 的阶段绑定推进。
            element = operation.node if isinstance(operation, AddNode) else operation.edge
            derived_in_metadata = set(element.metadata) & _DERIVED_EVIDENCE_FIELDS
            derived_flags = (
                {key for key in _DERIVED_EVIDENCE_FIELDS if getattr(element, key, None) is True}
                if isinstance(element, ElementaryStepEdge)
                else set()
            )
            level = getattr(element, "evidence_level", "proposed")
            non_pending_stages = [
                stage.kind.value
                for stage in getattr(element, "stages", [])
                if stage.status is not StageStatus.PENDING or stage.ref is not None
            ]
            if (
                level not in _MODEL_SETTABLE_EVIDENCE_LEVELS
                or derived_in_metadata
                or derived_flags
                or non_pending_stages
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
            if state.kind is GraphKind.DELIVERY:
                node_name = getattr(node, "name", getattr(node, "label", "")).strip()
                if not node_name:
                    raise _Rejected("invalid_operation", "species name cannot be empty")
                for existing in state.nodes.values():
                    existing_name = getattr(existing, "name", getattr(existing, "label", "")).strip()
                    if existing_name == node_name:
                        raise _Rejected("duplicate_name", f"species name {node_name!r} already exists")
            state.nodes[node.node_id] = node
            state.node_created[node.node_id] = state.revision + 1
            touched.add(state.kind)
            return
        if isinstance(operation, AddEdge):
            edge = operation.edge
            if edge.edge_id in state.edges:
                raise _Rejected("duplicate_id", f"edge {edge.edge_id!r} already exists")
            if state.kind is GraphKind.DELIVERY:
                edge_name = getattr(edge, "name", getattr(edge, "label", "")).strip()
                if edge_name:
                    for existing in state.edges.values():
                        existing_name = getattr(existing, "name", getattr(existing, "label", "")).strip()
                        if existing_name == edge_name:
                            raise _Rejected("duplicate_name", f"step name {edge_name!r} already exists")
            state.edges[edge.edge_id] = edge
            state.edge_created[edge.edge_id] = state.revision + 1
            touched.add(state.kind)
            return
        if isinstance(operation, RemoveEdge):
            self._remove_edge(state, operation)
            touched.add(state.kind)
            return
        if isinstance(operation, RemoveNode):
            self._remove_node(state, operation)
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
                isinstance(element, (SpeciesNode, OccurrenceNode))
                if kind is GraphKind.DELIVERY
                else not isinstance(element, (SpeciesNode, OccurrenceNode))
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
                "species/elementary_step"
                if kind is GraphKind.DELIVERY
                else process_types
            )
            raise _Rejected(
                "invalid_operation",
                f"{type_name!r} does not belong on the {kind.value} graph; "
                f"expected {expected}",
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
            matches = difflib.get_close_matches(element_id, list(elements.keys()), n=2, cutoff=0.35)
            suggestion = f" Did you mean '{matches[0]}'?" if matches else ""
            raise _Rejected(
                "missing_target",
                f"{id_key} {element_id!r} does not exist.{suggestion} Available {id_key}s: {sorted(elements.keys())}"
            )
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
        # 删边放开（任意端点状态），但批次必须带 rationale（在
        # _apply_transaction 入口强制），被删的边留在变更日志里供审计。
        if operation.edge_id not in state.edges:
            matches = difflib.get_close_matches(operation.edge_id, list(state.edges.keys()), n=2, cutoff=0.35)
            suggestion = f" Did you mean '{matches[0]}'?" if matches else ""
            raise _Rejected(
                "missing_target",
                f"edge {operation.edge_id!r} does not exist.{suggestion} Available edges: {sorted(state.edges.keys())}"
            )
        del state.edges[operation.edge_id]
        state.edge_created.pop(operation.edge_id, None)

    @staticmethod
    def _remove_node(state: _GraphState, operation: RemoveNode) -> None:
        # 删节点前必须已无连线：有入边或出边时拒绝并列出关联边标识，让
        # agent 先在同一原子批次内删相关边再删节点——不提供隐式级联删除。
        if operation.node_id not in state.nodes:
            matches = difflib.get_close_matches(operation.node_id, list(state.nodes.keys()), n=2, cutoff=0.35)
            suggestion = f" Did you mean '{matches[0]}'?" if matches else ""
            raise _Rejected(
                "missing_target",
                f"node {operation.node_id!r} does not exist.{suggestion} Available nodes: {sorted(state.nodes.keys())}"
            )
        linked = sorted(
            {
                getattr(edge, "name", "") or edge.edge_id
                for edge in state.edges.values()
                if edge.source_node_id == operation.node_id
                or edge.target_node_id == operation.node_id
            }
        )
        if linked:
            raise _Rejected(
                "node_has_edges",
                f"node {operation.node_id!r} still has edges; remove them first "
                f"in the same batch: {', '.join(linked)}",
            )
        del state.nodes[operation.node_id]
        state.node_created.pop(operation.node_id, None)

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

    def _validate_structure(self, con: sqlite3.Connection, state: _GraphState) -> None:
        if state.kind is GraphKind.DELIVERY:
            seen_nodes: set[str] = set()
            for node in state.nodes.values():
                name = getattr(node, "name", getattr(node, "label", "")).strip()
                if name:
                    if name in seen_nodes:
                        raise _Rejected("duplicate_name", f"duplicate species name {name!r}")
                    seen_nodes.add(name)
            seen_edges: set[str] = set()
            for edge in state.edges.values():
                name = getattr(edge, "name", getattr(edge, "label", "")).strip()
                if name:
                    if name in seen_edges:
                        raise _Rejected("duplicate_name", f"duplicate step name {name!r}")
                    seen_edges.add(name)
        for edge in state.edges.values():
            if edge.source_node_id not in state.nodes or edge.target_node_id not in state.nodes:
                raise _Rejected("dangling_edge", f"edge {edge.edge_id!r} has a missing endpoint")
            if edge.source_node_id == edge.target_node_id:
                raise _Rejected("cycle", f"edge {edge.edge_id!r} is a self-loop")
        for node in state.nodes.values():
            for ref in node.refs:
                self._validate_ref(con, ref)
        for edge in state.edges.values():
            for ref in edge.refs:
                self._validate_ref(con, ref)
        self._validate_acyclic(state)

    def _validate_ref(self, con: sqlite3.Connection, ref: GraphRef) -> None:
        if ref.ref_type == "species":
            row = con.execute(
                "SELECT 1 FROM dag_species WHERE species_id = ?", (ref.ref_id,)
            ).fetchone()
        elif ref.ref_type in ("tool_result", "file"):
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
                # compute_jobs 已迁到中央 compute.db（不再属于会话库）
                row = self._find_compute_job(job_id)
        else:  # GraphRef validation should make this unreachable.
            row = None
        if row is None:
            raise _Rejected(
                "invalid_reference",
                f"{ref.ref_type} reference {ref.ref_id!r} does not resolve",
            )

    def _find_compute_job(self, job_id: int):
        """compute_job 引用的存在性校验打中央 compute.db；库不存在即不存在。"""
        from cloudra.persistence.database import ComputeDB
        from cloudra.services.compute_store import get_compute_job

        db = ComputeDB(data_dir=self.store.db.data_dir)
        try:
            if not os.path.isfile(db.path) or os.path.getsize(db.path) == 0:
                return None
        except OSError:
            return None
        return get_compute_job(db, job_id)

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
    # 各有专列，stages 也有专列（读取侧 _read_element_stages 以专列为准）。
    # 读取侧 parse_dag_node/parse_dag_edge 对新旧形状双兼容。
    _PAYLOAD_COLUMN_EXCLUDE = {"node_id", "edge_id", "source_node_id", "target_node_id",
                               "node_type", "edge_type", "label", "refs", "payload", "stages"}

    @staticmethod
    def _payload_column(element: "DagNode | DagEdge") -> str:
        return _canonical_json(
            element.model_dump(mode="json", exclude=DagEngine._PAYLOAD_COLUMN_EXCLUDE)
        )

    @staticmethod
    def _stages_column(element: "DagNode | DagEdge") -> str:
        # process 元素没有 stages 字段，落空数组保持列语义一致
        return _canonical_json(
            [stage.model_dump(mode="json") for stage in getattr(element, "stages", [])]
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
                    graph_id, node_id, node_type, label, refs, payload, stages,
                    created_revision, updated_revision
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    state.graph_id,
                    node.node_id,
                    node.node_type,
                    node.label,
                    _canonical_json([ref.model_dump(mode="json") for ref in node.refs]),
                    DagEngine._payload_column(node),
                    DagEngine._stages_column(node),
                    state.node_created[node.node_id],
                    state.revision,
                ),
            )
        for edge in state.edges.values():
            con.execute(
                """
                INSERT INTO dag_edges(
                    graph_id, edge_id, source_node_id, target_node_id, edge_type,
                    label, refs, payload, stages, created_revision, updated_revision
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    DagEngine._stages_column(edge),
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
