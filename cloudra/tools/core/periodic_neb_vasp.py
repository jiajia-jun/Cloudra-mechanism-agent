"""Native VASP elastic-band input and evidence for a prepared fixed-cell path."""

from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from itertools import takewhile
from pathlib import Path

import numpy as np
from ase import Atoms
from ase.io import ParseError
from ase.io.vasp import read_vasp_configuration
from ase.io.vasp_parsers.vasp_outcar_parsers import (
    Cell,
    Energy,
    IonsPerSpecies,
    OutcarChunkParser,
    OutcarHeaderParser,
    PositionsAndForces,
    SpeciesTypes,
    build_chunk,
    build_header,
)

from cloudra.persistence.fs_utils import atomic_write_text
from cloudra.tools.core.periodic_geometry import (
    GEOMETRY_TOLERANCE_ANGSTROM,
    fixed_atom_indices,
    minimum_image_vectors,
)
from cloudra.tools.core.periodic_io import validate_cell_geometry, vasp_atom_order, write_periodic_geometry

# OUTCAR's evaluated Cartesian coordinates use five decimals in standard output.
_POSITION_ATOL_ANGSTROM = 1e-5
# The force table rounds each Cartesian component to six decimals.
_FORCE_ROUNDING_EV_PER_ANGSTROM = 0.5e-6 * 3**0.5
_IONIC_STOP = 'reached required accuracy - stopping structural energy minimisation'
_TIMING = 'General timing and accounting informations for this job:'
_VTST_NEB_FORCES = 'NEB: forces: par spring, perp REAL, dneb'
_PARSE_ERRORS = (OSError, ParseError, ValueError, KeyError, IndexError, StopIteration)
_BAND_TAGS = {'EDIFFG', 'SPRING', 'IMAGES', 'NSW'}
_ENERGY_ARRAY_TAGS = {'LDAUL', 'LDAUU', 'LDAUJ'}
_ENERGY_TAGS = {
    'PREC', 'ENCUT', 'ENAUG', 'LREAL', 'NELECT', 'ISPIN', 'NUPDOWN', 'LNONCOLLINEAR', 'LSORBIT',
    'ISMEAR', 'SIGMA', 'GGA', 'METAGGA', 'LEXCH', 'LASPH', 'LHFCALC', 'HFSCREEN', 'AEXX',
    'LDAU', 'LDAUTYPE', 'IVDW', 'LUSE_VDW', 'LDIPOL', 'IDIPOL', 'EFIELD',
} | _ENERGY_ARRAY_TAGS
_Settings = dict[str, tuple[float | str, ...]]


@dataclass(frozen=True)
class _IonicEvidence:
    step: int
    stopped: bool
    finished: bool
    incomplete: bool
    electronic_failed: bool
    chain_force: float | None
    vtst_neb: bool
    ediffg: float | None
    spring: float | None
    images: float | None
    nsw: float | None
    energy_settings: _Settings


def write_vasp_neb(directory: Path, images: list[Atoms]) -> tuple[list[str], list[str]]:
    """Write the native image geometries and IMAGES fragment."""
    files, warnings = [], []
    for index, atoms in enumerate(images):
        filename = f'{index:02d}/POSCAR'
        warnings.extend(write_periodic_geometry(directory / filename, atoms, 'vasp'))
        files.append(filename)
    atomic_write_text(str(directory / 'INCAR.neb'), f'IMAGES = {len(images) - 2}\n')
    return [*files, 'INCAR.neb'], list(dict.fromkeys(warnings))


def _same_positions(actual: np.ndarray, expected: np.ndarray, native: Atoms) -> bool:
    if not len(actual):
        return True
    if not np.isfinite(actual).all():
        return False
    displacements = minimum_image_vectors(native, actual - expected)
    return bool(np.all(np.linalg.norm(displacements, axis=1) <= _POSITION_ATOL_ANGSTROM))


def _read_prepared_poscar(path: Path, expected: Atoms, order: list[int]) -> Atoms:
    with path.open(encoding='utf-8') as stream:
        native = read_vasp_configuration(stream)
    validate_cell_geometry(native)
    grouped = expected[order]
    # The common POSCAR writer flips the third vector for a left-handed input.
    # Undo that for the comparison and leave the reported native cell intact.
    cell = native.cell.copy()
    if expected.cell.handedness < 0:
        cell[2] *= -1
    if (
        not np.array_equal(native.numbers, grouped.numbers)
        or not np.allclose(cell, grouped.cell, atol=GEOMETRY_TOLERANCE_ANGSTROM, rtol=0)
        or fixed_atom_indices(native) != fixed_atom_indices(grouped)
        or not _same_positions(native.positions, grouped.positions, native)
    ):
        raise ValueError('POSCAR does not match the prepared cell, coordinates, species order or fixed atoms')
    return native


