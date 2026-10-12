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
    "scope_completed",  # 声明范围已处置，包含跳过/豁免，不代表科学验证
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
    """Whether compute is active or a terminal result still awaits delivery."""
    from cloudra.persistence.database import ComputeDB
    from cloudra.services.compute_store import (
        acount_pending_compute_jobs,
        pending_terminal_jobs,
    )

    db = ComputeDB(data_dir=data_dir)
    if await acount_pending_compute_jobs(db, project_id):
        return True
    # A completed calculation is still background work until its durable
    # result reaches the agent inbox. Never release the delivery gate first.
    return bool(await asyncio.to_thread(
        pending_terminal_jobs, db, window_seconds=0, limit=1,
        conversation_id=project_id,
    ))


def has_running_siblings(core, *, project_id: str, session_id: str) -> bool:
    """Project agents or launch-group items with unfinished work.

    A parked ancestor must not hold its own child open: that would make the
    parent and child wait on each other after both successful run transitions.
    """
    from cloudra.runtime_v2.agent_host import is_background_parked

    # History probes can release the GIL for SQLite. Freeze registry membership
    # and values before probing rather than traversing a live dict across I/O.
    agents = {
        key: agent.model_copy(deep=True) for key, agent in list(core.agents.items())
    }

    def is_descendant(agent) -> bool:
        seen: set[str] = set()
        owner_id = agent.parent_session_id or agent.requested_by_session_id
        while owner_id and owner_id not in seen:
            if owner_id == session_id:
                return True
            seen.add(owner_id)
            owner = agents.get(owner_id)
            owner_id = (
                owner.parent_session_id or owner.requested_by_session_id
                if owner is not None else None
            )
        return False

    terminal = {"succeeded", "failed", "cancelled"}
    current = agents.get(session_id)
    # Coordinator audits the whole project (including legacy unowned agents).
    # A child must only wait on work it owns, never its active parent/siblings.
    project_wide = current is not None and current.role_id == "coordinator"
    scientific_supervision_pending = False
    if any(
        agent.role_id == "supervisor"
        and agent.id != session_id
        and agent.project_id == project_id
        and agent.state.value not in terminal
        for agent in agents.values()
    ):
        from cloudra.runtime_v2.supervision import pending_supervision_counts

        pending = pending_supervision_counts(project_id)
        scientific_supervision_pending = any(
            pending[kind] for kind in ("call_reviews", "open_drafts", "review_requests")
        )
    if any(
        agent.id != session_id
        and agent.project_id == project_id
        # Scientific review still counts as background work. Notebook tidying
        # alone must not hold delivery open.
        and (agent.role_id != "supervisor" or scientific_supervision_pending)
        and (
            (agent.state.value not in terminal and (project_wide or is_descendant(agent)))
            or (is_descendant(agent) and is_background_parked(core, agent))
        )
        for agent in agents.values()
    ):
        return True
    # A capped launch group can have queued items with no child agent yet.
    # Its first child finishes before admission dispatches the next item.
    return any(
        group.project_id == project_id
        and group.state == "running"
        and (group.pending_count or group.running_count)
        and (
            project_wide
            or group.parent_session_id == session_id
            or (
                group.parent_session_id in agents
                and is_descendant(agents[group.parent_session_id])
            )
        )
        for group in core.launch_groups.groups()
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
        if await asyncio.to_thread(
            has_running_siblings,
            core, project_id=self.conversation_id, session_id=self.session_id
        ):
            return True
        return bool(await asyncio.to_thread(core.reminders.pending, self.session_id))

    async def audit_stop(
        self,
        disposition: str,
        *,
        approval_id: str | None = None,
        user_stop_event_id: str | None = None,
    ) -> StopGate:
        """Audit a stop/final reply and return a :class:`StopGate`.

        The audit queues a disposition only for allow_final. The runner commits it
        after all completion policies and its final inbox check permit delivery.
        """
        if not self.enabled:
            return StopGate(action="allow_final", report=None, basis="declared")
        await self.initialize()
        self._pending_stop = None
        self._delivery_artifact = None

        # A real user termination is allowed regardless of graph coverage, but
        # the model must not be able to invent that source.
        if disposition == "user_terminated":
            event = (
                await asyncio.to_thread(self._core.event_log.get, user_stop_event_id)
                if self._core is not None and user_stop_event_id else None
            )
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
            state = await asyncio.to_thread(self.store.delivery_state_fingerprint)
            self._pending_stop = (disposition, None, None, state)
            return StopGate(action="allow_final", report=None, basis="user_terminated")

        if await self._has_pending_background():
            return StopGate(
                action="wait_background",
                report=None,
                reason="background work is still pending; stop only suspends",
                basis="background_wait",
            )

        state = await asyncio.to_thread(self.store.delivery_state_fingerprint)
        report = await asyncio.to_thread(self.delivery_report)
        from cloudra.dag.delivery_artifact import prepare_delivery_artifact
        graph = (await asyncio.to_thread(self.engine.snapshot)).delivery
        required = bool(self._core is not None and
                        self._core.require_project(self.conversation_id).settings.benchmark_task_id)
        try:
            self._delivery_artifact = await asyncio.to_thread(prepare_delivery_artifact,
                self.store, graph, report, self.working_directory, required=required)
        except (ValueError, OSError) as exc:
            return StopGate(action='continue_work', report=report,
                reason=f'Delivery artifact is inconsistent with the DAG: {exc}')
        if await asyncio.to_thread(self.store.delivery_state_fingerprint) != state:
            return StopGate(action='continue_work', report=report,
                reason='DAG evidence or review state changed during audit; re-audit the delivery.')
        self._audit_state = state
        if disposition == "complete" and report.complete:
            claim = await asyncio.to_thread(self.store.accepted_claim_spec)
            scope_only = bool(report.waived) or any(
                gate.code in {"branch_disposed", "stage_not_applicable"}
                for gate in report.satisfied
            ) or (claim is not None and not claim.required_checks)
            self._pending_stop = (disposition, report, None, state)
            return StopGate(
                action="allow_final",
                report=report,
                reason="coverage audit passed",
                basis=(
                    "scope_completed" if scope_only else "supervisor_supported"
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
                    self._pending_stop = (disposition, report, approval_id, state)
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
            self._pending_stop = (disposition, report, None, state)
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
                "delivery_artifact": self._delivery_artifact.model_dump(mode='json') if self._delivery_artifact else None,
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
        if request.proposal.get("disposition") != disposition or not self._exit_artifact_matches(request):
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
        self._pending_stop = (disposition, report, decision.decision_id, self._audit_state)
        return StopGate(
            action="allow_final",
            report=report,
            request_id=request.request_id,
            reason=f"approved by {decision.decision_id}",
            basis="supervisor_approved",
        )

    def _exit_artifact_matches(self, request) -> bool:
        artifact = getattr(self, '_delivery_artifact', None)
        return request.proposal.get('delivery_artifact') == (artifact.model_dump(mode='json') if artifact else None)

    async def _valid_exit_approval(self, decision_id: str, disposition: str, report: Any) -> bool:
        decision = await asyncio.to_thread(self.store.get_review_decision, decision_id)
        if decision is None or decision.verdict != "accept":
            return False
        request = await asyncio.to_thread(self.store.get_review_request, decision.request_id)
        if request is None or request.kind != "exit" or request.state != "resolved":
            return False
        if request.proposal.get("disposition") != disposition or not self._exit_artifact_matches(request):
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

    async def commit_stop(self) -> None:
        """Commit delivery only after the runner's combined gate allows final."""
        pending = getattr(self, '_pending_stop', None)
        if pending is None:
            return
        disposition, report, approval_id, state = pending
        if await asyncio.to_thread(self.store.delivery_state_fingerprint) != state:
            raise RuntimeError('DAG evidence or review state changed after audit; re-audit the delivery.')
        if approval_id and not await self._valid_exit_approval(approval_id, disposition, report):
            raise RuntimeError('Exit approval changed after audit; re-audit the delivery.')
        artifact = getattr(self, '_delivery_artifact', None)
        if disposition != 'user_terminated':
            from cloudra.dag.delivery_artifact import prepare_delivery_artifact
            graph = (await asyncio.to_thread(self.engine.snapshot)).delivery
            current_report = await asyncio.to_thread(self.delivery_report)
            required = bool(self._core is not None and
                            self._core.require_project(self.conversation_id).settings.benchmark_task_id)
            current_artifact = await asyncio.to_thread(prepare_delivery_artifact,
                self.store, graph, current_report, self.working_directory, required=required)
            if current_report != report or current_artifact != artifact:
                raise RuntimeError('Delivery artifact or scientific evidence changed after audit; re-audit the delivery.')
        if artifact is not None:
            from cloudra.dag.delivery_artifact import current_artifact_digest
            from cloudra.dag.evidence_ingest import snapshot_evidence_file
            snapshot = await asyncio.to_thread(snapshot_evidence_file, artifact.path,
                workspace_root=self.working_directory, conversation_id=self.conversation_id)
            if snapshot.sha256 != artifact.sha256 or await asyncio.to_thread(
                    current_artifact_digest, snapshot.snapshot_path) != artifact.sha256 or await asyncio.to_thread(
                    current_artifact_digest, artifact.path) != artifact.sha256:
                raise RuntimeError('Delivery artifact changed after audit; re-audit the delivery.')
            artifact = artifact.model_copy(update={'snapshot_path': snapshot.snapshot_path})
            report = report.model_copy(update={'output_artifact': artifact.model_dump(mode='json')})
        await asyncio.to_thread(self.store.record_delivery_disposition, self.session_id, disposition, report,
            expected_state=state)
        self._pending_stop = None
