"""Explicit per-app route context.

Replaces the closure state routes used to capture from ``create_v2_app``:
routers are built by factory functions that receive this container, so every
shared dependency (core, command bus, auth dependency) is visible at the
injection point instead of hiding in an enclosing scope.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException, status

from cloudra.runtime_v2.commands import CommandBus
from cloudra.runtime_v2.core import RuntimeCore
from cloudra.runtime_v2.schemas import AgentSession, Command, CommandRejected

from .models import CommandResponse
from .views import agent_dict


@dataclass
class ApiContext:
    core: RuntimeCore
    bus: CommandBus
    protected: list[Any]  # [Depends(authorize)] — shared auth dependency
    # Hosted benchmark batch service (GH #32); None only in minimal test apps
    # that never exercise the benchmark router.
    benchmark: Any = None

    async def execute(self, command: Command) -> CommandResponse:
        try:
            result = await self.bus.execute(command)
        except CommandRejected as exc:
            http_code = {
                "not_found": status.HTTP_404_NOT_FOUND,
                "state_conflict": status.HTTP_409_CONFLICT,
            }.get(exc.code, status.HTTP_400_BAD_REQUEST)
            raise HTTPException(
                status_code=http_code,
                detail={"code": exc.code, "message": exc.message},
            ) from exc
        data = result.data
        if isinstance(data, AgentSession):
            # 命令响应里的 agent 与 GET 端点同形：运行期投影（completion）也带上，
            # 否则前端用响应整体替换 agent 时会丢掉它。
            data = await asyncio.to_thread(agent_dict, self.core, data)
        return CommandResponse(
            command_id=result.command_id,
            accepted=result.accepted,
            event_id=result.event_id,
            data=data,
        )
