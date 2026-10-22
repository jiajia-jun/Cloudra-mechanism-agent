"""Runtime v2 persistence: snapshots, event durability, incremental restore."""

from __future__ import annotations

import asyncio
import sqlite3
import threading

import pytest

from cloudra.runtime_v2.commands import CommandBus
from cloudra.runtime_v2.core import RuntimeCore
from cloudra.runtime_v2.persistence import RuntimeStore, restore_core
from cloudra.runtime_v2.schemas import Command


async def _persist_event(store, event):
    await asyncio.to_thread(store.append_event, event)


def test_store_uses_wal_and_busy_timeout(tmp_path):
    """回滚日志模式下 telemetry 全表扫会堵死事件写入（database is locked）；
    RuntimeStore 必须 WAL + busy_timeout（与 ConversationDB/ComputeDB 一致）。"""
    store = RuntimeStore(tmp_path / "runtime.db")
    with sqlite3.connect(store.path) as con:
        mode = con.execute("PRAGMA journal_mode;").fetchone()[0]
    assert str(mode).lower() == "wal"
    with store._connect() as con:
        assert con.execute("PRAGMA busy_timeout;").fetchone()[0] == 30000


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
            payload={"yolo": True, "temperature": 0.2, "reasoning_effort": "high"},
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
    assert restored_agent.settings.reasoning_effort == "high"
    assert restored_agent.settings_revision == 1

    persisted = store.query_project_events(project.id)
    types = [e["type"] for e in persisted]
    assert "project.created" in types
    assert "agent.spawned" in types
    assert "agent.settings_changed" in types


@pytest.mark.asyncio
async def test_private_cores_share_store_without_rewinding_resumed_project_sequences(tmp_path):
    """A later private core's snapshot cannot hide an earlier project's counters."""
    store = RuntimeStore(tmp_path / "runtime.db")
    private_runs = []
    for name in ("first", "second"):
        core = RuntimeCore(strict_events=True)
        core.store = store
        bus = CommandBus(core)
        project = (await bus.execute(Command(type="project.create", payload={"name": name}))).data
        parent = (await bus.execute(Command(
            type="agent.spawn", target={"project_id": project.id},
            payload={"role_id": "coordinator"},
        ))).data
        await core.agent_host.start_run(parent)
        await core.agent_host.finish_run(parent, outcome="succeeded")
        await bus.flush_snapshot()
        private_runs.append((core, project, parent))

    first, project, parent = private_runs[0]
    old_project_seq = first.event_log.high_watermarks[project.id]
    old_session_seq = first.event_log.high_session_watermarks[parent.id]
    restored = RuntimeCore(strict_events=True)
    await asyncio.to_thread(restore_core, restored, store)
    bus = CommandBus(restored)
    await bus.execute(Command(
        type="agent.message", target={"session_id": parent.id}, payload={"content": "continue"},
    ))
    message = restored.event_log.query_session(parent.id, types={"agent.message_injected"})[-1]
    assert message.seq > old_project_seq
    assert message.session_seq > old_session_seq

    child = (await bus.execute(Command(
        type="agent.spawn", target={"project_id": project.id},
        payload={"role_id": "explorer", "parent_session_id": parent.id},
    ))).data
    await restored.agent_host.start_run(child)
    await restored.agent_host.finish_run(child, outcome="succeeded")
    terminal = restored.child_completions.terminal_by_session[child.id]
    assert terminal.data["to"] == "succeeded"
    assert terminal.seq > old_project_seq
    count, projects, sessions = await asyncio.to_thread(store.event_metadata)

    def durable_count():
        with store._connect() as con:
            return con.execute("SELECT COUNT(*) FROM events").fetchone()[0]

    assert count == await asyncio.to_thread(durable_count)
    assert projects[project.id] == restored.event_log.high_watermarks[project.id]
    assert sessions[parent.id] == restored.event_log.high_session_watermarks[parent.id]
    second, other_project, other_parent = private_runs[1]
    assert projects[other_project.id] == second.event_log.high_watermarks[other_project.id]
    assert sessions[other_parent.id] == second.event_log.high_session_watermarks[other_parent.id]


