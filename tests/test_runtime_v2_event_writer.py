"""Shared EventWriter: ordered write-ahead persistence + idempotent publication."""

from __future__ import annotations

import asyncio

import pytest

from cloudra.runtime_v2.commands import CommandBus
from cloudra.runtime_v2.core import RuntimeCore
from cloudra.runtime_v2.dispatcher import WakePolicy
from cloudra.runtime_v2.effects import EventDraft
from cloudra.runtime_v2.event_writer import EventWriter
from cloudra.runtime_v2.persistence import RuntimeStore
from cloudra.runtime_v2.schemas import Command


class RecordingStore:
    def __init__(self) -> None:
        self.types: list[str] = []

    def append_event(self, envelope) -> None:
        self.types.append(envelope.type)


class FailingStore:
    def append_event(self, envelope) -> None:
        raise RuntimeError("disk full")


def _request_draft(project_id: str = "p", session_id: str = "a") -> EventDraft:
    return EventDraft(
        "tool.requested",
        "agent",
        project_id,
        session_id,
        "run_1",
        {"tool_call_id": "tc1", "tool_name": "echo", "arguments_summary": {}},
    )


@pytest.mark.asyncio
async def test_unflushed_ancestors_precede_request_in_storage():
    core = RuntimeCore()  # no store attached: early events stay memory-only
    bus = CommandBus(core)
    await bus.execute(Command(type="project.create", payload={"name": "p"}))
    project = next(iter(core.projects.values()))
    await bus.execute(
        Command(type="agent.spawn", target={"project_id": project.id}, payload={"role_id": "coordinator"})
    )
    agent = next(iter(core.agents.values()))

    store = RecordingStore()
    core.store = store  # attach later; the writer must backfill in order
    envelope = await core.event_writer.commit(_request_draft(project.id, agent.id))

    expected = [e.type for e in core.event_log]
    assert store.types == expected
    assert store.types[-1] == "tool.requested"
    assert store.types.index("project.created") < store.types.index("tool.requested")
    assert envelope.type == "tool.requested"


@pytest.mark.asyncio
async def test_persistence_failure_propagates_before_publication():
    core = RuntimeCore()
    seen: list[str] = []

    async def subscriber(envelope) -> None:
        seen.append(envelope.type)

    core.event_hub.subscribe(subscriber)
    core.store = FailingStore()
    with pytest.raises(RuntimeError, match="disk full"):
        await core.event_writer.commit(_request_draft())
    assert seen == []
    assert [e.type for e in core.event_log] == []


@pytest.mark.asyncio
async def test_committed_event_survives_append_error_and_publishes_once(tmp_path):
    """A lost append acknowledgement must not turn a durable event into a retry."""

    class WriteThenRaiseStore(RuntimeStore):
        def append_event(self, envelope) -> None:
            super().append_event(envelope)
            raise RuntimeError("connection dropped after commit")

    core = RuntimeCore()
    store = WriteThenRaiseStore(tmp_path / "runtime.db")
    core.store = store
    seen: list[str] = []

    async def subscriber(envelope) -> None:
        seen.append(envelope.event_id)

    core.event_hub.subscribe(subscriber)
    envelope = await core.event_writer.commit(_request_draft())

    assert [row["event_id"] for row in store.events_after({})] == [envelope.event_id]
    assert [event.event_id for event in core.event_log] == [envelope.event_id]
    assert seen == [envelope.event_id]
    await core.event_writer.flush()
    assert seen == [envelope.event_id]


