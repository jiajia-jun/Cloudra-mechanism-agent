"""Compute job terminal notifications: IPC payload for runtime_v2 delivery.

Guard/Slurm/executor processes emit ``task_finished`` with a full message body;
the API process ``ComputeNotifyBroker`` turns that into ``agent.message``.
"""

from __future__ import annotations

from typing import Any

from cloudra.infra import events
from cloudra.persistence.database import ConversationDB


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
            "Next: use gaussian_log_parser on the log to extract energy/frequencies and other results."
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


async def resolve_submission_info(db: ConversationDB, task_id: int) -> dict[str, Any]:
    """Return submitter session_id and input path for one compute job."""
    info: dict[str, Any] = {"session_id": None, "path": ""}
    try:
        async with db.aconnect() as con:
            cur = await con.execute(
                "SELECT session_id, path FROM compute_jobs WHERE id=?",
                (task_id,),
            )
            row = await cur.fetchone()
            if row:
                info["session_id"] = row[0]
                info["path"] = row[1] or ""
    except Exception:
        pass
    return info


def emit_compute_task_finished(
    conversation_id: str,
    *,
    task_id: int,
    state: str,
    content: str,
    session_id: str | None,
    notify_coordinator: bool = True,
) -> None:
    """Broadcast a compute terminal event to the API process (best-effort)."""
    try:
        events.emit(
            conversation_id,
            "task_finished",
            task_id=task_id,
            task_kind="compute",
            state=state,
            content=content,
            session_id=session_id,
            notify_coordinator=notify_coordinator,
        )
    except Exception:
        pass