@pytest.mark.asyncio
async def test_snapshot_watermarks_exclude_unpersisted_tail(tmp_path, monkeypatch):
    """Appending during snapshot serialization must not advance its frozen cursor."""
    store = RuntimeStore(tmp_path / "runtime.db")
    core = RuntimeCore(strict_events=True)
    core.store = store
    bus = CommandBus(core)
    await bus.execute(Command(type="project.create", payload={"name": "snap"}))
    project = next(iter(core.projects.values()))
    await bus.flush_snapshot()
    persisted = dict(core.event_writer.persisted_watermarks())
    frozen = asyncio.Event()
    release = threading.Event()
    loop = asyncio.get_running_loop()
    save = store.save_snapshot

    def serialize_frozen(**kwargs):
        loop.call_soon_threadsafe(frozen.set)
        assert release.wait(5)
        save(**kwargs)

    monkeypatch.setattr(store, "save_snapshot", serialize_frozen)
    saving = asyncio.create_task(bus.flush_snapshot())
    await asyncio.wait_for(frozen.wait(), 5)
    tail = core.event_log.append(
        "agent.warning", stream="agent", project_id=project.id,
        data={"message": "unpersisted tail"},
    )
    assert core.event_log.high_watermarks[project.id] == tail.seq
    assert core.event_writer.persisted_watermarks() == persisted
    release.set()
    await saving
    monkeypatch.setattr(store, "save_snapshot", save)

    _, last_seqs = store.load_snapshot()
    assert last_seqs == persisted
    assert last_seqs[project.id] < tail.seq
    await core.event_writer.flush()
    core2 = RuntimeCore(strict_events=True)
    restore_core(core2, store)
    assert any(envelope.type == "agent.warning" for envelope in core2.event_log)


@pytest.mark.asyncio
async def test_restored_session_context_is_reused_byte_identical(tmp_path):
    """Task 4 恢复契约：会话上下文投影随快照/事件持久化；重启恢复后
    （running/waiting 仍按既有规则落 failed，本用例 agent 是 succeeded），
    显式新消息唤醒的下个 run 以恢复出的上下文为完整前缀——不悄悄换成
    摘要 seed。"""
    from cloudra.runtime_v2.agent_runner import AgentRunner
    from cloudra.runtime_v2.policies import default_stages
    from cloudra.runtime_v2.policies.base import ToolResult
    from cloudra.runtime_v2.schemas import InvocationProtocol
    from cloudra.runtime_v2.turn_pipeline import LLMResponse, TurnPipeline

    class RecordingLLM:
        def __init__(self, responses) -> None:
            self.responses = list(responses)
            self.calls: list[list[dict]] = []

        async def complete(self, agent, messages, tools, **_kwargs):
            self.calls.append(list(messages))
            return self.responses.pop(0)

    class EchoTools:
        async def execute(self, agent, call, **_kwargs):
            return ToolResult(is_success=True, summary="ok", data={})

    async def wait_succeeded(agent, timeout=5.0):
        deadline = asyncio.get_running_loop().time() + timeout
        while agent.state.value != "succeeded":
            assert asyncio.get_running_loop().time() < deadline, "agent did not finish"
            await asyncio.sleep(0.01)

    store = RuntimeStore(tmp_path / "runtime.db")
    core = RuntimeCore(strict_events=True)
    core.store = store
    core.event_hub.subscribe(lambda event: _persist_event(store, event))
    bus = CommandBus(core)
    llm1 = RecordingLLM([LLMResponse(content="first done", stop_requested=True)])
    pipeline = TurnPipeline(
        event_log=core.event_log, stages=default_stages(), llm=llm1, tools=EchoTools()
    )
    core.runner = AgentRunner(core, pipeline)
    await bus.execute(Command(type="project.create", payload={"name": "ctx"}))
    project = next(iter(core.projects.values()))
    agent = (
        await bus.execute(
            Command(
                type="agent.spawn",
                target={"project_id": project.id},
                payload={"role_id": "coordinator", "query": "solve it"},
            )
        )
    ).data
    agent.settings.invocation_protocol = InvocationProtocol.TRADITIONAL
    await wait_succeeded(agent)
    assert llm1.calls, "first run never called the LLM"
    await bus.flush_snapshot()

    # 模拟重启：同一 store 恢复新 core，接上新 runner 后用新消息唤醒。
    restored = RuntimeCore(strict_events=True)
    restore_core(restored, store)
    assert restored.session_contexts[agent.id].messages, "context projection lost across restore"
    llm2 = RecordingLLM([LLMResponse(content="second done", stop_requested=True)])
    restored_pipeline = TurnPipeline(
        event_log=restored.event_log,
        stages=default_stages(),
        llm=llm2,
        tools=EchoTools(),
    )
    restored.runner = AgentRunner(restored, restored_pipeline)
    bus2 = CommandBus(restored)
    await bus2.execute(
        Command(
            type="agent.message",
            target={"session_id": agent.id},
            payload={"content": "continue"},
        )
    )
    await wait_succeeded(restored.agents[agent.id])
    assert llm2.calls, "resumed run never called the LLM"
    first_request = llm1.calls[-1]
    resumed_request = llm2.calls[0]
    assert resumed_request[: len(first_request)] == first_request
    assert resumed_request[-1]["role"] == "user"
    assert resumed_request[-1]["content"] == "continue"


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
    run_id = await core.agent_host.start_run(agent)
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
    await core.agent_host.start_run(agent)
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
    # 重启中断是独立分类：不与 provider/科学失败混在同一统计桶（评审 5.10）。
    assert finished[-1].data["failure_kind"] == "runtime_interrupted"

    # 二次重启不再重复标记（幂等）
    again = RuntimeCore(strict_events=True)
    again.store = store
    restore_core(again, store)
    assert again.agents[agent.id].state is AgentState.FAILED
    assert len(again.event_log.query_session(agent.id, types={"run.finished"})) == len(finished)


