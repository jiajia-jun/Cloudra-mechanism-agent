from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from cloudra.infra.llm_client import ResponseDictWrapper
from cloudra.runtime_v2.commands import CommandBus
from cloudra.runtime_v2.core import RuntimeCore
from cloudra.runtime_v2.schemas import Command
from cloudra.runtime_v2.task_describer import (
    TaskDescriber,
    _extractive_fallback,
    _has_chinese,
    generate_task_description,
)


def test_has_chinese():
    assert _has_chinese("优化反应物构型") is True
    assert _has_chinese("Optimizing reactant geometry") is False
    assert _has_chinese("Run CREST conformer search: 反应物A") is True


def test_extractive_fallback():
    zh_short = _extractive_fallback("优化构型", "zh")
    assert "优化构型" in zh_short
    zh_long = _extractive_fallback("请计算这个长长长长长长长长长长长长长长长长长的分子反应路径", "zh")
    assert len(zh_long) <= 20

    en_short = _extractive_fallback("Optimize reactant", "en")
    assert "Optimize reactant" in en_short


@pytest.mark.asyncio
async def test_generate_task_description_with_mock_llm(tmp_path):
    core = RuntimeCore()
    bus = CommandBus(core)
    ws = tmp_path / "ws"
    await bus.execute(Command(type="project.create", payload={"name": "p1", "workspace_dir": str(ws)}))
    project = next(iter(core.projects.values()))

    res = await bus.execute(
        Command(
            type="agent.spawn",
            target={"project_id": project.id},
            payload={
                "role_id": "coordinator",
                "settings": {"model": "gpt-4o", "api_key": "test-key"},
            },
        )
    )
    agent = res.data

    mock_resp = ResponseDictWrapper({
        "choices": [{"message": {"content": '"正在优化反应物TS过渡态构型"\n'}}],
    })

    with patch("cloudra.infra.llm_client.LLMClient.create_with_retry", new=AsyncMock(return_value=mock_resp)):
        desc = await generate_task_description(agent, "请帮我优化过渡态TS构型", language="zh")
        assert desc == "正在优化反应物TS过渡态构型"


@pytest.mark.asyncio
async def test_task_describer_triggers_on_user_message_and_subagent_spawn(tmp_path):
    core = RuntimeCore()
    bus = CommandBus(core)
    ws = tmp_path / "ws"
    await bus.execute(Command(type="project.create", payload={"name": "p2", "workspace_dir": str(ws)}))
    project = next(iter(core.projects.values()))

    describer = TaskDescriber(core)
    describer.start()

    # 1. Spawn root coordinator
    coord = (
        await bus.execute(
            Command(
                type="agent.spawn",
                target={"project_id": project.id},
                payload={
                    "role_id": "coordinator",
                    "settings": {"model": "gpt-4o", "api_key": "dummy-key"},
                },
            )
        )
    ).data

    mock_coord_resp = ResponseDictWrapper({
        "choices": [{"message": {"content": "正在分析反应机理全貌"}}],
    })

    with patch("cloudra.infra.llm_client.LLMClient.create_with_retry", new=AsyncMock(return_value=mock_coord_resp)):
        # Trigger 1: User sends a message
        await bus.execute(
            Command(
                type="agent.message",
                target={"session_id": coord.id},
                payload={"content": "你好，请帮我分析一下这个镍催化偶联反应的机理", "language": "zh"},
                actor="user",
            )
        )
        # Give async task a brief moment to run
        await asyncio.sleep(0.05)

        updated_coord = core.require_agent(coord.id)
        assert updated_coord.current_task == "正在分析反应机理全貌"

    # Trigger 2: Parent spawns subagent with query
    mock_child_resp = ResponseDictWrapper({
        "choices": [{"message": {"content": "计算过渡态TS-1虚频"}}],
    })

    with patch("cloudra.infra.llm_client.LLMClient.create_with_retry", new=AsyncMock(return_value=mock_child_resp)):
        child = (
            await bus.execute(
                Command(
                    type="agent.spawn",
                    target={"project_id": project.id},
                    payload={
                        "role_id": "dft",
                        "parent_session_id": coord.id,
                        "query": "请对过渡态TS-1进行频率分析，验证虚频",
                        "settings": {"model": "gpt-4o", "api_key": "dummy-key"},
                        "language": "zh",
                    },
                    actor="agent",
                )
            )
        ).data

        await asyncio.sleep(0.05)
        updated_child = core.require_agent(child.id)
        assert updated_child.current_task == "计算过渡态TS-1虚频"

    describer.close()


@pytest.mark.asyncio
async def test_task_describer_ignores_system_notices(tmp_path):
    core = RuntimeCore()
    bus = CommandBus(core)
    ws = tmp_path / "ws"
    await bus.execute(Command(type="project.create", payload={"name": "p3", "workspace_dir": str(ws)}))
    project = next(iter(core.projects.values()))

    describer = TaskDescriber(core)
    describer.start()

    agent = (
        await bus.execute(
            Command(
                type="agent.spawn",
                target={"project_id": project.id},
                payload={"role_id": "coordinator", "settings": {"model": "m", "api_key": "k"}},
            )
        )
    ).data
    agent.current_task = "初始任务"

    # System notice: completion_gate
    await bus.execute(
        Command(
            type="agent.message",
            target={"session_id": agent.id},
            payload={"content": "Task stopped.", "sender": "completion_gate"},
            actor="system",
        )
    )
    await asyncio.sleep(0.02)
    # Remains "初始任务"
    assert core.require_agent(agent.id).current_task == "初始任务"

    describer.close()
