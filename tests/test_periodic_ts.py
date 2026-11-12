"""Test fixed-cell NEB preparation through Cloudra's tool entry point."""

from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from ase import Atoms
from ase.constraints import FixAtoms
from ase.io import read, write
from ase.units import Hartree

from cloudra.tools import get_tools_lst


@pytest.fixture
def endpoints(tmp_path):
    initial = Atoms(
        'AgLi', positions=[[1.5, 0, 5], [0.1, 1.5, 6]],
        cell=[[3, 0, 0], [0, 3, 0], [60, 0, 15]], pbc=(True, True, False),
        constraint=FixAtoms(indices=[0]),
    )
    final = initial.copy()
    final.positions[0] += initial.cell[0]
    final.positions[1, 0] = 2.9
    write(tmp_path / 'initial.extxyz', initial)
    write(tmp_path / 'final.extxyz', final)
    return initial, final


async def call_ts(tmp_path, **operation):
    entry = next((item for item in get_tools_lst() if item.tool_name == 'periodic_ts'), None)
    assert entry is not None, 'periodic_ts is registered for DFT agents'
    assert {'dft', 'coordinator'} <= entry.registration.role_allowlist
    tool = entry.instantiate(subagent=SimpleNamespace(working_directory=str(tmp_path)))
    return await tool.tool_call(tool.input_schema(operation=operation))


def prepare(**changes):
    return {
        'type': 'prepare', 'engine': 'vasp', 'initial_path': 'initial.extxyz', 'final_path': 'final.extxyz',
        'intermediate_images': 1, 'interpolation': 'linear', 'output_dir': 'neb',
        **changes,
    }


@pytest.mark.asyncio
@pytest.mark.parametrize('engine', ['vasp', 'cp2k'])
async def test_prepare_unwraps_surface_hop_and_keeps_frozen_substrate(tmp_path, endpoints, engine):
    initial, _ = endpoints
    result = await call_ts(tmp_path, **prepare(engine=engine))
    assert result.is_success, result.message
    directory = Path(result.run_dir)
    images = read(directory / 'band.extxyz', index=':')
    assert len(images) == 3
    np.testing.assert_allclose([image.positions[1, 0] for image in images], [0.1, 0, -0.1], atol=1e-8)
    for image in images:
        np.testing.assert_allclose(image.positions[0], initial.positions[0])
        np.testing.assert_allclose(image.cell, initial.cell)
        assert image.pbc.tolist() == [True, True, False]
        assert image.constraints[0].index.tolist() == [0]
    if engine == 'vasp':
        assert 'IMAGES = 1' in (directory / 'INCAR.neb').read_text()
        assert (directory / '02/POSCAR').is_file()
    else:
        assert 'NUMBER_OF_REPLICA 3' in (directory / 'band.inc').read_text()


@pytest.mark.asyncio
async def test_image_shifts_express_an_intentional_long_route(tmp_path, endpoints):
    result = await call_ts(tmp_path, **prepare(image_shifts=[{'atom_index': 2, 'shift': [0, 0, 0]}]))
    assert result.is_success, result.message
    images = read(Path(result.run_dir) / 'band.extxyz', index=':')
    np.testing.assert_allclose([image.positions[1, 0] for image in images], [0.1, 1.5, 2.9])
    bad = await call_ts(
        tmp_path, **prepare(output_dir='bad', image_shifts=[{'atom_index': 2, 'shift': [0, 0, 1]}]),
    )
    assert not bad.is_success and 'nonperiodic' in bad.message
    assert not (tmp_path / 'bad').exists()


@pytest.mark.asyncio
async def test_endpoint_atom_map_is_bijective_and_keeps_initial_order(tmp_path, endpoints):
    _, final = endpoints
    write(tmp_path / 'final.extxyz', final[[1, 0]])
    missing = await call_ts(tmp_path, **prepare())
    assert not missing.is_success and 'atom_map' in missing.message
    bad = await call_ts(tmp_path, **prepare(atom_map=[[1, 2]]))
    assert not bad.is_success and 'permutation' in bad.message
    result = await call_ts(tmp_path, **prepare(atom_map=[[1, 2], [2, 1]]))
    assert result.is_success, result.message
    image = read(Path(result.run_dir) / 'band.extxyz', index=-1)
    assert image.get_chemical_symbols() == ['Ag', 'Li']
    np.testing.assert_allclose(image.positions[1], [-0.1, 1.5, 6], atol=1e-8)


