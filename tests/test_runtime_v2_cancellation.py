"""Runtime-layer cancellation forensics (Task 0) + Task 5 fix regression.

Fake LLM providers + asyncio.Event latches; ``wait_for`` and poll deadlines
are failure upper bounds only.  Every test reaps its tasks in ``finally``.

Created RED at 2026-09-06 per
docs/superpowers/plans/2026-09-05-task0-cancellation-forensics.md; turned
green by the Task 5 fixes (registered background tasks + CANCELLED admission
checks + ``RuntimeCore.aclose()``).  2026-09-13（缓存连续性计划 Task 4）：
per-run 自动摘要/handover 管线（finalize）已删除——取消路径上不再有摘要
请求这一活动类别；取消语义由会话上下文投影承载（只记录真实进入过上下
文的消息）。
"""

from __future__ import annotations

import asyncio

import pytest

from cloudra.runtime_v2.agent_runner import AgentRunner
from cloudra.runtime_v2.commands import CommandBus
from cloudra.runtime_v2.core import RuntimeCore
from cloudra.runtime_v2.policies import default_stages
from cloudra.runtime_v2.policies.base import ToolCall
from cloudra.runtime_v2.schemas import AgentState, Command, InvocationProtocol
from cloudra.runtime_v2.turn_pipeline import LLMResponse, TurnPipeline


class EchoTools:
    async def execute(self, agent, call: ToolCall, **_kwargs):
        from cloudra.runtime_v2.policies.base import ToolResult

        return ToolResult(is_success=True, summary=f"echo:{call.arguments.get('x')}", data={})


async def _setup(llm, **runner_kwargs) -> tuple[RuntimeCore, object, object]:
    core = RuntimeCore(strict_events=True)
    pipeline = TurnPipeline(
        event_log=core.event_log,
        stages=default_stages(),
        llm=llm,
        tools=EchoTools(),
    )
    core.runner = AgentRunner(core, pipeline, **runner_kwargs)
    bus = CommandBus(core)
    await bus.execute(Command(type="project.create", payload={"name": "cancellation"}))
    project = next(iter(core.projects.values()))
    result = await bus.execute(
        Command(
            type="agent.spawn",
            target={"project_id": project.id},
            payload={"role_id": "coordinator", "query": "solve it"},
        )
    )
    agent = result.data
    # Scripted tool calls require the traditional protocol; the default
    # javascript protocol only admits js_exec + direct controls on the wire.
    agent.settings.invocation_protocol = InvocationProtocol.TRADITIONAL
    return core, project, agent


async def _wait_until(predicate, timeout: float = 5.0, what: str = "condition"):
    deadline = asyncio.get_running_loop().time() + timeout
    while not predicate():
        if asyncio.get_running_loop().time() > deadline:
            raise AssertionError(f"timed out waiting for {what}")
        await asyncio.sleep(0.01)


async def _wait_state(agent, state: AgentState, timeout: float = 5.0):
    await _wait_until(lambda: agent.state is state, timeout=timeout, what=f"state {state.value}")


class StopThenHangLLM:
    """Call 1 stops the run; later calls park until released (cancellable)."""

    def __init__(self) -> None:
        self.calls = 0
        self.second_entered = asyncio.Event()

    async def complete(self, agent, messages, tools, **_kwargs):
        self.calls += 1
        if self.calls == 1:
            return LLMResponse(content="first done", stop_requested=True)
        self.second_entered.set()
        await asyncio.Event().wait()  # hangs until the task is cancelled


