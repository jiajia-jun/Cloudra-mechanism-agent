"""Agent-facing, mode-gated access to the durable DAG pair."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from cloudra.agent import Agent
from cloudra.dag.completion import build_projection, evaluate_delivery
from cloudra.dag.engine import DagEngine
from cloudra.dag.models import (
    GraphActor,
    GraphKind,
    GraphOperation,
    MutationBatch,
    OrchestrationMode,
    normalize_orchestration_mode,
)
from cloudra.dag.store import DagStore
from cloudra.database import ConversationDB
from cloudra.session_class import Session
from cloudra.tools_class import Tool, input_schema, output_schema


class DagGraphInput(input_schema):
    action: Literal["view", "mutate", "delivery_report"] = Field(
        description="view reads a bounded projection; mutate submits one atomic batch; delivery_report evaluates coverage."
    )
    graph_kind: GraphKind | None = Field(
        default=None,
        description="For view only: return a bounded process or delivery subgraph instead of the normal projection.",
    )
    base_revisions: dict[str, int] | None = Field(
        default=None,
        description="Required for mutate; use the exact process and delivery revisions from the latest view.",
    )
    operations: list[GraphOperation] = Field(
        default_factory=list,
        description="Typed additive/update operations for one atomic mutation batch.",
    )
    rationale: str = Field(
        default="",
        description="Scientific or workflow reason for the mutation.",
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
        "Read or submit validated changes to the persistent process DAG and delivery/mechanism DAG. "
        "Use only in dag_record or dag_guided sessions. The Coordinator designs the delivery/mechanism "
        "DAG with mutate; the Supervisor reads both graphs and maintains the process DAG; accepted "
        "delivery mutations automatically wake the Supervisor to schedule work. Graph records contain "
        "durable pointers, not raw calculation bodies; delivery completion remains evidence-derived."
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

        if user_input.action == "mutate":
            if user_input.base_revisions is None or not user_input.operations:
                return DagGraphOutput(
                    success=False,
                    action="mutate",
                    error="mutate requires base_revisions and at least one operation",
                )
            # actor 从调用者身份派生；engine 再按 actor 强制分图（双保险）。
            actor = (
                GraphActor.SUPERVISOR
                if getattr(self.subagent, "type", "") == "supervisor"
                else GraphActor.AGENT
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
            return DagGraphOutput(
                success=mutation.accepted,
                action="mutate",
                accepted=mutation.accepted,
                rejection_code=mutation.rejection_code,
                error=mutation.rejection_reason or "",
                result={
                    "mutation_id": mutation.mutation_id,
                    "revisions": mutation.revisions,
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
            result["nodes"] = result["nodes"][:50]
            allowed = {node["node_id"] for node in result["nodes"]}
            result["edges"] = [
                edge
                for edge in result["edges"]
                if edge["source_node_id"] in allowed
                and edge["target_node_id"] in allowed
            ][:100]
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


def get_class():
    return DagGraph
