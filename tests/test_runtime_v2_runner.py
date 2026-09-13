"""AgentRunner integration: live execution, cancel, restart, wakeup."""

from __future__ import annotations

import asyncio

import pytest

from cloudra.runtime_v2.agent_runner import AgentRunner
from cloudra.runtime_v2.commands import CommandBus
from cloudra.runtime_v2.core import RuntimeCore
from cloudra.runtime_v2.policies import default_stages
from cloudra.runtime_v2.policies.base import ToolCall, ToolResult
from cloudra.runtime_v2.schemas import Command, InvocationProtocol
from cloudra.runtime_v2.turn_pipeline import LLMResponse, TurnPipeline


class ScriptedLLM:
    def __init__(self, responses: list[LLMResponse]) -> None:
        self.responses = list(responses)

    async def complete(self, agent, messages, tools, **_kwargs):
        assert self.responses, "no scripted LLM response left"
        return self.responses.pop(0)


class HangingLLM:
    async def complete(self, agent, messages, tools, **_kwargs):
        await asyncio.Event().wait()


class EchoTools:
    async def execute(self, agent, call: ToolCall) -> ToolResult:
        return ToolResult(is_success=True, summary=f"echo:{call.arguments.get('x')}", data={})


async def _setup(llm) -> tuple[RuntimeCore, object, object]:
    core = RuntimeCore(strict_events=True)
    pipeline = TurnPipeline(
        event_log=core.event_log,
        stages=default_stages(),
        llm=llm,
        tools=EchoTools(),
    )
    core.runner = AgentRunner(core, pipeline)
    bus = CommandBus(core)
    await bus.execute(Command(type="project.create", payload={"name": "runner demo"}))
    project = next(iter(core.projects.values()))
    result = await bus.execute(
        Command(
            type="agent.spawn",
            target={"project_id": project.id},
            payload={"role_id": "coordinator", "query": "solve it"},
        )
    )
    agent = result.data
    # ScriptedLLM 直接发业务工具调用，固定传统协议；
    # 默认 javascript 协议只放 js_exec + 直接控制类。
    agent.settings.invocation_protocol = InvocationProtocol.TRADITIONAL
    return core, project, agent


async def _wait_state(agent, state: str, timeout: float = 2.0):
    deadline = asyncio.get_running_loop().time() + timeout
    while agent.state.value != state:
        if asyncio.get_running_loop().time() > deadline:
            raise AssertionError(f"agent stuck in {agent.state.value}, expected {state}")
        await asyncio.sleep(0.01)


async def _wait_until(predicate, timeout: float = 2.0, what: str = "condition"):
    deadline = asyncio.get_running_loop().time() + timeout
    while not predicate():
        if asyncio.get_running_loop().time() > deadline:
            raise AssertionError(f"timed out waiting for {what}")
        await asyncio.sleep(0.01)


@pytest.mark.asyncio
async def test_thinking_mode_reasoning_is_echoed_on_next_turn():
    """DeepSeek-style thinking mode: after a tool-calling turn the next
    request must send the previous assistant's reasoning_content back."""

    class RecordingLLM:
        def __init__(self) -> None:
            self.calls: list[list[dict]] = []

        async def complete(self, agent, messages, tools, **_kwargs):
            self.calls.append(list(messages))
            if len(self.calls) == 1:
                return LLMResponse(
                    content="Let me look.",
                    reasoning="I should read the file first",
                    tool_calls=[ToolCall(id="tc1", name="echo", arguments={"x": 1})],
                )
            return LLMResponse(content="done", stop_requested=True)

    llm = RecordingLLM()
    core, _, agent = await _setup(llm)
    await _wait_state(agent, "succeeded")
    assert len(llm.calls) == 2
    echoed = [
        m.get("reasoning_content")
        for m in llm.calls[1]
        if m.get("role") == "assistant" and m.get("tool_calls")
    ]
    assert echoed == ["I should read the file first"]


