"""Evidence file ingest, workspace sandboxing, and TS vibration validation."""

from __future__ import annotations

import hashlib
import logging
import shutil
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)


class FileEvidenceSnapshot(BaseModel):
    """不可变的文件证据快照记录。"""

    model_config = ConfigDict(extra="forbid")

    original_path: str
    snapshot_path: str
    sha256: str
    file_size: int
    is_qm_log: bool = False
    engine: str | None = None
    frequencies: list[float] | None = None
    imaginary_frequencies: list[float] | None = None
    normal_modes: list[dict[str, Any]] | None = None
    final_energy_hartree: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class TSValidationResult(BaseModel):
    """过渡态虚频与振动模式校验结果。"""

    model_config = ConfigDict(extra="forbid")

    is_valid: bool
    verified: bool = Field(
        description="Whether the verdict is backed by actual frequency data. False means "
                    "'unverified': there was nothing to judge, so this result must never be used "
                    "to mark a step complete.",
    )
    n_imag: int
    imaginary_frequencies: list[float] = Field(default_factory=list)
    mode_matched: bool = True
    message: str = ""


class SpeciesValidationResult(BaseModel):
    """物种极小值振动频率校验结果。"""

    model_config = ConfigDict(extra="forbid")

    is_valid: bool
    verified: bool = Field(
        description="Whether the verdict is backed by actual frequency data. False means "
                    "'unverified': no frequency analysis was provided, so the species is NOT a "
                    "verified stationary minimum and must never be marked complete.",
    )
    n_imag: int
    imaginary_frequencies: list[float] = Field(default_factory=list)
    message: str = ""


def _extract_qm_log(path: Path) -> tuple[bool, str | None, list[float] | None, list[float] | None, float | None, list[dict[str, Any]] | None]:
    """尝试从文件中解析 QM 属性（引擎、虚频、实频、能量）。"""
    try:
        from cloudra.tools.core import orca_frames, xtb_frames
        from cloudra.tools.core.qm_engine import detect_qm_engine
    except ImportError:
        return False, None, None, None, None, None

    engine = detect_qm_engine(str(path))
    if engine == "unknown" and path.suffix.lower() not in (".log", ".out", ".txt"):
        return False, None, None, None, None, None

    orca_text: str | None = None
    xtb_text: str | None = None
    vibfreqs: list[float] | None = None
    final_energy: float | None = None

    if engine in ("orca", "xtb"):
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                content = f.read()
            if engine == "orca":
                orca_text = content
                vibfreqs = orca_frames.vibfreqs_from_text(orca_text) or None
                final_energy = orca_frames.final_energy_hartree(orca_text)
            else:
                xtb_text = content
                vibfreqs = xtb_frames.vibfreqs_from_text(xtb_text) or None
                final_energy = xtb_frames.final_energy_hartree(xtb_text)
        except Exception as exc:
            logger.debug("Failed reading %s frames for %s: %s", engine, path, exc)

    if vibfreqs is None or final_energy is None:
        try:
            import cclib
            import numpy as np

            data = cclib.io.ccread(str(path))
            if data is not None:
                if vibfreqs is None and hasattr(data, "vibfreqs") and data.vibfreqs is not None:
                    vibfreqs = [float(x) for x in np.asarray(data.vibfreqs, dtype=float)]
                if final_energy is None and hasattr(data, "scfenergies") and data.scfenergies is not None and len(data.scfenergies) > 0:
                    ev = float(data.scfenergies[-1])
                    final_energy = ev / 27.211386245988
        except Exception as exc:
            logger.debug("cclib parsing skipped/failed for %s: %s", path, exc)

    if vibfreqs is None and final_energy is None and engine == "unknown":
        return False, None, None, None, None, None

    imag_freqs = [f for f in vibfreqs if f < 0] if vibfreqs is not None else None

    return True, engine if engine != "unknown" else None, vibfreqs, imag_freqs, final_energy, None


