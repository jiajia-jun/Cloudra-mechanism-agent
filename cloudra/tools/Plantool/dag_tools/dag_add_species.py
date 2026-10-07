"""dag_add_species: AddNode(delivery SpeciesNode)."""

from __future__ import annotations

import uuid
from typing import Any

from pydantic import Field

from cloudra.base.session_class import Session
from cloudra.base.tool_actor import ToolActorContext
from cloudra.base.tools_class import input_schema
from cloudra.dag.models import (
    AddNode,
    OrchestrationMode,
    SpeciesNode,
    StageKind,
    StageState,
    StageStatus,
)
from cloudra.tools.Plantool.dag_tools._common import DagToolBase, DagToolOutput, fail, mutation_output


class DagAddSpeciesInput(input_schema):
    name: str = Field(min_length=1, description="Human-readable species system name.")
    smiles: str | None = Field(default=None, description="Optional SMILES for the species.")


class DagAddSpecies(DagToolBase):
    tool_id: str = "t-dag-species"
    tool_name: str = "dag_add_species"
    tool_description: str = (
        "Add one delivery species system node by name with optional smiles (Coordinator in dag_record or dag_guided). "
        "Input shape: {name: str, smiles: str | None}. "
        "Key discipline: species names must be unique within the delivery graph."
    )
    input_schema: Any = DagAddSpeciesInput
    output_schema: Any = DagToolOutput
    subagent: ToolActorContext | None = None

    async def tool_call(
        self, user_input: DagAddSpeciesInput, session: Session
    ) -> DagToolOutput:
        if self._mode() is OrchestrationMode.STANDARD:
            return self._standard_disabled()
        clean_name = user_input.name.strip()
        if not clean_name:
            return fail("dag_add_species", "species name cannot be empty")
        node_id = f"sp_{uuid.uuid4().hex[:8]}"
        kwargs: dict[str, Any] = {
            "node_id": node_id,
            "name": clean_name,
            "label": clean_name,
            "stages": [
                StageState(kind=StageKind.GEOMETRY, status=StageStatus.PENDING, required=True),
            ],
        }
        if user_input.smiles is not None:
            kwargs["smiles"] = user_input.smiles
        _, mutation = await self._apply(
            session,
            [
                AddNode(
                    op="add_node",
                    graph="delivery",
                    node=SpeciesNode(**kwargs),
                )
            ],
            rationale=f"add species {clean_name}",
        )
        return mutation_output("dag_add_species", mutation)
