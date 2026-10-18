"""Runtime contracts: concrete tool authority, owned waits and internal read snapshots."""
from __future__ import annotations

import asyncio

import pytest
from pydantic import ValidationError

from cloudra.base.tools_class import Tool
from cloudra.persistence.database import ComputeDB
from cloudra.runtime_v2.adapters import LegacyToolExecutor
from cloudra.runtime_v2.commands import CommandBus
from cloudra.runtime_v2.core import RuntimeCore
from cloudra.runtime_v2.effects import EventDraft
from cloudra.runtime_v2.invocation import InvocationService
from cloudra.runtime_v2.persistence import RuntimeStore, restore_core
from cloudra.runtime_v2.policies.base import PipelineContext, ToolCall
from cloudra.runtime_v2.policies.permission import PermissionStage
from cloudra.runtime_v2.policies.schedule_stage import ScheduleStage
from cloudra.runtime_v2.schemas import Command
from cloudra.runtime_v2.tool_catalog import guest_tool_names, wire_tool_schemas
from cloudra.services.compute_store import aget_compute_job, ainsert_compute_job
from cloudra.tools.Writetool.edit import Edit_input_schema
from cloudra.tools.Writetool.write import Write_input_schema
from tests.agent_scenarios import ScenarioHarness, ScriptedProvider, Step


async def setup_runtime(tmp_path, *, durable=False):
    core = RuntimeCore(strict_events=True)
    if durable:
        core.store = RuntimeStore(tmp_path / 'runtime.db')
    bus = CommandBus(core)
    project = (await bus.execute(Command(type='project.create', payload={
        'name': 'design repairs', 'workspace_dir': str(tmp_path),
    }))).data
    return core, bus, project


async def spawn(bus, project, role='coordinator', **payload):
    return (await bus.execute(Command(type='agent.spawn', target={'project_id': project.id},
        payload={'role_id': role, **payload}))).data


def context(agent):
    return PipelineContext(agent=agent, run_id='run_test', settings_snapshot=agent.settings,
        capabilities=agent.capabilities, inbox_messages=[], emit=lambda *_: None)


async def call(core, agent, name, arguments):
    service = InvocationService(event_writer=core.event_writer, stages=[PermissionStage()],
        tools=LegacyToolExecutor(core), agents=core.agents)
    ctx = context(agent)
    ctx.workspace_dir = core.require_project(agent.project_id).workspace_dir
    return await service.invoke(ctx, ToolCall(id=f'call_{len(core.event_log)}', name=name, arguments=arguments))


@pytest.mark.asyncio
@pytest.mark.parametrize('allow', [['*'], ['read', 'bash']])
async def test_role_deny_removes_tool_from_directory_and_execution(tmp_path, allow):
    core, bus, project = await setup_runtime(tmp_path)
    await bus.execute(Command(type='role.update', target={'role_id': 'coordinator'},
        payload={'tool_policy': {'allow': allow, 'deny': ['bash']}}))
    agent = await spawn(bus, project, settings={'invocation_protocol': 'traditional'})
    assert '*' not in agent.capabilities.tools
    assert 'bash' not in guest_tool_names(agent.capabilities.tools)
    schemas = wire_tool_schemas(agent, agent.capabilities.tools)
    assert all(row['function']['name'] != 'bash' for row in schemas)
    outcome = await call(core, agent, 'bash', {'command': 'pwd'})
    assert outcome.error is not None and outcome.error.code == 'policy_blocked'
    assert not core.event_log.query_session(agent.id, types={'tool.started'})


@pytest.mark.asyncio
@pytest.mark.parametrize('state', ['ready', 'done'])
async def test_schedule_child_does_not_wait_on_another_sessions_compute(tmp_path, state):
    core, bus, project = await setup_runtime(tmp_path)
    other = await spawn(bus, project, 'small_mol')
    child = await spawn(bus, project, 'researcher', settings={'schedule_mode': True})
    await ainsert_compute_job(await ComputeDB().ainit(), conversation_id=project.id,
        session_id=other.id, path=str(tmp_path / 'other.gjf'), state=state,
        jobtype='gaussian', node_id='local')
    gate = await ScheduleStage(core).audit_run_end(context(child), explicit_stop=False)
    assert gate.action == 'allow_final'
    coordinator = await spawn(bus, project, settings={'schedule_mode': True})
    gate = await ScheduleStage(core).audit_run_end(context(coordinator), explicit_stop=False)
    assert gate.action == 'continue_work'


