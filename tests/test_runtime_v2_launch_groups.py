"""Task 10: launch group concurrency tests."""

import asyncio

import pytest

from cloudra.runtime_v2.launch_groups import LaunchGroupManager
from cloudra.runtime_v2.schemas import AgentState


class FakeChild:
    def __init__(self, item_id: str):
        self.id = f"as_{item_id}"
        self.state = AgentState.RUNNING

    async def finish_soon(self, delay: float):
        await asyncio.sleep(delay)
        self.state = AgentState.SUCCEEDED


@pytest.mark.asyncio
async def test_max_concurrency_covers_child_lifetime():
    active = 0
    peak = 0
    started = []

    async def spawner(query):
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        started.append(query)
        child = FakeChild(query)
        asyncio.create_task(child.finish_soon(0.05))
        # Yield so the child can finish before this spawner returns.
        while child.state is AgentState.RUNNING:
            await asyncio.sleep(0.01)
        active -= 1
        return child

    manager = LaunchGroupManager(spawner=spawner)
    group = await manager.create(
        group_id="grp_1",
        parent_session_id="parent",
        items=[(f"i{i}", f"q{i}") for i in range(10)],
        max_concurrency=2,
    )
    assert group.pending_count == 10
    for _ in range(100):
        if group.state == "finished":
            break
        await asyncio.sleep(0.01)
    assert group.state == "finished"
    assert peak <= 2
    assert len(started) == 10
    assert all(item.state == "succeeded" for item in group.items)
    assert group.summary()["pending_count"] == 0


@pytest.mark.asyncio
async def test_background_wait_does_not_finish_group_item(tmp_path):
    """The lifetime slot stays held until the child's first real result."""
    from cloudra.runtime_v2.commands import CommandBus
    from cloudra.runtime_v2.core import RuntimeCore
    from cloudra.runtime_v2.effects import EventDraft
    from cloudra.runtime_v2.persistence import RuntimeStore, restore_core
    from cloudra.runtime_v2.schemas import Command

    core = RuntimeCore(strict_events=True)
    core.store = RuntimeStore(tmp_path / "runtime.db")
    bus = CommandBus(core)
    project = (await bus.execute(Command(type="project.create", payload={"name": "group-wait"}))).data
    parent = (await bus.execute(Command(
        type="agent.spawn", target={"project_id": project.id}, payload={"role_id": "coordinator"},
    ))).data

    async def spawner(_query):
        return (await bus.execute(Command(
            type="agent.spawn", target={"project_id": project.id},
            payload={"role_id": "explorer", "parent_session_id": parent.id},
        ))).data

    group = await core.launch_groups.create(
        group_id="grp_wait", parent_session_id=parent.id, project_id=project.id,
        items=[("i0", "task")], max_concurrency=1, spawner=spawner,
    )
    for _ in range(100):
        if group.items[0].child_session_id:
            break
        await asyncio.sleep(0.01)
    child = core.agents[group.items[0].child_session_id]

    async def finish(action):
        run_id = await core.agent_host.start_run(child)
        await core.event_writer.commit(EventDraft(
            "agent.completion_gate", stream="agent", project_id=project.id,
            session_id=child.id, run_id=run_id,
            data={"action": action, "reason": "test", "source": "test"},
        ))
        await core.agent_host.finish_run(child, outcome="succeeded")

    await finish("wait_background")
    await asyncio.sleep(0.05)
    assert group.state == "running"
    assert group.items[0].state == "running"

    restored = RuntimeCore(strict_events=True)
    restored.store = core.store
    restore_core(restored, core.store)
    restored_group = restored.launch_groups.get(group.group_id)
    assert restored_group.state == "interrupted"
    assert restored_group.items[0].state == "running"

    await finish("allow_final")
    for _ in range(100):
        if group.state == "finished":
            break
        await asyncio.sleep(0.01)
    assert group.state == "finished"
    assert group.items[0].state == "succeeded"


