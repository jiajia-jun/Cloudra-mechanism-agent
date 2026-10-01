"""Agent 状态机守卫表与纯规划器的直测（此前只有间接覆盖）。

``_TRANSITIONS`` 是 agent 迁移的唯一判据（命令侧 decide 与运行期 ``plan_*``
共用同一张表），但表本身此前没有任何直测：新增或改名 ``AgentState`` 而漏补
表时，``_transition_draft`` 里的 ``_TRANSITIONS.get(from_state, frozenset())``
会把该状态的**所有**迁移静默变成 ``state_conflict``——没有测试会红。

本文件把三件事钉成常驻守卫：
1. 表 ↔ 枚举的一致性（每个状态都有条目、无多余键、无自环、无死胡同）；
2. 可达性（全部状态都能从 queued 走到）；
3. 纯规划器的守卫语义与 ``wake`` 纪律逐状态的行为表。

断言只落在**事件序列与结构化字段**上（事件类型 + ``to``/``reason`` +
是否调度），不断言任何措辞。
"""

from __future__ import annotations

import pytest

from cloudra.runtime_v2.agent_host import (
    _TRANSITIONS,
    _run_finished_data,
    plan_cancel,
    plan_restart,
    plan_resume,
    plan_start_run,
    plan_transition,
    plan_wake,
)
from cloudra.runtime_v2.schemas import (
    AgentSession,
    AgentState,
    CommandRejected,
    CurrentRun,
    utc_now,
)


def _agent(state: AgentState, *, run_id: str | None = None) -> AgentSession:
    """指定状态的 agent 快照（纯规划器只读该快照，不需要 core）。"""
    session = AgentSession(
        id="as_probe",
        project_id="p_probe",
        role_id="coordinator",
        display_name="probe",
    )
    session.state = state
    session.current_run = (
        CurrentRun(run_id=run_id, started_at=utc_now()) if run_id is not None else None
    )
    return session


def _shape(drafts) -> list[tuple[str, str | None, str | None]]:
    """(事件类型, 迁移目标, 迁移原因)——状态机行为的结构投影。"""
    return [
        (draft.type, draft.data.get("to"), draft.data.get("reason")) for draft in drafts
    ]


# --------------------------------------------------------------- 表 ↔ 枚举一致性


def test_transition_table_covers_every_state_exactly() -> None:
    """每个 AgentState 必须有条目，且表里不得出现枚举外/已删除的状态。"""
    assert set(_TRANSITIONS) == set(AgentState)


def test_transition_table_has_no_self_loops() -> None:
    for state, allowed in _TRANSITIONS.items():
        assert state not in allowed, f"{state.value} 允许迁移到自身"


def test_every_state_has_an_exit() -> None:
    """没有死胡同：任何状态都至少有一条出边（终态经 queued 重开）。"""
    for state, allowed in _TRANSITIONS.items():
        assert allowed, f"{state.value} 没有任何出边"


def test_every_state_is_reachable_from_queued() -> None:
    """从初始态 queued 出发，7 个状态全部可达（表里没有孤岛）。"""
    seen = {AgentState.QUEUED}
    frontier = [AgentState.QUEUED]
    while frontier:
        state = frontier.pop()
        for nxt in _TRANSITIONS[state]:
            if nxt not in seen:
                seen.add(nxt)
                frontier.append(nxt)
    assert seen == set(AgentState)


def test_terminal_states_reopen_only_through_queued() -> None:
    """failed/cancelled 的唯一出口是 queued：语义上强制「重开」而非「续跑」。"""
    assert _TRANSITIONS[AgentState.FAILED] == frozenset({AgentState.QUEUED})
    assert _TRANSITIONS[AgentState.CANCELLED] == frozenset({AgentState.QUEUED})


def test_only_running_reaches_succeeded() -> None:
    predecessors = {
        state for state, allowed in _TRANSITIONS.items() if AgentState.SUCCEEDED in allowed
    }
    assert predecessors == {AgentState.RUNNING}


def test_waiting_states_cannot_jump_to_succeeded() -> None:
    """等待态必须经 running 才能收尾，不能直接跨到 succeeded。"""
    for state in (AgentState.WAITING_INPUT, AgentState.WAITING_APPROVAL):
        assert AgentState.SUCCEEDED not in _TRANSITIONS[state]


# ------------------------------------------------------------------ 守卫语义


def test_illegal_transition_rejected_with_stable_code() -> None:
    with pytest.raises(CommandRejected) as excinfo:
        plan_transition(_agent(AgentState.QUEUED), AgentState.SUCCEEDED, reason="probe")
    assert excinfo.value.code == "state_conflict"


def test_start_run_only_from_queued_or_succeeded() -> None:
    for state in (AgentState.QUEUED, AgentState.SUCCEEDED):
        run_id, drafts = plan_start_run(_agent(state))
        assert run_id
        assert _shape(drafts) == [
            ("agent.state_changed", "running", "run_started"),
            ("run.started", None, None),
        ]

    for state in (
        AgentState.RUNNING,
        AgentState.WAITING_INPUT,
        AgentState.WAITING_APPROVAL,
        AgentState.FAILED,
        AgentState.CANCELLED,
    ):
        with pytest.raises(CommandRejected):
            plan_start_run(_agent(state, run_id="run_x"))


