import pytest
from pydantic import ValidationError

from cloudra.tools.core.ts_inputs import TsInput, TsInputChanges, apply_input_changes


def current_input():
    return TsInput(reaction=dict(reactant_smiles='CO', product_smiles='CO', charge=0, multiplicity=1),
        conformers=dict(product=dict(kind='file', xyz_path='endpoint.xyz', mol_path='endpoint.mol',
            evidence_refs=['minimum.log'], optimization=dict(engine='orca', method='B3LYP', basis_set='def2-SVP'))))


def test_mapping_selection_replaces_public_manual_binding_fields():
    source = current_input()
    assert source.reaction.selected_candidate is None
    with pytest.raises(ValidationError):
        TsInput.model_validate({**source.model_dump(), 'reaction': {**source.reaction.model_dump(), 'atom_map': [1]}})
    with pytest.raises(ValidationError):
        TsInputChanges(reaction={'selected_candidate': True})
    with pytest.raises(ValidationError):
        TsInputChanges(reaction={'selected_candidate': -1})


def test_source_patch_schema_keeps_file_optimization_meaning():
    from cloudra.tools.core.ts_inputs import ConformerSourceChanges
    description = ConformerSourceChanges.model_fields['optimization'].description
    assert 'supplied file geometry as-is' in description
    assert 'null' in description and 'omitted source fields retain' in description


def test_file_source_partial_null_clears_optimization_and_retains_evidence():
    current = current_input()
    updated = apply_input_changes(current, TsInputChanges(conformers={'product': {'optimization': None}}))
    assert updated.conformers.product.optimization is None
    assert updated.conformers.product.xyz_path == 'endpoint.xyz'
    assert updated.conformers.product.mol_path == 'endpoint.mol'
    assert updated.conformers.product.evidence_refs == ['minimum.log']
    assert current.conformers.product.optimization is not None


def test_source_patch_omission_retains_and_null_clears_optional_fields():
    updated = apply_input_changes(current_input(), TsInputChanges(conformers={'product': {'mol_path': None}}))
    assert updated.conformers.product.mol_path is None
    assert updated.conformers.product.optimization.method == 'B3LYP'
    updated = apply_input_changes(updated, TsInputChanges(conformers={'product': {'optimization': {'keywords': 'TightSCF'}}}))
    assert updated.conformers.product.optimization.keywords == 'TightSCF'
    assert updated.conformers.product.optimization.basis_set == 'def2-SVP'


def test_switching_source_kind_replaces_previous_kind_and_revalidates():
    changes = TsInputChanges(conformers={'product': {'kind': 'generate', 'generation': 'ETKDGv3', 'seed': 17}})
    updated = apply_input_changes(current_input(), changes)
    assert updated.conformers.product.kind == 'generate'
    assert updated.conformers.product.seed == 17
    assert updated.conformers.product.optimization is None
    with pytest.raises(ValueError):
        apply_input_changes(current_input(), TsInputChanges(conformers={'product': {'seed': 8}}))
