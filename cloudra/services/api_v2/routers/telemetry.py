"""LLM 遥测只读路由：token 聚合、缓存分析、全量 context 导出下载。

纯只读（只开 mode=ro 连接），不走 CommandBus；同步 SQLite 读取一律
``asyncio.to_thread`` 让出事件循环。db 路径取 live core 的 store，
测试/嵌入方未挂 store 时回落 paths.runtime_db_path()。
"""

from __future__ import annotations

import asyncio
import os
import tempfile
from pathlib import Path
from typing import Optional

from anyio import CancelScope
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse, Response
from starlette.background import BackgroundTask

from cloudra.persistence import paths
from cloudra.services import telemetry

from ..context import ApiContext


def build_router(ctx: ApiContext) -> APIRouter:
    router = APIRouter()
    export_lock = asyncio.Lock()

    def _db_path() -> Path:
        store = getattr(ctx.core, "store", None)
        if store is not None:
            return Path(store.path)
        return paths.runtime_db_path()

    @router.get("/api/v2/telemetry/tokens", dependencies=ctx.protected)
    async def telemetry_tokens(
        since: Optional[str] = Query(default=None),
        until: Optional[str] = Query(default=None),
    ) -> dict:
        try:
            return await asyncio.to_thread(
                telemetry.token_summary, _db_path(), since=since, until=until
            )
        except telemetry.TelemetryError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.get("/api/v2/telemetry/cache", dependencies=ctx.protected)
    async def telemetry_cache(
        since: Optional[str] = Query(default=None),
        until: Optional[str] = Query(default=None),
        top_n: int = Query(default=20, ge=0, le=500),
    ) -> dict:
        try:
            return await asyncio.to_thread(
                telemetry.cache_summary, _db_path(), since=since, until=until, top_n=top_n
            )
        except telemetry.TelemetryError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.get("/api/v2/telemetry/agents", dependencies=ctx.protected)
    async def telemetry_agents(
        since: Optional[str] = Query(default=None),
        until: Optional[str] = Query(default=None),
    ) -> dict:
        try:
            return await asyncio.to_thread(
                telemetry.agent_summary, _db_path(), since=since, until=until
            )
        except telemetry.TelemetryError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    async def export_file(ident, suffix, media_type, writer):
        def build():
            fd, path = tempfile.mkstemp(prefix="cloudra-telemetry-", suffix=suffix)
            os.close(fd)
            try:
                writer(_db_path(), ident, path)
            except BaseException:
                Path(path).unlink(missing_ok=True)
                raise
            return path

        try:
            # Both full-history exports share one bounded preparation slot.
            # Keep the slot until a cancelled request's worker has finished.
            async with export_lock:
                task = asyncio.create_task(asyncio.to_thread(build))
                try:
                    path = await asyncio.shield(task)
                except asyncio.CancelledError:
                    with CancelScope(shield=True):
                        path = await task
                        await asyncio.to_thread(Path(path).unlink, missing_ok=True)
                    raise
        except telemetry.TelemetryError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return FileResponse(path, media_type=media_type, filename=f"{ident}{suffix}",
                            background=BackgroundTask(Path(path).unlink, missing_ok=True))

    @router.get("/api/v2/telemetry/export/session/{session_id}", dependencies=ctx.protected)
    async def telemetry_export_session(session_id: str) -> Response:
        return await export_file(session_id, ".jsonl", "application/x-ndjson", telemetry.write_session_jsonl)

    @router.get("/api/v2/telemetry/export/project/{project_id}", dependencies=ctx.protected)
    async def telemetry_export_project(project_id: str) -> Response:
        return await export_file(project_id, ".zip", "application/zip", telemetry.write_project_zip)

    return router
