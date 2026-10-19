"""Mechanism draft lifecycle: proposal validation and supervisor verdicts."""

from __future__ import annotations

import asyncio
from typing import Any, Literal

from pydantic import ValidationError

from cloudra.dag.models import (
    ELEMENTARY_STEP_STAGE_KINDS,
    OCCURRENCE_STAGE_KINDS,
    AddEdge,
    AddNode,
    ClaimSpec,
    ElementaryStepEdge,
    GraphActor,
    GraphData,
    GraphKind,
    GraphOperation,
    MechanismDraft,
    MutationBatch,
    MutationResult,
    OrchestrationMode,
    SpeciesNode,
    StageContract,
    StageKind,
    StageState,
    StageStatus,
    UpdateEdge,
    UpdateNode,
    parse_graph_operation,
)
from cloudra.dag.store import SpeciesConflictError
from cloudra.infra.tool_errors import validation_feedback


def _contract_targets(spec: ClaimSpec) -> set[str]:
    """契约声明的目标集合（scope.targets 优先，reference.targets 兼容）。"""
    for container in (spec.scope, spec.reference):
        targets = container.get("targets")
        if targets:
            return {str(item) for item in targets}
    return set()


def classify_contract_change(
    old: ClaimSpec | None, new: ClaimSpec
) -> Literal["compatible", "scope_change"]:
    """已接受契约 → 新提案的变更分类。

    scope_change（必须重新审批，未批准不改变当前范围）：
    - kind 变化（回答的科学问题变了，如电子能垒改成结构展示）；
    - 删除任何 required_checks（降低要求）；
    - 移除已声明目标（targets 收缩）；
    - 已声明 quantity/unit 被改写（所回答的量变了）。
    compatible：新增检查、补充 optional、显示标签修正等不缩小科学范围的
    变更。旧契约不存在（首次）一律 compatible。
    """
    if old is None:
        return "compatible"
    if new.kind != old.kind:
        return "scope_change"
    if old.required_checks - new.required_checks:
        return "scope_change"
    if _contract_targets(old) - _contract_targets(new):
        return "scope_change"
    if old.quantity and new.quantity != old.quantity:
        return "scope_change"
    if old.unit is not None and new.unit != old.unit:
        return "scope_change"
    return "compatible"


