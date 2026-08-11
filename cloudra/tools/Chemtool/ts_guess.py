"""过渡态初猜工作流工具：插值路径生成 / 约束扫描输入生成 / 扫描日志解析 / TS 候选检查。

工具自身不执行任何量化计算：坐标与输入文件一律落盘，上下文只回数值表、判定与路径。
正则解析全部封装在本模块内部，agent 无需啃日志格式。

默认 verify 只给 agent 提供方向建议；strict verify 只证明部分 IRC 的行进方向与两侧优化
中间体一致，不宣称一个 TS 因此“绝对正确”。
"""

from __future__ import annotations

import os
import re
from io import StringIO
from typing import Any, Literal, Optional, Sequence

from pydantic import Field

from cloudra.base.session_class import Session
from cloudra.base.tools_class import Tool, input_schema, output_schema
from cloudra.persistence.fs_utils import atomic_write_text
from cloudra.tools.Chemtool.internal_coordinates import (
    _COVALENT_RADII,
    _angle_deg,
    _dihedral_deg,
)

KCAL_PER_HARTREE = 627.5095
_STRICT_PAIR_DELTA_MIN_ANG = 0.15
_STRICT_INTERVAL_TOL_ANG = 0.10
_STRICT_MAX_AUTO_PAIRS = 5
_STRICT_PAIR_EPS_ANG = 1e-8

description = (
    "过渡态（TS）初猜工作流：四个子功能由 mode 区分。"
    "interpolate：由反应物/产物 xyz 做线性或 IDPP 插值生成 NEB 候选路径图像（自动对齐、"
    "支持 atom_map 原子重排、距离监测表与 TS 候选帧判定）；"
    "scan_prepare：生成 Gaussian/ORCA 约束扫描输入文件（键长/键角/二面角，modredundant 或 %geom Scan）；"
    "scan_parse：解析扫描日志，给出相对能量剖面表、势垒、单调性/不连续/边界极值/多峰判定，"
    "并提取能量最高点几何作为 TS 初猜 xyz；"
    "verify：默认以频率与 IRC 端点粗略连通性给出 candidate/unlikely/inconclusive 建议；"
    "strict=True 时，要求一个虚频、双向 IRC 有效端点和两个优化中间体，并检查每个部分 IRC 端点"
    "是否处于 TS 与对应中间体之间，给出限定于路径方向一致性的 pass/fail/inconclusive。"
    "本工具不做任何量化计算，只生成输入、解析输出并给出判定；计算用 submit_compute_job 提交。"
    "坐标不进上下文，只回数值表、判定与文件路径。"
)


class TsGuess_input_schema(input_schema):
    mode: Literal["interpolate", "scan_prepare", "scan_parse", "verify"] = Field(
        description="子功能：interpolate（插值路径）、scan_prepare（扫描输入生成）、"
                    "scan_parse（扫描日志解析判定）、verify（频率+IRC 验证判定）。"
    )

    # ---------- interpolate ----------
    reactant_path: Optional[str] = Field(
        default=None,
        description="反应物 xyz 文件路径；strict verify 中表示一侧端点优化所得中间体。",
    )
    reactant_text: Optional[str] = Field(
        default=None,
        description="反应物 xyz 文本；strict verify 中表示一侧端点优化所得中间体。提供 path 时优先。",
    )
    product_path: Optional[str] = Field(
        default=None,
        description="产物 xyz 文件路径；strict verify 中表示另一侧端点优化所得中间体。",
    )
    product_text: Optional[str] = Field(
        default=None,
        description="产物 xyz 文本；strict verify 中表示另一侧端点优化所得中间体。提供 path 时优先。",
    )
    n_images: int = Field(default=10, description="interpolate：总图像数（含两端），≥2。")
    interp_method: Literal["idpp", "linear"] = Field(
        default="idpp", description="interpolate：插值方法。idpp 按 Smidtstrup 2014 对图像间对距离弛豫；linear 为线性插值。"
    )
    atom_map: list[int] = Field(
        default_factory=list,
        description="interpolate：1-based 原子映射，产物第 k 个原子对应反应物第 atom_map[k-1] 个原子。"
                    "缺省为恒等映射；必须是 1..N 的合法排列且对应元素一致。",
    )
    watch_pairs: list[list[int]] = Field(
        default_factory=list,
        description="interpolate：距离监测原子对；strict verify：方向证明所用原子对。均为 1-based，"
                    "缺省自动选取 TS 与中间体之间距离变化最大的前 5 对。",
    )
    output_dir: Optional[str] = Field(
        default=None,
        description="interpolate：图像输出目录（缺省 ./ts_interp/）；verify：IRC 端点落盘目录（缺省 <freq_log_stem>_verify/）。",
    )

    # ---------- scan_prepare ----------
    input_path: Optional[str] = Field(default=None, description="scan_prepare：输入结构文件路径（xyz）。")
    input_text: Optional[str] = Field(default=None, description="scan_prepare：输入结构 xyz 文本。")
    engine: Literal["gaussian", "orca"] = Field(default="gaussian", description="目标量化程序。")
    coord_type: Literal["bond", "angle", "dihedral"] = Field(default="bond", description="扫描坐标类型。")
    atoms: list[int] = Field(
        default_factory=list, description="扫描坐标原子序号（1-based，bond/angle/dihedral 分别 2/3/4 个）。"
    )
    scan_start: Optional[float] = Field(default=None, description="扫描起点值（Å 或度）。缺省取当前几何值。")
    scan_end: float = Field(default=0.0, description="扫描终点值（Å 或度）。")
    scan_steps: int = Field(default=10, description="扫描步数。")
    method: str = Field(default="b3lyp/def2svp", description="方法/基组，如 'b3lyp/def2svp'。")
    charge: int = Field(default=0, description="体系总电荷。")
    spin: int = Field(default=1, description="自旋多重度（2S+1）。")
    extra_route: str = Field(default="", description="附加路由关键字（如 'scrf=(solvent=water)'）。")
    nprocs: int = Field(default=4, description="并行核数（Gaussian %nprocshared / ORCA %pal）。")
    output_path: Optional[str] = Field(default=None, description="scan_prepare：输入文件写入路径（gjf/inp，必填）。")
    job_name: str = Field(default="scan", description="作业名（chk 文件与标题用）。")

    # ---------- scan_parse ----------
    log_path: Optional[str] = Field(default=None, description="scan_parse：扫描日志文件路径。")
    ts_candidate_path: Optional[str] = Field(
        default=None, description="scan_parse：TS 初猜 xyz 写入路径（缺省 <log_stem>_ts_guess.xyz）。"
    )

    # ---------- verify ----------
    freq_log: Optional[str] = Field(default=None, description="verify：频率计算日志路径。")
    irc_log: Optional[str] = Field(
        default=None,
        description="verify：IRC 日志路径；默认模式可选，strict 模式必需并要求 rx<0/rx>0 两侧有效帧。",
    )
    strict: bool = Field(
        default=False,
        description="仅 verify：启用无状态的路径方向一致性证明。允许 IRC 未走到极小点，但要求双向有效端点、"
                    "TS 几何和两侧端点优化所得中间体。",
    )


