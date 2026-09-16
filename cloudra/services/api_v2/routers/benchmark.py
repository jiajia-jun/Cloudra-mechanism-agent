"""Benchmark batch control plane (GH #32 Phase 1).

Start/stop/status/history over the hosted BenchmarkService, plus an SSE feed
of batch events (batch_started / task_started / task_scored / task_cancelled /
task_error / batch_finished). The service lives on the app state so routes stay
thin; all task-level runtime work happens on the live core through the
CommandBus.
"""

from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from ..context import ApiContext
from ..models import BenchmarkStart


def _sse_event(event: dict) -> str:
    return f"event: {event['type']}\ndata: {json.dumps(event['data'], ensure_ascii=False)}\n\n"


def build_router(ctx: ApiContext) -> APIRouter:
    router = APIRouter()
    service = ctx.benchmark

    @router.post("/api/v2/benchmark/start", dependencies=ctx.protected)
    async def start_batch(body: BenchmarkStart) -> dict:
        return await service.start(
            tasks_dirs=body.tasks_dirs or None,
            only=body.only,
            concurrency=body.concurrency,
            timeout=body.timeout,
            tiers=body.tiers or None,
        )

    @router.get("/api/v2/benchmark/catalog", dependencies=ctx.protected)
    async def batch_catalog() -> dict:
        """内置档位清单（档位/目录/题目 id），供前端选题器使用。"""
        return await service.catalog()

    @router.post("/api/v2/benchmark/stop", dependencies=ctx.protected)
    async def stop_batch() -> dict:
        return await service.stop()

    @router.get("/api/v2/benchmark/status", dependencies=ctx.protected)
    async def batch_status() -> dict:
        return service.status()

    @router.get("/api/v2/benchmark/runs", dependencies=ctx.protected)
    async def batch_history() -> dict:
        return await service.history()

    @router.get("/api/v2/benchmark/stream", dependencies=ctx.protected)
    async def batch_stream(request: Request) -> StreamingResponse:
        """SSE：先推当前批次快照（benchmark.snapshot），再实时推批次事件。"""
        queue = service.subscribe()

        async def generate():
            try:
                yield _sse_event(
                    {"type": "benchmark.snapshot", "data": service.status()}
                )
                while True:
                    try:
                        event = await asyncio.wait_for(queue.get(), timeout=15.0)
                        yield _sse_event(event)
                    except asyncio.TimeoutError:
                        yield ": heartbeat\n\n"
                    if await request.is_disconnected():
                        break
            finally:
                service.unsubscribe(queue)

        return StreamingResponse(generate(), media_type="text/event-stream")

    return router
