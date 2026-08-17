"""Turn pipeline skeleton tests with fake LLM and tools."""

from __future__ import annotations

import pytest

from cloudra.runtime_v2.core import RuntimeCore
from cloudra.runtime_v2.policies import default_stages
from cloudra.runtime_v2.policies.base import ToolCall, ToolResult
from cloudra.runtime_v2.schemas import (
    AgentCapabilities,
    PermissionSet,
    RuntimeSettings,
)
from cloudra.runtime_v2.turn_pipeline import LLMResponse, TurnPipeline


class FakeLLM:
    def __init__(self, response: LLMResponse) -> None:
        self.response = response
        self.calls = 0

    async def complete(self, agent, messages, tools, **_kwargs):
        self.calls += 1
        return self.response


class FakeTools:
    def __init__(self, result: ToolResult) -> None:
        self.result = result

    async def execute(self, agent, call: ToolCall) -> ToolResult:
        return self.result


async def _spawn_agent(core: RuntimeCore):
    from cloudra.runtime_v2.commands import CommandBus
    from cloudra.runtime_v2.schemas import Command

    await CommandBus(core).execute(Command(type="project.create", payload={"name": "p"}))
    project = next(iter(core.projects.values()))
    await CommandBus(core).execute(
        Command(type="agent.spawn", target={"project_id": project.id}, payload={"role_id": "coordinator"})
    )
    return project, next(iter(core.agents.values()))


@pytest.mark.asyncio
async def test_pipeline_executes_tool_and_emits_ordered_events():
    core = RuntimeCore(strict_events=True)
    _, agent = await _spawn_agent(core)
    run_id = "run_test"
    pipeline = TurnPipeline(
        event_log=core.event_log,
        stages=default_stages(),
        llm=FakeLLM(
            LLMResponse(
                content="",
                tool_calls=[ToolCall(id="tc1", name="echo", arguments={"x": 1})],
                stop_requested=False,
            )
        ),
        tools=FakeTools(ToolResult(is_success=True, summary="ok")),
    )
    capabilities = AgentCapabilities(
        permissions=PermissionSet(), tools=["echo"], can_spawn=False
    )
    outcome = await pipeline.run_turn(
        agent=agent,
        run_id=run_id,
        settings=RuntimeSettings(),
        capabilities=capabilities,
        inbox_messages=[{"content": "hello"}],
    )
    assert outcome.decision == "continue"
    types = [e.type for e in core.event_log.query_session(agent.id) if e.run_id == run_id]
    assert types == ["llm.request_started", "llm.completed", "tool.started", "tool.finished"]


class RecordingLLM:
    def __init__(self) -> None:
        self.messages = None

    async def complete(self, agent, messages, tools, **_kwargs):
        self.messages = list(messages)
        return LLMResponse(content="done", stop_requested=True)


@pytest.mark.asyncio
async def test_prompt_provider_messages_are_prepended():
    core = RuntimeCore(strict_events=True)
    _, agent = await _spawn_agent(core)
    async def provider(**kwargs):
        return [{"role": "system", "content": "ROLE PROMPT"}]

    pipeline = TurnPipeline(
        event_log=core.event_log,
        stages=default_stages(),
        llm=RecordingLLM(),
        tools=FakeTools(ToolResult(is_success=True)),
        prompt_provider=provider,
    )
    await pipeline.run_turn(
        agent=agent,
        run_id="run_prompt",
        settings=RuntimeSettings(),
        capabilities=AgentCapabilities(permissions=PermissionSet(), tools=[]),
        inbox_messages=[{"content": "hello"}],
    )
    messages = pipeline.llm.messages
    assert messages[0] == {"role": "system", "content": "ROLE PROMPT"}
    assert messages[1] == {"role": "user", "content": "hello"}


