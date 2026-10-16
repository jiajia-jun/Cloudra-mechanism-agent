"""重启恢复时 pending 投影孤儿的显式过期 + compaction 请求事件化（FP 内核化 3c）。

- 进程崩溃时挂在 PendingBroker future 上的审批/提问只留下 ``*.requested``
  事件（等待者随进程消失，永远不会再有 decide/respond）。restore 必须为每个
  孤儿落 ``approval.expired`` / ``interaction.expired`` 终态事件：事件进日志、
  可持久化、可重放，pending 投影随之闭合——不再是无声消失。
- ``pending_compactions`` 是 ``compaction.requested`` 的事件投影（apply_event
  唯一写入点；``run.started`` 应用时清除，新 run 的内存 history 与旧请求无关），
  重启后经重放重建。
"""

from __future__ import annotations

import asyncio

import pytest

from cloudra.runtime_v2.apply import apply_event
from cloudra.runtime_v2.commands import CommandBus
from cloudra.runtime_v2.core import RuntimeCore
from cloudra.runtime_v2.persistence import RuntimeStore, restore_core
from cloudra.runtime_v2.schemas import Command, EventEnvelope


async def _persist_event(store: RuntimeStore, event: EventEnvelope) -> None:
    await asyncio.to_thread(store.append_event, event)


def _wire(tmp_path, db_name: str = "runtime.db"):
    store = RuntimeStore(tmp_path / db_name)
    core = RuntimeCore(strict_events=True)
    core.store = store
    core.event_hub.subscribe(lambda event: _persist_event(store, event))
    return core, store, CommandBus(core)


async def _project_and_agent(core, bus):
    project = (await bus.execute(Command(type="project.create", payload={"name": "exp"}))).data
    agent = (
        await bus.execute(
            Command(
                type="agent.spawn",
                target={"project_id": project.id},
                payload={"role_id": "coordinator"},
            )
        )
    ).data
    return project, agent


async def _crash_with_orphan(core, store, project, agent, kind: str, request_id: str) -> None:
    """模拟进程崩溃：requested 事件已落盘，等待 future 随进程消失（没有终态事件）。"""
    if kind == "approval":
        data = {
            "approval_id": request_id,
            "agent_name": agent.role_id,
            "tool_name": "write",
            "details": "write file",
            "risk_summary": "risk",
            "candidate_diff": "+x",
            "normalized_arguments": {"path": "a.txt"},
        }
    else:
        data = {"interaction_id": request_id, "agent_id": agent.role_id, "prompt": "which solvent?"}
    core.event_log.append(
        f"{kind}.requested",
        stream="agent",
        project_id=project.id,
        session_id=agent.id,
        data=data,
    )
    await core.event_writer.flush()


def _events(core, project_id: str, type_: str):
    return list(core.event_log.query_project(project_id, types={type_}, limit=10_000))


# ------------------------------------------------------------------ approvals


@pytest.mark.asyncio
async def test_restart_expires_orphan_approval(tmp_path):
    """孤儿审批：restore 落 approval.expired，pending 投影闭合，事件持久化。"""
    core, store, bus = _wire(tmp_path)
    project, agent = await _project_and_agent(core, bus)
    await _crash_with_orphan(core, store, project, agent, "approval", "apv_orphan")
    assert len(core.pending.list_pending_approvals(project.id)) == 1

    restored = RuntimeCore(strict_events=True)
    restore_core(restored, store)

    expired = _events(restored, project.id, "approval.expired")
    assert len(expired) == 1
    assert expired[0].data["approval_id"] == "apv_orphan"
    assert expired[0].data["agent_id"] == agent.role_id
    assert expired[0].data["reason"] == "restart"
    assert expired[0].session_id == agent.id
    # 投影闭合：孤儿不再出现在 pending 列表（agent 唤醒后看到的是明确终态）
    assert restored.pending.list_pending_approvals(project.id) == []
    # 过期事件已持久化（纯重放也能看到终态）
    persisted_types = [e["type"] for e in store.query_project_events(project.id, limit=10_000)]
    assert "approval.expired" in persisted_types

    replayed = RuntimeCore(strict_events=True)
    envelopes = [EventEnvelope.model_validate(raw) for raw in store.events_after({})]
    replayed.event_log.restore(envelopes)
    for envelope in envelopes:
        apply_event(replayed, envelope)
    assert replayed.pending.list_pending_approvals(project.id) == []


@pytest.mark.asyncio
async def test_restart_expires_orphan_interaction(tmp_path):
    """孤儿提问：restore 落 interaction.expired，pending 投影闭合。"""
    core, store, bus = _wire(tmp_path, "ixn.db")
    project, agent = await _project_and_agent(core, bus)
    await _crash_with_orphan(core, store, project, agent, "interaction", "ixn_orphan")
    assert len(core.pending.list_pending_interactions(project.id)) == 1

    restored = RuntimeCore(strict_events=True)
    restore_core(restored, store)

    expired = _events(restored, project.id, "interaction.expired")
    assert len(expired) == 1
    assert expired[0].data["interaction_id"] == "ixn_orphan"
    assert expired[0].data["agent_id"] == agent.role_id
    assert expired[0].data["reason"] == "restart"
    assert expired[0].session_id == agent.id
    assert restored.pending.list_pending_interactions(project.id) == []
    persisted_types = [e["type"] for e in store.query_project_events(project.id, limit=10_000)]
    assert "interaction.expired" in persisted_types


