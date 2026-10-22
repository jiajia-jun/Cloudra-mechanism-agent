from types import SimpleNamespace

import pytest
from pydantic import ValidationError

pytest.importorskip('rdkit')
from rdkit import Chem

from cloudra.tools.Chemtool import reaction_mapping as mapping
from cloudra.tools.core.ts_inputs import TsInput


def declaration(smiles='CO', selected_candidate=None):
    return TsInput(reaction=dict(reactant_smiles=smiles, product_smiles=smiles,
        charge=0, multiplicity=1, selected_candidate=selected_candidate))


def test_unique_concrete_mapping_is_automatic_and_does_not_mutate_endpoints():
    reactant = Chem.AddHs(Chem.MolFromSmiles('CO'))
    product = Chem.RenumberAtoms(reactant, [1, 0, 2, 3, 4, 5])
    result = mapping.bind_reaction_structures(declaration(), reactant, product)
    assert result['binding_status'] == 'complete'
    assert result['atom_map'] == [2, 1, 3, 4, 5, 6]
    assert result['heavy_atom_bindings'] == {'reactant': [1, 2], 'product': [2, 1]}
    assert not any(atom.HasProp('cloudra_smiles_heavy_index') for atom in reactant.GetAtoms())


def test_concrete_symmetry_automatically_selects_ranked_complete_candidate():
    mol = Chem.AddHs(Chem.MolFromSmiles('CC'))
    result = mapping.bind_reaction_structures(declaration('CC'), mol, mol)
    assert result['mapping_status'] == 'ambiguous'
    assert result['binding_status'] == 'complete'
    assert result['atom_map'] == result['candidates'][0]['atom_map']
    assert 'Automatically selected' in result['message']
    assert len(result['candidates']) == 2
    assert all(candidate['atom_map'] and candidate['heavy_atom_bindings'] for candidate in result['candidates'])
    selected = mapping.bind_reaction_structures(declaration('CC', 1), mol, mol)
    assert selected['binding_status'] == 'complete'
    assert selected['atom_map'] == result['candidates'][1]['atom_map']
    assert selected['mapping_status'] == 'ambiguous'
    assert selected['atom_map'] != result['atom_map']


def test_confirmed_molecule_heavy_identity_prevents_reopening_symmetry():
    from cloudra.tools.core.reaction_state import set_heavy_binding
    mol = Chem.AddHs(Chem.MolFromSmiles('CC'))
    mol.AddConformer(Chem.Conformer(mol.GetNumAtoms()))
    mol = set_heavy_binding(mol, [1, 2])
    result = mapping.bind_reaction_structures(declaration('CC'), mol, mol)
    assert result['binding_status'] == 'complete'
    assert result['atom_map'] == list(range(1, mol.GetNumAtoms() + 1))


@pytest.mark.parametrize('reactant,product,expected_candidates', [
    ('N.O', '[NH4+].[OH-]', 1),
    ('OC=O', 'O=C=O.[H][H]', 4),
])
def test_hydrogen_transfer_and_free_hydrogen_have_complete_candidates(reactant, product, expected_candidates):
    request = TsInput(reaction=dict(reactant_smiles=reactant, product_smiles=product, charge=0, multiplicity=1))
    r_mol, p_mol = (Chem.AddHs(Chem.MolFromSmiles(smiles)) for smiles in (reactant, product))
    result = mapping.bind_reaction_structures(request, r_mol, p_mol)
    assert len(result['candidates']) == expected_candidates
    for candidate in result['candidates']:
        assert sorted(candidate['atom_map']) == list(range(1, r_mol.GetNumAtoms() + 1))
    assert result['binding_status'] == 'complete'
    assert result['atom_map'] == result['candidates'][0]['atom_map']
    assert result['mapping_status'] == ('unique' if expected_candidates == 1 else 'ambiguous')


def test_hydrogen_enumeration_refuses_truncation_and_complete_labels_resolve_it():
    reactant = Chem.MolFromSmiles('[H][H].[H][H].[H][H]')
    product = Chem.Mol(reactant)
    candidates, diagnostic = mapping._expand_full_atom_maps(reactant, product, [], [], [])
    assert candidates == [] and 'incomplete' in diagnostic
    for atom in reactant.GetAtoms():
        atom.SetAtomMapNum(atom.GetIdx() + 1)
    product = Chem.RenumberAtoms(reactant, list(reversed(range(6))))
    candidates, diagnostic = mapping._expand_full_atom_maps(reactant, product, [], [], [])
    assert candidates == [[6, 5, 4, 3, 2, 1]], diagnostic


def test_hydrogen_only_endpoints_offer_complete_concrete_correspondence():
    mol = Chem.MolFromSmiles('[H][H]')
    request = declaration('[H][H]')
    result = mapping.bind_reaction_structures(request, mol, mol)
    assert [candidate['atom_map'] for candidate in result['candidates']] == [[1, 2], [2, 1]]
    assert result['binding_status'] == 'complete'
    assert result['mapping_status'] == 'ambiguous'
    assert result['atom_map'] == [1, 2]
    request.reaction.selected_candidate = 1
    assert mapping.bind_reaction_structures(request, mol, mol)['atom_map'] == [2, 1]


