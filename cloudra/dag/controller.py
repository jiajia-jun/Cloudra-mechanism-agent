"""Mode-aware harness integration for durable tool evidence and DAG prompts."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from cloudra.dag.completion import build_projection, evaluate_delivery
from cloudra.dag.drafts import DraftsMixin
from cloudra.dag.engine import DagEngine
from cloudra.dag.evidence_inbox import EvidenceInboxMixin, enqueue_compute_review
from cloudra.dag.models import (
    CoverageContract,
    CoverageGateResult,
    OrchestrationMode,
    normalize_orchestration_mode,
)
from cloudra.dag.review_context import review_target_identity
from cloudra.dag.stop_audit import StopAuditMixin
from cloudra.dag.store import DagStore
from cloudra.dag.supervision import SupervisionMixin
from cloudra.persistence.database import ConversationDB

__all__ = ["DagController", "enqueue_compute_review"]


class DagController(SupervisionMixin, StopAuditMixin, EvidenceInboxMixin, DraftsMixin):
    """Deterministic harness writer. Chemistry tools themselves remain stateless."""

    def __init__(
        self,
        db: ConversationDB,
        session_id: str,
        mode: str | OrchestrationMode,
        *,
        conversation_id: str | None = None,
        working_directory: str | Path | None = None,
        agent_id: str | None = None,
        role_id: str | None = None,
        core=None,
    ):
        self.db = db
        self.session_id = session_id
        self.mode = normalize_orchestration_mode(mode)
        self.conversation_id = conversation_id or db.conversation_id or "default"
        # 变更日志与 CallReview sidecar 使用的 actor id（legacy a-N 词表）
        self.agent_id = agent_id
        # v2 role_id（CallReview sidecar 用；legacy a-N 由单一映射推出，D13）
        self.role_id = role_id
        # runtime_v2 RuntimeCore 句柄（可选）：_has_pending_background 的
        # v2-native 信号（core.agents 投影 + ReminderBroker 投影，D8.2）
        self._core = core
        self.working_directory = (
            Path(working_directory).expanduser().resolve()
            if working_directory is not None
            else None
        )
        self.store = DagStore(db)
        self.engine = DagEngine(self.store)
        self.contract = CoverageContract.mechanism_default()
        self._initialized = False

    @property
    def enabled(self) -> bool:
        return self.mode is not OrchestrationMode.STANDARD

    async def initialize(self) -> None:
        """加载图存储与覆盖契约；不自动拉起 Supervisor。

        用户追加消息/唤醒会重开 agent run，轮管道经 DagPolicyStage 再次调到
        ``initialize()``。督导通知全部由 ``_trigger_supervisor_after_tool``
        （提案/显式送审/督导消息的完成钩子）/ 退出审查请求 /
        ``user_replan`` 在持久化后发出。
        """
        if not self.enabled or self._initialized:
            return
        await asyncio.to_thread(self.store.ensure_bundle, self.session_id)
        self.contract = await asyncio.to_thread(self.store.load_coverage_contract)
        self._initialized = True

    async def mechanism_accepted(self) -> bool:
        """D4：是否存在已接受的机理草稿（唯一判据，随库存续）。"""
        if not self.enabled:
            return True
        await self.initialize()
        # 同步 sqlite 读走 worker 线程，busy 等待不占事件循环
        return await asyncio.to_thread(self.store.has_accepted_draft)

    async def check_substantive_gate(
        self,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
    ) -> tuple[str, str] | None:
        """Return ``None``: a pending draft never blocks exploratory computation.

        The Supervisor's review and the final delivery gate remain stateful DAG
        concerns.  They do not turn an initial hypothesis into a prerequisite
        for computing, branching, or revising the hypothesis.
        """
        return None

    async def prompt_projection(self) -> str:
        if not self.enabled:
            return ""
        await self.initialize()
        self.contract = await asyncio.to_thread(self.store.load_coverage_contract)
        # 同步 sqlite 读也走 worker 线程，busy 等待不能占用事件循环
        snapshot = await asyncio.to_thread(self.engine.snapshot)
        history = await asyncio.to_thread(self.engine.history, limit=8)
        # 与 dag_view 同一口径：只有 source="explicit" 的显式送审行是可消费
        # 待办；legacy_auto/auto 行保留审计但永不可消费，不能投成"pending"。
        reviews = await asyncio.to_thread(
            self.store.list_call_reviews, "pending", source="explicit"
        )
        pending = [
            {
                "review_id": row.review_id,
                "tool_name": row.tool_name,
                "is_success": row.is_success,
                "caller": row.caller_legacy_id or row.caller_role_id,
                "source_path": row.source_path,
                "result_kind": row.result_kind,
                # §5：送审主张随投影给 Coordinator/Supervisor——裁决围绕 claim，
                # 撤销/重提也要对着它说。
                "claim": row.claim,
                **(
                    {"target": f"{row.suggested_target_id}.{row.suggested_stage}"}
                    if row.suggested_target_id
                    else {}
                ),
                **(
                    {"compute_job_id": row.compute_job_id}
                    if row.compute_job_id
                    else {}
                ),
            }
            for row in reviews
        ]
        # 最近被驳回的机理草稿：驳回理由随投影回给 Coordinator（open 草稿
        # 优先于已裁决草稿——有新草稿在审时驳回即已被修订响应）。
        rejected_draft = None
        draft = await asyncio.to_thread(self.store.latest_draft)
        if draft and draft["state"] == "rejected" and (draft["reject_reason"] or "").strip():
            rejected_draft = {
                "draft_id": draft["draft_id"],
                "rationale": draft["rationale"],
                "reject_reason": draft["reject_reason"],
            }
        report = await asyncio.to_thread(self.delivery_report)
        projection = build_projection(
            snapshot,
            mode=self.mode,
            report=report,
            history=history,
            pending_reviews=pending,
            rejected_draft=rejected_draft,
        )
        return projection.to_prompt_text(actor_id=self.agent_id)

    def delivery_report(self):
        """Evaluate the selected delivery, keeping machine facts and reviews separate."""
        if not self.enabled:
            return None
        self.contract = self.store.load_coverage_contract()
        claim = self.store.accepted_claim_spec()
        declared = None
        if self.mode is OrchestrationMode.DAG_GUIDED:
            declared = next(
                ((draft_id, draft, reason)
                 for draft_id, draft, reason in reversed(self.store.list_delivery_drafts())
                 if draft.claim_spec is not None),
                None,
            )
        delivery = self.engine.snapshot().delivery
        elements = {
            **{node.node_id: ("node", node) for node in delivery.nodes},
            **{edge.edge_id: ("edge", edge) for edge in delivery.edges},
        }
        accepted_targets = {
            str(item)
            for container in (claim.scope, claim.reference)
            for item in (container.get("targets") or [])
        } if claim is not None else set()
        pending_scope = None
        effective_claim = claim
        if declared is not None and declared[1].state != "accepted":
            draft_id, draft, reason = declared
            proposed = draft.claim_spec
            proposed_targets = {
                str(item)
                for container in (proposed.scope, proposed.reference)
                for item in (container.get("targets") or [])
            }
            pending_scope = (draft_id, draft.state, reason, proposed_targets)
            combined = accepted_targets | proposed_targets
            source = claim or proposed
            effective_claim = source.model_copy(update={
                "scope": {**source.scope, "targets": sorted(combined)},
                "reference": {key: value for key, value in source.reference.items()
                              if key != "targets"},
            })
        targets = {
            str(item)
            for container in (effective_claim.scope, effective_claim.reference)
            for item in (container.get("targets") or [])
        } if effective_claim is not None else set()
        selected = set(targets) if targets else set(elements)
        for edge in delivery.edges:
            if edge.edge_id in selected:
                selected.update((edge.source_node_id, edge.target_node_id))
        delivery = delivery.model_copy(update={
            "nodes": [node for node in delivery.nodes if node.node_id in selected],
            "edges": [edge for edge in delivery.edges if edge.edge_id in selected],
        })
        facts = {target: self.store.facts_for_target(target) for target in selected}
        report = evaluate_delivery(
            delivery, self.contract,
            claim_kind=effective_claim.kind.value if effective_claim is not None else None,
            claim_spec=effective_claim, evidence_facts=facts,
        )
        if self.mode is OrchestrationMode.DAG_GUIDED:
            report = self._apply_review_stage_credits(report, delivery, selected)
        unresolved = list(report.unresolved)
        for missing in sorted(selected - elements.keys()):
            unresolved.append(CoverageGateResult(
                code="missing_delivery_target", target_type="graph", target_id=missing,
                detail="A declared delivery target was removed or does not exist.",
            ))
        if pending_scope is not None:
            draft_id, state, reason, proposed_targets = pending_scope
            unresolved.append(CoverageGateResult(
                code="pending_scope_review" if state == "open" else "rejected_scope_review",
                target_type="graph", target_id=delivery.graph_id,
                detail=(
                    f"Declared delivery scope {sorted(proposed_targets)} in draft {draft_id} "
                    + ("awaits Supervisor review" if state == "open"
                       else f"was rejected: {reason}")
                ),
            ))
        if self.mode is OrchestrationMode.DAG_GUIDED:
            unresolved.extend(self._review_gaps(selected, elements))
            unresolved.extend(self._draft_gaps(selected, elements))
        return report.model_copy(update={
            "unresolved": unresolved,
            "complete": not unresolved and not report.inconclusive,
        })

    def _draft_gaps(self, selected, elements):
        """Only unresolved draft opinions about this delivery remain final debts."""
        latest = {}
        for draft_id, draft, reason in self.store.list_delivery_drafts():
            targets = set(draft.claim_spec.scope.get("targets", [])) if draft.claim_spec else set()
            for operation in draft.operations:
                element = getattr(operation, "node", None) or getattr(operation, "edge", None)
                target = (
                    getattr(element, "node_id", None)
                    or getattr(element, "edge_id", None)
                    or getattr(operation, "node_id", None)
                    or getattr(operation, "edge_id", None)
                )
                if target:
                    targets.add(target)
            for target in targets & selected:
                latest[target] = (draft_id, draft.state, reason)
        gaps = []
        for target, (draft_id, state, reason) in latest.items():
            if state not in {"open", "rejected"}:
                continue
            gaps.append(CoverageGateResult(
                code="pending_mechanism_review" if state == "open" else "rejected_mechanism_review",
                target_type=elements.get(target, ("graph", None))[0],
                target_id=target,
                detail=(f"Draft {draft_id} awaits Supervisor review" if state == "open"
                        else f"Draft {draft_id} was rejected: {reason}"),
            ))
        return gaps

    def _apply_review_stage_credits(self, report, delivery, selected):
        """Require scientific checks AND explicit Supervisor acceptance for file stages.

        A per-file review records Supervisor judgment, but it is deliberately
        not a graph mutation and must not change ``evidence_level``.  Only the
        exact pending stage(s) represented by the immutable file refs may be
        removed from the coverage report after their scientific checks pass;
        endpoint, thermochemistry and contradiction gates remain obligations.
        """
        from cloudra.dag.models import normalize_claim

        elements = {
            **{node.node_id: ("node", node) for node in delivery.nodes},
            **{edge.edge_id: ("edge", edge) for edge in delivery.edges},
        }
        requests = self.store.list_review_requests(state=None)
        latest: dict[tuple, tuple[Any, Any] | None] = {}
        for request in requests:
            if request.kind != "evidence" or not request.target_ids:
                continue
            targets = tuple(sorted(set(request.target_ids)))
            if not set(targets) & selected:
                continue
            key = (request.kind, targets, normalize_claim(request.question))
            if request.state in {"queued", "superseded"}:
                latest[key] = None
                continue
            if request.state != "resolved":
                continue
            decision = self.store.get_review_decision_for_request(request.request_id)
            if decision is not None:
                latest[key] = (request, decision)

        from cloudra.dag.file_science import file_scientific_checks

        credits: dict[str, set[str]] = {}
        scientific_gaps = []
        for item in latest.values():
            if item is None:
                continue
            request, decision = item
            if decision.verdict != "accept":
                continue
            refs = request.supporting_refs
            # A review must point at persisted content-addressed file evidence.
            if not refs or any(ref.ref_type != "file" or not ref.content_hash for ref in refs):
                continue
            proposal = request.proposal
            element_type = proposal.get("element_type")
            target = request.target_ids[0] if len(request.target_ids) == 1 else None
            if target not in elements:
                continue
            if proposal.get("target_identity") != review_target_identity(delivery, element_type, target):
                continue
            if any(ref not in elements[target][1].refs for ref in refs):
                continue
            expected = {stage.kind.value for stage in elements[target][1].stages
                        if stage.required and stage.status.value == "pending"}
            expected &= {"geometry", "ts_opt", "frequency", "short_irc"}
            if not expected:
                continue
            checks = file_scientific_checks(self.store, delivery, target,
                                            irc_files=proposal.get("irc_files"), endpoint_refs=proposal.get("endpoint_refs"), workspace_root=self.working_directory,
                                            evidence_refs=refs)
            for stage in expected:
                check = checks[stage]
                if check["status"] == "passed":
                    credits.setdefault(target, set()).add(stage)
                else:
                    scientific_gaps.append(CoverageGateResult(
                        code="scientific_check_incomplete", target_type=elements[target][0], target_id=target,
                        detail=f"{stage}: {check['status']}. {check['detail']} Next: {check['next_action']}",
                    ))

        if not credits and not scientific_gaps:
            return report
        satisfied = list(report.satisfied)
        unresolved = []
        for gate in report.unresolved:
            if gate.code != "missing_stage_evidence" or gate.target_id not in credits:
                unresolved.append(gate)
                continue
            # Only close the machine gate when every required stage is covered;
            # a partial review leaves the remaining stages visible as a gap.
            target_stages = elements[gate.target_id][1].stages
            required_pending = {
                stage.kind.value for stage in target_stages
                if stage.required and stage.status.value == "pending"
            }
            remaining = required_pending - credits[gate.target_id]
            if remaining:
                unresolved.append(gate.model_copy(update={
                    "detail": "required stages pending: " + ", ".join(sorted(remaining)),
                }))
            satisfied.append(CoverageGateResult(
                code="supervisor_evidence_accepted",
                target_type=gate.target_type,
                target_id=gate.target_id,
                detail="Supervisor accepted immutable per-file evidence for stages: "
                + ", ".join(sorted(required_pending & credits[gate.target_id])),
            ))
        return report.model_copy(update={"satisfied": satisfied, "unresolved": [*unresolved, *scientific_gaps]})

    def _review_gaps(self, selected, elements):
        """Read durable review outcomes; optional, unscoped advice is not a debt.

        Later adjudication of the same question can settle an earlier objection.
        Merely submitting another file cannot settle it: the new review must be
        accepted. Other questions and counterevidence remain independently open.
        """
        from cloudra.dag.models import normalize_claim

        gaps = []

        def gap(target, code, detail):
            gaps.append(CoverageGateResult(
                code=code, target_type=elements.get(target, ("graph", None))[0],
                target_id=target, detail=detail,
            ))

        requests = self.store.list_review_requests(state=None)
        newest = {}
        for request in requests:
            key = (request.kind, tuple(sorted(request.target_ids)), normalize_claim(request.question))
            newest[key] = request
        latest = {}
        for request in requests:
            if request.kind not in {"evidence", "exception"}:
                continue
            relevant = set(request.target_ids) & selected
            if not relevant:
                continue
            key = (request.kind, tuple(sorted(request.target_ids)), normalize_claim(request.question))
            if request.state == 'superseded':
                latest.pop(key, None)
                if newest[key].request_id == request.request_id:
                    for target in sorted(relevant):
                        gap(target, 'stale_evidence_review', f'Review {request.request_id} is superseded; resubmit current evidence for a new decision.')
                continue
            # A queued replacement never erases the previous decision. It adds
            # an outstanding review until the Supervisor actually resolves it.
            if request.state == "queued":
                for target in sorted(relevant):
                    gap(target, "pending_evidence_review", f"Evidence review {request.request_id} is pending: {request.question}")
            elif request.state == "resolved":
                decision = self.store.get_review_decision_for_request(request.request_id)
                if decision is not None:
                    latest[key] = (request, decision)
                else:
                    for target in sorted(relevant):
                        gap(target, "missing_review_decision", f"Review {request.request_id} has no durable decision.")
        for request, decision in latest.values():
            if decision.verdict in {"reject", "needs_evidence"}:
                for target in sorted(set(request.target_ids) & selected):
                    gap(target, "supervisor_review_gap",
                        f"Review {request.request_id} ({request.question}): {decision.verdict}: {decision.reason}")

        # Low-level call bindings retain stage-specific decisions. The normal
        # per-file interface above does not split a file into stage submissions.
        verdicts = {item["review_id"]: item for item in self.store.list_call_verdicts()}
        latest_calls = {}
        for review in self.store.list_call_reviews(state=None, source="explicit"):
            target = review.suggested_target_id
            if target not in selected:
                continue
            key = (target, review.suggested_stage, normalize_claim(review.claim))
            if review.state == "pending":
                gap(target, "pending_evidence_review", f"Evidence review {review.review_id} is pending: {review.claim}")
            elif review.state == "reviewed":
                if review.review_id in verdicts:
                    latest_calls[key] = verdicts[review.review_id]
                else:
                    gap(target, "missing_review_decision", f"Review {review.review_id} has no durable verdict.")
        for (target, _stage, _claim), verdict in latest_calls.items():
            if verdict.get("verdict") in {"disagree", "needs_evidence"}:
                gap(target, "supervisor_review_gap", f"{verdict['verdict']}: {verdict.get('reason', '')}")
        return gaps
