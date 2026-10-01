"""Versioned structural regions. Energies never determine region membership."""
from __future__ import annotations

import math
from typing import Literal

import numpy as np
from pydantic import Field, model_validator

from cloudra.tools.core.conformer_catalog import CandidateRecord, CatalogModel, content_digest


class DescriptorSpec(CatalogModel):
    kind: Literal['distance', 'angle', 'dihedral', 'ring', 'fragment_pose']
    stable_atom_ids: list[str]
    tolerance: float | None = None
    unit: str = ''
    source: str = 'engineering_initial'
    reason: str = 'Explicit structural descriptor; relevance requires the recorded declaration'
    required: bool = True

    @model_validator(mode='after')
    def validate_spec(self):
        n = {'distance': 2, 'angle': 3, 'dihedral': 4}.get(self.kind)
        if n and (len(self.stable_atom_ids) != n or len(set(self.stable_atom_ids)) != n):
            raise ValueError('descriptor needs distinct atom identities of correct length')
        tol = self.tolerance if self.tolerance is not None else {'distance': 0.5, 'angle': 15, 'dihedral': 30}.get(self.kind, 1)
        if tol <= 0 or not math.isfinite(tol):
            raise ValueError('descriptor tolerance must be positive and finite')
        unit = 'angstrom' if self.kind == 'distance' else 'degree' if self.kind in ('angle', 'dihedral') else 'unsupported'
        if self.unit and self.unit != unit:
            raise ValueError('descriptor unit mismatch')
        object.__setattr__(self, 'tolerance', tol)
        object.__setattr__(self, 'unit', unit)
        return self

    @property
    def key(self) -> str:
        return content_digest([self.kind, self.stable_atom_ids])


class RegionConfig(CatalogModel):
    version: int = Field(default=1, ge=1)
    descriptor_specs: list[DescriptorSpec]

    @model_validator(mode='after')
    def no_duplicates(self):
        if len({s.key for s in self.descriptor_specs}) != len(self.descriptor_specs):
            raise ValueError('duplicate descriptors')
        return self


class DescriptorRecord(CatalogModel):
    candidate_id: str
    values: dict[str, float] = Field(default_factory=dict)
    missing: dict[str, str] = Field(default_factory=dict)


class Region(CatalogModel):
    representative_id: str
    member_ids: list[str]


class RegionSnapshot(CatalogModel):
    catalog_id: str
    revision: str
    config: RegionConfig
    regions: dict[str, Region]
    descriptors: dict[str, DescriptorRecord]
    previous_revision: str | None = None
    region_mapping: dict[str, list[str]] = Field(default_factory=dict)
    candidate_ancestry: dict[str, list[str]] = Field(default_factory=dict)
    partition_method: Literal["fixed_tolerance_baseline", "exploratory_statistical_split"] = "fixed_tolerance_baseline"
    partition_evidence: dict = Field(default_factory=dict)


def periodic_difference(left: float, right: float) -> float:
    return abs((left - right + 180) % 360 - 180)


def describe_candidate(candidate: CandidateRecord, specs: list[DescriptorSpec]) -> DescriptorRecord:
    coordinates = dict(zip(candidate.atom_ids, candidate.positions))
    values, missing = {}, {}
    for spec in specs:
        if spec.kind not in ('distance', 'angle', 'dihedral'):
            missing[spec.key] = 'unsupported descriptor'
            continue
        if any(atom not in coordinates for atom in spec.stable_atom_ids):
            missing[spec.key] = 'missing atom identity'
            continue
        points = [np.asarray(coordinates[atom], dtype=float) for atom in spec.stable_atom_ids]
        if spec.kind == 'distance':
            value = float(np.linalg.norm(points[1] - points[0]))
        elif spec.kind == 'angle':
            u, v = points[0] - points[1], points[2] - points[1]
            denominator = np.linalg.norm(u) * np.linalg.norm(v)
            if denominator < 1e-12:
                missing[spec.key] = 'degenerate geometry'
                continue
            value = math.degrees(math.acos(float(np.clip(np.dot(u, v) / denominator, -1, 1))))
        else:
            b0, b1, b2 = points[0] - points[1], points[2] - points[1], points[3] - points[2]
            norm = np.linalg.norm(b1)
            if norm < 1e-12:
                missing[spec.key] = 'degenerate geometry'
                continue
            axis = b1 / norm
            v, w = b0 - np.dot(b0, axis) * axis, b2 - np.dot(b2, axis) * axis
            if min(np.linalg.norm(v), np.linalg.norm(w)) < 1e-12:
                missing[spec.key] = 'degenerate geometry'
                continue
            value = math.degrees(math.atan2(float(np.dot(np.cross(axis, v), w)), float(np.dot(v, w))))
        values[spec.key] = value
    return DescriptorRecord(candidate_id=candidate.candidate_id, values=values, missing=missing)


def _distance(left: DescriptorRecord, right: DescriptorRecord, specs: list[DescriptorSpec]) -> float:
    differences = []
    for spec in specs:
        if spec.key not in left.values or spec.key not in right.values:
            if spec.required:
                return math.inf
            continue
        a, b = left.values[spec.key], right.values[spec.key]
        differences.append((periodic_difference(a, b) if spec.kind == 'dihedral' else abs(a-b)) / spec.tolerance)
    return max(differences) if differences else math.inf


