"""Grouped TS writers and independent read-only inspection."""
from types import SimpleNamespace

import pytest

from cloudra.runtime_v2.invocation_context import InvocationScope, reset_invocation_scope, set_invocation_scope
from cloudra.tools.Chemtool.ts_search_process import (
    TsPrepare,
    TsPrepare_input_schema,
    TsResume,
    TsResume_input_schema,
)
from cloudra.tools.core.permission_model import Permission
from tests.ts_fixtures import calculation_input


@pytest.fixture(autouse=True)
def tool_invocation():
    token = set_invocation_scope(InvocationScope(tool_call_id='stable-test-call', tool_name='ts_prepare'))
    yield
    reset_invocation_scope(token)


def owned_tool(cls, project='project', workspace=None):
    tool = cls()
    object.__setattr__(tool, 'subagent', SimpleNamespace(conversation_id=project,
        working_directory=str(workspace) if workspace else None, permission_all=lambda: Permission.READ | Permission.WRITE))
    return tool


async def invoke(tool, request, session=None, *, call_id='stable-test-call'):
    token = set_invocation_scope(InvocationScope(tool_call_id=call_id, tool_name=tool.tool_name))
    try:
        return await tool.tool_call(request, session)
    finally:
        reset_invocation_scope(token)


def inputs(*, mapped=True):
    return calculation_input(reactant_smiles='O', product_smiles='O',
        method='HF/STO-3G', atom_map=[1,2,3] if mapped else [])


@pytest.mark.asyncio
@pytest.mark.usefixtures("rdkit_chemistry")
async def test_prepare_queues_one_path_and_response_replay_reuses_it(tmp_path, monkeypatch):
    from cloudra.persistence.database import ComputeDB
    from cloudra.services.compute_admission import AdmissionOutcome
    monkeypatch.setattr('cloudra.services.compute_admission.admit_job',
        lambda **_: AdmissionOutcome(ok=True,node_id='fixture',scheduler='local'))
    tool = owned_tool(TsPrepare, workspace=tmp_path)
    request = TsPrepare_input_schema(input=inputs())
    first = await invoke(tool, request)
    second = await invoke(tool, request)
    assert first.is_success and first.status == 'waiting', first.message
    assert first.run_id == second.run_id
    assert first.next["action"] == 'wait_for_system'
    with ComputeDB().connect() as con:
        assert con.execute('SELECT COUNT(*) FROM compute_jobs').fetchone()[0] == 1


@pytest.mark.asyncio
@pytest.mark.usefixtures("rdkit_chemistry")
async def test_prepare_reports_missing_map_and_keeps_explicit_stage_methods(tmp_path):
    first = await invoke(owned_tool(TsPrepare, workspace=tmp_path), TsPrepare_input_schema(input=inputs(mapped=False)))
    assert first.is_success and first.blocked["stage"] == 'map'
    assert first.blocked["failure_class"] == 'atom_map_missing'
    assert first.run_id
    assert first.next["action"] == 'resume'


@pytest.mark.asyncio
@pytest.mark.usefixtures("rdkit_chemistry")
async def test_resume_revises_same_path_and_returns_durable_receipt(tmp_path, monkeypatch):
    from cloudra.services.compute_admission import AdmissionOutcome
    monkeypatch.setattr('cloudra.services.compute_admission.admit_job',
        lambda **_: AdmissionOutcome(ok=True,node_id='fixture',scheduler='local'))
    first = await invoke(owned_tool(TsPrepare, workspace=tmp_path), TsPrepare_input_schema(input=inputs(mapped=False)))
    request = TsResume_input_schema(run_id=first.run_id,
        changes={'reaction':{'atom_map':[1,2,3]}}, reason='Bind the complete atom order',
        expected_revision=first.revision)
    tool = owned_tool(TsResume, workspace=tmp_path)
    revised = await invoke(tool, request)
    replay = await invoke(tool, request)
    assert revised.is_success, revised.message
    assert revised.run_id == first.run_id
    assert revised.receipt.input_revision == 2
    assert revised.receipt == replay.receipt
    assert revised.status == 'waiting'


@pytest.mark.asyncio
@pytest.mark.usefixtures('rdkit_chemistry')
async def test_new_tool_call_cannot_overwrite_revision_agent_did_not_observe(tmp_path, monkeypatch):
    from cloudra.services.compute_admission import AdmissionOutcome

    monkeypatch.setattr('cloudra.services.compute_admission.admit_job',
        lambda **_: AdmissionOutcome(ok=True,node_id='fixture',scheduler='local'))
    first = await invoke(owned_tool(TsPrepare, workspace=tmp_path), TsPrepare_input_schema(input=inputs(mapped=False)))
    request = TsResume_input_schema(run_id=first.run_id, reason='Bind atom map',
        changes={'reaction':{'atom_map':[1,2,3]}}, expected_revision=first.revision)
    tool = owned_tool(TsResume, workspace=tmp_path)
    accepted = await invoke(tool, request, call_id='repair-1')
    assert accepted.is_success
    stale = await invoke(tool, request, call_id='repair-2')
    assert not stale.is_success and 'stale process revision' in stale.message


