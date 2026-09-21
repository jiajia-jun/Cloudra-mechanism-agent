"""dag_review_species: supervisor directed adjudication for a species/intermediate."""

from __future__ import annotations

import uuid
from typing import Any, Literal

from pydantic import Field

from cloudra.base.session_class import Session
from cloudra.base.tools_class import input_schema
from cloudra.core.agent import Agent
from cloudra.dag.models import (
    GraphActor,
    OrchestrationMode,
    UpdateNode,
)
from cloudra.dag.review_context import ReviewContextManager
from cloudra.dag.review_requests import ReviewDecision
from cloudra.tools.Plantool.dag_tools._common import (
    DagToolBase,
    DagToolOutput,
    apply_mutation,
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
    subagent: Agent = None

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
        snapshot = ctx.store.load_snapshot()
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
        if user_input.verdict in (
            "supported",
            "saddle_supported",
            "endpoint_supported",
            "structure_supported",
            "thermo_annotated",
        ):
            return fail(
                "dag_review_species",
                "dag_review_species cannot write derived evidence_level; "
                "bind stages with dag_review_call or dag_bind_evidence",
                accepted=False,
            )

        # 2. Apply status update to species in delivery graph
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
                UpdateNode(
                    op="update_node",
                    graph="delivery",
                    node_id=species.node_id,
                    changes=changes,
                )
            ],
            rationale=f"Supervisor review: species {user_input.species_name} -> {user_input.verdict}",
        )
        if not mutation.accepted:
            return fail(
                "dag_review_species",
                mutation.rejection_reason or "Failed to record species verdict",
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
            action="dag_review_species",
            accepted=True,
            result={
                "species_name": user_input.species_name,
                "verdict": user_input.verdict,
                "rationale": user_input.rationale,
                "message": f"Species '{user_input.species_name}' adjudicated as {user_input.verdict}.",
            },
        )


def get_class():
    return DagReviewSpecies
