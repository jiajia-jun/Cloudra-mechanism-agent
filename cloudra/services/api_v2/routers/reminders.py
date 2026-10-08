"""Reminder 控制面：项目 pending 闹钟只读查询。

pending 列表是 reminder.scheduled/cancelled/fired 事件的投影
（``ReminderBroker.pending_in_project``），行里的 ``session_id`` 即归属
agent——闹钟到点唤醒的就是它。
"""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter

from ..context import ApiContext


def build_router(ctx: ApiContext) -> APIRouter:
    router = APIRouter()

    @router.get("/api/v2/projects/{project_id}/reminders/pending", dependencies=ctx.protected)
    async def list_pending_reminders(project_id: str) -> list[dict[str, Any]]:
        ctx.core.require_project(project_id)
        return await asyncio.to_thread(ctx.core.reminders.pending_in_project, project_id)

    return router
