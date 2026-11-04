"""Project-scoped batch delivery through the existing agent message command."""

from __future__ import annotations

from fastapi import APIRouter

from cloudra.runtime_v2.schemas import Command
from cloudra.services.subagent_schema import MessageBatch, MessageDeliveries

from ..context import ApiContext


def build_router(ctx: ApiContext) -> APIRouter:
    router = APIRouter()

    @router.post("/api/v2/projects/{project_id}/subagent/messages", dependencies=ctx.protected)
    async def send_message(project_id: str, body: MessageBatch) -> MessageDeliveries:
        ctx.core.require_project(project_id)
        deliveries = []
        for session_id in dict.fromkeys(body.recipients):
            agent = ctx.core.agents.get(session_id)
            if agent is None or agent.project_id != project_id:
                deliveries.append({
                    "session_id": session_id,
                    "error": {"code": "not_found", "message": "Agent not found in this project."},
                })
                continue
            result = await ctx.bus.execute(Command(
                type="agent.message",
                target={"session_id": session_id},
                payload={"content": body.content},
            ))
            if result.accepted:
                deliveries.append({"session_id": session_id, "message_event_id": result.event_id})
            else:
                deliveries.append({"session_id": session_id, "error": result.data["error"]})
        return {"deliveries": deliveries}

    return router
