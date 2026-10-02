"""Single event-driven tool invocation lifecycle (InvocationService)."""

from __future__ import annotations

import asyncio

import pytest

from cloudra.runtime_v2.core import RuntimeCore
from cloudra.runtime_v2.event_writer import EventPersistenceError, EventWriter
from cloudra.runtime_v2.invocation import InvocationService
from cloudra.runtime_v2.invocation_types import InvocationError
from cloudra.runtime_v2.policies.base import (
    PipelineContext,
    PolicyResult,
    ToolCall,
    ToolResult,
)
from cloudra.runtime_v2.schemas import (
    AgentCapabilities,
    AgentSession,
    PermissionSet,
    RuntimeSettings,
)


def _ctx(agent: AgentSession, *, tools=None) -> PipelineContext:
    caps = AgentCapabilities(permissions=PermissionSet(read=True), tools=tools or ["echo"])
    return PipelineContext(
        agent=agent,
        run_id="r",
        settings_snapshot=RuntimeSettings(),
        capabilities=caps,
        inbox_messages=[],
        emit=lambda *args: None,
    )


def _agent() -> AgentSession:
    return AgentSession(id="a", project_id="p", role_id="explorer", display_name="explorer")


class RecordingStore:
    def __init__(self, fail_on: set[str] | None = None) -> None:
        self.observations: list[str] = []
        self.fail_on = fail_on or set()

    def append_event(self, event) -> None:
        if event.type in self.fail_on:
            raise RuntimeError("disk full")
        self.observations.append(event.type)


class Executor:
    def __init__(self, result: ToolResult | None = None, observations: list[str] | None = None) -> None:
        self.result = result or ToolResult(True, "ok", {"value": 7})
        self.observations = observations if observations is not None else []
        self.calls = 0

    async def execute(self, agent, call):
        self.calls += 1
        if self.observations:
            assert "tool.requested" in self.observations
            assert "tool.started" in self.observations
        return self.result


def _service(core: RuntimeCore, store: RecordingStore, stages=None, tools=None):
    writer = EventWriter(core.event_log, store_provider=lambda: store)
    return InvocationService(event_writer=writer, stages=stages or [], tools=tools), writer


def _finished(core: RuntimeCore) -> list:
    return [e for e in core.event_log if e.type == "tool.finished"]


@pytest.mark.asyncio
async def test_progress_is_durable_live_and_scoped_to_parallel_invocations():
    from cloudra.runtime_v2 import invocation_context, schemas

    core = RuntimeCore(strict_events=True)
    store = RecordingStore()
    received = []
    gate = asyncio.Event()

    class ReportingExecutor:
        async def execute(self, agent, call):
            await invocation_context.report_tool_progress(schemas.ToolProgress(
                phase="executing", message=call.id,
                effective_arguments={"value": call.id},
            ))
            if call.id == "first":
                gate.set()
                await asyncio.sleep(0)
            else:
                await gate.wait()
            return ToolResult(True, call.id)

    async def observe(event):
        if event.type == "tool.progress":
            assert "tool.progress" in store.observations
            received.append(event)

    core.event_hub.subscribe(observe)
    writer = EventWriter(core.event_log, core.event_hub, store_provider=lambda: store)
    service = InvocationService(event_writer=writer, stages=[], tools=ReportingExecutor())
    await asyncio.gather(*(
        service.invoke(_ctx(_agent()), ToolCall(cid, "echo", {}), execution_id="js1")
        for cid in ["first", "second"]
    ))
    assert len(received) == 2
    assert {e.data["tool_call_id"] for e in received} == {"first", "second"}
    for event in received:
        assert event.data["message"] == event.data["tool_call_id"]
        assert event.data["execution_id"] == "js1"
        req = core.event_log.get(event.data["request_event_id"])
        assert req.type == "tool.requested"
        assert req.data["tool_call_id"] == event.data["tool_call_id"]
    assert invocation_context.current_invocation_scope() is None


