"""Task 8: stop audit gate matrix (StopGate)."""

import asyncio

import pytest

from cloudra.dag.controller import DagController
from cloudra.dag.review_requests import ReviewDecision
from cloudra.dag.stop_audit import StopGate
from cloudra.persistence.database import ConversationDB


async def _controller(tmp_path, conversation_id, mode):
    db = await asyncio.to_thread(lambda: ConversationDB(conversation_id, data_dir=tmp_path).init())
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


def test_stop_contract_keeps_supervisor_decision_identifiers_internal():
    from cloudra.tools.Stoptool.stop_tool import StopTool_input_schema

    assert 'approval_id' not in StopTool_input_schema.model_json_schema()['properties']


@pytest.mark.asyncio
async def test_complete_empty_graph_continue_work(tmp_path):
    c = await _controller(tmp_path, "exit-empty", "dag_record")
    gate = await c.audit_stop("complete")
    assert gate.action == "continue_work"


@pytest.mark.asyncio
async def test_reasoned_stage_dispositions_complete_scope_without_claiming_scientific_verification(tmp_path):
    from cloudra.dag.engine import DagEngine
    from cloudra.dag.models import (
        AddEdge,
        AddNode,
        ElementaryStepEdge,
        GraphActor,
        MutationBatch,
        SpeciesNode,
        StageState,
    )

    c = await _controller(tmp_path, "disposed-scope", "dag_record")
    result = await asyncio.to_thread(DagEngine(c.store).apply_batch, MutationBatch(
        session_id="s1", actor=GraphActor.HARNESS, actor_id="harness",
        base_revisions=(await asyncio.to_thread(c.store.load_bundle)).revisions, rationale="record approved scope dispositions",
        operations=[
            AddNode(op="add_node", graph="delivery", node=SpeciesNode(node_id=name, name=name, smiles="O",
                stages=[StageState(kind="geometry", status="skipped", reason="outside the declared scope")]))
            for name in ("r", "p")
        ] + [AddEdge(op="add_edge", graph="delivery", edge=ElementaryStepEdge(edge_id="e", name="e",
            source_node_id="r", target_node_id="p", stages=[
                StageState(kind=kind, status="skipped", reason="outside the declared scope")
                for kind in ("ts_opt", "frequency", "short_irc")]))],
    ))
    assert result.accepted

    gate = await c.audit_stop("complete")

    assert gate.action == "allow_final" and gate.report.complete
    assert gate.basis == "scope_completed"


@pytest.mark.asyncio
async def test_audit_stop_reloads_store_contract_after_strengthen(tmp_path):
    """initialize 缓存的契约不得盖过 store 里后来收紧的 require_thermochemistry。"""
    from cloudra.dag.engine import DagEngine
    from cloudra.dag.models import (
        AddEdge,
        AddNode,
        CoverageContract,
        ElementaryStepEdge,
        GraphActor,
        MutationBatch,
        OccurrenceNode,
        SetCoverageContract,
        StageState,
        StageStatus,
    )

    c = await _controller(tmp_path, "exit-stale-contract", "dag_record")
    engine = DagEngine(c.store)
    supported = [
        StageState(kind="ts_opt", status=StageStatus.SUPPORTED),
        StageState(kind="frequency", status=StageStatus.SUPPORTED),
    ]
    seeded = engine.apply_batch(
        MutationBatch(
            session_id="s1",
            actor=GraphActor.HARNESS,
            actor_id="test-harness",
            base_revisions=c.store.load_bundle().revisions,
            rationale="seed a live-complete step without thermochemistry",
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
                        source_node_id="r",
                        target_node_id="p",
                        stages=supported,
                    ),
                ),
            ],
        )
    )
    assert seeded.accepted
    first = await c.audit_stop("complete")
    assert first.action == "allow_final"
    assert first.report is not None and first.report.complete

    stronger = engine.apply_batch(
        MutationBatch(
            session_id="s1",
            actor=GraphActor.USER,
            actor_id="user",
            base_revisions=c.store.load_bundle().revisions,
            rationale="require thermochemistry after initialize cached the default",
            operations=[
                SetCoverageContract(
                    op="set_coverage_contract",
                    contract=CoverageContract.mechanism_default(
                        require_thermochemistry=True
                    ),
                )
            ],
        )
    )
    assert stronger.accepted
    gate = await c.audit_stop("complete")
    assert gate.action == "continue_work"
    assert gate.report is not None and not gate.report.complete


@pytest.mark.asyncio
async def test_user_terminated_requires_real_event(tmp_path):
    c = await _controller(tmp_path, "exit-user", "dag_record")
    fake = await c.audit_stop("user_terminated")
    assert fake.action == "continue_work"
    real = await c.audit_stop("user_terminated", user_stop_event_id="evt_user_1")
    assert real.action == "continue_work"