class DraftsMixin:
    """机理草稿：propose 即落候选图，accept 记录审查结论。"""

    @staticmethod
    def _normalize_ts_guess_advisory(
        draft: MechanismDraft,
    ) -> tuple[MechanismDraft, list[str]]:
        """ts_guess 按定义是 advisory 阶段（models.StageKind：永远不充抵
        ts_opt/frequency），不可被 required。契约生效（落图/落库）前一律
        规范化为 required=False，并返回逐条规范化痕迹——fail-loud，不静默
        改写。契约既可能在 stage_contracts 里，也可能直接嵌在 add op 的
        元素 stages 里，两处都收口。"""
        notes: list[str] = []

        def _fix(stages: list[StageState], element_id: str) -> list[StageState]:
            fixed: list[StageState] = []
            for stage in stages:
                if stage.kind is StageKind.TS_GUESS and stage.required:
                    stage = stage.model_copy(update={"required": False})
                    notes.append(
                        f"{element_id}: ts_guess normalized to advisory "
                        "(required=False); an advisory stage can never be "
                        "required and never blocks ts_opt/frequency binds"
                    )
                fixed.append(stage)
            return fixed

        contracts = {
            element_id: contract.model_copy(
                update={"stages": _fix(list(contract.stages), element_id)}
            )
            for element_id, contract in draft.stage_contracts.items()
        }
        operations: list[GraphOperation] = []
        for op in draft.operations:
            if isinstance(op, (AddNode, AddEdge)):
                element = op.node if isinstance(op, AddNode) else op.edge
                element_id = (
                    op.node.node_id if isinstance(op, AddNode) else op.edge.edge_id
                )
                embedded = list(getattr(element, "stages", []) or [])
                if embedded:
                    element = element.model_copy(
                        update={"stages": _fix(embedded, element_id)}
                    )
                    op = op.model_copy(
                        update={"node" if isinstance(op, AddNode) else "edge": element}
                    )
            operations.append(op)
        return (
            draft.model_copy(
                update={"operations": operations, "stage_contracts": contracts}
            ),
            notes,
        )

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
        for index, raw in enumerate(operations_raw):
            try:
                op = parse_graph_operation(raw)
            except ValidationError as exc:
                raise RuntimeError(validation_feedback(exc, prefix=f"operations.{index}")) from exc
            except ValueError as exc:
                raise RuntimeError(f"operations.{index}: invalid operation; use the documented delivery operation shape") from exc
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
    def _assemble_declarative_proposal(
        species: list[dict[str, Any] | Any],
        steps: list[dict[str, Any] | Any],
        rationale: str,
        existing: GraphData,
    ) -> MechanismDraft:
        import uuid

        seen_species_names: set[str] = set()
        name_to_node_ids: dict[str, set[str]] = {}
        all_node_ids: set[str] = set()
        for node in existing.nodes:
            all_node_ids.add(node.node_id)
            for key in {node.node_id, getattr(node, "name", ""), node.label}:
                if key:
                    name_to_node_ids.setdefault(key, set()).add(node.node_id)

        def resolve_species(value: str, step_name: str) -> str:
            matches = name_to_node_ids.get(value, set())
            if len(matches) != 1:
                reason = "unknown" if not matches else "ambiguous"
                raise RuntimeError(f"{reason} species {value!r} in step {step_name!r}")
            return next(iter(matches))

        species_ops: list[GraphOperation] = []

        for item in (species or []):
            raw_name = item.get("name") if isinstance(item, dict) else getattr(item, "name", None)
            if not raw_name or not str(raw_name).strip():
                raise RuntimeError("species name cannot be empty")
            name = str(raw_name).strip()
            if name in seen_species_names or name in name_to_node_ids:
                raise SpeciesConflictError(f"duplicate species name: {name!r}")
            seen_species_names.add(name)
            node_id = f"sp_{uuid.uuid4().hex[:8]}"
            name_to_node_ids[name] = {node_id}
            name_to_node_ids[node_id] = {node_id}
            all_node_ids.add(node_id)
            smiles = item.get("smiles") if isinstance(item, dict) else getattr(item, "smiles", None)
            species_ops.append(
                AddNode(
                    op="add_node",
                    graph=GraphKind.DELIVERY,
                    node=SpeciesNode(
                        node_id=node_id,
                        name=name,
                        label=name,
                        smiles=smiles,
                    ),
                )
            )

        seen_step_names: set[str] = {
            key for edge in existing.edges
            for key in (edge.edge_id, getattr(edge, "name", ""), edge.label)
            if key
        }
        step_ops: list[GraphOperation] = []
        for item in (steps or []):
            raw_name = item.get("name") if isinstance(item, dict) else getattr(item, "name", None)
            if not raw_name or not str(raw_name).strip():
                raise RuntimeError("step name cannot be empty")
            step_name = str(raw_name).strip()
            if step_name in seen_step_names:
                raise RuntimeError(f"duplicate step name: {step_name!r}")
            seen_step_names.add(step_name)

            from_raw = (
                item.get("from") or item.get("from_")
                if isinstance(item, dict)
                else getattr(item, "from_", getattr(item, "from", None))
            )
            to_raw = (
                item.get("to") or item.get("to_")
                if isinstance(item, dict)
                else getattr(item, "to", getattr(item, "to_", None))
            )
            from_name = str(from_raw).strip() if from_raw else ""
            to_name = str(to_raw).strip() if to_raw else ""

            from_node_id = resolve_species(from_name, step_name)
            to_node_id = resolve_species(to_name, step_name)
            if from_node_id == to_node_id:
                raise RuntimeError(f"step {step_name!r} is a self-loop: {from_name!r} -> {to_name!r}")

            edge_id = f"step_{uuid.uuid4().hex[:8]}"
            step_ops.append(
                AddEdge(
                    op="add_edge",
                    graph=GraphKind.DELIVERY,
                    edge=ElementaryStepEdge(
                        edge_id=edge_id,
                        name=step_name,
                        label=step_name,
                        source_node_id=from_node_id,
                        target_node_id=to_node_id,
                    ),
                )
            )

        # Acyclicity check
        indegree: dict[str, int] = {node_id: 0 for node_id in all_node_ids}
        outgoing: dict[str, list[str]] = {node_id: [] for node_id in all_node_ids}
        for edge in [*existing.edges, *(op.edge for op in step_ops if isinstance(op, AddEdge))]:
            indegree[edge.target_node_id] += 1
            outgoing[edge.source_node_id].append(edge.target_node_id)
        ready = [nid for nid, deg in indegree.items() if deg == 0]
        visited = 0
        while ready:
            nid = ready.pop(0)
            visited += 1
            for tgt in outgoing[nid]:
                indegree[tgt] -= 1
                if indegree[tgt] == 0:
                    ready.append(tgt)
        if visited != len(all_node_ids):
            raise RuntimeError("graph contains a cycle")

        contracts: dict[str, StageContract] = {}
        for sp_op in species_ops:
            assert isinstance(sp_op, AddNode)
            contracts[sp_op.node.node_id] = StageContract(
                stages=[StageState(kind=StageKind.GEOMETRY, status=StageStatus.PENDING)]
            )
        for st_op in step_ops:
            assert isinstance(st_op, AddEdge)
            # 默认 live 契约必须证明鞍点与两端物种的路径方向。
            # ts_guess 落库前会规范化为 advisory。
            contracts[st_op.edge.edge_id] = StageContract(
                stages=[
                    StageState(kind=StageKind.TS_GUESS, status=StageStatus.PENDING),
                    StageState(kind=StageKind.TS_OPT, status=StageStatus.PENDING),
                    StageState(kind=StageKind.FREQUENCY, status=StageStatus.PENDING),
                    StageState(kind=StageKind.SHORT_IRC, status=StageStatus.PENDING),
                ]
            )

        return MechanismDraft(
            operations=[*species_ops, *step_ops],
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

    @staticmethod
    def _resolve_delivery_targets(
        raw_targets: list[str], existing: GraphData, draft: MechanismDraft
    ) -> list[str]:
        candidates: dict[str, set[str]] = {}
        for element in [
            *existing.nodes, *existing.edges,
            *(op.node for op in draft.operations if isinstance(op, AddNode)),
            *(op.edge for op in draft.operations if isinstance(op, AddEdge)),
        ]:
            element_id = getattr(element, "node_id", None) or element.edge_id
            for key in {element_id, getattr(element, "name", ""), element.label}:
                if key:
                    candidates.setdefault(key, set()).add(element_id)
        resolved: list[str] = []
        for raw in raw_targets:
            target = str(raw).strip()
            matches = candidates.get(target, set())
            if len(matches) != 1:
                reason = "unknown" if not matches else "ambiguous"
                raise RuntimeError(f"{reason} delivery target {target!r}; use a unique name or ID")
            target_id = next(iter(matches))
            if target_id in resolved:
                raise RuntimeError(f"duplicate delivery target {target!r}")
            resolved.append(target_id)
        return resolved

    def _persist_draft(
        self, draft: MechanismDraft, graph_actor_id: str, draft_actor_id: str
    ) -> tuple[MutationResult | None, str]:
        if not draft.operations:
            return None, self.store.save_draft(draft, actor_id=draft_actor_id)
        operations = self._draft_operations(draft)
        last: MutationResult | None = None
        for _attempt in range(8):
            last, draft_id = self.engine.apply_draft_batch(
                MutationBatch(
                    session_id=self.session_id,
                    actor=GraphActor.HARNESS,
                    actor_id=graph_actor_id,
                    base_revisions=self.store.load_bundle().revisions,
                    operations=operations,
                    rationale=draft.rationale,
                ),
                draft,
                actor_id=draft_actor_id,
            )
            if last.accepted:
                assert draft_id is not None
                return last, draft_id
            if last.rejection_code != "stale_revision":
                break
        assert last is not None
        raise RuntimeError(
            f"mechanism draft failed to apply: {last.rejection_code}: "
            f"{last.rejection_reason}"
        )

    async def propose_mechanism(
        self,
        *,
        rationale: str,
        species: list[dict[str, Any] | Any] | None = None,
        steps: list[dict[str, Any] | Any] | None = None,
        operations: list[dict[str, Any]] | None = None,
        stage_contracts: dict[str, list[str]] | None = None,
        delivery_targets: list[str] | None = None,
        actor_id: str,
        claim_spec: dict[str, Any] | None = None,
        contract_version: int = 1,
    ) -> dict[str, Any]:
        """Coordinator 的机理草稿：两种模式立即落图，guided 异步送审。"""
        if not self.enabled:
            raise RuntimeError(
                "propose_mechanism is disabled in standard orchestration mode"
            )
        if not rationale or not rationale.strip():
            raise RuntimeError("a mechanism proposal requires a non-empty rationale")
        await self.initialize()
        existing = (await asyncio.to_thread(self.store.load_snapshot)).delivery
        if species is not None or steps is not None:
            draft = self._assemble_declarative_proposal(species or [], steps or [], rationale, existing)
        else:
            draft = self._validate_draft(operations or [], stage_contracts or {}, rationale)
        if not draft.operations and not delivery_targets:
            raise RuntimeError("a proposal requires graph changes or delivery_targets")
        # 契约生效收口：ts_guess 一律 advisory（required=False），痕迹随返回带出。
        draft, ts_guess_notes = self._normalize_ts_guess_advisory(draft)
        accepted_spec = await asyncio.to_thread(self.store.accepted_claim_spec)
        spec = ClaimSpec.model_validate(claim_spec) if claim_spec is not None else None
        if delivery_targets is not None:
            if not delivery_targets:
                raise RuntimeError("delivery_targets must name at least one species or step")
            resolved = self._resolve_delivery_targets(delivery_targets, existing, draft)
            spec = spec or accepted_spec or ClaimSpec(kind="mechanism")
            spec = spec.model_copy(update={
                "scope": {**spec.scope, "targets": resolved},
                "reference": {key: value for key, value in spec.reference.items()
                              if key != "targets"},
            })
        if spec is not None:
            draft = draft.model_copy(
                update={"claim_spec": spec, "contract_version": 2}
            )
            contract_version = 2
        scope_change = False
        if contract_version >= 2 and draft.claim_spec is not None:
            scope_change = classify_contract_change(accepted_spec, draft.claim_spec) == "scope_change"
        auto_accept = self.mode is OrchestrationMode.DAG_RECORD
        persisted = draft.model_copy(update={"state": "accepted"}) if auto_accept else draft
        mutation, draft_id = await asyncio.to_thread(
            self._persist_draft,
            persisted,
            "harness:auto" if auto_accept else "harness:draft-open",
            "harness:auto" if auto_accept else actor_id,
        )
        result = {
            "draft_id": draft_id,
            "state": persisted.state,
            "accepted": auto_accept,
            "normalized_advisory_stages": ts_guess_notes,
        }
        if scope_change:
            result["scope_change"] = True
            if not auto_accept:
                result["pending_approval"] = True
        if mutation is not None and auto_accept:
            result["revisions"] = mutation.revisions
        return result

    async def accept_mechanism(
        self,
        *,
        verdict: str,
        rationale: str = "",
        draft_id: str | None = None,
    ) -> dict[str, Any]:
        """Supervisor 的草稿裁决（guided only）：accept 确认已落图候选；
        reject 附理由。两种裁决都与落态同事务写一条
        durable 裁决通知（draft_verdict）给 proposer（legacy actor id，
        flush 时解析到活 session），由 flush_review_notifications 投递。"""
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
        proposer = await asyncio.to_thread(self.store.draft_actor_id, resolved_id)
        # 提案落图时已规范化 ts_guess；这里保持返回值含规范化痕迹。
        draft, ts_guess_notes = self._normalize_ts_guess_advisory(draft)

        def _notification(state: str, reason: str) -> dict[str, Any]:
            return {
                "recipient_session_id": proposer,
                "payload": {
                    "draft_id": resolved_id,
                    "verdict": state,
                    "reason": reason.strip(),
                },
            }

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
                notification=_notification("rejected", rationale),
            )
            return {
                "draft_id": resolved_id,
                "state": "rejected",
                "accepted": False,
                "reason": rationale,
            }
        await asyncio.to_thread(
            self.store.set_draft_state,
            resolved_id,
            "accepted",
            notification=_notification("accepted", ""),
        )
        return {
            "draft_id": resolved_id,
            "state": "accepted",
            "accepted": True,
            "revisions": (await asyncio.to_thread(self.engine.snapshot)).bundle.revisions,
            "normalized_advisory_stages": ts_guess_notes,
        }
