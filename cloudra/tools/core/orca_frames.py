"""ORCA 输出日志关键帧提取：任务类型识别 + 逐帧结构/能量/频率导出。

与 gaussian_frames 对齐的纯函数模块（复用其 FrameRecord / CSV 写出）：

- opt / freq / sp / unrelaxed scan 走 cclib（scfenergies / atomcoords /
  vibfreqs / optdone / scanparm），cclib 对 ORCA 支持良好；
- ORCA 的松弛面扫描（relaxed surface scan）在 cclib 1.8.x 中不暴露
  scanenergies/scancoords，仅给出 scfenergies + scanparm，几何序列暂缺；
- IRC（`IRC` 关键字）目前不提取逐点反应坐标：ORCA IRC 的路径点坐标在
  `_IRC.log` 附属文件而非主输出，v1 不做副文件追踪；
- 热化学（`FREQ` 后的 THERMOCHEMISTRY 块）为自写正则解析，对齐
  log_parser 的 corrections/totals 字段语义。

cclib / numpy 在函数内惰性导入。
"""

from __future__ import annotations

import re

from cloudra.tools.core.gaussian_frames import (
    EV_PER_HARTREE,
    FrameRecord,
    _as_float_list,
    _ccread,
    _coords_to_xyz,
    _get_vibfreqs,
    _opt_converged,
    _read_text,
)

# ---------------------------------------------------------------------------
# 任务类型识别
# ---------------------------------------------------------------------------

_ORCA_KEYWORDS_RE = re.compile(r"^\s*!\s*(?P<kw>.+)$", re.M | re.I)


def _collect_keyword_lines(text: str) -> str:
    """收集输入回显中的 `!` 关键字行（ORCA 在输出开头回显输入文件）。"""
    return " ".join(m.group("kw") for m in _ORCA_KEYWORDS_RE.finditer(text)).lower()


def detect_job_types(log_path: str) -> set[str]:
    """识别 ORCA 日志的任务类型，返回 {"opt","ts","freq","scan","irc","sp"} 的子集。"""
    text = _read_text(log_path)
    keywords = _collect_keyword_lines(text)
    jobs: set[str] = set()

    if re.search(r"\birc\b", keywords) or "IRC ITERATION" in text:
        jobs.add("irc")
    if (
        re.search(r"\bscan\b", keywords)
        or "Parameter Scan Calculation" in text
        or "Relaxed Surface Scan" in text
    ):
        jobs.add("scan")
    if re.search(r"\bopt(ts)?\b", keywords) or "GEOMETRY OPTIMIZATION CYCLE" in text:
        jobs.add("opt")
    if re.search(r"\boptts\b", keywords) or "SADDLE POINT SEARCH" in text.upper():
        jobs.add("ts")
    if (
        re.search(r"\b(freq|numfreq|anfreq)\b", keywords)
        or "VIBRATIONAL FREQUENCIES" in text
    ):
        jobs.add("freq")
    if not jobs & {"irc", "scan", "opt", "ts"}:
        jobs.add("sp")
    return jobs


# ---------------------------------------------------------------------------
# 热化学（THERMOCHEMISTRY 块）
# ---------------------------------------------------------------------------

_FLOAT = r"([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[DdEe][+-]?\d+)?)"

_ORCA_THERMO_PATTERNS = {
    # 修正量（加到电子能上）
    "zero_point_correction_hartree": rf"Zero point energy\s+\.\.\.\s+{_FLOAT}\s+Eh",
    "thermal_energy_correction_hartree": rf"Total thermal correction\s+{_FLOAT}\s+Eh",
    "thermal_enthalpy_correction_hartree": rf"Thermal Enthalpy correction\s+\.\.\.\s+{_FLOAT}\s+Eh",
    # 总量（含电子能）
    "total_zero_point_energy_hartree": None,  # 派生：电子能 + ZPE 修正
    "total_thermal_energy_hartree": rf"Total thermal energy\s+{_FLOAT}\s+Eh",
    "total_enthalpy_hartree": rf"Total [Ee]nthalpy\s+\.*\s*\.\.\.\s+{_FLOAT}\s+Eh",
    "total_gibbs_free_energy_hartree": rf"Final Gibbs free (?:enthalpy|energy)\s+\.\.\.\s+{_FLOAT}\s+Eh",
}


def _extract_electronic_energy(text: str) -> float | None:
    """取最后一个 FINAL SINGLE POINT ENERGY（电子能，Eh）。"""
    matches = re.findall(rf"FINAL SINGLE POINT ENERGY\s+{_FLOAT}", text)
    if not matches:
        return None
    return float(matches[-1])


