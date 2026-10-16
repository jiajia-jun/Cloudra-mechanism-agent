"""Project event stream (SSE)."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from cloudra.runtime_v2.events import event_size_bytes

from ..context import ApiContext
from ..sse import _sse, _sse_replay

_STREAM_QUEUE_SIZE = 256
_STREAM_QUEUE_BYTES = 8 * 1024 * 1024


def build_router(ctx: ApiContext) -> APIRouter:
    router = APIRouter()

    @router.get("/api/v2/projects/{project_id}/stream", dependencies=ctx.protected)
    async def project_stream(project_id: str, request: Request, cursor: int) -> StreamingResponse:
        project = ctx.core.require_project(project_id)

        async def generate():
            queue: asyncio.Queue = asyncio.Queue(maxsize=_STREAM_QUEUE_SIZE)
            queued_bytes = 0
            overflowed = False
            # A pending append may still fail and reuse its seq on rollback.
            # Only durable events may advance a stored runtime's reconnect cursor.
            watermarks = (
                ctx.core.event_writer.persisted_watermarks()
                if ctx.core.store is not None else ctx.core.event_log.high_watermarks
            )
            replay_through = watermarks.get(project.id, 0)
            delivered_through = max(cursor, replay_through)

            async def forward(event) -> None:
                nonlocal overflowed, queued_bytes
                if event.project_id != project.id or overflowed:
                    return
                if event.seq and event.seq <= replay_through:
                    return
                try:
                    cost = event_size_bytes(event)
                    if queued_bytes + cost > _STREAM_QUEUE_BYTES:
                        raise asyncio.QueueFull
                    queue.put_nowait((event, cost))
                    queued_bytes += cost
                except asyncio.QueueFull:
                    # Never apply network backpressure to durable event writes.
                    # Stop this stream before exposing a newer cursor; the
                    # client reconnects and replays from its last received seq.
                    overflowed = True
                    ctx.core.event_hub.unsubscribe(forward)
                    while not queue.empty():
                        queue.get_nowait()
                    queued_bytes = 0
                    queue.put_nowait(None)  # wake a consumer already waiting in queue.get()

            # Subscribe only when the body starts. A disconnected response
            # start cannot leave a callback whose generator never ran.
            handler = ctx.core.event_hub.subscribe(forward)
            try:
                async for chunk in _sse_replay(ctx.core, project, cursor, through_seq=replay_through):
                    if overflowed:
                        return
                    yield chunk
                while not overflowed:
                    try:
                        item = await asyncio.wait_for(queue.get(), timeout=15.0)
                        if overflowed:
                            return
                        event, cost = item
                        queued_bytes -= cost
                        if event.seq:
                            if event.seq <= delivered_through:
                                continue
                            if event.seq > delivered_through + 1:
                                # Nested event callbacks can publish a later
                                # durable seq first. Fill that gap from the
                                # authoritative prefix before advancing the
                                # client's reconnect cursor past unseen facts.
                                async for chunk in _sse_replay(
                                    ctx.core, project, delivered_through, through_seq=event.seq,
                                ):
                                    if overflowed:
                                        return
                                    yield chunk
                                delivered_through = event.seq
                                continue
                            delivered_through = event.seq
                        yield _sse(event)
                    except asyncio.TimeoutError:
                        yield ": heartbeat\n\n"
                    if await request.is_disconnected():
                        break
            finally:
                ctx.core.event_hub.unsubscribe(handler)

        return StreamingResponse(generate(), media_type="text/event-stream")

    return router
