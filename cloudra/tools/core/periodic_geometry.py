"""Minimum-image distances and surface geometry for periodic models."""

from collections import defaultdict
from dataclasses import dataclass
from itertools import product
from typing import Literal

import numpy as np
from ase import Atoms
from ase.cell import Cell
from ase.geometry import get_distances, minkowski_reduce
from scipy.spatial import QhullError, Voronoi

SiteKind = Literal['ontop', 'bridge', 'hollow']
_KINDS = ('ontop', 'bridge', 'hollow')
_FRACTIONAL_DIGITS = 10
GEOMETRY_TOLERANCE_ANGSTROM = 1e-7


@dataclass(frozen=True)
class AdsorptionSite:
    index: int | None
    kind: SiteKind
    position_angstrom: tuple[float, float, float]
    atom_indices: list[int]


def minimum_image_distances(atoms: Atoms, first: np.ndarray, second: np.ndarray) -> np.ndarray:
    """Measure distances on the periodic sublattice, including skew cells."""
    reduced, _ = minkowski_reduce(atoms.cell, pbc=atoms.pbc)
    cell = Cell(reduced.copy())
    # ASE completes the missing axes orthogonally before wrapping distances.
    cell[~atoms.pbc] = 0
    _, distances = get_distances(first, second, cell=cell, pbc=atoms.pbc)
    return distances


def slab_normal(cell, in_plane: np.ndarray) -> np.ndarray:
    """Return the unit normal pointing along the remaining cell vector."""
    normal = np.cross(*cell[in_plane])
    normal /= np.linalg.norm(normal)
    return normal if normal @ cell[~in_plane][0] > 0 else -normal


def adsorption_surface(atoms: Atoms, vacuum_axis: str | None, side: str) -> tuple[np.ndarray, np.ndarray]:
    in_plane = atoms.pbc.copy()
    if vacuum_axis is not None:
        requested_plane = np.ones(3, dtype=bool)
        requested_plane['abc'.index(vacuum_axis)] = False
        if not (in_plane.all() or np.array_equal(in_plane, requested_plane)):
            raise ValueError('vacuum_axis disagrees with the slab periodic axes.')
        in_plane = requested_plane
    if in_plane.sum() != 2:
        raise ValueError('Use a slab with two periodic axes or give vacuum_axis for a three-periodic slab file.')
    normal = slab_normal(atoms.cell, in_plane)
    return in_plane, normal if side == 'top' else -normal


def _slab_positions(atoms: Atoms, in_plane: np.ndarray, normal: np.ndarray, indices: list[int] | None) -> np.ndarray:
    if not atoms.pbc.all():
        return atoms.positions
    normal_vector = atoms.cell[~in_plane][0]
    height = normal_vector @ normal
    fraction = atoms.positions @ normal / height
    sampled = fraction if indices is None else fraction[indices]
    levels = np.unique(np.round(sampled % 1, _FRACTIONAL_DIGITS) % 1)
    gaps = np.diff(np.r_[levels, levels[0] + 1])
    largest = gaps.argmax()
    if np.count_nonzero(np.isclose(gaps, gaps[largest], rtol=0, atol=GEOMETRY_TOLERANCE_ANGSTROM / abs(height))) > 1:
        raise ValueError('The largest normal gap is ambiguous. Select surface_atoms from a known face or use an explicit atop atom.')
    # Choose the vacuum gap as the cut through the periodic representation.
    cut = (levels[largest] + gaps[largest] / 2) % 1
    return atoms.positions - np.floor(fraction - cut)[:, None] * normal_vector


