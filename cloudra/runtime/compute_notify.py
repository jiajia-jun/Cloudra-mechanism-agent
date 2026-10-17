"""Resolve compute submission ownership for the terminal-notification broker."""

from __future__ import annotations

from typing import Any

from cloudra.persistence.database import ComputeDB


async def resolve_submission_info(db: ComputeDB, task_id: int) -> dict[str, Any]:
    """Return submitter session_id and input path for one compute job."""
    from cloudra.services.compute_store import aget_compute_job

    info: dict[str, Any] = {"session_id": None, "path": ""}
    try:
        row = await aget_compute_job(db, task_id)
    except Exception:
        row = None
    if row:
        info["session_id"] = row["session_id"]
        info["path"] = row["path"] or ""
    return info
