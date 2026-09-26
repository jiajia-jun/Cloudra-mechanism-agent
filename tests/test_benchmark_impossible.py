"""impossible 档新语义（accessible=false 交付协议）+ accuracy 逐边能垒 /
性质锚点 / hard 定性选择性的测试。

拒答路线（refusal.py/impossible.py、expected_outcome/pair_id/impossible_case
特判）已删除：I 题走标准 composite——正确交付 = 同构图
+ 不可达元素标 accessible=false（图分满分、自洽豁免、accuracy 不可达边记 0.0，
final = 0.1·图 + 0.3·自洽）；硬算（不可达元素标 accessible=true）被图分的
标志一致性闸门按代价 1.0 倒扣。

无 LLM、无网络；评分路径是纯结构化 JSON/文件取证，不需要可选依赖。
测试替身（backend 等）签名带 **_kwargs，防接口加参后变红。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cloudra.benchmark.accuracy import (
    score_accuracy,
    score_qualitative_selectivity,
)
from cloudra.benchmark.barrier_evidence import BarrierEvidence
from cloudra.benchmark.runner import BenchmarkRunner
from cloudra.benchmark.schema import (
    AccuracyRubric,
    GoldMechanismGraph,
    GoldSpec,
    MechanismEdge,
    MechanismNode,
    NodeRole,
    PromptSpec,
    SelectivityReference,
    SystemSpec,
    TaskSpec,
    Tier,
)

FIXTURES = Path(__file__).parent / "fixtures"


def _graph_with_node_properties(props: dict) -> GoldMechanismGraph:
    return GoldMechanismGraph(
        nodes=[
            MechanismNode(id="R", role=NodeRole.REACTANT, smiles=["N#N"], properties=props)
        ]
    )


def _gold_properties(props: dict) -> GoldSpec:
    """gold 侧性质参考答案（GoldSpec.reference_properties）。"""
    return GoldSpec(
        mechanism_graph=GoldMechanismGraph(nodes=[]), reference_properties=props
    )


# --- accuracy：逐边能垒门禁（无参考边直通 / 有参考边缺证据记 0） ---


def test_accuracy_no_reference_edge_not_scored():
    """gold 机理图没有任何边 -> accuracy 不评分（final_score=1.0 + 注明）。"""
    gold = GoldSpec(mechanism_graph=GoldMechanismGraph(nodes=[]))
    rep = score_accuracy(evidence=BarrierEvidence(), gold=gold, rubric=AccuracyRubric())
    assert rep.final_score == 1.0
    assert any("carries no edges" in n for n in rep.notes)


def test_accuracy_accessible_edge_without_reference_scores_one():
    """无参考值但有效可达的 gold 边 -> 记 1.0（可算而标答未给参考值）。"""
    gold = GoldSpec(
        mechanism_graph=GoldMechanismGraph(
            nodes=[
                MechanismNode(id="R", role=NodeRole.REACTANT, smiles=["N#N"]),
                MechanismNode(id="P", role=NodeRole.PRODUCT, smiles=["N", "N"]),
            ],
            edges=[MechanismEdge.model_validate({"id": "E1", "from": "R", "to": "P"})],
        )
    )
    rep = score_accuracy(evidence=BarrierEvidence(), gold=gold, rubric=AccuracyRubric())
    assert rep.edge_scores["E1"] == 1.0
    assert rep.final_score == 1.0
    assert any("carries no reference barrier" in n for n in rep.notes)


def test_accuracy_edge_via_inaccessible_ts_scores_zero():
    """有效可达性传导：gold 把不可达标在 TS 节点上（边从不标）→ 经由它的边
    有效不可达，无参考边规则记 0.0；结构 0 分不被 max_penalty_fraction 封顶
    救回（I 题满分 = 图 + 自洽 = 0.4 的 accuracy 侧来源）。"""
    gold = GoldSpec(
        mechanism_graph=GoldMechanismGraph(
            nodes=[
                MechanismNode(id="R", role=NodeRole.REACTANT, smiles=["N#N"]),
                MechanismNode(
                    id="TS", role=NodeRole.TRANSITION_STATE, smiles=[], accessible=False
                ),
                MechanismNode(id="P", role=NodeRole.PRODUCT, smiles=["N", "N"]),
            ],
            edges=[
                MechanismEdge.model_validate(
                    {"id": "E1", "from": "R", "to": "P", "via": "TS"}
                )
            ],
        )
    )
    rep = score_accuracy(evidence=BarrierEvidence(), gold=gold, rubric=AccuracyRubric())
    assert rep.edge_scores["E1"] == 0.0
    assert rep.final_score == 0.0
    assert not rep.fail_loud
    assert any("effectively inaccessible" in n for n in rep.notes)


def test_accuracy_edge_without_via_ignores_endpoint_flags():
    """via 为空的边不做端点检查：端点物种标 accessible=false 不影响边的有效
    可达性（IE2 形制——不可达的是产物态本身，边只是状态间连线）。"""
    gold = GoldSpec(
        mechanism_graph=GoldMechanismGraph(
            nodes=[
                MechanismNode(id="R", role=NodeRole.REACTANT, smiles=["N#N"]),
                MechanismNode(
                    id="P", role=NodeRole.PRODUCT, smiles=["[N]", "[N]"], accessible=False
                ),
            ],
            edges=[MechanismEdge.model_validate({"id": "E1", "from": "R", "to": "P"})],
        )
    )
    rep = score_accuracy(evidence=BarrierEvidence(), gold=gold, rubric=AccuracyRubric())
    assert rep.edge_scores["E1"] == 1.0
    assert rep.final_score == 1.0


def test_accuracy_reference_edge_without_evidence_scored_zero():
    """gold 参考边找不到对应交付步 -> 该边 fail-loud 0 分。"""
    gold = GoldSpec(
        mechanism_graph=GoldMechanismGraph(
            nodes=[MechanismNode(id="R", role=NodeRole.REACTANT, smiles=["N#N"])],
            edges=[
                MechanismEdge.model_validate(
                    {"id": "E1", "from": "R", "to": "R", "barrier_kcal_mol": 27.5}
                )
            ],
        )
    )
    rep = score_accuracy(evidence=BarrierEvidence(), gold=gold, rubric=AccuracyRubric())
    assert rep.final_score == 0.0
    assert rep.fail_loud
    assert any("no delivered step matches its endpoint species" in n for n in rep.notes)


# --- accuracy：性质锚点 ---


def test_property_anchor_numeric_gaussian():
    gold = _gold_properties({"bond_length_angstrom": 1.098})
    good = score_accuracy(
        evidence=BarrierEvidence(),
        gold=gold,
        rubric=AccuracyRubric(),
        delivered_graph=_graph_with_node_properties({"bond_length_angstrom": 1.10}),
    )
    assert good.property_scores["bond_length_angstrom"] == pytest.approx(0.995, abs=0.005)
    assert good.final_score == pytest.approx(0.995, abs=0.005)

    far = score_accuracy(
        evidence=BarrierEvidence(),
        gold=gold,
        rubric=AccuracyRubric(),
        delivered_graph=_graph_with_node_properties({"bond_length_angstrom": 1.30}),
    )
    assert far.final_score < 0.01


def test_property_anchor_string_exact_match():
    gold = _gold_properties({"state_ordering": "triplet below singlet"})
    match = score_accuracy(
        evidence=BarrierEvidence(),
        gold=gold,
        rubric=AccuracyRubric(),
        delivered_graph=_graph_with_node_properties(
            {"state_ordering": "  Triplet BELOW singlet "}
        ),
    )
    assert match.final_score == 1.0  # 规范化（小写+去空白）后精确相等
    mismatch = score_accuracy(
        evidence=BarrierEvidence(),
        gold=gold,
        rubric=AccuracyRubric(),
        delivered_graph=_graph_with_node_properties(
            {"state_ordering": "singlet below triplet"}
        ),
    )
    assert mismatch.final_score == 0.0


def test_property_anchor_multi_key_mean_and_missing():
    gold = _gold_properties(
        {
            "bond_length_angstrom": 1.098,
            "harmonic_frequency_cm-1": 2359.0,
        }
    )
    rep = score_accuracy(
        evidence=BarrierEvidence(),
        gold=gold,
        rubric=AccuracyRubric(),
        delivered_graph=_graph_with_node_properties({"bond_length_angstrom": 1.098}),
    )
    # 一键满分、一键缺失记 0 -> 均值 0.5
    assert rep.final_score == pytest.approx(0.5)
    assert rep.property_scores["harmonic_frequency_cm-1"] == 0.0
    assert any("not declared on any species node" in n for n in rep.notes)


def test_property_anchor_no_delivered_graph_scores_zero():
    gold = _gold_properties({"bond_length_angstrom": 1.098})
    rep = score_accuracy(
        evidence=BarrierEvidence(), gold=gold, rubric=AccuracyRubric(),
        delivered_graph=None,
    )
    assert rep.final_score == 0.0
    assert any("no delivered graph" in n for n in rep.notes)


def test_property_sigma_table_fail_loud():
    """表外数值性质键：fail-loud 抛错，逼显式登记 σ（不静默兜底）。"""
    gold = _gold_properties({"mystery_property": 1.0})
    with pytest.raises(ValueError, match="no sigma registered"):
        score_accuracy(
            evidence=BarrierEvidence(),
            gold=gold,
            rubric=AccuracyRubric(),
            delivered_graph=_graph_with_node_properties({"mystery_property": 1.0}),
        )


# --- hard 定性选择性 ---


def _selectivity_delivery(channel: str | None, favored) -> GoldMechanismGraph:
    edge = {"id": "E1", "from": "R", "to": "P"}
    if channel is not None:
        edge["channel"] = channel
    if favored is not None:
        edge["favored"] = favored
    return GoldMechanismGraph(
        nodes=[
            MechanismNode(id="R", role=NodeRole.REACTANT, smiles=["C"]),
            MechanismNode(id="P", role=NodeRole.PRODUCT, smiles=["O"]),
        ],
        edges=[MechanismEdge.model_validate(edge)],
    )


def test_qualitative_selectivity_scoring():
    sel = SelectivityReference(spread_kcal_mol=2.0, favored_channel="chair_ts")
    hit, note = score_qualitative_selectivity(_selectivity_delivery("chair_ts", True), sel)
    assert hit == 1.0 and "matches" in note
    miss, _ = score_qualitative_selectivity(_selectivity_delivery("boat_ts", True), sel)
    assert miss == 0.0
    none_declared, note = score_qualitative_selectivity(_selectivity_delivery("chair_ts", None), sel)
    assert none_declared == 0.0 and "no edge declares" in note
    no_graph, note = score_qualitative_selectivity(None, sel)
    assert no_graph == 0.0 and "no delivered graph" in note


def test_qualitative_selectivity_multiple_favored_is_zero():
    sel = SelectivityReference(favored_channel="chair_ts")
    graph = GoldMechanismGraph(
        nodes=[
            MechanismNode(id="R", role=NodeRole.REACTANT, smiles=["C"]),
            MechanismNode(id="P", role=NodeRole.PRODUCT, smiles=["O"]),
            MechanismNode(id="P2", role=NodeRole.PRODUCT, smiles=["[O-]"]),
        ],
        edges=[
            MechanismEdge.model_validate({"id": "E1", "from": "R", "to": "P", "channel": "chair_ts", "favored": True}),
            MechanismEdge.model_validate({"id": "E2", "from": "R", "to": "P2", "channel": "boat_ts", "favored": True}),
        ],
    )
    score, note = score_qualitative_selectivity(graph, sel)
    assert score == 0.0 and "multiple edges" in note


# --- runner 集成：impossible 档标准 composite + 选择性槽位 ---


def _i_task() -> TaskSpec:
    """IA1 形制的最小 I 题：R →(经不可达 TS)→ P，gold 边无参考能垒。
    rubric 全默认（I 题不再有任何特判）。"""
    graph = GoldMechanismGraph(
        nodes=[
            MechanismNode(id="R", role=NodeRole.REACTANT, smiles=["O"]),
            MechanismNode(
                id="TS", role=NodeRole.TRANSITION_STATE, smiles=[], accessible=False
            ),
            MechanismNode(id="P", role=NodeRole.PRODUCT, smiles=["O"]),
        ],
        edges=[MechanismEdge.model_validate({"id": "E1", "from": "R", "to": "P", "via": "TS"})],
    )
    return TaskSpec(
        task_id="IX1",
        tier=Tier.IMPOSSIBLE,
        prompt=PromptSpec(query="q"),
        system=SystemSpec(reactants=["O"]),
        gold=GoldSpec(mechanism_graph=graph),
    )


def _write_delivery(sandbox: Path, graph: GoldMechanismGraph, **node_overrides) -> None:
    """按 gold 图写出交付 mechanism_graph.json（可按节点 id 覆盖字段），
    并附一份带 smiles 注释的真实 opt+freq 日志作为 R/P（同为水）的绑定 +
    验证极小值证据。"""
    payload = graph.model_dump(mode="json", by_alias=True)
    for node in payload["nodes"]:
        node.update(node_overrides.get(node["id"], {}))
    sandbox.mkdir(parents=True, exist_ok=True)
    (sandbox / "mechanism_graph.json").write_text(json.dumps(payload), encoding="utf-8")
    fixture = (FIXTURES / "gaussian" / "water_opt_freq_g16.out").read_text(
        encoding="utf-8", errors="replace"
    )
    (sandbox / "r_min.log").write_text("smiles: O\n" + fixture, encoding="utf-8")


def test_runner_i_task_correct_delivery_flags_inaccessible(tmp_path):
    """I 题正确交付：同构图 + 不可达 TS 标 accessible=false -> 图分满分
    （标志一致）、自洽豁免（边有效不可达——豁免元素不判、也不触发自洽回捞）、
    accuracy 不可达边记 0.0，final = 0.1·1 + 0.3·1 + 0.6·0 = 0.4。"""
    task = _i_task()
    _write_delivery(tmp_path, task.gold.mechanism_graph)
    res = BenchmarkRunner(tmp_path / "data").score_sandbox(task, tmp_path)
    assert res.graph_score == pytest.approx(1.0), res.notes
    assert res.selfconsistency_passed, res.notes
    assert res.accuracy_score == 0.0, res.notes
    assert res.final_score == pytest.approx(0.4)


def test_runner_i_task_wrongly_solve_flagged_accessible(tmp_path):
    """I 题硬算（把不可达 TS 标 accessible=true）：标志不一致 -> 边按代价 1.0
    倒扣进图分（2/3，该边本就赢不到覆盖，自洽回捞不改变它）；该边不再是有效
    不可达豁免，无一阶鞍点 + IRC 证据 -> 自洽判负；accuracy 不可达边仍 0.0。
    final = 0.1·(2/3) ≈ 0.0667。"""
    task = _i_task()
    _write_delivery(tmp_path, task.gold.mechanism_graph, TS={"accessible": True})
    res = BenchmarkRunner(tmp_path / "data").score_sandbox(task, tmp_path)
    assert res.graph_score == pytest.approx(2 / 3), res.notes
    assert res.selfconsistency_passed is False, res.notes
    assert res.accuracy_score == 0.0, res.notes
    assert res.final_score == pytest.approx(0.1 * 2 / 3, abs=1e-4)


def test_runner_pure_inaccessible_delivery_is_legal(tmp_path):
    """纯不可达交付（全部节点标 accessible=false）是合法交付：不触发零证据
    倒扣；ID2 形制（单参考态节点、无边）-> final = 0.1 + 0.3 + 0.6 = 1.0。"""
    graph = GoldMechanismGraph(
        nodes=[
            MechanismNode(
                id="R", role=NodeRole.REACTANT, smiles=["FOOF"], accessible=False
            )
        ]
    )
    task = TaskSpec(
        task_id="IX2",
        tier=Tier.IMPOSSIBLE,
        prompt=PromptSpec(query="q"),
        system=SystemSpec(reactants=["FOOF"]),
        gold=GoldSpec(mechanism_graph=graph),
    )
    sandbox = tmp_path / "sb"
    sandbox.mkdir()
    (sandbox / "mechanism_graph.json").write_text(
        graph.model_dump_json(by_alias=True), encoding="utf-8"
    )
    res = BenchmarkRunner(tmp_path / "data").score_sandbox(task, sandbox)
    assert not any("penalty applied" in n for n in res.notes), res.notes
    assert res.graph_score == pytest.approx(1.0), res.notes
    assert res.selfconsistency_passed, res.notes
    assert res.final_score == pytest.approx(1.0)


def test_runner_hard_selectivity_slot(tmp_path):
    """hard 题带 favored_channel：选择性分占 accuracy 槽位，不跑能垒门禁。"""
    graph = GoldMechanismGraph(
        nodes=[
            MechanismNode(id="R", role=NodeRole.REACTANT, smiles=["C"]),
            MechanismNode(id="TS", role=NodeRole.TRANSITION_STATE, smiles=[]),
            MechanismNode(id="P", role=NodeRole.PRODUCT, smiles=["O"]),
            MechanismNode(id="P2", role=NodeRole.PRODUCT, smiles=["[O-]"]),
        ],
        edges=[
            MechanismEdge.model_validate({"id": "E1", "from": "R", "to": "P", "via": "TS"}),
            MechanismEdge.model_validate({"id": "E2", "from": "R", "to": "P2", "via": "TS"}),
        ],
    )
    task = TaskSpec(
        task_id="SEL_T",
        tier=Tier.HARD,
        prompt=PromptSpec(query="q"),
        system=SystemSpec(reactants=["C"]),
        gold=GoldSpec(
            mechanism_graph=graph,
            selectivity=SelectivityReference(
                spread_kcal_mol=2.0, favored_channel="chair_ts"
            ),
        ),
    )
    delivery = {
        "nodes": [
            {"id": "R", "role": "reactant", "smiles": ["C"]},
            {"id": "P", "role": "product", "smiles": ["O"]},
            {"id": "P2", "role": "product", "smiles": ["[O-]"]},
        ],
        "edges": [
            {"id": "e1", "from": "R", "to": "P", "channel": "chair_ts", "favored": True},
            {"id": "e2", "from": "R", "to": "P2", "channel": "boat_ts", "favored": False},
        ],
    }
    (tmp_path / "mechanism_graph.json").write_text(json.dumps(delivery), encoding="utf-8")
    res = BenchmarkRunner(tmp_path / "data").score_sandbox(task, tmp_path)
    assert res.accuracy_score == 1.0
    assert any("qualitative selectivity" in n for n in res.notes)

    wrong = tmp_path / "wrong"
    wrong.mkdir()
    delivery["edges"][0]["channel"] = "boat_ts"  # 唯一 favored 边指错通道
    (wrong / "mechanism_graph.json").write_text(json.dumps(delivery), encoding="utf-8")
    res2 = BenchmarkRunner(tmp_path / "data2").score_sandbox(task, wrong)
    assert res2.accuracy_score == 0.0


def test_state_order_anchor_not_leaked_in_query():
    """泄题守卫：任何 impossible 题的 query 不得包含 gold 字符串锚点值
    （state_ordering 的答案顺序）；契约示例必须用占位物种名。"""
    pytest.importorskip("rdkit")
    from cloudra.benchmark import gen_impossible_tasks

    tasks = gen_impossible_tasks.parse_impossible_md(gen_impossible_tasks.DEFAULT_SRC)
    for t in tasks:
        for key, val in t.gold.reference_properties.items():
            if isinstance(val, str) and val:
                assert val not in t.prompt.query, f"{t.task_id} 泄露锚点 {key}={val!r}"
        # 占位示例而不是真实态序
        if "state_ordering" in t.prompt.query:
            assert '"<species A> below <species B>"' in t.prompt.query, t.task_id
            assert "triplet below singlet" not in t.prompt.query, t.task_id


def test_pyrazoline_denitrogenation_moved_to_impossible():
    """NU8 的脱氮边只在 impossible 交付，普通题集不再把它当可算闭壳层边。"""
    pytest.importorskip("rdkit")
    from cloudra.benchmark import gen_impossible_tasks, gen_normal_tasks

    normal = {t.task_id for t in gen_normal_tasks.parse_normal_md(gen_normal_tasks.DEFAULT_SRC)}
    impossible = {
        t.task_id: t
        for t in gen_impossible_tasks.parse_impossible_md(gen_impossible_tasks.DEFAULT_SRC)
    }
    assert "NU8" not in normal
    assert "IB9" in impossible and "SB9" not in impossible
    graph = impossible["IB9"].gold.mechanism_graph
    assert len(graph.edges) == 2
    assert graph.nodes[0].accessible
    assert next(n for n in graph.nodes if n.id == "IB9_TS1").accessible
    assert not next(n for n in graph.nodes if n.id == "IB9_TS2").accessible