@pytest.mark.asyncio
async def test_schedule_agent_finishes_while_another_sessions_job_remains_ready(tmp_path):
    """真实 runner 收尾不被其他 Agent 的计算拖进再次等待。"""
    provider = ScriptedProvider(by_role={'researcher': [Step(text='ready', stop=True)]})
    harness = await ScenarioHarness.start(tmp_path, workspace_dir=tmp_path, provider=provider)
    try:
        other = await harness.spawn('small_mol', query='')
        db = await ComputeDB().ainit()
        job_id = await ainsert_compute_job(db, conversation_id=harness.project.id,
            session_id=other.id, path=str(tmp_path / 'other.gjf'), state='ready',
            jobtype='gaussian', node_id='local')
        agent = await harness.spawn('researcher', protocol='traditional', schedule_mode=True)
        await harness.wait_terminal(agent)
        assert agent.state.value == 'succeeded'
        assert provider.call_count('researcher') == 1
        gates = [event for event in harness.events(agent) if event.type == 'agent.completion_gate']
        assert gates[-1].data['action'] == 'allow_final'
        assert (await aget_compute_job(db, job_id))['state'] == 'ready'
    finally:
        await harness.aclose()


def test_file_tool_inputs_do_not_accept_internal_hashes():
    assert 'expected_sha256' not in Edit_input_schema.model_fields
    assert 'expected_sha256' not in Write_input_schema.model_fields
    with pytest.raises(ValidationError):
        Write_input_schema(path='x', content='x', expected_sha256='missing')


@pytest.fixture
def approve(monkeypatch):
    async def approved(self, session, details, tool_args=None):
        return True, ''
    monkeypatch.setattr(Tool, 'ensure_safety', approved)


@pytest.mark.asyncio
@pytest.mark.parametrize('tool', ['edit', 'write'])
async def test_file_changes_bind_the_sessions_read_without_model_hash(tmp_path, approve, tool):
    core, bus, project = await setup_runtime(tmp_path)
    agent = await spawn(bus, project)
    path = tmp_path / 'note.txt'
    path.write_text('before\n')
    assert (await call(core, agent, 'read', {'path': 'note.txt'})).result.is_success
    arguments = {'path': 'note.txt', **({'content': 'after\n'} if tool == 'write' else
        {'edits': [{'old_text': 'before', 'new_text': 'after'}]})}
    result = (await call(core, agent, tool, arguments)).result
    assert result.is_success, result.summary
    assert path.read_text() == 'after\n'


@pytest.mark.asyncio
@pytest.mark.parametrize('durable', [False, True])
async def test_own_applied_changes_are_known_without_redundant_reads(tmp_path, approve, durable):
    core, bus, project = await setup_runtime(tmp_path, durable=durable)
    agent = await spawn(bus, project)
    created = (await call(core, agent, 'write', {'path': 'note.txt', 'content': 'first\n'})).result
    assert created.is_success
    for before, after in [('first', 'second'), ('second', 'third')]:
        edited = (await call(core, agent, 'edit', {'path': 'note.txt',
            'edits': [{'old_text': before, 'new_text': after}]})).result
        assert edited.is_success, edited.summary
    assert (tmp_path / 'note.txt').read_text() == 'third\n'
    assert all(event.data['tool_name'] != 'read' for event in
               core.event_log.query_session(agent.id, types={'tool.result_recorded'}))


@pytest.mark.asyncio
@pytest.mark.parametrize('durable', [False, True])
async def test_own_write_version_does_not_allow_external_changes_or_other_sessions(tmp_path, approve, durable):
    core, bus, project = await setup_runtime(tmp_path, durable=durable)
    owner, other = await spawn(bus, project), await spawn(bus, project)
    created = (await call(core, owner, 'write', {'path': 'note.txt', 'content': 'known\n'})).result
    assert created.is_success
    result = (await call(core, other, 'write', {'path': 'note.txt', 'content': 'other\n'})).result
    assert not result.is_success and result.data['status'] == 'conflict'
    (tmp_path / 'note.txt').write_text('external\n')
    result = (await call(core, owner, 'edit', {'path': 'note.txt',
        'edits': [{'old_text': 'external', 'new_text': 'changed'}]})).result
    assert not result.is_success and result.data['status'] == 'conflict'
    assert (tmp_path / 'note.txt').read_text() == 'external\n'


