"""dag_submit_species_evidence: submit QM calculation files as evidence for a species/intermediate."""

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
from cloudra.dag.evidence_ingest import snapshot_evidence_file, validate_species_minimum
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


class DagSubmitSpeciesEvidenceInput(input_schema):
    species_name: str = Field(
        description="Name of the species/intermediate in the delivery graph (e.g. 'R' or 'Int1')."
    )
    opt_file: str = Field(
        description="Path to the geometry optimization output file."
    )
    freq_file: Optional[str] = Field(
        default=None,
        description="Optional path to the frequency analysis output file (to confirm 0 imaginary frequencies).",
    )
    description: str = Field(
        default="",
        description="Description of the optimized geometry or conformational details.",
    )


class DagSubmitSpeciesEvidence(DagToolBase):
    def is_manage(self) -> bool:
        return False

    def is_write(self) -> bool:
        return True

    tool_id: str = "t-dag-submit-species-evidence"
    tool_name: str = "dag_submit_species_evidence"
    tool_description: str = (
        "Submit calculation output files as evidence for a species in the delivery graph. "
        "Automatically validates that the stationary point has 0 imaginary frequencies. "
        "In dag_record mode, attach validated evidence snapshots. "
        "In dag_guided mode, submits the evidence to the Supervisor for review."
    )
    input_schema: Any = DagSubmitSpeciesEvidenceInput
    output_schema: Any = DagToolOutput
    subagent: ToolActorContext | None = None

    async def tool_call(
        self, user_input: DagSubmitSpeciesEvidenceInput, session: Session
    ) -> DagToolOutput:
        mode = self._mode()
        if mode is OrchestrationMode.STANDARD:
            return self._standard_disabled()

        ctx = await self._prepare(session)
        workspace_root = getattr(self.subagent, "working_directory", None) or os.getcwd()

        # 1. Check if species exists in delivery graph
        snapshot = await asyncio.to_thread(ctx.store.load_snapshot)
        matching_nodes = [
            n
            for n in snapshot.delivery.nodes
            if getattr(n, "name", "") == user_input.species_name
            or getattr(n, "label", "") == user_input.species_name
            or n.node_id == user_input.species_name
        ]
        if not matching_nodes:
            return fail(
                "dag_submit_species_evidence",
                f"Species '{user_input.species_name}' does not exist in the delivery graph",
                accepted=False,
            )
        species = matching_nodes[0]

        # 2. Snapshot optimization and optional frequency files
        # snapshot_evidence_file 全量读文件 + cclib 解析（同步重活），卸载出事件循环。
        try:
            opt_snap = await asyncio.to_thread(
                snapshot_evidence_file,
                user_input.opt_file,
                workspace_root=workspace_root,
                conversation_id=ctx.conversation_id,
            )
        except Exception as exc:
            return fail("dag_submit_species_evidence", f"Failed to ingest opt file: {exc}", accepted=False)

        freq_snap = None
        if user_input.freq_file:
            try:
                freq_snap = await asyncio.to_thread(
                    snapshot_evidence_file,
                    user_input.freq_file,
                    workspace_root=workspace_root,
                    conversation_id=ctx.conversation_id,
                )
            except Exception as exc:
                return fail("dag_submit_species_evidence", f"Failed to ingest freq file: {exc}", accepted=False)

        # 3. Validate stationary minimum (0 imaginary frequencies)
        check_freqs = freq_snap.frequencies if freq_snap and freq_snap.frequencies is not None else opt_snap.frequencies
        check_imag = freq_snap.imaginary_frequencies if freq_snap and freq_snap.imaginary_frequencies is not None else opt_snap.imaginary_frequencies
        val = validate_species_minimum(check_freqs, imaginary_freqs=check_imag)
        # A known imaginary mode is a hard contradiction for an endpoint
        # minimum, including guided review. Missing frequency data may still
        # be sent to the Supervisor in guided mode as unverified evidence.
        if not val.is_valid and (ctx.mode is OrchestrationMode.DAG_RECORD or val.verified):
            kind = "was not verified" if not val.verified else "failed validation"
            return fail(
                "dag_submit_species_evidence",
                f"Stationary point {kind}: {val.message}",
                accepted=False,
            )

        # 4. Register evidence in store
        ref = await asyncio.to_thread(
            ctx.store.register_evidence,
            session.id,
            Path(user_input.opt_file).name,
            opt_snap.model_dump(mode="json"),
            source_type="file",
        )

        refs = [ref]
        if freq_snap is not None:
            refs.append(await asyncio.to_thread(
                ctx.store.register_evidence,
                session.id,
                Path(user_input.freq_file).name,
                freq_snap.model_dump(mode="json"),
                source_type="file",
            ))

        operations: list[GraphOperation] = [
            AttachRef(
                op="attach_ref",
                graph="delivery",
                target_type="node",
                target_id=species.node_id,
                ref=evidence_ref,
            )
            for evidence_ref in refs
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
                rationale=f"Auto-accept species evidence for {user_input.species_name}",
            )
            if not mutation.accepted:
                return fail(
                    "dag_submit_species_evidence",
                    mutation.rejection_reason or "Failed to record species evidence mutation",
                    accepted=False,
                )
            return DagToolOutput(
                is_success=True,
                action="dag_submit_species_evidence",
                accepted=True,
                result={
                    "species_name": user_input.species_name,
                    "status": "attached",
                    "validation": val.model_dump(),
                    "message": (
                        f"Species '{user_input.species_name}' evidence attached; "
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
            rationale=f"Attach species evidence for {user_input.species_name}",
        )
        if not mutation.accepted:
            return fail(
                "dag_submit_species_evidence",
                mutation.rejection_reason or "Failed to attach species evidence",
                accepted=False,
            )

        review = ActiveReview(
            review_id=f"rev_{uuid.uuid4().hex}",
            kind="species",
            target_name=user_input.species_name,
            target_id=species.node_id,
            requester=session.id,
            details={
                "element_type": "species",
                "species_name": user_input.species_name,
                "target_identity": review_target_identity(snapshot.delivery, "species", species.node_id),
                "opt_file": user_input.opt_file,
                "freq_file": user_input.freq_file,
                "validation": val.model_dump(),
                "description": user_input.description,
            },
            supporting_refs=refs,
            basis_fingerprint=opt_snap.sha256,
        )
        enqueued = await asyncio.to_thread(
            ReviewContextManager.set_active_review,
            ctx.conversation_id, review, ctx.db,
        )

        if not enqueued:
            return fail("dag_submit_species_evidence", "Failed to persist evidence review request", accepted=False)

        # 督导唤醒不在工具内做：queued review 落库后由 DAG policy 完成钩子
        # （_trigger_supervisor_after_tool）按这里的回执统一 notify_supervisor。
        return DagToolOutput(
            is_success=True,
            action="dag_submit_species_evidence",
            accepted=True,
            result={
                "species_name": user_input.species_name,
                "status": "submitted_for_review",
                "validation": val.model_dump(),
                "review_id": review.review_id,
                "enqueued": enqueued,
                "message": f"Species '{user_input.species_name}' evidence submitted for Supervisor review.",
            },
        )


def get_class():
    return DagSubmitSpeciesEvidence
