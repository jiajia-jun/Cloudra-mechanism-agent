"""dag_review_evidence: Supervisor resolves a structured ReviewRequest."""

from __future__ import annotations

import asyncio
from typing import Any, Literal

from pydantic import Field

from cloudra.base.session_class import Session
from cloudra.base.tool_actor import ToolActorContext
from cloudra.base.tools_class import input_schema
from cloudra.dag.models import GraphActor, GraphRef, OrchestrationMode
from cloudra.dag.review_requests import ReviewDecision
from cloudra.tools.Plantool.dag_tools._common import DagToolBase, DagToolOutput, fail


class DagReviewEvidenceInput(input_schema):
    request_id: str = Field(description="The ReviewRequest id to resolve, or an unresolved consultation decision to reconsider with current evidence.")
    verdict: Literal["accept", "reject", "needs_evidence"] = Field(
        description="Decision verdict for the structured request."
    )
    reason: str = Field(description="Scientific reason for the decision.")
    findings: list[dict[str, Any]] = Field(
        default_factory=list,
        description=(
            "Per-target findings; each item requires "
            "target_id/check/outcome/reason and may include evidence_refs."
        ),
    )
    evidence_refs: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Evidence references used by this decision.",
    )
    next_action: str | None = Field(
        default=None,
        description="Required for reject/needs_evidence.",
    )


