"""Worker-scoped adapter from generated geometries to immutable catalog records."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from cloudra.persistence.fs_utils import atomic_write_text
from cloudra.tools.core.conformer_catalog import CandidateRecord, EnergyObservation, Qualification, content_digest


@dataclass
class CandidateCapture:
    catalog_id: str
    project_id: str
    owner_id: str
    output_dir: str
    sink: Callable[[CandidateRecord], object] | None = None
    atom_ids: list[str] = field(default_factory=list)
    multiplicity: int = 1
    records: list[CandidateRecord] = field(default_factory=list)
    _references: dict = field(default_factory=dict, init=False, repr=False)

    def for_component(self, identities):
        ids = [self.atom_ids[a.index] if self.atom_ids else
               f'a{a.input_atom_index}' if a.origin=='input_atom' else
               f'h{a.parent_input_atom_index}:{a.hydrogen_ordinal}' for a in identities]
        return CandidateCapture(catalog_id=self.catalog_id,project_id=self.project_id,owner_id=self.owner_id,
            output_dir=self.output_dir,sink=self.sink,atom_ids=ids,multiplicity=self.multiplicity,records=self.records)

    def capture(self, mol, cid: int, *, generator: str, seed: int | None = None,
                parent_id: str | None = None, state: str = 'generated',
                energies: list[EnergyObservation] | None = None,
                qualification: Qualification | None = None,
                parameters: dict | None = None, job_ids: list[int] | None = None) -> CandidateRecord:
        from rdkit import Chem

        positions = mol.GetConformer(cid).GetPositions().tolist()
        fragments = {index: f'f{number}' for number, group in enumerate(Chem.GetMolFrags(mol)) for index in group}
        ids = self.atom_ids or [str(i) for i in range(mol.GetNumAtoms())]
        if len(ids) != mol.GetNumAtoms():
            raise ValueError('capture atom identity length mismatch')
        species = content_digest([Chem.MolToSmiles(mol, isomericSmiles=True), Chem.GetFormalCharge(mol), self.multiplicity])
        if not self.atom_ids:
            reference = self._references.get(species)
            if reference is None:
                reference = Chem.Mol(mol)
                reference.RemoveAllConformers()
                reference.AddConformer(Chem.Conformer(mol.GetConformer(cid)), assignId=True)
                self._references[species] = reference
            else:
                from rdkit.Chem import rdMolAlign
                matches = mol.GetSubstructMatches(reference, uniquify=False, useChirality=True, maxMatches=100001)
                if not matches or len(matches) >= 100001:
                    raise ValueError('complete stereo-preserving atom correspondence requires explicit identities')
                maps = [[(probe, ref) for ref, probe in enumerate(match)] for match in matches]
                _, _, mapping = rdMolAlign.GetBestAlignmentTransform(mol, reference, prbCid=cid, refCid=0,
                    map=maps, symmetrizeConjugatedTerminalGroups=False, reflect=False)
                identities = dict(mapping)
                ids = [str(identities[i]) for i in range(mol.GetNumAtoms())]
                reference_fragments = {i: f'f{n}' for n, group in enumerate(Chem.GetMolFrags(reference)) for i in group}
                fragments = {i: reference_fragments[identities[i]] for i in range(mol.GetNumAtoms())}
        record = CandidateRecord(catalog_id=self.catalog_id, project_id=self.project_id, owner_id=self.owner_id,
                                 species_key=species, atom_ids=ids, symbols=[a.GetSymbol() for a in mol.GetAtoms()],
                                 fragment_ids=[fragments[i] for i in range(mol.GetNumAtoms())], positions=positions,
                                 generator=generator, parameters=parameters or {}, seed=seed, parent_id=parent_id, state=state,
                                 energies=energies or [], job_ids=job_ids or [], qualification=qualification or Qualification())
        return self._publish(record)

    def capture_unresolved_frame(self, symbols, positions, *, generator, parameters, energy_hartree=None):
        """Archive returned atoms without inventing graph or inter-frame identity."""
        species=content_digest(['unresolved_graph',symbols,positions,parameters])
        record=CandidateRecord(catalog_id=self.catalog_id,project_id=self.project_id,owner_id=self.owner_id,
            species_key=species,atom_ids=[f'unresolved:{i}' for i in range(len(symbols))],symbols=symbols,
            fragment_ids=['unresolved']*len(symbols),positions=positions,generator=generator,parameters=parameters,
            energies=[EnergyObservation(value=energy_hartree,unit='Ha',method_fingerprint='CREST/unresolved_method',
                species_key=species,convergence='unknown',artifact_ref=parameters['source_artifact'])] if energy_hartree is not None else [],
            qualification=Qualification(reasons=['chemical graph and stable atom correspondence unresolved']))
        return self._publish(record)

    def _publish(self, record):
        ids=record.atom_ids
        positions=record.positions
        path = Path(self.output_dir) / 'catalog_geometries' / f'{record.candidate_id}.xyz'
        text = f'{len(ids)}\n{record.candidate_id}; generated geometry, not verified TS\n'
        text += ''.join(f'{symbol} {p[0]:.12g} {p[1]:.12g} {p[2]:.12g}\n'
                        for symbol, p in zip(record.symbols, positions))
        if path.exists() and path.read_text() != text:
            raise ValueError('immutable geometry path conflict')
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            atomic_write_text(str(path), text)
        record = CandidateRecord(**record.model_dump(exclude={'geometry_ref', 'artifact_hash'}), geometry_ref=str(path))
        if self.sink:
            self.sink(record)
        self.records.append(record)
        return record
