"""Turn pipeline: the fixed per-turn skeleton shared by every agent.

LLM and tool execution are injected protocols, so tests run without network or
external programs.  Harness behaviour is added exclusively through PolicyStage
instances; this module never special-cases a tool or orchestration mode.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Literal, Protocol

from cloudra.runtime_v2.events import EventLog
from cloudra.runtime_v2.policies.base import (
    PipelineContext,
    PolicyStage,
    ToolCall,
    ToolResult,
)
from cloudra.runtime_v2.schemas import (
    AgentCapabilities,
    AgentSession,
    EventEnvelope,
    RuntimeSettings,
)

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
    ) -> None:
        self.event_log = event_log
        self.stages = list(stages)
        self.llm = llm
        self.tools = tools
        self.stop_tool = stop_tool
        self.prompt_provider = prompt_provider
        self.event_hub = event_hub
        self.notices = notices

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
        ctx = PipelineContext(
            agent=agent,
            run_id=run_id,
            settings_snapshot=settings,
            capabilities=capabilities,
            inbox_messages=inbox_messages,
            emit=emit,
            workspace_dir=workspace_dir,
            notices=notice_sink,
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
        for call in response.tool_calls:
            self.event_log.append(
                "tool.started",
                stream="agent",
                project_id=agent.project_id,
                session_id=agent.id,
                run_id=run_id,
                data={"tool_call_id": call.id, "tool_name": call.name, "arguments_summary": call.arguments},
            )
            blocked = await self._apply_before_tool(ctx, call, emit)
            if blocked is not None:
                # The call never executed, but its tool.started is already in
                # the log — close it so timelines never show a phantom
                # "running" row for a call this turn gave up on.
                self.event_log.append(
                    "tool.finished",
                    stream="agent",
                    project_id=agent.project_id,
                    session_id=agent.id,
                    run_id=run_id,
                    data={
                        "tool_call_id": call.id,
                        "tool_name": call.name,
                        "is_success": False,
                        "result_summary": blocked.message or "not executed",
                    },
                )
                return TurnOutcome(
                    decision=blocked.decision,
                    content=blocked.content,
                    message=blocked.message,
                    blocked_call=call,
                    tool_exchanges=tuple(exchanges),
                    reasoning=response.reasoning,
                )
            started_call = time.monotonic()
            try:
                result = await self.tools.execute(agent, call)
            except asyncio.CancelledError:
                # Run cancelled mid-tool: pair the started event before the
                # cancellation propagates and the run task dies.
                self.event_log.append(
                    "tool.finished",
                    stream="agent",
                    project_id=agent.project_id,
                    session_id=agent.id,
                    run_id=run_id,
                    data={
                        "tool_call_id": call.id,
                        "tool_name": call.name,
                        "is_success": False,
                        "result_summary": "interrupted: run cancelled",
                        "cancelled": True,
                        "duration_ms": int((time.monotonic() - started_call) * 1000),
                    },
                )
                raise
            except Exception as exc:
                self.event_log.append(
                    "tool.finished",
                    stream="agent",
                    project_id=agent.project_id,
                    session_id=agent.id,
                    run_id=run_id,
                    data={
                        "tool_call_id": call.id,
                        "tool_name": call.name,
                        "is_success": False,
                        "result_summary": f"tool crashed: {exc}",
                        "duration_ms": int((time.monotonic() - started_call) * 1000),
                    },
                )
                raise
            result = ToolResult(
                is_success=result.is_success,
                summary=result.summary,
                data=result.data,
                duration_ms=int((time.monotonic() - started_call) * 1000),
            )
            exchanges.append((call, result))
            for stage in self.stages:
                await stage.after_tool(ctx, call, result)
            self.event_log.append(
                "tool.finished",
                stream="agent",
                project_id=agent.project_id,
                session_id=agent.id,
                run_id=run_id,
                data={
                    "tool_call_id": call.id,
                    "tool_name": call.name,
                    "is_success": result.is_success,
                    "result_summary": result.summary,
                    "duration_ms": result.duration_ms,
                },
            )
            if call.name == self.stop_tool:
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

    async def _apply_before_tool(self, ctx, call: ToolCall, emit) -> TurnOutcome | None:
        for stage in self.stages:
            policy = await stage.before_tool(ctx, call)
            if policy.outcome == "block":
                self.event_log.append(
                    "tool.blocked",
                    stream="agent",
                    project_id=ctx.agent.project_id,
                    session_id=ctx.agent.id,
                    run_id=ctx.run_id,
                    data={"tool_call_id": call.id, "tool_name": call.name, "stage": stage.name,
                          "message": policy.message},
                )
                return TurnOutcome(
                    decision="continue",
                    content=policy.message,
                    message=f"blocked by {stage.name}",
                )
            if policy.outcome == "ask":
                self.event_log.append(
                    "tool.approval_requested",
                    stream="agent",
                    project_id=ctx.agent.project_id,
                    session_id=ctx.agent.id,
                    run_id=ctx.run_id,
                    data={"tool_call_id": call.id, "tool_name": call.name, "message": policy.message},
                )
                return TurnOutcome(decision="wait_approval", message=policy.message)
            if policy.outcome == "warn":
                emit("agent.warning", {"code": f"{stage.name}.warn", "message": policy.message})
        return None
