"""CP2K BAND input fragments and evaluated replica output."""

from dataclasses import dataclass, field
from io import StringIO
from math import isclose, isfinite
from pathlib import Path

import numpy as np
from ase import Atoms
from ase.io import write
from ase.units import Bohr, Hartree

from cloudra.persistence.fs_utils import atomic_write_text
from cloudra.tools.core.periodic_geometry import (
    GEOMETRY_TOLERANCE_ANGSTROM,
    fixed_atom_indices,
    minimum_image_vectors,
)
from cloudra.tools.core.periodic_io import validate_cell_geometry, write_periodic_geometry

_ENERGY_FILE = 'band.ener'
_TRAJECTORY_PREFIX = 'cloudra-neb'
_TRAJECTORY_SEPARATOR = '-pos-Replica_nr_'
# CP2K neb_io.F writes 6 decimals in the compact summary, 9 in ENER and 10 in XMOL titles.
_SUMMARY_TOL_HARTREE = 0.5e-6 + 0.5e-9 + 1e-12
_TRAJECTORY_TOL_HARTREE = 0.5e-9 + 0.5e-10 + 1e-12
_CELL_LOG_TOL_ANGSTROM = 0.5e-3 + 1e-12  # CELL| vectors are printed to three decimal places.
_CRITERIA = {
    'RMS DISPLACEMENT': ('rms_displacement_angstrom', Bohr),
    'MAX DISPLACEMENT': ('max_displacement_angstrom', Bohr),
    'RMS FORCE': ('rms_force_ev_per_angstrom', Hartree / Bohr),
    'MAX FORCE': ('max_force_ev_per_angstrom', Hartree / Bohr),
}


def write_cp2k_fixed_atoms(directory: Path, atoms: Atoms) -> str | None:
    """Write whole-atom constraints for the CP2K MOTION/CONSTRAINT section."""
    fixed = sorted(fixed_atom_indices(atoms))
    if not fixed:
        return None
    atom_lists = ['  LIST ' + ' '.join(str(index + 1) for index in fixed[start:start + 20])
                  for start in range(0, len(fixed), 20)]
    filename = 'fixed-atoms.inc'
    directory.mkdir(parents=True, exist_ok=True)
    atomic_write_text(str(directory / filename), '\n'.join([
        '! Include inside &MOTION / &CONSTRAINT. Atom indices are 1-based.',
        '&FIXED_ATOMS', '  COMPONENTS_TO_FIX XYZ', *atom_lists, '&END FIXED_ATOMS', '',
    ]))
    return filename


def write_cp2k_neb(directory: Path, images: list[Atoms]) -> tuple[list[str], list[str]]:
    """Write explicit BAND replicas without selecting calculation or optimization settings."""
    if len(images) < 3:
        raise ValueError('CP2K BAND requires two endpoints and at least one intermediate replica.')
    first = images[0]
    fixed = fixed_atom_indices(first)
    for image in images:
        validate_cell_geometry(image)
        if not np.array_equal(image.numbers, first.numbers):
            raise ValueError('CP2K BAND replicas require the same atom order.')
        if not np.array_equal(image.pbc, first.pbc) or not np.allclose(
            image.cell, first.cell, rtol=0, atol=GEOMETRY_TOLERANCE_ANGSTROM,
        ):
            raise ValueError('CP2K BAND replicas require the same cell and periodic axes.')
        if fixed_atom_indices(image) != fixed:
            raise ValueError('CP2K BAND replicas require the same fixed atom indices.')

    geometry = first.copy()
    geometry.set_constraint()
    warnings = write_periodic_geometry(directory / 'geometry.inc', geometry, 'cp2k-geometry')
    files = ['geometry.inc', 'band.inc', 'trajectory.inc']
    band = [
        '! Include inside &MOTION / &BAND. Capture CP2K stdout for step and convergence evidence.',
        f'NUMBER_OF_REPLICA {len(images)}', 'ALIGN_FRAMES FALSE', 'ROTATE_FRAMES FALSE',
        '&ENERGY ON', f'  FILENAME ={_ENERGY_FILE}', '  &EACH', '    BAND 1', '  &END EACH', '&END ENERGY',
        '&PROGRAM_RUN_INFO ON', '  FILENAME __STD_OUT__', '&END PROGRAM_RUN_INFO',
        '&CONVERGENCE_INFO ON', '  FILENAME __STD_OUT__', '&END CONVERGENCE_INFO',
    ]
    for index, image in enumerate(images, 1):
        filename = f'replica-{index}.xyz'
        buffer = StringIO()
        # CP2K requires a nonempty XYZ title when it loads COORD_FILE_NAME.
        write(buffer, image, format='xyz', comment=f'Cloudra BAND input replica {index}')
        atomic_write_text(str(directory / filename), buffer.getvalue())
        files.append(filename)
        band.extend(['&REPLICA', f'  COORD_FILE_NAME {filename}', '&END REPLICA'])
    atomic_write_text(str(directory / 'band.inc'), '\n'.join(band) + '\n')
    atomic_write_text(str(directory / 'trajectory.inc'), (
        '! Include inside &MOTION / &PRINT. CP2K writes one trajectory for each BAND replica.\n'
        '&TRAJECTORY ON\n'
        f'  FILENAME ./{_TRAJECTORY_PREFIX}\n'
        '  FORMAT XMOL\n  UNIT angstrom\n  PRINT_ATOM_KIND FALSE\n  COMMON_ITERATION_LEVELS 1\n'
        '  &EACH\n    BAND 1\n  &END EACH\n&END TRAJECTORY\n'
    ))
    if fixed_include := write_cp2k_fixed_atoms(directory, first):
        files.append(fixed_include)
        warnings.append('CP2K BAND with OPT_TYPE MD can move fixed atoms through initial velocities. '
                        'Review the optimizer choice and verify frozen positions in the native trajectories. '
                        'DIIS initializes the band velocities to zero.')
    return files, warnings


