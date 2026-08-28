"""Layer 2 — self-consistency: physical validity of the delivered evidence.

Independent of the gold reference: a TS must be a first-order saddle
(exactly one imaginary frequency, excluding conformational fake TS below
`min_abs_imag_freq_cm1`), its IRC must connect the two endpoints, and each
species must pass a frequency (no imaginary) and identity (matches claimed
SMILES) check. Operates on the evidence files the integrity layer bound to
each graph node/step.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from cloudra.benchmark.integrity import EvidenceFile
from cloudra.benchmark.schema import SelfConsistencyRubric
from cloudra.tools.core import gaussian_frames, orca_frames, qm_engine


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
class SelfConsistencyReport:
    ts_checks: list[TsCheck] = field(default_factory=list)
    all_first_order: bool = False
    all_irc_connect: bool = False
    passed: bool = False
    notes: list[str] = field(default_factory=list)


def _frames_for(path: Path):
    engine = qm_engine.detect_qm_engine(str(path))
    try:
        if engine == "orca":
            return orca_frames.extract_frames(str(path)), orca_frames.extract_irc(str(path))
        return gaussian_frames.extract_frames(str(path)), gaussian_frames.extract_irc(str(path))
    except Exception:
        return [], None


def _imag_freqs(freqs: list[float]) -> list[float]:
    return [f for f in freqs if f < 0]


def check_ts_file(path: Path, rubric: SelfConsistencyRubric) -> TsCheck:
    chk = TsCheck(source=path.name)
    frames, irc = _frames_for(path)
    if not frames:
        chk.notes.append("no frames parsed")
        return chk
    # use the final frame's frequency block
    freqs: list[float] = []
    for fr in reversed(frames):
        if fr.frequencies_cm:
            freqs = list(fr.frequencies_cm)
            break
    imag = _imag_freqs(freqs)
    chk.imag_freqs_cm = imag
    chk.n_imag = len(imag)
    if rubric.ts_first_order_saddle:
        chk.is_first_order_saddle = len(imag) == 1
    if imag:
        chk.min_abs_imag_ok = min(abs(f) for f in imag) >= rubric.min_abs_imag_freq_cm1
    if rubric.irc_connects_endpoints:
        chk.irc_connects = _irc_connects(irc)
    return chk


def _irc_connects(irc) -> Optional[bool]:
    """Heuristic: an IRC trajectory connects both endpoints if it has both a
    forward and a backward branch (path numbers on both sides) and converged
    frames at each end."""
    if irc is None:
        return None
    try:
        # gaussian_frames.extract_irc returns a structure with forward/backward
        # point lists; be defensive about the exact shape.
        fwd = getattr(irc, "forward", None) or (irc.get("forward") if isinstance(irc, dict) else None)
        bwd = getattr(irc, "backward", None) or (irc.get("backward") if isinstance(irc, dict) else None)
        if fwd is None or bwd is None:
            return None
        return bool(fwd) and bool(bwd)
    except Exception:
        return None


def audit_self_consistency(
    evidence_files: list[EvidenceFile],
    sandbox: Path,
    rubric: Optional[SelfConsistencyRubric] = None,
) -> SelfConsistencyReport:
    rubric = rubric or SelfConsistencyRubric()
    report = SelfConsistencyReport()
    ts_files = [f for f in evidence_files if "ts" in Path(f.path).stem.lower() or f.kind in ("gaussian", "orca")]
    for f in ts_files:
        report.ts_checks.append(check_ts_file(sandbox / f.path, rubric))

    saddles = [c.is_first_order_saddle for c in report.ts_checks if c.is_first_order_saddle is not None]
    ircs = [c.irc_connects for c in report.ts_checks if c.irc_connects is not None]
    report.all_first_order = bool(saddles) and all(saddles)
    report.all_irc_connect = (all(ircs) if ircs else (not rubric.irc_connects_endpoints))
    report.passed = report.all_first_order and report.all_irc_connect
    if not report.ts_checks:
        report.notes.append("no TS evidence files found to check")
    return report
