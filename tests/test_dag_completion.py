import pytest


def _load_completion_api():
    try:
        from cloudra.dag.completion import build_projection, evaluate_delivery
        from cloudra.dag.models import (
            CoverageContract,
            CoverageWaiver,
            DagEdge,
            DagNode,
            GraphBundle,
            GraphData,
            GraphSnapshot,
        )
    except (ImportError, ModuleNotFoundError) as exc:
        pytest.fail(f"DAG completion API is missing: {exc}")
    return locals()


def _delivery(api, node_levels, edge_levels, *, edge_payloads=None):
    nodes = [
        api["DagNode"](
            node_id=f"i{index}",
            node_type="intermediate_occurrence",
            label=f"intermediate {index}",
            payload={"evidence_level": level},
        )
        for index, level in enumerate(node_levels)
    ]
    edges = []
    for index, level in enumerate(edge_levels):
        payload = {"evidence_level": level}
        if edge_payloads:
            payload.update(edge_payloads[index])
        edges.append(
            api["DagEdge"](
                edge_id=f"e{index}",
                source_node_id=nodes[index].node_id,
                target_node_id=nodes[index + 1].node_id,
                edge_type="elementary_step",
                label=f"step {index}",
                payload=payload,
            )
        )
    return api["GraphData"](
        graph_id="dag_delivery",
        graph_kind="delivery",
        revision=1,
        nodes=nodes,
        edges=edges,
    )


def test_endpoint_supported_path_satisfies_default_contract():
    api = _load_completion_api()
    delivery = _delivery(
        api,
        ["structure_supported", "structure_supported"],
        ["endpoint_supported"],
    )

    report = api["evaluate_delivery"](
        delivery, api["CoverageContract"].mechanism_default()
    )

    assert report.complete
    assert report.unresolved == []


@pytest.mark.parametrize("level", ["proposed", "saddle_supported"])
def test_ts_guess_or_saddle_without_endpoints_is_not_complete(level):
    api = _load_completion_api()
    delivery = _delivery(
        api,
        ["structure_supported", "structure_supported"],
        [level],
        edge_payloads=[{"advisory_sources": ["ts_guess", "scan_parse"]}],
    )

    report = api["evaluate_delivery"](
        delivery, api["CoverageContract"].mechanism_default()
    )

    assert not report.complete
    assert "missing_endpoint_evidence" in {gap.code for gap in report.unresolved}


def test_rejected_branch_needs_a_persisted_disposition_reason():
    api = _load_completion_api()
    without_reason = _delivery(
        api,
        ["structure_supported", "structure_supported"],
        ["rejected"],
    )
    with_reason = _delivery(
        api,
        ["structure_supported", "structure_supported"],
        ["rejected"],
        edge_payloads=[{"reason": "optimization returns to reactant minimum"}],
    )
    contract = api["CoverageContract"].mechanism_default()

    incomplete = api["evaluate_delivery"](without_reason, contract)
    complete = api["evaluate_delivery"](with_reason, contract)

    assert not incomplete.complete
    assert "missing_branch_disposition" in {
        gap.code for gap in incomplete.inconclusive
    }
    assert complete.complete


def test_disposed_branch_does_not_undermine_supported_intermediates():
    """带 reason 的 rejected 边是已处置的竞争分支，不是 claimed step。

    它与同文件 test_rejected_branch_needs_a_persisted_disposition_reason
    使用相同 fixture：claimed 中间体满足结构证据、竞争分支已显式处置，
    按设计即 complete；该 rejected 边不会计入 unresolved，也不能充当
    任何 claimed step 的端点证据。
    """
    api = _load_completion_api()
    delivery = _delivery(
        api,
        ["structure_supported", "structure_supported"],
        ["rejected"],
        edge_payloads=[{"reason": "candidate collapses to the reactant minimum"}],
    )

    report = api["evaluate_delivery"](
        delivery,
        api["CoverageContract"].mechanism_default(),
    )

    assert report.complete
    assert report.unresolved == []
    assert "branch_disposed" in {gate.code for gate in report.satisfied}


