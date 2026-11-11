"""GROMACS radial distribution and mean square displacement tools."""

from typing import Annotated, Any, ClassVar

from pydantic import Field

from cloudra.tools.core.md_observable import MDObservableInput, MDObservableTool, NonemptyText

PositiveNumber = Annotated[float, Field(gt=0, allow_inf_nan=False)]


class MDRDFInput(MDObservableInput):
    reference_group: NonemptyText = Field(description='Exact index group name for the reference atoms.')
    group: NonemptyText = Field(description='Exact index group name for the atoms counted around the reference atoms.')
    bin_width_nm: PositiveNumber | None = Field(default=None, description='Radial bin width in nm. Uses GROMACS default if omitted.')
    max_distance_nm: PositiveNumber | None = Field(default=None, description='Maximum distance in nm. Uses GROMACS default if omitted.')


class MDRDF(MDObservableTool):
    tool_id: str = 'md-rdf'
    tool_name: str = 'md_rdf'
    tool_description: str = 'Calculate the normalized radial distribution function between two atom groups using periodic distances.'
    input_schema: Any = MDRDFInput
    native_command: ClassVar[str] = 'rdf'
    x_unit: ClassVar[str] = 'nm'
    y_unit: ClassVar[str] = '1'

    def selected_groups(self, request: MDRDFInput) -> tuple[str, ...]:
        return request.reference_group, request.group

    def native_options(self, request: MDRDFInput, group_ids: tuple[int, ...]) -> tuple[list[str], str | None]:
        reference, selected = group_ids
        flags = ['-ref', f'group {reference}', '-sel', f'group {selected}']
        if request.bin_width_nm is not None:
            flags.extend(['-bin', str(request.bin_width_nm)])
        if request.max_distance_nm is not None:
            flags.extend(['-rmax', str(request.max_distance_nm)])
        return flags, None


class MDMSDInput(MDObservableInput):
    group: NonemptyText = Field(description='Exact index group name for the atoms or molecules to track.')
    molecular_com: bool = Field(
        default=False, description='Track the center of mass of each molecule touched by the group, using every atom in each molecule.',
    )
    origin_spacing_ps: PositiveNumber | None = Field(
        default=None, description='Interval between time origins in ps. Use a multiple of the saved frame spacing. Default is 10 ps in GROMACS.',
    )
    max_lag_ps: PositiveNumber | None = Field(
        default=None, description='Maximum lag time in ps. Set for long trajectories to limit work and memory.',
    )


class MDMSD(MDObservableTool):
    tool_id: str = 'md-msd'
    tool_name: str = 'md_msd'
    tool_description: str = 'Calculate a mean square displacement curve for an atom group or individual molecular centers of mass.'
    input_schema: Any = MDMSDInput
    native_command: ClassVar[str] = 'msd'
    x_unit: ClassVar[str] = 'ps'
    y_unit: ClassVar[str] = 'nm^2'

    def selected_groups(self, request: MDMSDInput) -> tuple[str, ...]:
        return (request.group,)

    def native_options(self, request: MDMSDInput, group_ids: tuple[int, ...]) -> tuple[list[str], str | None]:
        selection = f'group {group_ids[0]}'
        if request.molecular_com:
            selection = f'whole_mol_com of {selection}'
        flags = ['-sel', selection]
        if request.origin_spacing_ps is not None:
            flags.extend(['-trestart', str(request.origin_spacing_ps)])
        if request.max_lag_ps is not None:
            flags.extend(['-maxtau', str(request.max_lag_ps)])
        return flags, None