@pytest.mark.asyncio
async def test_pipeline_stop_without_tool_calls():
    core = RuntimeCore(strict_events=True)
    _, agent = await _spawn_agent(core)
    pipeline = TurnPipeline(
        event_log=core.event_log,
        stages=default_stages(),
        llm=FakeLLM(LLMResponse(content="done", stop_requested=True)),
        tools=FakeTools(ToolResult(is_success=True)),
    )
    outcome = await pipeline.run_turn(
        agent=agent,
        run_id="run_test",
        settings=RuntimeSettings(),
        capabilities=AgentCapabilities(permissions=PermissionSet(), tools=[]),
        inbox_messages=[],
    )
    assert outcome.decision == "stop"


class DeltaLLM:
    async def complete(self, agent, messages, tools, on_delta=None, **_kwargs):
        if on_delta is not None:
            await on_delta("content", "hel")
            await on_delta("content", "lo")
        return LLMResponse(content="hello", stop_requested=True)


@pytest.mark.asyncio
async def test_llm_chunks_published_to_hub_not_logged():
    from cloudra.runtime_v2.events import EventHub

    core = RuntimeCore(strict_events=True)
    _, agent = await _spawn_agent(core)
    hub = EventHub()
    received = []

    async def collect(event):
        received.append(event)

    hub.subscribe(collect)
    pipeline = TurnPipeline(
        event_log=core.event_log,
        stages=default_stages(),
        llm=DeltaLLM(),
        tools=FakeTools(ToolResult(is_success=True)),
        event_hub=hub,
    )
    outcome = await pipeline.run_turn(
        agent=agent,
        run_id="run_test",
        settings=RuntimeSettings(),
        capabilities=AgentCapabilities(permissions=PermissionSet(), tools=[]),
        inbox_messages=[],
    )
    assert outcome.decision == "stop"
    chunks = [e for e in received if e.type == "llm.chunk"]
    assert "".join(e.data["delta"] for e in chunks) == "hello"
    assert all(e.seq == 0 and e.session_id == agent.id for e in chunks)
    # Chunks are transient hub-only events: the log stays free of them.
    assert not [e for e in core.event_log if e.type == "llm.chunk"]


@pytest.mark.asyncio
async def test_goal_stage_pins_goal_into_messages():
    from cloudra.runtime_v2.policies.goal_stage import write_goal

    core = RuntimeCore(strict_events=True)
    _, agent = await _spawn_agent(core)
    write_goal(
        agent,
        {"objective": "optimize caffeine", "completion_criteria": "gap < 0.1", "current_focus": ""},
    )
    pipeline = TurnPipeline(
        event_log=core.event_log,
        stages=default_stages(),
        llm=RecordingLLM(),
        tools=FakeTools(ToolResult(is_success=True)),
    )
    await pipeline.run_turn(
        agent=agent,
        run_id="run_goal",
        settings=RuntimeSettings(),
        capabilities=AgentCapabilities(permissions=PermissionSet(), tools=[]),
        inbox_messages=[{"content": "hello"}],
    )
    system_contents = [m["content"] for m in pipeline.llm.messages if m["role"] == "system"]
    assert any(c.startswith("[Task goal] optimize caffeine") for c in system_contents)


@pytest.mark.asyncio
async def test_goal_stage_noop_without_goal():
    core = RuntimeCore(strict_events=True)
    _, agent = await _spawn_agent(core)
    pipeline = TurnPipeline(
        event_log=core.event_log,
        stages=default_stages(),
        llm=RecordingLLM(),
        tools=FakeTools(ToolResult(is_success=True)),
    )
    await pipeline.run_turn(
        agent=agent,
        run_id="run_nogoal",
        settings=RuntimeSettings(),
        capabilities=AgentCapabilities(permissions=PermissionSet(), tools=[]),
        inbox_messages=[{"content": "hello"}],
    )
    assert not any(
        str(m.get("content", "")).startswith("[Task goal]") for m in pipeline.llm.messages
    )