def _native_number(token: str) -> float:
    if not set(token) <= set('0123456789+-.eEdD'):
        raise ValueError(f'invalid numeric field {token!r}')
    value = float(token.replace('D', 'E').replace('d', 'e'))
    if not isfinite(value):
        raise ValueError(f'nonfinite numeric field {token!r}')
    return value


def _native_index(token: str) -> int:
    if not token.isascii() or not token.isdecimal():
        raise ValueError(f'invalid nonnegative integer field {token!r}')
    return int(token)


def _next_phase(previous_step: int | None, step: int, phase: int) -> int:
    if previous_step is not None and step <= previous_step:
        if step == 0:  # CP2K appends each new run beginning with its evaluated step zero.
            return phase + 1
        raise ValueError(f'out-of-order or repeated BAND step {step}')
    return phase


@dataclass
class _EnergyStep:
    step: int
    phase: int
    hartree: list[float]
    initial_hartree: list[float] | None


def _read_energy(path: Path, replica_count: int) -> _EnergyStep | None:
    latest = None
    initial_hartree = None
    phase = 0
    with path.open(encoding='utf-8') as handle:
        for line_number, line in enumerate(handle, 1):
            fields = line.split()
            if not fields:
                continue
            # CP2K neb_io.F emits exactly step, N energies, then N−1 adjacent distances, with no header.
            try:
                if len(fields) != 2 * replica_count:
                    raise ValueError(f'expected {2 * replica_count} columns, found {len(fields)}')
                step = _native_index(fields[0])
                values = [_native_number(field) for field in fields[1:]]
                if any(distance < 0 for distance in values[replica_count:]):
                    raise ValueError('negative replica distance')
                phase = _next_phase(latest.step if latest else None, step, phase)
            except ValueError as exc:
                raise ValueError(f'line {line_number}: {exc}') from exc
            energies = values[:replica_count]
            if step == 0:
                initial_hartree = energies
            latest = _EnergyStep(step, phase, energies, initial_hartree)
    return latest


@dataclass
class _BandLog:
    observed: bool = False
    version: str | None = None
    project: str | None = None
    energy: _EnergyStep | None = None
    criteria: dict[str, tuple[float, bool]] = field(default_factory=dict)
    completed: bool = False
    clean_end: bool = False
    error: str | None = None
    band_type: str = ''
    cell_vectors: dict[str, list[float]] = field(default_factory=dict)
    periodicity: str | None = None
    cell_error: str | None = None


