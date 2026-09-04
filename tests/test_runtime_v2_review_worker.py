"""Task 7: async review worker lease processing."""

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from cloudra.core.supervisor import GraphSupervisor
from cloudra.dag.models import OrchestrationMode
from cloudra.dag.review_requests import ReviewDecision, ReviewRequest
from cloudra.dag.store import DagStore
from cloudra.infra.config import get_config
from cloudra.persistence.database import ConversationDB
from cloudra.runtime_v2.agent_runner import AgentRunner
from cloudra.runtime_v2.commands import CommandBus
from cloudra.runtime_v2.core import RuntimeCore
from cloudra.runtime_v2.persistence import RuntimeStore
from cloudra.runtime_v2.policies import default_stages
from cloudra.runtime_v2.policies.base import ToolCall, ToolResult
from cloudra.runtime_v2.review_worker import ReviewWorker
from cloudra.runtime_v2.schemas import Command
from cloudra.runtime_v2.turn_pipeline import LLMResponse, TurnPipeline


class FakeSupervisor:
    def __init__(self, verdict="accept", reason="ok"):
        self.verdict = verdict
        self.reason = reason

    async def review(self, request: ReviewRequest) -> ReviewDecision:
        return ReviewDecision(
            request_id=request.request_id,
            basis_fingerprint=request.basis_fingerprint,
            verdict=self.verdict,
            reason=self.reason,
            next_action=None if self.verdict == "accept" else "add missing evidence",
        )


async def _core_project(tmp_path, conversation_id):
    core = RuntimeCore(strict_events=True)
    bus = CommandBus(core)
    project = (
        await bus.execute(
            Command(
                type="project.create",
                payload={"name": conversation_id, "workspace_dir": str(tmp_path)},
            )
        )
    ).data
    return core, project


def _store_factory(tmp_path, conversation_id):
    def factory(project_id):
        db = ConversationDB(project_id, data_dir=tmp_path).init()
        store = DagStore(db)
        store.ensure_bundle("s1")
        return store

    return factory


def _enqueue_request(tmp_path, conversation_id):
    store = _store_factory(tmp_path, conversation_id)(conversation_id)
    request_id = store.enqueue_review(
        ReviewRequest(
            kind="evidence",
            requester="coordinator",
            target_ids=["step1"],
            question="check identity mismatch",
            basis_fingerprint="basis-1",
        )
    )
    return request_id


@pytest.mark.asyncio
async def test_review_worker_processes_one_request_and_resolves(tmp_path):
    conversation_id = "worker-test"
    core, project = await _core_project(tmp_path, conversation_id)
    project_id = project.id
    _enqueue_request(tmp_path, project_id)
    store_factory = _store_factory(tmp_path, conversation_id)
    worker = ReviewWorker(
        core=core,
        store_factory=store_factory,
        supervisor_factory=lambda pid: FakeSupervisor(),
        poll_interval=0.01,
    )
    await worker.start()
    # Give the worker a chance to claim/process.
    for _ in range(20):
        await asyncio.sleep(0.02)
        if not store_factory(project_id).list_review_requests(state="queued"):
            break
    await worker.close()

    store = store_factory(project_id)
    assert store.list_review_requests(state="queued") == []
    assert store.list_review_requests(state="resolved")