@pytest.mark.asyncio
async def test_runner_executes_tool_then_stops():
    llm = ScriptedLLM(
        [
            LLMResponse(
                content="",
                tool_calls=[ToolCall(id="tc1", name="echo", arguments={"x": 1})],
                stop_requested=False,
            ),
            LLMResponse(content="done", stop_requested=True),
        ]
    )
    core, _, agent = await _setup(llm)
    await _wait_state(agent, "succeeded")
    events = [e.type for e in core.event_log.query_session(agent.id)]
    assert "run.started" in events
    assert "tool.started" in events
    assert "tool.finished" in events
    assert "run.finished" in events
    assert events.index("run.started") < events.index("tool.started") < events.index("run.finished")


@pytest.mark.asyncio
async def test_manual_compaction_rewrites_history(monkeypatch):
    """compact 命令在 run 进行中到达：下个轮次边界统一压缩全部轮次并原子
    安装；压缩后轮次的请求带 assistant 角色的 [Context compact] handoff。"""
    import json as _json

    async def fake_summarize(*args, **_kwargs):
        return _json.dumps(
            {
                "objective": {"text": "SUMMARY", "sources": []},
                "active_requests": [],
                "corrections": [],
                "constraints": [],
                "pending": [],
                "completed": [],
                "failed_attempts": [],
                "evidence": [],
                "next_actions": [],
            },
            ensure_ascii=False,
        )

    monkeypatch.setattr(
        "cloudra.runtime_v2.compaction.summarize_with_agent_settings", fake_summarize
    )

    core = RuntimeCore(strict_events=True)

    class GatedLLM:
        def __init__(self) -> None:
            self.gate = asyncio.Event()
            self.calls: list[list[dict]] = []

        async def complete(self, agent, messages, tools, **_kwargs):
            self.calls.append(list(messages))
            if len(self.calls) == 2:
                await self.gate.wait()
            if len(self.calls) <= 2:
                return LLMResponse(
                    content="",
                    tool_calls=[
                        ToolCall(id=f"tc{len(self.calls)}", name="echo", arguments={"x": 1})
                    ],
                )
            return LLMResponse(content="done", stop_requested=True)

    class BigTools:
        """大工具结果（让轨迹真实长于摘要）；首轮调用时投递第二个用户消息。"""

        def __init__(self) -> None:
            self.delivered = False

        async def execute(self, agent, call, **_kwargs):
            if not self.delivered:
                self.delivered = True
                core.mailbox.deliver(
                    to_session_id=agent.id,
                    project_id=agent.project_id,
                    content="second task",
                    sender="user",
                )
            return ToolResult(is_success=True, summary="x" * 5000, data={})

    llm = GatedLLM()
    pipeline = TurnPipeline(
        event_log=core.event_log,
        stages=default_stages(),
        llm=llm,
        tools=BigTools(),
    )
    core.runner = AgentRunner(core, pipeline)
    bus = CommandBus(core)
    await bus.execute(Command(type="project.create", payload={"name": "runner demo"}))
    project = next(iter(core.projects.values()))
    result = await bus.execute(
        Command(
            type="agent.spawn",
            target={"project_id": project.id},
            payload={"role_id": "coordinator", "query": "solve it"},
        )
    )
    agent = result.data
    agent.settings.invocation_protocol = InvocationProtocol.TRADITIONAL
    await _wait_state(agent, "running")
    await _wait_until(lambda: len(llm.calls) >= 2, what="second LLM call in flight")
    # turn 2 在 gate 中：此时压缩命令到达，应在 turn 3 的轮次边界应用
    await bus.execute(
        Command(
            type="agent.compact",
            target={"session_id": agent.id},
            payload={"keep_recent": 1},
        )
    )
    llm.gate.set()
    await _wait_state(agent, "succeeded")
    types = [e.type for e in core.event_log.query_session(agent.id)]
    assert "compaction.requested" in types
    assert types.index("compaction.requested") < types.index("compaction.started")
    finished = [e for e in core.event_log.query_session(agent.id) if e.type == "compaction.finished"]
    assert finished[-1].data["compacted"] is True
    # The next turn still runs (compact is not a new user message that
    # ends the run).  The handoff is an assistant summary, not role=user.
    third_turn = llm.calls[2]
    compact_msgs = [m for m in third_turn if "[Context compact]" in str(m.get("content"))]
    assert compact_msgs
    assert compact_msgs[0]["role"] == "assistant"
    assert any("SUMMARY" in str(m.get("content")) for m in compact_msgs)


