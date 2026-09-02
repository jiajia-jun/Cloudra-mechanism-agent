"""Huge observation → `.cloudra/tool_output/` (shared by `read` and later `bash`)."""

from __future__ import annotations

import asyncio
import os
import time
import uuid

from cloudra.persistence.fs_utils import atomic_write_text

MAX_OBSERVATION_CHARS = 30_000
OUTPUT_HEAD_CHARS = 4_000
TOOL_OUTPUT_DIR = os.path.join(".cloudra", "tool_output")


async def cap_observation(text: str, *, root: str | None, stem: str) -> str:
    """If text exceeds 30_000 chars, write all of it under .cloudra/tool_output/ and
    return a head + path. Never drop the file. Caller must mention read+offset/limit."""
    if len(text) <= MAX_OBSERVATION_CHARS:
        return text
    if root:
        name = f"{stem}-{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}.log"
        absolute = os.path.join(root, TOOL_OUTPUT_DIR, name)

        def _dump() -> None:
            os.makedirs(os.path.dirname(absolute), exist_ok=True)
            atomic_write_text(absolute, text)

        try:
            await asyncio.to_thread(_dump)
            relative = os.path.join(TOOL_OUTPUT_DIR, name).replace(os.sep, "/")
            return (
                f"{text[:OUTPUT_HEAD_CHARS]}\n\n"
                f"[Full output at {relative}; page with `read` `offset`/`limit`. "
                f"{len(text)} chars total, showing first {OUTPUT_HEAD_CHARS}.]"
            )
        except OSError:
            pass
    return (
        f"{text[:OUTPUT_HEAD_CHARS]}\n\n"
        f"[Full output could not be saved to the workspace; "
        f"{len(text)} chars total, showing first {OUTPUT_HEAD_CHARS}. "
        "Page with `read` `offset`/`limit`.]"
    )