@pytest.mark.asyncio
async def test_worker_real_graph_supervisor_resolves_claimed_request(tmp_path):
    """The production worker path must carry its lease into the DAG tool.

    This intentionally uses GraphSupervisor.run (with only its external LLM
    call replaced), rather than a detached ``review(request)`` helper.
    """
    get_config().data_dir = tmp_path
    core, project = await _core_project(tmp_path, "real-worker")
    project.settings.orchestration_mode = OrchestrationMode.DAG_GUIDED
    project_id = project.id
    store = _store_factory(tmp_path, project_id)(project_id)
    request = ReviewRequest(
        request_id="real-req",
        kind="evidence",
        requester="s1",
        target_ids=[],
        question="verify the evidence",
        basis_fingerprint="sha256:pending",
    )
    request = request.model_copy(update={"basis_fingerprint": store.review_basis(request)})
    store.enqueue_review(request)
    supervisor = GraphSupervisor(
        conversation_id=project_id,
        project_id=project_id,
        working_directory=str(tmp_path),
        core=core,
    )
    def call():
        return SimpleNamespace(
            model_dump=lambda exclude_none=False: {
                "id": "review-call",
                "type": "function",
                "function": {
                    "name": "dag_review_evidence",
                    "arguments": json.dumps({
                        "request_id": "real-req",
                        "verdict": "accept",
                        "reason": "evidence is sufficient",
                        "findings": [],
                    }),
                },
            }
        )
    supervisor._ensure_agent()
    object.__setattr__(
        supervisor._agent,
        "llm_call",
        AsyncMock(side_effect=[
            SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="", tool_calls=[call()]))]),
            SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="resolved", tool_calls=None))]),
        ]),
    )
    worker = ReviewWorker(
        core=core,
        store_factory=lambda _pid: store,
        supervisor_factory=lambda _pid: supervisor,
        poll_interval=0.01,
    )
    await worker.start()
    for _ in range(100):
        await asyncio.sleep(0.01)
        if store.get_review_request("real-req").state == "resolved":
            break
    await worker.close()
    assert store.get_review_request("real-req").state == "resolved"


@pytest.mark.asyncio
async def test_expired_review_claim_cannot_resolve(tmp_path):
    conversation_id = "expired-review"
    core, project = await _core_project(tmp_path, conversation_id)
    store = _store_factory(tmp_path, conversation_id)(project.id)
    request_id = _enqueue_request(tmp_path, project.id)
    claimed = store.claim_review("worker-a", lease_seconds=1)
    assert claimed is not None
    with store.db.connect() as con:
        con.execute(
            "UPDATE dag_review_requests SET lease_expires_at='2000-01-01T00:00:00+00:00' WHERE request_id=?",
            (request_id,),
        )
    decision = ReviewDecision(
        request_id=request_id,
        basis_fingerprint="basis-1",
        verdict="accept",
        reason="ok",
    )
    result = store.resolve_review(
        decision,
        expected_basis="basis-1",
        claim_token=claimed.claim_token,
    )
    assert result["accepted"] is False
    assert result["rejection_code"] == "stale_claim"


@pytest.mark.asyncio
async def test_long_review_renews_lease_before_resolving(tmp_path):
    class SlowSupervisor(FakeSupervisor):
        async def review(self, request):
            await asyncio.sleep(0.12)
            return await super().review(request)

    conversation_id = "renew-review"
    core, project = await _core_project(tmp_path, conversation_id)
    _enqueue_request(tmp_path, project.id)
    store_factory = _store_factory(tmp_path, conversation_id)
    worker = ReviewWorker(
        core=core,
        store_factory=store_factory,
        supervisor_factory=lambda _pid: SlowSupervisor(),
        poll_interval=0.01,
        lease_seconds=0.05,
    )
    await worker.start()
    for _ in range(80):
        await asyncio.sleep(0.01)
        if store_factory(project.id).list_review_requests(state="resolved"):
            break
    await worker.close()
    assert store_factory(project.id).list_review_requests(state="resolved")


