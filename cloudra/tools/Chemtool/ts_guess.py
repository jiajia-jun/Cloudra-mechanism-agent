"""过渡态初猜工作流工具：插值路径生成 / 约束扫描输入生成 / 扫描日志解析 / TS 候选检查。

工具自身不执行任何量化计算：坐标与输入文件一律落盘，上下文只回数值表、判定与路径。
引擎输出解析的正则封装在本模块与 cloudra/tools/core/*_frames 共享层
（gaussian_frames 的 FREQ_LINE_RE / vibdisps_from_text / std_orientation_frames），
agent 无需啃日志格式。

默认 verify 只给 agent 提供方向建议；strict verify 只证明部分 IRC 的行进方向与两侧优化
中间体一致，不宣称一个 TS 因此“绝对正确”。strict 的监测对与原子对应实现唯一，
住 cloudra/tools/core/irc_path（键图 diff 硬证据 + 启发提名软证据分层，
距离指纹 + Hungarian 对齐，任意原子序输入可判）。
"""

from __future__ import annotations

import asyncio
import os
import re
from io import StringIO
from typing import Any, Literal, Optional, Sequence

from pydantic import Field

from cloudra.base.session_class import Session
from cloudra.base.tools_class import Tool, input_schema, output_schema
from cloudra.persistence.fs_utils import atomic_write_text
from cloudra.persistence.workspace import resolve_tool_path
from cloudra.tools.Chemtool.internal_coordinates import (
    _angle_deg,
    _dihedral_deg,
)
from cloudra.tools.core import gaussian_frames, orca_frames
from cloudra.tools.core.irc_path import (
    COVALENT_RADII as _COVALENT_RADII,
)
from cloudra.tools.core.irc_path import (
    DISTANCE_CONNECTIVITY_FACTOR as _DISTANCE_CONNECTIVITY_FACTOR,
)
from cloudra.tools.core.irc_path import (
    bond_pairs_from_dist as _bond_pairs_from_dist,
)
from cloudra.tools.core.irc_path import (
    classify_watch_pairs as _classify_watch_pairs,
)
from cloudra.tools.core.irc_path import (
    dist_matrix as _dist_matrix,
)
from cloudra.tools.core.irc_path import (
    pair_label as _pair_label,
)
from cloudra.tools.core.irc_path import (
    parse_xyz as _parse_xyz,
)
from cloudra.tools.core.irc_path import (
    perceive_bonds as _perceive_bonds,
)
from cloudra.tools.core.irc_path import (
    prove_irc_endpoint_direction as _prove_irc_endpoint_direction,
)
from cloudra.tools.core.xtb_path_runner import DEFAULT_REFINEMENT_RUNS

KCAL_PER_HARTREE = 627.5095
# 虚频模式与反应坐标：watch_pairs 中至少一对的相对位移须达全局最大相对位移的该比例。
_IMAG_MODE_WATCH_RATIO = 0.5

# 可操作补救提示（仅文本）：strict verify 因「材料不足 / 未通过」而不 pass 时追加到
# checks 与 verdict 文案，指导 agent 去补做端点优化，而不是放宽阈值。不改变 verdict 取值。
_IRC_TRUNCATION_REMEDY = (
    "The IRC path may be truncated (an outer frame has not yet relaxed onto the "
    "target endpoint reference geometry). Remedy: re-optimize each IRC outer frame to a minimum "
    "(Opt, ideally with Freq to confirm zero imaginary frequencies) and resubmit "
    "the endpoint reference geometries as reactant_path / product_path, then run strict verify again."
)

description = (
    "Transition-state (TS) guess workflow: four sub-functions selected by mode. "
    "interpolate: linear or IDPP interpolation from reactant/product xyz to generate NEB candidate-path images "
    "(auto-align, optional atom_map reordering, distance-monitor table, and TS-candidate frame verdict); "
    "scan_prepare: write a Gaussian/ORCA constrained-scan input — one scan coordinate or two coupled ones "
    "(bond/angle/dihedral, modredundant or %geom Scan); for MLIP/external potentials pass "
    "method='ExtOpt' (ORCA, plus orca_blocks with the %method ProgExt block) or method='external' "
    "(Gaussian, plus extra_route='external=\"mace\"'); "
    "scan_parse: parse a scan log into a relative-energy profile table, constrained-scan diagnostic barrier, and monotonicity/discontinuity/boundary-extremum/multipeak verdicts, "
    "and extract the highest-energy geometry as a TS-guess xyz — for ORCA relaxed scans it reads "
    "relaxscanact.dat + ts_scan.NNN.xyz frame files so the TS guess is the energy-maximum frame, not the last frame; "
    "without the sidecar the log text is grouped per 'RELAXED SURFACE SCAN STEP' and each point's converged "
    "(last) energy/geometry is used, so per-cycle energies are never misread as scan points; "
    "verify: by default, frequency plus rough IRC-endpoint connectivity yields candidate/unlikely/inconclusive; "
    "with strict=True, requires one imaginary frequency, valid bidirectional IRC endpoints, and two endpoint reference geometries, "
    "and checks that each partial IRC endpoint lies between the TS and the matching endpoint reference geometry, yielding a path-direction-consistency pass/fail/inconclusive. "
    "DEFAULT seed path when one reaction coordinate is clear: scan_prepare (after internal_coordinates) → submit → scan_parse → fresh unconstrained OptTS; "
    "xtb_path/interpolate are fallbacks and never a saddle. This tool does no QM calculation itself — it only writes inputs, parses outputs, and issues verdicts; submit jobs with submit_compute_job. "
    "Coordinates never enter context; only numeric tables, verdicts, and file paths are returned."
)


class TsGuess_input_schema(input_schema):
    mode: Literal[
        "xtb_path", "interpolate", "scan_prepare", "scan_parse", "verify", "scan",
    ] = Field(
        default="xtb_path",
        description="Sub-function. DEFAULT SEED PATH when one forming/breaking bond/angle is known: "
                    "scan_prepare → submit → scan_parse (relaxed scan), then unconstrained OptTS from the peak. "
                    "Do NOT default to xtb_path/interpolate just because they are cheap. "
                    "xtb_path: xTB metadynamics path search between endpoints (needs `xtb`); falls back to "
                    "interpolate with path_kind='idpp_fallback' when xtb is absent (never silently). "
                    "interpolate: IDPP/linear images — only when both endpoints and the all-atom map are already "
                    "trustworthy; it is not the default TS-seed start. "
                    "scan_prepare (write a scan input; atom indices should come from internal_coordinates first), "
                    "scan_parse (parse a scan log and judge), verify (frequency+IRC verification). "
                    "Alias: 'scan' maps to 'scan_prepare' (or 'scan_parse' if log_path is given). "
                    "NOTE: xtb_path/interpolate return a PATH AND A GUESS, never a saddle point — "
                    "unconstrained OptTS + frequency + IRC are still required. The former 'xtb_neb' alias is gone: xTB has no NEB."
    )

    # ---------- interpolate ----------
    reactant_path: Optional[str] = Field(
        default=None,
        description="Reactant xyz file path; in strict verify, the reference geometry for one endpoint. "
                    "Absolute as-is, or relative to the Agent working directory.",
    )
    reactant_text: Optional[str] = Field(
        default=None,
        description="Reactant xyz text; in strict verify, the reference geometry for one endpoint. Path takes precedence.",
    )
    product_path: Optional[str] = Field(
        default=None,
        description="Product xyz file path; in strict verify, the reference geometry for the other endpoint. "
                    "Absolute as-is, or relative to the Agent working directory.",
    )
    product_text: Optional[str] = Field(
        default=None,
        description="Product xyz text; in strict verify, the reference geometry for the other endpoint. Path takes precedence.",
    )
    n_images: int = Field(default=10, description="interpolate: total image count (including endpoints), ≥2.")
    interp_method: Literal["idpp", "linear"] = Field(
        default="idpp", description="interpolate: interpolation method. idpp relaxes inter-image pair distances per Smidtstrup 2014; linear is linear interpolation."
    )
    atom_map: list[int] = Field(
        default_factory=list,
        description="interpolate: 1-based atom map; product atom k corresponds to reactant atom atom_map[k-1]. "
                    "Default is the identity; must be a valid permutation of 1..N with matching elements.",
    )
    watch_pairs: list[list[int]] = Field(
        default_factory=list,
        description="interpolate: atom pairs to monitor distances; strict/verify: pairs used for direction proof and imaginary-mode alignment. "
                    "All 1-based; default auto-picks the 5 pairs with the largest distance change between TS and intermediates "
                    "(imaginary-mode alignment is skipped if not provided).",
    )
    output_dir: Optional[str] = Field(
        default=None,
        description="interpolate: image output directory (default ./ts_interp/); verify: directory to write IRC endpoints (default <freq_log_stem>_verify/). "
                    "Relative paths resolve against the Agent working directory.",
    )
    timeout: int = Field(
        default=900,
        description="xtb_path: subprocess timeout in seconds. On expiry only this run's own "
                    "process group is terminated; its logs and intermediate files are kept.",
    )
    refinement_runs: int = Field(
        default=DEFAULT_REFINEMENT_RUNS, ge=1,
        description="xtb_path: ceiling on the number of path-refinement cycles handed to xTB "
                    "($path nrun). This is a COMPUTE ceiling, not a convergence criterion: the "
                    "engine stops by itself when its own criterion is met. Do NOT lower it: the "
                    "engine's built-in default is 3 cycles, which measurably truncates the path "
                    "(the highest frame then sits in the reactant's own basin, 21 deg from the "
                    "start, and an OptTS started from it never converges). If a run reports "
                    "termination='path_not_converged', raise this and rerun.",
    )

    # ---------- scan_prepare ----------
    input_path: Optional[str] = Field(default=None, description="scan_prepare: input structure file path (xyz). Absolute as-is, or relative to the Agent working directory.")
    input_text: Optional[str] = Field(default=None, description="scan_prepare: input structure xyz text.")
    engine: Literal["gaussian", "orca"] = Field(default="gaussian", description="Target QM program.")
    scans: Optional[list[dict]] = Field(
        default=None,
        description=(
            "scan_prepare: scan-coordinate list, one entry per scanned coordinate. "
            "Each entry: {\"coord_type\": \"bond\"|\"angle\"|\"dihedral\", \"atoms\": [2|3|4 atom indices, 1-based], "
            "\"scan_start\": optional start value (default the current geometry value), \"scan_end\": end value, "
            "\"scan_steps\": step count}. A single entry drives a 1D scan; a second entry makes a 2D coupled scan "
            "(Gaussian only — ORCA relaxed scans are 1D, so pass exactly one entry). "
            "Scanning only one geometric coordinate is often not enough: TS search frequently needs a second, "
            "coupled coordinate (e.g. both the forming and the breaking bond) to see a barrier."
        )
    )
    method: str = Field(default="b3lyp/def2svp", description="Method/basis, e.g. 'b3lyp/def2svp'. Honor the project/session MethodPolicy first (production often xtb + b3lyp); do not invent a freer functional unless policy/budget allows. For MLIP/external pass 'ExtOpt' (ORCA; pair with orca_blocks %method ProgExt) or 'external' (Gaussian; pair with extra_route='external=\"<prog>\"').")
    charge: int = Field(default=0, description="Total charge.")
    spin: int = Field(default=1, description="Spin multiplicity (2S+1).")
    extra_route: str = Field(default="", description="Extra route keywords (e.g. 'scrf=(solvent=water)' for Gaussian, or the external-program keyword for method='external').")
    nprocs: int = Field(default=4, description="Parallel cores (Gaussian %nprocshared / ORCA %pal).")
    output_path: Optional[str] = Field(default=None, description="scan_prepare: path to write the input file (gjf/inp, required). Absolute as-is, or relative to the Agent working directory.")
    job_name: str = Field(default="scan", description="Job name (used for chk file and title).")
    orca_blocks: Optional[str] = Field(
        default=None,
        description="scan_prepare, ORCA only: raw % blocks appended after %pal/%geom, e.g. the external-potential block '%method\\n  ProgExt \"/abs/path/to/mace\"\\n  Ext_Params \"--model /abs/model --device cpu --dtype float64\"\\nend' when method='ExtOpt'. Ignored for engine='gaussian'.",
    )

    # ---------- scan_parse ----------
    log_path: Optional[str] = Field(default=None, description="scan_parse: scan log file path. Absolute as-is, or relative to the Agent working directory.")
    ts_candidate_path: Optional[str] = Field(
        default=None, description="scan_parse: path to write the TS-guess xyz (default <log_stem>_ts_guess.xyz). Absolute as-is, or relative to the Agent working directory."
    )

    # ---------- verify ----------
    freq_log: Optional[str] = Field(default=None, description="verify: frequency-calculation log path. Absolute as-is, or relative to the Agent working directory.")
    irc_log: Optional[str] = Field(
        default=None,
        description="verify: IRC log path; optional in default mode, required in strict mode with valid frames on both rx<0 and rx>0 sides. "
                    "Absolute as-is, or relative to the Agent working directory.",
    )
    strict: bool = Field(
        default=False,
        description="verify only: enable a stateless path-direction consistency proof. IRC need not reach a minimum, but bidirectional valid endpoints, "
                    "TS geometry and reference geometries for both endpoints are required.",
    )


