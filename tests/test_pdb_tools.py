"""PDB selection/cleaning is file-based, explicit and independent of repair extras."""
import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest


def _pdb(tmp_path):
    path = tmp_path / 'complex.pdb'
    path.write_text(
        'SEQRES   1 A    1  ALA\n'
        'ATOM      1  N   ALA A   1       0.000   0.000   0.000  1.00 10.00           N  \n'
        'ATOM      2  CA AALA A   1       1.400   0.000   0.000  0.40 11.00           C  \n'
        'ATOM      3  CA BALA A   1       1.500   0.000   0.000  0.60 12.00           C  \n'
        'HETATM    4  O   HOH A 101       1.000   2.000   0.000  1.00 13.00           O  \n'
        'HETATM    5 ZN    ZN A 102       2.000   2.000   0.000  1.00 14.00          ZN  \n'
        'HETATM    6  C1  LIG A 103       4.000   0.000   0.000  1.00 15.00           C  \n'
        'HETATM    7 FE   HEM A 104       4.000   2.000   0.000  1.00 16.00          FE  \n'
        'HETATM    8  N1  HEM A 104       4.000   4.000   0.000  1.00 16.00           N  \nEND\n'
    )
    return path


def test_public_tools_are_lazy_registered():
    from cloudra.tools.registry import TOOL_REGISTRY
    entries = {r.tool_name: r for r in TOOL_REGISTRY}
    assert {'pdb_inspect', 'pdb_clean'} <= entries.keys()


def test_clean_schema_only_requires_intent_and_files():
    from cloudra.tools.Chemtool.pdb_clean import PDBCleanInput
    schema = PDBCleanInput.to_parameters_schema()
    assert set(schema['required']) == {'input_path', 'output_path', 'purpose'}
    assert not {'expected_revision', 'hash', 'mapping', 'residue_map'} & schema['properties'].keys()
    with pytest.raises(ValueError):
        PDBCleanInput(input_path='x.pdb', output_path='y.cif', purpose=' ')


@pytest.mark.asyncio
async def test_preserve_clean_needs_no_analysis_and_logs_selected_altloc(tmp_path, monkeypatch):
    gemmi = pytest.importorskip('gemmi')
    from cloudra.tools.Chemtool.pdb_clean import PDBClean, PDBCleanInput
    from cloudra.tools.core import pdb_workflow
    source = _pdb(tmp_path)
    original = source.read_bytes()
    def unexpected(*args, **kwargs):
        pytest.fail('pure selection must not run template or interaction analysis')
    monkeypatch.setattr(pdb_workflow, 'inspect_missing', unexpected)
    monkeypatch.setattr(pdb_workflow, 'analyze_interactions', unexpected)
    tool = PDBClean(subagent=SimpleNamespace(working_directory=str(tmp_path)))
    result = await tool.tool_call(PDBCleanInput(input_path=source.name, output_path='out.cif', purpose='查看结构'), None)
    assert result.is_success, result.message
    out = gemmi.read_structure(result.output_path)
    assert len(out) == 1 and out[0][0][0]['CA'][0].pos.x == pytest.approx(1.5)
    assert source.read_bytes() == original
    log = json.loads(Path(result.change_log_path).read_text())
    assert log['purpose'] == '查看结构'
    assert log['effective_options']['waters'] == 'all'
    assert any(c['kind'] == 'altloc_selection' and c['selected_altloc'] == 'B' for c in result.changes)


