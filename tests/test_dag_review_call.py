"""CallReview 收件箱 + dag_review_call（Phase 2）：enqueue 节流、顺序守卫、
D2 重绑、ignore、compute 终态入箱、D14 唤醒合并，以及头条回归——
disagree-with-reason 留下 INCOMPLETE 覆盖（prj_d6212be8a2934e80）。"""

import asyncio

import pytest

from cloudra.base.session_class import Session
from cloudra.core.agent import Coordinator
from cloudra.core.supervisor import SupervisorAgent
from cloudra.infra.config import get_config
from cloudra.persistence.database import ConversationDB
from cloudra.tools.Plantool.dag_tools.dag_review_call import DagReviewCall

_TS_FREQ_RESULT = {
    "is_success": True,
    "normal_termination": True,
    "imaginary_frequencies": [-518.3],
}


def _schema(cls):
    return cls.model_fields["input_schema"].default


async def _call(cls, agent, session, **kwargs):
    return await cls(subagent=agent).tool_call(_schema(cls)(**kwargs), session)


async def _seed_guided(
    tmp_path,
    conversation_id,
    *,
    stage_kinds=("ts_opt", "frequency"),
    calls=(),
):
    """guided 模式种子：带阶段契约的 delivery 边 + 若干已完成的工具调用
    （每次调用入一条 pending CallReview）。"""
    from cloudra.dag.controller import DagController
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
    from cloudra.dag.store import DagStore

    get_config().data_dir = tmp_path
    agent = Coordinator(
        query="study a mechanism",
        conversation_id=conversation_id,
        orchestration_mode="dag_guided",
    )
    session = Session("s1", str(tmp_path / "session.json"))
    db = ConversationDB(conversation_id).init()
    store = DagStore(db)
    store.ensure_bundle("s1")
    # 物种出现节点由 harness 批次落在 structure_supported（legacy 等级路径），
    # 让覆盖报告只看 step1 的阶段状态。
    seeded_nodes = DagEngine(store).apply_batch(
        MutationBatch(
            session_id="s1",
            actor=GraphActor.HARNESS,
            actor_id="test-harness",
            base_revisions=store.load_bundle().revisions,
            rationale="seed supported species occurrences",
            operations=[
                AddNode(
                    op="add_node",
                    graph="delivery",
                    node=OccurrenceNode(
                        node_id="r",
                        label="R",
                        role="reactant",
                        evidence_level="structure_supported",
                    ),
                ),
                AddNode(
                    op="add_node",
                    graph="delivery",
                    node=OccurrenceNode(
                        node_id="p",
                        label="P",
                        role="product",
                        evidence_level="structure_supported",
                    ),
                ),
            ],
        )
    )
    assert seeded_nodes.accepted
    # 阶段契约由 Coordinator（actor=agent, a-0）以全 pending 声明。
    seeded = DagEngine(store).apply_batch(
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
                ),
            ],
        )
    )
    assert seeded.accepted
    controller = DagController(db, "s1", "dag_guided", conversation_id=conversation_id)
    for call_id, tool_name, arguments, result in calls:
        await controller.on_tool_finished(call_id, tool_name, arguments, result)
    return agent, session, db


def _inbox(db):
    from cloudra.dag.store import DagStore

    return DagStore(db).list_call_reviews()


def _report(db):
    from cloudra.dag.completion import evaluate_delivery
    from cloudra.dag.models import CoverageContract
    from cloudra.dag.store import DagStore

    return evaluate_delivery(
        DagStore(db).load_snapshot().delivery,
        CoverageContract.mechanism_default(),
    )


def _edge(db, edge_id="step1"):
    from cloudra.dag.store import DagStore

    graph = DagStore(db).load_snapshot().delivery
    return next(e for e in graph.edges if e.edge_id == edge_id)


@pytest.mark.asyncio
async def test_review_tool_enqueues_but_submit_and_bash_do_not(tmp_path):
    """D5 节流：dag_review 工具入箱；submit_compute_job 调用与普通 bash 不入。"""
    await _seed_guided(
        tmp_path,
        "review-throttle",
        calls=[
            ("tc-guess", "ts_guess", {"smiles": "C=COCC=C"}, {"is_success": True, "verdict": "pass"}),
            ("tc-submit", "submit_compute_job", {"input_file": "ts.gjf"}, {"is_success": True, "job_id": 4}),
            ("tc-bash", "bashtools", {"command": "cat ts.log"}, {"is_success": True, "output": "ok"}),
        ],
    )
    db = ConversationDB("review-throttle")

    inbox = _inbox(db)
    assert [row.tool_name for row in inbox] == ["ts_guess"]
    assert inbox[0].tool_call_id == "tc-guess"
    assert inbox[0].is_success is True
    assert inbox[0].state == "pending"


