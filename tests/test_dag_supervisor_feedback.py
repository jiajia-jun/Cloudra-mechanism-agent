"""dag_guided 反馈环：督导结论回投 Coordinator（notices pin / agent.message
唤醒），以及被驳回草稿的 reject_reason 随 DAG 投影回到 Coordinator。

参照 test_dag_supervisor.py 的既有模式；core 搭建参照
test_runtime_v2_reminders.py 的 CommandBus 用法。
"""

import pytest

from cloudra.dag.controller import DagController
from cloudra.persistence.database import ConversationDB
from cloudra.runtime_v2.commands import CommandBus
from cloudra.runtime_v2.core import RuntimeCore
from cloudra.runtime_v2.schemas import Command
from cloudra.services import session_store


class FakeSupervisor:
    """返回固定报告文本的 GraphSupervisor 替身。"""

    def __init__(self, report: str = ""):
        self.report = report

    async def run(self, trigger, coordinator_request=None, session_id=None, **_kwargs):
        from cloudra.core.supervisor import GraphSupervisorResult

        return GraphSupervisorResult(trigger=trigger, report=self.report)


def _db(tmp_path, conversation_id):
    db = ConversationDB(conversation_id, data_dir=tmp_path).init()
    session_store.create_session_record(
        db,
        session_id="s1",
        agent_id="a-0",
        agent_type="coordinator",
        parent_session_id=None,
        query="mechanism",
        created_at="2026-08-10T00:00:00+00:00",
        orchestration_mode="dag_guided",
    )
    return db


async def _core_with_coordinator(name: str):
    core = RuntimeCore(strict_events=True)
    bus = CommandBus(core)
    project = (await bus.execute(Command(type="project.create", payload={"name": name}))).data
    coordinator = (
        await bus.execute(
            Command(
                type="agent.spawn",
                target={"project_id": project.id},
                payload={"role_id": "coordinator"},
            )
        )
    ).data
    return core, project, coordinator


def _wake_messages(core, session_id):
    return [
        e for e in core.event_log.query_session(session_id)
        if e.type == "agent.message_injected"
    ]


@pytest.mark.asyncio
async def test_supervision_report_pinned_into_coordinator_notices(tmp_path):
    """Coordinator 自己的工具循环触发督导（agent_id=a-0）：报告带理由 pin 进
    notices，下一轮 collect 即可见；不再重复发 agent.message。"""
    core, project, coordinator = await _core_with_coordinator("supervisor-feedback-pin")
    db = _db(tmp_path, project.id)
    supervisor = FakeSupervisor(report="Draft rejected: missing ts_opt stage for step1.")
    controller = DagController(
        db, "s1", "dag_guided",
        supervisor=supervisor,
        agent_id="a-0",
        conversation_id=project.id,
        core=core,
    )

    result = await controller.maybe_supervise("mechanism_proposed")

    assert result is not None
    pinned = core.notices.collect(coordinator.id)
    assert any(
        m["role"] == "system"
        and "[Supervisor]" in m["content"]
        and "missing ts_opt stage for step1" in m["content"]
        for m in pinned
    )
    # pin 是常驻注入：再次 collect 仍可见（turn_pipeline 每轮重建）
    assert core.notices.collect(coordinator.id)
    assert _wake_messages(core, coordinator.id) == []


@pytest.mark.asyncio
async def test_supervision_off_coordinator_loop_also_wakes(tmp_path):
    """子 Agent / API（agent_id 非 a-0）触发督导：除 pin 外再经 agent.message
    唤醒休眠的 Coordinator（终态自动 reopen，与 ReminderBroker 同一模式）。"""
    core, project, coordinator = await _core_with_coordinator("supervisor-feedback-wake")
    db = _db(tmp_path, project.id)
    supervisor = FakeSupervisor(report="Frequency review disagreed: n_imag == 2.")

    follower = DagController(
        db, "s-sub", "dag_guided",
        supervisor=supervisor,
        agent_id="a-4",
        conversation_id=project.id,
        core=core,
    )
    await follower.maybe_supervise("tool_call_review")

    api = DagController(
        db, "user_replan", "dag_guided",
        supervisor=supervisor,
        conversation_id=project.id,
        core=core,
    )
    await api.maybe_supervise("user_replan")

    pinned = core.notices.collect(coordinator.id)
    assert any("n_imag == 2" in m["content"] for m in pinned)
    wakes = _wake_messages(core, coordinator.id)
    assert len(wakes) == 2
    assert all("n_imag == 2" in str(e.data.get("content", "")) for e in wakes)
    assert all("[Supervisor]" in str(e.data.get("content", "")) for e in wakes)


