"""Role permission / tool-policy stage.

The stage only consults PipelineContext.capabilities; it has no knowledge of
specific tools.  New tool classes become visible automatically when the
runtime capability filter builds the tools list.
"""

from __future__ import annotations

from cloudra.runtime_v2.policies.base import PipelineContext, PolicyResult, ToolCall


class PermissionStage:
    name = "permission"

    async def before_tool(self, ctx: PipelineContext, call: ToolCall) -> PolicyResult:
        tools = set(ctx.capabilities.tools)
        if "*" in tools or call.name in tools:
            return PolicyResult.allow()
        return PolicyResult.block(
            f"tool {call.name!r} is not in this agent's capabilities "
            f"(available: {sorted(tools)})"
        )

    async def after_tool(self, ctx: PipelineContext, call: ToolCall, result) -> None:
        return None

    async def before_llm(self, ctx: PipelineContext, messages: list[dict]) -> None:
        return None
