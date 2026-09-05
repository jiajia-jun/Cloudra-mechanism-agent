"""Policy stage contract: the only harness extension point.

A stage observes one pipeline turn and may allow, warn, block or ask about a
tool call.  Stages are *decisionally* stateless: a verdict must be derivable
from the turn inputs (PipelineContext, tool call/result) plus projections of
durable state — never from mutable stage-private bookkeeping that a restart
could not reproduce.

Cross-turn state rules (3d):
- Anything that must survive a process restart lives outside the stage:
  event projections on the core, or each store's own authority (the DAG
  graph lives in the project's ConversationDB, the goal anchor in its file).
- A stage may keep **deliberately volatile** shell-private caches only when
  they are meaningless across restarts by construction (e.g. a per-run
  stop-confirmation tracker, a single tool call's before/after pairing
  window, a lazily rebuildable controller cache).  Each such cache carries
  an explicit "deliberately volatile" note on its owning class stating why
  discarding it on restart is correct.
- Stage-side file IO is pushed to the shell: TurnPipeline reads the goal via
  its ``goal_reader`` and hands it over on ``PipelineContext.goal`` (3d).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal, Protocol

from cloudra.runtime_v2.schemas import AgentCapabilities, AgentSession, RuntimeSettings

if TYPE_CHECKING:
    from cloudra.runtime_v2.invocation_types import InvocationError


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
    # Set only when the executor caught an unexpected fault and packaged it
    # as a result (LegacyToolExecutor's safe_call guard): the invocation
    # service turns this into a terminal unknown-effect outcome.  Explicit
    # business failures stay plain is_success=False results with error=None.
    error: "InvocationError | None" = None


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
        notices=None,
        goal: dict[str, Any] | None = None,
    ) -> None:
        self.agent = agent
        self.run_id = run_id
        self.settings = settings_snapshot
        self.capabilities = capabilities
        self.inbox_messages = list(inbox_messages)
        self.workspace_dir = workspace_dir
        self.notices = notices
        # The persisted goal anchor, read by the shell (TurnPipeline's
        # goal_reader) before stages run — stages never do that file IO.
        self.goal = goal
        self._emit = emit

    def emit(self, type: str, data: dict[str, Any] | None = None) -> None:
        self._emit(type, data or {})


class PolicyStage(Protocol):
    name: str

    async def before_tool(self, ctx: PipelineContext, call: ToolCall) -> PolicyResult: ...

    async def after_tool(self, ctx: PipelineContext, call: ToolCall, result: ToolResult) -> None: ...

    async def before_llm(self, ctx: PipelineContext, messages: list[dict[str, Any]]) -> None: ...
