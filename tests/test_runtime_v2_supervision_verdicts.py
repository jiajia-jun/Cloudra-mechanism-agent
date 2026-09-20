"""裁决通知泛化（D1）与督导终态告警（D2）的回归。

D1：per-CallReview 裁决（dag_review_call）与机理草稿裁决（dag_accept_mechanism）
与结构化 ReviewDecision 共用同一张 durable 通知表与同一条
flush_review_notifications 投递通道（pin + mailbox + 条件 wake +
标记 sent 闭环，failed/cancelled 收件人 park-don't-wake）。触发点是
dag policy stage 的 after_tool（裁决工具成功）与 reconcile（恢复补投）。

D2：Supervisor 落 failed/cancelled 且有可消费督导待办时，向项目
Coordinator 发一次性告警（pin 指纹去重：状态+待办摘要不变不重复投递，
变化才再投；条件消失撤 pin）。不复活是既定纪律，缺陷只在不可见。

测试确定性约定与 test_runtime_v2_supervision.py 相同：runner-less 的
host 原语构造状态，事件流断言投递次数，轮询只作失败上限。
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone

import pytest

from cloudra.dag.models import CallReview
from cloudra.dag.store import DagStore
from cloudra.persistence.database import ConversationDB
from cloudra.runtime_v2.commands import CommandBus
from cloudra.runtime_v2.core import RuntimeCore
from cloudra.runtime_v2.schemas import AgentState, Command
from cloudra.runtime_v2.supervision import (
    TERMINAL_SUPERVISOR_PIN_KEY,
    find_project_supervisor,
    flush_review_notifications,
    notify_supervisor,
    reconcile_supervision,
)


async def _project_with_coordinator(core, bus, name: str):
    project = (
        await bus.execute(
            Command(
                type="project.create",
                payload={
                    "name": name,
                    "settings": {"orchestration_mode": "dag_guided"},
                },
            )
        )
    ).data
    coordinator = (
        await bus.execute(
            Command(
                type="agent.spawn",
                target={"project_id": project.id},
                payload={
                    "role_id": "coordinator",
                    "settings": {"orchestration_mode": "dag_guided"},
                },
            )
        )
    ).data
    return project, coordinator


def _seed_delivery(project_id: str, *, stage_kinds=("ts_opt", "frequency")) -> None:
    """guided 交付图种子：r/p 节点 + 带阶段契约（全 pending）的 step1 边。"""
    from cloudra.dag.engine import DagEngine
    from cloudra.dag.models import (
        AddEdge,
        AddNode,
        ElementaryStepEdge,
        GraphActor,
        MutationBatch,
        OccurrenceNode,
        StageState,
    )

    db = ConversationDB(project_id).init()
    store = DagStore(db)
    store.ensure_bundle("s1")
    engine = DagEngine(store)
    for node_id, label, role in (("r", "R", "reactant"), ("p", "P", "product")):
        result = engine.apply_batch(
            MutationBatch(
                session_id="s1",
                actor=GraphActor.HARNESS,
                actor_id="test-harness",
                base_revisions=store.load_bundle().revisions,
                rationale=f"seed {role}",
                operations=[
                    AddNode(
                        op="add_node",
                        graph="delivery",
                        node=OccurrenceNode(
                            node_id=node_id,
                            label=label,
                            role=role,
                            evidence_level="structure_supported",
                        ),
                    )
                ],
            )
        )
        assert result.accepted
    result = engine.apply_batch(
        MutationBatch(
            session_id="s1",
            actor=GraphActor.AGENT,
            actor_id="a-0",
            base_revisions=store.load_bundle().revisions,
            rationale="declare the stage contract for step1",
            operations=[
                AddEdge(
                    op="add_edge",
                    graph="delivery",
                    edge=ElementaryStepEdge(
                        edge_id="step1",
                        source_node_id="r",
                        target_node_id="p",
                        stages=[StageState(kind=kind) for kind in stage_kinds],
                    ),
                )
            ],
        )
    )
    assert result.accepted


def _seed_explicit_review(
    project_id: str,
    submitter_session_id: str,
    *,
    target_id: str = "step1",
    stage_kind: str = "ts_opt",
    claim: str = "the optimization converged to a stationary point",
) -> str:
    """显式送审的持久化等价物：直接入箱一条 source=explicit 的 pending review。"""
    review_id = "rev_" + uuid.uuid4().hex
    store = DagStore(ConversationDB(project_id).init())
    store.enqueue_call_review(
        CallReview(
            review_id=review_id,
            tool_call_id="tc_seed",
            tool_name="log_parser",
            is_success=True,
            caller_session_id=submitter_session_id,
            caller_role_id="coordinator",
            caller_legacy_id="a-0",
            arguments_digest="sha256:seed",
            result_summary="{}",
            suggested_target_id=target_id,
            suggested_stage=stage_kind,
            claim=claim,
            submitter="a-0",
            source="explicit",
            state="pending",
            created_at=datetime.now(timezone.utc).isoformat(),
        )
    )
    return review_id


def _controller(project_id: str):
    from cloudra.dag.controller import DagController

    return DagController(
        ConversationDB(project_id),
        "as_sv",
        "dag_guided",
        conversation_id=project_id,
    )


def _injections(core, session_id: str, needle: str):
    return [
        e
        for e in core.event_log.query_session(session_id, types={"agent.message_injected"})
        if needle in str(e.data.get("content", ""))
    ]


def _pin_events(core, session_id: str, key: str):
    return [
        e
        for e in core.event_log
        if e.type == "context.pin_set"
        and e.session_id == session_id
        and e.data.get("key") == key
    ]


def _pending_notifications(project_id: str):
    return DagStore(ConversationDB(project_id)).pending_review_notifications()


# --------------------------------------------------------------------- D1


@pytest.mark.asyncio
async def test_call_verdict_disagree_notifies_submitter_exactly_once():
    """D1(a)：Supervisor disagree 一条显式送审 → 提交者收到 pin + mailbox 的
    可行动裁决通知（verdict/stage/target/reason/next），重复 flush 不重投。"""
    core = RuntimeCore(strict_events=True)
    bus = CommandBus(core)
    project, coordinator = await _project_with_coordinator(core, bus, "verdict-call")
    await asyncio.to_thread(_seed_delivery, project.id)
    review_id = await asyncio.to_thread(
        _seed_explicit_review, project.id, coordinator.id
    )

    reviewed = await _controller(project.id).review_call(
        review_id=review_id,
        target_id="step1",
        stage_kind="ts_opt",
        verdict="disagree",
        reason="the log shows a second imaginary frequency",
    )
    assert reviewed["accepted"] is True

    handled = await flush_review_notifications(core, project.id)
    assert handled == 1
    assert await asyncio.to_thread(_pending_notifications, project.id) == []

    injections = _injections(core, coordinator.id, "[Supervisor call verdict]")
    assert len(injections) == 1
    content = injections[0].data["content"]
    assert f"review_id={review_id}" in content
    assert "verdict=disagree" in content
    assert "stage=ts_opt" in content
    assert "target=edge:step1" in content
    assert "second imaginary frequency" in content
    assert "next=" in content  # 可行动的下一步指引
    assert len(_pin_events(core, coordinator.id, f"call-verdict-{review_id}")) == 1

    # 重投幂等：第二次 flush 不再投递（mark-sent 闭环）。
    assert await flush_review_notifications(core, project.id) == 0
    assert len(_injections(core, coordinator.id, "[Supervisor call verdict]")) == 1
    assert len(_pin_events(core, coordinator.id, f"call-verdict-{review_id}")) == 1


@pytest.mark.asyncio
async def test_call_verdict_needs_evidence_notifies_with_missing_list():
    """D1(a 补充)：needs_evidence 也必须通知提交者（要求补料重提）。"""
    core = RuntimeCore(strict_events=True)
    bus = CommandBus(core)
    project, coordinator = await _project_with_coordinator(core, bus, "verdict-needs")
    await asyncio.to_thread(_seed_delivery, project.id)
    review_id = await asyncio.to_thread(
        _seed_explicit_review, project.id, coordinator.id
    )

    reviewed = await _controller(project.id).review_call(
        review_id=review_id,
        target_id="step1",
        stage_kind="ts_opt",
        verdict="needs_evidence",
        reason="need the unconstrained hessian log",
    )
    assert reviewed["accepted"] is True

    handled = await flush_review_notifications(core, project.id)
    assert handled == 1
    injections = _injections(core, coordinator.id, "[Supervisor call verdict]")
    assert len(injections) == 1
    content = injections[0].data["content"]
    assert "verdict=needs_evidence" in content
    assert "unconstrained hessian" in content


@pytest.mark.asyncio
async def test_draft_verdicts_notify_proposer_with_reason():
    """D1(b)：草稿裁决（reject 带理由 / accept）按 proposer（legacy actor id
    解析到活 session）投递 [Supervisor draft verdict] 通知。"""
    from cloudra.dag.models import (
        AddNode,
        MechanismDraft,
        OccurrenceNode,
    )

    core = RuntimeCore(strict_events=True)
    bus = CommandBus(core)
    project, coordinator = await _project_with_coordinator(core, bus, "verdict-draft")
    await asyncio.to_thread(_seed_delivery, project.id)

    def _save_draft(operations) -> str:
        store = DagStore(ConversationDB(project.id).init())
        return store.save_draft(
            MechanismDraft(
                operations=operations,
                stage_contracts={},
                rationale="proposed mechanism",
                state="open",
            ),
            actor_id="a-0",
        )

    rejected_id = await asyncio.to_thread(
        _save_draft,
        [
            AddNode(
                op="add_node",
                graph="delivery",
                node=OccurrenceNode(node_id="i0", label="I0", role="intermediate"),
            )
        ],
    )
    controller = _controller(project.id)
    rejected = await controller.accept_mechanism(
        verdict="reject",
        rationale="step 2 is not elementary — split the proton transfer",
        draft_id=rejected_id,
    )
    assert rejected["state"] == "rejected"

    accepted_id = await asyncio.to_thread(
        _save_draft,
        [
            AddNode(
                op="add_node",
                graph="delivery",
                node=OccurrenceNode(node_id="i1", label="I1", role="intermediate"),
            )
        ],
    )
    accepted = await controller.accept_mechanism(verdict="accept", draft_id=accepted_id)
    assert accepted["state"] == "accepted"

    handled = await flush_review_notifications(core, project.id)
    assert handled == 2
    assert await asyncio.to_thread(_pending_notifications, project.id) == []

    injections = _injections(core, coordinator.id, "[Supervisor draft verdict]")
    assert len(injections) == 2
    by_draft = {
        draft_id: e.data["content"]
        for e in injections
        for draft_id in (rejected_id, accepted_id)
        if draft_id in e.data["content"]
    }
    assert f"draft_id={rejected_id}" in by_draft[rejected_id]
    assert "verdict=rejected" in by_draft[rejected_id]
    assert "not elementary" in by_draft[rejected_id]
    assert "verdict=accepted" in by_draft[accepted_id]
    # legacy a-0 解析到活的 coordinator session（不是裸 legacy id 投递）。
    assert len(_pin_events(core, coordinator.id, f"draft-verdict-{rejected_id}")) == 1
    assert len(_pin_events(core, coordinator.id, f"draft-verdict-{accepted_id}")) == 1


@pytest.mark.asyncio
async def test_call_verdict_to_cancelled_submitter_parks_without_wake():
    """D1(c)：裁决通知撞上已取消的提交者——park-don't-wake：照常 pin +
    投递驻留信箱、不唤醒不复活，通知行照样闭环标记 sent。"""
    core = RuntimeCore(strict_events=True)
    bus = CommandBus(core)
    project, coordinator = await _project_with_coordinator(core, bus, "verdict-parked")
    await asyncio.to_thread(_seed_delivery, project.id)
    review_id = await asyncio.to_thread(
        _seed_explicit_review, project.id, coordinator.id
    )
    await bus.execute(
        Command(type="agent.cancel", target={"session_id": coordinator.id}, payload={})
    )
    assert coordinator.state.value == "cancelled"

    reviewed = await _controller(project.id).review_call(
        review_id=review_id,
        target_id="step1",
        stage_kind="ts_opt",
        verdict="disagree",
        reason="evidence does not answer the claim",
    )
    assert reviewed["accepted"] is True

    handled = await flush_review_notifications(core, project.id)
    assert handled == 1
    assert await asyncio.to_thread(_pending_notifications, project.id) == []
    # parked：投递驻留但不唤醒、不开新 run。
    assert coordinator.state.value == "cancelled"
    assert len(_injections(core, coordinator.id, "[Supervisor call verdict]")) == 1
    assert len(_pin_events(core, coordinator.id, f"call-verdict-{review_id}")) == 1
    runs = [
        e for e in core.event_log.query_session(coordinator.id) if e.type == "run.started"
    ]
    assert runs == []


@pytest.mark.asyncio
async def test_call_verdict_does_not_wake_waiting_approval():
    core = RuntimeCore(strict_events=True)
    bus = CommandBus(core)
    project, coordinator = await _project_with_coordinator(core, bus, "verdict-waiting")
    await asyncio.to_thread(_seed_delivery, project.id)
    review_id = await asyncio.to_thread(
        _seed_explicit_review, project.id, coordinator.id
    )
    core.agent_host.start_run(coordinator)
    core.agent_host.transition(
        coordinator, AgentState.WAITING_APPROVAL, reason="approval"
    )

    class _Runner:
        def __init__(self) -> None:
            self.scheduled: list[str] = []

        def schedule(self, session_id: str) -> None:
            self.scheduled.append(session_id)

    core.runner = _Runner()
    reviewed = await _controller(project.id).review_call(
        review_id=review_id,
        target_id="step1",
        stage_kind="ts_opt",
        verdict="disagree",
        reason="do not interrupt the parked approval",
    )
    assert reviewed["accepted"] is True
    handled = await flush_review_notifications(core, project.id)
    assert handled == 1
    assert coordinator.state is AgentState.WAITING_APPROVAL
    assert core.runner.scheduled == []


@pytest.mark.asyncio
async def test_reconcile_after_restart_flushes_unsent_call_verdict(tmp_path):
    """D1(d)：裁决落库后、投递前崩溃的重启窗口——恢复路径的
    reconcile_supervision 补投未发送的 call 裁决通知并闭环。"""
    from cloudra.runtime_v2.persistence import RuntimeStore, restore_core

    store = RuntimeStore(tmp_path / "runtime.db")
    core1 = RuntimeCore(strict_events=True)
    core1.store = store
    bus1 = CommandBus(core1)
    project, coordinator = await _project_with_coordinator(core1, bus1, "verdict-restart")
    await asyncio.to_thread(_seed_delivery, project.id)
    review_id = await asyncio.to_thread(
        _seed_explicit_review, project.id, coordinator.id
    )
    reviewed = await _controller(project.id).review_call(
        review_id=review_id,
        target_id="step1",
        stage_kind="ts_opt",
        verdict="disagree",
        reason="crashed before the notification was delivered",
    )
    assert reviewed["accepted"] is True

    # 进程重启：从持久事件重建投影（coordinator 是 queued，保持非终态）。
    core2 = RuntimeCore(strict_events=True)
    core2.store = store
    restore_core(core2, store)
    coordinator2 = core2.agents[coordinator.id]

    await reconcile_supervision(core2, project.id, auto_wake=False)

    assert await asyncio.to_thread(_pending_notifications, project.id) == []
    injections = _injections(core2, coordinator2.id, "[Supervisor call verdict]")
    assert len(injections) == 1
    assert "verdict=disagree" in injections[0].data["content"]
    assert len(_pin_events(core2, coordinator2.id, f"call-verdict-{review_id}")) == 1
    # 恢复补投幂等：再 reconcile 不重投。
    await reconcile_supervision(core2, project.id, auto_wake=False)
    assert len(_injections(core2, coordinator2.id, "[Supervisor call verdict]")) == 1


# --------------------------------------------------------------------- D2


async def _failed_supervisor(bus, core, project, coordinator):
    """spawn 项目督导并用 host 原语驱动到 failed（runner-less 确定性构造）。"""
    supervisor = (
        await bus.execute(
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
    core.agent_host.start_run(supervisor)
    core.agent_host.finish_run(supervisor, outcome="failed", error="boom")
    assert supervisor.state is AgentState.FAILED
    return supervisor


def _alert_injections(core, session_id: str):
    return _injections(core, session_id, "[Supervision] ALERT")


@pytest.mark.asyncio
async def test_dead_supervisor_with_backlog_alerts_coordinator_once_per_fingerprint():
    """D2(a/c)：failed 督导 + 显式待办 → Coordinator 收一次性告警（点名终态、
    不自动复活、待办计数与真实恢复路径）；状态摘要不变不重复，变化才再投。"""
    core = RuntimeCore(strict_events=True)
    bus = CommandBus(core)
    project, coordinator = await _project_with_coordinator(core, bus, "alert-dedup")
    supervisor = await _failed_supervisor(bus, core, project, coordinator)
    await asyncio.to_thread(_seed_delivery, project.id)
    await asyncio.to_thread(_seed_explicit_review, project.id, coordinator.id)

    await notify_supervisor(core, project.id, reason="explicit evidence submission")
    # 通知本身仍 parked 到督导信箱（不复活）。
    assert supervisor.state is AgentState.FAILED

    alerts = _alert_injections(core, coordinator.id)
    assert len(alerts) == 1
    content = alerts[0].data["content"]
    assert "terminal state failed" in content
    assert "will not auto-revive" in content
    assert "call_reviews=1" in content
    # 恢复路径必须点名真实存在的入口（agent.message / agent.restart）。
    assert "agent.message" in content and "agent.restart" in content
    assert len(_pin_events(core, coordinator.id, TERMINAL_SUPERVISOR_PIN_KEY)) == 1

    # 指纹不变（同状态同待办）：重复 notify 不再告警。
    await notify_supervisor(core, project.id, reason="unchanged state")
    assert len(_alert_injections(core, coordinator.id)) == 1
    assert len(_pin_events(core, coordinator.id, TERMINAL_SUPERVISOR_PIN_KEY)) == 1

    # 指纹变化（待办计数 1→2）：再投一次。
    await asyncio.to_thread(_seed_explicit_review, project.id, coordinator.id)
    await notify_supervisor(core, project.id, reason="backlog grew")
    alerts = _alert_injections(core, coordinator.id)
    assert len(alerts) == 2
    assert "call_reviews=2" in alerts[-1].data["content"]
    assert len(_pin_events(core, coordinator.id, TERMINAL_SUPERVISOR_PIN_KEY)) == 2


@pytest.mark.asyncio
async def test_no_alert_for_absent_or_runnable_supervisor():
    """D2(b)：督导缺失（可由 notify 正常创建）或 queued/running/succeeded
    时不产生告警；succeeded 的唤醒路径行为不变。"""
    core = RuntimeCore(strict_events=True)
    bus = CommandBus(core)
    project, coordinator = await _project_with_coordinator(core, bus, "alert-absent")
    await asyncio.to_thread(_seed_delivery, project.id)
    await asyncio.to_thread(_seed_explicit_review, project.id, coordinator.id)

    # 缺失：notify 正常 spawn（queued），无告警。
    await notify_supervisor(core, project.id, reason="first submission")
    supervisor = find_project_supervisor(core, project.id)
    assert supervisor is not None
    assert _alert_injections(core, coordinator.id) == []
    assert _pin_events(core, coordinator.id, TERMINAL_SUPERVISOR_PIN_KEY) == []

    # succeeded（正常休眠）：wake 开新 run（无 runner 只落事件），无告警。
    core.agent_host.finish_run(supervisor, outcome="succeeded")
    assert supervisor.state is AgentState.SUCCEEDED
    await notify_supervisor(core, project.id, reason="second submission")
    assert _alert_injections(core, coordinator.id) == []
    assert _pin_events(core, coordinator.id, TERMINAL_SUPERVISOR_PIN_KEY) == []
    runs = [
        e for e in core.event_log.query_session(supervisor.id) if e.type == "run.started"
    ]
    # 状态表不变：首次 notify（queued）与 succeeded 后的 notify 各 wake 开一个 run。
    assert len(runs) == 2


@pytest.mark.asyncio
async def test_reconcile_fires_and_clears_dead_supervisor_alert():
    """D2 恢复面：reconcile 在 failed 督导 + 待办时补告警；待办清空后
    （条件消失）撤下告警 pin，之后同指纹复发可再投。"""
    core = RuntimeCore(strict_events=True)
    bus = CommandBus(core)
    project, coordinator = await _project_with_coordinator(core, bus, "alert-reconcile")
    supervisor = await _failed_supervisor(bus, core, project, coordinator)
    await asyncio.to_thread(_seed_delivery, project.id)
    review_id = await asyncio.to_thread(
        _seed_explicit_review, project.id, coordinator.id
    )

    await reconcile_supervision(core, project.id)
    assert len(_alert_injections(core, coordinator.id)) == 1
    assert len(_pin_events(core, coordinator.id, TERMINAL_SUPERVISOR_PIN_KEY)) == 1
    assert supervisor.state is AgentState.FAILED  # reconcile 不复活

    # 条件消失（待办清空）：reconcile 撤 pin。
    def _resolve_review() -> None:
        DagStore(ConversationDB(project.id)).mark_call_review(review_id, "reviewed")

    await asyncio.to_thread(_resolve_review)
    await reconcile_supervision(core, project.id)
    cleared = [
        e
        for e in core.event_log
        if e.type == "context.pin_cleared"
        and e.session_id == coordinator.id
        and e.data.get("key") == TERMINAL_SUPERVISOR_PIN_KEY
    ]
    assert len(cleared) == 1
    assert len(_alert_injections(core, coordinator.id)) == 1  # 不再新投

    # 同指纹复发（撤 pin 后状态+计数与首次相同）：重新告警一次。
    await asyncio.to_thread(_seed_explicit_review, project.id, coordinator.id)
    await reconcile_supervision(core, project.id)
    assert len(_alert_injections(core, coordinator.id)) == 2
