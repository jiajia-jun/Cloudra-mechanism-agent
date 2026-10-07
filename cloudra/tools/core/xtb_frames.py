"""xtb 输出日志文本原语：终止判定 + 能量/优化收敛/频率/热化学提取。

与 orca_frames 对齐的纯函数模块（GH #26）。xtb 主输出全部走 stdout
（calculator.sh 重定向到 ``<输入stem>.out``）；cclib 1.8.1 的 xtb parser
结果错误（opt 能量取到最后 cycle、hess 热化学为荒谬值），故终态判定与
字段提取一律走文本权威判据，xtb 引擎在 log_parser 中整体跳过 cclib；
guard（runtime/monitor.py）与 log_parser 共用本模块，行为与 orca_frames
同款：

- 正常终止标记 ``normal termination of xtb``（引擎自报）；
- 优化收敛是独立于终止标记的第二判据（GH #21 同款语义）：未收敛的优化
  仍打印 normal termination，以 ``GEOMETRY OPTIMIZATION CONVERGED`` /
  ``FAILED TO CONVERGE GEOMETRY OPTIMIZATION`` 文本标记为准；
- 能量按文本位置取最后出现的能量行（GH #22 同款语义）：最终
  ``TOTAL ENERGY`` 块 > SUMMARY 的 ``:: total energy`` > opt 周期能量行
  （截断日志时最后的周期能量是最佳估计）。
"""

from __future__ import annotations

import re

_FLOAT = r"([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[DdEe][+-]?\d+)?)"

# ---------------------------------------------------------------------------
# 终止判定与优化收敛（文本权威）
# ---------------------------------------------------------------------------

# xtb 正常终止标记：作业成败的文本权威判据（不依赖 cclib）。
NORMAL_TERMINATION_MARKER = "normal termination of xtb"


def normal_termination(text: str) -> bool:
    """xtb 日志文本是否含正常终止标记（引擎自报）。"""
    return NORMAL_TERMINATION_MARKER in text


# 优化收敛标记：未收敛（跑满最大步数）时 xtb 仍打印 normal termination，
# 终止标记不构成收敛判据（GH #21 同款语义）。两个标记互斥：FAILED 行是
# "CONVERGE GEOMETRY OPTIMIZATION"，
# 不含 "GEOMETRY OPTIMIZATION CONVERGED" 子串。
_OPT_CONVERGED_MARKER = "GEOMETRY OPTIMIZATION CONVERGED"
_OPT_NOT_CONVERGED_MARKER = "FAILED TO CONVERGE GEOMETRY OPTIMIZATION"


def opt_converged(text: str) -> bool | None:
    """几何优化的收敛状态（文本权威）。

    True=收敛，False=达到最大步数未收敛，None=非优化任务或日志判不出
    （两个标记都不出现，如中途被 kill 的优化日志）。
    """
    if _OPT_NOT_CONVERGED_MARKER in text:
        return False
    if _OPT_CONVERGED_MARKER in text:
        return True
    return None


# ---------------------------------------------------------------------------
# 能量 / HOMO-LUMO gap / 偶极
# ---------------------------------------------------------------------------

# 最终块 "| TOTAL ENERGY  -5.0703... Eh"（大小写敏感，避免误中周期行）
_FINAL_ENERGY_RE = re.compile(rf"\| TOTAL ENERGY\s+{_FLOAT}\s+Eh")
# SUMMARY 块 ":: total energy  -5.0703... Eh"
_SUMMARY_ENERGY_RE = re.compile(rf"::\s*total energy\s+{_FLOAT}\s+Eh")
# opt 周期能量行 " * total energy  :    -5.0703... Eh"
_CYCLE_ENERGY_RE = re.compile(rf"\*\s*total energy\s*:\s+{_FLOAT}\s+Eh")


