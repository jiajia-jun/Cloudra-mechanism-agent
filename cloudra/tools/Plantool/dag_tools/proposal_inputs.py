"""Writable proposal DTOs; graph validity remains the controller's authority.

Preserve the delivery wire shape without exposing persistence/derived fields.
"""

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ProposalFields(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProposalSpeciesInput(BaseModel):
    name: str = Field(min_length=1, description="Human-readable species system name.")
    smiles: str | None = Field(default=None, description="Optional SMILES for the complex system.")
    model_config = ConfigDict(extra="forbid")


class ProposalStepInput(BaseModel):
    name: str = Field(min_length=1, description="Human-readable transformation step name.")
    from_: str = Field(alias="from", min_length=1, description="Source species system name.")
    to: str = Field(min_length=1, description="Target species system name.")
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    @model_validator(mode="before")
    @classmethod
    def _normalize_from_to(cls, data: Any) -> Any:
        if isinstance(data, dict):
            data = dict(data)
            if "source" in data and "from" not in data and "from_" not in data:
                data["from"] = data.pop("source")
            if "target" in data and "to" not in data:
                data["to"] = data.pop("target")
        return data


class ProposalSpecies(ProposalFields):
    node_type: Literal["species", "occurrence"] = "species"
    node_id: str = Field(min_length=1, description="Unique species occurrence id.")
    label: str = Field(default="", description="Human-readable species name.")
    name: str = Field(default="", description="Human-readable species name.")
    role: str | None = None
    smiles: str | None = Field(default=None, description="Species SMILES, including disconnected fragments if needed.")
    required: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict, description="Optional species annotations.")


class ProposalStep(ProposalFields):
    edge_type: Literal["elementary_step"]
    edge_id: str = Field(min_length=1, description="Unique elementary-step id; TS evidence belongs to this step.")
    source_node_id: str = Field(min_length=1, description="Reactant-side occurrence id.")
    target_node_id: str = Field(min_length=1, description="Product-side occurrence id.")
    label: str = ""
    required: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict, description="Optional step annotations.")


class ProposalChanges(ProposalFields):
    label: str | None = None
    annotations: str | list[str] | dict[str, Any] | None = None
    reason: str | None = None
    required: bool | None = None
    supersedes: str | None = None
    evidence_level: Literal["proposed", "rejected", "inconclusive"] | None = Field(
        default=None, description="Disposition only; rejected/inconclusive requires a reason.",
    )


class ProposalAddSpecies(ProposalFields):
    op: Literal["add_node"]
    graph: Literal["delivery"]
    node: ProposalSpecies


class ProposalAddStep(ProposalFields):
    op: Literal["add_edge"]
    graph: Literal["delivery"]
    edge: ProposalStep


class ProposalUpdateSpecies(ProposalFields):
    op: Literal["update_node"]
    graph: Literal["delivery"]
    node_id: str
    changes: ProposalChanges


class ProposalUpdateStep(ProposalFields):
    op: Literal["update_edge"]
    graph: Literal["delivery"]
    edge_id: str
    changes: ProposalChanges


ProposalOperation = Annotated[
    ProposalAddSpecies | ProposalAddStep | ProposalUpdateSpecies | ProposalUpdateStep,
    Field(discriminator="op"),
]
