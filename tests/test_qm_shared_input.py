"""QM tools share rendering and never infer an XYZ calculation's charge."""
import asyncio

import pytest

from cloudra.tools.Chemtool.qm_input_writer import QmInputWriter, QmInputWriter_input_schema
from cloudra.tools.core.molecule import read_molecule

pytestmark = pytest.mark.usefixtures('rdkit_chemistry')

H2 = '2\nhydrogen\nH 0 0 0\nH 0 0 0.74\n'


def request(tmp_path, *, engine='gaussian', **values):
    return QmInputWriter_input_schema(
        engine=engine, method='HF', basis_set='STO-3G', source_type='xyz_file',
        source_value=str(tmp_path / 'hydrogen.xyz'), output_path=str(tmp_path / 'scan.inp'),
        **values,
    )


def test_gaussian_shared_writer_separates_geometry_from_scan_cards(tmp_path):
    declaration = request(tmp_path, charge=0, task_type=[{'opt': 'modredundant,maxstep=10'}],
        end_setting='B 1 2 S 4 0.05')
    native = QmInputWriter._build_gjf(declaration, read_molecule(input_text=H2, charge=0))
    geometry, tail = native.split('\n0 1\n', 1)[1].split('\n\n', 1)
    assert [row.split()[0] for row in geometry.splitlines()] == ['H', 'H']
    assert tail == 'B 1 2 S 4 0.05\n\n'


@pytest.mark.parametrize('engine', ['gaussian', 'orca'])
def test_shared_renderer_requires_explicit_xyz_charge(tmp_path, engine):
    declaration = request(tmp_path, engine=engine)
    with pytest.raises(ValueError, match='XYZ.*explicit.*charge'):
        QmInputWriter.render_input(declaration, read_molecule(input_text=H2))


@pytest.mark.parametrize('engine', ['gaussian', 'orca'])
def test_shared_renderer_keeps_declared_charge_multiplicity_and_resources(tmp_path, engine):
    declaration = request(tmp_path, engine=engine, charge=1, multiplicity=2,
        nproc=8, mem='8192MB')
    native = QmInputWriter.render_input(declaration, read_molecule(input_text=H2, charge=1))
    if engine == 'gaussian':
        assert '%nproc=8\n' in native and '%mem=8192MB\n' in native
        assert '\n1 2\n' in native
    else:
        assert '%pal nprocs 8 end\n' in native and '%maxcore 1024\n' in native
        assert '* xyz 1 2\n' in native


def test_shared_renderer_inherits_mol_graph_charge(tmp_path):
    Chem = pytest.importorskip('rdkit.Chem')
    sodium = Chem.MolFromSmiles('[Na+]')
    sodium.AddConformer(Chem.Conformer(1))
    mol = read_molecule(input_text=Chem.MolToMolBlock(sodium), input_format='mol')
    native = QmInputWriter.render_input(request(tmp_path), mol)
    assert '\n1 1\n' in native


def test_shared_renderer_places_default_checkpoint_next_to_gaussian_output(tmp_path):
    declaration = request(tmp_path, charge=0)
    native = QmInputWriter.render_input(declaration, read_molecule(input_text=H2, charge=0))
    assert f'%chk={tmp_path / "scan.chk"}\n' in native
    assert declaration.chk_name is None


def test_shared_renderer_preserves_explicit_gaussian_checkpoint(tmp_path):
    declaration = request(tmp_path, charge=0, chk_name='restart.chk')
    native = QmInputWriter.render_input(declaration, read_molecule(input_text=H2, charge=0))
    assert '%chk=restart.chk\n' in native


@pytest.mark.asyncio
@pytest.mark.parametrize('engine', ['gaussian', 'orca'])
async def test_writer_tool_uses_the_same_xyz_charge_requirement(tmp_path, engine):
    declaration = request(tmp_path, engine=engine)
    await asyncio.to_thread((tmp_path / 'hydrogen.xyz').write_text, H2)
    result = await QmInputWriter().tool_call(declaration, None)
    assert not result.is_success
    assert 'XYZ' in result.message and 'charge' in result.message
    assert not await asyncio.to_thread((tmp_path / 'scan.inp').exists)
