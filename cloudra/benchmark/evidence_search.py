"""Scorer-side evidence discovery: find a *passing* IRC -> Opt -> Freq chain.

The bound-evidence path starts from whichever logs the agent bound to a stage. When a
log was bound to the wrong slot (or never bound), the same scientific proof may
still exist in the sandbox. This module indexes the sandbox's native logs once,
uses cheap necessary conditions only to prune candidates, and accepts nothing
except ``verify_short_irc_direction(...) == True``.

Scoring is graded: saddle 0.35, IRC starting-saddle match 0.15, endpoint lineage
0.50 (0.25 when only one side connects). A full passing proof scores 1.0.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path

from cloudra.benchmark.integrity import evidence_within_sandbox
from cloudra.tools.core.irc_evidence import (
    _geometry_matches_species,
    _optimization_geometries,
    irc_endpoint_geometries,
    irc_start_geometry,
    verify_short_irc_direction,
)
from cloudra.tools.core.irc_path import same_geometry
from cloudra.tools.core.qm_log_facts import read_qm_log
from cloudra.tools.core.species_identity import chemical_smiles

_SADDLE_SCORE = 0.35
_IRC_SCORE = 0.15
_ENDPOINT_SCORE = 0.50


def irc_evidence_within_sandbox(path: Path, sandbox: Path) -> bool:
    """Check the native reader's selected sidecars, not merely the IRC log.

    Core readers also serve non-benchmark workflows and may follow native NAME
    paths. Only benchmark evidence must be entirely owned by one task sandbox.
    """
    from cloudra.tools.core import orca_frames, qm_engine

    if not evidence_within_sandbox(path, sandbox):
        return False
    try:
        archive = path.parent / 'irc_endpoints.json'
        if archive.is_file() and not evidence_within_sandbox(archive, sandbox):
            return False
        if qm_engine.detect_qm_engine(str(path)) != 'orca':
            return True
        # Follow the reader's precedence: an archived chain does not consult a
        # neighboring compute receipt or remote path map at all.
        if not archive.is_file():
            result_dir = path.parent.parent if path.parent.name == '.cloudra' else path.parent
            path_map = result_dir.parent / 'path-map.json'
            receipt = path.parent.parent / 'evidence.json'
            metadata = path_map if result_dir.name == 'results' and path_map.is_file() else receipt
            if metadata.is_file() and not evidence_within_sandbox(metadata, sandbox):
                return False
        endpoints = orca_frames.extract_irc_endpoints(str(path))
        return all(not endpoint.get('geometry_ref') or evidence_within_sandbox(
            Path(endpoint['geometry_ref']), sandbox) for endpoint in endpoints.values())
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        return False


def claim_native_chain(ts_log: Path, irc_logs, proof_lineage: dict, used_chains: dict | None) -> bool:
    """Claim actual directed native evidence, not renamable graph node IDs.

    Native verification supplies the ordered outer frames. Existing geometry
    equality identifies the same direction; reversing distinct frames remains
    allowed. Reusing either same-role endpoint reserves a constituent even if
    a paired log changes the opposite outer frame.
    """
    if used_chains is None:
        return True
    source = proof_lineage.get('source_endpoint')
    target = proof_lineage.get('target_endpoint')
    if source is None or target is None:
        return False

    def digest(path):
        with Path(path).open('rb') as stream:
            return hashlib.file_digest(stream, 'sha256').hexdigest()

    saddle = digest(ts_log)
    keys = {(saddle, digest(path)) for path in irc_logs}
    for key in keys:
        if any(same_geometry(source, prior_source) or same_geometry(target, prior_target)
               for prior_source, prior_target in used_chains.get(key, ())):
            return False
    for key in keys:
        used_chains.setdefault(key, []).append((source, target))
    return True


@dataclass
class LogFact:
    path: Path
    energy: float | None
    n_imag: int | None
    geometry: tuple | None
    job_types: set[str]
    normal: bool


@dataclass
class DiscoveryResult:
    passed: bool = False
    score: float = 0.0
    notes: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)


class SandboxEvidence:
    """One parse per native log; IRC endpoints and Opt geometries are lazy."""

    def __init__(self, sandbox: Path) -> None:
        self.sandbox = Path(sandbox)
        self.logs: list[LogFact] = []
        self._irc: list[tuple[LogFact, tuple, tuple]] | None = None
        self._opt: dict[Path, tuple | None] = {}
        for path in sorted(self.sandbox.rglob("*")):
            if path.suffix.lower() not in {'.log', '.out'} or not evidence_within_sandbox(path, self.sandbox):
                continue
            try:
                facts = read_qm_log(path)
            except Exception:  # one unreadable log must not fail the whole score
                continue
            if not facts.normal_termination:
                continue
            energy = (facts.electronic_energy_hartree if facts.electronic_energy_hartree is not None
                      else facts.scf_energy_hartree)
            frequencies = facts.frequencies_cm
            n_imag = sum(1 for f in frequencies if f < 0) if frequencies else None
            self.logs.append(LogFact(
                path=path, energy=energy, n_imag=n_imag, geometry=facts.geometry,
                job_types=set(facts.job_types or ()), normal=bool(facts.normal_termination),
            ))

    def by_energy(self, energy: float | None, tol: float = 1e-6) -> list[LogFact]:
        if energy is None:
            return []
        return [f for f in self.logs if f.energy is not None and abs(f.energy - energy) < tol]

    def optimizations(self, fact: LogFact) -> tuple | None:
        if fact.path not in self._opt:
            try:
                self._opt[fact.path] = _optimization_geometries(fact.path)
            except Exception:
                self._opt[fact.path] = None
        return self._opt[fact.path]

    def irc_logs(self) -> list[tuple[LogFact, tuple, tuple]]:
        if self._irc is None:
            found = []
            for fact in self.logs:
                if not irc_evidence_within_sandbox(fact.path, self.sandbox):
                    continue
                try:
                    start = irc_start_geometry(fact.path)
                    ends = irc_endpoint_geometries(fact.path)
                except Exception:
                    continue
                if start is not None and ends is not None:
                    found.append((fact, start, ends))
            self._irc = found
        return self._irc


def _node_energy(node) -> float | None:
    properties = node.properties or {}
    value = properties.get("energy_hartree")
    return float(value) if isinstance(value, (int, float)) else None


def discover_edge_proof(
    evidence: SandboxEvidence, graph, edge, *, charge: int = 0,
    used_chains: dict | None = None,
) -> DiscoveryResult:
    """Search for a passing proof of one edge; never accept a mere match."""
    nodes = {node.id: node for node in graph.nodes}
    ts_node = nodes.get(edge.via)
    source_node = nodes.get(edge.from_node)
    target_node = nodes.get(edge.to_node)
    result = DiscoveryResult()
    if ts_node is None:
        result.notes.append("no TS node on this edge")
        return result

    ts_energy = _node_energy(ts_node)
    if ts_energy is not None:
        # A declared energy identifies the saddle; never substitute another TS.
        saddles = [f for f in evidence.by_energy(ts_energy) if f.normal and f.n_imag == 1]
        if not saddles:
            result.notes.append(
                "no first-order saddle log matches the declared TS energy; refusing to "
                "substitute an unrelated saddle")
            return result
    else:
        saddles = [f for f in evidence.logs if f.normal and f.n_imag == 1]
        if saddles:
            result.notes.append("no TS energy declared; scanning for single-imaginary candidates")
    if not saddles:
        result.notes.append("no first-order saddle (exactly one imaginary frequency) anywhere in the sandbox")
        return result
    result.score = _SADDLE_SCORE
    result.evidence.extend(str(f.path) for f in saddles[:1])

    irc_matches = []
    for fact, start, ends in evidence.irc_logs():
        if any(saddle.geometry is not None and same_geometry(start, saddle.geometry) for saddle in saddles):
            irc_matches.append((fact, start, ends))
    if not irc_matches:
        result.notes.append(
            "no IRC log starts from a matching saddle geometry (an IRC log need not contain a frequency block)")
        return result
    result.score = _SADDLE_SCORE + _IRC_SCORE

    # An endpoint Opt and its same-geometry Freq may be separate jobs. Energy
    # anchors can be another conformer of the same species; the native verifier
    # remains responsible for species identity and the complete linkage.
    minima = [fact for fact in evidence.logs if fact.normal and fact.n_imag == 0]

    def matching_minima(smiles):
        if smiles is None:
            return minima
        expected = chemical_smiles(smiles)
        return [fact for fact in minima if fact.geometry is not None and
                _geometry_matches_species(fact.geometry, expected, charge=charge)]

    def connected(frame, minimum_logs) -> list[list[Path]]:
        hits = []
        for fact in evidence.logs:
            opt = evidence.optimizations(fact)
            if opt is None or not same_geometry(opt[0], frame):
                continue
            for minimum in minimum_logs:
                if minimum.geometry is not None and same_geometry(opt[1], minimum.geometry):
                    hits.append(list(dict.fromkeys([fact.path, minimum.path])))
        return hits

    reactant_smiles = source_node.smiles if source_node else None
    product_smiles = target_node.smiles if target_node else None
    source_minima = matching_minima(reactant_smiles)
    target_minima = matching_minima(product_smiles)
    one_side = False
    for irc_fact, start, (a, b) in irc_matches:
        sources = connected(b, source_minima) + connected(a, source_minima)
        targets = connected(a, target_minima) + connected(b, target_minima)
        one_side = one_side or bool(sources) or bool(targets)
        for saddle in saddles:
            if saddle.geometry is None or not same_geometry(start, saddle.geometry):
                continue
            for source in sources:
                for target in targets:
                    if source == target:
                        continue
                    proof_lineage = {}
                    try:
                        passed, details = verify_short_irc_direction(
                            irc_fact.path, [saddle.path], target, source,
                            charge=charge,
                            reactant_smiles=reactant_smiles,
                            product_smiles=product_smiles,
                            proof_lineage=proof_lineage,
                        )
                    except Exception as exc:
                        result.notes.append(f"discovery proof could not be evaluated: {exc}")
                        continue
                    if passed:
                        if not claim_native_chain(saddle.path, [irc_fact.path], proof_lineage, used_chains):
                            result.notes.append(
                                "the discovered chain is already used by another edge")
                            continue
                        result.passed = True
                        result.score = 1.0
                        result.evidence = list(dict.fromkeys(str(path) for path in
                            [saddle.path, irc_fact.path, *source, *target]))
                        result.notes.append("discovered a passing IRC -> Opt -> Freq chain in the sandbox")
                        return result
                    result.notes.extend(d for d in details[:2])
    if one_side:
        result.score = _SADDLE_SCORE + _IRC_SCORE + _ENDPOINT_SCORE / 2
        result.notes.append("only one endpoint side is connected by a native Opt/Freq log")
    else:
        result.notes.append(
            "the IRC outer frames are not connected to the declared minima by native Opt/Freq logs")
    return result