@pytest.mark.asyncio
async def test_commit_succeeds_when_later_event_fails_persistence(tmp_path):
    """A later failed tail must not keep a durable message out of the inbox."""

    class FailLaterStore(RuntimeStore):
        def append_event(self, envelope) -> None:
            if envelope.type == "agent.warning":
                raise RuntimeError("disk full")
            super().append_event(envelope)

    core = RuntimeCore()
    store = FailLaterStore(tmp_path / "runtime.db")
    core.store = store
    bus = CommandBus(core)
    project = (await bus.execute(Command(type="project.create", payload={"name": "p"}))).data
    agent = (
        await bus.execute(
            Command(
                type="agent.spawn",
                target={"project_id": project.id},
                payload={"role_id": "coordinator"},
            )
        )
    ).data
    seen: list[str] = []

    async def subscriber(envelope) -> None:
        seen.append(envelope.event_id)

    core.event_hub.subscribe(subscriber)
    async with core.event_writer._lock:
        committing = asyncio.create_task(
            core.dispatcher.commit_and_deliver(
                to_session_id=agent.id,
                project_id=project.id,
                content="peer call",
                sender="explorer",
                wake=WakePolicy.NEVER,
            )
        )
        await asyncio.sleep(0)
        own_event = list(core.event_log)[-1]
        assert own_event.type == "agent.message_injected"
        failed_tail = core.record(
            "agent.warning", stream="project", project_id=project.id, data={"message": "later"}
        )

    result = await committing
    assert result.event_id == own_event.event_id
    persisted_ids = [row["event_id"] for row in store.events_after({})]
    assert own_event.event_id in persisted_ids
    assert failed_tail.event_id not in persisted_ids
    assert core.event_log.get(failed_tail.event_id) is None
    assert seen == [own_event.event_id]
    inbox = core.mailbox.inbox(agent.id)
    assert inbox is not None
    assert inbox.get_nowait()["content"] == "peer call"
    assert inbox.empty()


class _FailOnTypeStore:
    def __init__(self, fail_type: str) -> None:
        self.types: list[str] = []
        self.fail_type = fail_type

    def append_event(self, envelope) -> None:
        if envelope.type == self.fail_type:
            raise RuntimeError("disk full")
        self.types.append(envelope.type)


@pytest.mark.asyncio
async def test_command_persist_failure_does_not_leave_unapplied_events():
    """flush 失败不得把事件留在内存日志里：否则下次 flush 会落库却从未 apply。"""
    from cloudra.runtime_v2.event_writer import EventPersistenceError

    core = RuntimeCore()
    core.store = FailingStore()
    bus = CommandBus(core)
    with pytest.raises(EventPersistenceError):
        await bus.execute(Command(type="project.create", payload={"name": "ghost"}))
    assert list(core.projects.values()) == []
    assert [e.type for e in core.event_log] == []


@pytest.mark.asyncio
async def test_command_applies_persisted_prefix_and_drops_failed_tail():
    from cloudra.runtime_v2.event_writer import EventPersistenceError

    core = RuntimeCore()
    store = _FailOnTypeStore("agent.spawned")
    core.store = store
    bus = CommandBus(core)
    await bus.execute(Command(type="project.create", payload={"name": "p"}))
    project = next(iter(core.projects.values()))
    before = [e.type for e in core.event_log]
    with pytest.raises(EventPersistenceError):
        await bus.execute(
            Command(
                type="agent.spawn",
                target={"project_id": project.id},
                payload={"role_id": "coordinator"},
            )
        )
    assert list(core.agents.values()) == []
    assert "agent.spawned" not in [e.type for e in core.event_log]
    assert "agent.spawned" not in store.types
    assert [e.type for e in core.event_log][: len(before)] == before


@pytest.mark.asyncio
async def test_command_retry_after_partial_persist_does_not_double_spawn():
    """spawned 已落盘、message_injected 失败时不得 500：返回已创建的 agent 并调度，
    同 command_id 重试不得再开一个。HTTP 用新 command_id 重试的前提是这次不再抛错。"""

    class _Runner:
        def __init__(self) -> None:
            self.scheduled: list[str] = []

        def schedule(self, session_id: str) -> None:
            self.scheduled.append(session_id)

    core = RuntimeCore()
    store = _FailOnTypeStore("agent.message_injected")
    core.store = store
    core.runner = _Runner()
    bus = CommandBus(core)
    await bus.execute(Command(type="project.create", payload={"name": "p"}))
    project = next(iter(core.projects.values()))
    command = Command(
        command_id="cmd-spawn-once",
        type="agent.spawn",
        target={"project_id": project.id},
        payload={"role_id": "coordinator", "query": "hello"},
    )
    first = await bus.execute(command)
    assert first.accepted is True
    assert len(core.agents) == 1
    agent_id = next(iter(core.agents))
    assert core.runner.scheduled == [agent_id]
    retried = await bus.execute(command)
    assert retried.accepted is True
    assert len(core.agents) == 1
    assert retried.data.id == first.data.id
    assert "agent.message_injected" not in [e.type for e in core.event_log]
    inbox = core.mailbox.inbox(agent_id)
    assert inbox is None or inbox.empty()