@pytest.mark.asyncio
async def test_capped_swarm_dispatches_after_compute_park_and_caps_resumed_runs():
    """A parked QM child frees a run slot; simultaneous notices still obey the cap."""
    from cloudra.persistence.database import ComputeDB
    from cloudra.runtime_v2.agent_runner import AgentRunner
    from cloudra.runtime_v2.commands import CommandBus
    from cloudra.runtime_v2.compute_notify import ComputeNotifyBroker
    from cloudra.runtime_v2.core import RuntimeCore
    from cloudra.runtime_v2.policies.schedule_stage import ScheduleStage
    from cloudra.runtime_v2.schemas import Command
    from cloudra.runtime_v2.subagent_bridge import _handle_swarm
    from cloudra.runtime_v2.turn_pipeline import LLMResponse, TurnPipeline
    from cloudra.services.compute_store import ainsert_compute_job

    core = RuntimeCore(strict_events=True)
    bus = CommandBus(core)
    project = (await bus.execute(Command(
        type="project.create", payload={"name": "capped compute swarm"},
    ))).data
    parent = (await bus.execute(Command(
        type="agent.spawn", target={"project_id": project.id},
        payload={"role_id": "coordinator"},
    ))).data

    class ParkThenFinishLLM:
        def __init__(self):
            self.calls: dict[str, int] = {}
            self.active = 0
            self.peak = 0
            self.jobs: list[int] = []

        async def complete(self, agent, messages, tools, **_kwargs):
            if agent.role_id == "coordinator":
                return LLMResponse(content="coordinator observed child result", stop_requested=True)
            self.active += 1
            self.peak = max(self.peak, self.active)
            try:
                await asyncio.sleep(0.03)
                number = self.calls.get(agent.id, 0) + 1
                self.calls[agent.id] = number
                if number == 1:
                    job_id = await ainsert_compute_job(
                        await ComputeDB().ainit(), conversation_id=project.id,
                        session_id=agent.id, path=f"/tmp/{agent.id}.gjf",
                        state="ready", jobtype="gaussian", node_id="local",
                    )
                    self.jobs.append(job_id)
                    return LLMResponse(content="waiting for compute", stop_requested=True)
                return LLMResponse(content="result checked", stop_requested=True)
            finally:
                self.active -= 1

    class NoTools:
        async def execute(self, *_args, **_kwargs):
            raise AssertionError("the scripted LLM does not call tools")

    llm = ParkThenFinishLLM()
    core.runner = AgentRunner(core, TurnPipeline(
        event_log=core.event_log, stages=[ScheduleStage(core)],
        llm=llm, tools=NoTools(),
    ))
    dispatched = await _handle_swarm(core, parent, {
        "agent_id": "a-4", "prompt_template": "work on {{item}}",
        "items": ["one", "two", "three"], "is_wait": False,
        "max_concurrency": 1,
    })
    assert dispatched.is_success
    group = core.launch_groups.get(dispatched.data["group_id"])

    async def wait_for(predicate, message):
        for _ in range(500):
            if predicate():
                return
            await asyncio.sleep(0.01)
        raise AssertionError(message)

    await wait_for(
        lambda: len(llm.jobs) == 3 and all(
            item.child_session_id and core.agents[item.child_session_id].state is AgentState.SUCCEEDED
            for item in group.items
        ),
        "all three children should park while their QM jobs remain active",
    )
    assert group.state == "running"
    assert all(item.state == "running" for item in group.items)
    assert llm.peak == 1
    for item in group.items:
        child_id = item.child_session_id
        events = list(core.event_log)
        dispatch_position = next(i for i, event in enumerate(events) if (
            event.type == "launch_group.item_dispatched" and
            event.data.get("child_session_id") == child_id
        ))
        run_position = next(i for i, event in enumerate(events) if (
            event.type == "run.started" and event.session_id == child_id
        ))
        assert dispatch_position < run_position

    async with ComputeDB().aconnect() as con:
        for job_id in llm.jobs:
            await con.execute("UPDATE compute_jobs SET state='done' WHERE id=?", (job_id,))
        await con.commit()
    await ComputeNotifyBroker(core)._poll_project(project.id)
    await wait_for(lambda: group.state == "finished", "resumed children should complete")
    assert all(item.state == "succeeded" for item in group.items)
    assert all(count == 2 for count in llm.calls.values())
    assert llm.peak == 1


