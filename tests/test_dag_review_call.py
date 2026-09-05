"""CallReview 收件箱 + dag_review_call：§5 起收件箱只由显式送审
（submit_evidence_for_review / dag_bind_evidence with claim）产生；
本文件覆盖顺序守卫、D2 重绑、ignore、needs_evidence、claim 匹配、
快照裁决、compute 终态（仅 dag_record 登记），以及头条回归——
disagree-with-reason 留下 INCOMPLETE 覆盖（prj_d6212be8a2934e80）。"""

import pytest

from cloudra.base.session_class import Session
from cloudra.core.agent import Coordinator
from cloudra.infra.config import get_config
from cloudra.persistence.database import ConversationDB
from cloudra.tools.Plantool.dag_tools.dag_review_call import DagReviewCall
from tests.dag_identity import call_dag_tool, make_supervisor

_TS_FREQ_RESULT = {
    "is_success": True,
    "normal_termination": True,
    "imaginary_frequencies": [-518.3],
}


async def _call(cls, agent, session, **kwargs):
    return await call_dag_tool(cls, agent, session, **kwargs)


async def _seed_guided(
    tmp_path,
    conversation_id,
    *,
    stage_kinds=("ts_opt", "frequency"),
    calls=(),
    submissions=(),
):
    """guided 模式种子：带阶段契约的 delivery 边 + 若干已完成的工具调用
    （§5 起只登记证据）；submissions 里的 (tool_call_id, target, stage, claim)
    经显式送审入箱。"""
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
    for tool_call_id, target, stage, claim in submissions:
        submitted = await controller.submit_evidence_for_review(
            [
                {
                    "tool_call_id": tool_call_id,
                    "bind_target": target,
                    "stage_kind": stage,
                    "claim": claim,
                }
            ]
        )
        assert submitted["attachments"][0]["enqueued"] is True
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
async def test_tool_completion_never_auto_enqueues(tmp_path):
    """§5：任何工具完成（含原 dag_review 白名单工具）都不再自动入箱——
    只有显式送审产生 pending review。"""
    await _seed_guided(
        tmp_path,
        "review-throttle",
        calls=[
            ("tc-guess", "ts_guess", {"smiles": "C=COCC=C"}, {"is_success": True, "verdict": "pass"}),
            ("tc-parse", "log_parser", {"log_path": "ts.log"}, _TS_FREQ_RESULT),
            ("tc-submit", "submit_compute_job", {"input_file": "ts.gjf"}, {"is_success": True, "job_id": 4}),
            ("tc-bash", "bash", {"command": "cat ts.log"}, {"is_success": True, "output": "ok"}),
        ],
    )
    db = ConversationDB("review-throttle")
    assert _inbox(db) == []
    # 证据登记不丢：四次调用都有不可变快照。
    with db.connect() as con:
        n_evidence = con.execute("SELECT COUNT(*) FROM dag_evidence").fetchone()[0]
    assert n_evidence == 4


