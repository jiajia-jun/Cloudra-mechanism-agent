"""Shared EventWriter: ordered write-ahead persistence + idempotent publication."""

from __future__ import annotations

import asyncio

import pytest

from cloudra.runtime_v2.commands import CommandBus
from cloudra.runtime_v2.core import RuntimeCore
from cloudra.runtime_v2.effects import EventDraft
from cloudra.runtime_v2.event_writer import EventWriter
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
