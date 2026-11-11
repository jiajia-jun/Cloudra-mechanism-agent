"""Agent tool for building a periodic solvent box with Packmol."""

import asyncio
from typing import Annotated, Any

from pydantic import Field, StringConstraints, model_validator

from cloudra.base.tools_class import Tool, input_schema, output_schema
from cloudra.persistence.workspace import resolve_tool_path

NonemptyPath = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
PositiveNumber = Annotated[float, Field(strict=True, gt=0, allow_inf_nan=False)]


class MDBoxComponent(input_schema):
    structure_path: NonemptyPath = Field(description='One explicit Cartesian template in XYZ, MOL, or SDF.')
    count: int = Field(strict=True, gt=0, description='Number of copies of the entire template.')


class MDBoxInput(input_schema):
    components: list[MDBoxComponent] = Field(min_length=1, description='Structure templates and exact copy counts.')
    output_dir: NonemptyPath = Field(description='New directory for the periodic geometry and build report.')
    initial_density_g_cm3: PositiveNumber | None = Field(
        default=None, description='Initial mass density in g/cm³. Builds a cube. Give exactly one of density or box lengths.'
    )
    box_lengths_angstrom: list[PositiveNumber] | None = Field(
        default=None, min_length=3, max_length=3,
        description='Three orthogonal box lengths in Å. Give exactly one of lengths or initial density.'
    )
    min_distance_angstrom: PositiveNumber = Field(
        default=2.0, description='Target minimum distance in Å between atoms of different copies, including across boundaries.'
    )
    seed: int | None = Field(
        default=None, strict=True, ge=1, le=2**31 - 1, description='Packmol random seed. Generated and recorded if omitted.'
    )

    @model_validator(mode='after')
    def validate_box_constraint(self):
        if (self.initial_density_g_cm3 is None) == (self.box_lengths_angstrom is None):
            raise ValueError('Give exactly one of initial_density_g_cm3 or box_lengths_angstrom')
        return self


class MDBoxOutput(output_schema):
    is_success: bool = True
    coordinates_path: str
    report_path: str
    box_lengths_angstrom: tuple[float, float, float]
    initial_density_g_cm3: float
    components: list[dict]
    min_distance_angstrom: float
    minimum_observed_distance_angstrom: float | None
    seed: int
    packmol_version: str | None = None
    density_reference: dict | None = None
    warnings: list[str] = Field(default_factory=list)


class MDBox(Tool):
    tool_id: str = 'md-box'
    tool_name: str = 'md_box'
    tool_description: str = (
        'Build an orthogonal periodic initial geometry from molecule templates with Packmol. '
        'Report composition, measured distances, initial density and any density warning. '
        'The result is coordinates and a box, without force-field topology or equilibration.'
    )
    input_schema: Any = MDBoxInput
    output_schema: Any = MDBoxOutput

    def is_write(self) -> bool:
        return True

    async def tool_call(self, user_input: MDBoxInput, session=None):
        from cloudra.tools.core.md_box import build_md_box

        options = user_input.model_dump()
        options['output_dir'] = resolve_tool_path(self, options['output_dir'])
        for component in options['components']:
            component['structure_path'] = resolve_tool_path(self, component['structure_path'])
        return MDBoxOutput(**await asyncio.to_thread(build_md_box, **options))
