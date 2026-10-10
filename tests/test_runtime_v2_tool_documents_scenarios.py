"""Document preloading is a durable first-task phase, not a new agent."""
import pytest

from cloudra.runtime_v2.schemas import Command
from cloudra.runtime_v2.turn_pipeline import LLMResponse
from tests.agent_scenarios import ScenarioHarness, ScriptedProvider, Step


class ChooseRead(ScriptedProvider):
    async def select_tool_names(self, agent, messages, *, resolved_settings):
        await super().select_tool_names(agent,messages,resolved_settings=resolved_settings)
        return LLMResponse(content='["read"]',usage={'input_tokens':7})


@pytest.mark.asyncio
async def test_tool_documents_preload_once_and_survive_new_task(tmp_path, monkeypatch):
    provider=ChooseRead(default=[Step(stop=True)])
    harness=await ScenarioHarness.start(tmp_path,provider=provider)
    try:
        agent=await harness.spawn('coordinator',query='Inspect actual evidence input')
        await harness.wait_terminal(agent)
        assert len(getattr(provider,'selection_calls',[]))==1
        assert 'Inspect actual evidence input' in str(provider.selection_calls[0][1])
        context=harness.core.session_contexts[agent.id]
        record=context.prefix_meta['tool_selection']
        assert record['status']=='selected'
        assert record['names']==['read']
        documents=[m for m in context.messages if m.get('tool_documents')]
        assert [item['name'] for item in documents[0]['tool_documents']]==['read']
        original_caps=list(agent.capabilities.tools)
        original_revision=record['document_revisions']['read']
        from cloudra.tools import get_tools_lst
        read_entry=next(entry for entry in get_tools_lst() if entry.tool_name=='read')
        monkeypatch.setattr(read_entry,'tool_description',read_entry.tool_description+' New contract revision.')
        provider.script_default(Step(stop=True))
        await harness.bus.execute(Command(type='agent.message',target={'session_id':agent.id},payload={'content':'Another task'}))
        await harness.wait_for(lambda:provider.call_count()==2,'second main request')
        await harness.wait_terminal(agent)
        assert len(provider.selection_calls)==1
        assert agent.capabilities.tools==original_caps
        changed=harness.core.session_contexts[agent.id].prefix_meta['tool_selection']
        assert changed['document_revisions']['read'] != original_revision
    finally:
        await harness.aclose()


@pytest.mark.asyncio
async def test_tool_selection_failure_still_allows_main_task(tmp_path):
    class Broken(ScriptedProvider):
        async def select_tool_names(self,*args,**kwargs):
            raise RuntimeError('No selection service')
    provider=Broken(default=[Step(stop=True)])
    harness=await ScenarioHarness.start(tmp_path,provider=provider)
    try:
        agent=await harness.spawn('coordinator',query='Read evidence')
        await harness.wait_terminal(agent)
        assert provider.call_count()==1
        record=harness.core.session_contexts[agent.id].prefix_meta['tool_selection']
        assert record['status']=='failed'
        assert record['error_code']=='RuntimeError'
    finally:
        await harness.aclose()


@pytest.mark.asyncio
async def test_empty_agent_defers_selection_and_interrupted_selection_restores_without_retry(tmp_path):
    from cloudra.runtime_v2.tool_selection import ToolSelectionRecord
    provider=ChooseRead(default=[Step(stop=True)])
    harness=await ScenarioHarness.start(tmp_path,provider=provider)
    agent=await harness.spawn('coordinator',query='')
    await harness.settle()
    assert getattr(provider,'selection_calls',[])==[]
    record=ToolSelectionRecord(status='started',source='llm',catalog_revision='revision',selection_id='attempt')
    await harness.core.contexts.record_tool_selection(agent=agent,run_id='interrupted',record=record,messages=[])
    await harness.aclose()
    resumed_provider=ChooseRead(default=[Step(stop=True)])
    restored=await ScenarioHarness.restore(tmp_path,provider=resumed_provider)
    try:
        resumed=restored.core.agents[agent.id]
        await restored.bus.execute(Command(type='agent.message',target={'session_id':resumed.id},payload={'content':'Read evidence now'}))
        await restored.wait_terminal(resumed)
        assert getattr(resumed_provider,'selection_calls',[])==[]
        state=restored.core.session_contexts[agent.id].prefix_meta['tool_selection']
        assert state['status']=='failed'
        assert state['error_code']=='selection_interrupted'
    finally:
        await restored.aclose()


@pytest.mark.asyncio
async def test_compacted_selection_restores_but_explicit_restart_selects_again(tmp_path):
    provider = ChooseRead(default=[Step(stop=True)])
    harness = await ScenarioHarness.start(tmp_path, provider=provider)
    agent = await harness.spawn('coordinator', query='Read first task')
    await harness.wait_terminal(agent)
    state = harness.core.contexts.prefix_state(agent.id)
    assert await harness.core.contexts.install_compacted(
        agent=agent, run_id='compact', messages=[{'role': 'assistant', 'content': 'Summary'}],
        prefix_meta=state['meta'], expected_version=len(state['messages']), trigger='test',
    )
    await harness.aclose()
    resumed_provider = ChooseRead(default=[Step(stop=True)])
    restored = await ScenarioHarness.restore(tmp_path, provider=resumed_provider)
    try:
        resumed = restored.core.agents[agent.id]
        await restored.bus.execute(Command(type='agent.message', target={'session_id': resumed.id},
            payload={'content': 'Continue after compact'}))
        await restored.wait_for(lambda: resumed_provider.call_count() == 1, 'resumed main request')
        await restored.wait_terminal(resumed)
        assert getattr(resumed_provider, 'selection_calls', []) == []
        assert restored.core.session_contexts[resumed.id].prefix_meta['tool_selection']['names'] == ['read']
        resumed_provider.script_default(Step(stop=True))
        await restored.bus.execute(Command(type='agent.restart', target={'session_id': resumed.id},
            payload={'message': 'Fresh context task'}))
        await restored.wait_for(lambda: resumed_provider.call_count() == 2, 'reset main request')
        await restored.wait_terminal(resumed)
        assert len(resumed_provider.selection_calls) == 1
    finally:
        await restored.aclose()


