"""Turn pipeline skeleton tests with fake LLM and tools."""

from __future__ import annotations

import pytest

from cloudra.runtime_v2.core import RuntimeCore
from cloudra.runtime_v2.policies import default_stages
from cloudra.runtime_v2.policies.base import ToolCall, ToolResult
from cloudra.runtime_v2.schemas import (
    AgentCapabilities,
    PermissionSet,
    RuntimeSettings,
)
from cloudra.runtime_v2.turn_pipeline import LLMResponse, TurnPipeline


class FakeLLM:
    def __init__(self, response: LLMResponse) -> None:
        self.response = response
        self.calls = 0

    async def complete(self, agent, messages, tools):
        self.calls += 1
        return self.response


class FakeTools:
    def __init__(self, result: ToolResult) -> None:
        self.result = result

    async def execute(self, agent, call: ToolCall) -> ToolResult:
        return self.result


async def _spawn_agent(core: RuntimeCore):
    from cloudra.runtime_v2.commands import CommandBus
    from cloudra.runtime_v2.schemas import Command

    await CommandBus(core).execute(Command(type="project.create", payload={"name": "p"}))
    project = next(iter(core.projects.values()))
    await CommandBus(core).execute(
        Command(type="agent.spawn", target={"project_id": project.id}, payload={"role_id": "coordinator"})
    )
    return project, next(iter(core.agents.values()))


@pytest.mark.asyncio
async def test_pipeline_executes_tool_and_emits_ordered_events():
    core = RuntimeCore(strict_events=True)
    _, agent = await _spawn_agent(core)
    run_id = "run_test"
    pipeline = TurnPipeline(
        event_log=core.event_log,
        stages=default_stages(),
        llm=FakeLLM(
            LLMResponse(
                content="",
                tool_calls=[ToolCall(id="tc1", name="echo", arguments={"x": 1})],
                stop_requested=False,
            )
        ),
        tools=FakeTools(ToolResult(is_success=True, summary="ok")),
    )
    capabilities = AgentCapabilities(
        permissions=PermissionSet(), tools=["echo"], can_spawn=False
    )
    outcome = await pipeline.run_turn(
        agent=agent,
        run_id=run_id,
        settings=RuntimeSettings(),
        capabilities=capabilities,
        inbox_messages=[{"content": "hello"}],
    )
    assert outcome.decision == "continue"
    types = [e.type for e in core.event_log.query_session(agent.id) if e.run_id == run_id]
    assert types == ["llm.request_started", "llm.completed", "tool.started", "tool.finished"]


class RecordingLLM:
    def __init__(self) -> None:
        self.messages = None

    async def complete(self, agent, messages, tools):
        self.messages = list(messages)
        return LLMResponse(content="done", stop_requested=True)


@pytest.mark.asyncio
async def test_prompt_provider_messages_are_prepended():
    core = RuntimeCore(strict_events=True)
    _, agent = await _spawn_agent(core)
    async def provider(**kwargs):
        return [{"role": "system", "content": "ROLE PROMPT"}]

    pipeline = TurnPipeline(
        event_log=core.event_log,
        stages=default_stages(),
        llm=RecordingLLM(),
        tools=FakeTools(ToolResult(is_success=True)),
        prompt_provider=provider,
    )
    await pipeline.run_turn(
        agent=agent,
        run_id="run_prompt",
        settings=RuntimeSettings(),
        capabilities=AgentCapabilities(permissions=PermissionSet(), tools=[]),
        inbox_messages=[{"content": "hello"}],
    )
    messages = pipeline.llm.messages
    assert messages[0] == {"role": "system", "content": "ROLE PROMPT"}
    assert messages[1] == {"role": "user", "content": "hello"}


@pytest.mark.asyncio
async def test_pipeline_stop_without_tool_calls():
    core = RuntimeCore(strict_events=True)
    _, agent = await _spawn_agent(core)
    pipeline = TurnPipeline(
        event_log=core.event_log,
        stages=default_stages(),
        llm=FakeLLM(LLMResponse(content="done", stop_requested=True)),
        tools=FakeTools(ToolResult(is_success=True)),
    )
    outcome = await pipeline.run_turn(
        agent=agent,
        run_id="run_test",
        settings=RuntimeSettings(),
        capabilities=AgentCapabilities(permissions=PermissionSet(), tools=[]),
        inbox_messages=[],
    )
    assert outcome.decision == "stop"


@pytest.mark.asyncio
async def test_permission_stage_blocks_unavailable_tool():
    core = RuntimeCore(strict_events=True)
    _, agent = await _spawn_agent(core)
    pipeline = TurnPipeline(
        event_log=core.event_log,
        stages=default_stages(),
        llm=FakeLLM(
            LLMResponse(
                tool_calls=[ToolCall(id="tc1", name="not_allowed", arguments={})]
            )
        ),
        tools=FakeTools(ToolResult(is_success=True)),
    )
    outcome = await pipeline.run_turn(
        agent=agent,
        run_id="run_test",
        settings=RuntimeSettings(),
        capabilities=AgentCapabilities(permissions=PermissionSet(), tools=["allowed"]),
        inbox_messages=[],
    )
    assert outcome.message.startswith("blocked by permission")
    assert [e.type for e in core.event_log.query_session(agent.id)][-1] == "tool.blocked"