class DagReviewEvidence(DagToolBase):
    tool_id: str = "t-dag-review-evidence"
    tool_name: str = "dag_review_evidence"
    tool_description: str = (
        "Resolve one structured ReviewRequest (Supervisor only in dag_guided). "
        "Use for: answering evidence/exception/draft/exit requests with a full "
        "basis-matched decision, or reconsidering a resolved consultation that "
        "was rejected or needed evidence, using its request_id and current evidence_refs. "
        "Do not use for: editing delivery graph structures directly or "
        "replacing a resolved species/step file submission (resubmit the files), or "
        "resolving old CallReview rows (use dag_review_call for those)."
    )
    input_schema: Any = DagReviewEvidenceInput
    output_schema: Any = DagToolOutput
    subagent: ToolActorContext | None = None

    async def tool_call(
        self, user_input: DagReviewEvidenceInput, session: Session
    ) -> DagToolOutput:
        mode = self._mode()
        if mode is OrchestrationMode.STANDARD:
            return self._standard_disabled()
        if mode is OrchestrationMode.DAG_RECORD:
            return fail(
                "dag_review_evidence",
                "disabled in dag_record (the Supervisor is offline)",
                accepted=False,
            )
        ctx = await self._prepare(session)
        if ctx.actor is not GraphActor.SUPERVISOR:
            return fail(
                "dag_review_evidence",
                "review_evidence is supervisor-only",
                accepted=False,
            )
        store = ctx.store
        request = await asyncio.to_thread(store.get_review_request, user_input.request_id)
        if request is None:
            return fail(
                "dag_review_evidence",
                f"review request {user_input.request_id!r} does not exist",
            )
        reconsider = False
        if (
            request.state == "resolved"
            and request.kind in {"evidence", "exception"}
            and request.proposal.get("element_type") not in {"species", "step"}
        ):
            previous = await asyncio.to_thread(store.get_review_decision_for_request, request.request_id)
            reconsider = previous is not None and previous.verdict in {"reject", "needs_evidence"}
        if request.state != "queued" and not reconsider:
            return fail(
                "dag_review_evidence",
                f"review request {user_input.request_id!r} is {request.state}",
            )
        if user_input.verdict in ("reject", "needs_evidence") and not (
            user_input.reason.strip() and (user_input.next_action or "").strip()
        ):
            return fail(
                "dag_review_evidence",
                "reject/needs_evidence requires a non-empty reason and next_action",
            )
        if (
            user_input.verdict == "accept"
            and request.kind == "exit"
            and not {"disposition", "scope", "remaining_gaps", "method_limits"}
            <= set(request.proposal)
        ):
            return fail(
                "dag_review_evidence",
                "accepting an exit request requires proposal with disposition, "
                "scope, remaining_gaps, and method_limits",
            )
        try:
            evidence_refs = [
                GraphRef(**item) if isinstance(item, dict) else item
                for item in user_input.evidence_refs
            ]
            if reconsider:
                # Keep the original question and decision intact. The new
                # material gets an ordinary request; enqueue_review deduplicates
                # retries of this old request + current material and basis.
                supporting_refs = [*request.supporting_refs, *[
                    ref for ref in evidence_refs if ref not in request.supporting_refs
                ]]
                request = request.model_copy(update={
                    "request_id": "", "state": "queued", "created_at": "", "updated_at": "",
                    "supporting_refs": supporting_refs,
                    "proposal": {**request.proposal, "reconsiders_request_id": request.request_id},
                })
                basis = await asyncio.to_thread(store.review_basis, request)
                request_id = await asyncio.to_thread(store.enqueue_review,
                    request.model_copy(update={"basis_fingerprint": basis}))
                request = await asyncio.to_thread(store.get_review_request, request_id)
            next_action = user_input.next_action
            scientific_checks = None
            if (
                request.kind == "evidence"
                and request.proposal.get("element_type") in {"species", "step"}
                and len(request.target_ids) == 1
            ):
                from cloudra.dag.file_science import file_scientific_checks

                snapshot = await asyncio.to_thread(store.load_snapshot)
                scientific_checks = await asyncio.to_thread(
                    file_scientific_checks, store, snapshot.delivery, request.target_ids[0],
                    irc_files=request.proposal.get("irc_files"), endpoint_refs=request.proposal.get("endpoint_refs"),
                    evidence_refs=request.supporting_refs,
                    workspace_root=getattr(self.subagent, "working_directory", None),
                )
                # A generic verdict addresses the immutable submitted files,
                # just like directed species/step review. Supplemental decision
                # refs cannot silently substitute a different submission.
                evidence_refs = [*request.supporting_refs, *[
                    ref for ref in evidence_refs if ref not in request.supporting_refs
                ]]
                repairs = [check["next_action"] for check in scientific_checks.values()
                           if check["status"] != "passed" and check.get("next_action")]
                next_action = " ".join(dict.fromkeys([*repairs, *([next_action] if next_action else [])])) or None
            if request.kind == "exception" and user_input.verdict == "accept":
                next_action = (
                    "Administrative acceptance only: no stage was changed or waived. "
                    "Inspect the remaining scientific gaps and provide the required evidence "
                    "or use an explicitly authorized stage disposition."
                    + (f" Reviewer next action: {next_action}" if next_action else "")
                )
            decision = ReviewDecision(
                request_id=request.request_id,
                basis_fingerprint=request.basis_fingerprint,
                verdict=user_input.verdict,
                reason=user_input.reason,
                evidence_refs=evidence_refs,
                findings=user_input.findings,
                next_action=next_action,
            )
            current_basis = await asyncio.to_thread(store.review_basis, request)
            resolved = await asyncio.to_thread(
                store.resolve_review, decision,
                expected_basis=request.basis_fingerprint,
                current_basis=current_basis,
            )
        except Exception as exc:
            return fail("dag_review_evidence", str(exc), accepted=False)
        if not resolved["accepted"]:
            return DagToolOutput(
                is_success=False,
                action="dag_review_evidence",
                accepted=False,
                rejection_code=resolved["rejection_code"],
                error=resolved["rejection_reason"] or "",
                result=resolved,
            )
        resolved["stage_changed"] = False
        if scientific_checks is not None:
            resolved.update(scientific_checks=scientific_checks, next_action=decision.next_action)
        if request.kind == "exception":
            target_ids = request.target_ids
            if not target_ids:
                snapshot = await asyncio.to_thread(store.load_snapshot)
                target_ids = [*[node.node_id for node in snapshot.delivery.nodes],
                              *[edge.edge_id for edge in snapshot.delivery.edges]]
            remaining = await asyncio.to_thread(store.collect_review_exceptions, target_ids)
            remaining = [item for item in remaining if item.get("category") != "untargeted_key_fact"]
            resolved.update(
                scientific_status="unresolved" if remaining else "not_evaluated",
                remaining_gaps=remaining,
                next_action=decision.next_action,
            )
        return DagToolOutput(
            is_success=True,
            action="dag_review_evidence",
            accepted=True,
            result=resolved,
        )
