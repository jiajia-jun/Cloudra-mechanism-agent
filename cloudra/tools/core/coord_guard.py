"""手写坐标守卫：计算输入/几何文件中的坐标应来自工具，模型逐字键入时给出警告。

背景：机理任务中模型反复出现"手写坐标"行为——把凭记忆或凭感觉拼出的
笛卡尔坐标块直接写进 .gjf/.xyz，绕开 smiles_to_mol / conformer_search /
format_converter / gjf_writer 等结构化工具。prompt 层的禁令不够，这里在
harness 层检测并警告：text_writer / edit_file / bashtools 在写入几何或计算
输入文件前调用本模块检查内容，命中时**放行写入但在返回消息里附警告**。
刻意不硬拦——改 gjf 关键词、补 modredundant 等正当编辑不该被误伤，而且
直接拒绝只会逼模型换一条更隐蔽的路径；让它在结果里读到"这是绕过 supervisor
审查"的明确信号，才能把这个习惯纠正过来。

判定依据是"内容里出现连续坐标行"——从日志提取坐标的正当流程
（sed/grep/format_converter 管道）不会把坐标文本嵌在命令或写入内容里，
只有模型逐字键入才会。模型用 bash 手写坐标时，本质是想绕开 supervisor
对机理证据的审查、把没有计算记录背书的坐标塞进 DAG 系统，警告里会点破
这一点。
"""

from __future__ import annotations

import re

# 元素符号 + 三个浮点数（允许科学计数法），一行一个原子。
_COORD_LINE = re.compile(
    r"^\s*[A-Z][a-z]?\s+"
    r"[-+]?\d+\.\d+(?:[eE][-+]?\d+)?\s+"
    r"[-+]?\d+\.\d+(?:[eE][-+]?\d+)?\s+"
    r"[-+]?\d+\.\d+(?:[eE][-+]?\d+)?\s*$"
)

# 几何/计算输入文件扩展名。刻意不含 .inp（ORCA/CP2K 输入常由 ASE 等脚本
# 程序化生成，误伤面大）与 .md 等报告文件（嵌入 xyz 块属正当内容）。
_GEOMETRY_EXTENSIONS = frozenset({".xyz", ".gjf", ".com"})

# 至少连续这么多坐标行才判定为坐标块，避免误伤零散引用。
MIN_COORD_LINES = 3

# 结构化坐标来源提示 + 绕开审查的定性：手写坐标不与计算记录绑定，
# 挂 DAG 证据时可能不被采信，也绕过了 supervisor 对证据等级的审查。
_GUIDANCE = (
    "Coordinates should come from tools; do not type them by hand or transcribe from memory: "
    "use smiles_to_mol / conformer_search for structure generation; extract coordinates from compute logs with "
    "format_converter (log→xyz) or log_parser; prefer gjf_writer for Gaussian input; "
    "geometry tweaks should use the internal_coordinates Z-matrix flow. "
    "Hand-writing coordinates with bash means trying to bypass Supervisor review of mechanism evidence: handwritten coordinates are not bound "
    "to any compute record and may not be accepted as DAG evidence. "
    "Do not use bash to bypass chemistry tools, and do not try to bypass the DAG system."
)


def count_consecutive_coord_lines(text: str) -> int:
    """文本中最长的连续坐标行数。"""
    best = run = 0
    for line in text.splitlines():
        if _COORD_LINE.match(line):
            run += 1
            if run > best:
                best = run
        else:
            run = 0
    return best


def is_geometry_path(path: str) -> bool:
    lowered = path.strip().lower()
    return any(lowered.endswith(ext) for ext in _GEOMETRY_EXTENSIONS)


def handwritten_coord_warning(text: str, *, path: str | None) -> str | None:
    """返回应附加到工具结果里的警告消息；无嫌疑返回 None。

    调用方**照常执行写入**，只把警告附在返回消息里让模型意识到行为不当。
    path 给定文件路径时只检查几何/计算输入文件；path 为 None（bash 命令）
    时要求命令同时提及几何文件扩展名才警告，避免误伤展示性输出。
    """
    if count_consecutive_coord_lines(text) < MIN_COORD_LINES:
        return None
    if path is not None:
        if not is_geometry_path(path):
            return None
        target = path
    else:
        if not any(ext in text.lower() for ext in _GEOMETRY_EXTENSIONS):
            return None
        target = "a geometry/compute input file"
    return f"[Warning: suspected handwritten coordinates] Wrote a typed-in coordinate block to {target}. {_GUIDANCE}"
