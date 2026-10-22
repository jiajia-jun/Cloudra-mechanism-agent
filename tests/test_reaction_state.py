"""One owned structure state supplies independent algorithm views."""
import numpy as np
import pytest

pytest.importorskip("rdkit", reason="requires RDKit (chem extra)")

from rdkit import Chem
from rdkit.Chem import AllChem


def water():
    mol = Chem.AddHs(Chem.MolFromSmiles("O"))
    AllChem.EmbedMolecule(mol, randomSeed=7)
    mol.GetAtomWithIdx(0).SetProp("cloudra_atom_id", "oxygen")
    return mol


def test_path_view_reorders_once_and_cannot_mutate_owned_state():
    from cloudra.tools.core.molecule import renumber_atoms
    from cloudra.tools.core.reaction_state import ReactionStructures, path_endpoints
    original = water()
    product = renumber_atoms(original, [1, 0, 2])
    state = ReactionStructures(reactant=original, product=product, product_to_reactant=(1, 0, 2))
    left, right = path_endpoints(state)
    np.testing.assert_array_equal(left.GetConformer().GetPositions(), right.GetConformer().GetPositions())
    right.GetConformer().SetAtomPosition(0, (9, 9, 9))
    assert state.product.GetConformer().GetAtomPosition(1).x != 9
    assert right.GetAtomWithIdx(0).GetProp("cloudra_atom_id") == "oxygen"
    restored = ReactionStructures.model_validate_json(state.model_dump_json())
    np.testing.assert_array_equal(restored.product.GetConformer().GetPositions(), product.GetConformer().GetPositions())


def test_unconfirmed_mapping_is_not_identity():
    from cloudra.tools.core.reaction_state import ReactionStructures, path_endpoints
    state = ReactionStructures(reactant=water(), product=water())
    with pytest.raises(ValueError, match="对应"):
        path_endpoints(state)


def test_binding_is_atom_owned_and_follows_renumbering():
    from cloudra.tools.core.molecule import renumber_atoms
    from cloudra.tools.core.reaction_state import heavy_binding, set_heavy_binding
    original = water()
    bound = set_heavy_binding(original, [1])
    assert heavy_binding(original) == []
    assert heavy_binding(renumber_atoms(bound, [1, 0, 2])) == [2]
