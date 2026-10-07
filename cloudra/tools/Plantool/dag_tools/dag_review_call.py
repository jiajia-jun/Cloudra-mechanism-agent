"""dag_review_call: supervisor-only per-call stage bind verdict."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from cloudra.base.session_class import Session
from cloudra.base.tool_actor import ToolActorContext
from cloudra.base.tools_class import input_schema
from cloudra.dag.controller import DagController
from cloudra.dag.models import GraphActor, OrchestrationMode
from cloudra.tools.Plantool.dag_tools._common import DagToolBase, DagToolOutput, fail


class DagReviewCallInput(input_schema):
    review_id: str = Field(
        description="The pending CallReview id from the review inbox."
    )
    target_id: str = Field(
        description="Delivery node or edge id the call is evidence for."
    )
    stage_kind: str = Field(
        description=(
            "The declared stage this verdict binds — one of geometry, "
            "frequency, single_point, ts_guess, ts_opt, short_irc, endpoint_a, "
            "endpoint_b, direction, identity, thermochemistry. ts_guess is "
            "advisory and never satisfies ts_opt/frequency."
        ),
    )
    verdict: Literal["agree", "disagree", "skip", "not_applicable", "needs_evidence", "ignore"] = Field(
        description=(
            "agree binds the call's evidence to the stage (order and harness "
            "checks apply); disagree marks the stage rejected (reason "
            "required, the stage is still owed — it is NOT a disposal); "
            "skip marks it skipped (reason required, counts as disposed — "
            "the stage COULD be computed but you choose not to); "
            "not_applicable marks the slot as not applying to this element "
            "(reason required, counts as complete — e.g. a barrierless step "
            "has no ts_opt/frequency, a unimolecular step has no endpoint_b "
            "complex); needs_evidence closes this round WITHOUT a stage "
            "change when the submitted snapshot cannot answer the claim "
            "(reason required — list exactly which evidence is missing; the "
            "submitter re-submits with the missing material); ignore means "
            "the call is not delivery evidence (no stage change)."
        ),
    )
    reason: str = Field(
        default="",
        description=(
            "Mandatory for disagree/skip/not_applicable/needs_evidence; "
            "recorded with the stage. For needs_evidence, name the concrete "
            "missing evidence (which log/calculation/check would answer the "
            "claim)."
        ),
    )


class DagReviewCall(DagToolBase):
    tool_id: str = "t-dag-review-call"
    tool_name: str = "dag_review_call"
    tool_description: str = (
        "Adjudicate one pending CallReview — an explicit evidence submission "
        "carrying the submitter's claim (what the evidence is claimed to "
        "prove for a specific target + stage) — and bind its stage verdict "
        "(Supervisor only in dag_guided; disabled in dag_record, where the "
        "Coordinator self-binds via dag_bind_evidence). The verdict must "
        "answer the claim AS SUBMITTED (target/stage are fixed by the "
        "submission) and is judged against the immutable snapshot taken at "
        "submission time (dag_view_evidence reads that snapshot, never the "
        "live file). "
        "Use for: reviewing a pending CallReview against a delivery element's "
        "stage contract. "
        "Do not use for: binding submit_compute_job calls (submit is never "
        "evidence), skipping stages out of order, treating disagree as a "
        "disposal — a rejected stage stays an open gap until re-bound or "
        "explicitly skipped/not_applicable with a reason — or re-adjudicating "
        "a claim with a different target/stage (ask for a re-submission). "
        "Key discipline: the harness resolves and validates the evidence ref "
        "from the review's submitted snapshot; the verdict only decides the stage."
    )
    input_schema: Any = DagReviewCallInput
    output_schema: Any = DagToolOutput
    subagent: ToolActorContext | None = None

    async def tool_call(
        self, user_input: DagReviewCallInput, session: Session
    ) -> DagToolOutput:
        mode = self._mode()
        if mode is OrchestrationMode.STANDARD:
            return self._standard_disabled()
        if mode is OrchestrationMode.DAG_RECORD:
            return fail(
                "dag_review_call",
                "disabled in dag_record (the Supervisor is offline); the "
                "Coordinator binds stages with dag_bind_evidence",
                accepted=False,
            )
        ctx = await self._prepare(session)
        if ctx.actor is not GraphActor.SUPERVISOR:
            return fail(
                "dag_review_call",
                "review_call is supervisor-only; stage verdicts are applied "
                "deterministically by the harness after review",
            )
        controller = DagController(
            ctx.db, session.id, ctx.mode, conversation_id=ctx.conversation_id
        )
        try:
            reviewed = await controller.review_call(
                review_id=user_input.review_id,
                target_id=user_input.target_id,
                stage_kind=user_input.stage_kind,
                verdict=user_input.verdict,
                reason=user_input.reason,
            )
        except Exception as exc:
            # review 缺失/已裁决/证据缺失等确定性拒绝，原文回报给模型自纠
            return fail("dag_review_call", str(exc), accepted=False)
        if not reviewed["accepted"]:
            return DagToolOutput(
                is_success=False,
                action="dag_review_call",
                accepted=False,
                rejection_code=reviewed["rejection_code"],
                error=reviewed["rejection_reason"] or "",
                result=reviewed,
            )
        return DagToolOutput(
            is_success=True,
            action="dag_review_call",
            accepted=True,
            result=reviewed,
        )
