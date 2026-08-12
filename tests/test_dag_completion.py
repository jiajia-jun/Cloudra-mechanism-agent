import pytest


def _load_completion_api():
    try:
        from cloudra.dag import completion, models
    except (ImportError, ModuleNotFoundError) as exc:
        pytest.fail(f"DAG completion API is missing: {exc}")
    return {
        "build_projection": completion.build_projection,
        "evaluate_delivery": completion.evaluate_delivery,
        "CoverageContract": models.CoverageContract,
        "CoverageWaiver": models.CoverageWaiver,
        "DependencyEdge": models.DependencyEdge,
        "ElementaryStepEdge": models.ElementaryStepEdge,
        "OccurrenceNode": models.OccurrenceNode,
        "PlannedNode": models.PlannedNode,
        "GraphBundle": models.GraphBundle,
        "GraphData": models.GraphData,
        "GraphSnapshot": models.GraphSnapshot,
    }


def _delivery(api, node_levels, edge_levels, *, edge_payloads=None):
    nodes = [
        api["OccurrenceNode"](
            node_id=f"i{index}",
            label=f"intermediate {index}",
            role="intermediate",
            evidence_level=level,
        )
        for index, level in enumerate(node_levels)
    ]
    edges = []
    for index, level in enumerate(edge_levels):
        extra = dict(edge_payloads[index]) if edge_payloads else {}
        edges.append(
            api["ElementaryStepEdge"](
                edge_id=f"e{index}",
                source_node_id=nodes[index].node_id,
                target_node_id=nodes[index + 1].node_id,
                label=f"step {index}",
                evidence_level=level,
                **extra,
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
        api["PlannedNode"](
            node_id=f"work-{index:02d}",
            label=f"work {index}",
            status="ready",
            priority=index % 4,
            created_at=f"2026-08-10T00:{index:02d}:00Z",
            metadata={"full_tool_result": "SECRET-HEAVY-ATOM-MAP"},
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
    # revisions 是存储层并发控制的内部状态，阶段 3 起不再投影给模型
    assert "revisions" not in text
    assert '"process": 4' not in text
    assert "missing_endpoint_evidence" in text
    assert "SECRET-HEAVY-ATOM-MAP" not in text


def test_projection_prompt_text_carries_mode_banner_and_discipline():
    """投影头部必须明确告诉 agent 当前模式与编排纪律（SOP / Supervisor 拍板）。"""
    api = _load_completion_api()
    snapshot = api["GraphSnapshot"](
        bundle=api["GraphBundle"](
            process_graph_id="dag_process",
            delivery_graph_id="dag_delivery",
            revisions={"process": 0, "delivery": 0},
        ),
        process=api["GraphData"](graph_id="dag_process", graph_kind="process", revision=0),
        delivery=api["GraphData"](graph_id="dag_delivery", graph_kind="delivery", revision=0),
    )

    guided = api["build_projection"](
        snapshot, mode="dag_guided", contract=api["CoverageContract"].mechanism_default()
    ).to_prompt_text()
    assert "当前编排模式: dag_guided" in guided
    assert "Supervisor 会被自动唤醒" in guided
    assert "status=ready" in guided
    assert "SOP" in guided
    assert "delivery_report" in guided

    record = api["build_projection"](
        snapshot, mode="dag_record", contract=api["CoverageContract"].mechanism_default()
    ).to_prompt_text()
    assert "当前编排模式: dag_record" in record
    assert "Supervisor 不在线" in record
    # record 模式子 agent 的自管理职责：回报指派节点、补挂证据带 role
    assert "assignee" in record
    assert "evidence_role" in record
    assert "拍板" not in record


def test_superseded_process_dependency_no_longer_blocks_frontier():
    api = _load_completion_api()
    predecessor = api["PlannedNode"](
        node_id="old-scan",
        label="obsolete scan",
        status="failed",
    )
    replacement = api["PlannedNode"](
        node_id="new-neb",
        label="replacement NEB",
        status="ready",
        priority=10,
    )
    dependency = api["DependencyEdge"](
        edge_id="old-scan-before-neb",
        source_node_id="old-scan",
        target_node_id="new-neb",
        status="superseded",
        reason="scan coordinate was wrong",
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


def test_assigned_to_me_filters_open_nodes_for_actor():
    api = _load_completion_api()
    nodes = [
        api["PlannedNode"](
            node_id="mine-ready",
            label="mine ready",
            status="ready",
            assignee="a-4",
        ),
        api["PlannedNode"](
            node_id="mine-running",
            label="mine running",
            status="running",
            assignee="a-4",
        ),
        api["PlannedNode"](
            node_id="mine-done",
            label="mine done",
            status="succeeded",
            assignee="a-4",
        ),
        api["PlannedNode"](
            node_id="theirs",
            label="theirs",
            status="ready",
            assignee="a-6",
        ),
    ]
    process = api["GraphData"](
        graph_id="dag_process",
        graph_kind="process",
        revision=1,
        nodes=nodes,
        edges=[],
    )
    delivery = _delivery(api, [], [])
    snapshot = api["GraphSnapshot"](
        bundle=api["GraphBundle"](
            process_graph_id="dag_process",
            delivery_graph_id="dag_delivery",
            revisions={"process": 1, "delivery": 1},
        ),
        process=process,
        delivery=delivery,
    )

    projection = api["build_projection"](
        snapshot,
        mode="dag_guided",
        contract=api["CoverageContract"].mechanism_default(),
        actor_id="a-4",
    )
    assert [item["node_id"] for item in projection.assigned_to_me] == ["mine-ready", "mine-running"]

    anonymous = api["build_projection"](
        snapshot,
        mode="dag_guided",
        contract=api["CoverageContract"].mechanism_default(),
    )
    assert anonymous.assigned_to_me == []
