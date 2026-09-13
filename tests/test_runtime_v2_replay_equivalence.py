"""快照恢复 == 纯事件重放 == 活 core：三路径逐字段等价门禁（FP 内核化 3a/3b）。

``cloudra.runtime_v2.apply.apply_event`` 是唯一状态应用器之后，同一份事件
流在三条路径上必须推出逐字段全等的内存状态：

- 活 core：CommandBus 的四拍（decide → append/publish/persist →
  apply_event → effects）运行期路径；
- 快照路径：``restore_core`` = 装快照 + ``events_after(last_seqs)`` 逐项目
  增量重放（3b：快照降级为节流缓存，测试用 ``bus.flush_snapshot()`` 显式
  冻结快照点）；
- 纯重放路径：空 core 对 ``events_after({})`` 逐条 ``apply_event``。

比较口径（关键，勿改歪）：
- 场景 A/B 结束时所有 agent 停在 queued/终态，``restore_core`` 的
  "RUNNING/WAITING → failed" 中断收尾在三条路径上都是无操作，因此三者
  必须**逐字段全等**（含 updated_at / current_run.started_at——它们由
  apply_event 统一取 envelope.created_at，不再取应用时刻墙钟）。
- 场景 C 留一个 RUNNING agent：纯重放与活 core 都停在 RUNNING（两者
  逐字段全等）；restore_core 额外执行中断收尾（新生成 state_changed /
  run.finished 事件，created_at 各异），故只断言其余 agent 与
  projects/roles/runtime_defaults 全等 + 僵尸 agent 的终态语义。
  restore 把收尾事件回写 store 之后，纯重放必须再次与 restored 全等。
- 场景 D（3b 新增）多项目交错：seq 是 per-project 计数，快照 meta 存
  逐项目高水位；快照后他项目 seq ≤ 他项目水位之外最大值的新事件必须
  零丢失重放（旧"单全局 last_seq"实现上本场景为红）。
- api_key 是 write-only 秘密，不进事件/快照（api_key_set 是 computed
  field，dump 恒反映内存秘密有无）——脚本全程不使用 api_key，等价比较
  才能对 computed dump 成立。
- pending_compactions 已由 compaction.requested 事件承载（3c），消费在
  runner 的轮次边界（shell 侧动作；Task 4 起跨 run 存活、不再作废），
  不是纯事件投影，故仍不在比较集内。
- session_contexts 由 context.prefix_installed/appended/compacted 承载，
  快照载荷随 save_snapshot 落地——在比较集内（_contexts_dump）。

任何新增状态承载事件若绕过 apply_event，或拍序倒退回"状态先于事件"，
本文件必须转红。
"""

from __future__ import annotations

import asyncio

import pytest

from cloudra.runtime_v2.apply import apply_event
from cloudra.runtime_v2.commands import CommandBus
from cloudra.runtime_v2.core import RuntimeCore
from cloudra.runtime_v2.persistence import RuntimeStore, restore_core
from cloudra.runtime_v2.schemas import AgentState, Command, EventEnvelope


async def _persist_event(store: RuntimeStore, event: EventEnvelope) -> None:
    await asyncio.to_thread(store.append_event, event)


def _wire(tmp_path, db_name: str = "runtime.db"):
    """活 core + store：hub 订阅把每条事件落盘（与 API 的持久化订阅同构）。"""
    store = RuntimeStore(tmp_path / db_name)
    core = RuntimeCore(strict_events=True)
    core.store = store
    core.event_hub.subscribe(lambda event: _persist_event(store, event))
    return core, store, CommandBus(core)


def _state_dump(core: RuntimeCore) -> dict:
    """四件事件溯源状态的确定序列化（脚本不碰 api_key，见模块 docstring）。"""
    return {
        "projects": {pid: p.model_dump(mode="json") for pid, p in core.projects.items()},
        "agents": {sid: a.model_dump(mode="json") for sid, a in core.agents.items()},
        "roles": {rid: r.model_dump(mode="json") for rid, r in core.roles._roles.items()},
        "runtime_defaults": core.runtime_defaults.model_dump(mode="json"),
    }


