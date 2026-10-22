"""Open-shell ingress preserves declared electronic and concrete atom identity."""
import pytest

pytest.importorskip('rdkit')

from rdkit import Chem
from rdkit.Chem import AllChem

from cloudra.tools.Chemtool.reaction_mapping import (
    bind_reaction_structures,
)
from cloudra.tools.core.reaction_state import heavy_binding, set_heavy_binding, structure_tables
from cloudra.tools.core.ts_inputs import FileConformer, TsInput
from cloudra.tools.core.ts_process import (
    _assemble,
    _bound_input_structure,
    _build,
    _declare,
    _endpoint_identity_error,
    _geometry_connectivity_error,
    _guess,
    _map,
)
from tests.test_ts_stage_inputs import record_fixture


def _mol(smiles):
    mol = Chem.AddHs(Chem.MolFromSmiles(smiles))
    assert AllChem.EmbedMolecule(mol, randomSeed=42) == 0
    return Chem.MolFromMolBlock(Chem.MolToMolBlock(mol), removeHs=False)


def _file_record(tmp_path, smiles='C[C](C)C', multiplicity=2, charge=0, electronic_character=None):
    mol = _mol(smiles)
    xyz, graph = tmp_path / 'seed.xyz', tmp_path / 'seed.mol'
    xyz.write_text(Chem.MolToXYZBlock(mol))
    graph.write_text(Chem.MolToMolBlock(mol))
    record = record_fixture(tmp_path)
    record.input.reaction.reactant_smiles = record.input.reaction.product_smiles = smiles
    record.input.reaction.multiplicity, record.input.reaction.charge = multiplicity, charge
    if electronic_character is not None:
        value = record.input.model_dump()
        value['reaction']['electronic_character'] = electronic_character
        from cloudra.tools.core.ts_inputs import TsInput
        record.input = TsInput.model_validate(value)
    record.input.reaction.selected_candidate = 0
    record.input.conformers.guidance.ring_order = []
    record.input.conformers.reactant = record.input.conformers.product = FileConformer(
        kind='file', xyz_path=str(xyz), mol_path=str(graph))
    return record, mol


def test_doublet_file_advances_without_compute_and_records_declared_bond_orders(tmp_path, monkeypatch):
    from cloudra.tools.core.ts_inputs import ProvidedGuess
    from cloudra.tools.core.ts_state_view import build_process_view

    record, mol = _file_record(tmp_path)
    provenance = tmp_path / 'source.txt'
    provenance.write_text('Externally supplied geometry provenance')
    record.input.guess = ProvidedGuess(kind='provided', xyz_path=record.input.conformers.reactant.xyz_path,
                                     evidence_refs=[str(provenance)])
    monkeypatch.setattr('cloudra.tools.core.ts_process._submit_step',
                        lambda *_: pytest.fail('Identity validation submitted a compute job'))
    for stage in (_declare, _build, _map, _assemble, _guess):
        stage(record)
        assert record.blocked is None
        assert record.terminal is None
    assert record.structures.product_to_reactant is not None
    assert sum(atom.GetNumRadicalElectrons() for atom in record.structures.reactant.GetAtoms()) == 1
    view = build_process_view(record.model_dump(), [], can_write=True)
    assert view.structures['reactant']['electronic_state']['is_open_shell'] is True
    assert _endpoint_identity_error(record, 'reactant', (
        [atom.GetSymbol() for atom in mol.GetAtoms()], mol.GetConformer().GetPositions().tolist())) == ''


def test_open_shell_declaration_refuses_wrong_formal_charge(tmp_path):
    record, _ = _file_record(tmp_path, '[CH3]', multiplicity=2, charge=-1)
    _declare(record)
    assert record.terminal == 'invalid_input'
    assert 'charge' in record.stage_record('declare').detail.lower()


