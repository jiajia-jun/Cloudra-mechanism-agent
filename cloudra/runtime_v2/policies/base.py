"""Policy stage contract: the only harness extension point.

A stage observes one pipeline turn and may allow, warn, block or ask about a
tool call.  Stages are stateless; any cross-turn state lives in PipelineContext
or the owning AgentSession.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

from cloudra.runtime_v2.schemas import AgentCapabilities, AgentSession, RuntimeSettings


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ToolResult:
    is_success: bool
    summary: str = ""
    data: dict[str, Any] = field(default_factory=dict)
    duration_ms: int = 0


@dataclass(frozen=True)
class PolicyResult:
    outcome: Literal["allow", "warn", "block", "ask"]
    message: str = ""
    annotation: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def allow(cls) -> "PolicyResult":
        return cls("allow")

    @classmethod
    def warn(cls, message: str) -> "PolicyResult":
        return cls("warn", message)

    @classmethod
    def block(cls, message: str) -> "PolicyResult":
        return cls("block", message)

    @classmethod
    def ask(cls, message: str) -> "PolicyResult":
        return cls("ask", message)


class PipelineContext:
    """Read/emit surface shared by one pipeline turn.

    Stages must not import AgentHost or API code; this context is their only
    handle on the runtime.
    """

    def __init__(
        self,
        *,
        agent: AgentSession,
        run_id: str,
        settings_snapshot: RuntimeSettings,
        capabilities: AgentCapabilities,
        inbox_messages: list[dict[str, Any]],
        emit,
        workspace_dir: str | None = None,
    ) -> None:
        self.agent = agent
        self.run_id = run_id
        self.settings = settings_snapshot
        self.capabilities = capabilities
        self.inbox_messages = list(inbox_messages)
        self.workspace_dir = workspace_dir
        self._emit = emit

    def emit(self, type: str, data: dict[str, Any] | None = None) -> None:
        self._emit(type, data or {})


class PolicyStage(Protocol):
    name: str

    async def before_tool(self, ctx: PipelineContext, call: ToolCall) -> PolicyResult: ...

    async def after_tool(self, ctx: PipelineContext, call: ToolCall, result: ToolResult) -> None: ...

    async def before_llm(self, ctx: PipelineContext, messages: list[dict[str, Any]]) -> None: ...
