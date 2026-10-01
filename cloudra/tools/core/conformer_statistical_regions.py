"""Exploratory split search with full-search calibration and stability.

Scores are conditional on a fitted unimodal reference model, never formal
p-values. Bootstrap stability is not a test of physical basin identity.
No score threshold is used to silently mutate the accepted partition.
"""
from __future__ import annotations

from typing import Literal

import numpy as np
from pydantic import Field, model_validator

from cloudra.tools.core.conformer_catalog import CatalogModel
from cloudra.tools.core.conformer_regions import DescriptorRecord, DescriptorSpec


class StatisticalPartitionRequest(CatalogModel):
    seed: int
    resamples: int = Field(ge=1)
    coordinate_keys: list[str] | None = None
    coordinate_reasons: dict[str,str] = Field(default_factory=dict)
    additional_candidate_ids: list[str] = Field(default_factory=list)
    include_energy: bool = False
    source_catalog_id: str | None = None
    source_revision: str | None = None
    proposal_indices: list[int] | None = None
    decision_id: str | None = None
    reason: str | None = None

    @model_validator(mode='after')
    def complete_acceptance(self):
        if self.additional_candidate_ids and not self.source_catalog_id:
            raise ValueError('additional candidates require archived source revision')
        if any(not reason.strip() for reason in self.coordinate_reasons.values()):
            raise ValueError('coordinate reasons must be nonempty')
        if bool(self.source_catalog_id) != bool(self.source_revision):
            raise ValueError('complete source catalog and revision required')
        if self.proposal_indices is not None and (not self.decision_id or not self.reason or not self.reason.strip()):
            raise ValueError('acceptance decision and reason required')
        return self


class StatisticalCoordinate(CatalogModel):
    key: str
    kind: Literal['distance', 'angle', 'dihedral', 'energy']
    reason: str = Field(min_length=1)
    energy_comparison_key: str | None = None

    @model_validator(mode='after')
    def validate_source(self):
        if not self.reason.strip() or (self.kind == 'energy' and not self.energy_comparison_key):
            raise ValueError('coordinate reason and comparable energy identity required')
        return self


class SplitProposal(CatalogModel):
    coordinate: StatisticalCoordinate
    boundary: float
    circular_origin: float | None
    left_ids: list[str]
    right_ids: list[str]
    effect_fraction: float
    observed_span: float
    full_search_null_percentile: float
    split_stability: float | None
    bootstrap_boundary_interval: list[float] | None


class StatisticalPartitionEvidence(CatalogModel):
    inference_kind: Literal['exploratory'] = 'exploratory'
    formal_p_value: None = None
    candidate_ids: list[str]
    proposals: list[SplitProposal]
    null_model: str = 'joint_gaussian_linear_and_wrapped_circular_unimodal_reference'
    resampling_unit: str
    seed: int
    resamples: int
    warnings: list[str]


def _unwrap(values, circular):
    if not circular:
        return values.copy(), None
    ordered = np.sort(values % 360)
    gaps = np.diff(np.r_[ordered, ordered[0] + 360])
    origin = float(ordered[(int(np.argmax(gaps)) + 1) % len(ordered)])
    return (values - origin) % 360, origin


def _search(matrix, coordinates):
    choices = []
    for index, coordinate in enumerate(coordinates):
        values, origin = _unwrap(matrix[:, index], coordinate.kind == 'dihedral')
        total = float(np.sum((values - values.mean()) ** 2))
        if total <= np.finfo(float).eps:
            continue
        order = np.argsort(values, kind='stable')
        sorted_values = values[order]
        for cut in range(2, len(values) - 1):
            if sorted_values[cut - 1] == sorted_values[cut]:
                continue
            left, right = sorted_values[:cut], sorted_values[cut:]
            within = np.sum((left-left.mean())**2) + np.sum((right-right.mean())**2)
            score = float(np.clip(1 - within / total, 0, 1))
            boundary = float((sorted_values[cut-1]+sorted_values[cut])/2)
            choices.append((score, coordinate.key, boundary, index, origin, values <= boundary, float(np.ptp(values))))
    return sorted(choices, key=lambda choice: (-choice[0], choice[1], choice[2]))


