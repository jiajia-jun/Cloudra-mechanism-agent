"""Small, auditable Slurm adapter used by the compute executor."""

from __future__ import annotations

import asyncio
import os
import re
import shlex
import shutil
import subprocess
from collections.abc import Awaitable, Callable
from pathlib import Path

from cloudra.infra.compute_utils import XtbParams, build_calculator_cmd
from cloudra.persistence.database import ComputeDB
from cloudra.services.compute_store import (
    acancel_compute_job,
    afinalize_compute_job,
    aget_compute_job,
    amark_slurm_submitted,
    aupdate_scheduler_state,
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
    *,
    xtb_params: XtbParams | None = None,
) -> str:
    ok, calculator_cmd, message = build_calculator_cmd(
        str(input_file), job_type, xtb_params=xtb_params
    )
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


async def run_slurm_compute(
    task_id: int,
    db_path: str,
    *,
    scheduler: dict,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> int:
    db = ComputeDB.from_path(db_path)
    row = await aget_compute_job(db, task_id)
    if not row:
        raise SlurmError(f"compute job {task_id} 不存在")
    scheduler_job_id = row["scheduler_job_id"]
    input_file = Path(row["path"]).expanduser().resolve(strict=True)
    if not scheduler_job_id:
        script_path = input_file.parent / f".cloudra-slurm-{task_id}.sh"
        # xtb 任务参数（charge/mult/task/solvent/cpus）从 compute_jobs 行透传
        xtb_params = (
            XtbParams.from_row(row) if (row["jobtype"] or "") == "xtb" else None
        )
        script_path.write_text(
            build_batch_script(
                input_file, row["jobtype"], task_id, scheduler, xtb_params=xtb_params
            ),
            encoding="utf-8",
        )
        os.chmod(script_path, 0o700)
        scheduler_job_id = submit_batch(script_path)
        await amark_slurm_submitted(db, task_id, str(scheduler_job_id), str(script_path))

    poll_seconds = min(max(float(scheduler.get("poll_seconds", 15)), 1), 300)
    while True:
        current = await aget_compute_job(db, task_id)
        if current and current["state"] in {"cancelled", "cancel_requested"}:
            await asyncio.to_thread(cancel_job, str(scheduler_job_id))
            await acancel_compute_job(db, task_id)
            return 1
        state, exit_code = await asyncio.to_thread(query_job, str(scheduler_job_id))
        await aupdate_scheduler_state(db, task_id, state)
        if state in SLURM_TERMINAL_SUCCESS | SLURM_TERMINAL_FAILURE:
            final = "done" if state in SLURM_TERMINAL_SUCCESS else "failed"
            await afinalize_compute_job(
                db,
                task_id,
                final,
                last_error=None if final == "done" else f"Slurm {state} ({exit_code})",
                only_running=False,
            )
            # 终态通知由 ComputeNotifyBroker 轮询 compute_jobs 表补投，不再发 IPC
            return 0 if final == "done" else 1
        await sleep(poll_seconds)
