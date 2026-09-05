"""Immutable contracts for the tool invocation lifecycle.

``decide_invocation`` is a pure planner: it validates the request envelope,
detaches the arguments with a JSON round-trip and produces the durable
``tool.requested`` draft plus the ``InvokeTool`` effect description.  The
imperative ``InvocationService`` commits the event before executing the
effect — an effect is data, never an event subscriber, so replay runs none
of this.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from cloudra.runtime_v2.effects import EventDraft
from cloudra.runtime_v2.policies.base import ToolCall, ToolResult

if TYPE_CHECKING:
    from cloudra.runtime_v2.policies.base import PipelineContext


@dataclass(frozen=True)
class InvocationError:
    code: str
    message: str
    effect_state: Literal["not_started", "completed", "unknown"]
    stage: str | None = None


@dataclass(frozen=True)
class InvocationOutcome:
    call: ToolCall
    result: ToolResult | None
    decision: Literal["continue", "wait_approval"] = "continue"
    error: InvocationError | None = None
    raw_result_event_id: str | None = None


@dataclass(frozen=True)
class InvokeTool:
    call: ToolCall
    execution_id: str | None = None


def decide_invocation(
    ctx: "PipelineContext", call: ToolCall, *, execution_id: str | None = None
) -> tuple[EventDraft, InvokeTool]:
    """Freeze/validate the request envelope; the request is a fact, not an authorization."""
    if not isinstance(call.id, str) or not call.id:
        raise ValueError("tool call id must be a non-empty string")
    if not isinstance(call.name, str) or not call.name:
        raise ValueError("tool name must be a non-empty string")
    if not isinstance(call.arguments, dict):
        raise ValueError("tool call arguments must be a JSON object")
    try:
        frozen_arguments = json.loads(json.dumps(call.arguments, allow_nan=False))
    except (TypeError, ValueError) as exc:
        raise ValueError(
            "tool call arguments must be JSON-serializable without NaN or Infinity"
        ) from exc
    frozen_call = ToolCall(call.id, call.name, frozen_arguments)
    return EventDraft(
        "tool.requested",
        "agent",
        ctx.agent.project_id,
        ctx.agent.id,
        ctx.run_id,
        {
            "tool_call_id": frozen_call.id,
            "tool_name": frozen_call.name,
            "arguments_summary": frozen_arguments,
            "execution_id": execution_id,
        },
    ), InvokeTool(frozen_call, execution_id)
