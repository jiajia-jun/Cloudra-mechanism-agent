"""The native xTB relaxed scan used by the existing chemistry-task ledger.

The manifest contains an immutable XYZ and a typed scan declaration.  Every
published point is matched to one native scan frame and one verbose optimization
and final-SCC block; an exit code or trajectory frame alone is not convergence.
"""
from __future__ import annotations

import hashlib
import math
import subprocess
from pathlib import Path

from cloudra.persistence.fs_utils import atomic_write_text
from cloudra.tools.core.conformer_catalog import content_digest
from cloudra.tools.core.run_dirs import next_run_dir
from cloudra.tools.core.structure_artifacts import read_xyz_atoms

_COORD_NAMES = {"bond": "distance", "angle": "angle", "dihedral": "dihedral"}
_HARTREE_TO_KCAL = 627.5094740631


def _xcontrol(scan, count: int) -> str:
    lines = ["$constrain", f" force constant={scan.force_constant:.12g}"]
    used = set()
    for index, row in enumerate(scan.scans, 1):
        if any(atom < 0 or atom >= count for atom in row.atoms):
            raise ValueError(f"scan coordinate {index} references an atom outside the bound XYZ")
        key = (row.coord_type, min(tuple(row.atoms), tuple(reversed(row.atoms))))
        if key in used:
            raise ValueError("duplicate scan coordinate")
        used.add(key)
        atoms = ",".join(str(atom + 1) for atom in row.atoms)
        lines.append(f" {_COORD_NAMES[row.coord_type]}: {atoms},{row.scan_start:.12g}")
    lines.append("$scan")
    if len(scan.scans) == 2:
        lines.append(f" mode={scan.mode}")
    for index, row in enumerate(scan.scans, 1):
        lines.append(f" {index}: {row.scan_start:.12g},{row.scan_end:.12g},{row.scan_steps}")
    lines.extend(["$opt", "$end", ""])
    return "\n".join(lines)


def _planned_targets(scan):
    rows = scan.scans
    samples = [
        [row.scan_start + (row.scan_end - row.scan_start) * i / (row.scan_steps - 1)
         for i in range(row.scan_steps)]
        for row in rows
    ]
    if len(rows) == 1:
        return [(1, [value]) for value in samples[0]]
    if scan.mode == 'concerted':
        return [(1, [left, right]) for left, right in zip(*samples)]
    return ([(1, [value, rows[1].scan_start]) for value in samples[0]]
            + [(2, [rows[0].scan_end, value]) for value in samples[1]])


def _frames(path: Path, symbols: list[str]) -> list[dict]:
    lines = path.read_text(errors='replace').splitlines()
    frames = []
    cursor = 0
    while cursor < len(lines):
        try:
            count = int(lines[cursor].strip())
            if count != len(symbols) or cursor + count + 1 >= len(lines):
                raise ValueError('scan frame atom count is inconsistent or truncated')
            comment = lines[cursor + 1].split()
            if len(comment) < 2 or comment[0] not in ('energy:', 'SCF'):
                raise ValueError('scan frame has no recognized native energy comment')
            energy = float(comment[1] if comment[0] == 'energy:' else comment[-1])
            if not math.isfinite(energy):
                raise ValueError('scan frame energy is nonfinite')
            positions = []
            for expected, line in zip(symbols, lines[cursor + 2:cursor + 2 + count]):
                parts = line.split()
                if len(parts) < 4 or parts[0].capitalize() != expected:
                    raise ValueError('scan frame atom identity/order differs from the input XYZ')
                point = [float(value) for value in parts[1:4]]
                if not all(map(math.isfinite, point)):
                    raise ValueError('scan frame has nonfinite coordinates')
                positions.append(point)
            frames.append(dict(energy_hartree=energy, positions=positions))
            cursor += count + 2
        except (IndexError, ValueError) as exc:
            raise ValueError(f'Invalid xTB scan trajectory at line {cursor + 1}: {exc}') from exc
    return frames


