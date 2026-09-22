"""子 Agent 设置继承（评审 5.5）：唯一解析点、字段分类与派发回执。

关键约定：
- 只有任务授权/运行边界继承父 agent；model/protocol 等由 child 的 role 与
  项目默认决定（父的 override 不传染）；
- 分类必须覆盖 RuntimeSettings 的每个字段（新增字段不归类 = 测试失败）；
- 回执是非敏感摘要，api_key/base_url 永不出现，且能解释 child 的设置来源。
"""

from __future__ import annotations

import asyncio
import json

import pytest

from cloudra.runtime_v2.adapters import LegacyToolExecutor
from cloudra.runtime_v2.agent_runner import AgentRunner
from cloudra.runtime_v2.child_settings import (
    INHERITED_FIELDS,
    NEVER_INHERITED_FIELDS,
    ROLE_DEFAULTED_FIELDS,
    SOURCE_INHERITED,
    SOURCE_OVERRIDE,
    SOURCE_ROLE,
    SOURCE_SCHEMA,
    resolve_child_settings,
)
from cloudra.runtime_v2.commands import CommandBus
from cloudra.runtime_v2.core import RuntimeCore
from cloudra.runtime_v2.policies import default_stages
from cloudra.runtime_v2.policies.base import ToolCall
from cloudra.runtime_v2.roles import RoleRegistry
from cloudra.runtime_v2.schemas import (
    AgentSession,
    Command,
    InvocationProtocol,
    OrchestrationMode,
    Project,
    RuntimeSettings,
)
from cloudra.runtime_v2.subagent_bridge import handle_native_tool
from cloudra.runtime_v2.turn_pipeline import LLMResponse, TurnPipeline

_ROLES = RoleRegistry()


def _parent(**settings) -> AgentSession:
    return AgentSession(
        id="as_parent",
        project_id="prj",
        role_id="coordinator",
        display_name="Coordinator",
        settings=RuntimeSettings(**settings),
    )


def test_field_classification_covers_every_setting_and_is_disjoint():
    """新增设置字段必须在分类里显式归类——否则继承行为会静默漂移。"""
    classified = set(INHERITED_FIELDS) | set(ROLE_DEFAULTED_FIELDS) | set(NEVER_INHERITED_FIELDS)
    assert classified == set(RuntimeSettings.model_fields), (
        "RuntimeSettings 字段与 child_settings 分类不一致："
        f"未归类={set(RuntimeSettings.model_fields) - classified} "
        f"多余={classified - set(RuntimeSettings.model_fields)}"
    )
    total = len(INHERITED_FIELDS) + len(ROLE_DEFAULTED_FIELDS) + len(NEVER_INHERITED_FIELDS)
    assert len(classified) == total, "字段分类有重叠"


def test_patch_carries_only_authorization_boundaries():
    parent = _parent(
        yolo=True,
        unattended=True,
        schedule_mode=True,
        clean_context=True,
        orchestration_mode=OrchestrationMode.DAG_GUIDED,
        model="parent-model",
        base_url="https://key@example.invalid/v1",
        reasoning_effort="high",
        invocation_protocol=InvocationProtocol.TRADITIONAL,
        api_key="sk-parent-secret",
    )
    plan = resolve_child_settings(
        parent, project=Project(id="prj", name="p"), role=_ROLES.require("small_mol")
    )
    assert set(plan.patch.model_fields_set) == set(INHERITED_FIELDS)
    payload = plan.spawn_payload_settings()
    assert payload == {
        "orchestration_mode": "dag_guided",
        "yolo": True,
        "unattended": True,
        "schedule_mode": True,
        "clean_context": True,
    }
    # 父的 model / 协议 / 秘密都不在补丁里。
    assert "model" not in payload and "api_key" not in payload
    assert "invocation_protocol" not in payload


def test_sources_explain_where_role_defaulted_fields_come_from():
    parent = _parent(model="parent-model")
    project = Project(id="prj", name="p")
    project.settings.defaults.model = "project-model"
    role = RoleRegistry().update("small_mol", {"default_settings": {"reasoning_effort": "medium"}})
    plan = resolve_child_settings(parent, project=project, role=role)
    assert plan.sources["orchestration_mode"] == SOURCE_INHERITED
    assert plan.sources["model"] == "project_default"
    assert plan.sources["reasoning_effort"] == SOURCE_ROLE
    assert plan.sources["invocation_protocol"] == SOURCE_SCHEMA
    assert plan.sources["api_key"] == SOURCE_SCHEMA


def test_override_wins_in_source_annotation():
    from cloudra.runtime_v2.schemas import RuntimeSettingsPatch

    plan = resolve_child_settings(
        _parent(),
        project=Project(id="prj", name="p"),
        role=_ROLES.require("small_mol"),
        override=RuntimeSettingsPatch(model="pinned-model", api_key="sk-system"),
    )
    assert plan.sources["model"] == SOURCE_OVERRIDE
    assert plan.sources["api_key"] == SOURCE_OVERRIDE