@pytest.mark.asyncio
async def test_interruption_after_input_commit_recovers_first_task_selection(tmp_path, monkeypatch):
    provider = ChooseRead(default=[Step(stop=True)])
    harness = await ScenarioHarness.start(tmp_path, provider=provider)
    initial = harness.pipeline._initial_tool_documents
    attempts = 0

    async def interrupted(*args, **kwargs):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError('interrupted after input commit')
        return await initial(*args, **kwargs)

    monkeypatch.setattr(harness.pipeline, '_initial_tool_documents', interrupted)
    try:
        agent = await harness.spawn('coordinator', query='Original first task anchor')
        await harness.wait_terminal(agent)
        assert provider.call_count() == 1
        assert len(getattr(provider, 'selection_calls', [])) == 1
        assert 'Original first task anchor' in str(provider.selection_calls[0][1])
        record = harness.core.session_contexts[agent.id].prefix_meta['tool_selection']
        assert record['task_message_ids']
    finally:
        await harness.aclose()


@pytest.mark.asyncio
async def test_on_demand_contract_version_survives_process_restore(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from cloudra.runtime_v2.adapters import LegacyToolExecutor
    from cloudra.runtime_v2.policies.base import ToolCall
    from cloudra.tools import get_tools_lst

    provider = ScriptedProvider(default=[Step(stop=True)])
    harness = await ScenarioHarness.start(tmp_path, provider=provider)
    agent = await harness.spawn('coordinator', query='Explanation only')
    await harness.wait_terminal(agent)
    call = ToolCall('docs', 'get_tool_docs', {'names': ['read']})
    result = await LegacyToolExecutor(harness.core).execute(agent, call)
    assert result.is_success
    await harness.core.runner._commit_turn_output(agent, 'docs', SimpleNamespace(content='', reasoning='',
        tool_exchanges=[(call, result)], blocked_call=None))
    version = harness.core.contexts.prefix_state(agent.id)['meta']['tool_document_revisions']['read']
    await harness.aclose()
    entry = next(entry for entry in get_tools_lst() if entry.tool_name == 'read')
    monkeypatch.setattr(entry, 'tool_description', entry.tool_description + ' RESTORED_CONTRACT_UPDATE')
    resumed_provider = ScriptedProvider(default=[Step(stop=True)])
    restored = await ScenarioHarness.restore(tmp_path, provider=resumed_provider)
    try:
        resumed = restored.core.agents[agent.id]
        await restored.bus.execute(Command(type='agent.message', target={'session_id': resumed.id},
            payload={'content': 'Continue after restore'}))
        await restored.wait_terminal(resumed)
        state = restored.core.contexts.prefix_state(resumed.id)
        assert state['meta']['tool_document_revisions']['read'] != version
        assert 'superseded' in str(state['messages'])
        assert getattr(resumed_provider, 'selection_calls', []) == []
    finally:
        await restored.aclose()


@pytest.mark.asyncio
async def test_committed_initial_batch_is_selected_instead_of_later_task():
    from cloudra.runtime_v2.core import RuntimeCore
    from cloudra.runtime_v2.schemas import AgentCapabilities, AgentSession, PermissionSet
    from cloudra.runtime_v2.turn_pipeline import TurnPipeline

    core = RuntimeCore(strict_events=True)
    provider = ChooseRead()
    agent = AgentSession(id='anchor', project_id='anchor-project', role_id='coordinator', display_name='Anchor',
        capabilities=AgentCapabilities(permissions=PermissionSet(read=True), tools=['read', 'get_tool_docs']))
    pipeline = TurnPipeline(event_log=core.event_log, stages=[], llm=provider, tools=None)
    first = [{'role': 'user', 'content': 'First task part one', 'message_id': 'first-one'},
        {'role': 'user', 'content': 'First task part two', 'message_id': 'first-two'}]
    later = [{'role': 'user', 'content': 'UNRELATED_LATER_TASK', 'message_id': 'later'}]
    await core.contexts.commit_input(agent=agent, run_id='first', context_prefix=None, notices=None, user_messages=first)
    await core.contexts.commit_input(agent=agent, run_id='later', context_prefix=None, notices=None, user_messages=later)
    await pipeline._initial_tool_documents(agent, 'retry', later, core.contexts, None)
    supplied = str(provider.selection_calls[0][1])
    assert 'First task part one' in supplied and 'First task part two' in supplied
    assert 'UNRELATED_LATER_TASK' not in supplied
    assert core.contexts.prefix_state(agent.id)['meta']['tool_selection']['task_message_ids'] == ['first-one', 'first-two']
