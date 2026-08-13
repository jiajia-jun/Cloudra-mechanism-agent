"""Prompt 体积预算：角色 prompt 单文件上限 10KiB。

工具描述仍单独收口：op data shapes 放在 skill / 工具错误反馈，
不要为过预算去压缩角色 prompt。
"""

from pathlib import Path

from cloudra.tools.Plantool.dag_graph import DagGraph

ROOT = Path(__file__).resolve().parents[1]
PROMPTS = ROOT / "cloudra" / "prompts"

_DEFAULT_BUDGET = 10 * 1024
# supervisor.md 含排产 JSON 示例，略超 10KiB；不要为过预算去删示例。
_BUDGETS = {
    "supervisor.md": 12 * 1024,
}

# dag_graph 是最大的工具描述：op data shapes 已移到 dag-operations skill，
# 描述里只留 action 一句话 + 关键约束。
_DAG_GRAPH_DESC_BUDGET = 2 * 1024


def test_prompt_files_stay_within_budget() -> None:
    for path in sorted(PROMPTS.glob("*.md")):
        budget = _BUDGETS.get(path.name, _DEFAULT_BUDGET)
        size = path.stat().st_size
        assert size <= budget, (
            f"{path.name} is {size} bytes, over its {budget}-byte budget"
        )


def test_dag_graph_description_stays_within_budget() -> None:
    desc = DagGraph.model_fields["tool_description"].default
    size = len(desc.encode())
    assert size <= _DAG_GRAPH_DESC_BUDGET, (
        f"dag_graph tool_description is {size} bytes, over "
        f"{_DAG_GRAPH_DESC_BUDGET}; per-op data shapes belong in the "
        "dag-operations skill"
    )


def test_dag_operations_skill_documents_mutation_shapes() -> None:
    skill = (
        ROOT / "cloudra" / "skills" / "dag-operations" / "SKILL.md"
    ).read_text(encoding="utf-8")
    # 阶段 6 起 SKILL 收敛为意图手册：attach_ref/add_link 不再向 agent 宣传
    # （attach_ref 由 bind_evidence 取代，add_link 是 Supervisor 簿记）
    for op in (
        "add_node",
        "add_edge",
        "remove_edge",
        "update_node",
        "update_edge",
        "bind_evidence",
    ):
        assert op in skill
    assert "attach_ref" not in skill
    assert "add_link" not in skill
    assert "evidence_role" in skill and "assignee" in skill