def candidate_lineage(candidate_id: str, by_id: dict[str, CandidateRecord]) -> set[str]:
    """Keep ancestors even when the parent is only present in an earlier snapshot."""
    lineage = set()
    current = candidate_id
    while current is not None:
        if current in lineage:
            raise ValueError('candidate lineage cycle')
        lineage.add(current)
        record = by_id.get(current)
        current = record.parent_id if record else None
    return lineage


def partition_candidates(candidates: list[CandidateRecord], config: RegionConfig,
                         *, previous: RegionSnapshot | None = None) -> RegionSnapshot:
    if not candidates:
        raise ValueError('cannot partition empty catalog')
    scopes = {(c.catalog_id, c.project_id, c.owner_id) for c in candidates}
    if len(scopes) != 1:
        raise ValueError('candidate catalog scope mismatch')
    by_id = {c.candidate_id: c for c in candidates}
    descriptors = {cid: describe_candidate(c, config.descriptor_specs) for cid, c in by_id.items()}
    regions: dict[str, Region] = {}
    config_hash = content_digest(config.model_dump())
    for cid in sorted(by_id):
        options = []
        for rid, region in regions.items():
            representative = by_id[region.representative_id]
            if representative.species_key != by_id[cid].species_key:
                continue
            distance = _distance(descriptors[cid], descriptors[region.representative_id], config.descriptor_specs)
            if distance <= 1:
                options.append((distance, region.representative_id, rid))
        if options:
            rid = min(options)[2]
            regions[rid] = regions[rid].model_copy(update={'member_ids': regions[rid].member_ids + [cid]})
        else:
            rid = content_digest([config_hash, cid])
            regions[rid] = Region(representative_id=cid, member_ids=[cid])
    ancestry = {}
    for cid in by_id:
        ancestors = candidate_lineage(cid, by_id)
        if previous:
            for ancestor in list(ancestors):
                ancestors.update(previous.candidate_ancestry.get(ancestor, []))
        ancestry[cid] = sorted(ancestors)
    mapping = {}
    if previous:
        if previous.catalog_id != candidates[0].catalog_id:
            raise ValueError('previous catalog mismatch')
        lineage = {cid: set(ancestors) for cid, ancestors in ancestry.items()}
        mapping = {old_id: sorted(rid for rid, r in regions.items()
                                 if any(lineage[cid] & set(old.member_ids) for cid in r.member_ids))
                   for old_id, old in previous.regions.items()}
        for historical_id, descendants in previous.region_mapping.items():
            mapping[historical_id] = sorted({rid for descendant in descendants for rid in mapping.get(descendant, [])})
    revision = content_digest([config_hash, {rid: r.model_dump() for rid, r in regions.items()},
                               previous.revision if previous else None, ancestry])
    return RegionSnapshot(catalog_id=candidates[0].catalog_id, revision=revision, config=config,
                          regions=regions, descriptors=descriptors,
                          previous_revision=previous.revision if previous else None, region_mapping=mapping, candidate_ancestry=ancestry)


def build_descriptor_specs(graph: object, reaction_atom_ids: list[str],
                           explicit: list[DescriptorSpec]) -> list[DescriptorSpec]:
    """Add canonical rotatable-bond torsions; atom IDs come from the resolved graph."""
    from rdkit import Chem
    from rdkit.Chem import Lipinski

    Chem.GetSymmSSSR(graph)

    ids = {a.GetIdx(): a.GetProp('cloudra_atom_id') if a.HasProp('cloudra_atom_id') else str(a.GetIdx())
           for a in graph.GetAtoms()}
    torsions = []
    for a, b in graph.GetSubstructMatches(Lipinski.RotatableBondSmarts):
        left = sorted((n.GetIdx() for n in graph.GetAtomWithIdx(a).GetNeighbors() if n.GetIdx() != b), key=lambda i:(graph.GetAtomWithIdx(i).GetAtomicNum()==1,ids[i]))
        right = sorted((n.GetIdx() for n in graph.GetAtomWithIdx(b).GetNeighbors() if n.GetIdx() != a), key=lambda i:(graph.GetAtomWithIdx(i).GetAtomicNum()==1,ids[i]))
        if left and right:
            atoms = [ids[left[0]], ids[a], ids[b], ids[right[0]]]
            atoms = min(atoms, list(reversed(atoms)))
            torsions.append(DescriptorSpec(kind='dihedral', stable_atom_ids=atoms, source='rotatable_bond',
                reason='Rotatable bond touches declared reaction atoms' if set(atoms)&set(reaction_atom_ids) else 'Rotatable bond describes alternative molecular shape; chemical importance unproven'))
    torsions.sort(key=lambda s: (not bool(set(s.stable_atom_ids) & set(reaction_atom_ids)), s.key))
    result = list(explicit)
    known = {s.key for s in result}
    for spec in torsions:
        if spec.key not in known:
            result.append(spec)
            known.add(spec.key)
    return result