class TsGuess_output_schema(output_schema):
    is_success: bool = Field(description="操作是否成功")
    message: str = Field(default="", description="状态或错误信息")

    # interpolate
    images_dir: str = Field(default="", description="interpolate：图像目录路径")
    distance_table: str = Field(default="", description="interpolate：逐帧距离文本表")
    ts_candidate_index: Optional[int] = Field(default=None, description="TS 候选帧序号（0-based）")
    # scan_parse 也复用 ts_candidate_path
    ts_candidate_path: str = Field(default="", description="TS 初猜 xyz 路径")

    # scan_prepare
    input_file_path: str = Field(default="", description="scan_prepare：生成的输入文件路径")
    run_hint: str = Field(default="", description="scan_prepare：提交运行提示")

    # scan_parse
    profile_table: str = Field(default="", description="scan_parse：逐点相对能量文本表（kcal/mol）")
    verdicts: list[str] = Field(default_factory=list, description="scan_parse：剖面判定列表")
    barrier_kcal: Optional[float] = Field(default=None, description="scan_parse：势垒（最高点−首点，kcal/mol）")

    # verify
    verdict: str = Field(
        default="",
        description="verify：默认 candidate/unlikely/inconclusive；strict 为 pass/fail/inconclusive。",
    )
    n_imag: Optional[int] = Field(default=None, description="verify：虚频个数")
    imag_freqs: list[float] = Field(default_factory=list, description="verify：虚频值列表（cm⁻¹，负值）")
    checks: list[str] = Field(default_factory=list, description="verify：逐项检查明细")
    irc_end_a_path: str = Field(default="", description="verify：IRC 端点 A xyz 路径")
    irc_end_b_path: str = Field(default="", description="verify：IRC 端点 B xyz 路径")


# ---------------------------------------------------------------------------
# 通用 xyz 读取 / 几何
# ---------------------------------------------------------------------------

def _load_xyz(input_path: Optional[str], input_text: Optional[str]):
    """从路径或文本读取 xyz，返回 ASE Atoms。惰性导入 ASE。"""
    import ase.io

    if input_path:
        if not os.path.isfile(input_path):
            raise ValueError(f"输入文件不存在: {input_path}")
        return ase.io.read(input_path, format="xyz")
    if input_text:
        return ase.io.read(StringIO(input_text), format="xyz")
    raise ValueError("必须提供路径或文本之一")


def _atoms_to_xyz_block(symbols, positions, comment: str = "") -> str:
    lines = [str(len(symbols)), comment]
    for s, p in zip(symbols, positions):
        lines.append(f"{s:<4} {p[0]:>14.8f} {p[1]:>14.8f} {p[2]:>14.8f}")
    return "\n".join(lines) + "\n"


def _bond_pairs(symbols, positions, scale: float = 1.25) -> set[tuple[int, int]]:
    """共价半径距离判据成键对集合（0-based，i<j）。"""
    import numpy as np

    pos = np.asarray(positions, dtype=float)
    pairs: set[tuple[int, int]] = set()
    for i in range(len(symbols)):
        ri = _COVALENT_RADII.get(symbols[i], 1.2)
        for j in range(i + 1, len(symbols)):
            rj = _COVALENT_RADII.get(symbols[j], 1.2)
            if float(np.linalg.norm(pos[i] - pos[j])) <= scale * (ri + rj):
                pairs.add((i, j))
    return pairs


def _pair_label(symbols, pair: tuple[int, int]) -> str:
    return f"{symbols[pair[0]]}{pair[0] + 1}-{symbols[pair[1]]}{pair[1] + 1}"


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


def _dist_matrix(coords):
    import numpy as np

    pos = np.asarray(coords, dtype=float)
    diff = pos[:, None, :] - pos[None, :, :]
    return np.linalg.norm(diff, axis=-1)


