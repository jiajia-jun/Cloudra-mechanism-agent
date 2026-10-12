"""Model calls declare scientific choices; internal bookkeeping stays local."""

import pytest

from tests.test_ts_input_evidence import concrete


@pytest.mark.parametrize("electronic_character", [None, "closed_shell"])
def test_explicit_concrete_binding_needs_indices_not_a_copied_digest(electronic_character):
    from cloudra.tools.Chemtool.reaction_mapping import (
        ReactionMapping_input_schema,
        check_concrete_binding,
    )

    text = concrete("O")
    request = ReactionMapping_input_schema(
        reactant_smiles="O", product_smiles="O",
        reactant_text=text, product_text=text,
        reactant_format="mol", product_format="mol",
        reactant_electronic_character=electronic_character,
        product_electronic_character=electronic_character,
        reactant_binding={"indices": [1]}, product_binding={"indices": [1]},
    )
    result = check_concrete_binding(request, {"heavy_atom_map": [1], "watch_pairs": []})
    assert result["binding_status"] == "complete"
    assert result["reactant_identity"] == result["product_identity"] == "match"
    assert result["atom_map"] == [1, 2, 3]








