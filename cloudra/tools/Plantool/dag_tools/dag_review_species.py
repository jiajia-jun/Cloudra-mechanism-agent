"""dag_review_species: supervisor directed adjudication for a species/intermediate."""

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


class DagReviewSpeciesInput(input_schema):
    species_name: str = Field(
        description="Name of the species to adjudicate (e.g. 'R' or 'Int1')."
    )
    verdict: Literal["supported", "rejected"] = Field(
        description="Supervisor decision: 'supported' or 'rejected'."
    )
    rationale: str = Field(
        default="",
        description="Mandatory reason explaining the verdict to the proposer agent.",
    )


class DagReviewSpecies(DagToolBase):
    tool_id: str = "t-dag-review-species"
    tool_name: str = "dag_review_species"
    tool_description: str = (
        "Adjudicate the evidence submitted for a species (Supervisor only in dag_guided). "
        "Verdict must be 'supported' or 'rejected', accompanied by scientific rationale."
    )
    input_schema: Any = DagReviewSpeciesInput
    output_schema: Any = DagToolOutput
    subagent: ToolActorContext | None = None

    async def tool_call(
        self, user_input: DagReviewSpeciesInput, session: Session
    ) -> DagToolOutput:
        mode = self._mode()
        if mode is not OrchestrationMode.DAG_GUIDED:
            return fail("dag_review_species", "dag_review_species is only available in dag_guided mode", accepted=False)

        ctx = await self._prepare(session)
        if ctx.actor is not GraphActor.SUPERVISOR:
            return fail("dag_review_species", "dag_review_species is supervisor-only", accepted=False)

        # 1. Find species node in delivery graph
        snapshot = await asyncio.to_thread(ctx.store.load_snapshot)
        matching = [
            n
            for n in snapshot.delivery.nodes
            if getattr(n, "name", "") == user_input.species_name
            or getattr(n, "label", "") == user_input.species_name
            or n.node_id == user_input.species_name
        ]
        if not matching:
            return fail(
                "dag_review_species",
                f"Species '{user_input.species_name}' not found in delivery graph",
                accepted=False,
            )
        species = matching[0]
        active_review = await asyncio.to_thread(
            ReviewContextManager.get_active_review, ctx.conversation_id, ctx.db
        )
        if active_review is None:
            return fail("dag_review_species", "no active evidence review is available", accepted=False)
        if active_review.kind != "species" or active_review.target_id != species.node_id:
            return fail("dag_review_species", "active review target does not match this species", accepted=False)
        if not user_input.rationale.strip():
            return fail("dag_review_species", "a non-empty rationale is required", accepted=False)
        try:
            request = await asyncio.to_thread(
                ctx.store.get_review_request, active_review.review_id
            )
            if request is None or request.state != "queued":
                return fail("dag_review_species", "the active review request is no longer queued", accepted=False)
            if request.target_ids != [species.node_id]:
                return fail("dag_review_species", "the review request target does not match this species", accepted=False)
            if (
                "target_identity" in request.proposal
                and request.proposal["target_identity"]
                != review_target_identity(snapshot.delivery, "species", species.node_id)
            ):
                return fail("dag_review_species", "the reviewed species changed after submission", accepted=False)
            decision = ReviewDecision(
                request_id=request.request_id,
                basis_fingerprint=request.basis_fingerprint,
                verdict="accept" if user_input.verdict == "supported" else "reject",
                reason=user_input.rationale.strip(),
                evidence_refs=request.supporting_refs,
            )
            reviewed = await asyncio.to_thread(
                ctx.store.resolve_review,
                decision,
                expected_basis=request.basis_fingerprint,
            )
        except Exception as exc:
            return fail("dag_review_species", str(exc), accepted=False)
        if not reviewed["accepted"]:
            return fail("dag_review_species", reviewed.get("rejection_reason") or "review was rejected", accepted=False)
        await asyncio.to_thread(
            ReviewContextManager.clear_active_review,
            ctx.conversation_id, ctx.db, active_review.review_id,
        )
        return DagToolOutput(
            is_success=True,
            action="dag_review_species",
            accepted=True,
            result={
                "species_name": user_input.species_name,
                "verdict": user_input.verdict,
                **reviewed,
            },
        )


def get_class():
    return DagReviewSpecies