def _setting_value(value: str) -> float | str:
    try:
        number = float(value.upper().replace('D', 'E'))
    except ValueError:
        return value.upper()
    return number if np.isfinite(number) else value.upper()


def _three_values(text: str) -> tuple[float, ...]:
    values = tuple(map(_setting_value, text.split()))
    if len(values) == 3 and all(isinstance(value, float) for value in values):
        return values
    return ()


def _outcar_settings(header: list[str]) -> tuple[dict[str, float], _Settings]:
    band, energy, potentials = {}, {}, []
    for index, line in enumerate(header):
        label, colon, value = line.strip().partition(':')
        if colon and label == 'POTCAR' and value.strip():
            potentials.append(' '.join(value.split()))
        elif colon and label == 'generate k-points for':
            if grid := _three_values(value):
                energy['k-point grid'] = grid
        elif label == 'Shift w.r.t. Gamma in fractional coordinates (k-lattice)' and index + 1 < len(header):
            if shift := _three_values(header[index + 1]):
                energy['k-point grid shift'] = tuple(round(value % 1, 9) for value in shift)
        for statement in line.split(';'):
            label, equals, value = statement.partition('=')
            tag, fields = label.strip(), value.split()
            if not equals or not fields or (tag not in _BAND_TAGS and tag not in _ENERGY_TAGS):
                continue
            first = _setting_value(fields[0])
            if tag in _BAND_TAGS and isinstance(first, float):
                band[tag] = first
            elif tag in _ENERGY_ARRAY_TAGS:
                values = tuple(takewhile(lambda item: isinstance(item, float), map(_setting_value, fields)))
                if values:
                    energy[tag] = values
            elif tag in _ENERGY_TAGS:
                energy[tag] = (first,)
    if potentials:
        energy['POTCAR'] = tuple(dict.fromkeys(potentials))
    return band, energy


def _energy_setting_differences(evidence: list[_IonicEvidence | None]) -> list[str]:
    observed = defaultdict(set)
    for image in evidence:
        if image is not None:
            for tag, value in image.energy_settings.items():
                observed[tag].add(value)
    return sorted(tag for tag, values in observed.items() if len(values) > 1)


def _max_chain_force(lines: list[str], native: Atoms) -> float | None:
    for index in range(len(lines) - 1, -1, -1):
        if lines[index].split() != ['CHAIN', '+', 'TOTAL', '(eV/Angst)']:
            continue
        start = index + 1
        while start < len(lines) and not lines[start].strip().strip('-'):
            start += 1
        try:
            forces = np.array([list(map(float, line.split())) for line in lines[start:start + len(native)]])
        except ValueError:
            return None
        if forces.shape == (len(native), 3) and np.isfinite(forces).all():
            moving = np.delete(forces, sorted(fixed_atom_indices(native)), axis=0)
            if moving.size:
                maximum = float(np.hypot.reduce(moving, axis=1).max())
                return maximum if np.isfinite(maximum) else None
        return None
    return None


def _has_vtst_neb_summary(lines: list[str]) -> bool:
    for line in reversed(lines):
        text = line.lstrip()
        if text.startswith(_VTST_NEB_FORCES):
            return bool(_three_values(text.removeprefix(_VTST_NEB_FORCES)))
    return False


def _iteration_step(line: str) -> int | None:
    fields = line.split(maxsplit=2)
    if len(fields) != 3 or fields[1] != 'Iteration' or fields[0].strip('-'):
        return None
    ion, opening, tail = fields[2].partition('(')
    electronic, closing, delimiter = tail.partition(')')
    delimiter = delimiter.strip()
    if opening and closing and delimiter and not delimiter.strip('-') and ion.strip().isdecimal() and electronic.strip().isdecimal():
        return int(ion)
    return None


