"""Concrete correspondence is proved on owned molecules, never copied from model arrays."""
import pytest

pytest.importorskip('rdkit', reason='concrete chemistry evidence requires the chem extra')
from rdkit import Chem
from rdkit.Chem import AllChem

from cloudra.tools.Chemtool.reaction_mapping import bind_reaction_structures
from cloudra.tools.core.ts_inputs import ConformerGuidance, FileConformer, QmCalculation, TsInput
from cloudra.tools.core.ts_process import TsProcessRecord, _bound_input_structure, _build, _map
from tests.test_ts_stage_inputs import record_fixture


def molecule(smiles):
    mol = Chem.AddHs(Chem.MolFromSmiles(smiles))
    assert AllChem.EmbedMolecule(mol, randomSeed=42) == 0
    return Chem.MolFromMolBlock(Chem.MolToMolBlock(mol), removeHs=False)


def test_constructed_rotation_still_rejects_the_wrong_declared_species(tmp_path):
    """An identity permutation proves row correspondence, not chemical identity."""
    from cloudra.tools.core.ts_process import _declare
    mol = molecule('CO')
    xyz, graph = tmp_path / 'wrong.xyz', tmp_path / 'wrong.mol'
    xyz.write_text(Chem.MolToXYZBlock(mol))
    graph.write_text(Chem.MolToMolBlock(mol))
    record = TsProcessRecord(run_id='rotation', run_dir=str(tmp_path), workspace_dir=str(tmp_path),
        input=TsInput(reaction=dict(reactant_smiles='CCO', product_smiles='CCO', charge=0, multiplicity=1),
            conformers=dict(reactant=dict(kind='file', xyz_path=str(xyz), mol_path=str(graph)),
                product=dict(kind='rotate_about_bond', atoms=(0, 1), degrees=30))))
    _declare(record)
    _build(record)
    _map(record)
    assert record.blocked is not None
    assert record.blocked.failure_class == 'input_identity_unconfirmed'
    assert record.structures.product_to_reactant is None


def declaration(smiles='CCO', product=None, selection=None):
    return TsInput(reaction=dict(reactant_smiles=smiles, product_smiles=product or smiles,
        charge=0, multiplicity=1, selected_candidate=selection))


def file_record(tmp_path, smiles='CCO', product=None):
    record = record_fixture(tmp_path, input=declaration(smiles))
    for role, identity in (('reactant', smiles), ('product', product or smiles)):
        mol = molecule(identity)
        xyz, graph = tmp_path / (role + '.xyz'), tmp_path / (role + '.mol')
        xyz.write_text(Chem.MolToXYZBlock(mol))
        graph.write_text(Chem.MolToMolBlock(mol))
        setattr(record.input.conformers, role, FileConformer(kind='file', xyz_path=str(xyz), mol_path=str(graph)))
    return record


def test_element_consistent_permutation_cannot_clear_identity_mismatch():
    result = bind_reaction_structures(declaration(), molecule('COC'), molecule('COC'))
    assert result['binding_status'] == 'inconclusive'
    assert result['reactant_identity'] == result['product_identity'] == 'mismatch'
    assert result['atom_map'] == []


def test_ambiguous_concrete_binding_allows_explicit_override_of_ranked_candidate():
    mol = molecule('CC')
    request = declaration('CC')
    result = bind_reaction_structures(request, mol, mol)
    assert result['binding_status'] == 'complete'
    assert result['mapping_status'] == 'ambiguous'
    assert result['atom_map'] == result['candidates'][0]['atom_map']
    assert len(result['candidates']) == 2
    request.reaction.selected_candidate = 1
    selected = bind_reaction_structures(request, mol, mol)
    assert selected['binding_status'] == 'complete'
    assert selected['atom_map'] == result['candidates'][1]['atom_map']
    assert selected['heavy_atom_bindings'] == result['candidates'][1]['heavy_atom_bindings']
    assert selected['mapping_status'] == 'ambiguous'
    assert selected['atom_map'] != result['atom_map']


def test_unambiguous_valid_binding_accepts_every_explicit_atom():
    mol = molecule('O')
    result = bind_reaction_structures(declaration('O'), mol, mol)
    assert result['binding_status'] == 'complete'
    assert result['atom_map'] == [1, 2, 3]
    assert result['reactant_identity'] == result['product_identity'] == 'match'


def test_identity_mismatch_requests_only_the_wrong_endpoint(tmp_path):
    record = file_record(tmp_path, product='COC')
    _build(record)
    _map(record)
    assert record.blocked.failure_class == 'input_identity_unconfirmed'
    assert [issue['role'] for issue in record.blocked.issues] == ['product']
    assert record.blocked.issues[0]['code'] == 'endpoint_identity_mismatch'
    assert record.blocked.needs == ['conformers.product', 'reaction.product_smiles']
    assert record.structures.product_to_reactant is None


