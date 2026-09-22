"""Agent 间消息的唯一提交入口（评审 5.2）：持久化先于可见、唤醒策略集中。

验收对应：
- 事件持久化失败时目标 inbox 不出现消息、目标 agent 不 wake；
- 持久化成功但未消费的消息，重启后由事件重建进 inbox（不依赖任何 flush）；
- 唤醒纪律由 WakePolicy 唯一解析（四种策略的允许/拒绝状态逐个断言）；
- Mailbox.deliver 已删除：不存在「先入队、事后 flush」的第二条语义。
"""

from __future__ import annotations

import pytest

from cloudra.runtime_v2.commands import CommandBus
from cloudra.runtime_v2.core import RuntimeCore
from cloudra.runtime_v2.dispatcher import (
    MessageDispatcher,
    WakePolicy,
    latest_state_reason,
    should_wake,
)
from cloudra.runtime_v2.mailbox import Mailbox
from cloudra.runtime_v2.persistence import RuntimeStore, restore_core
from cloudra.runtime_v2.schemas import AgentState, Command


class _BrokenStore:
    """append_event 永远失败：模拟磁盘/权限故障。"""

    def __init__(self) -> None:
        self.calls = 0

    def append_event(self, envelope) -> None:
        self.calls += 1
        raise OSError("disk is on fire")


async def _core_with_coordinator(*, store=None) -> tuple[RuntimeCore, object]:
    core = RuntimeCore(strict_events=True)
    bus = CommandBus(core)
    await bus.execute(Command(type="project.create", payload={"name": "dispatch"}))
    project = next(iter(core.projects.values()))
    await bus.execute(
        Command(
            type="agent.spawn",
            target={"project_id": project.id},
            payload={"role_id": "coordinator", "query": "q"},
        )
    )
    if store is not None:
        core.store = store
    return core, project


async def _coordinator(core) -> object:
    return next(a for a in core.agents.values() if a.role_id == "coordinator")


def _drain(core, session_id: str) -> list[str]:
    """取出（并由调用方处置）inbox 里已有的消息——spawn 的 query 会留在队列里。"""
    inbox = core.mailbox.inbox(session_id)
    drained = []
    while inbox is not None and not inbox.empty():
        drained.append(inbox.get_nowait()["content"])
    return drained


# --------------------------------------------------------------- 持久化先于可见


@pytest.mark.asyncio
async def test_persistence_failure_leaves_inbox_empty_and_does_not_wake():
    from cloudra.runtime_v2.event_writer import EventPersistenceError

    core, project = await _core_with_coordinator()
    agent = await _coordinator(core)
    before_queued = _drain(core, agent.id)  # spawn 的 query 先取走
    runs_before = [e for e in core.event_log.query_session(agent.id) if e.type == "run.started"]
    core.store = _BrokenStore()

    with pytest.raises(EventPersistenceError):
        await core.dispatcher.commit_and_deliver(
            to_session_id=agent.id,
            project_id=project.id,
            content="never delivered",
            sender="user",
        )

    assert _drain(core, agent.id) == [], "持久化失败绝不能入队"
    after = [e for e in core.event_log.query_session(agent.id) if e.type == "run.started"]
    assert len(after) == len(runs_before), "持久化失败绝不能唤醒"
    injected = [e for e in core.event_log if e.type == "agent.message_injected"]
    assert [e.data["content"] for e in injected] == ["q"], "只有 spawn 的 query 那一条"
    assert "never delivered" not in before_queued


@pytest.mark.asyncio
async def test_success_path_is_durable_then_visible(tmp_path):
    store = RuntimeStore(tmp_path / "runtime-v2.db")
    core, project = await _core_with_coordinator(store=store)
    agent = await _coordinator(core)
    _drain(core, agent.id)

    envelope = await core.dispatcher.commit_and_deliver(
        to_session_id=agent.id,
        project_id=project.id,
        content="hello",
        sender="user",
        wake=WakePolicy.NEVER,
    )

    # 事件已经在库里（不能等待任何后续 flush）。
    persisted = [
        e for e in store.events_after({}) if e["event_id"] == envelope.event_id
    ]
    assert len(persisted) == 1 and persisted[0]["type"] == "agent.message_injected"
    # 队列里也有同一条消息（同一 message_id）。
    queued = core.mailbox.inbox(agent.id).get_nowait()
    assert queued["message_id"] == envelope.data["message_id"]


@pytest.mark.asyncio
async def test_unconsumed_message_survives_restart_and_is_rebuilt(tmp_path):
    """持久化成功但从未被消费：重启后由事件重建进 inbox。"""
    store = RuntimeStore(tmp_path / "runtime-v2.db")
    core, project = await _core_with_coordinator(store=store)
    agent = await _coordinator(core)
    _drain(core, agent.id)
    await core.dispatcher.commit_and_deliver(
        to_session_id=agent.id,
        project_id=project.id,
        content="parked notice",
        sender="system",
        wake=WakePolicy.NEVER,
    )
    session_id = agent.id

    restored = RuntimeCore(strict_events=True)
    restored.store = store
    restore_core(restored, store)

    rebuilt = _drain(restored, session_id)
    # 未消费的 spawn query 与这条通知都在（重建按事件序）。
    assert rebuilt == ["q", "parked notice"]


