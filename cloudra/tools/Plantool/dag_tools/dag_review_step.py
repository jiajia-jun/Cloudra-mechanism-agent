"""dag_review_step: supervisor directed adjudication for an elementary step."""

from __future__ import annotations

import asyncio
from typing import Any, Literal

from pydantic import Field

from cloudra.base.session_class import Session
from cloudra.base.tool_actor import ToolActorContext
from cloudra.base.tools_class import input_schema
from cloudra.dag.models import (
    GraphActor,
    OrchestrationMode,
)
from cloudra.dag.review_context import ReviewContextManager, review_target_identity
from cloudra.dag.review_requests import ReviewDecision
from cloudra.tools.Plantool.dag_tools._common import (
    DagToolBase,
    DagToolOutput,
    fail,
)


class DagReviewStepInput(input_schema):
    step_name: str = Field(
        description="Name of the elementary step to adjudicate (e.g. 'step1')."
    )
    verdict: Literal["supported", "rejected"] = Field(
        description="Supervisor decision: 'supported' or 'rejected'."
    )
    rationale: str = Field(
        default="",
        description="Mandatory reason explaining the verdict to the proposer agent.",
    )


class DagReviewStep(DagToolBase):
    tool_id: str = "t-dag-review-step"
    tool_name: str = "dag_review_step"
    tool_description: str = (
        "Adjudicate the evidence submitted for an elementary step (Supervisor only in dag_guided). "
        "'supported' records your review acceptance; it cannot override failed or incomplete scientific checks. Read scientific_checks and next_action with dag_view_evidence. "
        "Default steps still require short_irc: accepting TS/frequency evidence alone leaves the IRC delivery gap open. "
        "'rejected' leaves an open gap. A scientific rationale is required."
    )
    input_schema: Any = DagReviewStepInput
    output_schema: Any = DagToolOutput
    subagent: ToolActorContext | None = None

    async def tool_call(
        self, user_input: DagReviewStepInput, session: Session
    ) -> DagToolOutput:
        mode = self._mode()
        if mode is not OrchestrationMode.DAG_GUIDED:
            return fail("dag_review_step", "dag_review_step is only available in dag_guided mode", accepted=False)

        ctx = await self._prepare(session)
        if ctx.actor is not GraphActor.SUPERVISOR:
            return fail("dag_review_step", "dag_review_step is supervisor-only", accepted=False)

        # 1. Find step edge in delivery graph
        snapshot = await asyncio.to_thread(ctx.store.load_snapshot)
        matching = [
            e
            for e in snapshot.delivery.edges
            if getattr(e, "name", "") == user_input.step_name
            or getattr(e, "label", "") == user_input.step_name
            or e.edge_id == user_input.step_name
        ]
        if not matching:
            return fail(
                "dag_review_step",
                f"Step '{user_input.step_name}' not found in delivery graph",
                accepted=False,
            )
        step = matching[0]
        active_review = await asyncio.to_thread(
            ReviewContextManager.get_active_review, ctx.conversation_id, ctx.db
        )
        if active_review is None:
            return fail("dag_review_step", "no active evidence review is available", accepted=False)
        if active_review.kind != "step" or active_review.target_id != step.edge_id:
            return fail("dag_review_step", "active review target does not match this step", accepted=False)
        if not user_input.rationale.strip():
            return fail("dag_review_step", "a non-empty rationale is required", accepted=False)
        try:
            request = await asyncio.to_thread(
                ctx.store.get_review_request, active_review.review_id
            )
            if request is None or request.state != "queued":
                return fail("dag_review_step", "the active review request is no longer queued", accepted=False)
            if request.target_ids != [step.edge_id]:
                return fail("dag_review_step", "the review request target does not match this step", accepted=False)
            if (
                "target_identity" in request.proposal
                and request.proposal["target_identity"]
                != review_target_identity(snapshot.delivery, "step", step.edge_id)
            ):
                return fail("dag_review_step", "the reviewed step changed after submission", accepted=False)
            from cloudra.dag.file_science import file_scientific_checks
            scientific_checks = await asyncio.to_thread(
                file_scientific_checks, ctx.store, snapshot.delivery, step.edge_id, irc_files=request.proposal.get("irc_files"),
                workspace_root=getattr(self.subagent, "working_directory", None))
            pending = {stage.kind.value for stage in step.stages if stage.required and stage.status.value == "pending"}
            repairs = [check["next_action"] for stage, check in scientific_checks.items()
                       if stage in pending and check["status"] != "passed"]
            decision = ReviewDecision(
                request_id=request.request_id,
                basis_fingerprint=request.basis_fingerprint,
                verdict="accept" if user_input.verdict == "supported" else "reject",
                reason=user_input.rationale.strip(),
                evidence_refs=request.supporting_refs,
                next_action=" ".join(dict.fromkeys(repairs)) or None,
            )
            reviewed = await asyncio.to_thread(
                ctx.store.resolve_review,
                decision,
                expected_basis=request.basis_fingerprint,
            )
        except Exception as exc:
            return fail("dag_review_step", str(exc), accepted=False)
        if not reviewed["accepted"]:
            return fail("dag_review_step", reviewed.get("rejection_reason") or "review was rejected", accepted=False)
        await asyncio.to_thread(
            ReviewContextManager.clear_active_review,
            ctx.conversation_id, ctx.db, active_review.review_id,
        )
        return DagToolOutput(
            is_success=True,
            action="dag_review_step",
            accepted=True,
            result={
                "step_name": user_input.step_name,
                "verdict": user_input.verdict,
                "scientific_checks": scientific_checks,
                **reviewed,
            },
        )