def final_energy_hartree(text: str) -> float | None:
    """取最终能量（Eh），按文本位置取最后出现的能量行。

    优先级由位置自然给出：最终 TOTAL ENERGY 块在文件尾部；截断/未收敛的
    日志没有最终块时，最后的 SUMMARY 能量或 opt 周期能量行是最佳估计
    （GH #22 同款语义）。
    """
    best_pos = -1
    energy: float | None = None
    for pattern in (_FINAL_ENERGY_RE, _SUMMARY_ENERGY_RE, _CYCLE_ENERGY_RE):
        for match in pattern.finditer(text):
            if match.start() > best_pos:
                best_pos = match.start()
                energy = float(match.group(1).replace("D", "E").replace("d", "e"))
    return energy


_HOMO_LUMO_GAP_RE = re.compile(rf"HOMO-LUMO GAP\s+{_FLOAT}\s+eV", re.IGNORECASE)


def homo_lumo_gap_ev(text: str) -> float | None:
    """HOMO-LUMO gap（eV；最终块/SUMMARY 同值，取第一个命中）。"""
    m = _HOMO_LUMO_GAP_RE.search(text)
    return float(m.group(1)) if m else None


# 偶极矩 "full:  x  y  z  tot"（Property Printout 的分子偶极行）
_DIPOLE_FULL_RE = re.compile(rf"full:\s+{_FLOAT}\s+{_FLOAT}\s+{_FLOAT}\s+{_FLOAT}")


def dipole_debye(text: str) -> float | None:
    """分子偶极矩模（Debye；"full:" 行第四列）。"""
    m = _DIPOLE_FULL_RE.search(text)
    return float(m.group(4)) if m else None


# ---------------------------------------------------------------------------
# 热化学（THERMODYNAMIC 块 + 最终块的 ENTHALPY/FREE ENERGY 行）
# ---------------------------------------------------------------------------

# THERMODYNAMIC 块：":: total free energy  -25.4987... Eh" 等
_THERMO_FREE_ENERGY_RE = re.compile(rf"::\s*total free energy\s+{_FLOAT}\s+Eh")
_THERMO_ZPE_RE = re.compile(rf"::\s*zero point energy\s+{_FLOAT}\s+Eh")
_THERMO_G_RRHO_RE = re.compile(rf"::\s*G\(RRHO\) contrib\.\s+{_FLOAT}\s+Eh")
# 最终块 "| TOTAL ENTHALPY  -25.4499... Eh"（hess 日志才有；TOTAL ENERGY /
# TOTAL FREE ENERGY 已由能量/free-energy 正则覆盖，注意前缀不互相误中）
_FINAL_ENTHALPY_RE = re.compile(rf"\| TOTAL ENTHALPY\s+{_FLOAT}\s+Eh")


def _last_float(pattern: re.Pattern, text: str) -> float | None:
    match = None
    for match in pattern.finditer(text):
        pass
    if match is None:
        return None
    return float(match.group(1).replace("D", "E").replace("d", "e"))


def thermochemistry(text: str) -> dict[str, float]:
    """提取 xtb hess 日志的热化学量（Eh），键名与 log_parser 输出字段对齐。

    cclib 对 xtb --hess 日志的热化学属性给出荒谬值（实锤：freeenergy 报
    -693 Eh），权威值在 THERMODYNAMIC 块与最终块：

    - ``total_gibbs_free_energy_hartree`` ← ``:: total free energy``；
    - ``total_enthalpy_hartree`` ← 最终块 ``TOTAL ENTHALPY``；
    - ``zero_point_correction_hartree`` ← ``:: zero point energy``；
    - ``thermal_gibbs_correction_hartree`` ← ``:: G(RRHO) contrib.``。

    无热化学块（非 freq 任务）时返回空 dict——缺数据保持缺失，不编数。
    """
    thermo: dict[str, float] = {}
    free_energy = _last_float(_THERMO_FREE_ENERGY_RE, text)
    if free_energy is not None:
        thermo["total_gibbs_free_energy_hartree"] = free_energy
    enthalpy = _last_float(_FINAL_ENTHALPY_RE, text)
    if enthalpy is not None:
        thermo["total_enthalpy_hartree"] = enthalpy
    zpe = _last_float(_THERMO_ZPE_RE, text)
    if zpe is not None:
        thermo["zero_point_correction_hartree"] = zpe
    g_rrho = _last_float(_THERMO_G_RRHO_RE, text)
    if g_rrho is not None:
        thermo["thermal_gibbs_correction_hartree"] = g_rrho
    return thermo