@pytest.mark.asyncio
async def test_supervision_delivery_without_core_is_best_effort(tmp_path):
    """无 core 句柄（api_v2 user_replan 直连 DagController 的形态）：督导照常
    运行，投递静默降级——驳回理由改由 DAG 投影的 rejected_draft 回环。"""
    db = _db(tmp_path, "supervisor-feedback-no-core")
    supervisor = FakeSupervisor(report="Replan done.")
    controller = DagController(db, "user_replan", "dag_guided", supervisor=supervisor)

    result = await controller.maybe_supervise("user_replan")

    assert result is not None
    assert result.report == "Replan done."


_OPS = [
    {
        "op": "add_node",
        "graph": "delivery",
        "node": {"node_id": "r", "node_type": "occurrence", "label": "R", "role": "reactant"},
    },
    {
        "op": "add_node",
        "graph": "delivery",
        "node": {"node_id": "p", "node_type": "occurrence", "label": "P", "role": "product"},
    },
    {
        "op": "add_edge",
        "graph": "delivery",
        "edge": {
            "edge_id": "step1",
            "edge_type": "elementary_step",
            "source_node_id": "r",
            "target_node_id": "p",
        },
    },
]


@pytest.mark.asyncio
async def test_prompt_projection_includes_rejected_draft_reason(tmp_path):
    """to_prompt_text 带最近被驳回草稿的 reject_reason：Coordinator 下一轮
    从投影直接读到督导的驳回理由。"""
    db = _db(tmp_path, "supervisor-feedback-projection")
    controller = DagController(db, "s1", "dag_guided", supervisor=FakeSupervisor())
    await controller.initialize()
    proposed = await controller.propose_mechanism(
        operations=_OPS,
        stage_contracts={"step1": ["ts_guess", "ts_opt", "frequency"]},
        rationale="Claisen chair hypothesis",
        actor_id="a-0",
    )
    await controller.accept_mechanism(
        verdict="reject",
        rationale="step1 lacks an IRC stage; add short_irc before frequency",
        draft_id=proposed["draft_id"],
    )

    text = await controller.prompt_projection()

    assert "rejected_draft" in text
    assert proposed["draft_id"] in text
    assert "add short_irc before frequency" in text


@pytest.mark.asyncio
async def test_prompt_projection_omits_reject_reason_after_new_open_draft(tmp_path):
    """有新的 open 草稿在审时，旧驳回不再投影（最新草稿优先，驳回已被响应）。"""
    db = _db(tmp_path, "supervisor-feedback-superseded")
    controller = DagController(db, "s1", "dag_guided", supervisor=FakeSupervisor())
    await controller.initialize()
    proposed = await controller.propose_mechanism(
        operations=_OPS,
        stage_contracts={"step1": ["ts_guess", "ts_opt", "frequency"]},
        rationale="first hypothesis",
        actor_id="a-0",
    )
    await controller.accept_mechanism(
        verdict="reject",
        rationale="stale rejection reason",
        draft_id=proposed["draft_id"],
    )
    await controller.propose_mechanism(
        operations=_OPS,
        stage_contracts={"step1": ["ts_guess", "ts_opt", "frequency"]},
        rationale="revised hypothesis",
        actor_id="a-0",
    )

    text = await controller.prompt_projection()

    assert "stale rejection reason" not in text