def test_instruction_message_includes_user_and_schedule_reminder():
    from cloudra.runtime_v2.compaction import is_instruction_message

    assert is_instruction_message({"role": "user", "content": "solve it"})
    assert is_instruction_message({"role": "user", "content": "[Reminder] check the gaussian log"})
    # Schedule wake-ups count even if the role is not user.
    assert is_instruction_message({"role": "assistant", "content": "[Reminder] check the gaussian log"})
    assert not is_instruction_message({"role": "assistant", "content": "working"})
    assert not is_instruction_message({"role": "tool", "content": "echo:1"})
    # A compact handoff is not a new instruction — the previous user/schedule stays the boundary.
    assert not is_instruction_message(
        {"role": "assistant", "content": "[Context compact] earlier work was summarized"}
    )
    assert not is_instruction_message(
        {"role": "user", "content": "[Context compact] earlier work was summarized"}
    )


@pytest.mark.asyncio
async def test_spawn_without_query_stays_queued_until_first_message():
    llm = ScriptedLLM([LLMResponse(content="done", stop_requested=True)])
    core = RuntimeCore(strict_events=True)
    pipeline = TurnPipeline(
        event_log=core.event_log,
        stages=default_stages(),
        llm=llm,
        tools=EchoTools(),
    )
    core.runner = AgentRunner(core, pipeline)
    bus = CommandBus(core)
    await bus.execute(Command(type="project.create", payload={"name": "queued spawn"}))
    project = next(iter(core.projects.values()))

    result = await bus.execute(
        Command(
            type="agent.spawn",
            target={"project_id": project.id},
            payload={"role_id": "coordinator"},
        )
    )
    agent = result.data
    assert agent.state.value == "queued"
    await asyncio.sleep(0.02)
    assert agent.state.value == "queued"
    assert "run.started" not in [e.type for e in core.event_log.query_session(agent.id)]

    message = await bus.execute(
        Command(
            type="agent.message",
            target={"session_id": agent.id},
            payload={"content": "start now"},
        )
    )
    assert message.data.state.value == "running"
    await _wait_state(agent, "succeeded")
    types = [e.type for e in core.event_log.query_session(agent.id)]
    assert types.index("agent.message_injected") < types.index("run.started")


@pytest.mark.asyncio
async def test_message_wakes_succeeded_agent_with_new_run():
    llm = ScriptedLLM(
        [
            LLMResponse(content="first done", stop_requested=True),
            LLMResponse(content="second done", stop_requested=True),
        ]
    )
    core, _, agent = await _setup(llm)
    await _wait_state(agent, "succeeded")
    first_runs = [e for e in core.event_log.query_session(agent.id) if e.type == "run.started"]
    assert len(first_runs) == 1

    result = await CommandBus(core).execute(
        Command(
            type="agent.message",
            target={"session_id": agent.id},
            payload={"content": "continue"},
        )
    )
    assert result.data.state == "running"
    await _wait_state(agent, "succeeded")
    assert agent.current_run is None
    messages = [
        e for e in core.event_log.query_session(agent.id) if e.type == "agent.message_injected"
    ]
    assert messages[-1].data["content"] == "continue"
    runs = [e for e in core.event_log.query_session(agent.id) if e.type == "run.started"]
    assert len(runs) == 2
    assert runs[1].run_id != runs[0].run_id


@pytest.mark.asyncio
async def test_wake_during_final_event_flush_reschedules_after_task_done():
    """A wake racing the final flush must not strand RUNNING without a task."""
    llm = ScriptedLLM(
        [
            LLMResponse(content="first", stop_requested=True),
            LLMResponse(content="second", stop_requested=True),
        ]
    )
    core, _, agent = await _setup(llm)
    runner = core.runner
    original_publish = runner._publish_new_events
    delivered = False

    async def publish(cursor):
        nonlocal delivered
        # The outer flush runs after finish_run has made the agent SUCCEEDED,
        # while the runner task itself is still alive.
        if agent.state.value == "succeeded" and not delivered:
            delivered = True
            core.mailbox.deliver(
                to_session_id=agent.id,
                project_id=agent.project_id,
                content="late review decision",
                sender="supervisor",
            )
            core.agent_host.wake(agent, runner=runner)
            assert agent.state.value == "running"
        await asyncio.sleep(0)
        await original_publish(cursor)

    runner._publish_new_events = publish
    await _wait_state(agent, "succeeded")
    assert delivered
    assert len(llm.responses) == 0


