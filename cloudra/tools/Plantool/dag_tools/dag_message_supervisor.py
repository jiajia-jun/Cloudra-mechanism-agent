"""dag_message_supervisor: Coordinator-only note to Supervisor (no graph change)."""

from __future__ import annotations

from typing import Any

from pydantic import Field

from cloudra.base.session_class import Session
from cloudra.base.tools_class import input_schema
from cloudra.core.agent import Agent
from cloudra.dag.models import OrchestrationMode
from cloudra.tools.Plantool.dag_tools._common import DagToolBase, DagToolOutput, fail


class DagMessageSupervisorInput(input_schema):
    message: str = Field(
        description=(
            "Plain-text note to the Supervisor (appeal a review verdict, explain "
            "a contract choice, report a blocker, etc.)."
        ),
    )


class DagMessageSupervisor(DagToolBase):
    tool_id: str = "t-dag-message"
    tool_name: str = "dag_message_supervisor"
    tool_description: str = (
        "Send a plain-text note to wake or inform the Supervisor without changing the graph "
        "(Coordinator only in dag_record or dag_guided). "
        "Use for: appealing a review verdict, explaining stage-contract choices, or reporting blockers. "
        "Do not use for: sub-agents — report results with tool_call_ids or use AgentHub; "
        "mutating the delivery graph directly. "
        "Key discipline: this nudges Supervisor review — it does not edit the DAG."
    )
    input_schema: Any = DagMessageSupervisorInput
    output_schema: Any = DagToolOutput
    subagent: Agent = None

    async def tool_call(
        self, user_input: DagMessageSupervisorInput, session: Session
    ) -> DagToolOutput:
        if self._mode() is OrchestrationMode.STANDARD:
            return self._standard_disabled()
        caller_type = getattr(self.subagent, "type", "")
        caller_id = getattr(self.subagent, "id", "")
        if caller_type == "supervisor":
            return fail(
                "dag_message_supervisor",
                "message_supervisor is for the Coordinator; you are the Supervisor.",
            )
        if caller_type != "coordinator" and caller_id != "a-0":
            return fail(
                "dag_message_supervisor",
                "message_supervisor is Coordinator-only; "
                "report results with concrete tool_call_ids or via AgentHub.",
            )
        msg = (user_input.message or "").strip()
        if not msg:
            return fail(
                "dag_message_supervisor",
                "message_supervisor requires a non-empty message.",
            )
        # 真正唤醒由 DagController.on_tool_finished → maybe_supervise 完成
        return DagToolOutput(
            is_success=True,
            action="dag_message_supervisor",
            accepted=True,
            result={"delivered": True, "message": msg[:2000]},
        )


def get_class():
    return DagMessageSupervisor
