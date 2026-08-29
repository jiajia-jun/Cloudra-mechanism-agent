"""Layer 2 — self-consistency: physical validity of the delivered evidence.

Independent of the gold reference: a TS must be a first-order saddle
(exactly one imaginary frequency, excluding conformational fake TS below
`min_abs_imag_freq_cm1`), its IRC must connect the two endpoints, and each
species must pass a minimum check (no imaginary frequencies). Species
identity (SMILES consistency) is Layer 1's evidence-binding job and is not
re-checked here. Operates on the evidence files the integrity layer bound to
each graph node/step.

File roles are decided by filename token: a `ts` token in the stem
(`ts.log`, `M6_ts_opt.out`) marks TS evidence; other Gaussian/ORCA logs are
treated as species evidence and checked for a minimum (no imaginary
frequencies). Files without a frequency block (SP logs, inputs) yield no
verdict instead of a spurious failure.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from cloudra.benchmark.integrity import EvidenceFile
from cloudra.benchmark.schema import SelfConsistencyRubric
from cloudra.tools.core import gaussian_frames, orca_frames, qm_engine

# "ts" 必须作为独立 token 出现（可带编号后缀如 ts1/ts2），否则
# "reactants"/"products" 这类以 ts 结尾的文件名会被误判为 TS 证据。
_TS_TOKEN_RE = re.compile(r"(?:^|[^a-z0-9])ts\d*(?:[^a-z0-9]|$)")


@dataclass
class TsCheck:
    source: str
    n_imag: Optional[int] = None
    imag_freqs_cm: list[float] = field(default_factory=list)
    is_first_order_saddle: Optional[bool] = None
    min_abs_imag_ok: Optional[bool] = None
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


def _is_ts_path(stem: str) -> bool:
    return bool(_TS_TOKEN_RE.search(stem.lower()))


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


def _imag_freqs(freqs: list[float]) -> list[float]:
    return [f for f in freqs if f < 0]


def check_ts_file(path: Path, rubric: SelfConsistencyRubric) -> TsCheck:
    chk = TsCheck(source=path.name)
    frames, irc_meta = _frames_for(path)
    freqs = _last_freqs(frames)
    imag = _imag_freqs(freqs)
    chk.imag_freqs_cm = imag
    if freqs:
        # 只有真的含频率块时才给鞍点判定；纯 IRC 日志没有频率块，跳过
        chk.n_imag = len(imag)
        if rubric.ts_first_order_saddle:
            chk.is_first_order_saddle = len(imag) == 1
        if imag:
            chk.min_abs_imag_ok = min(abs(f) for f in imag) >= rubric.min_abs_imag_freq_cm1
    if rubric.irc_connects_endpoints:
        chk.irc_connects = _irc_connects(irc_meta)
    if not freqs and irc_meta is None:
        chk.notes.append("no frequency or IRC data parsed")
    return chk


def check_minimum_file(path: Path) -> MinimumCheck:
    """Species evidence: the final frequency block must show no imaginary
    frequencies. Files without a frequency block (SP, inputs) give no verdict."""
    chk = MinimumCheck(source=path.name)
    frames, _ = _frames_for(path)
    freqs = _last_freqs(frames)
    if not freqs:
        chk.notes.append("no frequency block")
        return chk
    imag = _imag_freqs(freqs)
    chk.n_imag = len(imag)
    chk.is_minimum = not imag
    return chk


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
    qm_files = [f for f in evidence_files if f.kind in ("gaussian", "orca")]
    ts_files = [f for f in qm_files if _is_ts_path(Path(f.path).stem)]
    species_files = [f for f in qm_files if not _is_ts_path(Path(f.path).stem)]

    for f in ts_files:
        report.ts_checks.append(check_ts_file(sandbox / f.path, rubric))
    for f in species_files:
        report.min_checks.append(check_minimum_file(sandbox / f.path))

    saddle_verdicts = [
        c.is_first_order_saddle and c.min_abs_imag_ok is not False
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
    report.all_irc_connect = (all(ircs) if ircs else (not rubric.irc_connects_endpoints))
    report.passed = report.all_first_order and report.all_minima and report.all_irc_connect
    if not report.ts_checks:
        report.notes.append("no TS evidence files found to check")
    return report