@pytest.mark.asyncio
async def test_agree_out_of_order_then_in_order(tmp_path):
    """顺序守卫在 review 路径同样生效：ts_opt 之前 agree frequency 被拒
    （stage_out_of_order）；按序 agree 则推进。§5：一次 opt+freq 解析的两条
    阶段声明是两条独立 review（同证据、同目标、不同 stage/claim）。"""
    _agent, session, db = await _seed_guided(
        tmp_path,
        "review-order",
        calls=[
            ("tc-opt", "log_parser", {"log_path": "ts.log"}, _TS_FREQ_RESULT),
        ],
        submissions=[
            ("tc-opt", "step1", "ts_opt", "the optimization converged to a stationary point"),
            ("tc-opt", "step1", "frequency", "exactly one imaginary frequency"),
        ],
    )
    supervisor = make_supervisor(db.conversation_id, workspace_dir=str(tmp_path))
    reviews = _inbox(db)
    assert len(reviews) == 2
    opt_review, freq_review = reviews

    early = await _call(
        DagReviewCall, supervisor, session,
        review_id=freq_review.review_id, target_id="step1",
        stage_kind="frequency", verdict="agree",
    )
    assert not early.is_success
    assert early.rejection_code == "stage_out_of_order"

    opt = await _call(
        DagReviewCall, supervisor, session,
        review_id=opt_review.review_id, target_id="step1",
        stage_kind="ts_opt", verdict="agree",
    )
    assert opt.is_success
    assert opt.accepted is True
    freq = await _call(
        DagReviewCall, supervisor, session,
        review_id=freq_review.review_id, target_id="step1",
        stage_kind="frequency", verdict="agree",
    )
    assert freq.is_success
    assert freq.accepted is True

    by_kind = {s.kind.value: s.status.value for s in _edge(db).stages}
    assert by_kind == {"ts_opt": "supported", "frequency": "supported"}
    assert _edge(db).evidence_level == "saddle_supported"
    from cloudra.dag.store import DagStore

    assert DagStore(db).get_call_review(opt_review.review_id).state == "reviewed"
    assert DagStore(db).get_call_review(freq_review.review_id).state == "reviewed"
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
            ("tc-opt", "log_parser", {"log_path": "ts.log"}, _TS_FREQ_RESULT),
        ],
        submissions=[
            ("tc-guess", "step1", "ts_opt", "the guess supports the ts_opt stage"),
            ("tc-opt", "step1", "ts_opt", "the optimization converged to a stationary point"),
            ("tc-opt", "step1", "frequency", "exactly one imaginary frequency"),
        ],
    )
    supervisor = make_supervisor(db.conversation_id, workspace_dir=str(tmp_path))
    guess_review, opt_review, freq_review = _inbox(db)

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
        review_id=freq_review.review_id, target_id="step1",
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
        submissions=[
            ("tc-guess", "step1", "ts_opt", "the guess supports the ts_opt stage"),
        ],
    )
    supervisor = make_supervisor(db.conversation_id, workspace_dir=str(tmp_path))
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
    """§5：计算作业终态不再自动入 guided 信箱（研究 agent 解析、筛选后显式
    送审）；dag_record 保留登记（纯审计，source=auto），review_id 按作业
    确定，重复回调去重。compute_jobs 已迁中央 compute.db，入箱时从中央库
    读回归属会话，再开会话库读编排模式。"""
    from cloudra.dag.controller import enqueue_compute_review
    from cloudra.persistence.database import ComputeDB
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
    compute_db = ComputeDB().init()
    with compute_db.connect() as con:
        con.execute(
            "INSERT INTO compute_jobs(conversation_id, session_id, state, path) "
            "VALUES ('review-compute', 's-child', 'done', 'ts.gjf')"
        )
        taskid = con.execute("SELECT last_insert_rowid()").fetchone()[0]

    # guided：终态只通知研究 agent（既有 compute_job 事件链），不入 review 信箱。
    await enqueue_compute_review(taskid, "done")
    with compute_db.connect() as con:
        con.execute(
            "INSERT INTO compute_jobs(conversation_id, session_id, state, path) "
            "VALUES ('review-compute', 's-child', 'failed', 'ts2.gjf')"
        )
        failed_task = con.execute("SELECT last_insert_rowid()").fetchone()[0]
    await enqueue_compute_review(failed_task, "failed")
    assert _inbox(db) == []

    # dag_record：登记为审计行（source=auto），review_id 按作业确定且去重。
    session_store.create_session_record(
        db,
        session_id="s-record",
        agent_id="small_mol",
        agent_type="small_mol",
        parent_session_id="s1",
        query="TS opt (record)",
        created_at="2026-08-10T00:00:00+00:00",
        orchestration_mode="dag_record",
    )
    with compute_db.connect() as con:
        con.execute(
            "INSERT INTO compute_jobs(conversation_id, session_id, state, path) "
            "VALUES ('review-compute', 's-record', 'done', 'ts.gjf')"
        )
        record_task = con.execute("SELECT last_insert_rowid()").fetchone()[0]
    await enqueue_compute_review(record_task, "done")
    await enqueue_compute_review(record_task, "done")  # 幂等去重

    inbox = _inbox(db)
    assert len(inbox) == 1
    row = inbox[0]
    assert row.compute_job_id == str(record_task)
    assert row.is_success is True
    assert row.caller_role_id == "small_mol"
    assert row.caller_legacy_id == "a-4"  # D13 单一映射
    assert row.source == "auto"

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
    with compute_db.connect() as con:
        con.execute(
            "INSERT INTO compute_jobs(conversation_id, session_id, state, path) "
            "VALUES ('review-compute', 's-std', 'failed', 'x.gjf')"
        )
        std_task = con.execute("SELECT last_insert_rowid()").fetchone()[0]
    await enqueue_compute_review(std_task, "failed")
    assert len(_inbox(db)) == 1


