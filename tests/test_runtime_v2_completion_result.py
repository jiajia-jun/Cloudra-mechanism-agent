"""Completion identity refers to a real reply without changing the conversation."""

import asyncio
from types import SimpleNamespace

import pytest

from cloudra.dag.stop_audit import StopGate
from cloudra.runtime_v2.agent_runner import AgentRunner
from cloudra.runtime_v2.child_manifest import build_child_manifest
from cloudra.runtime_v2.core import RuntimeCore
from cloudra.runtime_v2.failures import RunFailureKind
from cloudra.runtime_v2.peer_completion import PeerCompletionIndex, peer_completion_message
from cloudra.runtime_v2.schemas import AgentSession, AgentState, Command, Project
from cloudra.services.api_v2.routers.tasks import _outcome
from tests.agent_scenarios import ScenarioHarness, ScriptedProvider, Step, frozen_exit_confirmation_steps


class _GateStage:
    name = "test_completion_identity"

    def __init__(self, verdict):
        self.verdict = verdict

    async def audit_run_end(self, _ctx, **_kwargs):
        return self.verdict


def _runtime(kind="child"):
    core = RuntimeCore(strict_events=True)
    core.projects["p"] = Project(id="p", name="Results")
    parent = AgentSession(id="parent", project_id="p", role_id="coordinator", display_name="Parent")
    agent = AgentSession(
        id="a", project_id="p", role_id="explorer", display_name="Worker",
        parent_session_id=parent.id if kind == "child" else None,
        requested_by_session_id=parent.id if kind == "peer" else None,
    )
    core.agents.update({parent.id: parent, agent.id: agent})
    for session in (parent, agent):
        core.mailbox.ensure_inbox(session.id)
    stage = _GateStage(StopGate(action="allow_final", basis="declared"))
    runner = AgentRunner(core, SimpleNamespace(stages=[stage], _emitter=lambda *_args: None))
    return core, agent, runner, stage


async def _reply(core, agent, run_id, content):
    await core.contexts.emit_assistant(agent=agent, run_id=run_id, content=content)
    return core.event_log.query_session(agent.id, types={"agent.message_emitted"}, limit=1)[0]


async def _gate(core, agent, runner, run_id, candidate):
    await runner._evaluate_completion_gate(
        agent, run_id, explicit_stop=True, stop_arguments={}, candidate_answer=candidate,
    )
    await core.event_writer.flush()
    return core.event_log.query_session(agent.id, types={"agent.completion_gate"}, limit=1)[0]


@pytest.mark.asyncio
async def test_candidate_result_uses_existing_pre_gate_reply_for_api_summary():
    core, agent, runner, _stage = _runtime()
    run_id = await core.agent_host.start_run(agent)
    reply = await _reply(core, agent, run_id, "actual candidate")
    gate = await _gate(core, agent, runner, run_id, "actual candidate")
    await core.agent_host.finish_run(agent, outcome="succeeded")

    assert gate.data.get("result_message_id") == reply.event_id
    result = _outcome(core, agent, core.event_log.high_session_watermarks[agent.id])
    assert result["result"]["summary"] == reply.data["content"]
    assert len(core.event_log.query_session(agent.id, types={"agent.message_emitted"})) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["child", "peer"])
@pytest.mark.parametrize("repeat_text", [False, True])
async def test_frozen_reviewed_reply_stays_result_when_new_reply_is_visible(kind, repeat_text):
    core, agent, runner, stage = _runtime(kind)
    run_id = await core.agent_host.start_run(agent)
    accepted = await _reply(core, agent, run_id, "frozen reviewed answer")
    stage.verdict = StopGate(action="wait_review", request_id="review")
    await _gate(core, agent, runner, run_id, accepted.data["content"])
    # A newer user instruction requires a genuine new reply after acceptance.
    # The later reply remains visible, even when it repeats the reviewed text.
    newer = await _reply(
        core, agent, run_id, accepted.data["content"] if repeat_text else "new unreviewed narration",
    )
    stage.verdict = StopGate(
        action="allow_final", request_id="review", basis="supervisor_approved",
        final_answer=accepted.data["content"],
    )
    gate = await _gate(core, agent, runner, run_id, newer.data["content"])
    await core.agent_host.finish_run(agent, outcome="succeeded")

    assert gate.data.get("result_message_id") == accepted.event_id
    manifest = build_child_manifest(core, agent)
    assert manifest["final_summary"] == accepted.data["content"]
    if kind == "peer":
        restored = PeerCompletionIndex()
        restored.restore(core.peer_completions.snapshot())
        report = peer_completion_message(core, agent, index=restored)
        assert report[2]["final_summary"] == accepted.data["content"]
    visible = core.event_log.query_session(agent.id, types={"agent.message_emitted"})
    assert [event.event_id for event in visible] == [accepted.event_id, newer.event_id]
    context = [item["content"] for item in core.contexts.current_messages(agent.id)]
    assert context == [accepted.data["content"], newer.data["content"]]


