"""The model sees the same current method-policy scope as execution gates."""

import json

import pytest

from cloudra.runtime_v2.core import RuntimeCore
from cloudra.runtime_v2.notices import NoticeManager
from cloudra.runtime_v2.policies.base import PipelineContext, ToolCall
from cloudra.runtime_v2.policies.method_policy import MethodPolicyStage
from cloudra.runtime_v2.schemas import AgentCapabilities, MethodPolicy, RuntimeSettings
from tests.test_runtime_v2_method_policy import _POLICY, _FakeLLM, _run_tool_turn, _spawn


def _context(agent, notices):
    return PipelineContext(agent=agent, run_id='scope', settings_snapshot=RuntimeSettings(),
        capabilities=AgentCapabilities(permissions=agent.capabilities.permissions),
        inbox_messages=[], emit=lambda *_: None, notices=notices)


def _scope(content):
    assert content is not None
    payload = content.split('[Current MethodPolicy scope]', 1)[1]
    return json.loads(payload.strip().splitlines()[0])


@pytest.mark.asyncio
async def test_ordinary_model_scope_ignores_stored_benchmark_defaults(tmp_path):
    core = RuntimeCore(strict_events=True)
    _, agent = await _spawn(core, tmp_path, settings={'method_policy': _POLICY})
    notices = NoticeManager()
    stage = MethodPolicyStage(core=core)
    context = _context(agent, notices)
    await stage.before_llm(context, [])
    scope = _scope(notices.pin_content(agent.id, 'method-policy-scope'))
    assert scope == {'project_id': agent.project_id, 'active': False, 'allowed_methods': []}
    result = await stage.before_tool(context, ToolCall(id='write', name='qm_input_writer',
        arguments={'method': 'PBE0', 'basis_set': 'def2-TZVP'}))
    assert result.outcome == 'allow'


@pytest.mark.asyncio
async def test_benchmark_model_scope_reports_actual_whitelist_and_gate(tmp_path):
    core = RuntimeCore(strict_events=True)
    _, agent = await _spawn(core, tmp_path, settings={'benchmark_task_id': 'scope-task', 'method_policy': _POLICY})
    notices = NoticeManager()
    stage = MethodPolicyStage(core=core)
    context = _context(agent, notices)
    await stage.before_llm(context, [])
    scope = _scope(notices.pin_content(agent.id, 'method-policy-scope'))
    assert scope == {'project_id': agent.project_id, 'active': True,
                    'allowed_methods': _POLICY['allowed_methods']}
    result = await stage.before_tool(context, ToolCall(id='write', name='qm_input_writer',
        arguments={'method': 'PBE0', 'basis_set': 'def2-TZVP'}))
    assert result.outcome == 'block'


@pytest.mark.asyncio
async def test_scope_notice_replaces_previous_policy_without_duplicate_pins(tmp_path):
    core = RuntimeCore(strict_events=True)
    project, agent = await _spawn(core, tmp_path,
        settings={'benchmark_task_id': 'scope-task', 'method_policy': _POLICY})
    notices = NoticeManager()
    context = _context(agent, notices)
    stage = MethodPolicyStage(core=core)
    await stage.before_llm(context, [])
    project.settings.method_policy = MethodPolicy(allowed_methods=['b3lyp/def2svp'])
    await stage.before_llm(context, [])
    assert _scope(notices.pin_content(agent.id, 'method-policy-scope'))['allowed_methods'] == ['b3lyp/def2svp']
    project.settings.benchmark_task_id = None
    await MethodPolicyStage(core=core).before_llm(context, [])
    assert _scope(notices.pin_content(agent.id, 'method-policy-scope'))['active'] is False
    assert len(notices.render_current(agent.id)) == 1


@pytest.mark.asyncio
async def test_scope_reaches_model_when_no_notice_manager(tmp_path):
    core = RuntimeCore(strict_events=True)
    _, agent = await _spawn(core, tmp_path)
    messages = []
    await MethodPolicyStage(core=core).before_llm(_context(agent, None), messages)
    assert len(messages) == 1 and messages[0]['role'] == 'system'
    assert _scope(messages[0]['content'])['active'] is False


@pytest.mark.asyncio
@pytest.mark.parametrize('benchmark', [False, True])
async def test_real_turn_model_and_execution_share_the_same_scope(tmp_path, monkeypatch, benchmark):
    core = RuntimeCore(strict_events=True)
    settings = {'method_policy': _POLICY}
    if benchmark:
        settings['benchmark_task_id'] = 'scope-task'
    _, agent = await _spawn(core, tmp_path, settings=settings)
    captured = []
    complete = _FakeLLM.complete

    async def capture(self, agent, messages, tools, **kwargs):
        captured.extend(messages)
        return await complete(self, agent, messages, tools, **kwargs)

    monkeypatch.setattr(_FakeLLM, 'complete', capture)
    _, tools = await _run_tool_turn(core, agent, tmp_path, ToolCall(id='writer', name='qm_input_writer',
        arguments={'method': 'PBE0', 'basis_set': 'def2-TZVP'}))
    contents = [message['content'] for message in captured
        if isinstance(message.get('content'), str) and '[Current MethodPolicy scope]' in message['content']]
    assert len(contents) == 1
    assert _scope(contents[0])['active'] is benchmark
    assert tools.calls == ([] if benchmark else ['qm_input_writer'])