@pytest.mark.asyncio
async def test_duplicate_artifact_is_not_reenqueued(tmp_path):
    """显式送审的幂等：相同 pending 声明（同证据+目标+阶段+claim）重发返回
    既有 review_id；来源与判别元数据落库。内容变化（真实重算）产生新证据
    身份，同 claim 照常入新箱。"""
    from cloudra.dag.controller import DagController

    await _seed_guided(
        tmp_path,
        "review-dedup",
        calls=[
            (
                "tc-1",
                "log_parser",
                {"log_path": "/x/da_ts.log"},
                {"is_success": True, "frequencies_cm": [144.7], "imaginary_frequencies": [-951.72]},
            ),
        ],
    )
    db = ConversationDB("review-dedup")
    controller = DagController(db, "s1", "dag_guided", conversation_id="review-dedup")
    claim = "one imaginary frequency supports the frequency stage"

    first = await controller.submit_evidence_for_review(
        [{"tool_call_id": "tc-1", "bind_target": "step1",
          "stage_kind": "frequency", "claim": claim}]
    )
    assert first["attachments"][0]["enqueued"] is True
    # 相同声明重发：幂等成功，返回既有 review_id。
    second = await controller.submit_evidence_for_review(
        [{"tool_call_id": "tc-1", "bind_target": "step1",
          "stage_kind": "frequency", "claim": claim}]
    )
    assert second["attachments"][0]["enqueued"] is False
    assert second["attachments"][0]["review_id"] == first["attachments"][0]["review_id"]
    inbox = _inbox(db)
    assert len(inbox) == 1
    assert inbox[0].source_path == "/x/da_ts.log"
    assert inbox[0].result_kind == "ok"
    assert inbox[0].claim == claim

    # 内容不同（结果变了）⇒ 新证据身份 ⇒ 同 claim 照常入箱。
    await controller.on_tool_finished(
        "tc-2",
        "log_parser",
        {"log_path": "/x/da_ts.log"},
        {"is_success": True, "frequencies_cm": [144.7], "imaginary_frequencies": [-950.0]},
    )
    third = await controller.submit_evidence_for_review(
        [{"tool_call_id": "tc-2", "bind_target": "step1",
          "stage_kind": "frequency", "claim": claim}]
    )
    assert third["attachments"][0]["enqueued"] is True
    assert len(_inbox(db)) == 2


@pytest.mark.asyncio
async def test_review_provenance_classifies_failure(tmp_path):
    """失败判别：失败证据显式送审后，source_missing / parse_failed 等
    判别元数据挂进 review（sidecar，供 Supervisor 判断，不构成绑定权威）。"""
    _agent, _session, db = await _seed_guided(
        tmp_path,
        "review-kinds",
        calls=[
            ("tc-miss", "log_parser", {"log_path": "/x/nope.log"},
             {"is_success": False, "message": "Log file not found: /x/nope.log"}),
            ("tc-parse", "log_parser", {"log_path": "/x/bad.log"},
             {"is_success": False, "message": "Failed to parse the log: truncated"}),
        ],
        submissions=[
            ("tc-miss", "step1", "ts_opt", "negative evidence: source log is missing"),
            ("tc-parse", "step1", "frequency", "negative evidence: log truncated"),
        ],
    )
    inbox = {row.tool_call_id: row for row in _inbox(db)}
    assert inbox["tc-miss"].result_kind == "source_missing"
    assert inbox["tc-parse"].result_kind == "parse_failed"
    assert inbox["tc-miss"].source_path == "/x/nope.log"
    assert inbox["tc-miss"].is_success is False


