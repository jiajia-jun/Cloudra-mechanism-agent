"""Host-mode HTTP routes: direct Cloudra tool execution and compute-job claim watchdog."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from cloudra.persistence.database import ComputeDB
from cloudra.services.host_bridge import (
    HostToolDomain,
    aclaim_host_compute,
    ainspect_host_compute,
    execute_host_tool,
    list_host_tools,
)

from ..context import ApiContext


class HostToolInvoke(BaseModel):
    model_config = ConfigDict(extra="forbid")

    arguments: dict[str, Any] = Field(default_factory=dict)
    owner_id: str | None = None


class HostComputeClaim(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: str | None = None
    owner_id: str | None = None
    job_ids: list[int] | None = None


def build_router(ctx: ApiContext) -> APIRouter:
    router = APIRouter()

    @router.get("/api/v2/host/tools", dependencies=ctx.protected)
    async def host_list_tools(
        domain: HostToolDomain = "all",
        include_dag: bool = False,
        include_schemas: bool = True,
    ) -> dict[str, Any]:
        tools = await asyncio.to_thread(
            list_host_tools,
            domain=domain,
            include_dag=include_dag,
            include_schemas=include_schemas,
        )
        return {"tools": tools}

    @router.post("/api/v2/projects/{project_id}/host/tools/{tool_name}", dependencies=ctx.protected)
    async def host_invoke_tool(
        project_id: str,
        tool_name: str,
        body: HostToolInvoke,
    ) -> dict[str, Any]:
        try:
            return await execute_host_tool(
                ctx.core,
                project_id=project_id,
                tool_name=tool_name,
                arguments=body.arguments,
                owner_id=body.owner_id,
            )
        except KeyError as exc:
            raise HTTPException(
                status_code=404,
                detail={"code": "not_found", "message": str(exc)},
            ) from exc
        except PermissionError as exc:
            raise HTTPException(
                status_code=403,
                detail={"code": "forbidden", "message": str(exc)},
            ) from exc
        except ValueError as exc:
            raise HTTPException(
                status_code=409,
                detail={"code": "state_conflict", "message": str(exc)},
            ) from exc

    @router.get("/api/v2/host/compute/watchdog", dependencies=ctx.protected)
    async def host_compute_watchdog(
        project_id: str | None = None,
        owner_id: str | None = None,
    ) -> dict[str, Any]:
        if project_id is not None:
            ctx.core.require_project(project_id)
        try:
            return await ainspect_host_compute(
                ComputeDB(), project_id=project_id, owner_id=owner_id
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=400,
                detail={"code": "invalid_request", "message": str(exc)},
            ) from exc

    @router.post("/api/v2/host/compute/claim", dependencies=ctx.protected)
    async def host_compute_claim(body: HostComputeClaim) -> dict[str, Any]:
        if body.project_id is not None:
            ctx.core.require_project(body.project_id)
        try:
            return await aclaim_host_compute(
                ComputeDB(),
                project_id=body.project_id,
                owner_id=body.owner_id,
                job_ids=body.job_ids,
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=400,
                detail={"code": "invalid_request", "message": str(exc)},
            ) from exc

    return router
