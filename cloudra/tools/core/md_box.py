"""Pack a periodic starting geometry with Packmol."""

import json
import math
import secrets
import shutil
import subprocess
from collections.abc import Sequence
from itertools import product
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np

# Converts the product of a molar mass (g/mol) and a molecule count to the
# mass of those molecules in grams times the number of Å³ per cm³.
_MASS_TO_ANGSTROM_DENSITY = 1e24 / 6.02214076e23
# Packmol's distance convergence criterion is applied to squared distances.
_PACKMOL_PRECISION = 0.01
# Native XYZ rounds each coordinate to six decimals, giving this worst-case
# error in the distance between two written atoms.
_PACKMOL_XYZ_DISTANCE_ROUNDING = math.sqrt(3) * 1e-6


def _read_template(path):
    from cloudra.tools.core.molecule import _read_xyz_structure, read_molecule, to_ase

    format_name = path.suffix.lower().lstrip('.')
    if format_name == 'xyz':
        atoms = _read_xyz_structure(path.read_text(encoding='utf-8-sig'))
        if atoms.info.get('cloudra_coordinate_units', 'angstrom') != 'angstrom':
            raise ValueError(f'{path}: convert XYZ coordinates to Angstrom before packing')
        return atoms, None
    if format_name not in {'mol', 'sdf'}:
        raise ValueError(f'{path}: use an XYZ, MOL, or SDF template with explicit atom coordinates')

    from rdkit import Chem

    content = path.read_text(encoding='utf-8-sig')
    if format_name == 'sdf' and sum(line.strip() == '$$$$' for line in content.splitlines()) > 1:
        raise ValueError(f'{path}: use a single SDF record for each component')
    molecule = read_molecule(input_text=content, input_format=format_name)
    if not molecule.GetNumAtoms() or not molecule.GetNumConformers():
        raise ValueError(f'{path}: a molecular template must have explicit atom coordinates')
    if any(atom.GetTotalNumHs() for atom in molecule.GetAtoms()):
        raise ValueError(f'{path}: add explicit hydrogens with coordinates before packing')
    atoms = to_ase(molecule)
    if 0 in atoms.numbers or not np.isfinite(atoms.positions).all():
        raise ValueError(f'{path}: a template must contain real elements with finite coordinates')
    masses = atoms.get_masses()
    for atom in molecule.GetAtoms():
        if atom.GetIsotope():
            masses[atom.GetIdx()] = atom.GetMass()
    atoms.set_masses(masses)
    return atoms, Chem.MolToInchiKey(molecule) or None


def _run_packmol(work_dir, templates, lengths, min_distance, seed):
    executable = shutil.which('packmol')
    if executable is None:
        raise ValueError('Packmol is required on PATH. Use version 20.15.0 or newer for periodic packing.')

    lines = [
        'filetype xyz', 'output packed.xyz', f'tolerance {min_distance:.17g}', f'seed {seed}',
        f'precision {_PACKMOL_PRECISION}', 'pbc ' + ' '.join(f'{length:.17g}' for length in lengths),
    ]
    for template_name, count in templates:
        lines.extend((f'structure {template_name}', f'  number {count}', 'end structure'))
    script = work_dir / 'packmol.inp'
    script.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    with script.open() as stdin:
        run = subprocess.run(
            [executable], stdin=stdin, cwd=work_dir, text=True,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        )
    output = [line.strip() for line in run.stdout.splitlines() if line.strip()]
    if run.returncode or 'Success!' not in output or not (work_dir / 'packed.xyz').is_file():
        diagnostics = '\n'.join(output[-12:])
        raise ValueError(f'Packmol did not produce a converged periodic box (exit {run.returncode}):\n{diagnostics}')
    if 'Periodic boundary condition activated:' not in output:
        raise ValueError('Packmol did not confirm periodic packing. Use version 20.15.0 or newer.')
    return next((line.removeprefix('Version ') for line in output if line.startswith('Version ')), None)


def _closest_copy_distance(positions, lengths, copy_ids, initial_radius):
    """Exact minimum-image separation between atoms in different template copies."""
    from scipy.spatial import cKDTree

    if copy_ids[-1] == 0:
        return None
    periodic_positions = np.remainder(positions, lengths)
    periodic_positions = np.where(periodic_positions == lengths, 0, periodic_positions)
    tree = cKDTree(periodic_positions, boxsize=lengths)
    radius = min(initial_radius, float(min(lengths)) / 2)
    while True:
        pairs = tree.query_pairs(radius, output_type='ndarray')
        pairs = pairs[copy_ids[pairs[:, 0]] != copy_ids[pairs[:, 1]]]
        if len(pairs):
            difference = periodic_positions[pairs[:, 0]] - periodic_positions[pairs[:, 1]]
            difference -= lengths * np.rint(difference / lengths)
            return float(np.linalg.norm(difference, axis=1).min())
        radius *= 2


def _periodic_image_warning(positions, lengths, templates, min_distance):
    from scipy.spatial import cKDTree

    # The distances for opposite images are equal. Keep one translation per pair.
    offsets = [offset for offset in product((-1, 0, 1), repeat=3) if offset > (0, 0, 0)]
    translations = np.asarray(offsets) * lengths
    start = 0
    for path, atoms, _, count in templates:
        stop = start + len(atoms) * count
        copies = positions[start:stop].reshape(count, len(atoms), 3)
        start = stop
        extents = np.ptp(copies, axis=1)
        for index in np.flatnonzero(np.any(lengths - extents < min_distance, axis=1)):
            # A pair of atoms can be no closer than the gap between the two bounds.
            gaps = np.maximum(np.abs(translations) - extents[index], 0)
            nearby = translations[np.linalg.norm(gaps, axis=1) < min_distance]
            copy = copies[index]
            tree = cKDTree(copy)
            for translation in nearby:
                distances, _ = tree.query(copy + translation, distance_upper_bound=min_distance)
                closest = float(distances.min())
                if closest < min_distance:
                    return (
                        f'{path.name} copy {index + 1} approaches its own periodic image at {closest:.6g} Å. '
                        f'The requested packing distance is {min_distance:g} Å.'
                    )
    return None