@pytest.mark.asyncio
async def test_nested_subscriber_commands_do_not_deadlock():
    core = RuntimeCore()
    bus = CommandBus(core)
    await bus.execute(Command(type="project.create", payload={"name": "p"}))
    project = next(iter(core.projects.values()))
    seen: list[str] = []
    fired = asyncio.Event()

    async def subscriber(envelope) -> None:
        seen.append(envelope.type)
        if envelope.type == "project.updated" and not fired.is_set():
            fired.set()
            # A subscriber submitting a command re-enters the writer while the
            # outer flush is still publishing; this must not deadlock and the
            # nested event must be delivered exactly once.
            await bus.execute(
                Command(
                    type="project.update",
                    target={"project_id": envelope.project_id},
                    payload={"archived": True},
                )
            )

    core.event_hub.subscribe(subscriber)
    await asyncio.wait_for(
        bus.execute(
            Command(type="project.update", target={"project_id": project.id}, payload={"name": "renamed"})
        ),
        timeout=5.0,
    )
    assert seen == ["project.updated", "project.updated"]


@pytest.mark.asyncio
async def test_mark_restored_skips_history_for_store_and_hub():
    core = RuntimeCore()
    bus = CommandBus(core)
    await bus.execute(Command(type="project.create", payload={"name": "p"}))
    core.event_writer.mark_restored()

    store = RecordingStore()
    core.store = store
    seen: list[str] = []

    async def subscriber(envelope) -> None:
        seen.append(envelope.type)

    core.event_hub.subscribe(subscriber)
    project = next(iter(core.projects.values()))
    await core.event_writer.commit(_request_draft(project.id))
    # History was marked restored: only the new event persists/publishes.
    assert store.types == ["tool.requested"]
    assert seen == ["tool.requested"]


@pytest.mark.asyncio
async def test_hub_publication_is_idempotent_by_event_id():
    core = RuntimeCore()
    seen: list[str] = []

    async def subscriber(envelope) -> None:
        seen.append(envelope.event_id)

    core.event_hub.subscribe(subscriber)
    envelope = core.record("agent.warning", stream="project", project_id="p", data={"message": "m"})
    await core.event_hub.publish(envelope)
    await core.event_hub.publish(envelope)
    assert seen == [envelope.event_id]


@pytest.mark.asyncio
async def test_event_writer_flush_is_shared_with_command_bus():
    core = RuntimeCore()
    store = RecordingStore()
    core.store = store
    bus = CommandBus(core)
    await bus.execute(Command(type="project.create", payload={"name": "p"}))
    assert store.types == ["project.created"]
    # Re-flushing is a no-op (the cursor makes repeat persistence free).
    await core.event_writer.flush()
    assert store.types == ["project.created"]


@pytest.mark.asyncio
async def test_standalone_writer_without_store_or_hub():
    from cloudra.runtime_v2.events import EventLog

    writer = EventWriter(EventLog())
    envelope = await writer.commit(_request_draft())
    assert envelope.type == "tool.requested"
    await writer.flush()


