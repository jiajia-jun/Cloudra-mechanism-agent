"""ORCA 输出日志关键帧提取：任务类型识别 + 逐帧结构/能量/频率导出。

与 gaussian_frames 对齐的纯函数模块（复用其 FrameRecord / CSV 写出）：

- opt / freq / sp / unrelaxed scan 走 cclib（scfenergies / atomcoords /
  vibfreqs / optdone / scanparm），cclib 对 ORCA 支持良好；
- ORCA 的松弛面扫描（relaxed surface scan）在 cclib 1.8.x 中不暴露
  scanenergies/scancoords，仅给出 scfenergies + scanparm，几何序列暂缺；
- IRC（`IRC` 关键字）：逐点的能量/收敛/端点能量从主输出的 FORWARD/
  BACKWARD IRC 迭代块与 IRC PATH SUMMARY 解析（`extract_irc`）；逐点坐标
  在 `*_trj.xyz` 边文件，主输出没有，故 extract_frames 对 IRC 返回空；
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

_ORCA_KEYWORDS_RE = re.compile(r"^\s*(?:\|\s*\d+>\s*)?!\s*(?P<kw>.+)$", re.M | re.I)


def _collect_keyword_lines(text: str) -> str:
    """收集输入回显中的 `!` 关键字行（ORCA 在输出开头回显输入文件）。"""
    return " ".join(m.group("kw") for m in _ORCA_KEYWORDS_RE.finditer(text)).lower()


def detect_job_types(log_path: str) -> set[str]:
    """识别 ORCA 日志的任务类型，返回 {"opt","ts","freq","scan","irc","sp"} 的子集。"""
    text = _read_text(log_path)
    keywords = _collect_keyword_lines(text)
    jobs: set[str] = set()

    if re.search(r"\birc\b", keywords) or "IRC ITERATION" in text or "IRC PATH SUMMARY" in text:
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


# ---------------------------------------------------------------------------
# 终止判定与最终能量（文本权威，不依赖 cclib）
# ---------------------------------------------------------------------------

# ORCA 正常终止标记：作业成败的文本权威判据。cclib 不感知外部 MLIP
# （ExtOpt/ProgExt 日志无 SCF 块，ccdata 常缺 spin multiplicity），其
# metadata.success 对这类日志不可靠——guard 与 log_parser 都以该标记为准
# （GH #17/#18）。
NORMAL_TERMINATION_MARKER = "ORCA TERMINATED NORMALLY"


def normal_termination(text: str) -> bool:
    """ORCA 日志文本是否含正常终止标记（引擎自报，不依赖 cclib）。"""
    return NORMAL_TERMINATION_MARKER in text


_FINAL_ENERGY_RE = re.compile(
    rf"FINAL SINGLE POINT ENERGY(?:\s*\([^)]*\))?\s+{_FLOAT}"
)


def final_energy_hartree(text: str) -> float | None:
    """取最后一次 FINAL SINGLE POINT ENERGY（Eh；含外部 MLIP 变体）。

    外部 MLIP（ExtOpt/ProgExt）日志没有 SCF 能量段，唯一能量行是
    ``FINAL SINGLE POINT ENERGY (From external program)``；几何优化每步
    打印一次，取最后一次。
    """
    energy: float | None = None
    for match in _FINAL_ENERGY_RE.finditer(text):
        energy = float(match.group(1).replace("D", "E").replace("d", "e"))
    return energy


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

    e_el = final_energy_hartree(text)
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
    """按识别到的任务类型提取关键帧。IRC 的逐点坐标在 trj 边文件（主输出无），
    这里对 IRC 返回空；IRC 的点数/收敛/能量走 extract_irc。"""
    jobs = detect_job_types(log_path)
    if "irc" in jobs:
        return []
    if "scan" in jobs:
        return _extract_scan_frames(log_path)
    if "opt" in jobs or "ts" in jobs:
        return _extract_opt_frames(log_path)
    return _extract_sp_frames(log_path)


# ---------------------------------------------------------------------------
# IRC 主输出解析（点数 / 收敛 / 能量）
# ---------------------------------------------------------------------------

# 迭代行：" 0 -1967.123694 -0.987880 0.009347 0.001949"
_IRCA_ITER_RE = re.compile(
    r"^\s*(\d+)\s+(-?\d+\.\d+)\s+(-?\d+\.\d+)\s+(\d+\.\d+)\s+(\d+\.\d+)\s*$"
)
# PATH SUMMARY 行，TS 行尾部带 "<= TS"
_IRCA_SUMMARY_RE = re.compile(
    r"^\s*(\d+)\s+(-?\d+\.\d+)\s+(-?\d+\.\d+)\s+(\d+\.\d+)\s+(\d+\.\d+)(?:\s*<=\s*TS)?\s*$"
)
_IRCA_BLOCK_RE = re.compile(r"\*\s*(FORWARD|BACKWARD)\s+IRC\s*\*")
_IRCA_CONVERGED_RE = re.compile(r"THE IRC HAS CONVERGED")


def _parse_irc_direction_block(text: str) -> tuple[int, bool]:
    """解析一个 FORWARD/BACKWARD IRC 块，返回 (点数, 是否收敛)。

    点数为迭代行数（不含表头/阈值行）；收敛以块尾 "THE IRC HAS CONVERGED"
    （HURRAY 段）为准——步数耗尽而终止的块没有该标记。
    """
    n_points = 0
    for line in text.splitlines():
        if _IRCA_ITER_RE.match(line):
            n_points += 1
    return n_points, bool(_IRCA_CONVERGED_RE.search(text))


def extract_irc(log_path: str) -> dict:
    """从 ORCA 主输出解析 IRC 元数据，对齐 gaussian_frames.extract_irc 的 meta dict。

    ORCA 把 IRC 逐点的能量/梯度直接打在主输出（FORWARD IRC / BACKWARD IRC
    迭代块 + 结尾 IRC PATH SUMMARY），无需追 `_IRC.log`/`*_trj.xyz` 边文件
    （边文件只额外提供逐点坐标，这里不取）。返回键：
    num_points_forward/backward、forward_converged/backward_converged、
    endpoint_energies_hartree（PATH SUMMARY 首/末行能量）、ts_energy_hartree
    （带 "<= TS" 标记行的能量）。找不到 IRC 段时抛 ValueError。
    """
    text = _read_text(log_path)
    blocks = list(_IRCA_BLOCK_RE.finditer(text))
    if not blocks:
        raise ValueError("ORCA 日志中未找到 FORWARD/BACKWARD IRC 段。")

    num_points: dict[str, int] = {"FORWARD": 0, "BACKWARD": 0}
    converged: dict[str, bool] = {"FORWARD": False, "BACKWARD": False}
    for i, m in enumerate(blocks):
        direction = m.group(1)
        seg_end = blocks[i + 1].start() if i + 1 < len(blocks) else len(text)
        # 截到 PATH SUMMARY 之前，避免把汇总表行也数进迭代点
        segment = text[m.end():seg_end]
        summary_idx = segment.find("IRC PATH SUMMARY")
        if summary_idx >= 0:
            segment = segment[:summary_idx]
        n, conv = _parse_irc_direction_block(segment)
        num_points[direction] = n
        converged[direction] = conv

    meta: dict = {
        "num_points_forward": num_points["FORWARD"],
        "num_points_backward": num_points["BACKWARD"],
        "forward_converged": converged["FORWARD"],
        "backward_converged": converged["BACKWARD"],
        "ts_energy_hartree": None,
        "rx_coord_range": None,
        "endpoint_energies_hartree": None,
    }

    # PATH SUMMARY：首行=反应物端、末行=产物端、"<= TS" 行=TS 能量。
    # 用 rfind 取最后一次出现（真实输出在文件尾部；避免命中开头注释/回显里的
    # 同名字样），且从该段标题的分隔线之后开始读数据行。
    summary_idx = text.rfind("IRC PATH SUMMARY")
    if summary_idx >= 0:
        summary_rows = []
        for line in text[summary_idx:].splitlines():
            m = _IRCA_SUMMARY_RE.match(line)
            if m:
                summary_rows.append((float(m.group(2)), "<=" in line and "TS" in line))
        if summary_rows:
            meta["endpoint_energies_hartree"] = (
                summary_rows[0][0],
                summary_rows[-1][0],
            )
            ts_rows = [e for e, is_ts in summary_rows if is_ts]
            if ts_rows:
                meta["ts_energy_hartree"] = ts_rows[0]
    return meta
