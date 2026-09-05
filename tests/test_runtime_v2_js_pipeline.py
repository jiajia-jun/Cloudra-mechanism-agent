"""Turn-pipeline routing for the JavaScript invocation protocol.

Route validation, one-program-per-response and mixed-response rejection are
tested with an injected fake JS shell; the lifecycle end-to-end path uses
the real QuickJS host (named skip when its prerequisites are absent).
"""

from __future__ import annotations

import asyncio
import shutil
from pathlib import Path

import pytest

from cloudra.runtime_v2.core import RuntimeCore
from cloudra.runtime_v2.policies.base import ToolCall, ToolResult
from cloudra.runtime_v2.schemas import (
    AgentCapabilities,
    InvocationProtocol,
    PermissionSet,
    RuntimeSettings,
)
from cloudra.runtime_v2.turn_pipeline import LLMResponse, TurnPipeline

HOST_DIR = Path(__file__).resolve().parent.parent / "cloudra" / "runtime_v2" / "js_host"
HOST_AVAILABLE = (
    shutil.which("node") is not None
    and (HOST_DIR / "node_modules" / "quickjs-emscripten" / "package.json").is_file()
)


class FakeLLM:
    def __init__(self, response: LLMResponse) -> None:
        self.response = response

    async def complete(self, agent, messages, tools, **_kwargs):
        return self.response


class FakeTools:
    def __init__(self, result: ToolResult | None = None) -> None:
        self.result = result or ToolResult(True, "ok", {"message": "final"})
        self.calls: list[ToolCall] = []

    async def execute(self, agent, call: ToolCall) -> ToolResult:
        self.calls.append(call)
        return self.result


class FakeJSRuntime:
    def __init__(self, result: ToolResult | None = None) -> None:
        self.calls: list[ToolCall] = []
        self.result = result or ToolResult(
            True, "program completed", {"status": "completed", "outputs": [], "calls": []}
        )

    async def execute(self, ctx, call: ToolCall) -> ToolResult:
        self.calls.append(call)
        return self.result


async def _spawn_agent(core: RuntimeCore, protocol: InvocationProtocol | None = None):
    from cloudra.runtime_v2.commands import CommandBus
    from cloudra.runtime_v2.schemas import Command

    await CommandBus(core).execute(Command(type="project.create", payload={"name": "p"}))
    project = next(iter(core.projects.values()))
    await CommandBus(core).execute(
        Command(type="agent.spawn", target={"project_id": project.id}, payload={"role_id": "coordinator"})
    )
    agent = next(iter(core.agents.values()))
    if protocol is not None:
        agent.settings.invocation_protocol = protocol
    return agent


def _pipeline(core: RuntimeCore, response: LLMResponse, tools=None, js_runtime=None) -> TurnPipeline:
    return TurnPipeline(
        event_log=core.event_log,
        stages=[],
        llm=FakeLLM(response),
        tools=tools or FakeTools(),
        js_runtime=js_runtime,
    )


def _caps() -> AgentCapabilities:
    return AgentCapabilities(permissions=PermissionSet(), tools=["echo", "stop"], can_spawn=False)


async def _run(pipeline: TurnPipeline, agent) -> object:
    return await pipeline.run_turn(
        agent=agent,
        run_id="run_test",
        settings=RuntimeSettings(),
        capabilities=_caps(),
        inbox_messages=[{"content": "go"}],
    )


@pytest.mark.asyncio
async def test_traditional_rejects_js_exec_without_executing():
    core = RuntimeCore(strict_events=True)
    agent = await _spawn_agent(core)  # traditional is the default
    js = FakeJSRuntime()
    pipeline = _pipeline(
        core, LLMResponse(tool_calls=[ToolCall("t1", "js_exec", {"code": "text(1);"})]),
        js_runtime=js,
    )
    outcome = await _run(pipeline, agent)
    assert outcome.decision == "continue"
    assert js.calls == []
    assert len(outcome.tool_exchanges) == 1
    _, result = outcome.tool_exchanges[0]
    assert not result.is_success
    assert "protocol_error[js_exec_in_traditional]" in result.summary
    assert [e.type for e in core.event_log if e.type.startswith("program.")] == []


