"""Host-only ContextVar carrying the active invocation identity.

``InvocationService`` sets this around the whole before/execute/after
lifecycle so nested brokers (PendingBroker approval / ask_user requests)
can stamp their request events and attention projections with the
correlating ``tool_call_id`` / ``execution_id``.  It is process-local
shell state, never exposed to guest code and never persisted.
"""

from __future__ import annotations

from contextvars import ContextVar, Token
from dataclasses import dataclass
from typing import Awaitable, Callable

from cloudra.runtime_v2.schemas import ToolProgress


@dataclass(frozen=True)
class InvocationScope:
    tool_call_id: str
    tool_name: str
    execution_id: str | None = None
    report_progress: Callable[[ToolProgress], Awaitable[None]] | None = None
    request_event_id: str | None = None


_active_invocation: ContextVar[InvocationScope | None] = ContextVar(
    "cloudra_active_invocation", default=None
)


def current_invocation_scope() -> InvocationScope | None:
    return _active_invocation.get()


def set_invocation_scope(scope: InvocationScope) -> Token:
    return _active_invocation.set(scope)


def reset_invocation_scope(token: Token) -> None:
    _active_invocation.reset(token)


async def report_tool_progress(progress: ToolProgress) -> None:
    """Publish progress for a runtime invocation; standalone tools have no sink."""
    progress = ToolProgress.model_validate(progress.model_dump(mode="json"))
    scope = current_invocation_scope()
    if scope is not None and scope.report_progress is not None:
        await scope.report_progress(progress)