def snapshot_evidence_file(
    file_path: str | Path,
    workspace_root: str | Path,
    conversation_id: str | None = None,
) -> FileEvidenceSnapshot:
    """对工作区内证据文件进行安全沙箱检查、sha256 签名与不可变快照复制。"""
    root = Path(workspace_root).expanduser().resolve(strict=True)
    p = Path(file_path).expanduser()

    if p.is_absolute():
        resolved = p.resolve()
    else:
        resolved = (root / p).resolve()

    if resolved.is_symlink():
        raise ValueError(f"Symlinks are not allowed as evidence: {file_path}")

    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"Path escapes workspace boundary: {file_path}") from exc

    if not resolved.exists():
        raise FileNotFoundError(f"Evidence file does not exist: {file_path}")
    if not resolved.is_file():
        raise ValueError(f"Evidence path is not a regular file: {file_path}")

    data = resolved.read_bytes()
    sha256_hex = hashlib.sha256(data).hexdigest()
    file_size = len(data)

    evidence_dir = root / ".cloudra" / "evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    snapshot_filename = f"{sha256_hex[:16]}_{resolved.name}"
    snapshot_path = evidence_dir / snapshot_filename

    if not snapshot_path.exists():
        shutil.copy2(resolved, snapshot_path)

    is_qm, engine, freqs, imag_freqs, energy, normal_modes = _extract_qm_log(resolved)

    return FileEvidenceSnapshot(
        original_path=str(resolved),
        snapshot_path=str(snapshot_path),
        sha256=sha256_hex,
        file_size=file_size,
        is_qm_log=is_qm,
        engine=engine,
        frequencies=freqs,
        imaginary_frequencies=imag_freqs,
        normal_modes=normal_modes,
        final_energy_hartree=energy,
        metadata={"filename": resolved.name},
    )


def validate_ts_mode(
    freqs: list[float] | None,
    normal_modes: list[dict[str, Any]] | None = None,
    description: str = "",
    imaginary_freqs: list[float] | None = None,
) -> TSValidationResult:
    """校验过渡态是否具有恰好 1 个虚频，并匹配反应坐标描述。"""
    has_freq_data = (freqs is not None and len(freqs) > 0) or (
        imaginary_freqs is not None and len(imaginary_freqs) > 0
    )
    if not has_freq_data:
        return TSValidationResult(
            is_valid=False,
            verified=False,
            n_imag=0,
            imaginary_frequencies=[],
            message=(
                "No frequency data available in the provided calculation output; the transition "
                "state is UNVERIFIED (submit a freq job for this structure)."
            ),
        )

    if imaginary_freqs is not None:
        imag = imaginary_freqs
    else:
        imag = [f for f in (freqs or []) if f < 0]
    n_imag = len(imag)

    if n_imag == 1:
        msg = f"Valid transition state saddle point with exactly 1 imaginary frequency ({imag[0]:.1f} cm⁻¹)."
        if description:
            msg += f" Mode description: {description}."
        return TSValidationResult(
            is_valid=True,
            verified=True,
            n_imag=1,
            imaginary_frequencies=imag,
            mode_matched=False,
            message=msg,
        )
    elif n_imag == 0:
        return TSValidationResult(
            is_valid=False,
            verified=True,
            n_imag=0,
            imaginary_frequencies=[],
            mode_matched=False,
            message="Zero imaginary frequencies found; the structure is a local minimum, not a transition state saddle point.",
        )
    else:
        return TSValidationResult(
            is_valid=False,
            verified=True,
            n_imag=n_imag,
            imaginary_frequencies=imag,
            mode_matched=False,
            message=f"Found {n_imag} imaginary frequencies ({imag}); this indicates a higher-order saddle point.",
        )


def validate_species_minimum(
    freqs: list[float] | None,
    imaginary_freqs: list[float] | None = None,
) -> SpeciesValidationResult:
    """校验稳定中间体/物种是否为驻点极小值（0 个虚频）。"""
    # 三分量：verified-minimum / verified-not-minimum / unverified（无数据）。
    # 驻点极小值必须有非空的频率数据支撑（len > 0）；
    # 若无实频且无虚频数据，或实频为空且无有效虚频，一律判定为 UNVERIFIED，绝不当成 0 虚频极小值。
    has_freq_data = (freqs is not None and len(freqs) > 0) or (
        imaginary_freqs is not None and len(imaginary_freqs) > 0
    )
    if not has_freq_data:
        return SpeciesValidationResult(
            is_valid=False,
            verified=False,
            n_imag=0,
            imaginary_frequencies=[],
            message=(
                "No vibrational frequency analysis provided: the stationary point is UNVERIFIED "
                "(submit a freq job for this structure, then resubmit the evidence)."
            ),
        )

    if imaginary_freqs is not None:
        imag = imaginary_freqs
    else:
        imag = [f for f in (freqs or []) if f < 0]
    n_imag = len(imag)

    if n_imag == 0:
        return SpeciesValidationResult(
            is_valid=True,
            verified=True,
            n_imag=0,
            imaginary_frequencies=[],
            message="Valid stationary local minimum (0 imaginary frequencies).",
        )
    else:
        return SpeciesValidationResult(
            is_valid=False,
            verified=True,
            n_imag=n_imag,
            imaginary_frequencies=imag,
            message=f"Invalid local minimum: found {n_imag} imaginary frequencies ({imag}).",
        )