@pytest.mark.asyncio
async def test_component_options_keep_cofactor_intact_and_exact_keep_overrides(tmp_path):
    gemmi = pytest.importorskip('gemmi')
    from cloudra.tools.Chemtool.pdb_clean import PDBClean, PDBCleanInput
    from cloudra.tools.core.pdb_structure import load_structure
    source = _pdb(tmp_path)
    structure, keys, _ = load_structure(str(source), 0, None)
    water_key = keys[(0,1)]
    result = await PDBClean().tool_call(PDBCleanInput(input_path=str(source), output_path=str(tmp_path/'out.cif'),
        purpose='移除独立离子与水', waters='none', metals='none', keep_residue_keys=[water_key]), None)
    assert result.is_success, result.message
    residues = list(gemmi.read_structure(result.output_path)[0][0])
    assert [r.name for r in residues] == ['ALA','HOH','LIG','HEM']
    assert len(residues[-1]) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize('options', [
    {'keep_residue_keys':['absent']}, {'remove_residue_keys':['absent']},
    {'keep_residue_keys':['same'],'remove_residue_keys':['same']},
    {'chains':['Z']}, {'model_index':9}, {'altloc':'Z'},
])
async def test_invalid_selection_never_publishes_output(tmp_path, options):
    pytest.importorskip('gemmi')
    from cloudra.tools.Chemtool.pdb_clean import PDBClean, PDBCleanInput
    result = await PDBClean().tool_call(PDBCleanInput(input_path=str(_pdb(tmp_path)),
        output_path=str(tmp_path/'out.cif'), purpose='test', **options), None)
    assert not result.is_success
    assert not (tmp_path/'out.cif').exists()
    assert not (tmp_path/'out.cif.changes.json').exists()


@pytest.mark.asyncio
async def test_clean_does_not_overwrite_existing_output_or_log(tmp_path):
    pytest.importorskip('gemmi')
    from cloudra.tools.Chemtool.pdb_clean import PDBClean, PDBCleanInput
    source = _pdb(tmp_path)
    output = tmp_path/'out.cif'
    log = tmp_path/'out.cif.changes.json'
    log.write_text('existing')
    result = await PDBClean().tool_call(PDBCleanInput(input_path=str(source), output_path=str(output),purpose='test'),None)
    assert not result.is_success and not output.exists() and log.read_text() == 'existing'


@pytest.mark.asyncio
async def test_wrappers_offload_work(tmp_path, monkeypatch):
    from cloudra.tools.Chemtool import pdb_inspect
    calls = []
    async def offload(func, *args):
        calls.append(func)
        return {'is_success':True, 'message':'ok'}
    monkeypatch.setattr(asyncio, 'to_thread', offload)
    result = await pdb_inspect.PDBInspect().tool_call(pdb_inspect.PDBInspectInput(input_path='x.pdb'),None)
    assert result.is_success and len(calls) == 1


def test_native_residue_address_handles_insertions_duplicates_and_long_chains(tmp_path):
    gemmi = pytest.importorskip('gemmi')
    from cloudra.tools.core.pdb_structure import load_structure, residue_keys
    source = _pdb(tmp_path)
    structure = gemmi.read_structure(str(source))
    structure[0][0].name = 'LongChain'
    structure[0][0][0].seqid.icode = 'A'
    structure[0][0].add_residue(structure[0][0][0].clone())
    keys = residue_keys(structure)
    assert len(set(keys.values())) == len(keys)
    assert keys[(0,0)].startswith('LongChain/ALA 1A')
    assert len(structure[0][0]) == 6
    # Equal mmCIF author addresses are merged by the parser; remove the
    # artificial duplicate before testing the normal author-address roundtrip.
    del structure[0][0][5]
    cif = tmp_path/'input.cif'
    structure.make_mmcif_document().write_file(str(cif))
    parsed, keys, summary = load_structure(str(cif))
    assert keys == residue_keys(parsed)


@pytest.mark.asyncio
async def test_pdb_rejects_long_chains_instead_of_truncating(tmp_path):
    gemmi = pytest.importorskip('gemmi')
    from cloudra.tools.Chemtool.pdb_clean import PDBClean, PDBCleanInput
    structure = gemmi.read_structure(str(_pdb(tmp_path)))
    structure[0][0].name = 'LongChain'
    source = tmp_path/'input.cif'
    structure.make_mmcif_document().write_file(str(source))
    result = await PDBClean().tool_call(PDBCleanInput(input_path=str(source), output_path=str(tmp_path/'out.pdb'), purpose='test'),None)
    assert not result.is_success and 'use .cif' in result.message
    assert not (tmp_path/'out.pdb').exists()


