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

import os
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
    """识别 ORCA 日志的任务类型，返回 {"opt","ts","freq","scan","irc","neb","sp"} 的子集。

    ``neb`` 由输入回显的 ``!`` 关键字行识别（``! NEB`` / ``! NEB-TS``）。识别它是为了
    **不让 NEB 日志掉进 ``sp``**：``NEB-TS`` 后续的 TS 优化会让本函数同时给出 ``ts``
    （那时逐帧几何由优化段解析），而只跑路径搜索的 ``! NEB`` 没有优化循环，若不识别就会
    被当成单点——把一整条路径说成一个结构比不报更糟。
    """
    return detect_job_types_from_text(_read_text(log_path))


def detect_job_types_from_text(text: str) -> set[str]:
    """detect_job_types 的文本变体：调用方已读过日志时避免重复 IO。"""
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
    if re.search(r"\bneb(-ts)?\b", keywords):
        jobs.add("neb")
    if re.search(r"\bopt(ts)?\b", keywords) or "GEOMETRY OPTIMIZATION CYCLE" in text:
        jobs.add("opt")
    if re.search(r"\boptts\b", keywords) or "SADDLE POINT SEARCH" in text.upper():
        jobs.add("ts")
    if (
        re.search(r"\b(freq|numfreq|anfreq)\b", keywords)
        or "VIBRATIONAL FREQUENCIES" in text
    ):
        jobs.add("freq")
    if not jobs & {"irc", "scan", "opt", "ts", "neb"}:
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


# ORCA 优化收敛标记：跑满最大步数未收敛时进程仍正常终止（照常打印
# ORCA TERMINATED NORMALLY），终止标记不构成优化收敛的判据（GH #21）。
_OPT_NOT_CONVERGED_MARKER = "The optimization did not converge"
_OPT_CONVERGED_MARKER = "THE OPTIMIZATION HAS CONVERGED"


def opt_converged(text: str) -> bool | None:
    """几何优化/TS 优化的收敛状态（文本权威，不依赖 cclib）。

    True=收敛，False=达到最大步数未收敛，None=非优化任务或日志判不出
    （两个标记都不出现，如中途被 kill 的优化日志）。
    """
    if _OPT_NOT_CONVERGED_MARKER in text:
        return False
    if _OPT_CONVERGED_MARKER in text:
        return True
    return None


_FINAL_ENERGY_RE = re.compile(
    rf"FINAL SINGLE POINT ENERGY(?:\s*\([^)]*\))?\s+{_FLOAT}"
)
# 公开别名：跨模块复用（如 ts_guess 的扫描能量解析）应走公开名，私有名可能重构
FINAL_ENERGY_RE = _FINAL_ENERGY_RE
# 几何优化逐周期能量行："Current Energy ....  -383.544742265 Eh"
_CURRENT_ENERGY_RE = re.compile(rf"Current Energy\s+\.+\s*{_FLOAT}\s+Eh")


def final_energy_hartree(text: str) -> float | None:
    """取最终能量（Eh；含外部 MLIP 变体），按文本位置取最后出现的能量行。

    外部 MLIP（ExtOpt/ProgExt）日志没有 SCF 能量段，唯一能量行是
    ``FINAL SINGLE POINT ENERGY (From external program)``。未收敛的优化
    （max-cycles）只打印一次 FINAL SP（起始几何），逐周期能量以
    ``Current Energy .... <E> Eh`` 给出——此时最后的 Current Energy 才是
    最佳几何能量（GH #22）；收敛的优化会在末几何再打印一次 FINAL SP，
    位置在最后，按位置取最后者天然正确，单点/无 Current Energy 的日志
    行为不变。
    """
    best_pos = -1
    energy: float | None = None
    for pattern in (_FINAL_ENERGY_RE, _CURRENT_ENERGY_RE):
        for match in pattern.finditer(text):
            if match.start() > best_pos:
                best_pos = match.start()
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
# 频率（VIBRATIONAL FREQUENCIES 块，文本权威回退）
# ---------------------------------------------------------------------------

# 模式行："   5:       289.50 cm**-1"；虚频为负值，尾部或带 ***imaginary mode***
# 标记。NORMAL MODES 等后续章节的行不匹配此模式，全局 finditer 天然只命中
# 频率块内的模式行。
_VIBFREQ_LINE_RE = re.compile(rf"^\s*\d+:\s*{_FLOAT}\s+cm\*\*-1", re.M)


