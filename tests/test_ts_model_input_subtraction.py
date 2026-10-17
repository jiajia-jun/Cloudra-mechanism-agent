"""Model calls declare scientific choices; internal bookkeeping stays local."""

import pytest

from tests.test_ts_input_evidence import molecule
from tests.test_ts_search_process_tools import inputs, invoke, owned_tool


@pytest.mark.parametrize("electronic_character", [None, "closed_shell"])
def test_unique_concrete_binding_needs_no_model_indices_or_digest(electronic_character):
    from cloudra.tools.Chemtool.reaction_mapping import bind_reaction_structures
    from cloudra.tools.core.ts_inputs import TsInput

    mol = molecule('O')
    request = TsInput(reaction=dict(reactant_smiles='O', product_smiles='O',
        charge=0, multiplicity=1, electronic_character=electronic_character))
    result = bind_reaction_structures(request, mol, mol)
    assert result['binding_status'] == 'complete'
    assert result['reactant_identity'] == result['product_identity'] == 'match'
    assert result['atom_map'] == [1, 2, 3]
    assert 'atom_map' not in request.reaction.model_dump()
    assert 'heavy_atom_binding' not in request.conformers.model_dump()


@pytest.mark.asyncio
@pytest.mark.usefixtures("rdkit_chemistry", "ts_producer_authority")
async def test_resume_tracks_current_revision_without_model_copying_version(tmp_path, monkeypatch):
    from cloudra.services.compute_admission import AdmissionOutcome
    from cloudra.tools.Chemtool.ts_search_process import (
        TsPrepare,
        TsPrepare_input_schema,
        TsResume,
        TsResume_input_schema,
    )
    monkeypatch.setattr('cloudra.services.compute_admission.admit_job',
        lambda **_: AdmissionOutcome(ok=True, node_id='fixture', scheduler='local'))
    first = await invoke(owned_tool(TsPrepare, workspace=tmp_path),
                         TsPrepare_input_schema(input=inputs()))
    assert first.is_success, first.message
    assert first.blocked is None
    assert first.structures['reactant']['binding_status'] == 'complete'
    request = TsResume_input_schema(
        run_id=first.run_id, reason="Revise the intended centre while correspondence stays owned by the program",
        changes={"reaction": {"reaction_center": [[1, 2]]}},
    )
    tool = owned_tool(TsResume, workspace=tmp_path)
    result = await invoke(tool, request, call_id="revision-owned-by-program")
    replay = await invoke(tool, request, call_id="revision-owned-by-program")
    assert result.is_success, result.message
    assert result.blocked is None
    assert result.structures['reactant']['binding_status'] == 'complete'
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
