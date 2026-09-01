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
    # 3b 起快照是节流缓存，测试显式冻结快照点。
    await bus.flush_snapshot()

    # 新 core 从同一 store 恢复
    core2 = RuntimeCore(strict_events=True)
    last_seqs = restore_core(core2, store)
    assert last_seqs == core.event_log.high_watermarks
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
    # 冻结点：快照停在最后一次 bus 命令
    await bus.flush_snapshot()

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
    # 事件回放保留记录，但恢复出的 running run 是上一进程的尸体：
    # restore 会把它落成 failed（current_run 清空）。
    assert restored.state.value == "failed"
    assert restored.current_run is None
    types = [e["type"] for e in store.query_project_events(project.id)]
    assert "tool.started" in types


@pytest.mark.asyncio
async def test_restore_marks_zombie_running_agents_failed(tmp_path):
    """run 只活在内存：恢复时仍处于 running/waiting 的 agent 是上一进程的
    尸体，必须落 failed（带 run.finished 事件），否则 UI 永远显示 running。"""
    store = RuntimeStore(tmp_path / "runtime.db")
    core = RuntimeCore(strict_events=True)
    core.store = store
    core.event_hub.subscribe(lambda event: _persist_event(store, event))
    bus = CommandBus(core)

    await bus.execute(Command(type="project.create", payload={"name": "zombie"}))
    project = next(iter(core.projects.values()))
    await bus.execute(
        Command(
            type="agent.spawn",
            target={"project_id": project.id},
            payload={"role_id": "coordinator", "query": "hello"},
        )
    )
    agent = next(iter(core.agents.values()))
    # 无 runner：手动把 agent 推进 running（模拟进程崩溃前的快照状态）
    core.agent_host.start_run(agent)
    for event in list(core.event_log)[-2:]:
        await _persist_event(store, event)
    store.save_snapshot(
        projects=core.projects,
        agents=core.agents,
        roles=core.roles._roles,
        runtime_defaults=core.runtime_defaults,
        last_seqs=core.event_log.high_watermarks,
    )

    restored = RuntimeCore(strict_events=True)
    restored.store = store
    restore_core(restored, store)

    revived = restored.agents[agent.id]
    from cloudra.runtime_v2.schemas import AgentState

    assert revived.state is AgentState.FAILED
    finished = restored.event_log.query_session(agent.id, types={"run.finished"})
    assert finished[-1].data["error"] == "interrupted by process restart"

    # 二次重启不再重复标记（幂等）
    again = RuntimeCore(strict_events=True)
    again.store = store
    restore_core(again, store)
    assert again.agents[agent.id].state is AgentState.FAILED
    assert len(again.event_log.query_session(agent.id, types={"run.finished"})) == len(finished)


@pytest.mark.asyncio
async def test_restore_merges_snapshot_roles_over_builtins(tmp_path):
    """旧快照（缺后加的内置角色，如 supervisor）恢复后，注册表仍包含全部
    内置角色；快照里的 role.update 补丁继续生效。"""
    store = RuntimeStore(tmp_path / "runtime.db")
    core = RuntimeCore(strict_events=True)
    core.store = store
    core.event_hub.subscribe(lambda event: _persist_event(store, event))
    bus = CommandBus(core)

    await bus.execute(Command(type="project.create", payload={"name": "roles"}))
    await bus.execute(
        Command(
            type="role.update",
            target={"role_id": "researcher"},
            payload={"default_settings": {"temperature": 0.9}},
        )
    )

    # 手工落一个缺 supervisor 角色的快照（模拟该角色加入 BUILTIN_ROLES
    # 之前保存的旧库）
    stale_roles = {k: v for k, v in core.roles._roles.items() if k != "supervisor"}
    store.save_snapshot(
        projects=core.projects,
        agents=core.agents,
        roles=stale_roles,
        runtime_defaults=core.runtime_defaults,
        last_seqs=core.event_log.high_watermarks,
    )

    restored = RuntimeCore(strict_events=True)
    restored.store = store
    restore_core(restored, store)

    assert restored.roles.require("supervisor").role_id == "supervisor"
    assert restored.roles.require("researcher").default_settings.temperature == 0.9


