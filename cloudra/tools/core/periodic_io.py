"""Structure I/O shared by periodic modeling and format conversion."""

import os
from io import BytesIO, StringIO
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Literal

import numpy as np
from ase import Atoms
from ase.constraints import FixAtoms, FixCartesian, FixedLine, FixedPlane, FixScaled
from ase.io import iread, write
from ase.units import Bohr

from cloudra.persistence.fs_utils import atomic_write_text

PeriodicInputFormat = Literal[
    'cif', 'poscar', 'vasp', 'contcar', 'xyz', 'extxyz', 'xsf', 'gen', 'espresso-in', 'espresso-out', 'abacus-stru',
]
PeriodicOutputFormat = Literal['cif', 'poscar', 'vasp', 'xyz', 'extxyz', 'xsf', 'gen', 'cp2k-geometry']

_PATH_FORMATS = {
    '.cif': 'cif', '.poscar': 'vasp', '.contcar': 'vasp', '.vasp': 'vasp',
    '.xyz': 'extxyz', '.extxyz': 'extxyz', '.xsf': 'xsf', '.gen': 'gen',
    '.pwi': 'espresso-in', '.pwo': 'espresso-out', '.stru': 'abacus-stru',
}
_SOURCE_NOTES = {
    'espresso-in': 'Extracted Quantum ESPRESSO geometry with three periodic cell axes. Electrostatics, magnetization and pseudopotentials are not transferred.',
    'espresso-out': 'Extracted the final frame with results and three periodic cell axes. Geometry convergence and electrostatics require separate evaluation.',
    'abacus-stru': 'Extracted STRU geometry. Pseudopotentials, orbitals, magnetic settings and movement flags are not transferred.',
}


def geometry_format_from_path(path: Path) -> str:
    name = path.name.lower()
    if name in {'poscar', 'contcar'}:
        return 'vasp'
    if name == 'stru':
        return 'abacus-stru'
    try:
        return _PATH_FORMATS[path.suffix.lower()]
    except KeyError as exc:
        raise ValueError(f'Unknown structure format for {path.name}; use a supported file extension.') from exc


def ase_geometry_format(fmt: str) -> str:
    return {
        'pdb': 'proteindatabank', 'xyz': 'extxyz',
        'poscar': 'vasp', 'contcar': 'vasp',
    }.get(fmt, fmt)


def _read_stru(path: Path) -> Atoms:
    """Read the explicit lattice and atom blocks of an ABACUS STRU."""
    sections = {name: [] for name in (
        'ATOMIC_SPECIES', 'NUMERICAL_ORBITAL', 'NUMERICAL_DESCRIPTOR', 'PAW_FILES',
        'LATTICE_CONSTANT', 'LATTICE_VECTORS', 'LATTICE_PARAMETERS', 'ATOMIC_POSITIONS',
    )}
    current = []
    for line in path.read_text(encoding='utf-8').splitlines():
        fields = line.partition('#')[0].partition('//')[0].split()
        if not fields:
            continue
        if len(fields) == 1 and fields[0].upper() in sections:
            current = sections[fields[0].upper()]
        else:
            current.append(fields)

    try:
        [[constant]] = sections['LATTICE_CONSTANT']
        scale = float(constant) * Bohr
        vectors = np.array(sections['LATTICE_VECTORS'], dtype=float)
        if not np.isfinite(scale) or scale <= 0 or vectors.shape != (3, 3):
            raise ValueError('expected a positive lattice constant and three explicit lattice vectors')
        species = {row[0] for row in sections['ATOMIC_SPECIES']}
        rows = iter(sections['ATOMIC_POSITIONS'])
        [mode] = next(rows)
        mode = mode.lower()
        if mode not in {'direct', 'cartesian', 'cartesian_au', 'cartesian_angstrom'}:
            raise ValueError(f'unsupported coordinate mode {mode}')
        symbols, positions = [], []
        for [symbol] in rows:
            next(rows)  # species initial magnetic moment
            [count_text] = next(rows)
            count = int(count_text)
            if symbol not in species or count < 0:
                raise ValueError(f'invalid atom block for {symbol}')
            for _ in range(count):
                x, y, z = map(float, next(rows)[:3])
                symbols.append(symbol)
                positions.append([x, y, z])
        cell = vectors * scale
        if mode == 'direct':
            return Atoms(symbols, scaled_positions=positions, cell=cell, pbc=True)
        units = {'cartesian': scale, 'cartesian_au': Bohr, 'cartesian_angstrom': 1.0}
        return Atoms(symbols, positions=np.array(positions) * units[mode], cell=cell, pbc=True)
    except (ValueError, KeyError, StopIteration) as exc:
        raise ValueError(f'Invalid STRU geometry: provide explicit LATTICE_VECTORS and complete ATOMIC_POSITIONS ({exc}).') from exc


