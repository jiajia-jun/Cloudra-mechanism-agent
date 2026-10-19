"""Native input conversion preserves geometry and declared molecular state."""

import threading

import pytest
from ase.units import Bohr
from rdkit import Chem

from cloudra.tools.Chemtool.format_converter import FormatConverter, FormatConverter_input_schema
from cloudra.tools.core.calculation_intent import native_input_geometry
from cloudra.tools.core.molecule import read_molecule, total_charge


def native_text(engine, *, bohr=False):
    if engine == 'gjf':
        return f'#p HF/STO-3G{" units=bohr" if bohr else ""}\n\nsource geometry\n\n-1 2\nH 0 0 0\nH 1.4 0 0\n\n'
    return f'! HF STO-3G{" Bohrs" if bohr else ""}\n* xyz -1 2\nH 0 0 0\nH 1.4 0 0\n*\n'


async def convert(tmp_path, input_format, output_format, text):
    source = tmp_path / f'source.{input_format}'
    source.write_text(text)
    target = tmp_path / f'converted.{output_format}'
    result = await FormatConverter().tool_call(FormatConverter_input_schema(
        input_path=str(source), input_format=input_format,
        output_path=str(target), output_format=output_format,
    ), session=None)
    return result, target


@pytest.mark.asyncio
@pytest.mark.parametrize('input_format,output_format', [('gjf', 'inp'), ('inp', 'gjf')])
@pytest.mark.parametrize('bohr', [False, True])
async def test_native_to_native_preserves_state_without_solver_options(tmp_path, input_format, output_format, bohr):
    result, target = await convert(tmp_path, input_format, output_format, native_text(input_format, bohr=bohr))

    assert result.is_success, result.message
    mol = read_molecule(input_path=target)
    assert total_charge(mol) == -1
    assert mol.GetIntProp('cloudra_multiplicity') == 2
    assert mol.GetNumBonds() == 0
    assert mol.GetConformer().GetAtomPosition(1).x == pytest.approx(1.4 * (Bohr if bohr else 1), abs=1e-8)
    assert 'HF' not in target.read_text()
    assert 'STO-3G' not in target.read_text()
    assert 'skeleton' in result.message.lower()
    assert 'method' in result.message.lower()


@pytest.mark.asyncio
@pytest.mark.parametrize('input_format', ['gjf', 'inp'])
@pytest.mark.parametrize('output_format', ['xyz', 'sdf'])
async def test_native_metadata_survives_coordinate_artifact_roundtrip(tmp_path, input_format, output_format):
    result, target = await convert(tmp_path, input_format, output_format, native_text(input_format, bohr=True))

    assert result.is_success, result.message
    mol = read_molecule(input_path=target)
    assert total_charge(mol) == -1
    assert mol.GetIntProp('cloudra_multiplicity') == 2
    assert mol.GetProp('cloudra_graph_status') == 'unresolved'
    assert mol.GetProp('cloudra_source_coordinate_units') == 'bohr'
    assert mol.GetNumBonds() == 0
    assert Chem.GetFormalCharge(mol) == 0  # Molecular charge is not an atomic identity assignment.
    assert mol.GetConformer().GetAtomPosition(1).x == pytest.approx(1.4 * Bohr, abs=1e-4)


@pytest.mark.asyncio
@pytest.mark.parametrize('input_format', ['gjf', 'inp'])
async def test_native_to_mol_discloses_unrepresentable_state(tmp_path, input_format):
    result, target = await convert(tmp_path, input_format, 'mol', native_text(input_format))

    assert result.is_success, result.message
    assert 'charge -1' in result.message
    assert 'multiplicity 2' in result.message
    assert 'not retained' in result.message
    mol = Chem.MolFromMolFile(str(target), removeHs=False)
    assert mol.GetNumBonds() == 0
    assert Chem.GetFormalCharge(mol) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize('text,reason', [
    ('! HF\n* xyzfile -1 2 other.xyz\n', 'xyzfile'),
    (native_text('inp') + '$new_job\n! HF\n', 'multiple'),
    (native_text('inp') + '* xyz 0 1\nHe 0 0 0\n*\n', 'one'),
    (native_text('inp').replace('*\n', ''), 'closing'),
])
async def test_orca_conversion_refuses_ambiguous_or_external_geometry(tmp_path, text, reason):
    result, target = await convert(tmp_path, 'inp', 'xyz', text)

    assert not result.is_success
    assert reason in result.message.lower()
    assert not target.exists()