class TsGuess_output_schema(output_schema):
    is_success: bool = Field(description="Whether the operation succeeded")
    message: str = Field(default="", description="Status or error message")

    # interpolate
    images_dir: str = Field(default="", description="interpolate: image directory path")
    distance_table: str = Field(default="", description="interpolate: per-frame distance text table")
    ts_candidate_index: Optional[int] = Field(default=None, description="TS candidate frame index (0-based)")
    # scan_parse 也复用 ts_candidate_path
    ts_candidate_path: str = Field(default="", description="TS-guess xyz path")
    refinement_termination: Literal["", "converged", "cycles_exhausted"] = Field(
        default="",
        description="xtb_path: what the engine's own path-refinement loop reported. 'converged' = "
                    "xTB declared its convergence criterion met (the only state in which the TS "
                    "candidate is handed over); 'cycles_exhausted' = the refinement hit the "
                    "`refinement_runs` ceiling and the path is TRUNCATED, so is_success is False.",
    )
    path_kind: Literal["", "xtb_path", "idpp_fallback"] = Field(
        default="",
        description="How the path guess was produced. 'xtb_path' = xTB metadynamics path search; "
                    "'idpp_fallback' = xtb was unavailable so IDPP interpolation was used instead "
                    "(a degraded route, reported explicitly); '' = this mode does not produce a path. "
                    "Never treat a guess as a verified saddle point.",
    )

    # scan_prepare
    input_file_path: str = Field(default="", description="scan_prepare: generated input file path")
    run_hint: str = Field(default="", description="scan_prepare: submit/run hint")

    # scan_parse
    profile_table: str = Field(default="", description="scan_parse: per-point relative-energy text table (kcal/mol)")
    verdicts: list[str] = Field(default_factory=list, description="scan_parse: profile verdicts")
    barrier_kcal: Optional[float] = Field(default=None, description="scan_parse: constrained-scan diagnostic only (highest point − first point, kcal/mol) — NOT a verified ΔE‡/ΔG‡; unconstrained OptTS + freq + IRC still required before any barrier claim")
    candidate: Optional[dict] = Field(
        default=None,
        description="scan_parse: constrained-scan peak candidate as {scan_index, energy, geometry_ref, source} — "
                    "a seed for a fresh unconstrained OptTS, NOT a validated TS; "
                    "null when no internal peak exists or its geometry is unavailable.",
    )
    candidate_unavailable: bool = Field(
        default=False,
        description="scan_parse: an internal peak exists but its geometry could not be "
                    "recovered from this run's artifacts (a missing sidecar frame is NEVER "
                    "substituted with the last frame).",
    )

    # verify
    verdict: str = Field(
        default="",
        description="verify: default candidate/unlikely/inconclusive; strict is pass/fail/inconclusive.",
    )
    n_imag: Optional[int] = Field(default=None, description="verify: number of imaginary frequencies")
    imag_freqs: list[float] = Field(default_factory=list, description="verify: imaginary frequencies (cm⁻¹, negative)")
    checks: list[str] = Field(default_factory=list, description="verify: per-check details")
    irc_end_a_path: str = Field(default="", description="verify: IRC endpoint A xyz path")
    irc_end_b_path: str = Field(default="", description="verify: IRC endpoint B xyz path")
    imag_mode_aligned: Optional[bool] = Field(
        default=None,
        description="verify: whether the imaginary normal mode matches the watch_pairs reaction coordinate; "
                    "None if displacements cannot be parsed.",
    )
    imag_mode_alignment: str = Field(
        default="",
        description="verify: explanation of the imaginary-mode vs reaction-coordinate alignment check.",
    )


# ---------------------------------------------------------------------------
# 通用 xyz 读取 / 几何
# ---------------------------------------------------------------------------

def _load_xyz(input_path: Optional[str], input_text: Optional[str]):
    """从路径或文本读取 xyz，返回 ASE Atoms。惰性导入 ASE。"""
    import ase.io

    if input_path:
        if not os.path.isfile(input_path):
            raise ValueError(f"Input file does not exist: {input_path}")
        return ase.io.read(input_path, format="xyz")
    if input_text:
        return ase.io.read(StringIO(input_text), format="xyz")
    raise ValueError("Must provide one of path or text")


def _orca_keyword_method(method: str) -> str:
    """组合拼写转 ORCA `!` 关键字行形式：slash 拆成空格；def2 基组补 ORCA
    原生连字符（归一拼写 `def2svp` 不是合法 ORCA 基组关键字，照写会让
    ORCA 报未知基组，也会被 method_policy 误拆成两个方法候选）。"""
    toks = []
    for tok in method.replace("/", " ").split():
        t = tok.lower()
        if t.startswith("def2") and not t.startswith("def2-"):
            toks.append("def2-" + t[4:].upper())
        else:
            toks.append(tok)
    return " ".join(toks)


def _atoms_to_xyz_block(symbols, positions, comment: str = "") -> str:
    lines = [str(len(symbols)), comment]
    for s, p in zip(symbols, positions):
        lines.append(f"{s:<4} {p[0]:>14.8f} {p[1]:>14.8f} {p[2]:>14.8f}")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# interpolate：对齐 + 插值 + IDPP
# ---------------------------------------------------------------------------

def _kabsch_rotate(mobile, ref):
    """把 mobile（已去质心）旋转到 ref（已去质心）上，返回旋转后坐标。纯 numpy Kabsch。"""
    import numpy as np

    h = np.asarray(mobile).T @ np.asarray(ref)
    u, _s, vt = np.linalg.svd(h)
    d = np.sign(np.linalg.det(vt.T @ u.T))
    rot = vt.T @ np.diag([1.0, 1.0, d]) @ u.T
    return np.asarray(mobile) @ rot.T


def _select_watch_pairs(symbols, d_start, d_end, watch_pairs) -> list[tuple[int, int]]:
    """选监测原子对：给了 watch_pairs 就用它（1-based 输入，越界即报错）；否则用
    irc_path.classify_watch_pairs 的闸门对（键图 diff ∪ |Δd| top-5，唯一实现，
    键图由距离矩阵按共价半径判据派生）。两端无任何显著变化（闸门为空，如刚性
    平移玩具）时退回 |Δd| 最大的 5 对——只用于距离表展示，不作任何判定。
    interpolate 与 xtb_path 共用这一份实现。"""
    import numpy as np

    n = len(symbols)
    if watch_pairs:
        pairs: list[tuple[int, int]] = []
        for pair in watch_pairs:
            if len(pair) != 2:
                raise ValueError(f"Each watch_pairs entry must contain 2 atom indices: {pair}")
            i, j = pair[0] - 1, pair[1] - 1
            if not (0 <= i < n and 0 <= j < n) or i == j:
                raise ValueError(
                    f"watch_pairs atom indices out of range: {pair} (system has {n} atoms)"
                )
            pairs.append((min(i, j), max(i, j)))
        return pairs
    start_bonds = _bond_pairs_from_dist(symbols, d_start)
    end_bonds = _bond_pairs_from_dist(symbols, d_end)
    cls = _classify_watch_pairs(symbols, d_start, d_end, start_bonds, end_bonds)
    gate = sorted(set(cls["bond_diff"]) | set(cls["distance_top5"]))
    if gate:
        return gate
    iu = np.triu_indices(n, k=1)
    deltas = np.abs(d_end[iu] - d_start[iu])
    order = np.argsort(-deltas)[:5]
    return sorted({(int(iu[0][o]), int(iu[1][o])) for o in order})


def _idpp_relax(images, max_iter: int = 4000, lr: float = 0.02, tol: float = 1e-7):
    """IDPP（Smidtstrup 2014）：中间图像的对距离矩阵向线性目标弛豫。

    images: (N, n, 3) 数组，首末帧固定。目标：第 k 帧对距离矩阵 = 两端对距离矩阵的线性插值，
    权重 w = 1/d_target^4。Adam 优化，纯 numpy 实现。
    """
    import numpy as np

    images = np.asarray(images, dtype=float).copy()
    n_img = len(images)
    if n_img <= 2:
        return images

    d_r = _dist_matrix(images[0])
    d_p = _dist_matrix(images[-1])
    n = images.shape[1]
    iu = np.triu_indices(n, k=1)

    targets = []
    weights = []
    for k in range(1, n_img - 1):
        t = k / (n_img - 1)
        d_t = (1.0 - t) * d_r + t * d_p
        targets.append(d_t[iu])
        weights.append(1.0 / np.clip(d_t[iu], 0.1, None) ** 4)

    m = np.zeros_like(images)
    v = np.zeros_like(images)
    beta1, beta2, eps = 0.9, 0.999, 1e-8

    for it in range(1, max_iter + 1):
        grad = np.zeros_like(images)
        for k in range(1, n_img - 1):
            pos = images[k]
            d = _dist_matrix(pos)[iu]
            diff = pos[iu[0]] - pos[iu[1]]  # (npair, 3)
            err = d - targets[k - 1]
            # dS/d(diff) = 2 w err * diff / d；先把 (npair,) 扩成 (npair,1) 再乘 (npair,3)
            scale = (2.0 * weights[k - 1] * err / np.clip(d, 1e-8, None))[:, None]
            g_pair = scale * diff
            np.add.at(grad[k], iu[0], g_pair)
            np.add.at(grad[k], iu[1], -g_pair)

        max_step = float(np.abs(grad[1:-1]).max()) if n_img > 2 else 0.0
        if max_step < tol:
            break
        m = beta1 * m + (1 - beta1) * grad
        v = beta2 * v + (1 - beta2) * grad ** 2
        m_hat = m / (1 - beta1 ** it)
        v_hat = v / (1 - beta2 ** it)
        step = lr * m_hat / (np.sqrt(v_hat) + eps)
        images[1:-1] -= step[1:-1]
    return images


# ---------------------------------------------------------------------------
# scan_parse：能量剖面判定（纯函数，便于单测）
# ---------------------------------------------------------------------------

def analyze_scan_profile(rel_energies_kcal: Sequence[float]) -> dict:
    """对相对能量剖面（kcal/mol）做判定。返回 barrier_kcal/ts_index/verdicts。

    判定项：全程单调、相邻能量突跳（滑谷/不连续）、极值在扫描边界、多峰。
    """
    import numpy as np

    e = np.asarray(rel_energies_kcal, dtype=float)
    if e.ndim != 1 or len(e) < 2:
        raise ValueError("The energy profile needs at least 2 points")
    n = len(e)
    ts_index = int(np.argmax(e))
    barrier = float(e[ts_index] - e[0])
    verdicts: list[str] = []

    diffs = np.diff(e)
    if np.all(diffs >= 0) or np.all(diffs <= 0):
        verdicts.append("Scan energy is monotonic throughout: possibly no barrier or a wrongly chosen scan coordinate; check the reaction coordinate choice.")

    abs_diffs = np.abs(diffs)
    med = float(np.median(abs_diffs))
    jump_idx = int(np.argmax(abs_diffs))
    jump = float(abs_diffs[jump_idx])
    if jump > 3.0 * med and jump > 2.0:
        verdicts.append(
            f"Energy jump of {jump:.2f} kcal/mol between frames {jump_idx}→{jump_idx + 1} "
            f"(median {med:.2f}): possible valley sliding/discontinuity; inspect the structures near this point."
        )

    if ts_index == 0 or ts_index == n - 1:
        verdicts.append(
            f"Energy extremum lies on the scan boundary (frame {ts_index}): extend the scan range to include the true barrier top."
        )

    peaks = [i for i in range(1, n - 1) if e[i] > e[i - 1] and e[i] > e[i + 1]]
    if len(peaks) > 1:
        verdicts.append(f"Multiple energy peaks detected (frames {', '.join(str(i) for i in peaks)}); inspect each one.")

    return {"barrier_kcal": barrier, "ts_index": ts_index, "verdicts": verdicts}


# ---------------------------------------------------------------------------
# scan_parse：Gaussian / ORCA 日志解析
# ---------------------------------------------------------------------------

_SCAN_SUMMARY_RE = re.compile(r"Summary of .*Potential Surface Scan", re.IGNORECASE)
_EIGEN_LINE_RE = re.compile(r"Eigenvalues --\s+((?:-?\d+\.\d+\s*)+)")


def _parse_gaussian_scan_summary(text: str) -> list[float]:
    """解析 Gaussian 扫描日志的 "Summary of ... Potential Surface Scan" 表，返回各点能量（Eh）。"""
    m = _SCAN_SUMMARY_RE.search(text)
    if not m:
        raise ValueError("No 'Summary of ... Potential Surface Scan' table found in the log.")
    energies: list[float] = []
    for line in text[m.end():].splitlines():
        em = _EIGEN_LINE_RE.search(line)
        if em:
            energies.extend(float(v) for v in em.group(1).split())
    if not energies:
        raise ValueError("No Eigenvalues energy lines parsed from the scan summary table.")
    return energies