@pytest.mark.asyncio
@pytest.mark.parametrize('project,owner',[('foreign',None),('project','foreign-owner')])
@pytest.mark.usefixtures("rdkit_chemistry")
async def test_resume_rejects_other_project_or_owner(tmp_path,project,owner):
    first = await invoke(owned_tool(TsPrepare, workspace=tmp_path), TsPrepare_input_schema(input=inputs(mapped=False)))
    request = TsResume_input_schema(run_id=first.run_id,
        reason='Change method', expected_revision=first.revision,
        changes={'ts_optimization':{'engine':'orca','method':'HF/STO-3G','keywords':'D3BJ'}})
    session = SimpleNamespace(id=owner) if owner else None
    result = await invoke(owned_tool(TsResume, project, tmp_path), request, session)
    assert not result.is_success
    assert 'owner' in result.message or 'project' in result.message


@pytest.mark.asyncio
async def test_resume_unknown_run_reports_error(tmp_path):
    result = await invoke(owned_tool(TsResume, workspace=tmp_path), TsResume_input_schema(run_id='ts_9999',
        reason='Change method',expected_revision=0))
    assert not result.is_success


@pytest.mark.asyncio
@pytest.mark.usefixtures("rdkit_chemistry")
async def test_resume_uses_authoritative_record_when_export_is_missing(tmp_path, monkeypatch):
    from pathlib import Path

    from cloudra.services.compute_admission import AdmissionOutcome
    monkeypatch.setattr('cloudra.services.compute_admission.admit_job',
        lambda **_: AdmissionOutcome(ok=True,node_id='fixture',scheduler='local'))
    first = await invoke(owned_tool(TsPrepare, workspace=tmp_path), TsPrepare_input_schema(input=inputs(mapped=False)))
    Path(first.run_dir, 'process.json').unlink()
    result = await invoke(owned_tool(TsResume, workspace=tmp_path), TsResume_input_schema(run_id=first.run_id,
        changes={'reaction':{'atom_map':[1,2,3]}},reason='Bind atoms',expected_revision=first.revision))
    assert result.is_success, result.message
    assert result.run_id == first.run_id


@pytest.mark.asyncio
@pytest.mark.usefixtures('rdkit_chemistry')
async def test_replacing_conformer_accepts_invalidation_of_stale_atom_binding(tmp_path):
    from cloudra.persistence.database import ComputeDB
    from cloudra.services.ts_pipeline_store import read_process_snapshot
    from cloudra.tools.core.ts_inputs import FileConformer

    value = inputs()
    value.conformers.reactant = FileConformer(kind='file', xyz_path=str(tmp_path / 'missing.xyz'))
    first = await invoke(owned_tool(TsPrepare, workspace=tmp_path), TsPrepare_input_schema(input=value))
    assert first.is_success and first.blocked['stage'] == 'build'
    replacement = tmp_path / 'replacement.xyz'
    replacement.write_text('3\nWater replacement\nO 0 0 0\nH 0.96 0 0\nH -0.24 0.93 0\n')
    revised = await invoke(owned_tool(TsResume, workspace=tmp_path), TsResume_input_schema(
        run_id=first.run_id, expected_revision=first.revision, reason='Replace the missing endpoint',
        changes={'conformers': {'reactant': {'kind': 'file', 'xyz_path': str(replacement)}}},
    ), call_id='replace-source')
    assert revised.is_success, revised.message
    assert revised.run_id == first.run_id and revised.receipt.input_revision == 2
    assert revised.blocked['stage'] == 'map'
    current, _ = read_process_snapshot(ComputeDB(), project_id='project', run_id=first.run_id,
                                       workspace_dir=str(tmp_path))
    assert current['input']['reaction']['atom_map'] == []
    assert current['input']['guess'] == value.guess.model_dump(mode='json')
    assert current['attempt_history'][0]['input']['reaction']['atom_map'] == [0, 1, 2]


@pytest.mark.asyncio
async def test_prepare_without_workspace_reports_caller_error():
    result = await invoke(owned_tool(TsPrepare), TsPrepare_input_schema(input=inputs()))
    assert not result.is_success and 'working directory' in result.message


def test_public_surface_has_two_writers_and_readonly_inspection():
    from cloudra.tools import get_tools_lst
    names = {entry.tool_name for entry in get_tools_lst()}
    assert {name for name in names if name.startswith('ts_')} - {'ts_guess'} == {'ts_prepare','ts_resume','ts_inspect'}
    fields = TsPrepare_input_schema.model_json_schema()['properties']
    assert 'input' in fields and 'compute_estimates' not in fields and 'declaration' not in fields
    assert 'request_key' not in fields and 'workspace_dir' not in fields
    assert 'request_key' not in TsResume_input_schema.model_json_schema()['properties']
    with pytest.raises(ValueError):
        TsPrepare_input_schema(input=inputs(),estimated_cpu_hours=2)


pytestmark = pytest.mark.usefixtures("ts_producer_authority")
