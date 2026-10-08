from __future__ import annotations

import asyncio

import pytest

from cloudra.runtime_v2.apply import apply_event
from cloudra.runtime_v2.commands import CommandBus
from cloudra.runtime_v2.core import RuntimeCore
from cloudra.runtime_v2.effects import EventDraft
from cloudra.runtime_v2.persistence import RuntimeStore, restore_core
from cloudra.runtime_v2.policies.base import ToolCall
from cloudra.runtime_v2.schemas import Command


async def _execute(bus, type_, *, project_id=None, session_id=None, **payload):
    target = {}
    if project_id is not None:
        target["project_id"] = project_id
    if session_id is not None:
        target["session_id"] = session_id
    result = await bus.execute(Command(type=type_, target=target, payload=payload))
    assert result.accepted, result.data
    return result.data


async def _prepared_project(core, bus, name):
    project = await _execute(bus, "project.create", name=name)
    agent = await _execute(bus, "agent.spawn", project_id=project.id, role_id="coordinator")
    await core.agent_host.start_run(agent)
    await core.contexts.append_output(
        agent=agent, run_id=agent.current_run.run_id,
        messages=[{"role": "assistant", "content": name + "x" * 65536}],
    )
    core.notices.pin(agent.id, "memory", "pin " + name)
    core.notices.collect_batch(agent.id, fresh=False)
    await _execute(bus, "agent.compact", session_id=agent.id)
    await core.agent_host.finish_run(agent, outcome="succeeded")
    return project, agent


@pytest.mark.asyncio
async def test_project_delete_releases_context_notices_and_pending_compaction(tmp_path):
    core = RuntimeCore(strict_events=True)
    core.store = RuntimeStore(tmp_path / "runtime.db")
    bus = CommandBus(core)
    deleted, deleted_agent = await _prepared_project(core, bus, "deleted")
    kept, kept_agent = await _prepared_project(core, bus, "kept")
    try:
        await _execute(bus, "project.update", project_id=deleted.id, archived=True)
        await _execute(bus, "project.delete", project_id=deleted.id)
        assert core.contexts.current_messages(deleted_agent.id) == []
        assert deleted_agent.id not in core.pending_compactions
        assert core.notices.render_current(deleted_agent.id) == []
        assert core.notices.pending_batch(deleted_agent.id) == ([], None)
        assert core.contexts.current_messages(kept_agent.id)
        assert kept_agent.id in core.pending_compactions
        assert core.notices.render_current(kept_agent.id)
        assert kept.id in core.projects
        await bus.flush_snapshot()
        restored = RuntimeCore(strict_events=True)
        await asyncio.to_thread(restore_core, restored, core.store)
        assert restored.contexts.current_messages(deleted_agent.id) == []
        assert deleted_agent.id not in restored.pending_compactions
        assert restored.notices.render_current(deleted_agent.id) == []
        assert restored.contexts.current_messages(kept_agent.id)
        await restored.aclose()
    finally:
        await core.aclose()


@pytest.mark.asyncio
async def test_restore_prunes_orphaned_contexts_from_pre_fix_snapshot(tmp_path):
    core = RuntimeCore(strict_events=True)
    core.store = RuntimeStore(tmp_path / "runtime.db")
    bus = CommandBus(core)
    project, agent = await _prepared_project(core, bus, "old snapshot")
    try:
        await _execute(bus, "project.update", project_id=project.id, archived=True)
        await _execute(bus, "project.delete", project_id=project.id)
        # Historical snapshots can already contain these obsolete projections;
        # no tombstone remains after their snapshot watermark to clean them.
        await bus.flush_snapshot()
        snapshot, watermarks = await asyncio.to_thread(core.store.load_snapshot)
        snapshot["session_contexts"][agent.id] = {
            "messages": [{"role": "assistant", "content": "old retained context"}],
        }
        snapshot["pending_compactions"] = [agent.id]
        await asyncio.to_thread(core.store.write_snapshot_payload, snapshot, watermarks)
        restored = RuntimeCore(strict_events=True)
        await asyncio.to_thread(restore_core, restored, core.store)
        assert agent.id not in restored.session_contexts
        assert agent.id not in restored.pending_compactions
        assert restored.notices.render_current(agent.id) == []
        await restored.aclose()
    finally:
        await core.aclose()


@pytest.mark.asyncio
async def test_project_delete_releases_launch_groups_and_local_reminder_tasks(tmp_path):
    core = RuntimeCore(strict_events=True)
    bus = CommandBus(core)
    project, agent = await _prepared_project(core, bus, "scoped resources")
    event = await core.event_writer.commit(EventDraft(
        "launch_group.created", stream="agent", project_id=project.id, session_id=agent.id,
        data={"group_id": "group-memory", "items": [{"item_id": "item-1", "query": "large query"}],
              "max_concurrency": 1},
    ))
    apply_event(core, event)
    await core.reminders.handle(agent, ToolCall(
        id="reminder-memory", name="schedule",
        arguments={"action": "create", "message": "later", "delay_seconds": 3600},
    ))
    timers = [task for group in core.reminders._timers.values() for task in group]
    assert timers
    try:
        await _execute(bus, "project.update", project_id=project.id, archived=True)
        await _execute(bus, "project.delete", project_id=project.id)
        assert core.launch_groups.groups() == []
        assert not core.reminders._timers
        await asyncio.gather(*timers, return_exceptions=True)
        assert all(task.cancelled() for task in timers)
    finally:
        await core.reminders.close()
        await core.aclose()