@pytest.mark.asyncio
async def test_remove_entire_chain_writes_only_retained_chains(tmp_path):
    gemmi = pytest.importorskip('gemmi')
    from cloudra.tools.Chemtool.pdb_clean import PDBClean, PDBCleanInput
    source = _pdb(tmp_path)
    structure = gemmi.read_structure(str(source))
    chain = gemmi.Chain('B')
    chain.add_residue(structure[0][0][1].clone())
    structure[0].add_chain(chain)
    source = tmp_path/'two.cif'
    structure.make_mmcif_document().write_file(str(source))
    result = await PDBClean().tool_call(PDBCleanInput(input_path=str(source),output_path=str(tmp_path/'out.cif'),purpose='keep only polymer',waters='none',ligands='none',metals='none'),None)
    assert result.is_success, result.message
    assert [c.name for c in gemmi.read_structure(result.output_path)[0]] == ['A']


@pytest.mark.asyncio
async def test_incomplete_water_analysis_cannot_delete_unknown_waters(tmp_path,monkeypatch):
    pytest.importorskip('gemmi')
    from cloudra.tools.Chemtool.pdb_clean import PDBClean, PDBCleanInput
    from cloudra.tools.core import pdb_workflow
    monkeypatch.setattr(pdb_workflow,'analyze_interactions',lambda *args: {
        'water_candidates':[], 'analysis_status':{'water_candidates':{'status':'unavailable','reason':'PLIP missing'}}})
    result = await PDBClean().tool_call(PDBCleanInput(input_path=str(_pdb(tmp_path)),output_path=str(tmp_path/'out.cif'),purpose='candidate waters',waters='candidates'),None)
    assert not result.is_success and 'no waters were removed' in result.message
    assert not (tmp_path/'out.cif').exists()


@pytest.mark.asyncio
async def test_zero_water_candidate_policy_does_not_require_interaction_backend(tmp_path, monkeypatch):
    gemmi = pytest.importorskip('gemmi')
    from cloudra.tools.Chemtool.pdb_clean import PDBClean, PDBCleanInput
    from cloudra.tools.core import pdb_workflow
    source = _pdb(tmp_path)
    structure = gemmi.read_structure(str(source))
    structure.remove_waters()
    structure.write_pdb(str(source))
    def unavailable(*args):
        pytest.fail('No water selection needs interaction analysis')
    monkeypatch.setattr(pdb_workflow,'analyze_interactions',unavailable)
    result = await PDBClean().tool_call(PDBCleanInput(input_path=str(source), output_path=str(tmp_path/'out.cif'),purpose='candidate water selection',waters='candidates'),None)
    assert result.is_success, result.message


@pytest.mark.asyncio
async def test_removed_connection_is_recorded_and_not_written_as_dangling_link(tmp_path):
    gemmi = pytest.importorskip('gemmi')
    from cloudra.tools.Chemtool.pdb_clean import PDBClean, PDBCleanInput
    structure = gemmi.read_structure(str(_pdb(tmp_path)))
    connection = gemmi.Connection()
    connection.name = 'test-metal-link'
    connection.type = gemmi.ConnectionType.MetalC
    connection.partner1 = gemmi.make_address(structure[0][0],structure[0][0][2],structure[0][0][2][0])
    connection.partner2 = gemmi.make_address(structure[0][0],structure[0][0][1],structure[0][0][1][0])
    structure.connections.append(connection)
    source = tmp_path/'links.cif'
    structure.make_mmcif_document().write_file(str(source))
    result = await PDBClean().tool_call(PDBCleanInput(input_path=str(source),output_path=str(tmp_path/'out.cif'),purpose='remove ions',metals='none'),None)
    assert result.is_success, result.message
    assert len(gemmi.read_structure(result.output_path).connections) == 0
    assert any(c.get('action') == 'remove_connection' and c['connection_name'] == 'test-metal-link' for c in result.changes)


@pytest.mark.parametrize('mode,waters,atoms', [('preserve','all',False),('docking','candidates',True),('md','all',True)])
def test_mode_options_are_transparent_and_each_override_wins(mode,waters,atoms):
    from cloudra.tools.Chemtool.pdb_clean import PDBCleanInput
    from cloudra.tools.core.pdb_workflow import effective_options
    value = PDBCleanInput(input_path='x.cif',output_path='y.cif',purpose='research',mode=mode)
    actual = effective_options(value.model_dump())
    assert (actual['waters'],actual['add_missing_atoms']) == (waters,atoms)
    assert actual['ligands'] == actual['metals'] == 'all'
    assert actual['add_missing_residues'] == 'none'
    value.waters, value.add_missing_atoms = 'none', False
    assert effective_options(value.model_dump())['waters'] == 'none'
    assert effective_options(value.model_dump())['add_missing_atoms'] is False


