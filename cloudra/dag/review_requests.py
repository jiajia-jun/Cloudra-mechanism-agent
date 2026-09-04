"""Structured review requests and decisions (contract_version=2).

This is the persistent protocol between research Agents and the Supervisor.
It replaces ad-hoc CallReview trigger strings with scoped, versioned requests:
a request carries target ids, a question, supporting/counter evidence, a
proposal, and a ``basis_fingerprint`` computed from the relevant evidence and
graph state.  A decision is accepted only when its basis still matches.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from cloudra.dag.models import GraphRef

ReviewKind = Literal["draft", "evidence", "exception", "exit"]
Verdict = Literal["accept", "reject", "needs_evidence"]
RequestState = Literal["queued", "resolved", "superseded"]


class ReviewRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    request_id: str = ""
    kind: ReviewKind
    requester: str = Field(min_length=1)
    target_ids: list[str] = Field(default_factory=list)
    question: str = Field(min_length=1)
    supporting_refs: list[GraphRef] = Field(default_factory=list)
    counterevidence_refs: list[GraphRef] = Field(default_factory=list)
    proposal: dict[str, Any] = Field(default_factory=dict)
    basis_fingerprint: str = Field(min_length=1)
    state: RequestState = "queued"
    created_at: str = ""
    updated_at: str = ""


class ReviewDecision(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    decision_id: str = ""
    request_id: str = Field(min_length=1)
    basis_fingerprint: str = Field(min_length=1)
    verdict: Verdict
    reason: str = Field(min_length=1)
    evidence_refs: list[GraphRef] = Field(default_factory=list)
    findings: list[dict[str, Any]] = Field(default_factory=list)
    next_action: str | None = None

    @field_validator("findings")
    @classmethod
    def _findings_shape(cls, value: list[dict[str, Any]]) -> list[dict[str, Any]]:
        for item in value:
            missing = {"target_id", "check", "outcome", "reason"} - set(item)
            if missing:
                raise ValueError(
                    "each finding requires target_id/check/outcome/reason; "
                    f"missing {sorted(missing)}"
                )
        return value


def scope_key(request: ReviewRequest) -> tuple[str, tuple[str, ...]]:
    """A stable identity for dedup: kind + sorted targets.

    Evidence fingerprint is intentionally not part of this key; it is stored in
    basis_fingerprint so a new contradiction produces a different request even
    when the human-readable question repeats.
    """
    return (request.kind, tuple(sorted(request.target_ids)))
