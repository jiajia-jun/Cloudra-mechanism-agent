"""dag_add_step: AddEdge(delivery ElementaryStepEdge)."""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

from pydantic import ConfigDict, Field

from cloudra.base.session_class import Session
from cloudra.base.tools_class import input_schema
from cloudra.core.agent import Agent
from cloudra.dag.models import AddEdge, ElementaryStepEdge, OrchestrationMode
from cloudra.tools.Plantool.dag_tools._common import DagToolBase, DagToolOutput, fail, mutation_output


class DagAddStepInput(input_schema):
    name: str = Field(default="", description="Human-readable step name.")
    from_: str | None = Field(default=None, alias="from", description="Source species name.")
    to: str | None = Field(default=None, description="Target species name.")
    edge_id: str | None = Field(default=None, description="Optional step id (auto-generated if omitted).")
    source_node_id: str | None = Field(default=None, description="Source node id (legacy).")
    target_node_id: str | None = Field(default=None, description="Target node id (legacy).")
    label: str | None = Field(default=None, description="Optional step label.")
    model_config = ConfigDict(populate_by_name=True)


class DagAddStep(DagToolBase):
    tool_id: str = "t-dag-step"
    tool_name: str = "dag_add_step"
    tool_description: str = (
        "Add one transformation step between species systems (Coordinator in dag_record or dag_guided). "
        "Input shape: {name: str, from: str, to: str}. "
        "Key discipline: step names must be unique; endpoints must exist on the delivery graph."
    )
    input_schema: Any = DagAddStepInput
    output_schema: Any = DagToolOutput
    subagent: Agent = None

    async def tool_call(
        self, user_input: DagAddStepInput, session: Session
    ) -> DagToolOutput:
        if self._mode() is OrchestrationMode.STANDARD:
            return self._standard_disabled()
        clean_name = (user_input.name or user_input.label or user_input.edge_id or "").strip()
        if not clean_name:
            return fail("dag_add_step", "step name cannot be empty")

        ctx = await self._prepare(session)
        snapshot = await asyncio.to_thread(ctx.engine.snapshot)
        nodes = snapshot.delivery.nodes

        if user_input.from_ is not None and user_input.to is not None:
            from_name = user_input.from_.strip()
            to_name = user_input.to.strip()
            if from_name == to_name:
                return fail("dag_add_step", f"step {clean_name!r} cannot be a self-loop")
            from_node = next(
                (n for n in nodes if getattr(n, "name", getattr(n, "label", "")).strip() == from_name),
                None,
            )
            to_node = next(
                (n for n in nodes if getattr(n, "name", getattr(n, "label", "")).strip() == to_name),
                None,
            )
            if from_node is None:
                return fail("dag_add_step", f"source species {from_name!r} not found on delivery graph")
            if to_node is None:
                return fail("dag_add_step", f"target species {to_name!r} not found on delivery graph")
            source_id = from_node.node_id
            target_id = to_node.node_id
        elif user_input.source_node_id and user_input.target_node_id:
            source_id = user_input.source_node_id
            target_id = user_input.target_node_id
            if source_id == target_id:
                return fail("dag_add_step", f"step {clean_name!r} cannot be a self-loop")
        else:
            return fail("dag_add_step", "endpoints 'from' and 'to' must be specified")

        edge_id = user_input.edge_id or f"step_{uuid.uuid4().hex[:8]}"
        edge_kwargs: dict[str, Any] = {
            "edge_id": edge_id,
            "name": clean_name,
            "label": clean_name,
            "source_node_id": source_id,
            "target_node_id": target_id,
        }
        _, mutation = await self._apply(
            session,
            [
                AddEdge(
                    op="add_edge",
                    graph="delivery",
                    edge=ElementaryStepEdge(**edge_kwargs),
                )
            ],
            rationale=f"add step {clean_name}",
            prepared=ctx,
        )
        return mutation_output("dag_add_step", mutation)


def get_class():
    return DagAddStep

