"""Compute job terminal notification content builders.

guard/Slurm 终态只 CAS 写中央 compute.db；API 进程的 ``ComputeNotifyBroker``
轮询 compute_jobs 表并用这里的构建件把终态重建为 ``agent.message`` 文本。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from cloudra.persistence.database import ComputeDB


def build_compute_knowledge_query(
    *,
    state: str,
    job_type: str = "gaussian",
    fail_reason: str = "",
    input_path: str = "",
) -> str:
    """Pure decision: terminal compute job → chem-kb library query string.

    Failed jobs query by the readable failure reason (which carries the
    termination marker / SCF / imaginary-frequency diagnostics the KB indexes);
    successful jobs fall back to the engine + input-file stem.
    """
    if state == "failed":
        return (fail_reason or f"{job_type} computation failed")[:500]
    stem = Path(input_path).stem if input_path else ""
    return " ".join(part for part in (job_type, stem) if part)[:300]


def build_compute_finish_content(
    *,
    task_id: int,
    state: str,
    input_path: str = "",
    log_path: str = "",
    json_path: str = "",
    fail_reason: str = "",
    library_hits: list[dict[str, Any]] | None = None,
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
    if library_hits:
        from cloudra.runtime_v2.knowledge import render_library_hits

        lines.append(
            "Knowledge base suggestions (auto-retrieved for this terminal state):\n"
            + render_library_hits(library_hits)
        )
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
