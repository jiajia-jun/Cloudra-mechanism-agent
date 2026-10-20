"""mark_compute_job_failed: reconcile a dead local orphan.

The scheduler normally adopts crashed workers. This tool reconciles a remaining
local orphan without overriding execution ownership or replacing cancellation.
"""

import os
from typing import Any

from pydantic import Field

from cloudra.base.session_class import Session
from cloudra.base.tools_class import Tool, input_schema, output_schema
from cloudra.persistence.database import ComputeDB
from cloudra.services.compute_store import afail_compute_job, aget_compute_job

description = (
    "Reconcile a local orphan still recorded as running, with a recorded reason. "
    "The runtime checks calculator/guard locks and refuses to fail a live calculation. "
    "The scheduler also adopts and finalizes crashed workers automatically. "
    "Do not use to withdraw queued work, cancel a calculation, free capacity, or declare scientific failure. "
    "For a TS workflow use ts_stop to withdraw queued work/request safe cancellation. "
    "Remote/scheduler jobs must be finalized by their execution poller; absence of a local process is not proof of exit."
)


class MarkComputeJobFailed_input_schema(input_schema):
    job_id: int = Field(
        description="Compute job ID (from submit_compute_job / query_compute_job).",
    )
    reason: str = Field(
        description="Reason for reconciling this dead local orphan, recorded for audit. "
        "This is not a cancellation request or a scientific verdict.",
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
        previous_state = ""
        try:
            row = await aget_compute_job(db, user_input.job_id)
            if row is None or row["conversation_id"] != conv_id:
                return MarkComputeJobFailed_output_schema(
                    is_success=False, job_id=user_input.job_id,
                    message=f"No compute job found for job_id={user_input.job_id}.",
                )
            previous_state = row["state"] or ""
            if previous_state in ("done", "failed", "cancelled"):
                return MarkComputeJobFailed_output_schema(
                    is_success=False, job_id=user_input.job_id,
                    previous_state=previous_state,
                    message=f"job {user_input.job_id} is already terminal ({previous_state}).",
                )
            if previous_state == "ready":
                return MarkComputeJobFailed_output_schema(
                    is_success=False, job_id=user_input.job_id, previous_state=previous_state,
                    message="Queued work cannot be withdrawn as failed; use cancellation controls (ts_stop for a TS workflow).",
                )
            if (row.get("scheduler") or "local") != "local":
                return MarkComputeJobFailed_output_schema(
                    is_success=False, job_id=user_input.job_id, previous_state=previous_state,
                    message="Remote execution liveness is unknown here; its execution poller must confirm the terminal state.",
                )
            wrote = await afail_compute_job(db, user_input.job_id, reason)
            if not wrote:
                return MarkComputeJobFailed_output_schema(
                    is_success=False,
                    job_id=user_input.job_id,
                    previous_state=previous_state,
                    message=(
                        f"job {user_input.job_id} was not changed; "
                        "its state changed or it is awaiting execution-side cancellation confirmation"
                    ),
                )
        except Exception as exc:
            return MarkComputeJobFailed_output_schema(
                is_success=False, job_id=user_input.job_id,
                previous_state=previous_state,
                message=f"mark failed: {exc}",
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
