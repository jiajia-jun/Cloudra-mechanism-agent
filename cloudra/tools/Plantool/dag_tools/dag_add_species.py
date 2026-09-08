"""dag_add_species: AddNode(delivery SpeciesNode)."""

from __future__ import annotations

import uuid
from typing import Any

from pydantic import Field, model_validator

from cloudra.base.session_class import Session
from cloudra.base.tools_class import input_schema
from cloudra.core.agent import Agent
from cloudra.dag.models import AddNode, OrchestrationMode, SpeciesNode
from cloudra.tools.Plantool.dag_tools._common import DagToolBase, DagToolOutput, fail, mutation_output


class DagAddSpeciesInput(input_schema):
    name: str = Field(default="", description="Human-readable species system name.")
    label: str | None = Field(default=None, description="Species label (alias for name).")
    smiles: str | None = Field(default=None, description="Optional SMILES.")
    node_id: str | None = Field(default=None, description="Optional node id (auto-generated if omitted).")
    role: str | None = Field(default=None, description="Legacy role (ignored).")
    required: bool | None = Field(default=None, description="Whether this species is required.")
    metadata: dict[str, Any] | None = Field(default=None, description="Optional extra attributes.")

    @model_validator(mode="after")
    def _validate_name(self):
        if not (self.name or self.label or "").strip():
            raise ValueError("name is required")
        return self


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
    subagent: Agent = None

    async def tool_call(
        self, user_input: DagAddSpeciesInput, session: Session
    ) -> DagToolOutput:
        if self._mode() is OrchestrationMode.STANDARD:
            return self._standard_disabled()
        clean_name = (user_input.name or user_input.label or "").strip()
        if not clean_name:
            return fail("dag_add_species", "species name cannot be empty")
        node_id = user_input.node_id or f"sp_{uuid.uuid4().hex[:8]}"
        kwargs: dict[str, Any] = {
            "node_id": node_id,
            "name": clean_name,
            "label": clean_name,
        }
        if user_input.smiles is not None:
            kwargs["smiles"] = user_input.smiles
        if user_input.required is not None:
            kwargs["required"] = user_input.required
        if user_input.metadata:
            kwargs["metadata"] = user_input.metadata
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


def get_class():
    return DagAddSpecies

