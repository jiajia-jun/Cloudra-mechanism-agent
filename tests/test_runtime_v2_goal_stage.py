"""GoalStage 决策纯化（FP 内核化 3d）：goal 的文件 IO 挪到 shell——
TurnPipeline 持有嵌入方注入的 ``goal_reader`` 回调，在调 stage 前读好，
经 ``PipelineContext.goal`` 传入；stage 本体零文件 IO，决策是纯函数。
"""

from __future__ import annotations

import pytest

from cloudra.runtime_v2.events import EventLog
from cloudra.runtime_v2.notices import NoticeManager
from cloudra.runtime_v2.policies.base import ToolResult
from cloudra.runtime_v2.policies.goal_stage import GoalStage, resolve_goal_content
from cloudra.runtime_v2.schemas import (
    AgentCapabilities,
    AgentSession,
    PermissionSet,
    RuntimeSettings,
)
from cloudra.runtime_v2.turn_pipeline import LLMResponse, TurnPipeline


class _FakeLLM:
    def __init__(self) -> None:
        self.seen: list[list[dict]] = []

    async def complete(self, agent, messages, tools, on_delta=None):
        self.seen.append(list(messages))
        return LLMResponse(content="ok")


class _FakeTools:
    async def execute(self, agent, call):
        return ToolResult(is_success=True, summary="ok")


def _agent() -> AgentSession:
    return AgentSession(id="as_goal", project_id="prj_goal", role_id="coordinator", display_name="c")


async def _run_turn(pipeline, agent, notices):
    return await pipeline.run_turn(
        agent=agent,
        run_id="run1",
        settings=RuntimeSettings(),
        capabilities=AgentCapabilities(permissions=PermissionSet(), tools=[]),
        inbox_messages=[{"content": "hi"}],
        history=[],
        notices=notices,
    )


@pytest.mark.asyncio
async def test_goal_reader_feeds_goal_pin():
    """shell 读好的 goal 经 ctx 进 stage：pin 进 notices 并注入本轮消息。"""
    notices = NoticeManager()
    llm = _FakeLLM()
    pipeline = TurnPipeline(
        event_log=EventLog(strict=True),
        stages=[GoalStage()],
        llm=llm,
        tools=_FakeTools(),
        goal_reader=lambda agent: {"objective": "pin me"},
    )
    agent = _agent()
    await _run_turn(pipeline, agent, notices)
    assert notices._pins[agent.id]["goal"].startswith("[Task goal] pin me")
    system = [m for m in llm.seen[0] if m.get("role") == "system"]
    assert any("[Task goal] pin me" in m["content"] for m in system)


@pytest.mark.asyncio
async def test_goal_absent_produces_no_pin():
    """goal_reader 读到空：不 pin 不注入（旧行为是读不到文件，同语义）。"""
    notices = NoticeManager()
    llm = _FakeLLM()
    pipeline = TurnPipeline(
        event_log=EventLog(strict=True),
        stages=[GoalStage()],
        llm=llm,
        tools=_FakeTools(),
        goal_reader=lambda agent: None,
    )
    agent = _agent()
    await _run_turn(pipeline, agent, notices)
    assert "goal" not in notices._pins.get(agent.id, {})
    system = [m for m in llm.seen[0] if m.get("role") == "system"]
    assert not any(m["content"].startswith("[Task goal]") for m in system)


@pytest.mark.asyncio
async def test_goal_replaced_across_turns():
    """goal 每轮重读（replace 语义）：shell 再次读到的值替换旧 pin。"""
    notices = NoticeManager()
    llm = _FakeLLM()
    current = {"goal": {"objective": "v1"}}
    pipeline = TurnPipeline(
        event_log=EventLog(strict=True),
        stages=[GoalStage()],
        llm=llm,
        tools=_FakeTools(),
        goal_reader=lambda agent: current["goal"],
    )
    agent = _agent()
    await _run_turn(pipeline, agent, notices)
    assert "[Task goal] v1" in notices._pins[agent.id]["goal"]
    current["goal"] = {"objective": "v2"}
    await _run_turn(pipeline, agent, notices)
    assert notices._pins[agent.id]["goal"].startswith("[Task goal] v2")


def test_resolve_goal_content_pure():
    """纯决策函数：goal 载荷 → 注入文本（与旧 stage 内联逻辑逐分支一致）。"""
    assert resolve_goal_content(None) == ""
    # 无 objective 的 dict 在 read_goal 侧已被滤成 None；直接传入时保持
    # format_goal 的旧语义（退化到裸 GOAL_MARKER），不做行为漂移。
    assert resolve_goal_content({}) == "[Task goal]"
    assert resolve_goal_content({"objective": "obj"}) == "[Task goal] obj"
    content = resolve_goal_content({"objective": "o", "completion_criteria": "done"})
    assert content.startswith("[Task goal] o")
    assert "Completion criteria: done" in content
