"""dag_remove_edge: RemoveEdge (rationale required)."""

from __future__ import annotations

import asyncio
from typing import Any, Literal

from pydantic import Field

from cloudra.base.session_class import Session
from cloudra.base.tools_class import input_schema
from cloudra.core.agent import Agent
from cloudra.dag.models import GraphKind, OrchestrationMode, RemoveEdge
from cloudra.tools.Plantool.dag_tools._common import DagToolBase, DagToolOutput, fail, mutation_output


class DagRemoveEdgeInput(input_schema):
    step: str | None = Field(
        default=None,
        description="Step name to delete from delivery graph.",
    )
    edge_id: str | None = Field(
        default=None,
        description="Edge id to delete (legacy).",
    )
    graph: Literal["process", "delivery"] = Field(
        default="delivery",
        description="Which DAG the edge belongs to.",
    )
    rationale: str = Field(
        ...,
        min_length=1,
        description="Scientific reason for deletion (mandatory; stays in change log).",
    )


class DagRemoveEdge(DagToolBase):
    tool_id: str = "t-dag-rm-edge"
    tool_name: str = "dag_remove_edge"
    tool_description: str = (
        "Delete one step from the delivery DAG with a mandatory rationale "
        "(Coordinator in dag_record or dag_guided). "
        "Input shape: {step: str, rationale: str}. "
        "Key discipline: deletion requires a non-empty rationale explaining why the step was removed."
    )
    input_schema: Any = DagRemoveEdgeInput
    output_schema: Any = DagToolOutput
    subagent: Agent = None

    async def tool_call(
        self, user_input: DagRemoveEdgeInput, session: Session
    ) -> DagToolOutput:
        if self._mode() is OrchestrationMode.STANDARD:
            return self._standard_disabled()
        if not user_input.rationale or not user_input.rationale.strip():
            return fail(self.tool_name, "remove_edge requires a non-empty rationale explaining the deletion")

        ctx = await self._prepare(session)
        target_edge_id = user_input.edge_id
        if user_input.step:
            step_name = user_input.step.strip()
            snapshot = await asyncio.to_thread(ctx.engine.snapshot)
            edge = next(
                (
                    e for e in snapshot.delivery.edges
                    if getattr(e, "name", getattr(e, "label", "")).strip() == step_name
                    or e.edge_id == step_name
                ),
                None,
            )
            if edge is None:
                return fail(self.tool_name, f"step {user_input.step!r} not found on delivery graph")
            target_edge_id = edge.edge_id

        if not target_edge_id:
            return fail(self.tool_name, "must specify 'step' to delete")

        _, mutation = await self._apply(
            session,
            [
                RemoveEdge(
                    op="remove_edge",
                    graph=GraphKind(user_input.graph),
                    edge_id=target_edge_id,
                )
            ],
            rationale=user_input.rationale,
            prepared=ctx,
        )
        return mutation_output(self.tool_name, mutation)


def get_class():
    return DagRemoveEdge