def vibfreqs_from_text(text: str) -> list[float]:
    """解析最后一个 VIBRATIONAL FREQUENCIES 块的频率（cm⁻¹，负值=虚频）。

    外部 MLIP（ExtOpt NumFreq）日志无 SCF 块，cclib 常整体解析失败，
    频率只能从文本回退（GH #16）。只取最后一个频率块（Opt+NumFreq 的
    日志可能逐周期多次打印）；与 cclib 的差异是保留打头的平动/转动
    零频模式（cclib 会裁掉），调用方按符号拆分实频/虚频即可。无频率块
    时返回空列表——调用方须保持 None 语义，不得当成零虚频。
    """
    idx = text.rfind("VIBRATIONAL FREQUENCIES")
    if idx < 0:
        return []
    return [float(m.group(1)) for m in _VIBFREQ_LINE_RE.finditer(text, idx)]


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
    """按识别到的任务类型提取关键帧。

    - IRC 的逐点坐标在 trj 边文件（主输出无）：返回空；点数/收敛/能量走 ``extract_irc``。
    - NEB（``! NEB`` / ``! NEB-TS``）：逐图像几何在 ``<作业名>_im<N>.xyz`` 边文件里（主输出
      只有迭代表），这里读那些边文件，并把收敛的 ``<作业名>_NEB-TS_converged.xyz`` 作为带
      ``converged=True`` 的末帧。**读不到边文件时返回空但绝不退化成单点**——把一条路径报成
      一个结构比什么都不报更糟；原因见 ``frames_unavailable_reason``。
    """
    jobs = detect_job_types(log_path)
    if "irc" in jobs:
        return []
    if "neb" in jobs and not (jobs & {"opt", "ts", "scan"}):
        # 逐图像几何在 <作业名>_im<N>.xyz 边文件里；读不到就返回空，但调用方可用
        # frames_unavailable_reason 拿到**具体原因**（不是静默的"没有帧"）
        frames, _reason = _neb_image_frames(_orca_sidecar_roots(log_path, _read_text(log_path)))
        return frames
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


# ---------------------------------------------------------------------------
# NEB 路径几何（逐图像边文件 + 收敛 TS）
# ---------------------------------------------------------------------------

#: ORCA NEB 逐图像边文件注释行：``Coordinates from ORCA-job <job> E <Eh>``
_NEB_IMAGE_SUFFIX = "_im"
#: NEB-TS 收敛的鞍点几何
_NEB_TS_SUFFIX = "_NEB-TS_converged.xyz"


def _neb_image_frames(roots: list[tuple[str, str]]) -> tuple[list[FrameRecord], str | None]:
    """读 NEB 的逐图像边文件，返回 ``(帧, 失败原因)``。

    与 IRC 同一个道理：路径几何**不在主输出里**，而是每个图像一个
    ``<作业名>_im<N>.xyz`` 边文件。日志里读不到几何不等于没有几何——所以这里去找边文件，
    找不到时**带出原因**，绝不静默返回空列表。
    """
    for directory, job in roots:
        if not os.path.isdir(directory):
            continue
        images: list[tuple[int, str]] = []
        for name in os.listdir(directory):
            if not name.startswith(job + _NEB_IMAGE_SUFFIX) or not name.endswith(".xyz"):
                continue
            middle = name[len(job) + len(_NEB_IMAGE_SUFFIX):-len(".xyz")]
            if not middle.isdigit():
                continue
            images.append((int(middle), os.path.join(directory, name)))
        if not images:
            continue
        frames: list[FrameRecord] = []
        for index, path in sorted(images):
            try:
                text = _read_text(path)
            except OSError as exc:
                return [], f"could not read the NEB image file {path}: {exc}"
            lines = text.splitlines()
            if len(lines) < 3:
                return [], f"the NEB image file {path} is too short to be a frame"
            # 原子数在这一节只用来判"是不是一帧"，几何整段原样交出去（下游按 xyz 解析）
            try:
                int(lines[0].strip())
            except ValueError:
                return [], f"the NEB image file {path} does not start with an atom count"
            energy: float | None = None
            tokens = lines[1].split()
            for position, token in enumerate(tokens[:-1]):
                if token == "E":
                    try:
                        energy = float(tokens[position + 1])
                    except ValueError:
                        energy = None
                    break
            frames.append(FrameRecord(
                frame=index, scf_energy_hartree=energy, xyz="\n".join(lines) + "\n",
            ))
        # 收敛的鞍点几何单独作为末帧（converged=True）：那是 NEB-TS 真正交出来的东西
        converged = os.path.join(directory, job + _NEB_TS_SUFFIX)
        if os.path.isfile(converged):
            try:
                text = _read_text(converged)
            except OSError:
                text = ""
            if text:
                frames.append(FrameRecord(
                    frame=len(frames), scf_energy_hartree=None, xyz=text, converged=True,
                ))
        return frames, None
    return [], (
        "no ORCA NEB image file (<job>_im<N>.xyz) was found next to the job; the path geometries "
        "live in those side files, not in the main output"
    )


