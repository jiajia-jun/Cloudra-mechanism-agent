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
    原样保留取消终态，reconcile 不复活（零新事件、零投递），持久化待办
    留在信箱等显式恢复。"""
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
    await reconcile_supervision(core2, project.id)
    assert len(core2.event_log) == events_before  # 零新事件：不复活不投递
    assert supervisor2.state is AgentState.CANCELLED
    inbox = core2.mailbox.inbox(supervisor2.id)
    assert inbox is None or inbox.empty()

    # 持久化待办不丢。
    from cloudra.dag.store import DagStore
    from cloudra.persistence.database import ConversationDB

    queued = await asyncio.to_thread(
        lambda: [r.request_id for r in DagStore(ConversationDB(project.id)).list_review_requests("queued")]
    )
    assert queued == [request_id]


@pytest.mark.asyncio
async def test_replay_and_restore_have_no_supervision_side_effects(tmp_path):
    """恢复矩阵·重放零副作用：事件重放/restore 路径绝不执行督导逻辑——
    不 spawn（记录之外的）agent、不发通知、不跑 LLM/工具。reconcile 是
    restore 之后的显式步骤，对僵尸收尾落 failed 的 supervisor 同样是
    no-op（不补通知）。"""
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
    injections_before = len(
        [e for e in core1.event_log if e.type == "agent.message_injected"]
    )

    # 纯重放：状态与"restore 前"的活 core 一致（僵尸仍 running），零副作用。
    replayed = _replay_all_events(store)
    assert replayed.agents[supervisor1.id].state is AgentState.RUNNING
    assert {a.id for a in replayed.agents.values()} == {
        a.id for a in core1.agents.values()
    }  # 重放不新增 agent

    # restore：僵尸 running → failed（中断收尾），此外不补通知。
    core2 = RuntimeCore(strict_events=True)
    core2.store = store
    restore_core(core2, store)
    supervisor2 = core2.agents[supervisor1.id]
    assert supervisor2.state is AgentState.FAILED
    injections_after = len(
        [e for e in core2.event_log if e.type == "agent.message_injected"]
    )
    assert injections_after == injections_before  # restore/reconcile 前零新投递

    # 收尾事件已回写 store：纯重放与 restored 逐字段全等（含 failed 收尾）。
    replayed_post = _replay_all_events(store)
    assert replayed_post.agents[supervisor1.id].model_dump(
        mode="json"
    ) == supervisor2.model_dump(mode="json")

    # reconcile 对 failed 是 no-op；全事件流无任何工具/LLM 执行痕迹。
    await reconcile_supervision(core2, project.id)
    executed = [
        e
        for e in core2.event_log
        if e.type in {"tool.requested", "tool.started", "llm.requested"}
    ]
    assert executed == []


@pytest.mark.asyncio
async def test_reconcile_after_restore_only_schedules_notification_events(tmp_path):
    """恢复矩阵·只安排通知：正常休眠（succeeded）的 supervisor 恢复后，
    reconcile 补通知只产生通知/生命周期事件族（message_injected +
    wake 的 state_changed/run.started/context_reset），无 LLM/工具执行
    （无 runner 时 wake 只落事件——调度是 runner 的职责）。"""
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
    core1.agent_host.start_run(supervisor1)
    core1.agent_host.finish_run(supervisor1, outcome="succeeded")
    await core1.event_writer.flush()
    await _seed_structured_request(project.id, coordinator.id, question="notify me after restart")

    core2 = RuntimeCore(strict_events=True)
    core2.store = store
    restore_core(core2, store)
    supervisor2 = core2.agents[supervisor1.id]
    assert supervisor2.state is AgentState.SUCCEEDED  # 休眠不是尸体，不收尾

    events_before = len(core2.event_log)
    await reconcile_supervision(core2, project.id)
    new_types = {e.type for e in list(core2.event_log)[events_before:]}
    assert new_types <= {
        "agent.message_injected",
        "agent.state_changed",
        "run.started",
        "agent.context_reset",
    }, new_types
    # wake 开了新 run（事件层），但无 runner → 零执行。
    assert supervisor2.state is AgentState.RUNNING
    inbox = core2.mailbox.inbox(supervisor2.id)
    assert inbox is not None and inbox.qsize() == 1
    assert not [
        e
        for e in list(core2.event_log)[events_before:]
        if e.type.startswith(("tool.", "llm."))
    ]
