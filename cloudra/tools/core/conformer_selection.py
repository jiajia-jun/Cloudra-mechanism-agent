"""Evidence-aware choices; this module never submits or cancels computation."""
from __future__ import annotations

from typing import Literal

from pydantic import Field, field_validator

from cloudra.tools.core.conformer_cards import AttemptEvidence, RegionCard
from cloudra.tools.core.conformer_catalog import CatalogModel, content_digest


class SamplingRequest(CatalogModel):
    method: Literal['independent_rigid_fragments', 'ETKDGv3']
    count: int = Field(ge=1)
    seed: int


class SelectionDecision(CatalogModel):
    decision_id: str
    catalog_id: str
    partition_revision: str
    declaration_hash: str
    status: Literal['ready', 'blocked', 'stopped'] = 'ready'
    action: Literal['select_candidate', 'refine_representative', 'supplement_sampling', 'propose_adjustment', 'stop'] = 'select_candidate'
    candidate_id: str | None = None
    region_id: str | None = None
    reason: str = Field(min_length=1)
    evidence_refs: list[str] = Field(default_factory=list)
    reuse_job_id: int | None = None
    blocked_reason: str | None = None
    sampling: SamplingRequest | None = None

    @field_validator('reason')
    @classmethod
    def meaningful_reason(cls, value):
        if not value.strip():
            raise ValueError('nonempty decision reason required')
        return value



class SelectionContext(CatalogModel):
    project_id: str
    owner_id: str
    catalog_id: str
    partition_revision: str
    declaration_hash: str
    method_fingerprint: str
    cards: list[RegionCard]
    attempts: list[AttemptEvidence] = Field(default_factory=list)
    chemical_ambiguities: list[str] = Field(default_factory=list)
    budget_available: bool = True


def _decision(context: SelectionContext, **fields) -> SelectionDecision:
    identity = dict(catalog_id=context.catalog_id,partition_revision=context.partition_revision,
                    declaration_hash=context.declaration_hash,**fields)
    return SelectionDecision(decision_id=content_digest(identity), **identity)


def select_default(cards: list[RegionCard], context: SelectionContext) -> SelectionDecision:
    if cards != context.cards:
        raise ValueError('selection cards differ from validated context')
    if context.chemical_ambiguities:
        return _decision(context,status='blocked',reason='; '.join(context.chemical_ambiguities),blocked_reason='chemical_decision_needed')
    for attempt in context.attempts:
        if attempt.failure_class == 'infrastructure' and attempt.job_id is not None:
            for card in cards:
                if attempt.candidate_id in card.candidate_ids:
                    return validate_selection(_decision(context,candidate_id=attempt.candidate_id,region_id=card.region_id,
                                     reuse_job_id=attempt.job_id,reason='Reconcile existing job before new chemistry',
                                     evidence_refs=card.evidence_refs), context)
    if not context.budget_available:
        return _decision(context,status="blocked",reason="No authorized budget for new action",blocked_reason="budget_exhausted")
    attempted_regions = {card.region_id for card in cards if card.attempts or
                         any(a.candidate_id in card.candidate_ids for a in context.attempts)}
    failed_candidates = {a.candidate_id for a in context.attempts if a.failure_class != 'infrastructure'}
    options = [(card, choice) for card in cards for choice in card.choices
               if choice.candidate_id not in failed_candidates and choice.state not in ('failed','rejected')
               and choice.qualification.status != 'rejected']
    keys = {choice.energy_key for _,choice in options}
    compare_energy = len(keys) == 1 and None not in keys
    options.sort(key=lambda pair: (pair[1].qualification.status != 'qualified',
                                  pair[0].region_id in attempted_regions,
                                  pair[1].relative_kcal if compare_energy else 0,
                                  pair[1].candidate_id))
    if not options:
        return _decision(context,status='blocked',reason='No untried eligible choice; inspect coverage or declaration',blocked_reason='choices_exhausted')
    card, choice = options[0]
    return validate_selection(_decision(context,candidate_id=choice.candidate_id,region_id=card.region_id,
                          action='select_candidate' if choice.qualification.status == 'qualified' else 'refine_representative',
                          reason='Preserve eligibility and structural coverage; compare only compatible energies',
                          evidence_refs=card.evidence_refs), context)


def validate_selection(decision: SelectionDecision, context: SelectionContext) -> SelectionDecision:
    if (decision.catalog_id,decision.partition_revision,decision.declaration_hash) != (
            context.catalog_id,context.partition_revision,context.declaration_hash):
        raise ValueError('stale decision or declaration')
    if decision.action == 'stop':
        return decision.model_copy(update={'status': 'stopped', 'blocked_reason': 'incomplete'})
    if decision.status != 'ready':
        return decision
    if decision.reuse_job_id is not None and decision.action not in ('select_candidate', 'refine_representative'):
        raise ValueError('job reuse is only allowed for validated candidate reconciliation')
    if decision.action == 'supplement_sampling':
        if decision.sampling is None:
            raise ValueError('supported sampling request required')
        known_refs = {ref for card in context.cards for ref in card.evidence_refs}
        if not decision.evidence_refs or not set(decision.evidence_refs) <= known_refs:
            raise ValueError('sampling request needs current coverage evidence')
    if decision.action == 'propose_adjustment':
        return decision.model_copy(update={'status': 'blocked', 'blocked_reason': 'explicit_declaration_adjustment_required'})
    if not context.budget_available and decision.action != 'stop' and decision.reuse_job_id is None:
        raise ValueError('budget unavailable')
    if decision.action in ('select_candidate','refine_representative'):
        card = next((c for c in context.cards if c.region_id == decision.region_id and decision.candidate_id in c.candidate_ids), None)
        if card is None or (card.project_id,card.owner_id,card.catalog_id,card.revision) != (
                context.project_id,context.owner_id,context.catalog_id,context.partition_revision):
            raise ValueError('foreign candidate or stale card')
        if not decision.evidence_refs or not set(decision.evidence_refs) <= set(card.evidence_refs):
            raise ValueError('decision requires current evidence')
        choice = next(c for c in card.choices if c.candidate_id == decision.candidate_id)
        if choice.qualification.status == 'rejected' or choice.state in ('failed','rejected'):
            raise ValueError('candidate rejected')
        if decision.action == 'select_candidate' and choice.qualification.status != 'qualified' and decision.reuse_job_id is None:
            raise ValueError('candidate must be qualified before TS selection')
        relevant = [a for a in context.attempts if a.candidate_id == decision.candidate_id]
        if decision.reuse_job_id is not None:
            if not any(a.job_id == decision.reuse_job_id and a.failure_class == 'infrastructure' for a in relevant):
                raise ValueError('job reuse lacks ownership/evidence')
        elif any(a.failure_class != 'infrastructure' for a in relevant):
            raise ValueError('same failed input cannot be requeued')
    return decision
