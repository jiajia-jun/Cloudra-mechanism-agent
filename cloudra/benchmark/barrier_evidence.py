"""RDS 能垒的交付物推导：只读 log 文件与交付 JSON，不解析任何 LLM 散文。

能垒口径（题库 query 协议一致）：**决速步（RDS）基元反应的能垒**，相对该步
起点最小值（单步题即"相对反应物络合物"）。推导链完全确定性：

1. 交付 ``mechanism_graph.json`` 声明每条边的 ``barrier_kcal_mol``；
2. harness 从绑定到该步的日志算出 ``E(TS) − E(起点最小值)``（Hartree →
   kcal/mol，用 ``tools/core/*_frames`` 的文本权威能量，不解析散文）；
3. 逐步比较，RDS = 推算能垒最大的那一步（并列按 edge id 排序，确定性）；
4. 评分要求声明值与推算值**都存在且一致**（复用 accuracy 的 sigma 容差），
   任一缺失/冲突一律 fail-loud 记 0 并写明原因——绝不用最终消息里的数字兜底。

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

# CODATA Hartree → kcal/mol
HARTREE_TO_KCAL_MOL = 627.5094740631

# 评分只认 ORCA/Gaussian 日志（题库协议句明示；其他程序输出不算证据）
_SCORING_ENGINES = ("gaussian", "orca")


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
    """交付物的能垒证据集合（steps 为空即无法从交付物推出能垒）。"""

    steps: list[StepBarrier] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    graph_found: bool = False

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


def _is_step_ts(sandbox: Path, rel_path: str) -> Optional[bool]:
    """该证据文件是否是一阶鞍点（TS）：True/False/None(不可判定)。"""
    imag = _imaginary_frequency_count(sandbox, rel_path)
    if imag is None:
        return None
    return imag == 1


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

    bindings = {b.node_id: b for b in bind_graph_to_evidence(graph, files)}
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
        base_binding = bindings.get(edge.from_node)
        base_candidates = list(base_binding.bound_files) if base_binding else []
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
            p for p in sorted(set(ts_candidates)) if _is_step_ts(sandbox, p) is True
        ]
        if not saddles:
            report.notes.append(
                f"edge {edge.id}: no first-order saddle log bound to TS "
                f"{edge.via}; barrier not derivable from evidence"
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

        ts_energy, ts_reason = _engine_energy_kcal(sandbox, ts_path)
        if ts_energy is None:
            report.notes.append(f"edge {edge.id}: {ts_reason}")
            continue

        # 起点最小值的选择：鞍点连通的是它正下方**最浅**的那个阱（能量最高
        # 但仍低于 TS 的极小值）——拿更深的远端极小值当起点会把别的阱的
        # 稳定化能错算进能垒（如把产物侧深阱当 RC，2 kcal 被读成 35 kcal）。
        minima = [
            p for p in base_candidates if _imaginary_frequency_count(sandbox, p) == 0
        ]
        below: list[tuple[float, str]] = []
        for candidate in minima:
            energy, _reason = _engine_energy_kcal(sandbox, candidate)
            if energy is not None and energy < ts_energy:
                below.append((energy, candidate))
        if not below:
            report.notes.append(
                f"edge {edge.id}: no bound minimum of {edge.from_node} lies "
                "below the saddle; barrier not derivable from evidence"
            )
            continue
        below.sort(key=lambda item: (-item[0], item[1]))
        base_energy, base_path = below[0]
        if len(below) > 1:
            report.notes.append(
                f"edge {edge.id}: several minima of {edge.from_node} below the "
                f"saddle; using {base_path} (highest-energy minimum below the "
                "saddle — the basin the saddle connects to)"
            )

        report.steps.append(
            StepBarrier(
                edge_id=edge.id,
                ts_path=ts_path,
                base_path=base_path,
                base_node_id=edge.from_node,
                barrier_kcal_mol=ts_energy - base_energy,
                declared_kcal_mol=edge.barrier_kcal_mol,
            )
        )

    if not report.steps:
        report.notes.append("no step barrier could be derived from the delivered logs")
    return report


def load_refusal_declaration(sandbox: Path | str):
    """交付 ``mechanism_graph.json`` 里可选的拒答声明；无则 None（绝不猜）。"""
    import json

    from cloudra.benchmark.schema import RefusalDeclaration

    path = Path(sandbox) / "mechanism_graph.json"
    if not path.is_file():
        return None
    try:
        data = json.loads(_read_text(path))
    except ValueError:
        return None
    if not isinstance(data, dict):
        return None
    raw = data.get("refusal")
    if not isinstance(raw, dict):
        return None
    try:
        declaration = RefusalDeclaration.model_validate(raw)
    except Exception:
        return None
    return declaration if declaration.refused else None
