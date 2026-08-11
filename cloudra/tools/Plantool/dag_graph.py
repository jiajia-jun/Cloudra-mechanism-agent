"""Agent-facing, mode-gated access to the durable DAG pair."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from cloudra.base.session_class import Session
from cloudra.base.tools_class import Tool, input_schema, output_schema
from cloudra.core.agent import Agent
from cloudra.dag.completion import build_projection, evaluate_delivery
from cloudra.dag.controller import DagController
from cloudra.dag.engine import DagEngine
from cloudra.dag.models import (
    GraphActor,
    GraphKind,
    GraphOperation,
    GraphRef,
    MutationBatch,
    OrchestrationMode,
    normalize_orchestration_mode,
)
from cloudra.dag.store import DagStore
from cloudra.persistence.database import ConversationDB

# 机理研究的起步骨架：Coordinator 的初始流程（分析需求 → 读 skill →
# 文献/领域共识 → 设计机理图）+ delivery 图的反应物/产物槽位。
# 只在两张图都为空时允许初始化，避免覆盖已有图。
_TEMPLATE_PROCESS_NODES = [
    ("p_analyze", "需求分析：拆解用户目标，确认机理问题与完成判据"),
    ("p_skill", "读取相关 skill 与领域方法（机理 SOP）"),
    ("p_literature", "文献与领域共识搜集（可派子 agent）"),
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


class DagGraphInput(input_schema):
    action: Literal["view", "mutate", "delivery_report", "init_from_template"] = Field(
        description="view reads a bounded projection; mutate submits one atomic batch; "
        "delivery_report evaluates coverage; init_from_template seeds the standard "
        "mechanism-study skeleton on empty graphs."
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
    base_revisions: dict[str, int] | None = Field(
        default=None,
        description=(
            "Required for mutate; use the revisions from the latest view. "
            "Only the graphs your operations actually touch are checked—delivery-only "
            "batches may omit process (harness recording advances it continuously)."
        ),
    )
    operations: list[GraphOperation] = Field(
        default_factory=list,
        description=(
            "One atomic batch, applied in order. Per-op data shapes (add_node/add_edge/"
            "update_node/update_edge/attach_ref/add_link) are documented in the tool description."
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
        "Supervisor to schedule work — only Supervisor-ready frontier tasks may be executed. "
        "Graph records hold durable pointers, not calculation bodies; completion is "
        "evidence-derived.\n"
        "mutate submits one atomic batch applied in order and validated together, so an edge "
        "may reference nodes created earlier in the same batch. Each operation is "
        '{"op": ..., "graph": "process"|"delivery"|null, "data": {...}}; ops: add_node / '
        "add_edge / remove_edge / update_node / update_edge / attach_ref / add_link. Full "
        'data shapes: getskill("dag-operations"); a rejected call returns the correct shape '
        "with the error.\n"
        "Key constraints:\n"
        "- evidence_level is harness-derived; a model may only set proposed/rejected/"
        "inconclusive. Planned nodes whose payload carries tool_name + delivery_target_type + "
        "delivery_target_id + evidence_role bind tool calls to delivery elements; unbound "
        "calls stay observed_tool_call records.\n"
        "- attach_ref ref_ids must be copied from real evidence in this conversation; invented "
        "ids are rejected. Attach a tool_result to a delivery element with evidence_role to "
        "claim pre-plan evidence (the harness re-derives the element's level).\n"
        "- remove_edge works on both graphs but the batch rationale is mandatory; on the "
        "process graph the Supervisor executes the removal after reviewing your rationale.\n"
        "- base_revisions come from your latest view; only touched graphs are checked — "
        "delivery-only batches may omit process.\n"
        "init_from_template seeds the standard mechanism-study skeleton on empty graphs "
        "(analysis → skill lookup → literature → mechanism design, plus reactant/product "
        "slots); fill species with update_node, then extend with mutate."
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
        db = ConversationDB(conversation_id).init()
        store = DagStore(db)
        store.ensure_bundle(session.id)
        engine = DagEngine(store)
        contract = store.load_coverage_contract()
        actor = (
            GraphActor.SUPERVISOR
            if getattr(self.subagent, "type", "") == "supervisor"
            else GraphActor.AGENT
        )

        if user_input.action == "init_from_template":
            snapshot = engine.snapshot()
            if snapshot.process.nodes or snapshot.delivery.nodes:
                return DagGraphOutput(
                    success=False,
                    action="init_from_template",
                    error="init_from_template is only allowed while both graphs are empty",
                )
            operations: list[GraphOperation] = []
            for node_id, label in _TEMPLATE_PROCESS_NODES:
                operations.append(GraphOperation(
                    op="add_node",
                    graph="process",
                    data={
                        "node_id": node_id,
                        "node_type": "workflow",
                        "label": label,
                        "payload": {"status": "proposed"},
                    },
                ))
            for edge_id, source, target in _TEMPLATE_PROCESS_EDGES:
                operations.append(GraphOperation(
                    op="add_edge",
                    graph="process",
                    data={
                        "edge_id": edge_id,
                        "source_node_id": source,
                        "target_node_id": target,
                        "edge_type": "dependency",
                    },
                ))
            for node_id, role, label in _TEMPLATE_DELIVERY_NODES:
                operations.append(GraphOperation(
                    op="add_node",
                    graph="delivery",
                    data={
                        "node_id": node_id,
                        "node_type": "occurrence",
                        "label": label,
                        "payload": {"role": role, "evidence_level": "proposed"},
                    },
                ))
            mutation = engine.apply_batch(
                MutationBatch(
                    session_id=session.id,
                    # 起步骨架是系统定义的确定性引导，不是任何模型的声明，
                    # 用 harness 身份播种；之后 process 归 Supervisor、delivery 归 Coordinator。
                    actor=GraphActor.HARNESS,
                    actor_id="dag-template",
                    base_revisions=store.load_bundle().revisions,
                    operations=operations,
                    rationale=user_input.rationale or "initialize mechanism-study skeleton",
                )
            )
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
            if user_input.base_revisions is None or not user_input.operations:
                return DagGraphOutput(
                    success=False,
                    action="mutate",
                    error="mutate requires base_revisions and at least one operation",
                )
            mutation = engine.apply_batch(
                MutationBatch(
                    session_id=session.id,
                    actor=actor,
                    actor_id=getattr(self.subagent, "id", "agent"),
                    base_revisions=user_input.base_revisions,
                    operations=user_input.operations,
                    rationale=user_input.rationale,
                )
            )
            derived: list[dict[str, Any]] = []
            if mutation.accepted:
                derived = self._rederive_retro_attachments(
                    db, session, mode, conversation_id, user_input.operations
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

        snapshot = engine.snapshot()
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
            result = graph.model_dump(mode="json")
            total_nodes = len(result["nodes"])
            result["nodes"] = result["nodes"][user_input.offset : user_input.offset + 50]
            allowed = {node["node_id"] for node in result["nodes"]}
            result["edges"] = [
                edge
                for edge in result["edges"]
                if edge["source_node_id"] in allowed
                and edge["target_node_id"] in allowed
            ][:100]
            result["total_nodes"] = total_nodes
            result["offset"] = user_input.offset
            return DagGraphOutput(success=True, action="view", result=result)

        projection = build_projection(
            snapshot,
            mode=mode,
            contract=contract,
            history=engine.history(limit=8),
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
            if op.op == "attach_ref"
            and op.graph is GraphKind.DELIVERY
            and op.data.get("evidence_role")
            and (op.data.get("ref") or {}).get("ref_type") == "tool_result"
        ]
        if not claims:
            return []
        controller = DagController(
            db, session.id, mode, conversation_id=conversation_id
        )
        derived: list[dict[str, Any]] = []
        for op in claims:
            try:
                ref = GraphRef.model_validate(op.data["ref"])
                changes = controller.rederive_delivery_element(
                    op.data.get("target_type"),
                    op.data.get("target_id"),
                    ref,
                    op.data["evidence_role"],
                )
            except Exception:  # 派生失败不影响已接受的挂接，模型可从视图看到现状
                changes = None
            if changes:
                derived.append({
                    "target_type": op.data.get("target_type"),
                    "target_id": op.data.get("target_id"),
                    "changes": changes,
                })
        return derived


def get_class():
    return DagGraph
