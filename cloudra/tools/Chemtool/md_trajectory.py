"""Inspect saved coordinate frames with GROMACS."""

import asyncio
from collections import deque
from pathlib import Path
from typing import Annotated, Any

from pydantic import Field, StringConstraints

from cloudra.base.tools_class import Tool, input_schema, output_schema
from cloudra.persistence.workspace import resolve_tool_path
from cloudra.tools.core.gromacs import GromacsError, check_trajectory_atom_count, gromacs_failure, start_gromacs

NonemptyPath = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class MDTrajectoryInput(input_schema):
    trajectory_path: NonemptyPath = Field(description='Saved GROMACS coordinate trajectory, such as XTC or TRR.')
    topology_path: NonemptyPath | None = Field(
        default=None, description='Matching TPR with the same atoms in the same order, for GROMACS bond-length checks.',
    )


class MDTrajectoryOutput(output_schema):
    is_success: bool
    message: str = ''
    atom_count: int | None = None
    frame_count: int | None = Field(default=None, description='Number of readable frames containing coordinates.')
    first_time_ps: float | None = Field(default=None, allow_inf_nan=False)
    last_time_ps: float | None = Field(
        default=None, allow_inf_nan=False,
        description='Native last time, estimated from the mean frame interval if GROMACS omits the final time.',
    )
    frame_interval_ps: float | None = Field(
        default=None, allow_inf_nan=False,
        description='Mean frame interval reported by GROMACS when it detects no cadence discrepancy.',
    )
    diagnostics: list[str] = Field(default_factory=list, description='Native warnings and other check diagnostics.')


def _inspect_trajectory(trajectory_path: str, topology_path: str | None) -> MDTrajectoryOutput:
    for path in (trajectory_path, topology_path):
        if path is not None and not Path(path).is_file():
            return MDTrajectoryOutput(is_success=False, message=f'Input file not found: {path}')

    args = ['check', '-f', trajectory_path]
    if topology_path is not None:
        trajectory_atoms, mismatch = check_trajectory_atom_count(trajectory_path, topology_path)
        if mismatch:
            return MDTrajectoryOutput(is_success=False, atom_count=trajectory_atoms, message=mismatch)
        args.extend(['-s1', topology_path])

    atom_count = frame_count = time_count = None
    first_time = last_time = interval = None
    diagnostics: list[str] = []
    incomplete = False
    tail: deque[str] = deque(maxlen=30)
    with start_gromacs(args) as process:
        assert process.stdout is not None
        for raw_line in process.stdout:
            tail.append(raw_line)
            # GROMACS can append the first bond diagnostic to a frame progress line.
            line, marker, detail = raw_line.strip().partition('Distance between atoms ')
            if marker and len(diagnostics) < 20:
                diagnostics.append(marker + detail)
            if line.startswith('# Atoms '):
                atom_count = int(line.split()[-1])
            elif line.startswith('Reading frame') and line.split()[2:4] == ['0', 'time']:
                first_time = float(line.split()[4])
            elif line.startswith('Last frame') and ' time ' in line:
                last_time = float(line.split()[-1])
            elif line.startswith('Time '):
                time_count = int(line.split()[1])
            elif line.startswith('Coords '):
                fields = line.split()
                frame_count = int(fields[1])
                if len(fields) == 3:
                    interval = float(fields[2])
            elif line.startswith(('WARNING', 'Warning', 'Timesteps at ', 'Number of atoms at ')):
                incomplete_frame = line.startswith('WARNING: Incomplete ')
                incomplete |= incomplete_frame
                if len(diagnostics) < 20 or incomplete_frame:
                    diagnostics.append(line)
        returncode = process.wait()

    message = ''
    if incomplete:
        message = 'GROMACS reported an incomplete trajectory frame.'
    elif returncode:
        message = f'GROMACS trajectory check failed (exit {returncode}). {gromacs_failure("".join(tail))}'
    elif not frame_count or not atom_count:
        message = 'GROMACS did not report any readable coordinate frames.'

    has_coordinate_times = bool(frame_count) and time_count == frame_count
    if has_coordinate_times and last_time is None and first_time is not None and interval is not None:
        # gmx check reports the mean interval over the observed first and last frame.
        last_time = round(first_time + (frame_count - 1) * interval, 3)
    return MDTrajectoryOutput(
        is_success=not message, message=message, atom_count=atom_count, frame_count=frame_count,
        first_time_ps=first_time if has_coordinate_times else None,
        last_time_ps=last_time if has_coordinate_times else None,
        frame_interval_ps=interval if has_coordinate_times else None, diagnostics=diagnostics,
    )


class MDTrajectory(Tool):
    tool_id: str = 'md-trajectory'
    tool_name: str = 'md_trajectory'
    tool_description: str = (
        'Inspect saved coordinate frames with GROMACS. Report atom count, frame count, saved time range and native '
        'diagnostics, with optional bond-length checks against the matching TPR.'
    )
    input_schema: Any = MDTrajectoryInput
    output_schema: Any = MDTrajectoryOutput

    def is_read(self) -> bool:
        return True

    async def tool_call(self, user_input: MDTrajectoryInput, session=None):
        trajectory_path = resolve_tool_path(self, user_input.trajectory_path)
        topology_path = resolve_tool_path(self, user_input.topology_path) if user_input.topology_path else None
        try:
            return await asyncio.to_thread(_inspect_trajectory, trajectory_path, topology_path)
        except (GromacsError, OSError) as exc:
            return MDTrajectoryOutput(is_success=False, message=str(exc))
        except ValueError:
            return MDTrajectoryOutput(is_success=False, message='Could not read the GROMACS trajectory summary.')
