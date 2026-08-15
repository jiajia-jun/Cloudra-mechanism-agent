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

from cloudra.tools.capabilities import is_substantive_tool as _capability_is_substantive

# 与 dag_graph.init_from_template 骨架 id 对齐（模板 ≠ 实质机理 / 排产）。
TEMPLATE_PROCESS_NODE_IDS = frozenset(
    {"p_analyze", "p_skill", "p_literature", "p_delivery_design"}
)
TEMPLATE_DELIVERY_NODE_IDS = frozenset({"occ_reactants", "occ_products"})
TEMPLATE_DELIVERY_PLACEHOLDER_LABELS = frozenset(
    {
        "Reactants (SMILES/notes to fill)",
        "Products (SMILES/notes to fill)",
    }
)

# explorer / researcher：机理提交与 Supervisor 排产之前可派发做初调调研。
EARLY_RESEARCH_SUBAGENT_IDS = frozenset({"a-1", "a-3"})

GUIDED_BLOCK_MESSAGE = (
    "[DAG gate] In dag_guided mode, before dispatching a sub-agent, writing/editing files, parsing compute logs, "
    "or submitting compute jobs, you must create a DAG first (at least one node on process or delivery). "
    "Call dag_graph: prefer action=init_from_template, or mutate to add nodes. "
    "Structure tools used to build the graph (smiles_to_mol / image_to_smiles / name_to_structure) are not gated."
)

GUIDED_WORKFLOW_BLOCK_MESSAGE = (
    "[DAG workflow gate] In dag_guided mode, before writing/editing files, starting compute, or dispatching a compute sub-agent, "
    "you must: (1) mutate a preliminary mechanism (delivery is not template placeholders); "
    "(2) wait for Supervisor review and non-template planned work on process. "
    "Early scouting may dispatch explorer(a-1) / researcher(a-3); "
    "dispatch small_mol/dft compute sub-agents only after process is broken down. "
    "gaussian_log_parser and similar tools maintain the graph automatically; use bind_evidence for unexpected cases; "
    "deliver only after mechanism coverage is satisfied."
)

RECORD_WARN_MESSAGE = (
    "[DAG note] In dag_record mode, build the graph before substantive work "
    "(process/delivery are both empty). Use dag_graph action=init_from_template. "
    "This call was allowed."
)


def is_substantive_tool(tool_name: str, arguments: dict[str, Any] | None = None) -> bool:
    """该工具调用是否属于「实质性操作」。语义定义在 tools/capabilities 的注册表投影。"""
    return _capability_is_substantive(tool_name, arguments)


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