def _pins_dump(core: RuntimeCore) -> dict:
    return {sid: dict(pins) for sid, pins in core.notices._pins.items()}


def _contexts_dump(core: RuntimeCore) -> dict:
    """会话级 LLM 上下文投影（Task 4 状态承载事件：context.prefix_installed /
    appended / compacted）——必须在三路径上逐字段全等。"""
    return {
        sid: ctx.model_dump(mode="json") for sid, ctx in core.session_contexts.items()
    }


def _replay_all(store: RuntimeStore) -> RuntimeCore:
    """纯重放路径：空 core + 全量事件逐条 apply_event（不经过快照）。"""
    core = RuntimeCore(strict_events=True)
    envelopes = [EventEnvelope.model_validate(raw) for raw in store.events_after({})]
    # 事件日志本身也是状态投影的载体（notices 投影从中重建），同步回填。
    core.event_log.restore(envelopes)
    for envelope in envelopes:
        apply_event(core, envelope)
    core.notices.restore_from(core.event_log)
    return core


def _assert_quiescent(core: RuntimeCore) -> None:
    # 静止前置：否则 restore 的中断收尾会额外落事件，三路径全等口径不成立。
    for agent in core.agents.values():
        assert agent.state not in {
            AgentState.RUNNING,
            AgentState.WAITING_INPUT,
            AgentState.WAITING_APPROVAL,
        }, f"agent {agent.id} still {agent.state.value}"


@pytest.mark.asyncio
async def test_quiescent_state_snapshot_restore_equals_pure_replay(tmp_path):
    """场景 A：多项目、全 bus 命令、静止收尾——三路径逐字段全等。"""
    core, store, bus = _wire(tmp_path)

    r = await bus.execute(
        Command(
            type="project.create",
            payload={"name": "alpha", "workspace_dir": str(tmp_path / "ws1")},
        )
    )
    p1 = r.data.id
    p2 = (await bus.execute(Command(type="project.create", payload={"name": "beta"}))).data.id

    # 单条 update 同时带字段与 settings：一条命令落 project.updated +
    # project.settings_changed 两条事件。
    await bus.execute(
        Command(
            type="project.update",
            target={"project_id": p1},
            payload={
                "name": "alpha-2",
                "settings": {"orchestration_mode": "dag_record", "defaults": {"temperature": 0.7}},
            },
        )
    )
    await bus.execute(
        Command(
            type="role.update",
            target={"role_id": "researcher"},
            payload={"default_settings": {"temperature": 0.9}, "can_spawn": True},
        )
    )

    coord = (
        await bus.execute(
            Command(
                type="agent.spawn",
                target={"project_id": p1},
                payload={"role_id": "coordinator", "query": "hello p1"},
            )
        )
    ).data
    researcher = (
        await bus.execute(
            Command(
                type="agent.spawn",
                target={"project_id": p1},
                payload={"role_id": "researcher"},
            )
        )
    ).data
    coord2 = (
        await bus.execute(
            Command(
                type="agent.spawn",
                target={"project_id": p2},
                payload={"role_id": "coordinator"},
            )
        )
    ).data

    await bus.execute(
        Command(
            type="agent.settings_update",
            target={"session_id": researcher.id},
            payload={"yolo": True, "temperature": 0.2, "orchestration_mode": "dag_record"},
        )
    )
    # queued 上直接 cancel（带留言）→ cancelled 终态
    await bus.execute(
        Command(
            type="agent.cancel",
            target={"session_id": researcher.id},
            payload={"message": "stop"},
        )
    )
    # 终态 restart（带 settings 补丁 + 留言）→ 回到 queued
    await bus.execute(
        Command(
            type="agent.restart",
            target={"session_id": researcher.id},
            payload={"message": "again", "settings": {"max_tokens": 4096}},
        )
    )
    # 拒径：未知角色 spawn → agent.spawn_rejected + command.rejected
    rejected = await bus.execute(
        Command(
            type="agent.spawn",
            target={"project_id": p1},
            payload={"role_id": "nonexistent"},
        )
    )
    assert not rejected.accepted
    # 拒径：restart 一个 queued agent → command.rejected
    rejected = await bus.execute(
        Command(type="agent.restart", target={"session_id": coord.id}, payload={})
    )
    assert not rejected.accepted
    # notices 投影：pin + unpin + push
    await bus.execute(
        Command(
            type="context.inject",
            target={"session_id": coord.id},
            payload={"kind": "pin", "key": "goal", "content": "test pin"},
        )
    )
    await bus.execute(
        Command(
            type="context.inject",
            target={"session_id": coord.id},
            payload={"kind": "pin", "key": "tmp", "content": "to be cleared"},
        )
    )
    await bus.execute(
        Command(
            type="context.inject",
            target={"session_id": coord.id},
            payload={"kind": "unpin", "key": "tmp"},
        )
    )
    # compaction.requested（事件投影由 apply_event 维护，不在比较集）
    await bus.execute(
        Command(
            type="agent.compact",
            target={"session_id": coord.id},
            payload={"keep_recent": 5},
        )
    )
    # 无留言 cancel（p2 的 queued coordinator）
    await bus.execute(Command(type="agent.cancel", target={"session_id": coord2.id}, payload={}))

    # 快照已是节流缓存（3b）：显式冻结快照点，restore 走"快照+空尾巴"。
    await bus.flush_snapshot()
    _assert_quiescent(core)

    restored = RuntimeCore(strict_events=True)
    restore_core(restored, store)
    replayed = _replay_all(store)

    live_dump = _state_dump(core)
    assert _state_dump(restored) == live_dump
    assert _state_dump(replayed) == live_dump
    # notices pins 也是事件投影：三路径一致
    assert _pins_dump(restored) == _pins_dump(core)
    assert _pins_dump(replayed) == _pins_dump(core)
    # 会话上下文投影（context.* 事件 + 快照载荷）：三路径一致
    assert _contexts_dump(restored) == _contexts_dump(core)
    assert _contexts_dump(replayed) == _contexts_dump(core)


