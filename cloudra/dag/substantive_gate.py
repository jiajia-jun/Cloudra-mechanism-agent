"""实质性操作前的 DAG 门槛（dag_guided 硬拦 / dag_record 软警告）。

两级门槛（仅 guided 硬拦；record 在空图时软警告一次）：

1. **空图**：process / delivery 均无节点时拦全部实质性工具。
2. **工作流就绪（B）**：须 delivery 已有实质机理，且 process 已有非模板
   Supervisor 排产，才放行写文件 / 开算 / 非调研子 Agent。

例外：explorer (a-1) / researcher (a-3) 在图非空后可提前派发（初调调研），
仍受空图门槛约束——先建骨架再派调研。

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

# 与 dag_graph.init_from_template 骨架 id 对齐（模板 ≠ 实质机理 / 排产）。
TEMPLATE_PROCESS_NODE_IDS = frozenset(
    {"p_analyze", "p_skill", "p_literature", "p_delivery_design"}
)
TEMPLATE_DELIVERY_NODE_IDS = frozenset({"occ_reactants", "occ_products"})
TEMPLATE_DELIVERY_PLACEHOLDER_LABELS = frozenset(
    {
        "反应物（待填 SMILES/说明）",
        "产物（待填 SMILES/说明）",
    }
)

# explorer / researcher：机理提交与 Supervisor 排产之前可派发做初调调研。
EARLY_RESEARCH_SUBAGENT_IDS = frozenset({"a-1", "a-3"})

GUIDED_BLOCK_MESSAGE = (
    "【DAG 门槛】dag_guided 模式下，派子 Agent、写/改文件、解析计算日志、"
    "提交计算任务等实质性操作前，必须先创建 DAG（process 或 delivery 至少一侧有节点）。"
    "请先调用 dag_graph：优先 action=init_from_template，或用 mutate 添加节点。"
    "smiles_to_mol / image_to_smiles / name_to_structure 等建图用结构工具不受此限。"
)

GUIDED_WORKFLOW_BLOCK_MESSAGE = (
    "【DAG 工作流门槛】dag_guided 下，写/改文件、开算、派计算类子 Agent 之前，"
    "须先完成：① mutate 提交初步机理（delivery 非模板占位）；"
    "② 等待 Supervisor 审核并在 process 上安排非模板计划任务。"
    "初调调研可派 explorer(a-1) / researcher(a-3)；"
    "按 process 拆解后再派 small_mol/dft 等计算子 Agent。"
    "log_parser 等会自动维护图；意外情况可用 bind_evidence；"
    "机理覆盖满足后方可交付。"
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


def is_early_research_subagent_call(
    tool_name: str, arguments: dict[str, Any] | None = None
) -> bool:
    """SubAgentLauncher/Swarm 且目标为 explorer/researcher。"""
    if tool_name not in {"SubAgentLauncher", "SubAgentSwarm"}:
        return False
    agent_id = str((arguments or {}).get("agent_id") or "").strip()
    return agent_id in EARLY_RESEARCH_SUBAGENT_IDS


def delivery_has_substance(snapshot: Any) -> bool:
    """delivery 是否已有实质机理（模板空槽不算）。"""
    delivery = getattr(snapshot, "delivery", None)
    if delivery is None:
        return False
    if getattr(delivery, "edges", None):
        return True
    for node in getattr(delivery, "nodes", None) or ():
        node_id = getattr(node, "node_id", "") or ""
        if node_id not in TEMPLATE_DELIVERY_NODE_IDS:
            return True
        smiles = getattr(node, "smiles", None)
        if smiles and str(smiles).strip():
            return True
        label = str(getattr(node, "label", "") or "").strip()
        if label and label not in TEMPLATE_DELIVERY_PLACEHOLDER_LABELS:
            return True
    return False


def process_has_supervisor_plan(snapshot: Any) -> bool:
    """process 是否已有非模板 planned 排产（模板骨架不算）。"""
    process = getattr(snapshot, "process", None)
    if process is None:
        return False
    for node in getattr(process, "nodes", None) or ():
        if getattr(node, "node_type", None) != "planned":
            continue
        node_id = getattr(node, "node_id", "") or ""
        if node_id not in TEMPLATE_PROCESS_NODE_IDS:
            return True
    return False


def workflow_ready(snapshot: Any) -> bool:
    """实质机理已提交且 Supervisor 已排产。"""
    return delivery_has_substance(snapshot) and process_has_supervisor_plan(snapshot)