@pytest.mark.parametrize('smiles,multiplicity,electronic_character', [
    ('[CH2][CH2]', 1, None),
    ('[CH2][CH2]', 3, None),
    ('O=O', 3, None),
    ('O=O', 1, 'open_shell'),
])
def test_declared_general_spin_coupling_advances_file_identity(
    tmp_path, smiles, multiplicity, electronic_character,
):
    record, mol = _file_record(tmp_path, smiles, multiplicity,
                               electronic_character=electronic_character)
    for stage in (_declare, _build, _map):
        stage(record)
        assert record.blocked is None
        assert record.terminal is None
    electronic = structure_tables(record)['reactant']['electronic_state']
    assert electronic['is_open_shell'] is True
    assert electronic['n_alpha'] - electronic['n_beta'] == multiplicity - 1
    assert _endpoint_identity_error(record, 'reactant', (
        [atom.GetSymbol() for atom in mol.GetAtoms()], mol.GetConformer().GetPositions().tolist())) == ''


def test_odd_electron_multiplicity_parity_is_refused_before_compute(tmp_path):
    record, _ = _file_record(tmp_path, '[CH3]', multiplicity=1)
    _declare(record)
    assert record.terminal == 'invalid_input'
    assert 'parity' in record.stage_record('declare').detail.lower()


def test_file_ingress_checks_formal_charge_even_when_declaration_was_bypassed(tmp_path):
    record, _ = _file_record(tmp_path, '[CH3]', multiplicity=2, charge=-1)
    _build(record)
    with pytest.raises(ValueError, match='charge'):
        _bound_input_structure(record, 'reactant')


def test_doublet_nondefault_explicit_binding_keeps_exact_source_indices(tmp_path):
    record, _ = _file_record(tmp_path)
    _build(record)
    for role in ('reactant', 'product'):
        setattr(record.structures, role, set_heavy_binding(getattr(record.structures, role), [4, 2, 3, 1]))
    _map(record)
    assert record.blocked is None
    assert {role: heavy_binding(getattr(record.structures, role)) for role in ('reactant', 'product')} == {
        'reactant': [4, 2, 3, 1], 'product': [4, 2, 3, 1]}


def test_open_shell_geometry_rejects_missing_and_extra_pairs(tmp_path):
    mol = _mol('C[C](C)C')
    symbols = [atom.GetSymbol() for atom in mol.GetAtoms()]
    positions = mol.GetConformer().GetPositions().tolist()
    missing = [point[:] for point in positions]
    missing[-1] = [20., 20., 20.]
    assert 'missing bonds' in _geometry_connectivity_error(
        mol, (symbols, missing), 0, 'reactant', multiplicity=2)
    extra = [point[:] for point in positions]
    extra[0] = [positions[2][0] + .8, positions[2][1], positions[2][2]]
    assert 'extra bonds' in _geometry_connectivity_error(
        mol, (symbols, extra), 0, 'reactant', multiplicity=2)


def _binding(smiles, mol, *, multiplicity=2, explicit_indices=None, electronic_character=None, selected_candidate=None):
    if explicit_indices is not None:
        mol = set_heavy_binding(mol, explicit_indices)
    request = TsInput(reaction=dict(reactant_smiles=smiles, product_smiles=smiles,
        charge=0, multiplicity=multiplicity, electronic_character=electronic_character,
        selected_candidate=selected_candidate))
    return bind_reaction_structures(request, mol, mol)


def test_open_and_closed_shell_symmetry_both_offer_complete_candidates():
    for smiles, multiplicity in (('C[C](C)C', 2), ('CC', 1)):
        mol = _mol(smiles)
        result = _binding(smiles, mol, multiplicity=multiplicity)
        assert result['binding_status'] == 'complete'
        assert result['mapping_status'] == 'ambiguous'
        assert result['candidates'] and result['candidates'][0]['atom_map']
        assert result['atom_map'] == result['candidates'][0]['atom_map']
        assert 'Automatically selected' in result['message']
        assert _binding(smiles, mol, multiplicity=multiplicity, selected_candidate=0)['binding_status'] == 'complete'


def test_open_shell_partial_hydrogen_labels_are_preserved_in_every_candidate():
    mol = _mol('C[C](C)C')
    mol.GetAtomWithIdx(4).SetAtomMapNum(1)
    result = _binding('C[C](C)C', mol)
    assert result['binding_status'] == 'complete'
    assert result['mapping_status'] == 'ambiguous'
    assert result['candidates']
    assert result['atom_map'] == result['candidates'][0]['atom_map']
    assert all(candidate['atom_map'][4] == 5 for candidate in result['candidates'])
    assert 'Automatically selected' in result['message']


