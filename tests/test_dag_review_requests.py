"""Task 6：结构化审查请求/裁决与异常汇总。"""

import pytest

from cloudra.dag.models import GraphRef
from cloudra.dag.review_requests import ReviewDecision, ReviewRequest
from cloudra.dag.store import DagStore
from cloudra.persistence.database import ConversationDB


def _store(tmp_path, conversation_id="review-req"):
    db = ConversationDB(conversation_id, data_dir=tmp_path).init()
    store = DagStore(db)
    store.ensure_bundle("s1")
    return store


def _ref(ev_id="ev_1", hash_="sha256:aaa"):
    return GraphRef(ref_type="tool_result", ref_id=ev_id, content_hash=hash_)


def _req(**kwargs):
    base = dict(
        kind="evidence",
        requester="small_mol",
        target_ids=["step1"],
        question="Is the endpoint identity mismatch counterevidence?",
        basis_fingerprint="basis-v1",
    )
    base.update(kwargs)
    return ReviewRequest(**base)


def test_enqueue_dedup_same_kind_scope_basis(tmp_path):
    store = _store(tmp_path)
    r1 = store.enqueue_review(_req())
    r2 = store.enqueue_review(_req())
    assert r1 == r2
    assert len(store.list_review_requests(state="queued")) == 1


def test_new_basis_is_new_request(tmp_path):
    store = _store(tmp_path)
    r1 = store.enqueue_review(_req())
    r2 = store.enqueue_review(_req(basis_fingerprint="basis-v2"))
    assert r1 != r2
    assert len(store.list_review_requests(state="queued")) == 2


def test_deleting_request_target_supersedes_queued_request(tmp_path):
    """定向到被删目标的 queued 结构化请求退出待办（superseded），不删历史行。"""
    from cloudra.dag.engine import DagEngine
    from cloudra.dag.models import (
        AddEdge,
        AddNode,
        ElementaryStepEdge,
        GraphActor,
        MutationBatch,
        OccurrenceNode,
        RemoveEdge,
    )

    store = _store(tmp_path, "review-req-delete")
    # 种一个带 step1 边的图
    seeded = DagEngine(store).apply_batch(
        MutationBatch(
            session_id="s1",
            actor=GraphActor.AGENT,
            actor_id="a-0",
            base_revisions=store.load_bundle().revisions,
            rationale="seed",
            operations=[
                AddNode(op="add_node", graph="delivery", node=OccurrenceNode(node_id="r", label="R")),
                AddNode(op="add_node", graph="delivery", node=OccurrenceNode(node_id="p", label="P")),
                AddEdge(op="add_edge", graph="delivery", edge=ElementaryStepEdge(
                    edge_id="step1", source_node_id="r", target_node_id="p")),
            ],
        )
    )
    assert seeded.accepted
    request_id = store.enqueue_review(_req(target_ids=["step1"]))
    assert store.get_review_request(request_id).state == "queued"

    removed = DagEngine(store).apply_batch(
        MutationBatch(
            session_id="s1",
            actor=GraphActor.AGENT,
            actor_id="a-0",
            base_revisions=store.load_bundle().revisions,
            rationale="path removed",
            operations=[RemoveEdge(op="remove_edge", graph="delivery", edge_id="step1")],
        )
    )
    assert removed.accepted

    # 待办退出；历史行保留为 superseded
    assert store.list_review_requests("queued") == []
    assert store.get_review_request(request_id).state == "superseded"


def test_resolve_review_valid_basis_marks_request_resolved(tmp_path):
    store = _store(tmp_path)
    request_id = store.enqueue_review(_req())
    decision = ReviewDecision(
        request_id=request_id,
        basis_fingerprint="basis-v1",
        verdict="accept",
        reason="mismatch is real; stop the path",
        evidence_refs=[],
        findings=[{
            "target_id": "step1",
            "check": "identity",
            "outcome": "refutes",
            "reason": "product graph differs from SMILES",
        }],
        next_action=None,
    )
    out = store.resolve_review(decision, expected_basis="basis-v1")
    assert out["accepted"] is True
    assert store.get_review_request(request_id).state == "resolved"