# 复用 orca_frames 的同一正则（容忍 "(From external program)" 后缀与 D 指数），
# 避免两处对同一日志行的解析规则漂移（GH #23）。
_ORCA_SPE_RE = orca_frames.FINAL_ENERGY_RE

# ORCA relaxed surface scan 的扫描点边界标记（每个扫描点一次）。
_SCAN_STEP_MARKER_RE = re.compile(r"RELAXED SURFACE SCAN STEP\s+\d+")


class _ScanStepsUngroupable(Exception):
    """ORCA relaxed-scan 日志文本无法按扫描步可靠分组（标记缺失/步内能量或几何
    缺位）：此时严禁按块均分等启发式把几何拼给某个能量帧（GH G1）。"""


def _parse_orca_scan(text: str) -> list[dict]:
    """按扫描步分组解析 ORCA relaxed-scan 文本回退，返回每步一帧（与扫描点一一对应）：

        [{"index": i, "energy_hartree": Eh, "geom": [(symbol, x, y, z), ...]}, ...]

    relaxed scan 的每个扫描点是一段约束优化，期间每轮优化周期都会打印一条
    'FINAL SINGLE POINT ENERGY'（实测 ORCA 6.1.1 的 10 点扫描共 55 条）——只有
    opt 块收敛后的最后一条才是该扫描点的能量。因此按 'RELAXED SURFACE SCAN
    STEP N' 标记切段，每段取最后一条能量与最后一块直角坐标（即收敛结构的
    能量与几何），而不是把每个优化周期的能量当扫描点、再按块均分猜几何。

    日志没有扫描步标记、或任一步段缺能量/几何时抛 _ScanStepsUngroupable；
    调用方走 candidate_unavailable 通道（参照 _SidecarIncomplete 语义），
    绝不按块均分等启发式发几何（GH #16/#G1）。
    """
    energies_all = [float(v.replace("D", "E").replace("d", "e")) for v in _ORCA_SPE_RE.findall(text)]
    if not energies_all:
        tail = text[-1500:]
        raise ValueError(f"Failed to parse scan energies from ORCA output ('FINAL SINGLE POINT ENERGY' not found).\nOutput tail:\n{tail}")
    markers = list(_SCAN_STEP_MARKER_RE.finditer(text))
    if not markers:
        raise _ScanStepsUngroupable(
            "the log text has no 'RELAXED SURFACE SCAN STEP' markers, so the "
            f"{len(energies_all)} 'FINAL SINGLE POINT ENERGY' lines (one per optimization "
            "cycle) cannot be mapped to scan points."
        )
    bounds = [m.start() for m in markers] + [len(text)]
    steps: list[dict] = []
    for i in range(len(markers)):
        seg = text[bounds[i]:bounds[i + 1]]
        seg_energies = [float(v.replace("D", "E").replace("d", "e")) for v in _ORCA_SPE_RE.findall(seg)]
        geoms: list[list[tuple[str, float, float, float]]] = []
        for m in re.finditer(r"CARTESIAN COORDINATES \(ANGSTROEM\)", seg):
            geom: list[tuple[str, float, float, float]] = []
            for line in seg[m.end():].splitlines()[2:]:
                parts = line.split()
                if len(parts) >= 4 and parts[0].isalpha():
                    try:
                        geom.append((parts[0], float(parts[1]), float(parts[2]), float(parts[3])))
                        continue
                    except ValueError:
                        pass
                break
            if geom:
                geoms.append(geom)
        if not seg_energies or not geoms:
            raise _ScanStepsUngroupable(
                f"scan step {i + 1} contains no FINAL SINGLE POINT ENERGY or no Cartesian "
                "geometry block; the per-step energies and geometries cannot be aligned."
            )
        steps.append({"index": i, "energy_hartree": seg_energies[-1], "geom": geoms[-1]})
    return steps


_ORCA_NAME_RE = re.compile(r"^\s*NAME\s*=\s*(?P<path>\S+)\s*$", re.M)


class _SidecarIncomplete(Exception):
    """relaxscanact.dat 存在但逐帧几何缺失/不匹配：峰值帧严禁用末帧替代。"""

    def __init__(self, message: str, energies: Optional[list] = None):
        super().__init__(message)
        self.energies = energies


def _find_orca_sidecar_dat(log_path: str, workdir: str) -> Optional[str]:
    """stem 不匹配时定位 relaxscanact.dat，找不到或无法唯一确定返回 None。

    优先从日志的输入回显（``NAME = <作业>.inp``）推导真实作业名——harness 的
    日志名（如 .cloudra/calc-28.out.log）与 ORCA 作业名无关；其次在日志目录
    与其父目录（计算工作目录）找唯一的 sidecar，多于一个时拒绝猜测（GH #23）。
    """
    try:
        with open(log_path, encoding="utf-8", errors="replace") as f:
            head = f.read(200_000)  # NAME 在日志开头的输入回显段
    except OSError:
        head = ""
    m = _ORCA_NAME_RE.search(head)
    if m:
        candidate = os.path.splitext(m.group("path"))[0] + ".relaxscanact.dat"
        if os.path.isfile(candidate):
            return candidate
    import glob

    found = set(glob.glob(os.path.join(workdir, "*.relaxscanact.dat")))
    found.update(glob.glob(os.path.join(os.path.dirname(workdir), "*.relaxscanact.dat")))
    if len(found) == 1:
        return found.pop()
    return None


def _parse_orca_relaxed_scan_sidecar(log_path: str) -> Optional[dict]:
    """解析 ORCA relaxed scan 的 sidecar 产物（优先于 .out 文本）。

    ORCA 沿作业名写 ``<job>.relaxscanact.dat``（每帧一行：扫描坐标值 + 总能量 Eh）
    与逐帧几何 ``<job>.NNN.xyz``（NNN=帧号，1-based，与 dat 行号一一对应）。
    返回 {"energies": [...], "frames": [(symbols, positions), ...]}，帧数必须与
    dat 行数一致；任何缺失/不一致返回 None（调用方回退 .out 文本解析）。

    能量最高帧（TS 候选）通常不是末帧；sidecar 让 scan_parse 能按能量最高帧
    而不是 ``rfind`` 出来的末帧取几何。

    sidecar 定位：先按日志名 stem 在日志同目录找；不匹配时经
    ``_find_orca_sidecar_dat`` 从日志 NAME 记录/唯一 glob 推导（GH #23）。
    """
    import glob

    import numpy as np

    stem = os.path.splitext(os.path.basename(log_path))[0]
    workdir = os.path.dirname(os.path.abspath(log_path))
    dat_path = os.path.join(workdir, f"{stem}.relaxscanact.dat")
    if not os.path.isfile(dat_path):
        dat_path = _find_orca_sidecar_dat(log_path, workdir)
        if dat_path is None:
            return None
        workdir = os.path.dirname(dat_path)
        stem = os.path.basename(dat_path)[: -len(".relaxscanact.dat")]
    try:
        with open(dat_path, encoding="utf-8", errors="replace") as f:
            energies = []
            for line in f:
                parts = line.split()
                if len(parts) < 2:
                    continue
                try:
                    energies.append(float(parts[1]))
                except ValueError:
                    continue
    except OSError as exc:
        raise _SidecarIncomplete(f"{dat_path} exists but cannot be read: {exc}") from exc
    if not energies:
        raise _SidecarIncomplete(f"{dat_path} contains no parseable energy rows.")

    frame_paths = sorted(
        glob.glob(os.path.join(workdir, f"{stem}.[0-9][0-9][0-9].xyz")),
    )
    if len(frame_paths) != len(energies):
        raise _SidecarIncomplete(
            f"{dat_path} lists {len(energies)} scan points but only "
            f"{len(frame_paths)} {stem}.NNN.xyz frame files exist next to it.",
            energies=energies,
        )
    # 帧号必须 1..N 连续（NNN 与 dat 行号一一对应）；glob 排序按文件名即号码序
    for i, p in enumerate(frame_paths):
        number = os.path.splitext(os.path.basename(p))[0].rsplit(".", 1)[-1]
        if not number.isdigit() or int(number) != i + 1:
            raise _SidecarIncomplete(
                f"frame numbering next to {dat_path} is not continuous 1..N "
                f"(offending file: {os.path.basename(p)}).",
                energies=energies,
            )

    try:
        import ase.io

        frames = []
        for p in frame_paths:
            atoms = ase.io.read(p, format="xyz")
            frames.append((atoms.get_chemical_symbols(), np.asarray(atoms.get_positions(), dtype=float)))
    except Exception as exc:
        raise _SidecarIncomplete(
            f"a scan frame file next to {dat_path} is unreadable: {exc}",
            energies=energies,
        ) from exc
    return {"energies": energies, "frames": frames}


# ---------------------------------------------------------------------------
# verify：频率解析（cclib 优先，正则回退）+ IRC 端点
#
# Gaussian 频率/位移块正则与 Standard orientation 解析归位共享层
# cloudra.tools.core.gaussian_frames（FREQ_LINE_RE / vibdisps_from_text /
# std_orientation_frames），本模块不再保留重复实现。
# ---------------------------------------------------------------------------


def _assess_imag_mode_alignment(
    vibfreqs: Sequence[float],
    vibdisps,
    watch_pairs: Sequence[Sequence[int]],
    symbols: Optional[Sequence[str]] = None,
    positions=None,
    charge: int = 0,
    **_kwargs,
) -> dict[str, Any]:
    """检查最低虚频模式是否主要落在 watch_pairs 反应中心上。

    对每个原子对取 |d_i - d_j|；要求 watch_pairs 中至少一对达到全局最大相对位移的
    `_IMAG_MODE_WATCH_RATIO` 倍。缺位移数据时 status=missing。

    扭转/角主导的 TS（阻转、环翻转、锥形反转）：全局最大相对位移对**两端不成键**
    （用 TS 几何的 perceive_bonds 键图判）时，键对距离本就几乎不动，pair-distance
    对齐材料不足以判方向——status=undecidable（strict 下降级为 inconclusive，
    不误判方向不符）。主导对是键对、或 TS 几何缺失无法判成键性时，维持原规则。
    """
    import numpy as np

    if vibdisps is None:
        return {
            "status": "missing",
            "aligned": None,
            "message": "The frequency log lacks normal-mode displacements; cannot check the imaginary-frequency direction.",
            "details": [],
        }
    imag_idxs = [i for i, f in enumerate(vibfreqs) if f < 0]
    if not imag_idxs:
        return {
            "status": "missing",
            "aligned": None,
            "message": "No imaginary frequency; skipping the imaginary-mode alignment check.",
            "details": [],
        }
    mode_idx = min(imag_idxs, key=lambda i: vibfreqs[i])
    try:
        disps = np.asarray(vibdisps[mode_idx], dtype=float)
    except (IndexError, TypeError, ValueError):
        return {
            "status": "missing",
            "aligned": None,
            "message": "The frequency log lacks normal-mode displacements; cannot check the imaginary-frequency direction.",
            "details": [],
        }
    if disps.ndim != 2 or disps.shape[1] != 3 or disps.shape[0] < 2:
        return {
            "status": "missing",
            "aligned": None,
            "message": "The frequency log lacks normal-mode displacements; cannot check the imaginary-frequency direction.",
            "details": [],
        }

    n = disps.shape[0]
    pair_mags: list[tuple[tuple[int, int], float]] = []
    max_rel = 0.0
    max_pair = (0, 1)
    for i in range(n):
        for j in range(i + 1, n):
            rel = float(np.linalg.norm(disps[i] - disps[j]))
            pair_mags.append(((i, j), rel))
            if rel > max_rel:
                max_rel = rel
                max_pair = (i, j)

    if max_rel <= 0.0:
        return {
            "status": "missing",
            "aligned": None,
            "message": "All imaginary-mode displacements are zero; cannot check direction.",
            "details": [],
        }

    if not watch_pairs:
        return {
            "status": "skipped",
            "aligned": None,
            "message": "No watch_pairs provided; skipping the imaginary-mode vs reaction-coordinate alignment check.",
            "details": [f"Global max relative-displacement pair=({max_pair[0] + 1},{max_pair[1] + 1})"],
        }

    threshold = _IMAG_MODE_WATCH_RATIO * max_rel
    watch_set: set[frozenset[int]] = set()
    watch_details: list[str] = []
    best_watch = 0.0
    for raw in watch_pairs:
        if len(raw) != 2:
            continue
        i, j = int(raw[0]) - 1, int(raw[1]) - 1
        if not (0 <= i < n and 0 <= j < n) or i == j:
            watch_details.append(f"watch_pairs atom indices invalid: {raw}")
            continue
        lo, hi = (i, j) if i < j else (j, i)
        watch_set.add(frozenset((lo, hi)))
        rel = float(np.linalg.norm(disps[lo] - disps[hi]))
        best_watch = max(best_watch, rel)
        watch_details.append(
            f"Atom pair ({lo + 1},{hi + 1}) relative displacement={rel:.3f}"
            f" (threshold {_IMAG_MODE_WATCH_RATIO:.2f}×{max_rel:.3f}={threshold:.3f})"
        )

    max_fs = frozenset(max_pair)
    # 最大相对位移对本身在 watch_pairs 中 → 对齐；否则须严格超过比例阈值，
    # 避免「两端反向伸缩、监视原子静止」时 |d_i-d_j| 恰好 = 0.5×max 的假阳性。
    if max_fs in watch_set:
        aligned = best_watch >= threshold
    else:
        aligned = best_watch > threshold
    if aligned:
        message = (
            f"Imaginary mode is consistent with the declared reaction coordinate: watch_pairs max relative displacement {best_watch:.3f} "
            f"≥ {_IMAG_MODE_WATCH_RATIO:.2f}×global max {max_rel:.3f} "
            f"(max pair=({max_pair[0] + 1},{max_pair[1] + 1}))."
        )
        status = "aligned"
    else:
        # 扭转/角主导模式：全局最大相对位移对两端不成键时，键对距离几乎不动是
        # 这类模式的固有性质，pair-distance 对齐无法判方向——undecidable。
        dominant_bonded: Optional[bool] = None
        if symbols is not None and positions is not None and len(symbols) == n:
            bond_graph, _src = _perceive_bonds(list(symbols), positions, charge)
            dominant_bonded = (min(max_pair), max(max_pair)) in bond_graph
        if dominant_bonded is False:
            return {
                "status": "undecidable",
                "aligned": None,
                "message": (
                    f"The imaginary mode's dominant motion is on the NON-BONDED atom pair "
                    f"({max_pair[0] + 1},{max_pair[1] + 1}): a torsion/angle-dominated mode "
                    "(hindered rotation, ring flip, pyramidal inversion) barely moves bonded-pair "
                    "distances, so pair-distance alignment against watch_pairs cannot judge its "
                    "direction. The material is insufficient for a pass/fail verdict."
                ),
                "details": watch_details,
            }
        message = (
            f"Imaginary mode is inconsistent with the declared reaction coordinate: watch_pairs max relative displacement {best_watch:.3f} "
            f"< {_IMAG_MODE_WATCH_RATIO:.2f}×global max {max_rel:.3f} "
            f"(dominant motion on atom pair ({max_pair[0] + 1},{max_pair[1] + 1}))."
        )
        status = "misaligned"
    return {
        "status": status,
        "aligned": aligned,
        "message": message,
        "details": watch_details,
    }


