"""Convert periodic structures through the normal format_converter entry point."""

import numpy as np
import pytest
from ase import Atoms
from ase.io import read, write

from cloudra.tools.Chemtool import format_converter


@pytest.fixture
def bulk():
    return Atoms(
        'FeO', scaled_positions=[[0, 0, 0], [0.5, 0.5, 0.5]],
        cell=[[4, 0, 0], [1, 5, 0], [0, 0, 6]], pbc=True,
    )


async def convert(source, target, source_format, target_format):
    return await format_converter.FormatConverter().tool_call(
        format_converter.FormatConverter_input_schema(
            input_path=str(source), output_path=str(target), input_format=source_format, output_format=target_format,
        ), None,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize('target_format', ['cif', 'extxyz', 'xsf', 'gen'])
async def test_solid_conversion_uses_lattice_and_coordinates_without_rdkit(tmp_path, bulk, monkeypatch, target_format):
    def reject_rdkit(_atoms):
        raise AssertionError('a periodic geometry must never become an RDKit molecule')

    monkeypatch.setattr(format_converter, 'from_ase', reject_rdkit)
    source = tmp_path / 'CONTCAR'
    target = tmp_path / f'converted.{target_format}'
    write(source, bulk, format='vasp')

    result = await convert(source, target, 'contcar', target_format)
    assert result.is_success, result.message
    converted = read(target, format=target_format)
    np.testing.assert_allclose(converted.cell, bulk.cell, atol=1e-7)
    np.testing.assert_allclose(converted.positions, bulk.positions, atol=1e-7)
    assert converted.get_chemical_symbols() == ['Fe', 'O']
    assert converted.pbc.all()


@pytest.mark.asyncio
async def test_slab_roundtrip_preserves_xy_and_reports_vasp_periodicity(tmp_path, bulk):
    bulk.pbc = [True, True, False]
    source = tmp_path / 'slab.extxyz'
    xsf = tmp_path / 'slab.xsf'
    poscar = tmp_path / 'POSCAR'
    write(source, bulk, format='extxyz')
    result = await convert(source, xsf, 'extxyz', 'xsf')
    assert result.is_success, result.message
    assert read(xsf, format='xsf').pbc.tolist() == [True, True, False]

    result = await convert(xsf, poscar, 'xsf', 'poscar')
    assert result.is_success, result.message
    assert 'three periodic axes' in result.message
    assert read(poscar, format='vasp').pbc.all()


@pytest.mark.asyncio
async def test_qe_explicit_cell_can_be_converted_to_cp2k_geometry(tmp_path):
    qe = tmp_path / 'pw.pwi'
    qe.write_text(
        '&SYSTEM\n ibrav=0, nat=2, ntyp=2\n/\n'
        'CELL_PARAMETERS angstrom\n4 0 0\n1 5 0\n0 0 6\n'
        'ATOMIC_SPECIES\nFe 55.845 Fe.UPF\nO 15.999 O.UPF\n'
        'ATOMIC_POSITIONS crystal\nFe 0 0 0\nO 0.5 0.5 0.5\n',
        encoding='utf-8',
    )
    output = tmp_path / 'geometry.inc'
    result = await convert(qe, output, 'espresso-in', 'cp2k-geometry')
    assert result.is_success, result.message
    text = output.read_text(encoding='utf-8')
    assert '&CELL' in text and 'PERIODIC XYZ' in text
    assert '&COORD' in text
    rows = {tokens[0]: list(map(float, tokens[1:])) for line in text.splitlines()
            if (tokens := line.split())[0] in {'A', 'B', 'C', 'Fe', 'O'}}
    assert rows['B'] == [1, 5, 0]
    assert rows['O'] == [2.5, 2.5, 3]
    assert 'Fe.UPF' not in text


@pytest.mark.asyncio
@pytest.mark.parametrize(('mode', 'coordinates'), [
    ('Direct', '0.5 0.5 0.5'),
    ('Cartesian', '2.5 2.5 3'),
    ('Cartesian_angstrom', '2.5 2.5 3'),
])
async def test_abacus_geometry_reads_cell_units_and_declared_position_mode(tmp_path, mode, coordinates):
    from ase.units import Bohr

    source = tmp_path / 'STRU'
    source.write_text(
        'ATOMIC_SPECIES\nFe 55.845 Fe.upf\nO 15.999 O.upf\n'
        f'LATTICE_CONSTANT\n{1 / Bohr}\n'
        'LATTICE_VECTORS\n4 0 0\n1 5 0\n0 0 6\n'
        f'ATOMIC_POSITIONS\n{mode}\nFe\n0.0\n1\n0 0 0 m 1 1 1\n'
        f'O\n0.0\n1\n{coordinates} 1 1 1\n',
        encoding='utf-8',
    )
    output = tmp_path / 'geometry.extxyz'
    result = await convert(source, output, 'abacus-stru', 'extxyz')
    assert result.is_success, result.message
    atoms = read(output, format='extxyz')
    np.testing.assert_allclose(atoms.cell, [[4, 0, 0], [1, 5, 0], [0, 0, 6]])
    np.testing.assert_allclose(atoms.positions, [[0, 0, 0], [2.5, 2.5, 3]])
    assert atoms.get_chemical_symbols() == ['Fe', 'O']
    assert 'movement flags' in result.message


@pytest.mark.asyncio
@pytest.mark.parametrize(('target_format', 'ase_format'), [('cif', 'cif'), ('poscar', 'vasp'), ('pdb', 'proteindatabank')])
async def test_export_does_not_reflect_a_left_handed_source(tmp_path, target_format, ase_format):
    atoms = Atoms(
        ['C', 'F', 'Cl', 'Br'], positions=[(1, 1, 1), (2, 1, 1), (1, 2, 1), (1, 1, 2)],
        cell=[(-10, 0, 0), (0, 10, 0), (0, 0, 10)], pbc=True,
    )
    source = tmp_path / 'left.extxyz'
    target = tmp_path / f'right.{target_format}'
    write(source, atoms, format='extxyz')
    result = await convert(source, target, 'extxyz', target_format)
    assert result.is_success, result.message
    exported = read(target, format=ase_format)
    relative = exported.get_distances(0, [1, 2, 3], mic=True, vector=True)
    assert np.linalg.det(relative) == pytest.approx(1)
    assert np.linalg.det(exported.cell) > 0
    assert 'right-handed' in result.message


@pytest.mark.asyncio
async def test_partial_occupancy_array_cannot_be_exported_as_ordered_crystal(tmp_path, bulk):
    bulk.new_array('occupancy', np.array([0.5, 1.0]))
    source = tmp_path / 'partial.extxyz'
    target = tmp_path / 'ordered.cif'
    write(source, bulk, format='extxyz')
    result = await convert(source, target, 'extxyz', 'cif')
    assert not result.is_success and 'occupancy' in result.message
    assert not target.exists()


@pytest.mark.asyncio
async def test_qe_species_magnetization_is_not_translated_to_extxyz(tmp_path):
    source = tmp_path / 'magnetic.pwi'
    source.write_text(
        '&SYSTEM\n ibrav=0, nat=2, ntyp=2, nspin=2,\n'
        ' starting_magnetization(1)=0.5, starting_magnetization(2)=-0.5\n/\n'
        'CELL_PARAMETERS angstrom\n4 0 0\n0 4 0\n0 0 4\n'
        'ATOMIC_SPECIES\nFe1 55.845 Fe.UPF\nFe2 55.845 Fe.UPF\n'
        'ATOMIC_POSITIONS crystal\nFe1 0 0 0\nFe2 0.5 0.5 0.5\n',
        encoding='utf-8',
    )
    output = tmp_path / 'geometry.extxyz'
    result = await convert(source, output, 'espresso-in', 'extxyz')
    assert result.is_success, result.message
    atoms = read(output, format='extxyz')
    assert atoms.get_chemical_symbols() == ['Fe', 'Fe']
    assert not atoms.has('initial_magmoms')


@pytest.mark.asyncio
async def test_qe_variable_cell_alat_is_used_for_its_positions(tmp_path):
    source = tmp_path / 'relax.pwo'
    source.write_text(
        '     Program PWSCF v.7.3 starts\n'
        '     number of atoms/cell      =  1\n'
        '     celldm(1)=  5.000000\n'
        '     crystal axes: (cart. coord. in units of alat)\n'
        '               a(1) = ( 1.0 0.0 0.0 )\n'
        '               a(2) = ( 0.0 1.0 0.0 )\n'
        '               a(3) = ( 0.0 0.0 1.0 )\n'
        '     site n.     atom                  positions (alat units)\n'
        '         1           Fe  tau(   1) = (   0.0   0.0   0.0  )\n'
        '!    total energy              =   -2.0000 Ry\n\n'
        'CELL_PARAMETERS (alat=  8.000000)\n1 0 0\n0 1 0\n0 0 1\n\n'
        'ATOMIC_POSITIONS (alat)\nFe 0.25 0.25 0.25\n\n'
        '!    total energy              =   -3.0000 Ry\n',
        encoding='utf-8',
    )
    output = tmp_path / 'final.extxyz'
    result = await convert(source, output, 'espresso-out', 'extxyz')
    assert result.is_success, result.message
    atoms = read(output, format='extxyz')
    np.testing.assert_allclose(atoms.get_scaled_positions(), [[0.25, 0.25, 0.25]])
    assert '2 coordinate frames' in result.message
