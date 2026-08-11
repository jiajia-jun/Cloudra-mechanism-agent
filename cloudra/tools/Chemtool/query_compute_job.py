import os
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import Field

from cloudra.base.session_class import Session
from cloudra.base.tools_class import Tool, input_schema, output_schema
from cloudra.persistence.database import ConversationDB, get_database_path

description = (
    "查询计算任务状态：按 job_id 查看 submit_compute_job 提交的任务当前状态、"
    "工作目录、起止时间与失败原因；不传 job_id 时列出本会话最近的任务。"
    "适用：提交异步计算后确认任务是 ready/running/done/failed，或失败时查看 last_error。"
    "不适用：提交新任务（用 submit_compute_job）、解析已完成计算的日志（用 log_parser）。"
)


class QueryComputeJob_input_schema(input_schema):
    job_id: Optional[int] = Field(
        default=None,
        description="要查询的计算任务 ID（submit_compute_job 返回的 job_id）。不传则列出最近任务。",
    )
    limit: int = Field(
        default=10,
        description="不传 job_id 时，列出最近多少条任务记录。",
    )


class QueryComputeJob_output_schema(output_schema):
    is_success: bool = Field(description="查询是否成功")
    jobs: List[Dict[str, Any]] = Field(default_factory=list, description="任务记录列表")
    message: str = Field(default="", description="状态或错误信息")


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
            return QueryComputeJob_output_schema(is_success=True, jobs=[], message="本会话还没有任何计算任务。")

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
                            message=f"未找到 job_id={user_input.job_id} 的计算任务。",
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
            return QueryComputeJob_output_schema(is_success=False, jobs=[], message=f"查询失败：{e}")

        jobs = [_row_to_dict(row) for row in rows]
        return QueryComputeJob_output_schema(
            is_success=True,
            jobs=jobs,
            message=f"共 {len(jobs)} 条任务记录。",
        )


def get_class():
    return QueryComputeJob
