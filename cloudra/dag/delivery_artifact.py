"""Validate the existing authored delivery against its authoritative DAG."""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from cloudra.benchmark.barrier_evidence import DECLARED_ENERGY_TOL_HARTREE, HARTREE_TO_KCAL_MOL
from cloudra.benchmark.schema import GoldMechanismGraph, NodeRole
from cloudra.dag.evidence_ingest import FileEvidenceSnapshot, _extract_qm_log
from cloudra.dag.file_science import (
    _geometry_species,
    _logs,
    _optimization_converged,
    file_scientific_checks,
    validate_frequency_geometry,
)
from cloudra.persistence.paths import mechanism_graph_path
from cloudra.tools.core import gaussian_frames, orca_frames, xtb_frames


class DeliveryArtifact(BaseModel):
    model_config = ConfigDict(frozen=True, extra='forbid')
    path: str
    sha256: str
    graph_revision: int
    scientific_checks: dict[str, dict]
    target_ids: dict[str, str]
    snapshot_path: str | None = None


def current_artifact_digest(path: str) -> str | None:
    candidate = Path(path)
    return hashlib.sha256(candidate.read_bytes()).hexdigest() if candidate.is_file() else None


def prepare_delivery_artifact(store, graph, report, workspace_root, *, required=False, disposition="complete"):
    if workspace_root is None:
        if required:
            raise ValueError('Benchmark delivery requires a project workspace and mechanism_graph.json.')
        return None
    root = Path(workspace_root).resolve()
    path = mechanism_graph_path(root)
    if not path.exists():
        if required:
            raise ValueError('Benchmark delivery requires mechanism_graph.json before requesting exit approval.')
        return None
    if not path.resolve().is_relative_to(root):
        raise ValueError('Delivery artifact must remain inside the project workspace.')
    content = path.read_bytes()
    raw = json.loads(content)
    json.dumps(raw, allow_nan=False)
    document = GoldMechanismGraph.model_validate(raw)
    if len({n.id for n in document.nodes}) != len(document.nodes) or len({e.id for e in document.edges}) != len(document.edges):
        raise ValueError('Delivery artifact contains duplicate node or edge IDs.')
    if {n.id for n in document.nodes} & {e.id for e in document.edges}:
        raise ValueError('Delivery artifact node and edge IDs must occupy distinct names.')
    partial = disposition == "partial"
    species = {}
    checks = {}
    target_ids = {}
    energies = {}
    open_targets = {g.target_id for g in [*report.unresolved, *report.inconclusive, *report.waived]}
    reviews = store.list_review_requests(state=None)

    def current_evidence(element):
        target_id = getattr(element, 'node_id', None) or element.edge_id
        request = next((r for r in reversed(reviews) if r.kind == 'evidence'
                        and r.proposal.get('element_type') in {'species', 'step'}
                        and r.target_ids == [target_id] and r.supporting_refs
                        and all(ref in element.refs for ref in r.supporting_refs)), None)
        return element.model_copy(update={'refs': request.supporting_refs, 'stages': []}) if request else element

    def scientific_checks(element):
        target_id = getattr(element, 'node_id', None) or element.edge_id
        request = next((r for r in reversed(reviews) if r.kind == 'evidence'
                        and r.proposal.get('element_type') in {'species', 'step'}
                        and r.target_ids == [target_id] and r.supporting_refs
                        and all(ref in element.refs for ref in r.supporting_refs)), None)
        return file_scientific_checks(store, graph, target_id, workspace_root=root,
            evidence_refs=request.supporting_refs if request else None,
            irc_files=request.proposal.get('irc_files') if request else None,
            endpoint_refs=request.proposal.get('endpoint_refs') if request else None)

    def match_species(node):
        matches = [n for n in graph.nodes if node.id in {n.node_id, n.name}]
        if not matches and partial:
            return None
        if len(matches) != 1:
            raise ValueError(f'Species {node.id!r} must identify exactly one DAG species by its ID or name.')
        expected = matches[0]
        if node.smiles != ([expected.smiles] if expected.smiles else []):
            raise ValueError(f'Species {node.id!r} SMILES differs from its DAG declaration {expected.smiles!r}.')
        if expected.node_id in {n.node_id for n in species.values() if n is not None}:
            raise ValueError('Multiple artifact species identify the same DAG occurrence.')
        return expected

    def bound_energy(element, node):
        declared = node.properties.get('evidence_log')
        if not isinstance(declared, str):
            raise ValueError(f'{node.id!r} requires an explicit bound evidence_log for its energy claim.')
        candidate = Path(declared)
        if not candidate.is_absolute():
            candidate = root / candidate
        if not candidate.resolve().is_relative_to(root):
            raise ValueError('Declared evidence log escapes the project workspace.')
        element = current_evidence(element)
        usable_logs, _ = _logs(store, element, root)
        for ref in [*element.refs, *[s.ref for s in element.stages if s.ref is not None]]:
            payload = store.resolve_evidence(ref)
            if not isinstance(payload, dict):
                continue
            paths = [payload.get('original_path'), payload.get('snapshot_path'),
                     (payload.get('arguments') or {}).get('log_path')]
            if not any(isinstance(p, str) and Path(p).resolve() == candidate.resolve() for p in paths):
                continue
            if 'snapshot_path' not in payload:
                raise ValueError('Energy declarations require a bound immutable file snapshot; re-submit the log file.')
            snapshot = FileEvidenceSnapshot.model_validate(payload)
            if snapshot.snapshot_path not in usable_logs:
                raise ValueError('Declared log did not pass the bound immutable-file checks.')
            if current_artifact_digest(str(candidate)) != snapshot.sha256:
                raise ValueError(f'Declared log {declared!r} differs from its bound immutable evidence.')
            path = Path(snapshot.snapshot_path)
            expected_imag = 1 if node.role is NodeRole.TRANSITION_STATE else 0
            imag = _extract_qm_log(path)[3]
            if imag is not None and len(imag) != expected_imag:
                raise ValueError(f'Declared energy log for {node.id!r} has the wrong imaginary-frequency count.')

            def same_geometry(raw):
                evidence_path = Path(raw)
                other = FileEvidenceSnapshot(original_path=raw, snapshot_path=raw,
                    sha256=current_artifact_digest(raw), file_size=evidence_path.stat().st_size)
                try:
                    validate_frequency_geometry(snapshot, other)
                except ValueError:
                    return False
                return True

            if not any(len(_extract_qm_log(Path(p))[3] or []) == expected_imag
                       and _extract_qm_log(Path(p))[3] is not None and same_geometry(p) for p in usable_logs):
                raise ValueError('Declared energy log has no matching frequency-verified geometry.')
            if expected_imag == 1 and not any(
                    _optimization_converged(p, _extract_qm_log(Path(p))[1]) is True
                    and same_geometry(p) for p in usable_logs):
                raise ValueError('Declared TS energy log has no matching converged optimization geometry.')
            if node.role is not NodeRole.TRANSITION_STATE and not _geometry_species(str(path), element.smiles):
                raise ValueError(f'Declared energy log does not match the whole species {node.id!r}.')
            text = path.read_text(errors='replace')
            if snapshot.engine == 'orca':
                energy = orca_frames.final_energy_hartree(text)
            elif snapshot.engine == 'xtb':
                energy = xtb_frames.final_energy_hartree(text)
            elif snapshot.engine == 'gaussian':
                energy = next((f.scf_energy_hartree for f in reversed(gaussian_frames.extract_frames(str(path)))
                               if f.scf_energy_hartree is not None), None)
            else:
                energy = None
            if energy is None:
                raise ValueError(f'No native final energy in declared log {declared!r}.')
            claimed = node.properties.get('energy_hartree', energy)
            if isinstance(claimed, bool) or not isinstance(claimed, (int, float)) or not math.isfinite(claimed):
                raise ValueError('energy_hartree must be a finite number.')
            if abs(claimed - energy) > DECLARED_ENERGY_TOL_HARTREE:
                raise ValueError(f'Declared energy of {node.id!r} differs from its native bound log energy.')
            return energy
        raise ValueError(f'Evidence log {declared!r} is not bound to DAG target {element.name!r}.')

    for node in document.nodes:
        if node.role is NodeRole.TRANSITION_STATE:
            continue
        element = match_species(node)
        species[node.id] = element
        if element is None:
            checks[node.id] = {'geometry': {'status': 'unreviewed',
                'reason': 'Exploratory output is not submitted for DAG review.'}}
            continue
        target_ids[node.id] = element.node_id
        checks[node.id] = scientific_checks(element)
        if 'energy_hartree' in node.properties or 'evidence_log' in node.properties:
            log = node.properties.get('evidence_log')
            if not isinstance(log, str) or checks[node.id]['geometry']['status'] != 'passed':
                raise ValueError(f'Species {node.id!r} cannot claim a minimum energy without matching bound geometry evidence.')
            energies[node.id] = bound_energy(element, node)

    declared_ts = {n.id: n for n in document.nodes if n.role is NodeRole.TRANSITION_STATE}
    used_edges = set()
    used_ts = set()
    for edge in document.edges:
        if edge.barrier_kcal_mol is not None and not math.isfinite(edge.barrier_kcal_mol):
            raise ValueError('barrier_kcal_mol must be finite.')
        if edge.from_node not in species or edge.to_node not in species:
            raise ValueError('A step must connect species, not transition-state nodes.')
        source, target = species[edge.from_node], species[edge.to_node]
        named = [e for e in graph.edges if edge.id in {e.edge_id, e.name}]
        if named and (source is None or target is None or any(
                e.source_node_id != source.node_id or e.target_node_id != target.node_id for e in named)):
            raise ValueError(f'Step {edge.id!r} changes the endpoints of its DAG declaration.')
        candidates = [e for e in graph.edges if source is not None and target is not None
                      and e.source_node_id == source.node_id and e.target_node_id == target.node_id]
        # A partial artifact may retain another attempt for the same reaction.
        # Only explicit DAG IDs/names claim completion credit; endpoints alone
        # must not turn an exploratory candidate into the declared step.
        matches = named if partial else (named or candidates)
        if not matches and partial:
            checks[edge.id] = {'connectivity': {'status': 'unreviewed',
                'reason': 'Exploratory output does not earn DAG completion credit.'}}
            if edge.via is not None:
                used_ts.add(edge.via)
                checks[edge.via] = {'saddle': {'status': 'unreviewed',
                    'reason': 'Exploratory candidate is not submitted for DAG review.'}}
            continue
        if len(matches) != 1 or matches[0].edge_id in used_edges:
            raise ValueError(f'Step {edge.id!r} does not uniquely match one DAG step with the same endpoints.')
        element = matches[0]
        used_edges.add(element.edge_id)
        target_ids[edge.id] = element.edge_id
        step_checks = scientific_checks(element)
        checks[edge.id] = step_checks
        verified = element.edge_id not in open_targets and all(c['status'] == 'passed' for c in step_checks.values())
        if edge.barrier_kcal_mol is not None and not verified:
            raise ValueError(f'Step {edge.id!r} cannot declare a barrier before its DAG scientific checks and review pass.')
        requires_ts = not element.stages or any(s.required and s.kind.value in {'ts_opt', 'frequency'} and s.status.value != 'not_applicable' for s in element.stages)
        if requires_ts and edge.via is None and not (partial and not verified):
            raise ValueError(f'Step {edge.id!r} requires a TS reference; missing evidence does not remove that requirement.')
        if edge.via is not None:
            used_ts.add(edge.via)
            node = declared_ts[edge.via]
            if 'energy_hartree' in node.properties or 'evidence_log' in node.properties:
                log = node.properties.get('evidence_log')
                if not isinstance(log, str) or any(step_checks[k]['status'] != 'passed' for k in ('ts_opt', 'frequency')):
                    raise ValueError(f'TS {node.id!r} cannot claim saddle evidence without bound converged optimization and frequency logs.')
                energies[node.id] = bound_energy(element, node)
        if edge.barrier_kcal_mol is not None:
            if edge.from_node not in energies or edge.via not in energies:
                raise ValueError('A declared barrier requires explicit bound source and TS energy logs.')
            derived = (energies[edge.via] - energies[edge.from_node]) * HARTREE_TO_KCAL_MOL
            # Reuse the existing declaration-rounding allowance for the two
            # operands. This checks the authored arithmetic, not Gold accuracy.
            if abs(edge.barrier_kcal_mol - derived) > 2 * DECLARED_ENERGY_TOL_HARTREE * HARTREE_TO_KCAL_MOL:
                raise ValueError(f'Declared barrier of {edge.id!r} differs from its bound log energies.')
    if not partial and used_ts != set(declared_ts):
        raise ValueError('Artifact contains TS nodes not associated with a declared DAG step.')
    represented = {n.node_id for n in species.values() if n is not None} | used_edges
    required_targets = {g.target_id for g in [*report.satisfied, *report.unresolved, *report.inconclusive] if g.target_type in {'node', 'edge'}}
    if required_targets - represented:
        raise ValueError(f'Artifact omits declared delivery targets: {sorted(required_targets - represented)}.')
    return DeliveryArtifact(path=str(path), sha256=hashlib.sha256(content).hexdigest(),
        graph_revision=graph.revision, scientific_checks=checks, target_ids=target_ids)