def extract_thermochemistry(log_path: str) -> dict[str, float]:
    """解析最后一个 THERMOCHEMISTRY 块，字段语义对齐 Gaussian 版。

    与 Gaussian 的差异：
    - ORCA 的 "Total thermal correction" 不含 ZPE（Gaussian 的
      "Thermal correction to Energy" 含 ZPE）。此处换算为含 ZPE 口径：
      thermal_energy_correction = Total thermal correction + ZPE，
      使 total_zero_point_energy = scf + zpe 等恒等式跨引擎一致。
    - Gibbs 修正量块内不直接给出，取 G − E(el)。
    """
    text = _read_text(log_path)
    blocks = re.split(r"-{5,}\s*\n\s*THERMOCHEMISTRY AT\s", text)
    if len(blocks) < 2:
        # 无 THERMOCHEMISTRY 标题的频算输出兜底：直接全文匹配
        target = text
    else:
        target = "THERMOCHEMISTRY AT" + blocks[-1]

    values: dict[str, float] = {}
    for field, pattern in _ORCA_THERMO_PATTERNS.items():
        if pattern is None:
            continue
        m = re.search(pattern, target)
        if m:
            values[field] = float(m.group(1))

    zpe = values.get("zero_point_correction_hartree")
    if zpe is not None:
        values["thermal_energy_correction_hartree"] = (
            values.get("thermal_energy_correction_hartree", 0.0) + zpe
        )

    e_el = _extract_electronic_energy(text)
    if e_el is not None:
        if zpe is not None:
            values["total_zero_point_energy_hartree"] = e_el + zpe
        gibbs = values.get("total_gibbs_free_energy_hartree")
        if gibbs is not None:
            values["thermal_gibbs_correction_hartree"] = gibbs - e_el
        energy_corr = values.get("thermal_energy_correction_hartree")
        if energy_corr is not None and "total_thermal_energy_hartree" not in values:
            values["total_thermal_energy_hartree"] = e_el + energy_corr
    return values


# ---------------------------------------------------------------------------
# 帧提取
# ---------------------------------------------------------------------------

def _extract_opt_frames(log_path: str) -> list[FrameRecord]:
    data = _ccread(log_path)
    energies = getattr(data, "scfenergies", None)
    atomcoords = getattr(data, "atomcoords", None)
    atomnos = getattr(data, "atomnos", None)
    if energies is None or atomcoords is None or atomnos is None:
        return []
    energies_ev = _as_float_list(energies)
    n = min(len(energies_ev), len(atomcoords))
    converged = _opt_converged(data)
    freqs = _get_vibfreqs(data)

    frames = []
    for i in range(n):
        is_last = i == n - 1
        frames.append(FrameRecord(
            frame=i,
            scf_energy_hartree=energies_ev[i] / EV_PER_HARTREE,
            frequencies_cm=freqs if (is_last and freqs) else [],
            xyz=_coords_to_xyz(atomnos, atomcoords[i], comment=f"opt step={i}"),
            converged=converged if is_last else None,
        ))
    return frames


def _extract_scan_frames(log_path: str) -> list[FrameRecord]:
    """ORCA 扫描：unrelaxed 时 scanparm 给出逐点参数；relaxed 扫描的

    逐点几何在 cclib 1.8.x 不暴露（scancoords 为 None），能量取
    scfenergies 序列（cclib 会把扫描各点的最终 SCF 记入）。
    逐点参数值：cclib 的 scanparm 对 unrelaxed 扫描只有初值，
    故回退解析 "TRAJECTORY STEP N / <param> : value" 文本标记。
    """
    data = _ccread(log_path)
    energies = getattr(data, "scfenergies", None)
    parm = getattr(data, "scanparm", None)
    if energies is None:
        return []
    energies_ev = _as_float_list(energies)
    n = len(energies_ev)

    parm_values: list[float] = []
    if parm is not None and len(parm) > 0:
        parm_values = _as_float_list(parm[0])
    if len(parm_values) < n:
        # 文本兜底：TRAJECTORY STEP 块内的 "D7 : 32.72727273" 参数行
        step_params = re.findall(
            r"TRAJECTORY STEP\s+\d+\s*\n\s*\S+\s*:\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[EeDd][+-]?\d+)?)",
            _read_text(log_path),
        )
        if len(step_params) >= n:
            parm_values = [float(v) for v in step_params[:n]]

    coords = getattr(data, "scancoords", None)
    atomcoords = getattr(data, "atomcoords", None)
    atomnos = getattr(data, "atomnos", None)
    frames_source = coords if coords is not None else atomcoords
    has_coords = frames_source is not None and atomnos is not None and len(frames_source) == n

    frames = []
    for i in range(n):
        rx = parm_values[i] if i < len(parm_values) else None
        xyz = ""
        if has_coords:
            xyz = _coords_to_xyz(atomnos, frames_source[i], comment=f"scan point={i} parm={rx}")
        frames.append(FrameRecord(
            frame=i,
            reaction_coordinate=rx,
            scf_energy_hartree=energies_ev[i] / EV_PER_HARTREE,
            xyz=xyz,
        ))
    return frames


def _extract_sp_frames(log_path: str) -> list[FrameRecord]:
    data = _ccread(log_path)
    energies = getattr(data, "scfenergies", None)
    atomcoords = getattr(data, "atomcoords", None)
    atomnos = getattr(data, "atomnos", None)
    if atomcoords is None or atomnos is None or len(atomcoords) == 0:
        return []
    energy_hartree = None
    if energies is not None and len(energies) > 0:
        energy_hartree = _as_float_list(energies)[-1] / EV_PER_HARTREE
    return [FrameRecord(
        frame=0,
        scf_energy_hartree=energy_hartree,
        frequencies_cm=_get_vibfreqs(data),
        xyz=_coords_to_xyz(atomnos, atomcoords[-1], comment="single point"),
    )]


def extract_frames(log_path: str) -> list[FrameRecord]:
    """按识别到的任务类型提取关键帧。IRC 暂不支持逐点提取（返回空）。"""
    jobs = detect_job_types(log_path)
    if "irc" in jobs:
        return []
    if "scan" in jobs:
        return _extract_scan_frames(log_path)
    if "opt" in jobs or "ts" in jobs:
        return _extract_opt_frames(log_path)
    return _extract_sp_frames(log_path)
