"""UTF-8 workspace text slice for `read`."""

from __future__ import annotations

import asyncio

from cloudra.persistence.workspace import WorkspaceService
from cloudra.tools.core.observation_offload import cap_observation

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp"}
PDF_EXTS = {".pdf"}


def offset_limit_to_slice(offset: int | None, limit: int | None) -> tuple[int, int]:
    if offset is not None and offset < 1:
        raise ValueError("offset is 1-based")
    start_0 = 0 if offset is None else offset - 1
    end_0 = -1 if limit is None else start_0 + limit
    return start_0, end_0


async def read_text(
    root: str,
    path: str,
    offset: int | None,
    limit: int | None,
) -> dict:
    start_0, end_0 = offset_limit_to_slice(offset, limit)
    service = WorkspaceService(root)
    snapshot, content, total, actual_start, actual_end = await asyncio.to_thread(
        service.read_text,
        path,
        start_0,
        end_0,
    )
    capped = await cap_observation(content, root=root, stem="read")
    message = ""
    if capped != content:
        message = (
            "Full output at .cloudra/tool_output/; page with `read` `offset`/`limit`."
        )
    return {
        "path": snapshot.relative_path,
        "content": capped,
        "sha256": snapshot.sha256,
        "total_lines": total,
        "offset": actual_start + 1,
        "limit": actual_end - actual_start,
        "message": message,
    }