@pytest.mark.asyncio
async def test_cancel_during_retry_backoff_stops_retries():
    """Guard (green today): cancelling inside the runner's retry backoff stops
    the retry loop; no further LLM call is made."""
    class AlwaysFailLLM:
        def __init__(self) -> None:
            self.calls = 0
            self.entered = asyncio.Event()

        async def complete(self, agent, messages, tools, **_kwargs):
            self.calls += 1
            self.entered.set()
            raise RuntimeError("transport boom")

    llm = AlwaysFailLLM()
    core, _, agent = await _setup(llm, retry_backoff=(30.0, 30.0))
    await asyncio.wait_for(llm.entered.wait(), timeout=5)
    await _wait_until(
        lambda: any(
            e.type == "run.retry" for e in core.event_log.query_session(agent.id)
        ),
        what="run.retry event",
    )
    # Backoff is 30s; we are deterministically inside it.
    await CommandBus(core).execute(
        Command(type="agent.cancel", target={"session_id": agent.id}, payload={})
    )
    assert agent.state is AgentState.CANCELLED
    assert llm.calls == 1
    assert core.runner._tasks.get(agent.id) is None
    retries = [
        e for e in core.event_log.query_session(agent.id) if e.type == "run.retry"
    ]
    assert len(retries) == 1


@pytest.mark.asyncio
async def test_cancel_during_compaction_stops_summary_request(monkeypatch):
    """Guard (expected green today): a manual compaction's summary call is
    awaited inside the runner task, so cancelling the agent interrupts it and
    no further compaction LLM request is made."""
    compact_gate = asyncio.Event()
    compact_calls = 0
    compact_entered = asyncio.Event()

    async def gated_summarize(agent, messages, **_kwargs):
        nonlocal compact_calls
        compact_calls += 1
        compact_entered.set()
        await compact_gate.wait()
        return "SUMMARY"

    monkeypatch.setattr(
        "cloudra.runtime_v2.compaction.summarize_with_agent_settings", gated_summarize
    )

    class GatedLLM:
        def __init__(self) -> None:
            self.gate = asyncio.Event()
            self.calls = 0

        async def complete(self, agent, messages, tools, **_kwargs):
            self.calls += 1
            if self.calls == 1:
                await self.gate.wait()
                return LLMResponse(
                    content="",
                    tool_calls=[ToolCall(id="tc1", name="echo", arguments={"x": 1})],
                )
            return LLMResponse(content="done", stop_requested=True)

    llm = GatedLLM()
    core, _, agent = await _setup(llm)
    try:
        await _wait_until(lambda: llm.calls == 1, what="first LLM call in flight")
        bus = CommandBus(core)
        await bus.execute(
            Command(
                type="agent.compact",
                target={"session_id": agent.id},
                payload={},
            )
        )
        llm.gate.set()
        await asyncio.wait_for(compact_entered.wait(), timeout=5)
        await bus.execute(
            Command(type="agent.cancel", target={"session_id": agent.id}, payload={})
        )
        assert agent.state is AgentState.CANCELLED
        assert compact_calls == 1
        compact_gate.set()
        await asyncio.sleep(0.05)
        assert compact_calls == 1, "compaction retried its LLM call after cancel"
    finally:
        llm.gate.set()
        compact_gate.set()


@pytest.mark.asyncio
async def test_core_aclose_cancels_runners_and_background_tasks():
    """``RuntimeCore.aclose()`` cancels every runner task and every registered
    background task; after it returns no new LLM request may fire.

    （Task 4 注：per-run 自动摘要/handover 的 finalize 管线已删除，取消路径
    上不再有摘要请求这一活动类别；本用例保 runner 任务的取消与准入停止。）
    """
    llm = StopThenHangLLM()
    core, _, agent = await _setup(llm)
    try:
        await _wait_state(agent, AgentState.SUCCEEDED)
        # Re-wake so run 2 parks in the LLM, then close the core.
        await CommandBus(core).execute(
            Command(
                type="agent.message",
                target={"session_id": agent.id},
                payload={"content": "again"},
            )
        )
        await asyncio.wait_for(llm.second_entered.wait(), timeout=5)
        await core.aclose()
        assert core.runner._tasks.get(agent.id) is None
        assert not core.runner._background.get(agent.id)
        deadline = asyncio.get_running_loop().time() + 0.3
        while asyncio.get_running_loop().time() < deadline:
            await asyncio.sleep(0.02)
        assert llm.calls == 2
    finally:
        runner_task = core.runner._tasks.get(agent.id)
        if runner_task is not None:
            runner_task.cancel()
            await asyncio.gather(runner_task, return_exceptions=True)
