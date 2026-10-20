"""Request cancellation by job identity; execution ownership stays internal."""

from typing import Any

from pydantic import Field

from cloudra.base.session_class import Session
from cloudra.base.tools_class import Tool, input_schema, output_schema
from cloudra.persistence.database import ComputeDB
from cloudra.services.compute_store import arequest_compute_job_cancellation


class CancelComputeJob_input_schema(input_schema):
    job_id: int = Field(description="Compute job ID returned by submit_compute_job.")
    reason: str = Field(min_length=1, description="Why this queued or running job should be cancelled.")


class CancelComputeJob_output_schema(output_schema):
    is_success: bool
    job_id: int
    previous_state: str = ""
    state: str = ""
    message: str = ""


class CancelComputeJob(Tool):
    tool_id: str = "t-cancel-compute"
    tool_name: str = "cancel_compute_job"
    tool_description: str = (
        "Cancel one compute job belonging to this project, using its job ID and a reason. "
        "Queued work is withdrawn immediately; running work receives a cancellation request "
        "and keeps its capacity until its execution owner confirms actual exit. "
        "Use for withdrawing superseded direct submissions or stopping a calculation; "
        "do not mark such jobs failed or send process signals yourself. "
        "For an automatic TS workflow use ts_stop to also stop future stage advancement. "
        "Cancellation does not declare scientific failure."
    )
    input_schema: Any = CancelComputeJob_input_schema
    output_schema: Any = CancelComputeJob_output_schema

    def is_write(self) -> bool:
        return True

    async def tool_call(self, user_input: CancelComputeJob_input_schema, session: Session):
        try:
            result = await arequest_compute_job_cancellation(
                ComputeDB(), user_input.job_id,
                project_id=getattr(self.subagent, "conversation_id", None) or "",
                reason=user_input.reason,
            )
        except (LookupError, ValueError) as exc:
            return CancelComputeJob_output_schema(is_success=False, job_id=user_input.job_id, message=str(exc))
        return CancelComputeJob_output_schema(**result)
