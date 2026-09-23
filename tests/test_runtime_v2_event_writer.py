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
async def test_start_run_durable_persist_failure_leaves_queued():
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
        await core.agent_host.start_run_durable(agent)
    assert agent.state is AgentState.QUEUED
    assert not any(envelope.type == "run.started" for envelope in core.event_log)


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