def test_restart_requires_terminal_state() -> None:
    for state in (AgentState.FAILED, AgentState.CANCELLED, AgentState.SUCCEEDED):
        _, drafts = plan_restart(_agent(state))
        assert _shape(drafts) == [("agent.state_changed", "queued", "restart")]

    for state in (
        AgentState.QUEUED,
        AgentState.RUNNING,
        AgentState.WAITING_INPUT,
        AgentState.WAITING_APPROVAL,
    ):
        with pytest.raises(CommandRejected):
            plan_restart(_agent(state, run_id="run_x"))


def test_resume_requires_waiting_state_with_live_run() -> None:
    for state in (AgentState.WAITING_INPUT, AgentState.WAITING_APPROVAL):
        run_id, drafts = plan_resume(_agent(state, run_id="run_live"))
        assert run_id == "run_live"
        assert _shape(drafts) == [("agent.state_changed", "running", "resumed")]

    for state in (AgentState.QUEUED, AgentState.RUNNING, AgentState.SUCCEEDED):
        with pytest.raises(CommandRejected):
            plan_resume(_agent(state, run_id="run_x"))

    # 等待态却没有活 run：状态与 current_run 的组合是坏的，必须拒绝而不是猜。
    with pytest.raises(CommandRejected):
        plan_resume(_agent(AgentState.WAITING_INPUT))


def test_cancel_semantics() -> None:
    assert plan_cancel(_agent(AgentState.CANCELLED)) == []

    for state in (AgentState.QUEUED, AgentState.RUNNING):
        drafts = plan_cancel(_agent(state, run_id="run_x"))
        assert _shape(drafts) == [("agent.state_changed", "cancelled", "cancel")]

    # succeeded 非挂起态是终态；只有 background parked 才允许取消。
    with pytest.raises(CommandRejected):
        plan_cancel(_agent(AgentState.SUCCEEDED))
    assert _shape(plan_cancel(_agent(AgentState.SUCCEEDED), allow_parked=True)) == [
        ("agent.state_changed", "cancelled", "cancel")
    ]

    # failed 不能被取消（重开走 restart）。
    with pytest.raises(CommandRejected):
        plan_cancel(_agent(AgentState.FAILED))


# --------------------------------------------------------------- wake 纪律


@pytest.mark.parametrize(
    ("state", "run_id", "expected"),
    [
        (AgentState.RUNNING, "run_x", ([], False)),
        (AgentState.QUEUED, None, (None, True)),
        (AgentState.SUCCEEDED, None, (None, True)),
        (AgentState.FAILED, None, (None, True)),
        (AgentState.CANCELLED, None, (None, True)),
        (AgentState.WAITING_INPUT, "run_live", (None, True)),
        (AgentState.WAITING_APPROVAL, "run_live", (None, True)),
    ],
)
def test_wake_discipline_per_state(state, run_id, expected) -> None:
    """wake 的行为表：RUNNING 是 no-op，终态先重开，等待态续跑同一个 run。"""
    expected_shape, expected_schedule = expected
    drafts, should_schedule = plan_wake(_agent(state, run_id=run_id))
    assert should_schedule is expected_schedule

    if expected_shape is not None:
        assert _shape(drafts) == expected_shape
    elif state in (AgentState.FAILED, AgentState.CANCELLED):
        # 先回到 queued（restart），再由同一次规划开出新 run。
        assert _shape(drafts) == [
            ("agent.state_changed", "queued", "restart"),
            ("agent.state_changed", "running", "run_started"),
            ("run.started", None, None),
        ]
    elif state in (AgentState.WAITING_INPUT, AgentState.WAITING_APPROVAL):
        # 续跑挂起的那个 run，不新开。
        assert _shape(drafts) == [("agent.state_changed", "running", "resumed")]
        assert drafts[0].run_id == "run_live"
    else:
        assert _shape(drafts) == [
            ("agent.state_changed", "running", "run_started"),
            ("run.started", None, None),
        ]


def test_wake_on_waiting_without_current_run_rejected() -> None:
    with pytest.raises(CommandRejected):
        plan_wake(_agent(AgentState.WAITING_APPROVAL))


# ------------------------------------------------------- 失败分类的硬不变量


def test_failed_run_finished_payload_requires_failure_kind() -> None:
    """评审 5.10 的硬不变量：失败的 run 必须带结构化分类，漏传就地 fail-loud。"""
    with pytest.raises(ValueError):
        _run_finished_data("failed", error="boom", failure_kind=None)

    assert _run_finished_data("succeeded", error=None, failure_kind=None) == {
        "outcome": "succeeded",
        "error": None,
        "failure_kind": None,
    }
