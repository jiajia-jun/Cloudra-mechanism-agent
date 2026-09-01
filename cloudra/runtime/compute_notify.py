"""Compute job terminal notification content builders.

guard/Slurm 终态只 CAS 写中央 compute.db；API 进程的 ``ComputeNotifyBroker``
轮询 compute_jobs 表并用这里的构建件把终态重建为 ``agent.message`` 文本。
"""

from __future__ import annotations

from typing import Any

from cloudra.persistence.database import ComputeDB


def build_compute_finish_content(
    *,
    task_id: int,
    state: str,
    input_path: str = "",
    log_path: str = "",
    json_path: str = "",
    fail_reason: str = "",
) -> str:
    if state == "done":
        guidance = (
            "Next: use log_parser on the log to extract energy/frequencies and other results."
        )
    else:
        guidance = (
            (f"Failure reason: {fail_reason}\n" if fail_reason else "")
            + "Next: use query_compute_job to inspect last_error, and read the log to locate the failure; "
            "if needed, fix the input file and resubmit with submit_compute_job. "
            "If you cannot resolve it, email the user."
        )
    lines = [
        f"Compute job task_id={task_id} finished, state={state}.",
    ]
    if input_path:
        lines.append(f"Input file: {input_path}")
    if log_path:
        lines.append(f"Log file: {log_path}")
    if json_path:
        lines.append(f"Structured result: {json_path}")
    lines.append(guidance)
    return "\n".join(lines)


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