def frames_unavailable_reason(log_path: str) -> str | None:
    """`extract_frames` 返回空时的**具体原因**；有帧可取或原因不明时返回 None。

    给出这个入口是因为"返回空列表"本身对调用方没有信息量：IRC 的路径点在边文件里、NEB 的
    几何在逐图像边文件里——两者都是"主输出没有但作业确实产出了几何"的情形。调用方需要能把
    这层区分讲给用户，而不是笼统地说"没有关键帧"。
    """
    try:
        text = _read_text(log_path)
    except OSError as exc:
        return f"the log could not be read: {exc}"
    jobs = detect_job_types_from_text(text)
    if "irc" in jobs:
        return (
            "this is an IRC job: its per-point coordinates live in the *_IRC_F_trj.xyz / "
            "*_IRC_B_trj.xyz side files, and the converged endpoints in *_IRC_F.xyz / *_IRC_B.xyz "
            "(use extract_irc_endpoints or ts_guess strict=True)"
        )
    if "neb" in jobs and not (jobs & {"opt", "ts", "scan"}):
        _frames, reason = _neb_image_frames(_orca_sidecar_roots(log_path, text))
        if reason:
            return f"this is an ORCA NEB job, but {reason}"
    return None


# ---------------------------------------------------------------------------
# IRC 端点几何（final endpoint 文件 / F/B trajectory 末帧）
# ---------------------------------------------------------------------------

_ORCA_NAME_RE = re.compile(r"^\s*NAME\s*=\s*(?P<path>\S+)\s*$", re.M)


def _orca_sidecar_roots(log_path: str, text: str) -> list[tuple[str, str]]:
    """ORCA 边文件（IRC 轨迹/端点、NEB 逐图像）的 (目录, 作业名) 候选：优先日志开头输入回显
    的 NAME 记录（harness 捕获的日志名 ``calc-<id>.out.log`` 与 ORCA 作业名无关），
    其次日志自身 stem。"""
    roots: list[tuple[str, str]] = []
    m = _ORCA_NAME_RE.search(text[:200_000])
    if m:
        job = os.path.splitext(m.group("path"))[0]
        roots.append((os.path.dirname(job), os.path.basename(job)))
    stem = os.path.splitext(os.path.basename(log_path))[0]
    roots.append((os.path.dirname(os.path.abspath(log_path)), stem))
    return roots


def _irc_endpoint_sidecar(
    roots: list[tuple[str, str]], suffix: str
) -> tuple[str | None, str | None]:
    """定位一个方向的端点来源：final endpoint 文件优先，trajectory 末帧其次。

    返回 (geometry_ref, origin)；都找不到返回 (None, None)。
    """
    for directory, stem in roots:
        final = os.path.join(directory, f"{stem}{suffix}.xyz")
        if os.path.isfile(final):
            return final, "final_endpoint_file"
    for directory, stem in roots:
        trajectory = os.path.join(directory, f"{stem}{suffix}_trj.xyz")
        if os.path.isfile(trajectory):
            return trajectory, "trajectory_last_frame"
    return None, None


def extract_irc_endpoints(log_path: str) -> dict:
    """定位 ORCA IRC forward/backward 端点几何（不命名 reactant/product）。

    返回 {"forward": {...}, "backward": {...}}，每方向含：
    - geometry_ref：端点几何来源路径（final endpoint 文件或 F/B trajectory），
      无来源时 None；
    - origin：final_endpoint_file / trajectory_last_frame / None；
    - availability：available / unavailable；
    - converged：主输出 IRC 块的收敛标记（无 IRC 段时 None）——块已终止但
      未收敛时端点缺口保持开放，不按固定点数要求补点。
    """
    text = _read_text(log_path)
    roots = _orca_sidecar_roots(log_path, text)
    converged: dict[str, bool | None] = {"FORWARD": None, "BACKWARD": None}
    try:
        meta = extract_irc(log_path)
        converged["FORWARD"] = bool(meta.get("forward_converged"))
        converged["BACKWARD"] = bool(meta.get("backward_converged"))
    except ValueError:
        pass

    result: dict[str, dict] = {}
    for direction, suffix in (("forward", "_IRC_F"), ("backward", "_IRC_B")):
        geometry_ref, origin = _irc_endpoint_sidecar(roots, suffix)
        result[direction] = {
            "geometry_ref": geometry_ref,
            "origin": origin,
            "availability": "available" if geometry_ref else "unavailable",
            "converged": converged["FORWARD" if direction == "forward" else "BACKWARD"],
        }
    return result


def read_endpoint_geometry(endpoint: dict) -> str | None:
    """读取 extract_irc_endpoints 返回的一个端点几何（xyz 文本）。

    final_endpoint_file 直接读取；trajectory_last_frame 取多帧 xyz 的最后一帧。
    解析规则只住在这里，调用方（ts_guess strict 等）不复制。"""
    ref = endpoint.get("geometry_ref")
    if not ref:
        return None
    try:
        with open(ref, encoding="utf-8", errors="replace") as handle:
            text = handle.read()
    except OSError:
        return None
    if endpoint.get("origin") != "trajectory_last_frame":
        return text if text.strip() else None
    frames: list[str] = []
    lines = text.splitlines(keepends=True)
    i = 0
    while i < len(lines):
        stripped = lines[i].strip()
        if stripped.isdigit() and i + 1 < len(lines):
            count = int(stripped)
            block = lines[i : i + 2 + count]
            if len(block) == 2 + count:
                frames.append("".join(block))
            i += 2 + count
        else:
            i += 1
    if frames:
        return frames[-1]
    return text if text.strip() else None
