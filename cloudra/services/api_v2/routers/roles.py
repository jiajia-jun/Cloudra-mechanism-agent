"""Role registry routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from cloudra.runtime_v2.schemas import Command

from ..context import ApiContext
from ..models import CommandResponse, RolePatch, _command_payload


def build_router(ctx: ApiContext) -> APIRouter:
    router = APIRouter()

    @router.get("/api/v2/roles", dependencies=ctx.protected)
    async def list_roles() -> list[dict[str, Any]]:
        return [role.model_dump(mode="json") for role in ctx.core.roles.list()]

    @router.get("/api/v2/roles/{role_id}", dependencies=ctx.protected)
    async def get_role(role_id: str) -> dict[str, Any]:
        return ctx.core.roles.require(role_id).model_dump(mode="json")

    @router.patch("/api/v2/roles/{role_id}", dependencies=ctx.protected)
    async def patch_role(role_id: str, body: RolePatch) -> CommandResponse:
        command = Command(
            type="role.update",
            target={"role_id": role_id, "project_id": "runtime"},
            payload=_command_payload(body),
        )
        return await ctx.execute(command)

    return router
