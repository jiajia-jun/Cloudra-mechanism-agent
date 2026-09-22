"""Stop-time delivery coverage audit, approvals, and scientific-outcome separation.

统一运行结束门禁（Task 4A，计划 2026-09-05-event-driven-supervisor §6）的
DAG 半边：显式 stop 与无 tool_calls 的纯文本最终回复在 runner 收尾前的同
一边界调用 ``audit_stop`` 裁决；before_tool 不再做任何带副作用的 stop 预检，
退出审批请求只在本模块创建一次（``enqueue_review_with_status`` 同 basis 去重，
复用既有请求时不重复通知 Supervisor）。
"""

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
    "continue_work",
]

# 收尾依据：这次 run「凭什么」被允许结束。写进 ``agent.completion_gate`` 事件
# 的 ``basis`` 字段，由 ``runtime_v2.completion`` 投影成给用户看的验证等级
# （已验证完成 / 部分交付 / 未独立验证）。结构化枚举，绝不解析 reason 文本。
CompletionBasis = Literal[
    "declared",  # 无门禁意见或明确声明结束：模型自述，未独立验证
    "background_wait",  # 有可核实唤醒来源的挂起（后台计算 / 存活子 agent / 提醒）
    "dag_verified",  # DAG 交付覆盖审计通过（证据闭合）
    "supervisor_supported",  # 完整交付由 Supervisor 对提交证据作出支持判定
    "supervisor_approved",  # dag_guided 下 partial 经 Supervisor 接受（或复用其裁决）
    "partial_recorded",  # dag_record 下 partial 直接记录，无督导裁决
    "user_terminated",  # 真实用户终止（带用户取消事件 id）
]


