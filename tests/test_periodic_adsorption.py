"""Exercise periodic site enumeration and rigid placement through the public tool."""

from types import SimpleNamespace

import numpy as np
import pytest
from ase import Atoms
from ase.io import read, write

from cloudra.tools import get_tools_lst


@pytest.fixture
def square_slab(tmp_path):
    slab = Atoms('Ag2', positions=[[0, 0, 5], [0, 0, 3]], cell=[3, 3, 14], pbc=(True, True, False))
    write(tmp_path / 'slab.extxyz', slab, format='extxyz')
    return slab


async def run_model(tmp_path, operation, *, source='slab.extxyz', output=None):
    entry = next(entry for entry in get_tools_lst() if entry.tool_name == 'periodic_model')
    tool = entry.instantiate(subagent=SimpleNamespace(working_directory=str(tmp_path)))
    return await tool.tool_call(tool.input_schema(input_path=source, operation=operation, output_path=output))


@pytest.mark.asyncio
async def test_square_surface_has_fourfold_hollow_without_diagonal_bridge(tmp_path, square_slab):
    preview = await run_model(tmp_path, {'type': 'adsorption_sites', 'side': 'top'})
    assert preview.is_success, preview.message
    sites = preview.adsorption_sites
    assert [site.kind for site in sites] == ['ontop', 'bridge', 'bridge', 'hollow']
    np.testing.assert_allclose([site.position_angstrom for site in sites], [
        [0, 0, 5], [0, 1.5, 5], [1.5, 0, 5], [1.5, 1.5, 5],
    ])
    assert sites[-1].atom_indices == [1, 1, 1, 1]
    assert preview.output_path is None


@pytest.mark.asyncio
async def test_oblique_surface_uses_periodic_plane_and_explicit_substrate_selection(tmp_path):
    a = [3, 0, 0]
    b = [1.5, 3 * np.sqrt(3) / 2, 0]
    slab = Atoms(
        'Ag2O', positions=[[0, 0, 5], [0, 0, 3], [1, 1, 8]],
        cell=[[2, 1, 15], a, b], pbc=(False, True, True),
    )
    write(tmp_path / 'slab.extxyz', slab, format='extxyz')
    preview = await run_model(tmp_path, {
        'type': 'adsorption_sites', 'side': 'top', 'surface_atoms': [1], 'kind': 'hollow',
    })
    assert preview.is_success, preview.message
    hollows = preview.adsorption_sites
    assert [site.index for site in hollows] == [5, 6]
    assert all(site.atom_indices == [1, 1, 1] for site in hollows)
    vector = np.add(a, b)
    np.testing.assert_allclose(
        [site.position_angstrom for site in hollows], [vector / 3 + [0, 0, 5], 2 * vector / 3 + [0, 0, 5]],
        atol=1e-7,
    )


@pytest.mark.asyncio
async def test_molecule_is_rigidly_anchored_then_atomic_coadsorption_reuses_output(tmp_path, square_slab):
    template = Atoms('COH', positions=[[1, 0, 0], [0, 0, 0], [0, 1, 0]])
    directory = tmp_path / 'templates'
    directory.mkdir()
    write(directory / 'molecule.xyz', template)
    result = await run_model(tmp_path, {
        'type': 'adsorb', 'side': 'top', 'site': 4, 'height_angstrom': 2,
        'adsorbate': {
            'path': 'templates/molecule.xyz', 'anchor_atom': 2,
            'orientation': {'axis_atom': 1, 'direction': 'outward', 'twist_degrees': 90},
        },
    }, output='molecular.extxyz')
    assert result.is_success, result.message
    adsorbed = read(result.output_path, format='extxyz')
    np.testing.assert_allclose(adsorbed.cell, square_slab.cell)
    np.testing.assert_allclose(adsorbed.positions[:2], square_slab.positions)
    assert adsorbed.pbc.tolist() == [True, True, False]
    adsorbate = adsorbed[2:]
    np.testing.assert_allclose(adsorbate.positions, [[1.5, 1.5, 8], [1.5, 1.5, 7], [0.5, 1.5, 7]], atol=1e-7)
    np.testing.assert_allclose(adsorbate.get_all_distances(), template.get_all_distances())
    assert result.adsorbate_min_distance_angstrom == pytest.approx(np.sqrt(6.5))
    assert result.adsorption_sites[0].kind == 'hollow'

    coadsorbed = await run_model(tmp_path, {
        'type': 'adsorb', 'side': 'top', 'site': {'atom_index': 4}, 'height_angstrom': 3, 'adsorbate': 'Li',
    }, source='molecular.extxyz', output='coadsorbed.extxyz')
    assert coadsorbed.is_success, coadsorbed.message
    final = read(coadsorbed.output_path, format='extxyz')
    np.testing.assert_allclose(final.positions[-1], [1.5, 1.5, 10])
    assert final.get_chemical_symbols()[-1] == 'Li'


@pytest.mark.asyncio
async def test_poscar_requires_explicit_vacuum_axis_and_keeps_original_pbc(tmp_path, square_slab):
    write(tmp_path / 'POSCAR', square_slab, format='vasp')
    operation = {'type': 'adsorb', 'side': 'bottom', 'site': {'atom_index': 2}, 'height_angstrom': 1, 'adsorbate': 'Li'}
    failure = await run_model(tmp_path, operation, source='POSCAR', output='bottom.extxyz')
    assert not failure.is_success and 'vacuum_axis' in failure.message
    assert not (tmp_path / 'bottom.extxyz').exists()

    success = await run_model(tmp_path, {**operation, 'vacuum_axis': 'c'}, source='POSCAR', output='bottom.extxyz')
    assert success.is_success, success.message
    slab = read(success.output_path, format='extxyz')
    assert slab.pbc.all()
    np.testing.assert_allclose(slab.positions[-1], [0, 0, 2])


