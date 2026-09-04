"""Task 8: stop audit gate matrix (StopGate)."""

import pytest

from cloudra.dag.controller import DagController
from cloudra.dag.review_requests import ReviewDecision
from cloudra.dag.stop_audit import StopGate
from cloudra.persistence.database import ConversationDB


async def _controller(tmp_path, conversation_id, mode):
    db = ConversationDB(conversation_id, data_dir=tmp_path).init()
    controller = DagController(db, "s1", mode, conversation_id=conversation_id)
    await controller.initialize()
    return controller


@pytest.mark.asyncio
async def test_partial_in_dag_record_allow_final(tmp_path):
    c = await _controller(tmp_path, "exit-record-partial", "dag_record")
    gate = await c.audit_stop("partial")
    assert isinstance(gate, StopGate)
    assert gate.action == "allow_final"


@pytest.mark.asyncio
async def test_partial_in_dag_guided_without_approval_waits_review(tmp_path):
    c = await _controller(tmp_path, "exit-guided-partial", "dag_guided")
    gate = await c.audit_stop("partial")
    assert gate.action == "wait_review"


@pytest.mark.asyncio
async def test_partial_in_dag_guided_with_approval_allow_final(tmp_path):
    c = await _controller(tmp_path, "exit-guided-approved", "dag_guided")
    gate = await c.audit_stop("partial", approval_id="approval-123")
    assert gate.action == "wait_review"
    assert gate.request_id


@pytest.mark.asyncio
async def test_complete_empty_graph_needs_work(tmp_path):
    c = await _controller(tmp_path, "exit-empty", "dag_record")
    gate = await c.audit_stop("complete")
    assert gate.action == "needs_work"


@pytest.mark.asyncio
async def test_user_terminated_requires_real_event(tmp_path):
    c = await _controller(tmp_path, "exit-user", "dag_record")
    fake = await c.audit_stop("user_terminated")
    assert fake.action == "needs_work"
    real = await c.audit_stop("user_terminated", user_stop_event_id="evt_user_1")
    assert real.action == "needs_work"


@pytest.mark.asyncio
async def test_rejected_exit_review_is_reused_as_needs_work(tmp_path):
    c = await _controller(tmp_path, "exit-guided-rejected", "dag_guided")
    first = await c.audit_stop("partial")
    request = c.store.get_review_request(first.request_id)
    decision = ReviewDecision(
        request_id=request.request_id,
        basis_fingerprint=request.basis_fingerprint,
        verdict="reject",
        reason="Missing evidence",
        next_action="Inspect existing log",
    )
    c.store.resolve_review(decision, expected_basis=request.basis_fingerprint, claim_token=0)
    second = await c.audit_stop("partial")
    assert second.action == "needs_work"
    assert "Missing evidence" in second.reason
    assert "Inspect existing log" in second.reason
    assert c.store.list_review_requests(state="queued") == []


@pytest.mark.asyncio
async def test_accepted_exit_review_is_reused_for_same_scope(tmp_path):
    c = await _controller(tmp_path, "exit-guided-accepted", "dag_guided")
    first = await c.audit_stop("partial")
    request = c.store.get_review_request(first.request_id)
    decision = ReviewDecision(
        request_id=request.request_id,
        basis_fingerprint=request.basis_fingerprint,
        verdict="accept",
        reason="Scoped partial is acceptable",
    )
    assert c.store.resolve_review(
        decision, expected_basis=request.basis_fingerprint, claim_token=0
    )["accepted"]
    second = await c.audit_stop("partial")
    assert second.action == "allow_final"
    assert c.store.list_review_requests(state="queued") == []
