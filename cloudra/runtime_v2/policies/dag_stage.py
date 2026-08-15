"""DAG harness as a policy stage.

The stage wraps the deterministic dag/ engine (DagController) without making
the turn pipeline aware of graphs.  ``dag_record`` / ``dag_guided`` are just
the same stage enabled by the agent's settings.
"""

from __future__ import annotations

from typing import Any

from cloudra.dag.controller import DagController
from cloudra.persistence.database import ConversationDB
from cloudra.runtime_v2.policies.base import PipelineContext, PolicyResult, ToolCall, ToolResult


class DagPolicyStage:
    name = "dag"

    def __init__(self) -> None:
        self._controllers: dict[str, DagController] = {}

    def _controller(self, ctx: PipelineContext) -> DagController | None:
        mode = ctx.settings.orchestration_mode
        if mode.value == "standard":
            return None
        agent = ctx.agent
        controller = self._controllers.get(agent.id)
        if controller is None or controller.mode.value != mode.value:
            db = ConversationDB(agent.project_id).init()
            supervisor = None
            if mode.value == "dag_guided":
                from cloudra.core.supervisor import GraphSupervisor

                supervisor = GraphSupervisor(
                    conversation_id=agent.project_id,
                    working_directory=ctx.workspace_dir,
                )
            controller = DagController(
                db,
                agent.id,
                mode,
                conversation_id=agent.project_id,
                working_directory=ctx.workspace_dir,
                agent_id=agent.role_id,
                supervisor=supervisor,
            )
            self._controllers[agent.id] = controller
        return controller

    async def before_tool(self, ctx: PipelineContext, call: ToolCall) -> PolicyResult:
        controller = self._controller(ctx)
        if controller is None:
            return PolicyResult.allow()
        await controller.initialize()
        disposition = await controller.check_substantive_gate(call.name, call.arguments)
        if disposition is None:
            return PolicyResult.allow()
        kind, message = disposition
        if kind == "block":
            ctx.emit("dag.gate_blocked", {"gate": self.name, "message": message, "tool": call.name})
            return PolicyResult.block(message)
        if kind == "warn":
            ctx.emit("agent.warning", {"code": "dag.gate.warn", "message": message})
        return PolicyResult.allow()

    async def after_tool(self, ctx: PipelineContext, call: ToolCall, result: ToolResult) -> None:
        controller = self._controller(ctx)
        if controller is None:
            return
        payload = {**(result.data or {}), "is_success": result.is_success}
        await controller.on_tool_finished(
            call.id,
            call.name,
            call.arguments,
            payload,
        )

    async def before_llm(self, ctx: PipelineContext, messages: list[dict[str, Any]]) -> None:
        controller = self._controller(ctx)
        if controller is None:
            return
        projection = await controller.prompt_projection()
        if projection:
            messages.append({"role": "system", "content": projection})