@pytest.mark.parametrize('label_change,diagnostic', [('conflict', 'conflict'), ('duplicate', 'unique')])
def test_open_shell_invalid_hydrogen_labels_cannot_be_overridden(label_change, diagnostic):
    reactant = _mol('C[C](C)C')
    reactant.GetAtomWithIdx(4).SetAtomMapNum(1)
    product = Chem.Mol(reactant)
    if label_change == 'conflict':
        product.GetAtomWithIdx(4).SetAtomMapNum(2)
    else:
        product.GetAtomWithIdx(5).SetAtomMapNum(1)
    request = TsInput(reaction=dict(reactant_smiles='C[C](C)C', product_smiles='C[C](C)C',
        charge=0, multiplicity=2, selected_candidate=0))
    result = bind_reaction_structures(request, reactant, product)
    assert result['binding_status'] == 'inconclusive'
    assert result['atom_map'] == result['candidates'] == []
    assert any('hydrogen' in item and diagnostic in item for item in result['binding_diagnostics'])


def test_open_shell_source_identity_annotations_are_not_representative_provenance(tmp_path):
    record, _ = _file_record(tmp_path)
    path = tmp_path / 'seed.mol'
    mol = Chem.MolFromMolFile(str(path), removeHs=False)
    mol.GetAtomWithIdx(0).SetAtomMapNum(1)
    path.write_text(Chem.MolToMolBlock(mol))
    _build(record)
    _map(record)
    assert record.blocked is not None
    assert 'complete and unique' in record.blocked.message


@pytest.mark.parametrize('smiles,concrete_smiles', [
    ('[13CH3][C](C)C', 'C[C](C)C'),
    ('[CH2]C[C@](F)(Cl)Br', '[CH2]C[C@@](F)(Cl)Br'),
    ('C[C]([2H])C', 'C[CH]C'),
])
def test_open_shell_symmetry_never_hides_isotope_stereo_or_radical_identity(smiles, concrete_smiles):
    result = _binding(smiles, _mol(concrete_smiles))
    assert result['binding_status'] == 'inconclusive'
    assert result['reactant_identity'] == 'mismatch'


def test_open_shell_high_symmetry_incomplete_enumeration_requires_explicit_binding():
    smiles = '[CH2]C(C(C)(C)C)(C(C)(C)C)C(C)(C)C'
    result = _binding(smiles, _mol(smiles))
    assert result['binding_status'] == 'inconclusive'
    assert any('enumeration' in item.lower() and 'labels' in item.lower()
               for item in result['binding_diagnostics'])


def test_closed_shell_connectivity_control_keeps_independent_bond_orders(tmp_path):
    record, mol = _file_record(tmp_path, 'CO', multiplicity=1)
    _build(record)
    _map(record)
    assert record.blocked is None
    assert _endpoint_identity_error(record, 'reactant', (
        [atom.GetSymbol() for atom in mol.GetAtoms()], mol.GetConformer().GetPositions().tolist())) == ''


def test_electronic_character_revision_restarts_declaration_and_invalidates_quantum_evidence(tmp_path):
    from cloudra.tools.core.ts_process import TsJobStep
    from cloudra.tools.core.ts_revision import plan_input_revision, revise_record
    from tests.test_ts_resume_transitions import request

    record, _ = _file_record(tmp_path, 'CO', multiplicity=1)
    _build(record)
    _map(record)
    record.stage = 'verdict'
    record.terminal = 'verified'
    record.job_steps = [TsJobStep(purpose='ts_opt', job_id=1, input_path='historical.inp', state='done',
                                 source_input_revision=record.declaration_revision)]
    change = request(record, {'reaction': {'electronic_character': 'open_shell'}})
    receipt = plan_input_revision(record, change)
    assert [reference.job_id for reference in receipt.invalidated] == [1]
    revised = revise_record(record, change, receipt)
    assert revised.stage == 'declare'
    assert revised.job_steps == []
    assert revised.input.reaction.selected_candidate is None