def test_resolve_review_stale_basis_rejected(tmp_path):
    store = _store(tmp_path)
    request_id = store.enqueue_review(_req())
    decision = ReviewDecision(
        request_id=request_id,
        basis_fingerprint="old-basis",
        verdict="accept",
        reason="would act on stale evidence",
    )
    out = store.resolve_review(decision, expected_basis="new-basis")
    assert out["accepted"] is False
    assert out["rejection_code"] == "stale_basis"
    assert store.get_review_request(request_id).state == "queued"


def test_resolve_review_duplicate_decision_rejected(tmp_path):
    store = _store(tmp_path)
    request_id = store.enqueue_review(_req())
    d1 = ReviewDecision(
        request_id=request_id,
        basis_fingerprint="basis-v1",
        verdict="reject",
        reason="not enough evidence",
        next_action="run endpoint identity check",
    )
    assert store.resolve_review(d1, expected_basis="basis-v1")["accepted"]
    d2 = ReviewDecision(
        request_id=request_id,
        basis_fingerprint="basis-v1",
        verdict="accept",
        reason="duplicate should not be applied",
    )
    out = store.resolve_review(d2, expected_basis="basis-v1")
    assert out["accepted"] is False
    assert out["rejection_code"] == "duplicate_decision"


def test_collect_review_exceptions_returns_contradiction_and_gaps(tmp_path):
    from cloudra.dag.evidence_facts import EvidenceFact, FactSubject

    store = _store(tmp_path, "review-exceptions")
    ref = _ref("ev_mismatch", "sha256:mmm")
    store.record_facts([
        EvidenceFact(
            fact_id="fact_mismatch",
            check="identity",
            outcome="refutes",
            subject=FactSubject(target_hint="step1"),
            source_refs=[ref],
            details={"reactant_identity": "match", "product_identity": "mismatch"},
        ),
        EvidenceFact(
            fact_id="fact_unbound",
            check="energy",
            outcome="supports",
            subject=FactSubject(target_hint="step1"),
            source_refs=[_ref("ev_unbound", "sha256:uuu")],
            details={"energy": -1.0},
        ),
        EvidenceFact(
            fact_id="fact_untargeted",
            check="path",
            outcome="supports",
            subject=FactSubject(),
            source_refs=[_ref("ev_untargeted", "sha256:ttt")],
            details={},
        ),
    ])
    exceptions = store.collect_review_exceptions(["step1"])
    categories = {item["category"] for item in exceptions}
    # The target-hinted mismatch is a contradiction; the unbound target-hinted
    # fact is also visible; no target key facts are listed separately.
    assert "contradiction" in categories
    assert "known_target_unbound_fact" in categories
    assert "untargeted_key_fact" in categories
    keys = [item["exception_key"] for item in exceptions]
    assert len(keys) == len(set(keys))  # stable unique keys


@pytest.mark.asyncio
async def test_dag_message_supervisor_structured_request_allows_follower_evidence(tmp_path):
    from cloudra.base.session_class import Session
    from cloudra.infra.config import get_config
    from cloudra.persistence.database import ConversationDB
    from cloudra.tools.Plantool.dag_tools.dag_message_supervisor import (
        DagMessageSupervisor,
    )
    from cloudra.tools.Plantool.dag_tools.dag_review_evidence import (
        DagReviewEvidence,
    )
    from tests.dag_identity import (
        call_dag_tool,
        make_coordinator,
        make_subagent,
        make_supervisor,
    )

    get_config().data_dir = tmp_path
    conversation_id = "structured-msg"
    follower = make_subagent(conversation_id, "small_mol", orchestration_mode="dag_guided")
    session = Session("s1", str(tmp_path / "session.json"))
    db = ConversationDB(conversation_id, data_dir=tmp_path).init()
    DagStore(db).ensure_bundle("s1")
    # A follower can submit evidence/exception review requests.
    out = await DagMessageSupervisor(subagent=follower).tool_call(
        DagMessageSupervisor.model_fields["input_schema"].default(
            kind="evidence",
            question="Check whether the product mismatch is counterevidence.",
            target_ids=["step1"],
        ),
        session,
    )
    assert out.is_success and out.accepted
    request_id = out.result["request_id"]
    assert DagStore(db).get_review_request(request_id) is not None

    # Coordinator can resolve? Actually Supervisor resolves via dag_review_evidence.
    coordinator = make_coordinator(conversation_id, orchestration_mode="dag_guided")
    # Exit requests require Coordinator.
    exit_out = await DagMessageSupervisor(subagent=coordinator).tool_call(
        DagMessageSupervisor.model_fields["input_schema"].default(
            kind="exit",
            question="Approve partial delivery?",
            target_ids=["step1"],
            proposal={
                "disposition": "partial",
                "scope": {"targets": ["step1"]},
                "remaining_gaps": ["endpoint_b optimization"],
                "method_limits": ["MACE PES"],
            },
        ),
        session,
    )
    assert exit_out.is_success and exit_out.accepted

    # Supervisor resolves the evidence request.
    supervisor = make_supervisor(conversation_id, workspace_dir=str(tmp_path))
    sv_out = await call_dag_tool(
        DagReviewEvidence,
        supervisor,
        session,
        request_id=request_id,
        verdict="reject",
        reason="mismatch is already registered as refutes",
        findings=[{
            "target_id": "step1",
            "check": "identity",
            "outcome": "refutes",
            "reason": "product mismatch",
        }],
        next_action="remove the wrong endpoint from the path",
    )
    assert sv_out.is_success and sv_out.accepted
    assert DagStore(db).get_review_request(request_id).state == "resolved"


