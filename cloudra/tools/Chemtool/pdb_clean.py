"""Purpose-recorded, composable PDB/mmCIF cleaning options."""
import asyncio
from typing import Any, Literal

from pydantic import Field, field_validator

from cloudra.base.tools_class import Tool, output_schema
from cloudra.persistence.workspace import resolve_tool_path
from cloudra.tools.Chemtool.pdb_inspect import PDBInspectInput


class PDBCleanInput(PDBInspectInput):
    output_path: str = Field(description='New .pdb/.cif/.mmcif output file; existing files are never overwritten.')
    purpose: str = Field(min_length=1, description='Research purpose, recorded verbatim. Choose mode/options explicitly; text does not infer configuration.')
    mode: Literal['preserve', 'docking', 'md'] = 'preserve'
    waters: Literal['all', 'candidates', 'none'] | None = None
    ligands: Literal['all', 'none'] | None = None
    metals: Literal['all', 'none'] | None = None
    keep_residue_keys: list[str] = Field(default_factory=list, description='Copy exact residue_key values from inspect; override component policies within selected model/chains.')
    remove_residue_keys: list[str] = Field(default_factory=list, description='Copy exact residue_key values to remove; cannot overlap keep selections.')
    add_missing_atoms: bool | None = None
    add_missing_residues: Literal['none', 'internal', 'all'] | None = None
    gap_ids: list[str] | None = Field(default=None, description='Optional subset of detected gap_id values within requested gap types.')
    replace_nonstandard_residues: bool = False
    add_hydrogens: bool = False
    ph: float = Field(default=7.0, allow_inf_nan=False, description='Used only for requested hydrogen addition; does not optimize metal protonation or predict all pKa values.')
    altloc: str = Field(default='highest_occupancy', min_length=1, description='Choose highest occupancy per residue (ties deterministic), or one explicit altloc ID.')

    @field_validator('purpose')
    @classmethod
    def nonempty_purpose(cls, value):
        if not value.strip():
            raise ValueError('purpose must describe the research intent')
        return value

    @field_validator('altloc')
    @classmethod
    def valid_altloc(cls, value):
        if value != 'highest_occupancy' and (len(value) != 1 or value.isspace() or value == '\0'):
            raise ValueError('altloc must be highest_occupancy or a single explicit conformer ID')
        return value


class PDBCleanOutput(output_schema):
    is_success: bool
    output_path: str = ''
    change_log_path: str = ''
    effective_options: dict = Field(default_factory=dict)
    changes: list[dict] = Field(default_factory=list)
    unresolved: list[dict] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    message: str = ''


class PDBClean(Tool):
    tool_id: str = 'pdb-clean'
    tool_name: str = 'pdb_clean'
    tool_description: str = (
        'Write a new cleaned PDB/mmCIF plus a changes JSON log. Select mode from research purpose and override individual options. '
        'preserve keeps all components without repair; docking keeps candidate waters/all ligands/all metals and adds missing heavy atoms; '
        'md keeps all components and adds missing heavy atoms. All modes default to no missing-segment repair and no hydrogen addition. '
        'Exact residue selections override component policies; metal-containing cofactors stay intact. '
        'Explicitly request internal/all or selected gap repairs. Success means requested operations completed, not production simulation readiness.'
    )
    input_schema: Any = PDBCleanInput
    output_schema: Any = PDBCleanOutput

    def is_write(self):
        return True

    async def tool_call(self, user_input: PDBCleanInput, session=None):
        from cloudra.tools.core.pdb_workflow import clean_structure
        options = user_input.model_dump()
        for name in ('input_path', 'output_path'):
            options[name] = resolve_tool_path(self, options[name])
        return PDBCleanOutput(**await asyncio.to_thread(clean_structure, options))
