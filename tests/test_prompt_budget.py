"""Prompt 体积预算：规则只在权威位置说一次，prompt 只留"什么时候做什么"。

防止规则细节重新膨胀回 prompt / 工具描述——细节应按需加载
（skill、工具错误反馈），而不是塞进每个请求都发送的静态文本。
"""

from pathlib import Path

from cloudra.tools.Plantool.dag_graph import DagGraph

ROOT = Path(__file__).resolve().parents[1]
PROMPTS = ROOT / "cloudra" / "prompts"

# 单文件预算（字节）：Coordinator 信息量最大，Supervisor 次之，其余角色从简。
_BUDGETS = {
    "coordinator.md": 8 * 1024,
    "supervisor.md": 5 * 1024,
}
_DEFAULT_BUDGET = 6 * 1024

# dag_graph 是最大的工具描述：op data shapes 已移到 dag-operations skill，
# 描述里只留 action 一句话 + 关键约束。
_DAG_GRAPH_DESC_BUDGET = 2 * 1024


def test_prompt_files_stay_within_budget() -> None:
    for path in sorted(PROMPTS.glob("*.md")):
        budget = _BUDGETS.get(path.name, _DEFAULT_BUDGET)
        size = path.stat().st_size
        assert size <= budget, (
            f"{path.name} is {size} bytes, over its {budget}-byte budget; "
            "move detail into skills or tool error feedback instead"
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
    for op in (
        "add_node",
        "add_edge",
        "remove_edge",
        "update_node",
        "update_edge",
        "attach_ref",
        "add_link",
    ):
        assert op in skill
    assert "evidence_role" in skill and "assignee" in skill