@pytest.mark.asyncio
async def test_rejected_exit_review_is_reused_as_continue_work(tmp_path):
    c = await _controller(tmp_path, "exit-guided-rejected", "dag_guided")
    first = await c.audit_stop("partial")
    request = await asyncio.to_thread(c.store.get_review_request, first.request_id)
    decision = ReviewDecision(
        request_id=request.request_id,
        basis_fingerprint=request.basis_fingerprint,
        verdict="reject",
        reason="Missing evidence",
        next_action="Inspect existing log",
    )
    c.store.resolve_review(decision, expected_basis=request.basis_fingerprint)
    second = await c.audit_stop("partial")
    assert second.action == "continue_work"
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
        decision, expected_basis=request.basis_fingerprint
    )["accepted"]
    second = await c.audit_stop("partial")
    assert second.action == "allow_final"
    assert c.store.list_review_requests(state="queued") == []


async def _seed_complete_delivery(c, *, scope_only=False):
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

    result = await asyncio.to_thread(DagEngine(c.store).apply_batch, MutationBatch(
        session_id="s1", actor=GraphActor.HARNESS, actor_id="harness",
        base_revisions=(await asyncio.to_thread(c.store.load_bundle)).revisions,
        rationale="seed the proposed complete delivery",
        operations=[
            AddNode(op="add_node", graph="delivery", node=OccurrenceNode(
                node_id=name, label=name, evidence_level="structure_supported"))
            for name in ("r", "p")
        ] + [AddEdge(op="add_edge", graph="delivery", edge=ElementaryStepEdge(
            edge_id="step1", source_node_id="r", target_node_id="p", evidence_level="endpoint_supported",
            stages=[StageState(kind="ts_opt", status="skipped", reason="outside the approved scope")]
            if scope_only else []))],
    ))
    assert result.accepted


@pytest.mark.asyncio
@pytest.mark.parametrize("verdict", ["accept", "reject", "needs_evidence"])
async def test_complete_final_review_decision_is_reused_without_duplicate_wake(tmp_path, monkeypatch, verdict):
    c = await _controller(tmp_path, "exit-complete-" + verdict, "dag_guided")
    await _seed_complete_delivery(c)
    notices = []

    async def notify(message):
        notices.append(message)

    monkeypatch.setattr(c, "_notify_supervisor", notify)
    first = await c.audit_stop("complete")
    assert first.action == "wait_review"
    assert first.report.complete
    request = await asyncio.to_thread(c.store.get_review_request, first.request_id)
    assert request.kind == "exit"
    assert request.proposal["disposition"] == "complete"
    assert set(request.proposal["scope"]) == {"r", "p", "step1"}
    assert request.proposal["remaining_gaps"] == []
    assert (await c.audit_stop("complete")).request_id == first.request_id
    assert len(notices) == 1
    decision = ReviewDecision(request_id=request.request_id, basis_fingerprint=request.basis_fingerprint,
        verdict=verdict, reason="Original path evidence reviewed", next_action="Inspect the native IRC geometry"
        if verdict != "accept" else None)
    assert (await asyncio.to_thread(c.store.resolve_review, decision,
        expected_basis=request.basis_fingerprint))["accepted"]
    for _ in range(2):
        reused = await c.audit_stop("complete")
        assert reused.request_id == first.request_id
        if verdict == "accept":
            assert reused.action == "allow_final"
            assert reused.basis == "supervisor_supported"
        else:
            assert reused.action == "continue_work"
            assert decision.reason in reused.reason and decision.next_action in reused.reason
    assert len(notices) == 1
    assert len(await asyncio.to_thread(c.store.list_review_requests, None)) == 1
    if verdict == "accept":
        await c.commit_stop()
        def recorded():
            with c.db.connect() as con:
                return con.execute("SELECT disposition FROM dag_delivery_dispositions").fetchall()
        assert await asyncio.to_thread(recorded) == [("complete",)]


