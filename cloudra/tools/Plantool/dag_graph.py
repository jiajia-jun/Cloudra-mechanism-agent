"""Agent-facing, mode-gated access to the durable DAG pair."""

from __future__ import annotations

import asyncio
import json
from typing import Any, Literal

from pydantic import Field

from cloudra.base.session_class import Session
from cloudra.base.tools_class import Tool, input_schema, output_schema
from cloudra.core.agent import Agent
from cloudra.dag.completion import build_projection, evaluate_delivery
from cloudra.dag.controller import DagController
from cloudra.dag.engine import DagEngine
from cloudra.dag.models import (
    AddEdge,
    AddNode,
    AttachRef,
    DependencyEdge,
    GraphActor,
    GraphKind,
    GraphOperation,
    MutationBatch,
    OccurrenceNode,
    OrchestrationMode,
    PlannedNode,
    normalize_orchestration_mode,
)
from cloudra.dag.store import DagStore
from cloudra.persistence.database import ConversationDB

# 机理研究的起步骨架：Coordinator 的初始流程（分析需求 → 读 skill →
# 文献/领域共识 → 设计机理图）+ delivery 图的反应物/产物槽位。
# delivery 非空、或 process 上已有非 observed 计划节点时拒绝，避免覆盖已有图；
# harness 的 observed_tool_call 遥测单独不算「已建图」。
_TEMPLATE_PROCESS_NODES = [
    ("p_analyze", "需求分析：拆解用户目标，确认机理问题与完成判据"),
    ("p_skill", "读取相关 skill 与领域方法（机理 SOP）"),
    (
        "p_literature",
        "文献与领域共识搜集（可派 explorer/researcher；计算类子 Agent 须等机理提交与 Supervisor 排产）",
    ),
    ("p_delivery_design", "设计机理假设图：中间体与基元步（delivery DAG）"),
]
_TEMPLATE_PROCESS_EDGES = [
    ("dep_analyze_skill", "p_analyze", "p_skill"),
    ("dep_analyze_lit", "p_analyze", "p_literature"),
    ("dep_skill_design", "p_skill", "p_delivery_design"),
    ("dep_lit_design", "p_literature", "p_delivery_design"),
]
_TEMPLATE_DELIVERY_NODES = [
    ("occ_reactants", "reactant", "反应物（待填 SMILES/说明）"),
    ("occ_products", "product", "产物（待填 SMILES/说明）"),
]


def _blocks_init_from_template(snapshot: Any) -> bool:
    """delivery 有节点、或 process 上已有非观察计划节点 → 不可模板初始化。"""
    if snapshot.delivery.nodes:
        return True
    return any(
        node.node_type != "observed_tool_call" for node in snapshot.process.nodes
    )


# graph_kind 子图视图只保留排产/审计需要的字段。完整 refs/hash 对 Supervisor
# 几乎无用（attach_ref 时另用证据库），却把单页 view 撑到 20k+ 字符。
_VIEW_PAYLOAD_KEYS = (
    "status",
    "priority",
    "tool_name",
    "evidence_role",
    "evidence_level",
    "assignee",
    "delivery_target_type",
    "delivery_target_id",
    "reason",
    "blocked_reason",
    "unplanned",
    "role",
    "required",
    "supersedes",
    "saddle_supported",
    "short_irc_supported",
    "endpoint_a_minimum_supported",
    "endpoint_b_minimum_supported",
    "endpoint_direction_consistent",
    "endpoint_identity_matched",
    "thermochemistry_supported",
)
_ANNOTATION_VIEW_CHARS = 240


def _compact_view_node(node: dict[str, Any]) -> dict[str, Any]:
    payload = node.get("payload") or {}
    compact_payload = {
        key: payload[key] for key in _VIEW_PAYLOAD_KEYS if key in payload
    }
    annotations = payload.get("annotations")
    if annotations is not None:
        text = annotations if isinstance(annotations, str) else json.dumps(
            annotations, ensure_ascii=False, default=str
        )
        compact_payload["annotations"] = text[:_ANNOTATION_VIEW_CHARS]
    refs = node.get("refs") or []
    return {
        "node_id": node.get("node_id"),
        "node_type": node.get("node_type"),
        "label": node.get("label"),
        "payload": compact_payload,
        "n_refs": len(refs),
    }