@pytest.mark.parametrize('labels', [(1, 0, 0), (1, 1, 1)])
def test_partial_or_duplicate_concrete_labels_cannot_be_ignored(labels):
    mol = molecule('CCO')
    for atom, label in zip(mol.GetAtoms(), labels):
        atom.SetAtomMapNum(label)
    result = bind_reaction_structures(declaration(), mol, mol)
    assert result['binding_status'] == 'inconclusive'
    assert any('complete and unique' in diagnostic for diagnostic in result['binding_diagnostics'])


def test_source_edits_do_not_silently_change_owned_structure(tmp_path):
    from pathlib import Path
    record = file_record(tmp_path)
    _build(record)
    _map(record)
    assert record.blocked is None
    before = record.model_dump_json()
    for role in ('reactant', 'product'):
        source = getattr(record.input.conformers, role)
        Path(source.mol_path).write_text(Chem.MolToMolBlock(molecule('COC')))
        Path(source.xyz_path).write_text('3\nreplaced source\nO 0 0 0\nH 0 0 1\nH 0 1 0\n')
    _build(record)
    _map(record)
    assert record.blocked is None
    assert Chem.MolToSmiles(Chem.RemoveHs(_bound_input_structure(record, 'reactant')[1])) == 'CCO'
    assert record.structures.product_to_reactant == tuple(range(9))
    assert TsProcessRecord.model_validate_json(before).structures.product_to_reactant == record.structures.product_to_reactant


def test_conformer_identity_checked_before_optimizer_submission(tmp_path, monkeypatch):
    record = file_record(tmp_path, product='COC')
    record.input.conformers.product.optimization = QmCalculation(engine='xtb', method='GFN2-xTB', basis_set='')
    monkeypatch.setattr('cloudra.tools.core.ts_process._submit_step',
        lambda *_: pytest.fail('Wrong identity cannot spend compute'))
    _build(record)
    assert record.blocked.failure_class == 'input_identity_unconfirmed'
    assert record.job_steps == []


def test_imported_xyz_preserves_concrete_graph_for_final_endpoint_proof(tmp_path):
    from cloudra.tools.core.ts_process import _endpoint_identity_error
    record = file_record(tmp_path, 'O')
    record.input.conformers.reactant.mol_path = record.input.conformers.product.mol_path = None
    _build(record)
    _map(record)
    assert record.blocked is None
    mol = record.structures.reactant
    assert record.structures.product is not None
    assert _endpoint_identity_error(record, 'reactant', (
        [a.GetSymbol() for a in mol.GetAtoms()], mol.GetConformer().GetPositions().tolist())) == ''


@pytest.mark.parametrize('passed', [True, False])
def test_guidance_warning_is_retained_without_deciding_acceptance(tmp_path, monkeypatch, passed):
    record = file_record(tmp_path, 'O')
    record.input.conformers.guidance = ConformerGuidance(distance_filters=[dict(atoms=[0, 1], min_ang=.5, max_ang=1.5)])
    warning = 'Warning: unexpected covalent contacts: [(0, 1)]'
    reasons = [] if passed else ['distance window 0-1 outside [0.5, 1.5]']
    monkeypatch.setattr('cloudra.tools.core.preorganization.qualify_geometry',
        lambda *_: (passed, reasons, {'0-1': .97}, [warning]))
    _build(record)
    restored = TsProcessRecord.model_validate_json(record.model_dump_json())
    stage = restored.stage_record('build')
    assert warning in stage.detail
    assert stage.status == ('done' if passed else 'blocked')
    if passed:
        assert restored.blocked is None
    else:
        assert restored.blocked.failure_class == 'seed_guidance_failed'
        assert reasons[0] in restored.blocked.message
        assert warning in restored.blocked.message


def test_symmetric_file_endpoints_automatically_bind_and_persist_ranked_candidate(tmp_path):
    from cloudra.tools.core.reaction_state import heavy_binding, structure_tables
    record = file_record(tmp_path, 'CC')
    _build(record)
    table = structure_tables(record)['reactant']
    assert table['atoms'][0]['symbol'] == 'C' and table['atoms'][0]['number'] == 1
    result = bind_reaction_structures(record.input, record.structures.reactant, record.structures.product)
    assert result['mapping_status'] == 'ambiguous'
    chosen = result['candidates'][0]
    _map(record)
    assert record.blocked is None
    assert record.input.reaction.selected_candidate is None
    assert 'Automatically selected' in record.stage_record('map').detail
    assert [index + 1 for index in record.structures.product_to_reactant] == chosen['atom_map']
    restored = TsProcessRecord.model_validate_json(record.model_dump_json())
    assert restored.structures.product_to_reactant == record.structures.product_to_reactant
    for role in ('reactant', 'product'):
        assert heavy_binding(getattr(restored.structures, role)) == chosen['heavy_atom_bindings'][role]


