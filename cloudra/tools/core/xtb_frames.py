"""xtb 输出日志文本原语：终止判定 + 能量/优化收敛/频率提取。

与 orca_frames 对齐的纯函数模块（GH #26）。xtb 主输出全部走 stdout
（calculator.sh 重定向到 ``<输入stem>.out``），cclib 对 xtb 支持薄弱，
故终态判定与字段提取一律走文本权威判据；guard（runtime/monitor.py）与
log_parser 共用本模块，行为与 orca_frames 同款：

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
# 频率（projected vibrational frequencies 的 eigval 行）
# ---------------------------------------------------------------------------

_EIGVAL_LINE_RE = re.compile(r"^\s*eigval\s*:\s*(.*)$")


def vibfreqs_from_text(text: str) -> list[float]:
    """解析最后一个 projected vibrational frequencies 块的频率（cm⁻¹）。

    负值=虚频；保留打头的平动/转动零频模式（与 orca_frames 同款语义），
    调用方按符号拆分实频/虚频即可。无频率块时返回空列表——调用方须保持
    None 语义，不得当成零虚频。
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
        freqs.extend(float(tok) for tok in m.group(1).split())
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