@pytest.mark.asyncio
@pytest.mark.parametrize('mismatch', ['cell', 'pbc', 'fixed coordinates'])
async def test_prepare_fails_for_different_periodic_models(tmp_path, endpoints, mismatch):
    _, final = endpoints
    if mismatch == 'cell':
        final.cell[1, 1] += 0.1
    elif mismatch == 'pbc':
        final.pbc = True
    else:
        final.positions[0, 2] += 0.1
    write(tmp_path / 'final.extxyz', final)
    result = await call_ts(tmp_path, **prepare())
    assert not result.is_success and mismatch.lower() in result.message.lower()
    assert not (tmp_path / 'neb').exists()


@pytest.mark.asyncio
async def test_waypoint_avoids_an_exchange_collision(tmp_path):
    initial = Atoms('Li2', positions=[[1, 1, 4], [3, 1, 4]], cell=[8, 8, 12], pbc=(True, True, False))
    final = initial.copy()
    final.positions = initial.positions[::-1].copy()
    waypoint = initial.copy()
    waypoint.positions = [[2, 0, 4], [2, 2, 4]]
    for name, atoms in [('initial', initial), ('final', final), ('waypoint', waypoint)]:
        write(tmp_path / f'{name}.extxyz', atoms)
    failed = await call_ts(tmp_path, **prepare())
    assert not failed.is_success and 'coincident' in failed.message
    assert not (tmp_path / 'neb').exists()

    result = await call_ts(tmp_path, **prepare(waypoint_path='waypoint.extxyz'))
    assert result.is_success, result.message
    images = read(Path(result.run_dir) / 'band.extxyz', index=':')
    np.testing.assert_allclose(images[1].positions, waypoint.positions)


@pytest.mark.asyncio
async def test_idpp_respects_periodic_atoms_and_the_frozen_mask(tmp_path, endpoints):
    result = await call_ts(tmp_path, **prepare(interpolation='idpp', intermediate_images=2))
    assert result.is_success, result.message
    images = read(Path(result.run_dir) / 'band.extxyz', index=':')
    assert len(images) == 4 and result.idpp is not None
    np.testing.assert_allclose([image.positions[0] for image in images], [[1.5, 0, 5]] * 4)
    np.testing.assert_allclose(images[-1].positions[1], [-0.1, 1.5, 6])


@pytest.mark.asyncio
async def test_existing_run_directory_is_never_overwritten(tmp_path, endpoints):
    existing = tmp_path / 'neb'
    existing.mkdir()
    (existing / 'user.txt').write_text('keep')
    result = await call_ts(tmp_path, **prepare())
    assert not result.is_success and 'exists' in result.message
    assert (existing / 'user.txt').read_text() == 'keep'


def _cp2k_evaluated_band(directory, final_energies):
    seed = read(directory / 'band.extxyz', index=':')
    first_energies = [-24.80, -24.74, -24.79]
    (directory / 'band.ener').write_text(
        '0 ' + ' '.join(map(str, first_energies)) + ' 0.1 0.1\n'
        + '3 ' + ' '.join(map(str, final_energies)) + ' 0.1 0.1\n',
    )
    for index, frame in enumerate(seed):
        trajectory = directory / f'cloudra-neb-pos-Replica_nr_{index + 1}-1.xyz'
        write(trajectory, frame, format='xyz', comment=f'i =        0, E = {first_energies[index]:.10f}')
        if index == 1:
            frame.positions[1, 0] = 0.025
        write(trajectory, frame, format='xyz', append=True, comment=f'i =        3, E = {final_energies[index]:.10f}')