@pytest.mark.asyncio
async def test_cancel_terminates_hanging_agent_and_closes_run():
    core, _, agent = await _setup(HangingLLM())
    await _wait_state(agent, "running")
    result = await CommandBus(core).execute(
        Command(type="agent.cancel", target={"session_id": agent.id}, payload={})
    )
    assert result.data.state == "cancelled"
    assert agent.current_run is None
    assert core.runner._tasks.get(agent.id) is None
    types = [e.type for e in core.event_log.query_session(agent.id)]
    assert "agent.cancelled" in types


@pytest.mark.asyncio
async def test_two_projects_run_agents_concurrently_and_stay_isolated():
    core = RuntimeCore(strict_events=True)
    class RoutedLLM:
        """Two concurrent agents share one LLM instance; a shared response
        queue races under interleaved scheduling.  Route by the task message
        (stable across the run's turns) so each agent gets its own script."""

        def __init__(self) -> None:
            self.counts = {"A": 0, "B": 0}

        async def complete(self, agent, messages, tools, **_kwargs):
            tag = "A" if any("task A" in str(m.get("content", "")) for m in messages) else "B"
            self.counts[tag] += 1
            if self.counts[tag] == 1:
                return LLMResponse(
                    content=f"{tag} tool",
                    tool_calls=[ToolCall(id=f"{tag.lower()}1", name="echo", arguments={"x": tag})],
                )
            return LLMResponse(content=f"{tag} done", stop_requested=True)

    pipeline = TurnPipeline(
        event_log=core.event_log,
        stages=default_stages(),
        llm=RoutedLLM(),
        tools=EchoTools(),
    )
    core.runner = AgentRunner(core, pipeline)
    bus = CommandBus(core)
    agents = []
    for name in ("A", "B"):
        await bus.execute(Command(type="project.create", payload={"name": name}))
        project = next(p for p in core.projects.values() if p.name == name)
        result = await bus.execute(
            Command(
                type="agent.spawn",
                target={"project_id": project.id},
                payload={"role_id": "coordinator", "query": f"task {name}"},
            )
        )
        # RoutedLLM 直接发业务工具调用，固定传统协议（默认 javascript 只放
        # js_exec + 直接控制类）。
        result.data.settings.invocation_protocol = InvocationProtocol.TRADITIONAL
        agents.append(result.data)

    deadline = asyncio.get_running_loop().time() + 2.0
    while any(a.state.value != "succeeded" for a in agents):
        assert asyncio.get_running_loop().time() < deadline, "agents did not finish concurrently"
        await asyncio.sleep(0.01)

    for agent in agents:
        events = [e for e in core.event_log.query_session(agent.id) if e.type.startswith(("llm.", "tool."))]
        assert [e.type for e in events][:6] == [
            "llm.request_started",
            "llm.completed",
            "tool.requested",
            "tool.started",
            "tool.result_recorded",
            "tool.finished",
        ]
        other_project_events = [
            e for e in core.event_log if e.project_id != agent.project_id and e.session_id == agent.id
        ]
        assert other_project_events == []


@pytest.mark.asyncio
async def test_restart_schedules_new_run_with_message():
    llm = ScriptedLLM(
        [
            LLMResponse(content="old run", stop_requested=True),
            LLMResponse(content="new run", stop_requested=True),
        ]
    )
    core, _, agent = await _setup(llm)
    await _wait_state(agent, "succeeded")
    result = await CommandBus(core).execute(
        Command(
            type="agent.restart",
            target={"session_id": agent.id},
            payload={"message": "start over"},
        )
    )
    assert result.data.state in {"queued", "running"}
    await _wait_state(agent, "succeeded")
    messages = [
        e for e in core.event_log.query_session(agent.id) if e.type == "agent.message_injected"
    ]
    assert messages[-1].data["content"] == "start over"