def _parse_freq_log(log_path: str, engine: str) -> dict:
    """解析频率日志。除频率与收敛性外，尽量返回末帧元素、坐标与 vibdisps。"""
    with open(log_path, encoding="utf-8", errors="replace") as f:
        text = f.read()

    vibfreqs: Optional[list[float]] = None
    vibdisps = None
    converged: Optional[bool] = None
    symbols: Optional[list[str]] = None
    positions = None

    try:
        import cclib

        data = cclib.io.ccread(log_path)
        if data is not None:
            vf = getattr(data, "vibfreqs", None)
            if vf is not None and len(vf) > 0:
                vibfreqs = [float(v) for v in vf]
            vd = getattr(data, "vibdisps", None)
            if vd is not None and len(vd) > 0:
                import numpy as np

                vibdisps = np.asarray(vd, dtype=float)
            optdone = getattr(data, "optdone", None)
            if isinstance(optdone, bool):
                converged = optdone
            elif optdone:
                converged = True
            atomnos = getattr(data, "atomnos", None)
            atomcoords = getattr(data, "atomcoords", None)
            # openbabel 回退解析失败时会给 shape (n,0) 的畸形空 atomcoords：
            # len(atomcoords)>0（帧数非零）但无原子。必须同时校验 atomnos 与
            # 末帧原子数非空，否则空 symbols/positions 会挡住标准取向回退。
            if (
                atomnos is not None
                and atomcoords is not None
                and len(atomnos) > 0
                and len(atomcoords) > 0
                and getattr(atomcoords[-1], "size", 0) > 0
            ):
                import numpy as np
                from cclib.parser.utils import PeriodicTable

                pt = PeriodicTable()
                symbols = [pt.element[int(z)] for z in atomnos]
                positions = np.asarray(atomcoords[-1], dtype=float)
    except Exception:
        pass

    if vibfreqs is None:
        if engine == "orca":
            # cclib 1.8.x 解析 ORCA 6.x 日志整体抛 IndexError（实测 ORCA 6.1.1 全灭），
            # 且 ExtOpt/NumFreq 等外部 MLIP 日志无 SCF 块 cclib 也常失败——文本回退
            # 走 orca_frames 的 VIBRATIONAL FREQUENCIES 原生解析（Gaussian 的
            # "Frequencies --" 行在 ORCA 日志里不存在，GH #G2）。
            vibfreqs = orca_frames.vibfreqs_from_text(text) or None
        else:
            # 正则回退：Gaussian "Frequencies --" 行（虚频以负值打印）
            freqs: list[float] = []
            for m in gaussian_frames.FREQ_LINE_RE.finditer(text):
                for tok in m.group(1).split():
                    try:
                        freqs.append(float(tok))
                    except ValueError:
                        break
            if freqs:
                vibfreqs = freqs

    if vibfreqs is None:
        raise ValueError(f"Failed to parse vibrational frequencies from the frequency log: {log_path}")

    if vibdisps is None and engine == "gaussian":
        vibdisps = gaussian_frames.vibdisps_from_text(text, len(vibfreqs))
    elif vibdisps is None and engine == "orca":
        # ORCA 6.1 日志 cclib 整体崩溃（vibdisps 拿不到）→ 文本权威 NORMAL MODES
        # 位移块回退（GH #G2）。ORCA 版式：模式号表头 + 3N 行笛卡尔分量。
        n_atoms = len(vibfreqs) // 3 if len(vibfreqs) % 3 == 0 else 0
        if n_atoms > 0:
            vibdisps = orca_frames.vibdisps_from_text(text, len(vibfreqs), n_atoms)

    if converged is None:
        if engine == "orca":
            # ORCA 没有 Gaussian 的 "Normal termination" 标记（自报 "ORCA TERMINATED
            # NORMALLY"），且跑满最大步数未收敛的优化仍会正常终止——收敛状态优先按
            # ORCA 自己的优化收敛标记判定，非优化作业回退到正常终止标记（GH #G3）。
            opt_state = orca_frames.opt_converged(text)
            converged = opt_state if opt_state is not None else orca_frames.normal_termination(text)
        else:
            # 文本回退：正常终止且无错误标记视为收敛（含纯 freq 作业沿用已收敛几何的情形）
            converged = ("Normal termination" in text) and ("Error termination" not in text)

    if positions is None and engine == "gaussian":
        blocks = gaussian_frames.std_orientation_frames(text)
        if blocks:
            import numpy as np
            from cclib.parser.utils import PeriodicTable

            rows = blocks[-1]
            pt = PeriodicTable()
            symbols = [pt.element[int(z)] for z, *_ in rows]
            positions = np.asarray([[x, y, z] for _, x, y, z in rows], dtype=float)
    elif positions is None and engine == "orca":
        # ORCA 末帧几何同样走文本权威 CARTESIAN COORDINATES (ANGSTROEM) 块：
        # strict 的几何区间层需要 TS 几何，而 freq 日志的末帧几何就是被验证的
        # TS（cclib 对 ORCA 6.1 崩溃时 positions 会缺失，不能因此判 inconclusive）。
        ts_xyz = orca_frames.final_xyz_from_text(text)
        parsed_xyz = _parse_xyz(ts_xyz) if ts_xyz.strip() else None
        if parsed_xyz is not None:
            import numpy as np

            symbols = list(parsed_xyz[0])
            positions = np.asarray(parsed_xyz[1], dtype=float)

    return {
        "vibfreqs": vibfreqs,
        "vibdisps": vibdisps,
        "converged": converged,
        "symbols": symbols,
        "positions": positions,
    }


# ---------------------------------------------------------------------------
# Tool 主类
# ---------------------------------------------------------------------------

