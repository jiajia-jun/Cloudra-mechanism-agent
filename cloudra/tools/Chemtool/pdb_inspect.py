"""Inspect macromolecular structures without modifying the input."""
import asyncio
from typing import Any

from pydantic import Field, field_validator

from cloudra.base.tools_class import Tool, input_schema, output_schema
from cloudra.persistence.workspace import resolve_tool_path


class PDBInspectInput(input_schema):
    input_path: str = Field(description='PDB/mmCIF path, absolute or relative to the agent working directory.')
    model_index: int = Field(default=0, ge=0, description='Zero-based model index; default first model.')
    chains: list[str] | None = Field(default=None, description='Author chain IDs; omitted selects all chains.')
    interaction_overrides: dict[str, float] = Field(default_factory=dict,
        description='Normally omit. Override documented PLIP water/metal parameters only with research justification; distances Å, angles degrees.')

    @field_validator('interaction_overrides')
    @classmethod
    def valid_rules(cls, value):
        from cloudra.tools.core.pdb_interactions import validate_interaction_overrides
        validate_interaction_overrides(value)
        return value


class PDBInspectOutput(output_schema):
    is_success: bool
    structure_summary: dict = Field(default_factory=dict)
    components: list[dict] = Field(default_factory=list)
    missing_atoms: list[dict] = Field(default_factory=list)
    internal_gaps: list[dict] = Field(default_factory=list)
    n_terminal_gaps: list[dict] = Field(default_factory=list)
    c_terminal_gaps: list[dict] = Field(default_factory=list)
    water_candidates: list[dict] = Field(default_factory=list)
    metal_sites: list[dict] = Field(default_factory=list)
    effective_rules: dict = Field(default_factory=dict)
    analysis_status: dict = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    message: str = ''


class PDBInspect(Tool):
    tool_id: str = 'pdb-inspect'
    tool_name: str = 'pdb_inspect'
    tool_description: str = (
        'Inspect PDB/mmCIF missing heavy atoms, internal and terminal missing segments, candidate waters and metal contacts. '
        'Copy residue_key and gap_id from results for selective cleaning. Geometry candidates are not established biological functions. '
        'Defaults come from installed mature backends; no distance guesses are required. Input files are unchanged.'
    )
    input_schema: Any = PDBInspectInput
    output_schema: Any = PDBInspectOutput

    def is_read(self):
        return True

    async def tool_call(self, user_input: PDBInspectInput, session=None):
        from cloudra.tools.core.pdb_workflow import inspect_structure
        options = user_input.model_dump()
        options['input_path'] = resolve_tool_path(self, user_input.input_path)
        return PDBInspectOutput(**await asyncio.to_thread(inspect_structure, options))