def _espresso_output(path: Path) -> StringIO:
    from ase.io.espresso import get_atomic_positions, get_cell_parameters

    lines = path.read_text(encoding='utf-8').splitlines(keepends=True)
    natoms = None
    for index, line in enumerate(lines):
        label, _, value = line.strip().partition('=')
        if label.rstrip() == 'number of atoms/cell':
            natoms = int(value)
        if not line.lstrip().startswith('ATOMIC_POSITIONS') or index < 5:
            continue
        unit = line.strip().removeprefix('ATOMIC_POSITIONS').strip(' (){}').lower()
        cell_card = lines[index - 5:index]
        if unit not in {'', 'alat'} or not cell_card[0].lstrip().startswith('CELL_PARAMETERS'):
            continue
        _, alat = get_cell_parameters(cell_card)
        if alat is None:
            continue
        if natoms is None:
            raise ValueError('QE output is missing the atom count for its variable-cell coordinates.')

        # ASE reads this frame's cell but applies the initial alat to its position card.
        rows = get_atomic_positions(lines[index:index + natoms + 1], natoms, alat=alat)
        lines[index] = 'ATOMIC_POSITIONS (angstrom)\n'
        for row_index, (symbol, point, flags) in enumerate(rows, index + 1):
            tokens = [symbol, *(f'{value:.16g}' for value in point), *(str(flag) for flag in flags or ())]
            lines[row_index] = ' '.join(tokens) + '\n'
    return StringIO(''.join(lines))


def read_geometry(path: Path, fmt: str) -> tuple[Atoms, int, list[str]]:
    """Read one geometry with the format's frame convention and report omitted frames."""
    notes = [_SOURCE_NOTES[fmt]] if fmt in _SOURCE_NOTES else []
    if fmt == 'abacus-stru':
        return _read_stru(path), 1, notes

    atoms = None
    count = 0
    last = fmt == 'espresso-out'
    source = _espresso_output(path) if last else str(path)
    try:
        for frame in iread(source, format=ase_geometry_format(fmt), do_not_split_by_at_sign=True):
            count += 1
            if atoms is None or last:
                atoms = frame
    except KeyError as exc:
        raise ValueError(f'Could not read a structure from {path} as {fmt}: {exc}') from exc
    if atoms is None:
        raise ValueError(f'Could not read a structure from {path} as {fmt}.')
    if fmt == 'espresso-in':
        # ASE interprets QE species magnetizations as atomic moments and can merge same-element species.
        atoms.set_array('initial_magmoms', None)
    if count > 1:
        selected = 'last' if last else 'first'
        notes.append(f'Input {fmt} contains {count} coordinate frames; only the {selected} one was converted.')
    return atoms, count, notes


def validate_atomic_geometry(atoms: Atoms) -> None:
    if not len(atoms) or np.any(atoms.numbers == 0) or not np.isfinite(atoms.positions).all():
        raise ValueError('A structure needs real elements and finite coordinates.')
    cif_occupancies = atoms.info.get('occupancy', {})
    if not np.allclose(atoms.arrays.get('occupancy', 1.0), 1.0, rtol=0, atol=1e-8) or any(
        len(species) != 1 or not np.isclose(next(iter(species.values())), 1.0, rtol=0, atol=1e-8)
        for species in cif_occupancies.values()
    ):
        raise ValueError('Partial or mixed site occupancy requires an explicit ordered structure.')


def validate_cell_geometry(atoms: Atoms) -> None:
    validate_atomic_geometry(atoms)
    if not np.isfinite(atoms.cell).all() or np.linalg.matrix_rank(atoms.cell) != 3:
        raise ValueError('A finite, nondegenerate 3D cell is required. Supply a cell-bearing structure file.')


