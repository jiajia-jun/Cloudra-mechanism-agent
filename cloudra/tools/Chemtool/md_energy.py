"""Extract GROMACS energy time series and the native EDR statistics."""

import asyncio
import math
from pathlib import Path
from typing import Annotated, Any

from pydantic import BaseModel, Field, FiniteFloat, StringConstraints, model_validator

from cloudra.base.tools_class import Tool, input_schema, output_schema
from cloudra.persistence.workspace import resolve_tool_path
from cloudra.tools.core.gromacs import (
    GromacsError,
    gromacs_failure,
    incomplete_gromacs_warning,
    run_gromacs,
    stage_gromacs_xvg,
)

NonemptyText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class MDEnergyInput(input_schema):
    energy_path: NonemptyText = Field(description='Local GROMACS .edr file.')
    terms: list[NonemptyText] = Field(min_length=1, description='Exact GROMACS term names, e.g. Density or Potential.')
    output_path: NonemptyText = Field(description='New .xvg path for the selected time series.')
    start_ps: FiniteFloat | None = Field(default=None, description='Optional start time in ps.')
    end_ps: FiniteFloat | None = Field(default=None, description='Optional end time in ps.')

    @model_validator(mode='after')
    def validate_selection(self):
        if self.start_ps is not None and self.end_ps is not None and self.start_ps > self.end_ps:
            raise ValueError('start_ps must be less than or equal to end_ps')
        if any('\n' in name or '\r' in name for name in self.terms):
            raise ValueError('Each term must be a single GROMACS name')
        return self


class MDEnergyStatistic(BaseModel):
    term: str
    unit: str
    average: FiniteFloat
    error_estimate: FiniteFloat | None
    rmsd: FiniteFloat
    total_drift: FiniteFloat


class MDEnergyOutput(output_schema):
    is_success: bool = True
    message: str = ''
    output_path: str = ''
    statistics: list[MDEnergyStatistic] = Field(default_factory=list, description='Native gmx energy statistics, in XVG column order.')
    frame_count: int = 0
    first_time_ps: float | None = None
    last_time_ps: float | None = None


def _selection_menu(report: str) -> str:
    _, found, menu = report.partition('End your selection with an empty line or a zero.')
    if not found:
        return ''
    return menu.strip().split('\n\n', 1)[0].partition('\n')[2].strip()


def _xvg_series(path: Path) -> tuple[list[str], int, float, float]:
    labels = []
    frame_count = 0
    first_time = last_time = 0.0
    with path.open(encoding='utf-8') as stream:
        for line in stream:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if line.startswith('@'):
                series, marker, label = line.partition(' legend ')
                if marker and series.removeprefix('@ s').isdigit():
                    labels.append(label.strip().strip('"'))
                continue
            values = [float(value) for value in line.split()]
            if len(values) != len(labels) + 1 or not all(math.isfinite(value) for value in values):
                raise GromacsError('GROMACS returned an incomplete or non-finite XVG data row.')
            if frame_count == 0:
                first_time = values[0]
            last_time = values[0]
            frame_count += 1
    if frame_count == 0:
        raise GromacsError('No energy frames in the requested time interval.')
    return labels, frame_count, first_time, last_time


def _statistics(report: str, labels: list[str]) -> list[MDEnergyStatistic]:
    by_term = {}
    for line in report.splitlines():
        values, separator, unit = line.rpartition('  (')
        if not separator or not unit.endswith(')'):
            continue
        columns = values.rsplit(None, 4)
        if len(columns) == 5 and columns[0] in labels:
            term, average, error, rmsd, drift = columns
            by_term[term] = MDEnergyStatistic(
                term=term, unit=unit[:-1], average=float(average),
                error_estimate=None if error == '--' else float(error), rmsd=float(rmsd), total_drift=float(drift),
            )
    if by_term.keys() != set(labels):
        raise GromacsError('GROMACS did not report statistics for all selected terms.')
    return [by_term[label] for label in labels]


def _extract_energy(energy_path: Path, output_path: Path, request: MDEnergyInput) -> MDEnergyOutput:
    if not energy_path.is_file() or energy_path.suffix.lower() != '.edr':
        raise GromacsError(f'Expected a local GROMACS .edr file: {energy_path}')
    with stage_gromacs_xvg(output_path) as series:
        args = ['energy', '-f', str(energy_path), '-o', str(series), '-xvg', 'xmgrace']
        for flag, time in (('-b', request.start_ps), ('-e', request.end_ps)):
            if time is not None:
                args.extend([flag, str(time)])
        # GROMACS lists space-containing labels with hyphens in its interactive menu.
        names = [term.replace(' ', '-') for term in request.terms]
        process = run_gromacs(args, selection='\n'.join([*names, '0', '']))
        if warning := incomplete_gromacs_warning(process.stdout):
            raise GromacsError(warning)
        if process.returncode or not series.is_file():
            details = gromacs_failure(process.stdout)
            if details == 'No energy terms selected':
                details += '\n' + _selection_menu(process.stdout)
            raise GromacsError(f'GROMACS could not extract {request.terms}.\n{details}')

        labels, count, first, last = _xvg_series(series)
        if {label.replace(' ', '-') for label in labels} != set(names):
            raise GromacsError(
                f'GROMACS selected {labels} for {request.terms}. Use exact term names.\n'
                f'{_selection_menu(process.stdout)}'
            )
        statistics = _statistics(process.stdout, labels)
    return MDEnergyOutput(
        output_path=str(output_path), statistics=statistics, frame_count=count,
        first_time_ps=first, last_time_ps=last,
    )


class MDEnergy(Tool):
    tool_id: str = 'md-energy'
    tool_name: str = 'md_energy'
    tool_description: str = (
        'Extract named quantities from a local GROMACS EDR into an XVG file, '
        'with native averages, uncertainty estimates, RMSD and drift over the requested time window.'
    )
    input_schema: Any = MDEnergyInput
    output_schema: Any = MDEnergyOutput

    def is_write(self) -> bool:
        return True

    async def tool_call(self, user_input: MDEnergyInput, session=None):
        energy_path = Path(resolve_tool_path(self, user_input.energy_path))
        output_path = Path(resolve_tool_path(self, user_input.output_path))
        try:
            return await asyncio.to_thread(_extract_energy, energy_path, output_path, user_input)
        except (GromacsError, OSError, ValueError) as exc:
            return MDEnergyOutput(is_success=False, message=str(exc))