def _compact_view_edge(edge: dict[str, Any]) -> dict[str, Any]:
    payload = edge.get("payload") or {}
    compact_payload = {
        key: payload[key] for key in _VIEW_PAYLOAD_KEYS if key in payload
    }
    return {
        "edge_id": edge.get("edge_id"),
        "source_node_id": edge.get("source_node_id"),
        "target_node_id": edge.get("target_node_id"),
        "edge_type": edge.get("edge_type"),
        "label": edge.get("label", ""),
        "payload": compact_payload,
        "n_refs": len(edge.get("refs") or []),
    }


def _node_index_entry(node: dict[str, Any]) -> dict[str, Any]:
    payload = node.get("payload") or {}
    return {
        "node_id": node.get("node_id"),
        "node_type": node.get("node_type"),
        "status": payload.get("status", "proposed"),
    }


class DagGraphInput(input_schema):
    action: Literal[
        "view", "mutate", "delivery_report", "init_from_template",
        "bind_evidence", "review_evidence", "message_supervisor",
    ] = Field(
        description="view reads a bounded projection; mutate submits one atomic batch; "
        "delivery_report evaluates coverage; init_from_template seeds the standard "
        "mechanism-study skeleton on empty graphs; bind_evidence mounts a finished "
        "tool call as delivery evidence; review_evidence (supervisor-only) adjudicates "
        "mounted evidence; message_supervisor (coordinator) sends feedback to the "
        "Supervisor without changing the graph."
    )
    message: str | None = Field(
        default=None,
        description=(
            "For message_supervisor: plain-text note to the Supervisor "
            "(request planning, report blockers, ask why frontier is empty, etc.)."
        ),
    )
    tool_call_id: str | None = Field(
        default=None,
        description=(
            "For bind_evidence: the tool_call_id of the finished call whose result "
            "becomes evidence. An observed_<hex> process node id works as an alias."
        ),
    )
    bind_target: str | None = Field(
        default=None,
        description="For bind_evidence/review_evidence: the delivery node or edge id.",
    )
    evidence_role: str | None = Field(
        default=None,
        description=(
            "For bind_evidence: what the evidence proves — one of "
            "intermediate_optimization, ts_optimization_frequency, short_irc, "
            "endpoint_a_optimization, endpoint_b_optimization, "
            "endpoint_direction_check, endpoint_identity_match, thermochemistry."
        ),
    )
    verdict: Literal["confirmed", "downgraded", "rejected"] | None = Field(
        default=None,
        description=(
            "For review_evidence (supervisor-only): confirmed keeps the level; "
            "downgraded lowers it one step; rejected vetoes the evidence. "
            "rationale is mandatory."
        ),
    )
    graph_kind: GraphKind | None = Field(
        default=None,
        description="For view only: return a bounded process or delivery subgraph instead of the normal projection.",
    )
    offset: int = Field(
        default=0,
        ge=0,
        description="For view with graph_kind: skip this many nodes (pagination over large graphs).",
    )
    node_ids: list[str] | None = Field(
        default=None,
        description=(
            "For view with graph_kind: return only these node_ids (plus edges among them). "
            "Prefer this over paging through the whole graph to inspect specific nodes."
        ),
    )
    status_filter: str | None = Field(
        default=None,
        description=(
            "For view with graph_kind: return only nodes whose payload.status equals this "
            "value (e.g. 'ready', 'failed'). Combines with node_ids."
        ),
    )
    include_observed: bool = Field(
        default=False,
        description=(
            "For view with graph_kind=process: include harness observed_tool_call nodes. "
            "Default false — those records dominate process graphs and are not schedulable "
            "work. Set true only when auditing unbound tool calls."
        ),
    )
    base_revisions: dict[str, int] | None = Field(
        default=None,
        description=(
            "Optional for mutate — leave it out. The harness pins the current revisions "
            "and retries automatically if the graph moved. Only supply this to assert a "
            "specific base revision (advanced); a mismatch then fails without retry."
        ),
    )
    operations: list[GraphOperation] = Field(
        default_factory=list,
        description=(
            "One atomic batch, applied in order. Each operation is a named command "
            "discriminated by 'op' (add_node/add_edge/remove_edge/update_node/"
            "update_edge/attach_ref/add_link); its parameters are explicit fields "
            "shown in the schema — e.g. add_node takes a full 'node' object whose "
            "fields (node_id/node_type/label/status/role/evidence_level/...) are "
            "self-documenting. Extra node attributes go to the node's 'metadata'."
        ),
    )
    rationale: str = Field(
        default="",
        description="Scientific or workflow reason for the mutation. Mandatory when the batch contains remove_edge.",
    )


