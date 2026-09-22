"""benchmark/watch.py — GH #30 等待状态机（wait_background / wait_review）。

红绿目标：
- SUCCEEDED + 存活子 agent/后台 = 未完成，继续等（C1 事故回归）；
- WAITING_APPROVAL(reason=wait_review) = 内部督导等待，不套 300s 人工卡死
  取消（NI1 事故回归），只有督导已死才按卡死处理；
- 其余无应答挂起（waiting_input / approval）与整体超时照旧取消。
"""

from __future__ import annotations

import asyncio

import pytest

from cloudra.benchmark.watch import RunWatcher
from cloudra.runtime_v2.commands import CommandBus
from cloudra.runtime_v2.core import RuntimeCore
from cloudra.runtime_v2.schemas import AgentState, Command


async def _spawn_quiet(core, bus, project_id: str, role_id: str):
    """spawn 不带 query：不投递消息、不调度（纯状态样本）。"""
    result = await bus.execute(
        Command(
            type="agent.spawn",
            target={"project_id": project_id},
            payload={"role_id": role_id},
        )
    )
    return result.data


async def _core_with_agents(tmp_path, second_role: str = "coordinator"):
    core = RuntimeCore(strict_events=True)
    bus = CommandBus(core)
    project = (
        await bus.execute(
            Command(
                type="project.create",
                payload={"name": "benchmark:T", "workspace_dir": str(tmp_path)},
            )
        )
    ).data
    parent = await _spawn_quiet(core, bus, project.id, "coordinator")
    sibling = await _spawn_quiet(core, bus, project.id, second_role)
    return core, project, parent, sibling


def _watcher(**kwargs) -> RunWatcher:
    params = {
        "run_timeout_s": 30.0,
        "stuck_grace_s": 5.0,
        "poll_interval_s": 0.01,
    }
    params.update(kwargs)
    return RunWatcher(**params)


def _set(core, agent, to: AgentState, reason: str) -> None:
    core.agent_host.transition(agent, to, reason=reason)


def _terminal(core, agent, to: AgentState, reason: str) -> None:
    """QUEUED 不能直接落终态：先补 RUNNING 再落终态（对齐真实状态机）。"""
    if agent.state is AgentState.QUEUED:
        _set(core, agent, AgentState.RUNNING, "run_started")
    _set(core, agent, to, reason)


@pytest.mark.asyncio
async def test_succeeded_with_live_sibling_keeps_waiting(tmp_path):
    """C1 事故：SUCCEEDED 只是当前 run 休眠（wait_background），子 agent 未竟
    前不得判题目完成。"""
    core, _project, parent, sibling = await _core_with_agents(tmp_path)
    _set(core, parent, AgentState.RUNNING, "run_started")
    _set(core, parent, AgentState.SUCCEEDED, "wait_background")
    watcher = _watcher()

    decision = await watcher.decide(core, parent)
    assert decision.kind == "continue"

    # 子 agent 到终态后，后台排空 → 真正完成
    _terminal(core, sibling, AgentState.CANCELLED, "cancel")
    decision = await watcher.decide(core, parent)
    assert decision.kind == "done"


@pytest.mark.asyncio
async def test_succeeded_without_background_is_done(tmp_path):
    core, _project, parent, sibling = await _core_with_agents(tmp_path)
    _terminal(core, sibling, AgentState.SUCCEEDED, "done")  # 兄弟已终态，不构成后台
    _set(core, parent, AgentState.RUNNING, "run_started")
    _set(core, parent, AgentState.SUCCEEDED, "allow_final")
    decision = await _watcher().decide(core, parent)
    assert decision.kind == "done"


@pytest.mark.asyncio
async def test_injected_background_extends_succeeded_wait(tmp_path):
    core, _project, parent, sibling = await _core_with_agents(tmp_path)
    _terminal(core, sibling, AgentState.CANCELLED, "cancel")
    _set(core, parent, AgentState.RUNNING, "run_started")
    _set(core, parent, AgentState.SUCCEEDED, "wait_background")

    async def pending() -> bool:
        return True

    watcher = _watcher(pending_background=pending)
    assert (await watcher.decide(core, parent)).kind == "continue"
    watcher = _watcher(pending_background=lambda: asyncio.sleep(0, result=False))
    assert (await watcher.decide(core, parent)).kind == "done"


@pytest.mark.asyncio
async def test_wait_review_with_live_supervisor_not_stuck(tmp_path):
    """NI1 事故：wait_review 挂起等内部 Supervisor，不是人工审批卡死。"""
    core, project, parent, supervisor = await _core_with_agents(tmp_path, second_role="supervisor")
    _set(core, supervisor, AgentState.RUNNING, "run_started")
    _set(core, parent, AgentState.RUNNING, "run_started")
    _set(core, parent, AgentState.WAITING_APPROVAL, "wait_review")

    decision = await _watcher().decide(core, parent)
    assert decision.kind == "continue"

    # 督导自身结束（无人会再裁决）→ 落入卡死取消，而不是永远挂着
    _terminal(core, supervisor, AgentState.SUCCEEDED, "done")
    decision = await _watcher().decide(core, parent)
    assert decision.kind == "cancel"
    assert "no live supervisor" in decision.reason


