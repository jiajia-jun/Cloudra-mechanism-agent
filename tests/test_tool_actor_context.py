"""工具侧调用者身份（评审 5.4）：ToolActorContext 是唯一契约。

验收对应：
- 工具不再 import 可执行的 ``cloudra.core.agent.Agent``（静态检查常驻）；
- 生产实现（runtime_v2 的 actor）满足该 Protocol，且能经 pydantic 构造注入；
- 工具真正拿到的是 actor 的身份（workspace / conversation 键），不是 legacy 实例。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from cloudra.base.tool_actor import ToolActorContext
from cloudra.runtime_v2.adapters import LegacyToolExecutor, _LegacyAgentBridge
from cloudra.runtime_v2.commands import CommandBus
from cloudra.runtime_v2.core import RuntimeCore
from cloudra.runtime_v2.policies.base import ToolCall
from cloudra.runtime_v2.schemas import Command

_CLOUDRA = Path(__file__).resolve().parents[1] / "cloudra"


def test_no_tool_module_imports_the_executable_agent():
    """工具层不得再依赖 legacy 执行类（评审验收：`rg` 只剩迁移边界，最好为零）。"""
    offenders = []
    for path in sorted((_CLOUDRA / "tools").rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        if "cloudra.core.agent" in text:
            offenders.append(str(path.relative_to(_CLOUDRA)))
    assert offenders == [], f"tools still import the legacy Agent: {offenders}"


async def _spawn(role_id: str = "coordinator"):
    core = RuntimeCore(strict_events=True)
    bus = CommandBus(core)
    await bus.execute(Command(type="project.create", payload={"name": "p"}))
    project = next(iter(core.projects.values()))
    agent = (
        await bus.execute(
            Command(
                type="agent.spawn",
                target={"project_id": project.id},
                payload={"role_id": role_id, "query": "go"},
            )
        )
    ).data
    return core, project, agent


@pytest.mark.asyncio
async def test_production_actor_satisfies_the_protocol(tmp_path):
    core, project, agent = await _spawn()
    actor = _LegacyAgentBridge(agent, str(tmp_path / "ws"))
    assert isinstance(actor, ToolActorContext)
    assert actor.id == agent.id
    assert actor.session_id == agent.id
    assert actor.name == "coordinator"
    assert actor.conversation_id == project.id
    assert actor.working_directory == str(tmp_path / "ws")
    assert actor.orchestration_mode == agent.settings.orchestration_mode.value
    assert actor.permission_all() != 0  # 权限位投影非空


@pytest.mark.asyncio
async def test_tool_model_accepts_the_protocol_and_rejects_others(tmp_path):
    """字段类型是 Protocol：合规对象可直接构造，非合规对象被 pydantic 拒绝
    （这正是旧实现必须用 object.__setattr__ 绕过校验的原因，现已消除）。"""
    from cloudra.tools.Plantool.goal import GoalSet

    core, project, agent = await _spawn()
    actor = _LegacyAgentBridge(agent, str(tmp_path / "ws"))
    tool = GoalSet(subagent=actor)
    assert tool.subagent is actor

    with pytest.raises(Exception):
        GoalSet(subagent=object())


@pytest.mark.asyncio
async def test_tool_receives_actor_identity_through_the_executor(tmp_path):
    """经真实执行器跑一个用到身份的工具：per-agent 存储键来自 actor。"""
    from cloudra.persistence.paths import data_dir

    core, project, agent = await _spawn()
    executor = LegacyToolExecutor(core)
    output = await executor.execute(
        agent,
        ToolCall(
            id="tc1",
            name="todo_write",
            arguments={"todos": [{"content": "hold the line", "status": "pending"}]},
        ),
    )
    assert output.is_success is True, output.summary

    plan_dir = data_dir() / "conversations" / project.id / "plan"
    files = sorted(p.name for p in plan_dir.glob("*.json"))
    assert files, f"tool did not receive the actor identity: {plan_dir}"
    assert any(agent.id in name for name in files)