@pytest.mark.asyncio
async def test_js_mode_rejects_top_level_business_call():
    core = RuntimeCore(strict_events=True)
    agent = await _spawn_agent(core, InvocationProtocol.JAVASCRIPT)
    tools = FakeTools()
    pipeline = _pipeline(
        core, LLMResponse(tool_calls=[ToolCall("t1", "echo", {"x": 1})]), tools=tools
    )
    outcome = await _run(pipeline, agent)
    assert outcome.decision == "continue"
    assert tools.calls == []
    _, result = outcome.tool_exchanges[0]
    assert not result.is_success
    assert "protocol_error[business_call_outside_program]" in result.summary


@pytest.mark.asyncio
async def test_js_mode_direct_stop_still_works():
    core = RuntimeCore(strict_events=True)
    agent = await _spawn_agent(core, InvocationProtocol.JAVASCRIPT)
    tools = FakeTools(ToolResult(True, "ok", {"message": "final answer"}))
    pipeline = _pipeline(
        core,
        LLMResponse(content="", tool_calls=[ToolCall("t1", "stop", {"reason": "done"})]),
        tools=tools,
    )
    outcome = await _run(pipeline, agent)
    assert outcome.decision == "stop"
    assert outcome.content == "final answer"
    assert [c.name for c in tools.calls] == ["stop"]


@pytest.mark.asyncio
async def test_js_mode_rejects_mixed_program_and_controls_before_execution():
    core = RuntimeCore(strict_events=True)
    agent = await _spawn_agent(core, InvocationProtocol.JAVASCRIPT)
    js = FakeJSRuntime()
    tools = FakeTools()
    pipeline = _pipeline(
        core,
        LLMResponse(
            tool_calls=[
                ToolCall("t1", "js_exec", {"code": "text(1);"}),
                ToolCall("t2", "stop", {"reason": "done"}),
            ]
        ),
        tools=tools,
        js_runtime=js,
    )
    outcome = await _run(pipeline, agent)
    assert outcome.decision == "continue"
    # Nothing executed: no program, no stop; both wire calls got feedback.
    assert js.calls == []
    assert tools.calls == []
    assert len(outcome.tool_exchanges) == 2
    assert all(not result.is_success for _, result in outcome.tool_exchanges)
    assert all(
        "protocol_error[mixed_program_and_controls]" in result.summary
        for _, result in outcome.tool_exchanges
    )


@pytest.mark.asyncio
async def test_js_mode_runs_first_program_and_rejects_the_second():
    core = RuntimeCore(strict_events=True)
    agent = await _spawn_agent(core, InvocationProtocol.JAVASCRIPT)
    js = FakeJSRuntime()
    pipeline = _pipeline(
        core,
        LLMResponse(
            tool_calls=[
                ToolCall("t1", "js_exec", {"code": "text(1);"}),
                ToolCall("t2", "js_exec", {"code": "text(2);"}),
            ]
        ),
        js_runtime=js,
    )
    outcome = await _run(pipeline, agent)
    assert outcome.decision == "continue"
    assert [c.id for c in js.calls] == ["t1"]
    assert len(outcome.tool_exchanges) == 2
    first, second = outcome.tool_exchanges
    assert first[1].is_success
    assert not second[1].is_success
    assert "protocol_error[multiple_programs]" in second[1].summary


@pytest.mark.asyncio
async def test_js_mode_wait_approval_returns_decision_without_blocked_call():
    core = RuntimeCore(strict_events=True)
    agent = await _spawn_agent(core, InvocationProtocol.JAVASCRIPT)
    js = FakeJSRuntime(ToolResult(
        False,
        "JavaScript program failed: approval required",
        {
            "status": "failed",
            "outputs": [],
            "calls": [],
            "control_decision": "wait_approval",
            "error": {"code": "policy_wait", "message": "needs DAG review approval"},
        },
    ))
    pipeline = _pipeline(
        core,
        LLMResponse(tool_calls=[ToolCall("t1", "js_exec", {"code": "await tools.echo({});"})]),
        js_runtime=js,
    )
    outcome = await _run(pipeline, agent)
    assert outcome.decision == "wait_approval"
    assert outcome.message == "needs DAG review approval"
    assert outcome.blocked_call is None
    # The outer exchange is present exactly once (not repeated as blocked_call).
    assert [call.id for call, _ in outcome.tool_exchanges] == ["t1"]