def _evaluate_endpoint_between(symbols: Sequence[str], ts_pos, end_pos,
                               intermediate_pos, watch_pairs: Sequence[Sequence[int]]) -> dict:
    """判断一个部分 IRC 端点是否位于 TS 与某个优化中间体之间。"""
    import numpy as np

    n = len(symbols)
    arrays = [np.asarray(pos, dtype=float) for pos in (ts_pos, end_pos, intermediate_pos)]
    if any(pos.shape != (n, 3) for pos in arrays):
        return {
            "is_decidable": False, "is_between": False, "score": float("inf"),
            "pairs": [], "details": ["TS、IRC 端点与中间体的坐标维度不一致。"],
        }

    d_ts, d_end, d_int = (_dist_matrix(pos) for pos in arrays)
    pairs: list[tuple[int, int]] = []
    if watch_pairs:
        for raw_pair in watch_pairs:
            if len(raw_pair) != 2:
                return {
                    "is_decidable": False, "is_between": False, "score": float("inf"),
                    "pairs": [], "details": [f"watch_pairs 项必须含两个原子序号: {raw_pair}"],
                }
            i, j = int(raw_pair[0]) - 1, int(raw_pair[1]) - 1
            if not (0 <= i < n and 0 <= j < n) or i == j:
                return {
                    "is_decidable": False, "is_between": False, "score": float("inf"),
                    "pairs": [], "details": [f"watch_pairs 原子序号无效: {raw_pair}"],
                }
            pair = (min(i, j), max(i, j))
            if pair not in pairs:
                pairs.append(pair)
        pairs = [pair for pair in pairs if abs(d_int[pair] - d_ts[pair]) > _STRICT_PAIR_EPS_ANG]
    else:
        ranked = []
        for i in range(n):
            for j in range(i + 1, n):
                delta = abs(d_int[i, j] - d_ts[i, j])
                if delta >= _STRICT_PAIR_DELTA_MIN_ANG:
                    ranked.append((delta, (i, j)))
        ranked.sort(reverse=True)
        pairs = [pair for _, pair in ranked[:_STRICT_MAX_AUTO_PAIRS]]

    if not pairs:
        return {
            "is_decidable": False, "is_between": False, "score": float("inf"),
            "pairs": [], "details": ["TS 与中间体之间没有足以判断方向的原子对距离变化。"],
        }

    q_ts = np.asarray([d_ts[pair] for pair in pairs])
    q_end = np.asarray([d_end[pair] for pair in pairs])
    q_int = np.asarray([d_int[pair] for pair in pairs])
    lower = np.minimum(q_ts, q_int) - _STRICT_INTERVAL_TOL_ANG
    upper = np.maximum(q_ts, q_int) + _STRICT_INTERVAL_TOL_ANG
    inside = (q_end >= lower) & (q_end <= upper)
    dist_ts_to_int = float(np.linalg.norm(q_ts - q_int))
    dist_end_to_int = float(np.linalg.norm(q_end - q_int))
    closer = dist_end_to_int < dist_ts_to_int
    is_between = bool(np.all(inside) and closer)
    score = dist_end_to_int / dist_ts_to_int if dist_ts_to_int > 0 else float("inf")

    details = [
        f"{_pair_label(symbols, pair)}: TS={d_ts[pair]:.3f} Å, "
        f"IRC端点={d_end[pair]:.3f} Å, 中间体={d_int[pair]:.3f} Å, "
        f"{'区间内' if inside[k] else '区间外'}"
        for k, pair in enumerate(pairs)
    ]
    details.append(f"端点到中间体的距离向量比值={score:.3f}（<1 表示比 TS 更接近）。")
    return {
        "is_decidable": True,
        "is_between": is_between,
        "score": score,
        "pairs": pairs,
        "details": details,
    }


def _assign_irc_endpoints(symbols: Sequence[str], ts_pos, end_a_pos, end_b_pos,
                          intermediate_a_pos, intermediate_b_pos,
                          watch_pairs: Sequence[Sequence[int]]) -> dict:
    """尝试 IRC 两端与两个优化中间体的 direct/swapped 无序配对。"""
    assignments = []
    for name, target_a, target_b in (
        ("direct", intermediate_a_pos, intermediate_b_pos),
        ("swapped", intermediate_b_pos, intermediate_a_pos),
    ):
        result_a = _evaluate_endpoint_between(symbols, ts_pos, end_a_pos, target_a, watch_pairs)
        result_b = _evaluate_endpoint_between(symbols, ts_pos, end_b_pos, target_b, watch_pairs)
        assignments.append({
            "name": name,
            "a": result_a,
            "b": result_b,
            "is_decidable": result_a["is_decidable"] and result_b["is_decidable"],
            "is_match": result_a["is_between"] and result_b["is_between"],
            "score": result_a["score"] + result_b["score"],
        })

    decidable = [item for item in assignments if item["is_decidable"]]
    if not decidable:
        details = assignments[0]["a"]["details"] + assignments[0]["b"]["details"]
        return {
            "is_decidable": False, "is_match": False, "assignment": "",
            "details": details,
        }

    matches = [item for item in decidable if item["is_match"]]
    chosen = min(matches or decidable, key=lambda item: item["score"])
    return {
        "is_decidable": True,
        "is_match": bool(matches),
        "assignment": chosen["name"] if matches else "",
        "details": chosen["a"]["details"] + chosen["b"]["details"],
    }


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
            # dS/d(diff) = 2 w err * diff / d
            g_pair = 2.0 * weights[k - 1] * err * diff / np.clip(d, 1e-8, None)[:, None]
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
        raise ValueError("能量剖面至少需要 2 个点")
    n = len(e)
    ts_index = int(np.argmax(e))
    barrier = float(e[ts_index] - e[0])
    verdicts: list[str] = []

    diffs = np.diff(e)
    if np.all(diffs >= 0) or np.all(diffs <= 0):
        verdicts.append("扫描能量全程单调：可能无势垒或扫描坐标选错，建议检查反应坐标的选择。")

    abs_diffs = np.abs(diffs)
    med = float(np.median(abs_diffs))
    jump_idx = int(np.argmax(abs_diffs))
    jump = float(abs_diffs[jump_idx])
    if jump > 3.0 * med and jump > 2.0:
        verdicts.append(
            f"帧 {jump_idx}→{jump_idx + 1} 能量突跳 {jump:.2f} kcal/mol"
            f"（中位数 {med:.2f}）：可能滑谷/不连续，建议检查该点附近结构。"
        )

    if ts_index == 0 or ts_index == n - 1:
        verdicts.append(
            f"能量极值在扫描边界（帧 {ts_index}）：建议扩大扫描范围以包含真正的势垒顶。"
        )

    peaks = [i for i in range(1, n - 1) if e[i] > e[i - 1] and e[i] > e[i + 1]]
    if len(peaks) > 1:
        verdicts.append(f"检测到多个能量峰（帧 {', '.join(str(i) for i in peaks)}），请逐一检查。")

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
        raise ValueError("日志中未找到 'Summary of ... Potential Surface Scan' 扫描汇总表。")
    energies: list[float] = []
    for line in text[m.end():].splitlines():
        em = _EIGEN_LINE_RE.search(line)
        if em:
            energies.extend(float(v) for v in em.group(1).split())
    if not energies:
        raise ValueError("扫描汇总表中未解析到 Eigenvalues 能量行。")
    return energies


