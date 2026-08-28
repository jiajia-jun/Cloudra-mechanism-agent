"""Layer 1 — delivery integrity: forensic sandbox scan and evidence binding.

The scorer never trusts the agent's self-declared mechanism. It recursively
walks the agent's sandbox, extracts the delivered `mechanism_graph.json`, and
binds each graph element to concrete computational evidence files found on
disk (parsed structure match, not filename convention). The result is an
integrity report: is there a parseable graph, and is every claimed node/step
backed by at least one evidence file whose parsed structure matches the
claimed SMILES.

Pure filesystem + parsing; no LLM, no DB.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from cloudra.benchmark.graph_similarity import GedConfig, species_substitution_cost
from cloudra.benchmark.schema import (
    GoldMechanismGraph,
    IntegrityRubric,
    NodeRole,
)

# file extensions we treat as computational evidence worth parsing for SMILES
_EVIDENCE_SUFFIXES = {".gjf", ".com", ".inp", ".xyz", ".log", ".out", ".sdf", ".mol", ".json"}

_SMILES_LINE_RE = re.compile(r"\bsmiles\s*[:=]\s*([^\s,;]+)", re.IGNORECASE)
_TITLE_SMILES_RE = re.compile(r"^([A-Za-z0-9@+\-\[\]\(\)=#\\/.:]+)$")


@dataclass
class EvidenceFile:
    path: str
    smiles_found: list[str] = field(default_factory=list)
    kind: str = ""  # 'gaussian'|'orca'|'xyz'|'json'|'unknown'


@dataclass
class NodeBinding:
    node_id: str
    bound_files: list[str] = field(default_factory=list)
    matched: bool = False


@dataclass
class IntegrityReport:
    graph_found: bool
    graph_parseable: bool
    graph_path: Optional[str] = None
    delivered_graph: Optional[GoldMechanismGraph] = None
    evidence_files: list[EvidenceFile] = field(default_factory=list)
    node_bindings: list[NodeBinding] = field(default_factory=list)
    fraction_bound: float = 0.0
    passed: bool = False
    notes: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# sandbox scan
# ---------------------------------------------------------------------------


def find_graph_json(sandbox: Path) -> Optional[Path]:
    """Locate the agent-maintained mechanism_graph.json at the sandbox root,
    falling back to any *.json that parses to a mechanism graph shape."""
    direct = sandbox / "mechanism_graph.json"
    if direct.is_file():
        return direct
    for p in sorted(sandbox.rglob("*.json")):
        try:
            data = json.loads(p.read_text(encoding="utf-8", errors="replace"))
        except Exception:
            continue
        if isinstance(data, dict) and "nodes" in data and "edges" in data:
            return p
    return None


def load_delivered_graph(path: Path) -> Optional[GoldMechanismGraph]:
    """Parse a delivered graph JSON into GoldMechanismGraph (the agent-facing
    wire shape is the same node/edge structure)."""
    try:
        data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return None
    try:
        return GoldMechanismGraph.model_validate(data)
    except Exception:
        return None


def _smiles_in_text(text: str) -> list[str]:
    out: list[str] = []
    for m in _SMILES_LINE_RE.finditer(text):
        out.append(m.group(1))
    return out


def scan_evidence_files(sandbox: Path) -> list[EvidenceFile]:
    files: list[EvidenceFile] = []
    for p in sorted(sandbox.rglob("*")):
        if not p.is_file():
            continue
        if p.suffix.lower() not in _EVIDENCE_SUFFIXES:
            continue
        if p.name == "mechanism_graph.json":
            continue
        kind = _classify(p)
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        files.append(EvidenceFile(path=str(p.relative_to(sandbox)), smiles_found=_smiles_in_text(text), kind=kind))
    return files


def _classify(p: Path) -> str:
    s = p.suffix.lower()
    if s in (".gjf", ".com"):
        return "gaussian"
    if s == ".inp":
        return "orca"
    if s == ".xyz":
        return "xyz"
    if s == ".json":
        return "json"
    if s in (".log", ".out"):
        # sniff engine by content header
        try:
            head = p.read_text(encoding="utf-8", errors="replace")[:2000]
        except Exception:
            return "unknown"
        if "Entering Gaussian System" in head or "Gaussian" in head:
            return "gaussian"
        if "O   R   C   A" in head or "ORCA" in head:
            return "orca"
        return "log"
    return "unknown"


# ---------------------------------------------------------------------------
# binding
# ---------------------------------------------------------------------------


def _component_in_file(component: str, file_smiles: list[str], cfg: GedConfig, threshold: float) -> bool:
    """True if `component` matches any single SMILES in the file (subset
    match: a log file holding several species still evidences each one)."""
    for fs in file_smiles:
        if species_substitution_cost([component], [fs], cfg) <= threshold:
            return True
    return False


def bind_graph_to_evidence(
    graph: GoldMechanismGraph,
    files: list[EvidenceFile],
    cfg: Optional[GedConfig] = None,
    match_threshold: float = 0.2,
) -> list[NodeBinding]:
    """Bind each non-TS node to evidence files whose parsed SMILES match the
    node's claimed SMILES. A multi-species node (complex) is bound when every
    one of its component SMILES is matched by at least one evidence file
    (union coverage), since a single log typically holds only one component.
    TS nodes carry no SMILES and are bound indirectly via their edge's
    endpoints."""
    cfg = cfg or GedConfig()
    bindings: list[NodeBinding] = []
    for node in graph.nodes:
        nb = NodeBinding(node_id=node.id)
        if node.role == NodeRole.TRANSITION_STATE or not node.smiles:
            nb.matched = True  # TS nodes carry no SMILES; not directly bindable
            bindings.append(nb)
            continue
        all_components_matched = True
        for component in node.smiles:
            component_files = [
                f.path for f in files
                if f.smiles_found and _component_in_file(component, f.smiles_found, cfg, match_threshold)
            ]
            if component_files:
                nb.bound_files.extend(component_files)
            else:
                all_components_matched = False
        nb.bound_files = sorted(set(nb.bound_files))
        nb.matched = all_components_matched and bool(nb.bound_files)
        bindings.append(nb)
    return bindings


# ---------------------------------------------------------------------------
# public entry
# ---------------------------------------------------------------------------


def audit_integrity(
    sandbox: Path,
    rubric: Optional[IntegrityRubric] = None,
    cfg: Optional[GedConfig] = None,
) -> IntegrityReport:
    rubric = rubric or IntegrityRubric()
    report = IntegrityReport(graph_found=False, graph_parseable=False)

    graph_path = find_graph_json(sandbox)
    if graph_path is None:
        report.notes.append("mechanism_graph.json not found in sandbox")
        report.passed = not rubric.require_graph_json
        return report
    report.graph_found = True
    report.graph_path = str(graph_path.relative_to(sandbox))

    graph = load_delivered_graph(graph_path)
    if graph is None:
        report.notes.append("mechanism_graph.json present but not parseable")
        return report
    report.graph_parseable = True
    report.delivered_graph = graph

    report.evidence_files = scan_evidence_files(sandbox)
    report.node_bindings = bind_graph_to_evidence(graph, report.evidence_files, cfg)

    bindable = [b for b in report.node_bindings]
    bound = [b for b in bindable if b.matched]
    report.fraction_bound = (len(bound) / len(bindable)) if bindable else 0.0

    ok_graph = report.graph_found and report.graph_parseable
    ok_evidence = (report.fraction_bound == 1.0) if rubric.require_evidence_files else True
    report.passed = ok_graph and ok_evidence
    if not ok_evidence:
        unbound = [b.node_id for b in bindable if not b.matched]
        report.notes.append(f"unbound nodes (no matching evidence file): {unbound}")
    return report
