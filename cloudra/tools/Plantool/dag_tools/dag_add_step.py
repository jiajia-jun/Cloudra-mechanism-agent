"""dag_add_step: AddEdge(delivery ElementaryStepEdge)."""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

from pydantic import ConfigDict, Field

from cloudra.base.session_class import Session
from cloudra.base.tool_actor import ToolActorContext
from cloudra.base.tools_class import input_schema
from cloudra.dag.models import (
    AddEdge,
    ElementaryStepEdge,
    OrchestrationMode,
    StageKind,
    StageState,
    StageStatus,
)
from cloudra.tools.Plantool.dag_tools._common import (
    DagToolBase,
    DagToolOutput,
    fail,
    mutation_output,
)


class DagAddStepInput(input_schema):
    name: str = Field(min_length=1, description="Human-readable step name.")
    from_: str = Field(alias="from", min_length=1, description="Source species name.")
    to: str = Field(min_length=1, description="Target species name.")
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
    subagent: ToolActorContext | None = None

    async def tool_call(
        self, user_input: DagAddStepInput, session: Session
    ) -> DagToolOutput:
        if self._mode() is OrchestrationMode.STANDARD:
            return self._standard_disabled()
        clean_name = user_input.name.strip()
        if not clean_name:
            return fail("dag_add_step", "step name cannot be empty")

        ctx = await self._prepare(session)
        snapshot = await asyncio.to_thread(ctx.engine.snapshot)
        nodes = snapshot.delivery.nodes

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

        edge_id = f"step_{uuid.uuid4().hex[:8]}"
        edge_kwargs: dict[str, Any] = {
            "edge_id": edge_id,
            "name": clean_name,
            "label": clean_name,
            "source_node_id": source_id,
            "target_node_id": target_id,
            "stages": [
                StageState(kind=StageKind.TS_GUESS, status=StageStatus.PENDING, required=False),
                StageState(kind=StageKind.TS_OPT, status=StageStatus.PENDING, required=True),
                StageState(kind=StageKind.FREQUENCY, status=StageStatus.PENDING, required=True),
            ],
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