def _parse_std_orientation_blocks(text: str) -> list[list[tuple[int, float, float, float]]]:
    """解析所有 "Standard orientation:" 坐标块，返回 [(atomno, x, y, z), ...] 列表的列表。"""
    blocks = []
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        if "Standard orientation:" in lines[i]:
            j = i + 1
            dash = 0
            rows: list[tuple[int, float, float, float]] = []
            while j < len(lines):
                s = lines[j].strip()
                if s and set(s) == {"-"}:
                    dash += 1
                    j += 1
                    if dash == 3:
                        break
                    continue
                if dash == 2:
                    parts = s.split()
                    if len(parts) >= 6:
                        rows.append((int(parts[1]), float(parts[3]), float(parts[4]), float(parts[5])))
                j += 1
            if rows:
                blocks.append(rows)
            i = j
        else:
            i += 1
    return blocks


_ORCA_SPE_RE = re.compile(r"FINAL SINGLE POINT ENERGY\s+(-?\d+\.\d+)")


def _parse_orca_scan(text: str) -> tuple[list[float], list[tuple[str, float, float, float]]]:
    """尽力而为解析 ORCA 扫描输出：各步单点能量（Eh）+ 末帧几何。"""
    energies = [float(v) for v in _ORCA_SPE_RE.findall(text)]
    if not energies:
        tail = text[-1500:]
        raise ValueError(f"未能从 ORCA 输出解析扫描能量（未找到 'FINAL SINGLE POINT ENERGY'）。\n输出尾部:\n{tail}")
    # 末帧几何：最后一个 "CARTESIAN COORDINATES (ANGSTROEM)" 块
    geom: list[tuple[str, float, float, float]] = []
    idx = text.rfind("CARTESIAN COORDINATES (ANGSTROEM)")
    if idx >= 0:
        for line in text[idx:].splitlines()[2:]:
            parts = line.split()
            if len(parts) >= 4 and parts[0].isalpha():
                try:
                    geom.append((parts[0], float(parts[1]), float(parts[2]), float(parts[3])))
                    continue
                except ValueError:
                    pass
            break
    if not geom:
        tail = text[-1500:]
        raise ValueError(f"未能从 ORCA 输出解析末帧几何。\n输出尾部:\n{tail}")
    return energies, geom


# ---------------------------------------------------------------------------
# verify：频率解析（cclib 优先，正则回退）+ IRC 端点
# ---------------------------------------------------------------------------

_FREQ_LINE_RE = re.compile(r"Frequencies --\s+(.*)")


