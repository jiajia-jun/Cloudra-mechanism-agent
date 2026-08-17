"""dag_bind_evidence: bind a finished tool call to a declared delivery stage."""

from __future__ import annotations

from typing import Any

from pydantic import Field

from cloudra.base.session_class import Session
from cloudra.base.tools_class import input_schema
from cloudra.core.agent import Agent
from cloudra.dag.controller import DagController
from cloudra.dag.models import OrchestrationMode
from cloudra.tools.Plantool.dag_tools._common import DagToolBase, DagToolOutput, fail


class DagBindEvidenceInput(input_schema):
    tool_call_id: str = Field(
        description=(
            "The tool_call_id of the finished call whose result becomes evidence."
        ),
    )
    bind_target: str = Field(description="Delivery node or edge id to mount onto.")
    stage_kind: str = Field(
        description=(
            "The declared stage this evidence supports — one of geometry, "
            "frequency, single_point, ts_guess, ts_opt, short_irc, endpoint_a, "
            "endpoint_b, direction, identity, thermochemistry. Stages bind "
            "strictly in contract order: every previous required stage must be "
            "supported or skipped first. ts_guess is advisory and never "
            "satisfies ts_opt/frequency."
        ),
    )


class DagBindEvidence(DagToolBase):
    tool_id: str = "t-dag-bind"
    tool_name: str = "dag_bind_evidence"
    tool_description: str = (
        "Bind a finished tool call to a declared stage of a delivery element. "
        "In dag_record the Coordinator binds directly; in dag_guided this "
        "submits the call's result into the review inbox for the Supervisor to "
        "adjudicate (use it for evidence-bearing tools that do not auto-review, "
        "e.g. format_converter or internal_coordinates). "
        "Use for: attaching a successful compute/parse result to the next "
        "pending stage of an element's stage contract. "
        "Do not use for: skipping stages (binds are strictly sequential), "
        "letting a ts_guess result satisfy optimization/frequency stages, "
        "binding a submit_compute_job call (submit is never evidence — bind "
        "the finished job's parser output), or setting evidence levels directly."
    )
    input_schema: Any = DagBindEvidenceInput
    output_schema: Any = DagToolOutput
    subagent: Agent = None

    async def tool_call(
        self, user_input: DagBindEvidenceInput, session: Session
    ) -> DagToolOutput:
        mode = self._mode()
        if mode is OrchestrationMode.STANDARD:
            return self._standard_disabled()
        ctx = await self._prepare(session)
        controller = DagController(
            ctx.db, session.id, ctx.mode, conversation_id=ctx.conversation_id
        )
        if mode is OrchestrationMode.DAG_GUIDED:
            # 证据通交通道：dag_guided 下不直接绑定，而是把该调用的产物提交进
            # review 收件箱，等 Supervisor 复核后绑定（绕过 dag_review 白名单）。
            try:
                submitted = await controller.submit_evidence_for_review(
                    user_input.tool_call_id,
                    user_input.bind_target,
                    user_input.stage_kind,
                )
            except Exception as exc:
                return fail("dag_bind_evidence", str(exc), accepted=False)
            if not submitted["enqueued"]:
                return DagToolOutput(
                    is_success=False,
                    action="dag_bind_evidence",
                    accepted=False,
                    error=(
                        f"duplicate of already-queued review "
                        f"{submitted['duplicate_review_id']}; re-submit only if the "
                        "evidence changed, or wait for that review's verdict"
                    ),
                    result=submitted,
                )
            return DagToolOutput(
                is_success=True,
                action="dag_bind_evidence",
                accepted=True,
                result=submitted,
            )
        if self._actor_id() != "a-0":
            return fail(
                "dag_bind_evidence",
                "only the Coordinator binds evidence to stages; report your "
                "tool_call_id in your result instead",
                accepted=False,
            )
        try:
            bound = await controller.bind_stage_for_call(
                user_input.tool_call_id,
                user_input.bind_target,
                user_input.stage_kind,
            )
        except Exception as exc:
            # 证据缺失/计算未成功/目标不存在等确定性拒绝，原文回报给模型自纠
            return fail("dag_bind_evidence", str(exc), accepted=False)
        if not bound["accepted"]:
            return DagToolOutput(
                is_success=False,
                action="dag_bind_evidence",
                accepted=False,
                rejection_code=bound["rejection_code"],
                error=bound["rejection_reason"] or "",
                result=bound,
            )
        return DagToolOutput(
            is_success=True,
            action="dag_bind_evidence",
            accepted=True,
            result=bound,
        )


def get_class():
    return DagBindEvidence