@pytest.mark.asyncio
async def test_wait_review_without_any_supervisor_cancels(tmp_path):
    core, _project, parent, _sibling = await _core_with_agents(tmp_path)
    _set(core, parent, AgentState.RUNNING, "run_started")
    _set(core, parent, AgentState.WAITING_APPROVAL, "wait_review")
    decision = await _watcher().decide(core, parent)
    assert decision.kind == "cancel"
    assert "no live supervisor" in decision.reason


@pytest.mark.asyncio
async def test_unanswered_hangs_are_stuck(tmp_path):
    core, _project, parent, sibling = await _core_with_agents(tmp_path)
    _terminal(core, sibling, AgentState.SUCCEEDED, "done")
    _set(core, parent, AgentState.RUNNING, "run_started")

    _set(core, parent, AgentState.WAITING_INPUT, "ask_user")
    decision = await _watcher().decide(core, parent)
    assert decision.kind == "cancel"
    assert "waiting_input" in decision.reason and "nobody to answer" in decision.reason

    _set(core, parent, AgentState.RUNNING, "resumed")
    _set(core, parent, AgentState.WAITING_APPROVAL, "approval")
    decision = await _watcher().decide(core, parent)
    assert decision.kind == "cancel"
    assert "waiting_approval" in decision.reason


@pytest.mark.asyncio
async def test_wait_applies_stuck_grace_then_cancels(tmp_path):
    core, _project, parent, sibling = await _core_with_agents(tmp_path)
    _terminal(core, sibling, AgentState.SUCCEEDED, "done")
    _set(core, parent, AgentState.RUNNING, "run_started")
    _set(core, parent, AgentState.WAITING_INPUT, "ask_user")

    reasons: list[str] = []

    async def cancel(reason: str) -> None:
        reasons.append(reason)

    watcher = _watcher(stuck_grace_s=0.05)
    reason = await watcher.wait(core, parent, cancel)
    assert reason is not None and "waiting_input" in reason
    assert reasons == [reason]


@pytest.mark.asyncio
async def test_wait_wait_review_survives_grace_with_live_supervisor(tmp_path):
    core, _project, parent, supervisor = await _core_with_agents(tmp_path, second_role="supervisor")
    _set(core, supervisor, AgentState.RUNNING, "run_started")
    _set(core, parent, AgentState.RUNNING, "run_started")
    _set(core, parent, AgentState.WAITING_APPROVAL, "wait_review")

    cancelled: list[str] = []

    async def cancel(reason: str) -> None:
        cancelled.append(reason)

    watcher = _watcher(stuck_grace_s=0.05)
    wait_task = asyncio.create_task(watcher.wait(core, parent, cancel))
    try:
        # 远超 stuck_grace 的时间窗内不得取消（督导还活着）
        await asyncio.wait_for(asyncio.sleep(0.2), timeout=1.0)
        assert not cancelled
        assert not wait_task.done()
    finally:
        # 督导死亡 → 落入卡死取消，等待收尾
        _terminal(core, supervisor, AgentState.SUCCEEDED, "done")
        reason = await asyncio.wait_for(wait_task, timeout=2.0)
        assert reason is not None and "no live supervisor" in reason
        assert cancelled == [reason]


@pytest.mark.asyncio
async def test_wait_run_timeout_cancels_running_agent(tmp_path):
    core, _project, parent, sibling = await _core_with_agents(tmp_path)
    _terminal(core, sibling, AgentState.SUCCEEDED, "done")
    _set(core, parent, AgentState.RUNNING, "run_started")

    reasons: list[str] = []

    async def cancel(reason: str) -> None:
        reasons.append(reason)

    watcher = _watcher(run_timeout_s=0.05, stuck_grace_s=5.0)
    reason = await watcher.wait(core, parent, cancel)
    assert reason is not None and "run timeout" in reason
    assert reasons == [reason]


@pytest.mark.asyncio
async def test_latest_state_reason_reads_event_log(tmp_path):
    from cloudra.runtime_v2.dispatcher import latest_state_reason

    core, _project, parent, _sibling = await _core_with_agents(tmp_path)
    assert latest_state_reason(core, parent.id) == ""
    _set(core, parent, AgentState.RUNNING, "run_started")
    _set(core, parent, AgentState.WAITING_APPROVAL, "wait_review")
    assert latest_state_reason(core, parent.id) == "wait_review"