@pytest.mark.asyncio
async def test_analyze_exports_native_peak_and_periodic_dimer_inputs(tmp_path, endpoints):
    prepared = await call_ts(tmp_path, **prepare(engine='cp2k'))
    assert prepared.is_success, prepared.message
    directory = Path(prepared.run_dir)
    _cp2k_evaluated_band(directory, [-24.8, -24.7, -24.79])

    result = await call_ts(tmp_path, type='analyze', run_dir='neb', dimer_dir='refine')

    assert result.is_success, result.message
    assert result.band_complete is True
    assert result.native_converged is None
    assert result.highest_interior_images == [1]
    assert result.forward_peak_ev == pytest.approx(0.1 * Hartree)
    assert result.reverse_peak_ev == pytest.approx(0.09 * Hartree)
    assert result.reaction_energy_ev == pytest.approx(0.01 * Hartree)
    assert all(image.geometry_observed for image in result.images)
    assert Path(result.candidate_path).is_file()
    geometry = read(result.candidate_path)
    assert geometry.positions[1, 0] == pytest.approx(0.025)
    assert geometry.constraints[0].get_indices().tolist() == [0]
    fragment = (tmp_path / 'refine/dimer.inc').read_text()
    assert 'TYPE TRANSITION_STATE' in fragment
    assert '&DIMER_VECTOR\n  0 0 0\n  -1 0 0\n' in fragment
    assert (tmp_path / 'refine/fixed-atoms.inc').is_file()


@pytest.mark.asyncio
async def test_analyze_keeps_signed_differences_and_requires_bound_evidence(tmp_path, endpoints):
    prepared = await call_ts(tmp_path, **prepare(engine='cp2k'))
    assert prepared.is_success, prepared.message
    directory = Path(prepared.run_dir)
    _cp2k_evaluated_band(directory, [-24.8, -24.81, -24.79])

    result = await call_ts(tmp_path, type='analyze', run_dir='neb', candidate_path='ts.extxyz')
    assert result.is_success and result.band_complete is True
    assert result.forward_peak_ev == pytest.approx(-0.01 * Hartree)
    assert result.reverse_peak_ev == pytest.approx(-0.02 * Hartree)
    assert result.candidate_path is None and not (tmp_path / 'ts.extxyz').exists()

    (directory / 'cloudra-neb-pos-Replica_nr_1-1.xyz').unlink()
    incomplete = await call_ts(tmp_path, type='analyze', run_dir='neb')
    assert incomplete.is_success and incomplete.band_complete is False
    assert incomplete.images[1].energy_ev is not None
    assert not incomplete.highest_interior_images and incomplete.forward_peak_ev is None

    with (directory / 'band.extxyz').open('a') as stream:
        stream.write('\n')
    changed = await call_ts(tmp_path, type='analyze', run_dir='neb')
    assert not changed.is_success and 'changed' in changed.message


def test_vasp_dimer_axis_uses_native_species_order_and_cartesian_vectors(tmp_path):
    from cloudra.tools.core.periodic_dimer import band_tangent, write_dimer

    peak = Atoms('AgLiAg', positions=[[1, 1, 3], [0, 3, 4], [3, 3, 3]], cell=[8, 8, 12], pbc=True,
                 constraint=FixAtoms([0, 2]))
    left = peak.copy()
    right = peak.copy()
    left.positions[1, 0] = 7.8
    right.positions[1, 0] = 0.3
    axis = band_tangent(left, peak, right)
    files, _ = write_dimer(tmp_path, 'vasp', peak, axis)
    assert set(files) == {'POSCAR', 'INCAR.dimer'}
    assert 'IBRION = 44' in (tmp_path / 'INCAR.dimer').read_text()
    poscar = tmp_path / 'POSCAR'
    assert [line.split() for line in poscar.read_text().splitlines()[-3:]] == [
        ['0', '0', '0'], ['0', '0', '0'], ['1', '0', '0'],
    ]
    assert read(poscar).get_chemical_symbols() == ['Ag', 'Ag', 'Li']
