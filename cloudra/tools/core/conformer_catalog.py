"""Immutable generated geometries, optimization lineage and comparable energies."""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from cloudra.tools.core.molecule import Molecule


def content_digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                     ensure_ascii=False, allow_nan=False).encode()).hexdigest()


class CatalogModel(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True, allow_inf_nan=False)


class Qualification(CatalogModel):
    status: Literal['unknown', 'qualified', 'rejected'] = 'unknown'
    reasons: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)


class EnergyObservation(CatalogModel):
    value: float
    unit: Literal['Ha', 'kcal/mol', 'kJ/mol']
    kind: Literal['potential', 'enthalpy', 'free_energy'] = 'potential'
    method_fingerprint: str = Field(min_length=1)
    species_key: str = Field(min_length=1)
    charge: int = 0
    multiplicity: int = Field(default=1, ge=1)
    solvent: str = ''
    reference: str = 'absolute'
    convergence: Literal['converged', 'unconverged', 'unknown'] = 'unknown'
    artifact_ref: str = ''

    def comparison_key(self) -> tuple:
        return (self.species_key, self.method_fingerprint, self.kind, self.charge,
                self.multiplicity, self.solvent, self.reference)

    def kcal(self) -> float:
        return self.value * {'Ha': 627.5094740631, 'kcal/mol': 1, 'kJ/mol': 1 / 4.184}[self.unit]


def relative_energies(observations: dict[str, EnergyObservation]) -> dict[str, float]:
    if not observations:
        return {}
    if len({e.comparison_key() for e in observations.values()}) != 1:
        raise ValueError('energies are not comparable')
    if any(e.convergence != 'converged' for e in observations.values()):
        raise ValueError('unconverged energies are not comparable')
    values = {key: obs.kcal() for key, obs in observations.items()}
    minimum = min(values.values())
    return {key: value - minimum for key, value in values.items()}


class CandidateRecord(CatalogModel):
    schema_version: Literal[2] = 2
    catalog_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    owner_id: str = Field(min_length=1)
    species_key: str = Field(min_length=1)
    mol: Molecule
    molecule_hash: str = ''
    geometry_ref: str = ''
    geometry_hash: str = ''
    artifact_hash: str = ''
    candidate_id: str = ''
    generator: str = Field(min_length=1)
    parameters: dict[str, str | int | float | bool | None] = Field(default_factory=dict)
    seed: int | None = None
    parent_id: str | None = None
    qualification: Qualification = Field(default_factory=Qualification)
    state: Literal['generated', 'optimized', 'failed', 'rejected'] = 'generated'
    energies: list[EnergyObservation] = Field(default_factory=list)
    job_ids: list[int] = Field(default_factory=list)

    @property
    def atom_ids(self) -> list[str]:
        return [atom.GetProp('cloudra_atom_id') for atom in self.mol.GetAtoms()]

    @property
    def fragment_ids(self) -> list[str]:
        return [atom.GetProp('cloudra_fragment_id') for atom in self.mol.GetAtoms()]

    @property
    def symbols(self) -> list[str]:
        return [atom.GetSymbol() for atom in self.mol.GetAtoms()]

    @property
    def positions(self) -> list[list[float]]:
        return self.mol.GetConformer().GetPositions().tolist()

    @model_validator(mode='after')
    def validate_identity(self):
        from rdkit import Chem

        object.__setattr__(self, 'mol', Chem.Mol(self.mol))
        if self.mol.GetNumConformers() != 1:
            raise ValueError('a candidate requires one molecular conformer')
        if any(not atom.HasProp('cloudra_atom_id') or not atom.HasProp('cloudra_fragment_id')
               for atom in self.mol.GetAtoms()):
            raise ValueError('candidate molecule requires atom and fragment identities')
        n = len(self.atom_ids)
        if not n or len(set(self.atom_ids)) != n or any(not x for x in self.atom_ids):
            raise ValueError('atom identities must be unique and nonempty')
        if any(len(values) != n for values in (self.fragment_ids, self.symbols, self.positions)):
            raise ValueError('geometry and identity lengths differ')
        if any(len(pos) != 3 or not all(math.isfinite(x) for x in pos) for pos in self.positions):
            raise ValueError('geometry requires finite 3D coordinates')
        if any(e.species_key != self.species_key for e in self.energies):
            raise ValueError('energy species differs from candidate identity')
        molecule_hash = content_digest(self.model_dump(mode='json', include={'mol'})['mol'])
        if self.molecule_hash and self.molecule_hash != molecule_hash:
            raise ValueError('molecular state hash mismatch')
        object.__setattr__(self, 'molecule_hash', molecule_hash)
        atoms = sorted(zip(self.atom_ids, self.fragment_ids, self.symbols, self.positions))
        geometry_hash = content_digest(atoms)
        if self.geometry_hash and self.geometry_hash != geometry_hash:
            raise ValueError('geometry hash mismatch')
        object.__setattr__(self, 'geometry_hash', geometry_hash)
        ident = content_digest([self.catalog_id, self.project_id, self.owner_id, self.species_key,
                                molecule_hash, geometry_hash, self.generator, self.parameters, self.seed, self.parent_id])
        if self.candidate_id and self.candidate_id != ident:
            raise ValueError('candidate identity mismatch')
        object.__setattr__(self, 'candidate_id', ident)
        if self.geometry_ref and not self.artifact_hash:
            object.__setattr__(self, 'artifact_hash', hashlib.sha256(Path(self.geometry_ref).read_bytes()).hexdigest())
        return self

    def verify_artifact(self) -> None:
        if self.geometry_ref and hashlib.sha256(Path(self.geometry_ref).read_bytes()).hexdigest() != self.artifact_hash:
            raise ValueError('geometry artifact has changed')

    def immutable_payload(self) -> dict:
        # A moved identical artifact is allowed; other provenance and outcomes are immutable.
        return self.model_dump(mode='json', exclude={'geometry_ref'})
