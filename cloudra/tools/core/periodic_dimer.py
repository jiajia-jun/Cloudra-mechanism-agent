"""Seed a native periodic dimer search from adjacent evaluated band images."""

from pathlib import Path

import numpy as np
from ase import Atoms

from cloudra.tools.core.periodic_geometry import (
    GEOMETRY_TOLERANCE_ANGSTROM,
    fixed_atom_indices,
    minimum_image_vectors,
)
from cloudra.tools.core.periodic_io import vasp_atom_order, write_periodic_geometry


def band_tangent(left: Atoms, peak: Atoms, right: Atoms) -> np.ndarray:
    """Use a Cartesian secant through the local band in the engine's periodic cell."""
    tangent = minimum_image_vectors(peak, peak.positions - left.positions)
    tangent += minimum_image_vectors(peak, right.positions - peak.positions)
    tangent[sorted(fixed_atom_indices(peak))] = 0
    norm = np.linalg.norm(tangent)
    if not np.isfinite(norm) or norm <= GEOMETRY_TOLERANCE_ANGSTROM:
        raise ValueError('The adjacent evaluated images do not define a nonzero mobile-atom dimer direction.')
    return tangent / norm


def write_dimer(directory: Path, engine: str, atoms: Atoms, axis: np.ndarray) -> tuple[list[str], list[str]]:
    """Write geometry and an initial dimer axis, leaving production parameters to the caller."""
    if engine == 'vasp':
        poscar = directory / 'POSCAR'
        warnings = write_periodic_geometry(poscar, atoms, 'vasp')
        with poscar.open('a', encoding='utf-8') as handle:
            handle.write('\n' + _rows(axis[vasp_atom_order(atoms)]))
        (directory / 'INCAR.dimer').write_text('IBRION = 44\n', encoding='utf-8')
        return ['POSCAR', 'INCAR.dimer'], warnings

    from cloudra.tools.core.periodic_neb_cp2k import write_cp2k_fixed_atoms

    geometry = atoms.copy()
    geometry.set_constraint()
    warnings = write_periodic_geometry(directory / 'geometry.inc', geometry, 'cp2k-geometry')
    (directory / 'dimer.inc').write_text(
        'TYPE TRANSITION_STATE\n&TRANSITION_STATE\n  METHOD DIMER\n  &DIMER\n    &DIMER_VECTOR\n'
        + _rows(axis)
        + '    &END DIMER_VECTOR\n  &END DIMER\n&END TRANSITION_STATE\n',
        encoding='utf-8',
    )
    fixed_file = write_cp2k_fixed_atoms(directory, atoms)
    return ['geometry.inc', 'dimer.inc', *([fixed_file] if fixed_file else [])], warnings


def _rows(axis: np.ndarray) -> str:
    return ''.join('  ' + ' '.join(f'{value:.16g}' for value in vector) + '\n' for vector in axis)