def _read_log(path: Path, replica_count: int) -> _BandLog:
    band = _BandLog()
    previous_step = None
    phase = 0
    step = None
    count = None
    energy_fields: list[str] | None = None
    initial_hartree = None
    reading_energies = reading_plot = False
    cell_vectors = {}
    periodicity = cell_error = None
    with path.open(encoding='utf-8', errors='replace') as handle:
        for line in handle:
            text = line.strip()
            banner = text.strip('* ').strip()
            if banner.startswith('PROGRAM STARTED AT '):
                band = _BandLog(observed=band.observed)
                cell_vectors = {}
                periodicity = cell_error = None
                step = None
                initial_hartree = None
                reading_energies = reading_plot = False
            elif banner.startswith('PROGRAM ENDED AT '):
                band.clean_end = band.energy is not None and band.criteria.keys() == _CRITERIA.keys()
            elif text.startswith('CP2K| version string:'):
                version_fields = text.split(':', 1)[1].split()
                if version_fields[:2] == ['CP2K', 'version'] and len(version_fields) >= 3:
                    band.version = version_fields[2]
            elif text.startswith('GLOBAL| Project name '):
                band.project = text.removeprefix('GLOBAL| Project name ').strip()
            elif text.startswith('CELL| Vector '):
                fields = text.split()
                try:
                    axis, unit = fields[2:4]
                    if axis not in ('a', 'b', 'c') or unit != '[angstrom]:' or len(fields) < 7:
                        raise ValueError('unexpected native CP2K cell vector format')
                    cell_vectors[axis] = [_native_number(field) for field in fields[4:7]]
                except ValueError as exc:
                    cell_error = str(exc)
            elif text.startswith('CELL| Periodicity '):
                periodicity = text.removeprefix('CELL| Periodicity ').strip()
            elif text == 'NEB| Replica_env Setup. START':
                band = _BandLog(observed=True, version=band.version, project=band.project)
                step = None
                initial_hartree = None
                reading_energies = reading_plot = False
            elif banner == 'BAND TASK COMPLETED':
                band.completed = band.energy is not None

            if band.band_type and text.split(maxsplit=5)[:5] == ['REPLICA', 'ENERGY', '[au]', 'TEMPERATURE', '[K]']:
                if energy_fields is not None:
                    band.error = 'repeated CP2K BAND energy table'
                energy_fields = []
                reading_plot = True
                continue
            if reading_plot and energy_fields is not None:
                body, plot_sep, _ = text.partition('|')
                columns = body.split()
                if columns and columns[0].isdecimal():
                    try:
                        replica, energy, marker, temperature = columns
                        if not plot_sep or _native_index(replica) != len(energy_fields) + 1 or len(marker) != 4:
                            raise ValueError('unexpected CP2K BAND energy table row')
                        if marker[0] != '(' or marker[-1] != ')' or any(sign not in '+-*' for sign in marker[1:-1]):
                            raise ValueError('unexpected CP2K BAND energy table marker')
                        _native_number(temperature)
                        energy_fields.append(energy)
                    except ValueError as exc:
                        band.error = str(exc)
                    continue

            label, sep, value = text.partition('=')
            label = ' '.join(label.split())
            if reading_energies and not sep:
                energy_fields.extend(text.split())
                continue
            if not sep:
                continue
            reading_energies = False
            if label == 'BAND TYPE':
                band = _BandLog(observed=True, version=band.version, project=band.project, band_type=value.strip())
                step, count, energy_fields = None, None, None
                reading_plot = False
            if not band.band_type:
                continue
            try:
                if label == 'STEP NUMBER':
                    step = _native_index(value.strip())
                    phase = _next_phase(previous_step, step, phase)
                    previous_step = step
                    if step == 0:
                        initial_hartree = None
                elif label == 'NUMBER OF NEB REPLICA':
                    count = _native_index(value.strip())
                elif label == 'ENERGIES [au]':
                    if energy_fields is not None:
                        raise ValueError('repeated CP2K BAND energy field')
                    energy_fields = value.split()
                    reading_energies = True
                elif label == 'BAND TOTAL ENERGY [au]':
                    reading_plot = False
                    if (band.error or step is None or count != replica_count
                            or energy_fields is None or len(energy_fields) != count):
                        raise ValueError('missing or ambiguous CP2K BAND step/replica energy fields')
                    _native_number(value.strip())
                    energies = [_native_number(field) for field in energy_fields]
                    if step == 0:
                        initial_hartree = energies
                    band.energy = _EnergyStep(step, phase, energies, initial_hartree)
                elif label in _CRITERIA and band.energy is not None:
                    measured, bracket, comparison = value.partition('[')
                    threshold, closing, decision = comparison.partition(']')
                    decision = decision.strip()
                    if not bracket or not closing or decision not in {'(YES)', '(NO)'} or label in band.criteria:
                        raise ValueError(f'malformed or repeated CP2K BAND criterion {label}')
                    measured_value = _native_number(measured.strip())
                    if measured_value < 0 or _native_number(threshold.strip()) < 0:
                        raise ValueError(f'negative CP2K BAND criterion {label}')
                    band.criteria[label] = (measured_value, decision == '(YES)')
            except ValueError as exc:
                band.error = str(exc)
    band.cell_vectors, band.periodicity, band.cell_error = cell_vectors, periodicity, cell_error
    return band


