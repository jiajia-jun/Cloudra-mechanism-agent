"""Black-box regressions for guided drafts and asynchronous DAG evidence review.

These tests deliberately exercise the public DAG tools/controller and inspect the
persistent store.  They do not use private mutation helpers to simulate a review
decision.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from cloudra.base.session_class import Session
from cloudra.dag.controller import DagController
from cloudra.dag.drafts import MechanismDraft
from cloudra.dag.engine import DagEngine
from cloudra.dag.models import (
    AddEdge,
    AddNode,
    ClaimSpec,
    ElementaryStepEdge,
    GraphActor,
    MutationBatch,
    OccurrenceNode,
    StageState,
)
from cloudra.dag.review_context import ActiveReview, ReviewContextManager
from cloudra.dag.review_requests import ReviewDecision, ReviewRequest
from cloudra.dag.store import DagStore
from cloudra.infra.config import get_config
from cloudra.persistence.database import ConversationDB
from cloudra.tools.Plantool.dag_tools.dag_delivery_report import DagDeliveryReport
from cloudra.tools.Plantool.dag_tools.dag_propose_mechanism import DagProposeMechanism
from cloudra.tools.Plantool.dag_tools.dag_review_species import DagReviewSpecies
from cloudra.tools.Plantool.dag_tools.dag_review_step import DagReviewStep
from cloudra.tools.Plantool.dag_tools.dag_submit_species_evidence import DagSubmitSpeciesEvidence
from cloudra.tools.Plantool.dag_tools.dag_submit_step_evidence import DagSubmitStepEvidence
from tests.dag_identity import call_dag_tool, make_coordinator, make_supervisor

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


def _coordinator(conversation_id: str):
    # The real file fixtures are under the repository workspace; the bridge's
    # default project workspace under data_dir is absent in these unit tests.
    return make_coordinator(
        conversation_id,
        orchestration_mode="dag_guided",
        workspace_dir=str(FIXTURES_DIR.parent.parent),
    )


def _session(tmp_path: str, conversation_id: str):
    get_config().data_dir = tmp_path
    agent = _coordinator(conversation_id)
    session = Session("s1", f"{tmp_path}/session.json")
    db = ConversationDB(conversation_id, data_dir=tmp_path).init()
    return agent, session, db


@pytest.mark.asyncio
async def test_guided_proposal_is_a_live_candidate_and_compute_is_allowed(tmp_path):
    """A guided proposal is immediately visible and does not gate computation."""
    agent, session, db = _session(tmp_path, "async-draft-candidate")

    out = await call_dag_tool(
        DagProposeMechanism,
        agent,
        session,
        rationale="single candidate pathway for the scoped transformation",
        species=[{"name": "R", "smiles": "C=C"}, {"name": "P", "smiles": "CC"}],
        steps=[{"name": "step1", "from": "R", "to": "P"}],
    )

    assert out.is_success
    assert out.result["state"] == "open"
    assert out.accepted is False

    graph = DagStore(db).load_snapshot().delivery
    assert {node.label for node in graph.nodes} >= {"R", "P"}
    assert {edge.name for edge in graph.edges} >= {"step1"}
    controller = DagController(db, "s1", "dag_guided", conversation_id=db.conversation_id)
    assert await controller.check_substantive_gate("submit_compute_job", {}) is None


def _seed_review_graph(tmp_path, conversation_id: str):
    _agent, session, db = _session(tmp_path, conversation_id)
    store = DagStore(db)
    store.ensure_bundle("s1")
    base = store.load_bundle().revisions
    result = DagEngine(store).apply_batch(
        MutationBatch(
            session_id="s1",
            actor=GraphActor.HARNESS,
            actor_id="test-harness",
            base_revisions=base,
            rationale="seed delivery graph for directed review",
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
                AddEdge(
                    op="add_edge",
                    graph="delivery",
                    edge=ElementaryStepEdge(
                        edge_id="step1",
                        name="step1",
                        source_node_id="r",
                        target_node_id="p",
                        stages=[StageState(kind="ts_opt"), StageState(kind="frequency")],
                    ),
                ),
            ],
        )
    )
    assert result.accepted
    return session, db, store


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("tool_cls", "kind", "target_name", "target_id"),
    [
        (DagReviewSpecies, "species", "R", "r"),
        (DagReviewStep, "step", "step1", "step1"),
    ],
)
async def test_supported_directed_review_is_durable_and_does_not_write_machine_level(
    tmp_path, tool_cls, kind, target_name, target_id
):
    """Supervisor supported records a durable decision for the active review.

    The graph's machine-derived evidence level is owned by the harness and must
    remain unchanged when this supervisor-only tool records its conclusion.
    """
    session, db, store = _seed_review_graph(tmp_path, f"async-supported-{kind}")
    graph_before = store.load_snapshot().delivery
    before = next(
        element
        for element in [*graph_before.nodes, *graph_before.edges]
        if getattr(element, "node_id", getattr(element, "edge_id", "")) == target_id
    )
    old_level = before.evidence_level

    request_id = f"review-{kind}-supported"
    persisted = ReviewContextManager.set_active_review(
        db.conversation_id,
        ActiveReview(
            review_id=request_id,
            kind=kind,
            target_name=target_name,
            target_id=target_id,
            details={"element_type": kind},
            basis_fingerprint=f"basis-{kind}",
        ),
        db=db,
    )
    assert persisted

    supervisor = make_supervisor(db.conversation_id, workspace_dir=str(tmp_path))
    out = await call_dag_tool(
        tool_cls,
        supervisor,
        session,
        **({"species_name": target_name} if kind == "species" else {"step_name": target_name}),
        verdict="supported",
        rationale="the submitted evidence answers the declared review question",
    )
    assert out.is_success and out.accepted

    request = store.get_review_request(request_id)
    assert request is not None and request.state == "resolved"
    decision = store.get_review_decision_for_request(request_id)
    assert decision is not None
    assert decision.request_id == request_id
    assert decision.verdict == "accept"
    assert decision.reason

    graph_after = store.load_snapshot().delivery
    after = next(
        element
        for element in [*graph_after.nodes, *graph_after.edges]
        if getattr(element, "node_id", getattr(element, "edge_id", "")) == target_id
    )
    assert after.evidence_level == old_level

    # The active item is consumed exactly once; a second supported verdict has
    # no review to consume and must fail instead of fabricating success.
    again = await call_dag_tool(
        tool_cls,
        supervisor,
        session,
        **({"species_name": target_name} if kind == "species" else {"step_name": target_name}),
        verdict="supported",
        rationale="duplicate review must not be accepted",
    )
    assert not again.is_success


@pytest.mark.asyncio
async def test_directed_review_rejects_missing_or_wrong_active_review(tmp_path):
    session, db, _store = _seed_review_graph(tmp_path, "async-review-target-gates")
    supervisor = make_supervisor(db.conversation_id, workspace_dir=str(tmp_path))
    ReviewContextManager.set_active_review(
        db.conversation_id,
        ActiveReview(
            review_id="review-step-only",
            kind="step",
            target_name="step1",
            target_id="step1",
            basis_fingerprint="basis-step-only",
        ),
        db=db,
    )
    wrong_target = await call_dag_tool(
        DagReviewSpecies,
        supervisor,
        session,
        species_name="R",
        verdict="supported",
        rationale="wrong active target must be rejected",
    )
    assert not wrong_target.is_success
    ReviewContextManager.clear_active_review(db.conversation_id, db=db, request_id="review-step-only")

    no_active = await call_dag_tool(
        DagReviewSpecies,
        supervisor,
        session,
        species_name="R",
        verdict="supported",
        rationale="no active review must be rejected",
    )
    assert not no_active.is_success


@pytest.mark.asyncio
async def test_unrelated_structured_request_cannot_drive_per_file_review(tmp_path):
    session, db, store = _seed_review_graph(tmp_path, "async-review-kind-gates")
    supervisor = make_supervisor(db.conversation_id, workspace_dir=str(tmp_path))
    request_id = _request(
        store,
        "queued-step-request",
        ["step1"],
        "Review the transition-state evidence",
        "basis-queued-step",
    )
    assert request_id == "queued-step-request"

    # A queued structured request for a step must not be silently interpreted
    # as the active species-file review.
    unrelated = await call_dag_tool(
        DagReviewSpecies,
        supervisor,
        session,
        species_name="R",
        verdict="supported",
        rationale="the unrelated step request must not drive this tool",
    )
    assert not unrelated.is_success
    assert store.get_review_request(request_id).state == "queued"

    # Even a matching target is invalid when the active review kind is wrong.
    ReviewContextManager.set_active_review(
        db.conversation_id,
        ActiveReview(
            review_id="wrong-kind-for-species",
            kind="step",
            target_name="R",
            target_id="r",
            basis_fingerprint="basis-wrong-kind",
        ),
        db=db,
    )
    wrong_kind = await call_dag_tool(
        DagReviewSpecies,
        supervisor,
        session,
        species_name="R",
        verdict="supported",
        rationale="step review cannot be adjudicated as species review",
    )
    assert not wrong_kind.is_success
    ReviewContextManager.clear_active_review(
        db.conversation_id, db=db, request_id="wrong-kind-for-species"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("tool_cls", [DagSubmitSpeciesEvidence, DagSubmitStepEvidence])
async def test_file_submission_failure_to_persist_review_is_not_reported_as_submitted(
    tmp_path, monkeypatch, tool_cls
):
    session, db, store = _seed_simple_complete_graph(
        tmp_path, f"async-review-persist-failure-{tool_cls.__name__}"
    )
    agent = _coordinator(db.conversation_id)
    monkeypatch.setattr(ReviewContextManager, "set_active_review", lambda *args, **kwargs: False)
    if tool_cls is DagSubmitSpeciesEvidence:
        out = await call_dag_tool(
            tool_cls,
            agent,
            session,
            species_name="R",
            opt_file=str(FIXTURES_DIR / "gaussian" / "water_opt_freq_g16.out"),
            description="persist failure",
        )
    else:
        out = await call_dag_tool(
            tool_cls,
            agent,
            session,
            step_name="step1",
            ts_file=str(FIXTURES_DIR / "xtb" / "ts_hess_xtb.out"),
            reaction_coordinate_description="persist failure",
        )
    assert not out.is_success
    assert out.result.get("enqueued") is not True
    assert store.list_review_requests(state="queued") == []


@pytest.mark.asyncio
async def test_species_submission_persists_opt_and_frequency_refs(tmp_path):
    session, db, store = _seed_simple_complete_graph(tmp_path, "async-species-two-files")
    agent = _coordinator(db.conversation_id)
    out = await call_dag_tool(
        DagSubmitSpeciesEvidence,
        agent,
        session,
        species_name="R",
        opt_file=str(FIXTURES_DIR / "gaussian" / "water_opt_freq_g16.out"),
        freq_file=str(FIXTURES_DIR / "gaussian" / "water_opt_freq_g16.out"),
        description="separate optimization and frequency submissions",
    )
    assert out.is_success
    review = store.get_review_request(out.result["review_id"])
    assert review is not None
    assert review.requester == session.id
    assert len(review.supporting_refs) == 2
    assert {ref.ref_id for ref in review.supporting_refs}


@pytest.mark.asyncio
async def test_step_submission_binds_real_irc_file_for_review_credit(tmp_path):
    session, db, store = _seed_review_graph(tmp_path, "async-step-irc-file")
    agent = _coordinator(db.conversation_id)
    supervisor = make_supervisor(db.conversation_id, workspace_dir=str(tmp_path))
    out = await call_dag_tool(
        DagSubmitStepEvidence, agent, session,
        step_name="step1",
        ts_file=str(FIXTURES_DIR / "xtb" / "ts_hess_xtb.out"),
        irc_file=str(FIXTURES_DIR / "gaussian" / "hcn_ts_irc_g16.log"),
        reaction_coordinate_description="TS and IRC for the declared step",
    )
    assert out.is_success
    request = store.get_review_request(out.result["review_id"])
    assert request is not None
    assert request.requester == session.id
    assert len(request.supporting_refs) == 2
    edge = store.load_snapshot().delivery.edges[0]
    assert {ref.ref_id for ref in edge.refs} == {
        ref.ref_id for ref in request.supporting_refs
    }

    reviewed = await call_dag_tool(
        DagReviewStep, supervisor, session,
        step_name="step1", verdict="supported",
        rationale="the TS and IRC files support the selected step",
    )
    assert reviewed.is_success
    report = DagController(db, "s1", "dag_guided", conversation_id=db.conversation_id).delivery_report()
    assert report.complete
    assert any(g.code == "supervisor_evidence_accepted" and g.target_id == "step1"
               for g in report.satisfied)


def _completed_edge(edge_id: str, source: str, target: str):
    return ElementaryStepEdge(
        edge_id=edge_id,
        name=edge_id,
        source_node_id=source,
        target_node_id=target,
        stages=[
            StageState(kind="ts_opt", status="supported"),
            StageState(kind="frequency", status="supported"),
        ],
    )


@pytest.mark.asyncio
async def test_delivery_report_counts_related_pending_and_needs_evidence_only(tmp_path):
    """Review work in the selected scope remains a delivery gap.

    An unrelated exploration target must not make the selected delivery
    incomplete, while both a queued review and a resolved needs_evidence round
    for selected targets must remain visible to the final report.
    """
    _agent, session, db = _session(tmp_path, "async-review-scope")
    store = DagStore(db)
    store.ensure_bundle("s1")
    result = DagEngine(store).apply_batch(
        MutationBatch(
            session_id="s1",
            actor=GraphActor.HARNESS,
            actor_id="test-harness",
            base_revisions=store.load_bundle().revisions,
            rationale="seed complete selected and unrelated branches",
            operations=[
                AddNode(op="add_node", graph="delivery", node=OccurrenceNode(
                    node_id="r", label="R", role="reactant", evidence_level="structure_supported")),
                AddNode(op="add_node", graph="delivery", node=OccurrenceNode(
                    node_id="p", label="P", role="product", evidence_level="structure_supported")),
                AddNode(op="add_node", graph="delivery", node=OccurrenceNode(
                    node_id="q", label="Q", role="product", evidence_level="structure_supported")),
                AddEdge(op="add_edge", graph="delivery", edge=_completed_edge("step1", "r", "p")),
                AddEdge(op="add_edge", graph="delivery", edge=_completed_edge("step2", "r", "q")),
            ],
        )
    )
    assert result.accepted

    # Persist the selected delivery scope as an accepted claim.  The graph is
    # already complete so any incomplete report below must come from reviews.
    store.save_draft(
        MechanismDraft(
            # The draft row only supplies the accepted claim scope here; the
            # delivery graph was seeded above.  A valid draft still needs one
            # declarative operation in its schema.
            operations=[
                AddNode(
                    op="add_node",
                    graph="delivery",
                    node=OccurrenceNode(node_id="r", label="R", role="reactant"),
                )
            ],
            rationale="selected step1 for this delivery",
            state="accepted",
            claim_spec=ClaimSpec(
                kind="mechanism",
                scope={"targets": ["step1", "step1b"]},
            ),
        ),
        actor_id="test-harness",
    )

    pending_id = store.enqueue_review(
        ReviewRequest(
            request_id="pending-step1",
            kind="evidence",
            requester="coordinator",
            target_ids=["step1"],
            question="Is the selected transition state adequately supported?",
            basis_fingerprint="basis-pending-step1",
        )
    )
    assert pending_id == "pending-step1"
    needs_id = store.enqueue_review(
        ReviewRequest(
            request_id="needs-step1b",
            kind="evidence",
            requester="coordinator",
            target_ids=["step1b"],
            question="Is the selected branch supported?",
            basis_fingerprint="basis-needs-step1b",
        )
    )
    assert needs_id == "needs-step1b"
    needs = store.resolve_review(
        ReviewDecision(
            request_id=needs_id,
            basis_fingerprint="basis-needs-step1b",
            verdict="needs_evidence",
            reason="frequency analysis and an IRC endpoint check are still missing",
            next_action="submit the missing frequency and IRC evidence",
        ),
        expected_basis="basis-needs-step1b",
    )
    assert needs["accepted"]

    report = DagController(
        db, "s1", "dag_guided", conversation_id=db.conversation_id
    ).delivery_report()
    unresolved = [*report.unresolved, *report.inconclusive]
    target_ids = {item.target_id for item in unresolved}
    assert "step1" in target_ids
    assert "step1b" in target_ids
    assert "step2" not in target_ids
    details = " ".join(item.detail for item in unresolved)
    assert "frequency analysis" in details or "needs_evidence" in details


def _save_claim(store, targets):
    store.save_draft(
        MechanismDraft(
            operations=[
                AddNode(
                    op="add_node",
                    graph="delivery",
                    node=OccurrenceNode(node_id="claim-anchor", label="claim-anchor"),
                )
            ],
            rationale="selected delivery scope",
            state="accepted",
            claim_spec=ClaimSpec(kind="mechanism", scope={"targets": list(targets)}),
        ),
        actor_id="test-harness",
    )


def _seed_simple_complete_graph(tmp_path, conversation_id, *, pending=False):
    """Seed a complete graph, optionally retaining machine pending contracts."""
    _agent, session, db = _session(tmp_path, conversation_id)
    store = DagStore(db)
    store.ensure_bundle("s1")
    result = DagEngine(store).apply_batch(
        MutationBatch(
            session_id="s1",
            actor=GraphActor.HARNESS,
            actor_id="test-harness",
            base_revisions=store.load_bundle().revisions,
            rationale="seed complete graph",
            operations=[
                AddNode(op="add_node", graph="delivery", node=OccurrenceNode(
                    node_id="r", label="R", role="reactant", smiles="O", evidence_level="structure_supported",
                    stages=[StageState(kind="geometry")] if pending else [])),
                AddNode(op="add_node", graph="delivery", node=OccurrenceNode(
                    node_id="p", label="P", role="product", evidence_level="structure_supported",
                    stages=[])),
                AddEdge(op="add_edge", graph="delivery", edge=ElementaryStepEdge(
                    edge_id="step1", name="step1", source_node_id="r", target_node_id="p",
                    evidence_level="endpoint_supported",
                    stages=[StageState(kind="ts_opt"), StageState(kind="frequency")] if pending else [])),
            ],
        )
    )
    assert result.accepted
    return session, db, store


@pytest.mark.asyncio
async def test_expanded_declared_scope_blocks_final_delivery_while_review_is_open(tmp_path):
    session, db, store = _seed_simple_complete_graph(tmp_path, "async-expanded-scope")
    expanded_graph = DagEngine(store).apply_batch(MutationBatch(
        session_id="s1", actor=GraphActor.HARNESS, actor_id="test-harness",
        base_revisions=store.load_bundle().revisions,
        rationale="add an already evidenced second step",
        operations=[
            AddNode(op="add_node", graph="delivery", node=OccurrenceNode(
                node_id="q", label="Q", role="product", evidence_level="structure_supported")),
            AddEdge(op="add_edge", graph="delivery", edge=_completed_edge("step2", "p", "q")),
        ],
    ))
    assert expanded_graph.accepted
    _save_claim(store, ["step1"])
    controller = DagController(db, "s1", "dag_guided", conversation_id=db.conversation_id)
    assert controller.delivery_report().complete

    agent = _coordinator(db.conversation_id)
    declared = await call_dag_tool(
        DagProposeMechanism, agent, session,
        rationale="deliver both AB and BC", delivery_targets=["step1", "step2"],
    )
    assert declared.is_success and declared.result["state"] == "open"
    pending = controller.delivery_report()
    assert not pending.complete
    assert any(g.code == "pending_scope_review" for g in pending.unresolved)

    supervisor = make_supervisor(db.conversation_id, workspace_dir=str(tmp_path))
    from cloudra.tools.Plantool.dag_tools.dag_accept_mechanism import DagAcceptMechanism

    accepted = await call_dag_tool(
        DagAcceptMechanism, supervisor, session,
        verdict="accept", draft_id=declared.result["draft_id"],
    )
    assert accepted.is_success
    assert controller.delivery_report().complete


@pytest.mark.asyncio
async def test_exploratory_branch_keeps_old_selected_delivery_complete(tmp_path):
    session, db, store = _seed_simple_complete_graph(tmp_path, "async-exploration-scope")
    _save_claim(store, ["step1"])
    agent = _coordinator(db.conversation_id)
    proposed = await call_dag_tool(
        DagProposeMechanism, agent, session,
        rationale="explore a later BC transformation",
        species=[{"name": "Q"}],
        steps=[{"name": "step2", "from": "P", "to": "Q"}],
    )
    assert proposed.is_success and proposed.result["state"] == "open"
    assert {edge.name for edge in store.load_snapshot().delivery.edges} == {"step1", "step2"}
    assert DagController(db, "s1", "dag_guided", conversation_id=db.conversation_id).delivery_report().complete


def _request(store, request_id, targets, question, basis):
    return store.enqueue_review(
        ReviewRequest(
            request_id=request_id,
            kind="evidence",
            requester="coordinator",
            target_ids=list(targets),
            question=question,
            basis_fingerprint=basis,
        )
    )


@pytest.mark.asyncio
async def test_needs_evidence_replaced_by_new_submission_then_accept_clears_gap(tmp_path):
    _session_obj, db, store = _seed_simple_complete_graph(tmp_path, "async-review-retry")
    _save_claim(store, ["step1"])
    question = "Does the selected saddle support the declared step?"
    first_id = _request(store, "review-first", ["step1"], question, "basis-first")
    first = store.resolve_review(
        ReviewDecision(
            request_id=first_id,
            basis_fingerprint="basis-first",
            verdict="needs_evidence",
            reason="add a frequency analysis",
            next_action="submit the missing frequency analysis",
        ),
        expected_basis="basis-first",
    )
    assert first["accepted"]

    report = DagController(db, "s1", "dag_guided", conversation_id=db.conversation_id).delivery_report()
    assert any(g.code == "supervisor_review_gap" and g.target_id == "step1" for g in report.unresolved)

    second_id = _request(store, "review-second", ["step1"], question, "basis-second")
    # A new submission is an outstanding review; it cannot erase the old
    # needs_evidence decision before the Supervisor accepts it.
    report = DagController(db, "s1", "dag_guided", conversation_id=db.conversation_id).delivery_report()
    assert any(g.code == "pending_evidence_review" and g.target_id == "step1" for g in report.unresolved)
    second = store.resolve_review(
        ReviewDecision(
            request_id=second_id,
            basis_fingerprint="basis-second",
            verdict="accept",
            reason="the replacement evidence answers the question",
        ),
        expected_basis="basis-second",
    )
    assert second["accepted"]
    report = DagController(db, "s1", "dag_guided", conversation_id=db.conversation_id).delivery_report()
    assert not any(g.code == "supervisor_review_gap" and g.target_id == "step1" for g in report.unresolved)
    assert store.get_review_decision_for_request(first_id).verdict == "needs_evidence"
    assert store.get_review_decision_for_request(second_id).verdict == "accept"


@pytest.mark.asyncio
async def test_unscoped_guided_delivery_still_honors_related_review(tmp_path):
    _session_obj, db, store = _seed_simple_complete_graph(tmp_path, "async-review-no-claim")
    review_id = _request(
        store,
        "review-no-claim",
        ["step1"],
        "Is this selected step supported?",
        "basis-no-claim",
    )
    assert review_id == "review-no-claim"
    report = DagController(db, "s1", "dag_guided", conversation_id=db.conversation_id).delivery_report()
    assert any(g.code == "pending_evidence_review" and g.target_id == "step1" for g in report.unresolved)


@pytest.mark.asyncio
async def test_selected_edge_review_includes_endpoint_target(tmp_path):
    _session_obj, db, store = _seed_simple_complete_graph(tmp_path, "async-endpoint-review")
    _save_claim(store, ["step1"])
    review_id = _request(
        store,
        "review-endpoint",
        ["p"],
        "Is the selected endpoint identity supported?",
        "basis-endpoint",
    )
    assert review_id == "review-endpoint"
    report = DagController(db, "s1", "dag_guided", conversation_id=db.conversation_id).delivery_report()
    assert any(g.code == "pending_evidence_review" and g.target_id == "p" for g in report.unresolved)


@pytest.mark.asyncio
@pytest.mark.parametrize("delete_target", [False, True])
async def test_missing_or_deleted_scoped_target_is_a_loud_gap(tmp_path, delete_target):
    _session_obj, db, store = _seed_simple_complete_graph(tmp_path, f"async-missing-target-{delete_target}")
    target = "step1" if delete_target else "deleted-or-never-existed"
    _save_claim(store, [target])
    if delete_target:
        from cloudra.dag.models import RemoveEdge

        removed = DagEngine(store).apply_batch(
            MutationBatch(
                session_id="s1",
                actor=GraphActor.AGENT,
                actor_id="a-0",
                base_revisions=store.load_bundle().revisions,
                rationale="remove out-of-scope branch",
                operations=[RemoveEdge(op="remove_edge", graph="delivery", edge_id="step1")],
            )
        )
        assert removed.accepted
    report = DagController(db, "s1", "dag_guided", conversation_id=db.conversation_id).delivery_report()
    assert any(g.code == "missing_delivery_target" and g.target_id == target for g in report.unresolved)


@pytest.mark.asyncio
@pytest.mark.parametrize("machine_unverified", [False, True])
async def test_real_species_and_step_files_are_reviewed_once_for_final_delivery(
    tmp_path, monkeypatch, machine_unverified
):
    """Real parsed files close the directed review without per-stage resubmission."""
    session, db, _store = _seed_simple_complete_graph(
        tmp_path, "async-real-file-review", pending=True
    )
    agent = _coordinator(db.conversation_id)
    store = DagStore(db)
    supervisor = make_supervisor(db.conversation_id, workspace_dir=str(tmp_path))
    water = FIXTURES_DIR / "gaussian" / "water_opt_freq_g16.out"
    ts = FIXTURES_DIR / "xtb" / "ts_hess_xtb.out"
    if machine_unverified:
        from cloudra.dag.evidence_ingest import TSValidationResult
        from cloudra.tools.Plantool.dag_tools import dag_submit_step_evidence

        monkeypatch.setattr(
            dag_submit_step_evidence,
            "validate_ts_mode",
            lambda *args, **kwargs: TSValidationResult(
                is_valid=False,
                verified=False,
                n_imag=0,
                message="fixture parser is inconclusive about the TS mode",
            ),
        )
    before = store.load_snapshot().delivery
    before_levels = {
        element.node_id if hasattr(element, "node_id") else element.edge_id: element.evidence_level
        for element in [*before.nodes, *before.edges]
    }
    before_stages = {
        element.node_id if hasattr(element, "node_id") else element.edge_id: tuple(
            (stage.kind.value, stage.status.value) for stage in element.stages
        )
        for element in [*before.nodes, *before.edges]
    }

    species = await call_dag_tool(
        DagSubmitSpeciesEvidence,
        agent,
        session,
        species_name="R",
        opt_file=str(water),
        description="fixture minimum",
    )
    assert species.is_success and species.result["status"] == "submitted_for_review"
    reviewed_species = await call_dag_tool(
        DagReviewSpecies,
        supervisor,
        session,
        species_name="R",
        verdict="supported",
        rationale="the parsed optimization/frequency fixture supports the minimum",
    )
    assert reviewed_species.is_success
    assert reviewed_species.result["basis_fingerprint"]

    step = await call_dag_tool(
        DagSubmitStepEvidence,
        agent,
        session,
        step_name="step1",
        ts_file=str(ts),
        reaction_coordinate_description="fixture transition mode",
    )
    assert step.is_success and step.result["status"] == "submitted_for_review"
    if machine_unverified:
        review = store.get_review_request(step.result["review_id"])
        assert review is not None
        assert review.proposal["ts_validation"]["verified"] is False
    reviewed_step = await call_dag_tool(
        DagReviewStep,
        supervisor,
        session,
        step_name="step1",
        verdict="supported",
        rationale="the parsed transition-state fixture supports the selected step",
    )
    assert reviewed_step.is_success
    assert reviewed_step.result["basis_fingerprint"]
    assert store.list_review_requests(state="queued") == []
    after = store.load_snapshot().delivery
    after_levels = {
        element.node_id if hasattr(element, "node_id") else element.edge_id: element.evidence_level
        for element in [*after.nodes, *after.edges]
    }
    after_stages = {
        element.node_id if hasattr(element, "node_id") else element.edge_id: tuple(
            (stage.kind.value, stage.status.value) for stage in element.stages
        )
        for element in [*after.nodes, *after.edges]
    }
    assert after_levels == before_levels
    assert after_stages == before_stages
    report = DagController(db, "s1", "dag_guided", conversation_id=db.conversation_id).delivery_report()
    assert report.complete
    gate = await DagController(
        db, "s1", "dag_guided", conversation_id=db.conversation_id
    ).audit_stop("complete")
    assert gate.action == "allow_final"
    assert gate.basis == "supervisor_supported"


@pytest.mark.asyncio
async def test_accepted_step_review_does_not_credit_replaced_edge_same_id(tmp_path):
    """A review is bound to the reviewed graph object, not merely edge_id."""
    session, db, store = _seed_review_graph(tmp_path, "async-replaced-edge-credit")
    agent = _coordinator(db.conversation_id)
    supervisor = make_supervisor(db.conversation_id, workspace_dir=str(tmp_path))
    ts = FIXTURES_DIR / "xtb" / "ts_hess_xtb.out"

    submitted = await call_dag_tool(
        DagSubmitStepEvidence,
        agent,
        session,
        step_name="step1",
        ts_file=str(ts),
        reaction_coordinate_description="original transition mode",
    )
    assert submitted.is_success
    reviewed = await call_dag_tool(
        DagReviewStep,
        supervisor,
        session,
        step_name="step1",
        verdict="supported",
        rationale="the original step evidence supports both required stages",
    )
    assert reviewed.is_success
    original_report = DagController(
        db, "s1", "dag_guided", conversation_id=db.conversation_id
    ).delivery_report()
    assert original_report.complete

    from cloudra.dag.models import RemoveEdge

    # Add a new endpoint, remove the old edge, then reuse the same edge_id for
    # a different object with fresh pending stages.
    added = DagEngine(store).apply_batch(
        MutationBatch(
            session_id="s1",
            actor=GraphActor.HARNESS,
            actor_id="test-harness",
            base_revisions=store.load_bundle().revisions,
            rationale="add alternative endpoint before replacing edge",
            operations=[
                AddNode(op="add_node", graph="delivery", node=OccurrenceNode(
                    node_id="q", label="Q", role="product", evidence_level="structure_supported")),
            ],
        )
    )
    assert added.accepted
    from cloudra.dag.models import UpdateEdge

    mutated = DagEngine(store).apply_batch(
        MutationBatch(
            session_id="s1",
            actor=GraphActor.HARNESS,
            actor_id="test-harness",
            base_revisions=store.load_bundle().revisions,
            rationale="change endpoint identity while retaining old evidence refs",
            operations=[
                UpdateEdge(
                    op="update_edge",
                    graph="delivery",
                    edge_id="step1",
                    changes={
                        "target_node_id": "q",
                        "stages": [
                            {"kind": "ts_opt", "status": "pending"},
                            {"kind": "frequency", "status": "pending"},
                        ],
                    },
                )
            ],
        )
    )
    # Endpoint identity is immutable in-place; the supported replacement path
    # below removes and re-adds the edge.  The old refs therefore remain audit
    # history on the old object rather than silently changing its meaning.
    assert not mutated.accepted
    assert mutated.rejection_code == "immutable_field"
    removed = DagEngine(store).apply_batch(
        MutationBatch(
            session_id="s1",
            actor=GraphActor.AGENT,
            actor_id="a-0",
            base_revisions=store.load_bundle().revisions,
            rationale="replace the original edge object",
            operations=[RemoveEdge(op="remove_edge", graph="delivery", edge_id="step1")],
        )
    )
    assert removed.accepted
    replaced = DagEngine(store).apply_batch(
        MutationBatch(
            session_id="s1",
            actor=GraphActor.AGENT,
            actor_id="a-0",
            base_revisions=store.load_bundle().revisions,
            rationale="re-add edge id for a different endpoint pair",
            operations=[
                AddEdge(op="add_edge", graph="delivery", edge=ElementaryStepEdge(
                    edge_id="step1", name="step1", source_node_id="r", target_node_id="q",
                    stages=[StageState(kind="ts_opt"), StageState(kind="frequency")],
                )),
            ],
        )
    )
    assert replaced.accepted

    replacement_report = DagController(
        db, "s1", "dag_guided", conversation_id=db.conversation_id
    ).delivery_report()
    assert any(
        gate.code == "missing_stage_evidence" and gate.target_id == "step1"
        for gate in replacement_report.unresolved
    )


@pytest.mark.asyncio
async def test_new_per_file_submission_supersedes_old_queued_review(tmp_path):
    session, db, store = _seed_review_graph(tmp_path, "async-supersede-file-review")
    agent = _coordinator(db.conversation_id)
    ts = FIXTURES_DIR / "xtb" / "ts_hess_xtb.out"
    first = await call_dag_tool(
        DagSubmitStepEvidence,
        agent,
        session,
        step_name="step1",
        ts_file=str(ts),
        reaction_coordinate_description="first candidate transition mode",
    )
    assert first.is_success
    first_id = first.result["review_id"]
    second = await call_dag_tool(
        DagSubmitStepEvidence,
        agent,
        session,
        step_name="step1",
        ts_file=str(ts),
        reaction_coordinate_description="replacement candidate transition mode",
    )
    assert second.is_success
    second_id = second.result["review_id"]
    assert first_id != second_id
    assert store.get_review_request(first_id).state == "superseded"
    queued = store.list_review_requests(state="queued")
    assert [request.request_id for request in queued] == [second_id]


@pytest.mark.asyncio
async def test_endpoint_identity_change_invalidates_old_step_review_credit(tmp_path):
    session, db, store = _seed_review_graph(tmp_path, "async-review-endpoint-identity")
    agent = _coordinator(db.conversation_id)
    supervisor = make_supervisor(db.conversation_id, workspace_dir=str(tmp_path))
    submitted = await call_dag_tool(
        DagSubmitStepEvidence,
        agent,
        session,
        step_name="step1",
        ts_file=str(FIXTURES_DIR / "xtb" / "ts_hess_xtb.out"),
        reaction_coordinate_description="identity-bound transition mode",
    )
    assert submitted.is_success
    reviewed = await call_dag_tool(
        DagReviewStep,
        supervisor,
        session,
        step_name="step1",
        verdict="supported",
        rationale="the original endpoints and transition evidence agree",
    )
    assert reviewed.is_success
    assert DagController(db, "s1", "dag_guided", conversation_id=db.conversation_id).delivery_report().complete

    from cloudra.dag.models import UpdateNode

    changed = DagEngine(store).apply_batch(
        MutationBatch(
            session_id="s1",
            actor=GraphActor.HARNESS,
            actor_id="test-harness",
            base_revisions=store.load_bundle().revisions,
            rationale="replace the endpoint chemical identity",
            operations=[
                UpdateNode(
                    op="update_node",
                    graph="delivery",
                    node_id="r",
                    changes={"smiles": "N#N", "label": "R-mutated"},
                )
            ],
        )
    )
    assert changed.accepted
    report = DagController(db, "s1", "dag_guided", conversation_id=db.conversation_id).delivery_report()
    assert any(
        gate.code == "missing_stage_evidence" and gate.target_id == "step1"
        for gate in report.unresolved
    )


@pytest.mark.asyncio
async def test_open_or_rejected_relevant_draft_blocks_final_delivery_only(tmp_path):
    session, db, store = _seed_simple_complete_graph(tmp_path, "async-final-draft-gate")
    controller = DagController(db, "s1", "dag_guided", conversation_id=db.conversation_id)
    draft = MechanismDraft(
        operations=[
            AddEdge(
                op="add_edge",
                graph="delivery",
                edge=ElementaryStepEdge(
                    edge_id="step1",
                    name="step1",
                    source_node_id="r",
                    target_node_id="p",
                    stages=[],
                ),
            )
        ],
        rationale="a scoped alternative mechanism candidate",
        state="open",
    )
    draft_id = store.save_draft(draft, actor_id="coordinator")

    # The open candidate is usable for exploratory compute, but remains a
    # final-delivery review debt.
    assert await controller.check_substantive_gate("submit_compute_job", {}) is None
    report = controller.delivery_report()
    assert any(g.code == "pending_mechanism_review" and g.target_id == "step1" for g in report.unresolved)

    store.set_draft_state(draft_id, "rejected", reject_reason="endpoint identity needs revision")
    report = controller.delivery_report()
    assert any(g.code == "rejected_mechanism_review" and g.target_id == "step1" for g in report.unresolved)

    revised_id = store.save_draft(
        draft.model_copy(update={"state": "accepted", "rationale": "revised candidate accepted"}),
        actor_id="harness:auto",
    )
    assert revised_id != draft_id
    report = controller.delivery_report()
    assert not any(
        g.code in {"pending_mechanism_review", "rejected_mechanism_review"}
        and g.target_id == "step1"
        for g in report.unresolved
    )
    assert report.complete


@pytest.mark.asyncio
async def test_public_delivery_report_matches_final_controller_after_file_accept_and_pending_review(
    tmp_path,
):
    session, db, store = _seed_simple_complete_graph(tmp_path, "async-report-source-of-truth")
    agent = _coordinator(db.conversation_id)
    supervisor = make_supervisor(db.conversation_id, workspace_dir=str(tmp_path))
    file_out = await call_dag_tool(
        DagSubmitSpeciesEvidence,
        agent,
        session,
        species_name="R",
        opt_file=str(FIXTURES_DIR / "gaussian" / "water_opt_freq_g16.out"),
        description="accepted real file before a new review round",
    )
    assert file_out.is_success
    accepted = await call_dag_tool(
        DagReviewSpecies,
        supervisor,
        session,
        species_name="R",
        verdict="supported",
        rationale="the immutable minimum fixture is sufficient",
    )
    assert accepted.is_success

    pending_id = _request(
        store,
        "pending-after-file-accept",
        ["r"],
        "Does the accepted species remain valid under the new scope?",
        "basis-pending-after-accept",
    )
    assert pending_id == "pending-after-file-accept"
    public = await call_dag_tool(DagDeliveryReport, agent, session)
    assert public.is_success
    controller_report = DagController(
        db, "s1", "dag_guided", conversation_id=db.conversation_id
    ).delivery_report()
    assert public.result == controller_report.model_dump(mode="json")
    assert any(
        gate["code"] == "pending_evidence_review"
        and gate["target_id"] == "r"
        for gate in public.result["unresolved"]
    )


@pytest.mark.parametrize("scope", [["step1"], ["r"]])
def test_scope_only_review_supersedes_only_its_named_draft_debt(tmp_path, scope):
    _, db, store = _seed_simple_complete_graph(tmp_path, "scope-only-revision")
    controller = DagController(db, "s1", "dag_guided", conversation_id=db.conversation_id)
    store.save_draft(MechanismDraft(
        operations=[AddEdge(op="add_edge", graph="delivery", edge=ElementaryStepEdge(
            edge_id="step1", name="step1", source_node_id="r", target_node_id="p"))],
        rationale="initial proposal", state="rejected"), actor_id="coordinator")
    revised = store.save_draft(MechanismDraft(
        operations=[], rationale="revised rationale for existing graph", state="open",
        claim_spec=ClaimSpec(kind="mechanism", scope={"targets": scope})), actor_id="coordinator")
    store.set_draft_state(revised, "accepted")
    gaps = controller._draft_gaps({"r", "p", "step1"}, {"step1": ("edge", None)})
    debts = [g for g in gaps if g.code == "rejected_mechanism_review" and g.target_id == "step1"]
    assert bool(debts) == ("step1" not in scope)