@pytest.mark.asyncio
async def test_live_run_context_events_replay_equal(tmp_path):
    """场景 E：真实 runner 产出的 context.* 事件（prefix_installed/appended）
    在三路径上逐字段全等——live / 快照恢复 / 纯重放。"""
    from cloudra.runtime_v2.agent_runner import AgentRunner
    from cloudra.runtime_v2.policies import default_stages
    from cloudra.runtime_v2.policies.base import ToolResult
    from cloudra.runtime_v2.turn_pipeline import LLMResponse, TurnPipeline

    class _ScriptedLLM:
        async def complete(self, agent, messages, tools, **_kwargs):
            return LLMResponse(content="done", stop_requested=True)

    class _EchoTools:
        async def execute(self, agent, call, **_kwargs):
            return ToolResult(is_success=True, summary="ok", data={})

    core, store, bus = _wire(tmp_path, "contexts.db")
    pipeline = TurnPipeline(
        event_log=core.event_log, stages=default_stages(), llm=_ScriptedLLM(), tools=_EchoTools()
    )
    core.runner = AgentRunner(core, pipeline)
    project = (await bus.execute(Command(type="project.create", payload={"name": "live"}))).data
    agent = (
        await bus.execute(
            Command(
                type="agent.spawn",
                target={"project_id": project.id},
                payload={"role_id": "coordinator", "query": "solve it"},
            )
        )
    ).data
    # 纯文本回复在两种调用协议下都直接收尾，无需改协议设置（设置改动必须
    # 走事件，否则活 core 与重放 core 的 agent 投影分叉）。
    deadline = asyncio.get_running_loop().time() + 5.0
    while agent.state.value != "succeeded":
        assert asyncio.get_running_loop().time() < deadline, "agent did not finish"
        await asyncio.sleep(0.01)
    # 上下文事件确实产生过（否则本场景是空守）
    types = {e.type for e in core.event_log.query_session(agent.id)}
    assert "context.appended" in types
    await bus.flush_snapshot()
    _assert_quiescent(core)

    restored = RuntimeCore(strict_events=True)
    restore_core(restored, store)
    replayed = _replay_all(store)
    live_dump = _state_dump(core)
    assert _state_dump(restored) == live_dump
    assert _state_dump(replayed) == live_dump
    assert _contexts_dump(core), "live core has no session context"
    assert _contexts_dump(restored) == _contexts_dump(core)
    assert _contexts_dump(replayed) == _contexts_dump(core)


