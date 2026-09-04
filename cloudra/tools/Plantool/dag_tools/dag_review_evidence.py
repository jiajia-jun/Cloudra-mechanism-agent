"""dag_review_evidence: Supervisor resolves a structured ReviewRequest."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from cloudra.base.session_class import Session
from cloudra.base.tools_class import input_schema
from cloudra.core.agent import Agent
from cloudra.dag.models import GraphActor, GraphRef, OrchestrationMode
from cloudra.dag.review_requests import ReviewDecision
from cloudra.tools.Plantool.dag_tools._common import DagToolBase, DagToolOutput, fail


class DagReviewEvidenceInput(input_schema):
    request_id: str = Field(description="The ReviewRequest id to resolve.")
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
        "basis-matched decision. "
        "Do not use for: editing delivery graph structures directly or "
        "resolving old CallReview rows (use dag_review_call for those)."
    )
    input_schema: Any = DagReviewEvidenceInput
    output_schema: Any = DagToolOutput
    subagent: Agent = None

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
        request = store.get_review_request(user_input.request_id)
        if request is None:
            return fail(
                "dag_review_evidence",
                f"review request {user_input.request_id!r} does not exist",
            )
        if request.state != "queued":
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
            decision = ReviewDecision(
                request_id=request.request_id,
                basis_fingerprint=request.basis_fingerprint,
                verdict=user_input.verdict,
                reason=user_input.reason,
                evidence_refs=evidence_refs,
                findings=user_input.findings,
                next_action=user_input.next_action,
            )
            resolved = store.resolve_review(
                decision,
                expected_basis=request.basis_fingerprint,
                claim_token=0,
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
        return DagToolOutput(
            is_success=True,
            action="dag_review_evidence",
            accepted=True,
            result=resolved,
        )


def get_class():
    return DagReviewEvidence