def test_progress_rejects_fabricated_or_invalid_structured_values():
    from pydantic import ValidationError

    from cloudra.runtime_v2 import schemas

    for payload in [
        {"phase": "invented"}, {"phase": "executing", "compute_job_ids": [True]},
        {"phase": "executing", "compute_job_ids": [-1]},
        {"phase": "executing", "percent": 50},
    ]:
        with pytest.raises(ValidationError):
            schemas.ToolProgress.model_validate(payload)


@pytest.mark.asyncio
async def test_progress_persistence_failure_is_not_a_retryable_tool_failure():
    from cloudra.runtime_v2.invocation_context import report_tool_progress
    from cloudra.runtime_v2.schemas import ToolProgress

    class ReportingExecutor:
        async def execute(self, agent, call):
            await report_tool_progress(ToolProgress(phase="executing"))
            pytest.fail("must stop after failed durable progress")

    core = RuntimeCore(strict_events=True)
    service, _ = _service(core, RecordingStore(fail_on={"tool.progress"}), tools=ReportingExecutor())
    with pytest.raises(EventPersistenceError):
        await service.invoke(_ctx(_agent()), ToolCall("call", "echo", {}))


@pytest.mark.asyncio
async def test_effect_waits_for_durable_request():
    core = RuntimeCore(strict_events=True)
    agent = _agent()
    ctx = _ctx(agent)
    store = RecordingStore()
    service, _ = _service(core, store, tools=Executor(observations=store.observations))
    outcome = await service.invoke(ctx, ToolCall("tc1", "echo", {}))
    assert outcome.result.data == {"value": 7}
    assert store.observations == ["tool.requested", "tool.started", "tool.result_recorded", "tool.finished"]


@pytest.mark.asyncio
async def test_arguments_and_raw_result_are_detached():
    core = RuntimeCore(strict_events=True)
    agent = _agent()
    ctx = _ctx(agent)
    store = RecordingStore()
    result = ToolResult(True, "ok", {"value": 7})
    service, _ = _service(core, store, tools=Executor(result))
    call = ToolCall("tc1", "echo", {"nested": {"x": 1}})
    outcome = await service.invoke(ctx, call)
    # Mutating caller-side objects must not rewrite stored events.
    call.arguments["nested"]["x"] = 999
    outcome.result.data["value"] = 999
    requested = next(e for e in core.event_log if e.type == "tool.requested")
    recorded = next(e for e in core.event_log if e.type == "tool.result_recorded")
    assert requested.data["arguments_summary"] == {"nested": {"x": 1}}
    assert recorded.data["result"]["data"] == {"value": 7}
    assert outcome.raw_result_event_id == recorded.event_id
    finished = _finished(core)
    assert len(finished) == 1
    assert finished[0].data["status"] == "completed"
    assert finished[0].data["effect_state"] == "completed"
    assert finished[0].data["raw_result_event_id"] == recorded.event_id


@pytest.mark.asyncio
async def test_invalid_call_envelope_is_rejected_without_side_effects():
    core = RuntimeCore(strict_events=True)
    service, _ = _service(core, RecordingStore(), tools=Executor())
    ctx = _ctx(_agent())
    with pytest.raises(ValueError):
        await service.invoke(ctx, ToolCall("", "echo", {}))
    with pytest.raises(ValueError):
        await service.invoke(ctx, ToolCall("tc1", "", {}))
    with pytest.raises(ValueError):
        await service.invoke(ctx, ToolCall("tc1", "echo", ["not", "a", "dict"]))
    with pytest.raises(ValueError):
        await service.invoke(ctx, ToolCall("tc1", "echo", {"x": float("nan")}))
    assert list(core.event_log) == []


class _BlockStage:
    name = "blocker"

    async def before_tool(self, ctx, call):
        return PolicyResult.block("no way")


class _AskStage:
    name = "asker"

    async def before_tool(self, ctx, call):
        return PolicyResult.ask("confirm?")


class _WarnStage:
    name = "warner"

    async def before_tool(self, ctx, call):
        return PolicyResult.warn("careful")

    async def after_tool(self, ctx, call, result):
        return None


