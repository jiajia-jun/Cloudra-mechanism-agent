"""Scorer-side evidence discovery: find a *passing* IRC -> Opt -> Freq chain.

The bound-evidence path trusts whichever logs the agent bound to a stage. When a
log was bound to the wrong slot (or never bound), the same scientific proof may
still exist in the sandbox. This module indexes the sandbox's native logs once,
uses cheap necessary conditions only to prune candidates, and accepts nothing
except ``verify_short_irc_direction(...) == True``.

Scoring is graded: saddle 0.35, IRC starting-saddle match 0.15, endpoint lineage
0.50 (0.25 when only one side connects). A full passing proof scores 1.0.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from cloudra.tools.core.irc_evidence import (
    _optimization_geometries,
    irc_endpoint_geometries,
    irc_start_geometry,
    verify_short_irc_direction,
)
from cloudra.tools.core.irc_path import same_geometry
from cloudra.tools.core.qm_log_facts import read_qm_log

_SADDLE_SCORE = 0.35
_IRC_SCORE = 0.15
_ENDPOINT_SCORE = 0.50


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
        for path in sorted(self.sandbox.rglob("*.log")):
            if not path.is_file():
                continue
            try:
                facts = read_qm_log(path)
            except Exception:  # one unreadable log must not fail the whole score
                continue
            energy = facts.electronic_energy_hartree or facts.scf_energy_hartree
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
                if "irc" not in fact.job_types:
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
    used_chains: set[str] | None = None,
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
        saddles = [f for f in evidence.by_energy(ts_energy) if f.n_imag == 1]
        if not saddles:
            result.notes.append(
                "no first-order saddle log matches the declared TS energy; refusing to "
                "substitute an unrelated saddle")
            return result
    else:
        saddles = [f for f in evidence.logs if f.n_imag == 1][:3]
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

    source_logs = evidence.by_energy(_node_energy(source_node)) if source_node else []
    target_logs = evidence.by_energy(_node_energy(target_node)) if target_node else []
    source_logs = [f for f in source_logs if f.n_imag == 0]
    target_logs = [f for f in target_logs if f.n_imag == 0]
    if not source_logs:
        source_logs = [f for f in evidence.logs if f.n_imag == 0][:4]
    if not target_logs:
        target_logs = [f for f in evidence.logs if f.n_imag == 0][:4]

    def connected(facts: list[LogFact], frame) -> list[LogFact]:
        hits = []
        for fact in facts:
            opt = evidence.optimizations(fact)
            if opt and same_geometry(opt[0], frame):
                hits.append(fact)
        return hits

    reactant_smiles = source_node.smiles if source_node else None
    product_smiles = target_node.smiles if target_node else None
    one_side = False
    for irc_fact, _start, (a, b) in irc_matches[:3]:
        sources = connected(source_logs, b) + connected(source_logs, a)
        targets = connected(target_logs, a) + connected(target_logs, b)
        one_side = one_side or bool(sources) or bool(targets)
        for saddle in saddles[:2]:
            for source in sources[:2]:
                for target in targets[:2]:
                    if source.path == target.path:
                        continue
                    try:
                        passed, details = verify_short_irc_direction(
                            irc_fact.path, [saddle.path], [target.path], [source.path],
                            charge=charge,
                            reactant_smiles=reactant_smiles,
                            product_smiles=product_smiles,
                        )
                    except Exception as exc:
                        result.notes.append(f"discovery proof could not be evaluated: {exc}")
                        continue
                    if passed:
                        chain_key = f"{saddle.path}|{irc_fact.path}"
                        if used_chains is not None and chain_key in used_chains:
                            result.notes.append(
                                "the discovered chain is already used by another edge")
                            continue
                        if used_chains is not None:
                            used_chains.add(chain_key)
                        result.passed = True
                        result.score = 1.0
                        result.evidence = [str(saddle.path), str(irc_fact.path),
                                           str(source.path), str(target.path)]
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
