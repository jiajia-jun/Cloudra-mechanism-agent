"""File requests and generic adjudication share the same scoped review contract."""
from __future__ import annotations

import asyncio

import pytest

from cloudra.dag.engine import DagEngine
from cloudra.dag.models import AddNode, GraphActor, MutationBatch, OccurrenceNode, UpdateNode
from cloudra.tools.Plantool.dag_tools.dag_message_supervisor import DagMessageSupervisor
from cloudra.tools.Plantool.dag_tools.dag_review_evidence import DagReviewEvidence
from cloudra.tools.Plantool.dag_tools.dag_submit_species_evidence import DagSubmitSpeciesEvidence
from cloudra.tools.Plantool.dag_tools.dag_submit_step_evidence import DagSubmitStepEvidence
from tests.dag_identity import call_dag_tool, make_supervisor
from tests.test_dag_async_evidence_review import FIXTURES_DIR, _coordinator, _seed_review_graph


@pytest.fixture(autouse=True)
def _reject_sync_sqlite_on_loop(monkeypatch):
    monkeypatch.setenv("CLOUDRA_DB_SYNC_ON_LOOP", "raise")


async def _submit(tmp_path, kind):
    session, db, store = await asyncio.to_thread(_seed_review_graph, tmp_path, f"file-contract-{kind}")
    if kind == "species":
        tool = DagSubmitSpeciesEvidence
        arguments = {"species_name": "R", "opt_file": str(FIXTURES_DIR / "gaussian" / "water_opt_freq_g16.out")}
    else:
        tool = DagSubmitStepEvidence
        arguments = {"step_name": "step1", "ts_file": str(FIXTURES_DIR / "xtb" / "ts_hess_xtb.out")}
    result = await call_dag_tool(tool, _coordinator(db.conversation_id), session, **arguments)
    assert result.is_success
    return session, db, store, result.result["review_id"]


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["species", "step"])
async def test_file_request_can_be_resolved_through_generic_review(tmp_path, kind):
    session, db, store, request_id = await _submit(tmp_path, kind)
    before = (await asyncio.to_thread(store.load_snapshot)).delivery
    result = await call_dag_tool(
        DagReviewEvidence, make_supervisor(db.conversation_id), session,
        request_id=request_id, verdict="accept", reason="Record the review of the submitted evidence",
    )
    assert result.is_success and result.accepted, result
    assert (await asyncio.to_thread(store.get_review_request, request_id)).state == "resolved"
    assert (await asyncio.to_thread(store.load_snapshot)).delivery == before
    assert result.result["stage_changed"] is False
    assert result.result["scientific_checks"]
    assert result.result["next_action"]
    decision = await asyncio.to_thread(store.get_review_decision_for_request, request_id)
    request = await asyncio.to_thread(store.get_review_request, request_id)
    assert decision.evidence_refs == request.supporting_refs
    assert decision.next_action == result.result["next_action"]
    assert decision.basis_fingerprint == (await asyncio.to_thread(store.get_review_request, request_id)).basis_fingerprint


def _mutate(store, operation):
    result = DagEngine(store).apply_batch(MutationBatch(
        session_id="s1", actor=GraphActor.HARNESS, actor_id="contract-test",
        base_revisions=store.load_bundle().revisions, rationale="Update scoped review basis",
        operations=[operation],
    ))
    assert result.accepted, result


@pytest.mark.asyncio
@pytest.mark.parametrize("change,accepted", [("unrelated", True), ("endpoint", False), ("target", False)])
async def test_step_file_review_checks_related_identity_without_global_invalidation(tmp_path, change, accepted):
    session, db, store, request_id = await _submit(tmp_path, "step")
    if change == "unrelated":
        await asyncio.to_thread(_mutate, store, AddNode(op="add_node", graph="delivery", node=OccurrenceNode(node_id="other", label="Other")))
    elif change == "endpoint":
        await asyncio.to_thread(_mutate, store, UpdateNode(op="update_node", graph="delivery", node_id="r", changes={"smiles": "O"}))
    else:
        from cloudra.dag.models import UpdateEdge
        await asyncio.to_thread(_mutate, store, UpdateEdge(op="update_edge", graph="delivery", edge_id="step1", changes={"label": "Changed target"}))
    result = await call_dag_tool(
        DagReviewEvidence, make_supervisor(db.conversation_id), session,
        request_id=request_id, verdict="accept", reason="Review the submitted target snapshot",
    )
    assert result.is_success is accepted, result
    if not accepted:
        assert result.rejection_code == "stale_basis"
        assert (await asyncio.to_thread(store.get_review_request, request_id)).state == "superseded"
        assert await asyncio.to_thread(store.get_review_decision_for_request, request_id) is None


@pytest.mark.asyncio
@pytest.mark.parametrize("target_ids", [["step1"], []])
async def test_exception_acceptance_does_not_waive_scientific_gaps(tmp_path, target_ids):
    session, db, store = await asyncio.to_thread(_seed_review_graph, tmp_path, "exception-receipt")
    before = (await asyncio.to_thread(store.load_snapshot)).delivery
    scope = target_ids or ["r", "p", "step1"]
    gaps = await asyncio.to_thread(store.collect_review_exceptions, scope)
    assert gaps
    submitted = await call_dag_tool(
        DagMessageSupervisor, _coordinator(db.conversation_id), session,
        kind="exception", question="Is IRC inapplicable?", target_ids=target_ids,
    )
    assert submitted.is_success
    reviewed = await call_dag_tool(
        DagReviewEvidence, make_supervisor(db.conversation_id), session,
        request_id=submitted.result["request_id"], verdict="accept", reason="Acknowledge the exception request",
        findings=[{"target_id": "step1", "check": "irc", "outcome": "not_applicable", "reason": "Reviewer opinion"}],
    )
    assert reviewed.is_success and reviewed.accepted
    assert reviewed.result["stage_changed"] is False
    assert reviewed.result["scientific_status"] == "unresolved"
    assert reviewed.result["remaining_gaps"] == gaps
    assert reviewed.result["next_action"]
    decision = await asyncio.to_thread(store.get_review_decision_for_request, submitted.result["request_id"])
    assert decision.next_action == reviewed.result["next_action"]
    assert (await asyncio.to_thread(store.load_snapshot)).delivery == before
    assert await asyncio.to_thread(store.collect_review_exceptions, scope) == gaps
