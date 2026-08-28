"""量子化学日志引擎嗅探：区分 Gaussian / ORCA 输出。

供 log_parser / format_converter 选择后端解析器。检测基于头部横幅，
纯文本、不做完整解析，开销为读取前 16 KiB。
"""

from __future__ import annotations

_HEAD_BYTES = 16384

_GAUSSIAN_MARKERS = (
    "Entering Gaussian System",
    "Gaussian, Inc.",
    "Gaussian 09",
    "Gaussian 16",
)
_ORCA_MARKERS = (
    "O   R   C   A",
    "O  R  C  A",
    "* O   R   C   A *",
    "ORCA VERSION",
    "An ab initio, DFT and semiempirical SCF-MO package",
)


def _read_head(log_path: str) -> str:
    with open(log_path, encoding="utf-8", errors="replace") as f:
        return f.read(_HEAD_BYTES)


def detect_qm_engine(log_path: str) -> str:
    """识别日志来源程序，返回 "gaussian" / "orca" / "unknown"。"""
    try:
        head = _read_head(log_path)
    except OSError:
        return "unknown"
    for marker in _GAUSSIAN_MARKERS:
        if marker in head:
            return "gaussian"
    for marker in _ORCA_MARKERS:
        if marker in head:
            return "orca"
    return "unknown"