@pytest.mark.asyncio
async def test_duplicate_group_id_is_rejected_loudly():
    """group_id 冲突绝不静默覆盖（A5：旧实现从 loop.time() 派生 id，撞车会
    无声替换整组）。重复 create 必须响亮拒绝。"""
    manager = LaunchGroupManager(spawner=lambda _query: None)
    await manager.create(
        group_id="grp_dup", parent_session_id="parent", items=[], max_concurrency=1
    )
    with pytest.raises(ValueError, match="grp_dup"):
        await manager.create(
            group_id="grp_dup", parent_session_id="parent", items=[], max_concurrency=1
        )
    assert manager.get("grp_dup") is not None


@pytest.mark.asyncio
async def test_each_group_keeps_its_project_spawner_context():
    seen = []

    async def spawner_a(query):
        child = FakeChild("a-" + query)
        seen.append(("project-a", query))
        child.state = AgentState.SUCCEEDED
        return child

    async def spawner_b(query):
        child = FakeChild("b-" + query)
        seen.append(("project-b", query))
        child.state = AgentState.SUCCEEDED
        return child

    manager = LaunchGroupManager(spawner=lambda _query: None)
    await manager.create(
        group_id="group-a", parent_session_id="parent-a", items=[("a", "task-a")],
        max_concurrency=1, spawner=spawner_a,
    )
    await manager.create(
        group_id="group-b", parent_session_id="parent-b", items=[("b", "task-b")],
        max_concurrency=1, spawner=spawner_b,
    )
    for _ in range(100):
        if manager.get("group-a").state == "finished" and manager.get("group-b").state == "finished":
            break
        await asyncio.sleep(0.01)
    assert seen == [("project-a", "task-a"), ("project-b", "task-b")]


# ---------------------------------------------------------------- 事件投影与恢复
# 评审 5.2 后半：组的创建/item 派发/item 终态/组终态是事件；重启只重建组清单并
# 标 interrupted——绝不重放 spawn 外部副作用。


class _EchoLLM:
    """脚本化 LLM：每个 child 一轮纯文本结束（不需要真实 key）。"""

    async def complete(self, agent, messages, tools, **_kwargs):
        from cloudra.runtime_v2.turn_pipeline import LLMResponse

        return LLMResponse(content=f"{agent.role_id} done", stop_requested=True)


async def _core_with_parent(store):
    from cloudra.runtime_v2.adapters import LegacyToolExecutor
    from cloudra.runtime_v2.agent_runner import AgentRunner
    from cloudra.runtime_v2.commands import CommandBus
    from cloudra.runtime_v2.core import RuntimeCore
    from cloudra.runtime_v2.policies import default_stages
    from cloudra.runtime_v2.schemas import Command
    from cloudra.runtime_v2.turn_pipeline import TurnPipeline

    core = RuntimeCore(strict_events=True)
    core.runner = AgentRunner(
        core,
        TurnPipeline(
            event_log=core.event_log,
            stages=default_stages(),
            llm=_EchoLLM(),
            tools=LegacyToolExecutor(core),
        ),
    )
    core.store = store
    bus = CommandBus(core)
    await bus.execute(Command(type="project.create", payload={"name": "groups"}))
    project = next(iter(core.projects.values()))
    parent = (
        await bus.execute(
            Command(
                type="agent.spawn",
                target={"project_id": project.id},
                payload={"role_id": "coordinator", "query": "coordinate"},
            )
        )
    ).data
    return core, project, parent


