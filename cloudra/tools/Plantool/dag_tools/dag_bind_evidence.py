"""dag_bind_evidence: bind a finished tool call to a declared delivery stage."""

from __future__ import annotations

from typing import Any, Optional

from pydantic import Field, model_validator

from cloudra.base.session_class import Session
from cloudra.base.tools_class import input_schema
from cloudra.core.agent import Agent
from cloudra.dag.controller import DagController
from cloudra.dag.models import OrchestrationMode
from cloudra.tools.Plantool.dag_tools._common import DagToolBase, DagToolOutput, fail

_STAGE_HELP = (
    "The declared stage this evidence supports — one of geometry, frequency, "
    "single_point, ts_guess, ts_opt, short_irc, endpoint_a, endpoint_b, "
    "direction, identity, thermochemistry. In legacy/contract_version=1 "
    "projects, binds remain sequential; after a v2 contract is accepted, "
    "evidence may bind out of order and the dependency check is done by the "
    "scientific requirements layer. ts_guess is advisory and never satisfies "
    "ts_opt/frequency."
)


class DagBindEvidenceAttachment(input_schema):
    """One deterministic stage attachment inside a batch bind."""

    tool_call_id: str = Field(
        description="The tool_call_id of the finished call whose result becomes evidence.",
    )
    bind_target: str = Field(description="Delivery node or edge id to mount onto.")
    stage_kind: str = Field(description=_STAGE_HELP)


class DagBindEvidenceInput(input_schema):
    tool_call_id: Optional[str] = Field(
        default=None,
        description=(
            "Legacy single-bind form: tool_call_id of the finished call. "
            "Prefer `attachments` for batch binds."
        ),
    )
    bind_target: Optional[str] = Field(
        default=None,
        description="Legacy single-bind form: delivery node or edge id.",
    )
    stage_kind: Optional[str] = Field(
        default=None,
        description="Legacy single-bind form: stage to bind.",
    )
    attachments: Optional[list[DagBindEvidenceAttachment]] = Field(
        default=None,
        description=(
            "Batch attachments, each with tool_call_id/bind_target/stage_kind. "
            "Either this field or the legacy trio must be provided, not both."
        ),
    )
    expected_revision: Optional[int] = Field(
        default=None,
        ge=0,
        description=(
            "Optional delivery revision expected by the caller. If provided and "
            "the delivery graph has moved, the batch is rejected with "
            "revision_conflict instead of being retried on a newer revision."
        ),
    )

    @model_validator(mode="after")
    def _validate_bind_mode(self):
        legacy_provided = bool(self.tool_call_id or self.bind_target or self.stage_kind)
        has_attachments = bool(self.attachments)
        if legacy_provided and has_attachments:
            raise ValueError(
                "provide either the legacy single-bind fields "
                "(tool_call_id/bind_target/stage_kind) or `attachments`, not both"
            )
        if not legacy_provided and not has_attachments:
            raise ValueError(
                "dag_bind_evidence requires a single bind or at least one attachment"
            )
        if legacy_provided and not (
            self.tool_call_id and self.bind_target and self.stage_kind
        ):
            raise ValueError(
                "legacy single-bind form requires tool_call_id, bind_target, and stage_kind together"
            )
        return self


class DagBindEvidence(DagToolBase):
    tool_id: str = "t-dag-bind"
    tool_name: str = "dag_bind_evidence"
    tool_description: str = (
        "Bind finished tool calls to declared stages of delivery elements. "
        "In dag_record the Coordinator binds directly (single or batch); in "
        "dag_guided this submits the call(s) into the review inbox for the "
        "Supervisor to adjudicate. "
        "Use for: attaching a successful compute/parse result to a stage of an "
        "element's stage contract. "
        "Do not use for: letting a ts_guess result satisfy optimization/frequency "
        "stages, binding a submit_compute_job call (submit is never evidence — "
        "bind the finished job's parser output), or setting evidence levels directly."
    )
    input_schema: Any = DagBindEvidenceInput
    output_schema: Any = DagToolOutput
    subagent: Agent = None

    @staticmethod
    def _legacy_attachments(user_input: DagBindEvidenceInput) -> list[dict[str, str]]:
        if user_input.attachments:
            return [
                {
                    "tool_call_id": item.tool_call_id,
                    "bind_target": item.bind_target,
                    "stage_kind": item.stage_kind,
                }
                for item in user_input.attachments
            ]
        return [
            {
                "tool_call_id": user_input.tool_call_id,
                "bind_target": user_input.bind_target,
                "stage_kind": user_input.stage_kind,
            }
        ]

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
        attachments = self._legacy_attachments(user_input)
        if mode is OrchestrationMode.DAG_GUIDED:
            # 证据通交通道：dag_guided 下不直接绑定，而是把调用的产物提交进
            # review 收件箱，等 Supervisor 复核后绑定（绕过 dag_review 白名单）。
            results = []
            for item in attachments:
                try:
                    submitted = await controller.submit_evidence_for_review(
                        item["tool_call_id"],
                        item["bind_target"],
                        item["stage_kind"],
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
                results.append(submitted)
            return DagToolOutput(
                is_success=True,
                action="dag_bind_evidence",
                accepted=True,
                result={"enqueued": True, "attachments": results},
            )
        if self._actor_id() != "a-0":
            return fail(
                "dag_bind_evidence",
                "only the Coordinator binds evidence to stages; report your "
                "tool_call_id in your result instead",
                accepted=False,
            )
        try:
            if len(attachments) == 1:
                bound = await controller.bind_stage_for_call(
                    attachments[0]["tool_call_id"],
                    attachments[0]["bind_target"],
                    attachments[0]["stage_kind"],
                    expected_revision=user_input.expected_revision,
                )
                results = [bound]
            else:
                bound = await controller.bind_stage_attachments(
                    attachments,
                    expected_revision=user_input.expected_revision,
                )
                results = [bound]
        except Exception as exc:
            # 证据缺失/计算未成功/目标不存在等确定性拒绝，原文回报给模型自纠
            return fail("dag_bind_evidence", str(exc), accepted=False)
        if not results[-1]["accepted"]:
            return DagToolOutput(
                is_success=False,
                action="dag_bind_evidence",
                accepted=False,
                rejection_code=results[-1]["rejection_code"],
                error=results[-1]["rejection_reason"] or "",
                result=results[0],
            )
        return DagToolOutput(
            is_success=True,
            action="dag_bind_evidence",
            accepted=True,
            result={"attachments": results},
        )


def get_class():
    return DagBindEvidence