@pytest.mark.asyncio
async def test_agree_out_of_order_then_in_order(tmp_path):
    """顺序守卫在 review 路径同样生效：ts_opt 之前 agree frequency 被拒
    （stage_out_of_order）；按序 agree 则推进。"""
    _agent, session, db = await _seed_guided(
        tmp_path,
        "review-order",
        calls=[
            ("tc-opt", "gaussian_log_parser", {"log_path": "ts.log"}, _TS_FREQ_RESULT),
        ],
    )
    supervisor = SupervisorAgent(
        conversation_id=db.conversation_id, orchestration_mode="dag_guided"
    )
    review = _inbox(db)[0]

    early = await _call(
        DagReviewCall, supervisor, session,
        review_id=review.review_id, target_id="step1",
        stage_kind="frequency", verdict="agree",
    )
    assert not early.is_success
    assert early.rejection_code == "stage_out_of_order"

    opt = await _call(
        DagReviewCall, supervisor, session,
        review_id=review.review_id, target_id="step1",
        stage_kind="ts_opt", verdict="agree",
    )
    assert opt.is_success
    assert opt.accepted is True
    freq = await _call(
        DagReviewCall, supervisor, session,
        review_id=review.review_id, target_id="step1",
        stage_kind="frequency", verdict="agree",
    )
    assert freq.is_success
    assert freq.accepted is True

    by_kind = {s.kind.value: s.status.value for s in _edge(db).stages}
    assert by_kind == {"ts_opt": "supported", "frequency": "supported"}
    assert _edge(db).evidence_level == "saddle_supported"
    from cloudra.dag.store import DagStore

    assert DagStore(db).get_call_review(review.review_id).state == "reviewed"
    assert _report(db).complete


@pytest.mark.asyncio
async def test_disagree_with_reason_leaves_coverage_incomplete(tmp_path):
    """prj_d6212be8a2934e80 头条回归：Supervisor disagree（带理由）→ 阶段
    rejected、覆盖 INCOMPLETE；rejected 可经重绑恢复（D2）。"""
    _agent, session, db = await _seed_guided(
        tmp_path,
        "review-veto-incomplete",
        calls=[
            ("tc-guess", "ts_guess", {"smiles": "C=COCC=C"}, {"is_success": True, "verdict": "pass"}),
            ("tc-opt", "gaussian_log_parser", {"log_path": "ts.log"}, _TS_FREQ_RESULT),
        ],
    )
    supervisor = SupervisorAgent(
        conversation_id=db.conversation_id, orchestration_mode="dag_guided"
    )
    guess_review, opt_review = _inbox(db)

    veto = await _call(
        DagReviewCall, supervisor, session,
        review_id=guess_review.review_id, target_id="step1",
        stage_kind="ts_opt", verdict="disagree",
        reason="the guess is not a validated saddle point",
    )
    assert veto.is_success
    assert veto.accepted is True

    report = _report(db)
    assert not report.complete
    gap = next(g for g in report.unresolved if g.code == "stage_rejected")
    assert "not a validated saddle point" in gap.detail

    # D2：用真实 opt+freq 证据重绑 rejected 阶段 → supported，最终 complete
    rebind = await _call(
        DagReviewCall, supervisor, session,
        review_id=opt_review.review_id, target_id="step1",
        stage_kind="ts_opt", verdict="agree",
    )
    assert rebind.is_success
    assert rebind.accepted is True
    freq = await _call(
        DagReviewCall, supervisor, session,
        review_id=opt_review.review_id, target_id="step1",
        stage_kind="frequency", verdict="agree",
    )
    assert freq.accepted is True
    assert _report(db).complete


@pytest.mark.asyncio
async def test_ignore_leaves_stages_untouched(tmp_path):
    _agent, session, db = await _seed_guided(
        tmp_path,
        "review-ignore",
        calls=[
            ("tc-guess", "ts_guess", {"smiles": "C=COCC=C"}, {"is_success": True, "verdict": "pass"}),
        ],
    )
    supervisor = SupervisorAgent(
        conversation_id=db.conversation_id, orchestration_mode="dag_guided"
    )
    review = _inbox(db)[0]

    out = await _call(
        DagReviewCall, supervisor, session,
        review_id=review.review_id, target_id="step1",
        stage_kind="ts_opt", verdict="ignore",
    )

    assert out.is_success
    assert out.accepted is True
    assert out.result["stage_changed"] is False
    assert all(s.status.value == "pending" for s in _edge(db).stages)
    from cloudra.dag.store import DagStore

    assert DagStore(db).get_call_review(review.review_id).state == "ignored"