def _find_band_log(directory: Path, output_log: Path | None, replica_count: int, warnings: list[str]):
    if output_log is not None:
        paths = [output_log if output_log.is_absolute() else directory / output_log]
    else:
        paths = [path for path in sorted(directory.glob('*.out'))
                 if not any(path.stem.rpartition(marker)[2].isdecimal() for marker in ('-BAND', '-r-'))]
        if (directory / 'band.nebLog').is_file():
            paths.append(directory / 'band.nebLog')
    logs = []
    for path in paths:
        try:
            band = _read_log(path, replica_count)
        except OSError as exc:
            warnings.append(f'Could not read CP2K output {path.name}: {exc}.')
            continue
        if band.observed:
            logs.append((path, band))
    if len(logs) > 1:
        warnings.append('Multiple CP2K BAND logs contain native output. Supply the stdout path for this run.')
    if len(logs) == 1:
        return logs[0]
    return None, _BandLog()


def _trajectory_paths(directory: Path, replica_count: int, warnings: list[str]) -> dict[int, Path]:
    families: dict[str, dict[int, Path]] = {}
    for path in sorted(directory.glob(f'*{_TRAJECTORY_SEPARATOR}*-1.xyz')):
        project, _, fields = path.name.rpartition(_TRAJECTORY_SEPARATOR)
        replica = fields.removesuffix('-1.xyz')
        if replica.isascii() and replica.isdecimal():
            index = int(replica)
            if 1 <= index <= replica_count and replica == str(index).zfill(len(str(replica_count))):
                families.setdefault(project, {})[index] = path
    if _TRAJECTORY_PREFIX in families:
        return families[_TRAJECTORY_PREFIX]
    if len(families) > 1:
        warnings.append('Multiple CP2K BAND trajectory prefixes were found. Use files from one run directory.')
        return {}
    return next(iter(families.values()), {})


def _trajectory_positions(lines: list[str], expected: Atoms) -> np.ndarray:
    positions = []
    for symbol, line in zip(expected.get_chemical_symbols(), lines, strict=True):
        fields = line.split()
        if len(fields) != 4 or fields[0] != symbol:
            raise ValueError('trajectory atom order or XYZ columns differ from the prepared replica')
        positions.append([_native_number(field) for field in fields[1:]])
    return np.array(positions)


def _same_positions(expected: Atoms, left: np.ndarray, right: np.ndarray) -> bool:
    delta = left - right
    if np.allclose(delta, 0, rtol=0, atol=GEOMETRY_TOLERANCE_ANGSTROM):
        return True
    return np.allclose(minimum_image_vectors(expected, delta), 0, rtol=0, atol=GEOMETRY_TOLERANCE_ANGSTROM)


def _read_trajectory(
    path: Path, expected: Atoms, band: _EnergyStep, replica: int, tolerance: float, *, endpoint: bool,
) -> Atoms:
    if band.initial_hartree is None:
        raise ValueError('native band energies are missing evaluated step zero for seed binding')
    phase, previous_step = 0, None
    anchored = False
    frame = None
    fixed = sorted(fixed_atom_indices(expected))
    with path.open(encoding='utf-8') as handle:
        for count in handle:
            if not count.strip():
                continue
            if _native_index(count.strip()) != len(expected):
                raise ValueError('trajectory atom count differs from the prepared replica')
            first, comma, second = handle.readline().partition(',')
            step_key, step_sep, step_field = first.partition('=')
            energy_key, energy_sep, energy_field = second.partition('=')
            if not comma or not step_sep or not energy_sep or step_key.strip() != 'i' or energy_key.strip() != 'E':
                raise ValueError('expected a native CP2K XMOL title with BAND step and energy')
            step = _native_index(step_field.strip())
            energy = _native_number(energy_field.strip())
            phase = _next_phase(previous_step, step, phase)
            previous_step = step
            lines = [handle.readline() for _ in expected]
            if not all(lines):
                raise ValueError('incomplete final trajectory frame')
            if phase != band.phase or step > band.step:
                continue
            positions = _trajectory_positions(lines, expected)
            if step == 0:
                if not isclose(energy, band.initial_hartree[replica - 1], rel_tol=0, abs_tol=tolerance):
                    raise ValueError('trajectory step zero energy does not match the native BAND step zero')
                # BAND consumes Cartesian replica arrays, including the prepared lattice winding.
                if not np.allclose(positions, expected.positions, rtol=0, atol=GEOMETRY_TOLERANCE_ANGSTROM):
                    raise ValueError('trajectory step zero Cartesian geometry does not match the prepared replica')
                anchored = True
            if endpoint and not _same_positions(expected, positions, expected.positions):
                raise ValueError(f'native trajectory moved a prepared endpoint at BAND step {step}')
            if fixed and not _same_positions(expected, positions[fixed], expected.positions[fixed]):
                raise ValueError(f'native trajectory moved fixed atoms at BAND step {step}')
            if step == band.step and isclose(energy, band.hartree[replica - 1], rel_tol=0, abs_tol=tolerance):
                frame = expected.copy()
                frame.set_positions(positions, apply_constraint=False)
    if not anchored:
        raise ValueError('trajectory is missing evaluated step zero for seed binding')
    if frame is None or previous_step != band.step or phase != band.phase:
        raise ValueError(f'latest trajectory step/energy does not match BAND step {band.step}')
    return frame


