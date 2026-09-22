"""角色身份唯一事实源（评审 5.4 第 2 步）。

验收对应：
- 角色 → DAG 词表 id 的映射只此一张（RoleProfile 投影 + 反向查询都取自它）；
- 旧词表只在**输入边界**归一（launcher/swarm 收到 a-4 → small_mol），
  不再有第二张手写映射表；
- 新增/改名角色不需要同步多处：清单漂移会被这里抓出来。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from cloudra.base.role_identity import (
    LEGACY_AGENT_ID_BY_ROLE,
    legacy_agent_id_for_role,
    role_id_for_legacy_agent_id,
)
from cloudra.runtime_v2.roles import BUILTIN_ROLES, RoleRegistry
from cloudra.subagents import SUBAGENT_REGISTRY

_CLOUDRA = Path(__file__).resolve().parents[1] / "cloudra"


def test_builtin_roles_project_the_single_mapping_table():
    """每个内置角色的 legacy_agent_id 都来自唯一映射表（不是手抄的第二份）。"""
    for role in BUILTIN_ROLES:
        assert role.legacy_agent_id == LEGACY_AGENT_ID_BY_ROLE.get(role.role_id, ""), role.role_id
    # 反向：表里的每个 role_id 都必须是真角色（少了/多了都要红）。
    registry = RoleRegistry()
    assert {role.role_id for role in BUILTIN_ROLES} == set(LEGACY_AGENT_ID_BY_ROLE)
    assert registry.get("small_mol").legacy_agent_id == "a-4"


def test_roundtrip_and_passthrough():
    for role_id, legacy in LEGACY_AGENT_ID_BY_ROLE.items():
        assert legacy_agent_id_for_role(role_id) == legacy
        assert role_id_for_legacy_agent_id(legacy) == role_id
    # 未知值（含已是另一套词表的值）原样透传——读取边界不改写历史身份。
    assert legacy_agent_id_for_role("a-4") == "a-4"
    assert legacy_agent_id_for_role("custom_role") == "custom_role"
    assert role_id_for_legacy_agent_id("small_mol") == "small_mol"
    assert role_id_for_legacy_agent_id("a-99") == "a-99"


def test_legacy_subagent_manifest_derives_ids_from_the_table():
    assert [
        (reg.agent_id, reg.class_name) for reg in SUBAGENT_REGISTRY
    ] == [
        (legacy_agent_id_for_role(reg.class_name), reg.class_name)
        for reg in SUBAGENT_REGISTRY
    ]
    assert [reg.agent_id for reg in SUBAGENT_REGISTRY] == [
        "a-1", "a-2", "a-3", "a-4", "a-5", "a-6", "a-7", "a-8",
    ]


def test_no_second_legacy_id_table_in_the_codebase():
    """静态守卫：除唯一映射表外，任何模块至多出现 **一个** a-N 字面量。

    一个 a-N 字面量是正常用法（如 dag_stage 判 ``!= "a-0"``）；成组的 a-N
    字面量就是又抄了一张映射表。legacy 子 Agent 类（cloudra/subagents/*.py）
    各自声明自己的 id，属待删执行栈（5.4 第 3 步），不在本守卫范围。
    """
    import re as _re

    pattern = _re.compile(r"[\"']a-(?:\d|supervisor)[\"']")
    offenders = []
    for path in sorted(_CLOUDRA.rglob("*.py")):
        if path.name == "role_identity.py" or path.parent.name == "subagents":
            continue
        found = set(pattern.findall(path.read_text(encoding="utf-8")))
        if len(found) > 1:
            offenders.append((str(path.relative_to(_CLOUDRA)), sorted(found)))
    assert offenders == [], f"duplicate legacy-id tables: {offenders}"


@pytest.mark.asyncio
async def test_launcher_accepts_role_id_and_legacy_alias():
    """launcher 参数以 role_id 为首选，历史 a-N 输入在边界归一。

    （身份来源是同一个 RoleProfile；工具参数不再需要调用方自己查表。）
    """
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

    for agent_id, expected in (("small_mol", "small_mol"), ("a-4", "small_mol")):
        result = await handle_native_tool(
            core,
            parent,
            ToolCall(
                id=f"tc_{agent_id}",
                name="subagent_launcher",
                arguments={"agent_id": agent_id, "query": "compute", "context": []},
            ),
        )
        assert result.is_success, result.summary
        child = [
            a for a in core.agents.values() if a.parent_session_id == parent.id
        ][-1]
        assert child.role_id == expected
