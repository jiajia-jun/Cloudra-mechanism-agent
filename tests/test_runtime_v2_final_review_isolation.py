"""Final delivery review uses a new session, outside the research discussion."""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timezone

import pytest

from cloudra.benchmark.watch import RunWatcher, has_running_peers
from cloudra.dag.controller import DagController
from cloudra.dag.models import CallReview
from cloudra.dag.review_requests import ReviewDecision, ReviewRequest
from cloudra.dag.stop_audit import has_running_siblings
from cloudra.dag.store import DagStore
from cloudra.persistence.database import ConversationDB
from cloudra.runtime_v2.commands import CommandBus
from cloudra.runtime_v2.core import RuntimeCore
from cloudra.runtime_v2.failures import RunFailureKind
from cloudra.runtime_v2.hub_bridge import handle_hub_tool
from cloudra.runtime_v2.persistence import RuntimeStore, restore_core
from cloudra.runtime_v2.policies.base import ToolCall
from cloudra.runtime_v2.schemas import AgentState, Command
from cloudra.runtime_v2.supervision import (
    TERMINAL_SUPERVISOR_PIN_KEY,
    find_project_supervisor,
    notify_supervisor,
    reconcile_supervision,
)

TASK = "Original HB10 task: compare electronic barriers, without ZPE or thermal corrections."
CONSTRAINT = "User correction: preserve every original native evidence file."
OLD_INTENT = "Private research-review intent: demand an unrelated Gibbs comparison."


async def _setup(tmp_path, *, durable=False):
    core = RuntimeCore(strict_events=True)
    if durable:
        core.store = await asyncio.to_thread(RuntimeStore, tmp_path / "runtime.db")
    bus = CommandBus(core)
    project = (await bus.execute(Command(type="project.create", payload={
        "name": "independent-final-review",
        "workspace_dir": str(tmp_path),
        "settings": {"orchestration_mode": "dag_guided"},
    }))).data
    coordinator = (await bus.execute(Command(type="agent.spawn",
        target={"project_id": project.id}, payload={
            "role_id": "coordinator", "query": TASK,
            "settings": {"orchestration_mode": "dag_guided"},
        }, actor="user"))).data
    await bus.execute(Command(type="agent.message", target={"session_id": coordinator.id},
        payload={"content": CONSTRAINT}, actor="user"))
    await notify_supervisor(core, project.id, observation="An earlier research result was recorded.")
    process_supervisor = find_project_supervisor(core, project.id)
    assert process_supervisor is not None
    if process_supervisor.current_run is None:
        await core.agent_host.start_run(process_supervisor)
    await core.contexts.append_output(agent=process_supervisor,
        run_id=process_supervisor.current_run.run_id,
        messages=[{"role": "assistant", "content": OLD_INTENT}])
    await core.agent_host.finish_run(process_supervisor, outcome="succeeded")
    db = await asyncio.to_thread(lambda: ConversationDB(project.id).init())
    controller = DagController(db, coordinator.id, "dag_guided",
        conversation_id=project.id, working_directory=tmp_path, core=core)
    await controller.initialize()
    return core, bus, project, coordinator, process_supervisor, controller


def _reviewers(core, project_id):
    return [agent for agent in core.agents.values()
            if agent.project_id == project_id and agent.role_id == "supervisor"
            and getattr(agent, "final_review_request_id", None)]


def _visible_text(core, agent):
    context = core.session_contexts.get(agent.id)
    messages = list(context.messages) if context is not None else []
    messages.extend(core.notices.collect_batch(agent.id, fresh=True))
    messages.extend(event.data for event in core.event_log.query_session(
        agent.id, types={"agent.message_injected"}, limit=None))
    return json.dumps(messages, ensure_ascii=False)


async def _finish(core, agent):
    if agent.current_run is not None:
        await core.agent_host.finish_run(agent, outcome="succeeded")


async def _bound_reviewer(core, bus, project, coordinator, controller, *, reason):
    request_id = await _queue_exit(controller, reason=reason)
    result = await bus.execute(Command(type="agent.spawn", target={"project_id": project.id},
        payload={"role_id": "supervisor", "parent_session_id": coordinator.id,
                 "final_review_request_id": request_id}, actor="system"))
    assert result.accepted
    reviewer = result.data
    await core.agent_host.start_run(reviewer)
    return reviewer


async def _queue_exit(controller, *, reason):
    snapshot = await asyncio.to_thread(controller.engine.snapshot)
    request = ReviewRequest(kind="exit", requester=controller.session_id,
        target_ids=[snapshot.delivery.graph_id], question="May the current partial delivery finish?",
        proposal={"disposition": "partial", "reason": reason}, basis_fingerprint="sha256:" + reason)
    return await asyncio.to_thread(controller.store.enqueue_review, request)