# --- §5 显式送审：选择性提交、校验与批量原子性（controller/工具层） ---


async def _guided_seed(tmp_path, conversation_id, *, n_calls=0, stage_kinds=("ts_opt", "frequency")):
    """guided 种子：step1 边（阶段契约）+ n_calls 次已完成的 log_parser 调用
    （只登记证据，不再自动入箱）。返回 (agent, session, db, controller)。"""
    from cloudra.base.session_class import Session
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
    from cloudra.infra.config import get_config
    from tests.dag_identity import make_coordinator

    get_config().data_dir = tmp_path
    agent = make_coordinator(conversation_id, orchestration_mode="dag_guided")
    session = Session("s1", str(tmp_path / "session.json"))
    db = ConversationDB(conversation_id, data_dir=tmp_path).init()
    store = DagStore(db)
    store.ensure_bundle("s1")
    seeded_nodes = DagEngine(store).apply_batch(
        MutationBatch(
            session_id="s1",
            actor=GraphActor.HARNESS,
            actor_id="test-harness",
            base_revisions=store.load_bundle().revisions,
            rationale="seed supported species occurrences",
            operations=[
                AddNode(op="add_node", graph="delivery", node=OccurrenceNode(
                    node_id="r", label="R", role="reactant",
                    evidence_level="structure_supported")),
                AddNode(op="add_node", graph="delivery", node=OccurrenceNode(
                    node_id="p", label="P", role="product",
                    evidence_level="structure_supported")),
            ],
        )
    )
    assert seeded_nodes.accepted
    seeded = DagEngine(store).apply_batch(
        MutationBatch(
            session_id="s1",
            actor=GraphActor.AGENT,
            actor_id="a-0",
            base_revisions=store.load_bundle().revisions,
            rationale="seed step1 with a stage contract",
            operations=[
                AddEdge(op="add_edge", graph="delivery", edge=ElementaryStepEdge(
                    edge_id="step1", source_node_id="r", target_node_id="p",
                    stages=[StageState(kind=k) for k in stage_kinds])),
            ],
        )
    )
    assert seeded.accepted
    controller = DagController(db, "s1", "dag_guided", conversation_id=conversation_id)
    for i in range(n_calls):
        await controller.on_tool_finished(
            f"tc-{i}", "log_parser", {"log_path": f"/w/log{i}.out"},
            {"is_success": True, "scf_energy": -100.0 - i},
        )
    return agent, session, db, controller