class OverflowLLM:
    """Raises a provider-style context-length 400 on the first N calls."""

    def __init__(self, failures: int) -> None:
        self.failures = failures
        self.calls: list[list[dict]] = []

    async def complete(self, agent, messages, tools, **_kwargs):
        self.calls.append(list(messages))
        if self.failures > 0:
            self.failures -= 1
            exc = RuntimeError("This model's maximum context length is 65536 tokens")
            exc.status_code = 400
            raise exc
        return LLMResponse(content="done", stop_requested=True)


@pytest.mark.asyncio
async def test_context_length_error_classification():
    from cloudra.runtime_v2.agent_runner import _is_context_length_error

    overflow = RuntimeError("maximum context length exceeded")
    overflow.status_code = 400
    assert _is_context_length_error(overflow)

    bad_request = RuntimeError("invalid tool schema")
    bad_request.status_code = 400
    assert not _is_context_length_error(bad_request)

    server_error = RuntimeError("boom")
    server_error.status_code = 500
    assert not _is_context_length_error(server_error)


@pytest.mark.asyncio
async def test_context_overflow_triggers_emergency_compaction_then_retry(monkeypatch):
    async def fake_summarize(*args, **_kwargs):
        import json as _json

        return _json.dumps(
            {
                "objective": {"text": "SUMMARY", "sources": []},
                "active_requests": [], "corrections": [], "constraints": [],
                "pending": [], "completed": [], "failed_attempts": [],
                "evidence": [], "next_actions": [],
            },
            ensure_ascii=False,
        )

    monkeypatch.setattr(
        "cloudra.runtime_v2.compaction.summarize_with_agent_settings", fake_summarize
    )

    class LLM:
        def __init__(self) -> None:
            self.calls: list[list[dict]] = []

        async def complete(self, agent, messages, tools, **_kwargs):
            self.calls.append(list(messages))
            if len(self.calls) == 1:
                # Grow the history past the emergency keep_recent so the
                # compaction actually summarizes a head.
                return LLMResponse(
                    content="",
                    tool_calls=[
                        ToolCall(id=f"tc{i}", name="echo", arguments={"x": i})
                        for i in range(12)
                    ],
                )
            if len(self.calls) == 2:
                exc = RuntimeError("This model's maximum context length is 65536 tokens")
                exc.status_code = 400
                raise exc
            if len(self.calls) == 3:
                # Overflow compact must retry the same turn and keep working,
                # not treat the handoff as a new user message that stops.
                return LLMResponse(
                    content="",
                    tool_calls=[ToolCall(id="tc-after", name="echo", arguments={"x": 99})],
                )
            return LLMResponse(content="done", stop_requested=True)

    llm = LLM()
    core, _, agent = await _setup(llm)
    await _wait_state(agent, "succeeded")

    events = list(core.event_log.query_session(agent.id))
    types = [e.type for e in events]
    assert "llm.failed" in types
    overflow = [
        e for e in events if e.type == "compaction.started" and e.data.get("trigger") == "context_overflow"
    ]
    assert len(overflow) == 1
    # The retried turn opened with an assistant handoff (not a user message)
    # and kept working: a tool ran after compact, then the run stopped.
    retried = llm.calls[2]
    compact_msgs = [m for m in retried if "[Context compact]" in str(m.get("content"))]
    assert compact_msgs
    assert compact_msgs[0]["role"] == "assistant"
    assert any("SUMMARY" in str(m.get("content")) for m in compact_msgs)
    stop_compacts = [
        e for e in events if e.type == "compaction.finished" and e.data.get("trigger") == "stop"
    ]
    assert stop_compacts == [], "a user-turn stop must not compact"


