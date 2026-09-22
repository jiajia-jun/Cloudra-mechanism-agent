"""dag_submit_step_evidence: submit QM calculation files as evidence for an elementary step."""

from __future__ import annotations

import asyncio
import os
import uuid
from pathlib import Path
from typing import Any, Optional

from pydantic import Field

from cloudra.base.session_class import Session
from cloudra.base.tool_actor import ToolActorContext
from cloudra.base.tools_class import input_schema
from cloudra.dag.evidence_ingest import snapshot_evidence_file, validate_ts_mode
from cloudra.dag.models import (
    AttachRef,
    GraphActor,
    GraphOperation,
    OrchestrationMode,
)
from cloudra.dag.review_context import ActiveReview, ReviewContextManager, review_target_identity
from cloudra.tools.Plantool.dag_tools._common import (
    DagToolBase,
    DagToolOutput,
    apply_mutation,
    fail,
)


class DagSubmitStepEvidenceInput(input_schema):
    step_name: str = Field(
        description="Name of the elementary step in the delivery graph (e.g. 'step1')."
    )
    ts_file: str = Field(
        description="Path to the transition state frequency/optimization output file."
    )
    irc_file: Optional[str] = Field(
        default=None,
        description="Optional path to combined IRC calculation output file.",
    )
    irc_forward_file: Optional[str] = Field(
        default=None,
        description="Optional path to forward IRC calculation output file.",
    )
    irc_reverse_file: Optional[str] = Field(
        default=None,
        description="Optional path to reverse IRC calculation output file.",
    )
    reaction_coordinate_description: str = Field(
        default="",
        description="Description of the reaction coordinate (e.g. bonds formed/cleaved along the mode).",
    )