@pytest.mark.asyncio
async def test_changed_complete_delivery_requires_a_new_final_review(tmp_path):
    from cloudra.dag.models import GraphActor, MutationBatch, UpdateEdge

    c = await _controller(tmp_path, "exit-complete-changed", "dag_guided")
    await _seed_complete_delivery(c)
    first = await c.audit_stop("complete")
    assert first.action == "wait_review"
    request = await asyncio.to_thread(c.store.get_review_request, first.request_id)
    assert (await asyncio.to_thread(c.store.resolve_review, ReviewDecision(
        request_id=request.request_id, basis_fingerprint=request.basis_fingerprint,
        verdict="accept", reason="reviewed this proposed step"), expected_basis=request.basis_fingerprint))["accepted"]
    assert (await c.audit_stop("complete")).action == "allow_final"
    assert (await asyncio.to_thread(c.engine.apply_batch, MutationBatch(
        session_id="s1", actor=GraphActor.HARNESS, actor_id="harness",
        base_revisions=(await asyncio.to_thread(c.store.load_bundle)).revisions,
        rationale="revise the delivered step statement", operations=[UpdateEdge(
            op="update_edge", graph="delivery", edge_id="step1", changes={"label": "revised step statement"})]
    ))).accepted
    changed = await c.audit_stop("complete")
    assert changed.action == "wait_review"
    assert changed.request_id != first.request_id


@pytest.mark.asyncio
async def test_complete_scope_only_still_requires_review_and_keeps_honest_basis(tmp_path):
    c = await _controller(tmp_path, "exit-complete-scope", "dag_guided")
    await _seed_complete_delivery(c, scope_only=True)
    first = await c.audit_stop("complete")
    assert first.action == "wait_review"
    request = await asyncio.to_thread(c.store.get_review_request, first.request_id)
    assert (await asyncio.to_thread(c.store.resolve_review, ReviewDecision(
        request_id=request.request_id, basis_fingerprint=request.basis_fingerprint,
        verdict="accept", reason="approved the declared limited scope"), expected_basis=request.basis_fingerprint))["accepted"]
    final = await c.audit_stop("complete")
    assert final.action == "allow_final"
    assert final.basis == "scope_completed"


@pytest.mark.asyncio
async def test_final_review_never_bypasses_complete_coverage_gaps(tmp_path):
    c = await _controller(tmp_path, "exit-complete-gaps", "dag_guided")
    partial = await c.audit_stop("partial")
    request = await asyncio.to_thread(c.store.get_review_request, partial.request_id)
    assert (await asyncio.to_thread(c.store.resolve_review, ReviewDecision(
        request_id=request.request_id, basis_fingerprint=request.basis_fingerprint,
        verdict="accept", reason="only the partial is acceptable"), expected_basis=request.basis_fingerprint))["accepted"]
    complete = await c.audit_stop("complete")
    assert complete.action == "continue_work"
    assert not complete.report.complete
    assert len(await asyncio.to_thread(c.store.list_review_requests, None)) == 1


@pytest.mark.asyncio
async def test_complete_final_review_waits_until_background_drains(tmp_path, monkeypatch):
    c = await _controller(tmp_path, "exit-complete-background", "dag_guided")
    await _seed_complete_delivery(c)
    pending = True

    async def has_background():
        return pending

    monkeypatch.setattr(c, "_has_pending_background", has_background)
    assert (await c.audit_stop("complete")).action == "wait_background"
    assert await asyncio.to_thread(c.store.list_review_requests, None) == []
    pending = False
    assert (await c.audit_stop("complete")).action == "wait_review"


@pytest.mark.asyncio
async def test_partial_exit_forwards_new_diagnostic_material_to_supervisor(tmp_path):
    c = await _controller(tmp_path, "exit-new-diagnostic", "dag_guided")
    first = await c.audit_stop("partial", reason="Initial checkpoint", final_answer="Initial findings")
    request = c.store.get_review_request(first.request_id)
    assert request.proposal["reason"] == "Initial checkpoint"
    assert request.proposal["final_answer"] == "Initial findings"
    decision = ReviewDecision(request_id=request.request_id,
        basis_fingerprint=request.basis_fingerprint, verdict="needs_evidence",
        reason="Inspect the second candidate")
    assert (await asyncio.to_thread(c.store.resolve_review, decision, expected_basis=request.basis_fingerprint))["accepted"]
    changed = await c.audit_stop("partial", reason="Second candidate failed; see ts_0033/process.json",
                                final_answer="The bound product representation differs")
    assert changed.action == "wait_review"
    assert changed.request_id != first.request_id
    queued = await asyncio.to_thread(c.store.get_review_request, changed.request_id)
    assert "ts_0033/process.json" in queued.proposal["reason"]
    assert queued.proposal["final_answer"] == "The bound product representation differs"
    assert changed.action != "allow_final"