# ------------------------------------------------------------- 跨重启子终态回传
# restore 把僵尸 running/waiting 落 failed 之外，还必须把子的终态按普通完成
# 回传送达父信箱（否则 is_wait=False 派发的父跨重启永远等不到子结果）。恢复
# 路径不 wake：succeeded 休眠父只驻留信箱，显式 resume 才开跑（issue #35）。


async def _seed_parent_with_running_child(store):
    """纯状态构造（无 runner）：父 succeeded 休眠 + 子 running 僵尸，全量落盘。"""
    from cloudra.runtime_v2.schemas import AgentState  # noqa: F401

    core = RuntimeCore(strict_events=True)
    core.store = store
    core.event_hub.subscribe(lambda event: _persist_event(store, event))
    bus = CommandBus(core)
    await bus.execute(Command(type="project.create", payload={"name": "zombie-child"}))
    project = next(iter(core.projects.values()))
    parent = (
        await bus.execute(
            Command(
                type="agent.spawn",
                target={"project_id": project.id},
                payload={"role_id": "coordinator"},
            )
        )
    ).data
    child = (
        await bus.execute(
            Command(
                type="agent.spawn",
                target={"project_id": project.id},
                payload={
                    "role_id": "explorer",
                    "parent_session_id": parent.id,
                    "query": "long running task",
                },
            )
        )
    ).data
    # 父跑完一轮正常休眠；子仍在跑（进程此刻"崩溃"）。
    await core.agent_host.start_run(parent)
    await core.agent_host.finish_run(parent, outcome="succeeded")
    await core.agent_host.start_run(child)
    for event in list(core.event_log):
        await _persist_event(store, event)
    store.save_snapshot(
        projects=core.projects,
        agents=core.agents,
        roles=core.roles._roles,
        runtime_defaults=core.runtime_defaults,
        last_seqs=core.event_log.high_watermarks,
    )
    return core, project, parent, child


@pytest.mark.asyncio
async def test_restore_delivers_zombie_child_failure_to_parent(tmp_path):
    """跨重启通知丢失（P0）：子 agent 随进程死掉时，restore 落 failed 之外
    必须把终态送达父信箱；通知文本明示是重启收尾（state=failed +
    interrupted by process restart），不是正常完成。休眠父不自动 wake
    （issue #35：重启不得把 succeeded 协调者打进 LLM）。"""
    from cloudra.runtime_v2.schemas import AgentState

    store = RuntimeStore(tmp_path / "runtime.db")
    _, project, parent, child = await _seed_parent_with_running_child(store)

    restored = RuntimeCore(strict_events=True)
    restored.store = store
    restore_core(restored, store)

    rchild = restored.agents[child.id]
    rparent = restored.agents[parent.id]
    assert rchild.state is AgentState.FAILED
    # 父收到子失败通知：durable 事件 + 信箱驻留。
    reports = [
        e
        for e in restored.event_log.query_session(parent.id, types={"agent.message_injected"})
        if child.id in str(e.data.get("content", ""))
    ]
    assert reports, "restore must deliver the zombie child's terminal state to the parent"
    body = reports[-1].data["content"]
    assert "[Sub-agent finished]" in body
    assert "state=failed" in body
    assert "interrupted by process restart" in body
    inbox = restored.mailbox.inbox(parent.id)
    assert inbox is not None and inbox.qsize() == 1
    # 恢复路径 park-don't-wake：succeeded 父保持休眠，信箱里的子终态等
    # 显式 resume 再读（issue #35）。
    assert rparent.state is AgentState.SUCCEEDED
    assert (
        len(
            [
                e
                for e in restored.event_log.query_session(parent.id)
                if e.type == "run.started"
            ]
        )
        == 1
    )
    persisted = store.query_project_events(project.id)
    assert any(
        row["type"] == "agent.message_injected" and child.id in row["data"]
        for row in persisted
    )


