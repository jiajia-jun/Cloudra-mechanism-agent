"""Recorded-policy comparison. Unknown branches never acquire invented outcomes."""
from __future__ import annotations

from typing import Literal

from pydantic import Field

from cloudra.tools.core.conformer_catalog import CatalogModel, content_digest
from cloudra.tools.core.conformer_selection import SelectionContext, SelectionDecision, validate_selection


class ReplayObservation(CatalogModel):
    outcome: Literal['verified','failed','incomplete']
    validation_standard: str
    method_fingerprint: str
    evidence_refs: list[str]
    source_kind: Literal['synthetic','recorded_engine']
    allocated_cpu_hours: float | None = Field(default=None,ge=0)


class ModelTelemetry(CatalogModel):
    calls: int = Field(ge=0)
    tokens: int | None = Field(default=None,ge=0)
    monetary_cost: float | None = Field(default=None,ge=0)
    source: str


class ReplayReport(CatalogModel):
    policy_name: str
    budget: int
    evidence_digest: str
    outcome: Literal['unknown','recorded_verified','synthetic_verified','incomplete']
    actions_requested: int
    reused_jobs: int
    region_ids: list[str]
    actual_cpu_hours: float | None
    fixture_cpu_hours: float | None
    model_calls: int | None
    model_tokens: int | None
    model_monetary_cost: float | None
    incomplete_reason: str | None


def replay_policy(context: SelectionContext, decisions: list[SelectionDecision],
                  observations: dict[str, ReplayObservation], *, max_actions: int,
                  validation_standard: str, policy_name: str,
                  model_telemetry: ModelTelemetry | None = None) -> ReplayReport:
    if max_actions < 0:
        raise ValueError('nonnegative explicit budget required')
    for observation in observations.values():
        if observation.validation_standard != validation_standard:
            raise ValueError('validation standard mismatch')
        if observation.method_fingerprint != context.method_fingerprint:
            raise ValueError('method mismatch')
        if not observation.evidence_refs:
            raise ValueError('recorded outcome needs evidence')
    context = context.model_copy(deep=True)
    count, reused, measured, fixture = 0, 0, [], []
    regions, seen, seen_jobs = set(), {}, set()
    outcome, reason = 'incomplete', 'no_verified_record'
    for raw in decisions:
        if raw.decision_id in seen:
            if raw!=seen[raw.decision_id]:
                raise ValueError('decision id conflict')
            continue
        decision = validate_selection(raw, context)
        seen[decision.decision_id]=raw
        if decision.status != 'ready':
            reason = decision.blocked_reason
            break
        if decision.reuse_job_id is not None:
            if decision.reuse_job_id in seen_jobs:
                continue
            seen_jobs.add(decision.reuse_job_id)
            reused += 1
        else:
            if count >= max_actions:
                reason = 'budget_exhausted'
                break
            count += 1
        if decision.region_id:
            regions.add(decision.region_id)
        observation = observations.get(decision.candidate_id)
        if observation is None:
            outcome,reason = 'unknown','unmeasured_branch'
            break
        (measured if observation.source_kind == 'recorded_engine' else fixture).append(observation.allocated_cpu_hours)
        if observation.outcome == 'failed':
            from cloudra.tools.core.conformer_cards import AttemptEvidence
            context.attempts.append(AttemptEvidence(candidate_id=decision.candidate_id,
                region_id=decision.region_id or '', stage='replay', input_hash=decision.candidate_id,
                failure_class='path_failed', job_id=decision.reuse_job_id,
                evidence_refs=observation.evidence_refs))
        if observation.outcome == 'verified':
            outcome = 'recorded_verified' if observation.source_kind == 'recorded_engine' else 'synthetic_verified'
            reason = None
            break
    return ReplayReport(policy_name=policy_name,budget=max_actions,
                         evidence_digest=content_digest({k:v.model_dump() for k,v in observations.items()}),
                         outcome=outcome,actions_requested=count,reused_jobs=reused,region_ids=sorted(regions),
                         actual_cpu_hours=sum(measured) if measured and all(v is not None for v in measured) else None,
                         fixture_cpu_hours=sum(fixture) if fixture and all(v is not None for v in fixture) else None,
                         model_calls=model_telemetry.calls if model_telemetry else None,
                         model_tokens=model_telemetry.tokens if model_telemetry else None,
                         model_monetary_cost=model_telemetry.monetary_cost if model_telemetry else None,
                         incomplete_reason=reason)