def _replica_scf_status(path: Path, band: _EnergyStep, replica: int, tolerance: float) -> bool | None:
    """Return the SCF failure flag for a replica evaluation matched by phase, step and energy."""
    step, phase, replica_id = None, 0, None
    failed = False
    energy = None
    with path.open(encoding='utf-8', errors='replace') as handle:
        for line in handle:
            text = ' '.join(line.strip('* \n').split())
            _, label, value = text.partition('Replica Band Nr. :')
            if label:
                replica_id = _native_index(value.strip())
            if text.startswith('Band Step Nr. :'):
                current = _native_index(text.removeprefix('Band Step Nr. :').strip())
                if current == 0 and step is not None:
                    phase += 1
                step = current
                failed, energy = False, None
            if step is None:
                continue
            if 'SCF run NOT converged' in text:
                failed = True
            if text.startswith('ENERGY| Total FORCE_EVAL ') and ' energy [a.u.]:' in text:
                energy = _native_number(text.rsplit(':', 1)[1].strip())
    if replica_id == replica and step == band.step and phase == band.phase and energy is not None and isclose(
        energy, band.hartree[replica - 1], rel_tol=0, abs_tol=tolerance,
    ):
        return failed
    return None


def _replica_scf_failed(
    directory: Path, band: _EnergyStep, replica_count: int, tolerance: float, project: str | None,
    warnings: list[str], evidence_paths: list[str],
) -> bool:
    failed = False
    if project is None:
        families = {prefix for path in directory.glob('*-BAND*.out')
                    if (prefix := path.stem.rpartition('-BAND')[0]) and path.stem.rpartition('-BAND')[2].isdecimal()}
        if len(families) != 1:
            if families:
                warnings.append('Multiple CP2K replica log families were found. Supply the main stdout to identify the project.')
            return failed
        project = families.pop()
    # Construct names from the observed CP2K project only when they remain local filenames.
    if Path(project).name != project:
        return failed
    for replica in range(1, replica_count + 1):
        path = directory / f'{project}-BAND{str(replica).zfill(len(str(replica_count)))}.out'
        if not path.is_file():
            continue
        try:
            replica_failed = _replica_scf_status(path, band, replica, tolerance)
        except (OSError, ValueError) as exc:
            warnings.append(f'Could not inspect CP2K replica SCF from {path.name}: {exc}.')
            continue
        if replica_failed is not None:
            evidence_paths.append(str(path.resolve()))
        if replica_failed:
            warnings.append(f'CP2K replica {replica} reports SCF nonconvergence at BAND step {band.step}.')
            failed = True
    return failed


def _native_cell_error(log: _BandLog, reference: Atoms) -> str | None:
    if log.cell_error:
        return log.cell_error
    expected_pbc = ''.join(axis for axis, enabled in zip('XYZ', reference.pbc) if enabled) or 'NONE'
    if log.periodicity is not None and log.periodicity != expected_pbc:
        return f'CP2K stdout periodicity {log.periodicity} differs from the prepared {expected_pbc} cell.'
    for axis, vector in log.cell_vectors.items():
        if not np.allclose(vector, reference.cell['abc'.index(axis)], rtol=0, atol=_CELL_LOG_TOL_ANGSTROM):
            return f'CP2K stdout cell vector {axis} differs from the prepared fixed cell.'
    return None


