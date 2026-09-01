"""Project event stream (SSE)."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from ..context import ApiContext
from ..sse import _sse, _sse_replay


def build_router(ctx: ApiContext) -> APIRouter:
    router = APIRouter()

    @router.get("/api/v2/projects/{project_id}/stream", dependencies=ctx.protected)
    async def project_stream(project_id: str, request: Request, cursor: int = 0) -> StreamingResponse:
        project = ctx.core.require_project(project_id)
        queue: asyncio.Queue = asyncio.Queue()

        async def forward(event) -> None:
            if event.project_id == project.id:
                await queue.put(event)

        handler = ctx.core.event_hub.subscribe(forward)

        async def generate():
            try:
                async for chunk in _sse_replay(ctx.core, project, cursor):
                    yield chunk
                while True:
                    try:
                        event = await asyncio.wait_for(queue.get(), timeout=15.0)
                        yield _sse(event)
                    except asyncio.TimeoutError:
                        yield ": heartbeat\n\n"
                    if await request.is_disconnected():
                        break
            finally:
                ctx.core.event_hub.unsubscribe(handler)

        return StreamingResponse(generate(), media_type="text/event-stream")

    return router
