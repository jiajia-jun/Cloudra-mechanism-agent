"""SSE framing helpers for the project event stream."""

from __future__ import annotations

import json
from itertools import islice


def _sse(event) -> str:
    return f"event: {event.type}\ndata: {json.dumps(event.model_dump(mode='json'), ensure_ascii=False)}\n\n"


async def _sse_replay(core, project, cursor: int):
    """回放历史事件并以 project.synced 边界标记收尾（前端据此抑制历史事件
    触发的提示）。抽成模块级 helper 是为了可测：httpx ASGITransport 缓冲整个
    响应，无限 SSE 流无法经它断言，测试直接驱动这个生成器。"""
    import asyncio

    from cloudra.runtime_v2.schemas import EventEnvelope

    replayed_through = cursor
    # Snapshot the append-only log's initial prefix without copying its backlog.
    # One iterator avoids rescanning all history for every page. Events appended
    # after this boundary are already captured by the router's live subscription.
    history = islice(iter(core.event_log), len(core.event_log))
    matching = (
        event for event in history
        if event.project_id == project.id and event.seq > cursor
    )
    page_size = 500
    while True:
        events = await asyncio.to_thread(lambda: list(islice(matching, page_size)))
        if not events:
            break
        for event in events:
            replayed_through = max(replayed_through, event.seq)
            yield _sse(event)
        if len(events) < page_size:
            break
    # seq=0 不影响客户端 cursor
    yield _sse(
        EventEnvelope(
            stream="project",
            project_id=project.id,
            seq=0,
            type="project.synced",
            data={"replayed_through": replayed_through},
        )
    )