@pytest.mark.asyncio
async def test_group_lifecycle_is_event_sourced(tmp_path):
    from cloudra.runtime_v2.persistence import RuntimeStore

    store = RuntimeStore(tmp_path / "runtime-v2.db")
    core, project, parent = await _core_with_parent(store)
    bus_calls: list[str] = []

    async def spawner(query):
        from cloudra.runtime_v2.commands import CommandBus
        from cloudra.runtime_v2.schemas import Command

        bus_calls.append(query)
        return (
            await CommandBus(core).execute(
                Command(
                    type="agent.spawn",
                    target={"project_id": project.id},
                    payload={"role_id": "explorer", "parent_session_id": parent.id, "query": query},
                )
            )
        ).data

    group = await core.launch_groups.create(
        group_id="grp_events",
        parent_session_id=parent.id,
        project_id=project.id,
        items=[("i0", "q0"), ("i1", "q1")],
        max_concurrency=2,
        spawner=spawner,
    )
    for _ in range(300):
        if group.state == "finished":
            break
        await asyncio.sleep(0.01)
    assert group.state == "finished"
    assert all(item.state == "succeeded" for item in group.items)

    types = [e["type"] for e in store.events_after({})]
    assert types.count("launch_group.created") == 1
    assert types.count("launch_group.item_dispatched") == 2
    assert types.count("launch_group.item_finished") == 2
    assert types.count("launch_group.finished") == 1
    # child session 记进事件（重启后可对账）。
    dispatched = [
        e for e in store.events_after({}) if e["type"] == "launch_group.item_dispatched"
    ]
    assert all(e["data"]["child_session_id"].startswith("as_") for e in dispatched)


@pytest.mark.asyncio
@pytest.mark.parametrize("fail_once", [True, False], ids=["one-failure", "persistent-failure"])
async def test_dispatch_persistence_failure_does_not_orphan_spawned_child(
    tmp_path, monkeypatch, fail_once
):
    """A deferred child must not be stranded if its group dispatch event cannot persist."""
    from cloudra.runtime_v2.adapters import LegacyToolExecutor
    from cloudra.runtime_v2.agent_runner import AgentRunner
    from cloudra.runtime_v2.commands import CommandBus
    from cloudra.runtime_v2.core import RuntimeCore
    from cloudra.runtime_v2.persistence import RuntimeStore
    from cloudra.runtime_v2.policies import default_stages
    from cloudra.runtime_v2.schemas import Command
    from cloudra.runtime_v2.turn_pipeline import TurnPipeline

    store = RuntimeStore(tmp_path / "runtime-v2.db")
    core = RuntimeCore(strict_events=True)
    core.store = store
    bus = CommandBus(core)
    project = (await bus.execute(Command(
        type="project.create", payload={"name": "dispatch-failure"},
    ))).data
    parent = (await bus.execute(Command(
        type="agent.spawn", target={"project_id": project.id},
        payload={"role_id": "coordinator"},
    ))).data
    core.runner = AgentRunner(core, TurnPipeline(
        event_log=core.event_log, stages=default_stages(), llm=_EchoLLM(),
        tools=LegacyToolExecutor(core),
    ))
    original_append = store.append_event
    failures = 0

    def fail_dispatch(envelope):
        nonlocal failures
        if envelope.type == "launch_group.item_dispatched" and (
            not fail_once or failures == 0
        ):
            failures += 1
            raise OSError("dispatch event unavailable")
        if (
            not fail_once and envelope.type == "agent.state_changed"
            and envelope.data.get("to") == "cancelled"
        ):
            raise OSError("cancel event unavailable")
        return original_append(envelope)

    monkeypatch.setattr(store, "append_event", fail_dispatch)
    spawned = []

    async def spawner(query):
        child = (await CommandBus(core).execute(Command(
            type="agent.spawn", target={"project_id": project.id},
            payload={
                "role_id": "explorer", "parent_session_id": parent.id,
                "query": query, "defer_schedule": True,
            },
        ))).data
        spawned.append(child.id)
        return child

    group = await core.launch_groups.create(
        group_id="grp_dispatch_fail", parent_session_id=parent.id,
        project_id=project.id, items=[("i0", "q0")], max_concurrency=1,
        spawner=spawner,
    )
    await asyncio.wait_for(group._task, timeout=3)

    assert spawned and len(spawned) == 1
    child = core.agents[spawned[0]]
    if fail_once:
        assert child.state is AgentState.SUCCEEDED
        assert group.item("i0").state == "succeeded"
        assert group.item("i0").child_session_id == child.id
        assert sum(
            event["type"] == "launch_group.item_dispatched"
            for event in store.events_after({})
        ) == 1
    else:
        assert child.state is AgentState.QUEUED
        assert core.runner.task_for(child.id) is None
        assert group.item("i0").state == "failed"
        assert group.item("i0").child_session_id == child.id
        assert any(
            event["type"] == "launch_group.item_finished"
            and event["data"].get("child_session_id") == child.id
            for event in store.events_after({})
        )