@pytest.mark.asyncio
@pytest.mark.parametrize('tool', ['edit', 'write'])
async def test_read_to_prepare_concurrent_changes_remain_conflicts(tmp_path, approve, tool):
    core, bus, project = await setup_runtime(tmp_path)
    agent = await spawn(bus, project)
    path = tmp_path / 'note.txt'
    path.write_text('before\n')
    await call(core, agent, 'read', {'path': 'note.txt'})
    path.write_text('external\n')
    arguments = {'path': 'note.txt', **({'content': 'after\n'} if tool == 'write' else
        {'edits': [{'old_text': 'before', 'new_text': 'after'}]})}
    result = (await call(core, agent, tool, arguments)).result
    assert not result.is_success and result.data['status'] == 'conflict'
    assert path.read_text() == 'external\n'


@pytest.mark.asyncio
async def test_prepare_to_apply_concurrent_changes_remain_conflicts(tmp_path, monkeypatch):
    core, bus, project = await setup_runtime(tmp_path)
    agent = await spawn(bus, project)
    path = tmp_path / 'note.txt'
    path.write_text('before\n')
    await call(core, agent, 'read', {'path': 'note.txt'})
    async def concurrent_edit(self, session, details, tool_args=None):
        await asyncio.to_thread(path.write_text, 'external\n')
        return True, ''
    monkeypatch.setattr(Tool, 'ensure_safety', concurrent_edit)
    result = (await call(core, agent, 'edit', {'path': 'note.txt',
        'edits': [{'old_text': 'before', 'new_text': 'after'}]})).result
    assert not result.is_success and result.data['status'] == 'conflict'
    assert path.read_text() == 'external\n'


@pytest.mark.asyncio
async def test_read_snapshot_survives_context_reset_cache_eviction_and_restore(tmp_path, approve):
    core, bus, project = await setup_runtime(tmp_path, durable=True)
    agent = await spawn(bus, project)
    (tmp_path / 'note.txt').write_text('before\n')
    await call(core, agent, 'read', {'path': 'note.txt'})
    core.event_log._max_cached_events = 2
    for index in range(5):
        await core.event_writer.commit(EventDraft('agent.warning', 'agent', project.id, agent.id, data={'index': index}))
    restored = RuntimeCore(strict_events=True)
    restored.store = core.store
    await asyncio.to_thread(restore_core, restored, restored.store)
    result = (await call(restored, restored.require_agent(agent.id), 'edit', {'path': 'note.txt',
        'edits': [{'old_text': 'before', 'new_text': 'after'}]})).result
    assert result.is_success, result.summary


@pytest.mark.asyncio
async def test_read_snapshot_is_not_shared_between_sessions(tmp_path, approve):
    core, bus, project = await setup_runtime(tmp_path)
    reader, writer = await spawn(bus, project), await spawn(bus, project)
    path = tmp_path / 'note.txt'
    path.write_text('before\n')
    await call(core, reader, 'read', {'path': 'note.txt'})
    result = (await call(core, writer, 'write', {'path': 'note.txt', 'content': 'after\n'})).result
    assert not result.is_success and result.data['status'] == 'conflict'
    assert path.read_text() == 'before\n'


@pytest.mark.asyncio
async def test_file_removed_after_read_is_not_silently_recreated(tmp_path, approve):
    core, bus, project = await setup_runtime(tmp_path)
    agent = await spawn(bus, project)
    path = tmp_path / 'note.txt'
    path.write_text('before\n')
    await call(core, agent, 'read', {'path': 'note.txt'})
    path.unlink()
    result = (await call(core, agent, 'write', {'path': 'note.txt', 'content': 'after\n'})).result
    assert not result.is_success and result.data.get('status') == 'conflict'
    assert not path.exists()


@pytest.mark.asyncio
@pytest.mark.parametrize('durable', [False, True])
async def test_read_version_matches_target_and_current_workspace(tmp_path, approve, durable):
    core, bus, project = await setup_runtime(tmp_path, durable=durable)
    agent = await spawn(bus, project)
    (tmp_path / 'first.txt').write_text('first\n')
    (tmp_path / 'second.txt').write_text('second\n')
    await call(core, agent, 'read', {'path': 'first.txt'})
    await call(core, agent, 'read', {'path': 'second.txt'})
    result = (await call(core, agent, 'write', {'path': 'first.txt', 'content': 'changed\n'})).result
    assert result.is_success, result.summary
    moved = tmp_path / 'moved'
    moved.mkdir()
    (moved / 'second.txt').write_text('second\n')
    await bus.execute(Command(type='project.update', target={'project_id': project.id},
        payload={'workspace_dir': str(moved)}))
    result = (await call(core, agent, 'write', {'path': 'second.txt', 'content': 'wrong\n'})).result
    assert not result.is_success and result.data.get('status') == 'conflict'
    assert (moved / 'second.txt').read_text() == 'second\n'