@pytest.mark.asyncio
async def test_restore_parks_zombie_child_notification_when_parent_also_zombie(tmp_path):
    """父子同为僵尸：两者都被 restore 落 failed；子的通知照常投递父信箱
    驻留（parked），但不唤醒 failed 的父（failed 绝不自动复活）。"""
    from cloudra.runtime_v2.schemas import AgentState

    store = RuntimeStore(tmp_path / "runtime.db")
    core, project, parent, child = await _seed_parent_with_running_child(store)
    # 把父也变成 running 僵尸：在已休眠的父上再起一个 run，补落盘+快照。
    await core.agent_host.start_run(parent)
    for event in list(core.event_log):
        await _persist_event(store, event)
    store.save_snapshot(
        projects=core.projects,
        agents=core.agents,
        roles=core.roles._roles,
        runtime_defaults=core.runtime_defaults,
        last_seqs=core.event_log.high_watermarks,
    )
    parent_runs_before = len(
        [e for e in core.event_log.query_session(parent.id) if e.type == "run.started"]
    )

    restored = RuntimeCore(strict_events=True)
    restored.store = store
    restore_core(restored, store)

    rparent = restored.agents[parent.id]
    assert restored.agents[child.id].state is AgentState.FAILED
    assert rparent.state is AgentState.FAILED  # parked：不唤醒
    runs = [e for e in restored.event_log.query_session(parent.id) if e.type == "run.started"]
    assert len(runs) == parent_runs_before  # 没有 reopen 新 run
    reports = [
        e
        for e in restored.event_log.query_session(parent.id, types={"agent.message_injected"})
        if child.id in str(e.data.get("content", ""))
    ]
    assert reports, "notification must still be parked in the failed parent's mailbox"
    inbox = restored.mailbox.inbox(parent.id)
    assert inbox is not None and inbox.qsize() == 1


@pytest.mark.asyncio
async def test_restore_parks_zombie_child_until_explicit_resume(tmp_path):
    """生产路径 runner 已装时，restore 也不得把休眠父打进 LLM（issue #35）。
    子失败通知驻留信箱；显式 message 才开跑并消费。"""
    from cloudra.runtime_v2.adapters import LegacyToolExecutor
    from cloudra.runtime_v2.agent_runner import AgentRunner
    from cloudra.runtime_v2.policies import default_stages
    from cloudra.runtime_v2.schemas import AgentState
    from cloudra.runtime_v2.turn_pipeline import LLMResponse, TurnPipeline

    class StopLLM:
        def __init__(self) -> None:
            self.calls = 0

        async def complete(self, agent, messages, tools, **_kwargs):
            self.calls += 1
            return LLMResponse(content="ack child failure", stop_requested=True)

    store = RuntimeStore(tmp_path / "runtime.db")
    _, project, parent, child = await _seed_parent_with_running_child(store)

    restored = RuntimeCore(strict_events=True)
    restored.store = store
    llm = StopLLM()
    pipeline = TurnPipeline(
        event_log=restored.event_log,
        stages=default_stages(),
        llm=llm,
        tools=LegacyToolExecutor(restored),
    )
    restored.runner = AgentRunner(restored, pipeline)
    restore_core(restored, store)

    rparent = restored.agents[parent.id]
    assert rparent.state is AgentState.SUCCEEDED
    assert llm.calls == 0
    inbox = restored.mailbox.inbox(rparent.id)
    assert inbox is not None and inbox.qsize() == 1
    await asyncio.sleep(0.05)
    assert rparent.state is AgentState.SUCCEEDED
    assert llm.calls == 0

    bus = CommandBus(restored)
    try:
        await bus.execute(
            Command(
                type="agent.message",
                target={"session_id": rparent.id},
                payload={"content": "resume after restart"},
            )
        )
        deadline = asyncio.get_running_loop().time() + 10.0
        while rparent.state.value != "succeeded" or llm.calls == 0:
            if asyncio.get_running_loop().time() > deadline:
                raise AssertionError(
                    f"parent stuck in {rparent.state.value} after explicit resume "
                    f"(llm.calls={llm.calls})"
                )
            await asyncio.sleep(0.01)
        emitted = [
            e
            for e in restored.event_log.query_session(rparent.id, types={"agent.message_emitted"})
            if "ack child failure" in str(e.data.get("content", ""))
        ]
        assert emitted, "explicit resume must run a turn and consume the parked notification"
        assert llm.calls >= 1
    finally:
        await restored.runner.cancel_all()


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
    original_write = store.write_snapshot_payload

    def counting_write(payload, last_seqs):
        nonlocal saves
        saves += 1
        return original_write(payload, last_seqs)

    monkeypatch.setattr(store, "write_snapshot_payload", counting_write)

    await bus.execute(Command(type="project.create", payload={"name": "throttle"}))
    project = next(iter(core.projects.values()))
    # 低于阈值：不落快照
    assert saves == 0

    # 无快照恢复：纯事件重放依然等价（缓存不是权威的直接证据）
    core2 = RuntimeCore(strict_events=True)
    restore_core(core2, store)
    assert core2.projects[project.id].name == "throttle"
    # Restore seeds the derived cache once; command throttling starts here.
    saves = 0

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