@pytest.mark.asyncio
async def test_context_broker_persist_failure_does_not_apply():
    from cloudra.runtime_v2.event_writer import EventPersistenceError

    core = RuntimeCore()
    bus = CommandBus(core)
    await bus.execute(Command(type="project.create", payload={"name": "p"}))
    project = next(iter(core.projects.values()))
    await bus.execute(
        Command(
            type="agent.spawn",
            target={"project_id": project.id},
            payload={"role_id": "coordinator"},
        )
    )
    agent = next(iter(core.agents.values()))
    before = list(core.contexts.current_messages(agent.id) or [])
    core.store = FailingStore()
    with pytest.raises(EventPersistenceError):
        await core.contexts.append_output(
            agent=agent,
            run_id="run_ghost",
            messages=[{"role": "assistant", "content": "ghost-output"}],
        )
    assert list(core.contexts.current_messages(agent.id) or []) == before
    assert not any(
        "ghost-output" in str(envelope.data) for envelope in core.event_log
    )


@pytest.mark.asyncio
async def test_start_run_persist_failure_leaves_queued():
    from cloudra.runtime_v2.event_writer import EventPersistenceError
    from cloudra.runtime_v2.schemas import AgentState

    core = RuntimeCore()
    bus = CommandBus(core)
    await bus.execute(Command(type="project.create", payload={"name": "p"}))
    project = next(iter(core.projects.values()))
    await bus.execute(
        Command(
            type="agent.spawn",
            target={"project_id": project.id},
            payload={"role_id": "coordinator"},
        )
    )
    agent = next(iter(core.agents.values()))
    core.store = FailingStore()
    with pytest.raises(EventPersistenceError):
        await core.agent_host.start_run(agent)
    assert agent.state is AgentState.QUEUED
    assert not any(envelope.type == "run.started" for envelope in core.event_log)


class RecordingRunner:
    def __init__(self) -> None:
        self.scheduled: list[str] = []

    def schedule(self, session_id: str) -> None:
        self.scheduled.append(session_id)


@pytest.mark.asyncio
async def test_wake_applies_and_schedules_committed_batch_when_later_write_fails(tmp_path, monkeypatch):
    """An unrelated failed tail cannot turn a durable wake into a lost effect."""
    from cloudra.runtime_v2.schemas import AgentState

    class FailLaterStore(RuntimeStore):
        def append_event(self, envelope) -> None:
            if envelope.type == "agent.warning":
                raise RuntimeError("unrelated tail failed")
            super().append_event(envelope)

    core = RuntimeCore()
    core.store = store = FailLaterStore(tmp_path / "runtime.db")
    bus = CommandBus(core)
    project = (await bus.execute(Command(type="project.create", payload={"name": "p"}))).data
    agent = (
        await bus.execute(
            Command(
                type="agent.spawn",
                target={"project_id": project.id},
                payload={"role_id": "coordinator"},
            )
        )
    ).data
    runner = RecordingRunner()
    seen: list[str] = []

    async def subscriber(envelope) -> None:
        assert await asyncio.to_thread(store.has_event, envelope.event_id)
        seen.append(envelope.event_id)
        # Recovery publication must release the writer lock and advance its
        # cursor before subscribers re-enter, just like a successful flush.
        await core.event_writer.flush()

    core.event_hub.subscribe(subscriber)
    before = len(core.event_log)
    original_flush = core.event_writer._flush_locked
    failed_tail = None
    wake_events = []

    async def append_later_tail():
        nonlocal failed_tail, wake_events
        if failed_tail is None:
            # The agent batch now appends only after acquiring the writer
            # lock. Inject a later concurrent tail before persistence captures
            # the prefix, preserving the original failure being reproduced.
            wake_events = list(core.event_log)[before:]
            assert [envelope.type for envelope in wake_events] == [
                "agent.state_changed", "run.started",
            ]
            failed_tail = core.record(
                "agent.warning", stream="project", project_id=project.id, data={"message": "later"},
            )
        return await original_flush()

    monkeypatch.setattr(core.event_writer, "_flush_locked", append_later_tail)
    await asyncio.wait_for(core.agent_host.wake(agent, runner=runner), timeout=5.0)

    assert agent.state is AgentState.RUNNING
    assert agent.current_run is not None
    assert agent.current_run.run_id == wake_events[-1].run_id
    assert runner.scheduled == [agent.id]
    assert seen == [envelope.event_id for envelope in wake_events]
    assert core.event_log.get(failed_tail.event_id) is None
    assert [row["event_id"] for row in store.events_after({})] == [
        envelope.event_id for envelope in core.event_log
    ]

    # A repeated wake/flush must neither start a duplicate run nor republish.
    await core.agent_host.wake(agent, runner=runner)
    await core.event_writer.flush()
    assert runner.scheduled == [agent.id]
    assert list(core.event_log)[before:] == wake_events
    assert seen == [envelope.event_id for envelope in wake_events]


