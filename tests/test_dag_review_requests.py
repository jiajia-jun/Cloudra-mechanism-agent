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
    out = store.resolve_review(decision, expected_basis="basis-v1", claim_token=1)
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
    out = store.resolve_review(decision, expected_basis="new-basis", claim_token=1)
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
    assert store.resolve_review(d1, expected_basis="basis-v1", claim_token=1)["accepted"]
    d2 = ReviewDecision(
        request_id=request_id,
        basis_fingerprint="basis-v1",
        verdict="accept",
        reason="duplicate should not be applied",
    )
    out = store.resolve_review(d2, expected_basis="basis-v1", claim_token=1)
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
    from cloudra.core.agent import Coordinator, Follower
    from cloudra.core.supervisor import SupervisorAgent
    from cloudra.infra.config import get_config
    from cloudra.persistence.database import ConversationDB
    from cloudra.tools.Plantool.dag_tools.dag_message_supervisor import (
        DagMessageSupervisor,
    )
    from cloudra.tools.Plantool.dag_tools.dag_review_evidence import (
        DagReviewEvidence,
    )

    get_config().data_dir = tmp_path
    conversation_id = "structured-msg"
    follower = Follower(
        id="a-4",
        name="small_mol",
        query="run opt",
        conversation_id=conversation_id,
        orchestration_mode="dag_guided",
    )
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
    coordinator = Coordinator(
        query="study",
        conversation_id=conversation_id,
        orchestration_mode="dag_guided",
    )
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
    supervisor = SupervisorAgent(
        conversation_id=conversation_id,
        orchestration_mode="dag_guided",
    )
    sv_out = await DagReviewEvidence(subagent=supervisor).tool_call(
        DagReviewEvidence.model_fields["input_schema"].default(
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
        ),
        session,
    )
    assert sv_out.is_success and sv_out.accepted
    assert DagStore(db).get_review_request(request_id).state == "resolved"
