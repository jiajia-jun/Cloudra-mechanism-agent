"""dag_review_step: supervisor directed adjudication for an elementary step."""

from __future__ import annotations

import uuid
from typing import Any, Literal

from pydantic import Field

from cloudra.base.session_class import Session
from cloudra.base.tool_actor import ToolActorContext
from cloudra.base.tools_class import input_schema
from cloudra.dag.models import (
    GraphActor,
    OrchestrationMode,
    UpdateEdge,
)
from cloudra.dag.review_context import ReviewContextManager
from cloudra.dag.review_requests import ReviewDecision
from cloudra.tools.Plantool.dag_tools._common import (
    DagToolBase,
    DagToolOutput,
    apply_mutation,
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
        "Verdict must be 'supported' or 'rejected', accompanied by scientific rationale."
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
        snapshot = ctx.store.load_snapshot()
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
        if user_input.verdict in (
            "supported",
            "saddle_supported",
            "endpoint_supported",
            "structure_supported",
            "thermo_annotated",
        ):
            return fail(
                "dag_review_step",
                "dag_review_step cannot write derived evidence_level; "
                "bind stages with dag_review_call or dag_bind_evidence",
                accepted=False,
            )

        # 2. Apply status update to step in delivery graph
        changes = {
            "status": user_input.verdict,
            "evidence_level": user_input.verdict,
            "reason": user_input.rationale,
        }
        mutation = apply_mutation(
            ctx.store,
            ctx.engine,
            session_id=session.id,
            actor=GraphActor.HARNESS,
            actor_id="supervisor",
            operations=[
                UpdateEdge(
                    op="update_edge",
                    graph="delivery",
                    edge_id=step.edge_id,
                    changes=changes,
                )
            ],
            rationale=f"Supervisor review: step {user_input.step_name} -> {user_input.verdict}",
        )
        if not mutation.accepted:
            return fail(
                "dag_review_step",
                mutation.rejection_reason or "Failed to record step verdict",
                accepted=False,
            )

        # 3. Resolve active review and record decision
        active_review = ReviewContextManager.get_active_review(ctx.conversation_id, db=ctx.db)
        if active_review:
            try:
                decision = ReviewDecision(
                    decision_id=f"dec_{uuid.uuid4().hex}",
                    request_id=active_review.review_id,
                    basis_fingerprint=active_review.basis_fingerprint or "default",
                    verdict="accept" if user_input.verdict == "supported" else "reject",
                    reason=user_input.rationale or user_input.verdict,
                )
                ctx.store.record_review_decision(decision)
            except Exception:
                pass
            ReviewContextManager.clear_active_review(
                ctx.conversation_id, db=ctx.db, request_id=active_review.review_id
            )

        return DagToolOutput(
            is_success=True,
            action="dag_review_step",
            accepted=True,
            result={
                "step_name": user_input.step_name,
                "verdict": user_input.verdict,
                "rationale": user_input.rationale,
                "message": f"Step '{user_input.step_name}' adjudicated as {user_input.verdict}.",
            },
        )


def get_class():
    return DagReviewStep
