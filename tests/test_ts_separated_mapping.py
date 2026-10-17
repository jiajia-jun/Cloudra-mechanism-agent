"""Separated-product declarations reach the real concrete mapping entry points."""
import pytest

pytest.importorskip('rdkit')
from rdkit import Chem

from cloudra.tools.Chemtool.reaction_mapping import bind_reaction_structures
from cloudra.tools.core.ts_inputs import TsInput
from cloudra.tools.core.ts_process import TsProcessRecord, _map


def separated_endpoints():
    declaration = TsInput(reaction={
        'reactant_smiles': 'N.O', 'product_smiles': ['[NH4+]', '[OH-]'],
        'charge': 0, 'multiplicity': 1,
    })
    reactant = Chem.AddHs(Chem.MolFromSmiles('N.O'))
    product = Chem.AddHs(Chem.MolFromSmiles('[NH4+].[OH-]'))
    for molecule in (reactant, product):
        molecule.AddConformer(Chem.Conformer(molecule.GetNumAtoms()))
    return declaration, reactant, product


def test_bind_separated_products_preserves_grouping_and_maps_every_atom():
    declaration, reactant, product = separated_endpoints()

    result = bind_reaction_structures(declaration, reactant, product)

    assert result['binding_status'] == 'complete', result['binding_diagnostics']
    assert result['product_identity'] == 'match'
    assert sorted(result['atom_map']) == list(range(1, reactant.GetNumAtoms() + 1))
    assert declaration.reaction.product_smiles == ['[NH4+]', '[OH-]']
    for index, target in enumerate(result['atom_map']):
        assert product.GetAtomWithIdx(index).GetAtomicNum() == reactant.GetAtomWithIdx(target - 1).GetAtomicNum()


def test_ts_map_accepts_separated_products_before_a_correspondence_exists(tmp_path):
    declaration, reactant, product = separated_endpoints()
    record = TsProcessRecord(run_id='separated-map', run_dir=str(tmp_path / 'run'),
        workspace_dir=str(tmp_path), input=declaration,
        structures={'reactant': reactant, 'product': product})
    assert record.structures.product_to_reactant is None

    result = _map(record)

    assert result.blocked is None, result.blocked
    assert result.stage_record('map').status == 'done'
    assert sorted(result.structures.product_to_reactant) == list(range(reactant.GetNumAtoms()))
    assert result.input.reaction.product_smiles == ['[NH4+]', '[OH-]']