class TsGuess(Tool):
    tool_id: str = 't-45'
    tool_name: str = 'ts_guess'
    tool_description: str = description
    input_schema: Any = TsGuess_input_schema
    output_schema: Any = TsGuess_output_schema

    def is_write(self) -> bool:
        return True

    async def tool_call(self, user_input: TsGuess_input_schema, session: Session) -> TsGuess_output_schema:
        # 路径语义收口：所有文件路径字段的相对路径统一解析到 agent 工作
        # 目录（沙箱）；绝对路径保持既有权限语义。
        user_input = user_input.model_copy(
            update={
                field: resolve_tool_path(self, value)
                for field, value in {
                    "reactant_path": user_input.reactant_path,
                    "product_path": user_input.product_path,
                    "input_path": user_input.input_path,
                    "output_path": user_input.output_path,
                    "log_path": user_input.log_path,
                    "ts_candidate_path": user_input.ts_candidate_path,
                    "freq_log": user_input.freq_log,
                    "irc_log": user_input.irc_log,
                    "output_dir": user_input.output_dir,
                }.items()
                if value
            }
        )
        mode = user_input.mode
        if mode == "scan":
            mode = "scan_parse" if user_input.log_path else "scan_prepare"

        handlers = {
            "xtb_path": self._xtb_path,
            "interpolate": self._interpolate,
            "scan_prepare": self._scan_prepare,
            "scan_parse": self._scan_parse,
            "verify": self._verify,
        }
        try:
            # handler 是同步重活（xtb_path 会 proc.communicate 等 xTB 子进程、
            # scan_parse 逐帧啃大日志）：卸载出事件循环，避免冻结整个 API。
            return await asyncio.to_thread(handlers[mode], user_input)
        except Exception as e:
            return TsGuess_output_schema(is_success=False, message=f"{user_input.mode} failed: {e}")

    # ---------- mode=interpolate ----------

    def _interpolate(self, user_input: TsGuess_input_schema) -> TsGuess_output_schema:
        import numpy as np

        if user_input.n_images < 2:
            raise ValueError("n_images must be ≥ 2")

        r_atoms = _load_xyz(user_input.reactant_path, user_input.reactant_text)
        p_atoms = _load_xyz(user_input.product_path, user_input.product_text)
        r_syms = r_atoms.get_chemical_symbols()
        p_syms = p_atoms.get_chemical_symbols()
        r_pos = np.asarray(r_atoms.get_positions(), dtype=float)
        p_pos = np.asarray(p_atoms.get_positions(), dtype=float)
        n = len(r_syms)

        if len(p_syms) != n:
            raise ValueError(f"Reactant ({n} atoms) and product ({len(p_syms)} atoms) have different atom counts")
        if sorted(r_syms) != sorted(p_syms):
            raise ValueError(f"Reactant and product element multisets differ: {sorted(r_syms)} vs {sorted(p_syms)}")

        # atom_map 重排产物：产物第 k 个原子（0-based k-1）对应反应物第 atom_map[k-1] 个原子
        if user_input.atom_map:
            am = user_input.atom_map
            if sorted(am) != list(range(1, n + 1)):
                raise ValueError(f"atom_map must be a valid permutation of 1..{n}, got: {am}")
            new_pos = np.zeros_like(p_pos)
            new_syms: list[str] = [""] * n
            for k, target in enumerate(am):
                if p_syms[k] != r_syms[target - 1]:
                    raise ValueError(
                        f"atom_map element mismatch: product atom {k + 1} ({p_syms[k]}) maps to "
                        f"reactant atom {target} ({r_syms[target - 1]})"
                    )
                new_pos[target - 1] = p_pos[k]
                new_syms[target - 1] = p_syms[k]
            p_pos = new_pos
            p_syms = new_syms
        elif r_syms != p_syms:
            raise ValueError(
                "Reactant and product atom orders differ and no atom_map was provided; cannot pair atoms one-to-one. "
                "Run reaction_mapping on the reactant/product SMILES first and pass its atom_map — "
                "degenerate/rearrangement systems (reactant = product with permuted atom numbering) always need one."
            )

        # Kabsch 对齐（各自去质心后旋转产物到反应物取向）
        r_centered = r_pos - r_pos.mean(axis=0)
        p_centered = p_pos - p_pos.mean(axis=0)
        p_aligned = _kabsch_rotate(p_centered, r_centered)

        # 生成 N 帧线性插值
        n_img = user_input.n_images
        images = np.zeros((n_img, n, 3))
        for k in range(n_img):
            t = k / (n_img - 1)
            images[k] = (1.0 - t) * r_centered + t * p_aligned

        if user_input.interp_method == "idpp":
            images = _idpp_relax(images)

        # 落盘
        out_dir = user_input.output_dir or resolve_tool_path(self, "./ts_interp")
        os.makedirs(out_dir, exist_ok=True)
        for k in range(n_img):
            atomic_write_text(
                os.path.join(out_dir, f"img_{k:02d}.xyz"),
                _atoms_to_xyz_block(r_syms, images[k], comment=f"ts_guess {user_input.interp_method} image {k}"),
            )

        # 监测原子对
        d_r = _dist_matrix(images[0])
        d_p = _dist_matrix(images[-1])
        pairs = _select_watch_pairs(r_syms, d_r, d_p, user_input.watch_pairs)

        # 距离表
        header = f"{'frame':>4}" + "".join(f"  {_pair_label(r_syms, pr):>12}" for pr in pairs)
        lines = [header]
        for k in range(n_img):
            d_k = _dist_matrix(images[k])
            row = f"{k:>4}" + "".join(f"  {d_k[i, j]:>12.4f}" for i, j in pairs)
            lines.append(row)
        distance_table = "\n".join(lines)

        # TS 候选帧：变化最大原子对的距离跨过两端中点的帧
        deltas = {pr: abs(d_p[pr] - d_r[pr]) for pr in pairs}
        key_pair = max(deltas, key=deltas.get)
        mid = 0.5 * (d_r[key_pair] + d_p[key_pair])
        ts_index = 0
        for k in range(n_img):
            d_k = _dist_matrix(images[k])[key_pair]
            if (d_k - mid) * (d_r[key_pair] - mid) <= 0:
                ts_index = k
                break
        else:
            ts_index = int(np.argmin([abs(_dist_matrix(images[k])[key_pair] - mid) for k in range(n_img)]))
        ts_path = os.path.join(out_dir, f"img_{ts_index:02d}.xyz")

        return TsGuess_output_schema(
            is_success=True,
            images_dir=out_dir,
            distance_table=distance_table,
            ts_candidate_index=ts_index,
            ts_candidate_path=ts_path,
            message=(
                f"Generated {n_img} images ({user_input.interp_method}) in {out_dir}. "
                f"TS candidate frame: img_{ts_index:02d}.xyz (watched pair {_pair_label(r_syms, key_pair)} crosses the endpoint midpoint). "
                "These images can serve directly as a NEB initial path, or be optimized frame by frame with constraints to find a TS guess; "
                "you can also use scan_prepare to generate a constrained-scan input to further locate the barrier top."
            ),
        )

    # ---------- mode=xtb_path ----------

    def _xtb_path(self, user_input: TsGuess_input_schema) -> TsGuess_output_schema:
        """xTB 元动力学路径搜索出 TS 初猜（SOP `guess` 阶段的便宜端）。

        **这个模式返回的是路径与初猜，不是鞍点**：``xtbpath_ts.xyz`` 是 MTD 采到的最高点附近
        结构，验证仍归 ``verify``（频率 + IRC）。两条纪律：

        - xTB **不存在**时退回 IDPP 插值，并把 ``path_kind`` 标成 ``idpp_fallback``、
          在 message 里写明走了降级路线——绝不静默降级。
        - xTB **存在但跑失败**时**不**换兜底充数：报出分层分类与持久运行目录，让调用方决定。
        """
        import numpy as np

        from cloudra.tools.core.xtb_path_runner import XtbPathRequest, run_xtb_path

        r_atoms = _load_xyz(user_input.reactant_path, user_input.reactant_text)
        p_atoms = _load_xyz(user_input.product_path, user_input.product_text)
        r_syms = r_atoms.get_chemical_symbols()
        p_syms = p_atoms.get_chemical_symbols()
        if sorted(r_syms) != sorted(p_syms):
            raise ValueError(
                "xtb_path needs one consistent atom set: the reactant and product element "
                f"multisets differ ({sorted(r_syms)} vs {sorted(p_syms)})"
            )
        r_pos = np.asarray(r_atoms.get_positions(), dtype=float)
        p_pos = np.asarray(p_atoms.get_positions(), dtype=float)

        out_dir = user_input.output_dir or resolve_tool_path(self, "./ts_path")
        os.makedirs(out_dir, exist_ok=True)

        run = run_xtb_path(XtbPathRequest(
            reactant_xyz=_atoms_to_xyz_block(r_syms, r_pos, "ts_guess reactant"),
            product_xyz=_atoms_to_xyz_block(p_syms, p_pos, "ts_guess product"),
            output_dir=out_dir,
            charge=user_input.charge,
            multiplicity=user_input.spin,
            timeout=user_input.timeout,
            refinement_runs=user_input.refinement_runs,
            run_label="guess",
        ))

        if run.termination_reason == "executable_missing":
            fallback = self._interpolate(user_input)
            fallback.path_kind = "idpp_fallback"
            fallback.message += (
                "\nNOTE: the `xtb` executable was not found on PATH, so this path guess fell back "
                f"to {user_input.interp_method.upper()} interpolation (path_kind='idpp_fallback'). "
                "That is a degraded route: an interpolation between the two endpoints, NOT a "
                "metadynamics path search. Install xtb to get path_kind='xtb_path'."
            )
            return fallback

        if not run.usable_as_guess:
            if run.termination_reason == "path_not_converged":
                return TsGuess_output_schema(
                    is_success=False,
                    path_kind="",
                    refinement_termination=run.refinement_termination,
                    message=(
                        f"the xTB path refinement hit its {run.refinement_runs}-cycle ceiling "
                        "before the engine declared convergence, so no usable TS guess was "
                        "produced. A truncated path's highest frame is not a transition-state "
                        "guess (measured: it sits in the reactant's own basin and an OptTS started "
                        "from it never converges). Call again with a larger `refinement_runs` and "
                        f"rerun. Persistent run directory (truncated path kept): {run.run_dir}"
                    ),
                )
            return TsGuess_output_schema(
                is_success=False,
                path_kind="",
                refinement_termination=run.refinement_termination,
                message=(
                    f"the xTB path search did not produce a usable guess (termination="
                    f"{run.termination_reason}, returncode={run.returncode}). No fallback was "
                    "substituted: a failed xTB run is reported, not silently replaced by an "
                    f"interpolation. Persistent run directory: {run.run_dir}"
                ),
            )

        # 帧与 interpolate 同名，下游不必区分来源；能量标注单位（相对 kcal/mol）
        for frame in run.frames:
            comment = f"ts_guess xtb_path frame {frame.frame_index}"
            if frame.rel_energy_kcal is not None:
                comment += f" rel_energy_kcal={frame.rel_energy_kcal:.3f}"
            atomic_write_text(
                os.path.join(out_dir, f"img_{frame.frame_index:02d}.xyz"),
                _atoms_to_xyz_block(run.symbols, np.asarray(frame.positions, dtype=float), comment),
            )

        ts_path = os.path.join(out_dir, "ts_candidate_xtbpath.xyz")
        atomic_write_text(
            ts_path,
            _atoms_to_xyz_block(
                run.symbols, np.asarray(run.ts_candidate_positions, dtype=float),
                f"ts_guess xtb_path MTD TS candidate energy_eh={run.ts_candidate_energy_eh:.8f}",
            ),
        )

        # 距离表：与 interpolate 同一套监测对选择
        d_r = _dist_matrix(r_pos)
        d_p = _dist_matrix(p_pos)
        pairs = _select_watch_pairs(r_syms, d_r, d_p, user_input.watch_pairs)
        lines = [f"{'frame':>4}" + "".join(f"  {_pair_label(r_syms, pr):>12}" for pr in pairs)]
        for frame in run.frames:
            d_k = _dist_matrix(np.asarray(frame.positions, dtype=float))
            lines.append(
                f"{frame.frame_index:>4}" + "".join(f"  {d_k[i, j]:>12.4f}" for i, j in pairs)
            )
        distance_table = "\n".join(lines)

        return TsGuess_output_schema(
            is_success=True,
            path_kind="xtb_path",
            refinement_termination=run.refinement_termination,
            images_dir=out_dir,
            distance_table=distance_table,
            ts_candidate_index=None,
            ts_candidate_path=ts_path,
            message=(
                f"xTB metadynamics path search finished: {len(run.frames)} path frames "
                f"(img_00..img_{len(run.frames) - 1:02d}.xyz) plus a TS CANDIDATE. "
                "The candidate is the highest point sampled along the MTD path — it is a GUESS, "
                "not a saddle point and NOT verified; run mode='verify' with a frequency job to "
                "judge it. Metadynamics is stochastic: a rerun gives a different path, so the "
                f"whole run is kept for inspection at {run.run_dir}."
            ),
        )

    # ---------- mode=scan_prepare ----------

    def _scan_prepare(self, user_input: TsGuess_input_schema) -> TsGuess_output_schema:
        import numpy as np

        need = {"bond": 2, "angle": 3, "dihedral": 4}
        if not user_input.scans:
            raise ValueError("scan_prepare requires scans: at least one scanned coordinate")
        if user_input.engine == "orca" and len(user_input.scans) > 1:
            raise ValueError(
                "ORCA relaxed scans are 1D: pass exactly one scan entry. "
                "For a coupled two-coordinate scan use engine='gaussian'."
            )
        if not user_input.output_path:
            raise ValueError("scan_prepare requires output_path (the path to write the input file)")

        atoms = _load_xyz(user_input.input_path, user_input.input_text)
        syms = atoms.get_chemical_symbols()
        pos = np.asarray(atoms.get_positions(), dtype=float)
        n = len(syms)

        def _coord_current(coord_type: str, idx: list[int]) -> float:
            if coord_type == "bond":
                return float(np.linalg.norm(pos[idx[0]] - pos[idx[1]]))
            if coord_type == "angle":
                return _angle_deg(pos[idx[0]], pos[idx[1]], pos[idx[2]])
            return _dihedral_deg(pos[idx[0]], pos[idx[1]], pos[idx[2]], pos[idx[3]])

        specs = []
        start_mismatches: list[str] = []
        for raw in user_input.scans:
            coord_type = raw.get("coord_type") or "bond"
            if coord_type not in need:
                raise ValueError(f"coord_type must be one of bond/angle/dihedral, got: {coord_type}")
            atoms_list = raw.get("atoms") or []
            if len(atoms_list) != need[coord_type]:
                raise ValueError(
                    f"coord_type={coord_type} requires {need[coord_type]} atom indices, "
                    f"got {len(atoms_list)} (in {raw})"
                )
            steps = int(raw.get("scan_steps") or 0)
            if steps < 1:
                raise ValueError(f"scan_steps must be ≥ 1 (in {raw})")
            idx = [a - 1 for a in atoms_list]
            for a in idx:
                if not (0 <= a < n):
                    raise ValueError(
                        f"Scanned atom indices out of range: {atoms_list} (system has {n} atoms)"
                    )
            current = _coord_current(coord_type, idx)
            explicit_start = raw.get("scan_start")
            start = float(explicit_start) if explicit_start is not None else current
            if explicit_start is not None:
                # Gaussian modredundant 扫描从当前几何值出发只加增量；
                # scan_start 与真实起点不同只调整增量会静默扫错区间。
                tolerance = 0.005 if coord_type == "bond" else 0.5
                if abs(start - current) > tolerance:
                    start_mismatches.append(
                        f"{coord_type} {atoms_list}: requested scan_start={start} "
                        f"but the current geometry value is {current:.4f}"
                    )
            end = float(raw.get("scan_end") or 0.0)
            specs.append({
                "coord_type": coord_type,
                "idx": idx,
                "start": start,
                "end": end,
                "steps": steps,
                "step_size": (end - start) / steps,
            })

        if start_mismatches and user_input.engine == "gaussian":
            return TsGuess_output_schema(
                is_success=False,
                message=(
                    "start_geometry_mismatch: "
                    + "; ".join(start_mismatches)
                    + ". A Gaussian modredundant scan starts from the CURRENT geometry "
                    "value and only applies the increment — generate the target start "
                    "geometry first (e.g. a constrained optimization to the requested "
                    "start value) instead of merely adjusting scan_start."
                ),
            )

        method = user_input.method.strip()
        extra = user_input.extra_route.strip()
        coord_letter = {"bond": "B", "angle": "A", "dihedral": "D"}
        scan_labels = [
            f"{coord_letter[spec['coord_type']]} {' '.join(str(a + 1) for a in spec['idx'])}"
            f" from {spec['start']:.4f} to {spec['end']:.4f} "
            f"({spec['steps']} steps, {spec['step_size']:+.6f})"
            for spec in specs
        ]

        if user_input.engine == "gaussian":
            route = f"# opt=(modredundant,maxstep=10) {method}"
            if extra:
                route += f" {extra}"
            coord_lines = "\n".join(
                f"{s:<4} {p[0]:>14.8f} {p[1]:>14.8f} {p[2]:>14.8f}" for s, p in zip(syms, pos)
            )
            scan_block = "\n".join(
                f"{coord_letter[spec['coord_type']]} {' '.join(str(a + 1) for a in spec['idx'])} "
                f"S {spec['steps']} {spec['step_size']:.6f}"
                for spec in specs
            )
            content = "\n".join([
                f"%nprocshared={user_input.nprocs}",
                f"%chk={user_input.job_name}.chk",
                route,
                "",
                f"{user_input.job_name} scan generated by ts_guess",
                "",
                f"{user_input.charge} {user_input.spin}",
                coord_lines,
                "",
                scan_block,
                "",
                "",
            ])
            dim = "2D coupled" if len(specs) > 1 else "1D"
            run_hint = (
                f"Submit {user_input.output_path} with submit_compute_job (job_type='gaussian'); "
                f"afterwards parse the log with ts_guess mode='scan_parse' and extract a TS guess. "
                f"This is a {dim} scan over {len(specs)} coordinate(s) — cost grows with every additional "
                "scanned coordinate."
            )
        else:
            orca_method = _orca_keyword_method(method)
            header = f"! OPT {orca_method}"
            if extra:
                header += f" {extra}"
            spec = specs[0]
            idx0 = [a for a in spec["idx"]]  # ORCA 原子序号 0-based
            xyz_lines = "\n".join(
                f"{s:<3} {p[0]:>14.8f} {p[1]:>14.8f} {p[2]:>14.8f}" for s, p in zip(syms, pos)
            )
            blocks = [header, f"%pal nprocs {user_input.nprocs} end", "%geom"]
            blocks.append(
                f"    Scan {coord_letter[spec['coord_type']]} {' '.join(str(a) for a in idx0)} "
                f"= {spec['start']:.6f}, {spec['end']:.6f}, {spec['steps']} end"
            )
            blocks.append("end")
            if user_input.orca_blocks:
                blocks.append(user_input.orca_blocks.strip())
            blocks.extend(["", f"* xyz {user_input.charge} {user_input.spin}", xyz_lines, "*", ""])
            content = "\n".join(blocks)
            run_hint = (
                f"Submit {user_input.output_path} with submit_compute_job (job_type='orca'); "
                "afterwards parse the log with ts_guess mode='scan_parse' engine='orca' and extract a TS guess."
            )

        out_dir = os.path.dirname(os.path.abspath(user_input.output_path))
        os.makedirs(out_dir, exist_ok=True)
        atomic_write_text(user_input.output_path, content)

        return TsGuess_output_schema(
            is_success=True,
            input_file_path=user_input.output_path,
            run_hint=run_hint,
            message=(
                f"{user_input.engine} constrained-scan input written to {user_input.output_path}: "
                + "; ".join(scan_labels)
                + ". If you hand-edit the input: for Gaussian keep one blank line between the coordinate "
                "block and the ModRedundant B/A/D lines; each scanned coordinate takes exactly one S line "
                "(two S lines in the same job = a 2D grid scan, N×M points, not a 1D diagonal scan)."
            ),
        )

    # ---------- mode=scan_parse ----------

    def _scan_parse(self, user_input: TsGuess_input_schema) -> TsGuess_output_schema:
        import numpy as np

        if not user_input.log_path:
            raise ValueError("scan_parse requires log_path")
        log_exists = os.path.isfile(user_input.log_path)
        text = None
        if log_exists:
            with open(user_input.log_path, encoding="utf-8", errors="replace") as f:
                text = f.read()

        symbols: Optional[list[str]] = None
        ts_coords = None
        notes: list[str] = []
        candidate_source = ""

        if user_input.engine == "gaussian":
            if text is None:
                raise ValueError(f"Gaussian scan parsing requires the scan log file: {user_input.log_path}")
            energies_eh = _parse_gaussian_scan_summary(text)
            n_pts = len(energies_eh)
            e0 = energies_eh[0]
            rel_kcal = [(e - e0) * KCAL_PER_HARTREE for e in energies_eh]
            profile = analyze_scan_profile(rel_kcal)
            ts_index = profile["ts_index"]

            # TS 初猜几何：优先 cclib scancoords（与汇总表逐点对应），回退 Standard orientation 块
            try:
                import cclib

                data = cclib.io.ccread(user_input.log_path)
                scancoords = getattr(data, "scancoords", None) if data is not None else None
                atomnos = getattr(data, "atomnos", None) if data is not None else None
                if scancoords is not None and atomnos is not None and len(scancoords) == n_pts:
                    from cclib.parser.utils import PeriodicTable

                    pt = PeriodicTable()
                    symbols = [pt.element[int(z)] for z in atomnos]
                    ts_coords = np.asarray(scancoords[ts_index], dtype=float)
                    candidate_source = "gaussian_log:cclib_scancoords"
            except Exception as e:
                notes.append(f"cclib geometry extraction failed ({e}); falling back to Standard orientation parsing.")

            if ts_coords is None and 0 < ts_index < n_pts - 1:
                blocks = gaussian_frames.std_orientation_frames(text)
                if len(blocks) == n_pts:
                    # 块数与扫描点一一对应（每点恰一块）：峰值帧几何可靠可取
                    rows = blocks[ts_index]
                    from cclib.parser.utils import PeriodicTable

                    pt = PeriodicTable()
                    symbols = [pt.element[int(z)] for z, *_ in rows]
                    ts_coords = np.asarray([[x, y, z] for _, x, y, z in rows], dtype=float)
                    candidate_source = "gaussian_log:std_orientation"
                else:
                    # 块数与扫描点无法一一对应：严禁按块均分猜峰值帧、也严禁拿
                    # 末块顶替（与 ORCA _ScanStepsUngroupable 同口径，GH #G1）。
                    lines = [f"{'frame':>4}  {'rel. energy (kcal/mol)':>18}"]
                    for k, e in enumerate(rel_kcal):
                        lines.append(f"{k:>4}  {e:>18.4f}")
                    return TsGuess_output_schema(
                        is_success=True,
                        profile_table="\n".join(lines),
                        verdicts=[
                            *profile["verdicts"], *notes,
                            f"The log has {len(blocks)} 'Standard orientation' blocks for {n_pts} "
                            "scan points, so the blocks cannot be aligned to scan points one-to-one. "
                            "The peak-frame geometry was NOT derived by equal-split block division "
                            "and the last block was NOT substituted (GH #G1).",
                            "No TS-guess geometry was written. Re-parse with cclib-accessible scan "
                            "coordinates, or extract the peak geometry from the per-point output files.",
                        ],
                        barrier_kcal=None,  # 拒发候选时不报 barrier（G4）
                        candidate=None,
                        candidate_unavailable=True,
                        message=(
                            "Scan profile parsed, but the TS-candidate geometry is unavailable: the "
                            "'Standard orientation' blocks cannot be reliably mapped to scan points, "
                            "and no equal-split or last-frame substitution was applied."
                        ),
                    )
        else:
            # ORCA relaxed scan：sidecar（relaxscanact.dat 逐帧能量 + ts_scan.NNN.xyz
            # 逐帧几何）优先——能量最高帧往往不是末帧，.out 的 rfind 末帧会选错
            # TS 候选；.out 文本仅作无 sidecar 时的回退。
            try:
                sidecar = _parse_orca_relaxed_scan_sidecar(user_input.log_path)
            except _SidecarIncomplete as exc:
                # 本次产物的 sidecar 存在但峰值帧丢失/不可读：严禁拿 .out
                # 文本的末帧块顶替——candidate=null + candidate_unavailable。
                if exc.energies:
                    energies_eh = exc.energies
                    e0 = energies_eh[0]
                    rel_kcal = [(e - e0) * KCAL_PER_HARTREE for e in energies_eh]
                    profile = analyze_scan_profile(rel_kcal)
                    peak = profile["ts_index"]
                    lines = [f"{'frame':>4}  {'rel. energy (kcal/mol)':>18}"]
                    for k, e in enumerate(rel_kcal):
                        lines.append(f"{k:>4}  {e:>18.4f}")
                    return TsGuess_output_schema(
                        is_success=True,
                        profile_table="\n".join(lines),
                        verdicts=[
                            f"Scan sidecar is incomplete: {exc}",
                            f"The energy-maximum frame is {peak} (1-based {peak + 1}) but its "
                            "geometry is unavailable; the last frame was NOT substituted. "
                            "Re-run or recover the missing per-frame xyz before extracting a TS guess.",
                        ],
                        barrier_kcal=None,  # 拒发候选（峰值帧不可得）时不报 barrier（G4）
                        candidate=None,
                        candidate_unavailable=True,
                        message=(
                            "Scan profile parsed, but the TS-candidate geometry is unavailable: "
                            f"{exc}. The energy-maximum frame was not replaced by any other frame."
                        ),
                    )
                return TsGuess_output_schema(
                    is_success=True,
                    verdicts=[
                        f"Scan sidecar is incomplete: {exc}",
                        "No TS candidate could be derived; the log text was not used as a "
                        "substitute for the missing per-frame geometries.",
                    ],
                    candidate=None,
                    candidate_unavailable=True,
                    message=f"Scan sidecar is present but unusable: {exc}",
                )
            if sidecar is not None:
                energies_eh = sidecar["energies"]
                e0 = energies_eh[0]
                rel_kcal = [(e - e0) * KCAL_PER_HARTREE for e in energies_eh]
                profile = analyze_scan_profile(rel_kcal)
                ts_index = profile["ts_index"]
                frame_symbols, ts_coords = sidecar["frames"][ts_index]
                symbols = frame_symbols
                candidate_source = "orca_relaxed_scan_sidecar"
            elif text is not None:
                try:
                    steps = _parse_orca_scan(text)
                except _ScanStepsUngroupable as exc:
                    # 日志文本无法按扫描步分组（如缺 RELAXED SURFACE SCAN STEP 标记）：
                    # 不产候选——绝不把优化周期能量当扫描点、也绝不按块均分取几何。
                    return TsGuess_output_schema(
                        is_success=True,
                        verdicts=[
                            f"ORCA scan log text cannot be grouped into scan points: {exc}",
                            "No TS-guess geometry was derived from the log text: per-cycle single-point "
                            "energies were NOT misread as scan points and no equal-split frame heuristic "
                            "was applied. Re-run the scan or recover the relaxscanact.dat sidecar "
                            "(<job>.relaxscanact.dat + <job>.NNN.xyz) for exact per-frame energies/geometries.",
                        ],
                        candidate=None,
                        candidate_unavailable=True,
                        message=f"ORCA scan text parsing refused (candidate unavailable): {exc}",
                    )
                energies_eh = [s["energy_hartree"] for s in steps]
                step_geoms = [s["geom"] for s in steps]
                e0 = energies_eh[0]
                rel_kcal = [(e - e0) * KCAL_PER_HARTREE for e in energies_eh]
                profile = analyze_scan_profile(rel_kcal)
                ts_index = profile["ts_index"]
                # 能量最高帧（TS 候选）的几何 = 该扫描步收敛结构的最后一块直角坐标
                geom = step_geoms[ts_index]
                symbols = [g[0] for g in geom]
                ts_coords = np.asarray([[g[1], g[2], g[3]] for g in geom], dtype=float)
                candidate_source = "orca_log_text"
            else:
                raise ValueError(
                    f"Cannot parse the ORCA scan: {user_input.log_path} does not exist and no "
                    "relaxscanact.dat sidecar was found next to it. ORCA relaxed scans write "
                    "<job>.relaxscanact.dat and <job>.NNN.xyz — point log_path at the job name "
                    "(e.g. .../ts_scan.out even if the .out file is absent) to use them."
                )

        # 内部峰判定：TS 候选只在存在内部能量极大（0 < i < n-1）时成立。
        # 单调（升或降）或极值落在扫描边界的剖面没有鞍点证据——端点"最高"
        # 只是扫描范围/坐标选择的假象，升/降在这里语义完全同构：都不产出
        # TS-guess，防止把解离/无垒扫描的端点帧误当 TS 初猜去提交 OptTS。
        has_internal_peak = 0 < ts_index < len(rel_kcal) - 1

        # 剖面文本表
        lines = [f"{'frame':>4}  {'rel. energy (kcal/mol)':>18}"]
        for k, e in enumerate(rel_kcal):
            marker = "  <- internal peak (TS guess)" if has_internal_peak and k == ts_index else ""
            lines.append(f"{k:>4}  {e:>18.4f}{marker}")
        profile_table = "\n".join(lines)

        # 候选来源注释只在真正发出 TS-guess（内部峰存在）时追加；无内部峰/拒发时
        # 不得声称 "TS-guess geometry is ..."（G4，避免与拒发 verdict 自相矛盾）。
        if has_internal_peak:
            if candidate_source == "orca_relaxed_scan_sidecar":
                notes.append(
                    "ORCA relaxed-scan sidecar used (relaxscanact.dat + per-frame xyz): "
                    f"TS-guess geometry is the energy-maximum frame {ts_index} (1-based {ts_index + 1}), not the last frame."
                )
            elif candidate_source == "orca_log_text":
                notes.append(
                    f"ORCA scan text fallback grouped {len(rel_kcal)} relaxed-scan steps by their "
                    "'RELAXED SURFACE SCAN STEP' markers and used each step's converged (last) "
                    "single-point energy, so the TS-guess geometry is the energy-maximum frame "
                    f"{ts_index} (1-based {ts_index + 1}), not the last frame."
                )

        verdicts = list(profile["verdicts"]) + notes
        if not has_internal_peak:
            verdicts.append(
                "The scan has no internal energy peak (the maximum sits on a scan endpoint or the "
                "profile is monotonic): an endpoint maximum is NOT a TS candidate — do not submit a TS "
                "optimization from it. Re-choose the reaction coordinate, extend/refine the scan, or use a "
                "two-coordinate coupled scan (scan_prepare with two scan entries, Gaussian) to locate a barrier."
            )

        ts_path = ""
        ts_candidate_index = None
        if has_internal_peak:
            ts_candidate_index = ts_index
            ts_path = (
                user_input.ts_candidate_path
                or os.path.splitext(user_input.log_path)[0] + "_ts_guess.xyz"
            )
            out_dir = os.path.dirname(os.path.abspath(ts_path))
            os.makedirs(out_dir, exist_ok=True)
            atomic_write_text(ts_path, _atoms_to_xyz_block(
                symbols, ts_coords,
                comment=f"ts_guess scan_parse TS candidate frame={ts_index} from {os.path.basename(user_input.log_path)}",
            ))

        if has_internal_peak:
            message = (
                f"Scan parsing complete: {len(rel_kcal)} points, barrier (highest point − first point) {profile['barrier_kcal']:.2f} kcal/mol, "
                f"internal energy maximum at frame {ts_index}; TS-guess geometry written to {ts_path}. "
                "Recommended next step: submit a TS optimization with opt=(ts,calcfc,noeigentest) plus a frequency calculation from this geometry, "
                "then verify with ts_guess mode='verify'."
            )
        else:
            message = (
                f"Scan parsing complete: {len(rel_kcal)} points; NO internal energy peak found — the "
                "highest point sits on a scan endpoint (an endpoint maximum is NOT a TS candidate; do "
                "not submit a TS optimization from it), so no TS-guess geometry was written. Choose a "
                "different/extra scan coordinate before hunting a TS."
            )
        candidate = None
        if has_internal_peak and ts_path:
            candidate = {
                "scan_index": ts_candidate_index,
                "energy": energies_eh[ts_index],
                "geometry_ref": ts_path,
                "source": candidate_source,
            }
        return TsGuess_output_schema(
            is_success=True,
            profile_table=profile_table,
            verdicts=verdicts,
            # G4：只有存在内部峰（确实发出 TS 候选）时才填 barrier；端点极大/单调
            # 剖面（无内部峰）的 "最高点−首点" 不是能垒，置 None。
            barrier_kcal=(None if not has_internal_peak else round(profile["barrier_kcal"], 4)),
            ts_candidate_index=ts_candidate_index,
            ts_candidate_path=ts_path,
            candidate=candidate,
            message=message,
        )

    # ---------- mode=verify ----------

    def _verify(self, user_input: TsGuess_input_schema) -> TsGuess_output_schema:
        if not user_input.freq_log:
            raise ValueError("verify requires freq_log")
        if not os.path.isfile(user_input.freq_log):
            raise ValueError(f"Frequency log does not exist: {user_input.freq_log}")

        freq = _parse_freq_log(user_input.freq_log, user_input.engine)
        vibfreqs = freq["vibfreqs"]
        imag = [f for f in vibfreqs if f < 0]
        n_imag = len(imag)
        checks: list[str] = []

        irc_end_a_path = ""
        irc_end_b_path = ""
        imag_mode_aligned: Optional[bool] = None
        imag_mode_alignment = ""

        def _record_mode_alignment() -> dict[str, Any]:
            nonlocal imag_mode_aligned, imag_mode_alignment
            assessment = _assess_imag_mode_alignment(
                vibfreqs,
                freq.get("vibdisps"),
                user_input.watch_pairs,
                symbols=freq.get("symbols"),
                positions=freq.get("positions"),
                charge=user_input.charge,
            )
            imag_mode_aligned = assessment["aligned"]
            imag_mode_alignment = assessment["message"]
            checks.append(assessment["message"])
            checks.extend(assessment.get("details") or [])
            return assessment

        if user_input.strict:
            if not freq["converged"]:
                checks.append("The frequency job did not converge normally; the first-order saddle-point premise cannot be established.")
                verdict = "inconclusive: the frequency job did not converge normally; the available material is insufficient for a strict judgement."
            elif n_imag != 1:
                if n_imag == 0:
                    checks.append("A normally terminated frequency job has no imaginary frequency: the structure is a minimum, not a first-order saddle point.")
                else:
                    checks.append(
                        f"A normally terminated frequency job has {n_imag} imaginary frequencies "
                        f"({', '.join(f'{f:.1f}' for f in imag)} cm⁻¹): the structure is a higher-order saddle point."
                    )
                verdict = "fail: the strict check requires exactly one imaginary frequency."
            else:
                checks.append(f"Exactly 1 imaginary frequency ({imag[0]:.1f} cm⁻¹): the first-order saddle-point premise holds.")
                mode = _record_mode_alignment()
                if mode["status"] == "missing":
                    verdict = (
                        "inconclusive: the frequency log lacks normal-mode displacements; cannot check the imaginary-frequency direction."
                    )
                elif mode["status"] == "undecidable":
                    verdict = (
                        "inconclusive: the imaginary mode is dominated by non-bonded-pair "
                        "(torsion/angle) motion; pair-distance alignment cannot judge its direction."
                    )
                elif mode["status"] == "misaligned":
                    verdict = "fail: the imaginary mode is inconsistent with the declared reaction coordinate."
                else:
                    verdict, info = self._strict_path_verdict(user_input, freq, checks)
                    if info is not None:
                        irc_end_a_path = info["path_a"]
                        irc_end_b_path = info["path_b"]
        else:
            if not freq["converged"]:
                checks.append("The frequency job did not converge normally; cannot judge the TS candidate from it.")
                verdict = "inconclusive: the frequency job did not converge normally."
            elif n_imag == 0:
                checks.append("No imaginary frequency: the structure is a minimum, not like a first-order saddle point.")
                verdict = "unlikely: no imaginary frequency; the structure looks more like a minimum."
            elif n_imag > 1:
                checks.append(
                    f"{n_imag} imaginary frequencies ({', '.join(f'{f:.1f}' for f in imag)} cm⁻¹): "
                    "the structure looks more like a higher-order saddle point."
                )
                verdict = "unlikely: multiple imaginary frequencies; the structure looks more like a higher-order saddle point."
            else:
                checks.append(
                    f"Exactly 1 imaginary frequency ({imag[0]:.1f} cm⁻¹): acceptable as a first-order saddle-point candidate, but this is not sufficient proof."
                )
                _record_mode_alignment()
                irc_ok: Optional[bool] = None
                info = self._extract_irc_endpoints(user_input, checks, require_two_sides=False)
                if info is not None:
                    irc_end_a_path = info["path_a"]
                    irc_end_b_path = info["path_b"]
                    irc_ok = self._check_irc_connectivity(
                        user_input, info["end_a"], info["end_b"], checks,
                    )

                if user_input.irc_log and info is None:
                    verdict = "inconclusive: IRC was provided, but comparable endpoint geometries could not be obtained."
                elif irc_ok is False:
                    verdict = "unlikely: the rough connectivity of the IRC endpoints is inconsistent with the expected structures."
                elif irc_ok == "inconclusive":
                    verdict = (
                        "inconclusive: the IRC endpoints could not be compared with the expected "
                        "structures (atom order or element mismatch); connectivity is undecidable."
                    )
                else:
                    reason = "one imaginary frequency" + ("; rough IRC connectivity consistent" if irc_ok else "")
                    verdict = f"candidate: {reason}; advisory only for the agent's next step, not a strict proof of the TS."

        return TsGuess_output_schema(
            is_success=True,
            verdict=verdict,
            n_imag=n_imag,
            imag_freqs=[round(f, 2) for f in imag],
            checks=checks,
            irc_end_a_path=irc_end_a_path,
            irc_end_b_path=irc_end_b_path,
            imag_mode_aligned=imag_mode_aligned,
            imag_mode_alignment=imag_mode_alignment,
            message=f"TS verification complete: {verdict}",
        )

    @staticmethod
    def _extract_irc_endpoints(user_input: TsGuess_input_schema, checks: list[str],
                               require_two_sides: bool) -> Optional[dict]:
        """提取有坐标的 IRC 外侧帧；strict 时必须分别来自 rx<0 与 rx>0。"""
        if not user_input.irc_log:
            checks.append("No IRC log provided.")
            return None
        if not os.path.isfile(user_input.irc_log):
            raise ValueError(f"IRC log does not exist: {user_input.irc_log}")

        if user_input.engine == "orca":
            return TsGuess._extract_orca_irc_endpoints(user_input, checks, require_two_sides)

        from cloudra.tools.core import gaussian_frames

        try:
            frames, meta = gaussian_frames.extract_irc(user_input.irc_log)
        except Exception as e:
            checks.append(f"IRC endpoint extraction failed: {e}")
            return None

        valid = [frame for frame in frames if frame.xyz.strip()]
        if require_two_sides:
            negative = [
                frame for frame in valid
                if frame.reaction_coordinate is not None and frame.reaction_coordinate < 0
            ]
            positive = [
                frame for frame in valid
                if frame.reaction_coordinate is not None and frame.reaction_coordinate > 0
            ]
            if not negative or not positive:
                checks.append("The IRC log does not provide valid coordinate frames on both rx<0 and rx>0 sides.")
                return None
            end_a = min(negative, key=lambda frame: frame.reaction_coordinate)
            end_b = max(positive, key=lambda frame: frame.reaction_coordinate)
        else:
            if len(valid) < 2:
                checks.append("Fewer than two path frames with coordinates in the IRC log.")
                return None
            end_a, end_b = valid[0], valid[-1]

        out_dir = user_input.output_dir or os.path.splitext(user_input.freq_log)[0] + "_verify"
        os.makedirs(out_dir, exist_ok=True)
        path_a = os.path.join(out_dir, "irc_end_a.xyz")
        path_b = os.path.join(out_dir, "irc_end_b.xyz")
        atomic_write_text(path_a, end_a.xyz.rstrip() + "\n")
        atomic_write_text(path_b, end_b.xyz.rstrip() + "\n")
        checks.append(
            f"IRC outer frames extracted: irc_end_a.xyz (rx={end_a.reaction_coordinate}), "
            f"irc_end_b.xyz (rx={end_b.reaction_coordinate}) -> {out_dir}"
        )
        if require_two_sides and not (
            meta.get("forward_converged", False) and meta.get("backward_converged", False)
        ):
            checks.append("The IRC did not reach a minimum on at least one side; strict only checks partial endpoint direction, so an incomplete run is not treated as failure.")
        return {
            "end_a": end_a,
            "end_b": end_b,
            "frames": frames,
            "meta": meta,
            "path_a": path_a,
            "path_b": path_b,
        }

    @staticmethod
    def _extract_orca_irc_endpoints(user_input: TsGuess_input_schema, checks: list[str],
                                    require_two_sides: bool) -> Optional[dict]:
        """ORCA IRC 端点：复用 orca_frames 的 final endpoint / F-B trajectory
        读取（解析规则不在这里复制）。forward/backward 是轨迹方向标签，
        不自动映射 reactant/product。收敛与否只记录、绝不做闸门：与 Gaussian
        通道同口径，每侧取最外侧可用几何（未收敛方向的轨迹末帧同样是合法的
        部分端点），方向是否成立交给 strict 的几何区间证明判定。"""
        from types import SimpleNamespace

        from cloudra.tools.core import orca_frames

        endpoints = orca_frames.extract_irc_endpoints(user_input.irc_log)
        forward, backward = endpoints["forward"], endpoints["backward"]
        for label, info in (("forward", forward), ("backward", backward)):
            converged = info.get("converged")
            if converged is False:
                checks.append(
                    f"The ORCA IRC {label} direction terminated WITHOUT converging; "
                    "strict only checks partial endpoint direction, so the trajectory's "
                    "outermost frame is still used as that side's partial endpoint."
                )
            elif converged:
                checks.append(
                    f"The ORCA IRC {label} direction converged; a short converged path "
                    "needs no padding to a fixed point count."
                )

        xyz_a = orca_frames.read_endpoint_geometry(forward)
        xyz_b = orca_frames.read_endpoint_geometry(backward)
        if xyz_a is None or xyz_b is None:
            checks.append(
                "ORCA IRC endpoint geometries are not available on both sides "
                "(final endpoint files or F/B trajectories are missing); one side's "
                "geometry is never reused as the other side."
            )
            return None

        end_a = SimpleNamespace(xyz=xyz_a, reaction_coordinate=None)
        end_b = SimpleNamespace(xyz=xyz_b, reaction_coordinate=None)
        out_dir = user_input.output_dir or os.path.splitext(user_input.freq_log)[0] + "_verify"
        os.makedirs(out_dir, exist_ok=True)
        path_a = os.path.join(out_dir, "irc_end_a.xyz")
        path_b = os.path.join(out_dir, "irc_end_b.xyz")
        atomic_write_text(path_a, xyz_a.rstrip() + "\n")
        atomic_write_text(path_b, xyz_b.rstrip() + "\n")
        checks.append(
            "ORCA IRC endpoints extracted (forward/backward are trajectory directions, "
            f"NOT reactant/product assignments): irc_end_a.xyz ({forward.get('origin')}), "
            f"irc_end_b.xyz ({backward.get('origin')}) -> {out_dir}"
        )
        return {
            "end_a": end_a,
            "end_b": end_b,
            "frames": [end_a, end_b],
            "meta": {
                "forward_converged": bool(forward.get("converged")),
                "backward_converged": bool(backward.get("converged")),
            },
            "path_a": path_a,
            "path_b": path_b,
        }

    def _strict_path_verdict(self, user_input: TsGuess_input_schema, freq: dict,
                             checks: list[str]) -> tuple[str, Optional[dict]]:
        """证明两个部分 IRC 端点分别位于 TS 与两个端点参考几何之间。"""
        import ase.io
        import numpy as np

        def _non_pass(reason: str) -> str:
            # 材料不足 / 未通过时追加可操作补救提示（仅文本，不改 verdict 取值）。
            checks.append(_IRC_TRUNCATION_REMEDY)
            return f"{reason} {_IRC_TRUNCATION_REMEDY}"

        has_intermediate_a = bool(user_input.reactant_path or user_input.reactant_text)
        has_intermediate_b = bool(user_input.product_path or user_input.product_text)
        if not (has_intermediate_a and has_intermediate_b):
            checks.append("strict requires reference structures for both endpoint species.")
            return _non_pass("inconclusive: missing the two endpoint reference structures."), None

        info = self._extract_irc_endpoints(user_input, checks, require_two_sides=True)
        if info is None:
            return _non_pass("inconclusive: no usable bidirectional IRC endpoints."), None

        try:
            end_a_atoms = ase.io.read(StringIO(info["end_a"].xyz), format="xyz")
            end_b_atoms = ase.io.read(StringIO(info["end_b"].xyz), format="xyz")
            intermediate_a = _load_xyz(user_input.reactant_path, user_input.reactant_text)
            intermediate_b = _load_xyz(user_input.product_path, user_input.product_text)
        except Exception as e:
            checks.append(f"Endpoint or optimized-intermediate structures could not be parsed: {e}")
            return "inconclusive: the structure material could not be parsed.", info

        ts_symbols = freq.get("symbols")
        ts_positions = freq.get("positions")
        if ts_symbols is None or ts_positions is None:
            zero_frames = [
                frame for frame in info["frames"]
                if frame.xyz.strip() and frame.reaction_coordinate == 0.0
            ]
            if zero_frames:
                ts_atoms = ase.io.read(StringIO(zero_frames[-1].xyz), format="xyz")
                ts_symbols = ts_atoms.get_chemical_symbols()
                ts_positions = np.asarray(ts_atoms.get_positions(), dtype=float)
                checks.append("The frequency log gave no TS geometry; using the IRC rx=0 frame instead.")
            else:
                checks.append("Neither the frequency log nor the IRC provides a usable TS geometry.")
                return _non_pass("inconclusive: missing TS geometry."), info

        # 原子对应：元素多重集必须一致（原子数不等进不了这一层），但不要求
        # 原子序相同——任意原子序的几何经距离指纹 + Hungarian 指派重排进
        # TS 坐标序（重排过的输入不再是障碍，irc_path 唯一实现）。
        endpoint_geometries = [
            (end_a_atoms.get_chemical_symbols(), np.asarray(end_a_atoms.get_positions(), dtype=float)),
            (end_b_atoms.get_chemical_symbols(), np.asarray(end_b_atoms.get_positions(), dtype=float)),
            (intermediate_a.get_chemical_symbols(), np.asarray(intermediate_a.get_positions(), dtype=float)),
            (intermediate_b.get_chemical_symbols(), np.asarray(intermediate_b.get_positions(), dtype=float)),
        ]
        assignment = _prove_irc_endpoint_direction(
            list(ts_symbols), np.asarray(ts_positions, dtype=float),
            endpoint_geometries[0], endpoint_geometries[1],
            endpoint_geometries[2], endpoint_geometries[3],
            user_input.watch_pairs, user_input.charge,
        )
        for label, aligned in zip(
            ("IRC endpoint A", "IRC endpoint B", "intermediate A", "intermediate B"),
            assignment.get("aligned_positions", []),
        ):
            checks.append(f"{label} aligned to TS atom order (distance-matrix geometry recorded).")
        if not assignment.get("is_decidable") and not assignment.get("details"):
            return "inconclusive: the structures could not be aligned.", info
        checks.extend(assignment["details"])

        # 唯一自动通过通道：几何区间证明——要求两条外侧帧各落在 TS 与配对
        # 参考几何之间。仅凭 XYZ 几何接近不能证明端点优化曾经收敛，也不能证明
        # 该结构确实由对应 IRC 外侧帧优化得到；这类证据不足时应补做优化后重试。
        if assignment["is_decidable"] and assignment["is_match"]:
            mapping = "direct pairing" if assignment["assignment"] == "direct" else "pairing after swapping sides"
            checks.append(f"{mapping} holds: both IRC outer frames lie between the TS and the corresponding endpoint reference geometries.")
            n_warnings = len(assignment.get("warnings", []))
            warning_note = (
                f" ({n_warnings} weak-contact warning(s): hydrogen-bond/non-covalent "
                "pairs the IRC need not preserve)"
                if n_warnings else ""
            )
            return (
                "pass: the bidirectional path of the partial IRC is consistent with the two endpoint reference geometries"
                + warning_note
                + "; this conclusion only proves path direction and does not make the TS absolutely correct in every chemical sense.",
                info,
            )
        if not assignment["is_decidable"]:
            checks.append("The selected atom pairs are insufficient to judge the direction of the IRC endpoints relative to the TS and the intermediates.")
            return _non_pass("inconclusive: missing geometric changes large enough to judge direction."), info
        if not assignment["is_match"]:
            checks.append("At least one IRC outer frame does not lie between the TS and any pairable endpoint reference geometry.")
            return _non_pass("fail: the path direction of the partial IRC is inconsistent with the endpoint reference geometries."), info

    @staticmethod
    def _check_irc_connectivity(user_input: TsGuess_input_schema, end_a, end_b,
                                checks: list[str]) -> "bool | str | None":
        """比较 IRC 两端点与预期反应物/产物的成键集合（rdDetermineBonds 主通道）。

        返回 True / False / "inconclusive" / None：
        - None：未提供预期结构，只报告成键表（不判连通性）；
        - "inconclusive"：端点或预期结构的原子序/元素不一致，连通性不可判
          （绝不静默跳过成 candidate）；
        - 键集差异按**预期结构侧**距离分级：超出 DISTANCE_CONNECTIVITY_FACTOR×共价半径和的弱接触
          （氢键/非键接触）差异只记 warning 不判负；共价差异判负。
        """
        import ase.io
        import numpy as np

        def frame_atoms(frame):
            return ase.io.read(StringIO(frame.xyz), format="xyz")

        def perceive(atoms) -> set[tuple[int, int]]:
            return set(_perceive_bonds(
                atoms.get_chemical_symbols(),
                [list(p) for p in atoms.get_positions()],
                user_input.charge,
            )[0])

        atoms_a = frame_atoms(end_a)
        atoms_b = frame_atoms(end_b)
        syms = atoms_a.get_chemical_symbols()
        if atoms_b.get_chemical_symbols() != syms:
            checks.append(
                "The two IRC endpoint frames differ in atom order or elements; "
                "connectivity is undecidable."
            )
            return "inconclusive"
        bonds_a = perceive(atoms_a)
        bonds_b = perceive(atoms_b)

        def bond_table(name, bonds):
            if bonds:
                return f"{name} bonds: " + ", ".join(_pair_label(syms, pr) for pr in sorted(bonds))
            return f"{name} bonds: (none)"

        if not (user_input.reactant_path or user_input.reactant_text) and \
           not (user_input.product_path or user_input.product_text):
            checks.append(
                "No expected reactant/product provided; reporting IRC endpoint bond tables only: "
                + bond_table("Endpoint A", bonds_a) + "; " + bond_table("Endpoint B", bonds_b)
            )
            return None

        r_atoms = _load_xyz(user_input.reactant_path, user_input.reactant_text)
        p_atoms = _load_xyz(user_input.product_path, user_input.product_text)
        if r_atoms.get_chemical_symbols() != syms or p_atoms.get_chemical_symbols() != syms:
            checks.append(
                "The expected reactant/product atom order or elements differ from the IRC job; "
                "the connectivity check is undecidable."
            )
            return "inconclusive"
        bonds_r = perceive(r_atoms)
        bonds_p = perceive(p_atoms)
        exp_pos = {"reactant": r_atoms.get_positions(), "product": p_atoms.get_positions()}

        def split_diff(end_bonds, exp_name, exp_bonds):
            """键集差异 → (共价差异, 弱接触差异)：按预期结构侧距离分级。"""
            covalent: list[tuple[int, int]] = []
            weak: list[tuple[int, int]] = []
            pos = exp_pos[exp_name]
            for pair in sorted(set(end_bonds) ^ set(exp_bonds)):
                limit = _DISTANCE_CONNECTIVITY_FACTOR * (
                    _COVALENT_RADII.get(syms[pair[0]], 1.2)
                    + _COVALENT_RADII.get(syms[pair[1]], 1.2)
                )
                d = float(np.linalg.norm(pos[pair[0]] - pos[pair[1]]))
                (weak if d > limit else covalent).append(pair)
            return covalent, weak

        # 两种端点↔预期指派，按共价差异键总数取小者（弱接触不参与指派计分）
        direct = (
            len(split_diff(bonds_a, "reactant", bonds_r)[0])
            + len(split_diff(bonds_b, "product", bonds_p)[0])
        )
        swapped = (
            len(split_diff(bonds_a, "product", bonds_p)[0])
            + len(split_diff(bonds_b, "reactant", bonds_r)[0])
        )
        if swapped < direct:
            assign = [("Endpoint A", bonds_a, "product", bonds_p), ("Endpoint B", bonds_b, "reactant", bonds_r)]
        else:
            assign = [("Endpoint A", bonds_a, "reactant", bonds_r), ("Endpoint B", bonds_b, "product", bonds_p)]

        diff_lines: list[str] = []
        warning_lines: list[str] = []
        for end_name, end_bonds, exp_name, exp_bonds in assign:
            covalent, weak = split_diff(end_bonds, exp_name, exp_bonds)
            if covalent:
                diff_lines.append(
                    f"{end_name} vs {exp_name} (covalent differences: "
                    + ", ".join(_pair_label(syms, pr) for pr in covalent) + ")"
                )
            if weak:
                warning_lines.append(
                    f"{end_name} vs {exp_name} (weak-contact differences: "
                    + ", ".join(_pair_label(syms, pr) for pr in weak) + ")"
                )

        if diff_lines:
            checks.append(
                "IRC endpoints' connectivity is inconsistent with the expected reactant/product "
                "(covalent bond-set differences): " + "; ".join(diff_lines)
            )
            return False
        for line in warning_lines:
            checks.append(
                "[warning] weak-contact (H-bond/non-covalent at the expected minimum) bond-set "
                "difference, not counted as failure: " + line
            )
        checks.append(
            "IRC endpoints' connectivity is consistent with the expected reactant/product: "
            + "; ".join(f"{end} ↔ {exp}" for end, _, exp, _ in assign)
        )
        return True


def get_class():
    return TsGuess


def is_compute_entry_call(arguments: dict[str, Any]) -> bool:
    """Phase-3 门槛谓词：interpolate/scan_prepare 会真正拉起计算（xtb/CREST），
    scan_parse/verify 只是读已有日志，不算计算入口。"""
    return (arguments or {}).get("mode") in {"interpolate", "scan_prepare"}


def derive_delivery_changes(
    *,
    current: dict[str, Any],
    role: str,
    arguments: dict[str, Any],
    result: dict[str, Any],
) -> dict[str, Any]:
    """DAG evidence derivation owned by this tool; kept out of DagController.

    ``ts_guess`` results are advisory by design: they may add an advisory
    source, and only a strict endpoint-direction check can set a derived flag.
    """
    advisory = list(current.get("advisory_sources") or [])
    if "ts_guess" not in advisory:
        advisory.append("ts_guess")
    changes: dict[str, Any] = {"advisory_sources": advisory}
    if (
        role == "endpoint_direction_check"
        and arguments.get("strict") is True
        and str(result.get("verdict") or "").startswith("pass")
    ):
        changes["endpoint_direction_consistent"] = True
    return changes