def _read_outcar(path: Path, native: Atoms) -> tuple[Atoms, Atoms, _IonicEvidence]:
    pending: list[str] = []
    first = final = None
    final_lines: list[str] = []
    step = 0
    incomplete = False
    with path.open(encoding='utf-8', errors='replace') as file:
        def remember_lines():
            for line in file:
                pending.append(line)
                yield line

        lines = remember_lines()
        header = build_header(lines)
        # Use ASE's native parsers for the fields needed here. A separate
        # CONTCAR may be stale or may contain the next unevaluated geometry.
        parser = OutcarChunkParser(
            OutcarHeaderParser(parsers=[SpeciesTypes(), IonsPerSpecies()]).build(header),
            parsers=[Cell(), PositionsAndForces(), Energy()],
        )
        pending.clear()
        while True:
            try:
                chunk = build_chunk(lines)
            except StopIteration:
                break
            try:
                evaluated = parser.build(chunk)
            except _PARSE_ERRORS:
                if final is None:
                    raise
                incomplete = True
                break
            iteration = next(((i, value) for i, line in enumerate(chunk)
                              if (value := _iteration_step(line)) is not None), None)
            if iteration is not None:
                step_start, ionic_step = iteration
            else:
                # ASE includes the first iteration delimiter in the OUTCAR header.
                initial = _iteration_step(header[-1]) if final is None else None
                step_start, ionic_step = 0, initial or 0
            incomplete |= ionic_step <= step
            step = ionic_step
            if first is None:
                first = evaluated
            final = evaluated
            final_lines = chunk[step_start:]
            pending.clear()
    if first is None or final is None:
        raise ValueError('no complete evaluated ionic frame in OUTCAR')

    for line in pending:
        if _iteration_step(line) is not None:
            incomplete = True
            break
        final_lines.append(line)
    band, method = _outcar_settings(header)
    return first, final, _IonicEvidence(
        step=step,
        stopped=any(line.strip() == _IONIC_STOP for line in final_lines),
        finished=any(line.strip() == _TIMING for line in final_lines),
        incomplete=incomplete,
        electronic_failed=any('The electronic self-consistency was not achieved' in line for line in final_lines),
        chain_force=_max_chain_force(final_lines, native),
        vtst_neb=_has_vtst_neb_summary(final_lines),
        ediffg=band.get('EDIFFG'),
        spring=band.get('SPRING'),
        images=band.get('IMAGES'),
        nsw=band.get('NSW'),
        energy_settings=method,
    )


def _stdout_step_energy(line: str) -> tuple[int, str] | None:
    step, free_tag, tail = line.partition('F=')
    free, energy_tag, value = tail.partition('E0=')
    fields = value.split(maxsplit=1)
    if free_tag and energy_tag and step.strip().isdecimal() and len(free.split()) == 1 and fields:
        return int(step), fields[0]
    return None


def _stdout_confirms(path: Path, step: int, energy: float) -> bool:
    summary = None
    stopped = False
    with path.open(encoding='utf-8', errors='replace') as stream:
        for line in stream:
            if match := _stdout_step_energy(line):
                summary = match
                stopped = False
            elif line.strip() == _IONIC_STOP:
                stopped = True
    if not stopped or summary is None or summary[0] != step:
        return False
    try:
        reported = Decimal(summary[1])
    except InvalidOperation:
        return False
    if not reported.is_finite() or not np.isfinite(float(reported)):
        return False
    # Allow half a digit from each native representation of E0.
    exponent = reported.as_tuple().exponent
    if not -324 <= exponent <= 308:
        return False
    tolerance = 0.5 * 10.0**exponent + 5e-9
    return abs(float(reported) - energy) <= tolerance


def _band_status(
    interiors: list[_IonicEvidence | None], image_one_ev: float | None, output_log: Path | None,
) -> tuple[bool, bool | None, dict[str, float], list[str]]:
    band = [evidence for evidence in interiors if evidence is not None]
    if (
        not band or len(band) != len(interiors)
        or any(e.incomplete or e.electronic_failed for e in band)
        or len({e.step for e in band}) != 1
    ):
        return False, None, {}, ['VASP interior OUTCAR frames do not establish one complete, synchronized band step.']
    vtst = all(e.vtst_neb for e in band)
    if any(
        (e.spring is not None and e.spring >= 0)
        or (e.images is not None and e.images != len(interiors))
        for e in band
    ) or (not vtst and any(e.vtst_neb or e.chain_force is None for e in band)):
        return False, None, {}, ['VASP interior OUTCAR files do not establish consistent NEB force evidence for the prepared band.']
    if _energy_setting_differences(interiors):
        return False, None, {}, ['The VASP interior images report different energy settings.']
    if vtst:
        return True, None, {}, ['Native VTST band convergence is unverified.']

    metrics = {'max_chain_force_ev_per_angstrom': max(e.chain_force for e in band if e.chain_force is not None)}
    force_margins = [
        abs(e.ediffg) - e.chain_force
        for e in band if e.chain_force is not None and e.ediffg is not None and e.ediffg < 0
    ]
    if any(margin < -_FORCE_ROUNDING_EV_PER_ANGSTROM for margin in force_margins):
        if all(e.finished and not e.stopped for e in band):
            return True, False, metrics, ['The final VASP band step exceeds the native projected-force criterion.']
        return True, None, metrics, ['The final VASP projected forces and ionic stop evidence do not agree.']
    if any(e.ediffg == 0 and e.stopped for e in band):
        return True, None, metrics, ['VASP ionic stop evidence conflicts with EDIFFG = 0.']
    if all(e.stopped for e in band):
        return True, True, metrics, []
    if len(force_margins) == len(band) and min(force_margins) > _FORCE_ROUNDING_EV_PER_ANGSTROM:
        if any(e.stopped for e in band):
            return True, True, metrics, []
        if output_log is not None and image_one_ev is not None:
            try:
                if _stdout_confirms(output_log, band[0].step, image_one_ev):
                    return True, True, metrics, []
            except OSError as exc:
                return True, None, metrics, [f'Could not read VASP stdout evidence ({exc}).']
    if all(e.finished and e.step == e.nsw and not e.stopped for e in band):
        return True, False, metrics, ['VASP finished at the native ionic step limit without the accuracy stop.']
    return True, None, metrics, ['VASP has no explicit ionic accuracy stop associated with the final band step.']