# ------------------------------------------------------------------ 集成：真派发


class _EchoLLM:
    async def complete(self, agent, messages, tools, **_kwargs):
        if agent.role_id == "coordinator":
            return LLMResponse(content="asked", stop_requested=True)
        return LLMResponse(content=f"{agent.role_id} done", stop_requested=True)


async def _core_with_parent(*, parent_settings: dict) -> tuple[RuntimeCore, object, AgentSession]:
    core = RuntimeCore(strict_events=True)
    pipeline = TurnPipeline(
        event_log=core.event_log,
        stages=default_stages(),
        llm=_EchoLLM(),
        tools=LegacyToolExecutor(core),
    )
    core.runner = AgentRunner(core, pipeline)
    bus = CommandBus(core)
    await bus.execute(Command(type="project.create", payload={"name": "child-settings"}))
    project = next(iter(core.projects.values()))
    result = await bus.execute(
        Command(
            type="agent.spawn",
            target={"project_id": project.id},
            payload={"role_id": "coordinator", "query": "solve it", "settings": parent_settings},
        )
    )
    return core, project, result.data


async def _wait_terminal(agent, timeout: float = 10.0) -> None:
    """等 child 自己跑完再收尾：把「取消一个正在调度中的 run」的噪音日志去掉。"""
    from cloudra.runtime_v2.schemas import AgentState

    terminal = {AgentState.SUCCEEDED, AgentState.FAILED, AgentState.CANCELLED}
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while agent.state not in terminal:
        if loop.time() > deadline:
            raise AssertionError(f"child stuck in {agent.state.value}")
        await asyncio.sleep(0.01)


async def _cancel(core: RuntimeCore) -> None:
    from cloudra.runtime_v2.schemas import AgentState

    bus = CommandBus(core)
    for agent in list(core.agents.values()):
        if agent.state is not AgentState.CANCELLED:
            await bus.execute(
                Command(type="agent.cancel", target={"session_id": agent.id}, payload={})
            )


@pytest.mark.asyncio
async def test_child_resolves_role_defaults_not_parent_overrides():
    """父单独钉了 protocol/model，child 仍按项目/角色默认解析——且回执可解释。"""
    core, project, parent = await _core_with_parent(
        parent_settings={"invocation_protocol": "traditional", "model": "parent-model"}
    )
    assert parent.settings.invocation_protocol is InvocationProtocol.TRADITIONAL
    try:
        result = await handle_native_tool(
            core,
            parent,
            ToolCall(id="tc1", name="subagent_launcher",
                     arguments={"agent_id": "a-4", "query": "opt the molecule", "is_wait": False}),
        )
        child_id = result.data["session_id"]
        child = core.agents.get(child_id)
        receipt = result.data["settings"]

        # child 不继承父的 model/协议（模型与协议由 role/项目默认决定）。
        assert child.settings.invocation_protocol is InvocationProtocol.JAVASCRIPT
        assert child.settings.model != "parent-model"
        # 回执能直接解释来源与最终值（协议用哪个、谁的默认）。
        assert receipt["role_id"] == "small_mol"
        assert receipt["invocation_protocol"] == "javascript"
        assert receipt["model"] == child.settings.model
        assert receipt["sources"]["invocation_protocol"] == SOURCE_SCHEMA
        assert receipt["sources"]["orchestration_mode"] == SOURCE_INHERITED
        assert receipt["orchestration_mode"] == "standard"
        # 人类可读回执里也带一行摘要，模型无需解析结构化数据。
        assert "protocol=javascript" in result.summary
        assert "role=small_mol" in result.summary
        await _wait_terminal(core.agents[child_id])
    finally:
        await _cancel(core)


@pytest.mark.asyncio
async def test_child_inherits_parent_authorization_flags_and_hides_secrets():
    core, project, parent = await _core_with_parent(
        parent_settings={
            "invocation_protocol": "traditional",
            "yolo": True,
            "unattended": True,
            "schedule_mode": True,
            "clean_context": True,
            "orchestration_mode": "dag_record",
            "api_key": "sk-parent-secret",
        }
    )
    try:
        result = await handle_native_tool(
            core,
            parent,
            ToolCall(id="tc1", name="subagent_launcher",
                     arguments={"agent_id": "a-4", "query": "opt", "is_wait": False}),
        )
        child = core.agents[result.data["session_id"]]
        assert child.settings.yolo is True
        assert child.settings.unattended is True
        assert child.settings.schedule_mode is True
        assert child.settings.clean_context is True
        assert child.settings.orchestration_mode is OrchestrationMode.DAG_RECORD
        # 秘密不继承：child 自己的 key 只在显式提供/桥接层补全时才存在。
        assert child.settings.api_key != "sk-parent-secret"

        receipt = result.data["settings"]
        blob = json.dumps(receipt)
        assert "sk-parent-secret" not in blob
        assert "api_key" not in receipt and "base_url" not in receipt
        await _wait_terminal(child)
    finally:
        await _cancel(core)