def _cp2k_geometry(atoms: Atoms) -> str:
    periodic = ''.join(axis for axis, enabled in zip('XYZ', atoms.pbc) if enabled) or 'NONE'
    vectors = [f'  {axis} ' + ' '.join(f'{v:.16g}' for v in vector) for axis, vector in zip('ABC', atoms.cell)]
    coordinates = [
        f'  {symbol} ' + ' '.join(f'{v:.16g}' for v in point)
        for symbol, point in zip(atoms.get_chemical_symbols(), atoms.positions)
    ]
    return '\n'.join(['&CELL', *vectors, f'  PERIODIC {periodic}', '&END CELL', '&COORD', *coordinates, '&END COORD', ''])


def vasp_atom_order(atoms: Atoms) -> list[int]:
    """Return the stable POSCAR grouping by first occurrence of each element."""
    species = {number: rank for rank, number in enumerate(dict.fromkeys(atoms.numbers))}
    return sorted(range(len(atoms)), key=lambda index: species[atoms.numbers[index]])


def write_periodic_geometry(path: Path, atoms: Atoms, fmt: str, *, exclusive: bool = False) -> list[str]:
    """Serialize cell and coordinates before publishing, with format-specific loss reported."""
    validate_cell_geometry(atoms)
    fmt = ase_geometry_format(fmt)
    if fmt not in {'cif', 'vasp', 'extxyz', 'xsf', 'gen', 'cp2k-geometry', 'proteindatabank'}:
        raise ValueError('Choose a geometry output such as .extxyz, .cif, .vasp, .xsf or .gen.')
    warnings = []
    if fmt in {'cif', 'vasp', 'gen'} and not atoms.pbc.all():
        warnings.append(f'{fmt.upper()} exports the cell with three periodic axes; use EXTXYZ to retain the boundary flags.')
    if fmt == 'proteindatabank' and not atoms.pbc.all():
        warnings.append('PDB exports the cell with three periodic axes; use EXTXYZ to retain the boundary flags.')
    if fmt == 'xsf' and tuple(atoms.pbc) not in {(True, False, False), (True, True, False), (True, True, True)}:
        raise ValueError('XSF requires periodic X, XY or XYZ for a cell-bearing structure; use EXTXYZ for these axes.')

    supported_constraints = {
        'extxyz': (FixAtoms, FixCartesian),
        'vasp': (FixAtoms, FixScaled, FixedLine, FixedPlane),
    }.get(fmt, ())
    if any(not isinstance(constraint, supported_constraints) for constraint in atoms.constraints):
        warnings.append(f'{fmt.upper()} does not carry all input atom constraints.')

    # Retain geometric metadata supported by the target without copying calculator results.
    atoms = atoms.copy()
    if fmt in {'cif', 'gen', 'proteindatabank'}:
        atoms.pbc = True
    if fmt in {'cif', 'vasp', 'proteindatabank'} and atoms.cell.handedness < 0:
        cell = atoms.cell.copy()
        cell[2] *= -1
        atoms.set_cell(cell)
        warnings.append('Reversed one lattice vector to write a right-handed cell without reflecting the geometry.')
    if fmt in {'cif', 'proteindatabank'}:
        _, rotation = atoms.cell.standard_form()
        if not np.allclose(rotation, np.eye(3)):
            warnings.append('The target stores cell lengths and angles; the Cartesian frame rotates on conversion.')
    if fmt == 'vasp':
        order = vasp_atom_order(atoms)
        if order != list(range(len(atoms))):
            atoms = atoms[order]
            warnings.append('POSCAR groups atoms by element. Inspect the output to obtain its atom numbers.')
    if fmt == 'cp2k-geometry':
        text = _cp2k_geometry(atoms)
        warnings.append('CP2K geometry fragment for &SUBSYS. Supply KIND, DFT and POISSON settings separately.')
    else:
        buffer = BytesIO() if fmt == 'cif' else StringIO()
        write(buffer, atoms, format=fmt)
        data = buffer.getvalue()
        text = data.decode('latin-1') if isinstance(data, bytes) else data

    path.parent.mkdir(parents=True, exist_ok=True)
    if exclusive:
        with NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent) as temporary:
            temporary.write(text)
            temporary.flush()
            try:
                os.link(temporary.name, path)
            except FileExistsError as exc:
                raise ValueError(f'Choose a new output path; {path} already exists.') from exc
    else:
        atomic_write_text(str(path), text)
    return warnings
