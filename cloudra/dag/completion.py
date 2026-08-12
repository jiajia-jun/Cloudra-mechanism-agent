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
    normalize_orchestration_mode,
)

_LEVEL_RANK = {
    "proposed": 0,
    "structure_supported": 1,
    "saddle_supported": 2,
    "endpoint_supported": 3,
    "thermo_annotated": 4,
}
_DISPOSITION_LEVELS = {"rejected", "inconclusive"}


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

    def record(gate: CoverageGateResult, *, uncertain: bool = False) -> None:
        waiver = _waiver_for(contract, gate)
        if waiver is not None:
            waived.append(gate.model_copy(update={"waiver": waiver}))
        elif uncertain:
            inconclusive.append(gate)
        else:
            unresolved.append(gate)

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
        level = node.evidence_level
        if level in _DISPOSITION_LEVELS:
            if contract.require_branch_disposition and not node.reason.strip():
                record(
                    CoverageGateResult(
                        code="missing_branch_disposition",
                        target_type="node",
                        target_id=node.node_id,
                        detail=f"{level} intermediate occurrence has no persisted reason",
                    ),
                    uncertain=True,
                )
            else:
                satisfied.append(
                    CoverageGateResult(
                        code="branch_disposed",
                        target_type="node",
                        target_id=node.node_id,
                        detail=f"intermediate occurrence is explicitly {level}",
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
        level = edge.evidence_level
        if level in _DISPOSITION_LEVELS:
            if contract.require_branch_disposition and not edge.reason.strip():
                record(
                    CoverageGateResult(
                        code="missing_branch_disposition",
                        target_type="edge",
                        target_id=edge.edge_id,
                        detail=f"{level} elementary-step branch has no persisted reason",
                    ),
                    uncertain=True,
                )
            else:
                satisfied.append(
                    CoverageGateResult(
                        code="branch_disposed",
                        target_type="edge",
                        target_id=edge.edge_id,
                        detail=f"elementary-step branch is explicitly {level}",
                    )
                )
            continue
        if _level_at_least(level, contract.required_edge_level):
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


def _compact_process_node(node) -> dict[str, Any]:
    return {
        "node_id": node.node_id,
        "node_type": node.node_type,
        "label": node.label,
        "status": node.status,
        "priority": node.priority,
    }


def build_projection(
    snapshot: GraphSnapshot,
    *,
    mode: str | OrchestrationMode,
    contract: CoverageContract,
    history: list[dict[str, Any]] | None = None,
    actor_id: str | None = None,
) -> DagProjection:
    process = snapshot.process
    statuses = {node.node_id: node.status for node in process.nodes}
    dependencies: dict[str, list[str]] = {node.node_id: [] for node in process.nodes}
    for edge in process.edges:
        if edge.status in {"skipped", "superseded"}:
            continue
        if edge.target_node_id in dependencies:
            dependencies[edge.target_node_id].append(edge.source_node_id)

    candidates = []
    blockers = []
    for node in process.nodes:
        status = statuses[node.node_id]
        unmet = [
            predecessor
            for predecessor in dependencies[node.node_id]
            if statuses.get(predecessor) not in {"succeeded", "skipped"}
        ]
        if status in {"proposed", "ready"} and not unmet:
            candidates.append(node)
        elif status in {"failed", "blocked"} or unmet:
            blockers.append(
                {
                    **_compact_process_node(node),
                    "reason": node.reason
                    or node.blocked_reason
                    or (f"waiting for: {', '.join(sorted(unmet))}" if unmet else ""),
                }
            )
    candidates.sort(
        key=lambda node: (
            -node.priority,
            node.created_at,
            node.node_id,
        )
    )
    blockers.sort(key=lambda item: (item["node_id"], item["status"]))

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
        frontier=[_compact_process_node(node) for node in candidates[:12]],
        blockers=blockers[:12],
        delivery_gaps=delivery_gaps,
        recent_mutations=safe_history,
        assigned_to_me=(
            [
                _compact_process_node(node)
                for node in process.nodes
                if node.assignee == actor_id
                and statuses[node.node_id] not in {"succeeded", "skipped"}
            ][:12]
            if actor_id
            else []
        ),
    )