@pytest.mark.asyncio
async def test_restore_marks_running_group_interrupted_without_respawning(tmp_path):
    from cloudra.runtime_v2.core import RuntimeCore
    from cloudra.runtime_v2.persistence import RuntimeStore, restore_core
    from cloudra.runtime_v2.schemas import AgentState as _State

    store = RuntimeStore(tmp_path / "runtime-v2.db")
    core, project, parent = await _core_with_parent(store)
    spawn_calls: list[str] = []
    blocked = asyncio.Event()

    async def spawner(query):
        from cloudra.runtime_v2.commands import CommandBus
        from cloudra.runtime_v2.schemas import Command

        spawn_calls.append(query)
        if query == "q1":
            # 模拟「派发在途中进程没了」：spawn 永不返回。
            await blocked.wait()
        return (
            await CommandBus(core).execute(
                Command(
                    type="agent.spawn",
                    target={"project_id": project.id},
                    payload={"role_id": "explorer", "parent_session_id": parent.id, "query": query},
                )
            )
        ).data

    group = await core.launch_groups.create(
        group_id="grp_crash",
        parent_session_id=parent.id,
        project_id=project.id,
        items=[("i0", "q0"), ("i1", "q1"), ("i2", "q2")],
        max_concurrency=1,
        spawner=spawner,
    )
    for _ in range(500):
        if group.item("i0").state == "succeeded" and len(spawn_calls) == 2:
            break
        await asyncio.sleep(0.01)
    assert group.item("i0").state == "succeeded"
    assert spawn_calls == ["q0", "q1"]

    children_before = [a for a in core.agents.values() if a.parent_session_id == parent.id]
    assert len(children_before) == 1

    # 「重启」：新 core 从同一个 store 恢复（旧 worker 还在等 blocked，模拟崩溃前的在途派发）。
    restored = RuntimeCore(strict_events=True)
    restored.store = store
    restore_core(restored, store)

    rebuilt = restored.launch_groups.get("grp_crash")
    assert rebuilt is not None
    assert rebuilt.state == "interrupted"
    assert "restart" in rebuilt.reason
    # 全部 item 与 child session 仍可查询。
    assert [i.item_id for i in rebuilt.items] == ["i0", "i1", "i2"]
    assert rebuilt.item("i0").state == "succeeded"  # 与活 child 终态对账
    assert rebuilt.item("i0").child_session_id.startswith("as_")
    assert rebuilt.item("i1").state == "queued"  # 未派发：保持 queued，等显式重派
    assert rebuilt.item("i2").state == "queued"
    # 不重复 spawn：恢复没有新增任何 child，也没有再调用 spawner。
    children_after = [a for a in restored.agents.values() if a.parent_session_id == parent.id]
    assert [a.id for a in children_after] == [a.id for a in children_before]
    assert spawn_calls == ["q0", "q1"]
    assert rebuilt._task is None
    # child 状态对账：崩溃前已成功的 child 保持原终态（不重放执行，也不改写）；
    # 若它当时还在跑，恢复会按既有规则收口为 failed（见 persistence 的僵尸收尾）。
    assert children_after[0].state is _State.SUCCEEDED
    _ = _State

    blocked.set()  # 放掉旧 worker，避免悬挂任务
    if group._task is not None:
        group._task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await group._task


@pytest.mark.asyncio
async def test_restored_group_summary_exposes_items_and_reason(tmp_path):
    from cloudra.runtime_v2.core import RuntimeCore
    from cloudra.runtime_v2.persistence import RuntimeStore, restore_core

    store = RuntimeStore(tmp_path / "runtime-v2.db")
    core, project, parent = await _core_with_parent(store)
    blocked = asyncio.Event()

    async def spawner(query):
        await blocked.wait()
        raise AssertionError("never reached")

    await core.launch_groups.create(
        group_id="grp_query",
        parent_session_id=parent.id,
        project_id=project.id,
        items=[("i0", "q0")],
        max_concurrency=1,
        spawner=spawner,
    )
    await asyncio.sleep(0.02)

    restored = RuntimeCore(strict_events=True)
    restored.store = store
    restore_core(restored, store)
    summary = restored.launch_groups.get("grp_query").summary()
    assert summary["state"] == "interrupted"
    assert summary["reason"]
    assert summary["items"][0]["item_id"] == "i0"
    assert summary["items"][0]["query"] == "q0"

    blocked.set()