@pytest.mark.asyncio
async def test_legacy_auto_pending_reviews_not_consumed_after_restore(tmp_path):
    """§5 历史兼容：升级前的自动 pending review（source=legacy_auto 或无标记
    旧行）恢复后不进入可消费信箱、审计保留；Coordinator 收到一次性提示
    （pin 幂等，重复调用/重启不重复轰炸）；显式重提才成为可消费待办。"""
    import uuid
    from datetime import datetime, timezone

    from cloudra.dag.models import CallReview
    from cloudra.dag.store import DagStore
    from cloudra.persistence.database import ConversationDB
    from cloudra.runtime_v2.supervision import (
        LEGACY_BACKLOG_PIN_KEY,
        pending_supervision_summary,
        reconcile_legacy_backlog_notice,
    )

    core = RuntimeCore(strict_events=True)
    bus = CommandBus(core)
    project = (
        await bus.execute(Command(type="project.create", payload={"name": "legacy-inbox"}))
    ).data
    coordinator = (
        await bus.execute(
            Command(
                type="agent.spawn",
                target={"project_id": project.id},
                payload={"role_id": "coordinator"},
            )
        )
    ).data

    def _seed() -> None:
        db = ConversationDB(project.id).init()
        store = DagStore(db)
        store.ensure_bundle("s1")
        now = datetime.now(timezone.utc).isoformat()
        # 历史自动行（显式标记 legacy_auto）
        store.enqueue_call_review(
            CallReview(
                review_id="rev_" + uuid.uuid4().hex,
                tool_call_id="tc_old1",
                tool_name="log_parser",
                is_success=True,
                source="legacy_auto",
                state="pending",
                created_at=now,
            )
        )
        # 显式送审行（唯一可消费来源）
        store.enqueue_call_review(
            CallReview(
                review_id="rev_" + uuid.uuid4().hex,
                tool_call_id="tc_new",
                tool_name="log_parser",
                is_success=True,
                suggested_target_id="step1",
                suggested_stage="ts_opt",
                claim="explicit claim",
                evidence_id="ev_x",
                source="explicit",
                state="pending",
                created_at=now,
            )
        )
        # 无标记旧行：直接 SQL 插入，source 列取库级默认值（legacy_auto）。
        with db.connect() as con:
            con.execute(
                "INSERT INTO dag_call_reviews("
                "review_id, tool_name, is_success, state, created_at"
                ") VALUES ('rev_unmarked', 'log_parser', 1, 'pending', ?)",
                (now,),
            )

    await asyncio.to_thread(_seed)

    summary = await pending_supervision_summary(project.id)
    assert summary["call_reviews"] == 1  # 只有 explicit 可消费
    assert summary["legacy_call_reviews"] == 2

    # store 读路径同样只把 explicit 当可消费；历史行保留（审计）。
    def _read() -> tuple[int, int]:
        store = DagStore(ConversationDB(project.id))
        consumable = store.list_call_reviews("pending", source="explicit")
        everything = store.list_call_reviews("pending")
        return len(consumable), len(everything)

    n_consumable, n_all = await asyncio.to_thread(_read)
    assert (n_consumable, n_all) == (1, 3)

    # 一次性提示：pin 进 Coordinator 上下文；重复调用幂等（无新事件）。
    await reconcile_legacy_backlog_notice(core, project.id)
    pin_events = [
        e
        for e in core.event_log
        if e.type == "context.pin_set" and e.data.get("key") == LEGACY_BACKLOG_PIN_KEY
    ]
    assert len(pin_events) == 1
    await reconcile_legacy_backlog_notice(core, project.id)
    pin_events_again = [
        e
        for e in core.event_log
        if e.type == "context.pin_set" and e.data.get("key") == LEGACY_BACKLOG_PIN_KEY
    ]
    assert len(pin_events_again) == 1
    pins = core.notices._pins.get(coordinator.id, {})
    assert "2" in pins[LEGACY_BACKLOG_PIN_KEY]

    # 重启（pin 从事件投影恢复）后再 reconcile 也不重复发事件。
    core.notices.restore_from(core.event_log)
    await reconcile_legacy_backlog_notice(core, project.id)
    assert len([e for e in core.event_log
                if e.type == "context.pin_set"
                and e.data.get("key") == LEGACY_BACKLOG_PIN_KEY]) == 1

    # 历史行被处置（裁决/显式重提后关闭）后，提示撤下。
    def _close_legacy() -> None:
        store = DagStore(ConversationDB(project.id))
        for row in store.list_call_reviews("pending"):
            if row.source != "explicit":
                store.mark_call_review(row.review_id, "reviewed")

    await asyncio.to_thread(_close_legacy)
    await reconcile_legacy_backlog_notice(core, project.id)
    assert LEGACY_BACKLOG_PIN_KEY not in core.notices._pins.get(coordinator.id, {})
    summary = await pending_supervision_summary(project.id)
    assert summary["legacy_call_reviews"] == 0
    assert summary["call_reviews"] == 1  # 显式待办不受影响