@pytest.mark.asyncio
async def test_second_message_after_consume_is_rebuilt_not_duplicated(tmp_path):
    """已进入上下文投影的消息不重复入队，未消费的那条照常重建。"""
    store = RuntimeStore(tmp_path / "runtime-v2.db")
    core, project = await _core_with_coordinator(store=store)
    agent = await _coordinator(core)
    _drain(core, agent.id)
    first = await core.dispatcher.commit_and_deliver(
        to_session_id=agent.id, project_id=project.id, content="consumed", sender="user",
        wake=WakePolicy.NEVER,
    )
    consumed = core.mailbox.inbox(agent.id).get_nowait()
    assert consumed["message_id"] == first.data["message_id"]
    # 消费 = 进入 session 上下文投影（重建按 message_id 去重）。
    from cloudra.runtime_v2.apply import apply_event

    core.event_log.append(
        "context.appended",
        stream="agent",
        project_id=project.id,
        session_id=agent.id,
        data={"messages": [{"role": "user", "content": "consumed",
                            "message_id": first.data["message_id"]}]},
    )
    apply_event(core, list(core.event_log)[-1])
    await core.dispatcher.commit_and_deliver(
        to_session_id=agent.id, project_id=project.id, content="still parked", sender="user",
        wake=WakePolicy.NEVER,
    )

    restored = RuntimeCore(strict_events=True)
    restored.store = store
    restore_core(restored, store)
    rebuilt = _drain(restored, agent.id)
    # spawn 的 query 从未进入上下文投影 → 同样被重建；已消费的那条不再入队。
    assert rebuilt == ["q", "still parked"]


# ------------------------------------------------------------------ 唤醒纪律


def _agent(state: AgentState, *, reason: str | None = None, session_id: str = "as_x"):
    from cloudra.runtime_v2.core import RuntimeCore as _Core
    from cloudra.runtime_v2.schemas import AgentSession

    core = _Core(strict_events=True)
    agent = AgentSession(
        id=session_id, project_id="prj", role_id="explorer", display_name="E", state=state
    )
    if reason is not None:
        core.event_log.append(
            "agent.state_changed",
            stream="agent",
            project_id="prj",
            session_id=session_id,
            data={"from": "running", "to": state.value, "reason": reason},
        )
    return core, agent


@pytest.mark.parametrize(
    ("policy", "state", "reason", "expected"),
    [
        # park_terminal：终态只驻留，其余照常唤醒
        (WakePolicy.PARK_TERMINAL, AgentState.FAILED, None, False),
        (WakePolicy.PARK_TERMINAL, AgentState.CANCELLED, None, False),
        (WakePolicy.PARK_TERMINAL, AgentState.WAITING_INPUT, None, True),
        (WakePolicy.PARK_TERMINAL, AgentState.RUNNING, None, True),
        # park_waiting：终态/人工输入/工具审批只驻留；wait_review 要唤醒
        (WakePolicy.PARK_WAITING, AgentState.FAILED, None, False),
        (WakePolicy.PARK_WAITING, AgentState.WAITING_INPUT, None, False),
        (WakePolicy.PARK_WAITING, AgentState.WAITING_APPROVAL, "approval", False),
        (WakePolicy.PARK_WAITING, AgentState.WAITING_APPROVAL, "wait_review", True),
        (WakePolicy.PARK_WAITING, AgentState.SUCCEEDED, None, True),
        # idle_only：只有 QUEUED/SUCCEEDED
        (WakePolicy.IDLE_ONLY, AgentState.QUEUED, None, True),
        (WakePolicy.IDLE_ONLY, AgentState.SUCCEEDED, None, True),
        (WakePolicy.IDLE_ONLY, AgentState.RUNNING, None, False),
        (WakePolicy.IDLE_ONLY, AgentState.WAITING_APPROVAL, "wait_review", False),
        # never
        (WakePolicy.NEVER, AgentState.QUEUED, None, False),
    ],
)
def test_wake_policy_table(policy, state, reason, expected):
    core, agent = _agent(state, reason=reason)
    assert should_wake(core, agent, policy) is expected


@pytest.mark.asyncio
async def test_wake_policy_actually_schedules_a_new_run_when_allowed():
    """策略允许时必须真的开跑（不是只改状态）；策略拒绝时不得新增 run。"""
    from cloudra.runtime_v2.schemas import AgentSession

    core, project = await _core_with_coordinator()
    agent = AgentSession(
        id="as_idle", project_id=project.id, role_id="explorer", display_name="E",
        state=AgentState.QUEUED,
    )
    core.agents[agent.id] = agent

    await core.dispatcher.commit_and_deliver(
        to_session_id=agent.id, project_id=project.id, content="go", sender="user",
        wake=WakePolicy.PARK_TERMINAL,
    )
    assert agent.state in {AgentState.RUNNING, AgentState.QUEUED}
    runs = [e for e in core.event_log.query_session(agent.id) if e.type == "run.started"]
    assert len(runs) == 1

    agent2 = AgentSession(
        id="as_parked", project_id=project.id, role_id="explorer", display_name="E",
        state=AgentState.WAITING_INPUT,
    )
    core.agents[agent2.id] = agent2
    await core.dispatcher.commit_and_deliver(
        to_session_id=agent2.id, project_id=project.id, content="stay parked", sender="user",
        wake=WakePolicy.PARK_WAITING,
    )
    assert agent2.state is AgentState.WAITING_INPUT
    assert [e for e in core.event_log.query_session(agent2.id) if e.type == "run.started"] == []


def test_mailbox_has_no_deliver_method():
    """唯一提交入口是 dispatcher；旧的两步语义不得复活。"""
    assert not hasattr(Mailbox, "deliver")
    assert isinstance(RuntimeCore(strict_events=True).dispatcher, MessageDispatcher)


def test_latest_state_reason_reads_the_event_log():
    core, agent = _agent(AgentState.WAITING_APPROVAL, reason="wait_review")
    assert latest_state_reason(core, agent.id) == "wait_review"
    assert latest_state_reason(core, "as_absent") == ""
