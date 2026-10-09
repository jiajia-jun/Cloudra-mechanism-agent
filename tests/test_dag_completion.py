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
        "ElementaryStepEdge": models.ElementaryStepEdge,
        "OccurrenceNode": models.OccurrenceNode,
        "GraphBundle": models.GraphBundle,
        "GraphData": models.GraphData,
        "GraphSnapshot": models.GraphSnapshot,
        "StageState": models.StageState,
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

    report = api["evaluate_delivery"](delivery, api["CoverageContract"].mechanism_default())

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

    report = api["evaluate_delivery"](delivery, api["CoverageContract"].mechanism_default())

    assert not report.complete
    assert "missing_endpoint_evidence" in {gap.code for gap in report.unresolved}


def test_rejected_branch_is_an_open_gap_even_with_a_reason():
    """D10：rejected 不是处置——带理由也是开放缺口（只能重绑或显式
    skip-with-reason 退出）；inconclusive（skip 的等价物）带理由才算处置。"""
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
    skipped_equivalent = _delivery(
        api,
        ["structure_supported", "structure_supported"],
        ["inconclusive"],
        edge_payloads=[{"reason": "optimization returns to reactant minimum"}],
    )
    contract = api["CoverageContract"].mechanism_default()

    no_reason_report = api["evaluate_delivery"](without_reason, contract)
    reasoned_report = api["evaluate_delivery"](with_reason, contract)
    skipped_report = api["evaluate_delivery"](skipped_equivalent, contract)

    assert not no_reason_report.complete
    assert not reasoned_report.complete
    rejected_gap = next(gap for gap in reasoned_report.unresolved if gap.code == "branch_rejected")
    assert "optimization returns to reactant minimum" in rejected_gap.detail
    assert skipped_report.complete


