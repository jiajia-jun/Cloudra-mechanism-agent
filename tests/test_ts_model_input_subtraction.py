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


def test_scan_recovery_model_only_names_real_repair_artifacts():
    from cloudra.tools.Chemtool.ts_search_process import TsResume_input_schema

    recovery = TsResume_input_schema(run_id="ts_owned", reason="Repair the failed scan",
                                    scan_recovery=["repaired-endpoint.xyz"])
    assert recovery.scan_recovery == ["repaired-endpoint.xyz"]


def test_pinned_ts_guidance_uses_current_resume_parameters():
    from cloudra.runtime_v2.policies.guidance import _TS_NOTICE
    from cloudra.tools.Chemtool.ts_search_process import TsResume_input_schema

    signature = _TS_NOTICE.split('ts_resume(', 1)[1].split(')', 1)[0]
    parameters = {name.strip() for name in signature.split(',')}
    assert parameters <= TsResume_input_schema.model_fields.keys()


def test_runtime_binds_repair_file_and_preserves_original_failure_guards(tmp_path):
    import json

    from cloudra.tools.Chemtool.ts_search_process import _scan_recovery_input
    from cloudra.tools.core.ts_revision import plan_input_revision
    from tests.test_ts_issue_regressions import _failed_scan_recovery

    record, schema, payload, proof = _failed_scan_recovery(tmp_path)
    proof.write_text(json.dumps({"repair": "Temporary-file access was repaired"}))
    recovery = _scan_recovery_input(record, [str(proof)], None)
    payload["scan_recovery"] = recovery
    request = schema.model_validate(payload)
    receipt = plan_input_revision(record, request)
    assert receipt.recovery_evidence["failed_attempt"]["attempt_id"] == "1:scan:7"
    artifact = receipt.recovery_evidence["evidence_refs"][0]
    assert artifact["receipt"]["repair_source_path"] == str(proof)
    proof.write_text(json.dumps({"repair": "A different unbound claim"}))
    with pytest.raises(ValueError, match="original repair artifact changed"):
        plan_input_revision(record, request)
