"""Task 7: async review worker lease processing."""

import asyncio

import pytest

from cloudra.dag.models import GraphRef
from cloudra.dag.review_requests import ReviewDecision, ReviewRequest
from cloudra.dag.store import DagStore
from cloudra.persistence.database import ConversationDB
from cloudra.runtime_v2.commands import CommandBus
from cloudra.runtime_v2.core import RuntimeCore
from cloudra.runtime_v2.review_worker import ReviewWorker
from cloudra.runtime_v2.schemas import Command


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
