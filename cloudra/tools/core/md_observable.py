"""Common GROMACS input and output handling for trajectory observables."""

import asyncio
import math
from pathlib import Path
from typing import Annotated, ClassVar

from pydantic import Field, FiniteFloat, StringConstraints, model_validator

from cloudra.base.tools_class import Tool, input_schema, output_schema
from cloudra.persistence.workspace import resolve_tool_path
from cloudra.tools.core.gromacs import (
    GromacsError,
    check_trajectory_atom_count,
    gromacs_failure,
    incomplete_gromacs_warning,
    run_gromacs,
    stage_gromacs_xvg,
)

NonemptyText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class MDObservableInput(input_schema):
    trajectory_path: NonemptyText = Field(description='GROMACS coordinate trajectory file in XTC, TRR, or TNG format.')
    topology_path: NonemptyText = Field(description='Matching .tpr file with the same atoms in the same order.')
    index_path: NonemptyText | None = Field(default=None, description='Optional .ndx file defining the named groups.')
    output_path: NonemptyText = Field(description='New .xvg path for the two-column numeric series.')
    start_ps: FiniteFloat | None = Field(default=None, description='Optional first trajectory time in ps.')
    end_ps: FiniteFloat | None = Field(default=None, description='Optional last trajectory time in ps.')

    @model_validator(mode='after')
    def validate_window(self):
        if self.start_ps is not None and self.end_ps is not None and self.start_ps > self.end_ps:
            raise ValueError('start_ps must be less than or equal to end_ps')
        return self


class MDObservableOutput(output_schema):
    is_success: bool
    message: str = ''
    output_path: str = ''
    point_count: int = Field(default=0, description='Number of numeric rows in the XVG.')
    x_unit: str = ''
    y_unit: str = ''
    diagnostics: list[str] = Field(default_factory=list, description='Warnings reported by GROMACS.')


def _resolve_group_ids(index_path: Path, requested: tuple[str, ...], atom_count: int) -> tuple[int, ...]:
    groups = {}
    nonempty = set()
    name = ''
    group_id = -1
    with index_path.open(encoding='utf-8') as index:
        for line in index:
            text = line.partition(';')[0].strip()
            if not text:
                continue
            if text.startswith('[') and text.endswith(']'):
                name = text[1:-1].strip()
                group_id += 1
                if name in groups and name in requested:
                    raise GromacsError(f'Group {name!r} appears more than once in the index.')
                groups[name] = group_id
            else:
                if group_id < 0 or any(not 1 <= int(value) <= atom_count for value in text.split()):
                    raise GromacsError(f'Invalid atom number in index group {name!r} for {atom_count} atoms.')
                nonempty.add(name)
    for group in requested:
        if group not in groups:
            raise GromacsError(f'Group {group!r} was not found. Available groups: {", ".join(groups)}')
        if group not in nonempty:
            raise GromacsError(f'Index group {group!r} is empty.')
    return tuple(groups[group] for group in requested)


def _curve_point_count(series: Path) -> int:
    count = 0
    with series.open(encoding='utf-8') as stream:
        for line in stream:
            fields = line.split()
            if not fields:
                continue
            if len(fields) != 2 or not all(math.isfinite(float(value)) for value in fields):
                raise GromacsError('GROMACS returned an incomplete or non-finite XVG row.')
            count += 1
    if not count:
        raise GromacsError('GROMACS returned no analysis points for the selected frames and groups.')
    return count


class MDObservableTool(Tool):
    output_schema: type[MDObservableOutput] = MDObservableOutput
    native_command: ClassVar[str]
    x_unit: ClassVar[str]
    y_unit: ClassVar[str]

    def is_write(self) -> bool:
        return True

    def selected_groups(self, request: MDObservableInput) -> tuple[str, ...]:
        raise NotImplementedError

    def native_options(self, request: MDObservableInput, group_ids: tuple[int, ...]) -> tuple[list[str], str | None]:
        raise NotImplementedError

    def _analyze(self, request: MDObservableInput) -> MDObservableOutput:
        trajectory = Path(resolve_tool_path(self, request.trajectory_path))
        topology = Path(resolve_tool_path(self, request.topology_path))
        index = Path(resolve_tool_path(self, request.index_path)) if request.index_path else None
        output = Path(resolve_tool_path(self, request.output_path))
        for path in (trajectory, topology, index):
            if path is not None and not path.is_file():
                raise GromacsError(f'Input file not found: {path}')
        if trajectory.suffix.lower() not in {'.xtc', '.trr', '.tng'}:
            raise GromacsError(f'Expected an XTC, TRR, or TNG trajectory: {trajectory}')
        if topology.suffix.lower() != '.tpr':
            raise GromacsError(f'Expected a matching GROMACS .tpr file: {topology}')
        atom_count, mismatch = check_trajectory_atom_count(str(trajectory), str(topology))
        if mismatch:
            raise GromacsError(mismatch)

        with stage_gromacs_xvg(output) as series:
            if index is None:
                index = series.parent / 'groups.ndx'
                process = run_gromacs(['make_ndx', '-f', str(topology), '-o', str(index)], selection='q\n')
                if process.returncode or not index.is_file():
                    raise GromacsError(gromacs_failure(process.stdout))
            group_ids = _resolve_group_ids(index, self.selected_groups(request), atom_count)
            flags, selection = self.native_options(request, group_ids)
            args = [self.native_command, '-f', str(trajectory), '-s', str(topology), '-n', str(index),
                    '-o', str(series), '-xvg', 'none', *flags]
            for flag, time in (('-b', request.start_ps), ('-e', request.end_ps)):
                if time is not None:
                    args.extend([flag, str(time)])
            process = run_gromacs(args, selection=selection)
            if warning := incomplete_gromacs_warning(process.stdout):
                raise GromacsError(warning)
            if process.returncode or not series.is_file():
                raise GromacsError(gromacs_failure(process.stdout))
            count = _curve_point_count(series)
            diagnostics = [line.strip() for line in process.stdout.splitlines()
                           if line.strip().startswith(('WARNING', 'Warning'))][:20]

        return MDObservableOutput(
            is_success=True, output_path=str(output), point_count=count,
            x_unit=self.x_unit, y_unit=self.y_unit, diagnostics=diagnostics,
        )

    async def tool_call(self, user_input: MDObservableInput, session=None):
        try:
            return await asyncio.to_thread(self._analyze, user_input)
        except (GromacsError, OSError, ValueError) as exc:
            return MDObservableOutput(is_success=False, message=str(exc))
