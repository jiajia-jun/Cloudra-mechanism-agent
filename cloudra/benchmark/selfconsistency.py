"""Layer 2 — self-consistency: per-element evidence coverage of the delivered graph.

Independent of the gold reference. The unit of judgment is the **delivered
graph element** (species node / TS-bearing edge), not the sandbox directory:

- Every accessible node and edge must have evidence bound to it (Layer 1
  bindings). Elements with no evidence are only excused when the delivery
  explicitly declares them meaningless via ``accessible=false``.
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
from cloudra.tools.core import gaussian_frames, orca_frames, qm_engine
from cloudra.tools.core.irc_path import assign_irc_endpoints, parse_xyz


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


def _frames_for(path: Path):
    """Return (frames, irc_meta). 两种解析各自隔离：opt+freq 日志没有 IRC 段
    是正常情况，不能让 extract_irc 的异常把已解析的 frames 一并丢弃。

    IRC meta 已归一化为 dict：gaussian_frames.extract_irc 返回
    (frames, meta) 二元组，orca_frames.extract_irc 直接返回 meta dict。
    """
    engine = qm_engine.detect_qm_engine(str(path))
    mod = orca_frames if engine == "orca" else gaussian_frames
    try:
        frames = mod.extract_frames(str(path))
    except Exception:
        frames = []
    try:
        raw_irc = mod.extract_irc(str(path))
    except Exception:
        raw_irc = None
    if isinstance(raw_irc, tuple):
        irc_meta = raw_irc[1] if len(raw_irc) == 2 else None
    else:
        irc_meta = raw_irc
    return frames, irc_meta


def _last_freqs(frames) -> list[float]:
    for fr in reversed(frames):
        if fr.frequencies_cm:
            return list(fr.frequencies_cm)
    return []


def _freqs_for(path: Path, frames) -> list[float]:
    """末帧频率；cclib 对 ORCA 6.1 日志裸抛 IndexError（帧为空）时回退
    文本权威 VIBRATIONAL FREQUENCIES 块（统一入口在 orca_frames）。"""
    freqs = _last_freqs(frames)
    if freqs:
        return freqs
    if qm_engine.detect_qm_engine(str(path)) == "orca":
        return orca_frames.frequencies_with_text_fallback(str(path))
    return []


def _imag_freqs(freqs: list[float]) -> list[float]:
    return [f for f in freqs if f < 0]


def _irc_frames_for(path: Path):
    """IRC 逐点帧。Gaussian 主日志内含逐点坐标；ORCA 的逐点坐标在边文件里，
    主日志没有（端点几何走 _orca_irc_endpoint_geometries 的边文件通道）。"""
    try:
        raw = gaussian_frames.extract_irc(str(path))
    except Exception:
        return []
    if isinstance(raw, tuple) and raw:
        return list(raw[0]) if raw[0] else []
    return []


def _gaussian_irc_endpoint_geometries(path: Path):
    """ts_guess strict 同口径的 Gaussian IRC 端点：rx<0 / rx>0 两侧各自最外侧
    的带坐标帧（不要求收敛到极小值）。"""
    frames = _irc_frames_for(path)
    valid = [fr for fr in frames if getattr(fr, "xyz", "").strip()]
    neg = [
        fr for fr in valid
        if fr.reaction_coordinate is not None and fr.reaction_coordinate < 0
    ]
    pos = [
        fr for fr in valid
        if fr.reaction_coordinate is not None and fr.reaction_coordinate > 0
    ]
    if not neg or not pos:
        return None
    end_a = min(neg, key=lambda fr: fr.reaction_coordinate)
    end_b = max(pos, key=lambda fr: fr.reaction_coordinate)
    geo_a = parse_xyz(end_a.xyz)
    geo_b = parse_xyz(end_b.xyz)
    if geo_a is None or geo_b is None:
        return None
    return geo_a, geo_b


def _orca_irc_endpoint_geometries(path: Path):
    """ts_guess strict 同口径的 ORCA IRC 端点：几何来自终点文件/F-B 轨迹边
    文件（未收敛方向取轨迹末帧，同样是合法的部分端点）；收敛与否不做闸门，
    方向是否成立交给几何区间证明。两侧都有可用几何才返回。

    前提是文件本身确实是 IRC 计算日志：输入文件（.inp）旁边恰好有同名
    轨迹边文件时，没有 IRC 段就没有任何"端点"可言。"""
    try:
        orca_frames.extract_irc(str(path))
    except Exception:
        return None  # 无 IRC 段（输入文件、非 IRC 作业）→ 不是 IRC 证据
    try:
        endpoints = orca_frames.extract_irc_endpoints(str(path))
    except Exception:
        return None
    xyz_a = orca_frames.read_endpoint_geometry(endpoints.get("forward", {}))
    xyz_b = orca_frames.read_endpoint_geometry(endpoints.get("backward", {}))
    if xyz_a is None or xyz_b is None:
        return None
    geo_a = parse_xyz(xyz_a)
    geo_b = parse_xyz(xyz_b)
    if geo_a is None or geo_b is None:
        return None
    return geo_a, geo_b


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
                geometry = None
                for fr in reversed(frames):
                    if getattr(fr, "xyz", "").strip():
                        geometry = parse_xyz(fr.xyz)
                        break
                if geometry is None and f.kind == "orca":
                    # cclib 对 ORCA 6.1 日志整体崩溃时帧为空——走文本权威
                    # CARTESIAN COORDINATES 块回退（同频率的文本回退纪律）
                    geometry = parse_xyz(
                        orca_frames.final_xyz_with_text_fallback(str(path))
                    )
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
) -> Optional[str]:
    """在绑定证据里完成 ts_guess strict 同口径的路径方向证明：找一组
    (TS 几何, 双侧 IRC 端点, 两端物种的验证极小值几何)，使两个 IRC 端点
    各自位于 TS 与对应极小值之间（direct/swapped 配对，watch_pairs 缺省走
    自动选取）。任一组合成立即返回用作证据的 IRC 日志路径，否则 None。"""
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
        (syms_a, pos_a), (syms_b, pos_b) = ends
        for ts_syms, ts_pos in ts_geos:
            if syms_a != ts_syms or syms_b != ts_syms:
                continue
            for from_syms, from_pos in from_geos:
                if from_syms != ts_syms:
                    continue
                for to_syms, to_pos in to_geos:
                    if to_syms != ts_syms:
                        continue
                    verdict = assign_irc_endpoints(
                        ts_syms, ts_pos, pos_a, pos_b, from_pos, to_pos, []
                    )
                    if verdict["is_decidable"] and verdict["is_match"]:
                        return p
    return None


def audit_self_consistency(
    graph: Optional[GoldMechanismGraph],
    bindings: list[NodeBinding],
    evidence_files: list[EvidenceFile],
    sandbox: Path,
    rubric: Optional[SelfConsistencyRubric] = None,
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
        if not edge.accessible:
            chk.declared_inaccessible = True
            chk.covered = True
            chk.notes.append("declared inaccessible; evidence not required")
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
            proof = _strict_irc_proof(probe, sorted(pool), from_files, to_files)
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