@pytest.mark.asyncio
async def test_pending_expiry_is_idempotent_across_restores(tmp_path):
    """expired 本身就是终态：二次 restore 不再重复落过期事件。"""
    core, store, bus = _wire(tmp_path, "idem.db")
    project, agent = await _project_and_agent(core, bus)
    await _crash_with_orphan(core, store, project, agent, "approval", "apv_once")
    await _crash_with_orphan(core, store, project, agent, "interaction", "ixn_once")

    first = RuntimeCore(strict_events=True)
    restore_core(first, store)
    assert len(_events(first, project.id, "approval.expired")) == 1
    assert len(_events(first, project.id, "interaction.expired")) == 1

    second = RuntimeCore(strict_events=True)
    restore_core(second, store)
    assert len(_events(second, project.id, "approval.expired")) == 1
    assert len(_events(second, project.id, "interaction.expired")) == 1
    assert second.pending.list_pending_approvals(project.id) == []
    assert second.pending.list_pending_interactions(project.id) == []


@pytest.mark.asyncio
async def test_decided_entries_are_not_expired(tmp_path):
    """已有终态的条目不是孤儿：restore 不补 expired。"""
    core, store, bus = _wire(tmp_path, "decided.db")
    project, agent = await _project_and_agent(core, bus)
    await _crash_with_orphan(core, store, project, agent, "approval", "apv_done")
    core.event_log.append(
        "approval.decided",
        stream="agent",
        project_id=project.id,
        session_id=agent.id,
        data={"approval_id": "apv_done", "decision": "approved", "reason": ""},
    )
    await core.event_writer.flush()

    restored = RuntimeCore(strict_events=True)
    restore_core(restored, store)
    assert _events(restored, project.id, "approval.expired") == []


# ------------------------------------------------------------------ compaction


@pytest.mark.asyncio
async def test_compaction_request_event_rebuilds_projection(tmp_path):
    """pending_compactions 是 compaction.requested 的事件投影：restore 重放重建。"""
    core, store, bus = _wire(tmp_path, "compact.db")
    project, agent = await _project_and_agent(core, bus)

    await bus.execute(
        Command(type="agent.compact", target={"session_id": agent.id}, payload={})
    )
    # 活 core：请求经事件 + apply_event 进投影
    assert core.pending_compactions == {agent.id}

    restored = RuntimeCore(strict_events=True)
    restore_core(restored, store)
    # 旧实现红在这里：事件在，但恢复路径不重建投影
    assert restored.pending_compactions == {agent.id}


@pytest.mark.asyncio
async def test_pending_compaction_survives_run_boundaries(tmp_path):
    """Task 4 新契约：上下文是 session 级投影、跨 run 连续——压缩请求不再随
    run.started 作废，存活到 runner 的下个轮次边界应用到会话上下文；
    活 core 与重放 core 一致。"""
    core, store, bus = _wire(tmp_path, "compact_clear.db")
    project, agent = await _project_and_agent(core, bus)

    await bus.execute(
        Command(type="agent.compact", target={"session_id": agent.id}, payload={})
    )
    assert core.pending_compactions == {agent.id}
    # message → wake → run.started：投影**保留**（无 runner 的纯状态模式下
    # 没有轮次边界消费，条目继续等待）。
    await bus.execute(
        Command(type="agent.message", target={"session_id": agent.id}, payload={"content": "go"})
    )
    assert core.pending_compactions == {agent.id}

    restored = RuntimeCore(strict_events=True)
    restore_core(restored, store)
    assert restored.pending_compactions == {agent.id}


@pytest.mark.asyncio
async def test_pending_compaction_survives_snapshot_then_restore(tmp_path):
    """快照水位越过 compaction.requested 之后，投影仍须从快照载荷恢复。"""
    core, store, bus = _wire(tmp_path, "compact_snap.db")
    _project, agent = await _project_and_agent(core, bus)

    await bus.execute(
        Command(type="agent.compact", target={"session_id": agent.id}, payload={})
    )
    assert core.pending_compactions == {agent.id}
    await bus.flush_snapshot()

    restored = RuntimeCore(strict_events=True)
    restore_core(restored, store)
    assert restored.pending_compactions == {agent.id}


@pytest.mark.asyncio
async def test_failed_manual_compaction_keeps_pending_across_snapshot(tmp_path):
    """压缩被拒不得清 pending：快照后恢复仍要重试用户的 compact 请求。"""
    from cloudra.runtime_v2.agent_runner import AgentRunner

    core, store, bus = _wire(tmp_path, "compact_fail.db")
    _project, agent = await _project_and_agent(core, bus)
    await bus.execute(
        Command(type="agent.compact", target={"session_id": agent.id}, payload={})
    )
    assert core.pending_compactions == {agent.id}

    runner = AgentRunner(core, object())

    async def _refuse(*_a, **_k):
        return {"compacted": False, "error": "refused"}

    runner._apply_compaction = _refuse  # type: ignore[method-assign]
    await runner._consume_pending_compaction(agent, "run_test")
    assert core.pending_compactions == {agent.id}
    await bus.flush_snapshot()

    restored = RuntimeCore(strict_events=True)
    restore_core(restored, store)
    assert restored.pending_compactions == {agent.id}
