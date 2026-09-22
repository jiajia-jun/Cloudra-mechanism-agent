"""dag_accept_mechanism: supervisor-only draft adjudication (dag_guided)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from cloudra.base.session_class import Session
from cloudra.base.tool_actor import ToolActorContext
from cloudra.base.tools_class import input_schema
from cloudra.dag.controller import DagController
from cloudra.dag.models import GraphActor, OrchestrationMode
from cloudra.tools.Plantool.dag_tools._common import DagToolBase, DagToolOutput, fail


class DagAcceptMechanismInput(input_schema):
    verdict: Literal["accept", "reject"] = Field(
        description=(
            "accept commits the draft (operations + stage contracts) to the "
            "delivery graph; reject returns it to the Coordinator."
        ),
    )
    rationale: str = Field(
        default="",
        description="Mandatory for reject: what the Coordinator must fix.",
    )
    draft_id: str | None = Field(
        default=None,
        description="Draft to adjudicate; defaults to the latest open draft.",
    )


class DagAcceptMechanism(DagToolBase):
    tool_id: str = "t-dag-accept"
    tool_name: str = "dag_accept_mechanism"
    tool_description: str = (
        "Accept or reject the Coordinator's mechanism draft (Supervisor only "
        "in dag_guided; dag_record auto-accepts on proposal). "
        "Use for: committing a reviewed draft — accept unlocks compute; "
        "reject returns it with a mandatory reason. "
        "Do not use for: editing the draft in place (reject with guidance "
        "instead); stage binds (use dag_review_call). "
        "Key discipline: until you accept, the compute gate stays closed."
    )
    input_schema: Any = DagAcceptMechanismInput
    output_schema: Any = DagToolOutput
    subagent: ToolActorContext | None = None

    async def tool_call(
        self, user_input: DagAcceptMechanismInput, session: Session
    ) -> DagToolOutput:
        mode = self._mode()
        if mode is OrchestrationMode.STANDARD:
            return self._standard_disabled()
        if mode is OrchestrationMode.DAG_RECORD:
            return fail(
                "dag_accept_mechanism",
                "disabled in dag_record (the Supervisor is offline); proposals "
                "are auto-accepted by the harness there",
                accepted=False,
            )
        ctx = await self._prepare(session)
        if ctx.actor is not GraphActor.SUPERVISOR:
            return fail(
                "dag_accept_mechanism",
                "accept_mechanism is supervisor-only",
            )
        controller = DagController(
            ctx.db, session.id, ctx.mode, conversation_id=ctx.conversation_id
        )
        try:
            decided = await controller.accept_mechanism(
                verdict=user_input.verdict,
                rationale=user_input.rationale,
                draft_id=user_input.draft_id,
            )
        except Exception as exc:
            return fail("dag_accept_mechanism", str(exc), accepted=False)
        return DagToolOutput(
            is_success=True,
            action="dag_accept_mechanism",
            accepted=True,
            result=decided,
        )


def get_class():
    return DagAcceptMechanism