@pytest.mark.asyncio
async def test_wake_applies_only_durable_prefix_and_does_not_schedule_partial_batch(tmp_path):
    """A partial own batch stays a non-retryable failure, with no speculative apply."""
    from cloudra.runtime_v2.event_writer import EventPersistenceError
    from cloudra.runtime_v2.schemas import AgentState

    class FailRunStartStore(RuntimeStore):
        def append_event(self, envelope) -> None:
            if envelope.type == "run.started":
                raise RuntimeError("run start failed")
            super().append_event(envelope)

    core = RuntimeCore()
    core.store = store = FailRunStartStore(tmp_path / "runtime.db")
    bus = CommandBus(core)
    project = (await bus.execute(Command(type="project.create", payload={"name": "p"}))).data
    agent = (
        await bus.execute(
            Command(
                type="agent.spawn",
                target={"project_id": project.id},
                payload={"role_id": "coordinator"},
            )
        )
    ).data
    runner = RecordingRunner()
    seen: list[str] = []

    async def subscriber(envelope) -> None:
        seen.append(envelope.event_id)

    core.event_hub.subscribe(subscriber)
    before = len(core.event_log)
    with pytest.raises(EventPersistenceError, match="run start failed"):
        await core.agent_host.wake(agent, runner=runner)

    durable_wake = list(core.event_log)[before:]
    assert [envelope.type for envelope in durable_wake] == ["agent.state_changed"]
    assert agent.state is AgentState.RUNNING
    assert agent.current_run is None
    assert runner.scheduled == []
    assert seen == [durable_wake[0].event_id]
    assert [row["event_id"] for row in store.events_after({})] == [
        envelope.event_id for envelope in core.event_log
    ]
    await core.event_writer.flush()
    assert list(core.event_log)[before:] == durable_wake
    assert seen == [durable_wake[0].event_id]
    assert runner.scheduled == []


@pytest.mark.asyncio
async def test_wake_persists_before_scheduling():
    """wake 落盘先于调度：落库失败既不推进状态，也不 schedule runner。"""
    from cloudra.runtime_v2.event_writer import EventPersistenceError
    from cloudra.runtime_v2.schemas import AgentState

    core = RuntimeCore()
    bus = CommandBus(core)
    project = (
        await bus.execute(Command(type="project.create", payload={"name": "p"}))
    ).data
    agent = (
        await bus.execute(
            Command(
                type="agent.spawn",
                target={"project_id": project.id},
                payload={"role_id": "coordinator"},
            )
        )
    ).data
    runner = RecordingRunner()

    # 正常路径：先落盘，再调度。
    await core.agent_host.wake(agent, runner=runner)
    assert runner.scheduled == [agent.id]
    assert agent.state is AgentState.RUNNING

    # 落库失败：状态不推进、日志不新增、绝不调度。
    runs_before = [
        envelope
        for envelope in core.event_log
        if envelope.type == "run.started" and envelope.session_id == agent.id
    ]
    core.store = FailingStore()
    live = core.agents[agent.id]
    live.state = AgentState.QUEUED
    live.current_run = None
    runner.scheduled.clear()
    with pytest.raises(EventPersistenceError):
        await core.agent_host.wake(live, runner=runner)
    assert runner.scheduled == []
    assert live.state is AgentState.QUEUED
    runs_after = [
        envelope
        for envelope in core.event_log
        if envelope.type == "run.started" and envelope.session_id == agent.id
    ]
    assert runs_after == runs_before