@pytest.mark.asyncio
async def test_incremental_replay_after_stale_snapshot(tmp_path):
    """场景 B：快照停在最后一次 bus 命令，之后的 host 级 run 事件走增量重放。"""
    core, store, bus = _wire(tmp_path, "incremental.db")

    project = (
        await bus.execute(Command(type="project.create", payload={"name": "inc"}))
    ).data
    agent = (
        await bus.execute(
            Command(
                type="agent.spawn",
                target={"project_id": project.id},
                payload={"role_id": "coordinator"},
            )
        )
    ).data
    # message → wake → start_run：agent 进入 RUNNING（无 runner，原地停住）
    await bus.execute(
        Command(
            type="agent.message",
            target={"session_id": agent.id},
            payload={"content": "run something"},
        )
    )
    await bus.execute(
        Command(
            type="agent.settings_update",
            target={"session_id": agent.id},
            payload={"temperature": 0.5},
        )
    )
    # 冻结点：快照停在这里，之后的事件必须靠增量重放追平。
    await bus.flush_snapshot()

    # 快照之后的运行期事件：纯通知类（no-op 重放）+ host 级 run 收尾。
    tail = [
        ("tool.started", {"tool_name": "stop"}),
        ("llm.completed", {"usage": {"total_tokens": 1}}),
        ("agent.thinking", {"text": "..."}),
        ("agent.message_emitted", {"sender": "coordinator", "content": "done"}),
        ("run.retry", {"attempt": 1, "max_retries": 2, "error": "x", "next_delay_s": 0}),
    ]
    for event_type, data in tail:
        envelope = core.event_log.append(
            event_type,
            stream="agent",
            project_id=project.id,
            session_id=agent.id,
            run_id=agent.current_run.run_id,
            data=data,
        )
        await _persist_event(store, envelope)
    before = len(core.event_log)
    core.agent_host.finish_run(agent, outcome="succeeded")
    for envelope in list(core.event_log)[before:]:
        await _persist_event(store, envelope)
    # 故意不再 save_snapshot：restore 必须靠增量重放追平。

    _assert_quiescent(core)
    restored = RuntimeCore(strict_events=True)
    restore_core(restored, store)
    replayed = _replay_all(store)

    live_dump = _state_dump(core)
    assert live_dump["agents"][agent.id]["state"] == "succeeded"
    assert _state_dump(restored) == live_dump
    assert _state_dump(replayed) == live_dump