@pytest.mark.parametrize('units', ['! Bohrs\n', '%coords Units Bohrs end\n', '%coords\n Units Bohrs\nend\n'])
def test_orca_all_geometry_callers_share_unit_normalization(units):
    text = units + native_text('inp')
    mol = read_molecule(input_text=text, input_format='orca')

    assert total_charge(mol) == -1
    assert mol.GetIntProp('cloudra_multiplicity') == 2
    assert mol.GetConformer().GetAtomPosition(1).x == pytest.approx(1.4 * Bohr)
    assert native_input_geometry(text, engine='orca')[1][1][0] == pytest.approx(1.4 * Bohr)


@pytest.mark.asyncio
async def test_structure_conversion_file_io_runs_off_event_loop(tmp_path, monkeypatch):
    import cloudra.tools.Chemtool.format_converter as module

    loop_thread = threading.get_ident()
    original = module.os.path.isfile
    observed = []

    def check(path):
        observed.append(threading.get_ident())
        return original(path)

    monkeypatch.setattr(module.os.path, 'isfile', check)
    result, _ = await convert(tmp_path, 'gjf', 'xyz', native_text('gjf'))

    assert result.is_success, result.message
    assert observed
    assert all(thread != loop_thread for thread in observed)


@pytest.mark.asyncio
@pytest.mark.parametrize('input_format,extra', [('gjf', ' scf=(tight'), ('inp', '\n%scf Broken "quote')])
async def test_bad_solver_options_do_not_hide_convertible_geometry(tmp_path, input_format, extra):
    text = native_text(input_format)
    text = text.replace('HF/STO-3G', 'HF/STO-3G' + extra) if input_format == 'gjf' else text + extra

    result, target = await convert(tmp_path, input_format, 'xyz', text)

    assert result.is_success, result.message
    mol = read_molecule(input_path=target)
    assert total_charge(mol) == -1
    assert mol.GetConformer().GetAtomPosition(1).x == pytest.approx(1.4)


@pytest.mark.asyncio
@pytest.mark.parametrize('input_format', ['gjf', 'inp'])
async def test_native_xyz_native_chain_keeps_state_and_geometry(tmp_path, input_format):
    first, xyz = await convert(tmp_path, input_format, 'xyz', native_text(input_format, bohr=True))
    assert first.is_success, first.message
    second, target = await convert(tmp_path, 'xyz', input_format, xyz.read_text())

    assert second.is_success, second.message
    mol = read_molecule(input_path=target)
    assert total_charge(mol) == -1
    assert mol.GetIntProp('cloudra_multiplicity') == 2
    assert mol.GetConformer().GetAtomPosition(1).x == pytest.approx(1.4 * Bohr, abs=1e-8)


def test_orca_unknown_or_conflicting_units_and_charge_override_are_explicit():
    text = native_text('inp', bohr=True)
    with pytest.raises(ValueError, match='units'):
        read_molecule(input_text='%coords Units Angs end\n' + text, input_format='orca')
    with pytest.raises(ValueError, match='units'):
        read_molecule(input_text='%coords Units nonsense end\n' + native_text('inp'), input_format='orca')
    with pytest.raises(ValueError, match='charge mismatch'):
        read_molecule(input_text=text, input_format='orca', charge=0)


def test_orca_geometry_blank_lines_do_not_truncate_atoms():
    text = native_text('inp').replace('H 1.4', '\nH 1.4')
    mol = read_molecule(input_text=text, input_format='orca')

    assert mol.GetNumAtoms() == 2
    assert native_input_geometry(text, engine='orca')[1][1][0] == pytest.approx(1.4)


@pytest.mark.asyncio
async def test_coordinate_only_sdf_accepts_its_declared_total_charge_without_assigning_atom_charge(tmp_path):
    result, target = await convert(tmp_path, 'inp', 'sdf', native_text('inp'))
    assert result.is_success, result.message

    mol = read_molecule(input_path=target, charge=-1)
    assert total_charge(mol) == -1
    assert Chem.GetFormalCharge(mol) == 0
    with pytest.raises(ValueError, match='charge'):
        read_molecule(input_path=target, charge=0)


@pytest.mark.asyncio
@pytest.mark.parametrize('metadata', [
    'cloudra_total_charge=-1.5 cloudra_multiplicity=2',
    'cloudra_total_charge=-1 cloudra_multiplicity=0',
    'cloudra_total_charge=-1 cloudra_multiplicity=2 cloudra_coordinate_units=bohr',
])
async def test_invalid_coordinate_state_is_not_truncated_or_guessed(tmp_path, metadata):
    text = f'1\n{metadata}\nH 0 0 0\n'
    with pytest.raises(ValueError):
        read_molecule(input_text=text)
    result, target = await convert(tmp_path, 'xyz', 'inp', text)
    assert not result.is_success
    assert not target.exists()