@pytest.mark.asyncio
async def test_cancel_persists_item_finished_and_survives_restore(tmp_path):
    """cancel 必须落 item_finished；二次 restore 后 item 仍是 cancelled，不是 queued。"""
    from cloudra.runtime_v2.core import RuntimeCore
    from cloudra.runtime_v2.persistence import RuntimeStore, restore_core

    store = RuntimeStore(tmp_path / "runtime-v2.db")
    core, project, parent = await _core_with_parent(store)
    blocked = asyncio.Event()

    async def spawner(query):
        await blocked.wait()
        raise AssertionError("never reached")

    group = await core.launch_groups.create(
        group_id="grp_cancel",
        parent_session_id=parent.id,
        project_id=project.id,
        items=[("i0", "q0"), ("i1", "q1")],
        max_concurrency=1,
        spawner=spawner,
    )
    await asyncio.sleep(0.02)
    await core.launch_groups.cancel(group.group_id)
    assert group.state == "cancelled"
    assert group.reason == "parent cancelled"
    assert all(item.state == "cancelled" for item in group.items)

    types = [e["type"] for e in store.events_after({})]
    assert types.count("launch_group.item_finished") == 2
    assert types.count("launch_group.finished") == 1
    finished = [e for e in store.events_after({}) if e["type"] == "launch_group.finished"]
    assert finished[-1]["data"]["reason"] == "parent cancelled"

    restored = RuntimeCore(strict_events=True)
    restored.store = store
    restore_core(restored, store)
    again = restored.launch_groups.get("grp_cancel")
    assert again is not None
    assert again.state == "cancelled"
    assert again.reason == "parent cancelled"
    assert [i.state for i in again.items] == ["cancelled", "cancelled"]

    # 二次恢复：投影只来自事件，不得回退成 queued。
    restored2 = RuntimeCore(strict_events=True)
    restored2.store = store
    restore_core(restored2, store)
    again2 = restored2.launch_groups.get("grp_cancel")
    assert [i.state for i in again2.items] == ["cancelled", "cancelled"]
    assert again2.reason == "parent cancelled"

    blocked.set()


@pytest.mark.asyncio
async def test_cancel_then_worker_cancelled_preserves_reason(tmp_path):
    """cancel 落 reason 后，worker CancelledError 的 best-effort 不得抹掉 reason。"""
    from cloudra.runtime_v2.persistence import RuntimeStore

    store = RuntimeStore(tmp_path / "runtime-v2.db")
    core, project, parent = await _core_with_parent(store)
    started = asyncio.Event()
    release = asyncio.Event()

    async def spawner(query):
        from cloudra.runtime_v2.commands import CommandBus
        from cloudra.runtime_v2.schemas import Command

        started.set()
        await release.wait()
        return (
            await CommandBus(core).execute(
                Command(
                    type="agent.spawn",
                    target={"project_id": project.id},
                    payload={"role_id": "explorer", "parent_session_id": parent.id, "query": query},
                )
            )
        ).data

    group = await core.launch_groups.create(
        group_id="grp_reason",
        parent_session_id=parent.id,
        project_id=project.id,
        items=[("i0", "q0")],
        max_concurrency=1,
        spawner=spawner,
    )
    await asyncio.wait_for(started.wait(), timeout=2.0)
    await core.launch_groups.cancel(group.group_id)
    assert group.state == "cancelled"
    assert group.reason == "parent cancelled"
    finished = [e for e in store.events_after({}) if e["type"] == "launch_group.finished"]
    assert finished
    assert finished[-1]["data"]["reason"] == "parent cancelled"
    release.set()
