import os
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import Field

from cloudra.base.session_class import Session
from cloudra.base.tools_class import Tool, input_schema, output_schema
from cloudra.persistence.database import ComputeDB
from cloudra.services.compute_store import TERMINAL_STATES, aget_compute_job, alist_compute_jobs

description = (
    "Query compute-job status: by job_id, show the current state, working directory, start/end times, and failure reason of a job submitted with submit_compute_job; "
    "without job_id, list recent jobs in this session. "
    "Use for: diagnosing a FAILED job (reading last_error) or confirming a job record exists after a submission error. "
    "Do not use for: submitting a new job (use submit_compute_job), queue/capacity overview (use query_compute_queue), "
    "or parsing a finished log (use log_parser). "
    "NEVER call this tool to wait on a running/queued job. Terminal states are PUSHED to you automatically — you are "
    "woken the moment the job finishes, so a poll can only ever return information you already had while burning a "
    "model turn each time. Polling to wait is a protocol violation: the only acceptable reason to query a "
    "non-terminal job is diagnosing a broken submission. If you genuinely need an interim checkpoint, `schedule` a "
    "one-shot read-only check_command and stop. "
    "Note: the scheduler daemon reconciles crashed workers automatically (lock-based, it never kills processes), "
    "so a dead worker's job is adopted and finalized deterministically; mark_compute_job_failed remains the manual "
    "escape hatch when you have out-of-band proof a job is truly gone."
)


class QueryComputeJob_input_schema(input_schema):
    job_id: Optional[int] = Field(
        default=None,
        description="Compute job ID to query (job_id returned by submit_compute_job). Omit to list recent jobs.",
    )
    limit: int = Field(
        default=10,
        description="How many recent job records to list when job_id is omitted.",
    )


class QueryComputeJob_output_schema(output_schema):
    is_success: bool = Field(description="Whether the query succeeded")
    jobs: List[Dict[str, Any]] = Field(default_factory=list, description="Job records")
    message: str = Field(default="", description="Status or error message")


def _iso(ts) -> str:
    try:
        ts = float(ts)
    except (TypeError, ValueError):
        return ""
    if ts <= 0:
        return ""
    return datetime.fromtimestamp(ts).astimezone().isoformat(timespec="seconds")


def _row_to_dict(row: Dict[str, Any]) -> Dict[str, Any]:
    path = row["path"] or ""
    # log_path 与完成通知统一走 resolve_log_path（GH #20）：优先 guard state
    # json 记录的真实日志 / calc 落盘文件，都没有才回退引擎惯例预测。
    from cloudra.infra.compute_utils import resolve_log_path

    log_path = (
        resolve_log_path(path, job_type=row["jobtype"] or "gaussian", task_id=row["id"])
        if path
        else ""
    )
    out = {
        "job_id": row["id"],
        "state": row["state"],
        "scheduler": row["scheduler"],
        "scheduler_state": row["scheduler_state"] or "",
        "jobtype": row["jobtype"],
        "path": path,
        "log_path": log_path,
        "started_at": _iso(row["start_timestamp"]),
        "ended_at": _iso(row["end_timestamp"]),
        "last_error": row["last_error"] or "",
        "attempt_count": row["attempt_count"] or 0,
    }
    if row["jobtype"] == "xtb":
        # xtb 显式任务参数（--chrg/--uhf/multiplicity、运行级别、溶剂、并行核数）
        out["charge"] = row["charge"] if row["charge"] is not None else 0
        out["multiplicity"] = row["multiplicity"] or 1
        out["task"] = row["xtb_task"] or "sp"
        out["solvent"] = row["xtb_solvent"] or ""
        out["cpus"] = row["req_cpus"] or 1
    return out


class QueryComputeJob(Tool):
    tool_id: str = 't-48'
    tool_name: str = 'query_compute_job'
    tool_description: str = description
    input_schema: Any = QueryComputeJob_input_schema
    output_schema: Any = QueryComputeJob_output_schema

    def is_read(self) -> bool:
        return True

    async def tool_call(self, user_input: QueryComputeJob_input_schema, session: Session) -> QueryComputeJob_output_schema:
        conv_id = getattr(self.subagent, 'conversation_id', None) or 'default'
        # compute_jobs 住中央库（节点级共享）；按 conversation_id 过滤出本会话的作业
        db = ComputeDB()
        if not os.path.exists(db.path):
            return QueryComputeJob_output_schema(is_success=True, jobs=[], message="No compute jobs have been submitted in this conversation yet.")

        try:
            if user_input.job_id is not None:
                row = await aget_compute_job(db, user_input.job_id)
                if row is None or row["conversation_id"] != conv_id:
                    return QueryComputeJob_output_schema(
                        is_success=False,
                        jobs=[],
                        message=f"No compute job found for job_id={user_input.job_id}.",
                    )
                rows = [row]
            else:
                limit = max(1, min(int(user_input.limit or 10), 50))
                rows = await alist_compute_jobs(
                    db, conversation_id=conv_id, order="recent", limit=limit
                )
        except Exception as e:
            return QueryComputeJob_output_schema(is_success=False, jobs=[], message=f"Query failed: {e}")

        jobs = [_row_to_dict(row) for row in rows]
        message = f"{len(jobs)} job record(s)."
        if any(job["state"] not in TERMINAL_STATES for job in jobs):
            message += (
                " STOP POLLING. Some jobs are still in a non-terminal state, and re-querying "
                "will NOT change that: terminal states (done/failed/cancelled) are PUSHED to you "
                "automatically and will wake you the instant the job finishes. Every additional "
                "query_compute_job call before the push arrives returns nothing new and burns a "
                "model turn; ending your turn repeatedly with no new progress is strike-counted "
                "by the completion gate and FAILS your run. Your only correct actions now: do "
                "other work, or end your turn and wait for the push. If you genuinely need an "
                "interim checkpoint, use schedule once with a one-shot read-only check_command."
            )
        return QueryComputeJob_output_schema(
            is_success=True,
            jobs=jobs,
            message=message,
        )


def get_class():
    return QueryComputeJob