def _parse_freq_log(log_path: str, engine: str) -> dict:
    """解析频率日志。除频率与收敛性外，尽量返回末帧元素和坐标。"""
    with open(log_path, encoding="utf-8", errors="replace") as f:
        text = f.read()

    vibfreqs: Optional[list[float]] = None
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
            optdone = getattr(data, "optdone", None)
            if isinstance(optdone, bool):
                converged = optdone
            elif optdone:
                converged = True
            atomnos = getattr(data, "atomnos", None)
            atomcoords = getattr(data, "atomcoords", None)
            if atomnos is not None and atomcoords is not None and len(atomcoords) > 0:
                import numpy as np
                from cclib.parser.utils import PeriodicTable

                pt = PeriodicTable()
                symbols = [pt.element[int(z)] for z in atomnos]
                positions = np.asarray(atomcoords[-1], dtype=float)
    except Exception:
        pass

    if vibfreqs is None:
        # 正则回退：Gaussian "Frequencies --" 行（虚频以负值打印）
        freqs: list[float] = []
        for m in _FREQ_LINE_RE.finditer(text):
            for tok in m.group(1).split():
                try:
                    freqs.append(float(tok))
                except ValueError:
                    break
        if freqs:
            vibfreqs = freqs

    if vibfreqs is None:
        raise ValueError(f"未能从频率日志解析振动频率: {log_path}")

    if converged is None:
        # 文本回退：正常终止且无错误标记视为收敛（含纯 freq 作业沿用已收敛几何的情形）
        converged = ("Normal termination" in text) and ("Error termination" not in text)

    if positions is None and engine == "gaussian":
        blocks = _parse_std_orientation_blocks(text)
        if blocks:
            import numpy as np
            from cclib.parser.utils import PeriodicTable

            rows = blocks[-1]
            pt = PeriodicTable()
            symbols = [pt.element[int(z)] for z, *_ in rows]
            positions = np.asarray([[x, y, z] for _, x, y, z in rows], dtype=float)

    return {
        "vibfreqs": vibfreqs,
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
        handlers = {
            "interpolate": self._interpolate,
            "scan_prepare": self._scan_prepare,
            "scan_parse": self._scan_parse,
            "verify": self._verify,
        }
        try:
            return handlers[user_input.mode](user_input)
        except Exception as e:
            return TsGuess_output_schema(is_success=False, message=f"{user_input.mode} 失败: {e}")

    # ---------- mode=interpolate ----------

    def _interpolate(self, user_input: TsGuess_input_schema) -> TsGuess_output_schema:
        import numpy as np

        if user_input.n_images < 2:
            raise ValueError("n_images 必须 ≥ 2")

        r_atoms = _load_xyz(user_input.reactant_path, user_input.reactant_text)
        p_atoms = _load_xyz(user_input.product_path, user_input.product_text)
        r_syms = r_atoms.get_chemical_symbols()
        p_syms = p_atoms.get_chemical_symbols()
        r_pos = np.asarray(r_atoms.get_positions(), dtype=float)
        p_pos = np.asarray(p_atoms.get_positions(), dtype=float)
        n = len(r_syms)

        if len(p_syms) != n:
            raise ValueError(f"反应物（{n} 原子）与产物（{len(p_syms)} 原子）原子数不一致")
        if sorted(r_syms) != sorted(p_syms):
            raise ValueError(f"反应物与产物元素多重集不一致: {sorted(r_syms)} vs {sorted(p_syms)}")

        # atom_map 重排产物：产物第 k 个原子（0-based k-1）对应反应物第 atom_map[k-1] 个原子
        if user_input.atom_map:
            am = user_input.atom_map
            if sorted(am) != list(range(1, n + 1)):
                raise ValueError(f"atom_map 必须是 1..{n} 的合法排列，收到: {am}")
            new_pos = np.zeros_like(p_pos)
            new_syms: list[str] = [""] * n
            for k, target in enumerate(am):
                if p_syms[k] != r_syms[target - 1]:
                    raise ValueError(
                        f"atom_map 元素不匹配: 产物第 {k + 1} 个原子（{p_syms[k]}）映射到"
                        f"反应物第 {target} 个原子（{r_syms[target - 1]}）"
                    )
                new_pos[target - 1] = p_pos[k]
                new_syms[target - 1] = p_syms[k]
            p_pos = new_pos
            p_syms = new_syms
        elif r_syms != p_syms:
            raise ValueError("反应物与产物原子序不同且未提供 atom_map，无法一一对应")

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
        out_dir = user_input.output_dir or "./ts_interp"
        os.makedirs(out_dir, exist_ok=True)
        for k in range(n_img):
            atomic_write_text(
                os.path.join(out_dir, f"img_{k:02d}.xyz"),
                _atoms_to_xyz_block(r_syms, images[k], comment=f"ts_guess {user_input.interp_method} image {k}"),
            )

        # 监测原子对
        d_r = _dist_matrix(images[0])
        d_p = _dist_matrix(images[-1])
        if user_input.watch_pairs:
            pairs = []
            for pair in user_input.watch_pairs:
                if len(pair) != 2:
                    raise ValueError(f"watch_pairs 每项必须是 2 个原子序号: {pair}")
                i, j = pair[0] - 1, pair[1] - 1
                if not (0 <= i < n and 0 <= j < n) or i == j:
                    raise ValueError(f"watch_pairs 原子序号越界: {pair}（体系共 {n} 个原子）")
                pairs.append((min(i, j), max(i, j)))
        else:
            iu = np.triu_indices(n, k=1)
            deltas = np.abs(d_p[iu] - d_r[iu])
            order = np.argsort(-deltas)[:5]
            pairs = sorted({(int(iu[0][o]), int(iu[1][o])) for o in order})

        # 距离表
        header = f"{'帧':>4}" + "".join(f"  {_pair_label(r_syms, pr):>12}" for pr in pairs)
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
                f"已生成 {n_img} 帧图像（{user_input.interp_method}）于 {out_dir}。"
                f"TS 候选帧：img_{ts_index:02d}.xyz（监测对 {_pair_label(r_syms, key_pair)} 跨过两端中点）。"
                "这些图像可直接作为 NEB 初始路径，或逐帧做约束优化找 TS 初猜；"
                "也可用 scan_prepare 生成约束扫描输入进一步定位势垒顶。"
            ),
        )

    # ---------- mode=scan_prepare ----------

    def _scan_prepare(self, user_input: TsGuess_input_schema) -> TsGuess_output_schema:
        import numpy as np

        need = {"bond": 2, "angle": 3, "dihedral": 4}[user_input.coord_type]
        if len(user_input.atoms) != need:
            raise ValueError(f"coord_type={user_input.coord_type} 需要 {need} 个原子序号，收到 {len(user_input.atoms)}")
        if not user_input.output_path:
            raise ValueError("scan_prepare 必须提供 output_path（输入文件写入路径）")
        if user_input.scan_steps < 1:
            raise ValueError("scan_steps 必须 ≥ 1")

        atoms = _load_xyz(user_input.input_path, user_input.input_text)
        syms = atoms.get_chemical_symbols()
        pos = np.asarray(atoms.get_positions(), dtype=float)
        n = len(syms)
        idx = [a - 1 for a in user_input.atoms]
        for a in idx:
            if not (0 <= a < n):
                raise ValueError(f"扫描原子序号越界: {user_input.atoms}（体系共 {n} 个原子）")

        if user_input.coord_type == "bond":
            current = float(np.linalg.norm(pos[idx[0]] - pos[idx[1]]))
        elif user_input.coord_type == "angle":
            current = _angle_deg(pos[idx[0]], pos[idx[1]], pos[idx[2]])
        else:
            current = _dihedral_deg(pos[idx[0]], pos[idx[1]], pos[idx[2]], pos[idx[3]])

        start = user_input.scan_start if user_input.scan_start is not None else current
        end = user_input.scan_end
        step_size = (end - start) / user_input.scan_steps
        method = user_input.method.strip()
        extra = user_input.extra_route.strip()
        coord_letter = {"bond": "B", "angle": "A", "dihedral": "D"}[user_input.coord_type]

        if user_input.engine == "gaussian":
            route = f"# opt=(modredundant,maxstep=10) {method}"
            if extra:
                route += f" {extra}"
            coord_lines = "\n".join(
                f"{s:<4} {p[0]:>14.8f} {p[1]:>14.8f} {p[2]:>14.8f}" for s, p in zip(syms, pos)
            )
            scan_block = f"{coord_letter} {' '.join(str(a) for a in user_input.atoms)} S {user_input.scan_steps} {step_size:.6f}"
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
            run_hint = (
                f"用 submit_compute_job（job_type='gaussian'）提交 {user_input.output_path}；"
                "完成后用 ts_guess mode='scan_parse' 解析日志并提取 TS 初猜。"
            )
        else:
            orca_method = method.replace("/", " ")
            header = f"! OPT {orca_method}"
            if extra:
                header += f" {extra}"
            idx0 = [a - 1 for a in user_input.atoms]  # ORCA 原子序号 0-based
            xyz_lines = "\n".join(f"{s:<3} {p[0]:>14.8f} {p[1]:>14.8f} {p[2]:>14.8f}" for s, p in zip(syms, pos))
            content = "\n".join([
                header,
                f"%pal nprocs {user_input.nprocs} end",
                "%geom",
                f"    Scan {coord_letter} {' '.join(str(a) for a in idx0)} = {start:.6f}, {end:.6f}, {user_input.scan_steps} end",
                "end",
                "",
                f"* xyz {user_input.charge} {user_input.spin}",
                xyz_lines,
                "*",
                "",
            ])
            run_hint = (
                f"用 submit_compute_job（job_type='orca'）提交 {user_input.output_path}；"
                "完成后用 ts_guess mode='scan_parse' engine='orca' 解析日志并提取 TS 初猜。"
            )

        out_dir = os.path.dirname(os.path.abspath(user_input.output_path))
        os.makedirs(out_dir, exist_ok=True)
        atomic_write_text(user_input.output_path, content)

        return TsGuess_output_schema(
            is_success=True,
            input_file_path=user_input.output_path,
            run_hint=run_hint,
            message=(
                f"{user_input.engine} 约束扫描输入已写入 {user_input.output_path}："
                f"{coord_letter} {'-'.join(str(a) for a in user_input.atoms)} 从 {start:.4f} 扫到 {end:.4f}，"
                f"共 {user_input.scan_steps} 步（步长 {step_size:+.6f}）。"
            ),
        )

    # ---------- mode=scan_parse ----------

    def _scan_parse(self, user_input: TsGuess_input_schema) -> TsGuess_output_schema:
        import numpy as np

        if not user_input.log_path:
            raise ValueError("scan_parse 必须提供 log_path")
        if not os.path.isfile(user_input.log_path):
            raise ValueError(f"日志文件不存在: {user_input.log_path}")
        with open(user_input.log_path, encoding="utf-8", errors="replace") as f:
            text = f.read()

        symbols: Optional[list[str]] = None
        ts_coords = None
        notes: list[str] = []

        if user_input.engine == "gaussian":
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
            except Exception as e:
                notes.append(f"cclib 几何提取失败（{e}），回退 Standard orientation 解析。")

            if ts_coords is None:
                blocks = _parse_std_orientation_blocks(text)
                if not blocks:
                    raise ValueError("无法从日志提取 TS 候选几何（cclib 与 Standard orientation 均失败）。")
                # 能量最高点那一帧的最后一个 Standard orientation
                if len(blocks) >= n_pts:
                    # 每帧优化含若干取向块，按帧均分取该帧最后一块
                    per = len(blocks) / n_pts
                    block_idx = min(int(round((ts_index + 1) * per)) - 1, len(blocks) - 1)
                else:
                    block_idx = len(blocks) - 1
                    notes.append("Standard orientation 块数少于扫描点数，取全文件最后一块作为近似。")
                rows = blocks[block_idx]
                from cclib.parser.utils import PeriodicTable

                pt = PeriodicTable()
                symbols = [pt.element[int(z)] for z, *_ in rows]
                ts_coords = np.asarray([[x, y, z] for _, x, y, z in rows], dtype=float)
        else:
            energies_eh, geom = _parse_orca_scan(text)
            e0 = energies_eh[0]
            rel_kcal = [(e - e0) * KCAL_PER_HARTREE for e in energies_eh]
            profile = analyze_scan_profile(rel_kcal)
            ts_index = profile["ts_index"]
            symbols = [g[0] for g in geom]
            ts_coords = np.asarray([[g[1], g[2], g[3]] for g in geom], dtype=float)
            notes.append("ORCA 扫描解析为尽力而为：几何取全文件最后一个笛卡尔坐标块（末帧），"
                         "若能量最高点不在末帧，请以剖面表为准手动取帧。")

        # 剖面文本表
        lines = [f"{'帧':>4}  {'相对能量 (kcal/mol)':>18}"]
        for k, e in enumerate(rel_kcal):
            marker = "  <- 最高点（TS 初猜）" if k == ts_index else ""
            lines.append(f"{k:>4}  {e:>18.4f}{marker}")
        profile_table = "\n".join(lines)

        ts_path = user_input.ts_candidate_path or os.path.splitext(user_input.log_path)[0] + "_ts_guess.xyz"
        out_dir = os.path.dirname(os.path.abspath(ts_path))
        os.makedirs(out_dir, exist_ok=True)
        atomic_write_text(ts_path, _atoms_to_xyz_block(
            symbols, ts_coords,
            comment=f"ts_guess scan_parse TS candidate frame={ts_index} from {os.path.basename(user_input.log_path)}",
        ))

        verdicts = list(profile["verdicts"]) + notes
        return TsGuess_output_schema(
            is_success=True,
            profile_table=profile_table,
            verdicts=verdicts,
            barrier_kcal=round(profile["barrier_kcal"], 4),
            ts_candidate_index=ts_index,
            ts_candidate_path=ts_path,
            message=(
                f"扫描解析完成：{len(rel_kcal)} 个点，势垒（最高点−首点）{profile['barrier_kcal']:.2f} kcal/mol，"
                f"最高点为帧 {ts_index}，TS 初猜几何已写入 {ts_path}。"
                "建议以此几何提交 opt=(ts,calcfc,noeigentest) 的 TS 优化 + 频率计算，"
                "再用 ts_guess mode='verify' 做验证。"
            ),
        )

    # ---------- mode=verify ----------

    def _verify(self, user_input: TsGuess_input_schema) -> TsGuess_output_schema:
        if not user_input.freq_log:
            raise ValueError("verify 必须提供 freq_log")
        if not os.path.isfile(user_input.freq_log):
            raise ValueError(f"频率日志不存在: {user_input.freq_log}")

        freq = _parse_freq_log(user_input.freq_log, user_input.engine)
        vibfreqs = freq["vibfreqs"]
        imag = [f for f in vibfreqs if f < 0]
        n_imag = len(imag)
        checks: list[str] = []

        irc_end_a_path = ""
        irc_end_b_path = ""

        if user_input.strict:
            if not freq["converged"]:
                checks.append("频率作业未正常收敛，无法建立一阶鞍点前提。")
                verdict = "inconclusive：频率作业未正常收敛，现有材料不足以作严格判断。"
            elif n_imag != 1:
                if n_imag == 0:
                    checks.append("正常结束的频率作业无虚频：该结构是极小点，不是一阶鞍点。")
                else:
                    checks.append(
                        f"正常结束的频率作业有 {n_imag} 个虚频"
                        f"（{', '.join(f'{f:.1f}' for f in imag)} cm⁻¹）：该结构是高阶鞍点。"
                    )
                verdict = "fail：严格检查要求恰有一个虚频。"
            else:
                checks.append(f"恰有 1 个虚频（{imag[0]:.1f} cm⁻¹）：一阶鞍点前提成立。")
                verdict, info = self._strict_path_verdict(user_input, freq, checks)
                if info is not None:
                    irc_end_a_path = info["path_a"]
                    irc_end_b_path = info["path_b"]
        else:
            if not freq["converged"]:
                checks.append("频率作业未正常收敛，不能据此判断 TS 候选。")
                verdict = "inconclusive：频率作业未正常收敛。"
            elif n_imag == 0:
                checks.append("无虚频：该结构是极小点，不像一阶鞍点。")
                verdict = "unlikely：无虚频，该结构更像极小点。"
            elif n_imag > 1:
                checks.append(
                    f"有 {n_imag} 个虚频（{', '.join(f'{f:.1f}' for f in imag)} cm⁻¹）："
                    "该结构更像高阶鞍点。"
                )
                verdict = "unlikely：存在多个虚频，该结构更像高阶鞍点。"
            else:
                checks.append(
                    f"恰有 1 个虚频（{imag[0]:.1f} cm⁻¹）：可作为一阶鞍点候选，但这不是充分证明。"
                )
                irc_ok: Optional[bool] = None
                info = self._extract_irc_endpoints(user_input, checks, require_two_sides=False)
                if info is not None:
                    irc_end_a_path = info["path_a"]
                    irc_end_b_path = info["path_b"]
                    irc_ok = self._check_irc_connectivity(
                        user_input, info["end_a"], info["end_b"], checks,
                    )

                if user_input.irc_log and info is None:
                    verdict = "inconclusive：IRC 已提供，但未能取得可比较的两端几何。"
                elif irc_ok is False:
                    verdict = "unlikely：IRC 端点的粗略连通性与预期结构不一致。"
                else:
                    reason = "一个虚频" + ("，IRC 粗略连通性一致" if irc_ok else "")
                    verdict = f"candidate：{reason}；仅供 agent 判断后续方向，不代表 TS 已被严格证明。"

        return TsGuess_output_schema(
            is_success=True,
            verdict=verdict,
            n_imag=n_imag,
            imag_freqs=[round(f, 2) for f in imag],
            checks=checks,
            irc_end_a_path=irc_end_a_path,
            irc_end_b_path=irc_end_b_path,
            message=f"TS 验证完成：{verdict}",
        )

    @staticmethod
    def _extract_irc_endpoints(user_input: TsGuess_input_schema, checks: list[str],
                               require_two_sides: bool) -> Optional[dict]:
        """提取有坐标的 IRC 外侧帧；strict 时必须分别来自 rx<0 与 rx>0。"""
        if not user_input.irc_log:
            checks.append("未提供 IRC 日志。")
            return None
        if not os.path.isfile(user_input.irc_log):
            raise ValueError(f"IRC 日志不存在: {user_input.irc_log}")
        if user_input.engine != "gaussian":
            checks.append("当前仅支持从 Gaussian IRC 日志提取路径端点。")
            return None

        from cloudra.tools.core import gaussian_frames

        try:
            frames, meta = gaussian_frames.extract_irc(user_input.irc_log)
        except Exception as e:
            checks.append(f"IRC 端点提取失败：{e}")
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
                checks.append("IRC 日志没有同时提供 rx<0 与 rx>0 的有效坐标帧。")
                return None
            end_a = min(negative, key=lambda frame: frame.reaction_coordinate)
            end_b = max(positive, key=lambda frame: frame.reaction_coordinate)
        else:
            if len(valid) < 2:
                checks.append("IRC 日志中少于两个带坐标的路径帧。")
                return None
            end_a, end_b = valid[0], valid[-1]

        out_dir = user_input.output_dir or os.path.splitext(user_input.freq_log)[0] + "_verify"
        os.makedirs(out_dir, exist_ok=True)
        path_a = os.path.join(out_dir, "irc_end_a.xyz")
        path_b = os.path.join(out_dir, "irc_end_b.xyz")
        atomic_write_text(path_a, end_a.xyz.rstrip() + "\n")
        atomic_write_text(path_b, end_b.xyz.rstrip() + "\n")
        checks.append(
            f"IRC 两侧外帧已提取：irc_end_a.xyz（rx={end_a.reaction_coordinate}）、"
            f"irc_end_b.xyz（rx={end_b.reaction_coordinate}）→ {out_dir}"
        )
        if require_two_sides and not (
            meta.get("forward_converged", False) and meta.get("backward_converged", False)
        ):
            checks.append("IRC 至少一侧未走到极小点；strict 仅检查部分端点方向，因此不把未跑完整视为失败。")
        return {
            "end_a": end_a,
            "end_b": end_b,
            "frames": frames,
            "meta": meta,
            "path_a": path_a,
            "path_b": path_b,
        }

    def _strict_path_verdict(self, user_input: TsGuess_input_schema, freq: dict,
                             checks: list[str]) -> tuple[str, Optional[dict]]:
        """证明两个部分 IRC 端点分别位于 TS 与两个优化中间体之间。"""
        import ase.io
        import numpy as np

        has_intermediate_a = bool(user_input.reactant_path or user_input.reactant_text)
        has_intermediate_b = bool(user_input.product_path or user_input.product_text)
        if not (has_intermediate_a and has_intermediate_b):
            checks.append("strict 需要两侧 IRC 外帧分别优化所得的两个中间体结构。")
            return "inconclusive：缺少两个端点优化中间体。", None

        info = self._extract_irc_endpoints(user_input, checks, require_two_sides=True)
        if info is None:
            return "inconclusive：缺少可用的双向 IRC 端点。", None

        try:
            end_a_atoms = ase.io.read(StringIO(info["end_a"].xyz), format="xyz")
            end_b_atoms = ase.io.read(StringIO(info["end_b"].xyz), format="xyz")
            intermediate_a = _load_xyz(user_input.reactant_path, user_input.reactant_text)
            intermediate_b = _load_xyz(user_input.product_path, user_input.product_text)
        except Exception as e:
            checks.append(f"端点或优化中间体结构无法解析：{e}")
            return "inconclusive：结构材料无法解析。", info

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
                checks.append("频率日志未给出 TS 几何，改用 IRC 的 rx=0 帧。")
            else:
                checks.append("频率日志与 IRC 均未提供可用的 TS 几何。")
                return "inconclusive：缺少 TS 几何。", info

        symbol_sets = [
            list(ts_symbols),
            end_a_atoms.get_chemical_symbols(),
            end_b_atoms.get_chemical_symbols(),
            intermediate_a.get_chemical_symbols(),
            intermediate_b.get_chemical_symbols(),
        ]
        if any(symbols != symbol_sets[0] for symbols in symbol_sets[1:]):
            checks.append("TS、IRC 两侧外帧与两个优化中间体的元素或原子顺序不一致。")
            return "inconclusive：各结构的元素或原子顺序不一致。", info

        assignment = _assign_irc_endpoints(
            symbol_sets[0],
            np.asarray(ts_positions, dtype=float),
            np.asarray(end_a_atoms.get_positions(), dtype=float),
            np.asarray(end_b_atoms.get_positions(), dtype=float),
            np.asarray(intermediate_a.get_positions(), dtype=float),
            np.asarray(intermediate_b.get_positions(), dtype=float),
            user_input.watch_pairs,
        )
        checks.extend(assignment["details"])
        if not assignment["is_decidable"]:
            checks.append("所选原子对不足以判断 IRC 端点相对 TS 与中间体的方向。")
            return "inconclusive：缺少足以判断方向的几何变化。", info
        if not assignment["is_match"]:
            checks.append("至少一侧 IRC 外帧不在 TS 与任一可配对优化中间体之间。")
            return "fail：部分 IRC 的路径方向与两个优化中间体不一致。", info

        mapping = "直接配对" if assignment["assignment"] == "direct" else "交换两侧后配对"
        checks.append(f"{mapping}成立：两侧 IRC 外帧均位于 TS 与对应优化中间体之间。")
        return (
            "pass：部分 IRC 的双向路径与两个优化中间体一致；"
            "该结论只证明路径方向，不代表 TS 在所有化学意义上绝对正确。",
            info,
        )

    @staticmethod
    def _check_irc_connectivity(user_input: TsGuess_input_schema, end_a, end_b,
                                checks: list[str]) -> Optional[bool]:
        """比较 IRC 两端点与预期反应物/产物的成键集合。未提供预期结构时只报告成键表。"""
        import ase.io

        def frame_atoms(frame):
            return ase.io.read(StringIO(frame.xyz), format="xyz")

        atoms_a = frame_atoms(end_a)
        atoms_b = frame_atoms(end_b)
        syms = atoms_a.get_chemical_symbols()
        bonds_a = _bond_pairs(syms, atoms_a.get_positions())
        bonds_b = _bond_pairs(syms, atoms_b.get_positions())

        def bond_table(name, bonds):
            if bonds:
                return f"{name} 成键: " + ", ".join(_pair_label(syms, pr) for pr in sorted(bonds))
            return f"{name} 成键: （无）"

        if not (user_input.reactant_path or user_input.reactant_text) and \
           not (user_input.product_path or user_input.product_text):
            checks.append(
                "未提供预期反应物/产物，仅报告 IRC 端点成键表："
                + bond_table("端点A", bonds_a) + "；" + bond_table("端点B", bonds_b)
            )
            return None

        r_atoms = _load_xyz(user_input.reactant_path, user_input.reactant_text)
        p_atoms = _load_xyz(user_input.product_path, user_input.product_text)
        if r_atoms.get_chemical_symbols() != syms or p_atoms.get_chemical_symbols() != syms:
            checks.append("预期反应物/产物与 IRC 作业原子序不一致，跳过连通性核对。")
            return None
        bonds_r = _bond_pairs(syms, r_atoms.get_positions())
        bonds_p = _bond_pairs(syms, p_atoms.get_positions())

        def diff_count(b1, b2):
            return len(b1.symmetric_difference(b2))

        # 两种端点↔预期指派，取差异键总数小者
        direct = diff_count(bonds_a, bonds_r) + diff_count(bonds_b, bonds_p)
        swapped = diff_count(bonds_a, bonds_p) + diff_count(bonds_b, bonds_r)
        if swapped < direct:
            assign = [("端点A", bonds_a, "产物", bonds_p), ("端点B", bonds_b, "反应物", bonds_r)]
        else:
            assign = [("端点A", bonds_a, "反应物", bonds_r), ("端点B", bonds_b, "产物", bonds_p)]

        diff_lines = []
        for end_name, end_bonds, exp_name, exp_bonds in assign:
            extra = sorted(end_bonds - exp_bonds)
            missing = sorted(exp_bonds - end_bonds)
            if extra or missing:
                parts = []
                if extra:
                    parts.append("多出键: " + ", ".join(_pair_label(syms, pr) for pr in extra))
                if missing:
                    parts.append("缺少键: " + ", ".join(_pair_label(syms, pr) for pr in missing))
                diff_lines.append(f"{end_name} vs {exp_name}（{'; '.join(parts)}）")

        if diff_lines:
            checks.append(
                "IRC 两端与预期反应物/产物连通性不一致（差异键）：" + "；".join(diff_lines)
            )
            return False
        checks.append(
            "IRC 两端与预期反应物/产物连通性一致："
            + "；".join(f"{end} ↔ {exp}" for end, _, exp, _ in assign)
        )
        return True


def get_class():
    return TsGuess
