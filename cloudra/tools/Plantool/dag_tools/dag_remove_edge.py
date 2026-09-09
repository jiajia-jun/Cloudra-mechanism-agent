"""dag_remove_edge: RemoveEdge (rationale required)."""

from __future__ import annotations

import asyncio
from typing import Any

from pydantic import Field

from cloudra.base.session_class import Session
from cloudra.base.tools_class import input_schema
from cloudra.core.agent import Agent
from cloudra.dag.models import GraphKind, OrchestrationMode, RemoveEdge
from cloudra.tools.Plantool.dag_tools._common import (
    DagToolBase,
    DagToolOutput,
    fail,
    mutation_output,
    resolve_delivery_target,
)


class DagRemoveEdgeInput(input_schema):
    name: str = Field(
        min_length=1,
        description="Step name or edge id to delete from delivery graph.",
    )
    reason: str = Field(
        min_length=1,
        description="Scientific reason for deletion (mandatory; stays in change log).",
    )


class DagRemoveEdge(DagToolBase):
    tool_id: str = "t-dag-rm-edge"
    tool_name: str = "dag_remove_edge"
    tool_description: str = (
        "Delete one step from the delivery DAG with a mandatory reason "
        "(research agents and Coordinator in dag_record or dag_guided). "
        "Input shape: {name: str, reason: str}. "
        "Key discipline: deletion requires a non-empty reason explaining why the step was removed."
    )
    input_schema: Any = DagRemoveEdgeInput
    output_schema: Any = DagToolOutput
    subagent: Agent = None

    async def tool_call(
        self, user_input: DagRemoveEdgeInput, session: Session
    ) -> DagToolOutput:
        if self._mode() is OrchestrationMode.STANDARD:
            return self._standard_disabled()
        step_name = user_input.name.strip()
        rationale = user_input.reason.strip()
        if not step_name:
            return fail(self.tool_name, "remove_edge requires a non-empty name")
        if not rationale:
            return fail(self.tool_name, "remove_edge requires a non-empty reason explaining the deletion")

        ctx = await self._prepare(session)
        snapshot = await asyncio.to_thread(ctx.engine.snapshot)
        edge, status = resolve_delivery_target(snapshot, "edge", step_name)
        if status == "not_found":
            return fail(self.tool_name, f"step {step_name!r} not found on delivery graph")
        if status == "ambiguous":
            return fail(
                self.tool_name,
                f"step name {step_name!r} is ambiguous; use the edge id instead",
            )

        _, mutation = await self._apply(
            session,
            [
                RemoveEdge(
                    op="remove_edge",
                    graph=GraphKind.DELIVERY,
                    edge_id=edge.edge_id,
                )
            ],
            rationale=rationale,
            prepared=ctx,
        )
        return mutation_output(self.tool_name, mutation, extra={"target_id": edge.edge_id})


def get_class():
    return DagRemoveEdge