@pytest.mark.asyncio
async def test_permission_stage_blocks_unavailable_tool():
    core = RuntimeCore(strict_events=True)
    _, agent = await _spawn_agent(core)
    pipeline = TurnPipeline(
        event_log=core.event_log,
        stages=default_stages(),
        llm=FakeLLM(
            LLMResponse(
                tool_calls=[ToolCall(id="tc1", name="not_allowed", arguments={})]
            )
        ),
        tools=FakeTools(ToolResult(is_success=True)),
    )
    outcome = await pipeline.run_turn(
        agent=agent,
        run_id="run_test",
        settings=RuntimeSettings(),
        capabilities=AgentCapabilities(permissions=PermissionSet(), tools=["allowed"]),
        inbox_messages=[],
    )
    assert outcome.message.startswith("blocked by permission")
    types = [e.type for e in core.event_log.query_session(agent.id)]
    # tool.started is always paired: block closes the call with tool.finished.
    assert types[-2:] == ["tool.blocked", "tool.finished"]
    assert core.event_log.query_session(agent.id)[-1].data["is_success"] is False


@pytest.mark.asyncio
async def test_reasoning_persisted_as_thinking_event():
    """LLM 调用的 reasoning 在每轮落一条 agent.thinking（持久、可回放），
    不被瞬时的 llm.chunk 吞掉。"""
    core = RuntimeCore(strict_events=True)
    _, agent = await _spawn_agent(core)
    pipeline = TurnPipeline(
        event_log=core.event_log,
        stages=default_stages(),
        llm=FakeLLM(LLMResponse(content="answer", reasoning="let me think")),
        tools=FakeTools(ToolResult(is_success=True)),
    )
    await pipeline.run_turn(
        agent=agent,
        run_id="run_think",
        settings=RuntimeSettings(),
        capabilities=AgentCapabilities(permissions=PermissionSet(), tools=["*"]),
        inbox_messages=[],
    )
    thinking = core.event_log.query_session(agent.id, types={"agent.thinking"})
    assert len(thinking) == 1
    assert thinking[0].data["content"] == "let me think"


@pytest.mark.asyncio
async def test_intermediate_turn_content_is_persisted():
    """带工具调用的中间轮次，模型正文落持久 agent.message_emitted——
    否则历史轮次的 narration 只活在流式气泡里，turn 结束即被吞。"""
    core = RuntimeCore(strict_events=True)
    _, agent = await _spawn_agent(core)
    pipeline = TurnPipeline(
        event_log=core.event_log,
        stages=default_stages(),
        llm=FakeLLM(
            LLMResponse(
                content="Let me check the file first.",
                tool_calls=[ToolCall(id="tc1", name="allowed", arguments={})],
            )
        ),
        tools=FakeTools(ToolResult(is_success=True)),
    )
    await pipeline.run_turn(
        agent=agent,
        run_id="run_narration",
        settings=RuntimeSettings(),
        capabilities=AgentCapabilities(permissions=PermissionSet(), tools=["*"]),
        inbox_messages=[],
    )
    emitted = core.event_log.query_session(agent.id, types={"agent.message_emitted"})
    assert len(emitted) == 1
    assert emitted[0].data["content"] == "Let me check the file first."


