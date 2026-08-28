"""Small, auditable Slurm adapter used by the compute executor."""

from __future__ import annotations

import asyncio
import os
import re
import shlex
import shutil
import subprocess
import time
from collections.abc import Awaitable, Callable
from pathlib import Path

from cloudra.infra.compute_utils import build_calculator_cmd
from cloudra.persistence.database import ConversationDB
from cloudra.runtime.compute_notify import (
    build_compute_finish_content,
    emit_compute_task_finished,
    resolve_submission_info,
)

_SBATCH_VALUE = re.compile(r"[A-Za-z0-9_.:@+/%-]{1,100}\Z")
_MEMORY = re.compile(r"[1-9][0-9]{0,6}(?:[KMGTP])?\Z", re.IGNORECASE)
_TIME_LIMIT = re.compile(r"(?:[0-9]{1,3}-)?[0-9]{1,2}:[0-9]{2}:[0-9]{2}\Z")
_JOB_ID = re.compile(r"[0-9]+(?:_[0-9]+)?\Z")

SLURM_TERMINAL_SUCCESS = frozenset({"COMPLETED"})
SLURM_TERMINAL_FAILURE = frozenset(
    {
        "BOOT_FAIL", "CANCELLED", "DEADLINE", "FAILED", "NODE_FAIL",
        "OUT_OF_MEMORY", "PREEMPTED", "REVOKED", "SPECIAL_EXIT", "TIMEOUT",
    }
)


class SlurmError(RuntimeError):
    pass


def check_slurm_tools() -> tuple[bool, str]:
    missing = [name for name in ("sbatch", "sacct", "scancel") if not shutil.which(name)]
    if missing:
        return False, f"Slurm 命令不可用: {', '.join(missing)}"
    return True, ""


def _directive(name: str, value: object, validator: re.Pattern[str] = _SBATCH_VALUE) -> str:
    text = str(value).strip()
    if not validator.fullmatch(text):
        raise SlurmError(f"无效的 Slurm {name}: {text!r}")
    return f"#SBATCH --{name}={text}"


def build_batch_script(
    input_file: Path,
    job_type: str,
    task_id: int,
    scheduler: dict,
) -> str:
    ok, calculator_cmd, message = build_calculator_cmd(str(input_file), job_type)
    if not ok:
        raise SlurmError(message)
    lines = [
        "#!/bin/bash",
        "set -euo pipefail",
        _directive("job-name", f"cloudra-{task_id}"),
        _directive("output", f"cloudra-slurm-{task_id}-%j.out"),
        _directive("error", f"cloudra-slurm-{task_id}-%j.err"),
    ]
    for key, directive_name in (
        ("partition", "partition"),
        ("account", "account"),
        ("qos", "qos"),
    ):
        value = scheduler.get(key)
        if value:
            lines.append(_directive(directive_name, value))
    if scheduler.get("time_limit"):
        lines.append(_directive("time", scheduler["time_limit"], _TIME_LIMIT))
    if scheduler.get("cpus") is not None:
        cpus = int(scheduler["cpus"])
        if cpus < 1 or cpus > 4096:
            raise SlurmError("Slurm cpus 必须在 1..4096")
        lines.append(f"#SBATCH --cpus-per-task={cpus}")
    if scheduler.get("memory"):
        lines.append(_directive("mem", scheduler["memory"], _MEMORY))
    lines.extend(
        [
            f"cd {shlex.quote(str(input_file.parent))}",
            shlex.join(calculator_cmd),
            "",
        ]
    )
    return "\n".join(lines)


