import pytest

pytest.importorskip("rdkit", reason="concrete chemistry evidence requires the chem extra")

from rdkit import Chem
from rdkit.Chem import AllChem

from cloudra.tools.Chemtool import reaction_mapping


def concrete(smiles):
    mol = Chem.AddHs(Chem.MolFromSmiles(smiles))
    AllChem.EmbedMolecule(mol, randomSeed=42)
    return Chem.MolToMolBlock(mol)


def test_element_consistent_map_cannot_clear_identity_mismatch():
    request = reaction_mapping.ReactionMapping_input_schema(reactant_smiles='CCO', product_smiles='CCO', reactant_text=concrete('COC'), product_text=concrete('COC'), reactant_format='mol', product_format='mol')
    binding = reaction_mapping.check_concrete_binding(request, {'atom_map': list(range(1, 10)), 'watch_pairs': []})
    assert binding['binding_status'] == 'inconclusive'
    assert binding['reactant_identity'] == 'mismatch'
    assert binding['atom_map'] == []


def test_explicit_map_keeps_ambiguous_concrete_binding_inconclusive():
    text = concrete('CC')
    request = reaction_mapping.ReactionMapping_input_schema(reactant_smiles='CC', product_smiles='CC', reactant_text=text, product_text=text, reactant_format='mol', product_format='mol')
    binding = reaction_mapping.check_concrete_binding(request, {'atom_map': list(range(1, 9)), 'watch_pairs': []})
    assert binding['binding_status'] == 'inconclusive'


def test_unambiguous_valid_binding_accepts_full_atom_map():
    text = concrete('O')
    request = reaction_mapping.ReactionMapping_input_schema(reactant_smiles='O', product_smiles='O', reactant_text=text, product_text=text, reactant_format='mol', product_format='mol')
    binding = reaction_mapping.check_concrete_binding(request, {'atom_map': [1, 2, 3], 'watch_pairs': []})
    assert binding['binding_status'] == 'complete'
    assert binding['reactant_identity'] == binding['product_identity'] == 'match'


def test_identity_is_rechecked_after_geometry_source_changes(tmp_path, monkeypatch):
    from cloudra.tools.core.ts_inputs import FileConformer
    from cloudra.tools.core.ts_process import _build, _guess, _map
    from tests.test_ts_stage_inputs import record_fixture
    record=record_fixture(tmp_path)
    record.input.conformers.guidance.ring_order=[]
    record.input.reaction.atom_map=list(range(9))
    files=[]
    for role in ('reactant','product'):
        mol=Chem.MolFromMolBlock(concrete('CCO'),removeHs=False)
        xyz=tmp_path/(role+'.xyz')
        xyz.write_text(Chem.MolToXYZBlock(mol))
        mol_path=tmp_path/(role+'.mol')
        mol_path.write_text(Chem.MolToMolBlock(mol))
        setattr(record.input.conformers,role,FileConformer(kind='file',xyz_path=str(xyz),mol_path=str(mol_path)))
        files.append(mol_path)
    _build(record)
    _map(record)
    assert record.blocked is None
    original=record.input_binding['hashes'].copy()
    Path=__import__('pathlib').Path
    wrong = Chem.RenumberAtoms(Chem.MolFromMolBlock(concrete('COC'), removeHs=False), [0,2,1,*range(3,9)])
    Path(record.current_seed_mol_path).write_text(Chem.MolToMolBlock(wrong))
    monkeypatch.setattr('cloudra.tools.core.ts_process._queued_path',lambda *_: (_ for _ in ()).throw(AssertionError('identity mismatch cannot enter path search')))
    _guess(record)
    assert record.blocked.failure_class=='input_identity_unconfirmed'
    assert record.input_binding['binding_status']=='inconclusive'
    assert 'connectivity' in record.input_binding['binding_diagnostics'][0]
    assert record.input_binding.get('hashes')!=original


def test_conformer_identity_checked_before_optimizer_submission(tmp_path, monkeypatch):
    from cloudra.tools.core.ts_inputs import FileConformer, TsCalculation
    from cloudra.tools.core.ts_process import _build
    from tests.test_ts_stage_inputs import record_fixture
    record = record_fixture(tmp_path)
    record.input.conformers.guidance.ring_order = []
    mol = Chem.RenumberAtoms(Chem.MolFromMolBlock(concrete('COC'), removeHs=False), [0,2,1,*range(3,9)])
    xyz, graph = tmp_path/'wrong.xyz', tmp_path/'wrong.mol'
    xyz.write_text(Chem.MolToXYZBlock(mol))
    graph.write_text(Chem.MolToMolBlock(mol))
    record.input.conformers.reactant = FileConformer(kind='file', xyz_path=str(xyz), mol_path=str(graph),
        optimization=TsCalculation(engine='xtb', method='GFN2-xTB', keywords=''))
    monkeypatch.setattr('cloudra.tools.core.ts_process._submit_step', lambda *_: (_ for _ in ()).throw(AssertionError('Wrong identity cannot spend compute')))
    _build(record)
    assert record.blocked.failure_class == 'input_identity_unconfirmed'
    assert record.job_steps == []


def test_xyz_binding_preserves_concrete_graph_for_final_endpoint_proof(tmp_path):
    from cloudra.tools.core.ts_inputs import FileConformer
    from cloudra.tools.core.ts_process import _build, _endpoint_identity_error, _map
    from tests.test_ts_stage_inputs import record_fixture
    record = record_fixture(tmp_path)
    record.input.reaction.reactant_smiles = record.input.reaction.product_smiles = 'O'
    record.input.reaction.atom_map = [0,1,2]
    record.input.conformers.guidance.ring_order = []
    mol = Chem.MolFromMolBlock(concrete('O'), removeHs=False)
    xyz = tmp_path/'water.xyz'
    xyz.write_text(Chem.MolToXYZBlock(mol))
    record.input.conformers.reactant = record.input.conformers.product = FileConformer(kind='file', xyz_path=str(xyz))
    _build(record)
    _map(record)
    assert record.blocked is None
    assert record.current_seed_mol_path and record.product_seed_mol_path
    assert _endpoint_identity_error(record, 'reactant', ([a.GetSymbol() for a in mol.GetAtoms()], mol.GetConformer().GetPositions().tolist())) == ''
