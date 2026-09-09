"""dag_remove_node: RemoveNode (rationale required)."""

from __future__ import annotations

import asyncio
from typing import Any

from pydantic import Field

from cloudra.base.session_class import Session
from cloudra.base.tools_class import input_schema
from cloudra.core.agent import Agent
from cloudra.dag.models import GraphKind, OrchestrationMode, RemoveNode
from cloudra.tools.Plantool.dag_tools._common import (
    DagToolBase,
    DagToolOutput,
    fail,
    mutation_output,
    resolve_delivery_target,
)


class DagRemoveNodeInput(input_schema):
    name: str = Field(
        min_length=1,
        description="Species name or node id to delete from the delivery graph.",
    )
    reason: str = Field(
        min_length=1,
        description="Scientific reason for deletion (mandatory; stays in change log).",
    )


class DagRemoveNode(DagToolBase):
    tool_id: str = "t-dag-rm-node"
    tool_name: str = "dag_remove_node"
    tool_description: str = (
        "Delete one species node from the delivery DAG with a mandatory reason "
        "(research agents and Coordinator in dag_record or dag_guided). "
        "Input shape: {name: str, reason: str}. "
        "Key discipline: a node that still has incoming/outgoing steps is "
        "refused with the linked step names — remove those steps first "
        "(dag_remove_edge) rather than expecting an implicit cascade."
    )
    input_schema: Any = DagRemoveNodeInput
    output_schema: Any = DagToolOutput
    subagent: Agent = None

    async def tool_call(
        self, user_input: DagRemoveNodeInput, session: Session
    ) -> DagToolOutput:
        if self._mode() is OrchestrationMode.STANDARD:
            return self._standard_disabled()
        node_name = user_input.name.strip()
        rationale = user_input.reason.strip()
        if not node_name:
            return fail(self.tool_name, "remove_node requires a non-empty name")
        if not rationale:
            return fail(
                self.tool_name,
                "remove_node requires a non-empty reason explaining the deletion",
            )

        ctx = await self._prepare(session)
        snapshot = await asyncio.to_thread(ctx.engine.snapshot)
        node, status = resolve_delivery_target(snapshot, "node", node_name)
        if status == "not_found":
            return fail(self.tool_name, f"node {node_name!r} not found on delivery graph")
        if status == "ambiguous":
            return fail(
                self.tool_name,
                f"node name {node_name!r} is ambiguous; use the node id instead",
            )

        _, mutation = await self._apply(
            session,
            [
                RemoveNode(
                    op="remove_node",
                    graph=GraphKind.DELIVERY,
                    node_id=node.node_id,
                )
            ],
            rationale=rationale,
            prepared=ctx,
        )
        return mutation_output(self.tool_name, mutation, extra={"target_id": node.node_id})


def get_class():
    return DagRemoveNode