@pytest.mark.asyncio
async def test_view_evidence_returns_full_arguments_and_result(tmp_path):
    """dag_view_evidence 开放 read：取回完整 arguments + result + 送审主张
    （claim/rationale），供 Supervisor 围绕 claim 审查快照。"""
    from cloudra.tools.Plantool.dag_tools.dag_view_evidence import DagViewEvidence

    agent, session, db = await _seed_guided(
        tmp_path,
        "review-view-evidence",
        calls=[
            (
                "tc-1",
                "log_parser",
                {"log_path": "/x/da_ts.log", "requested": ["frequencies"]},
                {"is_success": True, "imaginary_frequencies": [-951.72]},
            ),
        ],
        submissions=[
            ("tc-1", "step1", "frequency", "exactly one imaginary frequency"),
        ],
    )
    review = _inbox(db)[0]
    out = await _call(
        DagViewEvidence, agent, session, review_id=review.review_id
    )
    assert out.is_success is True
    assert out.result["source_name"] == "log_parser"
    assert out.result["arguments"]["log_path"] == "/x/da_ts.log"
    assert out.result["result"]["imaginary_frequencies"] == [-951.72]
    assert out.result["review_id"] == review.review_id
    assert out.result["claim"] == "exactly one imaginary frequency"


@pytest.mark.asyncio
async def test_needs_evidence_verdict_closes_round_without_stage_change(tmp_path):
    """needs_evidence：缺证据时明确返回缺失清单、本轮不再审（review 离开
    pending 信箱，不 busy-loop）、阶段不动；reason 必填。"""
    _agent, session, db = await _seed_guided(
        tmp_path,
        "review-needs-evidence",
        calls=[
            ("tc-opt", "log_parser", {"log_path": "ts.log"}, _TS_FREQ_RESULT),
        ],
        submissions=[
            ("tc-opt", "step1", "frequency", "exactly one imaginary frequency"),
        ],
    )
    supervisor = make_supervisor(db.conversation_id, workspace_dir=str(tmp_path))
    review = _inbox(db)[0]

    missing_reason = await _call(
        DagReviewCall, supervisor, session,
        review_id=review.review_id, target_id="step1",
        stage_kind="frequency", verdict="needs_evidence",
    )
    assert not missing_reason.is_success
    assert "reason" in missing_reason.error

    out = await _call(
        DagReviewCall, supervisor, session,
        review_id=review.review_id, target_id="step1",
        stage_kind="frequency", verdict="needs_evidence",
        reason="need the unconstrained hessian log; the submitted file is constrained",
    )
    assert out.is_success
    assert out.accepted is True
    assert out.result["verdict"] == "needs_evidence"
    assert out.result["stage_changed"] is False
    assert "unconstrained hessian" in out.result["missing_evidence"]
    # 本轮不再审：离开 pending 信箱；阶段保持 pending。
    assert _inbox(db) == []
    from cloudra.dag.store import DagStore

    assert DagStore(db).get_call_review(review.review_id).state == "reviewed"
    assert all(s.status.value == "pending" for s in _edge(db).stages)


@pytest.mark.asyncio
async def test_verdict_must_match_the_submitted_claim(tmp_path):
    """裁决围绕送审的明确 claim：verdict 的目标/阶段与送审声明不一致时
    拒绝（claim_mismatch）——要改目标/阶段就重新送审。"""
    _agent, session, db = await _seed_guided(
        tmp_path,
        "review-claim-match",
        calls=[
            ("tc-opt", "log_parser", {"log_path": "ts.log"}, _TS_FREQ_RESULT),
        ],
        submissions=[
            ("tc-opt", "step1", "ts_opt", "the optimization converged"),
        ],
    )
    supervisor = make_supervisor(db.conversation_id, workspace_dir=str(tmp_path))
    review = _inbox(db)[0]

    wrong_stage = await _call(
        DagReviewCall, supervisor, session,
        review_id=review.review_id, target_id="step1",
        stage_kind="frequency", verdict="agree",
    )
    assert not wrong_stage.is_success
    assert "claim" in wrong_stage.error
    wrong_target = await _call(
        DagReviewCall, supervisor, session,
        review_id=review.review_id, target_id="r",
        stage_kind="ts_opt", verdict="agree",
    )
    assert not wrong_target.is_success
    # 信箱未被动过：仍是 pending，可重新按声明裁决。
    assert _inbox(db) != []