@pytest.mark.asyncio
async def test_transition_persist_failure_does_not_apply_or_keep_the_draft():
    """transition 落库失败时既不投影状态，也不把草稿留在内存日志里。"""
    from cloudra.runtime_v2.event_writer import EventPersistenceError
    from cloudra.runtime_v2.schemas import AgentState

    core = RuntimeCore()
    core.store = RecordingStore()
    bus = CommandBus(core)
    project = (
        await bus.execute(Command(type="project.create", payload={"name": "p"}))
    ).data
    agent = (
        await bus.execute(
            Command(
                type="agent.spawn",
                target={"project_id": project.id},
                payload={"role_id": "coordinator"},
            )
        )
    ).data
    run_id = await core.agent_host.start_run(agent)
    assert agent.state is AgentState.RUNNING

    core.store = FailingStore()
    with pytest.raises(EventPersistenceError):
        await core.agent_host.transition(
            agent, AgentState.WAITING_APPROVAL, reason="wait_review", run_id=run_id
        )
    assert agent.state is AgentState.RUNNING
    assert not any(
        envelope.type == "agent.state_changed"
        and envelope.data.get("to") == AgentState.WAITING_APPROVAL.value
        for envelope in core.event_log
    )


def test_persisted_watermarks_ignore_unpersisted_tail():
    from cloudra.runtime_v2.events import EventLog

    log = EventLog(strict=True)
    writer = EventWriter(log, store_provider=lambda: None)
    first = log.append(
        "agent.warning",
        stream="agent",
        project_id="p1",
        data={"message": "kept"},
    )
    writer.mark_restored()
    second = log.append(
        "agent.warning",
        stream="agent",
        project_id="p1",
        data={"message": "tail"},
    )
    assert log.high_watermarks["p1"] == second.seq
    assert writer.persisted_watermarks()["p1"] == first.seq


@pytest.mark.asyncio
@pytest.mark.parametrize('fail', [False, True])
async def test_cancellation_during_text_persistence_cannot_publish_unprojected_output(tmp_path, fail):
    import threading

    from cloudra.runtime_v2.event_writer import EventPersistenceError
    from cloudra.runtime_v2.persistence import restore_core

    core = RuntimeCore(strict_events=True)
    bus = CommandBus(core)
    project = (await bus.execute(Command(type='project.create', payload={'name': 'text-cancel'}))).data
    agent = (await bus.execute(Command(type='agent.spawn', target={'project_id': project.id},
                                      payload={'role_id': 'coordinator'}))).data
    store = await asyncio.to_thread(RuntimeStore, tmp_path / 'text-cancel.db')
    entered = threading.Event()
    release = threading.Event()
    original_append = store.append_event

    def append_with_barrier(event):
        if event.type == 'agent.message_emitted':
            entered.set()
            if not release.wait(timeout=5):
                raise AssertionError('text persistence barrier was not released')
            if fail:
                raise OSError('text write failed')
        return original_append(event)

    store.append_event = append_with_barrier
    core.store = store
    visible = []
    observed_contexts = []

    async def observe(event):
        if event.type == 'agent.message_emitted':
            visible.append(event.data['content'])
            observed_contexts.append([m['content'] for m in core.contexts.current_messages(agent.id)])

    core.event_hub.subscribe(observe)
    task = asyncio.create_task(core.contexts.emit_assistant(
        agent=agent, run_id='text-run', content='committed-cancellation-marker',
    ))
    try:
        assert await asyncio.to_thread(entered.wait, 5)
        task.cancel()
        await asyncio.sleep(0)
        release.set()
        with pytest.raises((asyncio.CancelledError, EventPersistenceError)):
            await task
        await core.event_writer.flush()
        expected = [] if fail else ['committed-cancellation-marker']
        assert visible == expected
        assert observed_contexts == ([] if fail else [expected])
        assert [m['content'] for m in core.contexts.current_messages(agent.id)] == expected
        restored = RuntimeCore(strict_events=True)
        await asyncio.to_thread(restore_core, restored, store)
        assert restored.contexts.current_messages(agent.id) == core.contexts.current_messages(agent.id)
    finally:
        release.set()
        await asyncio.gather(task, return_exceptions=True)