class DagGraphOutput(output_schema):
    success: bool
    action: str
    result: dict[str, Any] = Field(default_factory=dict)
    accepted: bool | None = None
    rejection_code: str | None = None
    error: str = ""


class DagGraph(Tool):
    tool_id: str = "t-42"
    tool_name: str = "dag_graph"
    tool_description: str = (
        "Read or submit validated changes to the persistent process DAG and delivery/mechanism "
        "DAG (dag_record/dag_guided sessions only). The Coordinator designs the delivery DAG; "
        "the Supervisor maintains the process DAG; accepted delivery mutations wake the "
        "Supervisor to schedule work — execute frontier tasks (planned nodes whose "
        "dependencies are met and status is proposed or ready; do not require "
        "status=ready alone). "
        "message_supervisor (Coordinator only) sends a note to the Supervisor without "
        "mutating the graph. "
        "Graph records hold durable pointers, not calculation bodies; completion is "
        "evidence-derived.\n"
        "mutate submits one atomic batch applied in order and validated together, so an edge "
        "may reference nodes created earlier in the same batch. Each operation is a named "
        "command discriminated by 'op' (add_node/add_edge/remove_edge/update_node/update_edge/"
        "attach_ref/add_link) with explicit fields in the schema: add_node takes a full node "
        "object (extra attributes go to its metadata), add_edge an edge object, "
        "update_node/update_edge take id + changes. A rejected call returns the correct "
        'shape with the error; conventions: getskill("dag-operations").\n'
        "Key constraints:\n"
        "- evidence_level is harness-derived; a model may only set proposed/rejected/"
        "inconclusive. Planned nodes carrying tool_name + delivery_target_type + "
        "delivery_target_id + evidence_role bind tool calls to delivery elements; unbound "
        "calls stay observed_tool_call records.\n"
        "- Mount a finished calculation with bind_evidence(tool_call_id, bind_target, "
        "evidence_role): the harness resolves its registered tool_result, requires "
        "success, attaches and derives the level (observed_<hex> ids accepted).\n"
        "- remove_edge works on both graphs but the batch rationale is mandatory; on the "
        "process graph the Supervisor executes the removal after reviewing your rationale.\n"
        "- Prefer default view (frontier/blockers/gaps); graph_kind is compact (no full "
        "refs; process omits observed_tool_call unless include_observed).\n"
        "review_evidence is supervisor-only. "
        "init_from_template seeds the standard mechanism-study skeleton when delivery is "
        "empty and process has no planned nodes (observed_tool_call records alone do not "
        "block); fill species with update_node, then extend with mutate."
    )
    input_schema: Any = DagGraphInput
    output_schema: Any = DagGraphOutput
    subagent: Agent = None

    def is_read(self) -> bool:
        return True

    def is_write(self) -> bool:
        # 权限类别为 MANAGE（编排管理类工具）；写安全由 DAG engine 按 actor 强制分图。
        return False

    def is_manage(self) -> bool:
        return True

    def _mode(self) -> OrchestrationMode:
        return normalize_orchestration_mode(
            getattr(self.subagent, "orchestration_mode", OrchestrationMode.STANDARD)
        )

    async def tool_call(
        self,
        user_input: DagGraphInput,
        session: Session,
    ) -> DagGraphOutput:
        mode = self._mode()
        if mode is OrchestrationMode.STANDARD:
            return DagGraphOutput(
                success=False,
                action=user_input.action,
                error="dag_graph is disabled in standard orchestration mode",
            )

        conversation_id = getattr(self.subagent, "conversation_id", "default")
        caller_type = getattr(self.subagent, "type", "")
        caller_id = getattr(self.subagent, "id", "")

        if user_input.action == "message_supervisor":
            if caller_type == "supervisor":
                return DagGraphOutput(
                    success=False,
                    action="message_supervisor",
                    error="message_supervisor is for the Coordinator; you are the Supervisor.",
                )
            if caller_type != "coordinator" and caller_id != "a-0":
                return DagGraphOutput(
                    success=False,
                    action="message_supervisor",
                    error=(
                        "message_supervisor is Coordinator-only; "
                        "report blockers on your assigned process node or via AgentHub."
                    ),
                )
            msg = (user_input.message or "").strip()
            if not msg:
                return DagGraphOutput(
                    success=False,
                    action="message_supervisor",
                    error="message_supervisor requires a non-empty message.",
                )
            # 真正唤醒由 DagController.on_tool_finished → maybe_supervise 完成
            return DagGraphOutput(
                success=True,
                action="message_supervisor",
                accepted=True,
                result={"delivered": True, "message": msg[:2000]},
            )

        def _prepare_db_and_store():
            # 工具调用路径上不做 init() 的 schema 写，版本落后才迁移；
            # 全新库 migrate_if_needed 不建表，仍需 init() 兜底。
            # 同步 sqlite 调用统一 offload 到 worker 线程，busy 等待不占事件循环
            db = ConversationDB(conversation_id)
            if not db.migrate_if_needed():
                db.init()
            store = DagStore(db)
            store.ensure_bundle(session.id)
            return db, store, store.load_coverage_contract()

        db, store, contract = await asyncio.to_thread(_prepare_db_and_store)
        engine = DagEngine(store)
        actor = (
            GraphActor.SUPERVISOR
            if caller_type == "supervisor"
            else GraphActor.AGENT
        )

        if user_input.action == "init_from_template":
            # 同步 sqlite 读也走 worker 线程，busy 等待不能占用事件循环
            snapshot = await asyncio.to_thread(engine.snapshot)
            if _blocks_init_from_template(snapshot):
                return DagGraphOutput(
                    success=False,
                    action="init_from_template",
                    error=(
                        "init_from_template is only allowed while delivery is empty and "
                        "process has no planned nodes (observed_tool_call records alone "
                        "are OK)"
                    ),
                )
            operations: list[GraphOperation] = []
            for node_id, label in _TEMPLATE_PROCESS_NODES:
                operations.append(AddNode(
                    op="add_node",
                    graph="process",
                    node=PlannedNode(node_id=node_id, label=label),
                ))
            for edge_id, source, target in _TEMPLATE_PROCESS_EDGES:
                operations.append(AddEdge(
                    op="add_edge",
                    graph="process",
                    edge=DependencyEdge(
                        edge_id=edge_id,
                        source_node_id=source,
                        target_node_id=target,
                    ),
                ))
            for node_id, role, label in _TEMPLATE_DELIVERY_NODES:
                operations.append(AddNode(
                    op="add_node",
                    graph="delivery",
                    node=OccurrenceNode(node_id=node_id, label=label, role=role),
                ))
            def _apply_template():
                # load_bundle 也是同步 sqlite 读，连同批次构造一起放进 worker 线程
                return engine.apply_batch(
                    MutationBatch(
                        session_id=session.id,
                        # 起步骨架是系统定义的确定性引导，不是任何模型的声明，
                        # 用 harness 身份播种；之后 process 归 Supervisor、delivery 归 Coordinator。
                        actor=GraphActor.HARNESS,
                        actor_id="dag-template",
                        base_revisions=store.load_bundle().revisions,
                        operations=operations,
                        rationale=user_input.rationale or "initialize mechanism-study skeleton",
                    ),
                )

            mutation = await asyncio.to_thread(_apply_template)
            return DagGraphOutput(
                success=mutation.accepted,
                action="init_from_template",
                accepted=mutation.accepted,
                rejection_code=mutation.rejection_code,
                error=mutation.rejection_reason or "",
                result={
                    "mutation_id": mutation.mutation_id,
                    "revisions": mutation.revisions,
                },
            )

        if user_input.action == "mutate":
            if not user_input.operations:
                return DagGraphOutput(
                    success=False,
                    action="mutate",
                    error="mutate requires at least one operation",
                )
            explicit_revisions = user_input.base_revisions is not None

            def _apply_mutation():
                # 调用方未显式提供 revision 时，由 harness 固定当前版本并在
                # stale 时自动重试一次——与自身写入（_apply_harness）同等待遇，
                # 模型不再承担搬运 revision 的职责。显式提供者保留旧语义：
                # 版本不匹配即失败，让显式声明并发意图的调用方知晓冲突。
                revisions = user_input.base_revisions or store.load_bundle().revisions
                for attempt in range(2):
                    result = engine.apply_batch(
                        MutationBatch(
                            session_id=session.id,
                            actor=actor,
                            actor_id=getattr(self.subagent, "id", "agent"),
                            base_revisions=revisions,
                            operations=user_input.operations,
                            rationale=user_input.rationale,
                        ),
                    )
                    if (
                        result.accepted
                        or explicit_revisions
                        or result.rejection_code != "stale_revision"
                        or attempt == 1
                    ):
                        return result
                    revisions = store.load_bundle().revisions
                raise RuntimeError("unreachable")

            mutation = await asyncio.to_thread(_apply_mutation)
            derived: list[dict[str, Any]] = []
            if mutation.accepted:
                derived = await asyncio.to_thread(
                    self._rederive_retro_attachments,
                    db, session, mode, conversation_id, user_input.operations,
                )
            return DagGraphOutput(
                success=mutation.accepted,
                action="mutate",
                accepted=mutation.accepted,
                rejection_code=mutation.rejection_code,
                error=mutation.rejection_reason or "",
                result={
                    "mutation_id": mutation.mutation_id,
                    "revisions": mutation.revisions,
                    **({"derived": derived} if derived else {}),
                },
            )

        if user_input.action == "bind_evidence":
            missing = [
                name
                for name, value in (
                    ("tool_call_id", user_input.tool_call_id),
                    ("bind_target", user_input.bind_target),
                    ("evidence_role", user_input.evidence_role),
                )
                if not value
            ]
            if missing:
                return DagGraphOutput(
                    success=False,
                    action="bind_evidence",
                    error=f"bind_evidence requires: {', '.join(missing)}",
                )
            controller = DagController(
                db, session.id, mode, conversation_id=conversation_id
            )
            try:
                bound = await controller.bind_evidence_for_call(
                    user_input.tool_call_id,
                    user_input.bind_target,
                    user_input.evidence_role,
                )
            except Exception as exc:
                # 证据缺失/计算未成功/目标不存在等确定性拒绝，原文回报给模型自纠
                return DagGraphOutput(
                    success=False,
                    action="bind_evidence",
                    accepted=False,
                    error=str(exc),
                )
            return DagGraphOutput(
                success=True,
                action="bind_evidence",
                accepted=True,
                result=bound,
            )

        if user_input.action == "review_evidence":
            # Supervisor 对 delivery 只读：工具校验身份后由 harness 确定性下调等级
            if actor is not GraphActor.SUPERVISOR:
                return DagGraphOutput(
                    success=False,
                    action="review_evidence",
                    error=(
                        "review_evidence is supervisor-only; evidence vetoes are "
                        "applied deterministically by the harness after review"
                    ),
                )
            missing = [
                name
                for name, value in (
                    ("bind_target", user_input.bind_target),
                    ("verdict", user_input.verdict),
                    ("rationale", user_input.rationale),
                )
                if not value
            ]
            if missing:
                return DagGraphOutput(
                    success=False,
                    action="review_evidence",
                    error=f"review_evidence requires: {', '.join(missing)}",
                )
            controller = DagController(
                db, session.id, mode, conversation_id=conversation_id
            )
            try:
                reviewed = await controller.review_evidence(
                    user_input.bind_target,
                    user_input.verdict,
                    user_input.rationale,
                    reviewer=getattr(self.subagent, "id", "supervisor"),
                )
            except Exception as exc:
                return DagGraphOutput(
                    success=False,
                    action="review_evidence",
                    accepted=False,
                    error=str(exc),
                )
            return DagGraphOutput(
                success=True,
                action="review_evidence",
                accepted=True,
                result=reviewed,
            )

        # 同步 sqlite 读也走 worker 线程，busy 等待不能占用事件循环
        snapshot = await asyncio.to_thread(engine.snapshot)
        if user_input.action == "delivery_report":
            report = evaluate_delivery(snapshot.delivery, contract)
            return DagGraphOutput(
                success=True,
                action="delivery_report",
                result=report.model_dump(mode="json"),
            )

        if user_input.graph_kind is not None:
            graph = (
                snapshot.process
                if user_input.graph_kind is GraphKind.PROCESS
                else snapshot.delivery
            )
            raw = graph.model_dump(mode="json")
            nodes = list(raw["nodes"])
            omitted_observed = 0
            if (
                user_input.graph_kind is GraphKind.PROCESS
                and not user_input.include_observed
                and not user_input.node_ids
            ):
                kept = []
                for node in nodes:
                    if node.get("node_type") == "observed_tool_call":
                        omitted_observed += 1
                    else:
                        kept.append(node)
                nodes = kept
            if user_input.node_ids:
                wanted = set(user_input.node_ids)
                nodes = [node for node in nodes if node["node_id"] in wanted]
            if user_input.status_filter:
                nodes = [
                    node
                    for node in nodes
                    if (node.get("payload") or {}).get("status") == user_input.status_filter
                ]
            total_nodes = len(nodes)
            page = nodes[user_input.offset : user_input.offset + 50]
            allowed = {node["node_id"] for node in page}
            # 页外节点的轻量索引（id/type/status），避免为找 id 整图翻页；
            # 当前页已有完整摘要，不再重复进 index。
            index = [
                _node_index_entry(node)
                for node in nodes
                if node["node_id"] not in allowed
            ]
            edges = [
                _compact_view_edge(edge)
                for edge in raw["edges"]
                if edge["source_node_id"] in allowed
                and edge["target_node_id"] in allowed
            ][:100]
            result: dict[str, Any] = {
                "graph_id": raw.get("graph_id"),
                "graph_kind": raw.get("graph_kind"),
                "revision": raw.get("revision"),
                "nodes": [_compact_view_node(node) for node in page],
                "edges": edges,
                "total_nodes": total_nodes,
                "offset": user_input.offset,
            }
            if index:
                result["index"] = index
            if omitted_observed:
                result["omitted_observed_tool_calls"] = omitted_observed
                result["hint"] = (
                    "observed_tool_call nodes omitted; set include_observed=true "
                    "only if auditing unbound tool calls"
                )
            if user_input.node_ids or user_input.status_filter or user_input.include_observed:
                result["filters"] = {
                    **({"node_ids": user_input.node_ids} if user_input.node_ids else {}),
                    **({"status": user_input.status_filter} if user_input.status_filter else {}),
                    **({"include_observed": True} if user_input.include_observed else {}),
                }
            return DagGraphOutput(success=True, action="view", result=result)

        history = await asyncio.to_thread(engine.history, limit=8)
        projection = build_projection(
            snapshot,
            mode=mode,
            contract=contract,
            history=history,
        )
        return DagGraphOutput(
            success=True,
            action="view",
            result=projection.model_dump(mode="json"),
        )

    @staticmethod
    def _rederive_retro_attachments(
        db: ConversationDB,
        session: Session,
        mode: OrchestrationMode,
        conversation_id: str,
        operations: list[GraphOperation],
    ) -> list[dict[str, Any]]:
        """事后认领挂钩：批次里带 evidence_role 的 delivery attach_ref，
        逐个重跑确定性派生，让补挂的证据升级元素等级。"""
        claims = [
            op for op in operations
            if isinstance(op, AttachRef)
            and op.graph is GraphKind.DELIVERY
            and op.evidence_role
            and op.ref.ref_type == "tool_result"
        ]
        if not claims:
            return []
        controller = DagController(
            db, session.id, mode, conversation_id=conversation_id
        )
        derived: list[dict[str, Any]] = []
        for op in claims:
            try:
                changes = controller.rederive_delivery_element(
                    op.target_type,
                    op.target_id,
                    op.ref,
                    op.evidence_role,
                )
            except Exception:  # 派生失败不影响已接受的挂接，模型可从视图看到现状
                changes = None
            if changes:
                derived.append({
                    "target_type": op.target_type,
                    "target_id": op.target_id,
                    "changes": changes,
                })
        return derived


def get_class():
    return DagGraph
