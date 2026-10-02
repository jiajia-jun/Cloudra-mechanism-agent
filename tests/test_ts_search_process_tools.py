"""Grouped TS writers and independent read-only inspection."""
from types import SimpleNamespace

import pytest

from cloudra.tools.Chemtool.ts_search_process import (
    TsPrepare,
    TsPrepare_input_schema,
    TsResume,
    TsResume_input_schema,
)
from cloudra.tools.core.permission_model import Permission
from tests.ts_fixtures import calculation_input


def owned_tool(cls, project='project'):
    tool = cls()
    object.__setattr__(tool, 'subagent', SimpleNamespace(conversation_id=project,
        working_directory=None, permission_all=lambda: Permission.READ | Permission.WRITE))
    return tool


def inputs(*, mapped=True):
    return calculation_input(reactant_smiles='O', product_smiles='O',
        method='HF/STO-3G', atom_map=[1,2,3] if mapped else [])


@pytest.mark.asyncio
async def test_prepare_queues_one_path_and_response_replay_reuses_it(tmp_path, monkeypatch):
    from cloudra.persistence.database import ComputeDB
    from cloudra.services.compute_admission import AdmissionOutcome
    monkeypatch.setattr('cloudra.services.compute_admission.admit_job',
        lambda **_: AdmissionOutcome(ok=True,node_id='fixture',scheduler='local'))
    tool = owned_tool(TsPrepare)
    request = TsPrepare_input_schema(input=inputs(), workspace_dir=str(tmp_path), request_key='prepare')
    first = await tool.tool_call(request, None)
    second = await tool.tool_call(request, None)
    assert first.is_success and first.status == 'waiting', first.message
    assert first.run_id == second.run_id
    assert first.next["action"] == 'wait_for_system'
    with ComputeDB().connect() as con:
        assert con.execute('SELECT COUNT(*) FROM compute_jobs').fetchone()[0] == 1


@pytest.mark.asyncio
async def test_prepare_reports_missing_map_and_keeps_explicit_stage_methods(tmp_path):
    first = await owned_tool(TsPrepare).tool_call(TsPrepare_input_schema(input=inputs(mapped=False), workspace_dir=str(tmp_path)),None)
    assert first.is_success and first.blocked["stage"] == 'map'
    assert first.blocked["failure_class"] == 'atom_map_missing'
    assert first.run_id
    assert first.next["action"] == 'resume'


@pytest.mark.asyncio
async def test_resume_revises_same_path_and_returns_durable_receipt(tmp_path, monkeypatch):
    from cloudra.services.compute_admission import AdmissionOutcome
    monkeypatch.setattr('cloudra.services.compute_admission.admit_job',
        lambda **_: AdmissionOutcome(ok=True,node_id='fixture',scheduler='local'))
    first = await owned_tool(TsPrepare).tool_call(TsPrepare_input_schema(input=inputs(mapped=False),workspace_dir=str(tmp_path)),None)
    request = TsResume_input_schema(run_id=first.run_id, workspace_dir=str(tmp_path),
        changes={'reaction':{'atom_map':[1,2,3]}}, reason='Bind the complete atom order',
        request_key='mapping', expected_revision=first.revision)
    tool = owned_tool(TsResume)
    revised = await tool.tool_call(request,None)
    replay = await tool.tool_call(request,None)
    assert revised.is_success, revised.message
    assert revised.run_id == first.run_id
    assert revised.receipt.input_revision == 2
    assert revised.receipt == replay.receipt
    assert revised.status == 'waiting'


@pytest.mark.asyncio
@pytest.mark.parametrize('project,owner',[('foreign',None),('project','foreign-owner')])
async def test_resume_rejects_other_project_or_owner(tmp_path,project,owner):
    first = await owned_tool(TsPrepare).tool_call(TsPrepare_input_schema(input=inputs(mapped=False),workspace_dir=str(tmp_path)),None)
    request = TsResume_input_schema(run_id=first.run_id,workspace_dir=str(tmp_path),
        reason='Change method', request_key='foreign', expected_revision=first.revision,
        changes={'ts_optimization':{'engine':'orca','method':'HF/STO-3G','keywords':'D3BJ'}})
    session = SimpleNamespace(id=owner) if owner else None
    result = await owned_tool(TsResume,project).tool_call(request,session)
    assert not result.is_success
    assert 'owner' in result.message or 'project' in result.message


@pytest.mark.asyncio
async def test_resume_unknown_run_reports_error(tmp_path):
    result = await owned_tool(TsResume).tool_call(TsResume_input_schema(run_id='ts_9999',workspace_dir=str(tmp_path),
        reason='Change method',request_key='unknown',expected_revision=0),None)
    assert not result.is_success


@pytest.mark.asyncio
async def test_resume_uses_authoritative_record_when_export_is_missing(tmp_path, monkeypatch):
    from pathlib import Path

    from cloudra.services.compute_admission import AdmissionOutcome
    monkeypatch.setattr('cloudra.services.compute_admission.admit_job',
        lambda **_: AdmissionOutcome(ok=True,node_id='fixture',scheduler='local'))
    first = await owned_tool(TsPrepare).tool_call(TsPrepare_input_schema(input=inputs(mapped=False),workspace_dir=str(tmp_path)),None)
    Path(first.run_dir, 'process.json').unlink()
    result = await owned_tool(TsResume).tool_call(TsResume_input_schema(run_id=first.run_id,workspace_dir=str(tmp_path),
        changes={'reaction':{'atom_map':[1,2,3]}},reason='Bind atoms',request_key='after-export-loss',expected_revision=first.revision),None)
    assert result.is_success, result.message
    assert result.run_id == first.run_id


@pytest.mark.asyncio
async def test_prepare_without_workspace_reports_caller_error():
    result = await owned_tool(TsPrepare).tool_call(TsPrepare_input_schema(input=inputs()),None)
    assert not result.is_success and 'workspace' in result.message


def test_public_surface_has_two_writers_and_readonly_inspection():
    from cloudra.tools import get_tools_lst
    names = {entry.tool_name for entry in get_tools_lst()}
    assert {name for name in names if name.startswith('ts_')} - {'ts_guess'} == {'ts_prepare','ts_resume','ts_inspect'}
    fields = TsPrepare_input_schema.model_json_schema()['properties']
    assert 'input' in fields and 'compute_estimates' not in fields and 'declaration' not in fields
    with pytest.raises(ValueError):
        TsPrepare_input_schema(input=inputs(),estimated_cpu_hours=2)


pytestmark = pytest.mark.usefixtures("ts_producer_authority")