class DagSubmitStepEvidence(DagToolBase):
    tool_id: str = "t-dag-submit-step-evidence"
    tool_name: str = "dag_submit_step_evidence"
    tool_description: str = (
        "Submit calculation output files as evidence for an elementary step in the delivery graph. "
        "Automatically validates that the TS calculation contains exactly one imaginary frequency. "
        "In dag_record mode, attach validated evidence snapshots. "
        "In dag_guided mode, submits the evidence to the Supervisor for review."
    )
    input_schema: Any = DagSubmitStepEvidenceInput
    output_schema: Any = DagToolOutput
    subagent: ToolActorContext | None = None

    async def tool_call(
        self, user_input: DagSubmitStepEvidenceInput, session: Session
    ) -> DagToolOutput:
        mode = self._mode()
        if mode is OrchestrationMode.STANDARD:
            return self._standard_disabled()

        ctx = await self._prepare(session)
        workspace_root = getattr(self.subagent, "working_directory", None) or os.getcwd()

        # 1. Check if step exists in delivery graph
        snapshot = await asyncio.to_thread(ctx.store.load_snapshot)
        matching_edges = [
            e
            for e in snapshot.delivery.edges
            if getattr(e, "name", "") == user_input.step_name
            or getattr(e, "label", "") == user_input.step_name
            or e.edge_id == user_input.step_name
        ]
        if not matching_edges:
            return fail(
                "dag_submit_step_evidence",
                f"Step '{user_input.step_name}' does not exist in the delivery graph",
                accepted=False,
            )
        step = matching_edges[0]

        # 2. Snapshot TS file and validate vibration mode
        # snapshot_evidence_file 全量读文件 + cclib 解析（同步重活），卸载出事件循环。
        try:
            ts_snap = await asyncio.to_thread(
                snapshot_evidence_file,
                user_input.ts_file,
                workspace_root=workspace_root,
                conversation_id=ctx.conversation_id,
            )
        except Exception as exc:
            return fail("dag_submit_step_evidence", f"Failed to ingest TS file: {exc}", accepted=False)

        ts_val = validate_ts_mode(
            ts_snap.frequencies,
            ts_snap.normal_modes,
            description=user_input.reaction_coordinate_description,
            imaginary_freqs=ts_snap.imaginary_frequencies,
        )
        if ctx.mode is OrchestrationMode.DAG_RECORD and not ts_val.is_valid:
            kind = "was not verified" if not ts_val.verified else "failed validation"
            return fail(
                "dag_submit_step_evidence",
                f"TS {kind}: {ts_val.message}",
                accepted=False,
            )

        # 3. Snapshot optional IRC files
        irc_snaps: dict[str, Any] = {}
        irc_refs = []
        for key, path in [
            ("irc_file", user_input.irc_file),
            ("irc_forward_file", user_input.irc_forward_file),
            ("irc_reverse_file", user_input.irc_reverse_file),
        ]:
            if path:
                try:
                    snap = await asyncio.to_thread(
                        snapshot_evidence_file,
                        path,
                        workspace_root=workspace_root,
                        conversation_id=ctx.conversation_id,
                    )
                    irc_snaps[key] = snap.model_dump(mode="json")
                    irc_refs.append(
                        await asyncio.to_thread(
                            ctx.store.register_evidence,
                            session.id,
                            Path(path).name,
                            snap.model_dump(mode="json"),
                            source_type="file",
                        )
                    )
                except Exception as exc:
                    return fail("dag_submit_step_evidence", f"Failed to ingest IRC file '{path}': {exc}", accepted=False)

        # 4. Register evidence in store
        ref = await asyncio.to_thread(
            ctx.store.register_evidence,
            session.id,
            Path(user_input.ts_file).name,
            ts_snap.model_dump(mode="json"),
            source_type="file",
        )

        operations: list[GraphOperation] = [
            AttachRef(
                op="attach_ref",
                graph="delivery",
                target_type="edge",
                target_id=step.edge_id,
                ref=evidence_ref,
            )
            for evidence_ref in [ref, *irc_refs]
        ]

        # 5. Adjudicate according to orchestration mode
        if ctx.mode is OrchestrationMode.DAG_RECORD:
            # dag_record 只挂快照；evidence_level 由阶段绑定派生，不在这里写。
            mutation = await asyncio.to_thread(
                apply_mutation,
                ctx.store,
                ctx.engine,
                session_id=session.id,
                actor=GraphActor.HARNESS,
                actor_id="harness",
                operations=operations,
                rationale=f"Auto-accept step evidence for {user_input.step_name}",
            )
            if not mutation.accepted:
                return fail(
                    "dag_submit_step_evidence",
                    mutation.rejection_reason or "Failed to record step evidence mutation",
                    accepted=False,
                )
            return DagToolOutput(
                is_success=True,
                action="dag_submit_step_evidence",
                accepted=True,
                result={
                    "step_name": user_input.step_name,
                    "status": "attached",
                    "ts_validation": ts_val.model_dump(),
                    "message": (
                        f"Step '{user_input.step_name}' evidence attached; "
                        "bind stages with dag_bind_evidence / dag_review_call."
                    ),
                },
            )

        # DAG_GUIDED mode: submit for supervisor review
        mutation = await asyncio.to_thread(
            apply_mutation,
            ctx.store,
            ctx.engine,
            session_id=session.id,
            actor=GraphActor.HARNESS,
            actor_id="harness",
            operations=operations,
            rationale=f"Attach step evidence for {user_input.step_name}",
        )
        if not mutation.accepted:
            return fail(
                "dag_submit_step_evidence",
                mutation.rejection_reason or "Failed to attach step evidence",
                accepted=False,
            )

        review = ActiveReview(
            review_id=f"rev_{uuid.uuid4().hex}",
            kind="step",
            target_name=user_input.step_name,
            target_id=step.edge_id,
            requester=getattr(self.subagent, "agent_id", "coordinator") or "coordinator",
            details={
                "element_type": "step",
                "step_name": user_input.step_name,
                "target_identity": review_target_identity(snapshot.delivery, "step", step.edge_id),
                "ts_file": user_input.ts_file,
                "ts_validation": ts_val.model_dump(),
                "irc_files": irc_snaps,
                "reaction_coordinate_description": user_input.reaction_coordinate_description,
            },
            supporting_refs=[ref, *irc_refs],
            basis_fingerprint=ts_snap.sha256,
        )
        enqueued = await asyncio.to_thread(
            ReviewContextManager.set_active_review,
            ctx.conversation_id, review, ctx.db,
        )

        if not enqueued:
            return fail("dag_submit_step_evidence", "Failed to persist evidence review request", accepted=False)

        # 督导唤醒不在工具内做：queued review 落库后由 DAG policy 完成钩子
        # （_trigger_supervisor_after_tool）按这里的回执统一 notify_supervisor。
        return DagToolOutput(
            is_success=True,
            action="dag_submit_step_evidence",
            accepted=True,
            result={
                "step_name": user_input.step_name,
                "status": "submitted_for_review",
                "ts_validation": ts_val.model_dump(),
                "review_id": review.review_id,
                "enqueued": enqueued,
                "message": f"Step '{user_input.step_name}' evidence submitted for Supervisor review.",
            },
        )


def get_class():
    return DagSubmitStepEvidence