@pytest.mark.asyncio
async def test_stop_does_not_compact_after_user(monkeypatch):
    """stop 不再是压缩触发（Task 5）：用户轮次收尾只保留轨迹——压缩只由
    手动 compact / 预算 / overflow 触发。"""

    async def fake_summarize(*args, **_kwargs):
        return "AGENT TAIL SUMMARY"

    monkeypatch.setattr(
        "cloudra.runtime_v2.compaction.summarize_with_agent_settings", fake_summarize
    )

    llm = ScriptedLLM(
        [
            LLMResponse(
                content="",
                tool_calls=[ToolCall(id="tc1", name="echo", arguments={"x": 1})],
            ),
            LLMResponse(content="done", stop_requested=True),
        ]
    )
    core, _, agent = await _setup(llm)
    await _wait_state(agent, "succeeded")
    finished = [
        e
        for e in core.event_log.query_session(agent.id)
        if e.type == "compaction.finished" and e.data.get("trigger") == "stop"
    ]
    assert finished == []


@pytest.mark.asyncio
async def test_second_overflow_after_emergency_compaction_fails_run(monkeypatch):
    async def fake_summarize(*args, **_kwargs):
        import json as _json

        return _json.dumps(
            {
                "objective": {"text": "SUMMARY", "sources": []},
                "active_requests": [], "corrections": [], "constraints": [],
                "pending": [], "completed": [], "failed_attempts": [],
                "evidence": [], "next_actions": [],
            },
            ensure_ascii=False,
        )

    monkeypatch.setattr(
        "cloudra.runtime_v2.compaction.summarize_with_agent_settings", fake_summarize
    )

    class AlwaysOverflowLLM:
        def __init__(self) -> None:
            self.calls = 0

        async def complete(self, agent, messages, tools, **_kwargs):
            self.calls += 1
            if self.calls == 1:
                return LLMResponse(
                    content="",
                    tool_calls=[
                        ToolCall(id=f"tc{i}", name="echo", arguments={"x": i})
                        for i in range(12)
                    ],
                )
            exc = RuntimeError("This model's maximum context length is 65536 tokens")
            exc.status_code = 400
            raise exc

    core, _, agent = await _setup(AlwaysOverflowLLM())
    await _wait_state(agent, "failed")
    types = [e.type for e in core.event_log.query_session(agent.id)]
    # One emergency compaction, then the retried turn fails fast (4xx).
    assert types.count("compaction.started") == 1
    assert types.count("llm.failed") == 2
    assert "run.finished" in types
    finished = [e for e in core.event_log.query_session(agent.id) if e.type == "run.finished"]
    assert finished[-1].data["outcome"] == "failed"


@pytest.mark.asyncio
async def test_compaction_summary_is_appended_to_workspace(monkeypatch, tmp_path):
    async def fake_summarize(*args, **_kwargs):
        import json as _json

        return _json.dumps(
            {
                "objective": {"text": "SUMMARY OF EVERYTHING", "sources": []},
                "active_requests": [], "corrections": [], "constraints": [],
                "pending": [], "completed": [], "failed_attempts": [],
                "evidence": [], "next_actions": [],
            },
            ensure_ascii=False,
        )

    monkeypatch.setattr(
        "cloudra.runtime_v2.compaction.summarize_with_agent_settings", fake_summarize
    )

    class GatedLLM:
        def __init__(self) -> None:
            self.gate = asyncio.Event()
            self.calls: list[list[dict]] = []

        async def complete(self, agent, messages, tools, **_kwargs):
            self.calls.append(list(messages))
            if len(self.calls) == 2:
                await self.gate.wait()
            if len(self.calls) <= 2:
                return LLMResponse(
                    content="",
                    tool_calls=[
                        ToolCall(id=f"tc{len(self.calls)}", name="echo", arguments={"x": 1})
                    ],
                )
            return LLMResponse(content="done", stop_requested=True)

    core = RuntimeCore(strict_events=True)

    class BigTools:
        """大工具结果（让轨迹真实长于摘要）；首轮调用时投递第二个用户消息。"""

        def __init__(self) -> None:
            self.delivered = False

        async def execute(self, agent, call, **_kwargs):
            if not self.delivered:
                self.delivered = True
                core.mailbox.deliver(
                    to_session_id=agent.id,
                    project_id=agent.project_id,
                    content="second task",
                    sender="user",
                )
            return ToolResult(is_success=True, summary="x" * 5000, data={})

    llm = GatedLLM()
    pipeline = TurnPipeline(
        event_log=core.event_log,
        stages=default_stages(),
        llm=llm,
        tools=BigTools(),
    )
    core.runner = AgentRunner(core, pipeline)
    bus = CommandBus(core)
    await bus.execute(Command(type="project.create", payload={"name": "runner demo"}))
    project = next(iter(core.projects.values()))
    result = await bus.execute(
        Command(
            type="agent.spawn",
            target={"project_id": project.id},
            payload={"role_id": "coordinator", "query": "solve it"},
        )
    )
    agent = result.data
    agent.settings.invocation_protocol = InvocationProtocol.TRADITIONAL
    await bus.execute(
        Command(
            type="project.update",
            target={"project_id": agent.project_id},
            payload={"workspace_dir": str(tmp_path)},
        )
    )
    # turn 2 的 LLM 调用在 gate 中：此时压缩命令到达，turn 3 轮次边界应用
    await _wait_until(lambda: len(llm.calls) >= 2, what="second LLM call in flight")
    await bus.execute(
        Command(
            type="agent.compact",
            target={"session_id": agent.id},
            payload={"keep_recent": 1},
        )
    )
    llm.gate.set()
    await _wait_state(agent, "succeeded")

    handoff_file = tmp_path / ".cloudra" / "context_compacts.md"
    assert handoff_file.exists()
    text = handoff_file.read_text(encoding="utf-8")
    assert "SUMMARY OF EVERYTHING" in text
    # The pointer note reached the model on the next turn.
    assert any(
        ".cloudra/context_compacts.md" in str(m.get("content")) for m in llm.calls[2]
    )


