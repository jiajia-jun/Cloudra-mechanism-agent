"""Turn pipeline: the fixed per-turn skeleton shared by every agent.

LLM and tool execution are injected protocols, so tests run without network or
external programs.  Harness behaviour is added exclusively through PolicyStage
instances; this module never special-cases a tool or orchestration mode.

Tool calls no longer execute here: every call goes through
``InvocationService`` (durable request -> policy -> executor -> durable raw
result -> post hooks -> durable finish), so traditional dispatch and the JS
runtime share one lifecycle.  The loop guard moved with it
(``invocation.InvocationService``); it stays deliberately volatile per-run
shell state.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Literal, Protocol

from cloudra.runtime_v2.event_writer import EventWriter
from cloudra.runtime_v2.events import EventLog
from cloudra.runtime_v2.invocation import InvocationService
from cloudra.runtime_v2.js_runtime import JavaScriptRuntime
from cloudra.runtime_v2.policies.base import (
    PipelineContext,
    PolicyStage,
    ToolCall,
    ToolResult,
)
from cloudra.runtime_v2.policies.goal_stage import read_goal
from cloudra.runtime_v2.schemas import (
    AgentCapabilities,
    AgentSession,
    EventEnvelope,
    InvocationProtocol,
    RuntimeSettings,
    effective_invocation_protocol,
)
from cloudra.runtime_v2.tool_catalog import JS_EXEC_NAME, validate_wire_route
from cloudra.tools.capabilities import is_direct_only

logger = logging.getLogger(__name__)

# Streaming delta sink: (kind, text) where kind is "content" or "reasoning".
DeltaSink = Callable[[str, str], Awaitable[None]]


@dataclass(frozen=True)
class LLMResponse:
    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    stop_requested: bool = False
    usage: dict[str, int] = field(default_factory=dict)
    finish_reason: str | None = None
    # 本次 LLM 调用的完整 reasoning（thinking）文本；流式 delta 走 llm.chunk
    # 不进事件日志，这里在每轮落一条 agent.thinking，保证历史轮次的 thinking
    # 在重进会话/刷新后仍可见。
    reasoning: str = ""


class LLMProvider(Protocol):
    async def complete(
        self,
        agent: AgentSession,
        messages: list[dict[str, Any]],
        tools: list[str],
        on_delta: DeltaSink | None = None,
    ) -> LLMResponse: ...


class ToolExecutor(Protocol):
    async def execute(self, agent: AgentSession, call: ToolCall) -> ToolResult: ...


@dataclass(frozen=True)
class TurnOutcome:
    decision: Literal["continue", "stop", "wait_input", "wait_approval"]
    content: str = ""
    message: str = ""
    tool_exchanges: tuple[tuple[ToolCall, ToolResult], ...] = ()
    blocked_call: ToolCall | None = None
    # Thinking-mode models require this on the next request's assistant turn.
    reasoning: str = ""


class TurnPipeline:
    def __init__(
        self,
        *,
        event_log: EventLog,
        stages: list[PolicyStage],
        llm: LLMProvider,
        tools: ToolExecutor,
        stop_tool: str = "stop",
        prompt_provider=None,
        event_hub=None,
        notices=None,
        goal_reader=read_goal,
        event_writer: EventWriter | None = None,
        invocations: InvocationService | None = None,
        js_runtime: JavaScriptRuntime | None = None,
    ) -> None:
        self.event_log = event_log
        self.stages = list(stages)
        self.llm = llm
        self.tools = tools
        self.stop_tool = stop_tool
        self.prompt_provider = prompt_provider
        self.event_hub = event_hub
        self.notices = notices
        # Shell-side goal IO: ``goal_reader(agent) -> dict | None`` reads the
        # persisted goal anchor (sync file IO, offloaded per turn) so stages
        # receive it read-only via PipelineContext.goal and stay IO-free.
        # The default is the built-in file reader; pass None to disable goal
        # injection entirely, or a custom callable to source it elsewhere.
        self.goal_reader = goal_reader
        # Single tool lifecycle for this pipeline.  Real wiring passes the
        # shared core EventWriter (API/benchmark); standalone tests get a
        # memory-only writer on the same log.
        self.event_writer = event_writer or (invocations.event_writer if invocations else None)
        if self.event_writer is None:
            self.event_writer = EventWriter(event_log, event_hub)
        self.invocations = invocations or InvocationService(
            event_writer=self.event_writer, stages=self.stages, tools=tools
        )
        # JS protocol shell: shares the same writer/lifecycle; js_exec is a
        # protocol execution request, never registered as a normal tool.
        self.js_runtime = js_runtime or JavaScriptRuntime(
            event_writer=self.event_writer, invocations=self.invocations
        )

    def _emitter(self, agent: AgentSession, run_id: str):
        def emit(type: str, data: dict[str, Any] | None = None) -> None:
            self.event_log.append(
                type,
                stream="agent",
                project_id=agent.project_id,
                session_id=agent.id,
                run_id=run_id,
                data=data or {},
            )

        return emit

    async def _publish(self, envelope: EventEnvelope) -> None:
        # Chunks already go to the hub live; log events normally wait for the
        # runner's end-of-turn flush.  Narration (thinking / intermediate
        # message_emitted) must not wait — the UI would otherwise drop the
        # streaming bubble when the delayed llm.request_started + tools land.
        if self.event_hub is None:
            return
        await self.event_hub.publish(envelope)

    async def run_turn(
        self,
        *,
        agent: AgentSession,
        run_id: str,
        settings: RuntimeSettings,
        capabilities: AgentCapabilities,
        inbox_messages: list[dict[str, Any]],
        history: list[dict[str, Any]] | None = None,
        workspace_dir: str | None = None,
        notices=None,
    ) -> TurnOutcome:
        emit = self._emitter(agent, run_id)
        notice_sink = notices if notices is not None else self.notices
        goal = None
        if self.goal_reader is not None:
            goal = await asyncio.to_thread(self.goal_reader, agent)
        ctx = PipelineContext(
            agent=agent,
            run_id=run_id,
            settings_snapshot=settings,
            capabilities=capabilities,
            inbox_messages=inbox_messages,
            emit=emit,
            workspace_dir=workspace_dir,
            notices=notice_sink,
            goal=goal,
        )

        messages: list[dict[str, Any]] = []
        if self.prompt_provider is not None:
            prompt_messages = await self.prompt_provider(
                agent=agent,
                workspace_dir=workspace_dir,
                tool_names=capabilities.tools,
            )
            messages.extend(prompt_messages or [])
        messages.extend(history or [])
        messages.extend(
            {"role": "user", "content": item.get("content", "")}
            for item in inbox_messages
        )
        # Only messages that are actually entering the model context count as
        # consumed.  AgentHub-targeted mentions/replies carry a text marker.
        for item in inbox_messages:
            content = str(item.get("content") or "")
            if "AgentHub" in content or "mentioned you in AgentHub" in content or "replied to your AgentHub" in content:
                self.event_log.append(
                    "hub.notification_consumed",
                    stream="agent",
                    project_id=agent.project_id,
                    session_id=agent.id,
                    run_id=run_id,
                    data={
                        "session_id": agent.id,
                        "message_id": str(item.get("message_id") or ""),
                        "post_id": str(item.get("post_id") or ""),
                        "consumed_at": __import__("datetime").datetime.now(
                            __import__("datetime").timezone.utc
                        ).isoformat(),
                        "content": content[:200],
                    },
                )
        for stage in self.stages:
            await stage.before_llm(ctx, messages)
        if notice_sink is not None:
            messages.extend(notice_sink.collect(agent.id))

        self.event_log.append(
            "llm.request_started",
            stream="agent",
            project_id=agent.project_id,
            session_id=agent.id,
            run_id=run_id,
            data={"model": settings.model},
        )
        started = time.monotonic()
        on_delta: DeltaSink | None = None
        if self.event_hub is not None:

            async def on_delta(kind: str, delta: str) -> None:
                # Transient hub-only event: never appended to the event log,
                # so it is neither replayed nor persisted.  seq 0 keeps SSE
                # client cursors anchored to real log events.
                await self.event_hub.publish(
                    EventEnvelope(
                        stream="agent",
                        project_id=agent.project_id,
                        session_id=agent.id,
                        run_id=run_id,
                        seq=0,
                        type="llm.chunk",
                        data={"kind": kind, "delta": delta},
                    )
                )

        try:
            response = await self.llm.complete(agent, messages, capabilities.tools, on_delta=on_delta)
        except Exception as exc:
            self.event_log.append(
                "llm.failed",
                stream="agent",
                project_id=agent.project_id,
                session_id=agent.id,
                run_id=run_id,
                data={"error": str(exc), "latency_ms": int((time.monotonic() - started) * 1000)},
            )
            raise
        self.event_log.append(
            "llm.completed",
            stream="agent",
            project_id=agent.project_id,
            session_id=agent.id,
            run_id=run_id,
            data={
                "usage": response.usage,
                "finish_reason": response.finish_reason,
                "latency_ms": int((time.monotonic() - started) * 1000),
            },
        )
        if response.reasoning:
            await self._publish(
                self.event_log.append(
                    "agent.thinking",
                    stream="agent",
                    project_id=agent.project_id,
                    session_id=agent.id,
                    run_id=run_id,
                    data={"content": response.reasoning},
                )
            )

        if not response.tool_calls:
            # 无工具调用的纯文本最终回复只是结束*意向*：是否允许结束由 runner
            # 收尾前的统一结束门禁裁决（与显式 stop 同一边界，Task 4A）。
            return TurnOutcome(
                decision="stop", content=response.content, reasoning=response.reasoning
            )

        # 中间轮次的正文（模型在工具调用前后说的话）不能只活在流式气泡里：
        # 落成持久 agent.message_emitted，否则历史轮次的 narration 全被吞掉。
        # stop 轮的正文由 runner 的最终消息承载，这里跳过避免重复。
        # 立刻推到 hub：等整轮工具跑完再 flush 时，前端会先被
        # llm.request_started 清掉流式气泡，内容来不及进时间线。
        if response.content.strip() and not any(
            call.name == self.stop_tool for call in response.tool_calls
        ):
            await self._publish(
                self.event_log.append(
                    "agent.message_emitted",
                    stream="agent",
                    project_id=agent.project_id,
                    session_id=agent.id,
                    run_id=run_id,
                    data={"sender": agent.role_id, "content": response.content},
                )
            )

        exchanges: list[tuple[ToolCall, ToolResult]] = []
        protocol = effective_invocation_protocol(agent)
        if protocol is InvocationProtocol.JAVASCRIPT and response.tool_calls:
            names = [call.name for call in response.tool_calls]
            has_direct = any(is_direct_only(name) for name in names)
            if JS_EXEC_NAME in names and has_direct:
                # Never partially execute a mixed program/control response:
                # every wire call gets matching feedback, nothing runs.
                reason = (
                    "protocol_error[mixed_program_and_controls]: a response "
                    "combining js_exec with direct controls is rejected; "
                    "issue them in separate responses"
                )
                exchanges = [(call, ToolResult(False, reason)) for call in response.tool_calls]
                return TurnOutcome(
                    decision="continue",
                    content=response.content,
                    tool_exchanges=tuple(exchanges),
                    reasoning=response.reasoning,
                )
        js_programs_run = 0
        for call in response.tool_calls:
            route_error = validate_wire_route(protocol, call.name)
            if route_error is not None:
                # Misrouted calls never execute; the message is model feedback.
                exchanges.append((call, ToolResult(False, route_error)))
                continue
            if protocol is InvocationProtocol.JAVASCRIPT and call.name == JS_EXEC_NAME:
                js_programs_run += 1
                if js_programs_run > 1:
                    exchanges.append((
                        call,
                        ToolResult(
                            False,
                        "protocol_error[multiple_programs]: only one js_exec "
                        "call runs per model response; the first program was "
                        "already processed and this later program was not executed. "
                        "Repair only the unexecuted program; do not replay the first one.",
                        ),
                    ))
                    continue
                result = await self.js_runtime.execute(ctx, call)
                exchanges.append((call, result))
                control = (result.data or {}).get("control_decision")
                if control == "wait_approval":
                    error = (result.data or {}).get("error") or {}
                    return TurnOutcome(
                        decision="wait_approval",
                        message=str(error.get("message") or ""),
                        tool_exchanges=tuple(exchanges),
                        reasoning=response.reasoning,
                    )
                continue
            # The full lifecycle (requested -> policy -> started -> raw result
            # -> post hooks -> finished) lives in the InvocationService; this
            # loop only translates outcomes into turn decisions.
            outcome = await self.invocations.invoke(ctx, call)
            if outcome.decision == "wait_approval":
                return TurnOutcome(
                    decision="wait_approval",
                    message=outcome.error.message if outcome.error else "",
                    blocked_call=outcome.call,
                    tool_exchanges=tuple(exchanges),
                    reasoning=response.reasoning,
                )
            if outcome.error is not None and outcome.error.code == "policy_blocked":
                return TurnOutcome(
                    decision="continue",
                    content=outcome.error.message,
                    message=f"blocked by {outcome.error.stage}",
                    blocked_call=outcome.call,
                    tool_exchanges=tuple(exchanges),
                    reasoning=response.reasoning,
                )
            result = outcome.result
            if result is None:
                # Only wait_approval returns result=None (handled above).
                continue
            exchanges.append((outcome.call, result))
            if outcome.call.name == self.stop_tool:
                # 用户可见的最终消息是模型自己的陈述；stop 工具的 summary 是
                # 输出 schema 的 JSON dump，直接当正文会把最终回答吞成工具噪音。
                # 模型没写正文时回退 stop 输出的 message（含 reason/[ANSWER]）。
                final_text = response.content.strip()
                if not final_text:
                    final_text = str((result.data or {}).get("message") or result.summary)
                return TurnOutcome(
                    decision="stop",
                    content=final_text,
                    tool_exchanges=tuple(exchanges),
                    reasoning=response.reasoning,
                )
        return TurnOutcome(
            decision="continue",
            content=response.content,
            tool_exchanges=tuple(exchanges),
            reasoning=response.reasoning,
        )