@pytest.mark.asyncio
async def test_partial_exit_creates_independent_supervisor_with_full_user_scope(tmp_path):
    core, _bus, project, _coordinator, process, controller = await _setup(tmp_path)
    try:
        gate = await controller.audit_stop("partial", reason="Deliver the observed partial result.")
        assert gate.action == "wait_review"
        reviewers = _reviewers(core, project.id)
        assert len(reviewers) == 1, "exit review must spawn a new Supervisor session"
        final = reviewers[0]
        assert final.id != process.id
        assert final.final_review_request_id == gate.request_id
        assert OLD_INTENT in _visible_text(core, process)
        visible = _visible_text(core, final)
        assert OLD_INTENT not in visible, "the final reviewer must not inherit prior intentions"
        assert TASK in visible
        assert CONSTRAINT in visible
        assert find_project_supervisor(core, project.id).id == process.id
    finally:
        await core.aclose()


@pytest.mark.asyncio
async def test_same_pending_exit_reuses_reviewer_but_new_submission_gets_fresh_context(tmp_path):
    core, _bus, project, _coordinator, _process, controller = await _setup(tmp_path)
    try:
        first = await controller.audit_stop("partial", reason="Initial partial delivery.")
        assert first.action == "wait_review"
        reviewers = _reviewers(core, project.id)
        assert len(reviewers) == 1, "the first exit submission must get its own reviewer"
        first_reviewer = reviewers[0]
        await _finish(core, first_reviewer)

        duplicate = await controller.audit_stop("partial")
        assert duplicate.request_id == first.request_id
        assert [agent.id for agent in _reviewers(core, project.id)] == [first_reviewer.id]
        await _finish(core, first_reviewer)

        second = await controller.audit_stop("partial", reason="Revised partial delivery with new limits.")
        assert second.action == "wait_review"
        assert second.request_id != first.request_id
        reviewers = _reviewers(core, project.id)
        assert len(reviewers) == 2
        second_reviewer = next(agent for agent in reviewers if agent.id != first_reviewer.id)
        assert second_reviewer.final_review_request_id == second.request_id
        assert OLD_INTENT not in _visible_text(core, second_reviewer)
    finally:
        await core.aclose()


def _seed_call_review(project_id, coordinator_id):
    store = DagStore(ConversationDB(project_id))
    store.enqueue_call_review(CallReview(
        review_id="rev_" + uuid.uuid4().hex,
        tool_call_id="tc_new_scientific_result", tool_name="log_parser", is_success=True,
        caller_session_id=coordinator_id, caller_role_id="coordinator", caller_legacy_id="a-0",
        arguments_digest="sha256:test-scientific-result", result_summary="{}", source_path="",
        result_kind="ok", state="pending", source="explicit",
        created_at=datetime.now(timezone.utc).isoformat(),
    ))


@pytest.mark.asyncio
async def test_ordinary_scientific_review_still_notifies_process_supervisor(tmp_path):
    core, _bus, project, coordinator, process, controller = await _setup(tmp_path)
    try:
        gate = await controller.audit_stop("partial", reason="Pending final review.")
        assert gate.action == "wait_review"
        reviewers = _reviewers(core, project.id)
        assert len(reviewers) == 1
        before = len(core.event_log.query_session(process.id, types={"agent.message_injected"}))
        await asyncio.to_thread(_seed_call_review, project.id, coordinator.id)
        await notify_supervisor(core, project.id, reason="new scientific evidence")
        assert find_project_supervisor(core, project.id).id == process.id
        after = core.event_log.query_session(process.id, types={"agent.message_injected"})
        assert len(after) > before
        assert len(_reviewers(core, project.id)) == 1
    finally:
        await core.aclose()


@pytest.mark.asyncio
async def test_restore_parks_pending_final_review_without_spawning_or_waking(tmp_path):
    core, bus, project, _coordinator, _process, controller = await _setup(tmp_path, durable=True)
    restored = None
    try:
        gate = await controller.audit_stop("partial", reason="Pending final review at shutdown.")
        assert gate.action == "wait_review"
        reviewers = _reviewers(core, project.id)
        assert len(reviewers) == 1
        final_id = reviewers[0].id
        await _finish(core, reviewers[0])
        await bus.flush_snapshot()

        restored = RuntimeCore(strict_events=True)
        restored.store = await asyncio.to_thread(RuntimeStore, tmp_path / "runtime.db")
        await asyncio.to_thread(restore_core, restored, restored.store)
        before_agents = set(restored.agents)
        before_runs = len(await asyncio.to_thread(
            restored.event_log.query_session, final_id, types={"run.started"}))
        await reconcile_supervision(restored, project.id, auto_wake=False)
        assert set(restored.agents) == before_agents
        after_runs = await asyncio.to_thread(
            restored.event_log.query_session, final_id, types={"run.started"})
        assert len(after_runs) == before_runs
        assert restored.agents[final_id].state.value == "succeeded"
        assert restored.agents[final_id].final_review_request_id == gate.request_id
    finally:
        if restored is not None:
            await restored.aclose()
        await core.aclose()


