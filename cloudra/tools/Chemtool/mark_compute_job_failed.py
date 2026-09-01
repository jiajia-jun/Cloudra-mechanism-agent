"""mark_compute_job_failed: force a stuck compute job to a failed terminal state.

Orphaned jobs (executor/guard process died, files deleted, DB still says
"running") block delivery stages forever.  This tool lets an agent explicitly
mark such a job failed with a recorded reason instead of waiting for the lease
to expire.
"""

import os
from typing import Any

from pydantic import Field

from cloudra.base.session_class import Session
from cloudra.base.tools_class import Tool, input_schema, output_schema
from cloudra.persistence.database import ComputeDB
from cloudra.services.compute_store import afail_compute_job, aget_compute_job

description = (
    "Force a compute job into the failed state with a recorded reason. "
    "Use for: a job that is stuck 'running' forever because its executor/guard "
    "process died or its input/log files were removed — confirm with `ps -p <pid>` "
    "/ file existence first, then mark it failed so the DAG stage can be re-planned. "
    "The system never kills processes or marks jobs failed on its own, so reconcile "
    "dead jobs yourself with this tool. "
    "Do not use for: a job that is still legitimately running, or a job that "
    "already reached done/failed (marking is refused for terminal jobs)."
)


class MarkComputeJobFailed_input_schema(input_schema):
    job_id: int = Field(
        description="Compute job ID (from submit_compute_job / query_compute_job).",
    )
    reason: str = Field(
        description="Why the job is being marked failed (recorded for audit); "
        "state what you verified, e.g. 'lease_owner process not in ps and input deleted'.",
    )


class MarkComputeJobFailed_output_schema(output_schema):
    is_success: bool = Field(description="Whether the job was marked failed")
    job_id: int = Field(default=-1, description="The job id")
    previous_state: str = Field(default="", description="State before this call")
    message: str = Field(default="", description="Status or error message")


class MarkComputeJobFailed(Tool):
    tool_id: str = "t-mark-compute-failed"
    tool_name: str = "mark_compute_job_failed"
    tool_description: str = description
    input_schema: Any = MarkComputeJobFailed_input_schema
    output_schema: Any = MarkComputeJobFailed_output_schema

    def is_write(self) -> bool:
        return True

    async def tool_call(
        self, user_input: MarkComputeJobFailed_input_schema, session: Session
    ) -> MarkComputeJobFailed_output_schema:
        reason = (user_input.reason or "").strip()
        if not reason:
            return MarkComputeJobFailed_output_schema(
                is_success=False, job_id=user_input.job_id, message="reason is required"
            )
        conv_id = getattr(self.subagent, "conversation_id", None) or "default"
        db = ComputeDB()
        if not os.path.exists(db.path):
            return MarkComputeJobFailed_output_schema(
                is_success=False, job_id=user_input.job_id,
                message="no compute-jobs database on this node yet",
            )
        try:
            row = await aget_compute_job(db, user_input.job_id)
            if row is None or row["conversation_id"] != conv_id:
                return MarkComputeJobFailed_output_schema(
                    is_success=False, job_id=user_input.job_id,
                    message=f"No compute job found for job_id={user_input.job_id}.",
                )
            previous_state = row["state"] or ""
            if previous_state in ("done", "failed"):
                return MarkComputeJobFailed_output_schema(
                    is_success=False, job_id=user_input.job_id,
                    previous_state=previous_state,
                    message=f"job {user_input.job_id} is already terminal ({previous_state}).",
                )
            await afail_compute_job(db, user_input.job_id, reason)
        except Exception as exc:
            return MarkComputeJobFailed_output_schema(
                is_success=False, job_id=user_input.job_id, message=f"mark failed: {exc}"
            )
        try:
            from cloudra.dag.controller import enqueue_compute_review

            await enqueue_compute_review(user_input.job_id, "failed")
        except Exception:
            pass  # 非 dag 模式/无 session 时内部跳过；失败不影响落库
        return MarkComputeJobFailed_output_schema(
            is_success=True,
            job_id=user_input.job_id,
            previous_state=previous_state,
            message=f"job {user_input.job_id} marked failed (was {previous_state}); reason recorded.",
        )


def get_class():
    return MarkComputeJobFailed
