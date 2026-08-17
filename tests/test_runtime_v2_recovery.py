"""Failure recovery: crashed turns auto-retry; messaging a terminal agent reopens it."""

from __future__ import annotations

import asyncio

import pytest

from cloudra.runtime_v2.adapters import LegacyToolExecutor
from cloudra.runtime_v2.agent_runner import AgentRunner
from cloudra.runtime_v2.commands import CommandBus
from cloudra.runtime_v2.core import RuntimeCore
from cloudra.runtime_v2.policies import default_stages
from cloudra.runtime_v2.policies.base import ToolCall
from cloudra.runtime_v2.schemas import AgentState, Command
from cloudra.runtime_v2.turn_pipeline import LLMResponse, TurnPipeline


class FlakyLLM:
    """Fails ``fail_times`` times, then replays scripted responses."""

    def __init__(self, plan: list[LLMResponse], fail_times: int = 0) -> None:
        self.plan = list(plan)
        self.fail_times = fail_times
        self.calls: list[int] = []  # message count per LLM call

    async def complete(self, agent, messages, tools, **_kwargs):
        self.calls.append(len(messages))
        if self.fail_times > 0:
            self.fail_times -= 1
            raise RuntimeError("transport boom")
        assert self.plan, "no scripted response left"
        return self.plan.pop(0)


async def _setup(llm, **runner_kwargs):
    core = RuntimeCore(strict_events=True)
    pipeline = TurnPipeline(
        event_log=core.event_log,
        stages=default_stages(),
        llm=llm,
        tools=LegacyToolExecutor(core),
    )
    core.runner = AgentRunner(core, pipeline, retry_backoff=(0.0, 0.0), **runner_kwargs)
    bus = CommandBus(core)
    await bus.execute(Command(type="project.create", payload={"name": "recovery"}))
    project = next(iter(core.projects.values()))
    result = await bus.execute(
        Command(
            type="agent.spawn",
            target={"project_id": project.id},
            payload={"role_id": "coordinator", "query": "solve it"},
        )
    )
    return core, project, result.data


async def _wait_state(agent, state: AgentState, timeout: float = 5.0):
    deadline = asyncio.get_running_loop().time() + timeout
    while agent.state is not state:
        if asyncio.get_running_loop().time() > deadline:
            raise AssertionError(f"agent stuck in {agent.state.value}, expected {state.value}")
        await asyncio.sleep(0.01)


def _retries(core, session_id: str):
    return [e for e in core.event_log.query_session(session_id) if e.type == "run.retry"]


@pytest.mark.asyncio
async def test_crash_turn_retries_and_succeeds():
    llm = FlakyLLM([LLMResponse(content="recovered", stop_requested=True)], fail_times=1)
    core, _, agent = await _setup(llm)
    await _wait_state(agent, AgentState.SUCCEEDED)
    retries = _retries(core, agent.id)
    assert len(retries) == 1
    assert "transport boom" in retries[0].data["error"]
    emitted = core.event_log.query_session(agent.id, types={"agent.message_emitted"})
    assert emitted[-1].data["content"] == "recovered"


@pytest.mark.asyncio
async def test_persistent_crash_fails_after_bounded_retries():
    llm = FlakyLLM([], fail_times=99)
    core, _, agent = await _setup(llm, max_turn_retries=2)
    await _wait_state(agent, AgentState.FAILED)
    assert len(_retries(core, agent.id)) == 2  # 1 initial + 2 retries, then failed
    finished = core.event_log.query_session(agent.id, types={"run.finished"})
    assert finished[-1].data["outcome"] == "failed"


@pytest.mark.asyncio
async def test_retry_preserves_completed_turn_history():
    llm = FlakyLLM(
        [
            LLMResponse(
                content="",
                tool_calls=[ToolCall(id="t1", name="ask_user", arguments={"question": "q"})],
            ),
            LLMResponse(content="final", stop_requested=True),
        ],
        fail_times=0,
    )
    core, project, agent = await _setup(llm)
    # Turn 1 (ask_user) parks; respond; turn 2 crashes once, then succeeds.
    await _wait_state(agent, AgentState.WAITING_INPUT)
    pending = core.pending.list_pending_interactions(project.id)
    llm.fail_times = 1  # the next LLM call (turn 2) crashes, retry succeeds
    bus = CommandBus(core)
    await bus.execute(
        Command(
            type="interaction.respond",
            target={"project_id": project.id},
            payload={"interaction_id": pending[0]["interaction_id"], "response": "answer"},
        )
    )
    await _wait_state(agent, AgentState.SUCCEEDED)
    assert len(_retries(core, agent.id)) == 1
    # The retried turn saw the completed first turn's tool exchange.
    assert llm.calls[-1] == llm.calls[-2]
    assert llm.calls[-1] > llm.calls[0]


