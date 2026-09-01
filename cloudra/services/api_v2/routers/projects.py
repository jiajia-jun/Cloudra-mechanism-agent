"""Project CRUD, workspace/transcript reads, and project-scoped agent spawn."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Response, status

from cloudra.runtime_v2.schemas import Command

from ..context import ApiContext
from ..models import AgentSpawn, CommandResponse, ProjectCreate, ProjectPatch, _command_payload


def build_router(ctx: ApiContext) -> APIRouter:
    router = APIRouter()

    @router.get("/api/v2/projects", dependencies=ctx.protected)
    async def list_projects(include_archived: bool = False) -> list[dict[str, Any]]:
        projects = ctx.core.projects.values()
        if not include_archived:
            projects = [p for p in projects if not p.archived]
        return [p.model_dump(mode="json") for p in projects]

    @router.post("/api/v2/projects", dependencies=ctx.protected, status_code=status.HTTP_201_CREATED)
    async def create_project(body: ProjectCreate) -> CommandResponse:
        command = Command(type="project.create", payload=_command_payload(body))
        return await ctx.execute(command)

    @router.get("/api/v2/projects/{project_id}", dependencies=ctx.protected)
    async def get_project(project_id: str) -> dict[str, Any]:
        return ctx.core.require_project(project_id).model_dump(mode="json")

    @router.patch("/api/v2/projects/{project_id}", dependencies=ctx.protected)
    async def patch_project(project_id: str, body: ProjectPatch) -> CommandResponse:
        command = Command(
            type="project.update",
            target={"project_id": project_id},
            payload=_command_payload(body),
        )
        return await ctx.execute(command)

    @router.delete("/api/v2/projects/{project_id}", dependencies=ctx.protected)
    async def archive_project(project_id: str) -> CommandResponse:
        command = Command(
            type="project.update",
            target={"project_id": project_id},
            payload={"archived": True},
        )
        return await ctx.execute(command)

    @router.get("/api/v2/projects/{project_id}/workspace", dependencies=ctx.protected)
    async def project_workspace(project_id: str) -> dict[str, Any]:
        project = ctx.core.require_project(project_id)
        return {"workspace_dir": project.workspace_dir, "valid": bool(project.workspace_dir)}

    @router.get("/api/v2/projects/{project_id}/transcript", dependencies=ctx.protected)
    async def project_transcript(project_id: str) -> Response:
        """Full human-readable Markdown dump of the project's event stream.

        Every persisted event with its complete payload (messages, thinking,
        tool arguments/results, compaction and context-tree snapshots) — built
        for offline diagnosis and ablation analysis.
        """
        from cloudra.runtime_v2.transcript import render_project_transcript

        project = ctx.core.require_project(project_id)
        events = ctx.core.event_log.query_project(project_id, limit=1_000_000)
        text = render_project_transcript(project, ctx.core.agents, events)
        safe = "".join(
            ch if ch.isascii() and (ch.isalnum() or ch in "-_") else "-"
            for ch in (project.name or project.id)
        ).strip("-")[:60] or project.id
        return Response(
            content=text,
            media_type="text/markdown; charset=utf-8",
            headers={
                "Content-Disposition": f'attachment; filename="cloudra-transcript-{safe}.md"'
            },
        )

    @router.get("/api/v2/projects/{project_id}/agents", dependencies=ctx.protected)
    async def list_agents(project_id: str) -> list[dict[str, Any]]:
        return [a.model_dump(mode="json") for a in ctx.core.list_project_agents(project_id)]

    @router.post("/api/v2/projects/{project_id}/agents", dependencies=ctx.protected, status_code=status.HTTP_201_CREATED)
    async def spawn_agent(project_id: str, body: AgentSpawn) -> CommandResponse:
        command = Command(
            type="agent.spawn",
            target={"project_id": project_id},
            payload=_command_payload(body),
        )
        return await ctx.execute(command)

    return router