def build_md_box(
    components: list[dict], output_dir: str | Path, *,
    initial_density_g_cm3: float | None,
    box_lengths_angstrom: Sequence[float] | None,
    min_distance_angstrom: float, seed: int | None,
) -> dict:
    from ase.io import read, write

    from cloudra.tools.core.md_box_density import lookup_density_reference

    output_dir = Path(output_dir)
    if output_dir.exists():
        raise ValueError(f'Output path already exists: {output_dir}; choose a new directory')
    templates = []
    for component in components:
        path = Path(component['structure_path'])
        try:
            atoms, inchi_key = _read_template(path)
        except (OSError, ValueError) as exc:
            raise ValueError(f'Cannot read component {path}: {exc}') from exc
        templates.append((path, atoms, inchi_key, component['count']))

    mass = sum(float(atoms.get_masses().sum()) * count for _, atoms, _, count in templates)
    if box_lengths_angstrom is None:
        length = (mass * _MASS_TO_ANGSTROM_DENSITY / initial_density_g_cm3) ** (1 / 3)
        lengths = (length, length, length)
    else:
        lengths = tuple(box_lengths_angstrom)
    volume = math.prod(lengths)
    density = mass * _MASS_TO_ANGSTROM_DENSITY / volume
    seed = secrets.randbelow(2**31 - 1) + 1 if seed is None else seed
    reference = lookup_density_reference([(key, count) for _, _, key, count in templates])
    warnings = []
    if reference:
        reference_density = reference['density_g_cm3']
        if density <= 0.8 * reference_density or density >= 1.2 * reference_density:
            deviation = abs(density / reference_density - 1)
            pressure = reference['pressure_kpa']
            pressure_description = f'{pressure:g} kPa' if pressure is not None else 'unspecified pressure'
            warnings.append(
                f'Initial density {density:.3f} g/cm³ differs by {deviation:.0%} from the reference '
                f'{reference_density:.3f} g/cm³ at {reference["temperature_k"]:g} K and '
                f'{pressure_description}.'
            )
    else:
        warnings.append('No ambient reference density is available for the supplied chemical identities and composition.')

    output_dir.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix='.cloudra-packmol-', dir=output_dir.parent) as temp_dir:
        work_dir = Path(temp_dir)
        input_files = []
        for index, (_, atoms, _, count) in enumerate(templates):
            name = f'component_{index}.xyz'
            write(work_dir / name, atoms, format='xyz')
            input_files.append((name, count))
        packmol_version = _run_packmol(work_dir, input_files, lengths, min_distance_angstrom, seed)
        packed = read(work_dir / 'packed.xyz', format='xyz')
        expected_numbers = np.concatenate([np.tile(atoms.numbers, count) for _, atoms, _, count in templates])
        if not np.array_equal(packed.numbers, expected_numbers) or not np.isfinite(packed.positions).all():
            raise ValueError('Packmol output has unexpected atom counts, atom order, or nonfinite coordinates')

        copy_sizes = [len(atoms) for _, atoms, _, count in templates for _ in range(count)]
        copy_ids = np.repeat(np.arange(len(copy_sizes)), copy_sizes)
        observed_distance = _closest_copy_distance(packed.positions, lengths, copy_ids, min_distance_angstrom)
        if observed_distance is not None and (
            (observed_distance + _PACKMOL_XYZ_DISTANCE_ROUNDING) ** 2
            < min_distance_angstrom**2 - _PACKMOL_PRECISION
        ):
            raise ValueError(
                f'Packmol output violates the requested minimum distance of {min_distance_angstrom:g} Å. '
                f'Closest atoms in different copies are {observed_distance:.6g} Å apart under PBC.'
            )
        image_warning = _periodic_image_warning(packed.positions, lengths, templates, min_distance_angstrom)
        if image_warning:
            warnings.append(image_warning)
        packed.set_cell(lengths)
        packed.set_pbc(True)
        packed.set_masses(np.concatenate([np.tile(atoms.get_masses(), count) for _, atoms, _, count in templates]))

        result = {
            'coordinates_path': str(output_dir / 'box.xyz'),
            'report_path': str(output_dir / 'box.json'),
            'box_lengths_angstrom': list(lengths),
            'initial_density_g_cm3': density,
            'components': [
                {
                    'structure_path': str(path), 'count': count, 'atoms_per_molecule': len(atoms),
                    'concentration_mol_l': count * 1e3 * _MASS_TO_ANGSTROM_DENSITY / volume,
                }
                for path, atoms, _, count in templates
            ],
            'min_distance_angstrom': min_distance_angstrom,
            'minimum_observed_distance_angstrom': observed_distance,
            'seed': seed,
            'packmol_version': packmol_version,
            'density_reference': reference,
            'warnings': warnings,
        }
        stage = work_dir / 'result'
        stage.mkdir()
        write(stage / 'box.xyz', packed, format='extxyz', columns=['symbols', 'positions', 'masses'])
        (stage / 'box.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')

        # Reserve the final name to keep simultaneous calls from replacing each other's results.
        output_dir.mkdir()
        try:
            stage.replace(output_dir)
        except OSError:
            output_dir.rmdir()
            raise
    return result