@pytest.mark.asyncio
@pytest.mark.parametrize("flush_command_snapshot", [False, True], ids=["restore", "command"])
async def test_group_survives_second_restore_after_snapshot_covers_events(
    tmp_path, flush_command_snapshot
):
    """快照水位越过 launch_group.* 事件后，二次恢复仍能重建组清单。

    回归：恢复写快照时若不把组清单随快照落地，下一次恢复只重放快照之后的
    事件——快照覆盖的那批组会凭空消失（评审 5.2 后半的「重启可查询」承诺
    在二次恢复下破功）。
    """
    from cloudra.runtime_v2.commands import CommandBus
    from cloudra.runtime_v2.core import RuntimeCore
    from cloudra.runtime_v2.persistence import RuntimeStore, restore_core
    from cloudra.runtime_v2.schemas import Command

    store = RuntimeStore(tmp_path / "runtime-v2.db")
    core, project, parent = await _core_with_parent(store)
    blocked = asyncio.Event()

    async def spawner(query):
        if query == "q1":
            await blocked.wait()
        return (
            await CommandBus(core).execute(
                Command(
                    type="agent.spawn",
                    target={"project_id": project.id},
                    payload={"role_id": "explorer", "parent_session_id": parent.id, "query": query},
                )
            )
        ).data

    group = await core.launch_groups.create(
        group_id="grp_twice",
        parent_session_id=parent.id,
        project_id=project.id,
        items=[("i0", "q0"), ("i1", "q1")],
        max_concurrency=1,
        spawner=spawner,
    )
    for _ in range(500):
        if group.item("i0").state == "succeeded":
            break
        await asyncio.sleep(0.01)

    if flush_command_snapshot:
        # 命令/关闭路径独立组装快照，必须同样保存水位覆盖的组清单。
        await CommandBus(core).flush_snapshot()

    restored = RuntimeCore(strict_events=True)
    restored.store = store
    restore_core(restored, store)
    first = restored.launch_groups.get("grp_twice")
    assert first is not None and first.state == "interrupted"

    # 二次恢复：事件已被第一次恢复写的快照水位覆盖。
    restored2 = RuntimeCore(strict_events=True)
    restored2.store = store
    restore_core(restored2, store)
    again = restored2.launch_groups.get("grp_twice")
    assert again is not None, "快照未携带组清单 → 二次恢复丢组"
    assert again.state == "interrupted"
    assert [i.item_id for i in again.items] == ["i0", "i1"]
    assert again.item("i0").state == "succeeded"
    assert again.item("i1").state == "queued"
    assert again._task is None

    blocked.set()
    if group._task is not None:
        group._task.cancel()


@pytest.mark.asyncio
async def test_corrupt_group_snapshot_fails_loud(tmp_path):
    """快照形状错误必须 fail-loud（静默降级会掩盖「组清单丢了」）。"""
    from cloudra.runtime_v2.core import RuntimeCore
    from cloudra.runtime_v2.persistence import RuntimeStore, restore_core

    store = RuntimeStore(tmp_path / "runtime-v2.db")
    store.write_snapshot_payload(
        {"launch_groups": [{"group_id": "grp_bad", "state": "running", "items": [{"state": "nope"}]}]},
        {},
    )
    core = RuntimeCore(strict_events=True)
    core.store = store
    with pytest.raises(ValueError):
        restore_core(core, store)


@pytest.mark.asyncio
async def test_snapshot_roundtrip_keeps_group_identity(tmp_path):
    """snapshot()/restore() 是纯数据往返：身份与状态逐字保留。"""
    from cloudra.runtime_v2.launch_groups import LaunchGroupManager

    manager = LaunchGroupManager(spawner=lambda _q: None)
    await manager.create(
        group_id="grp_rt",
        parent_session_id="parent",
        project_id="prj",
        items=[("i0", "q0"), ("i1", "q1")],
        max_concurrency=2,
    )
    payload = manager.snapshot()

    other = LaunchGroupManager(spawner=lambda _q: None)
    other.restore(payload)
    group = other.get("grp_rt")
    assert group.state == "running"
    assert group.project_id == "prj"
    assert group.max_concurrency == 2
    assert [(i.item_id, i.query, i.state) for i in group.items] == [
        ("i0", "q0", "queued"),
        ("i1", "q1", "queued"),
    ]
    assert group._task is None  # 恢复不重建 worker
    if manager.get("grp_rt")._task is not None:
        manager.get("grp_rt")._task.cancel()
