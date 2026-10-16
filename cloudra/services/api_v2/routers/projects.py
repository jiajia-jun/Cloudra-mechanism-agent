"""Project CRUD, workspace/transcript reads, and project-scoped agent spawn."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, HTTPException, Response, status

from cloudra.persistence.database import ComputeDB
from cloudra.runtime_v2.schemas import Command
from cloudra.services.compute_store import (
    acount_active_compute_job_states,
    active_jobs_delete_message,
)

from ..context import ApiContext
from ..models import AgentSpawn, CommandResponse, ProjectCreate, ProjectPatch, _command_payload
from ..views import agent_dict, agent_dicts


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
    async def delete_project(project_id: str, hard: bool = False) -> CommandResponse:
        if not hard:
            command = Command(
                type="project.update",
                target={"project_id": project_id},
                payload={"archived": True},
            )
            return await ctx.execute(command)
        # 硬删除前置门禁：有非终态 compute job（ready/running/cancel_requested）
        # 的项目拒绝删除——绝不杀计算进程，提示先走 cancel-all。
        # 状态机校验（必须已归档、无存活 agent）在 project.delete 的 decider。
        counts = await acount_active_compute_job_states(ComputeDB(), project_id)
        if counts:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "code": "state_conflict",
                    "message": active_jobs_delete_message(counts),
                },
            )
        command = Command(type="project.delete", target={"project_id": project_id})
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
        # 事件查询 + 全文渲染是同步 DB/CPU 重活，卸载出事件循环。
        events = await asyncio.to_thread(ctx.core.event_log.query_project, project_id, limit=1_000_000)
        text = await asyncio.to_thread(render_project_transcript, project, ctx.core.agents, events)
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

    @router.get("/api/v2/projects/{project_id}/view", dependencies=ctx.protected)
    async def project_view(project_id: str) -> dict[str, Any]:
        # Commands and background agent-state writes use these existing locks.
        # Completion history is read later, off-loop, through the same prefix.
        async with ctx.core.command_lock, ctx.core.event_writer._lock:
            agents = [
                agent.model_copy(deep=True)
                for agent in ctx.core.list_project_agents(project_id)
            ]
            watermarks = (
                ctx.core.event_writer.persisted_watermarks()
                if ctx.core.store is not None else ctx.core.event_log.high_watermarks
            )
            cursor = watermarks.get(project_id, 0)
            session_boundaries = ctx.core.event_log.high_session_watermarks

        def serialize_agents():
            return [
                agent_dict(
                    ctx.core, agent,
                    before_session_seq=session_boundaries.get(agent.id, 0),
                )
                for agent in agents
            ]

        return {"agents": await asyncio.to_thread(serialize_agents), "cursor": cursor}

    @router.get("/api/v2/projects/{project_id}/agents", dependencies=ctx.protected)
    async def list_agents(project_id: str) -> list[dict[str, Any]]:
        agents = ctx.core.list_project_agents(project_id)
        return await asyncio.to_thread(agent_dicts, ctx.core, agents)

    @router.post("/api/v2/projects/{project_id}/agents", dependencies=ctx.protected, status_code=status.HTTP_201_CREATED)
    async def spawn_agent(project_id: str, body: AgentSpawn) -> CommandResponse:
        command = Command(
            type="agent.spawn",
            target={"project_id": project_id},
            payload=_command_payload(body),
        )
        return await ctx.execute(command)

    return router