def _native_convergence(band: _BandLog) -> bool | None:
    if band.error:
        return None
    if band.completed:
        return None if any(not passed for _, passed in band.criteria.values()) else True
    if band.criteria.keys() != _CRITERIA.keys():
        return None
    if not all(passed for _, passed in band.criteria.values()):
        return False
    # v2025.2 checks all four flags and then exits its BAND loop without a completion banner.
    return True if band.version == '2025.2' and band.clean_end else None


def _same_log_band(band: _EnergyStep, logged: _EnergyStep | None) -> bool:
    if logged is None or (band.phase, band.step) != (logged.phase, logged.step):
        return False
    pairs = list(zip(band.hartree, logged.hartree, strict=True))
    if band.initial_hartree is not None and logged.initial_hartree is not None:
        pairs.extend(zip(band.initial_hartree, logged.initial_hartree, strict=True))
    return all(isclose(a, b, rel_tol=0, abs_tol=_SUMMARY_TOL_HARTREE) for a, b in pairs)


def read_cp2k_neb(directory: Path, expected: list[Atoms], output_log: Path | None = None) -> dict:
    """Read the latest native BAND record and attach only matching evaluated geometries."""
    warnings, evidence_paths = [], []
    replica_count = len(expected)
    energies: list[float | None] = [None] * replica_count
    geometries: list[Atoms | None] = [None] * replica_count
    result = {
        'energies_ev': energies, 'geometries': geometries, 'native_converged': None, 'band_complete': False,
        'energy_convention': 'CP2K BAND absolute replica energies (Hartree converted to eV)',
        'metrics': {}, 'evidence_paths': evidence_paths, 'warnings': warnings,
    }
    energy_path = directory / _ENERGY_FILE
    table = None
    if energy_path.is_file():
        try:
            table = _read_energy(energy_path, replica_count)
        except (OSError, ValueError) as exc:
            warnings.append(f'Could not read {energy_path.name}: {exc}.')
    log_path, log = _find_band_log(directory, output_log, replica_count, warnings)
    if log.error:
        warnings.append(f'Could not verify CP2K BAND stdout from {log_path.name}: {log.error}.')
    band = table or log.energy
    if band is None:
        warnings.append('No complete native CP2K BAND energy row was found.')
        return result
    if table is not None:
        evidence_paths.append(str(energy_path.resolve()))
    log_matches = _same_log_band(band, log.energy)
    if log_matches:
        evidence_paths.append(str(log_path.resolve()))
        result['native_converged'] = _native_convergence(log)
        result['metrics'] = {_CRITERIA[key][0]: value * _CRITERIA[key][1]
                             for key, (value, _) in log.criteria.items()}
        if log.band_type == 'CI-NEB':
            warnings.append('The CP2K CI-NEB label records BAND_TYPE. The climbing phase requires separate evidence.')
    elif log.observed:
        warnings.append('The latest CP2K BAND stdout does not match the selected energy row.')
    if result['native_converged'] is None:
        warnings.append('Native CP2K BAND convergence is unverified for the selected energy row.')

    energies[:] = [value * Hartree for value in band.hartree]
    if log_matches and (cell_error := _native_cell_error(log, expected[0])):
        warnings.append(cell_error)
        return result
    paths = _trajectory_paths(directory, replica_count, warnings)
    tolerance = _TRAJECTORY_TOL_HARTREE if table is not None else _SUMMARY_TOL_HARTREE
    for replica, path in paths.items():
        try:
            geometries[replica - 1] = _read_trajectory(
                path, expected[replica - 1], band, replica, tolerance, endpoint=replica in (1, replica_count),
            )
        except (OSError, ValueError) as exc:
            warnings.append(f'Could not attach CP2K replica {replica} from {path.name}: {exc}.')
        else:
            evidence_paths.append(str(path.resolve()))
    scf_failed = _replica_scf_failed(
        directory, band, replica_count, tolerance, log.project if log_matches else None, warnings, evidence_paths,
    )
    trajectories_complete = all(geometry is not None for geometry in geometries)
    if not trajectories_complete:
        warnings.append(f'Matching seed-bound CP2K trajectories are missing for some replicas at BAND step {band.step}.')
    elif not log_matches or len(log.cell_vectors) != 3 or log.periodicity is None:
        warnings.append('CP2K XMOL supplies positions. The prepared fixed-cell band supplies any cell or PBC metadata absent from stdout.')
    result['band_complete'] = trajectories_complete and not scf_failed and (log_matches or not log.observed)
    return result