def test_labels_preserve_transferred_hydrogen_identity():
    reactant, product = (Chem.AddHs(Chem.MolFromSmiles(smiles)) for smiles in ('OC=O', 'O=C=O.[H][H]'))
    for graph in (reactant, product):
        for atom in graph.GetAtoms():
            atom.SetAtomMapNum(atom.GetIdx() + 1)
    candidates, diagnostic = mapping._expand_full_atom_maps(reactant, product, [0, 1, 2], [0, 1, 2], [1, 2, 3])
    assert candidates == [[1, 2, 3, 4, 5]], diagnostic


def test_mapping_run_reference_excludes_independent_sources():
    request = mapping.ReactionMapping_input_schema(run_id='run-1', selected_candidate=1)
    assert request.run_id == 'run-1'
    with pytest.raises(ValidationError):
        mapping.ReactionMapping_input_schema(run_id='run-1', reactant_smiles='CO', product_smiles='CO')
    with pytest.raises(ValidationError):
        mapping.ReactionMapping_input_schema(reactant_smiles='CO', product_smiles='CO', reactant_binding={'indices': [1, 2]})


def test_mapping_is_a_write_tool():
    assert mapping.ReactionMapping().is_write()
    assert not mapping.ReactionMapping().is_read()
    from cloudra.tools.registry import TOOL_REGISTRY
    registration = next(item for item in TOOL_REGISTRY if item.tool_name == 'reaction_mapping')
    assert registration.supervisor_access == 'none'


def test_mapping_exposes_the_same_exclusive_contract_in_both_schema_exports():
    jsonschema = pytest.importorskip('jsonschema')
    for schema in (mapping.ReactionMapping_input_schema.model_json_schema(),
                   mapping.ReactionMapping_input_schema.to_parameters_schema()):
        jsonschema.validate({'run_id': 'r1', 'selected_candidate': 0}, schema)
        jsonschema.validate({'reactant_smiles': 'CO', 'product_smiles': 'CO'}, schema)
        for invalid in ({'run_id': 'r1'}, {'run_id': 'r1', 'selected_candidate': None},
                        {'run_id': 'r1', 'selected_candidate': 0, 'reactant_smiles': 'CO'}):
            with pytest.raises(jsonschema.ValidationError):
                jsonschema.validate(invalid, schema)


@pytest.mark.asyncio
async def test_run_candidate_choice_uses_existing_revision_transaction(monkeypatch, tmp_path, mock_session):
    from cloudra.services import ts_pipeline_context
    from cloudra.tools.Chemtool import ts_search_process
    from cloudra.tools.core.permission_model import Permission

    captured = []

    async def revise(tool, run_id, changes, reason, session):
        captured.append((run_id, changes, reason, session))
        return SimpleNamespace(is_success=True)

    from cloudra.tools.core.reaction_state import ReactionStructures, set_heavy_binding
    mol = Chem.AddHs(Chem.MolFromSmiles('CC'))
    mol.AddConformer(Chem.Conformer(mol.GetNumAtoms()))
    candidates = mapping.bind_reaction_structures(declaration('CC'), mol, mol)['candidates']
    chosen = candidates[1]
    state = ReactionStructures(reactant=set_heavy_binding(mol, chosen['heavy_atom_bindings']['reactant']),
        product=set_heavy_binding(mol, chosen['heavy_atom_bindings']['product']),
        product_to_reactant=tuple(index - 1 for index in chosen['atom_map']))
    record = SimpleNamespace(input=declaration('CC', selected_candidate=1), structures=state)
    monkeypatch.setattr(ts_search_process, 'revise_run', revise)
    monkeypatch.setattr(ts_search_process, '_read_resume_record', lambda *args: record)
    monkeypatch.setattr(ts_pipeline_context, 'pipeline_database', lambda: object())
    agent = SimpleNamespace(conversation_id='project', working_directory=str(tmp_path), permission_all=lambda: Permission.WRITE)
    result = await mapping.ReactionMapping(subagent=agent).tool_call(
        mapping.ReactionMapping_input_schema(run_id='run-1', selected_candidate=1), mock_session)
    assert result.is_success and result.binding_status == 'complete'
    assert captured[0][0:2] == ('run-1', {'reaction': {'selected_candidate': 1}})
    assert result.atom_map == chosen['atom_map']
    assert captured[0][3] is mock_session


@pytest.mark.asyncio
async def test_mapping_rejects_read_only_producer(mock_session):
    from cloudra.tools.core.permission_model import Permission
    agent = SimpleNamespace(permission_all=lambda: Permission.READ)
    result = await mapping.ReactionMapping(subagent=agent).tool_call(
        mapping.ReactionMapping_input_schema(reactant_smiles='CO', product_smiles='CO'), mock_session)
    assert not result.is_success
    assert result.candidates == []