@pytest.mark.asyncio
async def test_pending_notification_recovery_persists_wake_and_details(tmp_path):
    """A resolved row with only a pending notification survives the crash window."""
    conversation_id = "notification-recovery"
    core = RuntimeCore(strict_events=True)
    core.store = RuntimeStore(tmp_path / "runtime.db")
    bus = CommandBus(core)
    project = (await bus.execute(Command(
        type="project.create", payload={"name": conversation_id, "workspace_dir": str(tmp_path)}
    ))).data
    agent = (await bus.execute(Command(
        type="agent.spawn", target={"project_id": project.id}, payload={"role_id": "coordinator"}
    ))).data
    store = _store_factory(tmp_path, project.id)(project.id)
    request = ReviewRequest(
        request_id="recovery-request",
        kind="evidence",
        requester=agent.id,
        target_ids=["step1"],
        question="recover notification",
        basis_fingerprint="basis-recovery",
    )
    store.enqueue_review(request)
    claimed = store.claim_review("worker-a", lease_seconds=30)
    decision = ReviewDecision(
        decision_id="decision-recovery",
        request_id=request.request_id,
        basis_fingerprint=request.basis_fingerprint,
        verdict="reject",
        reason="Missing evidence",
        next_action="Inspect existing log",
    )
    assert store.resolve_review(
        decision,
        expected_basis=request.basis_fingerprint,
        claim_token=claimed.claim_token,
    )["accepted"]
    worker = ReviewWorker(
        core=core,
        store_factory=lambda _pid: store,
        supervisor_factory=lambda _pid: FakeSupervisor(),
    )
    await worker._poll_once()
    assert store.pending_review_notifications() == []
    persisted = core.store.query_project_events(project.id)
    assert any(
        row["type"] == "agent.message_injected"
        and "verdict=reject" in json.loads(row["data"])["content"]
        and "next_action=Inspect existing log" in json.loads(row["data"])["content"]
        for row in persisted
    )


@pytest.mark.asyncio
async def test_real_runner_waits_then_finishes_after_worker_approval(tmp_path):
    """Coordinator, DAG stage, runner, and worker form one approval loop."""
    get_config().data_dir = tmp_path
    core = RuntimeCore(strict_events=True)

    class ApprovalLLM:
        def __init__(self):
            self.calls = 0

        async def complete(self, agent, messages, tools, **_kwargs):
            self.calls += 1
            approval_id = "decision-runtime" if self.calls > 1 else None
            return LLMResponse(
                tool_calls=[ToolCall(
                    id=f"stop-{self.calls}",
                    name="stop",
                    arguments={"delivery_disposition": "partial", **(
                        {"approval_id": approval_id} if approval_id else {}
                    )},
                )]
            )

    class StopTools:
        async def execute(self, agent, call):
            return ToolResult(is_success=True, summary="stopped")

    llm = ApprovalLLM()
    pipeline = TurnPipeline(
        event_log=core.event_log,
        stages=default_stages(core),
        llm=llm,
        tools=StopTools(),
    )
    async def summarize(_messages):
        return "[RUN LOG]\nstub"

    core.runner = AgentRunner(core, pipeline, run_summarizer=summarize)
    bus = CommandBus(core)
    project = (await bus.execute(Command(
        type="project.create",
        payload={
            "name": "runtime approval",
            "workspace_dir": str(tmp_path),
            "settings": {"orchestration_mode": "dag_guided"},
        },
    ))).data
    agent = (await bus.execute(Command(
        type="agent.spawn",
        target={"project_id": project.id},
        payload={"role_id": "coordinator"},
    ))).data
    await bus.execute(Command(
        type="agent.settings_update",
        target={"session_id": agent.id},
        payload={"orchestration_mode": "dag_guided"},
    ))
    await bus.execute(Command(
        type="agent.message",
        target={"session_id": agent.id},
        payload={"content": "deliver partial"},
    ))
    store_factory = _store_factory(tmp_path, project.id)
    worker = ReviewWorker(
        core=core,
        store_factory=store_factory,
        supervisor_factory=lambda _pid: FakeSupervisor(),
        poll_interval=0.01,
    )
    await worker.start()
    for _ in range(300):
        await asyncio.sleep(0.01)
        if agent.state.value == "succeeded":
            break
    await worker.close()
    assert agent.state.value == "succeeded"
    assert llm.calls >= 2
    assert store_factory(project.id).list_review_requests(state="resolved")
