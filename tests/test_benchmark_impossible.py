"""impossible 档算分器 + accuracy 新语义（逐边能垒 / 性质锚点 /
hard 定性选择性）的测试。

无 LLM、无网络；评分路径是纯结构化 JSON/文件取证，不需要可选依赖。
测试替身（backend 等）签名带 **_kwargs，防接口加参后变红。
"""

from __future__ import annotations

import json

import pytest

from cloudra.benchmark.accuracy import (
    score_accuracy,
    score_qualitative_selectivity,
)
from cloudra.benchmark.barrier_evidence import BarrierEvidence
from cloudra.benchmark.impossible import (
    decision_score,
    reason_quality,
)
from cloudra.benchmark.refusal import RunOutcome, classify_refusal_reason
from cloudra.benchmark.runner import BenchmarkRunner
from cloudra.benchmark.schema import (
    AccuracyRubric,
    ExpectedOutcome,
    GoldMechanismGraph,
    GoldSpec,
    ImpossibleCaseRubric,
    IntegrityRubric,
    MechanismEdge,
    MechanismNode,
    NodeRole,
    PromptSpec,
    RefusalDeclaration,
    RubricSpec,
    SelectivityReference,
    SystemSpec,
    TaskSpec,
    Tier,
)


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


# --- 拒答理由分类（refusal.py 结构化 token 识别，无正则） ---


def test_classify_refusal_reason():
    assert classify_refusal_reason("") == "empty"
    assert classify_refusal_reason("   ") == "empty"
    assert (
        classify_refusal_reason(
            "The TS is strongly multireference: static correlation dominates."
        )
        == "electronic_structure"
    )
    assert (
        classify_refusal_reason("Open-shell singlet needs CASSCF") == "electronic_structure"
    )
    assert classify_refusal_reason("I ran out of compute time") == "other"


# --- I 题决策分与理由质量分 ---


def test_decision_score():
    assert decision_score(RunOutcome.REFUSED)[0] == 1.0
    assert decision_score(RunOutcome.ANSWERED)[0] == 0.0
    assert decision_score(RunOutcome.FAILED)[0] == pytest.approx(0.2)


def test_reason_quality():
    electronic = RefusalDeclaration(refused=True, reason="multireference ground state")
    assert reason_quality(electronic)[0] == 1.0
    other = RefusalDeclaration(refused=True, reason="too expensive")
    assert reason_quality(other)[0] == 0.5
    empty = RefusalDeclaration(refused=True, reason="")
    assert reason_quality(empty)[0] == 0.0
    assert reason_quality(None)[0] == 0.0


# --- accuracy：逐边能垒门禁（无参考边直通 / 有参考边缺证据记 0） ---


def test_accuracy_no_reference_edge_not_scored():
    """gold 机理图无可参考边 -> accuracy 直通（final_score=1.0 + 注明）。"""
    gold = GoldSpec(mechanism_graph=GoldMechanismGraph(nodes=[]))
    rep = score_accuracy(evidence=BarrierEvidence(), gold=gold, rubric=AccuracyRubric())
    assert rep.final_score == 1.0
    assert any("no gold edge carries a reference barrier" in n for n in rep.notes)


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
    assert any("no matching step" in n for n in rep.notes)


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


# --- runner 集成：impossible 路由 + 选择性槽位 + verification 直通 ---


def _impossible_task(expected: ExpectedOutcome, task_id: str, pair_id: str) -> TaskSpec:
    impossible = expected is ExpectedOutcome.CORRECT_REFUSAL
    graph = GoldMechanismGraph(
        nodes=[MechanismNode(id="R", role=NodeRole.REACTANT, smiles=["N#N"])]
    )
    return TaskSpec(
        task_id=task_id,
        tier=Tier.IMPOSSIBLE,
        pair_id=pair_id,
        prompt=PromptSpec(query="q"),
        system=SystemSpec(reactants=["N#N"]),
        gold=GoldSpec(mechanism_graph=graph),
        rubric=RubricSpec(
            expected_outcome=expected,
            integrity=IntegrityRubric(
                require_graph_json=not impossible,
                require_evidence_files=not impossible,
            ),
            accuracy=AccuracyRubric(enabled=False),
            impossible_case=(
                ImpossibleCaseRubric(
                    gold_inaccessible_nodes=["R"], wrongly_solve_penalty="high"
                )
                if impossible
                else None
            ),
        ),
    )


def _write_refusal(sandbox, reason: str) -> None:
    sandbox.mkdir(parents=True, exist_ok=True)
    (sandbox / "mechanism_graph.json").write_text(
        json.dumps({"refusal": {"refused": True, "reason": reason}}),
        encoding="utf-8",
    )


def test_runner_i_task_correct_refusal(tmp_path):
    """I 题：结构化拒答 + 电子结构理由 -> 0.7*1 + 0.3*1 = 1.0。"""
    task = _impossible_task(ExpectedOutcome.CORRECT_REFUSAL, "IX1", "SX1")
    _write_refusal(tmp_path, "strong multireference character, needs CASSCF")
    res = BenchmarkRunner(tmp_path / "data").score_sandbox(task, tmp_path)
    assert res.outcome == RunOutcome.REFUSED.value
    assert res.final_score == pytest.approx(1.0)
    assert any("pair_id=SX1" in n for n in res.notes)


