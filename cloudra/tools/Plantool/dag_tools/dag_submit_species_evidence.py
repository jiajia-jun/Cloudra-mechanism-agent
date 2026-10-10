"""dag_submit_species_evidence: submit QM calculation files as evidence for a species/intermediate."""

from __future__ import annotations

import asyncio
import os
import uuid
from pathlib import Path
from typing import Any

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
    opt_file: str | list[str] = Field(
        description="Optimization output path, or a list containing every component when submitting component evidence."
    )
    freq_file: str | list[str] | None = Field(
        default=None,
        description="Frequency output path, or a list paired in the same order with opt_file; omit for combined opt/frequency logs.",
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

        # One submission is one complete evidence set. Do not borrow files
        # from previous attempts to fill missing components or frequencies.
        opt_files = [user_input.opt_file] if isinstance(user_input.opt_file, str) else user_input.opt_file
        freq_files = ([user_input.freq_file] if isinstance(user_input.freq_file, str)
                      else user_input.freq_file)
        if not opt_files or any(not path.strip() for path in opt_files):
            return fail("dag_submit_species_evidence", "opt_file must contain non-empty paths", accepted=False)
        if freq_files is not None and len(freq_files) != len(opt_files):
            return fail("dag_submit_species_evidence", "freq_file must pair one-to-one with opt_file", accepted=False)
        refs, validations = [], []
        for index, opt_path in enumerate(opt_files):
            try:
                opt_snap = await asyncio.to_thread(snapshot_evidence_file, opt_path,
                    workspace_root=workspace_root, conversation_id=ctx.conversation_id)
                freq_snap = None
                if freq_files is not None:
                    freq_snap = await asyncio.to_thread(snapshot_evidence_file, freq_files[index],
                        workspace_root=workspace_root, conversation_id=ctx.conversation_id)
                    from cloudra.dag.file_science import validate_frequency_geometry
                    await asyncio.to_thread(validate_frequency_geometry, opt_snap, freq_snap)
            except Exception as exc:
                return fail("dag_submit_species_evidence", f"Failed to ingest species evidence: {exc}", accepted=False)
            frequency = freq_snap if freq_snap is not None else opt_snap
            val = validate_species_minimum(frequency.frequencies,
                imaginary_freqs=frequency.imaginary_frequencies)
            if not val.frequency_count_valid and (ctx.mode is OrchestrationMode.DAG_RECORD or val.frequency_data_present):
                return fail("dag_submit_species_evidence", f"Stationary point failed validation: {val.message}", accepted=False)
            validations.append(val.model_dump())
            for snap in [opt_snap, *([freq_snap] if freq_snap is not None else [])]:
                ref = await asyncio.to_thread(ctx.store.register_evidence, session.id,
                    Path(snap.original_path).name, snap.model_dump(mode="json"), source_type="file")
                refs.append(ref)
        validation = validations[0] if len(validations) == 1 else {"components": validations}

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
                    "validation": validation,
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

        from cloudra.dag.file_science import file_scientific_checks
        graph = await asyncio.to_thread(ctx.store.load_snapshot)
        scientific_checks = await asyncio.to_thread(file_scientific_checks, ctx.store, graph.delivery, species.node_id, evidence_refs=refs)

        review = ActiveReview(
            review_id=f"rev_{uuid.uuid4().hex}",
            kind="species",
            target_name=user_input.species_name,
            target_id=species.node_id,
            requester=session.id,
            details={
                "scientific_checks": scientific_checks,
                "element_type": "species",
                "species_name": user_input.species_name,
                "target_identity": review_target_identity(snapshot.delivery, "species", species.node_id),
                "opt_file": user_input.opt_file,
                "freq_file": user_input.freq_file,
                "validation": validation,
                "description": user_input.description,
            },
            supporting_refs=refs,
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
                "scientific_checks": scientific_checks,
                "validation": validation,
                "review_id": review.review_id,
                "enqueued": enqueued,
                "message": f"Species '{user_input.species_name}' evidence submitted for Supervisor review.",
            },
        )