def propose_statistical_splits(records: list[DescriptorRecord], specs: list[DescriptorSpec | StatisticalCoordinate],
                              *, seed: int, resamples: int,
                              sampling_batches: dict[str, str] | None = None) -> StatisticalPartitionEvidence:
    if resamples < 1:
        raise ValueError('explicit positive resampling count required')
    rows = sorted(records, key=lambda row: row.candidate_id)
    if len({row.candidate_id for row in rows}) != len(rows):
        raise ValueError('duplicate candidate identity')
    coordinates = sorted([spec if isinstance(spec, StatisticalCoordinate) else StatisticalCoordinate(
        key=spec.key, kind=spec.kind, reason=spec.source+": "+spec.reason) for spec in specs], key=lambda item: item.key)
    if len({c.key for c in coordinates}) != len(coordinates):
        raise ValueError('duplicate statistical coordinate')
    ids = [row.candidate_id for row in rows]
    warnings = ['sampling_independence_unverified', 'fitted_null_model_is_an_exploratory_assumption']
    unit = 'candidate_assumed_independent'
    if any(c.reason.startswith(('engineering_initial','rotatable_bond')) for c in coordinates):
        warnings.append('coordinate_relevance_unverified')
    if not rows or len(rows) < 4 or not coordinates:
        return StatisticalPartitionEvidence(candidate_ids=ids, proposals=[], seed=seed, resamples=resamples,
            resampling_unit=unit, warnings=warnings+['insufficient_samples_for_within_region_variation'])
    if any(c.key not in row.values for row in rows for c in coordinates):
        return StatisticalPartitionEvidence(candidate_ids=ids, proposals=[], seed=seed, resamples=resamples,
            resampling_unit=unit, warnings=warnings+['missing_coordinate_values'])
    matrix = np.array([[row.values[c.key] for c in coordinates] for row in rows], dtype=float)
    if not np.isfinite(matrix).all():
        raise ValueError('finite descriptor values required')
    choices = _search(matrix, coordinates)
    if not choices:
        return StatisticalPartitionEvidence(candidate_ids=ids, proposals=[], seed=seed, resamples=resamples,
            resampling_unit=unit, warnings=warnings+['no_identifiable_split'])
    # Fit the reference in each circular coordinate's contiguous arc. Each null
    # replicate reruns arc selection, every coordinate and every cutpoint.
    fitted = np.column_stack([_unwrap(matrix[:, i], c.kind == 'dihedral')[0] for i,c in enumerate(coordinates)])
    origins = [_unwrap(matrix[:, i], c.kind == 'dihedral')[1] for i,c in enumerate(coordinates)]
    covariance = np.atleast_2d(np.cov(fitted, rowvar=False))
    rng = np.random.default_rng(seed)
    null_scores, bootstrap = [], []
    groups = None
    if sampling_batches is not None:
        if set(sampling_batches) != set(ids):
            raise ValueError('complete sampling batch identities required')
        groups = [[i for i,cid in enumerate(ids) if sampling_batches[cid] == batch]
                  for batch in sorted(set(sampling_batches.values()))]
        unit = 'candidate_assumed_independent_null_and_sampling_batch_bootstrap'
        if len(groups) < 2:
            warnings.append('only_one_sampling_batch')
        warnings.append('null_reference_does_not_model_within_batch_correlation')
    for _ in range(resamples):
        draw = rng.multivariate_normal(fitted.mean(axis=0), covariance, size=len(rows))
        for i, origin in enumerate(origins):
            if origin is not None:
                draw[:, i] = (draw[:, i]+origin) % 360
        null = _search(draw, coordinates)
        null_scores.append(null[0][0] if null else 0.)
        indices = rng.integers(0,len(rows),len(rows)) if groups is None else np.concatenate(
            [groups[i] for i in rng.integers(0,len(groups),len(groups))])
        sample = _search(matrix[indices], coordinates)
        bootstrap.append(sample[0] if sample else None)
    # One best proposal per coordinate, calibrated against the maximum across
    # the entire searched family. Keep all original members in each proposal.
    proposals, seen = [], set()
    for score, key, boundary, index, origin, mask, span in choices:
        if key in seen:
            continue
        seen.add(key)
        agreement, boundaries = [], []
        for sample in bootstrap:
            if sample is None:
                agreement.append(0.)
                continue
            _, _, other_boundary, other_index, other_origin, _, _ = sample
            other_values = matrix[:,other_index] if other_origin is None else (matrix[:,other_index]-other_origin)%360
            other_mask = other_values <= other_boundary
            agreement.append(float(max(np.mean(mask==other_mask),np.mean(mask!=other_mask))))
            if other_index == index:
                # Express bootstrap boundaries in the observed arc, so ±180
                # does not inflate an interval merely because the origin moved.
                value = other_boundary if origin is None else (other_boundary+other_origin-origin)%360
                boundaries.append(value)
        proposals.append(SplitProposal(coordinate=coordinates[index], boundary=boundary,circular_origin=origin,
            left_ids=[cid for cid,keep in zip(ids,mask) if keep],right_ids=[cid for cid,keep in zip(ids,mask) if not keep],
            effect_fraction=score,observed_span=span,
            full_search_null_percentile=float((sum(s<=score for s in null_scores)+1)/(resamples+1)),
            split_stability=None if groups is not None and len(groups)<2 else float(np.mean(agreement)),
            bootstrap_boundary_interval=np.quantile(boundaries,[.025,.975]).tolist() if boundaries else None))
    return StatisticalPartitionEvidence(candidate_ids=ids,proposals=proposals,resampling_unit=unit,
        seed=seed,resamples=resamples,warnings=warnings)


