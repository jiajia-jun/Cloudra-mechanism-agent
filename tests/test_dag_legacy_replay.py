"""Regression tests for deleted legacy process tools and operations."""

from pathlib import Path

CODE_ROOT = Path(__file__).resolve().parents[1] / "cloudra"

DELETED_NAMES = (
    "dag_schedule_work",
    "dag_update_process_node",
    "dag_init_from_template",
    "AddLink",
    "PlannedNode",
    "ObservedNode",
    "DependencyEdge",
)


def test_deleted_process_tools_and_operations_do_not_appear_in_code():
    """Grep-gate：已删工具名与操作类不得出现在 cloudra/ 的 *.py 代码里。"""
    offenders = []
    for path in sorted(CODE_ROOT.rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        for name in DELETED_NAMES:
            if name in text:
                offenders.append(f"{path.relative_to(CODE_ROOT)}: {name}")
    assert offenders == []