@pytest.mark.asyncio
async def test_resume_recreates_missing_reviewer_after_request_was_committed(tmp_path, monkeypatch):
    core, bus, project, coordinator, _process, controller = await _setup(tmp_path, durable=True)
    restored = None
    try:
        async def interrupted_before_notification(_reason):
            return None

        monkeypatch.setattr(controller, "_notify_supervisor", interrupted_before_notification)
        first = await controller.audit_stop("partial", reason="Persisted before the notification.")
        assert first.action == "wait_review"
        assert _reviewers(core, project.id) == []
        await bus.flush_snapshot()
        await core.aclose()

        restored = RuntimeCore(strict_events=True)
        restored.store = await asyncio.to_thread(RuntimeStore, tmp_path / "runtime.db")
        await asyncio.to_thread(restore_core, restored, restored.store)
        await reconcile_supervision(restored, project.id, auto_wake=False)
        assert _reviewers(restored, project.id) == [], "loading alone must not start a model"

        db = await asyncio.to_thread(lambda: ConversationDB(project.id).init())
        resumed = DagController(db, coordinator.id, "dag_guided",
            conversation_id=project.id, working_directory=tmp_path, core=restored)
        await resumed.initialize()
        retry = await resumed.audit_stop("partial")
        assert retry.action == "wait_review"
        assert retry.request_id == first.request_id
        reviewers = _reviewers(restored, project.id)
        assert len(reviewers) == 1, "resuming a committed request must repair a missing notification"
        assert reviewers[0].final_review_request_id == first.request_id
    finally:
        if restored is not None:
            await restored.aclose()
        await core.aclose()


@pytest.mark.asyncio
async def test_restore_does_not_blame_failed_process_supervisor_for_live_final_review(tmp_path):
    core, bus, project, coordinator, process, controller = await _setup(tmp_path, durable=True)
    restored = None
    try:
        gate = await controller.audit_stop("partial", reason="Final reviewer owns the only pending work.")
        assert gate.action == "wait_review"
        final = _reviewers(core, project.id)[0]
        await core.agent_host.wake(process)
        await core.agent_host.finish_run(process, outcome="failed", error="Process reviewer stopped.",
            failure_kind=RunFailureKind.PIPELINE_INTERNAL)
        await bus.flush_snapshot()
        await core.aclose()

        restored = RuntimeCore(strict_events=True)
        restored.store = await asyncio.to_thread(RuntimeStore, tmp_path / "runtime.db")
        await asyncio.to_thread(restore_core, restored, restored.store)
        await CommandBus(restored).execute(Command(type="agent.message", target={"session_id": final.id},
            payload={"content": "Resume the independent final review."}, actor="user"))
        await reconcile_supervision(restored, project.id, auto_wake=False)
        assert restored.agents[process.id].state is AgentState.FAILED
        assert restored.agents[final.id].state is AgentState.RUNNING
        assert restored.notices.pin_content(coordinator.id, TERMINAL_SUPERVISOR_PIN_KEY) is None
    finally:
        if restored is not None:
            await restored.aclose()
        await core.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize("request_state", ["superseded", "resolved"])
@pytest.mark.parametrize("entrypoint", ["notify", "reconcile"])
async def test_closed_final_request_clears_its_terminal_alert(tmp_path, request_state, entrypoint):
    core, _bus, project, coordinator, _process, controller = await _setup(tmp_path)
    try:
        gate = await controller.audit_stop("partial", reason="Current partial submission.")
        final = _reviewers(core, project.id)[0]
        await core.agent_host.finish_run(final, outcome="failed", error="Reviewer provider stopped.",
            failure_kind=RunFailureKind.PROVIDER_PERMANENT)
        await notify_supervisor(core, project.id, reason="The current final reviewer failed.")
        pin_key = f"{TERMINAL_SUPERVISOR_PIN_KEY}-{gate.request_id}"
        assert core.notices.pin_content(coordinator.id, pin_key) is not None

        if request_state == "superseded":
            await _queue_exit(controller, reason="Replacement partial submission.")
        else:
            request = await asyncio.to_thread(controller.store.get_review_request, gate.request_id)
            decision = ReviewDecision(request_id=request.request_id,
                basis_fingerprint=request.basis_fingerprint, verdict="needs_evidence",
                reason="The submitted partial result requires additional native evidence.")
            result = await asyncio.to_thread(controller.store.resolve_review, decision,
                expected_basis=request.basis_fingerprint)
            assert result["accepted"]
        closed = await asyncio.to_thread(controller.store.get_review_request, gate.request_id)
        assert closed.state == request_state

        if entrypoint == "notify":
            await notify_supervisor(core, project.id, reason="The exit review request changed.")
        else:
            await reconcile_supervision(core, project.id, auto_wake=False)
        assert core.notices.pin_content(coordinator.id, pin_key) is None
    finally:
        await core.aclose()