def _last_native_energy(text: str, label: str) -> float | None:
    value = None
    for line in text.splitlines():
        if label in line:
            parts = line.split()
            try:
                number = float(parts[parts.index(label.split()[-1]) + 1])
            except (ValueError, IndexError):
                number = None
            if number is not None and math.isfinite(number):
                value = number
    return value


def _point_logs(text: str) -> list[dict]:
    if 'RELAXED SCAN' not in text:
        return []
    scan_section = text.split('RELAXED SCAN', 1)[1]
    chunks = scan_section.split('Final Singlepoint')
    if len(chunks) < 2:
        return []
    result = []
    for index in range(len(chunks) - 1):
        optimization = chunks[index]
        singlepoint = chunks[index + 1].split('A N C O P T', 1)[0]
        # The final SCC block belongs to the point whose optimizer precedes it.
        total = _last_native_energy(singlepoint, ':: total energy')
        bias = _last_native_energy(singlepoint, ':: add. restraining')
        result.append(dict(
            geometry_converged=('GEOMETRY OPTIMIZATION CONVERGED' in optimization
                                and 'FAILED TO CONVERGE GEOMETRY OPTIMIZATION' not in optimization),
            scc_converged='convergence criteria satisfied' in singlepoint,
            biased_total_hartree=total, bias_energy_hartree=bias,
        ))
    return result


def _coordinate(row, positions):
    import numpy as np

    points = [np.asarray(positions[index], dtype=float) for index in row.atoms]
    if row.coord_type == 'bond':
        return float(np.linalg.norm(points[0] - points[1]))
    if row.coord_type == 'angle':
        left, right = points[0] - points[1], points[2] - points[1]
        product = float(np.linalg.norm(left) * np.linalg.norm(right))
        if product == 0:
            raise ValueError('degenerate scan angle')
        return float(math.degrees(math.acos(max(-1.0, min(1.0, float(left @ right) / product)))))
    first, middle, last = points[0] - points[1], points[2] - points[1], points[3] - points[2]
    axis = middle / np.linalg.norm(middle)
    left, right = first - first.dot(axis) * axis, last - last.dot(axis) * axis
    if np.linalg.norm(left) == 0 or np.linalg.norm(right) == 0:
        raise ValueError('degenerate scan dihedral')
    return float(math.degrees(math.atan2(float(np.cross(axis, left).dot(right)), float(left.dot(right)))))