def enumerate_adsorption_sites(
    atoms: Atoms, in_plane: np.ndarray, normal: np.ndarray, indices: list[int] | None,
) -> list[AdsorptionSite]:
    """Find sites from the periodic Voronoi diagram of the selected atom projections."""
    positions = _slab_positions(atoms, in_plane, normal, indices)
    heights = positions @ normal
    if indices is None:
        # Group only coincident outermost heights. Rumpled layers can be given explicitly.
        indices = np.flatnonzero(np.isclose(heights, heights.max(), rtol=0, atol=GEOMETRY_TOLERANCE_ANGSTROM)).tolist()

    basis = atoms.cell[in_plane]
    x = basis[0] / np.linalg.norm(basis[0])
    projection = np.column_stack((x, np.cross(normal, x)))
    plane = basis @ projection
    reduced_cell, _ = minkowski_reduce(atoms.cell, pbc=in_plane)
    reduced_plane = reduced_cell[in_plane] @ projection
    inverse_plane = np.linalg.inv(plane)
    inverse_reduced = np.linalg.inv(reduced_plane)

    fractional = (positions[indices] @ projection @ inverse_reduced) % 1
    reduced_keys = np.round(fractional, _FRACTIONAL_DIGITS) % 1
    if len(np.unique(reduced_keys, axis=0)) != len(indices):
        raise ValueError('Selected surface atoms share a projected position. Choose one atom for each projection.')
    fractional[reduced_keys == 0] = 0
    primary = fractional @ reduced_plane
    shifts = np.array(list(product(range(-2, 3), repeat=2))) @ reduced_plane
    tiled = (primary[None, :, :] + shifts[:, None, :]).reshape(-1, 2)
    atom_for_point = np.tile(indices, len(shifts))

    try:
        voronoi = Voronoi(tiled)
    except QhullError as exc:
        raise ValueError('Could not resolve adsorption sites for the projected surface geometry.') from exc
    sites = {}

    def record(kind: SiteKind, xy: np.ndarray, support: np.ndarray) -> None:
        local = np.round(xy @ inverse_reduced, _FRACTIONAL_DIGITS)
        if np.any((local < 0) | (local >= 1)):
            return
        wrapped = (xy @ inverse_plane) % 1
        key = np.round(wrapped, _FRACTIONAL_DIGITS) % 1
        wrapped[key == 0] = 0
        position = wrapped @ plane @ projection.T + heights[support].mean() * normal
        if atoms.pbc.all():
            vector = atoms.cell[~in_plane][0]
            turns = np.floor(np.round((position @ normal) / (vector @ normal), _FRACTIONAL_DIGITS))
            position -= turns * vector
        sites.setdefault(
            (_KINDS.index(kind), *key),
            (kind, tuple(position.tolist()), sorted((support + 1).tolist())),
        )

    for point, index in zip(primary, indices):
        record('ontop', point, np.array([index]))

    # Round-trip coordinate noise can split a fourfold vertex into two
    # vertices joined by a numerically zero ridge. Restore the shared vertex.
    parent = list(range(len(voronoi.vertices)))

    def representative(index: int) -> int:
        while parent[index] != index:
            index = parent[index]
        return index

    for left, right in voronoi.ridge_vertices:
        if min(left, right) < 0:
            continue
        if np.linalg.norm(voronoi.vertices[left] - voronoi.vertices[right]) <= GEOMETRY_TOLERANCE_ANGSTROM:
            parent[representative(right)] = representative(left)

    supports = defaultdict(set)
    vertices_by_group = defaultdict(list)
    for index, position in enumerate(voronoi.vertices):
        vertices_by_group[representative(index)].append(position)
    for pair, vertices in zip(voronoi.ridge_points, voronoi.ridge_vertices):
        groups = {representative(vertex) for vertex in vertices if vertex >= 0}
        if len(groups) == 2:
            record('bridge', tiled[pair].mean(axis=0), atom_for_point[pair])
        for group in groups:
            supports[group].update(pair)
    for group, points in supports.items():
        if len(points) >= 3:
            record('hollow', np.mean(vertices_by_group[group], axis=0), atom_for_point[sorted(points)])

    return [
        AdsorptionSite(index, kind, position, atom_indices)
        for index, (kind, position, atom_indices) in enumerate(
            (sites[key] for key in sorted(sites)), start=1,
        )
    ]
