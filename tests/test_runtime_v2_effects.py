"""decide/effect 分离（3b）：效果执行顺序、decide 纯度、拒绝审计轨迹。

- 四拍拍序：事件 append+publish+persist 与 apply 都先于 effects；
  effects 内部按 decide 声明顺序执行（EnsureDir/DeliverMessage 先于
  ScheduleAgent——runner 启动前工作区与 inbox 必须就绪）。
- decide 是纯函数：不落事件、不改状态、不碰文件系统。
- 拒绝路径：decide 挂在 CommandRejected.events 上的领域审计草稿
  （spawn_requested/spawn_rejected）随 command.rejected 一起落日志、
  发布并持久化（旧实现只落内存日志，重启即丢）。
"""

from __future__ import annotations

import asyncio

import pytest

from cloudra.runtime_v2 import commands as commands_mod
from cloudra.runtime_v2.commands import DECIDERS, CommandBus
from cloudra.runtime_v2.core import RuntimeCore
from cloudra.runtime_v2.effects import DeliverMessage, EnsureDir, ScheduleAgent
from cloudra.runtime_v2.persistence import RuntimeStore
from cloudra.runtime_v2.schemas import Command, CommandRejected


class FakeRunner:
    def __init__(self) -> None:
        self.scheduled: list[str] = []
        self.cancelled: list[str] = []

    def schedule(self, session_id: str) -> None:
        self.scheduled.append(session_id)

    async def cancel(self, session_id: str) -> None:
        self.cancelled.append(session_id)


async def _persist_event(store: RuntimeStore, event) -> None:
    await asyncio.to_thread(store.append_event, event)


def _spy_timeline(core: RuntimeCore, monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str]]:
    """合并时间线：("event", type) 来自 hub 发布，("effect", ClassName) 来自效果执行。"""
    timeline: list[tuple[str, str]] = []

    async def collect(envelope) -> None:
        timeline.append(("event", envelope.type))

    core.event_hub.subscribe(collect)

    original = commands_mod._execute_effect

    async def spy(core_, effect):
        timeline.append(("effect", type(effect).__name__))
        await original(core_, effect)

    monkeypatch.setattr(commands_mod, "_execute_effect", spy)
    return timeline


@pytest.mark.asyncio
async def test_effects_run_after_events_and_state_in_declared_order(tmp_path, monkeypatch):
    core = RuntimeCore(strict_events=True)
    runner = FakeRunner()
    core.runner = runner
    bus = CommandBus(core)
    timeline = _spy_timeline(core, monkeypatch)

    ws = tmp_path / "ws"
    await bus.execute(
        Command(type="project.create", payload={"name": "fx", "workspace_dir": str(ws)})
    )
    project = next(iter(core.projects.values()))
    # 事件先于效果；EnsureDir 是 create 的唯一效果
    assert timeline == [("event", "project.created"), ("effect", "EnsureDir")]
    assert ws.is_dir()

    timeline.clear()
    result = await bus.execute(
        Command(
            type="agent.spawn",
            target={"project_id": project.id},
            payload={"role_id": "coordinator", "query": "hello fx"},
        )
    )
    agent = result.data
    # 全部事件（因果序：spawned 先于 message_injected）先于任何效果；
    # 效果按 decide 声明顺序：DeliverMessage 先于 ScheduleAgent。
    assert timeline == [
        ("event", "agent.spawn_requested"),
        ("event", "agent.spawned"),
        ("event", "agent.message_injected"),
        ("effect", "DeliverMessage"),
        ("effect", "ScheduleAgent"),
    ]
    # 状态先于效果：runner 收到调度时 agent 已在 core.agents（apply 已过）
    assert runner.scheduled == [agent.id]
    assert core.require_agent(agent.id) is agent
    # inbox 载荷与事件载荷的 message_id 一致
    injected = [e for e in core.event_log if e.type == "agent.message_injected"][-1]
    queued = core.mailbox.inbox(agent.id).get_nowait()
    assert queued["message_id"] == injected.data["message_id"]
    assert queued["content"] == "hello fx"


@pytest.mark.asyncio
async def test_cancel_effects_and_idempotent_noop(tmp_path, monkeypatch):
    core = RuntimeCore(strict_events=True)
    runner = FakeRunner()
    core.runner = runner
    bus = CommandBus(core)
    timeline = _spy_timeline(core, monkeypatch)

    await bus.execute(Command(type="project.create", payload={"name": "c"}))
    project = next(iter(core.projects.values()))
    agent = (
        await bus.execute(
            Command(type="agent.spawn", target={"project_id": project.id}, payload={"role_id": "coordinator"})
        )
    ).data
    await core.agent_host.start_run(agent)

    timeline.clear()
    result = await bus.execute(
        Command(type="agent.cancel", target={"session_id": agent.id}, payload={"message": "stop"})
    )
    assert result.data.state == "cancelled"
    assert timeline == [
        # start_run 走 persist-then-apply：state_changed / run.started 在调用时
        # 就已落盘并发布，不再有"积压到下一个命令才顺带发布"的尾巴。
        ("event", "agent.cancel_requested"),
        ("event", "agent.message_injected"),
        ("event", "agent.state_changed"),
        ("event", "agent.cancelled"),
        ("effect", "DeliverMessage"),
        # 取消级联（C2）：先停 launch group，再取消父/子的 run。
        ("effect", "CancelLaunchGroups"),
        ("effect", "CancelRunner"),
    ]
    assert runner.cancelled == [agent.id]

    # 已 cancelled：幂等 no-op——零事件、零效果、event_id 为空
    timeline.clear()
    again = await bus.execute(Command(type="agent.cancel", target={"session_id": agent.id}, payload={}))
    assert again.accepted is True
    assert again.event_id == ""
    assert timeline == []