def submit_batch(script_path: Path) -> str:
    completed = subprocess.run(
        ["sbatch", "--parsable", str(script_path)],
        cwd=script_path.parent,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if completed.returncode != 0:
        raise SlurmError((completed.stderr or completed.stdout or "sbatch failed")[:2000])
    job_id = completed.stdout.strip().split(";", 1)[0]
    if not _JOB_ID.fullmatch(job_id):
        raise SlurmError(f"sbatch 返回了无效 job id: {job_id!r}")
    return job_id


def query_job(job_id: str) -> tuple[str, str]:
    if not _JOB_ID.fullmatch(job_id):
        raise SlurmError("无效的 Slurm job id")
    completed = subprocess.run(
        [
            "sacct", "--jobs", job_id, "--noheader", "--parsable2",
            "--format=State,ExitCode",
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if completed.returncode != 0:
        raise SlurmError((completed.stderr or "sacct failed")[:2000])
    rows = [line.strip() for line in completed.stdout.splitlines() if line.strip()]
    if not rows:
        return "PENDING", ""
    state, _, exit_code = rows[0].partition("|")
    return state.split("+", 1)[0].strip().upper(), exit_code.strip()


def cancel_job(job_id: str) -> None:
    if not _JOB_ID.fullmatch(job_id):
        raise SlurmError("无效的 Slurm job id")
    completed = subprocess.run(
        ["scancel", job_id],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if completed.returncode != 0:
        raise SlurmError((completed.stderr or "scancel failed")[:2000])


def cancel_interrupted_jobs(db: ConversationDB) -> int:
    """Best-effort cancellation for Slurm jobs orphaned by server recovery."""
    with db.connect() as con:
        rows = con.execute(
            """SELECT id, scheduler_job_id FROM compute_jobs
            WHERE scheduler='slurm' AND state='failed'
            AND last_error='parent session heartbeat expired'
            AND scheduler_job_id IS NOT NULL
            AND COALESCE(scheduler_state, '') NOT IN
            ('COMPLETED', 'CANCELLED', 'FAILED', 'TIMEOUT', 'CANCEL_FAILED')"""
        ).fetchall()
    cancelled = 0
    for task_id, job_id in rows:
        try:
            cancel_job(str(job_id))
            scheduler_state = "CANCELLED"
            cancelled += 1
        except Exception as exc:
            scheduler_state = "CANCEL_FAILED"
            error = f"Slurm orphan cancellation failed: {exc}"[:2000]
        with db.connect() as con:
            if scheduler_state == "CANCELLED":
                con.execute(
                    "UPDATE compute_jobs SET scheduler_state=? WHERE id=?",
                    (scheduler_state, task_id),
                )
            else:
                con.execute(
                    """UPDATE compute_jobs SET scheduler_state=?, last_error=?
                    WHERE id=?""",
                    (scheduler_state, error, task_id),
                )
            con.commit()
    return cancelled


async def run_slurm_compute(
    task_id: int,
    db_path: str,
    *,
    scheduler: dict,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> int:
    db = ConversationDB.from_path(db_path)
    async with db.aconnect() as con:
        row = await (
            await con.execute(
                "SELECT conversation_id, path, jobtype, state, scheduler_job_id "
                "FROM compute_jobs WHERE id=?",
                (task_id,),
            )
        ).fetchone()
    if not row:
        raise SlurmError(f"compute job {task_id} 不存在")
    conversation_id, raw_path, job_type, db_state, scheduler_job_id = row
    input_file = Path(raw_path).expanduser().resolve(strict=True)
    if not scheduler_job_id:
        script_path = input_file.parent / f".cloudra-slurm-{task_id}.sh"
        script_path.write_text(
            build_batch_script(input_file, job_type, task_id, scheduler),
            encoding="utf-8",
        )
        os.chmod(script_path, 0o700)
        scheduler_job_id = submit_batch(script_path)
        async with db.aconnect() as con:
            await con.execute(
                """UPDATE compute_jobs SET scheduler_job_id=?, scheduler_script=?,
                scheduler_state='PENDING', start_timestamp=? WHERE id=?""",
                (str(scheduler_job_id), str(script_path), time.time(), task_id),
            )
            await con.commit()

    poll_seconds = min(max(float(scheduler.get("poll_seconds", 15)), 1), 300)
    while True:
        async with db.aconnect() as con:
            current = await (
                await con.execute("SELECT state FROM compute_jobs WHERE id=?", (task_id,))
            ).fetchone()
        if current and current[0] in {"cancelled", "cancel_requested"}:
            await asyncio.to_thread(cancel_job, str(scheduler_job_id))
            async with db.aconnect() as con:
                await con.execute(
                    """UPDATE compute_jobs SET state='cancelled',
                    scheduler_state='CANCELLED', end_timestamp=? WHERE id=?""",
                    (time.time(), task_id),
                )
                await con.commit()
            return 1
        state, exit_code = await asyncio.to_thread(query_job, str(scheduler_job_id))
        async with db.aconnect() as con:
            await con.execute(
                "UPDATE compute_jobs SET scheduler_state=? WHERE id=?",
                (state, task_id),
            )
            await con.commit()
        if state in SLURM_TERMINAL_SUCCESS | SLURM_TERMINAL_FAILURE:
            final = "done" if state in SLURM_TERMINAL_SUCCESS else "failed"
            async with db.aconnect() as con:
                await con.execute(
                    """UPDATE compute_jobs SET state=?, end_timestamp=?, last_error=?
                    WHERE id=?""",
                    (
                        final,
                        time.time(),
                        None if final == "done" else f"Slurm {state} ({exit_code})",
                        task_id,
                    ),
                )
                await con.commit()
            info = await resolve_submission_info(db, task_id)
            content = build_compute_finish_content(
                task_id=task_id,
                state=final,
                input_path=str(info.get("path") or ""),
                fail_reason="" if final == "done" else f"Slurm {state} ({exit_code})",
            )
            emit_compute_task_finished(
                conversation_id,
                task_id=task_id,
                state=final,
                content=content,
                session_id=info.get("session_id"),
                notify_coordinator=True,
            )
            return 0 if final == "done" else 1
        await sleep(poll_seconds)
