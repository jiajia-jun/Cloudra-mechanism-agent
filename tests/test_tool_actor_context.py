"""工具侧调用者身份（评审 5.4）：ToolActorContext 是唯一契约。

验收对应：
- 工具不再 import 可执行的 ``cloudra.core.agent.Agent``（静态检查常驻）；
- 生产实现（runtime_v2 的 actor）满足该 Protocol，且能经 pydantic 构造注入；
- 工具真正拿到的是 actor 的身份（workspace / conversation 键），不是 legacy 实例。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

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


def test_legacy_execution_stack_is_deleted():
    """评审 5.4 第 5 条：旧 ``llm_call`` 路径与旧子类已删除，且不得回流。

    `rg "from cloudra.core.agent import" cloudra` 必须为零；两个模块文件不再存在。
    """
    assert not (_CLOUDRA / "core" / "agent.py").exists()
    assert not (_CLOUDRA / "core" / "message_history.py").exists()
    offenders = []
    for path in sorted(_CLOUDRA.rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        for needle in (
            "from cloudra.core.agent import",
            "import cloudra.core.agent",
            "from cloudra.core.message_history import",
            "import cloudra.core.message_history",
        ):
            if needle in text:
                offenders.append(f"{path.relative_to(_CLOUDRA)}: {needle}")
    assert offenders == [], f"legacy execution stack came back: {offenders}"


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

    with pytest.raises(ValidationError) as error:
        GoalSet(subagent=object())
    assert any(
        item["loc"] == ("subagent",) and item["type"] == "is_instance_of"
        for item in error.value.errors()
    )


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
    expected = [{"content": "hold the line", "status": "pending", "id": "t1"}]
    assert output.data["todos"] == expected

    plan_dir = data_dir() / "conversations" / project.id / "plan"
    files = list(plan_dir.glob("*.json"))
    assert len(files) == 1, f"tool did not receive the actor identity: {plan_dir}"
    assert files[0].name.startswith(f"{agent.id}_")
    assert json.loads(files[0].read_text(encoding="utf-8")) == expected


@pytest.mark.asyncio
async def test_same_role_actor_todos_remain_isolated_after_one_actor_updates(tmp_path):
    """同项目同角色两个调用者不能覆盖彼此的持久任务清单。"""
    from cloudra.persistence.paths import data_dir

    core, project, first = await _spawn()
    second = (await CommandBus(core).execute(Command(
        type="agent.spawn", target={"project_id": project.id},
        payload={"role_id": "coordinator", "query": "another task"},
    ))).data
    executor = LegacyToolExecutor(core)
    for agent, content in ((first, "first actor task"), (second, "second actor task")):
        result = await executor.execute(agent, ToolCall(
            id=f"write-{agent.id}", name="todo_write",
            arguments={"todos": [{"id": "stable", "content": content, "status": "pending"}]},
        ))
        assert result.is_success is True, result.summary
    updated = await executor.execute(first, ToolCall(
        id="update-first", name="todo_write",
        arguments={"todos": [{"id": "stable", "content": "first actor task", "status": "done"}]},
    ))
    assert updated.is_success is True, updated.summary

    plan_dir = data_dir() / "conversations" / project.id / "plan"
    files = list(plan_dir.glob("*.json"))
    assert len(files) == 2
    for agent, expected in (
        (first, [{"id": "stable", "content": "first actor task", "status": "done"}]),
        (second, [{"id": "stable", "content": "second actor task", "status": "pending"}]),
    ):
        own_files = [path for path in files if path.name.startswith(f"{agent.id}_")]
        assert len(own_files) == 1
        assert json.loads(own_files[0].read_text(encoding="utf-8")) == expected