def read_vasp_neb(directory: Path, expected: list[Atoms], output_log: Path | None = None) -> dict:
    """Read evaluated E0 and geometries in the prepared reference atom order."""
    energies: list[float | None] = [None] * len(expected)
    geometries: list[Atoms | None] = [None] * len(expected)
    steps: list[_IonicEvidence | None] = [None] * len(expected)
    evidence_paths, warnings = [], []
    for index, reference in enumerate(expected):
        image = directory / f'{index:02d}'
        poscar, outcar = image / 'POSCAR', image / 'OUTCAR'
        if not outcar.is_file():
            warnings.append(f'{image.name}/OUTCAR is missing evaluated VASP energy and geometry.')
            continue
        evidence_paths.extend(str(path.resolve()) for path in (poscar, outcar) if path.is_file())
        order = vasp_atom_order(reference)
        try:
            native = _read_prepared_poscar(poscar, reference, order)
            first, frame, step = _read_outcar(outcar, native)
            endpoint = index in (0, len(expected) - 1)
            validate_cell_geometry(frame)
            if not np.array_equal(frame.numbers, native.numbers) or not np.allclose(
                frame.cell, native.cell, atol=GEOMETRY_TOLERANCE_ANGSTROM, rtol=0,
            ):
                raise ValueError('OUTCAR evaluated species order or cell differs from POSCAR')
            anchor = frame if endpoint else first
            if not _same_positions(anchor.positions, native.positions, native):
                raise ValueError('OUTCAR geometry does not identify the prepared image')
            fixed = sorted(fixed_atom_indices(native))
            if not _same_positions(frame.positions[fixed], native.positions[fixed], native):
                raise ValueError('OUTCAR moves atoms fixed in POSCAR')
            energy = frame.calc.results.get('energy')
            if energy is None or not np.isfinite(energy):
                raise ValueError('OUTCAR has no finite E0 for the evaluated frame')
        except _PARSE_ERRORS as exc:
            warnings.append(f'{image.name}/OUTCAR evidence rejected: {exc}')
            continue
        frame.set_constraint(native.constraints)
        geometries[index], steps[index] = frame[np.argsort(order)], step
        if not (endpoint and step.electronic_failed):
            energies[index] = float(energy)
        if step.incomplete:
            warnings.append(f'{image.name}/OUTCAR has an incomplete or inconsistent ionic step sequence.')
        if step.electronic_failed:
            warnings.append(f'{image.name}/OUTCAR reports electronic self-consistency failure for the sampled energy.')

    stdout = directory / output_log if output_log is not None else None
    if stdout is not None and stdout.is_file():
        evidence_paths.append(str(stdout.resolve()))
    else:
        stdout = None
    complete, converged, metrics, notes = _band_status(steps[1:-1], energies[1] if len(energies) > 2 else None, stdout)
    differences = _energy_setting_differences(steps)
    if differences:
        warnings.append('VASP OUTCAR files disagree on energy settings ' + ', '.join(differences) + '.')
    return {
        'energies_ev': energies,
        'geometries': geometries,
        'band_complete': complete,
        'profile_comparable': not differences,
        'native_converged': converged,
        'energy_convention': 'VASP OUTCAR E0 (energy(sigma->0), eV)',
        'metrics': metrics,
        'evidence_paths': list(dict.fromkeys(evidence_paths)),
        'warnings': [*warnings, *notes],
    }
