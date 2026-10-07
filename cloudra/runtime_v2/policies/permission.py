"""Role permission / tool-policy stage.

The stage consults PipelineContext.capabilities plus registry projections
(visual gate, role allowlist); it has no knowledge of specific tools.  New
tool classes become visible automatically when the runtime capability filter
builds the tools list.
"""

from __future__ import annotations

from cloudra.runtime_v2.policies.base import PipelineContext, PolicyResult, ToolCall
from cloudra.tools.capabilities import role_hidden_tools, visual_tools


class PermissionStage:
    name = "permission"

    async def before_tool(self, ctx: PipelineContext, call: ToolCall) -> PolicyResult:
        from cloudra.tools.capabilities import is_dag_compute_entry
        try:
            compute_entry = is_dag_compute_entry(call.name, call.arguments)
        except ValueError as exc:
            return PolicyResult.block(f"Invalid tool arguments: {exc}")
        if compute_entry and not ctx.capabilities.permissions.write:
            return PolicyResult.block("Compute production requires write permission in the current task")
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
        if call.name in role_hidden_tools(ctx.agent.role_id):
            return PolicyResult.block(
                f"tool {call.name!r} is restricted to specific roles and is not "
                f"available to role {ctx.agent.role_id!r}"
            )
        return PolicyResult.allow()

    async def after_tool(self, ctx: PipelineContext, call: ToolCall, result) -> None:
        return None

    async def before_llm(self, ctx: PipelineContext, messages: list[dict]) -> None:
        return None


def require_delegation_permissions(caller, target):
    """A task cannot gain effective permissions by delegating its instruction."""
    from cloudra.runtime_v2.schemas import CommandRejected
    missing = [name for name, granted in target.model_dump().items() if granted and not getattr(caller,name)]
    if missing:
        raise CommandRejected('forbidden', 'Delegation would grant permissions absent from the caller: '+', '.join(missing))