@pytest.mark.asyncio
async def test_coincident_molecule_fails_without_writing(tmp_path, square_slab):
    write(tmp_path / 'inward.xyz', Atoms('OC', positions=[[0, 0, 0], [0, 0, -1]]))
    result = await run_model(tmp_path, {
        'type': 'adsorb', 'side': 'top', 'site': {'atom_index': 1}, 'height_angstrom': 1,
        'adsorbate': {'path': 'inward.xyz', 'anchor_atom': 1},
    }, output='overlap.extxyz')
    assert not result.is_success and 'coincides' in result.message
    assert not (tmp_path / 'overlap.extxyz').exists()


@pytest.mark.asyncio
async def test_roundtrip_square_preserves_fourfold_hollows_on_a_tilted_face(tmp_path):
    from scipy.spatial.transform import Rotation

    rotation = Rotation.from_euler('xyz', [23, 38, 17], degrees=True)
    slab = Atoms(
        'Ag4', positions=rotation.apply([[0, 0, 5], [3, 0, 5], [0, 3, 5], [3, 3, 5]]),
        cell=rotation.apply(np.diag([6, 6, 14])), pbc=(True, True, False),
    )
    write(tmp_path / 'slab.extxyz', slab, format='extxyz')
    preview = await run_model(tmp_path, {'type': 'adsorption_sites', 'side': 'top'})
    assert preview.is_success, preview.message
    sites = preview.adsorption_sites
    assert [site.kind for site in sites] == ['ontop'] * 4 + ['bridge'] * 8 + ['hollow'] * 4
    assert all(len(site.atom_indices) == 4 for site in sites if site.kind == 'hollow')


@pytest.mark.asyncio
@pytest.mark.parametrize(('cell', 'pbc', 'positions', 'height', 'distance'), [
    ([[3, 0, 0], [0, 3, 0], [60, 0, 12]], (True, True, False), [[0, 0, 5]], 3, 3),
    ([[4, 0, 0], [3.8, 0.3, 0], [0, 0, 10]], (True, True, True), [[0, 0, 5], [0.46, -0.09, 6]], 1,
     np.hypot(0.26, 0.21)),
])
async def test_distance_uses_true_periodic_images_in_skew_cells(tmp_path, cell, pbc, positions, height, distance):
    slab = Atoms(['Ag'] * len(positions), positions=positions, cell=cell, pbc=pbc)
    write(tmp_path / 'slab.extxyz', slab, format='extxyz')
    result = await run_model(tmp_path, {
        'type': 'adsorb', 'side': 'top', 'site': {'atom_index': 1}, 'vacuum_axis': 'c',
        'height_angstrom': height, 'adsorbate': 'O',
    }, output='with-oxygen.extxyz')
    assert result.is_success, result.message
    assert result.adsorbate_min_distance_angstrom == pytest.approx(distance)


@pytest.mark.asyncio
async def test_periodic_slab_split_at_cell_boundary_uses_the_vacuum_facing_layer(tmp_path):
    slab = Atoms('Ag2', positions=[[0, 0, 9], [0, 0, 1]], cell=[3, 3, 10], pbc=True)
    write(tmp_path / 'POSCAR', slab, format='vasp')
    preview = await run_model(tmp_path, {
        'type': 'adsorption_sites', 'side': 'top', 'vacuum_axis': 'c', 'kind': 'ontop',
    }, source='POSCAR')
    assert preview.is_success, preview.message
    assert preview.adsorption_sites[0].atom_indices == [2]
    result = await run_model(tmp_path, {
        'type': 'adsorb', 'side': 'top', 'vacuum_axis': 'c', 'site': preview.adsorption_sites[0].index,
        'height_angstrom': 1, 'adsorbate': 'O',
    }, source='POSCAR', output='boundary.extxyz')
    assert result.is_success, result.message
    final = read(result.output_path, format='extxyz')
    np.testing.assert_allclose(final.positions[:2], slab.positions)
    assert final.positions[-1, 2] % 10 == pytest.approx(2)


@pytest.mark.asyncio
async def test_adsorbate_atoms_cannot_coincide_across_periodic_images(tmp_path, square_slab):
    write(tmp_path / 'span.xyz', Atoms('CO', positions=[[0, 0, 0], [3, 0, 0]]))
    result = await run_model(tmp_path, {
        'type': 'adsorb', 'side': 'top', 'site': {'atom_index': 1}, 'height_angstrom': 2,
        'adsorbate': {'path': 'span.xyz', 'anchor_atom': 1},
    }, output='overlap.extxyz')
    assert not result.is_success and 'adsorbate atoms coincide' in result.message.lower()
    assert not (tmp_path / 'overlap.extxyz').exists()


@pytest.mark.asyncio
async def test_invalid_adsorbate_symbol_returns_an_actionable_error(tmp_path, square_slab):
    (tmp_path / 'invalid.xyz').write_text('1\ninvalid element\nQq 0 0 0\n', encoding='utf-8')
    result = await run_model(tmp_path, {
        'type': 'adsorb', 'side': 'top', 'site': {'atom_index': 1}, 'height_angstrom': 2,
        'adsorbate': {'path': 'invalid.xyz', 'anchor_atom': 1},
    }, output='invalid.extxyz')
    assert not result.is_success and 'Qq' in result.message
    assert not (tmp_path / 'invalid.extxyz').exists()
