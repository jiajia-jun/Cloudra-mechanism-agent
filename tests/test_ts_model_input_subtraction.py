"""Model calls declare scientific choices; internal bookkeeping stays local."""

import pytest

from tests.test_ts_input_evidence import concrete
from tests.test_ts_search_process_tools import inputs, invoke, owned_tool


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


@pytest.mark.asyncio
@pytest.mark.usefixtures("rdkit_chemistry", "ts_producer_authority")
async def test_resume_tracks_current_revision_without_model_copying_version(tmp_path):
    from cloudra.tools.Chemtool.ts_search_process import (
        TsPrepare,
        TsPrepare_input_schema,
        TsResume,
        TsResume_input_schema,
    )

    first = await invoke(owned_tool(TsPrepare, workspace=tmp_path),
                         TsPrepare_input_schema(input=inputs(mapped=False)))
    assert first.is_success, first.message
    assert first.blocked["failure_class"] == "atom_map_missing"
    request = TsResume_input_schema(
        run_id=first.run_id, reason="Declare the intended centre; mapping is still unresolved",
        changes={"reaction": {"reaction_center": [[1, 2]]}},
    )
    tool = owned_tool(TsResume, workspace=tmp_path)
    result = await invoke(tool, request, call_id="revision-owned-by-program")
    replay = await invoke(tool, request, call_id="revision-owned-by-program")
    assert result.is_success, result.message
    assert result.blocked["failure_class"] == "atom_map_missing"
    assert result.receipt == replay.receipt
    assert result.receipt.input_revision == 2


def test_resume_has_only_research_changes_and_reason():
    from cloudra.tools.Chemtool.ts_search_process import TsResume_input_schema

    assert set(TsResume_input_schema.model_fields) == {"run_id", "changes", "reason"}
    request = TsResume_input_schema(run_id="ts_owned", reason="Retry the native scan")
    assert request.changes.model_dump(exclude_unset=True) == {}


def test_pinned_ts_guidance_uses_current_resume_parameters():
    from cloudra.runtime_v2.policies.guidance import _TS_NOTICE
    from cloudra.tools.Chemtool.ts_search_process import TsResume_input_schema

    signature = _TS_NOTICE.split('ts_resume(', 1)[1].split(')', 1)[0]
    parameters = {name.strip() for name in signature.split(',')}
    assert parameters <= TsResume_input_schema.model_fields.keys()
