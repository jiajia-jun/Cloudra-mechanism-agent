"""Final-delivery reviewers consume only their assigned exit request."""

import asyncio
from types import SimpleNamespace

import pytest

from cloudra.base.session_class import Session
from cloudra.dag.models import CallReview, MechanismDraft
from cloudra.dag.review_requests import ReviewRequest
from cloudra.dag.store import DagStore
from cloudra.dag.supervisor_tools import SupervisorToolExecutor
from cloudra.persistence.database import ConversationDB
from cloudra.tools.Plantool.dag_tools.dag_review_evidence import DagReviewEvidence
from cloudra.tools.Plantool.dag_tools.dag_view import DagView
from cloudra.tools.Plantool.dag_tools.dag_view_evidence import DagViewEvidence
from tests.dag_identity import call_dag_tool, make_actor


@pytest.fixture
def review_case(tmp_path):
    project_id = "final-review-tool-scope"
    store = DagStore(ConversationDB(project_id).init())
    store.ensure_bundle("as_coordinator")
    requests = {}
    for name, kind, requester in (
        ("process", "evidence", "as_research"),
        ("final", "exit", "as_coordinator"),
        ("other_final", "exit", "as_other_coordinator"),
    ):
        request = ReviewRequest(
            request_id=f"req_{name}",
            kind=kind,
            requester=requester,
            question=f"Review {name}",
            proposal={
                "disposition": "partial", "scope": [],
                "remaining_gaps": [], "method_limits": [],
            } if kind == "exit" else {},
            basis_fingerprint="pending",
        )
        request = request.model_copy(update={"basis_fingerprint": store.review_basis(request)})
        requests[name] = store.enqueue_review(request)
    draft_id = store.save_draft(MechanismDraft(operations=[], rationale="Process hypothesis"), actor_id="a-0")
    evidence = store.register_evidence("as_research", "log_parser", {
        "tool_call_id": "tc_process", "arguments": {"log_path": "native.out"},
        "result": {"is_success": True, "scf_energy": -1.0},
    })
    store.enqueue_call_review(CallReview(
        review_id="rev_process", tool_call_id="tc_process", tool_name="log_parser", is_success=True,
        evidence_id=evidence.ref_id,
        claim="Process evidence claim",
    ))
    return project_id, store, requests, draft_id


def _actor(project_id, tmp_path, *, role="supervisor", request_id=None, runtime_marker=False):
    actor = make_actor(project_id, role, workspace_dir=str(tmp_path))
    if runtime_marker:
        actor._runtime_agent = SimpleNamespace(final_review_request_id=request_id)
    else:
        actor.final_review_request_id = request_id
    return actor, Session(id=actor.id, path="")


@pytest.mark.asyncio
@pytest.mark.parametrize("role,scope,expected", [
    ("supervisor", None, {"process"}),
    ("supervisor", "final", {"final"}),
    ("coordinator", None, {"process", "final", "other_final"}),
])
async def test_dag_view_routes_review_inbox_by_reviewer_identity(review_case, tmp_path, role, scope, expected):
    project_id, _store, requests, draft_id = review_case
    actor, session = _actor(project_id, tmp_path, role=role, request_id=requests.get(scope))

    output = await call_dag_tool(DagView, actor, session)

    assert output.is_success
    assert {row["request_id"] for row in output.result["queued_requests"]} == {requests[key] for key in expected}
    if scope:
        assert output.result["open_drafts"] == []
        assert output.result["pending_reviews"] == []
    else:
        assert [row["draft_id"] for row in output.result["open_drafts"]] == [draft_id]
        assert [row["review_id"] for row in output.result["pending_reviews"]] == ["rev_process"]


@pytest.mark.asyncio
@pytest.mark.parametrize("scope,target,allowed", [
    (None, "process", True),
    (None, "final", False),
    ("final", "final", True),
    ("final", "other_final", False),
    ("final", "process", False),
])
async def test_review_material_read_cannot_cross_reviewer_scope(review_case, tmp_path, scope, target, allowed):
    project_id, _store, requests, _draft_id = review_case
    actor, session = _actor(project_id, tmp_path, request_id=requests.get(scope))

    output = await call_dag_tool(DagViewEvidence, actor, session, review_id=requests[target])

    assert output.is_success is allowed, output
    if allowed:
        assert output.result["review_id"] == requests[target]


