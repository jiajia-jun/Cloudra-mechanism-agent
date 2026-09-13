"""Layer 2 — self-consistency: physical validity of the delivered evidence.

Independent of the gold reference: a TS must be a first-order saddle
(exactly one imaginary frequency, n_imag == 1), its IRC must connect the two
endpoints, and each species must pass a minimum check (no imaginary
frequencies). No imaginary-frequency magnitude lower bound is imposed —
whether a single imaginary mode is "appropriate" is delegated to IRC
connectivity (`irc_connects_endpoints`) and the frequency-direction/IRC
verification in the validation layer, not to a `min_abs_imag_freq_cm1`
threshold. Species identity (SMILES consistency) is Layer 1's evidence-binding
job and is not re-checked here. Operates on the evidence files the integrity
layer bound to each graph node/step.

File roles are decided by **content**, not filename: a frequency block with
imaginary frequencies marks TS evidence (saddle check); a clean block marks
species evidence (minimum check); IRC-only logs yield only a connectivity
verdict. Filename tokens are deliberately ignored — harness-produced compute
logs are always named `calc-<jobid>.out.log`, so name-based roles would
misroute every real TS log into the minimum check.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from cloudra.benchmark.integrity import MAX_SCAN_BYTES, EvidenceFile
from cloudra.benchmark.schema import SelfConsistencyRubric
from cloudra.tools.core import gaussian_frames, orca_frames, qm_engine


@dataclass
class TsCheck:
    source: str
    n_imag: Optional[int] = None
    imag_freqs_cm: list[float] = field(default_factory=list)
    is_first_order_saddle: Optional[bool] = None
    irc_connects: Optional[bool] = None
    notes: list[str] = field(default_factory=list)


@dataclass
class MinimumCheck:
    source: str
    n_imag: Optional[int] = None
    is_minimum: Optional[bool] = None  # 无虚频
    notes: list[str] = field(default_factory=list)


@dataclass
class SelfConsistencyReport:
    ts_checks: list[TsCheck] = field(default_factory=list)
    min_checks: list[MinimumCheck] = field(default_factory=list)
    all_first_order: bool = False
    all_minima: bool = True
    all_irc_connect: bool = False
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


def _classify_and_check(path: Path, frames, irc_meta, rubric: SelfConsistencyRubric):
    """按**内容**判定文件角色并出检查项：频率块含虚频 → TS 证据（鞍点
    检查）；频率块零虚频 → 物种证据（极小值通过）；无频率块但有 IRC
    数据 → 只对 IRC 连通性出判；其余（输入文件、SP）不出判，返回 None。

    文件名 token 不作数：harness 产出的计算日志统一命名
    ``calc-<jobid>.out.log``，agent 无法决定文件名，按文件名分角色会把
    真 TS 日志错送进极小值检查（1 个虚频必然判负）。"""
    freqs = _freqs_for(path, frames)
    imag = _imag_freqs(freqs)
    if imag:
        chk = TsCheck(source=path.name, n_imag=len(imag), imag_freqs_cm=imag)
        if rubric.ts_first_order_saddle:
            chk.is_first_order_saddle = len(imag) == 1
        if rubric.irc_connects_endpoints:
            chk.irc_connects = _irc_connects(irc_meta)
        return chk
    if freqs:
        return MinimumCheck(source=path.name, n_imag=0, is_minimum=True)
    if irc_meta is not None:
        chk = TsCheck(source=path.name)
        if rubric.irc_connects_endpoints:
            chk.irc_connects = _irc_connects(irc_meta)
        return chk
    return None


def _irc_connects(meta) -> Optional[bool]:
    """IRC 连通判定：正/反两个分支都有点数且各自收敛（收敛标记来自日志解析，
    步数耗尽而终止的分支不算到达端点）。无 IRC 数据时返回 None。"""
    if not isinstance(meta, dict):
        return None
    fwd = meta.get("num_points_forward") or 0
    bwd = meta.get("num_points_backward") or 0
    if not fwd and not bwd:
        return None
    return (
        bool(fwd)
        and bool(bwd)
        and bool(meta.get("forward_converged"))
        and bool(meta.get("backward_converged"))
    )


def audit_self_consistency(
    evidence_files: list[EvidenceFile],
    sandbox: Path,
    rubric: Optional[SelfConsistencyRubric] = None,
) -> SelfConsistencyReport:
    rubric = rubric or SelfConsistencyRubric()
    report = SelfConsistencyReport()
    # 超过共享大小上限的文件在 Layer 1 没整读（无 SMILES 绑定），这里也不让
    # cclib 整读——两层对齐，避免超大日志拖住评分器。
    qm_files = [
        f for f in evidence_files
        if f.kind in ("gaussian", "orca") and f.size <= MAX_SCAN_BYTES
    ]
    for f in qm_files:
        path = sandbox / f.path
        frames, irc_meta = _frames_for(path)
        chk = _classify_and_check(path, frames, irc_meta, rubric)
        if isinstance(chk, TsCheck):
            report.ts_checks.append(chk)
        elif isinstance(chk, MinimumCheck):
            report.min_checks.append(chk)

    saddle_verdicts = [
        c.is_first_order_saddle
        for c in report.ts_checks
        if c.is_first_order_saddle is not None
    ]
    ircs = [c.irc_connects for c in report.ts_checks if c.irc_connects is not None]
    minima = [m.is_minimum for m in report.min_checks if m.is_minimum is not None]

    if rubric.ts_first_order_saddle:
        # 没有任何含频率块的 TS 证据 = 没有鞍点证据，判负
        report.all_first_order = bool(saddle_verdicts) and all(saddle_verdicts)
    else:
        report.all_first_order = True
    report.all_minima = all(minima) if minima else True
    # IRC 连通：存在至少一条双向收敛的 IRC 即支撑 TS 连通性声明——沙箱刻意
    # 保留失败/未收敛的先期尝试（structure_artifacts 纪律），all() 会把
    # 已被后续成功作业取代的重试记录误判为交付不合格。
    report.all_irc_connect = (any(ircs) if ircs else (not rubric.irc_connects_endpoints))
    report.passed = report.all_first_order and report.all_minima and report.all_irc_connect
    if not report.ts_checks:
        report.notes.append("no TS evidence files found to check")
    return report
