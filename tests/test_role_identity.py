"""角色身份唯一事实源（评审 5.4 第 2 步）。

验收对应：
- 角色 → DAG 词表 id 的映射只此一张（RoleProfile 投影取自它）；
- 运行时输入使用语义 role_id，旧词表仅留在 DAG 存储边界；
- 新增/改名角色不需要同步多处：清单漂移会被这里抓出来。
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from cloudra.base.role_identity import (
    LEGACY_AGENT_ID_BY_ROLE,
    legacy_agent_id_for_role,
)
from cloudra.runtime_v2.roles import BUILTIN_ROLES, RoleRegistry

_CLOUDRA = Path(__file__).resolve().parents[1] / "cloudra"


def _legacy_id_literals(source: str) -> set[str]:
    """Return exact legacy-id string literals, ignoring comments and prose."""
    values: set[str] = set()

    class LiteralVisitor(ast.NodeVisitor):
        def visit_JoinedStr(self, node: ast.JoinedStr) -> None:
            return

        def visit_Constant(self, node: ast.Constant) -> None:
            if isinstance(node.value, str):
                values.add(node.value)

    LiteralVisitor().visit(ast.parse(source))
    return {
        value
        for value in values
        if value == "a-supervisor"
        or (
            value.startswith("a-")
            and len(value) == 3
            and value.removeprefix("a-").isdigit()
        )
    }


def test_legacy_id_literal_scanner_ignores_comments_and_embedded_text():
    source = '''
# "a-1" and "a-2" are documentation, not a mapping.
NOTE = "mentions a-3 in prose"
PRIMARY = "a-4"
SUPERVISOR = "a-supervisor"
DYNAMIC = f"a-5{suffix}"
ALSO_DYNAMIC = f"a-6{suffix}"
'''
    assert _legacy_id_literals(source) == {"a-4", "a-supervisor"}


def test_builtin_roles_project_the_single_mapping_table():
    """每个内置角色的 legacy_agent_id 都来自唯一映射表（不是手抄的第二份）。"""
    for role in BUILTIN_ROLES:
        assert role.legacy_agent_id == LEGACY_AGENT_ID_BY_ROLE.get(role.role_id, ""), role.role_id
    # 反向：表里的每个 role_id 都必须是真角色（少了/多了都要红）。
    registry = RoleRegistry()
    assert {role.role_id for role in BUILTIN_ROLES} == set(LEGACY_AGENT_ID_BY_ROLE)
    assert registry.get("small_mol").legacy_agent_id == "a-4"


def test_dag_identity_projection_and_passthrough():
    for role_id, legacy in LEGACY_AGENT_ID_BY_ROLE.items():
        assert legacy_agent_id_for_role(role_id) == legacy
    # 未知值（含已是另一套词表的值）原样透传——读取边界不改写历史身份。
    assert legacy_agent_id_for_role("a-4") == "a-4"
    assert legacy_agent_id_for_role("custom_role") == "custom_role"


def test_no_second_legacy_id_table_in_the_codebase():
    """静态守卫：除唯一映射表外，任何模块至多出现 **一个** a-N 字面量。

    一个 a-N 字面量是正常用法（如 dag_stage 判 ``!= "a-0"``）；成组的 a-N
    字面量就是又抄了一张映射表。
    """
    offenders = []
    for path in sorted(_CLOUDRA.rglob("*.py")):
        if path.name == "role_identity.py":
            continue
        found = _legacy_id_literals(path.read_text(encoding="utf-8"))
        if len(found) > 1:
            offenders.append((str(path.relative_to(_CLOUDRA)), sorted(found)))
    assert offenders == [], f"duplicate legacy-id tables: {offenders}"


@pytest.mark.asyncio
async def test_launcher_semantic_role_preserves_dag_legacy_identity():
    """语义 role_id 派单保留同一 RoleProfile 的 DAG legacy 身份边界。"""
    from cloudra.runtime_v2.commands import CommandBus
    from cloudra.runtime_v2.core import RuntimeCore
    from cloudra.runtime_v2.schemas import Command

    core = RuntimeCore(strict_events=True)
    bus = CommandBus(core)
    await bus.execute(Command(type="project.create", payload={"name": "p"}))
    project = next(iter(core.projects.values()))
    parent = (
        await bus.execute(
            Command(
                type="agent.spawn",
                target={"project_id": project.id},
                payload={"role_id": "coordinator", "query": "go"},
            )
        )
    ).data

    from cloudra.runtime_v2.policies.base import ToolCall
    from cloudra.runtime_v2.subagent_bridge import handle_native_tool

    result = await handle_native_tool(
        core,
        parent,
        ToolCall(
            id="tc_small_mol",
            name="subagent_launcher",
            arguments={"role_id": "small_mol", "query": "compute", "context": []},
        ),
    )
    assert result.is_success, result.summary
    children = [a for a in core.agents.values() if a.parent_session_id == parent.id]
    assert len(children) == 1
    assert children[0].role_id == "small_mol"
    assert core.roles.require(children[0].role_id).legacy_agent_id == "a-4"