@pytest.mark.asyncio
async def test_restore_tolerates_removed_agent_fields(tmp_path):
    """旧快照/事件还带着已删除的 state_since 与 current_run.current_tool
    （AgentSession 是 extra="forbid"）；恢复必须静默丢弃而不是崩。"""

    class RawDump:
        """save_snapshot 对 agents 调 model_dump；包一层传入预序列化的旧格式负载。"""

        def __init__(self, data: dict) -> None:
            self._data = data

        def model_dump(self, mode: str = "json") -> dict:
            return dict(self._data)

    store = RuntimeStore(tmp_path / "runtime.db")
    core = RuntimeCore(strict_events=True)
    core.store = store
    core.event_hub.subscribe(lambda event: _persist_event(store, event))
    bus = CommandBus(core)

    await bus.execute(Command(type="project.create", payload={"name": "legacy"}))
    project = next(iter(core.projects.values()))
    await bus.execute(
        Command(
            type="agent.spawn",
            target={"project_id": project.id},
            payload={"role_id": "coordinator"},
        )
    )
    agent = next(iter(core.agents.values()))

    # 手工落一个带已删字段的旧格式快照
    legacy_agent = agent.model_dump(mode="json")
    legacy_agent["state_since"] = "2026-01-01T00:00:00+00:00"
    legacy_agent["current_run"] = {
        "run_id": "run_old",
        "started_at": "2026-01-01T00:00:00+00:00",
        "current_tool": "ts_guess",
    }
    store.save_snapshot(
        projects=core.projects,
        agents={agent.id: RawDump(legacy_agent)},
        roles=core.roles._roles,
        runtime_defaults=core.runtime_defaults,
        last_seqs=core.event_log.high_watermarks,
    )

    restored = RuntimeCore(strict_events=True)
    restored.store = store
    restore_core(restored, store)
    revived = restored.agents[agent.id]
    # 已删字段被静默丢弃，其余内容原样恢复
    assert revived.state.value == "queued"
    assert revived.current_run is not None
    assert revived.current_run.run_id == "run_old"


@pytest.mark.asyncio
async def test_snapshot_is_throttled_cache_not_per_command(tmp_path, monkeypatch):
    """快照降级为缓存（3b）：命令路径不再每命令整库快照，而是按事件数/时间
    节流；无快照时 restore 靠全量重放也等价（缓存不是权威）。"""
    from cloudra.runtime_v2 import commands as commands_mod

    store = RuntimeStore(tmp_path / "runtime.db")
    core = RuntimeCore(strict_events=True)
    core.store = store
    core.event_hub.subscribe(lambda event: _persist_event(store, event))
    bus = CommandBus(core)

    saves = 0
    original_save = store.save_snapshot

    def counting_save(**kwargs):
        nonlocal saves
        saves += 1
        return original_save(**kwargs)

    monkeypatch.setattr(store, "save_snapshot", counting_save)

    await bus.execute(Command(type="project.create", payload={"name": "throttle"}))
    project = next(iter(core.projects.values()))
    # 低于阈值：不落快照
    assert saves == 0

    # 无快照恢复：纯事件重放依然等价（缓存不是权威的直接证据）
    core2 = RuntimeCore(strict_events=True)
    restore_core(core2, store)
    assert core2.projects[project.id].name == "throttle"

    # 事件阈值触发：把阈值压到 2，下一条命令（1 条事件 + 之前 1 条）越阈
    monkeypatch.setattr(commands_mod, "_SNAPSHOT_EVENT_INTERVAL", 2)
    await bus.execute(
        Command(type="project.update", target={"project_id": project.id}, payload={"name": "t2"})
    )
    assert saves == 1
    # 节流复位后未越阈不再落
    await bus.execute(
        Command(type="project.update", target={"project_id": project.id}, payload={"name": "t3"})
    )
    assert saves == 1

    # 时间阈值触发：间隔压到 0，任何命令都落
    monkeypatch.setattr(commands_mod, "_SNAPSHOT_TIME_INTERVAL_S", 0.0)
    await bus.execute(
        Command(type="project.update", target={"project_id": project.id}, payload={"name": "t4"})
    )
    assert saves == 2

    # 关机路径：显式 flush 无条件补一次
    await bus.flush_snapshot()
    assert saves == 3
    # flush 后水位覆盖全部事件：restore 无增量尾巴
    core3 = RuntimeCore(strict_events=True)
    restore_core(core3, store)
    assert core3.projects[project.id].name == "t4"
