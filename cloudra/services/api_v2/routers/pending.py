"""Pending approvals / ask-user interactions (project-scoped inbox)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from cloudra.runtime_v2.schemas import Command

from ..context import ApiContext
from ..models import ApprovalDecision, InteractionResponse


def build_router(ctx: ApiContext) -> APIRouter:
    router = APIRouter()

    @router.get("/api/v2/projects/{project_id}/approvals", dependencies=ctx.protected)
    async def list_approvals(project_id: str) -> list[dict[str, Any]]:
        ctx.core.require_project(project_id)
        return ctx.core.pending.list_pending_approvals(project_id)

    @router.post("/api/v2/projects/{project_id}/approvals/{approval_id}/decision", dependencies=ctx.protected)
    async def decide_approval(
        project_id: str, approval_id: str, body: ApprovalDecision
    ) -> dict[str, Any]:
        result = await ctx.bus.execute(
            Command(
                type="approval.decide",
                target={"project_id": project_id},
                payload={
                    "approval_id": approval_id,
                    "decision": "approved" if body.decision == "approve" else "denied",
                    "reason": body.reason,
                },
            )
        )
        if not result.accepted:
            error = (result.data or {}).get("error", {})
            http_code = 404 if error.get("code") == "not_found" else 400
            raise HTTPException(status_code=http_code, detail=error.get("message", "decision rejected"))
        return {"accepted": True}

    @router.get("/api/v2/projects/{project_id}/interactions", dependencies=ctx.protected)
    async def list_interactions(
        project_id: str, session_id: str | None = None
    ) -> list[dict[str, Any]]:
        ctx.core.require_project(project_id)
        rows = ctx.core.pending.list_pending_interactions(project_id)
        if session_id is not None:
            rows = [row for row in rows if row["session_id"] == session_id]
        return rows

    @router.post("/api/v2/projects/{project_id}/interactions/{interaction_id}/response", dependencies=ctx.protected)
    async def respond_interaction(
        project_id: str,
        interaction_id: str,
        body: InteractionResponse,
    ) -> dict[str, Any]:
        result = await ctx.bus.execute(
            Command(
                type="interaction.respond",
                target={"project_id": project_id},
                payload={"interaction_id": interaction_id, "response": body.response},
            )
        )
        if not result.accepted:
            error = (result.data or {}).get("error", {})
            http_code = 404 if error.get("code") == "not_found" else 400
            raise HTTPException(status_code=http_code, detail=error.get("message", "response rejected"))
        return result.data

    return router
