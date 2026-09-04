"""Stop-time delivery coverage audit, approvals, and scientific-outcome separation."""

from __future__ import annotations

import asyncio
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from cloudra.dag.models import OrchestrationMode
from cloudra.dag.review_requests import ReviewRequest

StopAction = Literal[
    "allow_final",
    "wait_background",
    "wait_review",
    "needs_work",
]


class StopGate(BaseModel):
    """Deterministic result of a delivery stop audit.

    - allow_final: the run may finish and the disposition is recorded.
    - wait_background: the stop is a suspension because background work is
      still active; no delivery disposition is recorded.
    - wait_review: a Supervisor/approval is required before this disposition
      may be recorded.
    - needs_work: the stop is blocked until concrete gaps are resolved or a
      required approval/scope change is granted.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    action: StopAction
    report: Any = None
    request_id: str | None = None
    reason: str = Field(default="", description="Human-readable audit reason.")


class StopAuditMixin:
    """stop 交付门禁（audit_stop）与未审计 partial 落账；由 DagController 组合。"""

    async def _has_pending_background(self) -> bool:
        """会话级后台是否还有未竟工作（子任务/计算/定时提醒）。

        与 runner._count_pending_tasks 同一判定口径：只要后台未排空，
        stop 就是"挂起等唤醒"而不是交付。D8.2：子 agent 与提醒读
        v2-native 信号（core.agents 投影 + ReminderBroker 事件投影）——
        旧 scheduled_reminders/subagent_requests 表已删除，不存在遗留盲区；
        compute_jobs 仍是权威，但已迁到中央 compute.db（按 conversation_id 过滤本会话）。
        """
        from cloudra.persistence.database import ComputeDB
        from cloudra.services.compute_store import acount_pending_compute_jobs

        if await acount_pending_compute_jobs(
            ComputeDB(data_dir=self.db.data_dir), self.conversation_id
        ):
            return True
        core = self._core
        if core is None:
            return False
        terminal = {"succeeded", "failed", "cancelled"}
        if any(
            agent.id != self.session_id
            and agent.project_id == self.conversation_id
            and agent.state.value not in terminal
            for agent in core.agents.values()
        ):
            return True
        return bool(core.reminders.pending(self.session_id))

    async def record_unaudited_partial(self) -> None:
        """D8.3：非 stop 的运行结束（最终消息路径）自动落 partial。

        complete 只能来自被审计的显式 stop；只对 Coordinator（a-0）记录，
        子 agent 的运行结束不构成交付。
        """
        if not self.enabled or self.agent_id != "a-0":
            return
        await self.initialize()
        report = await asyncio.to_thread(self.delivery_report)
        await asyncio.to_thread(
            self.store.record_delivery_disposition,
            self.session_id,
            "partial",
            report,
        )

    async def audit_stop(
        self,
        disposition: str,
        *,
        approval_id: str | None = None,
        user_stop_event_id: str | None = None,
    ) -> StopGate:
        """Audit an explicit stop and return a :class:`StopGate`.

        Legacy callers that previously unpacked a tuple should use
        ``gate.action``/``gate.report`` instead.  The delivery disposition is
        recorded only when ``action == allow_final``.
        """
        if not self.enabled:
            return StopGate(action="allow_final", report=None)
        await self.initialize()

        # A real user termination is allowed regardless of graph coverage, but
        # the model must not be able to invent that source.
        if disposition == "user_terminated":
            event = self._core.event_log.get(user_stop_event_id) if self._core is not None and user_stop_event_id else None
            if (
                event is None
                or event.type != "agent.cancel_requested"
                or event.data.get("actor") != "user"
                or event.session_id != self.session_id
                or event.project_id != self.conversation_id
            ):
                return StopGate(
                    action="needs_work",
                    report=None,
                    reason=(
                        "user_terminated requires a real user stop event id; "
                        "a model cannot self-declare user termination"
                    ),
                )
            await asyncio.to_thread(
                self.store.record_delivery_disposition,
                self.session_id,
                disposition,
                None,
            )
            return StopGate(action="allow_final", report=None)

        if await self._has_pending_background():
            return StopGate(
                action="wait_background",
                report=None,
                reason="background work is still pending; stop only suspends",
            )

        report = self.delivery_report()
        if disposition == "complete" and report.complete:
            await asyncio.to_thread(
                self.store.record_delivery_disposition,
                self.session_id,
                disposition,
                report,
            )
            return StopGate(
                action="allow_final",
                report=report,
                reason="coverage audit passed",
            )

        if disposition == "complete":
            # Complete with gaps requires a review/approval path.  In guided
            # mode give the Supervisor one pre-delivery chance; otherwise block.
            if self.mode is OrchestrationMode.DAG_GUIDED and approval_id is None:
                await self.maybe_supervise("pre_delivery")
                report = self.delivery_report()
                if report.complete:
                    await asyncio.to_thread(
                        self.store.record_delivery_disposition,
                        self.session_id,
                        disposition,
                        report,
                    )
                    return StopGate(
                        action="allow_final",
                        report=report,
                        reason="coverage became complete after pre-delivery review",
                    )
                return StopGate(
                    action="needs_work",
                    report=report,
                    reason="complete was declared but required coverage is still missing",
                )
            # A Supervisor cannot waive deterministic completeness.  An exit
            # approval may authorize partial/method-limited scope only.
            return StopGate(
                action="needs_work",
                report=report,
                reason="complete was declared but required coverage is missing",
            )

        # partial without approval in dag_guided must wait for a Supervisor
        # decision; in dag_record partial is the ordinary unaudited stop.
        if disposition == "partial":
            if self.mode is OrchestrationMode.DAG_GUIDED:
                if approval_id is not None:
                    if not await self._valid_exit_approval(approval_id, disposition, report):
                        request_id = await self._enqueue_exit_review(disposition, report)
                        reused = await self._reused_exit_review(request_id, disposition, report)
                        if reused is not None:
                            return reused
                        return StopGate(
                            action="wait_review",
                            report=report,
                            request_id=request_id,
                            reason="approval is missing, stale, out of scope, or not an accepted Supervisor decision",
                        )
                    await asyncio.to_thread(
                        self.store.record_delivery_disposition,
                        self.session_id,
                        disposition,
                        report,
                    )
                    return StopGate(action="allow_final", report=report, reason=f"approved by {approval_id}")
                request_id = await self._enqueue_exit_review(disposition, report)
                reused = await self._reused_exit_review(request_id, disposition, report)
                if reused is not None:
                    return reused
                return StopGate(
                    action="wait_review",
                    report=report,
                    request_id=request_id,
                    reason="partial delivery requires Supervisor approval in dag_guided",
                )
            await asyncio.to_thread(
                self.store.record_delivery_disposition,
                self.session_id,
                disposition,
                report,
            )
            return StopGate(
                action="allow_final",
                report=report,
                reason="partial delivery recorded",
            )

        return StopGate(
            action="needs_work",
            report=report,
            reason=f"unsupported delivery disposition {disposition!r}",
        )

    async def _enqueue_exit_review(self, disposition: str, report: Any) -> str:
        snapshot = await asyncio.to_thread(self.engine.snapshot)
        target_ids = [
            *(node.node_id for node in snapshot.delivery.nodes),
            *(edge.edge_id for edge in snapshot.delivery.edges),
        ]
        if not target_ids:
            target_ids = [snapshot.delivery.graph_id]
        request = ReviewRequest(
            kind="exit",
            requester=self.session_id,
            target_ids=target_ids,
            question="May this delivery finish as a partial result under the declared scope?",
            proposal={
                "disposition": disposition,
                "scope": target_ids,
                "remaining_gaps": [g.model_dump(mode="json") for g in [*(report.unresolved), *(report.inconclusive)]],
                "method_limits": [],
            },
            basis_fingerprint="sha256:pending",
        )
        basis = await asyncio.to_thread(self.store.review_basis, request)
        request = request.model_copy(update={"basis_fingerprint": basis})
        return await asyncio.to_thread(self.store.enqueue_review, request)

    async def _reused_exit_review(self, request_id: str, disposition: str, report: Any) -> StopGate | None:
        """Consume a durable same-basis exit verdict without re-enqueuing it.

        A resolved rejection is actionable feedback, not a fresh request that
        can wait forever for a worker.  An accepted verdict may be reused only
        after the request scope and current basis have been revalidated.
        """
        request = await asyncio.to_thread(self.store.get_review_request, request_id)
        if request is None or request.state != "resolved" or request.kind != "exit":
            return None
        if request.proposal.get("disposition") != disposition:
            return None
        decision = await asyncio.to_thread(
            self.store.get_review_decision_for_request, request.request_id
        )
        if decision is None:
            return None
        if decision.basis_fingerprint != await asyncio.to_thread(self.store.review_basis, request):
            return None
        if decision.verdict != "accept":
            next_action = f"; next action: {decision.next_action}" if decision.next_action else ""
            return StopGate(
                action="needs_work",
                report=report,
                request_id=request.request_id,
                reason=f"{decision.reason}{next_action}",
            )
        await asyncio.to_thread(
            self.store.record_delivery_disposition,
            self.session_id,
            disposition,
            report,
        )
        return StopGate(
            action="allow_final",
            report=report,
            request_id=request.request_id,
            reason=f"approved by {decision.decision_id}",
        )

    async def _valid_exit_approval(self, decision_id: str, disposition: str, report: Any) -> bool:
        decision = await asyncio.to_thread(self.store.get_review_decision, decision_id)
        if decision is None or decision.verdict != "accept":
            return False
        request = await asyncio.to_thread(self.store.get_review_request, decision.request_id)
        if request is None or request.kind != "exit" or request.state != "resolved":
            return False
        if request.proposal.get("disposition") != disposition:
            return False
        if request.requester not in {self.agent_id, self.session_id}:
            return False
        current = await asyncio.to_thread(self.store.review_basis, request)
        if decision.basis_fingerprint != current:
            return False
        snapshot = await asyncio.to_thread(self.engine.snapshot)
        current_targets = {
            *(node.node_id for node in snapshot.delivery.nodes),
            *(edge.edge_id for edge in snapshot.delivery.edges),
        }
        if not current_targets:
            current_targets = {snapshot.delivery.graph_id}
        return set(request.target_ids) == current_targets
