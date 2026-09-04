"""Asynchronous per-project review worker (contract_version=2).

The worker is deliberately an ephemeral executor.  The authoritative queue is
the DAG review table in each project's ConversationDB; this class only claims
leased requests, asks a Supervisor to produce a ReviewDecision, and resolves
it through the store.

No in-memory request state is authoritative: after a crash the same request
can be claimed again once its lease expires.  Decision notifications are also
durable rows and are deduplicated by decision_id.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Awaitable, Callable

from cloudra.dag.review_requests import ClaimedReview, ReviewDecision

logger = logging.getLogger(__name__)


class ReviewWorker:
    """Per-project poller; call ``start()``/``await close()`` from the host.

    ``store_factory(project_id)`` returns the project's DagStore.
    ``supervisor_factory(project_id)`` returns a Supervisor-like object.  A
    supervisor may expose either:

    - ``async review(request) -> ReviewDecision | dict``
    - ``async run(trigger, coordinator_request=...)`` (GraphSupervisor style)

    For the second form the worker only records that the Supervisor has been
    woken; it does not fabricate a decision.
    """

    def __init__(
        self,
        *,
        core: Any,
        store_factory: Callable[[str], Any],
        supervisor_factory: Callable[[str], Any] | None = None,
        poll_interval: float = 0.05,
        owner: str = "review-worker",
        lease_seconds: int = 120,
    ) -> None:
        self.core = core
        self.store_factory = store_factory
        self.supervisor_factory = supervisor_factory or (
            lambda project_id: None
        )
        self.poll_interval = poll_interval
        self.owner = owner
        self.lease_seconds = lease_seconds
        self._task: asyncio.Task | None = None
        self._closing = asyncio.Event()

    async def start(self) -> None:
        if self._task is not None:
            return
        self._task = asyncio.create_task(self._loop(), name="dag-review-worker")

    async def close(self) -> None:
        self._closing.set()
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _loop(self) -> None:
        while not self._closing.is_set():
            try:
                await self._poll_once()
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("review worker poll failed")
            await asyncio.sleep(self.poll_interval)

    async def _poll_once(self) -> None:
        if self.supervisor_factory is None:
            return
        projects = list(getattr(self.core, "projects", {}).values())
        for project in projects:
            project_id = getattr(project, "id", None) or getattr(project, "project_id", None)
            if not project_id:
                continue
            try:
                store = self.store_factory(project_id)
                claimed = await asyncio.to_thread(
                    store.claim_review,
                    self.owner,
                    lease_seconds=self.lease_seconds,
                )
            except Exception:
                logger.exception("claim review failed for project %s", project_id)
                continue
            if claimed is None:
                continue
            try:
                await self._process_claimed(project_id, claimed)
            except Exception:
                logger.exception(
                    "review processing failed for project %s request %s",
                    project_id,
                    claimed.request.request_id,
                )

    async def _process_claimed(self, project_id: str, claimed: ClaimedReview) -> None:
        supervisor = self.supervisor_factory(project_id)
        if supervisor is None:
            return
        review = getattr(supervisor, "review", None)
        if callable(review):
            decision = await review(claimed.request)
            if not isinstance(decision, ReviewDecision):
                decision = ReviewDecision.model_validate(decision)
            store = self.store_factory(project_id)
            result = await asyncio.to_thread(
                store.resolve_review,
                decision,
                expected_basis=claimed.request.basis_fingerprint,
                claim_token=claimed.claim_token,
            )
            if result.get("accepted"):
                await self._notify(project_id, result["decision_id"])
            return
        run = getattr(supervisor, "run", None)
        if callable(run):
            await run(
                trigger="review_request",
                coordinator_request=claimed.request.question,
            )
            return
        logger.warning("supervisor factory returned an object without review/run")

    async def _notify(self, project_id: str, decision_id: str) -> None:
        """Deliver pending decision notifications via the core notice manager.

        The durable row remains pending until the host has actually put the
        decision into the recipient's context; in this default implementation
        we mark it sent after emitting a notice pin.  Hosts may override by
        using ``pending_review_notifications`` directly.
        """
        try:
            store = self.store_factory(project_id)
            notifications = await asyncio.to_thread(
                store.pending_review_notifications
            )
            for item in notifications:
                if item["decision_id"] != decision_id:
                    continue
                recipient = item["recipient_session_id"]
                if recipient:
                    self.core.notices.pin(
                        recipient,
                        key=f"review-{decision_id}",
                        content=(
                            f"[Supervisor review decision] {decision_id} "
                            f"request {item['request_id']} resolved"
                        ),
                    )
                await asyncio.to_thread(
                    store.mark_review_notification_sent, decision_id
                )
        except Exception:
            logger.exception("review notification delivery failed for %s", project_id)
