"""AgentRunner integration: live execution, cancel, restart, wakeup."""

from __future__ import annotations

import asyncio

import pytest

from cloudra.runtime_v2.agent_runner import AgentRunner
from cloudra.runtime_v2.commands import CommandBus
from cloudra.runtime_v2.core import RuntimeCore
from cloudra.runtime_v2.policies import default_stages
from cloudra.runtime_v2.policies.base import ToolCall, ToolResult
from cloudra.runtime_v2.schemas import Command
from cloudra.runtime_v2.turn_pipeline import LLMResponse, TurnPipeline


class ScriptedLLM:
    def __init__(self, responses: list[LLMResponse]) -> None:
        self.responses = list(responses)

    async def complete(self, agent, messages, tools):
        assert self.responses, "no scripted LLM response left"
        return self.responses.pop(0)


class HangingLLM:
    async def complete(self, agent, messages, tools):
        await asyncio.Event().wait()


class EchoTools:
    async def execute(self, agent, call: ToolCall) -> ToolResult:
        return ToolResult(is_success=True, summary=f"echo:{call.arguments.get('x')}", data={})


async def _setup(llm) -> tuple[RuntimeCore, object, object]:
    core = RuntimeCore(strict_events=True)
    pipeline = TurnPipeline(
        event_log=core.event_log,
        stages=default_stages(),
        llm=llm,
        tools=EchoTools(),
    )
    core.runner = AgentRunner(core, pipeline)
    bus = CommandBus(core)
    await bus.execute(Command(type="project.create", payload={"name": "runner demo"}))
    project = next(iter(core.projects.values()))
    result = await bus.execute(
        Command(
            type="agent.spawn",
            target={"project_id": project.id},
            payload={"role_id": "coordinator", "query": "solve it"},
        )
    )
    return core, project, result.data


async def _wait_state(agent, state: str, timeout: float = 2.0):
    deadline = asyncio.get_running_loop().time() + timeout
    while agent.state.value != state:
        if asyncio.get_running_loop().time() > deadline:
            raise AssertionError(f"agent stuck in {agent.state.value}, expected {state}")
        await asyncio.sleep(0.01)


@pytest.mark.asyncio
async def test_runner_executes_tool_then_stops():
    llm = ScriptedLLM(
        [
            LLMResponse(
                content="",
                tool_calls=[ToolCall(id="tc1", name="echo", arguments={"x": 1})],
                stop_requested=False,
            ),
            LLMResponse(content="done", stop_requested=True),
        ]
    )
    core, _, agent = await _setup(llm)
    await _wait_state(agent, "succeeded")
    events = [e.type for e in core.event_log.query_session(agent.id)]
    assert "run.started" in events
    assert "tool.started" in events
    assert "tool.finished" in events
    assert "run.finished" in events
    assert events.index("run.started") < events.index("tool.started") < events.index("run.finished")


@pytest.mark.asyncio
async def test_message_wakes_succeeded_agent_with_new_run():
    llm = ScriptedLLM(
        [
            LLMResponse(content="first done", stop_requested=True),
            LLMResponse(content="second done", stop_requested=True),
        ]
    )
    core, _, agent = await _setup(llm)
    await _wait_state(agent, "succeeded")
    first_runs = [e for e in core.event_log.query_session(agent.id) if e.type == "run.started"]
    assert len(first_runs) == 1

    result = await CommandBus(core).execute(
        Command(
            type="agent.message",
            target={"session_id": agent.id},
            payload={"content": "continue"},
        )
    )
    assert result.data.state == "running"
    await _wait_state(agent, "succeeded")
    assert agent.current_run is None
    messages = [
        e for e in core.event_log.query_session(agent.id) if e.type == "agent.message_injected"
    ]
    assert messages[-1].data["content"] == "continue"
    runs = [e for e in core.event_log.query_session(agent.id) if e.type == "run.started"]
    assert len(runs) == 2
    assert runs[1].run_id != runs[0].run_id


@pytest.mark.asyncio
async def test_cancel_terminates_hanging_agent_and_closes_run():
    core, _, agent = await _setup(HangingLLM())
    await _wait_state(agent, "running")
    result = await CommandBus(core).execute(
        Command(type="agent.cancel", target={"session_id": agent.id}, payload={})
    )
    assert result.data.state == "cancelled"
    assert agent.current_run is None
    assert core.runner._tasks.get(agent.id) is None
    types = [e.type for e in core.event_log.query_session(agent.id)]
    assert "agent.cancelled" in types


@pytest.mark.asyncio
async def test_two_projects_run_agents_concurrently_and_stay_isolated():
    core = RuntimeCore(strict_events=True)
    pipeline = TurnPipeline(
        event_log=core.event_log,
        stages=default_stages(),
        llm=ScriptedLLM(
            [
                LLMResponse(content="A tool", tool_calls=[ToolCall(id="a1", name="echo", arguments={"x": 1})]),
                LLMResponse(content="A done", stop_requested=True),
                LLMResponse(content="B tool", tool_calls=[ToolCall(id="b1", name="echo", arguments={"x": 2})]),
                LLMResponse(content="B done", stop_requested=True),
            ]
        ),
        tools=EchoTools(),
    )
    core.runner = AgentRunner(core, pipeline)
    bus = CommandBus(core)
    agents = []
    for name in ("A", "B"):
        await bus.execute(Command(type="project.create", payload={"name": name}))
        project = next(p for p in core.projects.values() if p.name == name)
        result = await bus.execute(
            Command(
                type="agent.spawn",
                target={"project_id": project.id},
                payload={"role_id": "coordinator", "query": f"task {name}"},
            )
        )
        agents.append(result.data)

    deadline = asyncio.get_running_loop().time() + 2.0
    while any(a.state.value != "succeeded" for a in agents):
        assert asyncio.get_running_loop().time() < deadline, "agents did not finish concurrently"
        await asyncio.sleep(0.01)

    for agent in agents:
        events = [e for e in core.event_log.query_session(agent.id) if e.type.startswith(("llm.", "tool."))]
        assert [e.type for e in events][:4] == [
            "llm.request_started",
            "llm.completed",
            "tool.started",
            "tool.finished",
        ]
        other_project_events = [
            e for e in core.event_log if e.project_id != agent.project_id and e.session_id == agent.id
        ]
        assert other_project_events == []


@pytest.mark.asyncio
async def test_restart_schedules_new_run_with_message():
    llm = ScriptedLLM(
        [
            LLMResponse(content="old run", stop_requested=True),
            LLMResponse(content="new run", stop_requested=True),
        ]
    )
    core, _, agent = await _setup(llm)
    await _wait_state(agent, "succeeded")
    result = await CommandBus(core).execute(
        Command(
            type="agent.restart",
            target={"session_id": agent.id},
            payload={"message": "start over"},
        )
    )
    assert result.data.state in {"queued", "running"}
    await _wait_state(agent, "succeeded")
    messages = [
        e for e in core.event_log.query_session(agent.id) if e.type == "agent.message_injected"
    ]
    assert messages[-1].data["content"] == "start over"