@pytest.mark.asyncio
async def test_verdict_binds_the_submitted_snapshot_not_the_live_file(tmp_path):
    """快照裁决：送审后同名日志被"覆盖"（新解析产生新证据），对原 review
    的 agree 仍绑定提交时的不可变快照；dag_view_evidence 读回的也是原快照。"""
    from cloudra.tools.Plantool.dag_tools.dag_view_evidence import DagViewEvidence

    agent, session, db = await _seed_guided(
        tmp_path,
        "review-snapshot",
        calls=[
            (
                "tc-1",
                "log_parser",
                {"log_path": "/x/ts.log"},
                {"is_success": True, "scf_energy": -100.0,
                 "imaginary_frequencies": [-951.72]},
            ),
        ],
        submissions=[
            ("tc-1", "step1", "ts_opt", "the optimization converged"),
        ],
    )
    from cloudra.dag.controller import DagController

    controller = DagController(db, "s1", "dag_guided", conversation_id=db.conversation_id)
    # 同名文件被覆盖后重新解析：新证据、新内容。
    await controller.on_tool_finished(
        "tc-2",
        "log_parser",
        {"log_path": "/x/ts.log"},
        {"is_success": True, "scf_energy": -200.0, "imaginary_frequencies": [-300.0]},
    )
    review = _inbox(db)[0]

    supervisor = make_supervisor(db.conversation_id, workspace_dir=str(tmp_path))
    verdict = await _call(
        DagReviewCall, supervisor, session,
        review_id=review.review_id, target_id="step1",
        stage_kind="ts_opt", verdict="agree",
    )
    assert verdict.is_success and verdict.accepted is True
    # 绑定的是送审时快照（review.evidence_id），不是覆盖后的新证据。
    edge = _edge(db)
    assert edge.refs and edge.refs[-1].ref_id == review.evidence_id

    view = await _call(DagViewEvidence, agent, session, review_id=review.review_id)
    assert view.result["result"]["scf_energy"] == -100.0


def test_supervisor_prompt_carries_claim_snapshot_and_observation_discipline():
    """固定 fixture：督导 prompt 承载 §5 裁决契约——围绕送审 claim、以不可变
    快照为准、needs_evidence 收轮、观察 vs 推断标注。这是对 prompt 文本的
    确定性检查，不是、也不声称是幻觉率评估。"""
    from cloudra.dag.models import load_supervisor_prompt

    text = load_supervisor_prompt()
    assert "claim" in text
    assert "immutable snapshot" in text
    assert "needs_evidence" in text
    assert "observed" in text and "infer" in text
    # 先筛选再送审：未提交的探索结果不是督导待办。
    assert "never read as review work" in text or "not your todo list" in text


@pytest.mark.asyncio
async def test_legacy_auto_review_is_not_adjudicable(tmp_path):
    """历史/自动来源的 review 不是可消费信箱内容：裁决工具拒绝，只有显式
    重提后才可裁决。"""
    _agent, session, db = await _seed_guided(tmp_path, "review-legacy", calls=[])
    from cloudra.dag.models import CallReview
    from cloudra.dag.store import DagStore

    DagStore(db).enqueue_call_review(
        CallReview(
            review_id="rev_legacy",
            tool_call_id="tc_old",
            tool_name="log_parser",
            is_success=True,
            source="legacy_auto",
            state="pending",
        )
    )
    supervisor = make_supervisor(db.conversation_id, workspace_dir=str(tmp_path))
    out = await _call(
        DagReviewCall, supervisor, session,
        review_id="rev_legacy", target_id="step1",
        stage_kind="ts_opt", verdict="agree",
    )
    assert not out.is_success
    assert "legacy_auto" in out.error
    # 审计保留：行还在，状态不变。
    assert DagStore(db).get_call_review("rev_legacy").state == "pending"
