"""Layer 2 — self-consistency: per-element evidence coverage of the delivered graph.

Independent of the gold reference. The unit of judgment is the **delivered
graph element** (species node / TS-bearing edge), not the sandbox directory:

- Every accessible node and edge must have evidence bound to it (Layer 1
  bindings). Elements with no evidence are only excused when the delivery
  explicitly declares them meaningless via ``accessible=false`` — for edges the
  effective accessibility applies (an edge routed via an inaccessible TS node
  counts as declared inaccessible; ``GoldMechanismGraph.edge_effectively_accessible``).
- For each element, **any single usable piece of its bound evidence** covers
  its required checks (existential, not universal): one verified minimum
  covers a species; one first-order saddle plus one direction-proven IRC
  covers a TS edge. Trial-and-error leftovers in the sandbox are never
  judged — unbound files do not exist for this layer — and a superseded
  failed attempt that *is* bound cannot veto a good log bound alongside it.

Required evidence per element:

- species node (reactant/product/intermediate): one bound QM log whose
  frequency block shows zero imaginary frequencies (a verified minimum);
- edge via a TS node (candidate pool = bound files of the TS node and both
  endpoints): one bound log with exactly one imaginary frequency
  (``ts_first_order_saddle``) and one bound IRC log passing the strict
  path-direction proof (``irc_connects_endpoints``) — same criterion as
  ``ts_guess verify strict=True``: convergence to a minimum is NOT required,
  but both sides' endpoint geometries (Gaussian: outermost frames on the
  rx<0/rx>0 sides; ORCA: endpoint files or outermost trajectory frames —
  an unconverged direction's last frame is a legitimate partial endpoint)
  must each lie geometrically between the TS and a corresponding verified
  endpoint minimum. Each rubric flag gates its own check;
- edge without ``via``: covered once both endpoint species are covered;
- TS node: rides on its edges — covered when at least one accessible edge
  through it is covered, otherwise it must itself be declared inaccessible.

Species identity (SMILES consistency) is Layer 1's evidence-binding job and
is not re-checked here. Only ORCA/Gaussian logs at or below MAX_SCAN_BYTES
are parsed (aligned with Layer 1, which never read them either).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from cloudra.benchmark.integrity import MAX_SCAN_BYTES, EvidenceFile, NodeBinding
from cloudra.benchmark.schema import (
    GoldMechanismGraph,
    NodeRole,
    SelfConsistencyRubric,
)
from cloudra.tools.core.irc_evidence import (
    frames_for as _frames_for,
)
from cloudra.tools.core.irc_evidence import (
    freqs_for as _freqs_for,
)
from cloudra.tools.core.irc_evidence import (
    gaussian_irc_endpoints_from_frames,
    iter_direction_verdicts,
)
from cloudra.tools.core.irc_evidence import (
    imag_freqs as _imag_freqs,
)
from cloudra.tools.core.irc_evidence import (
    irc_frames_for as _irc_frames_for,
)
from cloudra.tools.core.irc_evidence import (
    last_geometry as _last_geometry,
)
from cloudra.tools.core.irc_evidence import (
    orca_irc_endpoint_geometries as _orca_irc_endpoint_geometries,
)


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


def _gaussian_irc_endpoint_geometries(path: Path):
    """ts_guess strict 同口径的 Gaussian IRC 端点：rx<0 / rx>0 两侧各自最外侧
    的带坐标帧（不要求收敛到极小值）。

    实现唯一来源是 tools/core/irc_evidence（帧选取逻辑）；本 wrapper 保持
    逐点帧走模块级 ``_irc_frames_for`` 的读取通道（测试在该名字上拦截）。"""
    return gaussian_irc_endpoints_from_frames(_irc_frames_for(path))


class _LogProbe:
    """按路径缓存的日志探针：同一绑定文件可能被多个元素引用，只解析一次。

    只解析 Layer 1 意义上可读的 QM 日志（gaussian/orca 且 ≤ MAX_SCAN_BYTES）；
    其余一律返回 None——绑定了不可解析文件不等于有可用证据。"""

    def __init__(self, sandbox: Path, files_by_path: dict[str, EvidenceFile]):
        self._sandbox = sandbox
        self._files = files_by_path
        self._cache: dict[str, tuple[Optional[int], Optional[tuple]]] = {}
        self._irc_cache: dict[str, Optional[tuple]] = {}

    def _parse(self, rel_path: str) -> tuple[Optional[int], Optional[tuple]]:
        """(虚频数, 末帧几何)。虚频数 None = 无频率块/文件不可解析。"""
        if rel_path not in self._cache:
            result: tuple[Optional[int], Optional[tuple]] = (None, None)
            f = self._files.get(rel_path)
            if (
                f is not None
                and f.kind in ("gaussian", "orca")
                and f.size <= MAX_SCAN_BYTES
            ):
                path = self._sandbox / rel_path
                frames, _irc_meta = _frames_for(path)
                freqs = _freqs_for(path, frames)
                n_imag = len(_imag_freqs(freqs)) if freqs else None
                geometry = _last_geometry(path, frames)
                result = (n_imag, geometry)
            self._cache[rel_path] = result
        return self._cache[rel_path]

    def n_imag(self, rel_path: str) -> Optional[int]:
        return self._parse(rel_path)[0]

    def last_geometry(self, rel_path: str) -> Optional[tuple]:
        """末帧几何 (symbols, positions)；无坐标帧返回 None。"""
        return self._parse(rel_path)[1]

    def irc_endpoint_geometries(self, rel_path: str) -> Optional[tuple]:
        """双侧 IRC 端点几何 ((symbols, positions) × 2)，ts_guess strict 口径。"""
        if rel_path not in self._irc_cache:
            result = None
            f = self._files.get(rel_path)
            if f is not None and f.size <= MAX_SCAN_BYTES:
                path = self._sandbox / rel_path
                if f.kind == "gaussian":
                    result = _gaussian_irc_endpoint_geometries(path)
                elif f.kind == "orca":
                    result = _orca_irc_endpoint_geometries(path)
            self._irc_cache[rel_path] = result
        return self._irc_cache[rel_path]


def _strict_irc_proof(
    probe: _LogProbe,
    pool: list[str],
    from_files: list[str],
    to_files: list[str],
    charge: int = 0,
) -> Optional[str]:
    """在绑定证据里完成 ts_guess strict 同口径的路径方向证明：找一组
    (TS 几何, 双侧 IRC 端点, 两端物种的验证极小值几何)，使两个 IRC 端点
    各自位于 TS 与对应极小值之间（direct/swapped 配对）。任一组合成立即
    返回用作证据的 IRC 日志路径，否则 None。

    原子序无关：每组几何经 align_atom_order 重排进 TS 坐标序（距离指纹 +
    Hungarian，元素多重集不符的组合才跳过）——agent 用不同原子序重优化的
    端点极小值不再被误拒。"""
    ts_geos = []
    for p in sorted(pool):
        if probe.n_imag(p) == 1:
            geo = probe.last_geometry(p)
            if geo is not None:
                ts_geos.append(geo)
    from_geos = [
        geo for p in sorted(from_files)
        if probe.n_imag(p) == 0
        for geo in (probe.last_geometry(p),)
        if geo is not None
    ]
    to_geos = [
        geo for p in sorted(to_files)
        if probe.n_imag(p) == 0
        for geo in (probe.last_geometry(p),)
        if geo is not None
    ]
    if not (ts_geos and from_geos and to_geos):
        return None
    for p in sorted(pool):
        ends = probe.irc_endpoint_geometries(p)
        if ends is None:
            continue
        if any(
            verdict["is_decidable"] and verdict["is_match"]
            for verdict in iter_direction_verdicts(
                ends, ts_geos, from_geos, to_geos, charge=charge
            )
        ):
            return p
    return None


def audit_self_consistency(
    graph: Optional[GoldMechanismGraph],
    bindings: list[NodeBinding],
    evidence_files: list[EvidenceFile],
    sandbox: Path,
    rubric: Optional[SelfConsistencyRubric] = None,
    charge: int = 0,
) -> SelfConsistencyReport:
    rubric = rubric or SelfConsistencyRubric()
    report = SelfConsistencyReport()
    if not (rubric.ts_first_order_saddle or rubric.irc_connects_endpoints):
        report.passed = True
        report.notes.append("self-consistency checks disabled by rubric; passthrough")
        return report
    if graph is None:
        report.notes.append("no delivered graph; self-consistency not assessable")
        return report

    probe = _LogProbe(sandbox, {f.path: f for f in evidence_files})
    bmap = {b.node_id: b for b in bindings}
    species_covered: dict[str, bool] = {}
    edge_checks: dict[str, ElementCheck] = {}

    # 物种节点：任一绑定日志验证为极小值（频率块零虚频）即覆盖
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
                for p in b.bound_files:
                    if probe.n_imag(p) == 0:
                        chk.covered = True
                        chk.evidence_used.append(p)
                        break
                if not chk.covered:
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
        chk.bound = bool(pool)
        if not pool:
            chk.notes.append(
                f"no evidence bound to TS {edge.via} or the edge endpoints"
            )
            continue
        saddle_ok = not rubric.ts_first_order_saddle
        irc_ok = not rubric.irc_connects_endpoints
        for p in sorted(pool):
            if not saddle_ok and probe.n_imag(p) == 1:
                saddle_ok = True
                chk.evidence_used.append(p)
                break
        if not irc_ok:
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
            proof = _strict_irc_proof(probe, sorted(pool), from_files, to_files, charge)
            if proof is not None:
                irc_ok = True
                if proof not in chk.evidence_used:
                    chk.evidence_used.append(proof)
        chk.covered = saddle_ok and irc_ok
        if not saddle_ok:
            chk.notes.append(
                "no first-order saddle (exactly one imaginary frequency) "
                "among bound evidence"
            )
        if not irc_ok:
            chk.notes.append(
                "no IRC with endpoints proven to lie between the TS and the "
                "endpoint minima among bound evidence"
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
