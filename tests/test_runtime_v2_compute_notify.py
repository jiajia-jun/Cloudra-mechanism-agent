"""Compute job IPC notifications -> agent.message (v2 native path)."""

from __future__ import annotations

import pytest

from cloudra.runtime_v2.commands import CommandBus
from cloudra.runtime_v2.compute_notify import ComputeNotifyBroker
from cloudra.runtime_v2.core import RuntimeCore
from cloudra.runtime_v2.schemas import Command


async def _setup_core():
    core = RuntimeCore(strict_events=True)
    bus = CommandBus(core)
    await bus.execute(Command(type="project.create", payload={"name": "compute"}))
    project = next(iter(core.projects.values()))
    result = await bus.execute(
        Command(
            type="agent.spawn",
            target={"project_id": project.id},
            payload={"role_id": "coordinator"},
        )
    )
    coordinator = result.data
    # Drain spawn query-less inbox noise if any.
    inbox = core.mailbox.inbox(coordinator.id)
    if inbox is not None:
        while not inbox.empty():
            inbox.get_nowait()
    return core, project, coordinator


def _inbox_texts(core, session_id: str) -> list[str]:
    inbox = core.mailbox.inbox(session_id)
    texts = []
    if inbox is not None:
        while not inbox.empty():
            texts.append(str(inbox.get_nowait().get("content", "")))
    return texts


@pytest.mark.asyncio
async def test_compute_notify_delivers_agent_message():
    core, project, coordinator = await _setup_core()
    broker = ComputeNotifyBroker(core)

    await broker._deliver(
        project.id,
        {
            "kind": "task_finished",
            "task_kind": "compute",
            "task_id": 42,
            "state": "done",
            "content": "Compute job task_id=42 finished, state=done.",
            "session_id": coordinator.id,
            "notify_coordinator": False,
        },
    )

    events = core.event_log.query_session(
        coordinator.id, types={"agent.message_injected"}
    )
    assert len(events) == 1
    assert "task_id=42" in events[0].data["content"]
    texts = _inbox_texts(core, coordinator.id)
    assert any("task_id=42" in t for t in texts)


@pytest.mark.asyncio
async def test_compute_notify_dedupes_same_terminal_event():
    core, project, coordinator = await _setup_core()
    broker = ComputeNotifyBroker(core)
    payload = {
        "kind": "task_finished",
        "task_kind": "compute",
        "task_id": 7,
        "state": "failed",
        "content": "Compute job task_id=7 finished, state=failed.",
        "session_id": coordinator.id,
        "notify_coordinator": False,
    }
    await broker._deliver(project.id, payload)
    await broker._deliver(project.id, payload)
    assert len(core.event_log.query_session(coordinator.id, types={"agent.message_injected"})) == 1


@pytest.mark.asyncio
async def test_compute_notify_notifies_coordinator_when_session_unknown():
    core, project, coordinator = await _setup_core()
    broker = ComputeNotifyBroker(core)

    await broker._deliver(
        project.id,
        {
            "kind": "task_finished",
            "task_kind": "compute",
            "task_id": 11,
            "state": "done",
            "content": "Compute job task_id=11 finished, state=done.",
            "session_id": None,
            "notify_coordinator": True,
        },
    )

    events = core.event_log.query_session(
        coordinator.id, types={"agent.message_injected"}
    )
    assert len(events) == 1
    assert "task_id=11" in events[0].data["content"]
