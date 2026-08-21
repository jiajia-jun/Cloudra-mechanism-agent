"""Role permission / tool-policy stage.

The stage only consults PipelineContext.capabilities; it has no knowledge of
specific tools.  New tool classes become visible automatically when the
runtime capability filter builds the tools list.
"""

from __future__ import annotations

from cloudra.runtime_v2.policies.base import PipelineContext, PolicyResult, ToolCall
from cloudra.tools.capabilities import visual_tools


class PermissionStage:
    name = "permission"

    async def before_tool(self, ctx: PipelineContext, call: ToolCall) -> PolicyResult:
        tools = set(ctx.capabilities.tools)
        if "*" not in tools and call.name not in tools:
            return PolicyResult.block(
                f"tool {call.name!r} is not in this agent's capabilities "
                f"(available: {sorted(tools)})"
            )
        if not ctx.settings.visual_mode and call.name in visual_tools():
            return PolicyResult.block(
                f"tool {call.name!r} requires visual mode, which is off for this agent; "
                "turn it on with /visual to use vision tools"
            )
        return PolicyResult.allow()

    async def after_tool(self, ctx: PipelineContext, call: ToolCall, result) -> None:
        return None

    async def before_llm(self, ctx: PipelineContext, messages: list[dict]) -> None:
        return None
