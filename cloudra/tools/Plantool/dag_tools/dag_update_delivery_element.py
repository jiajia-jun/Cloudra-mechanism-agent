"""dag_update_delivery_element: UpdateNode/UpdateEdge on delivery by id lookup."""

from __future__ import annotations

import asyncio
from typing import Any

from pydantic import Field

from cloudra.base.session_class import Session
from cloudra.base.tools_class import input_schema
from cloudra.core.agent import Agent
from cloudra.dag.models import OrchestrationMode, UpdateEdge, UpdateNode
from cloudra.tools.Plantool.dag_tools._common import (
    DagToolBase,
    DagToolOutput,
    fail,
    mutation_output,
)


class DagUpdateDeliveryElementInput(input_schema):
    element_id: str = Field(description="Delivery node_id or edge_id to update.")
    label: str | None = Field(default=None, description="New label.")
    status: str | None = Field(default=None, description="Optional status (metadata on occurrences).")
    evidence_level: str | None = Field(
        default=None,
        description=(
            "Optional disposition only: proposed, rejected, or inconclusive. "
            "Cannot set structure_supported, saddle_supported, or endpoint_supported — harness-derived. "
            "Cannot set smiles or role here."
        ),
    )
    annotations: Any = Field(default=None, description="Free-text notes.")
    reason: str | None = Field(default=None, description="Reason for the change.")
    required: bool | None = Field(default=None, description="Whether the element is required.")
    supersedes: str | None = Field(default=None, description="Id this element supersedes.")


class DagUpdateDeliveryElement(DagToolBase):
    tool_id: str = "t-dag-upd-deliv"
    tool_name: str = "dag_update_delivery_element"
    tool_description: str = (
        "Update metadata on an existing delivery node or edge by element_id "
        "(Coordinator in dag_record or dag_guided). "
        "Use for: label, annotations, supersedes, and evidence_level proposed/rejected/inconclusive on placeholders. "
        "Do not use for: changing smiles or role (use dag_add_species + dag_add_step); "
        "structure/saddle/endpoint evidence levels; Supervisor writes. "
        "Key discipline: identity is fixed at create time — add new species instead of patching."
    )
    input_schema: Any = DagUpdateDeliveryElementInput
    output_schema: Any = DagToolOutput
    subagent: Agent = None

    async def tool_call(
        self, user_input: DagUpdateDeliveryElementInput, session: Session
    ) -> DagToolOutput:
        if self._mode() is OrchestrationMode.STANDARD:
            return self._standard_disabled()
        ctx = await self._prepare(session)
        snapshot = await asyncio.to_thread(ctx.engine.snapshot)
        changes: dict[str, Any] = {}
        for key in ("label", "status", "evidence_level", "reason", "required", "supersedes"):
            value = getattr(user_input, key)
            if value is not None:
                changes[key] = value
        if user_input.annotations is not None:
            changes["annotations"] = user_input.annotations
        if not changes:
            return fail(
                "dag_update_delivery_element",
                "dag_update_delivery_element requires at least one field to change",
            )
        node = next(
            (n for n in snapshot.delivery.nodes if n.node_id == user_input.element_id),
            None,
        )
        edge = next(
            (e for e in snapshot.delivery.edges if e.edge_id == user_input.element_id),
            None,
        )
        if node is not None:
            op = UpdateNode(
                op="update_node",
                graph="delivery",
                node_id=user_input.element_id,
                changes=changes,
            )
        elif edge is not None:
            op = UpdateEdge(
                op="update_edge",
                graph="delivery",
                edge_id=user_input.element_id,
                changes=changes,
            )
        else:
            return fail(
                "dag_update_delivery_element",
                f"no delivery node or edge with id {user_input.element_id!r}",
            )
        _, mutation = await self._apply(
            session,
            [op],
            rationale=f"update delivery {user_input.element_id}",
            prepared=ctx,
        )
        return mutation_output("dag_update_delivery_element", mutation)


def get_class():
    return DagUpdateDeliveryElement
