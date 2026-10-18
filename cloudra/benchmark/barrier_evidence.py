"""RDS 能垒的交付物推导：只读 log 文件与交付 JSON，不解析任何 LLM 散文。

能垒口径（题库 query 协议一致）：**决速步（RDS）基元反应的能垒**，相对该步
稳定起点最小值（单步题即"相对反应物络合物"）。化学反应步可沿图中已声明的
同物种构象连接选稳定中间体；构象步本身仍相对其局部起点。推导链完全确定性：

1. 交付 ``mechanism_graph.json`` 声明每条边的 ``barrier_kcal_mol``；
2. harness 从绑定到该步的日志算出 ``E(TS) − E(起点最小值)``（Hartree →
   kcal/mol，用 ``tools/core/*_frames`` 的文本权威能量，不解析散文）；
3. 逐步比较，RDS = 推算能垒最大的那一步（并列按 edge id 排序，确定性）；
4. 评分要求声明值与推算值**都存在且一致**（复用 accuracy 的 sigma 容差）。
   缺失只计该边 0 分；声明与日志冲突按 accuracy 的证据核对规则处理。
   绝不用最终消息里的数字兜底。

TS 日志的识别是内容权威而非文件名猜谜：优先取物理上就是一阶鞍点（恰一个
虚频）的证据文件；多个候选/无法唯一确定时**不猜**，记 note 并跳过该步。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from cloudra.benchmark.integrity import (
    find_graph_json,
    load_delivered_graph,
    scan_evidence_files,
)
from cloudra.benchmark.schema import GoldMechanismGraph
from cloudra.tools.core.irc_evidence import normal_log

# CODATA Hartree → kcal/mol
HARTREE_TO_KCAL_MOL = 627.5094740631

# 评分只认 ORCA/Gaussian 日志（题库协议句明示；其他程序输出不算证据）
_SCORING_ENGINES = ("gaussian", "orca")

# 声明能量用于"指认交付日志"（同节点绑定多份合法日志时选哪一份）的容差：
# 声明值与日志解析值来自同一份日志，正常应严格一致；留 1e-4 Ha（≈0.06 kcal）
# 吸收交付侧的舍入。
DECLARED_ENERGY_TOL_HARTREE = 1e-4


@dataclass(frozen=True)
class StepBarrier:
    """一步基元反应的能垒：推算值 + 交付 JSON 的声明值。"""

    edge_id: str
    ts_path: str
    base_path: str
    base_node_id: str
    barrier_kcal_mol: float
    declared_kcal_mol: Optional[float] = None


@dataclass
class BarrierEvidence:
    """交付物的能垒证据集合（steps 为空即无法从交付物推出能垒）。

    ``steps`` 是策略选中的组合（TS 声明能量指认，反应步取稳定中间体）；
    ``alternatives[edge_id]`` 保留该边**全部合法组合**（TS 日志 × 起点极小值
    日志）——当交付声明的是一个构象、而参考答案对应另一个已算好的构象时，
    评分侧需要看到这些组合才能区分"指认/定义差异"与"无据声明"。"""

    steps: list[StepBarrier] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    graph_found: bool = False
    alternatives: dict[str, list[StepBarrier]] = field(default_factory=dict)

    def rds(self) -> Optional[StepBarrier]:
        """决速步 = 推算能垒最大的一步；并列按 edge id 取最小者（确定性）。"""
        if not self.steps:
            return None
        return sorted(
            self.steps, key=lambda s: (-s.barrier_kcal_mol, s.edge_id)
        )[0]


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _resolve_in_sandbox(sandbox: Path, rel_path: str) -> Optional[Path]:
    """把证据相对引用收在本题目沙箱内：越界（`../`、指向别的题目录、符号链接）
    一律返回 None —— 相对证据引用绝不跨题，跨题引用按不可用处理。"""
    try:
        candidate = (sandbox / rel_path).resolve()
        candidate.relative_to(Path(sandbox).resolve())
    except (OSError, ValueError):
        return None
    return candidate


def _frames_for(sandbox: Path, rel_path: str):
    """(引擎, 帧列表)；非 ORCA/Gaussian 或解析失败返回 (engine, [])。"""
    from cloudra.tools.core import gaussian_frames, orca_frames
    from cloudra.tools.core.qm_engine import detect_qm_engine

    path = _resolve_in_sandbox(sandbox, rel_path)
    if path is None:
        return None, []
    engine = detect_qm_engine(str(path)) if path.is_file() else None
    if engine not in _SCORING_ENGINES:
        return engine, []
    mod = orca_frames if engine == "orca" else gaussian_frames
    try:
        return engine, list(mod.extract_frames(str(path)))
    except Exception:
        return engine, []


def _last_frequencies(frames) -> list[float]:
    """末帧携带的频率列表（有符号，负值 = 虚频）；没有频率块返回 []。"""
    for frame in reversed(frames):
        if frame.frequencies_cm:
            return list(frame.frequencies_cm)
    return []


def _engine_energy_kcal(sandbox: Path, rel_path: str) -> tuple[Optional[float], str]:
    """证据日志 → 最终能量（kcal/mol）。(值, 原因) —— 原因非空即不可用。

    ORCA 走文本权威能量行（cclib 对外部势/ExtOpt 日志常失败）；Gaussian 走
    帧记录的 cclib 能量。两者都不读任何散文。
    """
    from cloudra.tools.core import gaussian_frames, orca_frames
    from cloudra.tools.core.qm_engine import detect_qm_engine

    path = _resolve_in_sandbox(sandbox, rel_path)
    if path is None:
        return None, (
            f"{rel_path}: evidence reference escapes this task's sandbox; "
            "relative evidence references never cross tasks"
        )
    if not path.is_file():
        return None, f"{rel_path}: evidence file missing"
    if not normal_log(path):
        return None, f'{rel_path}: normally terminated native evidence required'
    engine = detect_qm_engine(str(path))
    if engine not in _SCORING_ENGINES:
        return None, (
            f"{rel_path}: engine {engine or 'unknown'} output does not count as "
            "evidence (ORCA/Gaussian log formats only)"
        )
    text = _read_text(path)
    if not text.strip():
        return None, f"{rel_path}: empty log"
    if engine == "orca":
        energy = orca_frames.final_energy_hartree(text)
    else:
        energy = None
        for frame in reversed(gaussian_frames.extract_frames(str(path))):
            if frame.scf_energy_hartree is not None:
                energy = frame.scf_energy_hartree
                break
    if energy is None:
        return None, f"{rel_path}: no final energy in the {engine} log"
    return float(energy) * HARTREE_TO_KCAL_MOL, ""


def _imaginary_frequency_count(sandbox: Path, rel_path: str) -> Optional[int]:
    """证据文件里的虚频个数（判定它物理上是不是一阶鞍点）；不可判定返回 None。"""
    path = _resolve_in_sandbox(sandbox, rel_path)
    if path is None or not normal_log(path):
        return None
    engine, frames = _frames_for(sandbox, rel_path)
    if engine not in _SCORING_ENGINES:
        return None
    if engine == "orca":
        # cclib 对 ORCA 6.1 日志裸抛 IndexError——走带文本回退的统一入口
        path = _resolve_in_sandbox(sandbox, rel_path)
        if path is None or not path.is_file():
            return None
        from cloudra.tools.core import orca_frames

        freqs = orca_frames.frequencies_with_text_fallback(str(path))
    else:
        freqs = _last_frequencies(frames)
    if not freqs:
        return None
    return sum(1 for f in freqs if f < 0)


def _frequency_supported(sandbox, path, candidates, expected):
    """A separate Freq can support an energy log only at the same geometry."""
    from cloudra.tools.core.irc_evidence import frames_for, last_geometry
    from cloudra.tools.core.irc_path import same_geometry
    resolved = _resolve_in_sandbox(sandbox, path)
    if resolved is None or not normal_log(resolved):
        return False
    if _imaginary_frequency_count(sandbox, path) == expected:
        return True
    source = last_geometry(resolved, frames_for(resolved)[0])
    return any(_imaginary_frequency_count(sandbox, other) == expected and
               same_geometry(source, last_geometry(sandbox / other, frames_for(sandbox / other)[0]))
               for other in candidates)


def _declared_node_energy_hartree(node) -> Optional[float]:
    """节点 `properties.energy_hartree`（交付声明）→ Ha；缺失/非法 None。

    只用于**指认交付日志**：同一物种/节点绑定了多份合法日志时，告诉系统
    交付的到底是哪一份。数值本身不作证据——能量仍从日志解析。"""
    if node is None:
        return None
    raw = node.properties.get("energy_hartree")
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _log_energy_hartree(sandbox: Path, rel_path: str) -> Optional[float]:
    kcal, _reason = _engine_energy_kcal(sandbox, rel_path)
    return None if kcal is None else kcal / HARTREE_TO_KCAL_MOL


def _identify_by_declared_energy(
    sandbox: Path, candidates: list[str], declared: Optional[float]
) -> Optional[str]:
    """候选日志里最终能量与声明值最接近（容差内）的那份；无声明/无命中 None。"""
    if declared is None:
        return None
    from cloudra.tools.core.irc_evidence import frames_for, last_geometry
    from cloudra.tools.core.irc_path import same_geometry

    matches = []
    for path in candidates:
        energy = _log_energy_hartree(sandbox, path)
        if energy is None:
            continue
        delta = abs(energy - declared)
        if delta <= DECLARED_ENERGY_TOL_HARTREE:
            matches.append((delta, path))
    if not matches:
        return None
    matches.sort()
    anchor = last_geometry(sandbox / matches[0][1], frames_for(sandbox / matches[0][1])[0])
    if any(not same_geometry(anchor, last_geometry(sandbox / path, frames_for(sandbox / path)[0]))
           for _, path in matches[1:]):
        return None  # An energy alone cannot select between different structures.
    return matches[0][1]


def _reference_node_ids(graph: GoldMechanismGraph, edge) -> list[str]:
    """反应步沿同物种构象边找稳定参考；不合并独立通道或立体异构底物。"""
    selected = {edge.from_node}
    if not edge.bond_changes.pairs():
        return [edge.from_node]
    from cloudra.benchmark.graph_similarity import GedConfig, species_substitution_cost

    nodes = {node.id: node for node in graph.nodes}
    source = nodes[edge.from_node]
    cfg = GedConfig(stereo_free=False)
    pending = [edge.from_node]
    while pending:
        current = pending.pop()
        for link in graph.edges:
            if link.bond_changes.pairs() or not graph.edge_effectively_accessible(link):
                continue
            if link.from_node == current:
                candidate = link.to_node
            elif link.to_node == current:
                candidate = link.from_node
            else:
                continue
            node = nodes[candidate]
            if (
                candidate not in selected and node.accessible and node.smiles
                and species_substitution_cost(source.smiles, node.smiles, cfg) == 0.0
            ):
                selected.add(candidate)
                pending.append(candidate)
    return [edge.from_node, *sorted(selected - {edge.from_node})]


def collect_barrier_evidence(sandbox: Path | str) -> BarrierEvidence:
    """从交付图 + 绑定日志推出逐步能垒（不做任何散文解析）。"""
    sandbox = Path(sandbox)
    report = BarrierEvidence()
    graph_path = find_graph_json(sandbox)
    if graph_path is None:
        report.notes.append("no delivered mechanism graph; no barrier evidence")
        return report
    graph: Optional[GoldMechanismGraph] = load_delivered_graph(graph_path)
    if graph is None:
        report.notes.append(f"delivered graph unparseable: {graph_path.name}")
        return report
    report.graph_found = True

    files = scan_evidence_files(sandbox, exclude=graph_path)
    from cloudra.benchmark.integrity import bind_graph_to_evidence

    bindings = {b.node_id: b for b in bind_graph_to_evidence(graph, files, sandbox=sandbox)}
    log_paths = [f.path for f in files if f.kind in _SCORING_ENGINES]
    by_id = {node.id: node for node in graph.nodes}

    for edge in graph.edges:
        if edge.via is None:
            report.notes.append(f"edge {edge.id}: no transition-state node (`via`)")
            continue
        base_node = by_id.get(edge.from_node)
        ts_node = by_id.get(edge.via)
        ts_node_name = getattr(ts_node, "name", "") if ts_node is not None else ""
        if base_node is None:
            report.notes.append(f"edge {edge.id}: unknown base node {edge.from_node}")
            continue
        if len(base_node.smiles) > 1:
            report.notes.append(
                f"edge {edge.id}: separated source species have no single complex energy reference; "
                "component energies are not substituted for it"
            )
            continue
        reference_nodes = _reference_node_ids(graph, edge)
        base_owners = {}
        for node_id in reference_nodes:
            binding = bindings.get(node_id)
            for path in binding.bound_files if binding else []:
                base_owners.setdefault(path, node_id)
        base_candidates = sorted(base_owners)
        if not base_candidates:
            report.notes.append(
                f"edge {edge.id}: base node {edge.from_node} has no bound evidence"
            )
            continue
        # TS 证据：从两端点绑定文件的并集里按内容找一阶鞍点；多步题优先用
        # 文件名携带该步 TS 身份（edge id / TS 节点 id / 步名）的那一个——
        # 这是确定性偏好，不是猜谜；无法唯一确定时记 note 说明所用文件。
        ts_binding = bindings.get(edge.via)
        ts_candidates = list(ts_binding.bound_files) if ts_binding else []
        saddles = [
            p for p in sorted(set(ts_candidates)) if _frequency_supported(sandbox, p, log_paths, 1)
        ]
        if not saddles:
            report.notes.append(
                f"edge {edge.id}: no first-order saddle log bound to TS "
                f"{edge.via}; barrier not derivable from evidence"
            )
            continue
        all_saddles = list(saddles)
        # TS 日志指认：节点声明的 energy_hartree 直接钉住交付的是哪一份鞍点
        # 日志（同物种/同节点可绑定多份）；无声明或未命中时退回名字/路径序。
        declared_ts_energy = _declared_node_energy_hartree(ts_node)
        matched_ts = _identify_by_declared_energy(sandbox, saddles, declared_ts_energy)
        if matched_ts is not None:
            if len(saddles) > 1:
                report.notes.append(
                    f"edge {edge.id}: {len(saddles)} saddle logs bound to TS "
                    f"{edge.via}; using {matched_ts} (matches the node's declared "
                    "energy_hartree)"
                )
            saddles = [matched_ts]
        elif declared_ts_energy is not None:
            report.notes.append(
                f"edge {edge.id}: TS {edge.via} declares energy_hartree "
                f"{declared_ts_energy:.6f} but no bound saddle log matches it; "
                "barrier not derivable from the declared evidence"
            )
            continue
        if len(saddles) > 1:
            tokens = [t.lower() for t in (edge.id, edge.via, ts_node_name) if t]
            preferred = [
                p for p in saddles if any(t in Path(p).name.lower() for t in tokens)
            ]
            report.notes.append(
                f"edge {edge.id}: several saddle logs {saddles}; "
                + (f"using {preferred[0]} (name matches the step)" if preferred
                   else f"using {saddles[0]} (deterministic first by path)")
            )
            saddles = preferred or saddles
        ts_path = saddles[0]

        # 全部合法组合（TS 日志 × 起点极小值日志）都要留给评分侧：交付声明的
        # 是一个构象、而参考答案对应另一个已算好的构象时，只有看到全部组合
        # 才能区分"指认/答案定义差异"与"无据声明"。
        saddle_energies: dict[str, float] = {}
        for candidate in all_saddles:
            energy, _reason = _engine_energy_kcal(sandbox, candidate)
            if energy is not None:
                saddle_energies[candidate] = energy
        ts_energy = saddle_energies.get(ts_path)
        if ts_energy is None:
            _energy, ts_reason = _engine_energy_kcal(sandbox, ts_path)
            report.notes.append(f"edge {edge.id}: {ts_reason}")
            continue

        # 反应步按用户确认的稳定中间体作分母，不用声明能量强制选较浅构象。
        # 构象步只在自己的起点节点内指认局部参考，不把另一端稳定化重复计入。
        minima = [
            p for p in base_candidates if _frequency_supported(sandbox, p, log_paths, 0)
        ]
        minima_energies: dict[str, float] = {}
        for candidate in minima:
            energy, _reason = _engine_energy_kcal(sandbox, candidate)
            if energy is not None:
                minima_energies[candidate] = energy
        below: list[tuple[float, str]] = [
            (energy, path)
            for path, energy in sorted(minima_energies.items())
            if energy < ts_energy
        ]
        if not below:
            report.notes.append(
                f"edge {edge.id}: no bound minimum of {edge.from_node} lies "
                "below the saddle; barrier not derivable from evidence"
            )
            continue
        report.alternatives[edge.id] = [
            StepBarrier(
                edge_id=edge.id,
                ts_path=ts_candidate,
                base_path=base_candidate,
                base_node_id=base_owners[base_candidate],
                barrier_kcal_mol=ts_e - base_e,
                declared_kcal_mol=edge.barrier_kcal_mol,
            )
            for ts_candidate, ts_e in sorted(saddle_energies.items())
            for base_candidate, base_e in sorted(minima_energies.items())
            if base_e < ts_e
        ]
        declared_base_energy = (
            _declared_node_energy_hartree(base_node) if not edge.bond_changes.pairs() else None
        )
        matched_base = None
        if declared_base_energy is not None:
            matched_base = _identify_by_declared_energy(sandbox, [path for _, path in below], declared_base_energy)
        if matched_base is not None:
            base_energy, base_path = next(
                (energy, path) for energy, path in below if path == matched_base
            )
            if len(below) > 1:
                report.notes.append(
                    f"edge {edge.id}: {len(below)} minima of {edge.from_node} below "
                    f"the saddle; using {base_path} (matches the node's declared "
                    "energy_hartree)"
                )
        else:
            if declared_base_energy is not None:
                report.notes.append(
                    f"edge {edge.id}: {edge.from_node} declares energy_hartree "
                    f"{declared_base_energy:.6f} but no bound minimum matches it; "
                    "barrier not derivable from the declared evidence"
                )
                continue
            below.sort(key=lambda item: (item[0], item[1]))
            base_energy, base_path = below[0]
            if len(below) > 1:
                report.notes.append(
                    f"edge {edge.id}: several minima of {edge.from_node} below the "
                    f"saddle; using {base_path} (lowest-energy stable intermediate "
                    "in the declared source conformational state)"
                )

        report.steps.append(
            StepBarrier(
                edge_id=edge.id,
                ts_path=ts_path,
                base_path=base_path,
                base_node_id=base_owners[base_path],
                barrier_kcal_mol=ts_energy - base_energy,
                declared_kcal_mol=edge.barrier_kcal_mol,
            )
        )

    if not report.steps:
        report.notes.append("no step barrier could be derived from the delivered logs")
    return report