class StopGate(BaseModel):
    """Deterministic result of a delivery stop audit.

    - allow_final: the run may finish and the disposition is recorded.
    - wait_background: the stop is a suspension because background work is
      still active; no delivery disposition is recorded.
    - wait_review: a Supervisor/approval is required before this disposition
      may be recorded.
    - continue_work: the stop is blocked until concrete gaps are resolved or a
      required approval/scope change is granted.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    action: StopAction
    report: Any = None
    request_id: str | None = None
    reason: str = Field(default="", description="Human-readable audit reason.")
    # 只在 allow_final / wait_background 这些「本次 run 将收尾」的判定上显式
    # 声明；被拦的判定（continue_work / wait_review）没有依据可言，保持 None。
    basis: CompletionBasis | None = None


async def pending_compute_jobs_exist(*, data_dir, project_id: str) -> bool:
    """本会话（项目）是否还有未终态的计算作业——compute.db 是唯一权威。"""
    from cloudra.persistence.database import ComputeDB
    from cloudra.services.compute_store import acount_pending_compute_jobs

    return bool(
        await acount_pending_compute_jobs(ComputeDB(data_dir=data_dir), project_id)
    )


def has_running_siblings(core, *, project_id: str, session_id: str) -> bool:
    """项目内是否还有未终态的其他 agent（纯 core.agents 事件投影读，不查库）。"""
    terminal = {"succeeded", "failed", "cancelled"}
    return any(
        agent.id != session_id
        and agent.project_id == project_id
        and agent.state.value not in terminal
        for agent in core.agents.values()
    )


def format_gate_gaps(report, *, limit: int = 12) -> list[str]:
    """把 coverage 报告的开放缺口格式化成反馈行（runner 的 continue_work
    反馈与历史 block 文案共用同一模式）。"""
    if report is None:
        return []
    gaps = [*(report.unresolved or []), *(report.inconclusive or [])]
    return [
        f"- {g.code} on {g.target_type} {g.target_id}: {g.detail}" for g in gaps[:limit]
    ]


class StopAuditMixin:
    """stop 交付门禁（audit_stop）；由 DagController 组合。"""

    async def _has_pending_background(self) -> bool:
        """会话级后台是否还有未竟工作（子任务/计算/定时提醒）。

        与 runner 的收件箱复查同一判定口径：只要后台未排空，stop 就是
        "挂起等唤醒"而不是交付。D8.2：子 agent 与提醒读 v2-native 信号
        （core.agents 投影 + ReminderBroker 事件投影）；compute_jobs 仍是
        权威，但已迁到中央 compute.db（按 conversation_id 过滤本会话）。
        """
        if await pending_compute_jobs_exist(
            data_dir=self.db.data_dir, project_id=self.conversation_id
        ):
            return True
        core = self._core
        if core is None:
            return False
        if has_running_siblings(
            core, project_id=self.conversation_id, session_id=self.session_id
        ):
            return True
        return bool(core.reminders.pending(self.session_id))

    async def audit_stop(
        self,
        disposition: str,
        *,
        approval_id: str | None = None,
        user_stop_event_id: str | None = None,
    ) -> StopGate:
        """Audit a stop/final reply and return a :class:`StopGate`.

        The delivery disposition is recorded only when ``action == allow_final``.
        判定副作用（记录处置 / 创建退出请求 / 通知 Supervisor）只在本方法
        发生；调用方（统一结束边界）负责按 action 落运行状态。
        """
        if not self.enabled:
            return StopGate(action="allow_final", report=None, basis="declared")
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
                    action="continue_work",
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
            return StopGate(action="allow_final", report=None, basis="user_terminated")

        if await self._has_pending_background():
            return StopGate(
                action="wait_background",
                report=None,
                reason="background work is still pending; stop only suspends",
                basis="background_wait",
            )

        report = await asyncio.to_thread(self.delivery_report)
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
                basis=(
                    "supervisor_supported"
                    if any(
                        gate.code == "supervisor_evidence_accepted"
                        for gate in report.satisfied
                    )
                    else "dag_verified"
                ),
            )

        if disposition == "complete":
            # Complete with gaps is blocked deterministically.  The audit
            # report names the missing evidence; the agent may submit it for
            # review (dag_bind_evidence) — there is no automatic pre-delivery
            # LLM review round anymore (§1: the stop gate never triggers the
            # Supervisor itself).  Accepted file evidence is accounted for separately from machine
            # verification in the report; an exit approval may authorize partial/
            # method-limited scope only.
            return StopGate(
                action="continue_work",
                report=report,
                reason="complete was declared but required coverage is missing",
            )

        # partial without approval in dag_guided must wait for a Supervisor
        # decision; in dag_record partial is the ordinary recorded stop.
        if disposition == "partial":
            if self.mode is OrchestrationMode.DAG_GUIDED:
                if approval_id is not None and await self._valid_exit_approval(
                    approval_id, disposition, report
                ):
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
                        basis="supervisor_approved",
                    )
                request_id, created = await self._enqueue_exit_review(disposition, report)
                reused = await self._reused_exit_review(request_id, disposition, report)
                if reused is not None:
                    return reused
                if created:
                    # 同一交付版本/退出声明复用既有请求时不再重复叫醒督导
                    # （§6 wait_review 契约）；请求是持久化待办，恢复路径由
                    # reconcile_supervision 补通知。
                    await self._notify_supervisor("exit review requested")
                reason = (
                    "approval is missing, stale, out of scope, or not an accepted Supervisor decision"
                    if approval_id is not None
                    else "partial delivery requires Supervisor approval in dag_guided"
                )
                return StopGate(
                    action="wait_review",
                    report=report,
                    request_id=request_id,
                    reason=reason,
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
                basis="partial_recorded",
            )

        return StopGate(
            action="continue_work",
            report=report,
            reason=f"unsupported delivery disposition {disposition!r}",
        )

    async def _enqueue_exit_review(self, disposition: str, report: Any) -> tuple[str, bool]:
        """持久化退出审查请求；同 kind+scope+basis 去重。返回 (request_id,
        是否新建）——只有新建才值得通知 Supervisor。"""
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
        return await asyncio.to_thread(self.store.enqueue_review_with_status, request)

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
                action="continue_work",
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
            basis="supervisor_approved",
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
