"""Unit tests for ScheduleStage (Autonomous Schedule Mode Guard)."""

from __future__ import annotations

import pytest

from cloudra.runtime_v2.core import RuntimeCore
from cloudra.runtime_v2.policies.base import ToolCall, ToolResult
from cloudra.runtime_v2.policies.schedule_stage import ScheduleStage
from cloudra.runtime_v2.schemas import AgentCapabilities, PermissionSet
from cloudra.runtime_v2.turn_pipeline import LLMResponse, TurnPipeline


class FakeLLM:
    def __init__(self, response):
        self.response = response
        self.recorded_messages = []

    async def complete(self, agent, messages, tools, **_kwargs):
        self.recorded_messages = list(messages)
        return self.response


class FakeTools:
    async def execute(self, agent, call: ToolCall) -> ToolResult:
        return ToolResult(is_success=True, summary="ok")


async def _setup_agent(core, schedule_mode=False):
    from cloudra.runtime_v2.commands import CommandBus
    from cloudra.runtime_v2.schemas import Command

    await CommandBus(core).execute(
        Command(
            type="project.create",
            payload={"name": "sched project"},
        )
    )
    project = next(iter(core.projects.values()))
    result = await CommandBus(core).execute(
        Command(
            type="agent.spawn",
            target={"project_id": project.id},
            payload={"role_id": "coordinator", "settings": {"schedule_mode": schedule_mode}},
        )
    )
    return project, result.data


@pytest.mark.asyncio
async def test_schedule_mode_disabled_allows_stop():
    core = RuntimeCore(strict_events=True)
    _, agent = await _setup_agent(core, schedule_mode=False)
    agent.settings.schedule_mode = False
    pipeline = TurnPipeline(
        event_log=core.event_log,
        stages=[ScheduleStage(core)],
        llm=FakeLLM(LLMResponse(content="", tool_calls=[ToolCall(id="c1", name="stop", arguments={})])),
        tools=FakeTools(),
    )
    capabilities = AgentCapabilities(permissions=PermissionSet(), tools=["*"])
    outcome = await pipeline.run_turn(
        agent=agent,
        run_id="run1",
        settings=agent.settings,
        capabilities=capabilities,
        inbox_messages=[{"content": "go"}],
    )
    assert outcome.blocked_call is None


@pytest.mark.asyncio
async def test_schedule_mode_pins_notice():
    core = RuntimeCore(strict_events=True)
    _, agent = await _setup_agent(core, schedule_mode=True)
    agent.settings.schedule_mode = True
    llm = FakeLLM(LLMResponse(content="Finished message", tool_calls=[]))
    stage = ScheduleStage(core)
    pipeline = TurnPipeline(
        event_log=core.event_log,
        stages=[stage],
        llm=llm,
        tools=FakeTools(),
    )
    capabilities = AgentCapabilities(permissions=PermissionSet(), tools=["*"])
    await pipeline.run_turn(
        agent=agent,
        run_id="run1",
        settings=agent.settings,
        capabilities=capabilities,
        inbox_messages=[{"content": "go"}],
    )
    assert any("[AUTONOMOUS SCHEDULE MODE ACTIVE]" in m.get("content", "") for m in llm.recorded_messages)


@pytest.mark.asyncio
async def test_schedule_mode_blocks_first_stop_without_reminder():
    core = RuntimeCore(strict_events=True)
    _, agent = await _setup_agent(core, schedule_mode=True)
    agent.settings.schedule_mode = True
    pipeline = TurnPipeline(
        event_log=core.event_log,
        stages=[ScheduleStage(core)],
        llm=FakeLLM(LLMResponse(content="", tool_calls=[ToolCall(id="c1", name="stop", arguments={})])),
        tools=FakeTools(),
    )
    capabilities = AgentCapabilities(permissions=PermissionSet(), tools=["*"])
    outcome = await pipeline.run_turn(
        agent=agent,
        run_id="run1",
        settings=agent.settings,
        capabilities=capabilities,
        inbox_messages=[{"content": "go"}],
    )
    assert outcome.blocked_call is not None
    assert outcome.blocked_call.name == "stop"
    assert "Stop intercepted by Schedule Mode" in (outcome.content or "")


@pytest.mark.asyncio
async def test_schedule_mode_allows_stop_when_reminder_pending():
    core = RuntimeCore(strict_events=True)
    _, agent = await _setup_agent(core, schedule_mode=True)
    agent.settings.schedule_mode = True
    stage = ScheduleStage(core)
    pipeline = TurnPipeline(
        event_log=core.event_log,
        stages=[stage],
        llm=FakeLLM(LLMResponse(content="", tool_calls=[ToolCall(id="c1", name="stop", arguments={})])),
        tools=FakeTools(),
    )
    capabilities = AgentCapabilities(permissions=PermissionSet(), tools=["*"])

    # Schedule a reminder in core via ReminderBroker handle
    agent_session = core.agents.get(agent.id)
    await core.reminders.handle(
        agent_session,
        ToolCall(id="r1", name="schedule", arguments={"action": "create", "delay_seconds": 60, "message": "Check job"}),
    )

    outcome = await pipeline.run_turn(
        agent=agent,
        run_id="run1",
        settings=agent.settings,
        capabilities=capabilities,
        inbox_messages=[{"content": "go"}],
    )
    assert outcome.blocked_call is None


@pytest.mark.asyncio
async def test_schedule_mode_allows_second_consecutive_stop_as_confirmation():
    core = RuntimeCore(strict_events=True)
    _, agent = await _setup_agent(core, schedule_mode=True)
    agent.settings.schedule_mode = True
    stage = ScheduleStage(core)
    capabilities = AgentCapabilities(permissions=PermissionSet(), tools=["*"])

    # Turn 1: First stop -> blocked
    pipeline1 = TurnPipeline(
        event_log=core.event_log,
        stages=[stage],
        llm=FakeLLM(LLMResponse(content="", tool_calls=[ToolCall(id="c1", name="stop", arguments={})])),
        tools=FakeTools(),
    )
    outcome1 = await pipeline1.run_turn(
        agent=agent,
        run_id="run1",
        settings=agent.settings,
        capabilities=capabilities,
        inbox_messages=[{"content": "go"}],
    )
    assert outcome1.blocked_call is not None

    # Turn 2: Agent confirms goal is done by calling stop again -> allowed
    pipeline2 = TurnPipeline(
        event_log=core.event_log,
        stages=[stage],
        llm=FakeLLM(LLMResponse(content="", tool_calls=[ToolCall(id="c2", name="stop", arguments={})])),
        tools=FakeTools(),
    )
    outcome2 = await pipeline2.run_turn(
        agent=agent,
        run_id="run2",
        settings=agent.settings,
        capabilities=capabilities,
        inbox_messages=[{"content": "go"}],
    )
    assert outcome2.blocked_call is None
