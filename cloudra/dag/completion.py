"""Deterministic delivery coverage and bounded prompt projections."""

from __future__ import annotations

from typing import Any

from cloudra.dag.models import (
    CoverageContract,
    CoverageGateResult,
    DagProjection,
    DeliveryReport,
    GraphData,
    GraphSnapshot,
    OrchestrationMode,
    StageState,
    StageStatus,
    derive_evidence_level,
    normalize_orchestration_mode,
)

_LEVEL_RANK = {
    "proposed": 0,
    "structure_supported": 1,
    "saddle_supported": 2,
    "endpoint_supported": 3,
    "thermo_annotated": 4,
}


def _level_at_least(actual: str, required: str) -> bool:
    return _LEVEL_RANK.get(actual, -1) >= _LEVEL_RANK.get(required, 10_000)


def _waiver_for(
    contract: CoverageContract,
    gate: CoverageGateResult,
):
    return next(
        (
            waiver
            for waiver in contract.waivers
            if waiver.gate_code == gate.code
            and waiver.target_type == gate.target_type
            and waiver.target_id == gate.target_id
        ),
        None,
    )


def evaluate_delivery(
    delivery: GraphData,
    contract: CoverageContract,
) -> DeliveryReport:
    satisfied: list[CoverageGateResult] = []
    unresolved: list[CoverageGateResult] = []
    inconclusive: list[CoverageGateResult] = []
    waived: list[CoverageGateResult] = []

    def record(
        gate: CoverageGateResult, *, uncertain: bool = False, waivable: bool = True
    ) -> None:
        waiver = _waiver_for(contract, gate) if waivable else None
        if waiver is not None:
            waived.append(gate.model_copy(update={"waiver": waiver}))
        elif uncertain:
            inconclusive.append(gate)
        else:
            unresolved.append(gate)

    def evaluate_stages(
        target_type: str,
        target_id: str,
        stages: list[StageState],
    ) -> str:
        """逐阶段评估声明了阶段契约的元素，返回 supported/disposed/open。

        complete 口径（D10）：每个必需阶段 supported、带非空理由的
        not_applicable（该槽不成立），或带非空理由的 skipped。pending 与
        rejected 都是开放缺口——rejected 不是处置，只能重绑（D2）或显式
        skip-with-reason（D6）；缺口带上其理由。无理由的 skipped /
        not_applicable（missing_stage_reason）不可豁免（D9——USER waiver
        也不能让无理由处置计入完成）。not_applicable 与 skipped 都计入完成
        但记不同的 code，供审计区分"槽位不成立"与"主动放弃"。
        """
        required = [stage for stage in stages if stage.required]
        open_gap = False
        for stage in required:
            if stage.status is StageStatus.REJECTED:
                detail = f"stage {stage.kind.value} was rejected"
                if stage.reason.strip():
                    detail += f": {stage.reason.strip()}"
                record(
                    CoverageGateResult(
                        code="stage_rejected",
                        target_type=target_type,
                        target_id=target_id,
                        detail=detail,
                    )
                )
                open_gap = True
            elif stage.status in (StageStatus.SKIPPED, StageStatus.NOT_APPLICABLE) and not stage.reason.strip():
                record(
                    CoverageGateResult(
                        code="missing_stage_reason",
                        target_type=target_type,
                        target_id=target_id,
                        detail=(
                            f"stage {stage.kind.value} is {stage.status.value} "
                            "without a persisted reason"
                        ),
                    ),
                    uncertain=True,
                    waivable=False,
                )
                open_gap = True
        pending = [
            stage for stage in required if stage.status is StageStatus.PENDING
        ]
        if pending:
            record(
                CoverageGateResult(
                    code="missing_stage_evidence",
                    target_type=target_type,
                    target_id=target_id,
                    detail=(
                        "required stages pending: "
                        + ", ".join(stage.kind.value for stage in pending)
                    ),
                )
            )
            open_gap = True
        if open_gap:
            return "open"
        not_applicable = [
            stage for stage in required if stage.status is StageStatus.NOT_APPLICABLE
        ]
        skipped = [
            stage for stage in required if stage.status is StageStatus.SKIPPED
        ]
        if not_applicable:
            satisfied.append(
                CoverageGateResult(
                    code="stage_not_applicable",
                    target_type=target_type,
                    target_id=target_id,
                    detail=(
                        "required stages not applicable with reasons: "
                        + ", ".join(stage.kind.value for stage in not_applicable)
                    ),
                )
            )
            if skipped:
                satisfied.append(
                    CoverageGateResult(
                        code="branch_disposed",
                        target_type=target_type,
                        target_id=target_id,
                        detail="required stages are explicitly skipped with reasons",
                    )
                )
            return "disposed"
        if skipped:
            satisfied.append(
                CoverageGateResult(
                    code="branch_disposed",
                    target_type=target_type,
                    target_id=target_id,
                    detail="required stages are explicitly skipped with reasons",
                )
            )
            return "disposed"
        level = derive_evidence_level(stages, is_edge=target_type == "edge")
        satisfied.append(
            CoverageGateResult(
                code=(
                    "elementary_step_endpoint_supported"
                    if target_type == "edge"
                    else "intermediate_structure_supported"
                ),
                target_type=target_type,
                target_id=target_id,
                detail=f"all required stages supported; evidence level is {level}",
            )
        )
        return "supported"

    if not delivery.nodes or not delivery.edges:
        record(
            CoverageGateResult(
                code="empty_delivery_graph",
                target_type="graph",
                target_id=delivery.graph_id,
                detail="a mechanism delivery requires intermediates and at least one elementary step",
            )
        )

    for node in delivery.nodes:
        if node.stages:
            evaluate_stages("node", node.node_id, node.stages)
            continue
        level = node.evidence_level
        if level == "rejected":
            # D10：rejected 不是处置——带理由也是开放缺口，只能重绑或
            # 显式 skip-with-reason 退出。
            detail = "intermediate occurrence was rejected"
            if node.reason.strip():
                detail += f": {node.reason.strip()}"
            record(
                CoverageGateResult(
                    code="branch_rejected",
                    target_type="node",
                    target_id=node.node_id,
                    detail=detail,
                )
            )
            continue
        if level == "inconclusive":
            # inconclusive 是 skip 的等价处置：理由永远必需（D9——
            # require_branch_disposition 被 USER 降低也不能让无理由处置
            # 计入完成；该缺口同样不可豁免）。
            if not node.reason.strip():
                record(
                    CoverageGateResult(
                        code="missing_branch_disposition",
                        target_type="node",
                        target_id=node.node_id,
                        detail="inconclusive intermediate occurrence has no persisted reason",
                    ),
                    uncertain=True,
                    waivable=False,
                )
            else:
                satisfied.append(
                    CoverageGateResult(
                        code="branch_disposed",
                        target_type="node",
                        target_id=node.node_id,
                        detail="intermediate occurrence is explicitly inconclusive",
                    )
                )
            continue
        if _level_at_least(level, contract.required_node_level):
            satisfied.append(
                CoverageGateResult(
                    code="intermediate_structure_supported",
                    target_type="node",
                    target_id=node.node_id,
                    detail=f"evidence level is {level}",
                )
            )
        else:
            record(
                CoverageGateResult(
                    code="missing_intermediate_structure",
                    target_type="node",
                    target_id=node.node_id,
                    detail=f"requires {contract.required_node_level}, found {level}",
                )
            )

    for edge in delivery.edges:
        if edge.stages:
            evaluate_stages("edge", edge.edge_id, edge.stages)
            if contract.require_thermochemistry and not (
                derive_evidence_level(edge.stages, is_edge=True)
                == "thermo_annotated"
                or edge.thermochemistry_supported is True
            ):
                # f2：契约级检查对每个元素都生效，不因 skipped 处置而跳过。
                record(
                    CoverageGateResult(
                        code="missing_thermochemistry",
                        target_type="edge",
                        target_id=edge.edge_id,
                        detail="thermochemistry was requested but no supported energy annotation is linked",
                    )
                )
            continue
        level = edge.evidence_level
        if level == "rejected":
            # D10：同节点分支——rejected 是开放缺口，不是处置。
            detail = "elementary-step branch was rejected"
            if edge.reason.strip():
                detail += f": {edge.reason.strip()}"
            record(
                CoverageGateResult(
                    code="branch_rejected",
                    target_type="edge",
                    target_id=edge.edge_id,
                    detail=detail,
                )
            )
        elif level == "inconclusive":
            # D9：同节点分支——无理由处置永不计入完成，且不可豁免。
            if not edge.reason.strip():
                record(
                    CoverageGateResult(
                        code="missing_branch_disposition",
                        target_type="edge",
                        target_id=edge.edge_id,
                        detail="inconclusive elementary-step branch has no persisted reason",
                    ),
                    uncertain=True,
                    waivable=False,
                )
            else:
                satisfied.append(
                    CoverageGateResult(
                        code="branch_disposed",
                        target_type="edge",
                        target_id=edge.edge_id,
                        detail="elementary-step branch is explicitly inconclusive",
                    )
                )
        elif _level_at_least(level, contract.required_edge_level):
            satisfied.append(
                CoverageGateResult(
                    code="elementary_step_endpoint_supported",
                    target_type="edge",
                    target_id=edge.edge_id,
                    detail=f"evidence level is {level}",
                )
            )
        else:
            record(
                CoverageGateResult(
                    code="missing_endpoint_evidence",
                    target_type="edge",
                    target_id=edge.edge_id,
                    detail=(
                        f"requires {contract.required_edge_level}, found {level}; "
                        "TS guesses and scans are advisory"
                    ),
                )
            )
        # f2：契约级检查不因分支处置（rejected/inconclusive）而跳过。
        if contract.require_thermochemistry and not (
            level == "thermo_annotated"
            or edge.thermochemistry_supported is True
        ):
            record(
                CoverageGateResult(
                    code="missing_thermochemistry",
                    target_type="edge",
                    target_id=edge.edge_id,
                    detail="thermochemistry was requested but no supported energy annotation is linked",
                )
            )

    return DeliveryReport(
        complete=not unresolved and not inconclusive,
        satisfied=satisfied,
        unresolved=unresolved,
        inconclusive=inconclusive,
        waived=waived,
    )