@pytest.mark.asyncio
async def test_js_mode_program_failure_is_a_failed_exchange_and_continues():
    core = RuntimeCore(strict_events=True)
    agent = await _spawn_agent(core, InvocationProtocol.JAVASCRIPT)
    js = FakeJSRuntime(ToolResult(
        False,
        "JavaScript program failed: guest error",
        {"status": "failed", "outputs": [1], "calls": [], "error": {"code": "guest_error"}},
    ))
    pipeline = _pipeline(
        core,
        LLMResponse(
            tool_calls=[ToolCall("t1", "js_exec", {"code": "throw new Error('x')"})],
            reasoning="thinking",
        ),
        js_runtime=js,
    )
    outcome = await _run(pipeline, agent)
    assert outcome.decision == "continue"
    assert outcome.reasoning == "thinking"
    _, result = outcome.tool_exchanges[0]
    assert not result.is_success


@pytest.mark.skipif(not HOST_AVAILABLE, reason="optional JS host prerequisites missing")
@pytest.mark.asyncio
async def test_js_mode_end_to_end_with_real_host():
    core = RuntimeCore(strict_events=True)
    agent = await _spawn_agent(core, InvocationProtocol.JAVASCRIPT)

    class EchoTools:
        async def execute(self, agent, call):
            return ToolResult(True, "ok", {"value": call.arguments.get("value")})

    pipeline = TurnPipeline(
        event_log=core.event_log,
        stages=[],
        llm=FakeLLM(LLMResponse(
            tool_calls=[ToolCall(
                "wire-9", "js_exec",
                {"code": "const r = await tools.echo({value: 5}); text(r.data.value);"},
            )],
            reasoning="plan it",
        )),
        tools=EchoTools(),
    )
    outcome = await _run(pipeline, agent)
    assert outcome.decision == "continue"
    assert outcome.reasoning == "plan it"
    # Only the outer js_exec exchange enters model history.
    assert len(outcome.tool_exchanges) == 1
    call, result = outcome.tool_exchanges[0]
    assert call.id == "wire-9" and call.name == "js_exec"
    assert result.is_success
    assert result.data["outputs"] == [5]
    # Nested calls are audit events, not extra model exchanges.
    types = [e.type for e in core.event_log]
    assert types.count("tool.requested") == 1
    assert "program.submitted" in types and "program.finished" in types


@pytest.mark.skipif(not HOST_AVAILABLE, reason="optional JS host prerequisites missing")
@pytest.mark.asyncio
async def test_child_image_paths_reach_the_outer_exchange():
    core = RuntimeCore(strict_events=True)
    agent = await _spawn_agent(core, InvocationProtocol.JAVASCRIPT)

    class ImageTools:
        async def execute(self, agent, call):
            return ToolResult(True, "ok", {"image_paths": ["/workspace/plot.png"]})

    pipeline = TurnPipeline(
        event_log=core.event_log,
        stages=[],
        llm=FakeLLM(LLMResponse(
            tool_calls=[ToolCall("w", "js_exec", {"code": "await tools.echo({});"})]
        )),
        tools=ImageTools(),
    )
    outcome = await pipeline.run_turn(
        agent=agent,
        run_id="run_test",
        settings=RuntimeSettings(),
        capabilities=_caps(),
        inbox_messages=[{"content": "go"}],
    )
    _, result = outcome.tool_exchanges[0]
    assert result.is_success
    assert result.data["image_paths"] == ["/workspace/plot.png"]


@pytest.mark.skipif(not HOST_AVAILABLE, reason="optional JS host prerequisites missing")
@pytest.mark.asyncio
async def test_approval_pause_inside_tool_resumes_the_same_guest():
    core = RuntimeCore(strict_events=True)
    agent = await _spawn_agent(core, InvocationProtocol.JAVASCRIPT)
    gate = asyncio.Event()

    class PausingTools:
        def __init__(self) -> None:
            self.calls = 0

        async def execute(self, agent, call):
            self.calls += 1
            await gate.wait()  # simulates PendingBroker's approval pause
            return ToolResult(True, "ok", {"value": 8})

    tools = PausingTools()
    pipeline = TurnPipeline(
        event_log=core.event_log,
        stages=[],
        llm=FakeLLM(LLMResponse(
            tool_calls=[ToolCall(
                "w", "js_exec",
                {"code": "const r = await tools.echo({}); text(r.data.value * 2);"},
            )]
        )),
        tools=tools,
    )
    task = asyncio.create_task(_run(pipeline, agent))
    await asyncio.sleep(0.5)
    assert not task.done()  # guest is suspended on the same tool call
    gate.set()
    outcome = await asyncio.wait_for(task, timeout=15)
    _, result = outcome.tool_exchanges[0]
    assert result.is_success
    assert result.data["outputs"] == [16]
    assert tools.calls == 1  # resumed, never resubmitted
