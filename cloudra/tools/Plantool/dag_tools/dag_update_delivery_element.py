"""dag_update_delivery_element: UpdateNode/UpdateEdge on delivery by id lookup."""

from __future__ import annotations

import asyncio
from typing import Any

from pydantic import Field

from cloudra.base.session_class import Session
from cloudra.base.tool_actor import ToolActorContext
from cloudra.base.tools_class import input_schema
from cloudra.dag.models import OrchestrationMode, UpdateEdge, UpdateNode
from cloudra.tools.Plantool.dag_tools._common import (
    DagToolBase,
    DagToolOutput,
    fail,
    mutation_output,
)


class DagUpdateDeliveryElementInput(input_schema):
    name: str = Field(min_length=1, description="Delivery species or step name to update.")
    status: str | None = Field(default=None, description="Optional status.")
    reason: str | None = Field(default=None, description="Reason for the change.")


class DagUpdateDeliveryElement(DagToolBase):
    tool_id: str = "t-dag-upd-deliv"
    tool_name: str = "dag_update_delivery_element"
    tool_description: str = (
        "Update status/disposition on an existing delivery species or step "
        "(Coordinator in dag_record or dag_guided). "
        "Input shape: {name: str, status: str | None, reason: str | None}. "
        "Do not use for: renaming or patching smiles; identity is fixed at create time."
    )
    input_schema: Any = DagUpdateDeliveryElementInput
    output_schema: Any = DagToolOutput
    subagent: ToolActorContext | None = None

    async def tool_call(
        self, user_input: DagUpdateDeliveryElementInput, session: Session
    ) -> DagToolOutput:
        if self._mode() is OrchestrationMode.STANDARD:
            return self._standard_disabled()
        target_name = user_input.name.strip()
        if not target_name:
            return fail("dag_update_delivery_element", "must specify element name to update")
        ctx = await self._prepare(session)
        snapshot = await asyncio.to_thread(ctx.engine.snapshot)
        changes: dict[str, Any] = {}
        if user_input.status is not None:
            changes["status"] = user_input.status
        if user_input.reason is not None:
            changes["reason"] = user_input.reason
        if not changes:
            return fail(
                "dag_update_delivery_element",
                "dag_update_delivery_element requires at least one field to change (status or reason)",
            )
        node = next(
            (
                n for n in snapshot.delivery.nodes
                if n.node_id == target_name or getattr(n, "name", getattr(n, "label", "")).strip() == target_name
            ),
            None,
        )
        edge = next(
            (
                e for e in snapshot.delivery.edges
                if e.edge_id == target_name or getattr(e, "name", getattr(e, "label", "")).strip() == target_name
            ),
            None,
        )
        if node is not None:
            op = UpdateNode(
                op="update_node",
                graph="delivery",
                node_id=node.node_id,
                changes=changes,
            )
        elif edge is not None:
            op = UpdateEdge(
                op="update_edge",
                graph="delivery",
                edge_id=edge.edge_id,
                changes=changes,
            )
        else:
            return fail(
                "dag_update_delivery_element",
                f"no delivery node or edge with name/id {target_name!r}",
            )
        _, mutation = await self._apply(
            session,
            [op],
            rationale=f"update delivery {target_name}",
            prepared=ctx,
        )
        return mutation_output("dag_update_delivery_element", mutation)


def get_class():
    return DagUpdateDeliveryElement
