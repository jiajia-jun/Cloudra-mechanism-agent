"""Measure GROMACS RMSD and RMSF on a prepared trajectory."""

from typing import Any, ClassVar

from pydantic import Field

from cloudra.tools.core.md_observable import MDObservableInput, MDObservableTool, NonemptyText


class MDRMSDInput(MDObservableInput):
    group: NonemptyText = Field(description='Exact GROMACS group name for RMSD measurement.')
    fit_group: NonemptyText | None = Field(
        description='Exact group name for rotation and translation fitting to the TPR reference. Use null for no fitting.',
    )


class MDRMSD(MDObservableTool):
    tool_id: str = 'md-rmsd'
    tool_name: str = 'md_rmsd'
    tool_description: str = (
        'Calculate RMSD in nm from the TPR reference with gmx rms using TPR masses. '
        'Supply the measurement group and explicitly choose a fitting group or no fitting.'
    )
    input_schema: Any = MDRMSDInput
    native_command: ClassVar[str] = 'rms'
    x_unit: ClassVar[str] = 'ps'
    y_unit: ClassVar[str] = 'nm'

    def selected_groups(self, request: MDRMSDInput) -> tuple[str, ...]:
        if request.fit_group is None:
            return (request.group,)
        return (request.fit_group, request.group)

    def native_options(self, request: MDRMSDInput, group_ids: tuple[int, ...]) -> tuple[list[str], str | None]:
        fit = 'none' if request.fit_group is None else 'rot+trans'
        selection = ''.join(f'{group_id}\n' for group_id in group_ids)
        return ['-fit', fit], selection


class MDRMSFInput(MDObservableInput):
    group: NonemptyText = Field(description='Exact GROMACS group name for RMSF measurement and any fitting.')
    fit: bool = Field(
        default=True, description='Use a mass-weighted fit of the selected atoms to the TPR reference before measuring RMSF.',
    )
    per_residue: bool = Field(
        default=False, description='Report one RMSF value per residue instead of one per atom.',
    )


class MDRMSF(MDObservableTool):
    tool_id: str = 'md-rmsf'
    tool_name: str = 'md_rmsf'
    tool_description: str = (
        'Calculate positional RMSF in nm with gmx rmsf. The x-axis gives one-based atom indices '
        'or topology residue numbers with per_residue enabled.'
    )
    input_schema: Any = MDRMSFInput
    native_command: ClassVar[str] = 'rmsf'
    x_unit: ClassVar[str] = 'index'
    y_unit: ClassVar[str] = 'nm'

    def selected_groups(self, request: MDRMSFInput) -> tuple[str, ...]:
        return (request.group,)

    def native_options(self, request: MDRMSFInput, group_ids: tuple[int, ...]) -> tuple[list[str], str | None]:
        fit = '-fit' if request.fit else '-nofit'
        resolution = '-res' if request.per_residue else '-nores'
        return [fit, resolution], f'{group_ids[0]}\n'