@pytest.mark.asyncio
async def test_policy_block_never_executes_and_has_single_terminal():
    core = RuntimeCore(strict_events=True)
    store = RecordingStore()
    executor = Executor()
    service, _ = _service(core, store, stages=[_BlockStage()], tools=executor)
    outcome = await service.invoke(_ctx(_agent()), ToolCall("tc1", "echo", {}))
    assert executor.calls == 0
    assert outcome.decision == "continue"
    assert outcome.error.code == "policy_blocked"
    assert outcome.error.stage == "blocker"
    assert outcome.error.effect_state == "not_started"
    assert store.observations == ["tool.requested", "tool.blocked", "tool.finished"]
    finished = _finished(core)[-1]
    assert finished.data["status"] == "blocked"
    assert finished.data["effect_state"] == "not_started"
    assert finished.data["is_success"] is False


@pytest.mark.asyncio
async def test_policy_ask_returns_wait_approval_without_execution():
    core = RuntimeCore(strict_events=True)
    store = RecordingStore()
    executor = Executor()
    service, _ = _service(core, store, stages=[_AskStage()], tools=executor)
    outcome = await service.invoke(_ctx(_agent()), ToolCall("tc1", "echo", {}))
    assert executor.calls == 0
    assert outcome.decision == "wait_approval"
    assert outcome.error.code == "policy_wait"
    assert store.observations == ["tool.requested", "tool.approval_requested", "tool.finished"]
    finished = _finished(core)[-1]
    assert finished.data["status"] == "waiting"
    assert finished.data["effect_state"] == "not_started"


@pytest.mark.asyncio
async def test_business_failure_is_completed_not_an_exception():
    core = RuntimeCore(strict_events=True)
    store = RecordingStore()
    service, _ = _service(core, store, tools=Executor(ToolResult(False, "bad input", {"err": 1})))
    outcome = await service.invoke(_ctx(_agent()), ToolCall("tc1", "echo", {}))
    assert outcome.error is None
    assert outcome.result.is_success is False
    finished = _finished(core)[-1]
    assert finished.data["status"] == "failed"
    assert finished.data["effect_state"] == "completed"
    assert finished.data["error"] is None


@pytest.mark.asyncio
async def test_executor_exception_is_terminal_unknown_not_raised():
    core = RuntimeCore(strict_events=True)
    store = RecordingStore()

    class Crashing:
        async def execute(self, agent, call):
            raise RuntimeError("boom")

    service, _ = _service(core, store, tools=Crashing())
    outcome = await service.invoke(_ctx(_agent()), ToolCall("tc1", "echo", {}))
    assert outcome.error.code == "tool_exception"
    assert outcome.error.effect_state == "unknown"
    assert outcome.result is not None and outcome.result.is_success is False
    assert store.observations == ["tool.requested", "tool.started", "tool.finished"]
    finished = _finished(core)[-1]
    assert finished.data["status"] == "failed"
    assert finished.data["effect_state"] == "unknown"
    assert finished.data["error"]["code"] == "tool_exception"


@pytest.mark.asyncio
async def test_executor_error_metadata_becomes_terminal_unknown():
    core = RuntimeCore(strict_events=True)
    store = RecordingStore()
    result = ToolResult(
        False,
        "kaput",
        error=InvocationError(code="tool_exception", message="kaput", effect_state="unknown"),
    )
    service, _ = _service(core, store, tools=Executor(result))
    outcome = await service.invoke(_ctx(_agent()), ToolCall("tc1", "echo", {}))
    assert outcome.error.code == "tool_exception"
    assert store.observations == ["tool.requested", "tool.started", "tool.finished"]


@pytest.mark.asyncio
async def test_after_tool_failure_keeps_raw_result_reference():
    core = RuntimeCore(strict_events=True)
    store = RecordingStore()

    class BadAfter:
        name = "bad_after"

        async def before_tool(self, ctx, call):
            return PolicyResult.allow()

        async def after_tool(self, ctx, call, result):
            raise RuntimeError("hook exploded")

    service, _ = _service(core, store, stages=[BadAfter()], tools=Executor())
    outcome = await service.invoke(_ctx(_agent()), ToolCall("tc1", "echo", {}))
    assert outcome.error.code == "postprocessing_failed"
    assert outcome.error.effect_state == "completed"
    assert outcome.raw_result_event_id is not None
    assert store.observations == ["tool.requested", "tool.started", "tool.result_recorded", "tool.finished"]
    finished = _finished(core)[-1]
    assert finished.data["status"] == "failed"
    assert finished.data["effect_state"] == "completed"
    assert finished.data["error"]["code"] == "postprocessing_failed"
    assert finished.data["raw_result_event_id"] == outcome.raw_result_event_id