@pytest.mark.asyncio
async def test_approved_partial_confirmation_reuses_saved_material_without_copying_ids(tmp_path):
    c = await _controller(tmp_path, "exit-confirm-saved-material", "dag_guided")
    first = await c.audit_stop("partial", reason="Search exhausted within the present scope",
                               final_answer="Evidence is incomplete; this is a partial result")
    request = await asyncio.to_thread(c.store.get_review_request, first.request_id)
    decision = ReviewDecision(request_id=request.request_id,
        basis_fingerprint=request.basis_fingerprint, verdict="accept", reason="Partial evidence is accurately described")
    assert (await asyncio.to_thread(c.store.resolve_review, decision, expected_basis=request.basis_fingerprint))["accepted"]
    confirmation = await c.audit_stop("partial")
    assert confirmation.action == "allow_final"
    assert confirmation.final_answer == "Evidence is incomplete; this is a partial result"
    assert len(await asyncio.to_thread(c.store.list_review_requests, None)) == 1



@pytest.mark.asyncio
@pytest.mark.parametrize("verdict", [None, "needs_evidence", "reject"])
async def test_partial_confirmation_never_recovers_old_approval_after_new_submission(tmp_path, verdict):
    c = await _controller(tmp_path, "exit-latest-decision", "dag_guided")
    first = await c.audit_stop("partial", reason="Initial scope", final_answer="Initial candidate")
    request = await asyncio.to_thread(c.store.get_review_request, first.request_id)
    approved = ReviewDecision(request_id=request.request_id, basis_fingerprint=request.basis_fingerprint,
        verdict="accept", reason="Accept initial candidate")
    assert (await asyncio.to_thread(c.store.resolve_review, approved, expected_basis=request.basis_fingerprint))["accepted"]
    second = await c.audit_stop("partial", reason="New diagnostics", final_answer="Updated candidate")
    current = await asyncio.to_thread(c.store.get_review_request, second.request_id)
    if verdict is not None:
        rejected = ReviewDecision(request_id=current.request_id, basis_fingerprint=current.basis_fingerprint,
            verdict=verdict, reason="Updated evidence remains incomplete")
        assert (await asyncio.to_thread(c.store.resolve_review, rejected, expected_basis=current.basis_fingerprint))["accepted"]
    confirmation = await c.audit_stop("partial")
    assert confirmation.action == ("wait_review" if verdict is None else "continue_work")
    assert confirmation.request_id == second.request_id



@pytest.mark.asyncio
async def test_replaced_exit_request_cannot_receive_a_late_approval(tmp_path):
    c = await _controller(tmp_path, 'exit-late-verdict', 'dag_guided')
    first = await c.audit_stop('partial', reason='Initial material')
    old = await asyncio.to_thread(c.store.get_review_request, first.request_id)
    second = await c.audit_stop('partial', reason='New diagnostic material')
    late = ReviewDecision(request_id=old.request_id, basis_fingerprint=old.basis_fingerprint,
        verdict='accept', reason='Late approval of the replaced material')

    result = await asyncio.to_thread(c.store.resolve_review, late, expected_basis=old.basis_fingerprint)

    assert not result['accepted']
    assert result['rejection_code'] == 'stale_basis'
    assert (await asyncio.to_thread(c.store.get_review_request, old.request_id)).state == 'superseded'
    assert (await c.audit_stop('partial')).request_id == second.request_id



@pytest.mark.asyncio
@pytest.mark.parametrize("disposition", ["partial", "complete"])
@pytest.mark.parametrize("verdict", [None, "accept", "reject"])
@pytest.mark.parametrize("confirmation", [{}, {"reason": "", "final_answer": ""}], ids=["omitted", "empty_strings"])
async def test_empty_confirmation_keeps_current_review_material(tmp_path, disposition, verdict, confirmation):
    c = await _controller(tmp_path, "empty-confirmation", "dag_guided")
    if disposition == "complete":
        await _seed_complete_delivery(c)
    first = await c.audit_stop(disposition, reason="Recorded stopping reason", final_answer="Reviewed answer")
    assert first.action == "wait_review"
    request = await asyncio.to_thread(c.store.get_review_request, first.request_id)
    if verdict is not None:
        decision = ReviewDecision(request_id=request.request_id, basis_fingerprint=request.basis_fingerprint,
            verdict=verdict, reason="Supervisor decision")
        assert (await asyncio.to_thread(c.store.resolve_review, decision,
            expected_basis=request.basis_fingerprint))["accepted"]

    reused = await c.audit_stop(disposition, **confirmation)

    assert reused.request_id == first.request_id
    assert reused.action == ("wait_review" if verdict is None else "allow_final" if verdict == "accept" else "continue_work")
    saved = await asyncio.to_thread(c.store.get_review_request, first.request_id)
    assert saved.proposal["reason"] == "Recorded stopping reason"
    assert saved.proposal["final_answer"] == "Reviewed answer"
    assert saved.state == ("queued" if verdict is None else "resolved")
    assert len(await asyncio.to_thread(c.store.list_review_requests, None)) == 1
    if verdict == "accept":
        assert reused.final_answer == "Reviewed answer"
