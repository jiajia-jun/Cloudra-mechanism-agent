"""Approved result metadata is independent of visible conversation replies."""

import asyncio
from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient

from cloudra.dag.stop_audit import StopGate
from cloudra.runtime_v2.agent_runner import AgentRunner
from cloudra.runtime_v2.child_manifest import build_child_manifest
from cloudra.runtime_v2.core import RuntimeCore
from cloudra.runtime_v2.peer_completion import peer_completion_message
from cloudra.runtime_v2.schemas import AgentSession, AgentState, Command, Project
from cloudra.services.api_v2 import create_v2_app
from cloudra.services.api_v2.routers.tasks import _outcome
from tests.agent_scenarios import ScenarioHarness, ScriptedProvider, Step, frozen_exit_confirmation_steps


def _runtime(gate):
    core = RuntimeCore(strict_events=True)
    core.projects["p"] = Project(id="p", name="Results")
    parent = AgentSession(id="parent", project_id="p", role_id="coordinator", display_name="Parent")
    agent = AgentSession(id="a", project_id="p", role_id="explorer", display_name="Worker",
                         requested_by_session_id=parent.id)
    core.agents.update({parent.id: parent, agent.id: agent})
    for session in (parent, agent):
        core.mailbox.ensure_inbox(session.id)

    class GateStage:
        name = "test_completion_result"

        async def audit_run_end(self, _ctx, **_kwargs):
            return gate

    runner = AgentRunner(core, SimpleNamespace(stages=[GateStage()], _emitter=lambda *_args: None))
    return core, agent, runner


@pytest.mark.asyncio
async def test_api_returns_candidate_committed_before_its_completion_gate():
    core, agent, runner = _runtime(StopGate(action="allow_final", basis="declared"))
    run_id = await core.agent_host.start_run(agent)
    candidate = "actual-candidate-marker"
    await core.contexts.emit_assistant(agent=agent, run_id=run_id, content=candidate)
    await runner._evaluate_completion_gate(
        agent, run_id, explicit_stop=False, stop_arguments=None, candidate_answer=candidate,
    )
    await core.agent_host.finish_run(agent, outcome="succeeded")

    async with AsyncClient(transport=ASGITransport(app=create_v2_app(core)), base_url="http://testserver") as client:
        result = (await client.get("/api/v2/projects/p/agents/a/result")).json()
    assert result["result"]["summary"] == candidate
    events = core.event_log.query_session(agent.id)
    replies = [event for event in events if event.type == "agent.message_emitted"]
    gate = next(event for event in events if event.type == "agent.completion_gate")
    assert len(replies) == 1 and replies[0].session_seq < gate.session_seq
    assert gate.data["final_answer"] == candidate


@pytest.mark.asyncio
async def test_approved_empty_answer_does_not_upgrade_visible_narration_to_a_result():
    core, agent, runner = _runtime(StopGate(action="allow_final", final_answer="", basis="supervisor_approved"))
    run_id = await core.agent_host.start_run(agent)
    narration = "unreviewed-narration-marker"
    await core.contexts.emit_assistant(agent=agent, run_id=run_id, content=narration)
    await runner._evaluate_completion_gate(
        agent, run_id, explicit_stop=True, stop_arguments={}, candidate_answer=narration,
    )
    await core.agent_host.finish_run(agent, outcome="succeeded")

    assert build_child_manifest(core, agent)["final_summary"] == ""
    assert peer_completion_message(core, agent)[2]["final_summary"] == ""
    result = await asyncio.to_thread(_outcome, core, agent, core.event_log.high_session_watermarks[agent.id])
    assert result["result"]["summary"] == ""
    replies = core.event_log.query_session(agent.id, types={"agent.message_emitted"})
    assert [event.data["content"] for event in replies] == [narration]
    assert [item["content"] for item in core.contexts.current_messages(agent.id)] == [narration]


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
        assert gate.data["final_answer"] == frozen
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