@pytest.mark.asyncio
async def test_interleaved_projects_snapshot_tail_zero_loss(tmp_path):
    """场景 D（多项目交错 seq 丢事件回归）：seq 是 per-project 计数，快照
    水位必须逐项目记录。两项目交错时，若快照只存全局 max(seq)，快照后
    他项目的新事件（seq ≤ max）会被增量重放永久漏掉。

    先红后绿：本场景在"单全局 last_seq"旧实现上验证过红（restored 整体
    丢失 a2），逐项目高水位修复后转绿。
    """
    core, store, bus = _wire(tmp_path, "interleave.db")

    p1 = (await bus.execute(Command(type="project.create", payload={"name": "p1"}))).data
    p2 = (await bus.execute(Command(type="project.create", payload={"name": "p2"}))).data
    a1 = (
        await bus.execute(
            Command(
                type="agent.spawn",
                target={"project_id": p1.id},
                payload={"role_id": "coordinator"},
            )
        )
    ).data
    # 抬高 p1 水位，使其超过 p2 快照后尾巴的每一条 seq
    await bus.execute(
        Command(
            type="agent.settings_update",
            target={"session_id": a1.id},
            payload={"temperature": 0.5},
        )
    )
    await bus.execute(
        Command(
            type="context.inject",
            target={"session_id": a1.id},
            payload={"kind": "pin", "key": "goal", "content": "p1 pin"},
        )
    )

    # 冻结点：快照水位 {p1: 5, p2: 1}
    await bus.flush_snapshot()

    # 快照后的 p2 尾巴：seq 2..5，全部 <= p1 的水位 5
    a2 = (
        await bus.execute(
            Command(
                type="agent.spawn",
                target={"project_id": p2.id},
                payload={"role_id": "coordinator", "query": "hello p2"},
            )
        )
    ).data
    await bus.execute(
        Command(
            type="agent.settings_update",
            target={"session_id": a2.id},
            payload={"yolo": True},
        )
    )
    # 交错：p1 在快照后也有新事件（seq 6，必须同样重放到）
    await bus.execute(
        Command(
            type="agent.settings_update",
            target={"session_id": a1.id},
            payload={"temperature": 0.6},
        )
    )

    _assert_quiescent(core)
    restored = RuntimeCore(strict_events=True)
    restore_core(restored, store)
    replayed = _replay_all(store)

    live_dump = _state_dump(core)
    assert _state_dump(restored) == live_dump
    assert _state_dump(replayed) == live_dump
    assert _pins_dump(restored) == _pins_dump(core)
    assert _contexts_dump(restored) == _contexts_dump(core)
    assert _contexts_dump(replayed) == _contexts_dump(core)


@pytest.mark.asyncio
async def test_zombie_run_finalize_keeps_replay_consistent(tmp_path):
    """场景 C：RUNNING 快照。重放==活 core（全等）；restore 追加中断收尾。"""
    core, store, bus = _wire(tmp_path, "zombie.db")

    project = (
        await bus.execute(Command(type="project.create", payload={"name": "z"}))
    ).data
    zombie = (
        await bus.execute(
            Command(
                type="agent.spawn",
                target={"project_id": project.id},
                payload={"role_id": "coordinator"},
            )
        )
    ).data
    idle = (
        await bus.execute(
            Command(
                type="agent.spawn",
                target={"project_id": project.id},
                payload={"role_id": "explorer"},
            )
        )
    ).data
    await bus.execute(
        Command(
            type="agent.message",
            target={"session_id": zombie.id},
            payload={"content": "start then die"},
        )
    )
    assert core.agents[zombie.id].state is AgentState.RUNNING

    # 冻结快照点（3b 起快照是节流缓存，测试显式 flush）。
    await bus.flush_snapshot()

    # 收尾前：纯重放必须逐字段等于活 core（两者都停在 RUNNING）。
    replayed_pre = _replay_all(store)
    assert _state_dump(replayed_pre) == _state_dump(core)

    restored = RuntimeCore(strict_events=True)
    restore_core(restored, store)
    revived = restored.agents[zombie.id]
    assert revived.state is AgentState.FAILED
    assert revived.current_run is None
    # 未被收尾的 agent 与其余三件状态与活 core 全等
    assert _state_dump(restored)["agents"][idle.id] == _state_dump(core)["agents"][idle.id]
    for key in ("projects", "roles", "runtime_defaults"):
        assert _state_dump(restored)[key] == _state_dump(core)[key]

    # 收尾事件已回写 store：纯重放现在必须与 restored 逐字段全等。
    replayed_post = _replay_all(store)
    assert _state_dump(replayed_post) == _state_dump(restored)