@pytest.mark.asyncio
async def test_message_reopen_preserves_session_context():
    """Task 4 契约：终态 agent 收到新消息自动重开 run 时**不再**重置上下文
    （不再落 agent.context_reset）；会话上下文投影跨 run 连续——新 run 的
    请求以上一 run 的实际发送内容为完整前缀。"""
    llm = ScriptedLLM(
        [
            LLMResponse(content="first done", stop_requested=True),
            LLMResponse(content="second done", stop_requested=True),
        ]
    )
    llm_calls: list[list[dict]] = []

    class RecordingLLM:
        async def complete(self, agent, messages, tools, **_kwargs):
            llm_calls.append(list(messages))
            return llm.responses.pop(0)

    core, _, agent = await _setup(RecordingLLM())
    await _wait_state(agent, "succeeded")
    await CommandBus(core).execute(
        Command(
            type="agent.message",
            target={"session_id": agent.id},
            payload={"content": "continue"},
        )
    )
    await _wait_state(agent, "succeeded")
    # 自动重开不落 context_reset（只有显式 restart 命令才重置投影）。
    resets = [
        e for e in core.event_log.query_session(agent.id) if e.type == "agent.context_reset"
    ]
    assert resets == []
    # 跨 run 前缀连续：第二次请求以第一次请求为完整前缀。
    assert len(llm_calls) == 2
    first, second = llm_calls
    assert second[: len(first)] == first
    assert second[-1]["role"] == "user"
    assert second[-1]["content"] == "continue"
    # 投影里的用户消息带 message_id（重试/重启去重锚点）。
    ctx = core.session_contexts[agent.id]
    assert any(
        m.get("role") == "user" and m.get("message_id") for m in ctx.messages
    )


@pytest.mark.asyncio
async def test_restart_command_emits_context_reset_event():
    llm = ScriptedLLM(
        [
            LLMResponse(content="old run", stop_requested=True),
            LLMResponse(content="new run", stop_requested=True),
        ]
    )
    core, _, agent = await _setup(llm)
    await _wait_state(agent, "succeeded")
    await CommandBus(core).execute(
        Command(
            type="agent.restart",
            target={"session_id": agent.id},
            payload={"message": "start over"},
        )
    )
    await _wait_state(agent, "succeeded")
    resets = [
        e for e in core.event_log.query_session(agent.id) if e.type == "agent.context_reset"
    ]
    assert len(resets) == 1
    assert resets[0].data["reason"] == "restart_command"
    assert resets[0].data["previous_outcome"] == "succeeded"