@pytest.mark.asyncio
@pytest.mark.parametrize("scope,target,allowed", [
    (None, "process", True),
    (None, "final", False),
    ("final", "final", True),
    ("final", "other_final", False),
    ("final", "process", False),
])
async def test_review_decision_cannot_cross_reviewer_scope(review_case, tmp_path, scope, target, allowed):
    project_id, store, requests, _draft_id = review_case
    actor, session = _actor(project_id, tmp_path, request_id=requests.get(scope))

    output = await call_dag_tool(
        DagReviewEvidence, actor, session, request_id=requests[target],
        verdict="reject", reason="The submitted evidence is incomplete", next_action="Inspect the native files",
    )

    assert output.is_success is allowed, output
    request = await asyncio.to_thread(store.get_review_request, requests[target])
    assert request.state == ("resolved" if allowed else "queued")


@pytest.mark.asyncio
async def test_final_reviewer_reads_raw_evidence_without_process_review_narrative(review_case, tmp_path):
    project_id, store, requests, _draft_id = review_case
    actor, session = _actor(project_id, tmp_path, request_id=requests["final"])
    review = await asyncio.to_thread(store.get_call_review, "rev_process")

    process_review = await call_dag_tool(DagViewEvidence, actor, session, review_id=review.review_id)
    raw_evidence = await call_dag_tool(DagViewEvidence, actor, session, evidence_id=review.evidence_id)

    assert not process_review.is_success
    assert raw_evidence.is_success, raw_evidence
    assert raw_evidence.result["result"]["scf_energy"] == -1.0
    assert "claim" not in raw_evidence.result


@pytest.mark.asyncio
@pytest.mark.parametrize("name,arguments", [
    ("write", {"path": "PROCESS.md", "content": "Changed account"}),
    ("edit", {"path": "PROCESS.md", "edits": [{"old_text": "Original", "new_text": "Changed"}]}),
    ("dag_set_coverage_contract", {"require_thermochemistry": True}),
    ("dag_accept_mechanism", {"verdict": "accept"}),
    ("dag_review_call", {"review_id": "rev_process", "target_id": "x", "stage_kind": "ts_opt", "verdict": "agree"}),
    ("dag_review_species", {"species_name": "R", "verdict": "supported", "rationale": "Inspected"}),
    ("dag_review_step", {"step_name": "step1", "verdict": "supported", "rationale": "Inspected"}),
])
async def test_final_reviewer_cannot_write_process_or_adjudicate_process_work(review_case, tmp_path, name, arguments):
    project_id, _store, requests, _draft_id = review_case
    actor, session = _actor(project_id, tmp_path, request_id=requests["final"], runtime_marker=True)
    process_path = tmp_path / "PROCESS.md"
    process_path.write_text("Original account")
    executor = SupervisorToolExecutor(project_id=project_id, workspace_root=str(tmp_path))
    executor.bind_run(agent=actor, session=session)

    output = await executor.execute(name, arguments, session_id=actor.id)

    assert not output["is_success"], output
    assert "[permission denied]" in output.get("message", ""), output
    assert process_path.read_text() == "Original account"


@pytest.mark.asyncio
async def test_final_reviewer_resolves_own_request_through_real_executor(review_case, tmp_path):
    project_id, store, requests, _draft_id = review_case
    actor, session = _actor(project_id, tmp_path, request_id=requests["final"], runtime_marker=True)
    executor = SupervisorToolExecutor(project_id=project_id, workspace_root=str(tmp_path))
    executor.bind_run(agent=actor, session=session)

    output = await executor.execute("dag_review_evidence", {
        "request_id": requests["final"], "verdict": "reject", "reason": "The delivery is incomplete",
        "next_action": "Supply missing evidence",
    }, session_id=actor.id)

    assert output["is_success"], output
    request = await asyncio.to_thread(store.get_review_request, requests["final"])
    assert request.state == "resolved"