@pytest.mark.asyncio
async def test_frozen_reply_can_belong_to_reviewed_submission_in_earlier_run():
    core, agent, runner, stage = _runtime("standalone")
    old_run = await core.agent_host.start_run(agent)
    accepted = await _reply(core, agent, old_run, "reviewed before restart")
    stage.verdict = StopGate(action="wait_review", request_id="review")
    await _gate(core, agent, runner, old_run, accepted.data["content"])
    await core.agent_host.finish_run(
        agent, outcome="failed", failure_kind=RunFailureKind.RUNTIME_INTERRUPTED,
    )
    await core.agent_host.wake(agent)
    run_id = agent.current_run.run_id
    newer = await _reply(core, agent, run_id, "confirmation after restart")
    stage.verdict = StopGate(
        action="allow_final", request_id="review", basis="supervisor_approved",
        final_answer=accepted.data["content"],
    )
    gate = await _gate(core, agent, runner, run_id, newer.data["content"])
    await core.agent_host.finish_run(agent, outcome="succeeded")

    assert gate.data.get("result_message_id") == accepted.event_id
    assert gate.run_id != accepted.run_id
    assert build_child_manifest(core, agent)["final_summary"] == accepted.data["content"]
    result = _outcome(core, agent, core.event_log.high_session_watermarks[agent.id])
    assert result["result"]["summary"] == accepted.data["content"]


@pytest.mark.asyncio
@pytest.mark.parametrize("mismatch", ["project", "session", "run", "type", "sender", "content"])
async def test_candidate_does_not_bind_an_event_outside_its_actual_reply(mismatch):
    core, agent, runner, _stage = _runtime()
    run_id = await core.agent_host.start_run(agent)
    fields = {"project_id": agent.project_id, "session_id": agent.id, "run_id": run_id}
    data = {"sender": agent.role_id, "content": "candidate"}
    event_type = "agent.message_emitted"
    if mismatch in {"project", "session", "run"}:
        fields[mismatch + "_id"] = "different"
    elif mismatch == "type":
        event_type = "agent.thinking"
    else:
        data[mismatch] = "different"
    core.event_log.append(event_type, stream="agent", **fields, data=data)
    gate = await _gate(core, agent, runner, run_id, "candidate")
    assert "result_message_id" in gate.data
    assert gate.data["result_message_id"] is None


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["child", "peer"])
@pytest.mark.parametrize("invalid", ["missing", "project", "session", "type", "future", "unbound"])
async def test_success_reports_do_not_guess_a_summary_without_a_valid_reference(kind, invalid):
    core, agent, _runner, _stage = _runtime(kind)
    run_id = await core.agent_host.start_run(agent)
    fields = {"project_id": agent.project_id, "session_id": agent.id, "run_id": run_id}
    if invalid in {"project", "session"}:
        fields[invalid + "_id"] = "different"
    reply = core.event_log.append(
        "agent.thinking" if invalid == "type" else "agent.message_emitted",
        stream="agent", **fields, data={"sender": agent.role_id, "content": "visible narration"},
    )
    data = {"action": "allow_final", "basis": "declared"}
    if invalid != "unbound":
        data["result_message_id"] = "missing" if invalid == "missing" else reply.event_id
    gate = core.event_log.append(
        "agent.completion_gate", stream="agent", project_id=agent.project_id,
        session_id=agent.id, run_id=run_id, data=data,
    )
    if invalid == "future":
        future = core.event_log.append(
            "agent.message_emitted", stream="agent", project_id=agent.project_id,
            session_id=agent.id, run_id=run_id, data={"content": "late narration"},
        )
        gate.data["result_message_id"] = future.event_id
    await core.agent_host.finish_run(agent, outcome="succeeded")

    manifest = build_child_manifest(core, agent)
    assert manifest["final_summary_source"] != "message"
    assert "no bound completion message" in manifest["final_summary"]
    assert core.event_log.get(reply.event_id) is reply
    assert _outcome(core, agent, core.event_log.high_session_watermarks[agent.id])["result"]["summary"] is None
    if kind == "peer":
        report = peer_completion_message(core, agent)[2]
        assert report["final_summary_source"] == "terminal_state"
        assert "no bound completion message" in report["final_summary"]