@pytest.mark.asyncio
async def test_only_explicitly_selected_evidence_enters_the_inbox(tmp_path):
    """24 份探索证据只选 2 份送审 → 仅这 2 份入箱（带 claim/rationale），
    其余 22 份留在证据库不成为督导待办。"""
    from cloudra.tools.Plantool.dag_tools.dag_bind_evidence import DagBindEvidence

    agent, session, db, _controller = await _guided_seed(tmp_path, "selective", n_calls=24)
    out = await DagBindEvidence(subagent=agent).tool_call(
        DagBindEvidence.model_fields["input_schema"].default(
            attachments=[
                {
                    "tool_call_id": "tc-3",
                    "bind_target": "step1",
                    "stage_kind": "ts_opt",
                    "claim": "tc-3 geometry is a converged saddle guess refinement",
                    "rationale": "lowest-energy candidate of the batch",
                },
                {
                    "tool_call_id": "tc-7",
                    "bind_target": "step1",
                    "stage_kind": "frequency",
                    "claim": "tc-7 frequency run shows exactly one imaginary mode",
                },
            ]
        ),
        session,
    )
    assert out.is_success and out.accepted
    pending = DagStore(db).list_call_reviews("pending")
    assert len(pending) == 2
    by_call = {row.tool_call_id: row for row in pending}
    assert set(by_call) == {"tc-3", "tc-7"}
    assert by_call["tc-3"].claim.startswith("tc-3 geometry")
    assert by_call["tc-3"].rationale == "lowest-energy candidate of the batch"
    assert by_call["tc-3"].suggested_stage == "ts_opt"
    assert by_call["tc-7"].suggested_stage == "frequency"
    assert all(row.source == "explicit" for row in pending)
    # 24 份证据全部登记在库（不丢审计），只有 2 份成为待办。
    with db.connect() as con:
        n_evidence = con.execute("SELECT COUNT(*) FROM dag_evidence").fetchone()[0]
    assert n_evidence == 24


@pytest.mark.asyncio
async def test_guided_submission_requires_a_claim(tmp_path):
    """无 claim 的送审被拒：主张是送审语义的一部分（要证明什么）。"""
    from cloudra.tools.Plantool.dag_tools.dag_bind_evidence import DagBindEvidence

    agent, session, db, _controller = await _guided_seed(tmp_path, "no-claim", n_calls=1)
    out = await DagBindEvidence(subagent=agent).tool_call(
        DagBindEvidence.model_fields["input_schema"].default(
            attachments=[{"tool_call_id": "tc-0", "bind_target": "step1", "stage_kind": "ts_opt"}]
        ),
        session,
    )
    assert not out.is_success
    assert "claim" in out.error
    assert DagStore(db).list_call_reviews("pending") == []


@pytest.mark.asyncio
async def test_identical_claim_resubmission_returns_existing_review(tmp_path):
    """相同声明重发：is_success=True（幂等成功），返回既有 review_id。"""
    from cloudra.tools.Plantool.dag_tools.dag_bind_evidence import DagBindEvidence

    agent, session, db, _controller = await _guided_seed(tmp_path, "idem", n_calls=1)
    schema = DagBindEvidence.model_fields["input_schema"].default
    kwargs = dict(
        attachments=[{
            "tool_call_id": "tc-0", "bind_target": "step1", "stage_kind": "ts_opt",
            "claim": "tc-0 supports the ts_opt stage",
        }],
    )
    first = await DagBindEvidence(subagent=agent).tool_call(schema(**kwargs), session)
    assert first.is_success and first.accepted
    second = await DagBindEvidence(subagent=agent).tool_call(schema(**kwargs), session)
    assert second.is_success and second.accepted
    first_row = first.result["attachments"][0]
    second_row = second.result["attachments"][0]
    assert first_row["enqueued"] is True
    assert second_row["enqueued"] is False
    assert second_row["review_id"] == first_row["review_id"]
    assert len(DagStore(db).list_call_reviews("pending")) == 1


@pytest.mark.asyncio
async def test_batch_with_one_invalid_attachment_commits_nothing(tmp_path):
    """批量中一项非法 → 全部不提交；报错指名非法项，不掩盖部分副作用。"""
    from cloudra.tools.Plantool.dag_tools.dag_bind_evidence import DagBindEvidence

    agent, session, db, _controller = await _guided_seed(tmp_path, "atomic", n_calls=2)
    out = await DagBindEvidence(subagent=agent).tool_call(
        DagBindEvidence.model_fields["input_schema"].default(
            attachments=[
                {"tool_call_id": "tc-0", "bind_target": "step1",
                 "stage_kind": "ts_opt", "claim": "valid item"},
                {"tool_call_id": "tc-1", "bind_target": "no_such_edge",
                 "stage_kind": "ts_opt", "claim": "invalid target"},
            ]
        ),
        session,
    )
    assert not out.is_success
    assert "no_such_edge" in out.error
    assert DagStore(db).list_call_reviews("pending") == []


