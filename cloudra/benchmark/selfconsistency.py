"""Layer 2 — self-consistency: per-element evidence coverage of the delivered graph.

Independent of the gold reference. The unit of judgment is the **delivered
graph element** (species node / TS-bearing edge), not the sandbox directory:

- Every accessible node and edge must have evidence bound to it (Layer 1
  bindings). Elements with no evidence are only excused when the delivery
  explicitly declares them meaningless via ``accessible=false`` — for edges the
  effective accessibility applies (an edge routed via an inaccessible TS node
  counts as declared inaccessible; ``GoldMechanismGraph.edge_effectively_accessible``).
- For each element, usable bound evidence must cover its required checks:
  one verified minimum covers a whole species or complex; separated species
  need a verified minimum for each declared list member.
  One first-order saddle plus one direction-proven IRC
  covers a TS edge. Trial-and-error leftovers in the sandbox are never
  judged — unbound files do not exist for this layer — and a superseded
  failed attempt that *is* bound cannot veto a good log bound alongside it.

Required evidence per element:

- species node (reactant/product/intermediate): one bound QM log whose
  frequency block shows zero imaginary frequencies (a verified minimum),
  or a separate normally terminated frequency log at that same geometry;
  verified minimum logs must cover each separated species; a dot-connected
  complex requires its own whole-system minimum;
- edge via a TS node (candidate pool = bound files of the TS node and both
  endpoints): one bound log with exactly one imaginary frequency
  (``ts_first_order_saddle``) and one bound IRC log passing the strict
  path-direction proof (``irc_connects_endpoints``): both IRC directions start
  at that TS, and native optimization logs connect their outer frames to the
  corresponding zero-imaginary-frequency endpoint minima. IRC itself need not
  converge to either minimum. Geometric intervals are advisory diagnostics.
  Each rubric flag gates its own check;
- edge without ``via``: covered once both endpoint species are covered;
- TS node: rides on its edges — covered when at least one accessible edge
  through it is covered, otherwise it must itself be declared inaccessible.

Species identity (SMILES consistency) follows Layer 1's evidence-binding
rules, reapplied to eligible minimum logs for complexes. ORCA/Gaussian logs
are judged from their native evidence; file size is not a scientific verdict.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from itertools import combinations
from pathlib import Path
from typing import Optional

from cloudra.benchmark.graph_similarity import GedConfig
from cloudra.benchmark.integrity import (
    EvidenceFile,
    NodeBinding,
    bind_graph_to_evidence,
    find_graph_json,
)
from cloudra.benchmark.schema import (
    GoldMechanismGraph,
    IntegrityRubric,
    NodeRole,
    SelfConsistencyRubric,
)
from cloudra.tools.core.irc_evidence import (
    normal_log,
    verify_short_irc_direction,
    verify_short_irc_pair,
)
from cloudra.tools.core.qm_log_facts import read_qm_log


@dataclass
class ElementCheck:
    """一个图元素（节点/边）的覆盖判定。"""

    element_id: str
    kind: str  # "species" | "transition_state" | "edge"
    declared_inaccessible: bool = False
    bound: bool = False
    covered: bool = False
    evidence_used: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


@dataclass
class SelfConsistencyReport:
    checks: list[ElementCheck] = field(default_factory=list)
    passed: bool = False
    notes: list[str] = field(default_factory=list)


class _LogProbe:
    """按路径缓存的日志探针：同一绑定文件可能被多个元素引用，只解析一次。

    只解析正常终止的 QM 日志（gaussian/orca）；
    其余一律返回 None——绑定了不可解析文件不等于有可用证据。"""

    def __init__(self, sandbox: Path, files_by_path: dict[str, EvidenceFile]):
        self._sandbox = sandbox
        self._files = files_by_path
        self._cache: dict[str, tuple[Optional[int], Optional[tuple]]] = {}

    def _parse(self, rel_path: str) -> tuple[Optional[int], Optional[tuple]]:
        """(虚频数, 末帧几何)。虚频数 None = 无频率块/文件不可解析。"""
        if rel_path not in self._cache:
            result: tuple[Optional[int], Optional[tuple]] = (None, None)
            f = self._files.get(rel_path)
            if (
                f is not None
                and f.kind in ("gaussian", "orca")
            ):
                try:
                    facts = read_qm_log(self._sandbox / rel_path)
                except (OSError, ValueError):
                    facts = None
                if facts is not None and facts.engine in {'gaussian', 'orca'} and facts.normal_termination:
                    freqs = facts.frequencies_cm
                    n_imag = sum(freq < 0 for freq in freqs) if freqs else None
                    result = (n_imag, facts.geometry)
            self._cache[rel_path] = result
        return self._cache[rel_path]

    def n_imag(self, rel_path: str) -> Optional[int]:
        return self._parse(rel_path)[0]

    def last_geometry(self, rel_path: str) -> Optional[tuple]:
        """末帧几何 (symbols, positions)；无坐标帧返回 None。"""
        return self._parse(rel_path)[1]

    def ts_witness(self, anchor, pool):
        from cloudra.tools.core.irc_path import same_geometry
        if self.n_imag(anchor) == 1:
            return anchor
        geometry = self.last_geometry(anchor)
        return next((p for p in sorted(pool) if self.n_imag(p) == 1 and
                     same_geometry(geometry, self.last_geometry(p))), None)

    def minimum_witness(self, anchor, pool):
        """Verify the bound geometry, never substitute a historical minimum."""
        from cloudra.tools.core.irc_path import same_geometry
        if self.n_imag(anchor) == 0:
            return anchor
        geometry = self.last_geometry(anchor)
        return next((p for p in sorted(pool) if self.n_imag(p) == 0 and
                     same_geometry(geometry, self.last_geometry(p))), None)

    def irc_atom_binding(self, rel_path: str):
        evidence = self._files.get(rel_path)
        if evidence is None or evidence.kind not in {'gaussian', 'orca'}:
            return None
        from cloudra.tools.core.orca_frames import _archived_irc_endpoints

        endpoints = _archived_irc_endpoints(str(self._sandbox / rel_path))
        return endpoints['forward'].get('atom_binding') if endpoints is not None else None


def _strict_irc_proof(
    probe: _LogProbe,
    pool: list[str],
    from_files: list[str],
    to_files: list[str],
    charge: int = 0,
    *, ts_files: list[str] | None = None, product_smiles: list[str] | None = None,
    reactant_smiles: list[str] | None = None, details: list[str] | None = None,
    endpoint_evidence: dict[str, list[str]] | None = None,
) -> Optional[tuple[list[str], list[str]]]:
    """Reconstruct the same native IRC→Opt→Freq proof used by DAG and tools."""
    from cloudra.tools.core import gaussian_frames, orca_frames
    from cloudra.tools.core.irc_evidence import irc_start_geometry
    from cloudra.tools.core.irc_path import same_geometry

    ts_candidates = [(p, witness) for p in sorted(ts_files if ts_files is not None else pool)
                     for witness in (probe.ts_witness(p, pool),) if witness is not None]

    def endpoint_candidates(anchors):
        candidates = set()
        for anchor in anchors:
            witness = probe.minimum_witness(anchor, pool)
            if witness is None:
                continue
            candidates.update((anchor, witness))
            geometry = probe.last_geometry(witness)
            candidates.update(path for path in pool
                              if same_geometry(geometry, probe.last_geometry(path)))
        return sorted(candidates)

    # The energy reference identifies the delivered species geometry. An
    # approved step can end at a separately optimized minimum of that species;
    # keep its exact bound Opt/Freq logs instead of replacing them with history.
    source = endpoint_evidence["source"] if endpoint_evidence is not None else endpoint_candidates(from_files)
    target = endpoint_evidence["target"] if endpoint_evidence is not None else endpoint_candidates(to_files)
    failures = [
        f"IRC proof TS candidates (anchor, frequency witness): {ts_candidates or ts_files}; "
        f"SOURCE endpoint evidence: {source or from_files}; TARGET endpoint evidence: {target or to_files}."
    ]

    def failed():
        if details is not None:
            details.extend(dict.fromkeys(failures))
        return None

    irc_logs = []
    for path in sorted(pool):
        native = probe._sandbox / path
        try:
            normal = normal_log(native)
            start = irc_start_geometry(native) if normal else None
        except (OSError, ValueError) as exc:
            failures.append(f'QM evidence candidate {path} is unusable: {exc}')
            continue
        if normal and start is not None:
            irc_logs.append(path)
            continue
        evidence = probe._files.get(path)
        if evidence is None or evidence.kind not in {'gaussian', 'orca'}:
            continue
        parser = gaussian_frames if evidence.kind == 'gaussian' else orca_frames
        try:
            jobs = parser.detect_job_types(str(native))
        except OSError as exc:
            failures.append(f'QM evidence candidate {path} could not be read: {exc}')
            continue
        if 'irc' not in jobs:
            continue
        try:
            parser.extract_irc(str(native))
        except ValueError as exc:
            failures.append(f'IRC candidate {path} is unusable: {exc}')
        if not normal:
            failures.append(f'IRC candidate {path} lacks normally terminated native evidence.')
        elif start is None:
            failures.append(f'IRC candidate {path} has no usable native starting saddle.')
    if not irc_logs:
        failures.append('No normally terminated IRC candidate supplies a native starting saddle.')
    if not (ts_candidates and source and target):
        failures.append('IRC proof requires a same-geometry first-order saddle witness and verified minima for both endpoints.')
        return failed()

    def absolute(paths):
        return [probe._sandbox / path for path in paths]

    for ts_path, frequency_path in ts_candidates:
        bindings = {}
        for path in irc_logs:
            binding = probe.irc_atom_binding(path)
            if binding and hashlib.sha256((probe._sandbox / frequency_path).read_bytes()).hexdigest() == binding.get('ts_log_sha256'):
                bindings[str(probe._sandbox / path)] = binding
                bindings[str(probe._sandbox / frequency_path)] = binding
                binding_status = 'verified for the selected frequency witness'
            else:
                binding_status = 'absent' if not binding else 'not associated with the selected frequency witness'
            failures.append(f'IRC candidate {path}, TS {ts_path}, frequency witness {frequency_path}: atom binding {binding_status}.')
        options = dict(atom_bindings=bindings, product_smiles=product_smiles,
                       reactant_smiles=reactant_smiles)
        for path in irc_logs:
            passed, proof_details = verify_short_irc_direction(probe._sandbox / path,
                absolute([frequency_path]), absolute(target), absolute(source),
                charge=charge, **options)
            if passed:
                return list(dict.fromkeys([ts_path, frequency_path, path, *source, *target])), proof_details
            failures.extend(f'IRC {path}, TS {frequency_path}: {item}' for item in proof_details)
        for forward, reverse in combinations(irc_logs, 2):
            passed, proof_details = verify_short_irc_pair(probe._sandbox / forward, probe._sandbox / reverse,
                absolute([frequency_path]), absolute(target), absolute(source), charge=charge, **options)
            if passed:
                return list(dict.fromkeys([ts_path, frequency_path, forward, reverse, *source, *target])), proof_details
            failures.extend(f'IRC pair {forward}; {reverse}, TS {frequency_path}: {item}' for item in proof_details)
    return failed()


def audit_self_consistency(
    graph: Optional[GoldMechanismGraph],
    bindings: list[NodeBinding],
    evidence_files: list[EvidenceFile],
    sandbox: Path,
    rubric: Optional[SelfConsistencyRubric] = None,
    charge: int = 0,
    *,
    integrity_rubric: Optional[IntegrityRubric] = None,
    ged_config: Optional[GedConfig] = None,
) -> SelfConsistencyReport:
    rubric = rubric or SelfConsistencyRubric()
    integrity_rubric = integrity_rubric or IntegrityRubric()
    report = SelfConsistencyReport()
    if not (rubric.ts_first_order_saddle or rubric.irc_connects_endpoints):
        report.passed = True
        report.notes.append("self-consistency checks disabled by rubric; passthrough")
        return report
    if graph is None:
        report.notes.append("no delivered graph; self-consistency not assessable")
        return report

    from cloudra.benchmark.delivery_evidence import read_step_endpoint_evidence

    step_endpoints = {}
    endpoint_error = None
    if rubric.irc_connects_endpoints:
        try:
            graph_path = find_graph_json(sandbox)
            digest = hashlib.sha256(graph_path.read_bytes()).hexdigest() if graph_path is not None else ""
            step_endpoints = read_step_endpoint_evidence(sandbox, digest)
        except (OSError, ValueError) as exc:
            endpoint_error = str(exc)

    files_by_path = {f.path: f for f in evidence_files}
    probe = _LogProbe(sandbox, files_by_path)
    qm_paths = [f.path for f in evidence_files if f.kind in {'gaussian', 'orca'}]
    bmap = {b.node_id: b for b in bindings}
    species_covered: dict[str, bool] = {}
    edge_checks: dict[str, ElementCheck] = {}

    # 物种节点：极小值证据须覆盖整络合物或每个分开交付的组分。
    for node in graph.nodes:
        if node.role == NodeRole.TRANSITION_STATE:
            continue
        chk = ElementCheck(element_id=node.id, kind="species")
        report.checks.append(chk)
        if not node.accessible:
            chk.declared_inaccessible = True
            chk.covered = True
            chk.notes.append("declared inaccessible; evidence not required")
        else:
            b = bmap.get(node.id)
            chk.bound = bool(b and b.matched)
            if not chk.bound:
                chk.notes.append("no evidence bound to this node")
            else:
                minimum_witnesses = {
                    p: witness for p in b.bound_files
                    for witness in (probe.minimum_witness(p, qm_paths),)
                    if witness is not None
                }
                if len(node.smiles) > 1 or any("." in species for species in node.smiles):
                    # Recheck component coverage using verified bound anchors;
                    # replacing anchors with Freq paths loses explicit references.
                    minimum_files = [files_by_path[p] for p in minimum_witnesses]
                    minimum_binding = bind_graph_to_evidence(
                        GoldMechanismGraph(nodes=[node], edges=[]), minimum_files,
                        ged_config,
                        match_threshold=integrity_rubric.match_threshold,
                        partial_quality=integrity_rubric.protonation_partial_quality,
                        sandbox=sandbox,
                    )[0]
                    chk.covered = minimum_binding.matched
                    if chk.covered:
                        chk.evidence_used.extend(dict.fromkeys(
                            path for anchor in minimum_binding.bound_files
                            for path in (anchor, minimum_witnesses[anchor])
                        ))
                    else:
                        chk.notes.append("verified minima do not cover every declared species; a complex needs its own minimum")
                else:
                    for p, witness in minimum_witnesses.items():
                        chk.covered = True
                        chk.evidence_used.extend(dict.fromkeys([p, witness]))
                        break
                if not chk.covered and not chk.notes:
                    chk.notes.append(
                        "no verified minimum (frequency block with zero "
                        "imaginary frequencies) among bound evidence"
                    )
        species_covered[node.id] = chk.covered

    # 边：TS 步查一阶鞍点 + IRC 方向区间证明（各按 rubric 开关），任一合格证据即覆盖
    for edge in graph.edges:
        chk = ElementCheck(element_id=edge.id, kind="edge")
        report.checks.append(chk)
        edge_checks[edge.id] = chk
        if not graph.edge_effectively_accessible(edge):
            # 有效不可达（边自身 accessible=false，或经由的 TS 节点不可达）视同
            # declared_inaccessible 豁免——与图分/accuracy 同一口径
            # （schema.edge_effectively_accessible）
            chk.declared_inaccessible = True
            chk.covered = True
            chk.notes.append(
                "effectively inaccessible (the edge or its via transition state); "
                "evidence not required"
            )
            continue
        if edge.via is None:
            endpoints_bound = all(
                (bmap.get(nid) is not None and bmap[nid].matched)
                for nid in (edge.from_node, edge.to_node)
            )
            chk.bound = endpoints_bound
            chk.covered = species_covered.get(edge.from_node, False) and (
                species_covered.get(edge.to_node, False)
            )
            if not chk.covered:
                chk.notes.append("no TS node on this edge; endpoint species not both covered")
            continue
        pool: set[str] = set()
        for nid in (edge.via, edge.from_node, edge.to_node):
            b = bmap.get(nid)
            if b and b.matched:
                pool.update(b.bound_files)
        ts_binding = bmap.get(edge.via)
        ts_files = list(ts_binding.bound_files) if ts_binding and ts_binding.matched else []
        # IRC logs are candidates only; the native starting geometry must match
        # the selected TS. Endpoint annotations do not establish that lineage.
        pool.update(qm_paths)
        chk.bound = bool(ts_files)
        if not ts_files:
            chk.notes.append(
                f"no evidence explicitly associated with TS {edge.via}; declare its evidence_log or energy_hartree"
            )
            continue
        saddle_ok = not rubric.ts_first_order_saddle
        irc_ok = not rubric.irc_connects_endpoints
        for p in sorted(ts_files):
            witness = probe.ts_witness(p, pool)
            if not saddle_ok and witness is not None:
                saddle_ok = True
                chk.evidence_used.extend(dict.fromkeys([p, witness]))
                break
        if not irc_ok:
            if endpoint_error is not None:
                chk.notes.append(endpoint_error)
                continue
            from_binding = bmap.get(edge.from_node)
            to_binding = bmap.get(edge.to_node)
            from_files = (
                list(from_binding.bound_files)
                if from_binding and from_binding.matched else []
            )
            to_files = (
                list(to_binding.bound_files)
                if to_binding and to_binding.matched else []
            )
            proof = _strict_irc_proof(probe, sorted(pool), from_files, to_files, charge,
                ts_files=ts_files,
                details=chk.notes,
                endpoint_evidence=step_endpoints.get(edge.id),
                product_smiles=next(node.smiles for node in graph.nodes if node.id == edge.to_node),
                reactant_smiles=next(node.smiles for node in graph.nodes if node.id == edge.from_node))
            if proof is not None:
                irc_ok = True
                saddle_ok = True
                chk.evidence_used, details = proof
                chk.notes.extend(details)
        chk.covered = saddle_ok and irc_ok
        if not saddle_ok:
            chk.notes.append(
                "no first-order saddle (exactly one imaginary frequency) "
                "among bound evidence"
            )
        if not irc_ok:
            chk.notes.append(
                "no same-TS bidirectional IRC whose outer frames are connected by native "
                "converged optimization logs to the declared verified endpoint minima"
            )

    # TS 节点随边覆盖：至少一条 accessible 的边经由它且被覆盖；否则必须自我声明豁免
    for node in graph.nodes:
        if node.role != NodeRole.TRANSITION_STATE:
            continue
        chk = ElementCheck(element_id=node.id, kind="transition_state")
        report.checks.append(chk)
        covering = [
            e.id for e in graph.edges
            if e.via == node.id and e.accessible and edge_checks[e.id].covered
        ]
        if covering:
            chk.bound = True
            chk.covered = True
        elif not node.accessible:
            chk.declared_inaccessible = True
            chk.covered = True
            chk.notes.append("declared inaccessible; evidence not required")
        else:
            b = bmap.get(node.id)
            chk.bound = bool(b and b.matched)
            chk.notes.append("no accessible edge through this TS is covered")

    report.passed = all(c.covered for c in report.checks)
    for c in report.checks:
        if not c.covered:
            for n in c.notes:
                report.notes.append(f"{c.kind} {c.element_id}: {n}")
    return report