@pytest.mark.asyncio
async def test_review_call_mode_and_actor_gates(tmp_path):
    """dag_review_call 只在 dag_guided 且仅 Supervisor 可用。"""
    agent, session, db = await _seed_guided(
        tmp_path, "review-gates", calls=[]
    )
    from cloudra.dag.models import CallReview
    from cloudra.dag.store import DagStore

    DagStore(db).enqueue_call_review(
        CallReview(review_id="rev_x", tool_name="ts_guess", is_success=True)
    )

    coordinator = await _call(
        DagReviewCall, agent, session,
        review_id="rev_x", target_id="step1", stage_kind="ts_opt", verdict="ignore",
    )
    assert not coordinator.is_success
    assert "supervisor-only" in coordinator.error

    record_agent = Coordinator(
        query="q", conversation_id="review-gates", orchestration_mode="dag_record"
    )
    record = await _call(
        DagReviewCall, record_agent, session,
        review_id="rev_x", target_id="step1", stage_kind="ts_opt", verdict="ignore",
    )
    assert not record.is_success
    assert "dag_record" in record.error


@pytest.mark.asyncio
async def test_compute_job_terminal_state_enqueues_review(tmp_path):
    """D11：计算作业的终态入箱（带作业终态，而非 submit 调用的成败）；
    review_id 按作业确定，重复回调去重。"""
    from cloudra.dag.controller import enqueue_compute_review
    from cloudra.services import session_store

    get_config().data_dir = tmp_path
    db = ConversationDB("review-compute").init()
    session_store.create_session_record(
        db,
        session_id="s-child",
        agent_id="small_mol",
        agent_type="small_mol",
        parent_session_id="s1",
        query="TS opt",
        created_at="2026-08-10T00:00:00+00:00",
        orchestration_mode="dag_guided",
    )
    with db.connect() as con:
        con.execute(
            "INSERT INTO compute_jobs(conversation_id, session_id, state, path) "
            "VALUES ('review-compute', 's-child', 'done', 'ts.gjf')"
        )
        taskid = con.execute("SELECT last_insert_rowid()").fetchone()[0]

    await enqueue_compute_review(db, taskid, "done")
    await enqueue_compute_review(db, taskid, "done")  # 幂等去重

    inbox = _inbox(db)
    assert len(inbox) == 1
    row = inbox[0]
    assert row.compute_job_id == str(taskid)
    assert row.is_success is True
    assert row.caller_role_id == "small_mol"
    assert row.caller_legacy_id == "a-4"  # D13 单一映射

    # standard 模式的会话不入箱
    session_store.create_session_record(
        db,
        session_id="s-std",
        agent_id="small_mol",
        agent_type="small_mol",
        parent_session_id=None,
        query="plain",
        created_at="2026-08-10T00:00:00+00:00",
        orchestration_mode="standard",
    )
    with db.connect() as con:
        con.execute(
            "INSERT INTO compute_jobs(conversation_id, session_id, state, path) "
            "VALUES ('review-compute', 's-std', 'failed', 'x.gjf')"
        )
        std_task = con.execute("SELECT last_insert_rowid()").fetchone()[0]
    await enqueue_compute_review(db, std_task, "failed")
    assert len(_inbox(db)) == 1


@pytest.mark.asyncio
async def test_supervisor_wakes_coalesce_while_running(tmp_path):
    """D14：督导运行中的触发折叠成一次合并运行，不再一个事件一整轮。"""
    from cloudra.dag.controller import DagController

    class SlowSupervisor:
        def __init__(self) -> None:
            self.triggers: list[str] = []
            self.started = asyncio.Event()
            self.release = asyncio.Event()

        async def run(self, trigger, **_kwargs):
            self.triggers.append(trigger)
            self.started.set()
            await self.release.wait()
            return None

    get_config().data_dir = tmp_path
    db = ConversationDB("review-coalesce").init()
    supervisor = SlowSupervisor()
    controller = DagController(db, "s1", "dag_guided", supervisor=supervisor)
    try:
        first = asyncio.create_task(controller.maybe_supervise("tool_call_review"))
        await supervisor.started.wait()
        # 运行期间的触发全部折叠
        assert await controller.maybe_supervise("delivery_updated") is None
        assert await controller.maybe_supervise("tool_call_review") is None
        supervisor.release.set()
        await first
    finally:
        DagController._SUPERVISION_STATES.pop("review-coalesce", None)

    # 3 个触发只跑出 2 轮：首轮 + 一次合并轮
    assert len(supervisor.triggers) == 2
    assert supervisor.triggers[0] == "tool_call_review"
