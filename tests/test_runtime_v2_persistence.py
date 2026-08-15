"""Runtime v2 persistence: snapshots, event durability, incremental restore."""

from __future__ import annotations

import asyncio

import pytest

from cloudra.runtime_v2.commands import CommandBus
from cloudra.runtime_v2.core import RuntimeCore
from cloudra.runtime_v2.persistence import RuntimeStore, restore_core
from cloudra.runtime_v2.schemas import Command


async def _persist_event(store, event):
    await asyncio.to_thread(store.append_event, event)


@pytest.mark.asyncio
async def test_snapshot_and_event_durability_roundtrip(tmp_path):
    store = RuntimeStore(tmp_path / "runtime.db")
    core = RuntimeCore(strict_events=True)
    core.store = store
    core.event_hub.subscribe(lambda event: _persist_event(store, event))
    bus = CommandBus(core)

    await bus.execute(Command(type="project.create", payload={"name": "durable"}))
    project = next(iter(core.projects.values()))
    await bus.execute(
        Command(
            type="agent.spawn",
            target={"project_id": project.id},
            payload={"role_id": "coordinator", "query": "hello"},
        )
    )
    agent = next(iter(core.agents.values()))
    await bus.execute(
        Command(
            type="agent.settings_update",
            target={"session_id": agent.id},
            payload={"yolo": True, "temperature": 0.2},
        )
    )

    # 新 core 从同一 store 恢复
    core2 = RuntimeCore(strict_events=True)
    last_seq = restore_core(core2, store)
    assert last_seq == core.event_log.last_seq
    assert core2.projects[project.id].name == "durable"
    restored_agent = core2.agents[agent.id]
    assert restored_agent.state == "queued"
    assert restored_agent.settings.yolo is True
    assert restored_agent.settings.temperature == 0.2
    assert restored_agent.settings_revision == 1

    persisted = store.query_project_events(project.id)
    types = [e["type"] for e in persisted]
    assert "project.created" in types
    assert "agent.spawned" in types
    assert "agent.settings_changed" in types


@pytest.mark.asyncio
async def test_events_after_snapshot_are_replayed(tmp_path):
    store = RuntimeStore(tmp_path / "runtime.db")
    core = RuntimeCore(strict_events=True)
    core.store = store
    core.event_hub.subscribe(lambda event: _persist_event(store, event))
    bus = CommandBus(core)
    await bus.execute(Command(type="project.create", payload={"name": "p"}))
    project = next(iter(core.projects.values()))
    agent = (await bus.execute(
        Command(type="agent.spawn", target={"project_id": project.id}, payload={"role_id": "coordinator"})
    )).data

    # 快照之后、下一次命令之前，模拟运行期状态事件未进快照
    before = len(core.event_log)
    run_id = core.agent_host.start_run(agent)
    core.event_log.append(
        "tool.started",
        stream="agent",
        project_id=project.id,
        session_id=agent.id,
        run_id=run_id,
        data={"tool_name": "stop"},
    )
    await asyncio.gather(
        *[core.event_hub.publish(e) for e in list(core.event_log)[before:]]
    )

    core2 = RuntimeCore(strict_events=True)
    restore_core(core2, store)
    restored = core2.agents[agent.id]
    assert restored.current_run is not None
    assert restored.current_run.run_id == run_id
    types = [e["type"] for e in store.query_project_events(project.id)]
    assert "tool.started" in types