@pytest.mark.asyncio
async def test_guided_peer_keeps_accepted_result_when_new_user_message_requires_a_reply(tmp_path, monkeypatch):
    """Real review tools, dispatch, runner and durable peer reporting share one result identity."""
    from cloudra.dag.store import DagStore
    from cloudra.persistence.database import ConversationDB
    from cloudra.runtime_v2.dispatcher import WakePolicy

    frozen, newer = "reviewed-result-marker", "new-user-acknowledgement-marker"
    review_ready = asyncio.Event()
    review = Step(wait_for=review_ready)
    scripts = frozen_exit_confirmation_steps(review, Step(text=newer, tools=[("stop", {
        "delivery_disposition": "partial", "reason": "", "final_answer": "",
    })]), answer=frozen)
    provider = ScriptedProvider(by_role=scripts)
    harness = await ScenarioHarness.start(tmp_path, provider=provider, workspace_dir=tmp_path)
    try:
        await harness.bus.execute(Command(type="role.update", target={"role_id": "supervisor"},
            payload={"default_settings": {
                "orchestration_mode": "dag_guided", "invocation_protocol": "traditional",
            }}))
        requester = (await harness.bus.execute(Command(type="agent.spawn",
            target={"project_id": harness.project.id}, payload={"role_id": "researcher"}))).data
        await harness.bus.execute(Command(type="agent.cancel", target={"session_id": requester.id}))
        peer = (await harness.bus.execute(Command(type="agent.spawn",
            target={"project_id": harness.project.id}, payload={
                "role_id": "coordinator", "query": "Report the observed evidence.",
                "requested_by_session_id": requester.id,
                "settings": {"orchestration_mode": "dag_guided", "invocation_protocol": "traditional"},
            }))).data
        await harness.wait_for(lambda: peer.state is AgentState.WAITING_APPROVAL, "peer awaiting final review")
        requests = await asyncio.to_thread(lambda: DagStore(ConversationDB(harness.project.id)).list_review_requests())
        request = next(item for item in requests if item.kind == "exit" and item.requester == peer.id)
        original_deliver = harness.core.dispatcher.commit_and_deliver

        async def deliver_with_new_user_message(*args, **kwargs):
            manifest = kwargs.get("manifest") or {}
            if kwargs.get("to_session_id") == peer.id and manifest.get("kind") == "exit_review_decision":
                receipt = await original_deliver(*args, **{**kwargs, "wake": WakePolicy.NEVER})
                await harness.bus.execute(Command(type="agent.message", actor="user",
                    target={"session_id": peer.id}, payload={"content": "Please acknowledge receipt."}))
                return receipt
            return await original_deliver(*args, **kwargs)

        monkeypatch.setattr(harness.core.dispatcher, "commit_and_deliver", deliver_with_new_user_message)
        review.tools = [
            ("dag_view_evidence", {"review_id": request.request_id}),
            ("dag_review_evidence", {"request_id": request.request_id, "verdict": "accept",
                "reason": "The partial delivery accurately records its evidence limits."}),
        ]
        review_ready.set()
        await harness.wait_terminal(peer)

        def reports():
            return [event for event in harness.events(requester)
                    if (event.data.get("manifest") or {}).get("kind") == "peer_call_completion"]

        await harness.wait_for(lambda: bool(reports()), "durable peer completion")
        events = harness.events(peer)
        visible = [event for event in events if event.type == "agent.message_emitted"]
        gate = [event for event in events if event.type == "agent.completion_gate"][-1]
        assert peer.state is AgentState.SUCCEEDED
        assert [event.data["content"] for event in visible] == [frozen, newer]
        assert gate.data["result_message_id"] == visible[0].event_id
        assert gate.data["request_id"] == request.request_id
        assert provider.call_count("coordinator") == 2
        assert build_child_manifest(harness.core, peer)["final_summary"] == frozen
        assert reports()[0].data["manifest"]["final_summary"] == frozen
        result = await asyncio.to_thread(
            _outcome, harness.core, peer, harness.core.event_log.high_session_watermarks[peer.id],
        )
        assert result["result"]["summary"] == frozen
        assert [message["content"] for message in harness.core.contexts.current_messages(peer.id)
                if message["role"] == "assistant" and message.get("content")] == [frozen, newer]
    finally:
        review_ready.set()
        await harness.aclose()
