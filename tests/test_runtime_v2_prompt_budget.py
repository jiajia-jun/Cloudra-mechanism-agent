"""完整请求的容量控制：新输入、真实用量反馈及设置上限。"""

from __future__ import annotations

import pytest

from cloudra.runtime_v2.schemas import Command
from tests.agent_scenarios import ScenarioHarness, ScriptedProvider, Step


async def _idle_agent(harness):
    result = await harness.bus.execute(Command(
        type="agent.spawn",
        target={"project_id": harness.project.id},
        payload={"role_id": "coordinator", "settings": {
            "model": "budget-test", "context_window": 4000, "max_tokens": 256,
            "invocation_protocol": "traditional",
        }},
    ))
    return result.data


async def _send(harness, agent, text):
    await harness.bus.execute(Command(
        type="agent.message", target={"session_id": agent.id},
        payload={"content": text},
    ))
    await harness.wait_terminal(agent)


def _summarizer(monkeypatch, provider):
    async def summarize(agent, messages, **kwargs):
        return await provider.summarize(messages)

    monkeypatch.setattr(
        "cloudra.runtime_v2.compaction.summarize_with_agent_settings", summarize,
    )


@pytest.mark.asyncio
async def test_new_input_triggers_compaction_before_first_request(tmp_path, monkeypatch):
    """旧历史未超预算，加上当前输入才超限：发送前压旧历史，当前指令保留原文。"""
    provider = ScriptedProvider(default=[Step(stop=True)])
    _summarizer(monkeypatch, provider)
    harness = await ScenarioHarness.start(tmp_path, provider=provider)
    try:
        agent = await _idle_agent(harness)
        await harness.core.contexts.append_output(
            agent=agent, run_id="old-run",
            messages=[{"role": "assistant", "content": "old " * 2400}],
        )
        current_request = " ".join(["current"] * 1200)
        await _send(harness, agent, current_request)
        assert agent.state.value == "succeeded", harness.describe(agent)
        types = harness.types(agent)
        assert "context.compacted" in types
        assert types.index("context.compacted") < types.index("llm.request_started")
        sent = provider.calls[0][1]
        assert sum(m.get("content") == current_request for m in sent) == 1
        assert not any(m.get("content") == "old " * 2400 for m in sent)
        assert provider.summary_calls > 0
    finally:
        await harness.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize("intervening", [None, "summary", "missing_usage"])
async def test_provider_usage_corrects_next_turn_budget(tmp_path, monkeypatch, intervening):
    """本地估计仍未超限时，上一轮真实用量已经要求压缩。"""
    provider = ScriptedProvider(default=[Step(stop=True)])
    _summarizer(monkeypatch, provider)
    harness = await ScenarioHarness.start(tmp_path, provider=provider)
    try:
        agent = await _idle_agent(harness)
        await harness.core.contexts.append_output(
            agent=agent, run_id="old-run",
            messages=[{"role": "assistant", "content": "observation " * 2000}],
        )
        harness.core.event_log.append(
            "llm.completed", stream="agent", project_id=agent.project_id,
            session_id=agent.id, run_id="old-run", data={
                "model": "budget-test", "estimated_prompt_tokens": 1000,
                "usage": {"prompt_tokens": 2000},
            },
        )
        if intervening:
            harness.core.event_log.append(
                "llm.completed", stream="agent", project_id=agent.project_id,
                session_id=agent.id, run_id="old-run", data={
                    "model": "budget-test", "kind": intervening,
                    "usage": {"prompt_tokens": 1500} if intervening == "summary" else {},
                },
            )
        await _send(harness, agent, "continue")
        assert agent.state.value == "succeeded", harness.describe(agent)
        assert "context.compacted" in harness.types(agent)
    finally:
        await harness.aclose()


@pytest.mark.asyncio
async def test_unshrinkable_current_input_never_exceeds_configured_window(tmp_path, monkeypatch):
    """单条新指令已超过窗口时明确失败，不能把设置当作无效提示。"""
    provider = ScriptedProvider(default=[Step(stop=True)])
    _summarizer(monkeypatch, provider)
    harness = await ScenarioHarness.start(tmp_path, provider=provider)
    try:
        agent = await _idle_agent(harness)
        current_request = " ".join(["current"] * 6000)
        await _send(harness, agent, current_request)
        assert agent.state.value == "failed", harness.describe(agent)
        assert provider.call_count() == 0
        assert "run.retry" not in harness.types(agent)
        assert any(m.get("content") == current_request
                   for m in harness.core.contexts.current_messages(agent.id))
    finally:
        await harness.aclose()


@pytest.mark.asyncio
async def test_completed_event_records_the_estimate_used_for_usage_feedback(tmp_path):
    provider = ScriptedProvider(default=[Step(stop=True, usage={"prompt_tokens": 42})])
    harness = await ScenarioHarness.start(tmp_path, provider=provider)
    try:
        agent = await harness.spawn("coordinator", protocol="traditional")
        await harness.wait_terminal(agent)
        completed = next(e for e in harness.events(agent) if e.type == "llm.completed")
        assert completed.data["estimated_prompt_tokens"] > 0
        assert completed.data["usage"]["prompt_tokens"] == 42
    finally:
        await harness.aclose()


@pytest.mark.asyncio
async def test_summary_requests_use_the_same_provider_usage_correction(tmp_path, monkeypatch):
    """触发压缩时用过的真实用量修正，也必须用于摘要请求的分段。"""
    from cloudra.runtime_v2.compaction import estimate_messages_tokens

    provider = ScriptedProvider(default=[Step(stop=True)])
    summary_inputs = []

    async def summarize(agent, messages, **kwargs):
        summary_inputs.append(messages)
        return await provider.summarize(messages)

    monkeypatch.setattr("cloudra.runtime_v2.compaction.summarize_with_agent_settings", summarize)
    harness = await ScenarioHarness.start(tmp_path, provider=provider)
    try:
        agent = await _idle_agent(harness)
        await harness.core.contexts.append_output(
            agent=agent, run_id="old-run",
            messages=[{"role": "assistant", "content": "0," * 2500}],
        )
        harness.core.event_log.append(
            "llm.completed", stream="agent", project_id=agent.project_id,
            session_id=agent.id, run_id="old-run", data={
                "model": "budget-test", "estimated_prompt_tokens": 1000,
                "usage": {"prompt_tokens": 2000},
            },
        )
        await _send(harness, agent, "continue")
        assert agent.state.value == "succeeded", harness.describe(agent)
        assert summary_inputs
        assert all(estimate_messages_tokens(messages) * 2 + 256 <= 4000
                   for messages in summary_inputs)
    finally:
        await harness.aclose()


def test_provider_budget_includes_tool_schemas():
    from cloudra.runtime_v2.adapters import LegacyLLMProvider
    from cloudra.runtime_v2.compaction import estimate_messages_tokens
    from cloudra.runtime_v2.schemas import AgentSession, RuntimeSettings

    agent = AgentSession(id="as_budget", project_id="p", role_id="coordinator", display_name="budget",
                         settings=RuntimeSettings(model="budget-test"))
    messages = [{"role": "user", "content": "continue"}]
    tokens = LegacyLLMProvider().estimate_prompt_tokens(agent, messages, ["stop"])
    assert tokens > estimate_messages_tokens(messages) + 20