@pytest.mark.asyncio
async def test_message_to_failed_agent_reopens_run():
    llm = FlakyLLM([LLMResponse(content="second life", stop_requested=True)], fail_times=99)
    core, _, agent = await _setup(llm)
    await _wait_state(agent, AgentState.FAILED)

    llm.fail_times = 0  # transport is back
    bus = CommandBus(core)
    result = await bus.execute(
        Command(type="agent.message", target={"session_id": agent.id}, payload={"content": "try again"})
    )
    assert result.accepted is True
    await _wait_state(agent, AgentState.SUCCEEDED)
    emitted = core.event_log.query_session(agent.id, types={"agent.message_emitted"})
    assert emitted[-1].data["content"] == "second life"


@pytest.mark.asyncio
async def test_cancel_mid_tool_closes_tool_event():
    llm = FlakyLLM(
        [
            LLMResponse(
                content="",
                tool_calls=[ToolCall(id="t1", name="ask_user", arguments={"question": "hold on"})],
            ),
            LLMResponse(content="unreachable", stop_requested=True),
        ]
    )
    core, _, agent = await _setup(llm)
    await _wait_state(agent, AgentState.WAITING_INPUT)
    bus = CommandBus(core)
    await bus.execute(Command(type="agent.cancel", target={"session_id": agent.id}, payload={}))
    assert agent.state is AgentState.CANCELLED
    finishes = [
        e
        for e in core.event_log.query_session(agent.id)
        if e.type == "tool.finished" and e.data.get("tool_name") == "ask_user"
    ]
    assert finishes, "in-flight tool was never closed"
    assert finishes[-1].data["cancelled"] is True
    assert finishes[-1].data["is_success"] is False


@pytest.mark.asyncio
async def test_message_to_cancelled_agent_reopens_run():
    llm = FlakyLLM(
        [
            LLMResponse(
                content="",
                tool_calls=[ToolCall(id="t1", name="ask_user", arguments={"question": "hold on"})],
            ),
            LLMResponse(content="after cancel", stop_requested=True),
        ]
    )
    core, _, agent = await _setup(llm)
    await _wait_state(agent, AgentState.WAITING_INPUT)
    bus = CommandBus(core)
    await bus.execute(Command(type="agent.cancel", target={"session_id": agent.id}, payload={}))
    assert agent.state is AgentState.CANCELLED

    await bus.execute(
        Command(type="agent.message", target={"session_id": agent.id}, payload={"content": "come back"})
    )
    await _wait_state(agent, AgentState.SUCCEEDED)
    emitted = core.event_log.query_session(agent.id, types={"agent.message_emitted"})
    assert emitted[-1].data["content"] == "after cancel"


@pytest.mark.asyncio
async def test_non_transient_4xx_fails_fast_without_retry():
    """402/401 这类非瞬态错误不值得原地重试：直接 failed，0 次 run.retry。"""
    from cloudra.runtime_v2.agent_runner import _is_retryable

    class Http402(Exception):
        status_code = 402

    class Failing402LLM:
        async def complete(self, agent, messages, tools, **_kwargs):
            raise Http402("Insufficient Balance")

    assert _is_retryable(Http402("x")) is False
    assert _is_retryable(RuntimeError("boom")) is True

    core = RuntimeCore(strict_events=True)
    pipeline = TurnPipeline(
        event_log=core.event_log,
        stages=default_stages(),
        llm=Failing402LLM(),
        tools=LegacyToolExecutor(core),
    )
    core.runner = AgentRunner(core, pipeline, retry_backoff=(0.0, 0.0))
    bus = CommandBus(core)
    await bus.execute(Command(type="project.create", payload={"name": "no-retry"}))
    project = next(iter(core.projects.values()))
    result = await bus.execute(
        Command(
            type="agent.spawn",
            target={"project_id": project.id},
            payload={"role_id": "coordinator", "query": "go"},
        )
    )
    agent = result.data
    await _wait_state(agent, AgentState.FAILED)
    assert _retries(core, agent.id) == []
    finished = core.event_log.query_session(agent.id, types={"run.finished"})
    assert "Insufficient Balance" in (finished[-1].data.get("error") or "")