@pytest.mark.asyncio
async def test_submission_rejections(tmp_path):
    """拒绝面：无依据引用（调用不存在/未结束）、错目标、阶段不在契约内、
    跨项目引用（别的会话库登记的 tool_call_id 在本项目不可解析）。"""
    agent, session, db, controller = await _guided_seed(tmp_path, "rejections", n_calls=1)

    async def expect_error(**item):
        try:
            await controller.submit_evidence_for_review([item])
        except RuntimeError as exc:
            return str(exc)
        raise AssertionError(f"submission should have been rejected: {item}")

    # 调用不存在/未结束（未登记的 tool_call_id）
    assert "no registered evidence" in await expect_error(
        tool_call_id="tc-running", bind_target="step1", stage_kind="ts_opt",
        claim="unfinished call",
    )
    # 错目标
    assert "does not exist" in await expect_error(
        tool_call_id="tc-0", bind_target="ghost", stage_kind="ts_opt",
        claim="wrong target",
    )
    # 阶段不在该元素的阶段契约内
    assert "not declared" in await expect_error(
        tool_call_id="tc-0", bind_target="step1", stage_kind="short_irc",
        claim="stage not in contract",
    )
    # 未知阶段词表
    assert "unknown stage_kind" in await expect_error(
        tool_call_id="tc-0", bind_target="step1", stage_kind="made_up",
        claim="bad stage vocabulary",
    )
    # 缺 claim
    assert "claim" in await expect_error(
        tool_call_id="tc-0", bind_target="step1", stage_kind="ts_opt", claim="  ",
    )
    # 跨项目引用：tool_call_id 在另一个会话库登记，本项目不可解析
    other_db = ConversationDB("other-project", data_dir=tmp_path).init()
    DagStore(other_db).register_evidence(
        "s9", "log_parser",
        {"tool_call_id": "tc-foreign", "arguments": {}, "result": {"is_success": True}},
    )
    assert "no registered evidence" in await expect_error(
        tool_call_id="tc-foreign", bind_target="step1", stage_kind="ts_opt",
        claim="cross-project reference",
    )
    # 全部拒绝：没有任何东西入箱
    assert DagStore(db).list_call_reviews("pending") == []


@pytest.mark.asyncio
async def test_failed_evidence_cannot_complete_a_success_stage(tmp_path):
    """失败证据可送审（负证据），但 Supervisor agree 时被 harness 拒
    （tool_not_succeeded）——失败证据不能冒充成功把阶段置为 supported。"""
    from cloudra.tools.Plantool.dag_tools.dag_review_call import DagReviewCall
    from tests.dag_identity import call_dag_tool, make_supervisor

    agent, session, db, controller = await _guided_seed(tmp_path, "failed-ev", n_calls=0)
    await controller.on_tool_finished(
        "tc-fail", "log_parser", {"log_path": "/w/bad.log"},
        {"is_success": False, "error": "SCF not converged"},
    )
    submitted = await controller.submit_evidence_for_review([{
        "tool_call_id": "tc-fail", "bind_target": "step1", "stage_kind": "ts_opt",
        "claim": "negative evidence: this attempt failed, stage still owed",
    }])
    assert submitted["attachments"][0]["enqueued"] is True
    review = DagStore(db).list_call_reviews("pending")[0]
    assert review.is_success is False  # 如实记录失败

    supervisor = make_supervisor("failed-ev", workspace_dir=str(tmp_path))
    verdict = await call_dag_tool(
        DagReviewCall,
        supervisor,
        session,
        review_id=review.review_id, target_id="step1", stage_kind="ts_opt",
        verdict="agree",
    )
    assert not verdict.is_success
    assert verdict.rejection_code == "tool_not_succeeded"
    edge = next(
        e for e in DagStore(db).load_snapshot().delivery.edges if e.edge_id == "step1"
    )
    assert all(s.status.value == "pending" for s in edge.stages)
