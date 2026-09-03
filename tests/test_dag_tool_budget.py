"""DAG 工具面预算与文档守卫。

工具描述单独收口：字段细节放在 skill / 工具错误反馈，
dag_* 工具描述保持精简，dag-operations skill 必须覆盖完整工具族。
"""

from pathlib import Path

from cloudra.tools import get_tools_lst

ROOT = Path(__file__).resolve().parents[1]

_DAG_TOOL_DESC_BUDGET = 2 * 1024


def test_dag_tool_descriptions_stay_within_budget() -> None:
    dag_tools = [e for e in get_tools_lst() if e.tool_name.startswith("dag_")]
    assert dag_tools, "dag_* tool family must be registered"
    for entry in dag_tools:
        desc = entry.cls.model_fields["tool_description"].default
        size = len(desc.encode())
        assert size <= _DAG_TOOL_DESC_BUDGET, (
            f"{entry.tool_name} tool_description is {size} bytes, over "
            f"{_DAG_TOOL_DESC_BUDGET}; per-field details belong in the "
            "dag-operations skill"
        )


def test_dag_operations_skill_documents_tool_family() -> None:
    skill = (
        ROOT / "cloudra" / "skills" / "dag-operations" / "SKILL.md"
    ).read_text(encoding="utf-8")
    for name in (
        "dag_view",
        "dag_propose_mechanism",
        "dag_accept_mechanism",
        "dag_review_call",
        "dag_bind_evidence",
        "dag_add_species",
        "dag_add_step",
        "dag_update_delivery_element",
        "dag_remove_edge",
        "dag_set_coverage_contract",
        "dag_message_supervisor",
        "dag_delivery_report",
    ):
        assert name in skill, name
    for deleted in (
        "dag_schedule_work",
        "dag_update_process_node",
        "dag_init_from_template",
        "dag_review_evidence",
    ):
        assert deleted not in skill, deleted
    assert "attach_ref" not in skill
    assert "stage_kind" in skill and "dag_review_call" in skill