def test_reselecting_a_complete_candidate_preserves_its_original_concrete_meaning(tmp_path):
    from cloudra.tools.core.ts_inputs import TsResumeRequest
    from cloudra.tools.core.ts_revision import plan_input_revision, revise_record

    record = file_record(tmp_path, 'CC')
    _build(record)
    candidates = bind_reaction_structures(record.input, record.structures.reactant, record.structures.product)['candidates']
    _map(record)
    assert record.blocked is None
    assert [index + 1 for index in record.structures.product_to_reactant] == candidates[0]['atom_map']
    request = TsResumeRequest(changes={'reaction': {'selected_candidate': 1}},
        reason='Override the automatically selected correspondence', request_key='select', expected_revision=record.revision)
    record = revise_record(record, request, plan_input_revision(record, request))
    assert record.structures.product_to_reactant is None
    _map(record)
    assert [index + 1 for index in record.structures.product_to_reactant] == candidates[1]['atom_map']
    request = TsResumeRequest(changes={'reaction': {'selected_candidate': 0}},
        reason='Choose the other inspected correspondence', request_key='reselect', expected_revision=record.revision)
    revised = revise_record(record, request, plan_input_revision(record, request))
    assert revised.structures.product_to_reactant is None
    _map(revised)
    assert revised.blocked is None
    assert [index + 1 for index in revised.structures.product_to_reactant] == candidates[0]['atom_map']
    assert [index + 1 for index in record.structures.product_to_reactant] == candidates[1]['atom_map']


def test_wrong_persisted_graph_binding_cannot_override_identity(tmp_path):
    from cloudra.tools.core.reaction_state import set_heavy_binding
    record = file_record(tmp_path)
    _build(record)
    record.structures.reactant = set_heavy_binding(record.structures.reactant, [2, 1, 3])
    _map(record)
    assert record.blocked.failure_class == 'input_identity_unconfirmed'
    assert record.structures.product_to_reactant is None


@pytest.mark.parametrize('declared,concrete', [
    ('F[C@](Cl)(Br)I', 'F[C@@](Cl)(Br)I'),
    ('[13CH3]CO', 'CCO'),
    ('[2H]CO', 'CO'),
])
def test_stereo_and_isotope_identity_are_not_repaired_by_candidate_selection(declared, concrete):
    mol = molecule(concrete)
    result = bind_reaction_structures(declaration(declared, selection=0), mol, mol)
    assert result['reactant_identity'] == result['product_identity'] == 'mismatch'
    assert result['binding_status'] == 'inconclusive' and result['atom_map'] == []


def test_component_order_is_bound_to_actual_hydrogen_rows(tmp_path):
    from cloudra.tools.core.reaction_state import structure_tables
    from tests.agent_scenarios import d1_component_order_files
    reactant_xyz, reactant_graph = d1_component_order_files(tmp_path)
    reactant = Chem.MolFromMolFile(str(reactant_graph), removeHs=False)
    order = [0, 1, 2, 3, 10, 11, 4, 5, 6, 7, 8, 9, 12, 13, 14, 15]
    product = Chem.RenumberAtoms(reactant, order)
    xyz, graph = tmp_path / 'heavy_first.xyz', tmp_path / 'heavy_first.mol'
    xyz.write_text(Chem.MolToXYZBlock(product))
    graph.write_text(Chem.MolToMolBlock(product))
    record = record_fixture(tmp_path, input=declaration('C=CC=C.C=C'))
    record.input.conformers.reactant = FileConformer(kind='file', xyz_path=str(reactant_xyz), mol_path=str(reactant_graph))
    record.input.conformers.product = FileConformer(kind='file', xyz_path=str(xyz), mol_path=str(graph))
    _build(record)
    result = bind_reaction_structures(record.input, record.structures.reactant, record.structures.product)
    _map(record)
    assert structure_tables(record)['reactant']['atoms'][4]['symbol'] == 'H'
    assert record.blocked is None
    assert result['mapping_status'] == 'ambiguous'
    assert [index + 1 for index in record.structures.product_to_reactant] == result['candidates'][0]['atom_map']
    for candidate in result['candidates']:
        assert sorted(candidate['atom_map']) == list(range(1, 17))
        for index, target in enumerate(candidate['atom_map']):
            assert product.GetAtomWithIdx(index).GetAtomicNum() == reactant.GetAtomWithIdx(target - 1).GetAtomicNum()
