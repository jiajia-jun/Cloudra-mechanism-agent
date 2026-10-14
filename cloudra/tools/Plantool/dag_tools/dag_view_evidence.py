"""dag_view_evidence: read the full source + parsed result of one CallReview.

The review inbox projection only carries provenance sidecars (tool name,
success, caller, source path, result kind); the full canonical evidence lives
in the evidence store.  This tool exposes it so the Supervisor can verify
whether "all-null" means a broken parser or genuinely missing source, without
waiting for a Coordinator appeal.
"""

from __future__ import annotations

import asyncio
from typing import Any

from pydantic import Field

from cloudra.base.session_class import Session
from cloudra.base.tool_actor import ToolActorContext
from cloudra.base.tools_class import input_schema
from cloudra.dag.models import GraphRef, OrchestrationMode
from cloudra.dag.store import InvalidGraphReference
from cloudra.tools.Plantool.dag_tools._common import DagToolBase, DagToolOutput, fail


class DagViewEvidenceInput(input_schema):
    review_id: str = Field(
        default="",
        description=(
            "The call, file or final-delivery review id (from the review inbox) to read. "
            "Provide either this or evidence_id."
        ),
    )
    evidence_id: str = Field(
        default="",
        description=(
            "An evidence id (ev_...) to read directly, e.g. one already bound "
            "to a delivery stage. Provide either this or review_id."
        ),
    )


class DagViewEvidence(DagToolBase):
    def is_manage(self) -> bool:
        return False

    tool_id: str = "t-dag-view-evidence"
    tool_name: str = "dag_view_evidence"
    tool_description: str = (
        "Read a final-delivery proposal and verdict, file-review scientific checks and repair actions, or the full source arguments + parsed result behind one CallReview "
        "(or evidence id). Use for: checking the source log path, compute job, "
        "and the raw parser output when the inbox summary is too terse; "
        "distinguishing a broken parser from a genuinely missing source file. "
        "Do not use for: binding stages (use dag_review_call / dag_bind_evidence)."
    )
    input_schema: Any = DagViewEvidenceInput
    output_schema: Any = DagToolOutput
    subagent: ToolActorContext | None = None

    async def tool_call(self, user_input: DagViewEvidenceInput, session: Session) -> DagToolOutput:
        if self._mode() is OrchestrationMode.STANDARD:
            return self._standard_disabled()
        ctx = await self._prepare(session)
        store = ctx.store

        evidence_id = user_input.evidence_id.strip()
        if user_input.review_id.strip():
            review = await asyncio.to_thread(
                store.get_call_review, user_input.review_id.strip()
            )
            if review is None:
                request = await asyncio.to_thread(store.get_review_request, user_input.review_id.strip())
                if request is None or request.kind not in {"evidence", "exception", "exit"}:
                    return fail("dag_view_evidence", f"evidence review {user_input.review_id!r} does not exist")
                decision = await asyncio.to_thread(store.get_review_decision_for_request, request.request_id)
                result = {"review_id": request.request_id, "state": request.state,
                          "kind": request.kind, "question": request.question, "target_ids": request.target_ids,
                          "proposal": request.proposal,
                          "supporting_refs": [ref.model_dump(mode="json") for ref in request.supporting_refs],
                          "counterevidence_refs": [ref.model_dump(mode="json") for ref in request.counterevidence_refs],
                          "decision": decision.model_dump(mode="json") if decision is not None else None}
                if request.proposal.get("element_type") in ("step", "species") and len(request.target_ids) == 1:
                    from cloudra.dag.file_science import file_scientific_checks
                    snapshot = await asyncio.to_thread(store.load_snapshot)
                    try:
                        result["scientific_checks"] = await asyncio.to_thread(
                            file_scientific_checks, store, snapshot.delivery, request.target_ids[0], irc_files=request.proposal.get("irc_files"), endpoint_refs=request.proposal.get("endpoint_refs"), evidence_refs=request.supporting_refs,
                            workspace_root=getattr(self.subagent, "working_directory", None))
                    except InvalidGraphReference as exc:
                        result["message"] = (
                            f"{exc} Showing the original review and decision as history; "
                            "they do not validate or grant evidence credit to a replacement target."
                        )
                return DagToolOutput(is_success=True, action="dag_view_evidence", result=result)
            ref = await asyncio.to_thread(
                store.resolve_evidence_for_call, review.tool_call_id
            )
            if ref is None:
                return fail(
                    "dag_view_evidence",
                    f"review {review.review_id} has no registered evidence "
                    f"for call {review.tool_call_id!r}",
                )
            evidence_id = ref.ref_id
            review_meta = {
                "review_id": review.review_id,
                "tool_call_id": review.tool_call_id,
                "is_success": review.is_success,
                "caller_role_id": review.caller_role_id,
                "caller_legacy_id": review.caller_legacy_id,
                "source_path": review.source_path,
                "result_kind": review.result_kind,
                "compute_job_id": review.compute_job_id,
                "state": review.state,
                # §5：送审主张与快照身份——裁决围绕 claim，内容以提交时的
                # 不可变快照（evidence_id 指向的 payload）为准。
                "claim": review.claim,
                "rationale": review.rationale,
                "suggested_target_id": review.suggested_target_id,
                "suggested_stage": review.suggested_stage,
                "evidence_id": review.evidence_id,
            }
        else:
            if not evidence_id:
                return fail(
                    "dag_view_evidence",
                    "provide either review_id or evidence_id",
                )
            review_meta = {}

        try:
            source_name, payload = await asyncio.to_thread(
                store.resolve_evidence_with_source,
                GraphRef(ref_type="tool_result", ref_id=evidence_id, content_hash=None),
            )
        except InvalidGraphReference as exc:
            return fail("dag_view_evidence", str(exc))

        result: dict[str, Any] = {
            **review_meta,
            "evidence_id": evidence_id,
            "source_name": source_name,
            "arguments": (payload or {}).get("arguments", {}) if isinstance(payload, dict) else {},
            "result": (payload or {}).get("result", {}) if isinstance(payload, dict) else payload,
        }
        return DagToolOutput(is_success=True, action="dag_view_evidence", result=result)
