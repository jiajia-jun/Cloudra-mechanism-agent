"""Runtime-layer cancellation forensics (Task 0) + Task 5 fix regression.

Fake LLM providers + asyncio.Event latches; ``wait_for`` and poll deadlines
are failure upper bounds only.  Every test reaps its tasks in ``finally``.

Created RED at 2026-09-06 per
docs/superpowers/plans/2026-09-05-task0-cancellation-forensics.md; turned
green by the Task 5 fixes:
- ``_schedule_run_finalize`` registers via ``AgentRunner.track_background``;
  ``cancel()`` cancels and awaits the session's run + background tasks;
- ``_finalize_run_context`` skips the LLM summary when the agent is already
  CANCELLED (admission check for the armed-but-not-started window);
- ``RuntimeCore.aclose()`` cancels everything and reaps JS hosts.
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


def _finalize_tasks(agent_id: str) -> list[asyncio.Task]:
    return [
        task
        for task in asyncio.all_tasks()
        if task.get_name() == f"finalize:{agent_id}" and not task.done()
    ]


class GatedSummarizer:
    """Counts calls; can park the first call on a latch."""

    def __init__(self, gate: asyncio.Event | None = None) -> None:
        self.calls = 0
        self.entered = asyncio.Event()
        self.gate = gate

    async def __call__(self, messages, **_kwargs):
        self.calls += 1
        self.entered.set()
        if self.gate is not None:
            await self.gate.wait()
        return "[RUN LOG]\ntrajectory\n[HANDOVER]\nstate"


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
async def test_cancel_cancels_inflight_finalize_summary():
    """A succeeded run's detached finalize is mid-summary when the user
    cancels the (re-woken) agent.  Stop semantics require the cancel to also
    cancel that background task.  RED today: the finalize task is a bare
    asyncio.create_task with no registry entry, so it survives."""
    gate = asyncio.Event()
    summarizer = GatedSummarizer(gate=gate)
    llm = StopThenHangLLM()
    core, _, agent = await _setup(llm, run_summarizer=summarizer)
    try:
        await _wait_state(agent, AgentState.SUCCEEDED)
        await asyncio.wait_for(summarizer.entered.wait(), timeout=5)
        # Re-wake so the agent is cancellable, then park run 2 in the LLM.
        await CommandBus(core).execute(
            Command(
                type="agent.message",
                target={"session_id": agent.id},
                payload={"content": "again"},
            )
        )
        await asyncio.wait_for(llm.second_entered.wait(), timeout=5)
        await CommandBus(core).execute(
            Command(type="agent.cancel", target={"session_id": agent.id}, payload={})
        )
        assert agent.state is AgentState.CANCELLED
        survivors = _finalize_tasks(agent.id)
        assert not survivors, (
            "detached finalize task survived user cancel "
            f"({len(survivors)} still pending); it must be registered and "
            "cancelled with the session's execution"
        )
        assert summarizer.calls == 1
    finally:
        gate.set()
        for task in _finalize_tasks(agent.id):
            task.cancel()
        await asyncio.gather(*_finalize_tasks(agent.id), return_exceptions=True)


@pytest.mark.asyncio
async def test_cancel_before_finalize_starts_blocks_summary_request():
    """The finalize is armed (scheduled) but has not reached its LLM call when
    the user cancels.  After cancel completes, releasing the latch must not
    produce a new summary request.  RED today: the detached task proceeds and
    fires the LLM summary after the cancel."""
    arm_gate = asyncio.Event()
    summarizer = GatedSummarizer()
    llm = StopThenHangLLM()
    core, _, agent = await _setup(llm, run_summarizer=summarizer)
    runner = core.runner
    original_schedule = runner._schedule_run_finalize

    def gated_schedule(agent, run_id, history, seed_count, *, outcome):
        if outcome != "succeeded":
            return original_schedule(
                agent, run_id, history, seed_count, outcome=outcome
            )

        async def gated_finalize():
            await arm_gate.wait()
            await runner._finalize_run_context(
                agent, run_id, history, seed_count, outcome=outcome
            )

        asyncio.create_task(gated_finalize(), name=f"finalize:{agent.id}")

    runner._schedule_run_finalize = gated_schedule
    try:
        await _wait_state(agent, AgentState.SUCCEEDED)
        assert summarizer.calls == 0  # armed but gated before the LLM call
        await CommandBus(core).execute(
            Command(
                type="agent.message",
                target={"session_id": agent.id},
                payload={"content": "again"},
            )
        )
        await asyncio.wait_for(llm.second_entered.wait(), timeout=5)
        await CommandBus(core).execute(
            Command(type="agent.cancel", target={"session_id": agent.id}, payload={})
        )
        assert agent.state is AgentState.CANCELLED
        arm_gate.set()
        await _wait_until(
            lambda: not _finalize_tasks(agent.id),
            what="finalize task to settle",
        )
        assert summarizer.calls == 0, (
            "finalize scheduled before the cancel fired a new LLM summary "
            "request after the agent was cancelled"
        )
    finally:
        arm_gate.set()
        for task in _finalize_tasks(agent.id):
            task.cancel()
        await asyncio.gather(*_finalize_tasks(agent.id), return_exceptions=True)


@pytest.mark.asyncio
async def test_cancelled_run_finalize_uses_deterministic_fallback():
    """Guard (green today): a cancelled run's finalize must not make any LLM
    summary call — it degrades to the deterministic event-derived summary."""
    summarizer = GatedSummarizer()

    class FirstCallHangs:
        def __init__(self) -> None:
            self.entered = asyncio.Event()

        async def complete(self, agent, messages, tools, **_kwargs):
            self.entered.set()
            await asyncio.Event().wait()

    hanging = FirstCallHangs()
    core, _, agent = await _setup(hanging, run_summarizer=summarizer)
    await asyncio.wait_for(hanging.entered.wait(), timeout=5)
    await CommandBus(core).execute(
        Command(type="agent.cancel", target={"session_id": agent.id}, payload={})
    )
    assert agent.state is AgentState.CANCELLED
    await _wait_until(
        lambda: any(
            e.type == "context.run_summarized"
            for e in core.event_log.query_session(agent.id)
        ),
        what="cancelled finalize to record its deterministic summary",
    )
    summarized = [
        e
        for e in core.event_log.query_session(agent.id)
        if e.type == "context.run_summarized"
    ]
    assert summarized[-1].data["outcome"] == "cancelled"
    assert summarized[-1].data["fallback"] is True
    assert summarizer.calls == 0


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
    core, _, agent = await _setup(llm, run_summarizer=GatedSummarizer())
    try:
        await _wait_until(lambda: llm.calls == 1, what="first LLM call in flight")
        bus = CommandBus(core)
        await bus.execute(
            Command(
                type="agent.compact",
                target={"session_id": agent.id},
                payload={"keep_recent": 1},
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
        await _wait_until(
            lambda: not _finalize_tasks(agent.id),
            what="post-cancel finalize to settle",
        )
        assert compact_calls == 1, "compaction retried its LLM call after cancel"
    finally:
        llm.gate.set()
        compact_gate.set()
        for task in _finalize_tasks(agent.id):
            task.cancel()
        await asyncio.gather(*_finalize_tasks(agent.id), return_exceptions=True)


@pytest.mark.asyncio
async def test_core_aclose_cancels_runners_and_finalizes():
    """Planned Task 5 shutdown entry point: ``RuntimeCore.aclose()`` must
    cancel every runner task and every registered background (finalize) task,
    after which no new LLM request may fire.  RED today with AttributeError —
    the entry point does not exist yet."""
    gate = asyncio.Event()
    summarizer = GatedSummarizer(gate=gate)
    llm = StopThenHangLLM()
    core, _, agent = await _setup(llm, run_summarizer=summarizer)
    try:
        await _wait_state(agent, AgentState.SUCCEEDED)
        await asyncio.wait_for(summarizer.entered.wait(), timeout=5)
        await CommandBus(core).execute(
            Command(
                type="agent.message",
                target={"session_id": agent.id},
                payload={"content": "again"},
            )
        )
        await asyncio.wait_for(llm.second_entered.wait(), timeout=5)
        await core.aclose()  # Task 5 API; AttributeError today (expected RED)
        assert core.runner._tasks.get(agent.id) is None
        assert not _finalize_tasks(agent.id)
        gate.set()
        deadline = asyncio.get_running_loop().time() + 0.3
        while asyncio.get_running_loop().time() < deadline:
            await asyncio.sleep(0.02)
        assert summarizer.calls == 1
        assert llm.calls == 2
    finally:
        gate.set()
        for task in _finalize_tasks(agent.id):
            task.cancel()
        await asyncio.gather(*_finalize_tasks(agent.id), return_exceptions=True)
        runner_task = core.runner._tasks.get(agent.id)
        if runner_task is not None:
            runner_task.cancel()
            await asyncio.gather(runner_task, return_exceptions=True)