@pytest.mark.asyncio
async def test_cancel_decides_background_parked_once(tmp_path, monkeypatch):
    """background parked 判定在一条 cancel 命令里只求值一次。

    它要扫事件日志，且下游「拒绝」与「级联」两条路径必须看同一个值——两处各判
    一次是判据漂移的入口。
    """
    from cloudra.runtime_v2 import commands as commands_module

    core = RuntimeCore(strict_events=True)
    core.runner = FakeRunner()
    bus = CommandBus(core)
    await bus.execute(Command(type="project.create", payload={"name": "c"}))
    project = next(iter(core.projects.values()))
    agent = (
        await bus.execute(
            Command(
                type="agent.spawn",
                target={"project_id": project.id},
                payload={"role_id": "coordinator"},
            )
        )
    ).data

    calls: list[str] = []
    real = commands_module.is_background_parked

    def counting(core_arg, agent_arg):
        calls.append(agent_arg.id)
        return real(core_arg, agent_arg)

    monkeypatch.setattr(commands_module, "is_background_parked", counting)
    await bus.execute(Command(type="agent.cancel", target={"session_id": agent.id}))
    assert calls == [agent.id]


@pytest.mark.asyncio
async def test_decide_is_pure_no_io_no_mutation(tmp_path):
    """decide 零 IO、零 mutate：不调 bus 直接调 decider，世界必须纹丝不动。"""
    core = RuntimeCore(strict_events=True)
    bus = CommandBus(core)
    await bus.execute(Command(type="project.create", payload={"name": "host"}))
    project = next(iter(core.projects.values()))
    agent = (
        await bus.execute(
            Command(
                type="agent.spawn",
                target={"project_id": project.id},
                payload={"role_id": "coordinator"},
            )
        )
    ).data

    projects_before = dict(core.projects)
    agents_before = dict(core.agents)
    log_len = len(core.event_log)
    ws = tmp_path / "not-created"

    decision = DECIDERS["project.create"](
        core,
        Command(type="project.create", payload={"name": "pure", "workspace_dir": str(ws)}),
    )
    assert decision.effects == (EnsureDir(str(ws)),)
    assert not ws.exists()  # EnsureDir 只是描述，未执行

    spawn_decision = DECIDERS["agent.spawn"](
        core,
        Command(
            type="agent.spawn",
            target={"project_id": project.id},
            payload={"role_id": "researcher", "query": "q"},
        ),
    )
    assert [d.type for d in spawn_decision.events] == [
        "agent.spawn_requested",
        "agent.spawned",
        "agent.message_injected",
    ]
    assert [type(e).__name__ for e in spawn_decision.effects] == ["DeliverMessage", "ScheduleAgent"]

    # RUNNING agent 的 message：只有投递，无 wake 草稿、无 ScheduleAgent
    await core.agent_host.start_run(agent)
    log_len = len(core.event_log)
    running_decision = DECIDERS["agent.message"](
        core,
        Command(type="agent.message", target={"session_id": agent.id}, payload={"content": "hi"}),
    )
    assert [d.type for d in running_decision.events] == ["agent.message_injected"]
    assert running_decision.effects and isinstance(running_decision.effects[0], DeliverMessage)
    assert not any(isinstance(e, ScheduleAgent) for e in running_decision.effects)

    # 守卫在 decide 抛错，同样零副作用
    with pytest.raises(CommandRejected):
        DECIDERS["agent.restart"](
            core, Command(type="agent.restart", target={"session_id": agent.id}, payload={})
        )

    assert len(core.event_log) == log_len
    assert dict(core.projects) == projects_before
    assert dict(core.agents) == agents_before or set(core.agents) == set(agents_before)
    assert core.agents[agent.id].state.value == "running"


@pytest.mark.asyncio
async def test_rejection_appends_audit_drafts_and_persists(tmp_path):
    """拒绝轨迹（spawn_requested/spawn_rejected）随 command.rejected 落日志、
    发布、持久化——旧实现只进内存日志，重启即丢。"""
    store = RuntimeStore(tmp_path / "runtime.db")
    core = RuntimeCore(strict_events=True)
    core.store = store
    core.event_hub.subscribe(lambda event: _persist_event(store, event))
    bus = CommandBus(core)
    published: list[str] = []

    async def collect(envelope) -> None:
        published.append(envelope.type)

    core.event_hub.subscribe(collect)

    await bus.execute(Command(type="project.create", payload={"name": "rej"}))
    project = next(iter(core.projects.values()))
    result = await bus.execute(
        Command(type="agent.spawn", target={"project_id": project.id}, payload={"role_id": "nope"})
    )
    assert result.accepted is False
    assert result.data["error"]["code"] == "not_found"

    types = [e.type for e in core.event_log]
    assert types[-3:] == ["agent.spawn_requested", "agent.spawn_rejected", "command.rejected"]
    assert published[-3:] == ["agent.spawn_requested", "agent.spawn_rejected", "command.rejected"]
    persisted = [e["type"] for e in store.query_project_events(project.id)]
    assert "agent.spawn_requested" in persisted
    assert "agent.spawn_rejected" in persisted
    assert "command.rejected" in persisted