def test_open_shell_explicit_binding_cannot_override_concrete_atom_labels():
    smiles = '[CH3:1][C:2]([CH3:3])[CH3:4]'
    result = _binding(smiles, _mol(smiles), explicit_indices=[4, 2, 3, 1])
    assert result['binding_status'] == 'inconclusive'
    assert any('conflict' in item.lower() for item in result['binding_diagnostics'])


def test_open_shell_xyz_without_electronic_graph_has_actionable_checkpoint(tmp_path):
    record, _ = _file_record(tmp_path, '[CH2][CH2]', multiplicity=1)
    for role in ('reactant', 'product'):
        getattr(record.input.conformers, role).mol_path = None
    _build(record)
    assert record.blocked is not None
    assert 'MOL' in record.blocked.message


@pytest.mark.parametrize('smiles,multiplicity,electronic_character', [
    ('[CH2][CH2]', 1, None), ('O=O', 3, None), ('O=O', 1, 'open_shell'),
])
def test_single_generated_component_preserves_declared_general_state_before_compute(
    tmp_path, monkeypatch, smiles, multiplicity, electronic_character,
):
    from cloudra.tools.core.ts_inputs import GeneratedConformer

    record, _ = _file_record(tmp_path, smiles, multiplicity, electronic_character=electronic_character)
    source = GeneratedConformer(kind='generate', generation='ETKDGv3', seed=42)
    record.input.conformers.reactant = record.input.conformers.product = source
    monkeypatch.setattr('cloudra.tools.core.ts_process._submit_step',
                        lambda *_: pytest.fail('Generated identity validation submitted compute'))
    for stage in (_declare, _build, _map):
        stage(record)
        assert record.blocked is None
        assert record.terminal is None
    graph = _bound_input_structure(record, 'reactant')[1]
    assert sum(atom.GetNumRadicalElectrons() for atom in graph.GetAtoms()) == sum(
        atom.GetNumRadicalElectrons() for atom in Chem.MolFromSmiles(smiles).GetAtoms())
    assert structure_tables(record)['reactant']['electronic_state']['is_open_shell']


def test_character_revision_refreshes_pinned_digest_without_changing_binding(tmp_path):
    from cloudra.tools.core.ts_revision import plan_input_revision, revise_record
    from tests.test_ts_resume_transitions import request

    record, _ = _file_record(tmp_path, 'CO', multiplicity=1)
    _build(record)
    _map(record)
    original_digest = structure_tables(record)['reactant']['structure_digest']
    change = request(record, {'reaction': {'electronic_character': 'open_shell'}})
    revised = revise_record(record, change, plan_input_revision(record, change))
    assert heavy_binding(revised.structures.reactant) == [1, 2]
    for stage in (_declare, _build, _map):
        stage(revised)
        assert revised.blocked is None
        assert revised.terminal is None
    assert structure_tables(revised)['reactant']['structure_digest'] != original_digest


def test_generated_open_shell_fragments_are_unoptimized_seeds(tmp_path, monkeypatch):
    from cloudra.tools.core.ts_inputs import GeneratedConformer

    record, _ = _file_record(tmp_path, '[CH3].[CH3]', multiplicity=1)
    record.input.conformers.reactant = record.input.conformers.product = GeneratedConformer(
        kind='generate', generation='ETKDGv3', seed=42)
    monkeypatch.setattr('cloudra.tools.core.ts_process._submit_step',
                        lambda *_: pytest.fail('Fragment identity validation submitted compute'))
    for stage in (_declare, _build, _map):
        stage(record)
        assert record.blocked is None
        assert record.terminal is None
    assert structure_tables(record)['reactant']['components'] == 2
    assert structure_tables(record)['reactant']['electronic_state']['localized_radical_electrons'] == 2
    assert record.job_steps == []


