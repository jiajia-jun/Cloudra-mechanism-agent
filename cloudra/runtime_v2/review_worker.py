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
from typing import Any, Callable

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
                # Notification delivery is independent of whether this project
                # is still in guided mode; a mode switch must not strand a verdict
                # already committed during the previous run.
                for item in await asyncio.to_thread(store.pending_review_notifications):
                    await self._notify(project_id, item["decision_id"])
            except Exception:
                logger.exception("review notification recovery failed for project %s", project_id)
                continue
            # Do not claim requests for projects whose production factory has
            # no Supervisor (e.g. standard/dag_record); otherwise the lease
            # would be held until expiry with no consumer.
            supervisor = self.supervisor_factory(project_id)
            if supervisor is None:
                continue
            try:
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
                await self._process_claimed(project_id, claimed, supervisor=supervisor)
            except Exception:
                logger.exception(
                    "review processing failed for project %s request %s",
                    project_id,
                    claimed.request.request_id,
                )

    async def _process_claimed(self, project_id: str, claimed: ClaimedReview, *, supervisor=None) -> None:
        renewal = asyncio.create_task(
            self._renew_claim(project_id, claimed),
            name=f"review-lease:{claimed.request.request_id}",
        )
        try:
            await self._process_claimed_once(project_id, claimed, supervisor=supervisor)
        finally:
            renewal.cancel()
            await asyncio.gather(renewal, return_exceptions=True)

    async def _renew_claim(self, project_id: str, claimed: ClaimedReview) -> None:
        interval = max(0.01, min(self.lease_seconds / 3, 30.0))
        while True:
            await asyncio.sleep(interval)
            store = self.store_factory(project_id)
            alive = await asyncio.to_thread(
                store.renew_review_claim,
                claimed.request.request_id,
                self.owner,
                claimed.claim_token,
                lease_seconds=self.lease_seconds,
            )
            if not alive:
                logger.warning("review lease lost for %s", claimed.request.request_id)
                return

    async def _process_claimed_once(self, project_id: str, claimed: ClaimedReview, *, supervisor=None) -> None:
        supervisor = supervisor or self.supervisor_factory(project_id)
        if supervisor is None:
            return
        review = getattr(supervisor, "review", None)
        if callable(review):
            decision = await review(claimed.request)
            if not isinstance(decision, ReviewDecision):
                decision = ReviewDecision.model_validate(decision)
            store = self.store_factory(project_id)
            current_basis = None
            if claimed.request.basis_fingerprint.startswith("sha256:"):
                current_basis = await asyncio.to_thread(store.review_basis, claimed.request)
            result = await asyncio.to_thread(
                store.resolve_review,
                decision,
                expected_basis=claimed.request.basis_fingerprint,
                claim_token=claimed.claim_token,
                current_basis=current_basis,
            )
            if result.get("accepted"):
                await self._notify(project_id, result["decision_id"])
            return
        run = getattr(supervisor, "run", None)
        if callable(run):
            await run(
                trigger="review_request",
                coordinator_request=(
                    f"request_id={claimed.request.request_id}\n"
                    f"request={claimed.request.model_dump_json()}"
                ),
                review_claim=claimed,
            )
            # GraphSupervisor resolves through dag_review_evidence when the
            # model calls it.  Deliver the durable notification after the run
            # instead of treating merely waking the Supervisor as a verdict.
            store = self.store_factory(project_id)
            for item in await asyncio.to_thread(store.pending_review_notifications):
                if item["request_id"] == claimed.request.request_id:
                    await self._notify(project_id, item["decision_id"])
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
                decision = await asyncio.to_thread(store.get_review_decision, decision_id)
                reason = decision.reason if decision is not None else ""
                next_action = decision.next_action if decision is not None else None
                content = (
                    f"[Supervisor review decision] decision_id={decision_id} "
                    f"request_id={item['request_id']} "
                    f"verdict={decision.verdict if decision is not None else 'unknown'} "
                    f"reason={reason} "
                    f"next_action={next_action or 'none'}"
                )
                agent = self.core.agents.get(recipient) if recipient else None
                # A cancelled user run must not be resurrected by a late
                # review decision.  Marking the durable notification sent is
                # still safe: the cancelled request has no live consumer.
                agent_state = getattr(getattr(agent, "state", None), "value", None)
                if recipient and agent_state != "cancelled":
                    before_events = len(self.core.event_log)
                    self.core.notices.pin(
                        recipient,
                        key=f"review-{decision_id}",
                        content=content,
                    )
                    # Mailbox delivery is the durable wake handshake.  If the
                    # decision races the transition into WAITING_APPROVAL,
                    # AgentRunner's post-transition inbox check observes it
                    # and wakes deterministically (no timing sleep).
                    self.core.mailbox.deliver(
                        to_session_id=recipient,
                        project_id=project_id,
                        content=content,
                        sender="supervisor",
                    )
                    if agent is not None:
                        self.core.agent_host.wake(agent, runner=self.core.runner)
                    # This path is outside CommandBus, so it owns the same
                    # publish+persist boundary explicitly.  Marking the
                    # notification sent before these events are durable would
                    # lose the wake across a crash.
                    for envelope in list(self.core.event_log)[before_events:]:
                        await self.core.event_hub.publish(envelope)
                        if self.core.store is not None:
                            await asyncio.to_thread(self.core.store.append_event, envelope)
                await asyncio.to_thread(
                    store.mark_review_notification_sent, decision_id
                )
        except Exception:
            logger.exception("review notification delivery failed for %s", project_id)
