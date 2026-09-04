"""Task 8: stop audit gate matrix (StopGate)."""

import pytest

from cloudra.dag.controller import DagController
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
    assert gate.action == "allow_final"


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
    assert real.action == "allow_final"
