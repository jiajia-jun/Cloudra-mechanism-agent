"""Build a fixed-cell NEB seed with explicit atom correspondence and winding."""

from pathlib import Path

import numpy as np
from ase import Atoms
from ase.constraints import FixAtoms
from ase.neighborlist import primitive_neighbor_list

from cloudra.tools.core.neb_idpp import relax_standard_idpp
from cloudra.tools.core.periodic_geometry import (
    GEOMETRY_TOLERANCE_ANGSTROM,
    fixed_atom_indices,
    minimum_image_cell,
    minimum_image_vectors,
)
from cloudra.tools.core.periodic_io import geometry_format_from_path, read_geometry, validate_cell_geometry

_TOL = GEOMETRY_TOLERANCE_ANGSTROM


def read_endpoint(path: Path) -> tuple[Atoms, list[str]]:
    atoms, count, warnings = read_geometry(path, geometry_format_from_path(path))
    if count != 1:
        raise ValueError(f'{path} contains {count} frames. Supply an explicitly selected single structure.')
    validate_cell_geometry(atoms)
    if not atoms.pbc.any():
        raise ValueError(f'{path} has no periodic axes. Supply the full cell and periodic flags.')
    return atoms, warnings


def _same_cell(initial: Atoms, other: Atoms, label: str) -> None:
    if not np.allclose(initial.cell, other.cell, rtol=0, atol=_TOL):
        raise ValueError(f'The {label} cell differs from the initial cell. Prepare both structures at one fixed cell.')
    if not np.array_equal(initial.pbc, other.pbc):
        raise ValueError(f'The {label} PBC flags differ from the initial PBC flags.')


def _mapped_order(initial: Atoms, final: Atoms, atom_map: list[tuple[int, int]]) -> np.ndarray:
    count = len(initial)
    if len(final) != count:
        raise ValueError('Endpoint atom counts differ. Use the same atoms in the initial and final structures.')
    order = np.arange(count)
    supplied = set()
    for source, target in atom_map:
        if source > count or target > count or source in supplied:
            raise ValueError('atom_map requires distinct 1-based initial atoms and in-range final atoms.')
        supplied.add(source)
        order[source - 1] = target - 1
    if len(set(order)) != count:
        raise ValueError('atom_map must produce a full permutation after filling unlisted rows with identity.')
    if not np.array_equal(initial.numbers, final.numbers[order]):
        raise ValueError('Endpoint element order differs after atom_map. Match every atom to the same element.')
    return order


def _keep_fixed(positions: np.ndarray, initial: Atoms, fixed: np.ndarray, label: str) -> None:
    if not np.allclose(positions[fixed], initial.positions[fixed], rtol=0, atol=_TOL):
        raise ValueError(f'{label} fixed coordinates differ. Use identical positions for all frozen atoms.')
    positions[fixed] = initial.positions[fixed]


def _check_path(images: list[Atoms]) -> None:
    cell = minimum_image_cell(images[0])
    for index, image in enumerate(images):
        if primitive_neighbor_list('i', image.pbc, cell, image.positions, _TOL).size:
            raise ValueError(
                f'Image {index} has coincident atoms under PBC. Inspect atom_map or supply a waypoint_path.'
            )
    for index, (left, right) in enumerate(zip(images, images[1:])):
        step = right.positions - left.positions
        if not np.allclose(step, minimum_image_vectors(left, step), rtol=0, atol=_TOL):
            raise ValueError(
                f'Images {index} and {index + 1} cross a minimum-image jump. '
                'Increase intermediate_images or revise image_shifts and waypoint_path.'
            )


def build_band(
    initial: Atoms, final: Atoms, *, intermediate_images: int, interpolation: str,
    atom_map: list[tuple[int, int]], image_shifts: dict[int, tuple[int, int, int]],
    fixed_atoms: list[int] | None, waypoint: Atoms | None,
) -> tuple[list[Atoms], dict | None]:
    _same_cell(initial, final, 'final')
    order = _mapped_order(initial, final, atom_map)
    if fixed_atoms is None:
        try:
            fixed_set = fixed_atom_indices(initial)
            final_fixed = fixed_atom_indices(final)
        except ValueError as exc:
            raise ValueError(f'{exc} Give fixed_atoms explicitly to replace the endpoint constraints.') from exc
        if fixed_set != {i for i, j in enumerate(order) if j in final_fixed}:
            raise ValueError('Endpoint frozen masks differ after atom_map. Give fixed_atoms explicitly to replace them.')
    else:
        if len(set(fixed_atoms)) != len(fixed_atoms) or any(index > len(initial) for index in fixed_atoms):
            raise ValueError('fixed_atoms requires distinct, in-range 1-based initial atom numbers.')
        fixed_set = {index - 1 for index in fixed_atoms}
    if len(fixed_set) == len(initial):
        raise ValueError('At least one atom must be mobile in the band.')
    fixed = np.array(sorted(fixed_set), dtype=int)
    start = initial.positions

    via = start
    if waypoint is not None:
        _same_cell(initial, waypoint, 'waypoint')
        if not np.array_equal(initial.numbers, waypoint.numbers):
            raise ValueError('waypoint_path must use the initial structure atom order and elements.')
        via = waypoint.positions.copy()
        _keep_fixed(via, initial, fixed, 'Waypoint')

    raw_final = final.positions[order]
    end = via + minimum_image_vectors(initial, raw_final - via)
    for index, shift in image_shifts.items():
        if index > len(initial):
            raise ValueError('image_shifts atom_index must be an in-range initial atom number.')
        if np.any(np.asarray(shift)[~initial.pbc]):
            raise ValueError('image_shifts cannot translate a nonperiodic lattice axis.')
        end[index - 1] = raw_final[index - 1] + np.asarray(shift) @ initial.cell
    _keep_fixed(end, initial, fixed, 'Endpoint')

    if waypoint is None:
        if np.allclose(start, end, rtol=0, atol=_TOL):
            raise ValueError('The mapped endpoints coincide. Supply a distinct endpoint or an explicit periodic route.')
        coordinates = np.linspace(start, end, intermediate_images + 2)
    else:
        first_length, last_length = np.linalg.norm(via - start), np.linalg.norm(end - via)
        if min(first_length, last_length) <= _TOL:
            raise ValueError('waypoint_path must differ from both unwrapped endpoints.')
        steps = intermediate_images + 1
        first_steps = min(max(round(steps * first_length / (first_length + last_length)), 1), steps - 1)
        coordinates = np.concatenate((
            np.linspace(start, via, first_steps + 1),
            np.linspace(via, end, steps - first_steps + 1)[1:],
        ))

    images = [
        Atoms(
            numbers=initial.numbers, positions=frame, cell=initial.cell, pbc=initial.pbc,
            constraint=FixAtoms(indices=fixed) if fixed.size else None,
        )
        for frame in coordinates
    ]
    _check_path(images)
    report = None
    if interpolation == 'idpp':
        work = [image.copy() for image in images]
        mic_cell = minimum_image_cell(initial)
        for image in work:
            image.set_cell(mic_cell)
        report = relax_standard_idpp(work, mic=True)
        for image, relaxed in zip(images, work):
            image.set_positions(relaxed.positions)
        _check_path(images)
    return images, report
