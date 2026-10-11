from typing import Any, Literal

from pydantic import Field

from cloudra.base.session_class import Session
from cloudra.base.tools_class import Tool, input_schema, output_schema


class StopTool_input_schema(input_schema):
    reason: str = Field(
        default="",
        description="Reason for stopping, optional"
    )
    final_answer: str = Field(
        default="",
        description="Candidate final answer. It is published only after the runtime completion gate allows final delivery."
    )
    delivery_disposition: Literal["complete", "partial", "user_terminated"] = Field(
        default="complete",
        description=(
            "DAG-mode delivery declaration (defaults to complete when omitted): complete must pass evidence-derived coverage; "
            "partial finishes with remaining gaps (this is a final delivery statement, not a pause); "
            "user_terminated means the user asked to stop. "
            "If background jobs/reminders are still pending, stop only suspends — no audit and no disposition is recorded."
        ),
    )


class StopTool_output_schema(output_schema):
    request_received: bool = Field(
        default=True,
        description="The stop request was received; this does not confirm that the run ended or science passed."
    )
    message: str = Field(
        default="Stop request received; awaiting the runtime completion gate.",
        description="Stop request receipt"
    )


class StopTool(Tool):
    tool_id: str = 't-stop'
    tool_name: str = 'stop'
    tool_description: str = (
        "Request completion of the current run; remaining tools in this round finish before the runtime audits the request. "
        "Use for: the task is done, the goal is met, or you confirm you cannot proceed and need to wrap up. "
        "Also used to suspend while waiting on background work: for jobs submitted by this sub-agent "
        "through submit_compute_job, terminal notifications provide the wake-up; for other background "
        "work, schedule a wake-up first, then stop. "
        "The completion gate records wait_background for an accepted background wait. This run ends, and a later "
        "wake-up starts another run in the same session. Pending work is not a final delivery, and DAG mode does not "
        "run a delivery audit for that background wait. "
        "Do not use for: questions that still need the user (use ask_user), or stopping early while later steps remain and no wake-up is scheduled. "
        "Note: for quiz/eval tasks, put the final concise answer in final_answer. "
        "In DAG mode the stop is audited after this call: the run may be kept working (gap feedback), suspended pending a "
        "Supervisor exit review (dag_guided partial), or accepted — the completion-gate feedback message tells you which."
        " DAG-mode Benchmark delivery requires mechanism_graph.json matching the declared species and steps. "
        "Energy/barrier declarations must cite the unchanged bound native logs; partial approval covers the exact file bytes."
    )
    input_schema: Any = StopTool_input_schema
    output_schema: Any = StopTool_output_schema

    async def tool_call(
        self,
        user_input: StopTool_input_schema,
        session: Session
    ) -> StopTool_output_schema:
        """不做任何业务操作，仅返回请求回执。"""
        return StopTool_output_schema(
            request_received=True,
            message="Stop request received; awaiting the runtime completion gate.",
        )