def test_disposed_branch_does_not_undermine_supported_intermediates():
    """带 reason 的 inconclusive 边是已处置的竞争分支（skip 等价物），不是
    claimed step：claimed 中间体满足结构证据、竞争分支已显式处置，按设计即
    complete；该边不会计入 unresolved，也不能充当任何 claimed step 的端点证据。"""
    api = _load_completion_api()
    delivery = _delivery(
        api,
        ["structure_supported", "structure_supported"],
        ["inconclusive"],
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
    contract = api["CoverageContract"].mechanism_default(waivers=[waiver])

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


def _staged_delivery(api, node_stages, edge_stages):
    """阶段契约直接声明在元素上（evidence_level 保持 proposed，不走旧等级路径）。"""
    nodes = [
        api["OccurrenceNode"](
            node_id=f"i{index}",
            label=f"intermediate {index}",
            role="intermediate",
            stages=stages,
        )
        for index, stages in enumerate(node_stages)
    ]
    edges = [
        api["ElementaryStepEdge"](
            edge_id=f"e{index}",
            source_node_id=nodes[index].node_id,
            target_node_id=nodes[index + 1].node_id,
            label=f"step {index}",
            stages=stages,
        )
        for index, stages in enumerate(edge_stages)
    ]
    return api["GraphData"](
        graph_id="dag_delivery",
        graph_kind="delivery",
        revision=1,
        nodes=nodes,
        edges=edges,
    )


def _supported_geometry(api):
    return [api["StageState"](kind="geometry", status="supported")]


def test_projection_is_bounded_deterministic_and_contains_no_evidence_bodies():
    """Phase 4：投影 = delivery 缺口 + 待复核调用 + 近期变更；无 frontier/
    blockers/assigned_to_me，且不携带证据正文。"""
    api = _load_completion_api()
    delivery = _delivery(
        api,
        ["structure_supported", "structure_supported"],
        ["saddle_supported"],
        edge_payloads=[{"metadata": {"full_tool_result": "SECRET-HEAVY-ATOM-MAP"}}],
    )
    snapshot = api["GraphSnapshot"](
        bundle=api["GraphBundle"](
            process_graph_id="dag_process",
            delivery_graph_id="dag_delivery",
            revisions={"process": 0, "delivery": 1},
        ),
        process=api["GraphData"](graph_id="dag_process", graph_kind="process", revision=0),
        delivery=delivery,
    )
    history = [{"mutation_id": f"mut-{index}", "actor": "harness", "accepted": True} for index in range(15)]
    reviews = [
        {
            "review_id": f"rev-{index}",
            "tool_name": "log_parser",
            "is_success": True,
            "caller": "a-4",
        }
        for index in range(20)
    ]

    projection = api["build_projection"](
        snapshot,
        mode="dag_guided",
        contract=api["CoverageContract"].mechanism_default(),
        history=history,
        pending_reviews=reviews,
    )
    text = projection.to_prompt_text()

    assert len(projection.recent_mutations) == 8
    assert len(projection.pending_reviews) == 12
    assert projection.delivery_gaps
    assert "dag_guided" in text
    # revisions 是存储层并发控制的内部状态，不投影给模型
    assert "revisions" not in text
    assert "missing_endpoint_evidence" in text
    assert "rev-0" in text
    assert "SECRET-HEAVY-ATOM-MAP" not in text


def test_projection_prompt_text_carries_mode_banner_and_discipline():
    """投影头部必须明确告诉 agent 当前模式与编排纪律（提案先行 / 复核绑定）。"""
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
    assert "Current orchestration mode: dag_guided" in guided
    assert "dag_propose_mechanism" in guided
    assert "no frontier" in guided
    assert "dag_review_call" in guided
    assert "delivery_report" in guided

    follower = api["build_projection"](
        snapshot, mode="dag_guided", contract=api["CoverageContract"].mechanism_default()
    ).to_prompt_text(actor_id="a-4")
    assert "sub-agent" in follower
    assert "do not maintain the graph" in follower

    record = api["build_projection"](
        snapshot, mode="dag_record", contract=api["CoverageContract"].mechanism_default()
    ).to_prompt_text()
    assert "Current orchestration mode: dag_record" in record
    assert "Supervisor is offline" in record
    assert "dag_bind_evidence" in record
    assert "stage_kind" in record


def test_supported_and_reasoned_skipped_stages_complete_coverage():
    """stage 驱动覆盖：必需阶段全部 supported 或带理由 skipped ⇒ complete。"""
    api = _load_completion_api()
    StageState = api["StageState"]
    delivery = _staged_delivery(
        api,
        node_stages=[_supported_geometry(api), _supported_geometry(api)],
        edge_stages=[
            [
                StageState(
                    kind="ts_opt",
                    status="skipped",
                    reason="TS search collapsed back to the reactant minimum",
                ),
                StageState(
                    kind="frequency",
                    status="skipped",
                    reason="no stationary point left to confirm",
                ),
            ]
        ],
    )

    report = api["evaluate_delivery"](delivery, api["CoverageContract"].mechanism_default())

    assert report.complete
    assert report.unresolved == []
    assert report.inconclusive == []


def test_all_required_stages_supported_is_complete():
    api = _load_completion_api()
    StageState = api["StageState"]
    delivery = _staged_delivery(
        api,
        node_stages=[_supported_geometry(api), _supported_geometry(api)],
        edge_stages=[
            [
                StageState(kind=kind, status="supported")
                for kind in (
                    "ts_opt",
                    "frequency",
                    "short_irc",
                    "endpoint_a",
                    "endpoint_b",
                    "direction",
                    "identity",
                )
            ]
        ],
    )

    report = api["evaluate_delivery"](delivery, api["CoverageContract"].mechanism_default())

    assert report.complete
    assert "elementary_step_endpoint_supported" in {gate.code for gate in report.satisfied}


def test_required_pending_stage_blocks_completion():
    api = _load_completion_api()
    StageState = api["StageState"]
    delivery = _staged_delivery(
        api,
        node_stages=[_supported_geometry(api), _supported_geometry(api)],
        edge_stages=[
            [
                StageState(kind="ts_opt", status="supported"),
                StageState(kind="frequency", status="pending"),
            ]
        ],
    )

    report = api["evaluate_delivery"](delivery, api["CoverageContract"].mechanism_default())

    assert not report.complete
    assert "missing_stage_evidence" in {gap.code for gap in report.unresolved}


@pytest.mark.parametrize("status", ["skipped", "rejected"])
def test_stage_disposition_without_reason_stays_open_even_when_waived(status):
    """D9/D10：无理由的 skipped（missing_stage_reason）不可豁免——匹配的
    USER waiver 也不能让它计入完成；rejected 永远是开放缺口（stage_rejected），
    与豁免无关。"""
    api = _load_completion_api()
    StageState = api["StageState"]
    delivery = _staged_delivery(
        api,
        node_stages=[_supported_geometry(api), _supported_geometry(api)],
        edge_stages=[[StageState(kind="ts_opt", status=status, reason="")]],
    )
    waiver = api["CoverageWaiver"](
        gate_code="missing_stage_reason",
        target_type="edge",
        target_id="e0",
        user_id="chemist",
        session_id="s1",
        rationale="accept the unreasoned disposition for this exploratory run",
    )
    contract = api["CoverageContract"].mechanism_default(waivers=[waiver])

    report = api["evaluate_delivery"](delivery, contract)

    assert not report.complete
    assert report.waived == []
    if status == "skipped":
        assert "missing_stage_reason" in {gap.code for gap in report.inconclusive}
    else:
        assert "stage_rejected" in {gap.code for gap in report.unresolved}


@pytest.mark.parametrize("status", ["skipped", "rejected"])
def test_stage_disposition_without_reason_unwaived_is_not_complete(status):
    """回归守护：无豁免时，无理由的 skipped 与任何 rejected（带不带理由）
    都不计入完成（D10：rejected 是开放缺口，不是处置）。"""
    api = _load_completion_api()
    StageState = api["StageState"]
    delivery = _staged_delivery(
        api,
        node_stages=[_supported_geometry(api), _supported_geometry(api)],
        edge_stages=[[StageState(kind="ts_opt", status=status, reason="  ")]],
    )

    report = api["evaluate_delivery"](delivery, api["CoverageContract"].mechanism_default())

    assert not report.complete
    if status == "skipped":
        assert "missing_stage_reason" in {gap.code for gap in report.inconclusive}
    else:
        assert "stage_rejected" in {gap.code for gap in report.unresolved}


def test_rejected_stage_with_reason_and_pending_stages_is_incomplete():
    """prj_d6212be8a2934e80 回归：Supervisor 否决（rejected+理由）且其余必需
    阶段仍 pending 的边必须评估为 INCOMPLETE——否决不再是终态处置。"""
    api = _load_completion_api()
    StageState = api["StageState"]
    delivery = _staged_delivery(
        api,
        node_stages=[_supported_geometry(api), _supported_geometry(api)],
        edge_stages=[
            [
                StageState(
                    kind="ts_opt",
                    status="rejected",
                    reason="the imaginary frequency does not belong to the target TS",
                ),
                StageState(kind="frequency", status="pending"),
                StageState(kind="short_irc", status="pending"),
            ]
        ],
    )

    report = api["evaluate_delivery"](delivery, api["CoverageContract"].mechanism_default())

    assert not report.complete
    rejected = next(gap for gap in report.unresolved if gap.code == "stage_rejected")
    assert "does not belong to the target TS" in rejected.detail
    assert "missing_stage_evidence" in {gap.code for gap in report.unresolved}


def test_contract_thermochemistry_applies_to_disposed_elements():
    """f2 回归：契约级检查（require_thermochemistry）对每个元素生效，
    不因所有必需阶段都已 skip-with-reason 而跳过。"""
    api = _load_completion_api()
    StageState = api["StageState"]
    delivery = _staged_delivery(
        api,
        node_stages=[_supported_geometry(api), _supported_geometry(api)],
        edge_stages=[
            [
                StageState(kind="ts_opt", status="skipped", reason="branch abandoned"),
                StageState(kind="frequency", status="skipped", reason="nothing to confirm"),
            ]
        ],
    )

    report = api["evaluate_delivery"](
        delivery,
        api["CoverageContract"].mechanism_default(require_thermochemistry=True),
    )

    assert not report.complete
    assert "missing_thermochemistry" in {gap.code for gap in report.unresolved}


def test_non_required_pending_stage_never_blocks_coverage():
    api = _load_completion_api()
    StageState = api["StageState"]
    delivery = _staged_delivery(
        api,
        node_stages=[_supported_geometry(api), _supported_geometry(api)],
        edge_stages=[
            [
                StageState(kind="ts_opt", status="supported"),
                StageState(kind="thermochemistry", status="pending", required=False),
            ]
        ],
    )

    report = api["evaluate_delivery"](delivery, api["CoverageContract"].mechanism_default())

    assert report.complete
    assert report.unresolved == []


def test_not_applicable_with_reason_counts_as_complete():
    """not_applicable（带理由）计入完成，且记独立的 stage_not_applicable code
    与 skipped 的 branch_disposed 区分。"""
    api = _load_completion_api()
    StageState = api["StageState"]
    # 无能垒步：ts_opt/frequency/short_irc 槽位不成立，endpoint 与 identity 仍算
    delivery = _staged_delivery(
        api,
        node_stages=[_supported_geometry(api), _supported_geometry(api)],
        edge_stages=[
            [
                StageState(
                    kind="ts_opt",
                    status="not_applicable",
                    reason="barrierless association, no first-order saddle on this PES",
                ),
                StageState(
                    kind="frequency",
                    status="not_applicable",
                    reason="no TS to confirm",
                ),
                StageState(
                    kind="short_irc",
                    status="not_applicable",
                    reason="no saddle to launch IRC from",
                ),
                StageState(kind="endpoint_a", status="supported"),
                StageState(kind="endpoint_b", status="supported"),
                StageState(kind="direction", status="supported"),
                StageState(kind="identity", status="supported"),
            ]
        ],
    )

    report = api["evaluate_delivery"](delivery, api["CoverageContract"].mechanism_default())

    assert report.complete
    assert report.unresolved == []
    assert "stage_not_applicable" in {gate.code for gate in report.satisfied}
    assert "branch_disposed" not in {gate.code for gate in report.satisfied}


def test_not_applicable_without_reason_is_not_waivable():
    """无理由的 not_applicable 记 missing_stage_reason，且 USER waiver 不能豁免。"""
    api = _load_completion_api()
    StageState = api["StageState"]
    delivery = _staged_delivery(
        api,
        node_stages=[_supported_geometry(api), _supported_geometry(api)],
        edge_stages=[[StageState(kind="ts_opt", status="not_applicable", reason="  ")]],
    )
    waiver = api["CoverageWaiver"](
        gate_code="missing_stage_reason",
        target_type="edge",
        target_id="e0",
        user_id="chemist",
        session_id="s1",
        rationale="trying to excuse a missing reason",
    )

    plain = api["evaluate_delivery"](delivery, api["CoverageContract"].mechanism_default())
    waived = api["evaluate_delivery"](delivery, api["CoverageContract"].mechanism_default(waivers=[waiver]))

    assert not plain.complete
    assert not waived.complete
    assert "missing_stage_reason" in {gap.code for gap in plain.inconclusive}


def test_not_applicable_does_not_block_stage_order_or_derive():
    """顺序守卫把 not_applicable 视为已处置的前置阶段；derive 将其视为已满足。"""
    api = _load_completion_api()
    from cloudra.dag.engine import apply_stage_verdict
    from cloudra.dag.models import GraphRef, StageKind, derive_evidence_level

    StageState = api["StageState"]
    stages = [
        StageState(kind="ts_opt", status="not_applicable", reason="barrierless"),
        StageState(kind="frequency", status="pending"),
        StageState(kind="identity", status="pending"),
    ]
    ref = GraphRef(ref_type="tool_result", ref_id="x")
    bound = apply_stage_verdict(
        stages,
        stage_kind=StageKind.FREQUENCY,
        verdict="agree",
        ref=ref,
        tool_succeeded=True,
    )
    assert bound[1].status.value == "supported"

    derived = derive_evidence_level(
        [
            StageState(kind="ts_opt", status="not_applicable", reason="barrierless"),
            StageState(kind="frequency", status="not_applicable", reason="no TS"),
            StageState(kind="short_irc", status="supported"),
            StageState(kind="endpoint_a", status="supported"),
            StageState(kind="endpoint_b", status="supported"),
            StageState(kind="direction", status="supported"),
            StageState(kind="identity", status="supported"),
        ],
        is_edge=True,
    )
    assert derived == "endpoint_supported"


def test_status_update_does_not_override_pending_stages():
    """只更新节点/边的 status 不盖过 pending 阶段：带 stage 契约的元素以阶段
    为准（模型不能靠写 status='supported' 绕过缺失的阶段证据）。"""
    api = _load_completion_api()
    StageState = api["StageState"]
    node = api["OccurrenceNode"](
        node_id="n0",
        label="intermediate 0",
        role="intermediate",
        status="supported",
        stages=[StageState(kind="geometry", status="pending")],
    )
    node2 = api["OccurrenceNode"](
        node_id="n1",
        label="intermediate 1",
        role="intermediate",
        evidence_level="structure_supported",
    )
    edge = api["ElementaryStepEdge"](
        edge_id="e0",
        source_node_id="n0",
        target_node_id="n1",
        label="step 0",
        status="supported",
        stages=[StageState(kind="ts_opt", status="pending")],
    )
    delivery = api["GraphData"](
        graph_id="dag_delivery",
        graph_kind="delivery",
        revision=1,
        nodes=[node, node2],
        edges=[edge],
    )

    report = api["evaluate_delivery"](delivery, api["CoverageContract"].mechanism_default())

    assert not report.complete
    assert "missing_stage_evidence" in {g.code for g in report.unresolved}


def test_not_applicable_verdict_requires_reason():
    """apply_stage_verdict 的 not_applicable verdict 与 skip/disagree 一样 reason 必填。"""
    api = _load_completion_api()
    from cloudra.dag.engine import apply_stage_verdict
    from cloudra.dag.models import StageKind

    StageState = api["StageState"]
    stages = [StageState(kind="ts_opt", status="pending")]

    with pytest.raises(Exception) as excinfo:
        apply_stage_verdict(
            stages,
            stage_kind=StageKind.TS_OPT,
            verdict="not_applicable",
            reason="   ",
        )
    assert getattr(excinfo.value, "code", None) == "reason_required"


def test_empty_frequencies_is_unverified_minimum():
    from cloudra.dag.evidence_ingest import validate_species_minimum

    res1 = validate_species_minimum(None, imaginary_freqs=[])
    assert not res1.verified
    assert not res1.is_valid

    res2 = validate_species_minimum([], imaginary_freqs=[])
    assert not res2.verified
    assert not res2.is_valid

    res3 = validate_species_minimum([], imaginary_freqs=None)
    assert not res3.verified
    assert not res3.is_valid

    res4 = validate_species_minimum([100.0, 200.0], imaginary_freqs=[])
    assert res4.verified
    assert res4.is_valid


def test_element_without_stages_status_supported_cannot_bypass_evidence():
    api = _load_completion_api()
    node0 = api["OccurrenceNode"](
        node_id="n0",
        label="int 0",
        role="intermediate",
        evidence_level="proposed",
        status="supported",
    )
    node1 = api["OccurrenceNode"](
        node_id="n1",
        label="int 1",
        role="intermediate",
        evidence_level="proposed",
        status="supported",
    )
    edge = api["ElementaryStepEdge"](
        edge_id="e0",
        source_node_id="n0",
        target_node_id="n1",
        label="step 0",
        evidence_level="proposed",
        status="supported",
    )
    delivery = api["GraphData"](
        graph_id="dag_delivery",
        graph_kind="delivery",
        revision=1,
        nodes=[node0, node1],
        edges=[edge],
    )

    report = api["evaluate_delivery"](delivery, api["CoverageContract"].mechanism_default())

    assert not report.complete
    unresolved_codes = {g.code for g in report.unresolved}
    assert "missing_intermediate_structure" in unresolved_codes
    assert "missing_endpoint_evidence" in unresolved_codes


def test_unstaged_supported_level_is_not_endpoint_coverage():
    """``supported`` 不得与 endpoint_supported 同级——否则无 stages 旧边
    只交一份 TS 频率就会被当成端点覆盖。"""
    api = _load_completion_api()
    node0 = api["OccurrenceNode"](
        node_id="n0",
        label="int 0",
        role="intermediate",
        evidence_level="structure_supported",
        status="supported",
    )
    node1 = api["OccurrenceNode"](
        node_id="n1",
        label="int 1",
        role="intermediate",
        evidence_level="structure_supported",
        status="supported",
    )
    edge = api["ElementaryStepEdge"](
        edge_id="e0",
        source_node_id="n0",
        target_node_id="n1",
        label="step 0",
        evidence_level="supported",
        status="supported",
    )
    delivery = api["GraphData"](
        graph_id="dag_delivery",
        graph_kind="delivery",
        revision=1,
        nodes=[node0, node1],
        edges=[edge],
    )
    report = api["evaluate_delivery"](delivery, api["CoverageContract"].mechanism_default())
    assert not report.complete
    assert "missing_endpoint_evidence" in {g.code for g in report.unresolved}