def build_projection(
    snapshot: GraphSnapshot,
    *,
    mode: str | OrchestrationMode,
    contract: CoverageContract,
    history: list[dict[str, Any]] | None = None,
    pending_reviews: list[dict[str, Any]] | None = None,
    rejected_draft: dict[str, Any] | None = None,
) -> DagProjection:
    """有界投影：delivery 缺口 + 待复核调用 + 近期变更 + 被驳回草稿。

    Phase 4 起 process 图已删除——不再有 frontier/blockers/assigned_to_me；
    投影只讲交付面：每个元素欠哪些阶段、哪些调用在等复核、最近被驳回的
    机理草稿附驳回理由。
    """
    report = evaluate_delivery(snapshot.delivery, contract)
    gaps = [*report.unresolved, *report.inconclusive]
    delivery_gaps = [
        gate.model_dump(mode="json", exclude={"waiver"}) for gate in gaps[:12]
    ]
    safe_history = []
    for item in (history or [])[:8]:
        safe_history.append(
            {
                key: item[key]
                for key in (
                    "mutation_id",
                    "actor",
                    "accepted",
                    "rejection_code",
                    "resulting_revisions",
                    "created_at",
                )
                if key in item
            }
        )
    return DagProjection(
        mode=normalize_orchestration_mode(mode),
        revisions=dict(snapshot.bundle.revisions),
        delivery_gaps=delivery_gaps,
        recent_mutations=safe_history,
        pending_reviews=list(pending_reviews or [])[:12],
        rejected_draft=rejected_draft,
    )
