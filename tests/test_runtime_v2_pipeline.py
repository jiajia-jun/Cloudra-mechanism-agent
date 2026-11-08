"""Turn pipeline skeleton tests with fake LLM and tools."""

from __future__ import annotations

import pytest

from cloudra.runtime_v2.core import RuntimeCore
from cloudra.runtime_v2.policies import default_stages
from cloudra.runtime_v2.policies.base import ToolCall, ToolResult
from cloudra.runtime_v2.schemas import (
    AgentCapabilities,
    InvocationProtocol,
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
    agent = next(iter(core.agents.values()))
    # 本文件测试用 FakeLLM 直接发业务工具调用，固定传统协议；
    # 默认 javascript 协议只放 js_exec + 直接控制类。
    agent.settings.invocation_protocol = InvocationProtocol.TRADITIONAL
    return project, agent


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
    assert types == [
        "llm.request_started",
        "llm.completed",
        "tool.requested",
        "tool.started",
        "tool.result_recorded",
        "tool.finished",
    ]


class RecordingLLM:
    def __init__(self) -> None:
        self.messages = None

    async def complete(self, agent, messages, tools, **_kwargs):
        self.messages = list(messages)
        return LLMResponse(content="done", stop_requested=True)


@pytest.mark.asyncio
async def test_prompt_provider_messages_are_prepended():
    """新契约（Task 2）：prompt provider vend per-run ContextPrefix owner，
    首轮转 install（静态前缀置于请求最前），同一上下文恰好安装一次。"""
    core = RuntimeCore(strict_events=True)
    _, agent = await _spawn_agent(core)

    class StaticPrefix:
        def __init__(self):
            self.installs = 0

        def matches(self, history):
            return False

        async def install(self):
            self.installs += 1
            return [{"role": "system", "content": "ROLE PROMPT"}]

        async def refresh(self):
            return []

    class PrefixProvider:
        def __init__(self):
            self.prefix = StaticPrefix()

        def begin_context(self, **_kwargs):
            return self.prefix

    provider = PrefixProvider()
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
    assert provider.prefix.installs == 1


@pytest.mark.asyncio
async def test_pipeline_stop_without_tool_calls():
    """无 tool_calls 的纯文本回复在管道层产出 decision="stop"——但这只是结束
    *意向*：是否允许结束由 runner 收尾前的统一结束门禁裁决（与显式 stop 同一
    边界，Task 4A；见 tests/test_runtime_v2_completion_gate.py）。管道层不再
    自行放行，也不再被 dag stage 在 before_tool 拦截 stop。"""
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
    request = next(e for e in received if e.type == "llm.request_started")
    assert received.index(request) < received.index(chunks[0])
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
    assert "is not in this agent's capabilities" in outcome.message
    assert outcome.content == ""
    types = [e.type for e in core.event_log.query_session(agent.id)]
    # A blocked call is never admitted: tool.requested + diagnostic, closed by
    # tool.finished — no tool.started is emitted for it.
    assert types[-3:] == ["tool.requested", "tool.blocked", "tool.finished"]
    assert "tool.started" not in types
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
async def test_stop_turn_preserves_narration_and_model_authored_final_answer():
    """停止工具不覆盖原文，正文与工具内的模型答复各提交一次。"""
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
    assert [event.data["content"] for event in emitted] == ["final narration", "x"]


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

    # No narration: carry the declared candidate, never the stop receipt.
    pipeline2 = TurnPipeline(
        event_log=core.event_log,
        stages=default_stages(),
        llm=FakeLLM(
            LLMResponse(
                content="",
                tool_calls=[ToolCall(id="tc2", name="stop", arguments={"reason": "done", "final_answer": "245.8"})],
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
    assert outcome2.content == "245.8"


@pytest.mark.asyncio
async def test_loop_detected_after_threshold_identical_calls():
    """同一 run 内连续 3 次（阈值，spec 未定）相同 name+arguments 的调用
    触发 loop.detected 审计事件，并向模型 push 换思路的软警告（不 block）。"""
    from cloudra.runtime_v2.notices import NoticeManager

    core = RuntimeCore(strict_events=True)
    _, agent = await _spawn_agent(core)
    notices = NoticeManager()
    pipeline = TurnPipeline(
        event_log=core.event_log,
        stages=default_stages(),
        llm=FakeLLM(
            LLMResponse(tool_calls=[ToolCall(id="tc1", name="echo", arguments={"x": 1})])
        ),
        tools=FakeTools(ToolResult(is_success=True, summary="ok")),
        notices=notices,
    )
    capabilities = AgentCapabilities(permissions=PermissionSet(), tools=["*"])
    for turn in range(3):
        outcome = await pipeline.run_turn(
            agent=agent,
            run_id="run_loop",
            settings=RuntimeSettings(),
            capabilities=capabilities,
            inbox_messages=[] if turn else [{"content": "go"}],
        )
        assert outcome.decision == "continue"  # 软护栏：不阻断调用
        # This standalone pipeline has no ContextBroker to commit notice
        # consumption; acknowledge the batch supplied to this model request.
        _, through = notices.pending_batch(agent.id)
        if through is not None:
            notices.apply_consumed(agent.id, through)
    events = core.event_log.query_session(agent.id, types={"loop.detected"})
    assert len(events) == 1
    assert events[0].data == {"tool_name": "echo", "repeat": 3}
    warnings = notices.collect_batch(agent.id, fresh=False)
    assert len(warnings) == 1
    assert any("Loop detected" in warning["content"] for warning in warnings)


@pytest.mark.asyncio
async def test_loop_guard_resets_on_different_call_or_new_run():
    """不同参数/不同工具打断连续计数；新 run 重新计数。"""
    core = RuntimeCore(strict_events=True)
    _, agent = await _spawn_agent(core)
    capabilities = AgentCapabilities(permissions=PermissionSet(), tools=["*"])
    calls = [
        ToolCall(id="tc1", name="echo", arguments={"x": 1}),
        ToolCall(id="tc2", name="echo", arguments={"x": 1}),
        ToolCall(id="tc3", name="echo", arguments={"x": 2}),  # 参数不同 → 重置
        ToolCall(id="tc4", name="echo", arguments={"x": 1}),
    ]
    pipeline = TurnPipeline(
        event_log=core.event_log,
        stages=default_stages(),
        llm=FakeLLM(LLMResponse(tool_calls=calls)),
        tools=FakeTools(ToolResult(is_success=True, summary="ok")),
    )
    await pipeline.run_turn(
        agent=agent,
        run_id="run_a",
        settings=RuntimeSettings(),
        capabilities=capabilities,
        inbox_messages=[{"content": "go"}],
    )
    assert core.event_log.query_session(agent.id, types={"loop.detected"}) == []

    # 新 run 重新计数（同一 pipeline 实例，与生产共享单例一致）：
    # 同样的调用再来两次不触发
    pipeline.llm = FakeLLM(
        LLMResponse(
            tool_calls=[
                ToolCall(id="tc5", name="echo", arguments={"x": 1}),
                ToolCall(id="tc6", name="echo", arguments={"x": 1}),
            ]
        )
    )
    await pipeline.run_turn(
        agent=agent,
        run_id="run_b",
        settings=RuntimeSettings(),
        capabilities=capabilities,
        inbox_messages=[],
    )
    assert core.event_log.query_session(agent.id, types={"loop.detected"}) == []


@pytest.mark.asyncio
async def test_narration_enters_context_before_tool_execution_even_if_tool_is_cancelled():
    """A completed provider reply cannot remain UI-only while a tool runs."""
    import asyncio

    core = RuntimeCore(strict_events=True)
    _, agent = await _spawn_agent(core)
    text = 'visible-before-tool-marker'
    observed_context = []

    class CancelTools:
        async def execute(self, agent, call):
            emitted = core.event_log.query_session(agent.id, types={'agent.message_emitted'})
            assert [e.data['content'] for e in emitted] == [text]
            observed_context.extend(core.contexts.current_messages(agent.id))
            raise asyncio.CancelledError

    pipeline = TurnPipeline(
        event_log=core.event_log, event_hub=core.event_hub,
        event_writer=core.event_writer, stages=default_stages(),
        llm=FakeLLM(LLMResponse(content=text, tool_calls=[ToolCall(id='cancel-call', name='allowed', arguments={})])),
        tools=CancelTools(),
    )
    with pytest.raises(asyncio.CancelledError):
        await pipeline.run_turn(
            agent=agent, run_id='cancel-narration', settings=RuntimeSettings(),
            capabilities=AgentCapabilities(permissions=PermissionSet(), tools=['*']),
            inbox_messages=[], context_broker=core.contexts,
        )
    assert [m['content'] for m in observed_context if m['role'] == 'assistant'] == [text]
    assert not any(m.get('tool_calls') for m in observed_context)
