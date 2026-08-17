"""NoticeManager unit tests: pin/push collect semantics."""

from __future__ import annotations

import pytest

from cloudra.runtime_v2.events import EventLog
from cloudra.runtime_v2.notices import NoticeManager
from cloudra.runtime_v2.policies.base import PolicyResult, ToolResult
from cloudra.runtime_v2.schemas import (
    AgentCapabilities,
    AgentSession,
    PermissionSet,
    RuntimeSettings,
)
from cloudra.runtime_v2.turn_pipeline import LLMResponse, TurnPipeline


def test_pin_is_idempotent_and_replaces():
    notices = NoticeManager()
    notices.pin("s1", "goal", "first")
    notices.pin("s1", "dag", "graph")
    notices.pin("s1", "goal", "second")
    collected = notices.collect("s1")
    assert [m["content"] for m in collected] == ["second", "graph"]
    # pins persist across collect
    again = notices.collect("s1")
    assert [m["content"] for m in again] == ["second", "graph"]


def test_push_is_consumed_once():
    notices = NoticeManager()
    notices.pin("s1", "goal", "stay")
    notices.push("s1", "once")
    first = notices.collect("s1")
    assert [m["content"] for m in first] == ["stay", "once"]
    second = notices.collect("s1")
    assert [m["content"] for m in second] == ["stay"]


def test_pins_precede_pushes():
    notices = NoticeManager()
    notices.push("s1", "ephemeral")
    notices.pin("s1", "a", "pin-a")
    notices.pin("s1", "b", "pin-b")
    collected = notices.collect("s1")
    assert [m["role"] for m in collected] == ["system", "system", "system"]
    assert [m["content"] for m in collected] == ["pin-a", "pin-b", "ephemeral"]


def test_unpin_drops_key():
    notices = NoticeManager()
    notices.pin("s1", "goal", "g")
    notices.unpin("s1", "goal")
    assert notices.collect("s1") == []


class _PinStage:
    name = "pin"

    def __init__(self, notices: NoticeManager) -> None:
        self.notices = notices
        self._pushed = False

    async def before_tool(self, ctx, call):
        return PolicyResult.allow()

    async def after_tool(self, ctx, call, result):
        return None

    async def before_llm(self, ctx, messages):
        self.notices.pin(ctx.agent.id, "goal", "[Task goal] keep me")
        if not self._pushed:
            self.notices.push(ctx.agent.id, "once")
            self._pushed = True


class _FakeLLM:
    def __init__(self) -> None:
        self.seen: list[list[dict]] = []

    async def complete(self, agent, messages, tools, on_delta=None):
        self.seen.append(list(messages))
        return LLMResponse(content="ok")


class _FakeTools:
    async def execute(self, agent, call):
        return ToolResult(is_success=True, summary="ok")


async def _run_turn(pipeline, agent, notices=None):
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
async def test_pipeline_collects_notices_each_turn():
    log = EventLog(strict=True)
    notices = NoticeManager()
    llm = _FakeLLM()
    pipeline = TurnPipeline(
        event_log=log,
        stages=[_PinStage(notices)],
        llm=llm,
        tools=_FakeTools(),
    )
    agent = AgentSession(
        id="as_test",
        project_id="prj",
        role_id="coordinator",
        display_name="c",
    )
    await _run_turn(pipeline, agent, notices)
    first = llm.seen[0]
    system = [m for m in first if m.get("role") == "system"]
    assert any(m["content"] == "[Task goal] keep me" for m in system)
    assert any(m["content"] == "once" for m in system)

    await _run_turn(pipeline, agent, notices)
    second = llm.seen[1]
    system2 = [m["content"] for m in second if m.get("role") == "system"]
    assert "[Task goal] keep me" in system2
    assert "once" not in system2
