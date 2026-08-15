"""Turn pipeline: the fixed per-turn skeleton shared by every agent.

LLM and tool execution are injected protocols, so tests run without network or
external programs.  Harness behaviour is added exclusively through PolicyStage
instances; this module never special-cases a tool or orchestration mode.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

from cloudra.runtime_v2.events import EventLog
from cloudra.runtime_v2.policies.base import (
    PipelineContext,
    PolicyStage,
    ToolCall,
    ToolResult,
)
from cloudra.runtime_v2.schemas import AgentCapabilities, AgentSession, RuntimeSettings


@dataclass(frozen=True)
class LLMResponse:
    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    stop_requested: bool = False
    usage: dict[str, int] = field(default_factory=dict)
    finish_reason: str | None = None


class LLMProvider(Protocol):
    async def complete(
        self,
        agent: AgentSession,
        messages: list[dict[str, Any]],
        tools: list[str],
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
    ) -> None:
        self.event_log = event_log
        self.stages = list(stages)
        self.llm = llm
        self.tools = tools
        self.stop_tool = stop_tool
        self.prompt_provider = prompt_provider

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
    ) -> TurnOutcome:
        emit = self._emitter(agent, run_id)
        ctx = PipelineContext(
            agent=agent,
            run_id=run_id,
            settings_snapshot=settings,
            capabilities=capabilities,
            inbox_messages=inbox_messages,
            emit=emit,
            workspace_dir=workspace_dir,
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

        self.event_log.append(
            "llm.request_started",
            stream="agent",
            project_id=agent.project_id,
            session_id=agent.id,
            run_id=run_id,
            data={"model": settings.model},
        )
        started = time.monotonic()
        response = await self.llm.complete(agent, messages, capabilities.tools)
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

        if not response.tool_calls:
            return TurnOutcome(decision="stop", content=response.content)

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
                return TurnOutcome(
                    decision=blocked.decision,
                    content=blocked.content,
                    message=blocked.message,
                    blocked_call=call,
                    tool_exchanges=tuple(exchanges),
                )
            started_call = time.monotonic()
            result = await self.tools.execute(agent, call)
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
                return TurnOutcome(
                    decision="stop",
                    content=result.summary,
                    tool_exchanges=tuple(exchanges),
                )
        return TurnOutcome(
            decision="continue",
            content=response.content,
            tool_exchanges=tuple(exchanges),
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
