"""SSE framing helpers for the project event stream."""

from __future__ import annotations

import json

from cloudra.runtime_v2.events import event_size_bytes

_REPLAY_PAGE_BYTES = 8 * 1024 * 1024


def _sse(event) -> str:
    return f"event: {event.type}\ndata: {json.dumps(event.model_dump(mode='json'), ensure_ascii=False)}\n\n"


async def _sse_replay(core, project, cursor: int, *, through_seq: int | None = None):
    """回放历史事件并以 project.synced 边界标记收尾（前端据此抑制历史事件
    触发的提示）。抽成模块级 helper 是为了可测：httpx ASGITransport 缓冲整个
    响应，无限 SSE 流无法经它断言，测试直接驱动这个生成器。"""
    import asyncio

    from cloudra.runtime_v2.schemas import EventEnvelope

    replayed_through = cursor
    # Capture a project sequence boundary, independently of the resident cache.
    # Advancing this iterator may read SQLite, so consume each page in a worker.
    boundary = (
        core.event_log.high_watermarks.get(project.id, 0)
        if through_seq is None else through_seq
    )
    matching = core.event_log.iter_project(project.id, after_seq=cursor, before_seq=boundary)
    page_size = 500
    exhausted = False

    def take_page():
        nonlocal exhausted
        events = []
        size = 0
        for _ in range(page_size):
            event = next(matching, None)
            if event is None:
                exhausted = True
                break
            events.append(event)
            size += event_size_bytes(event)
            if size >= _REPLAY_PAGE_BYTES:
                break
        return events

    while True:
        events = await asyncio.to_thread(take_page)
        if not events:
            break
        for event in events:
            replayed_through = max(replayed_through, event.seq)
            yield _sse(event)
        if exhausted:
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
