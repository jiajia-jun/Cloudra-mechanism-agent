"""AgentHub forum routes: post projection + user-authored posts.

The forum store is the project event log (``hub.posted`` events), so reads are
pure in-memory projections.  A user post goes through the same EventWriter
commit + mailbox notification path as an agent's ``agent_hub`` tool post —
writes here are event appends (there is no hub command type), which is why
this POST does not go through the CommandBus.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Query

from cloudra.runtime_v2.hub_bridge import _posts, post_user_post

from ..context import ApiContext
from ..models import HubPostCreate


def build_router(ctx: ApiContext) -> APIRouter:
    router = APIRouter()

    @router.get("/api/v2/projects/{project_id}/hub/posts", dependencies=ctx.protected)
    async def list_hub_posts(
        project_id: str,
        topic: Optional[str] = Query(default=None),
        limit: int = Query(default=500, ge=1, le=2000),
    ) -> dict[str, Any]:
        project = ctx.core.require_project(project_id)
        posts = _posts(ctx.core, project.id, limit=limit)
        if topic is not None:
            posts = [p for p in posts if p["topic"] == topic]
        return {"posts": posts}

    @router.post("/api/v2/projects/{project_id}/hub/posts", dependencies=ctx.protected)
    async def create_hub_post(project_id: str, body: HubPostCreate) -> dict[str, Any]:
        return await post_user_post(
            ctx.core,
            project_id,
            topic=body.topic,
            content=body.content,
            kind=body.kind,
            to_agent=body.to_agent or "",
            parent_id=body.parent_id,
        )

    return router
