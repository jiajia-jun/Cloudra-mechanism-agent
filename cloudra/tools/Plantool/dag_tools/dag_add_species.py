"""dag_add_species: AddNode(delivery OccurrenceNode)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from cloudra.base.session_class import Session
from cloudra.base.tools_class import input_schema
from cloudra.core.agent import Agent
from cloudra.dag.models import AddNode, OccurrenceNode, OrchestrationMode
from cloudra.tools.Plantool.dag_tools._common import DagToolBase, DagToolOutput, mutation_output


class DagAddSpeciesInput(input_schema):
    node_id: str = Field(description="New delivery occurrence node id.")
    label: str = Field(description="Human-readable species label.")
    role: Literal["reactant", "intermediate", "product"] = Field(
        description="Species role on the mechanism graph."
    )
    smiles: str | None = Field(default=None, description="Optional SMILES.")
    required: bool | None = Field(
        default=None, description="Whether this occurrence is required for coverage."
    )
    metadata: dict[str, Any] | None = Field(
        default=None, description="Optional extra attributes stored on the node."
    )


class DagAddSpecies(DagToolBase):
    tool_id: str = "t-dag-species"
    tool_name: str = "dag_add_species"
    tool_description: str = (
        "Add one delivery occurrence node with smiles and role at create time (Coordinator in dag_record or dag_guided). "
        "Use for: real reactants, intermediates, and products — especially replacing template placeholders "
        "occ_reactants/occ_products. "
        "Do not use for: Supervisor writes; patching smiles or role onto an existing node; "
        "operations arrays or nested arguments wrappers. "
        "Key discipline: set identity here, then connect with dag_add_step."
    )
    input_schema: Any = DagAddSpeciesInput
    output_schema: Any = DagToolOutput
    subagent: Agent = None

    async def tool_call(
        self, user_input: DagAddSpeciesInput, session: Session
    ) -> DagToolOutput:
        if self._mode() is OrchestrationMode.STANDARD:
            return self._standard_disabled()
        kwargs: dict[str, Any] = {
            "node_id": user_input.node_id,
            "label": user_input.label,
            "role": user_input.role,
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
                    node=OccurrenceNode(**kwargs),
                )
            ],
            rationale=f"add species {user_input.node_id}",
        )
        return mutation_output("dag_add_species", mutation)


def get_class():
    return DagAddSpecies
