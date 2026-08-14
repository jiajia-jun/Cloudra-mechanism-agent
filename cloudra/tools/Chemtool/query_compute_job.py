import os
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import Field

from cloudra.base.session_class import Session
from cloudra.base.tools_class import Tool, input_schema, output_schema
from cloudra.persistence.database import ConversationDB, get_database_path

description = (
    "Query compute-job status: by job_id, show the current state, working directory, start/end times, and failure reason of a job submitted with submit_compute_job; "
    "without job_id, list recent jobs in this session. "
    "Use for: confirming an async job is ready/running/done/failed, or reading last_error on failure. "
    "Do not use for: submitting a new job (use submit_compute_job) or parsing a finished log (use gaussian_log_parser)."
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


def _row_to_dict(row) -> Dict[str, Any]:
    (job_id, state, path, start_ts, end_ts, jobtype, scheduler,
     scheduler_state, last_error, attempt_count) = row
    log_path = ""
    if path:
        base, ext = os.path.splitext(path)
        if ext.lower() in (".gjf", ".com", ".inp"):
            log_path = base + ".log"
    return {
        "job_id": job_id,
        "state": state,
        "scheduler": scheduler,
        "scheduler_state": scheduler_state or "",
        "jobtype": jobtype,
        "path": path or "",
        "log_path": log_path,
        "started_at": _iso(start_ts),
        "ended_at": _iso(end_ts),
        "last_error": last_error or "",
        "attempt_count": attempt_count or 0,
    }


class QueryComputeJob(Tool):
    tool_id: str = 't-48'
    tool_name: str = 'query_compute_job'
    tool_description: str = description
    input_schema: Any = QueryComputeJob_input_schema
    output_schema: Any = QueryComputeJob_output_schema

    def is_read(self) -> bool:
        return True

    async def tool_call(self, user_input: QueryComputeJob_input_schema, session: Session) -> QueryComputeJob_output_schema:
        conv_id = getattr(self.subagent, 'conversation_id', 'default')
        db = ConversationDB.from_path(get_database_path(conv_id))
        if not os.path.exists(db.path):
            return QueryComputeJob_output_schema(is_success=True, jobs=[], message="No compute jobs have been submitted in this conversation yet.")

        columns = (
            "id, state, path, start_timestamp, end_timestamp, jobtype,"
            " scheduler, scheduler_state, last_error, attempt_count"
        )
        try:
            async with db.aconnect() as con:
                if user_input.job_id is not None:
                    cur = await con.execute(
                        f"SELECT {columns} FROM compute_jobs WHERE id=? AND conversation_id=?",
                        (user_input.job_id, conv_id),
                    )
                    rows = await cur.fetchall()
                    if not rows:
                        return QueryComputeJob_output_schema(
                            is_success=False,
                            jobs=[],
                            message=f"No compute job found for job_id={user_input.job_id}.",
                        )
                else:
                    limit = max(1, min(int(user_input.limit or 10), 50))
                    cur = await con.execute(
                        f"SELECT {columns} FROM compute_jobs WHERE conversation_id=?"
                        " ORDER BY id DESC LIMIT ?",
                        (conv_id, limit),
                    )
                    rows = await cur.fetchall()
        except Exception as e:
            return QueryComputeJob_output_schema(is_success=False, jobs=[], message=f"Query failed: {e}")

        jobs = [_row_to_dict(row) for row in rows]
        return QueryComputeJob_output_schema(
            is_success=True,
            jobs=jobs,
            message=f"{len(jobs)} job record(s).",
        )


def get_class():
    return QueryComputeJob