# ------------------------------------------------------------- Task 4 · 恢复矩阵
# 督导恢复用例（runner-less 纯投影层；需要 runner/LLM 的恢复用例在
# tests/test_runtime_v2_supervision.py）。


async def _seed_structured_request(project_id: str, requester: str, *, question: str) -> str:
    """结构化督导请求的持久化等价物（basis 与 review_basis 对齐）。"""
    from cloudra.dag.review_requests import ReviewRequest
    from cloudra.dag.store import DagStore
    from cloudra.persistence.database import ConversationDB

    def _write() -> str:
        store = DagStore(ConversationDB(project_id).init())
        store.ensure_bundle("s1")
        draft = ReviewRequest(
            kind="evidence",
            requester=requester,
            question=question,
            basis_fingerprint="placeholder",
        )
        basis = store.review_basis(draft)
        return store.enqueue_review(draft.model_copy(update={"basis_fingerprint": basis}))

    return await asyncio.to_thread(_write)


def _replay_all_events(store: RuntimeStore):
    """纯重放路径：空 core + 全量事件逐条 apply_event（不经过快照）。"""
    from cloudra.runtime_v2.apply import apply_event
    from cloudra.runtime_v2.schemas import EventEnvelope

    core = RuntimeCore(strict_events=True)
    envelopes = [EventEnvelope.model_validate(raw) for raw in store.events_after({})]
    core.event_log.restore(envelopes)
    for envelope in envelopes:
        apply_event(core, envelope)
    core.notices.restore_from(core.event_log)
    return core


@pytest.mark.asyncio
async def test_cancelled_supervisor_not_revived_by_reconcile_after_restart(tmp_path):
    """恢复矩阵·用户取消后重启进程：cancelled 不是僵尸 running——restore
    原样保留取消终态，reconcile 不复活，也不重投取消时遗留的普通通知。
    科学待办留在 DAG 存储，Coordinator 收到一次性显式恢复告警。"""
    from cloudra.runtime_v2.schemas import AgentState
    from cloudra.runtime_v2.supervision import (
        find_project_supervisor,
        notify_supervisor,
        reconcile_supervision,
    )

    store = RuntimeStore(tmp_path / "runtime.db")
    core1 = RuntimeCore(strict_events=True)
    core1.store = store
    bus1 = CommandBus(core1)
    project = (
        await bus1.execute(
            Command(
                type="project.create",
                payload={"name": "cancel-restart", "settings": {"orchestration_mode": "dag_guided"}},
            )
        )
    ).data
    coordinator = (
        await bus1.execute(
            Command(
                type="agent.spawn",
                target={"project_id": project.id},
                payload={"role_id": "coordinator"},
            )
        )
    ).data
    request_id = await _seed_structured_request(
        project.id, coordinator.id, question="survives cancel + restart"
    )
    await notify_supervisor(core1, project.id, reason="explicit evidence submission")
    supervisor1 = find_project_supervisor(core1, project.id)
    assert supervisor1 is not None
    await bus1.execute(
        Command(type="agent.cancel", target={"session_id": supervisor1.id}, payload={})
    )
    assert supervisor1.state.value == "cancelled"

    # 进程重启：取消终态原样恢复（不是僵尸收尾）。
    core2 = RuntimeCore(strict_events=True)
    core2.store = store
    restore_core(core2, store)
    supervisor2 = core2.agents[supervisor1.id]
    assert supervisor2.state is AgentState.CANCELLED

    events_before = len(core2.event_log)
    await reconcile_supervision(core2, project.id, auto_wake=False)
    # Recovery discards ordinary unread messages for cancelled sessions. The
    # durable work fingerprint still prevents duplicate notification/revival.
    # D2：cancelled 督导 + 可消费待办同时给 Coordinator 发
    # 一次性告警（pin + mailbox；告警不复活督导，点名显式恢复入口）。
    from cloudra.runtime_v2.supervision import TERMINAL_SUPERVISOR_PIN_KEY

    new_events = list(core2.event_log)[events_before:]
    supervisor_events = [e for e in new_events if e.session_id == supervisor2.id]
    assert supervisor_events == []
    assert supervisor2.state is AgentState.CANCELLED
    inbox = core2.mailbox.inbox(supervisor2.id)
    assert inbox is not None and inbox.empty()
    assert not any(event.session_id == supervisor2.id for event in core2.mailbox.unread())
    assert any(
        e.type == "context.pin_set"
        and e.session_id == coordinator.id
        and e.data.get("key") == TERMINAL_SUPERVISOR_PIN_KEY
        for e in new_events
    )
    assert any(
        e.type == "agent.message_injected"
        and e.session_id == coordinator.id
        and "[Supervision] ALERT" in str(e.data.get("content", ""))
        for e in new_events
    )

    # 持久化待办不丢。
    from cloudra.dag.store import DagStore
    from cloudra.persistence.database import ConversationDB

    queued = await asyncio.to_thread(
        lambda: [r.request_id for r in DagStore(ConversationDB(project.id)).list_review_requests("queued")]
    )
    assert queued == [request_id]


