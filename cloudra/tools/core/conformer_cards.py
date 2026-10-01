"""Evidence-linked, paginated region cards for deterministic or agent selection."""
from __future__ import annotations

from typing import Literal

from pydantic import Field

from cloudra.tools.core.conformer_catalog import (
    CandidateRecord,
    CatalogModel,
    Qualification,
    content_digest,
    relative_energies,
)
from cloudra.tools.core.conformer_regions import RegionConfig, RegionSnapshot, candidate_lineage


class AttemptEvidence(CatalogModel):
    candidate_id: str
    region_id: str
    stage: str
    input_hash: str
    failure_class: Literal['none', 'geometry', 'path_failed', 'nonconvergence', 'wrong_mode', 'endpoint_identity', 'infrastructure', 'unclassified_failure']
    job_id: int | None = None
    evidence_refs: list[str]


class Measurement(CatalogModel):
    candidate_id: str
    kind: str
    atom_ids: list[str]
    value: float
    unit: str
    evidence_ref: str


class SemanticLabel(CatalogModel):
    text: str
    evidence_ref: str


class CandidateChoice(CatalogModel):
    candidate_id: str
    qualification: Qualification
    energy_key: str | None = None
    relative_kcal: float | None = None
    state: str


class RegionCard(CatalogModel):
    project_id: str
    owner_id: str
    catalog_id: str
    region_id: str
    revision: str
    partition_method: Literal['fixed_tolerance_baseline', 'exploratory_statistical_split'] = 'fixed_tolerance_baseline'
    partition_evidence: dict = Field(default_factory=dict)
    partition_config: RegionConfig
    candidate_ids: list[str]
    choices: list[CandidateChoice]
    measurements: list[Measurement]
    labels: list[SemanticLabel]
    evidence_refs: list[str]
    attempts: list[AttemptEvidence]
    unknowns: list[str]


class CardPage(CatalogModel):
    total_regions: int
    cards: list[RegionCard]
    omitted_region_ids: list[str]
    next_offset: int | None


def build_region_cards(snapshot: RegionSnapshot, candidates: list[CandidateRecord],
                       attempts: list[AttemptEvidence]) -> list[RegionCard]:
    by_id = {c.candidate_id: c for c in candidates}
    if set(by_id) != set(snapshot.descriptors):
        raise ValueError('candidate/snapshot membership mismatch')
    if len({(c.catalog_id, c.project_id, c.owner_id) for c in candidates}) != 1:
        raise ValueError('candidate scope mismatch')
    energy_groups = {}
    for cid, c in by_id.items():
        # Multiple observations are retained, but a choice has only its latest converged observation.
        valid = [e for e in c.energies if e.convergence == 'converged']
        if valid:
            obs = valid[-1]
            energy_groups.setdefault(content_digest(obs.comparison_key()), {})[cid] = obs
    energy_values = {}
    for key, group in energy_groups.items():
        for cid, value in relative_energies(group).items():
            energy_values[cid] = (key, value)
    cards = []
    for rid, region in sorted(snapshot.regions.items()):
        measurements, labels, refs, unknowns, choices = [], [], [], [], []
        for cid in region.member_ids:
            candidate = by_id[cid]
            desc = snapshot.descriptors[cid]
            for spec in snapshot.config.descriptor_specs:
                if spec.key in desc.values:
                    value = desc.values[spec.key]
                    ref = f'{snapshot.revision}/{cid}/{spec.key}'
                    measurements.append(Measurement(candidate_id=cid, kind=spec.kind,atom_ids=spec.stable_atom_ids,
                                                    value=value, unit=spec.unit,evidence_ref=ref))
                    labels.append(SemanticLabel(text=f'{spec.kind} {",".join(spec.stable_atom_ids)} = {value:.3f} {spec.unit}', evidence_ref=ref))
                    refs.append(ref)
                else:
                    unknowns.append(f'{cid}/{spec.key}: {desc.missing.get(spec.key, "not measured")}')
            key, energy = energy_values.get(cid, (None, None))
            if key is None:
                unknowns.append('energy unmeasured')
            refs.extend(candidate.qualification.evidence_refs)
            refs.append(f'candidate:{cid}')
            choices.append(CandidateChoice(candidate_id=cid,qualification=candidate.qualification,
                                           energy_key=key,relative_kcal=energy,state=candidate.state))
        ancestors = set().union(*(set(snapshot.candidate_ancestry.get(cid, [])) | candidate_lineage(cid, by_id) for cid in region.member_ids))
        exemplar = by_id[region.representative_id]
        cards.append(RegionCard(project_id=exemplar.project_id,owner_id=exemplar.owner_id,catalog_id=exemplar.catalog_id,
                                region_id=rid,revision=snapshot.revision,partition_config=snapshot.config,candidate_ids=region.member_ids,
                                partition_method=snapshot.partition_method, partition_evidence=snapshot.partition_evidence,
                                choices=choices,measurements=measurements,labels=labels,evidence_refs=sorted(set(refs)),
                                attempts=[a for a in attempts if a.candidate_id in ancestors],unknowns=sorted(set(unknowns))))
    return cards


def paginate_cards(cards: list[RegionCard], *, offset: int = 0, limit: int = 20) -> CardPage:
    if offset < 0 or limit < 1:
        raise ValueError('positive limit and nonnegative offset required')
    page = cards[offset:offset+limit]
    shown = {c.region_id for c in page}
    return CardPage(total_regions=len(cards),cards=page,omitted_region_ids=[c.region_id for c in cards if c.region_id not in shown],
                    next_offset=offset+limit if offset+limit < len(cards) else None)