def test_prepare_open_shell_singlet_reaches_only_mocked_quantum_submission(
    tmp_path, monkeypatch, ts_producer_authority,
):
    from pathlib import Path

    from cloudra.tools.core.ts_inputs import ProvidedGuess
    from cloudra.tools.core.ts_process import TsStartRequest, start

    record, _ = _file_record(tmp_path, '[CH2][CH2]', multiplicity=1)
    provenance = tmp_path / 'source.txt'
    provenance.write_text('Externally prepared candidate')
    record.input.guess = ProvidedGuess(kind='provided', xyz_path=str(tmp_path / 'seed.xyz'),
                                     evidence_refs=[str(provenance)])
    submissions = []

    def mock_submit(state, purpose, input_path, engine):
        submissions.append((purpose, engine, Path(input_path).read_text()))
        return '', 901

    monkeypatch.setattr('cloudra.tools.core.ts_process._submit_step', mock_submit)
    monkeypatch.setattr('cloudra.tools.core.ts_process._read_job_state', lambda *_: 'ready')
    result = start(TsStartRequest(request_key='open-singlet-prepare', input=record.input,
        workspace_dir=str(tmp_path), owner_conversation_id='project', owner_session_id='owner'))
    assert [(purpose, engine) for purpose, engine, _ in submissions] == [('ts_opt', 'orca')]
    assert '* xyz 0 1' in submissions[0][2]
    assert result.blocked is None
    assert result.terminal is None
    assert result.structures.product_to_reactant is not None
    assert result.stage == 'refine'


def test_open_shell_product_geometry_respects_declared_full_atom_remap(tmp_path):
    record, reactant = _file_record(tmp_path, 'C[NH]', multiplicity=2)
    order = [1, 0, *range(2, reactant.GetNumAtoms())]
    product = Chem.RenumberAtoms(reactant, order)
    xyz, graph = tmp_path / 'product.xyz', tmp_path / 'product.mol'
    xyz.write_text(Chem.MolToXYZBlock(product))
    graph.write_text(Chem.MolToMolBlock(product))
    record.input.conformers.product = FileConformer(kind='file', xyz_path=str(xyz), mol_path=str(graph))
    _build(record)
    _map(record)
    assert record.blocked is None
    assert record.structures.product_to_reactant == tuple(order)
    assert _endpoint_identity_error(record, 'product', (
        [atom.GetSymbol() for atom in reactant.GetAtoms()], reactant.GetConformer().GetPositions().tolist())) == ''


def test_explicit_closed_shell_carbene_keeps_graph_radicals_as_diagnostic(tmp_path):
    record, mol = _file_record(tmp_path, '[CH2]', multiplicity=1, electronic_character='closed_shell')
    for stage in (_declare, _build, _map):
        stage(record)
        assert record.blocked is None
        assert record.terminal is None
    electronic = structure_tables(record)['reactant']['electronic_state']
    assert electronic['is_open_shell'] is False
    assert electronic['localized_radical_electrons'] == 2
    assert record.structures.reactant.GetNumAtoms() == mol.GetNumAtoms()
    assert _endpoint_identity_error(record, 'reactant', (
        [atom.GetSymbol() for atom in mol.GetAtoms()], mol.GetConformer().GetPositions().tolist())) == ''


def test_explicit_closed_character_preserves_ambiguity_and_explicit_binding():
    smiles = '[CH2][CH2]'
    mol = _mol(smiles)
    result = _binding(smiles, mol, multiplicity=1, electronic_character='closed_shell')
    assert result['binding_status'] == 'complete'
    assert result['mapping_status'] == 'ambiguous'
    assert len(result['candidates']) == 2
    assert result['atom_map'] == result['candidates'][0]['atom_map']
    explicit = _binding(smiles, mol, multiplicity=1, electronic_character='closed_shell', explicit_indices=[2, 1])
    assert explicit['binding_status'] == 'complete'
    assert explicit['heavy_atom_bindings'] == {'reactant': [2, 1], 'product': [2, 1]}


def test_open_shell_coarse_seed_can_bind_but_wrong_stereochemistry_cannot_verify(tmp_path):
    record, mol = _file_record(tmp_path, '[CH2]C[C@](F)(Cl)Br', multiplicity=2)
    for index, point in enumerate(mol.GetConformer().GetPositions()):
        mol.GetConformer().SetAtomPosition(index, [-point[0], point[1], point[2]])
    (tmp_path / 'seed.xyz').write_text(Chem.MolToXYZBlock(mol))
    _build(record)
    _map(record)
    assert record.blocked is None
    assert record.structures.product_to_reactant is not None
    assert _endpoint_identity_error(record, 'reactant', (
        [atom.GetSymbol() for atom in mol.GetAtoms()], mol.GetConformer().GetPositions().tolist()))
