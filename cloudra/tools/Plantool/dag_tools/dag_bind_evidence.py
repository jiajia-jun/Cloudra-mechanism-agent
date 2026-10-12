"""dag_bind_evidence: bind a finished tool call to a declared delivery stage."""

from __future__ import annotations

from typing import Any

from pydantic import Field

from cloudra.base.session_class import Session
from cloudra.base.tool_actor import ToolActorContext
from cloudra.base.tools_class import input_schema
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
    claim: str = Field(
        default="",
        description=(
            "What this evidence is supposed to prove for that stage "
            "(REQUIRED in dag_guided: submissions are explicit claims the "
            "Supervisor adjudicates around). One claim per (evidence, target, "
            "stage) — submit several attachments when one log supports several "
            "stages."
        ),
    )
    rationale: str = Field(
        default="",
        description="Why this particular call was selected as evidence (optional).",
    )


class DagBindEvidenceInput(input_schema):
    attachments: list[DagBindEvidenceAttachment] = Field(
        min_length=1,
        description=(
            "Evidence attachments, each with tool_call_id/bind_target/stage_kind and its own claim/rationale. "
            "Use a one-element list for a single bind."
        ),
    )

class DagBindEvidence(DagToolBase):
    def is_manage(self) -> bool:
        return False

    def is_write(self) -> bool:
        return True

    tool_id: str = "t-dag-bind"
    tool_name: str = "dag_bind_evidence"
    tool_description: str = (
        "Bind finished tool calls to declared stages of delivery elements. "
        "In dag_record the Coordinator binds the attachment list directly. In "
        "dag_guided finished calls are submitted for Supervisor review: "
        "finished tool calls are NEVER auto-submitted — first select the calls "
        "whose result actually supports a stage, then submit each with a claim "
        "(what it proves) and an optional rationale; unsubmitted exploration "
        "results are not read as review work. Identical re-submissions of a "
        "still-pending claim are idempotent (the existing review id comes "
        "back); a batch is validated as a whole and committed atomically. "
        "Use for: attaching a compute/parse result to a stage of an element's "
        "stage contract. "
        "Do not use for: letting a ts_guess result satisfy optimization/frequency "
        "stages, binding a submit_compute_job call (submit is never evidence — "
        "bind the finished job's parser output), or setting evidence levels directly."
    )
    input_schema: Any = DagBindEvidenceInput
    output_schema: Any = DagToolOutput
    subagent: ToolActorContext | None = None

    async def tool_call(
        self, user_input: DagBindEvidenceInput, session: Session
    ) -> DagToolOutput:
        mode = self._mode()
        if mode is OrchestrationMode.STANDARD:
            return self._standard_disabled()
        ctx = await self._prepare(session)
        controller = DagController(
            ctx.db, session.id, ctx.mode, conversation_id=ctx.conversation_id,
            working_directory=getattr(self.subagent, "working_directory", None),
        )
        attachments = [item.model_dump(mode="json") for item in user_input.attachments]
        if mode is OrchestrationMode.DAG_GUIDED:
            # §5 显式送审口：dag_guided 下不直接绑定——把筛选后的调用产物连同
            # 提交者主张（claim/rationale）持久化为 pending CallReview，等
            # Supervisor 围绕 claim 与快照裁决。批量先全部校验再原子提交；
            # 相同 pending 声明幂等返回既有 review_id（enqueued=False），
            # 整条调用仍是成功。
            try:
                submitted = await controller.submit_evidence_for_review(attachments)
            except Exception as exc:
                return fail("dag_bind_evidence", str(exc), accepted=False)
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
            if len(attachments) == 1:
                bound = await controller.bind_stage_for_call(
                    attachments[0]["tool_call_id"],
                    attachments[0]["bind_target"],
                    attachments[0]["stage_kind"],
                )
                results = [bound]
            else:
                bound = await controller.bind_stage_attachments(
                    attachments,
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