def test_only_explicit_user_waiver_can_close_a_missing_gate():
    api = _load_completion_api()
    delivery = _delivery(
        api,
        ["structure_supported", "structure_supported"],
        ["saddle_supported"],
    )
    waiver = api["CoverageWaiver"](
        gate_code="missing_endpoint_evidence",
        target_type="edge",
        target_id="e0",
        user_id="chemist",
        session_id="s1",
        rationale="accept partial endpoint validation for this exploratory run",
    )
    contract = api["CoverageContract"].mechanism_default(
        waivers=[waiver]
    )

    report = api["evaluate_delivery"](delivery, contract)

    assert report.complete
    assert report.unresolved == []
    assert report.waived[0].waiver == waiver


def test_thermochemistry_is_required_only_when_requested():
    api = _load_completion_api()
    delivery = _delivery(
        api,
        ["structure_supported", "structure_supported"],
        ["endpoint_supported"],
    )

    ordinary = api["evaluate_delivery"](
        delivery,
        api["CoverageContract"].mechanism_default(),
    )
    thermo = api["evaluate_delivery"](
        delivery,
        api["CoverageContract"].mechanism_default(require_thermochemistry=True),
    )

    assert ordinary.complete
    assert not thermo.complete
    assert "missing_thermochemistry" in {gap.code for gap in thermo.unresolved}


def test_projection_is_bounded_deterministic_and_contains_no_evidence_bodies():
    api = _load_completion_api()
    process_nodes = [
        api["DagNode"](
            node_id=f"work-{index:02d}",
            node_type="calculation",
            label=f"work {index}",
            payload={
                "status": "ready",
                "priority": index % 4,
                "created_at": f"2026-08-10T00:{index:02d}:00Z",
                "full_tool_result": "SECRET-HEAVY-ATOM-MAP",
            },
        )
        for index in range(20)
    ]
    process = api["GraphData"](
        graph_id="dag_process",
        graph_kind="process",
        revision=4,
        nodes=process_nodes,
    )
    delivery = _delivery(
        api,
        ["structure_supported", "structure_supported"],
        ["saddle_supported"],
    )
    snapshot = api["GraphSnapshot"](
        bundle=api["GraphBundle"](
            process_graph_id="dag_process",
            delivery_graph_id="dag_delivery",
            revisions={"process": 4, "delivery": 1},
        ),
        process=process,
        delivery=delivery,
    )
    history = [
        {"mutation_id": f"mut-{index}", "actor": "harness", "accepted": True}
        for index in range(15)
    ]

    projection = api["build_projection"](
        snapshot,
        mode="dag_guided",
        contract=api["CoverageContract"].mechanism_default(),
        history=history,
    )
    text = projection.to_prompt_text()

    assert len(projection.frontier) == 12
    assert len(projection.recent_mutations) == 8
    assert [item["node_id"] for item in projection.frontier[:3]] == [
        "work-03",
        "work-07",
        "work-11",
    ]
    assert "dag_guided" in text
    assert '"process": 4' in text
    assert "missing_endpoint_evidence" in text
    assert "SECRET-HEAVY-ATOM-MAP" not in text


def test_superseded_process_dependency_no_longer_blocks_frontier():
    api = _load_completion_api()
    predecessor = api["DagNode"](
        node_id="old-scan",
        node_type="calculation",
        label="obsolete scan",
        payload={"status": "failed"},
    )
    replacement = api["DagNode"](
        node_id="new-neb",
        node_type="calculation",
        label="replacement NEB",
        payload={"status": "ready", "priority": 10},
    )
    dependency = api["DagEdge"](
        edge_id="old-scan-before-neb",
        source_node_id="old-scan",
        target_node_id="new-neb",
        edge_type="depends_on",
        payload={"status": "superseded", "reason": "scan coordinate was wrong"},
    )
    process = api["GraphData"](
        graph_id="dag_process",
        graph_kind="process",
        revision=2,
        nodes=[predecessor, replacement],
        edges=[dependency],
    )
    delivery = _delivery(
        api,
        ["structure_supported", "structure_supported"],
        ["saddle_supported"],
    )
    snapshot = api["GraphSnapshot"](
        bundle=api["GraphBundle"](
            process_graph_id="dag_process",
            delivery_graph_id="dag_delivery",
            revisions={"process": 2, "delivery": 1},
        ),
        process=process,
        delivery=delivery,
    )

    projection = api["build_projection"](
        snapshot,
        mode="dag_guided",
        contract=api["CoverageContract"].mechanism_default(),
    )

    assert [item["node_id"] for item in projection.frontier] == ["new-neb"]
