"""Mechanism draft lifecycle: proposal validation and supervisor verdicts."""

from __future__ import annotations

import asyncio
from typing import Any

from cloudra.dag.models import (
    ELEMENTARY_STEP_STAGE_KINDS,
    OCCURRENCE_STAGE_KINDS,
    AddEdge,
    AddNode,
    GraphActor,
    GraphKind,
    GraphOperation,
    MechanismDraft,
    MutationBatch,
    MutationResult,
    OrchestrationMode,
    StageContract,
    StageKind,
    StageState,
    StageStatus,
    UpdateEdge,
    UpdateNode,
    parse_graph_operation,
)


class DraftsMixin:
    """机理草稿（Phase 3：propose → accept → 解锁计算）；由 DagController 组合。"""

    @staticmethod
    def _validate_draft(
        operations_raw: list[dict[str, Any]],
        stage_contracts_raw: dict[str, list[str]],
        rationale: str,
    ) -> MechanismDraft:
        """校验草稿：delivery-only add/update ops；阶段全部 pending（阶段状态
        只由 harness 推进）；stage_contracts 的键必须解析到草稿自身 add 的
        元素，且阶段词表与元素种类匹配。"""
        operations: list[GraphOperation] = []
        for raw in operations_raw:
            try:
                op = parse_graph_operation(raw)
            except ValueError as exc:
                raise RuntimeError(f"invalid draft operation: {exc}") from exc
            if (
                not isinstance(op, (AddNode, AddEdge, UpdateNode, UpdateEdge))
                or op.graph is not GraphKind.DELIVERY
            ):
                raise RuntimeError(
                    "draft operations must be delivery-only "
                    "add_node/add_edge/update_node/update_edge"
                )
            if isinstance(op, (AddNode, AddEdge)):
                element = op.node if isinstance(op, AddNode) else op.edge
                if any(
                    stage.status is not StageStatus.PENDING or stage.ref is not None
                    for stage in getattr(element, "stages", [])
                ):
                    raise RuntimeError(
                        "draft stages must all be pending; stage states are "
                        "advanced by harness stage binds only"
                    )
            else:
                extras = set(op.changes) - {
                    "status", "priority", "label", "annotations",
                    "reason", "blocked_reason", "evidence_level",
                    "supersedes", "required",
                }
                if extras:
                    raise RuntimeError(
                        f"draft update changes exceed mutable fields: {sorted(extras)}"
                    )
                if op.changes.get("evidence_level") not in (
                    None, "proposed", "rejected", "inconclusive"
                ):
                    raise RuntimeError(
                        "a draft cannot promote evidence levels; evidence is "
                        "derived by the harness from stage binds"
                    )
            operations.append(op)
        added: dict[str, str] = {}
        for op in operations:
            if isinstance(op, AddNode):
                added[op.node.node_id] = "node"
            elif isinstance(op, AddEdge):
                added[op.edge.edge_id] = "edge"
        contracts: dict[str, StageContract] = {}
        for element_id, kinds in (stage_contracts_raw or {}).items():
            if element_id not in added:
                raise RuntimeError(
                    f"stage contract for {element_id!r} does not resolve to an "
                    "element added by this draft"
                )
            allowed = (
                OCCURRENCE_STAGE_KINDS
                if added[element_id] == "node"
                else ELEMENTARY_STEP_STAGE_KINDS
            )
            stages: list[StageState] = []
            for raw_kind in kinds:
                try:
                    kind = StageKind(raw_kind)
                except ValueError:
                    raise RuntimeError(
                        f"unknown stage kind {raw_kind!r}; "
                        f"allowed: {sorted(item.value for item in StageKind)}"
                    ) from None
                if kind not in allowed:
                    raise RuntimeError(
                        f"stage {kind.value!r} does not apply to "
                        f"{'occurrence nodes' if added[element_id] == 'node' else 'elementary-step edges'}; "
                        f"allowed here: {sorted(item.value for item in allowed)}"
                    )
                if kind in {stage.kind for stage in stages}:
                    raise RuntimeError(f"duplicate stage {kind.value!r} for {element_id!r}")
                stages.append(StageState(kind=kind))
            contracts[element_id] = StageContract(stages=stages)
        return MechanismDraft(
            operations=operations,
            stage_contracts=contracts,
            rationale=rationale,
        )

    @staticmethod
    def _draft_operations(draft: MechanismDraft) -> list[GraphOperation]:
        """把阶段契约并进 add ops（元素 stages 随 add 落图，全 pending）。"""
        operations: list[GraphOperation] = []
        for op in draft.operations:
            if isinstance(op, AddNode) and op.node.node_id in draft.stage_contracts:
                op = op.model_copy(update={
                    "node": op.node.model_copy(update={
                        "stages": list(draft.stage_contracts[op.node.node_id].stages)
                    })
                })
            elif isinstance(op, AddEdge) and op.edge.edge_id in draft.stage_contracts:
                op = op.model_copy(update={
                    "edge": op.edge.model_copy(update={
                        "stages": list(draft.stage_contracts[op.edge.edge_id].stages)
                    })
                })
            operations.append(op)
        return operations

    def _apply_draft(self, draft: MechanismDraft, actor_id: str) -> MutationResult:
        operations = self._draft_operations(draft)
        last: MutationResult | None = None
        for _attempt in range(8):
            last = self.engine.apply_batch(
                MutationBatch(
                    session_id=self.session_id,
                    actor=GraphActor.HARNESS,
                    actor_id=actor_id,
                    base_revisions=self.store.load_bundle().revisions,
                    operations=operations,
                    rationale=draft.rationale,
                )
            )
            if last.accepted or last.rejection_code != "stale_revision":
                return last
        assert last is not None
        return last

    async def propose_mechanism(
        self,
        *,
        operations: list[dict[str, Any]],
        stage_contracts: dict[str, list[str]],
        rationale: str,
        actor_id: str,
    ) -> dict[str, Any]:
        """Coordinator 的机理草稿（D1）：guided 落 open 草稿等 Supervisor
        接受；record 由 harness 立即自动接受（actor="harness:auto"）。"""
        if not self.enabled:
            raise RuntimeError(
                "propose_mechanism is disabled in standard orchestration mode"
            )
        if not rationale.strip():
            raise RuntimeError("a mechanism proposal requires a non-empty rationale")
        await self.initialize()
        draft = self._validate_draft(operations, stage_contracts, rationale)
        if self.mode is OrchestrationMode.DAG_RECORD:
            mutation = await asyncio.to_thread(
                self._apply_draft, draft, "harness:auto"
            )
            if not mutation.accepted:
                raise RuntimeError(
                    f"mechanism draft failed to apply: {mutation.rejection_code}: "
                    f"{mutation.rejection_reason}"
                )
            accepted = draft.model_copy(update={"state": "accepted"})
            draft_id = await asyncio.to_thread(
                self.store.save_draft, accepted, actor_id="harness:auto"
            )
            return {
                "draft_id": draft_id,
                "state": "accepted",
                "accepted": True,
                "revisions": mutation.revisions,
            }
        draft_id = await asyncio.to_thread(
            self.store.save_draft, draft, actor_id=actor_id
        )
        return {"draft_id": draft_id, "state": "open", "accepted": False}

    async def accept_mechanism(
        self,
        *,
        verdict: str,
        rationale: str = "",
        draft_id: str | None = None,
    ) -> dict[str, Any]:
        """Supervisor 的草稿裁决（guided only）：accept 落图（契约并入
        add ops）；reject 退回草稿并附理由。"""
        if not self.enabled:
            raise RuntimeError(
                "accept_mechanism is disabled in standard orchestration mode"
            )
        if self.mode is not OrchestrationMode.DAG_GUIDED:
            raise RuntimeError(
                "dag_accept_mechanism is guided-only; dag_record auto-accepts proposals"
            )
        await self.initialize()
        if draft_id:
            draft = await asyncio.to_thread(self.store.get_draft, draft_id)
            if draft is None:
                raise RuntimeError(f"mechanism draft {draft_id!r} does not exist")
            if draft.state != "open":
                raise RuntimeError(
                    f"mechanism draft {draft_id!r} is already {draft.state}"
                )
            resolved_id = draft_id
        else:
            found = await asyncio.to_thread(self.store.latest_open_draft)
            if found is None:
                raise RuntimeError("no open mechanism draft to review")
            resolved_id, draft = found
        if verdict == "reject":
            if not rationale.strip():
                raise RuntimeError(
                    "rejecting a mechanism draft requires a non-empty rationale"
                )
            await asyncio.to_thread(
                self.store.set_draft_state,
                resolved_id,
                "rejected",
                reject_reason=rationale,
            )
            return {
                "draft_id": resolved_id,
                "state": "rejected",
                "accepted": False,
                "reason": rationale,
            }
        mutation = await asyncio.to_thread(
            self._apply_draft, draft, "harness:supervisor-accept"
        )
        if not mutation.accepted:
            raise RuntimeError(
                f"mechanism draft failed to apply: {mutation.rejection_code}: "
                f"{mutation.rejection_reason}"
            )
        await asyncio.to_thread(
            self.store.set_draft_state, resolved_id, "accepted"
        )
        return {
            "draft_id": resolved_id,
            "state": "accepted",
            "accepted": True,
            "revisions": mutation.revisions,
        }