@pytest.mark.asyncio
async def test_real_public_inspect_and_gap_only_clean_use_same_keys_and_gap_ids(tmp_path):
    gemmi = pytest.importorskip('gemmi')
    pytest.importorskip('pdbfixer')
    pytest.importorskip('plip')
    pytest.importorskip('openmm')
    pytest.importorskip('openbabel.openbabel')
    from cloudra.tools.Chemtool.pdb_clean import PDBClean, PDBCleanInput
    from cloudra.tools.Chemtool.pdb_inspect import PDBInspect, PDBInspectInput
    from tests.test_pdb_repair import _structure
    structure = _structure(['ALA','GLY','VAL'],['ALA','SER','GLY','VAL'],numbers=[50,50,51],label_ids=[1,3,4],chain_name='LongChain')
    structure[0][0][1].seqid.icode = 'A'
    source = tmp_path/'enzyme.cif'
    structure.make_mmcif_document().write_file(str(source))
    original = source.read_bytes()
    report = await PDBInspect().tool_call(PDBInspectInput(input_path=str(source)),None)
    assert report.is_success, report.model_dump()
    gap, = report.internal_gaps
    assert gap['left_anchor'] in {r['residue_key'] for r in report.components}
    result = await PDBClean().tool_call(PDBCleanInput(input_path=str(source),output_path=str(tmp_path/'enzyme_md.cif'),purpose='repair selected internal gap',add_missing_residues='internal',gap_ids=[gap['gap_id']],add_missing_atoms=False),None)
    assert result.is_success, result.message
    assert [r.name for r in gemmi.read_structure(result.output_path)[0][0]] == ['ALA','SER','GLY','VAL']
    assert source.read_bytes() == original
    assert any(c.get('gap_id') == gap['gap_id'] and c.get('status') == 'modeled' for c in result.changes)
    assert Path(result.change_log_path).is_file()


def test_tool_schemas_do_not_import_optional_backends():
    import subprocess
    import sys
    code = '''
import sys
from cloudra.tools.Chemtool.pdb_inspect import PDBInspectInput
from cloudra.tools.Chemtool.pdb_clean import PDBCleanInput
PDBInspectInput.to_parameters_schema()
PDBCleanInput.to_parameters_schema()
assert not {'gemmi','pdbfixer','openmm','plip','openbabel'} & sys.modules.keys()
'''
    completed = subprocess.run([sys.executable,'-c',code],capture_output=True,text=True)
    assert completed.returncode == 0, completed.stderr


def test_highest_occupancy_does_not_favor_a_larger_low_occupancy_conformer(tmp_path):
    gemmi = pytest.importorskip('gemmi')
    from cloudra.tools.core.pdb_structure import residue_keys, select_altlocs
    source = _pdb(tmp_path)
    structure = gemmi.read_structure(str(source))
    residue = structure[0][0][0]
    residue[1].occ = 0.6
    residue[2].occ = 0.4
    extra = residue[2].clone()
    extra.name = 'CB'
    residue.add_atom(extra)
    changes = select_altlocs(structure,residue_keys(structure),'highest_occupancy')
    assert changes[0]['selected_altloc'] == 'A'
    assert {a.name for a in residue} == {'N','CA'}


def test_connection_pruning_preserves_surviving_conect_bond_multiplicity(tmp_path):
    gemmi = pytest.importorskip('gemmi')
    from cloudra.tools.core.pdb_structure import prune_connections
    structure = gemmi.read_structure(str(_pdb(tmp_path)))
    structure.add_conect(1,2,1)
    structure.add_conect(1,4,1)
    del structure[0][0][1]  # Remove only water atom serial 4.
    changes = prune_connections(structure)
    assert structure.conect_map == {1:[2],2:[1]}
    assert any(c.get('action') == 'remove_conect_records' for c in changes)
