"""Writable proposal DTOs; graph validity remains the controller's authority.

Preserve the delivery wire shape without exposing persistence/derived fields.
"""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ProposalFields(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProposalSpeciesInput(BaseModel):
    name: str = Field(min_length=1, description="Human-readable species system name.")
    smiles: str | list[str] | None = Field(default=None,
        description="SMILES string for one species or dot-connected complex (B.C); a list [B, C] declares separated species.")
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