def test_runner_i_task_refusal_reason_grading(tmp_path):
    """I 题理由分级：非空未分类 0.85；空理由 0.7。"""
    task = _impossible_task(ExpectedOutcome.CORRECT_REFUSAL, "IX1", "SX1")
    other_dir = tmp_path / "other"
    _write_refusal(other_dir, "I do not want to compute this")
    res = BenchmarkRunner(tmp_path / "d1").score_sandbox(task, other_dir)
    assert res.final_score == pytest.approx(0.7 + 0.3 * 0.5)

    empty_dir = tmp_path / "empty"
    _write_refusal(empty_dir, "")
    res2 = BenchmarkRunner(tmp_path / "d2").score_sandbox(task, empty_dir)
    assert res2.final_score == pytest.approx(0.7)


def test_runner_i_task_answered_is_wrongly_solved(tmp_path):
    """I 题硬算交付机理图 -> 0.0（wrongly_solve）。"""
    task = _impossible_task(ExpectedOutcome.CORRECT_REFUSAL, "IX1", "SX1")
    (tmp_path / "mechanism_graph.json").write_text(
        task.gold.mechanism_graph.model_dump_json(by_alias=True)
    )
    res = BenchmarkRunner(tmp_path / "data").score_sandbox(task, tmp_path)
    assert res.outcome == RunOutcome.ANSWERED.value
    assert res.final_score == 0.0
    assert any("wrongly_solve" in n for n in res.notes)


def test_runner_i_task_no_delivery_is_incomplete(tmp_path):
    """I 题既未拒答也未交付 -> 0.7*0.2 = 0.14（不完整但无害）。"""
    task = _impossible_task(ExpectedOutcome.CORRECT_REFUSAL, "IX1", "SX1")
    empty = tmp_path / "empty"
    empty.mkdir()
    res = BenchmarkRunner(tmp_path / "data").score_sandbox(task, empty)
    assert res.outcome == RunOutcome.FAILED.value
    assert res.final_score == pytest.approx(0.14)


def test_runner_s_task_wrong_refusal_gate(tmp_path):
    """S 题错误拒答：注明 wrongly refused；负分（无证据倒扣）不被闸门放大。"""
    task = _impossible_task(ExpectedOutcome.MECHANISM_FOUND, "SX1", "IX1")
    _write_refusal(tmp_path, "multireference, cannot compute")
    res = BenchmarkRunner(tmp_path / "data").score_sandbox(task, tmp_path)
    assert res.outcome == RunOutcome.REFUSED.value
    assert any("wrongly refused a solvable sibling" in n for n in res.notes)
    assert res.final_score == -1.0  # 无证据倒扣保持原值（闸门只压正分）


def test_runner_s_task_normal_answer_no_gate(tmp_path):
    """S 题正常作答：走标准 composite，不带拒答闸门注记。"""
    task = _impossible_task(ExpectedOutcome.MECHANISM_FOUND, "SX1", "IX1")
    (tmp_path / "mechanism_graph.json").write_text(
        task.gold.mechanism_graph.model_dump_json(by_alias=True)
    )
    (tmp_path / "r.log").write_text("gaussian log\n# smiles: N#N\n")
    res = BenchmarkRunner(tmp_path / "data").score_sandbox(task, tmp_path)
    assert res.outcome == RunOutcome.ANSWERED.value
    assert not any("wrongly refused" in n for n in res.notes)
    assert any("impossible-tier scorer" in n for n in res.notes)


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


# --- sibling 性质锚点回填（gold_properties）与泄题守卫 ---


def test_sibling_property_anchors_backfilled():
    """七个 sibling 性质/态序题已回填 gold 锚点且 accuracy 自动启用；
    数值键的 σ 都能命中 _PROPERTY_SIGMAS（表外 fail-loud 的前置核对）。"""
    pytest.importorskip("rdkit")
    from cloudra.benchmark import gen_impossible_tasks
    from cloudra.benchmark.accuracy import _property_sigma

    tasks = {t.task_id: t for t in gen_impossible_tasks.parse_impossible_md(gen_impossible_tasks.DEFAULT_SRC)}
    anchored = {"SE2", "SD2", "SA9", "SF3", "SG8", "SC3", "SA8"}
    for tid in anchored:
        t = tasks[tid]
        props = t.gold.reference_properties
        assert props, f"{tid} 缺 gold 性质锚点"
        assert t.rubric.accuracy.enabled, f"{tid} 有锚点但 accuracy 未启用"
        for key, val in props.items():
            if not isinstance(val, str):
                _property_sigma(key)  # 表外键在此即抛（fail-loud 前置）
    # 抽查回填值（出处见 registry 注释）
    assert tasks["SE2"].gold.reference_properties == {
        "bond_length_angstrom": 1.0977,
        "harmonic_frequency_cm-1": 2358.57,
    }
    assert tasks["SA8"].gold.reference_properties == {
        "energy_relative_to_reactant_kcal_mol": 90.9,
        "state_ordering": "formic acid below dioxirane",
    }


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


def test_removed_contract_keys_not_in_query():
    """SC3 频率键 / SF3 几何汇总键已从契约移除：query 不再要求这两个键。"""
    pytest.importorskip("rdkit")
    from cloudra.benchmark import gen_impossible_tasks

    tasks = {t.task_id: t for t in gen_impossible_tasks.parse_impossible_md(gen_impossible_tasks.DEFAULT_SRC)}
    assert "`harmonic_frequencies_cm-1`" not in tasks["SC3"].prompt.query
    assert "`principal_geometry_summary`" not in tasks["SF3"].prompt.query