@pytest.mark.asyncio
async def test_replay_and_restore_have_no_supervision_side_effects(tmp_path):
    """恢复矩阵·重放零副作用：事件重放绝不产生任何副作用；restore 只做
    确定性的中断收尾——僵尸落 failed；Supervisor 不发普通子任务回报，
    科学待办由 reconcile 的专用持久通知显式告警。不 spawn（记录之外的）agent、
    不跑 LLM/工具。reconcile 是 restore 之后的显式步骤，对僵尸收尾落
    failed 的 supervisor 只 parked 投递、不唤醒。"""
    from cloudra.runtime_v2.schemas import AgentState
    from cloudra.runtime_v2.supervision import (
        find_project_supervisor,
        notify_supervisor,
        reconcile_supervision,
    )

    store = RuntimeStore(tmp_path / "runtime.db")
    core1 = RuntimeCore(strict_events=True)
    core1.store = store
    bus1 = CommandBus(core1)
    project = (
        await bus1.execute(
            Command(
                type="project.create",
                payload={"name": "replay-purity", "settings": {"orchestration_mode": "dag_guided"}},
            )
        )
    ).data
    coordinator = (
        await bus1.execute(
            Command(
                type="agent.spawn",
                target={"project_id": project.id},
                payload={"role_id": "coordinator"},
            )
        )
    ).data
    await _seed_structured_request(project.id, coordinator.id, question="pending at crash")
    await notify_supervisor(core1, project.id, reason="explicit evidence submission")
    supervisor1 = find_project_supervisor(core1, project.id)
    assert supervisor1 is not None and supervisor1.state.value == "running"

    # 纯重放：状态与"restore 前"的活 core 一致（僵尸仍 running），零副作用。
    replayed = _replay_all_events(store)
    assert replayed.agents[supervisor1.id].state is AgentState.RUNNING
    assert {a.id for a in replayed.agents.values()} == {
        a.id for a in core1.agents.values()
    }  # 重放不新增 agent

    # restore：僵尸 running → failed（中断收尾），Supervisor 不发普通子回报。
    # coordinator 是 queued，restore 不唤醒。新落盘的事件只许
    # 是这一族，绝无任何执行痕迹。
    persisted_before = {row["event_id"] for row in store.query_project_events(project.id)}
    core2 = RuntimeCore(strict_events=True)
    core2.store = store
    restore_core(core2, store)
    supervisor2 = core2.agents[supervisor1.id]
    assert supervisor2.state is AgentState.FAILED
    new_rows = [
        row
        for row in store.query_project_events(project.id)
        if row["event_id"] not in persisted_before
    ]
    new_types = {row["type"] for row in new_rows}
    assert new_types <= {
        "agent.state_changed",
        "run.finished",
        "agent.message_injected",
        "run.started",
        "agent.context_reset",
    }, new_types
    reports = [
        e
        for e in core2.event_log.query_session(coordinator.id, types={"agent.message_injected"})
        if supervisor1.id in str(e.data.get("content", ""))
    ]
    assert reports == []
    assert core2.agents[coordinator.id].state is AgentState.QUEUED  # 恢复不 wake

    # 收尾+回传事件已回写 store：纯重放与 restored 逐字段全等。
    replayed_post = _replay_all_events(store)
    assert replayed_post.agents[supervisor1.id].model_dump(
        mode="json"
    ) == supervisor2.model_dump(mode="json")
    assert replayed_post.agents[coordinator.id].model_dump(
        mode="json"
    ) == core2.agents[coordinator.id].model_dump(mode="json")

    # reconcile 对 failed 只 parked 投递不唤醒；全事件流无任何工具/LLM 执行痕迹。
    await reconcile_supervision(core2, project.id, auto_wake=False)
    assert supervisor2.state is AgentState.FAILED
    assert core2.agents[coordinator.id].state is AgentState.QUEUED
    alerts = [
        event for event in core2.event_log.query_session(coordinator.id, types={"agent.message_injected"})
        if str(event.data.get("content", "")).startswith("[Supervision] ALERT")
    ]
    assert len(alerts) == 1
    assert alerts[0].data["sender"] == "system"
    assert not [event for event in core2.event_log.query_session(coordinator.id, types={"agent.message_injected"})
                if event.data.get("manifest", {}).get("kind") == "child_completion"]
    executed = [
        e
        for e in core2.event_log
        if e.type in {"tool.requested", "tool.started", "llm.requested"}
    ]
    assert executed == []