@pytest.mark.asyncio
async def test_intermediate_content_reaches_hub_before_tools_run():
    """SSE 客户端在工具开始前就要收到 agent.message_emitted。

    runner 把整轮（含工具）结束后才 flush 到 hub 时，前端会先看到
    llm.request_started 清空流式气泡，正文还没落进时间线，下一轮工具
    一出现内容就没了。
    """
    core = RuntimeCore(strict_events=True)
    _, agent = await _spawn_agent(core)
    hub_types: list[str] = []

    async def capture(envelope) -> None:
        hub_types.append(envelope.type)

    core.event_hub.subscribe(capture)

    class SlowTools:
        async def execute(self, agent, call):
            assert "agent.message_emitted" in hub_types, (
                "message_emitted must reach the hub before tool execution, "
                f"already seen: {hub_types}"
            )
            return ToolResult(is_success=True)

    pipeline = TurnPipeline(
        event_log=core.event_log,
        stages=default_stages(),
        llm=FakeLLM(
            LLMResponse(
                content="Let me check the file first.",
                tool_calls=[ToolCall(id="tc1", name="allowed", arguments={})],
            )
        ),
        tools=SlowTools(),
        event_hub=core.event_hub,
    )
    await pipeline.run_turn(
        agent=agent,
        run_id="run_hub_flush",
        settings=RuntimeSettings(),
        capabilities=AgentCapabilities(permissions=PermissionSet(), tools=["*"]),
        inbox_messages=[],
    )
    assert "agent.message_emitted" in hub_types


@pytest.mark.asyncio
async def test_stop_turn_content_not_double_emitted():
    """stop 轮正文由 runner 的最终消息承载，管道不重复落事件。"""
    core = RuntimeCore(strict_events=True)
    _, agent = await _spawn_agent(core)
    pipeline = TurnPipeline(
        event_log=core.event_log,
        stages=default_stages(),
        llm=FakeLLM(
            LLMResponse(
                content="final narration",
                tool_calls=[ToolCall(id="tc1", name="stop", arguments={"reason": "done", "final_answer": "x"})],
            )
        ),
        tools=FakeTools(ToolResult(is_success=True)),
    )
    await pipeline.run_turn(
        agent=agent,
        run_id="run_stop_narration",
        settings=RuntimeSettings(),
        capabilities=AgentCapabilities(permissions=PermissionSet(), tools=["*"]),
        inbox_messages=[],
    )
    emitted = core.event_log.query_session(agent.id, types={"agent.message_emitted"})
    assert emitted == []


@pytest.mark.asyncio
async def test_stop_turn_final_message_is_model_text_not_tool_json():
    """stop 轮的用户可见消息必须是模型自己的陈述；模型没写正文时回退
    stop 输出的 message（含 reason/[ANSWER]），而不是输出 schema 的 JSON dump。"""
    core = RuntimeCore(strict_events=True)
    _, agent = await _spawn_agent(core)

    class StopWithData:
        async def execute(self, agent, call):
            return ToolResult(
                is_success=True,
                summary='{"stopped": true, "message": "Task stopped. Reason: done"}',
                data={"stopped": True, "message": "Task stopped. Reason: done"},
            )

    pipeline = TurnPipeline(
        event_log=core.event_log,
        stages=default_stages(),
        llm=FakeLLM(
            LLMResponse(
                content="机理是协同的周环反应。",
                tool_calls=[ToolCall(id="tc1", name="stop", arguments={"reason": "done"})],
            )
        ),
        tools=StopWithData(),
    )
    outcome = await pipeline.run_turn(
        agent=agent,
        run_id="run_final_text",
        settings=RuntimeSettings(),
        capabilities=AgentCapabilities(permissions=PermissionSet(), tools=["*"]),
        inbox_messages=[],
    )
    assert outcome.decision == "stop"
    assert outcome.content == "机理是协同的周环反应。"

    # 模型没写正文 → 回退 stop 的 message（保留 [ANSWER]/reason 语义）
    pipeline2 = TurnPipeline(
        event_log=core.event_log,
        stages=default_stages(),
        llm=FakeLLM(
            LLMResponse(
                content="",
                tool_calls=[ToolCall(id="tc2", name="stop", arguments={"reason": "done"})],
            )
        ),
        tools=StopWithData(),
    )
    outcome2 = await pipeline2.run_turn(
        agent=agent,
        run_id="run_final_fallback",
        settings=RuntimeSettings(),
        capabilities=AgentCapabilities(permissions=PermissionSet(), tools=["*"]),
        inbox_messages=[],
    )
    assert outcome2.content == "Task stopped. Reason: done"