def apply_statistical_partition(candidates, previous, evidence: StatisticalPartitionEvidence, *,
                                proposal_indices: list[int], decision_id: str, reason: str):
    """Accept explicit exploratory proposals as a new immutable partition.

    Acceptance is a recorded exploration decision, without a statistical
    significance claim. Species identities always remain separated.
    """
    from cloudra.tools.core.conformer_catalog import content_digest
    from cloudra.tools.core.conformer_regions import Region, partition_candidates

    ids = {c.candidate_id for c in candidates}
    if ids != set(evidence.candidate_ids) or not set(previous.descriptors)<=ids:
        raise ValueError('stale partition membership')
    if not reason.strip() or not decision_id.strip():
        raise ValueError('partition decision and reason required')
    if not proposal_indices or len(set(proposal_indices)) != len(proposal_indices):
        raise ValueError('distinct explicit proposals required')
    if any(i < 0 or i >= len(evidence.proposals) for i in proposal_indices):
        raise ValueError('unknown split proposal')
    selected = [evidence.proposals[i] for i in sorted(proposal_indices)]
    for proposal in selected:
        left, right = set(proposal.left_ids), set(proposal.right_ids)
        if not left or not right or left & right or left | right != ids:
            raise ValueError('invalid proposal membership')
        # Do not accept membership detached from the measured source coordinate.
        if proposal.coordinate.kind != 'energy':
            if proposal.coordinate.key not in {s.key for s in previous.config.descriptor_specs}:
                raise ValueError('coordinate absent from source partition')
            from cloudra.tools.core.conformer_regions import describe_candidate
            measured={c.candidate_id:describe_candidate(c,previous.config.descriptor_specs) for c in candidates}
            for cid, record in measured.items():
                value = record.values.get(proposal.coordinate.key)
                if value is None:
                    raise ValueError('coordinate measurement missing')
                if proposal.circular_origin is not None:
                    value = (value - proposal.circular_origin) % 360
                if (value <= proposal.boundary) != (cid in left):
                    raise ValueError('proposal membership disagrees with source measurements')
        else:
            values=_comparable_energy_values(candidates,proposal.coordinate.energy_comparison_key)
            if values is None or proposal.coordinate.key!='energy:'+proposal.coordinate.energy_comparison_key:
                raise ValueError('energy split lacks complete comparable observations')
            for cid,value in values.items():
                if (value<=proposal.boundary)!=(cid in left):
                    raise ValueError('energy proposal disagrees with source observations')
    base = partition_candidates(candidates, previous.config, previous=previous)
    proof = dict(evidence.model_dump(mode='json'), decision_id=decision_id, reason=reason,
                 accepted_proposal_indices=sorted(proposal_indices), source_revision=previous.revision)
    groups = {}
    for candidate in sorted(candidates, key=lambda c: c.candidate_id):
        signature = [candidate.species_key, *[candidate.candidate_id in p.left_ids for p in selected]]
        key = content_digest(signature)
        groups.setdefault(key, []).append(candidate.candidate_id)
    regions = {content_digest([proof, key]): Region(representative_id=members[0], member_ids=members)
               for key, members in groups.items()}
    mapping = {rid: sorted(newid for newid, region in regions.items()
                          if set(old.member_ids) & set(region.member_ids)) for rid, old in previous.regions.items()}
    for historical, descendants in previous.region_mapping.items():
        mapping[historical] = sorted({rid for descendant in descendants for rid in mapping.get(descendant, [])})
    return base.model_copy(update=dict(regions=regions, partition_method='exploratory_statistical_split',
        partition_evidence=proof, region_mapping=mapping,
        revision=content_digest([previous.revision, proof, {rid:r.model_dump() for rid,r in regions.items()}])))


