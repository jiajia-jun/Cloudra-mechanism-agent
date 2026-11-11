"""Unit tests for ScheduleStage (Autonomous Schedule Mode Guard)."""

from __future__ import annotations

import pytest

from cloudra.runtime_v2.core import RuntimeCore
from cloudra.runtime_v2.policies.base import ToolCall, ToolResult
from cloudra.runtime_v2.policies.schedule_stage import INTERCEPT_MESSAGE, ScheduleStage
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


async def _setup_agent(core, schedule_mode=False, role_id="coordinator"):
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
            payload={"role_id": role_id, "settings": {"schedule_mode": schedule_mode}},
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
async def test_owned_compute_job_suspends_stop_without_schedule_mode():
    from cloudra.persistence.database import ComputeDB
    from cloudra.runtime_v2.policies.base import PipelineContext
    from cloudra.services.compute_store import insert_compute_job

    core = RuntimeCore(strict_events=True)
    project, agent = await _setup_agent(core, schedule_mode=False, role_id="small_mol")
    insert_compute_job(
        ComputeDB().init(),
        conversation_id=project.id,
        session_id=agent.id,
        path="/tmp/owned-job.gjf",
        state="ready",
        jobtype="gaussian",
        node_id="local",
    )
    stage = ScheduleStage(core)
    ctx = PipelineContext(
        agent=agent,
        run_id="run1",
        settings_snapshot=agent.settings,
        capabilities=agent.capabilities,
        inbox_messages=[],
        emit=lambda *_args: None,
    )

    gate = await stage.audit_run_end(ctx, explicit_stop=True)

    assert gate is not None
    assert gate.action == "wait_background"
    assert gate.basis == "background_wait"


@pytest.mark.asyncio
async def test_owned_compute_job_is_wake_source_for_schedule_mode():
    from cloudra.persistence.database import ComputeDB
    from cloudra.runtime_v2.policies.base import PipelineContext
    from cloudra.services.compute_store import insert_compute_job

    core = RuntimeCore(strict_events=True)
    project, agent = await _setup_agent(core, schedule_mode=True, role_id="small_mol")
    insert_compute_job(
        ComputeDB().init(),
        conversation_id=project.id,
        session_id=agent.id,
        path="/tmp/owned-job.gjf",
        state="ready",
        jobtype="gaussian",
        node_id="local",
    )
    stage = ScheduleStage(core)
    ctx = PipelineContext(
        agent=agent,
        run_id="run1",
        settings_snapshot=agent.settings,
        capabilities=agent.capabilities,
        inbox_messages=[],
        emit=lambda *_args: None,
    )

    allowed = await stage.before_tool(ctx, ToolCall(id="stop", name="stop"))
    gate = await stage.audit_run_end(ctx, explicit_stop=True)

    assert allowed.outcome == "allow"
    assert gate is not None and gate.action == "wait_background"


@pytest.mark.asyncio
async def test_terminal_job_without_durable_notification_still_suspends():
    """The job may finish before the broker delivers its result to the child."""
    from cloudra.persistence.database import ComputeDB
    from cloudra.runtime_v2.policies.base import PipelineContext
    from cloudra.services.compute_store import ainsert_compute_job

    core = RuntimeCore(strict_events=True)
    project, agent = await _setup_agent(core, role_id="small_mol")
    db = await ComputeDB().ainit()
    job_id = await ainsert_compute_job(
        db,
        conversation_id=project.id,
        session_id=agent.id,
        path="/tmp/finished-job.gjf",
        state="done",
        jobtype="gaussian",
        node_id="local",
    )
    stage = ScheduleStage(core)
    ctx = PipelineContext(
        agent=agent,
        run_id="run1",
        settings_snapshot=agent.settings,
        capabilities=agent.capabilities,
        inbox_messages=[],
        emit=lambda *_args: None,
    )

    gate = await stage.audit_run_end(ctx, explicit_stop=True)
    assert gate is not None and gate.action == "wait_background"

    async with db.aconnect() as con:
        await con.execute("UPDATE compute_jobs SET notified_at=1 WHERE id=?", (job_id,))
        await con.commit()
    assert await stage.audit_run_end(ctx, explicit_stop=True) is None


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
    assistant_text = "I checked the current status."
    pipeline = TurnPipeline(
        event_log=core.event_log,
        stages=[ScheduleStage(core)],
        llm=FakeLLM(LLMResponse(content=assistant_text, tool_calls=[ToolCall(id="c1", name="stop", arguments={})])),
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
    assert outcome.decision == "continue"
    assert outcome.content == assistant_text
    assert outcome.message == INTERCEPT_MESSAGE


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


@pytest.mark.asyncio
async def test_schedule_mode_allows_stop_when_check_pending():
    core = RuntimeCore(strict_events=True)
    _, agent = await _setup_agent(core, schedule_mode=True)
    agent.settings = agent.settings.model_copy(update={"yolo": True, "schedule_mode": True})
    stage = ScheduleStage(core)
    pipeline = TurnPipeline(
        event_log=core.event_log,
        stages=[stage],
        llm=FakeLLM(LLMResponse(content="", tool_calls=[ToolCall(id="c1", name="stop", arguments={})])),
        tools=FakeTools(),
    )
    capabilities = AgentCapabilities(permissions=PermissionSet(), tools=["*"])
    agent_session = core.agents.get(agent.id)
    agent_session.settings = agent.settings
    created = await core.reminders.handle(
        agent_session,
        ToolCall(
            id="r1",
            name="schedule",
            arguments={
                "action": "create",
                "message": "wait for squeue",
                "check_command": "false",
                "interval_seconds": 5,
                "timeout_seconds": 60,
            },
        ),
    )
    assert created.is_success is True
    outcome = await pipeline.run_turn(
        agent=agent,
        run_id="run1",
        settings=agent.settings,
        capabilities=capabilities,
        inbox_messages=[{"content": "go"}],
    )
    assert outcome.blocked_call is None
    await core.reminders.close()