# ---------------------------------------------------------------------------
# 频率（projected vibrational frequencies 的 eigval 行）
# ---------------------------------------------------------------------------

_EIGVAL_LINE_RE = re.compile(r"^\s*eigval\s*:\s*(.*)$")
# 虚频的另一种写法：数值带 i 后缀（如 "68.66i"），语义等同负值
_EIGVAL_TOKEN_RE = re.compile(rf"^{_FLOAT}(i?)$", re.IGNORECASE)


def _eigval_tokens(line_body: str) -> list[float]:
    values: list[float] = []
    for tok in line_body.split():
        m = _EIGVAL_TOKEN_RE.match(tok)
        if m is None:
            continue
        value = float(m.group(1).replace("D", "E").replace("d", "e"))
        values.append(-abs(value) if m.group(2) else value)
    return values


def vibfreqs_from_text(text: str) -> list[float]:
    """解析最后一个 projected vibrational frequencies 块的频率（cm⁻¹）。

    负值=虚频（i 后缀写法同样解析为负值）；保留打头的平动/转动零频模式
    （与 orca_frames 同款语义），调用方按符号拆分实频/虚频即可。无频率块
    时返回空列表——调用方须保持 None 语义，不得当成零虚频。
    """
    idx = text.rfind("projected vibrational frequencies")
    if idx < 0:
        return []
    freqs: list[float] = []
    for line in text[idx:].splitlines()[1:]:
        m = _EIGVAL_LINE_RE.match(line)
        if m is None:
            if freqs:
                break  # eigval 行连续成块，块外即停
            continue
        freqs.extend(_eigval_tokens(m.group(1)))
    return freqs


# ---------------------------------------------------------------------------
# 任务类型识别
# ---------------------------------------------------------------------------

# opt 周期分隔行 ".............................. CYCLE    8 ..........."
_OPT_CYCLE_RE = re.compile(r"^\.{3,}\s*CYCLE\s+\d+\s*\.{3,}\s*$", re.M)


def detect_job_types_from_text(text: str) -> set[str]:
    """识别 xtb 日志的任务类型，返回 {"opt","freq","sp"} 的子集。

    xtb stdout 不回显 CLI 标志，只能从输出节判定：CYCLE 迭代行/收敛标记
    → opt；projected vibrational frequencies 块 → freq；非优化即 sp。
    TS 搜索无独立输出节，判不出（xtb 的 saddle 优化走外部约束文件）。
    """
    jobs: set[str] = set()
    if (
        _OPT_CONVERGED_MARKER in text
        or _OPT_NOT_CONVERGED_MARKER in text
        or _OPT_CYCLE_RE.search(text)
    ):
        jobs.add("opt")
    if "projected vibrational frequencies" in text:
        jobs.add("freq")
    if "opt" not in jobs:
        jobs.add("sp")
    return jobs


def final_xyz_from_text(text: str) -> str:
    """Read xTB's final structure XYZ block, never a neighboring mutable file."""
    lines = text.splitlines()
    starts = [i for i, line in enumerate(lines) if line.strip().lower() == 'final structure:']
    if not starts:
        return ''
    index = starts[-1] + 1
    while index < len(lines) and (not lines[index].strip() or set(lines[index].strip()) == {'='}):
        index += 1
    if index >= len(lines):
        return ''
    try:
        count = int(lines[index].strip())
    except ValueError:
        return ''
    if count <= 0 or index + count + 2 > len(lines):
        return ''
    xyz = '\n'.join(lines[index:index + count + 2]) + '\n'
    from cloudra.tools.core.irc_path import parse_xyz
    return xyz if parse_xyz(xyz) is not None else ''