@pytest.mark.asyncio
async def test_wait_review_tracks_its_bound_reviewer_instead_of_the_process_supervisor(tmp_path):
    core, bus, project, coordinator, process, controller = await _setup(tmp_path)
    try:
        final = await _bound_reviewer(core, bus, project, coordinator, controller, reason="Current delivery.")
        await core.agent_host.transition(coordinator, AgentState.WAITING_APPROVAL, reason="wait_review")
        watcher = RunWatcher(stuck_grace_s=0.01, poll_interval_s=0.01)
        assert (await watcher.decide(core, coordinator)).kind == "continue"

        await _finish(core, final)
        await core.agent_host.wake(process)
        assert process.state is AgentState.RUNNING
        decision = await watcher.decide(core, coordinator)
        assert decision.kind == "cancel", "an active process Supervisor cannot mask a dead final reviewer"
        assert "no live supervisor" in decision.reason
    finally:
        await core.aclose()


@pytest.mark.asyncio
async def test_superseded_final_review_does_not_block_new_partial_submission(tmp_path):
    core, bus, project, coordinator, process, controller = await _setup(tmp_path)
    try:
        stale = await _bound_reviewer(core, bus, project, coordinator, controller, reason="Earlier delivery.")
        assert await asyncio.to_thread(has_running_siblings, core,
            project_id=project.id, session_id=coordinator.id)
        await _queue_exit(controller, reason="Replacement delivery.")
        await core.agent_host.wake(process)
        assert stale.state is AgentState.RUNNING
        assert process.state is AgentState.RUNNING
        assert not await asyncio.to_thread(has_running_siblings, core,
            project_id=project.id, session_id=coordinator.id)
        assert not await asyncio.to_thread(has_running_peers, core, coordinator)

        gate = await controller.audit_stop("partial", reason="Current delivery after replacing old material.")
        assert gate.action == "wait_review", "superseded review work must not park a fresh submission"
        current = next(agent for agent in _reviewers(core, project.id)
                       if agent.final_review_request_id == gate.request_id)
        assert current.id != stale.id
    finally:
        await core.aclose()


@pytest.mark.asyncio
async def test_process_supervisor_with_pending_scientific_work_still_blocks_delivery(tmp_path):
    core, _bus, project, coordinator, process, controller = await _setup(tmp_path)
    try:
        await asyncio.to_thread(_seed_call_review, project.id, coordinator.id)
        await core.agent_host.wake(process)
        assert await asyncio.to_thread(has_running_siblings, core,
            project_id=project.id, session_id=coordinator.id)
        assert await asyncio.to_thread(has_running_peers, core, coordinator)
        assert (await controller.audit_stop("partial", reason="Pending science review.")).action == "wait_background"
    finally:
        await core.aclose()


@pytest.mark.asyncio
async def test_wait_review_ignores_running_supervisor_for_a_superseded_exit(tmp_path):
    core, bus, project, coordinator, process, controller = await _setup(tmp_path)
    try:
        await _bound_reviewer(core, bus, project, coordinator, controller, reason="Earlier delivery.")
        await _queue_exit(controller, reason="Replacement without a live reviewer.")
        await core.agent_host.wake(process)
        await core.agent_host.transition(coordinator, AgentState.WAITING_APPROVAL, reason="wait_review")
        watcher = RunWatcher(stuck_grace_s=0.01, poll_interval_s=0.01)
        assert (await watcher.decide(core, coordinator)).kind == "cancel"
    finally:
        await core.aclose()


@pytest.mark.asyncio
async def test_hub_supervisor_alias_stays_on_process_context_but_explicit_id_is_respected(tmp_path):
    core, bus, project, coordinator, process, controller = await _setup(tmp_path)
    try:
        final = await _bound_reviewer(core, bus, project, coordinator, controller, reason="Current delivery.")
        alias = await handle_hub_tool(core, coordinator, ToolCall(id="hub-alias", name="agent_hub",
            arguments={"action": "call", "to": "@supervisor", "message": "New research observation."}))
        assert alias.is_success
        assert alias.data["session_id"] == process.id

        explicit = await handle_hub_tool(core, coordinator, ToolCall(id="hub-explicit", name="agent_hub",
            arguments={"action": "call", "to": final.id, "message": "Read this delivery clarification."}))
        assert explicit.is_success
        assert explicit.data["session_id"] == final.id
    finally:
        await core.aclose()
