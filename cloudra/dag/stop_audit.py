"""Stop-time delivery coverage audit, approvals, and scientific-outcome separation."""

from __future__ import annotations

import asyncio
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from cloudra.dag.models import OrchestrationMode

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
            if not user_stop_event_id:
                return StopGate(
                    action="needs_work",
                    report=None,
                    reason=(
                        "user_terminated requires a real user stop event id; "
                        "a model cannot self-declare user termination"
                    ),
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
            if approval_id is not None:
                # Approval-id path is accepted as a scoped partial/complete
                # grant; the original gaps remain visible in the report.
                await asyncio.to_thread(
                    self.store.record_delivery_disposition,
                    self.session_id,
                    disposition,
                    report,
                )
                return StopGate(
                    action="allow_final",
                    report=report,
                    reason=f"approved by {approval_id}",
                )
            return StopGate(
                action="needs_work",
                report=report,
                reason="complete was declared but required coverage is missing",
            )

        # partial without approval in dag_guided must wait for a Supervisor
        # decision; in dag_record partial is the ordinary unaudited stop.
        if disposition == "partial":
            if (
                self.mode is OrchestrationMode.DAG_GUIDED
                and approval_id is None
            ):
                return StopGate(
                    action="wait_review",
                    report=report,
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