@pytest.mark.asyncio
async def test_reconcile_after_restore_only_schedules_notification_events(tmp_path):
    """恢复矩阵·只安排通知：正常休眠（succeeded）的 supervisor 恢复后，
    reconcile 默认仍会 wake（在线补通知契约）；API 装载路径必须传
    auto_wake=False，只产生投递事件、保持 succeeded，无 LLM/工具执行。"""
    from cloudra.runtime_v2.schemas import AgentState
    from cloudra.runtime_v2.supervision import reconcile_supervision

    store = RuntimeStore(tmp_path / "runtime.db")
    core1 = RuntimeCore(strict_events=True)
    core1.store = store
    bus1 = CommandBus(core1)
    project = (
        await bus1.execute(
            Command(
                type="project.create",
                payload={"name": "reconcile-schedule", "settings": {"orchestration_mode": "dag_guided"}},
            )
        )
    ).data
    coordinator = (
        await bus1.execute(
            Command(
                type="agent.spawn",
                target={"project_id": project.id},
                payload={"role_id": "coordinator"},
            )
        )
    ).data
    supervisor1 = (
        await bus1.execute(
            Command(
                type="agent.spawn",
                target={"project_id": project.id},
                payload={
                    "role_id": "supervisor",
                    "parent_session_id": coordinator.id,
                    "settings": {"orchestration_mode": "dag_guided"},
                },
            )
        )
    ).data
    # 手动驱动到 succeeded（正常休眠）并落盘。
    await core1.agent_host.start_run(supervisor1)
    await core1.agent_host.finish_run(supervisor1, outcome="succeeded")
    await core1.event_writer.flush()
    await _seed_structured_request(project.id, coordinator.id, question="notify me after restart")

    core2 = RuntimeCore(strict_events=True)
    core2.store = store
    restore_core(core2, store)
    supervisor2 = core2.agents[supervisor1.id]
    assert supervisor2.state is AgentState.SUCCEEDED  # 休眠不是尸体，不收尾

    events_before = len(core2.event_log)
    await reconcile_supervision(core2, project.id, auto_wake=False)
    new_types = {e.type for e in list(core2.event_log)[events_before:]}
    assert new_types <= {
        "agent.message_injected",
        "context.pin_set",
        "context.pin_cleared",
    }, new_types
    # 装载路径不 wake：督导保持休眠，信箱驻留。
    assert supervisor2.state is AgentState.SUCCEEDED
    inbox = core2.mailbox.inbox(supervisor2.id)
    assert inbox is not None and inbox.qsize() == 1
    assert not [
        e
        for e in list(core2.event_log)[events_before:]
        if e.type.startswith(("tool.", "llm.")) or e.type in {"run.started", "agent.state_changed"}
    ]


def test_store_connect_closes_connection_without_fd_leak(tmp_path):
    """RuntimeStore._connect 必须在 with 块退出后显式关闭连接，
    不能依赖 GC，避免长期运行中持续泄漏文件描述符导致 Too many open files (Errno 24)。"""
    store = RuntimeStore(tmp_path / "runtime.db")
    # 连续调用 300 次（超越 macOS 默认软限制 256）
    for _ in range(300):
        with store._connect() as con:
            row = con.execute("SELECT 1").fetchone()
            assert row[0] == 1


@pytest.mark.asyncio
async def test_double_restart_preserves_unconsumed_inbox_messages(tmp_path):
    """跨多次重启信箱恢复：未进入上下文投影的 agent.message_injected 在多次崩溃后依然驻留信箱。"""
    store = RuntimeStore(tmp_path / "runtime.db")
    core1 = RuntimeCore(strict_events=True)
    core1.store = store
    bus1 = CommandBus(core1)
    project = (
        await bus1.execute(
            Command(type="project.create", payload={"name": "multi-crash"})
        )
    ).data
    agent = (
        await bus1.execute(
            Command(
                type="agent.spawn",
                target={"project_id": project.id},
                payload={"role_id": "coordinator"},
            )
        )
    ).data

    # 注入一条消息（但未消费进 context）
    await bus1.execute(
        Command(
            type="agent.message",
            target={"session_id": agent.id},
            payload={"content": "hello across crash 1 and 2"},
        )
    )

    # 第一次重启
    core2 = RuntimeCore(strict_events=True)
    core2.store = store
    restore_core(core2, store)
    inbox2 = core2.mailbox.inbox(agent.id)
    assert inbox2 is not None and inbox2.qsize() == 1

    # 第二次重启（未唤醒消费的前提下再次重启）
    core3 = RuntimeCore(strict_events=True)
    core3.store = store
    restore_core(core3, store)
    inbox3 = core3.mailbox.inbox(agent.id)
    assert inbox3 is not None and inbox3.qsize() == 1
    msg = inbox3.get_nowait()
    assert msg["content"] == "hello across crash 1 and 2"