def parse_xtb_scan(task, directory: Path, returncode: int) -> dict:
    from cloudra.tools.Chemtool.ts_guess import analyze_scan_profile

    source = directory / 'input.xyz'
    control = directory / 'scan.inp'
    log = directory / 'engine.out'
    trajectory = directory / 'xtbscan.log'
    text = log.read_text(errors='replace') if log.is_file() else ''
    symbols = [symbol for symbol, _ in read_xyz_atoms(str(source))]
    planned = _planned_targets(task.scan)
    native = _point_logs(text)
    issues = []
    try:
        frames = _frames(trajectory, symbols)
    except (OSError, ValueError) as exc:
        frames = []
        issues.append(str(exc))
    if len(native) != len(planned) or len(frames) != len(planned):
        issues.append(f'planned {len(planned)} points, found {len(native)} native point logs and {len(frames)} frames')
    points = []
    for index, ((segment, targets), frame, evidence) in enumerate(zip(planned, frames, native), 1):
        electronic = evidence['biased_total_hartree']
        bias = evidence['bias_energy_hartree']
        energy_resolved = (electronic is not None and bias is not None and
                           abs(electronic - bias - frame['energy_hartree']) < 1e-5)
        if not energy_resolved:
            issues.append(f'point {index} native energy and trajectory disagree or lack bias evidence')
        frame_path = directory / f'point_{index:04d}.xyz'
        atomic_write_text(str(frame_path), '\n'.join([str(len(symbols)), f'xTB scan point {index}',
            *[symbol + ' ' + ' '.join(f'{number:.14f}' for number in position)
              for symbol, position in zip(symbols, frame['positions'])]]) + '\n')
        try:
            actual = [_coordinate(row, frame['positions']) for row in task.scan.scans]
        except ValueError as exc:
            actual = []
            issues.append(f'point {index}: {exc}')
        points.append(dict(index=index, segment=segment, targets=targets,
            actual_coordinates=actual, units=['angstrom' if row.coord_type == 'bond' else 'degree' for row in task.scan.scans],
            geometry_converged=evidence['geometry_converged'], scc_converged=evidence['scc_converged'],
            energy_hartree=frame['energy_hartree'] if energy_resolved else None,
            energy_kind='electronic' if energy_resolved else 'unresolved',
            biased_total_hartree=electronic, bias_energy_hartree=bias,
            frame_path=str(frame_path), geometry_digest=content_digest(frame['positions'])))
    for point in points:
        if not point['geometry_converged'] or not point['scc_converged']:
            issues.append(f"point {point['index']} lacks native geometry or SCC convergence")
    normal = 'normal termination of xtb' in text and '#ERROR!' not in text
    complete = returncode == 0 and normal and len(points) == len(planned) and not issues
    candidates = []
    if complete:
        for segment in sorted({point['segment'] for point in points}):
            section = [point for point in points if point['segment'] == segment]
            if len(section) < 3:
                continue
            relative = [(point['energy_hartree'] - section[0]['energy_hartree']) * _HARTREE_TO_KCAL
                        for point in section]
            profile = analyze_scan_profile(relative)
            peak = profile['ts_index']
            if 0 < peak < len(section) - 1:
                candidate = section[peak]
                candidates.append(dict(segment=segment, point_index=candidate['index'], frame_path=candidate['frame_path'],
                                       energy_kind='electronic', verdicts=profile['verdicts']))
    candidate_path = candidates[0]['frame_path'] if len(candidates) == 1 else None
    version = next((line.strip() for line in text.splitlines() if 'xtb version' in line), '')
    return dict(returncode=returncode, normal_termination=normal, scan_status='complete' if complete else 'incomplete',
        usable_as_guess=bool(candidate_path), candidate_path=candidate_path, candidates=candidates,
        points=points, issues=issues, engine_version=version, method='GFN2-xTB',
        mode=task.scan.mode or 'sequential', force_constant=task.scan.force_constant,
        input_xyz_path=str(source), scan_input_path=str(control), scan_xyz_path=str(trajectory), log_file=str(log),
        input_digest=content_digest(task.reactant_xyz), scan_digest=content_digest(task.scan.model_dump()))


def run_xtb_scan(task, manifest: Path) -> dict:
    directory = Path(next_run_dir(str(manifest.parent), 'native_scan_runs', 'native_scan'))
    source, control, log = directory / 'input.xyz', directory / 'scan.inp', directory / 'engine.out'
    atomic_write_text(str(source), task.reactant_xyz)
    symbols = [symbol for symbol, _ in read_xyz_atoms(str(source))]
    atomic_write_text(str(control), _xcontrol(task.scan, len(symbols)))
    argv = ['xtb', str(source), '--gfn', '2', '--opt', '--input', str(control),
            '--parallel', str(task.cpus), '--chrg', str(task.charge), '--uhf', str(task.multiplicity - 1), '--verbose']
    if task.scan.solvation:
        argv.extend([f'--{task.scan.solvation.model}', task.scan.solvation.solvent])
    with log.open('w') as stream:
        process = subprocess.run(argv, cwd=str(directory), stdout=stream, stderr=subprocess.STDOUT, check=False)
    result = parse_xtb_scan(task, directory, process.returncode)
    result['command'] = argv
    result['artifact_hashes'] = {
        str(path.relative_to(manifest.parent)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in [source, control, log, directory / 'xtbscan.log', *sorted(directory.glob('point_*.xyz'))]
        if path.is_file()
    }
    return result