@pytest.mark.asyncio
async def test_cancellation_commits_terminal_and_reraises():
    core = RuntimeCore(strict_events=True)
    store = RecordingStore()

    class Hanging:
        async def execute(self, agent, call):
            raise asyncio.CancelledError()

    service, _ = _service(core, store, tools=Hanging())
    with pytest.raises(asyncio.CancelledError):
        await service.invoke(_ctx(_agent()), ToolCall("tc1", "echo", {}))
    finished = _finished(core)[-1]
    assert finished.data["status"] == "cancelled"
    assert finished.data["effect_state"] == "unknown"


@pytest.mark.asyncio
async def test_store_failure_before_execution_blocks_the_effect():
    core = RuntimeCore(strict_events=True)
    store = RecordingStore(fail_on={"tool.requested"})
    executor = Executor()
    service, _ = _service(core, store, tools=executor)
    with pytest.raises(EventPersistenceError):
        await service.invoke(_ctx(_agent()), ToolCall("tc1", "echo", {}))
    assert executor.calls == 0


@pytest.mark.asyncio
async def test_store_failure_after_raw_execution_stops_dispatch():
    core = RuntimeCore(strict_events=True)
    store = RecordingStore(fail_on={"tool.result_recorded"})
    executor = Executor()
    service, _ = _service(core, store, tools=executor)
    with pytest.raises(EventPersistenceError):
        await service.invoke(_ctx(_agent()), ToolCall("tc1", "echo", {}))
    # The external effect already happened; nothing may fabricate a terminal
    # success after the unaudited gap.
    assert executor.calls == 1
    assert _finished(core) == []


@pytest.mark.asyncio
async def test_queued_invocations_serialize():
    core = RuntimeCore(strict_events=True)
    store = RecordingStore()
    order: list[str] = []
    midway = asyncio.Event()

    class Slow:
        async def execute(self, agent, call):
            order.append(f"enter:{call.id}")
            if call.id == "tc1":
                midway.set()
            await asyncio.sleep(0)
            order.append(f"exit:{call.id}")
            return ToolResult(True, "ok", {})

    service, _ = _service(core, store, tools=Slow())
    ctx = _ctx(_agent())
    first = asyncio.create_task(service.invoke(ctx, ToolCall("tc1", "echo", {})))
    await midway.wait()
    second = asyncio.create_task(service.invoke(ctx, ToolCall("tc2", "echo", {})))
    await asyncio.gather(first, second)
    assert order == ["enter:tc1", "exit:tc1", "enter:tc2", "exit:tc2"]
    types = [e.type for e in core.event_log]
    assert types == [
        "tool.requested",
        "tool.started",
        "tool.result_recorded",
        "tool.finished",
        "tool.requested",
        "tool.started",
        "tool.result_recorded",
        "tool.finished",
    ]


@pytest.mark.asyncio
async def test_warn_stage_emits_warning_but_continues():
    core = RuntimeCore(strict_events=True)
    store = RecordingStore()
    emitted: list[tuple] = []
    agent = _agent()
    caps = AgentCapabilities(permissions=PermissionSet(read=True), tools=["echo"])
    ctx = PipelineContext(
        agent=agent,
        run_id="r",
        settings_snapshot=RuntimeSettings(),
        capabilities=caps,
        inbox_messages=[],
        emit=lambda *args: emitted.append(args),
    )
    service, _ = _service(core, store, stages=[_WarnStage()], tools=Executor())
    outcome = await service.invoke(ctx, ToolCall("tc1", "echo", {}))
    assert outcome.error is None
    assert emitted and emitted[0][0] == "agent.warning"
