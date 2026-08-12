"""实质性操作前的 DAG 门槛（dag_guided 硬拦 / dag_record 软警告）。

空的 ``ensure_bundle`` 不算建图：process 或 delivery 至少一侧已有节点才放行。
建图所需的 SMILES/结构工具不在门槛内。
"""

from __future__ import annotations

from typing import Any

from cloudra.tools.core.bash_habit_guard import (
    _direct_compute_program,
    bash_file_write_warning,
)

# 实质性操作：派工、改工作区、开算、解析计算日志等。
# SMILES/结构准备类工具刻意不在此列（建图需要它们）。
SUBSTANTIVE_TOOLS = frozenset(
    {
        "SubAgentLauncher",
        "SubAgentSwarm",
        "text_writer",
        "edit_file",
        "gaussian_log_parser",
        "submit_compute_job",
        "gjf_writer",
        "conformer_search",
        "ts_guess",
        "thermo_analysis",
        "electronic_analysis",
        "ir_processor",
        "nmr_processor",
        "device.workspace.apply_patch",
        "device.documents.write",
    }
)

# bashtools 仅在命令像写文件 / 直调量化时视为实质性
_BASH_TOOL = "bashtools"

GUIDED_BLOCK_MESSAGE = (
    "【DAG 门槛】dag_guided 模式下，派子 Agent、写/改文件、解析计算日志、"
    "提交计算任务等实质性操作前，必须先创建 DAG（process 或 delivery 至少一侧有节点）。"
    "请先调用 dag_graph：优先 action=init_from_template，或用 mutate 添加节点。"
    "smiles_to_mol / image_to_smiles / name_to_structure 等建图用结构工具不受此限。"
)

RECORD_WARN_MESSAGE = (
    "【DAG 提醒】dag_record 模式下建议先建图再执行实质性操作"
    "（当前 process/delivery 均为空）。可用 dag_graph action=init_from_template。"
    "本次调用已放行。"
)


def is_substantive_tool(tool_name: str, arguments: dict[str, Any] | None = None) -> bool:
    """该工具调用是否属于「实质性操作」。"""
    if tool_name in SUBSTANTIVE_TOOLS:
        return True
    if tool_name != _BASH_TOOL:
        return False
    args = arguments or {}
    command = str(args.get("command") or "")
    if not command.strip():
        return False
    if bash_file_write_warning(command):
        return True
    if _direct_compute_program(command):
        return True
    return False