def _comparable_energy_values(candidates, comparison_key):
    from cloudra.tools.core.conformer_catalog import content_digest
    values={}
    for candidate in candidates:
        observations=[e for e in candidate.energies if content_digest(e.comparison_key())==comparison_key and e.convergence=='converged']
        if len(observations)!=1:
            return None
        values[candidate.candidate_id]=observations[0].kcal()
    return values


def statistical_coordinates(snapshot,candidates,request: StatisticalPartitionRequest):
    """Measured geometry axes and explicitly requested comparable energy axes."""
    from cloudra.tools.core.conformer_catalog import content_digest
    specs=[s for s in snapshot.config.descriptor_specs if s.kind in ('distance','angle','dihedral')]
    if request.coordinate_keys is not None:
        if not set(request.coordinate_keys)<={s.key for s in specs}:
            raise ValueError('unknown or unsupported statistical coordinate')
        specs=[s for s in specs if s.key in request.coordinate_keys]
    coordinates=[StatisticalCoordinate(key=s.key,kind=s.kind,reason=s.source+": "+s.reason) for s in specs]
    from cloudra.tools.core.conformer_regions import describe_candidate
    if not set(request.coordinate_reasons)<={s.key for s in specs}:
        raise ValueError('coordinate reason must name a selected coordinate')
    coordinates=[c.model_copy(update={'reason':request.coordinate_reasons.get(c.key,c.reason)}) for c in coordinates]
    rows=[describe_candidate(c,snapshot.config.descriptor_specs) for c in sorted(candidates,key=lambda c:c.candidate_id)]
    warnings=[]
    if request.include_energy:
        groups=sorted({content_digest(e.comparison_key()) for c in candidates for e in c.energies if e.convergence=='converged'})
        found=False
        for group in groups:
            values=_comparable_energy_values(candidates,group)
            if values is None:
                continue
            found=True
            key='energy:'+group
            coordinates.append(StatisticalCoordinate(key=key,kind='energy',reason='explicit exploration of a complete same-method energy population',energy_comparison_key=group))
            rows=[r.model_copy(update={'values':dict(r.values,**{key:values[r.candidate_id]})}) for r in rows]
        if not found:
            warnings.append('no_complete_comparable_converged_energy_axis')
    return rows,coordinates,warnings
