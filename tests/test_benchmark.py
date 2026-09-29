"""Anchor tests for the benchmark module.

Covers:
- schema round-trip (TaskSpec dump -> validate), including alias keys.
- easy task generation count and field correctness.
- GED cost ordering anchors (identical > similar > far).
- accuracy Gaussian scoring + penalty cap.
- method-policy interception verdicts.
- integrity audit on a synthetic sandbox.

No LLM, no network. networkx is a hard dependency; RDKit is optional — node
costs degrade to exact SMILES set equality without it (anchor orderings still
hold).
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from cloudra.benchmark import gen_easy_tasks, selfconsistency
from cloudra.benchmark.accuracy import score_accuracy
from cloudra.benchmark.graph_similarity import GedConfig, mechanism_similarity
from cloudra.benchmark.integrity import (
    EvidenceFile,
    NodeBinding,
    audit_integrity,
    scan_evidence_files,
)
from cloudra.benchmark.method_policy import (
    check_input_content,
    check_input_files,
    check_method,
    intercept,
)
from cloudra.benchmark.schema import (
    AccuracyRubric,
    BondChangeSet,
    GoldMechanismGraph,
    GoldSpec,
    MechanismEdge,
    MechanismNode,
    MethodPolicy,
    NodeRole,
    SelfConsistencyRubric,
    TaskSpec,
)
from cloudra.benchmark.selfconsistency import audit_self_consistency
from cloudra.tools.core.gaussian_frames import FrameRecord


def _graph(r, p, bc=None, with_ts=True):
    nodes = [
        MechanismNode(id="R", role=NodeRole.REACTANT, smiles=r),
        MechanismNode(id="P", role=NodeRole.PRODUCT, smiles=p),
    ]
    via = None
    if with_ts:
        nodes.insert(1, MechanismNode(id="TS", role=NodeRole.TRANSITION_STATE, smiles=[]))
        via = "TS"
    e = MechanismEdge(id="E", **{"from": "R", "to": "P"}, via=via, bond_changes=bc or BondChangeSet())
    return GoldMechanismGraph(nodes=nodes, edges=[e])


# --- schema / generation ---


def test_easy_generation_count_and_roundtrip(tmp_path):
    tasks = gen_easy_tasks.parse_easy_md(gen_easy_tasks.DEFAULT_SRC)
    assert len(tasks) == 20
    for t in tasks:
        dumped = t.model_dump(mode="json", by_alias=True)
        rt = TaskSpec.model_validate(dumped)
        assert rt.task_id == t.task_id


def test_easy_charge_and_smiles():
    tasks = {t.task_id: t for t in gen_easy_tasks.parse_easy_md(gen_easy_tasks.DEFAULT_SRC)}
    assert tasks["E1"].system.charge == -1
    assert tasks["D1"].system.charge == 0
    assert tasks["D1"].system.reactants == ["C=CC=C", "C=C"]
    # degenerate M-group process: product falls back to reactant
    assert tasks["M1"].system.products == tasks["M1"].system.reactants


def test_easy_barrier_parsing_no_garbage():
    """能垒解析不得抓年份/键长/百分数：无锚点数字题 -> None；
    锚点数字取范围下界/正确抓取；DOI 含括号不得截断（见保留题集合内 DOI 题）。"""
    tasks = {t.task_id: t for t in gen_easy_tasks.parse_easy_md(gen_easy_tasks.DEFAULT_SRC)}

    def _edge_barrier(t):
        return t.gold.mechanism_graph.edges[0].barrier_kcal_mol

    assert _edge_barrier(tasks["M3"]) is not None
    assert _edge_barrier(tasks["D1"]) == 18.83  # 自算：相对反应物络合物的 ΔE‡
    assert _edge_barrier(tasks["E1"]) == 0.88  # 自算：近淹没浅垒（TS 相对离子-偶极络合物）
    for tid, t in tasks.items():
        b = _edge_barrier(t)
        assert b is None or 0.0 <= b <= 200.0, f"{tid} implausible barrier {b}"
        assert t.name.isascii(), f"{tid} name not English: {t.name!r}"
        assert t.system.conditions.isascii()
        # query 允许 ΔE‡ 记号（电子能垒契约句），其余一律 ASCII（挡中文混入）
        assert all(ord(c) < 128 or c in "Δ‡" for c in t.prompt.query), f"{tid} query non-ASCII"
        assert "Determine the mechanism" in t.prompt.query


def test_easy_computed_barriers():
    """二十题回填值来自原始 RC/TS ORCA 能量，题源重生成不可退回文献锚点。"""
    tasks = {t.task_id: t for t in gen_easy_tasks.parse_easy_md(gen_easy_tasks.DEFAULT_SRC)}
    expected = {
        # 第一批（gold_compute/easy_backfill_2026-09-23.md）
        "M3": 5.94, "M14": 9.05, "M15": 14.54, "P2": 26.55,
        "L1": 35.17, "M8": 12.00, "D1": 18.83, "L2": 29.77,
        "G2": 0.87, "P3": 30.23,
        # 第二批（gold_compute/easy_backfill_2026-09-25.md）
        "D3": 14.65, "D4": 11.30, "X1": 40.90, "E1": 0.88,
        "F1": 39.41, "G3": 30.15, "M1": 15.10, "M16": 70.97,
        # 补位题（pilots：gold_compute/campaign/pilots/R4、R9）
        "F4": 16.02, "M17": 44.50,
    }
    for task_id, barrier in expected.items():
        assert tasks[task_id].gold.mechanism_graph.edges[0].barrier_kcal_mol == barrier


def test_task_id_rejects_path_traversal():
    """task_id 会拼进沙箱路径并被整目录删除：必须拒绝路径逃逸字符。"""
    tasks = gen_easy_tasks.parse_easy_md(gen_easy_tasks.DEFAULT_SRC)
    dumped = tasks[0].model_dump(mode="json", by_alias=True)
    dumped["task_id"] = "../escape"
    with pytest.raises(ValidationError):
        TaskSpec.model_validate(dumped)
    dumped["task_id"] = "a/b"
    with pytest.raises(ValidationError):
        TaskSpec.model_validate(dumped)
    dumped["task_id"] = "ok_TASK-1"
    assert TaskSpec.model_validate(dumped).task_id == "ok_TASK-1"


def test_gold_graph_edge_reference_integrity_validator():
    """端点引用完整性：边的 from/to 必须指向已声明节点、via 必须指向
    transition_state 角色节点——违反即 ValidationError（不静默造幽灵节点）。"""
    nodes = [
        MechanismNode(id="R", role=NodeRole.REACTANT, smiles=["C"]),
        MechanismNode(id="TS", role=NodeRole.TRANSITION_STATE, smiles=[]),
        MechanismNode(id="P", role=NodeRole.PRODUCT, smiles=["CC"]),
    ]
    # 合法图照常通过
    GoldMechanismGraph(
        nodes=nodes,
        edges=[MechanismEdge(id="E1", **{"from": "R", "to": "P"}, via="TS")],
    )
    # 悬空 from
    with pytest.raises(ValidationError, match="not a declared node"):
        GoldMechanismGraph(
            nodes=nodes,
            edges=[MechanismEdge(id="E1", **{"from": "GHOST", "to": "P"}, via="TS")],
        )
    # 悬空 to
    with pytest.raises(ValidationError, match="not a declared node"):
        GoldMechanismGraph(
            nodes=nodes,
            edges=[MechanismEdge(id="E1", **{"from": "R", "to": "GHOST"}, via="TS")],
        )
    # via 指向不存在的节点
    with pytest.raises(ValidationError, match="not a declared"):
        GoldMechanismGraph(
            nodes=nodes,
            edges=[MechanismEdge(id="E1", **{"from": "R", "to": "P"}, via="GHOST")],
        )
    # via 指向非 TS 角色节点
    with pytest.raises(ValidationError, match="transition_state"):
        GoldMechanismGraph(
            nodes=nodes,
            edges=[MechanismEdge(id="E1", **{"from": "R", "to": "P"}, via="R")],
        )


def test_edge_effective_accessibility_transduction():
    """有效可达性：边自身 AND 经由的 TS 节点；via 为空的边不做端点检查。"""
    def _g(ts_accessible=True, edge_accessible=True, with_via=True):
        nodes = [
            MechanismNode(id="R", role=NodeRole.REACTANT, smiles=["C"]),
            MechanismNode(id="P", role=NodeRole.PRODUCT, smiles=["CC"]),
        ]
        via = None
        if with_via:
            nodes.insert(1, MechanismNode(
                id="TS", role=NodeRole.TRANSITION_STATE, smiles=[],
                accessible=ts_accessible,
            ))
            via = "TS"
        return GoldMechanismGraph(
            nodes=nodes,
            edges=[MechanismEdge(
                id="E1", **{"from": "R", "to": "P"}, via=via,
                accessible=edge_accessible,
            )],
        )

    g = _g()
    assert g.edge_effectively_accessible(g.edges[0]) is True
    # 经由不可达 TS -> 有效不可达（gold 只在节点上标的情形）
    g = _g(ts_accessible=False)
    assert g.edge_effectively_accessible(g.edges[0]) is False
    # 边自身标 false（交付侧协议允许的形式）
    g = _g(edge_accessible=False)
    assert g.edge_effectively_accessible(g.edges[0]) is False
    # via 为空：不做端点检查，只看边自身
    g = _g(with_via=False)
    assert g.edge_effectively_accessible(g.edges[0]) is True
    g = _g(with_via=False, edge_accessible=False)
    assert g.edge_effectively_accessible(g.edges[0]) is False


def test_easy_query_requires_structured_barrier_declaration():
    """accuracy 只读交付物：query 必须要求把每步能垒声明进交付 JSON，
    不再有"在最终总结里报数"这类散文契约。"""
    tasks = gen_easy_tasks.parse_easy_md(gen_easy_tasks.DEFAULT_SRC)
    for t in tasks:
        assert "as `barrier_kcal_mol` in mechanism_graph.json" in t.prompt.query
        assert "In your final summary you must report" not in t.prompt.query


def test_easy_gold_bond_changes_and_edge_barrier():
    """gold 边必须携带键变化（否则 agent 填了 bond_changes 反而被对称差扣分），
    且索引约定必须与 query 展示的原子映射 SMILES 一致；easy 单步题的整题参考
    能垒逐边承载在该唯一边上。"""
    tasks = {t.task_id: t for t in gen_easy_tasks.parse_easy_md(gen_easy_tasks.DEFAULT_SRC)}
    no_bond_change = {"M1", "M3", "M8", "M14", "M15"}  # 纯构象/翻转步
    for tid, t in tasks.items():
        assert gen_easy_tasks._MAPPED_REACTANTS[tid] in t.prompt.query
        assert "bond_changes" in t.prompt.query
        edge = t.gold.mechanism_graph.edges[0]
        bc = edge.bond_changes
        if tid in no_bond_change:
            assert not bc.break_ and not bc.form, f"{tid} 纯构象/翻转步应为空键变化"
        else:
            assert bc.break_ or bc.form, f"{tid} gold edge missing bond_changes"
        # 逐边权重：分离反应物口径/部分核实题 0.5，其余同底物可核实题 1.0
        downgraded = {"D1", "D3", "D4", "C3", "G2", "G3", "M1"}
        assert edge.weight == (0.5 if tid in downgraded else 1.0), (tid, edge.weight)


# --- runner ---


def test_runner_rerun_starts_from_clean_sandbox(tmp_path):
    """复跑不清空旧目录：新批次拿到全新干净沙箱（无残留污染取证），
    上一批的残留文件原样保留（数据珍贵，框架永不删）。"""
    from cloudra.benchmark.runner import BenchmarkRunner

    tasks = gen_easy_tasks.parse_easy_md(gen_easy_tasks.DEFAULT_SRC)
    r1 = BenchmarkRunner(tmp_path / "bench", batch_id="batch_A")
    sandbox_a = r1.sandbox_for(tasks[0].task_id, "batch_A")
    sandbox_a.mkdir(parents=True)
    (sandbox_a / "stale_evidence.log").write_text("smiles: C=CC=C\n")  # 上一批残留
    r1.run_task(tasks[0])  # 默认 no-op backend

    r2 = BenchmarkRunner(tmp_path / "bench", batch_id="batch_B")
    r2.run_task(tasks[0])
    sandbox_b = r2.sandbox_for(tasks[0].task_id, "batch_B")
    # 新批目录干净：上一批的残留不在其中
    assert not (sandbox_b / "stale_evidence.log").exists()
    # 旧批目录原样保留
    assert (sandbox_a / "stale_evidence.log").exists()


def test_runner_rerun_over_symlink_or_file_sandbox(tmp_path):
    """沙箱路径被 symlink/普通文件占位时 run_task 不传播 OSError：
    单题落失败行，整批继续（清理永远不做，占位也永不强拆）。"""
    from cloudra.benchmark.runner import BenchmarkRunner

    tasks = gen_easy_tasks.parse_easy_md(gen_easy_tasks.DEFAULT_SRC)
    runner = BenchmarkRunner(tmp_path / "bench")
    sandbox = runner.sandbox_for(tasks[0].task_id)
    sandbox.parent.mkdir(parents=True, exist_ok=True)
    sandbox.write_text("leftover")  # 普通文件占位
    results = runner.run_all(tasks[:1])
    assert results[0].final_score == 0.0  # 崩溃题 0 分（不倒扣）
    assert any("crashed" in n for n in results[0].notes)
    assert sandbox.is_file()  # 占位文件未被强拆


def test_run_all_isolates_task_failure(tmp_path, capsys):
    """单题后端异常不拖垮整批：失败题落 notes 带原因的零分行并继续。"""
    from cloudra.benchmark.runner import BenchmarkRunner

    tasks = gen_easy_tasks.parse_easy_md(gen_easy_tasks.DEFAULT_SRC)[:2]

    def backend(task, sandbox):
        if task.task_id == tasks[0].task_id:
            raise RuntimeError("backend exploded")
        sandbox.mkdir(parents=True, exist_ok=True)
        return None

    runner = BenchmarkRunner(tmp_path / "bench", backend=backend)
    results = runner.run_all(tasks)
    assert [r.task_id for r in results] == [t.task_id for t in tasks]
    assert results[0].final_score == 0.0
    assert any("backend exploded" in n for n in results[0].notes)
    assert "backend exploded" in capsys.readouterr().out
    # 后续题目照常评分（no-op 交付：无图，integrity 判负）
    assert any("mechanism_graph.json not found" in n for n in results[1].notes)


def test_runner_rerun_appends_runs_rows(tmp_path):
    """runs 表 append-only：复跑同题累计多行，历史永不覆写。"""
    import sqlite3

    from cloudra.benchmark.runner import BenchmarkRunner

    tasks = gen_easy_tasks.parse_easy_md(gen_easy_tasks.DEFAULT_SRC)[:1]
    runner = BenchmarkRunner(tmp_path / "bench")
    runner.run_task(tasks[0])
    runner.run_task(tasks[0])
    with sqlite3.connect(runner.db.db_path) as c:
        rows = c.execute(
            "SELECT task_id FROM runs WHERE task_id = ?", (tasks[0].task_id,)
        ).fetchall()
    assert len(rows) == 2


# --- GED anchors ---


def test_ged_cost_ordering():
    bc = BondChangeSet(**{"break": []}, form=[[1, 2], [3, 4]])
    gold = _graph(["C=CC=C", "C=C"], ["C1CC=CCC1"], bc)
    same = _graph(["C=CC=C", "C=C"], ["C1CC=CCC1"], BondChangeSet(**{"break": []}, form=[[1, 2], [3, 4]]))
    similar = _graph(["C=CC=C", "C=C"], ["C1CCCC1"], BondChangeSet(**{"break": []}, form=[[1, 2]]))
    far = _graph(["CC"], ["CC"], BondChangeSet(**{"break": [[1, 2]]}))
    cfg = GedConfig()
    s_same = mechanism_similarity(same, gold, cfg).score
    s_sim = mechanism_similarity(similar, gold, cfg).score
    s_far = mechanism_similarity(far, gold, cfg).score
    assert s_same == pytest.approx(1.0)
    assert s_same > s_sim > s_far
    assert s_far < 0.2


def test_ged_missing_ts_lowers_score():
    gold = _graph(["C=CC=C", "C=C"], ["C1CC=CCC1"], with_ts=True)
    no_ts = _graph(["C=CC=C", "C=C"], ["C1CC=CCC1"], with_ts=False)
    cfg = GedConfig()
    assert mechanism_similarity(no_ts, gold, cfg).score < 1.0


def test_ged_node_insertion_order_irrelevant():
    """同一拓扑不同节点写入顺序应得同一分数（GED 取最优近似值，而非第一个）。"""
    g1 = GoldMechanismGraph(nodes=[
        MechanismNode(id="R", role=NodeRole.REACTANT, smiles=["C=CC=C", "C=C"]),
        MechanismNode(id="TS", role=NodeRole.TRANSITION_STATE, smiles=[]),
        MechanismNode(id="P", role=NodeRole.PRODUCT, smiles=["C1CC=CCC1"]),
    ], edges=[MechanismEdge(id="E", **{"from": "R", "to": "P"}, via="TS")])
    g2 = GoldMechanismGraph(nodes=list(reversed(g1.nodes)), edges=list(g1.edges))
    assert mechanism_similarity(g2, g1, GedConfig()).score == pytest.approx(1.0)


def test_ged_parallel_edges_preserved():
    """双通道机理：gold 两条 R->P 边（不同键变化），agent 只交付一条 -> 扣分。"""
    nodes = [
        MechanismNode(id="R", role=NodeRole.REACTANT, smiles=["[F-]", "CCl"]),
        MechanismNode(id="TS1", role=NodeRole.TRANSITION_STATE, smiles=[]),
        MechanismNode(id="TS2", role=NodeRole.TRANSITION_STATE, smiles=[]),
        MechanismNode(id="P", role=NodeRole.PRODUCT, smiles=["CF", "[Cl-]"]),
    ]
    e1 = MechanismEdge(id="E1", **{"from": "R", "to": "P"}, via="TS1",
                       bond_changes=BondChangeSet(**{"break": [[1, 2]]}, form=[[1, 3]]))
    e2 = MechanismEdge(id="E2", **{"from": "R", "to": "P"}, via="TS2",
                       bond_changes=BondChangeSet(**{"break": [[1, 2]]}, form=[[4, 5]]))
    gold = GoldMechanismGraph(nodes=nodes, edges=[e1, e2])
    one_path = GoldMechanismGraph(
        nodes=[n for n in nodes if n.id != "TS2"], edges=[e1],
    )
    both = mechanism_similarity(gold, gold, GedConfig())
    missing = mechanism_similarity(one_path, gold, GedConfig())
    assert both.score == pytest.approx(1.0)
    assert missing.score < 1.0  # 平行边没有被覆盖丢失


def test_ged_edit_script_uses_species_not_ids():
    """edit_script 按物种 SMILES 描述差异，不受 agent/gold 节点 id 命名影响。"""
    gold = _graph(["C=CC=C", "C=C"], ["C1CC=CCC1"])
    # 与 gold 完全同构但节点 id 完全不同：无差异（按 id 做差会全报 missing）
    agent = GoldMechanismGraph(nodes=[
        MechanismNode(id="n0", role=NodeRole.REACTANT, smiles=["C=CC=C", "C=C"]),
        MechanismNode(id="n1", role=NodeRole.TRANSITION_STATE, smiles=[]),
        MechanismNode(id="n2", role=NodeRole.PRODUCT, smiles=["C1CC=CCC1"]),
    ], edges=[MechanismEdge(id="e0", **{"from": "n0", "to": "n2"}, via="n1")])
    assert mechanism_similarity(agent, gold, GedConfig()).edit_script == []
    # 产物不同：出现 species_missing，且内容是 SMILES 而非节点 id
    other = _graph(["C=CC=C", "C=C"], ["C1CCCC1"])
    script = mechanism_similarity(other, gold, GedConfig()).edit_script
    assert any("species_missing" in s and "C1CC=CCC1" in s for s in script)


def test_subgraph_extra_nodes_and_edges_are_free():
    """子图打分：交付图多出节点/边（含前置的分离反应物平衡步）不扣分。"""
    gold = _graph(["[F-]", "CCl"], ["CF", "[Cl-]"])
    extra_species = GoldMechanismGraph(
        nodes=[
            MechanismNode(id="sep", role=NodeRole.REACTANT, smiles=["[F-]", "CCl"]),
            MechanismNode(id="RC", role=NodeRole.REACTANT, smiles=["[F-]", "CCl"]),
            MechanismNode(id="TS", role=NodeRole.TRANSITION_STATE, smiles=[]),
            MechanismNode(id="P", role=NodeRole.PRODUCT, smiles=["CF", "[Cl-]"]),
        ],
        edges=[
            MechanismEdge(id="E0", **{"from": "sep", "to": "RC"}),  # 多出的络合平衡步
            MechanismEdge(id="E1", **{"from": "RC", "to": "P"}, via="TS"),
        ],
    )
    res = mechanism_similarity(extra_species, gold, GedConfig())
    assert res.score == pytest.approx(1.0)


def test_subgraph_missing_and_mismatch_still_cost():
    """缺失 gold 物种扣一个节点插入代价；化学不符的物种同样拉低分数。"""
    gold = _graph(["[F-]", "CCl"], ["CF", "[Cl-]"])
    # 空交付 -> 0 分（3 节点 + 1 边全缺）
    empty = GoldMechanismGraph(nodes=[], edges=[])
    assert mechanism_similarity(empty, gold, GedConfig()).score == 0.0
    # 只有反应物、缺产物 -> 扣 1 节点 + 1 边（gold lift 后 2 物种节点 + 1 边，分母 3）-> 1/3
    only_r = GoldMechanismGraph(
        nodes=[MechanismNode(id="R", role=NodeRole.REACTANT, smiles=["[F-]", "CCl"])],
        edges=[],
    )
    assert mechanism_similarity(only_r, gold, GedConfig()).score == pytest.approx(1 / 3)
    # 产物错误（CCl4 而非 CF·Cl⁻ 络合物）→ 产物节点替换代价 ≈0.98（指纹
    # Tanimoto≈0；络合物形态下是 1-vs-1 比对，无旧组分列表的基数罚分，代价
    # 顶不到 1.0，边仍按结构比对）；无 RDKit 时退化为字符串不等 → 按缺失连边
    # 扣两个插入代价（1/3）。两种环境都必须显著低于满分
    wrong_p = _graph(["[F-]", "CCl"], ["ClC(Cl)(Cl)Cl"])
    assert mechanism_similarity(wrong_p, gold, GedConfig()).score < 0.7


def _flagged_graph(ts_accessible: bool, edge_accessible: bool) -> GoldMechanismGraph:
    return GoldMechanismGraph(
        nodes=[
            MechanismNode(id="R", role=NodeRole.REACTANT, smiles=["O"]),
            MechanismNode(
                id="TS", role=NodeRole.TRANSITION_STATE, smiles=[],
                accessible=ts_accessible,
            ),
            MechanismNode(id="P", role=NodeRole.PRODUCT, smiles=["O"]),
        ],
        edges=[MechanismEdge(
            id="E1", **{"from": "R", "to": "P"}, via="TS", accessible=edge_accessible,
        )],
    )


def test_accessible_flag_consistency_scores_both_directions():
    """accessible 标志一致性进图分（双向）：gold 不可达交付硬算 / gold 可达
    交付躲证据 → 该边替换代价 1.0（等同缺失，3 元素图 -> 2/3）。按有效可达性
    比较：gold 标在 TS 节点上、交付标在边上（协议允许的两种形式）同口径一致。"""
    gold_ts_false = _flagged_graph(ts_accessible=False, edge_accessible=True)
    delivered_all_true = _flagged_graph(ts_accessible=True, edge_accessible=True)
    delivered_edge_false = _flagged_graph(ts_accessible=True, edge_accessible=False)

    # gold 不可达（TS 节点 false），交付硬算（全 true）-> 不一致 -> 扣 1 边
    assert mechanism_similarity(
        delivered_all_true, gold_ts_false, GedConfig()
    ).score == pytest.approx(2 / 3)
    # gold 可达，交付躲证据（边 false）-> 不一致 -> 同样扣
    assert mechanism_similarity(
        delivered_edge_false, _flagged_graph(True, True), GedConfig()
    ).score == pytest.approx(2 / 3)
    # gold 标 TS 节点 false、交付标边 false：有效不可达一致 -> 满分
    assert mechanism_similarity(
        delivered_edge_false, gold_ts_false, GedConfig()
    ).score == pytest.approx(1.0)
    # 全 true 交付对上 gold TS false 的反例对照：gold 也全 true 时满分
    assert mechanism_similarity(
        delivered_all_true, _flagged_graph(True, True), GedConfig()
    ).score == pytest.approx(1.0)


def test_binding_quality_partial_credit_enters_graph_score():
    """质子化 partial 绑定（q=0.85）并进图分：有效节点代价 = 1-(1-subst)·q
    = 0.15 -> score = 1 - 0.15/3（节点全等同构，只差绑定质量）。"""
    gold = _graph(["C"], ["O"])
    full = mechanism_similarity(gold, gold, GedConfig())
    assert full.score == pytest.approx(1.0)
    partial = mechanism_similarity(
        gold, gold, GedConfig(), binding_quality={"R": 1.0, "P": 0.85, "TS": 0.85}
    )
    assert partial.score == pytest.approx(1.0 - 0.15 / 3)
    # 未绑定（q=0）等同未覆盖：P 按缺失记账（代价 1.0），其边连带缺失 -> 1/3
    unbound = mechanism_similarity(
        gold, gold, GedConfig(), binding_quality={"R": 1.0, "P": 0.0, "TS": 0.0}
    )
    assert unbound.score == pytest.approx(1 / 3)


# --- accuracy ---


def _evidence(steps):
    from cloudra.benchmark.barrier_evidence import BarrierEvidence, StepBarrier

    return BarrierEvidence(
        steps=[
            StepBarrier(
                edge_id=edge_id,
                ts_path=f"{edge_id}_ts.log",
                base_path=f"{edge_id}_r.log",
                base_node_id="r1",
                barrier_kcal_mol=derived,
                declared_kcal_mol=declared,
            )
            for edge_id, derived, declared in steps
        ],
        graph_found=True,
    )


def _gold_edges(spec):
    """spec: list of (edge_id, barrier_kcal_mol, weight) -> GoldSpec（gold 参考边）。
    逐边链式端点（A→B→C…，物种可区分），避免物种匹配下两端点全等的歧义。"""

    chain = ["C", "CC", "CCC", "CCCC", "CCCCC", "CCCCCC"]
    nodes = [
        MechanismNode(id=f"N{i}", role=NodeRole.INTERMEDIATE, smiles=[chain[i]])
        for i in range(len(spec) + 1)
    ]
    nodes[0] = MechanismNode(id="N0", role=NodeRole.REACTANT, smiles=[chain[0]])
    nodes[-1] = MechanismNode(
        id=f"N{len(spec)}", role=NodeRole.PRODUCT, smiles=[chain[len(spec)]]
    )
    return GoldSpec(
        mechanism_graph=GoldMechanismGraph(
            nodes=nodes,
            edges=[
                MechanismEdge(
                    id=edge_id,
                    **{"from": f"N{i}", "to": f"N{i + 1}"},
                    barrier_kcal_mol=barrier,
                    weight=weight,
                )
                for i, (edge_id, barrier, weight) in enumerate(spec)
            ],
        )
    )


def _delivered_for_gold(gold: GoldSpec, edge_ids: list[str]) -> GoldMechanismGraph:
    """与 gold 同物种节点、端点接线相同但以交付 edge id 命名的交付图
    （accuracy 按物种对应匹配，gold/交付 edge id 不需要一致）。"""
    g = gold.mechanism_graph
    by_id = {e.id: e for e in g.edges}
    return GoldMechanismGraph(
        nodes=list(g.nodes),
        edges=[
            MechanismEdge(id=eid, **{"from": by_id[eid].from_node, "to": by_id[eid].to_node})
            for eid in edge_ids
        ],
    )


def test_accuracy_per_edge_requires_both_sources_and_agreement():
    """逐边双来源门禁：log 推算值与交付 JSON 声明值都必须存在且一致，缺一该边即 0。"""
    gold = _gold_edges([("E1", 27.5, 1.0)])
    r = AccuracyRubric(sigma_kcal_mol=3.0, max_penalty_fraction=0.3)
    delivered = _delivered_for_gold(gold, ["E1"])

    exact = score_accuracy(
        evidence=_evidence([("E1", 27.5, 27.5)]), gold=gold, rubric=r,
        delivered_graph=delivered,
    )
    assert exact.gaussian_score == pytest.approx(1.0)
    assert exact.final_score == pytest.approx(1.0)

    near = score_accuracy(
        evidence=_evidence([("E1", 28.0, 28.4)]), gold=gold, rubric=r,
        delivered_graph=delivered,
    )
    assert near.gaussian_score > 0.95

    far = score_accuracy(
        evidence=_evidence([("E1", 100.0, 100.0)]), gold=gold, rubric=r,
        delivered_graph=delivered,
    )
    assert far.capped_penalty == pytest.approx(0.3)  # capped
    assert far.final_score == pytest.approx(0.7)

    from cloudra.benchmark.barrier_evidence import BarrierEvidence

    # gold 参考边找不到对应交付步 -> 该边 0 分（fail-loud）
    assert (
        score_accuracy(
            evidence=BarrierEvidence(), gold=gold, rubric=r, delivered_graph=delivered
        ).final_score
        == 0.0
    )
    undeclared = score_accuracy(
        evidence=_evidence([("E1", 27.5, None)]), gold=gold, rubric=r,
        delivered_graph=delivered,
    )
    assert undeclared.final_score == 0.0
    assert any("declares no barrier_kcal_mol" in n for n in undeclared.notes), undeclared.notes
    # 声明值与日志推算值冲突、但证据里含有与参考一致的组合 → 答案定义差异，
    # 按固定小扣分记（不归零；见 _DEFINITION_MISMATCH_EDGE_SCORE）
    conflict = score_accuracy(
        evidence=_evidence([("E1", 27.5, 40.0)]), gold=gold, rubric=r,
        delivered_graph=delivered,
    )
    # gaussian_score = 0.9 → raw penalty 0.1（未触封顶）→ final 0.9
    assert conflict.edge_scores["E1"] == pytest.approx(0.9)
    assert conflict.final_score == pytest.approx(0.9)
    assert any("answer-definition mismatch" in n for n in conflict.notes), conflict.notes


def test_accuracy_matches_gold_edge_by_endpoint_species_not_edge_id():
    """gold 边与交付步 edge id 不同（题库内部 id agent 不可知）时，按端点物种
    对应匹配评分；端点物种不符则该边 fail-loud 记 0。"""
    gold = GoldSpec(
        mechanism_graph=GoldMechanismGraph(
            nodes=[
                MechanismNode(id="R", role=NodeRole.REACTANT, smiles=["C=O"]),
                MechanismNode(id="P", role=NodeRole.PRODUCT, smiles=["CO"]),
            ],
            edges=[
                MechanismEdge.model_validate(
                    {"id": "GOLD_E1", "from": "R", "to": "P", "barrier_kcal_mol": 20.0}
                )
            ],
        )
    )
    delivered = GoldMechanismGraph(
        nodes=[
            MechanismNode(id="RC", role=NodeRole.REACTANT, smiles=["C=O"]),
            MechanismNode(id="PC", role=NodeRole.PRODUCT, smiles=["CO"]),
        ],
        edges=[MechanismEdge.model_validate({"id": "e7", "from": "RC", "to": "PC"})],
    )
    r = AccuracyRubric(sigma_kcal_mol=3.0, max_penalty_fraction=1.0)
    rep = score_accuracy(
        evidence=_evidence([("e7", 21.0, 21.0)]), gold=gold, rubric=r,
        delivered_graph=delivered,
    )
    assert rep.gaussian_score > 0.9
    assert any("matched delivered step e7 by endpoint species" in n for n in rep.notes)

    # 端点物种不符 -> 找不到对应步
    other = GoldMechanismGraph(
        nodes=[
            MechanismNode(id="X", role=NodeRole.REACTANT, smiles=["N#N"]),
            MechanismNode(id="Y", role=NodeRole.PRODUCT, smiles=["O=O"]),
        ],
        edges=[MechanismEdge.model_validate({"id": "e7", "from": "X", "to": "Y"})],
    )
    rep2 = score_accuracy(
        evidence=_evidence([("e7", 21.0, 21.0)]), gold=gold, rubric=r,
        delivered_graph=other,
    )
    assert rep2.final_score == 0.0


def test_accuracy_parallel_same_endpoint_edges_require_distinct_channels():
    """HH1 的 syn/anti 同端点、同键变化边不可复用同一交付能垒。"""
    nodes = [
        MechanismNode(id="R", role=NodeRole.REACTANT, smiles=["C1=CC=CC=C1"]),
        MechanismNode(id="P", role=NodeRole.PRODUCT, smiles=["C1=CC=CC=C1"]),
    ]
    gold = GoldSpec(mechanism_graph=GoldMechanismGraph(
        nodes=nodes,
        edges=[
            MechanismEdge(id="G1", **{"from": "R", "to": "P"}, channel="syn", barrier_kcal_mol=23.01),
            MechanismEdge(id="G2", **{"from": "R", "to": "P"}, channel="anti", barrier_kcal_mol=32.36),
        ],
    ))
    syn_only = GoldMechanismGraph(nodes=nodes, edges=[
        MechanismEdge(id="candidate", **{"from": "R", "to": "P"}, channel="syn"),
    ])
    rubric = AccuracyRubric(sigma_kcal_mol=2.0)
    missing = score_accuracy(
        evidence=_evidence([("candidate", 23.01, 23.01)]), gold=gold,
        rubric=rubric, delivered_graph=syn_only,
    )
    assert missing.edge_scores["G1"] == pytest.approx(1.0)
    assert missing.edge_scores["G2"] == 0.0
    assert missing.final_score == 0.0

    both = GoldMechanismGraph(nodes=nodes, edges=[
        *syn_only.edges,
        MechanismEdge(id="other", **{"from": "R", "to": "P"}, channel="anti"),
    ])
    complete = score_accuracy(
        evidence=_evidence([("candidate", 23.01, 23.01), ("other", 32.36, 32.36)]),
        gold=gold, rubric=rubric, delivered_graph=both,
    )
    assert complete.edge_scores == {"G1": pytest.approx(1.0), "G2": pytest.approx(1.0)}
    assert complete.final_score == pytest.approx(1.0)


def test_accuracy_small_barrier_widens_sigma():
    """小能垒口径：gold 边 ≤ 阈值时对 gold 的比较放宽到小能垒 sigma
    （2.01 vs 5.0 在 sigma=3 下 ~0.61，放宽到 5 后 ~0.84）；大能垒仍用
    基准 sigma。声明值 vs 日志的内部一致性核对不放宽。"""
    import math

    gold = _gold_edges([("E1", 5.0, 1.0)])
    r = AccuracyRubric(sigma_kcal_mol=3.0, max_penalty_fraction=0.5)
    rep = score_accuracy(
        evidence=_evidence([("E1", 2.01, 2.01)]), gold=gold, rubric=r,
        delivered_graph=_delivered_for_gold(gold, ["E1"]),
    )
    assert rep.gaussian_score == pytest.approx(math.exp(-((2.99) ** 2) / (2 * 25.0)))

    big = _gold_edges([("E1", 27.5, 1.0)])
    rep_big = score_accuracy(
        evidence=_evidence([("E1", 28.0, 28.4)]), gold=big, rubric=r,
        delivered_graph=_delivered_for_gold(big, ["E1"]),
    )
    assert rep_big.gaussian_score == pytest.approx(
        math.exp(-((28.0 - 27.5) ** 2) / (2 * 3.0 ** 2))
    )


def test_accuracy_weighted_average_uses_edge_weights():
    """全部参考边通过一致性门禁时：汇总 = 逐边高斯分按 gold 边 weight 加权平均。"""
    import math

    gold = _gold_edges([("E1", 10.0, 1.0), ("E2", 20.0, 0.5)])
    r = AccuracyRubric(sigma_kcal_mol=3.0, max_penalty_fraction=1.0)
    rep = score_accuracy(
        evidence=_evidence([("E1", 10.0, 10.0), ("E2", 22.0, 22.0)]), gold=gold, rubric=r,
        delivered_graph=_delivered_for_gold(gold, ["E1", "E2"]),
    )
    g1 = 1.0
    g2 = math.exp(-((22.0 - 20.0) ** 2) / (2 * 3.0 ** 2))
    assert rep.edge_scores["E1"] == pytest.approx(g1)
    assert rep.edge_scores["E2"] == pytest.approx(g2)
    assert rep.gaussian_score == pytest.approx((1.0 * g1 + 0.5 * g2) / 1.5)


def test_accuracy_missing_reference_edge_fails_loud():
    """gold 参考边在交付 evidence 里找不到对应步 -> 整题 accuracy 记 0（fail-loud）。"""
    gold = _gold_edges([("E1", 10.0, 1.0), ("E2", 20.0, 0.5)])
    r = AccuracyRubric(sigma_kcal_mol=3.0, max_penalty_fraction=1.0)
    rep = score_accuracy(
        evidence=_evidence([("E1", 10.0, 10.0)]), gold=gold, rubric=r,
        delivered_graph=_delivered_for_gold(gold, ["E1"]),
    )
    assert rep.edge_scores["E2"] == 0.0
    assert rep.final_score == 0.0
    assert any("no delivered step matches its endpoint species" in n for n in rep.notes)


def test_accuracy_no_reference_edge_not_scored():
    """gold 边不带参考值且有效可达 -> 该边记 1.0（可算但标答未给参考值）。"""
    gold = _gold_edges([("E1", None, 1.0)])
    rep = score_accuracy(evidence=_evidence([]), gold=gold, rubric=AccuracyRubric())
    assert rep.edge_scores["E1"] == 1.0
    assert rep.final_score == 1.0
    assert any("carries no reference barrier" in n for n in rep.notes)


def test_accuracy_disabled_passthrough():
    gold = _gold_edges([("E1", 27.5, 1.0)])
    r = AccuracyRubric(enabled=False)
    assert score_accuracy(evidence=_evidence([]), gold=gold, rubric=r).final_score == 1.0


# --- method policy ---

# qm_input_writer：method 字段精确白名单；缺 method 字段 fail-closed
@pytest.mark.parametrize(
    "tool,args,allowed",
    [
        ("qm_input_writer", {"method": "mace-omol25"}, False),
        ("qm_input_writer", {"method": "xtb"}, True),
        ("qm_input_writer", {"method": "wb97m-v"}, False),
        ("qm_input_writer", {"method": "ccsd(t)"}, False),
        ("qm_input_writer", {}, False),
        ("read", {"path": "x"}, True),
    ],
)
def test_method_policy(tool, args, allowed):
    assert intercept(tool, args, MethodPolicy()).allowed is allowed


def test_method_policy_submit_compute_job_by_content(tmp_path):
    """submit_compute_job 没有 method 字段：按 input_file 的文件内容判定。"""
    policy = MethodPolicy(allowed_methods=["b3lyp", "xtb"])
    (tmp_path / "ok.gjf").write_text("#p b3lyp/6-31g(d) opt freq\n")
    (tmp_path / "bad.gjf").write_text("# wb97m-v/def2-tzvpd opt\n")
    (tmp_path / "junk.inp").write_text("not a QM input at all\n")
    assert intercept(
        "submit_compute_job", {"input_file": str(tmp_path / "ok.gjf")}, policy
    ).allowed
    assert not intercept(
        "submit_compute_job", {"input_file": str(tmp_path / "bad.gjf")}, policy
    ).allowed
    # 无法识别为 QM 输入：strict 模式 fail-closed
    assert not intercept(
        "submit_compute_job", {"input_file": str(tmp_path / "junk.inp")}, policy
    ).allowed
    # 文件不存在 / 缺参数：fail-closed
    assert not intercept(
        "submit_compute_job", {"input_file": str(tmp_path / "missing.gjf")}, policy
    ).allowed
    assert not intercept("submit_compute_job", {}, policy).allowed
    # 相对路径经 base_dir 解析
    assert intercept(
        "submit_compute_job", {"input_file": "ok.gjf"}, policy, base_dir=tmp_path
    ).allowed


# bash 层：判定基于写入的 QM 输入文件内容，不扫描命令文本
@pytest.mark.parametrize(
    "command,allowed",
    [
        # 引用已有文件 / 普通命令：无内嵌 QM 输入 -> 放行
        ("xtb ts.xyz --opt", True),
        ("cat scan_g4.log", True),
        ("tail -n 50 new1.out", True),
        ("grep -c ccsd summary.log", True),
        # 内嵌写入非 QM 输入（坐标/脚本）-> 放行
        ("cat > t.xyz <<EOF\n3\n\nO 0.0 0.0 0.0\nEOF", True),
        ("cat > run.sh <<EOF\nxtb a.xyz --opt\nEOF", True),
        # 内嵌写入 QM 输入：easy 白名单（mace/xtb）下任何 gaussian/orca 输入都拦截
        ("cat > t.gjf <<EOF\n# wb97m-v/def2-tzvpd opt\nEOF", False),
        ("cat > t.gjf <<EOF\n# b3lyp/6-31g(d) opt freq\nEOF", False),
        ("cat > t.com <<EOF\n#p opt=(ts) pbe1pbe/6-311++g(d,p)\nEOF", False),
        ("cat <<EOF > t.inp\n! dlpno-ccsd(t) cc-pvtz tightscf\nEOF", False),
        ("cat > t.inp <<EOF\n! b3lyp def2-svp opt\nEOF", False),
        # QM 输入无方法指令 -> fail-closed
        ("cat > t.gjf <<EOF\njust some coordinates\nEOF", False),
        # echo/printf 直写重定向同样按内容判定
        ("printf '# ccsd(t)/cc-pvtz sp\\n' > t.gjf", False),
        ('echo "# b3lyp/6-31g(d) opt" > t.gjf', False),
        # 嵌套：QM heredoc 藏进脚本 heredoc 里也要被看到
        ("cat > run.sh <<OUTER\ncat > t.gjf <<EOF\n# wb97m-v/def2-tzvpd\nEOF\nOUTER", False),
        # 位移运算与 python heredoc（首行 # 注释）不是 QM 输入
        ("echo $((1 << 2))", True),
        ("python3 - <<EOF\n# compute barrier with mace\nprint(1)\nEOF", True),
    ],
)
def test_method_policy_bash_content(command, allowed):
    assert intercept("bash", {"command": command}, MethodPolicy()).allowed is allowed


def test_method_policy_bash_tool_name():
    """注册的 bash 工具真实名是 bash：bash 层拦截生效。"""
    policy = MethodPolicy()
    bad = "cat > t.gjf <<EOF\n# b3lyp/6-31g(d) opt freq\nEOF"
    assert not intercept("bash", {"command": bad}, policy).allowed
    good = "cat > t.inp <<EOF\n! XTB2 OPT FREQ\nEOF"
    assert intercept("bash", {"command": good}, policy).allowed


def test_method_policy_family_granularity():
    """白名单按方法族匹配：xtb2/gfn2-xtb -> xtb，mace-off -> mace；
    族外方法（wb97m-v）仍拦。"""
    policy = MethodPolicy(allowed_methods=["mace-omol25", "xtb"])
    assert check_input_content("! XTB2 OPT FREQ\n", policy, "t.inp").allowed
    assert check_input_content("! gfn2-xtb opt\n", policy, "t.inp").allowed
    assert intercept("qm_input_writer", {"method": "mace-off"}, policy).allowed
    assert not intercept("qm_input_writer", {"method": "wb97m-v"}, policy).allowed


def test_method_policy_gaussian_external_route():
    """Gaussian MLIP 走 external 路由：引擎值即方法候选；裸 external 无值
    保持 fail-closed。"""
    policy = MethodPolicy(allowed_methods=["mace"])
    assert check_input_content(
        '#p opt=(ts,noeigen,calcfc) freq external="mace"\n', policy, "t.gjf"
    ).allowed
    assert check_input_content("#p freq external='mace'\n", policy, "t.gjf").allowed
    assert check_input_content("#p freq external=mace\n", policy, "t.gjf").allowed
    assert not check_input_content("#p b3lyp/6-31g* opt\n", policy, "t.gjf").allowed
    assert not check_input_content("#p opt external\n", policy, "t.gjf").allowed


def test_method_policy_orca_extopt_route():
    """ORCA MLIP 走 ExtOpt 路由：%method 块里 ProgExt 的外部程序名即方法候选
    （与 Gaussian external="engine" 对齐）；裸 ExtOpt 无 ProgExt 保持 fail-closed。
    GH #16：否则 MACE 白名单下的合法 ExtOpt 输入会被当成方法不明拦截。"""
    policy = MethodPolicy(allowed_methods=["mace"])
    content = (
        "! ExtOpt Opt\n"
        "%pal nprocs 1 end\n"
        "%method\n"
        '  ProgExt "/opt/conda/envs/chemai/bin/mace"\n'
        '  Ext_Params "--model /opt/MACE-omol-0.model --device cpu --dtype float64"\n'
        "end\n"
        "* xyz 0 1\nC 0.0 0.0 0.0\n*\n"
    )
    verdict = check_input_content(content, policy, "t.inp")
    assert verdict.allowed, verdict.reason
    # 白名单外外部程序：拦截
    blocked = content.replace("chemai/bin/mace", "opt/bin/g16")
    assert not check_input_content(blocked, policy, "t.inp").allowed
    # 裸 ExtOpt（无 %method ProgExt）：无法验证 -> fail-closed
    bare = "! ExtOpt Opt\n* xyz 0 1\nC 0.0 0.0 0.0\n*\n"
    assert not check_input_content(bare, policy, "t.inp").allowed


def test_method_policy_qm_input_writer_external_program():
    """qm_input_writer 结构化拦截：带 external_program 时以外部程序名为方法候选，
    method 字段（工具默认值残留）不再参与判定。"""
    policy = MethodPolicy(allowed_methods=["mace"])
    ok = intercept(
        "qm_input_writer",
        {"method": "b3lyp", "external_program": "/opt/conda/envs/chemai/bin/mace"},
        policy,
    )
    assert ok.allowed, ok.reason
    bad = intercept(
        "qm_input_writer",
        {"method": "mace", "external_program": "/opt/bin/g16"},
        policy,
    )
    assert not bad.allowed


def test_method_policy_link1_and_multi_candidate():
    """--Link1-- 多步输入的每张路由卡都要过白名单；ORCA 多个方法候选即拦。"""
    policy = MethodPolicy(allowed_methods=["b3lyp"])
    link1 = (
        "%chk=s.chk\n#p b3lyp/6-31g(d) opt\n\n0 1\nC 0 0 0\n\n"
        "--Link1--\n%chk=s.chk\n#p ccsd(t)/cc-pvtz sp\n"
    )
    assert not check_input_content(link1, policy, "t.gjf").allowed
    # 两张卡都白名单 -> 放行
    link1_ok = link1.replace("ccsd(t)/cc-pvtz", "b3lyp/6-31g(d)")
    assert check_input_content(link1_ok, policy, "t.gjf").allowed
    # 白名单方法旁掺杂第二个方法候选 -> 拦
    assert not check_input_content("! b3lyp dlpno-ccsd(t) def2-svp", policy, "t.inp").allowed
    # ORCA 裸基组别名不是方法候选
    assert check_input_content("! rks b3lyp tzvp opt", policy, "t.inp").allowed


def test_method_policy_content_whitelisted_method():
    """白名单放宽后，内容匹配到白名单方法的输入放行（覆盖 normal/hard 档语义）。"""
    policy = MethodPolicy(allowed_methods=["b3lyp", "xtb"])
    assert check_input_content("# b3lyp/6-31g(d) opt freq", policy, "t.gjf").allowed
    assert not check_input_content("# wb97m-v/def2-tzvpd opt", policy, "t.gjf").allowed
    assert check_input_content("! b3lyp def2-svp opt", policy, "t.inp").allowed
    assert not check_input_content("! dlpno-ccsd(t) cc-pvtz", policy, "t.inp").allowed
    # Gaussian Link0 行（%chk/%mem）在路由卡之前，不干扰方法提取
    assert check_input_content(
        "%chk=t.chk\n%mem=4GB\n#p opt=(ts,calcfc) b3lyp/6-31g(d) freq\n", policy, "t.gjf"
    ).allowed
    # ORCA 波函数类型修饰符（rks/uks/...）不是方法
    assert check_input_content("! rks b3lyp def2-svp tightscf opt", policy, "t.inp").allowed
    # 无后缀时按内容嗅探引擎
    assert check_input_content("# b3lyp/6-31g(d) opt", policy).allowed
    # slash 方法优先于裸 token：禁用方法旁填充白名单词不能蒙混
    assert not check_input_content("# ccsd(t)/cc-pvtz xtb\n", policy, "t.gjf").allowed
    # 非 QM 输入内容不在管辖范围
    assert check_input_content("hello world", policy, "notes.txt").allowed


def test_method_policy_combo_entries_pin_basis():
    """组合条目 `functional/basis` 把基组钉进许可：错基组或缺基组一律
    fail-closed；ORCA `def2-SVP` 与 Gaussian `def2svp` 拼写归一；裸族条目
    （xtb/mace，无基组概念）不约束基组。"""
    policy = MethodPolicy(allowed_methods=["xtb", "b3lyp/def2svp"])
    # qm_input_writer 结构化路径：method 与 basis_set 分字段
    assert check_method("b3lyp", policy, basis="def2svp").allowed
    assert check_method("b3lyp", policy, basis="def2-SVP").allowed
    assert not check_method("b3lyp", policy, basis="6-31g*").allowed
    assert not check_method("b3lyp", policy).allowed  # 缺基组 fail-closed
    assert check_method("b3lyp/def2svp", policy).allowed  # 方法字符串自带 slash
    assert not check_method("b3lyp/def2tzvp", policy).allowed
    assert check_method("xtb", policy).allowed  # 裸族条目无基组概念
    # intercept 层接线：basis_set 字段参与判定
    assert intercept("qm_input_writer", {"method": "b3lyp", "basis_set": "def2svp"}, policy).allowed
    assert not intercept("qm_input_writer", {"method": "b3lyp", "basis_set": "sto-3g"}, policy).allowed
    assert not intercept("qm_input_writer", {"method": "b3lyp"}, policy).allowed
    # Gaussian 路由卡：slash 权威声明带基组
    assert check_input_content("#p b3lyp/def2svp opt freq", policy, "t.gjf").allowed
    assert not check_input_content("#p b3lyp/6-31g* opt", policy, "t.gjf").allowed
    assert not check_input_content("# b3lyp opt", policy, "t.gjf").allowed
    # ORCA 关键字行：同行基组与泛函配对；d3bj 是色散修饰不是方法
    assert check_input_content("! b3lyp def2-SVP optts", policy, "t.inp").allowed
    assert check_input_content("! b3lyp D3BJ def2-svp opt", policy, "t.inp").allowed
    assert not check_input_content("! b3lyp def2-TZVP opt", policy, "t.inp").allowed
    assert not check_input_content("! b3lyp opt", policy, "t.inp").allowed


def test_method_policy_files_on_disk(tmp_path):
    """`g16 foo.gjf` 这类引用磁盘已有输入的调用由 check_input_files 覆盖。"""
    (tmp_path / "ok.gjf").write_text("# b3lyp/6-31g(d) opt\n")
    (tmp_path / "bad.inp").write_text("! wb97m-v def2-tzvpd opt\n")
    policy = MethodPolicy(allowed_methods=["b3lyp"])
    assert check_input_files([tmp_path / "ok.gjf"], policy).allowed
    assert not check_input_files([tmp_path / "bad.inp"], policy).allowed
    # 非 QM 后缀直接跳过
    (tmp_path / "data.xyz").write_text("3\n\nO 0 0 0\n")
    assert check_input_files([tmp_path / "data.xyz"], policy).allowed
    # QM 后缀文件不可读 -> fail-closed（白名单语义下"读不了"等于"验不了"）
    unreadable = tmp_path / "locked.gjf"
    unreadable.write_text("# b3lyp/6-31g(d) opt\n")
    unreadable.chmod(0)
    try:
        assert not check_input_files([unreadable], policy).allowed
    finally:
        unreadable.chmod(0o644)


# --- integrity ---


def test_integrity_audit_binds_evidence(tmp_path):
    g = {
        "nodes": [
            {"id": "R", "role": "reactant", "smiles": ["C=CC=C.C=C"], "accessible": True, "label": "r"},
            {"id": "TS", "role": "transition_state", "smiles": [], "accessible": True, "label": "ts"},
            {"id": "P", "role": "product", "smiles": ["C1CC=CCC1"], "accessible": True, "label": "p"},
        ],
        "edges": [{"id": "E1", "from": "R", "to": "P", "via": "TS", "step_type": "da",
                    "bond_changes": {"break": [], "form": [[1, 2]]}, "accessible": True}],
    }
    (tmp_path / "mechanism_graph.json").write_text(json.dumps(g))
    (tmp_path / "r.log").write_text("smiles: C=CC=C.C=C\n")
    (tmp_path / "p.log").write_text("smiles: C1CC=CCC1\n")
    rep = audit_integrity(tmp_path)
    assert rep.graph_found and rep.graph_parseable
    assert all(b.matched and b.quality == 1.0 for b in rep.node_bindings)
    assert rep.binding_quality == 1.0


def test_integrity_missing_graph_fails(tmp_path):
    rep = audit_integrity(tmp_path)
    assert not rep.graph_found
    assert not rep.graph_parseable


def test_integrity_ts_bound_via_endpoints(tmp_path):
    """TS 节点不再无条件通过：仅当经由它的边的两端物种都有证据时才算绑定。"""
    base_nodes = [
        {"id": "R", "role": "reactant", "smiles": ["C=CC=C.C=C"]},
        {"id": "TS", "role": "transition_state", "smiles": []},
        {"id": "P", "role": "product", "smiles": ["C1CC=CCC1"]},
    ]
    edge = {"id": "E1", "from": "R", "to": "P", "via": "TS"}

    # 只有 R 端有证据：P 与 TS 都不应绑定
    (tmp_path / "mechanism_graph.json").write_text(
        json.dumps({"nodes": base_nodes, "edges": [edge]})
    )
    (tmp_path / "r.log").write_text("smiles: C=CC=C.C=C\n")
    rep = audit_integrity(tmp_path)
    matched = {b.node_id: b.matched for b in rep.node_bindings}
    assert matched == {"R": True, "TS": False, "P": False}
    assert rep.binding_quality == pytest.approx(1 / 3)

    # 两端证据补齐后 TS 经端点间接绑定
    (tmp_path / "p.log").write_text("smiles: C1CC=CCC1\n")
    rep = audit_integrity(tmp_path)
    matched = {b.node_id: b.matched for b in rep.node_bindings}
    assert matched == {"R": True, "TS": True, "P": True}
    assert rep.binding_quality == 1.0

    # TS 未被任何边经由：即使物种证据齐全也不应绑定
    orphan = {
        "nodes": base_nodes,
        "edges": [{"id": "E1", "from": "R", "to": "P", "via": None}],
    }
    (tmp_path / "mechanism_graph.json").write_text(json.dumps(orphan))
    rep = audit_integrity(tmp_path)
    matched = {b.node_id: b.matched for b in rep.node_bindings}
    assert matched["TS"] is False
    assert rep.binding_quality < 1.0


def test_integrity_evidence_smiles_tolerant_formats(tmp_path):
    """证据 SMILES 注释容忍 JSON/YAML 引号与注释前缀（交付协议的注释行会
    出现在 .gjf 标题、日志回显、JSON 摘要等各种格式里）。"""
    g = {
        "nodes": [
            {"id": "R", "role": "reactant", "smiles": ["C=CC=C.C=C"]},
            {"id": "P", "role": "product", "smiles": ["C1CC=CCC1"]},
        ],
        "edges": [{"id": "E1", "from": "R", "to": "P"}],
    }
    (tmp_path / "mechanism_graph.json").write_text(json.dumps(g))
    (tmp_path / "r.log").write_text('title\n{"smiles": "C=CC=C.C=C"}\n')
    (tmp_path / "p.log").write_text("smiles: 'C1CC=CCC1'\n")
    rep = audit_integrity(tmp_path)
    assert all(b.matched for b in rep.node_bindings), rep.notes


def test_integrity_evidence_bracket_smiles_not_truncated(tmp_path):
    """离子 bracket SMILES（[F-]、[Cl-]）必须完整捕获——正则排除集若误含
    方括号会把 [F-].CCl 截断导致永远绑不上（干跑实测抓出）。"""
    g = {
        "nodes": [
            {"id": "R", "role": "reactant", "smiles": ["[F-].CCl"]},
            {"id": "P", "role": "product", "smiles": ["CF.[Cl-]"]},
        ],
        "edges": [{"id": "E1", "from": "R", "to": "P"}],
    }
    (tmp_path / "mechanism_graph.json").write_text(json.dumps(g))
    (tmp_path / "r.gjf").write_text("# title\nsmiles: [F-].CCl\n")
    (tmp_path / "p_summary.json").write_text(json.dumps({"smiles": ["CF.[Cl-]"]}))
    rep = audit_integrity(tmp_path)
    assert all(b.matched for b in rep.node_bindings), rep.notes


def test_integrity_empty_smiles_species_not_bound(tmp_path):
    """物种节点不带 SMILES = 只有声明没有可取证内容，不得自动通过。"""
    g = {
        "nodes": [
            {"id": "R", "role": "reactant", "smiles": []},
            {"id": "P", "role": "product", "smiles": ["C1CC=CCC1"]},
        ],
        "edges": [{"id": "E1", "from": "R", "to": "P"}],
    }
    (tmp_path / "mechanism_graph.json").write_text(json.dumps(g))
    (tmp_path / "p.log").write_text("smiles: C1CC=CCC1\n")
    rep = audit_integrity(tmp_path)
    matched = {b.node_id: b.matched for b in rep.node_bindings}
    assert matched["R"] is False
    assert matched["P"] is True
    assert rep.binding_quality < 1.0


def test_integrity_delivered_graph_lenient_loading(tmp_path):
    """交付图宽松加载：agent 多写的键忽略、边缺 id 自动补。"""
    g = {
        "nodes": [
            {"id": "R", "role": "reactant", "smiles": ["CC"], "energy": -40.1},
            {"id": "P", "role": "product", "smiles": ["CC"], "note": "same"},
        ],
        "edges": [{"from": "R", "to": "P", "via": None}],
        "metadata": {"tool": "whatever"},
    }
    (tmp_path / "mechanism_graph.json").write_text(json.dumps(g))
    (tmp_path / "r.log").write_text("smiles: CC\n")
    rep = audit_integrity(tmp_path)
    assert rep.graph_parseable
    assert rep.delivered_graph is not None
    assert rep.delivered_graph.edges[0].id  # 缺省 id 已自动补
    assert all(b.matched for b in rep.node_bindings)


def test_integrity_delivered_graph_postel_aliases(tmp_path):
    """GH #29：agent 按常规图论字段交付（type/source/target、字符串 SMILES）也
    必须可解析：type→role、source→from、target→to、str smiles→[smiles]。"""
    g = {
        "nodes": [
            {"id": "rc", "type": "reactant", "label": "pre-reaction complex", "smiles": "[F-].CCl"},
            {"id": "ts_walden", "type": "ts"},
            {"id": "pc", "type": "product", "smiles": "[Cl-].CF"},
        ],
        "edges": [
            {"source": "rc", "target": "pc", "type": "elementary_step", "via": "ts_walden"},
            {"id": "e2", "from": "pc", "to": "pc", "via": None},
        ],
    }
    (tmp_path / "mechanism_graph.json").write_text(json.dumps(g))
    rep = audit_integrity(tmp_path)
    assert rep.graph_parseable, rep.notes
    assert rep.delivered_graph is not None
    nodes = {n.id: n for n in rep.delivered_graph.nodes}
    assert nodes["rc"].role.value == "reactant"
    assert nodes["rc"].smiles == ["[F-].CCl"]
    edges = rep.delivered_graph.edges
    assert (edges[0].from_node, edges[0].to_node, edges[0].via) == ("rc", "pc", "ts_walden")
    assert edges[1].id == "e2"  # 显式 id 原样保留


def test_integrity_delivered_graph_free_text_role_falls_back_to_type(tmp_path):
    """生产实锤（benchmark D3）：节点同写 type（合法枚举别名）与 role（自由文本
    描述）时，自由文本 role 不得撞 NodeRole 枚举校验毁掉整图——以 type 的映射值
    为 role，原文本并进 label；role 本身是合法枚举值时不动。"""
    g = {
        "nodes": [
            {"id": "R", "type": "reactant", "role": "starting materials complex",
             "label": "substrates", "smiles": ["CC=O"]},
            {"id": "TS", "type": "transition_state", "role": "C-C bond forming saddle",
             "smiles": []},
            {"id": "P", "type": "product", "role": "product", "smiles": ["CC(=O)C"]},
        ],
        "edges": [{"id": "E1", "from": "R", "to": "P", "via": "TS"}],
    }
    (tmp_path / "mechanism_graph.json").write_text(json.dumps(g))
    rep = audit_integrity(tmp_path)
    assert rep.graph_parseable, rep.notes
    assert rep.delivered_graph is not None
    nodes = {n.id: n for n in rep.delivered_graph.nodes}
    assert nodes["R"].role.value == "reactant"
    assert "substrates" in nodes["R"].label
    assert "starting materials complex" in nodes["R"].label
    assert nodes["TS"].role.value == "transition_state"
    assert "C-C bond forming saddle" in nodes["TS"].label
    # role 本身是合法枚举：不改写、不进 label
    assert nodes["P"].role.value == "product"
    assert nodes["P"].label == ""


def test_integrity_delivered_graph_unknown_node_type_fails_loud(tmp_path):
    """Postel 只映射可识别的 type 别名；无法识别的内容照旧 fail-loud 判不可解析。"""
    g = {
        "nodes": [{"id": "rc", "type": "quantum_vortex", "smiles": "C"}],
        "edges": [],
    }
    (tmp_path / "mechanism_graph.json").write_text(json.dumps(g))
    rep = audit_integrity(tmp_path)
    assert not rep.graph_parseable
    assert "present but not parseable" in rep.notes[0]


def test_integrity_fallback_graph_cannot_self_bind(tmp_path):
    """兜底发现的交付图（sub/my_graph.json）不得充当自身证据：图内嵌 SMILES
    不构成计算证据，零计算证据的交付必须判负。"""
    g = {
        "nodes": [
            {"id": "R", "role": "reactant", "smiles": ["C=CC=C", "C=C"]},
            {"id": "P", "role": "product", "smiles": ["C1CC=CCC1"]},
        ],
        "edges": [{"id": "E1", "from": "R", "to": "P"}],
    }
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "my_graph.json").write_text(json.dumps(g))
    rep = audit_integrity(tmp_path)
    assert rep.graph_found and rep.graph_parseable
    assert rep.graph_path == "sub/my_graph.json"
    assert rep.evidence_files == []  # 交付图自身被排除出证据扫描
    assert rep.node_bindings and not any(b.matched for b in rep.node_bindings)
    assert rep.binding_quality == 0.0


# --- 「节点即络合物」归一化（NI1 回归：组分列表交付 ↔ 络合物标注证据） ---


def test_mechanism_node_folds_component_list_to_complex():
    """schema 级归一化（用户裁决）：>1 个组分的 smiles 列表折叠成点连接络合物
    单条 SMILES；单组分与空列表（TS 节点）不动。"""
    rc = MechanismNode(id="RC", role=NodeRole.REACTANT, smiles=["C=O", "CN"])
    assert rc.smiles == ["C=O.CN"]
    three = MechanismNode(id="RC", role=NodeRole.REACTANT, smiles=["C=C", "F", "[Cl-]"])
    assert three.smiles == ["C=C.F.[Cl-]"]
    assert MechanismNode(id="P", role=NodeRole.PRODUCT, smiles=["CC"]).smiles == ["CC"]
    assert MechanismNode(id="TS", role=NodeRole.TRANSITION_STATE, smiles=[]).smiles == []


def test_delivered_component_list_binds_complex_annotated_evidence(tmp_path):
    """NI1 回归：交付图 RC 写组分列表（含反序）、证据日志按络合物标注
    （# smiles: C=O.CN）——折叠后 complex-vs-complex cost=0，绑定满分。"""
    pytest.importorskip("rdkit")  # 反序形态（CN.C=O vs C=O.CN）靠 molhash 归一判等
    for order in (["C=O", "CN"], ["CN", "C=O"]):
        g = {
            "nodes": [
                {"id": "RC", "role": "reactant", "smiles": order},
                {"id": "P", "role": "product", "smiles": ["CNCO"]},
            ],
            "edges": [{"id": "E1", "from": "RC", "to": "P"}],
        }
        (tmp_path / "mechanism_graph.json").write_text(json.dumps(g))
        (tmp_path / "rc.log").write_text("smiles: C=O.CN\n")
        (tmp_path / "p.log").write_text("smiles: CNCO\n")
        rep = audit_integrity(tmp_path)
        assert rep.delivered_graph is not None
        rc_smiles = rep.delivered_graph.nodes[0].smiles
        assert len(rc_smiles) == 1 and "." in rc_smiles[0]
        assert all(
            b.matched and b.quality == 1.0 for b in rep.node_bindings
        ), (order, rep.notes)


def test_three_component_complex_binds(tmp_path):
    """三组分络合物同一口径：组分列表 ["C=C","F","[Cl-]"] 交付 ↔
    络合物标注 "C=C.F.[Cl-]" 证据。"""
    g = {
        "nodes": [{"id": "RC", "role": "reactant", "smiles": ["C=C", "F", "[Cl-]"]}],
        "edges": [],
    }
    (tmp_path / "mechanism_graph.json").write_text(json.dumps(g))
    (tmp_path / "rc.log").write_text("smiles: C=C.F.[Cl-]\n")
    rep = audit_integrity(tmp_path)
    assert rep.delivered_graph is not None
    assert rep.delivered_graph.nodes[0].smiles == ["C=C.F.[Cl-]"]
    assert rep.node_bindings[0].matched and rep.node_bindings[0].quality == 1.0


def test_complex_binding_rejects_truly_different_species(tmp_path):
    """反例：形态统一不得放松化学判定——苯+水络合物证据不得绑上甲醛+甲胺
    络合物节点。"""
    g = {
        "nodes": [{"id": "RC", "role": "reactant", "smiles": ["C=O", "CN"]}],
        "edges": [],
    }
    (tmp_path / "mechanism_graph.json").write_text(json.dumps(g))
    (tmp_path / "rc.log").write_text("smiles: c1ccccc1.O\n")
    rep = audit_integrity(tmp_path)
    assert not rep.node_bindings[0].matched
    assert rep.node_bindings[0].quality == 0.0


def test_component_list_delivery_full_graph_score_vs_complex_gold():
    """图分同口径：交付图组分列表（折叠为络合物）对 gold 络合物节点给满分。"""
    gold = _graph(["C=O.CN"], ["CNCO"])
    delivered = _graph(["C=O", "CN"], ["CNCO"])
    assert mechanism_similarity(delivered, gold, GedConfig()).score == pytest.approx(1.0)


# --- 逐组分联合覆盖兜底（用户裁决：络合物优化不干净时允许拆开交付） ---


def _rc_only_graph(tmp_path):
    g = {
        "nodes": [{"id": "RC", "role": "reactant", "smiles": ["C=O.CN"]}],
        "edges": [],
    }
    (tmp_path / "mechanism_graph.json").write_text(json.dumps(g))


def test_complex_binds_via_per_component_coverage(tmp_path):
    """(a) 整络合物标注缺席时，逐组分联合覆盖可绑：两个组分各一个证据文件，
    全部组分有覆盖 → matched，quality 取最弱组分（此处双双全绑 = 1.0）。"""
    _rc_only_graph(tmp_path)
    (tmp_path / "frag1.log").write_text("smiles: C=O\n")
    (tmp_path / "frag2.log").write_text("smiles: CN\n")
    rep = audit_integrity(tmp_path)
    b = rep.node_bindings[0]
    assert b.matched and b.quality == 1.0
    assert b.bound_files == ["frag1.log", "frag2.log"]


def test_whole_complex_annotation_preferred_over_components(tmp_path):
    """(b) 整络合物与逐组分证据同时存在时优先整络合物：quality 1.0 且绑定文件
    只含整络合物标注（兜底通道不启动）。"""
    _rc_only_graph(tmp_path)
    (tmp_path / "whole.log").write_text("smiles: C=O.CN\n")
    (tmp_path / "frag1.log").write_text("smiles: C=O\n")
    (tmp_path / "frag2.log").write_text("smiles: CN\n")
    rep = audit_integrity(tmp_path)
    b = rep.node_bindings[0]
    assert b.matched and b.quality == 1.0
    assert b.bound_files == ["whole.log"]


def test_complex_unbound_when_only_one_component_evidenced(tmp_path):
    """(c) 只有一个组分有证据（另一组分无标注）→ 联合覆盖不成立，仍不绑。"""
    _rc_only_graph(tmp_path)
    (tmp_path / "frag1.log").write_text("smiles: C=O\n")
    rep = audit_integrity(tmp_path)
    b = rep.node_bindings[0]
    assert not b.matched and b.quality == 0.0

# --- self-consistency ---

FIXTURES = Path(__file__).parent / "fixtures"


def _sc_graph(**node_overrides):
    """R → P 经 TS 的交付图；默认全部 accessible。"""
    graph = {
        "nodes": [
            {"id": "R", "role": "reactant", "smiles": ["O"]},
            {"id": "TS", "role": "transition_state", "smiles": []},
            {"id": "P", "role": "product", "smiles": ["O"]},
        ],
        "edges": [{"id": "E1", "from": "R", "to": "P", "via": "TS"}],
    }
    for node in graph["nodes"]:
        node.update(node_overrides.get(node["id"], {}))
    return GoldMechanismGraph.model_validate(graph)


def _checks_by_id(rep):
    return {c.element_id: c for c in rep.checks}


def test_selfconsistency_real_fixtures_split_roles(tmp_path):
    """真实日志：水 opt+freq 覆盖物种极小值；ORCA IRC 日志没有边文件轨迹，
    拿不到可验证端点几何，且无频率块不能充当一阶鞍点证据——边双缺不覆盖。"""
    import shutil

    shutil.copy(FIXTURES / "gaussian" / "water_opt_freq_g16.out", tmp_path / "reactant.log")
    shutil.copy(FIXTURES / "orca" / "hcn_irc_orca60.out", tmp_path / "ts_irc.log")
    files = scan_evidence_files(tmp_path)
    bindings = [
        NodeBinding(node_id="R", bound_files=["reactant.log"], matched=True, quality=1.0),
        NodeBinding(node_id="P", bound_files=["reactant.log"], matched=True, quality=1.0),
        NodeBinding(
            node_id="TS",
            bound_files=["reactant.log", "ts_irc.log"],
            matched=True,
            quality=1.0,
        ),
    ]
    rep = audit_self_consistency(_sc_graph(), bindings, files, tmp_path)
    by_id = _checks_by_id(rep)
    # 水 opt+freq 是经验证的极小值 → 两个物种节点都覆盖
    assert by_id["R"].covered and by_id["R"].evidence_used == ["reactant.log"]
    assert by_id["P"].covered
    # 边：候选池里没有一阶鞍点频率块，也没有可验证的 IRC 端点几何 → 不覆盖
    edge = by_id["E1"]
    assert not edge.covered
    assert any("first-order saddle" in n for n in edge.notes)
    assert any("IRC" in n for n in edge.notes)
    assert rep.passed is False
    assert any("edge E1" in n for n in rep.notes)


def _fake_ts_frames(imag_freqs, irc_meta):
    frames = [FrameRecord(frame=0, frequencies_cm=imag_freqs + [100.0, 200.0])]
    return frames, irc_meta


def _hh_xyz(d):
    return f"2\n\nH 0.0 0.0 0.0\nH 0.0 0.0 {d:.2f}\n"


def _geo_frames(imag_freqs, d):
    """带几何的 opt 帧：双原子玩具体系，键长 d（Å）。"""
    frames = [FrameRecord(frame=0, frequencies_cm=imag_freqs + [100.0], xyz=_hh_xyz(d))]
    return frames, None


def _irc_frames(end_a_d, end_b_d):
    """双侧 IRC 端点帧（rx<0 / rx>0）；任一侧 None 表示该侧无帧。"""
    frames = []
    if end_a_d is not None:
        frames.append(FrameRecord(frame=0, reaction_coordinate=-0.5, xyz=_hh_xyz(end_a_d)))
    if end_b_d is not None:
        frames.append(FrameRecord(frame=1, reaction_coordinate=0.5, xyz=_hh_xyz(end_b_d)))
    return frames


# 严格档玩具几何：from-min d=1.0 / TS d=2.0 / to-min d=3.0（Å）；
# 合格 IRC 端点 1.5 / 2.5 分别落在 TS 与对应极小值之间。
_STRICT_FILES = [
    EvidenceFile(path="work/opt/calc-305.out.log", kind="gaussian"),
    EvidenceFile(path="work/opt/calc-306.out.log", kind="gaussian"),
    EvidenceFile(path="work/ts/calc-321.out.log", kind="gaussian"),
]
_STRICT_BINDINGS = [
    NodeBinding(
        node_id="R", bound_files=["work/opt/calc-305.out.log"], matched=True, quality=1.0
    ),
    NodeBinding(
        node_id="P", bound_files=["work/opt/calc-306.out.log"], matched=True, quality=1.0
    ),
    NodeBinding(
        node_id="TS", bound_files=["work/ts/calc-321.out.log"], matched=True, quality=1.0
    ),
]


@pytest.mark.parametrize(
    "imag_freqs,irc_frames,want_saddle,want_irc",
    [
        # 一阶鞍点 + 端点各自落在 TS 与对应极小值之间 -> 覆盖
        ([-500.0], _irc_frames(1.5, 2.5), True, True),
        # 单个虚频即为合法一阶鞍点：虚频大小不是判负条件（用户决策），
        # 是否"合适"由 IRC 方向证明承担，此处证明成立 -> 覆盖
        ([-50.0], _irc_frames(1.5, 2.5), True, True),
        # 两个虚频 -> 非一阶鞍点；没有 TS 几何，方向证明也无从谈起（双缺）
        ([-500.0, -300.0], _irc_frames(1.5, 2.5), False, False),
        # 鞍点成立但 b 端点不在 TS 与 to-min 之间 -> IRC 方向证明不成立
        ([-500.0], _irc_frames(1.5, 1.5), True, False),
        # 鞍点成立但 IRC 只有一侧 -> 无可验证的双向端点
        ([-500.0], _irc_frames(1.5, None), True, False),
    ],
)
def test_selfconsistency_saddle_logic(monkeypatch, imag_freqs, irc_frames, want_saddle, want_irc):
    def fake_frames_for(path):
        s = str(path)
        if "305" in s:
            return _geo_frames([], 1.0)
        if "306" in s:
            return _geo_frames([], 3.0)
        return _geo_frames(imag_freqs, 2.0)

    monkeypatch.setattr(selfconsistency, "_frames_for", fake_frames_for)
    monkeypatch.setattr(selfconsistency, "_irc_frames_for", lambda path: irc_frames)
    # 物种节点声明豁免，把判定隔离到边上（绑定仍提供方向证明的参考几何）
    graph = _sc_graph(R={"accessible": False}, P={"accessible": False})
    rep = audit_self_consistency(graph, _STRICT_BINDINGS, _STRICT_FILES, Path("."))
    edge = _checks_by_id(rep)["E1"]
    assert edge.covered is (want_saddle and want_irc)
    assert any("first-order saddle" in n for n in edge.notes) is (not want_saddle)
    assert any("IRC" in n for n in edge.notes) is (not want_irc)
    assert rep.passed is (want_saddle and want_irc)


def test_selfconsistency_roles_are_decided_by_content_not_filename(monkeypatch):
    """证据可用性按频率块内容判定：harness 日志命名（calc-N.out.log）不携带
    角色信息——含 1 虚频的即一阶鞍点证据，零虚频的即极小值证据。"""
    def fake_frames(path):
        # calc-296 是真 TS 日志（1 虚频），calc-292 是极小值（0 虚频）
        if "296" in str(path):
            return _fake_ts_frames([-164.95], None)
        return _fake_ts_frames([], None)

    monkeypatch.setattr(selfconsistency, "_frames_for", fake_frames)
    files = [
        EvidenceFile(path="runs/rc/.cloudra/calc-296.out.log", kind="orca"),
        EvidenceFile(path="runs/rc/.cloudra/calc-292.out.log", kind="orca"),
    ]
    bindings = [
        NodeBinding(
            node_id="R",
            bound_files=["runs/rc/.cloudra/calc-292.out.log"],
            matched=True,
            quality=1.0,
        ),
        NodeBinding(
            node_id="P",
            bound_files=["runs/rc/.cloudra/calc-292.out.log"],
            matched=True,
            quality=1.0,
        ),
        NodeBinding(
            node_id="TS",
            bound_files=["runs/rc/.cloudra/calc-296.out.log"],
            matched=True,
            quality=1.0,
        ),
    ]
    rep = audit_self_consistency(
        _sc_graph(), bindings, files, Path("."),
        SelfConsistencyRubric(irc_connects_endpoints=False),
    )
    by_id = _checks_by_id(rep)
    assert by_id["R"].covered
    assert by_id["R"].evidence_used == ["runs/rc/.cloudra/calc-292.out.log"]
    assert by_id["E1"].covered
    assert by_id["E1"].evidence_used == ["runs/rc/.cloudra/calc-296.out.log"]
    assert rep.passed is True


def test_selfconsistency_unbound_failed_attempts_do_not_veto(monkeypatch):
    """NI1 calc-315 回归：沙箱里未绑定的试错烂尾（4 虚频日志）不参与判定——
    未绑定的文件对本层不存在，绑定的合格证据有一条即覆盖。"""
    def fake_frames(path):
        s = str(path)
        if "315" in s:
            return _geo_frames([-1492.15, -702.92, -300.0, -50.0], 2.0)
        if "321" in s:
            return _geo_frames([-164.95], 2.0)
        if "306" in s:
            return _geo_frames([], 3.0)
        return _geo_frames([], 1.0)

    monkeypatch.setattr(selfconsistency, "_frames_for", fake_frames)
    monkeypatch.setattr(
        selfconsistency, "_irc_frames_for",
        lambda path: _irc_frames(1.5, 2.5) if "321" in str(path) else [],
    )
    files = [
        # 烂尾：在沙箱里但没有任何元素绑定它
        EvidenceFile(path="work/ts/.cloudra/calc-315.out.log", kind="gaussian"),
        EvidenceFile(path="work/ts/.cloudra/calc-321.out.log", kind="gaussian"),
        EvidenceFile(path="work/opt/.cloudra/calc-305.out.log", kind="gaussian"),
        EvidenceFile(path="work/opt/.cloudra/calc-306.out.log", kind="gaussian"),
    ]
    bindings = [
        NodeBinding(
            node_id="R",
            bound_files=["work/opt/.cloudra/calc-305.out.log"],
            matched=True,
            quality=1.0,
        ),
        NodeBinding(
            node_id="P",
            bound_files=["work/opt/.cloudra/calc-306.out.log"],
            matched=True,
            quality=1.0,
        ),
        NodeBinding(
            node_id="TS",
            bound_files=["work/ts/.cloudra/calc-321.out.log"],
            matched=True,
            quality=1.0,
        ),
    ]
    rep = audit_self_consistency(_sc_graph(), bindings, files, Path("."))
    assert rep.passed is True, rep.notes


def test_selfconsistency_bound_multi_imag_only_fails(monkeypatch):
    """绑到 TS 的证据全是多虚频（无一阶鞍点）→ 边不覆盖：any 语义豁免的是
    被取代的残留，不是拿高阶鞍点充数。"""
    monkeypatch.setattr(
        selfconsistency, "_frames_for",
        lambda path: _fake_ts_frames([-1492.15, -702.92, -300.0, -50.0], None),
    )
    graph = _sc_graph(R={"accessible": False}, P={"accessible": False})
    files = [EvidenceFile(path="work/ts/.cloudra/calc-315.out.log", kind="orca")]
    bindings = [
        NodeBinding(
            node_id="TS",
            bound_files=["work/ts/.cloudra/calc-315.out.log"],
            matched=True,
            quality=1.0,
        ),
    ]
    rep = audit_self_consistency(graph, bindings, files, Path("."))
    edge = _checks_by_id(rep)["E1"]
    assert not edge.covered
    assert any("first-order saddle" in n for n in edge.notes)
    assert rep.passed is False


def test_selfconsistency_any_saddle_among_bound_covers(monkeypatch):
    """候选池里即使绑着一条多虚频烂尾，只要另有一条一阶鞍点 + 方向证明成立的
    IRC 即覆盖。"""
    def fake_frames(path):
        s = str(path)
        if "315" in s:
            return _geo_frames([-1492.15, -702.92], 2.0)
        if "305" in s:
            return _geo_frames([], 1.0)
        if "306" in s:
            return _geo_frames([], 3.0)
        return _geo_frames([-164.95], 2.0)

    monkeypatch.setattr(selfconsistency, "_frames_for", fake_frames)
    monkeypatch.setattr(
        selfconsistency, "_irc_frames_for",
        lambda path: _irc_frames(1.5, 2.5) if "321" in str(path) else [],
    )
    graph = _sc_graph(R={"accessible": False}, P={"accessible": False})
    files = [
        EvidenceFile(path="calc-315.out.log", kind="gaussian"),
        EvidenceFile(path="calc-321.out.log", kind="gaussian"),
        EvidenceFile(path="calc-305.out.log", kind="gaussian"),
        EvidenceFile(path="calc-306.out.log", kind="gaussian"),
    ]
    bindings = [
        NodeBinding(
            node_id="R", bound_files=["calc-305.out.log"], matched=True, quality=1.0
        ),
        NodeBinding(
            node_id="P", bound_files=["calc-306.out.log"], matched=True, quality=1.0
        ),
        NodeBinding(
            node_id="TS",
            bound_files=["calc-315.out.log", "calc-321.out.log"],
            matched=True,
            quality=1.0,
        ),
    ]
    rep = audit_self_consistency(graph, bindings, files, Path("."))
    assert _checks_by_id(rep)["E1"].covered
    assert rep.passed is True


def test_selfconsistency_irc_direction_proof_required(monkeypatch):
    """严格档：光"双向有帧"不够——端点必须几何上位于 TS 与两端极小值之间；
    多份 IRC 里有一份证明成立即覆盖（any 语义）。"""
    def fake_frames(path):
        s = str(path)
        if "305" in s:
            return _geo_frames([], 1.0)
        if "306" in s:
            return _geo_frames([], 3.0)
        return _geo_frames([-164.95], 2.0)

    def fake_irc_frames(path):
        # 只有 IRC 日志才有 IRC 段；bad：两端都偏向 from-min 一侧（b 端不在
        # TS 与 to-min 之间）；good：合格
        s = str(path)
        if "irc" not in s:
            return []
        if "bad" in s:
            return _irc_frames(1.5, 1.6)
        return _irc_frames(1.5, 2.5)

    monkeypatch.setattr(selfconsistency, "_frames_for", fake_frames)
    monkeypatch.setattr(selfconsistency, "_irc_frames_for", fake_irc_frames)
    graph = _sc_graph(R={"accessible": False}, P={"accessible": False})
    files = [
        EvidenceFile(path="irc_bad.out.log", kind="gaussian"),
        EvidenceFile(path="irc_good.out.log", kind="gaussian"),
        EvidenceFile(path="calc-305.out.log", kind="gaussian"),
        EvidenceFile(path="calc-306.out.log", kind="gaussian"),
    ]
    bindings = [
        NodeBinding(
            node_id="R", bound_files=["calc-305.out.log"], matched=True, quality=1.0
        ),
        NodeBinding(
            node_id="P", bound_files=["calc-306.out.log"], matched=True, quality=1.0
        ),
        NodeBinding(
            node_id="TS",
            bound_files=["irc_bad.out.log", "irc_good.out.log"],
            matched=True,
            quality=1.0,
        ),
    ]
    rep = audit_self_consistency(graph, bindings, files, Path("."))
    assert rep.passed is True, rep.notes

    # 只有方向证明不成立的 IRC → IRC 缺项（鞍点项是覆盖的）
    bindings_bad = [
        bindings[0],
        bindings[1],
        NodeBinding(
            node_id="TS", bound_files=["irc_bad.out.log"], matched=True, quality=1.0
        ),
    ]
    rep_bad = audit_self_consistency(graph, bindings_bad, files, Path("."))
    edge = _checks_by_id(rep_bad)["E1"]
    assert not edge.covered
    assert any("IRC" in n for n in edge.notes)
    assert not any("first-order saddle" in n for n in edge.notes)


def test_selfconsistency_orca_irc_uses_endpoint_sidecars(monkeypatch):
    """ORCA 日志的 IRC 端点走边文件通道（终点文件/F-B 轨迹），与 Gaussian 的
    主日志帧通道分开；拿不到双侧端点几何时 IRC 缺项。"""
    def fake_frames(path):
        s = str(path)
        if "305" in s:
            return _geo_frames([], 1.0)
        if "306" in s:
            return _geo_frames([], 3.0)
        return _geo_frames([-164.95], 2.0)

    monkeypatch.setattr(selfconsistency, "_frames_for", fake_frames)
    # Gaussian 帧通道对 ORCA 文件不应被调用；ORCA 边文件通道返回合格端点
    monkeypatch.setattr(
        selfconsistency, "_irc_frames_for",
        lambda path: (_ for _ in ()).throw(AssertionError("wrong channel")),
    )
    good_ends = (
        (["H", "H"], [[0.0, 0.0, 0.0], [0.0, 0.0, 1.5]]),
        (["H", "H"], [[0.0, 0.0, 0.0], [0.0, 0.0, 2.5]]),
    )
    monkeypatch.setattr(
        selfconsistency, "_orca_irc_endpoint_geometries",
        lambda path: good_ends if "good" in str(path) else None,
    )
    graph = _sc_graph(R={"accessible": False}, P={"accessible": False})
    files = [
        EvidenceFile(path="irc_good.out.log", kind="orca"),
        EvidenceFile(path="irc_gap.out.log", kind="orca"),
        EvidenceFile(path="calc-305.out.log", kind="orca"),
        EvidenceFile(path="calc-306.out.log", kind="orca"),
    ]
    bindings = [
        NodeBinding(
            node_id="R", bound_files=["calc-305.out.log"], matched=True, quality=1.0
        ),
        NodeBinding(
            node_id="P", bound_files=["calc-306.out.log"], matched=True, quality=1.0
        ),
        NodeBinding(
            node_id="TS",
            bound_files=["irc_good.out.log", "irc_gap.out.log"],
            matched=True,
            quality=1.0,
        ),
    ]
    rep = audit_self_consistency(graph, bindings, files, Path("."))
    assert rep.passed is True, rep.notes

    # 双侧端点都拿不到（如方向明确未收敛留缺口）→ IRC 缺项
    bindings_gap = [
        bindings[0],
        bindings[1],
        NodeBinding(
            node_id="TS", bound_files=["irc_gap.out.log"], matched=True, quality=1.0
        ),
    ]
    rep_gap = audit_self_consistency(graph, bindings_gap, files, Path("."))
    edge = _checks_by_id(rep_gap)["E1"]
    assert not edge.covered
    assert any("IRC" in n for n in edge.notes)


def test_selfconsistency_unbound_element_requires_inaccessible_declaration():
    """每个 accessible 的元素都要有证据绑定；没有证据只有 accessible=false
    声明可以豁免。"""
    files: list[EvidenceFile] = []
    # 未绑定且未声明 → 挂
    rep = audit_self_consistency(_sc_graph(), [], files, Path("."))
    assert rep.passed is False
    assert any("species R: no evidence bound" in n for n in rep.notes)
    # 全部声明 accessible=false → 豁免通过
    graph = _sc_graph(
        R={"accessible": False}, TS={"accessible": False}, P={"accessible": False}
    )
    graph = GoldMechanismGraph.model_validate({
        "nodes": [n.model_dump() for n in graph.nodes],
        "edges": [
            {**e.model_dump(by_alias=True), "accessible": False} for e in graph.edges
        ],
    })
    rep2 = audit_self_consistency(graph, [], files, Path("."))
    assert rep2.passed is True, rep2.notes
    assert all(c.declared_inaccessible for c in rep2.checks)


def test_selfconsistency_edge_via_inaccessible_ts_is_exempt():
    """有效可达性传导进自洽：交付把不可达标在 TS 节点上（边保持默认
    accessible=true）时，经由它的边视同 declared_inaccessible 豁免——
    与图分/accuracy 同一口径（edge_effectively_accessible）。"""
    files: list[EvidenceFile] = []
    # TS 节点 false、边不标：边豁免；TS 节点随豁免
    graph = _sc_graph(R={"accessible": False}, TS={"accessible": False}, P={"accessible": False})
    rep = audit_self_consistency(graph, [], files, Path("."))
    assert rep.passed is True, rep.notes
    edge = _checks_by_id(rep)["E1"]
    assert edge.declared_inaccessible and edge.covered
    assert any("effectively inaccessible" in n for n in edge.notes)
    # 对照：TS 可达且边未标 -> 边不豁免（无证据判负）
    rep2 = audit_self_consistency(_sc_graph(R={"accessible": False}, P={"accessible": False}), [], files, Path("."))
    edge2 = _checks_by_id(rep2)["E1"]
    assert not edge2.declared_inaccessible and not edge2.covered


# --- 题库可复现性 ---


def test_easy_tasks_regenerate_identically():
    """版本化题库必须与生成器输出一致（generator 是唯一事实来源）。"""
    tasks = gen_easy_tasks.parse_easy_md(gen_easy_tasks.DEFAULT_SRC)
    for t in tasks:
        committed = gen_easy_tasks.DEFAULT_OUT / f"{t.task_id}.json"
        assert committed.is_file(), f"missing committed task file: {committed}"
        regenerated = json.loads(json.dumps(t.model_dump(mode="json", by_alias=True)))
        assert json.loads(committed.read_text(encoding="utf-8")) == regenerated
        # 四档共用 xtb+pm7+b3lyp/def2svp 白名单。
        assert t.method_policy.allowed_methods == ["xtb", "pm7", "b3lyp/def2svp"]


def test_normal_tasks_regenerate_identically():
    """normal 档题库（10 题；U8/R4 已移入 impossible，B1 已补入）必须与
    生成器输出一致。"""
    pytest.importorskip("rdkit")  # 生成器的映射校验依赖 RDKit；CI 只装 dev extra
    from cloudra.benchmark import gen_normal_tasks

    tasks = gen_normal_tasks.parse_normal_md(gen_normal_tasks.DEFAULT_SRC)
    assert len(tasks) == 10
    for t in tasks:
        committed = gen_normal_tasks.DEFAULT_OUT / f"{t.task_id}.json"
        assert committed.is_file(), f"missing committed task file: {committed}"
        regenerated = json.loads(json.dumps(t.model_dump(mode="json", by_alias=True)))
        assert json.loads(committed.read_text(encoding="utf-8")) == regenerated
        assert t.method_policy.allowed_methods == ["xtb", "pm7", "b3lyp/def2svp"]


def test_malonic_decarboxylation_gold_edges():
    pytest.importorskip("rdkit")
    from cloudra.benchmark import gen_normal_tasks

    (task,) = gen_normal_tasks.parse_normal_md(gen_normal_tasks.DEFAULT_SRC, only={"B1"})
    first, second = task.gold.mechanism_graph.edges
    assert first.barrier_kcal_mol == 27.94
    assert second.barrier_kcal_mol is None
    assert [2, 4] in first.bond_changes.break_
    assert [3, 8] in first.bond_changes.break_
    assert [6, 8] in first.bond_changes.form
    assert [4, 8] in second.bond_changes.form


def test_aromatic_claisen_terminal_allyl_atom_forms_ortho_bond():
    pytest.importorskip("rdkit")
    from cloudra.benchmark import gen_normal_tasks

    task = next(
        t for t in gen_normal_tasks.parse_normal_md(gen_normal_tasks.DEFAULT_SRC)
        if t.task_id == "NQ1"
    )
    edge = task.gold.mechanism_graph.edges[0]
    assert [1, 6] in edge.bond_changes.form
    assert [3, 4] in edge.bond_changes.break_
    assert [3, 6] not in edge.bond_changes.form
    assert edge.barrier_kcal_mol == 37.75


def test_aqueous_imine_barrier_stays_separate_from_gas_phase_task():
    pytest.importorskip("rdkit")
    from cloudra.benchmark import gen_normal_tasks

    tasks = {
        t.task_id: t
        for t in gen_normal_tasks.parse_normal_md(gen_normal_tasks.DEFAULT_SRC, only={"I1", "I5"})
    }
    gas_edges = tasks["NI1"].gold.mechanism_graph.edges
    aqueous_edges = tasks["NI5"].gold.mechanism_graph.edges
    assert [e.barrier_kcal_mol for e in gas_edges] == [27.9, 57.67]
    assert [e.barrier_kcal_mol for e in aqueous_edges] == [None, 3.59, 31.2]
    assert [e.to_node for e in aqueous_edges[:2]] == ["NI5_I1", "NI5_I2"]
    assert [1, 3] in aqueous_edges[0].bond_changes.form
    assert [3, 5] in aqueous_edges[1].bond_changes.break_
    assert [2, 5] in aqueous_edges[1].bond_changes.form
    assert tasks["NI5"].rubric.accuracy.enabled


def test_passerini_first_edge_couples_proton_transfer_and_isocyanide_attack():
    pytest.importorskip("rdkit")
    from cloudra.benchmark import gen_normal_tasks

    task = gen_normal_tasks.parse_normal_md(gen_normal_tasks.DEFAULT_SRC, only={"U5"})[0]
    edges = task.gold.mechanism_graph.edges
    assert len(edges) == 3
    assert edges[0].barrier_kcal_mol == 8.21
    assert [5, 6] in edges[0].bond_changes.break_
    assert [2, 6] in edges[0].bond_changes.form
    assert [1, 9] in edges[0].bond_changes.form
    assert edges[1].barrier_kcal_mol is None


def test_pinacol_dehydration_and_migration_are_separate_edges():
    pytest.importorskip("rdkit")
    from cloudra.benchmark import gen_normal_tasks

    task = gen_normal_tasks.parse_normal_md(gen_normal_tasks.DEFAULT_SRC, only={"R1"})[0]
    edges = task.gold.mechanism_graph.edges
    assert [e.barrier_kcal_mol for e in edges] == [None, None, 5.16, 5.74]
    assert [4, 6] in edges[1].bond_changes.break_
    assert [7, 8] in edges[2].bond_changes.break_
    assert [4, 8] in edges[2].bond_changes.form
    carbocation = next(n for n in task.gold.mechanism_graph.nodes if n.id == "NR1_I2")
    assert "[C+]" in carbocation.smiles[0]


def test_hard_tasks_regenerate_identically():
    """hard 档题库（v3：10 题立体化学档）必须与生成器输出一致。"""
    pytest.importorskip("rdkit")  # 生成器的映射校验依赖 RDKit；CI 只装 dev extra
    from cloudra.benchmark import gen_hard_tasks

    tasks = gen_hard_tasks.parse_hard_md(gen_hard_tasks.DEFAULT_SRC)
    assert len(tasks) == 10
    for t in tasks:
        committed = gen_hard_tasks.DEFAULT_OUT / f"{t.task_id}.json"
        assert committed.is_file(), f"missing committed task file: {committed}"
        regenerated = json.loads(json.dumps(t.model_dump(mode="json", by_alias=True)))
        assert json.loads(committed.read_text(encoding="utf-8")) == regenerated
        # hard 档一律 stereo 计代价
        assert t.rubric.graph_similarity.stereo_tier_rule == "hard_stereo_costly"
        assert t.method_policy.allowed_methods == ["xtb", "pm7", "b3lyp/def2svp"]


def test_hh1_shared_endpoint_channels():
    pytest.importorskip("rdkit")
    from cloudra.benchmark import gen_hard_tasks

    task = gen_hard_tasks.parse_hard_md(gen_hard_tasks.DEFAULT_SRC, only={"H1"})[0]
    graph = task.gold.mechanism_graph
    assert len(graph.nodes) == 4  # R, P, and two distinct transition states
    assert len(graph.edges) == 2
    assert {e.channel: e.barrier_kcal_mol for e in graph.edges} == {
        "syn": 23.01, "anti": 32.36,
    }
    assert len({(e.from_node, e.to_node) for e in graph.edges}) == 1
    assert len({e.via for e in graph.edges}) == 2
    committed = json.loads((gen_hard_tasks.DEFAULT_OUT / "HH1.json").read_text(encoding="utf-8"))
    assert committed == task.model_dump(mode="json", by_alias=True)
    one_path = GoldMechanismGraph(
        nodes=[n for n in graph.nodes if n.id != "HH1_TSM1"],
        edges=[graph.edges[0]],
    )
    assert mechanism_similarity(graph, graph, GedConfig()).score == pytest.approx(1.0)
    assert mechanism_similarity(one_path, graph, GedConfig()).score < 1.0


def test_hf1_regenerated_gold_scores_barriers():
    pytest.importorskip("rdkit")
    from cloudra.benchmark import gen_hard_tasks

    task = gen_hard_tasks.parse_hard_md(gen_hard_tasks.DEFAULT_SRC, only={"F1"})[0]
    assert not task.gold.reference_properties  # provenance is not a scored property
    assert {e.channel: e.barrier_kcal_mol for e in task.gold.mechanism_graph.edges} == {
        "directed_face": 16.82, "opposite_face": 20.70,
    }
    assert task.gold.selectivity.spread_kcal_mol == pytest.approx(3.87)


def test_impossible_tasks_regenerate_identically():
    """impossible 档只生成 11 道 I 题；每题至少一个不可达节点。"""
    pytest.importorskip("rdkit")  # 生成器的映射校验依赖 RDKit；CI 只装 dev extra
    from cloudra.benchmark import gen_impossible_tasks

    tasks = gen_impossible_tasks.parse_impossible_md(gen_impossible_tasks.DEFAULT_SRC)
    assert len(tasks) == 12
    assert sum(t.task_id.startswith("I") for t in tasks) == 12
    assert not list(gen_impossible_tasks.DEFAULT_OUT.glob("S*.json"))
    protocol = 'mark the corresponding node or edge "accessible": false'
    for t in tasks:
        committed = gen_impossible_tasks.DEFAULT_OUT / f"{t.task_id}.json"
        assert committed.is_file(), f"missing committed task file: {committed}"
        regenerated = json.loads(json.dumps(t.model_dump(mode="json", by_alias=True)))
        assert json.loads(committed.read_text(encoding="utf-8")) == regenerated
        assert t.method_policy.allowed_methods == ["xtb", "pm7", "b3lyp/def2svp"]
        # accessible=false 协议句全档同款、一字不动
        assert protocol in t.prompt.query, t.task_id
        graph = t.gold.mechanism_graph
        assert any(not n.accessible for n in graph.nodes), t.task_id
    ib9 = next(t for t in tasks if t.task_id == "IB9")
    assert [e.barrier_kcal_mol for e in ib9.gold.mechanism_graph.edges] == [14.74, None]


def test_query_declares_electronic_barrier_type():
    """四档题面统一声明能垒为电子能差 ΔE‡（不含 ZPE/热校正），各自相对该步
    起点最小值（双分子：预反应络合物）。"""
    pytest.importorskip("rdkit")
    from cloudra.benchmark import gen_hard_tasks, gen_impossible_tasks, gen_normal_tasks

    clause = "electronic energy differences (ΔE‡) in kcal/mol, without ZPE or thermal corrections"
    easy = gen_easy_tasks.parse_easy_md(gen_easy_tasks.DEFAULT_SRC)
    normal = gen_normal_tasks.parse_normal_md(gen_normal_tasks.DEFAULT_SRC)
    hard = gen_hard_tasks.parse_hard_md(gen_hard_tasks.DEFAULT_SRC)
    impossible = gen_impossible_tasks.parse_impossible_md(gen_impossible_tasks.DEFAULT_SRC)
    for t in (*easy, *normal, *hard):
        assert clause in t.prompt.query, t.task_id
        assert "that step's own starting minimum" in t.prompt.query, t.task_id
    # impossible 机理类同样声明；性质/态序类走 properties 交付（见下）
    assert clause in next(t for t in impossible if t.task_id == "IA1").prompt.query


def test_conditions_modeling_guidance():
    """条件建模要求句（用户口径）：要求 agent **在允许方法内尽量逼近题面描述
    的真实条件**，但不指定具体溶剂模型（建模是 Cloudra 自己的权衡）；含明确
    温度时另加"只报电子能垒、不加该温度热校正"的评分口径句。

    - "kinetics" 等含 k 的词不得误判为开尔文温度。"""
    from cloudra.benchmark.query_builder import conditions_modeling_guidance

    base = (
        "Within the allowed methods, model the system so that it approximates the "
        "real conditions stated above as closely as the level of theory permits."
    )
    assert conditions_modeling_guidance("gas phase") == base
    assert conditions_modeling_guidance("20-30 mol% (S)-proline, DMSO, room temperature") == base
    g = conditions_modeling_guidance("THF, -20 degC to rt, catalytic")
    assert g.startswith(base) and "do not add thermal corrections" in g
    g = conditions_modeling_guidance("gas phase, 403-448 K")
    assert g.startswith(base) and "do not add thermal corrections" in g
    assert "do not add thermal corrections" not in conditions_modeling_guidance("gas phase kinetics")


def test_hard_query_does_not_leak_stereo_answers():
    """hard 泄题守卫：题面/system 产物 SMILES 去立体（constitution-only），
    题名不含答案词；gold 图节点保留立体 SMILES 不动。"""
    pytest.importorskip("rdkit")
    from cloudra.benchmark import gen_hard_tasks

    tasks = gen_hard_tasks.parse_hard_md(gen_hard_tasks.DEFAULT_SRC)
    leaked_names = ("outward", "inward", " cis", " trans-di", ", cis", ", syn", "chair preference")
    for t in tasks:
        assert t.system.products, t.task_id
        for p in t.system.products:
            assert "@" not in p and "/" not in p and "\\" not in p, (t.task_id, p)
        assert f"product SMILES: {'.'.join(t.system.products)}" in t.prompt.query
        for w in leaked_names:
            assert w not in t.name, (t.task_id, w)
    by_id = {t.task_id: t for t in tasks}
    gold_smiles = [s for n in by_id["HA1"].gold.mechanism_graph.nodes for s in n.smiles]
    assert any("/" in s or "\\" in s for s in gold_smiles)
    # 反应物立体是给定条件（HA6 底物 trans-3,4-二甲基），不在去立体范围
    assert any("@" in r for r in by_id["HA6"].system.reactants)


def test_hard_selectivity_qualitative_contract():
    """hard 选择性契约：query 要求 channel/favored 结构化声明并声明定性计分；
    gold selectivity 带 favored_channel，与主线立体决定边的 channel 对齐。"""
    pytest.importorskip("rdkit")
    from cloudra.benchmark import gen_hard_tasks

    tasks = gen_hard_tasks.parse_hard_md(gen_hard_tasks.DEFAULT_SRC)
    for t in tasks:
        assert "`channel`" in t.prompt.query and "`favored: true`" in t.prompt.query
        assert "scored qualitatively" in t.prompt.query
        assert "not scored numerically" in t.prompt.query
        if t.gold.selectivity is None:
            continue
        assert t.gold.selectivity.favored_channel
        edges = t.gold.mechanism_graph.edges
        favored = [e for e in edges if e.favored is True]
        unfavored = [e for e in edges if e.favored is False]
        assert len(favored) == 1
        assert favored[0].channel == t.gold.selectivity.favored_channel
        assert unfavored and all(e.channel for e in unfavored)


def test_impossible_deliverable_clause_by_kind():
    """impossible 交付句按 deliverable_kind 生成：机理类走 RDS 边能垒，性质/
    态序类走物种节点 properties（键带单位，字符串值允许）；accessible=false
    协议句全档同款、一字不动，拒答契约句已随 refusal 线删除。"""
    pytest.importorskip("rdkit")
    from cloudra.benchmark import gen_impossible_tasks

    tasks = gen_impossible_tasks.parse_impossible_md(gen_impossible_tasks.DEFAULT_SRC)
    by_id = {t.task_id: t for t in tasks}
    protocol = 'mark the corresponding node or edge "accessible": false'
    for t in tasks:
        assert protocol in t.prompt.query, t.task_id
        assert "refusal" not in t.prompt.query, t.task_id
    # 机理类维持边能垒声明
    assert "as `barrier_kcal_mol`" in by_id["IA1"].prompt.query
    assert "rate-determining step's edge" in by_id["IA1"].prompt.query
    # 机理类附带产物节点性质（IA7 反应能）
    assert "`reaction_energy_kcal_mol` in a `properties` object on the product node" in by_id["IA7"].prompt.query
    # 性质类无边题（ID2 FOOF）：挂物种节点而非边
    assert "`properties` object on the reactant species node" in by_id["ID2"].prompt.query
    assert "`f_o_bond_length_angstrom`" in by_id["ID2"].prompt.query
    # 态序类：state_ordering 字符串
    assert "`state_ordering`" in by_id["IC3"].prompt.query


def test_runner_wires_stereo_tier_rule():
    """runner._ged_config_for 必须把 rubric 的 stereo_tier_rule 接到 GedConfig.stereo_free。"""
    from cloudra.benchmark.runner import BenchmarkRunner
    from cloudra.benchmark.schema import GraphSimilarityRubric

    runner = BenchmarkRunner.__new__(BenchmarkRunner)
    runner.ged_config = GedConfig()

    class _FakeTask:
        pass

    hard_task = _FakeTask()
    hard_task.rubric = type("R", (), {"graph_similarity": GraphSimilarityRubric(stereo_tier_rule="hard_stereo_costly")})()
    assert runner._ged_config_for(hard_task).stereo_free is False

    easy_task = _FakeTask()
    easy_task.rubric = type("R", (), {"graph_similarity": GraphSimilarityRubric()})()
    assert runner._ged_config_for(easy_task).stereo_free is True


def test_gold_selectivity_reference_roundtrip():
    """SelectivityReference（hard 档 ΔΔ 选择性锚点）schema 往返与默认值。"""
    from cloudra.benchmark.schema import GoldSpec, SelectivityReference

    gold = GoldSpec(
        mechanism_graph=GoldMechanismGraph(nodes=[]),
        selectivity=SelectivityReference(
            spread_kcal_mol=2.0,
            minor_channel="inward rotation -> (Z)-diene",
        ),
    )
    dumped = gold.model_dump(mode="json")
    assert dumped["selectivity"]["spread_kcal_mol"] == 2.0
    assert dumped["selectivity"]["minor_channel"] == "inward rotation -> (Z)-diene"
    assert dumped["reference_properties"] == {}
    back = GoldSpec.model_validate(dumped)
    assert back.selectivity.spread_kcal_mol == 2.0
    # 无选择性锚点时默认 None
    plain = GoldSpec(mechanism_graph=GoldMechanismGraph(nodes=[]))
    assert plain.selectivity is None


# --- 方法白名单 policy stage + runtime_v2 后端接线 ---


def test_referenced_input_paths_extraction():
    from cloudra.benchmark.method_policy import referenced_input_paths

    cmd = (
        "g16 ts_opt.gjf && orca run.inp > run.out\n"
        "cat > new.gjf <<'EOF'\n#p external=\"mace\" opt\nEOF\n"
    )
    refs = referenced_input_paths(cmd)
    assert "ts_opt.gjf" in refs
    assert "run.inp" in refs
    # 写入目标也会出现；调用方按 is_file 过滤，其内容已被 heredoc 抽取覆盖
    assert "new.gjf" in refs
    assert referenced_input_paths("ls -la") == []


def _stage_ctx(workspace: Path):
    from cloudra.runtime_v2.policies.base import PipelineContext
    from cloudra.runtime_v2.schemas import (
        AgentCapabilities,
        AgentSession,
        PermissionSet,
        RuntimeSettings,
    )

    agent = AgentSession(id="as_b", project_id="prj", role_id="coordinator", display_name="c")
    return PipelineContext(
        agent=agent,
        run_id="run1",
        settings_snapshot=RuntimeSettings(),
        capabilities=AgentCapabilities(permissions=PermissionSet(), tools=["*"]),
        inbox_messages=[],
        emit=lambda *_a, **_k: None,
        workspace_dir=str(workspace),
    )


@pytest.mark.asyncio
async def test_method_policy_stage_blocks_and_allows(tmp_path):
    from cloudra.benchmark.policy_stage import MethodPolicyStage
    from cloudra.runtime_v2.policies.base import ToolCall

    stage = MethodPolicyStage(MethodPolicy(), base_dir=tmp_path)
    ctx = _stage_ctx(tmp_path)

    # bash heredoc 写非白名单方法 -> 拦
    cmd = "cat > ts.gjf <<'EOF'\n#p b3lyp/6-31g* opt\n\nt\n\n0 1\nC 0 0 0\nEOF\n"
    res = await stage.before_tool(ctx, ToolCall(id="c1", name="bash", arguments={"command": cmd}))
    assert res.outcome == "block" and "b3lyp" in res.message

    # 白名单方法（xTB 路由）-> 放行
    cmd_ok = "cat > ts.inp <<'EOF'\n! XTB2 OPT FREQ\n* xyz 0 1\nC 0 0 0\n*\nEOF\n"
    res = await stage.before_tool(ctx, ToolCall(id="c2", name="bash", arguments={"command": cmd_ok}))
    assert res.outcome == "allow"

    # 引用磁盘已有输入（g16 evil.gjf）-> 查文件内容，非白名单 -> 拦
    (tmp_path / "evil.gjf").write_text("#p b3lyp/6-31g* opt\n\nt\n\n0 1\nC 0 0 0\n")
    res = await stage.before_tool(ctx, ToolCall(id="c3", name="bash", arguments={"command": "g16 evil.gjf"}))
    assert res.outcome == "block"

    # submit_compute_job 层：按 input_file 内容判定（相对路径基于沙箱解析）
    (tmp_path / "ok.inp").write_text("! XTB2 OPT\n* xyz 0 1\nC 0 0 0\n*\n")
    res = await stage.before_tool(ctx, ToolCall(id="c4", name="submit_compute_job", arguments={"input_file": "ok.inp"}))
    assert res.outcome == "allow"
    res = await stage.before_tool(ctx, ToolCall(id="c5", name="submit_compute_job", arguments={"input_file": "evil.gjf"}))
    assert res.outcome == "block"

    # 与拦截层无关的工具不受影响
    res = await stage.before_tool(ctx, ToolCall(id="c6", name="write", arguments={}))
    assert res.outcome == "allow"

    # Retired wire name bashtools is not bash policy — on-disk QM refs are not checked here
    # (unknown-tool hint is the executor's job; this stage must not dual-name treat it).
    res = await stage.before_tool(
        ctx, ToolCall(id="c7", name="bashtools", arguments={"command": "g16 evil.gjf"})
    )
    assert res.outcome == "allow"


@pytest.mark.asyncio
async def test_unattended_stage_blocks_ask_user_fail_closed(tmp_path):
    """GH #31：unattended 下 ask_user 被 fail-closed 拦截（block 反馈，绝不进
    waiting_input）；其他工具与未开 unattended 的 agent 不受影响。"""
    from cloudra.runtime_v2.policies.base import ToolCall
    from cloudra.runtime_v2.policies.unattended import UnattendedStage

    ctx = _stage_ctx(tmp_path)
    ctx.settings.unattended = True
    stage = UnattendedStage()

    res = await stage.before_tool(
        ctx, ToolCall(id="a1", name="ask_user", arguments={"question": "which?"})
    )
    assert res.outcome == "block"
    assert "unattended" in res.message

    res = await stage.before_tool(ctx, ToolCall(id="a2", name="stop", arguments={}))
    assert res.outcome == "allow"

    ctx.settings.unattended = False
    res = await stage.before_tool(
        ctx, ToolCall(id="a3", name="ask_user", arguments={"question": "which?"})
    )
    assert res.outcome == "allow"


# --- runtime_v2 后端端到端（FakeLLM，无网络） ---

class _ScriptedLLM:
    def __init__(self, responses):
        self.responses = list(responses)

    async def complete(self, agent, messages, tools, **_kwargs):
        assert self.responses, "no scripted LLM response left"
        return self.responses.pop(0)


class _RecordingTools:
    def __init__(self):
        self.calls: list[str] = []

    async def execute(self, agent, call):
        from cloudra.runtime_v2.policies.base import ToolResult

        self.calls.append(call.name)
        return ToolResult(is_success=True, summary="ok")


def _tiny_task(**kwargs) -> TaskSpec:
    from cloudra.benchmark.schema import GoldSpec, PromptSpec, SystemSpec
    from cloudra.runtime_v2.schemas import OrchestrationMode

    return TaskSpec(
        task_id="BENCH_T",
        tier="easy",
        prompt=PromptSpec(query="do it", orchestration_mode=OrchestrationMode.STANDARD),
        system=SystemSpec(reactants=["C"]),
        gold=GoldSpec(mechanism_graph=_graph(["C"], ["C"])),
        **kwargs,
    )


def test_backend_runs_to_terminal_and_scores_from_deliverables(tmp_path, monkeypatch):
    from cloudra.benchmark.backend import RuntimeV2Backend
    from cloudra.runtime_v2.adapters import legacy_default_runtime_settings
    from cloudra.runtime_v2.policies.base import ToolCall as PToolCall
    from cloudra.runtime_v2.schemas import InvocationProtocol
    from cloudra.runtime_v2.turn_pipeline import LLMResponse

    monkeypatch.setattr(
        "cloudra.runtime_v2.adapters.legacy_default_runtime_settings",
        lambda: legacy_default_runtime_settings().model_copy(
            update={"invocation_protocol": InvocationProtocol.TRADITIONAL}
        ),
    )

    llm = _ScriptedLLM([
        LLMResponse(
            content="",
            tool_calls=[PToolCall(
                id="t1",
                name="bash",
                arguments={"command": "cat > ts.gjf <<'EOF'\n#p b3lyp/6-31g* opt\n\nt\n\n0 1\nEOF\n"},
            )],
        ),
        LLMResponse(content="Done. The computed barrier is 12.3 kcal/mol."),
    ])
    tools = _RecordingTools()
    backend = RuntimeV2Backend(
        llm=llm,
        tools=tools,
        start_scheduler=False,
        poll_interval_s=0.01,
        run_timeout_s=30.0,
        stuck_grace_s=5.0,
    )
    result = backend(
        _tiny_task(method_policy={"allowed_methods": ["xtb"]}),
        tmp_path / "sandbox",
    )
    assert next(iter(backend.last_core.agents.values())).settings.clean_context is True
    # 后端不再回传任何供评分的文本/数字：评分输入只有沙箱交付物
    assert result is None
    core = backend.last_core
    agent = next(iter(core.agents.values()))
    assert agent.state.value == "succeeded"
    messages = [
        str((e.data or {}).get("content") or "")
        for e in core.event_log.query_session(agent.id)
        if e.type == "agent.message_emitted"
    ]
    assert any("12.3 kcal/mol" in m for m in messages)  # 仅作审计留痕
    # b3lyp 调用被 MethodPolicyStage 拦截，工具从未真正执行
    assert tools.calls == []


def test_cli_backend_starts_and_closes_compute_notifier(tmp_path, monkeypatch):
    from cloudra.benchmark.backend import RuntimeV2Backend
    from cloudra.runtime_v2.compute_notify import ComputeNotifyBroker
    from cloudra.runtime_v2.turn_pipeline import LLMResponse

    calls = []
    original_start = ComputeNotifyBroker.start
    original_close = ComputeNotifyBroker.close

    async def start(self):
        calls.append("start")
        await original_start(self)

    async def close(self):
        calls.append("close")
        await original_close(self)

    monkeypatch.setattr(ComputeNotifyBroker, "start", start)
    monkeypatch.setattr(ComputeNotifyBroker, "close", close)
    backend = RuntimeV2Backend(
        llm=_ScriptedLLM([LLMResponse(content="done")]),
        tools=_RecordingTools(), start_scheduler=False,
        poll_interval_s=0.01, run_timeout_s=5.0, stuck_grace_s=1.0,
    )
    backend(_tiny_task(), tmp_path / "sandbox")
    assert calls == ["start", "close"]


def test_cli_backend_timeout_survives_finished_agent_cancel_rejection(tmp_path, monkeypatch):
    import asyncio

    from cloudra.benchmark.backend import RuntimeV2Backend
    from cloudra.benchmark.watch import RunWatcher
    from cloudra.runtime_v2.schemas import AgentState
    from cloudra.runtime_v2.turn_pipeline import LLMResponse

    async def timeout_after_agent_finishes(self, core, agent, cancel):
        for _ in range(100):
            if agent.state is AgentState.SUCCEEDED:
                break
            await asyncio.sleep(0.01)
        assert agent.state is AgentState.SUCCEEDED
        await cancel("benchmark run timeout (test)")
        return "benchmark run timeout (test)"

    monkeypatch.setattr(RunWatcher, "wait", timeout_after_agent_finishes)
    backend = RuntimeV2Backend(
        llm=_ScriptedLLM([LLMResponse(content="done")]),
        tools=_RecordingTools(), start_scheduler=False,
        poll_interval_s=0.01, run_timeout_s=5.0, stuck_grace_s=1.0,
    )
    with pytest.raises(TimeoutError, match="benchmark run timeout"):
        backend(_tiny_task(), tmp_path / "sandbox")
    assert any(
        event.type == "command.rejected"
        and event.data.get("command_type") == "agent.cancel"
        for event in backend.last_core.event_log
    )


def test_backend_unattended_ask_user_blocked_without_parking(tmp_path, monkeypatch):
    """GH #31 端到端：agent 调 ask_user → UnattendedStage 拦截并以 block 反馈
    继续，全程绝不进入 waiting_input，最终消息与能垒正常提取。"""
    from cloudra.benchmark.backend import RuntimeV2Backend
    from cloudra.runtime_v2.adapters import legacy_default_runtime_settings
    from cloudra.runtime_v2.policies.base import ToolCall as PToolCall
    from cloudra.runtime_v2.schemas import InvocationProtocol
    from cloudra.runtime_v2.turn_pipeline import LLMResponse

    monkeypatch.setattr(
        "cloudra.runtime_v2.adapters.legacy_default_runtime_settings",
        lambda: legacy_default_runtime_settings().model_copy(
            update={"invocation_protocol": InvocationProtocol.TRADITIONAL}
        ),
    )

    llm = _ScriptedLLM([
        LLMResponse(
            content="",
            tool_calls=[PToolCall(
                id="a1",
                name="ask_user",
                arguments={"question": "Which pathway should I follow?"},
            )],
        ),
        LLMResponse(content="Proceeded autonomously. The barrier is 9.8 kcal/mol."),
    ])
    backend = RuntimeV2Backend(
        llm=llm,
        tools=_RecordingTools(),
        start_scheduler=False,
        poll_interval_s=0.01,
        run_timeout_s=30.0,
        stuck_grace_s=5.0,
    )
    result = backend(_tiny_task(), tmp_path / "sandbox")

    core = backend.last_core
    agent = next(iter(core.agents.values()))
    assert agent.settings.unattended is True
    states = [
        e.data.get("to")
        for e in core.event_log.query_session(agent.id, types={"agent.state_changed"})
    ]
    assert "waiting_input" not in states
    assert result is None
    core = backend.last_core
    agent = next(iter(core.agents.values()))
    messages = [
        str((e.data or {}).get("content") or "")
        for e in core.event_log.query_session(agent.id)
        if e.type == "agent.message_emitted"
    ]
    assert any("Proceeded autonomously" in m for m in messages)


def _last_agent_id(core) -> str:
    return next(iter(core.agents))


# --- 证据绑定的 partial credit（质子化/电荷态变体） ---


def _graph_with_ts(r_smiles, p_smiles):
    return GoldMechanismGraph(
        nodes=[
            MechanismNode(id="R", role=NodeRole.REACTANT, smiles=r_smiles),
            MechanismNode(id="TS", role=NodeRole.TRANSITION_STATE, smiles=[]),
            MechanismNode(id="P", role=NodeRole.PRODUCT, smiles=p_smiles),
        ],
        edges=[MechanismEdge(id="E", **{"from": "R", "to": "P"}, via="TS")],
    )


def test_binding_protonation_variant_partial_credit():
    """质子化变体（[OH3+] vs O、乙酸根 vs 乙酸）给 partial 分而非判零；
    真不同物种仍不绑。TS 继承较弱端点的质量。"""
    pytest.importorskip("rdkit")  # 质子化骨架通道依赖 RDKit；CI 只装 dev extra
    from cloudra.benchmark.integrity import bind_graph_to_evidence

    graph = _graph_with_ts(["[OH3+]"], ["CC(=O)[O-]"])
    files = [
        EvidenceFile(path="rc.log", smiles_found=["O"]),          # 质子化变体（指纹退化 -> 扣满 0.3）
        EvidenceFile(path="pc.log", smiles_found=["CC(=O)O"]),    # 质子化变体（tanimoto 0.5 -> 扣 0.15）
    ]
    bindings = {b.node_id: b for b in bind_graph_to_evidence(graph, files)}
    assert bindings["R"].matched and bindings["R"].quality == pytest.approx(0.7)
    assert bindings["P"].matched and bindings["P"].quality == pytest.approx(0.85)
    assert bindings["TS"].matched and bindings["TS"].quality == pytest.approx(0.7)  # 继承较弱端点

    # 真不同物种不绑（乙烷 vs 乙烯骨架不同）
    files_bad = [EvidenceFile(path="rc.log", smiles_found=["C=C"]),
                 EvidenceFile(path="pc.log", smiles_found=["CC(=O)O"])]
    bindings_bad = {b.node_id: b for b in bind_graph_to_evidence(graph, files_bad)}
    assert not bindings_bad["R"].matched and bindings_bad["R"].quality == 0.0
    assert not bindings_bad["TS"].matched  # 端点未绑 -> TS 不绑


def test_binding_full_match_quality_one():
    """指纹/哈希级匹配（含 kekulé 写法差异）仍是满分。"""
    from cloudra.benchmark.integrity import bind_graph_to_evidence

    graph = _graph_with_ts(["c1ccccc1"], ["C1=CC=CC=C1"])
    files = [EvidenceFile(path="a.log", smiles_found=["C1=CC=CC=C1"]),
             EvidenceFile(path="b.log", smiles_found=["c1ccccc1"])]
    bindings = {b.node_id: b for b in bind_graph_to_evidence(graph, files)}
    assert all(b.matched and b.quality == 1.0 for b in bindings.values())


def test_integrity_report_binding_quality_enters_graph_score(tmp_path):
    """端到端：质子化变体证据 -> 逐节点绑定质量 q<1，runner 把质量图并进图分
    （有效节点代价 = 1-(1-subst)·q）而不是判零或全局乘性扣减。"""
    pytest.importorskip("rdkit")  # 同上：质子化 partial 通道依赖 RDKit
    from cloudra.benchmark.runner import BenchmarkRunner
    from cloudra.benchmark.schema import GoldSpec, PromptSpec, SystemSpec, TaskSpec

    graph = _graph_with_ts(["[OH3+]"], ["CC(=O)[O-]"])
    (tmp_path / "mechanism_graph.json").write_text(graph.model_dump_json(by_alias=True))
    (tmp_path / "rc.log").write_text("gaussian log\n# smiles: O\n")
    (tmp_path / "pc.log").write_text("gaussian log\n# smiles: CC(=O)O\n")

    rep = audit_integrity(tmp_path)
    assert all(b.matched for b in rep.node_bindings)
    assert rep.binding_quality == pytest.approx((0.7 + 0.85 + 0.7) / 3)
    assert any("partial-credit" in n for n in rep.notes)

    task = TaskSpec(
        task_id="PROTO_T",
        tier="easy",
        prompt=PromptSpec(query="q"),
        system=SystemSpec(reactants=["[OH3+]"]),
        gold=GoldSpec(mechanism_graph=graph),
    )
    runner = BenchmarkRunner(tmp_path / "data")
    res = runner.score_sandbox(task, tmp_path)
    # 绑定质量并进图分：R 有效代价 1-(1-0)·0.7 = 0.3，P = 0.15；交付步无鞍点
    # 证据 → 自洽不合格 → 该 gold 边覆盖贡献倒扣（edge 代价 0 → 1.0）：
    # distance 1.45 / max 3 -> graph ≈ 0.5167；sc 判负；accuracy 无 gold 参考
    # 边记 1.0 -> final = 0.1·0.5167 + 0.6·1.0 ≈ 0.6517
    assert res.graph_score == pytest.approx(1 - 1.45 / 3, abs=1e-4)
    assert res.final_score == pytest.approx(0.1 * (1 - 1.45 / 3) + 0.6, abs=1e-4)
    assert any("partial-credit" in n for n in res.notes)


# --- 评分语义与取证修复（2a/2b/2c + 分级 composite） ---


def _runner_task(graph):
    from cloudra.benchmark.schema import GoldSpec, PromptSpec, SystemSpec

    return TaskSpec(
        task_id="SEMI_T",
        tier="easy",
        prompt=PromptSpec(query="q"),
        system=SystemSpec(reactants=["C"]),
        gold=GoldSpec(mechanism_graph=graph),
    )


def test_scan_excludes_graph_shaped_json_copies(tmp_path):
    """2b：交付图的改名拷贝（任何顶层 nodes+edges 的 JSON）不算证据，
    不能拿自己的图给自己的节点当证据。"""
    graph = _graph_with_ts(["C"], ["O"])
    payload = graph.model_dump_json(by_alias=True)
    (tmp_path / "mechanism_graph.json").write_text(payload)
    sub = tmp_path / "notes"
    sub.mkdir()
    (sub / "draft.json").write_text(payload)  # 改名拷贝
    files = scan_evidence_files(tmp_path, exclude=tmp_path / "mechanism_graph.json")
    assert files == []  # 拷贝被排除，没有任何证据文件
    rep = audit_integrity(tmp_path)
    assert rep.node_bindings and not any(b.matched for b in rep.node_bindings)
    assert rep.binding_quality == 0.0


def test_edit_script_reflects_missing_ts():
    """2a：缺 TS 的交付在诊断 diff 里可见（步骤键含 has_ts）。"""
    gold = _graph(["C=CC=C", "C=C"], ["C1CC=CCC1"], with_ts=True)
    agent = _graph(["C=CC=C", "C=C"], ["C1CC=CCC1"], with_ts=False)
    res = mechanism_similarity(agent, gold, GedConfig())
    assert res.score < 1.0
    assert any("step_missing" in s or "step_removed" in s for s in res.edit_script)


def test_selfconsistency_skips_oversized_logs(tmp_path, monkeypatch):
    """2c：超过共享上限的 QM 日志两层都不整读——绑定了超限文件的元素按
    未覆盖判负（用 monkeypatch 缩小上限模拟）。"""
    from cloudra.benchmark import selfconsistency as sc_mod

    big = tmp_path / "ts_opt.log"
    big.write_text(" Entering Gaussian System\n" + "x" * 100)
    monkeypatch.setattr(sc_mod, "MAX_SCAN_BYTES", 10)
    graph = _sc_graph(R={"accessible": False}, P={"accessible": False})
    files = [EvidenceFile(path="ts_opt.log", kind="gaussian", size=big.stat().st_size)]
    bindings = [
        NodeBinding(node_id="TS", bound_files=["ts_opt.log"], matched=True, quality=1.0),
    ]
    rep = sc_mod.audit_self_consistency(graph, bindings, files, tmp_path)
    edge = _checks_by_id(rep)["E1"]
    assert not edge.covered  # 超限文件不可解析，不构成可用证据
    assert rep.passed is False


def test_composite_no_evidence_penalty(tmp_path):
    """图缺失 / 图在但零证据绑定 -> 倒扣 no_evidence_penalty（默认 -1）。"""
    from cloudra.benchmark.runner import BenchmarkRunner

    task = _runner_task(_graph_with_ts(["C"], ["O"]))
    runner = BenchmarkRunner(tmp_path / "data")

    # 图缺失
    res = runner.score_sandbox(task, tmp_path)
    assert res.final_score == -1.0

    # 图可解析但没有任何证据
    sb2 = tmp_path / "sb2"
    sb2.mkdir()
    (sb2 / "mechanism_graph.json").write_text(task.gold.mechanism_graph.model_dump_json(by_alias=True))
    res2 = runner.score_sandbox(task, sb2)
    assert res2.final_score == -1.0
    assert any("no evidence bound" in n for n in res2.notes)


def test_composite_partial_evidence_is_graded_not_zero(tmp_path):
    """缺部分证据：未绑定的 accessible 节点按代价 1.0 并进图分（逐元素倒扣），
    不是判零也不是整体倒扣。"""
    from cloudra.benchmark.runner import BenchmarkRunner

    graph = _graph_with_ts(["C"], ["O"])
    task = _runner_task(graph)
    (tmp_path / "mechanism_graph.json").write_text(graph.model_dump_json(by_alias=True))
    (tmp_path / "rc.log").write_text("gaussian log\n# smiles: C\n")  # 只绑上 R

    runner = BenchmarkRunner(tmp_path / "data")
    res = runner.score_sandbox(task, tmp_path)
    # R 全绑 q=1（代价 0），P 未绑 q=0（等同未覆盖：节点缺失连带边缺失）
    # -> distance 2 / max 3 -> graph = 1/3（边本就连带未覆盖，自洽回捞不再
    # 改变它）；sc 判负；accuracy 无参考边记 1.0
    # -> final = 0.1·(1/3) + 0.6·1.0 ≈ 0.6333
    assert res.graph_score == pytest.approx(1 / 3, abs=1e-4)
    assert res.final_score == pytest.approx(0.1 / 3 + 0.6, abs=1e-4)
    assert res.final_score > 0.0


def test_composite_sc_failed_step_claws_back_gold_edge_graph_credit(tmp_path):
    """自洽回捞（用户裁决）：gold 边被交付步覆盖、但该交付步自洽不合格
    （绑定证据里无一阶鞍点/IRC 证明）→ 这条 gold 边赢下的图分覆盖贡献倒扣
    （交付边剔出后重算 GED），notes 逐条写明；自洽层保持全有或全无判负。

    交付 = gold（R→P 经 TS），证据是无频率块的假日志：物种绑定质量 1.0、
    图分原本 1.0；倒扣后边按未覆盖计 -> distance 1/3 -> graph = 2/3，
    final = 0.1·(2/3) + 0.3·0 + 0.6·1.0（accuracy 无参考边）≈ 0.6667。"""
    from cloudra.benchmark.runner import BenchmarkRunner

    graph = _graph_with_ts(["C"], ["O"])
    task = _runner_task(graph)
    (tmp_path / "mechanism_graph.json").write_text(graph.model_dump_json(by_alias=True))
    (tmp_path / "rc.log").write_text("gaussian log\n# smiles: C\n")
    (tmp_path / "pc.log").write_text("gaussian log\n# smiles: O\n")

    runner = BenchmarkRunner(tmp_path / "data")
    res = runner.score_sandbox(task, tmp_path)
    assert res.graph_score == pytest.approx(2 / 3, abs=1e-4)
    assert res.selfconsistency_passed is False
    assert any(
        "edge E: selfconsistency failed, graph credit for gold edge E clawed back"
        in n for n in res.notes
    ), res.notes
    assert res.final_score == pytest.approx(0.1 * (2 / 3) + 0.6, abs=1e-4)


# --- 自洽全有或全无 + 额外边不倒扣图分（用户裁决） ---


def _sc_task(graph, *, saddle=True, irc=False):
    """默认 rubric 但自洽只留鞍点检查（IRC 关闭，探针替身无需几何帧）。"""
    from cloudra.benchmark.schema import (
        GoldSpec,
        PromptSpec,
        RubricSpec,
        SelfConsistencyRubric,
        SystemSpec,
    )

    return TaskSpec(
        task_id="SEMI_T",
        tier="easy",
        prompt=PromptSpec(query="q"),
        system=SystemSpec(reactants=["C"]),
        gold=GoldSpec(mechanism_graph=graph),
        rubric=RubricSpec(
            self_consistency=SelfConsistencyRubric(
                ts_first_order_saddle=saddle, irc_connects_endpoints=irc
            )
        ),
    )


def _patch_sc_probe(monkeypatch, freq_by_name):
    """自洽日志探针替身：按文件名给频率表（负值 = 虚频）。"""
    from cloudra.benchmark import selfconsistency as sc_mod

    monkeypatch.setattr(sc_mod, "_frames_for", lambda path: ([], None))
    monkeypatch.setattr(
        sc_mod,
        "_freqs_for",
        lambda path, frames: list(freq_by_name.get(Path(path).name, [])),
    )
    monkeypatch.setattr(
        sc_mod, "_imag_freqs", lambda freqs: [f for f in freqs if f < 0]
    )
    monkeypatch.setattr(sc_mod, "_last_geometry", lambda path, frames: None)


def _extra_edge_delivery(tmp_path):
    """交付 = gold（R→P 经 TS）+ 额外物种 X 与额外边 P→X 经 TSX；
    证据：主线鞍点日志 ts.log（标注 R 物种）、端点极小值齐全。"""
    delivered = GoldMechanismGraph(
        nodes=[
            MechanismNode(id="R", role=NodeRole.REACTANT, smiles=["C"]),
            MechanismNode(id="TS", role=NodeRole.TRANSITION_STATE, smiles=[]),
            MechanismNode(id="P", role=NodeRole.PRODUCT, smiles=["O"]),
            MechanismNode(id="X", role=NodeRole.PRODUCT, smiles=["[O-]"]),
            MechanismNode(id="TSX", role=NodeRole.TRANSITION_STATE, smiles=[]),
        ],
        edges=[
            MechanismEdge(id="E", **{"from": "R", "to": "P"}, via="TS"),
            MechanismEdge(id="EX", **{"from": "P", "to": "X"}, via="TSX"),
        ],
    )
    (tmp_path / "mechanism_graph.json").write_text(
        delivered.model_dump_json(by_alias=True)
    )
    (tmp_path / "r.log").write_text("Gaussian log\n# smiles: C\n")
    (tmp_path / "ts.log").write_text("Gaussian log\n# smiles: C\n")
    (tmp_path / "p.log").write_text("Gaussian log\n# smiles: O\n")
    (tmp_path / "x.log").write_text("Gaussian log\n# smiles: [O-]\n")
    (tmp_path / "tsx.log").write_text("Gaussian log\n# smiles: [O-]\n")


def test_extra_edge_sc_failure_zeroes_layer_but_keeps_graph(tmp_path, monkeypatch):
    """③额外边（不在 gold 子图里）自洽不合格：自洽层保持全有或全无 → 整层
    判负，但图分**不倒扣**（gold 边由合格交付步覆盖）——gold 边出错与其他边
    出错严重程度不同。"""
    from cloudra.benchmark.runner import BenchmarkRunner

    task = _sc_task(_graph_with_ts(["C"], ["O"]))
    _extra_edge_delivery(tmp_path)
    _patch_sc_probe(monkeypatch, {
        "r.log": [100.0, 200.0],          # R 验证极小值
        "ts.log": [-500.0, 100.0],        # 主线一阶鞍点 -> 边 E 合格
        "p.log": [100.0],                 # P 验证极小值
        "x.log": [100.0],                 # X 验证极小值
        "tsx.log": [100.0],               # 额外边无鞍点 -> EX 不合格
    })
    res = BenchmarkRunner(tmp_path / "data").score_sandbox(task, tmp_path)
    assert res.selfconsistency_passed is False       # 全有或全无：一条边不合格整层 0
    assert res.graph_score == pytest.approx(1.0, abs=1e-4)  # 额外边不倒扣图分
    assert not any("clawed back" in n for n in res.notes), res.notes
    # accuracy 无参考边记 1.0 -> final = 0.1·1 + 0.3·0 + 0.6·1 = 0.7
    assert res.final_score == pytest.approx(0.7, abs=1e-4)


def test_all_elements_sc_pass_keeps_bool_and_full_graph(tmp_path, monkeypatch):
    """①自洽全有或全无的"全有"侧：全部元素合格 -> selfconsistency_passed
    为 True（布尔语义不变），无任何倒扣，图分保持 1.0。"""
    from cloudra.benchmark.runner import BenchmarkRunner

    task = _sc_task(_graph_with_ts(["C"], ["O"]))
    _extra_edge_delivery(tmp_path)
    _patch_sc_probe(monkeypatch, {
        "r.log": [100.0, 200.0],
        "ts.log": [-500.0, 100.0],
        "p.log": [100.0],
        "x.log": [100.0],
        "tsx.log": [-300.0, 100.0],       # 额外边也有一阶鞍点 -> 全元素合格
    })
    res = BenchmarkRunner(tmp_path / "data").score_sandbox(task, tmp_path)
    assert res.selfconsistency_passed is True
    assert res.graph_score == pytest.approx(1.0, abs=1e-4)
    assert not any("clawed back" in n for n in res.notes), res.notes
    # final = 0.1·1 + 0.3·1 + 0.6·1 = 1.0
    assert res.final_score == pytest.approx(1.0, abs=1e-4)


# --- 受控并行 ---


def test_run_all_parallel_controlled(tmp_path):
    """concurrency>1：结果按提交顺序返回、崩溃隔离保持、DB 每题落一行（append-only）、
    **并且真的并发**（同刻多题在跑）。

    并发判据用汇合点而不是墙钟：并发 3 时，让每题在 backend 里等"同时有 3 题在跑"
    才放行——串行/被意外串行化的实现会等不到而失败。墙钟差值（"并行必须快 20%"）
    在带 --cov 的 CI 格子上会误报：覆盖率 tracer 把每题的固定开销放大，省下的
    4×0.3s 睡眠被开销吃掉，曾实测出 parallel 1.466s vs serial 1.330s 的假失败。
    """
    import sqlite3
    import threading

    from cloudra.benchmark.runner import BenchmarkRunner

    tasks = gen_easy_tasks.parse_easy_md(gen_easy_tasks.DEFAULT_SRC)[:5]

    concurrency = 3
    lock = threading.Lock()
    started = threading.Event()
    in_flight = 0
    max_in_flight = 0

    def backend(task, sandbox):
        nonlocal in_flight, max_in_flight
        sandbox.mkdir(parents=True, exist_ok=True)
        if task.task_id == tasks[1].task_id:
            raise RuntimeError("boom")  # 崩溃题不参与汇合
        with lock:
            in_flight += 1
            max_in_flight = max(max_in_flight, in_flight)
            if in_flight >= concurrency:
                started.set()
        # 串行实现会在这里等到超时（Event 永不置位），由下面的断言定性
        started.wait(timeout=10)
        with lock:
            in_flight -= 1
        return None

    runner = BenchmarkRunner(tmp_path / "bench", backend=backend)
    results = runner.run_all(tasks, concurrency=concurrency)

    assert started.is_set(), (
        f"runner did not run tasks concurrently: peak in-flight {max_in_flight} "
        f"< concurrency {concurrency}"
    )
    assert [r.task_id for r in results] == [t.task_id for t in tasks]
    assert any("boom" in n for n in results[1].notes)
    assert results[1].final_score == 0.0  # 崩溃题 0 分，不是 no_evidence_penalty
    with sqlite3.connect(runner.db.db_path) as c:
        assert c.execute("SELECT COUNT(*) FROM runs").fetchone()[0] == 5


def test_run_all_serial_default_unchanged(tmp_path):
    """concurrency=1（默认）保持串行语义：逐题顺序执行。"""
    from cloudra.benchmark.runner import BenchmarkRunner

    tasks = gen_easy_tasks.parse_easy_md(gen_easy_tasks.DEFAULT_SRC)[:3]
    order: list[str] = []

    def backend(task, sandbox):
        order.append(task.task_id)
        sandbox.mkdir(parents=True, exist_ok=True)
        return None

    runner = BenchmarkRunner(tmp_path / "bench", backend=backend)
    results = runner.run_all(tasks)
    assert order == [t.task_id for t in tasks]
    assert [r.task_id for r in results] == order


# --- API 端点池（防 429） ---


def _rate_limit_error():
    import httpx
    import openai

    req = httpx.Request("POST", "https://x/v1/chat/completions")
    return openai.RateLimitError("rate limited", response=httpx.Response(429, request=req), body=None)


class _FixedRng:
    def __init__(self, order):
        self._order = order

    def sample(self, population, k):
        return [x for x in self._order if x in population]


def test_api_pool_load_and_fallback_fields(tmp_path):
    from cloudra.benchmark.api_pool import Endpoint, load_endpoints

    p = tmp_path / "pool.json"
    p.write_text(json.dumps([
        {"base_url": "https://a", "api_key": "ka", "label": "A"},
        {"base_url": "https://b"},  # api_key 留空 -> 回落 settings
    ]))
    eps = load_endpoints(p)
    assert eps[0] == Endpoint(base_url="https://a", api_key="ka", label="A")
    assert eps[1].api_key == "" and eps[1].display() == "https://b"
    assert Endpoint().display() == "(settings default)"
    bad = tmp_path / "bad.json"
    bad.write_text("{}")
    with pytest.raises(ValueError):
        load_endpoints(bad)


@pytest.mark.asyncio
async def test_api_pool_failover_on_429(monkeypatch):
    """首个端点 429 -> 换下一个且不重复；成功的端点收到完整调用。"""
    import cloudra.benchmark.api_pool as api_pool
    from cloudra.benchmark.api_pool import Endpoint, PooledLLMProvider
    from cloudra.runtime_v2.turn_pipeline import LLMResponse

    ep_a, ep_b = Endpoint(base_url="https://a", label="A"), Endpoint(base_url="https://b", label="B")
    seen: list[str] = []

    async def fake_complete(self, agent, messages, tools, on_delta=None):
        ep = api_pool._current_endpoint.get()
        seen.append(ep.display())
        if ep is ep_a:
            raise _rate_limit_error()
        return LLMResponse(content="ok")

    monkeypatch.setattr(api_pool.LegacyLLMProvider, "complete", fake_complete)
    pool = PooledLLMProvider([ep_a, ep_b], rng=_FixedRng([ep_a, ep_b]))
    resp = await pool.complete(None, [], [])
    assert resp.content == "ok"
    assert seen == ["A", "B"]


@pytest.mark.asyncio
async def test_api_pool_does_not_retry_non_429(monkeypatch):
    """非 429 错误（认证、参数等确定性错误）不重试、直接抛。"""
    import cloudra.benchmark.api_pool as api_pool
    from cloudra.benchmark.api_pool import Endpoint, PooledLLMProvider

    ep_a, ep_b = Endpoint(base_url="https://a"), Endpoint(base_url="https://b")
    seen: list[str] = []

    async def fake_complete(self, agent, messages, tools, on_delta=None):
        seen.append(api_pool._current_endpoint.get().base_url)
        raise RuntimeError("deterministic failure")

    monkeypatch.setattr(api_pool.LegacyLLMProvider, "complete", fake_complete)
    pool = PooledLLMProvider([ep_a, ep_b], rng=_FixedRng([ep_a, ep_b]))
    with pytest.raises(RuntimeError):
        await pool.complete(None, [], [])
    assert seen == ["https://a"]  # 没试第二个


@pytest.mark.asyncio
async def test_api_pool_all_429_raises_last(monkeypatch):
    import cloudra.benchmark.api_pool as api_pool
    from cloudra.benchmark.api_pool import Endpoint, PooledLLMProvider

    ep_a, ep_b = Endpoint(base_url="https://a"), Endpoint(base_url="https://b")

    async def fake_complete(self, agent, messages, tools, on_delta=None):
        raise _rate_limit_error()

    monkeypatch.setattr(api_pool.LegacyLLMProvider, "complete", fake_complete)
    pool = PooledLLMProvider([ep_a, ep_b], rng=_FixedRng([ep_a, ep_b]))
    import openai

    with pytest.raises(openai.RateLimitError):
        await pool.complete(None, [], [])


@pytest.mark.asyncio
async def test_api_pool_empty_pool_passthrough(monkeypatch):
    """空池 = 不启用池化，透传默认端点（_current_endpoint 不设置）。"""
    import cloudra.benchmark.api_pool as api_pool
    from cloudra.benchmark.api_pool import PooledLLMProvider
    from cloudra.runtime_v2.turn_pipeline import LLMResponse

    async def fake_complete(self, agent, messages, tools, on_delta=None):
        assert api_pool._current_endpoint.get() is None
        return LLMResponse(content="plain")

    monkeypatch.setattr(api_pool.LegacyLLMProvider, "complete", fake_complete)
    resp = await PooledLLMProvider([]).complete(None, [], [])
    assert resp.content == "plain"


# ---------------------------------------------------------------------------
# Task 6（P1）：从可执行到可评分的证据闭环（本机引擎契约 + 评分现状特征化）
# ---------------------------------------------------------------------------

_RDKIT_AVAILABLE = importlib.util.find_spec("rdkit") is not None

_FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"
_GAUSSIAN_FIXTURE = _FIXTURE_DIR / "gaussian" / "water_opt_freq_g16.out"
_ORCA_MIN_FIXTURE = _FIXTURE_DIR / "orca" / "co2_freq_orca42.out"
_ORCA_OPT_FIXTURE = _FIXTURE_DIR / "orca" / "dvb_opt_orca42.out"
_XTB_FIXTURE = _FIXTURE_DIR / "xtb" / "water_sp_xtb.out"
_MACE_MODEL = Path("/Users/cloudrayyy/opt/mace-omol25/MACE-omol-0-extra-large-1024.model")


def _evidence_task(**rubric_overrides):
    """带显式 rubric 的任务：只断言当前评分定义，不引入新标准。"""
    from cloudra.benchmark.schema import (
        AccuracyRubric,
        IntegrityRubric,
        SelfConsistencyRubric,
    )

    task = _tiny_task()
    sc = SelfConsistencyRubric(
        ts_first_order_saddle=rubric_overrides.get("ts_first_order_saddle", False),
        irc_connects_endpoints=rubric_overrides.get("irc_connects_endpoints", False),
    )
    return task.model_copy(
        update={
            "rubric": task.rubric.model_copy(
                update={
                    "integrity": IntegrityRubric(),
                    "self_consistency": sc,
                    "accuracy": AccuracyRubric(),
                }
            ),
            "gold": task.gold.model_copy(
                update={
                    "mechanism_graph": task.gold.mechanism_graph.model_copy(
                        update={
                            "edges": [
                                e.model_copy(update={"barrier_kcal_mol": 10.0})
                                for e in task.gold.mechanism_graph.edges
                            ]
                        }
                    )
                }
            ),
        }
    )


def test_evidence_loop_engine_output_to_score(tmp_path):
    """真实日志 fixture 走"引擎输出 → 证据文件 → 沙箱扫描 → 评分"闭环：
    只断言当前评分定义（图相似度 + 物理自检 + 能垒容差）。"""
    from cloudra.benchmark.runner import BenchmarkRunner

    task = _evidence_task()
    sandbox = tmp_path / "sandbox"
    (sandbox / "calc").mkdir(parents=True)
    (sandbox / "mechanism_graph.json").write_text(json.dumps({
        "nodes": [
            {"id": "R", "role": "reactant", "smiles": ["O"], "accessible": True},
            {"id": "P", "role": "product", "smiles": ["O"], "accessible": True},
        ],
        "edges": [{"id": "E1", "from": "R", "to": "P", "bond_changes": {"break": [], "form": []}, "accessible": True}],
    }))
    # 计算产物：真实 Gaussian 引擎输出 + 携带协议注释行的证据文件
    (sandbox / "calc" / "r_min.log").write_bytes(_GAUSSIAN_FIXTURE.read_bytes())
    (sandbox / "r_evidence.log").write_text(
        f"smiles: O\n{_GAUSSIAN_FIXTURE.read_text(encoding='utf-8', errors='replace')}",
        encoding="utf-8",
    )

    runner = BenchmarkRunner(tmp_path / "bench")
    result = runner.score_sandbox(task, sandbox)
    # Layer 2：真实 opt+freq 日志被物理自检读成极小值（rubric 未要求鞍点）
    assert result.selfconsistency_passed, result.notes
    # Layer 3：本条交付没有 via/TS 日志 → 能垒不可评分（fail-loud 0 分）
    assert result.accuracy_score == 0.0, result.notes
    assert any("no step barrier" in n for n in result.notes), result.notes
    # fail-loud 短路：final 只保留图分（自洽/accuracy 分量清零）
    assert any("final keeps the graph component only" in n for n in result.notes), result.notes
    assert result.final_score == pytest.approx(0.1 * result.graph_score, abs=1e-4)
    # 图相似度的化学指纹依赖 RDKit（可选依赖）：缺失时该层退化，CI（只装
    # dev extra）就属于这种情况，因此只在 RDKit 可用时断言图分
    if _RDKIT_AVAILABLE:
        assert result.graph_score > 0.0, result.notes
    # 落库（append-only；score_sandbox 只算不落库，落库由 runner/批次负责）
    runner.db.record(result)
    rows = runner.db.list_runs_for("")
    assert [r["task_id"] for r in rows] == [task.task_id]


def test_captured_stdout_log_is_scanned_and_failed_log_is_not_enough(tmp_path):
    """guard 捕获的 .cloudra/calc-<id>.out.log 必须被证据扫描发现；但"文件存在"
    不等于满足物理验证——未完成/无频率的日志不得判为极小值。"""
    from cloudra.benchmark.integrity import scan_evidence_files
    from cloudra.benchmark.selfconsistency import audit_self_consistency

    sandbox = tmp_path / "sandbox"
    (sandbox / ".cloudra").mkdir(parents=True)
    captured = sandbox / ".cloudra" / "calc-7.out.log"
    captured.write_bytes(_ORCA_MIN_FIXTURE.read_bytes())

    files = scan_evidence_files(sandbox)
    paths = {f.path for f in files}
    assert ".cloudra/calc-7.out.log" in paths, paths
    kinds = {f.path: f.kind for f in files}
    assert kinds[".cloudra/calc-7.out.log"] == "orca"

    graph = GoldMechanismGraph.model_validate({
        "nodes": [{"id": "R", "role": "reactant", "smiles": ["O"]}],
        "edges": [],
    })
    bindings = [
        NodeBinding(
            node_id="R",
            bound_files=[".cloudra/calc-7.out.log"],
            matched=True,
            quality=1.0,
        ),
    ]
    report = audit_self_consistency(graph, bindings, files, sandbox)
    chk = report.checks[0]
    assert chk.covered, report.notes
    assert chk.evidence_used == [".cloudra/calc-7.out.log"]

    # 反例：同一位置放"未完成/无频率"的日志（opt 日志截断），不得满足物理验证
    bad_sandbox = tmp_path / "bad"
    (bad_sandbox / ".cloudra").mkdir(parents=True)
    (bad_sandbox / ".cloudra" / "calc-8.out.log").write_bytes(
        _ORCA_OPT_FIXTURE.read_bytes()
    )
    bad_files = scan_evidence_files(bad_sandbox)
    assert any(f.path.startswith(".cloudra/") for f in bad_files)
    bad_bindings = [
        NodeBinding(
            node_id="R",
            bound_files=[".cloudra/calc-8.out.log"],
            matched=True,
            quality=1.0,
        ),
    ]
    bad_report = audit_self_consistency(graph, bad_bindings, bad_files, bad_sandbox)
    assert not bad_report.checks[0].covered, bad_report.notes
    assert bad_report.passed is False


def test_input_and_graph_files_cannot_masquerade_as_evidence(tmp_path):
    """手写输入文件/机理图形状的 JSON 不是成功计算证据：图 JSON 被排除在
    证据集外，输入文件不满足物理自检。"""
    from cloudra.benchmark.integrity import audit_integrity, scan_evidence_files
    from cloudra.benchmark.selfconsistency import audit_self_consistency

    sandbox = tmp_path / "sandbox"
    sandbox.mkdir()
    graph = {
        "nodes": [
            {"id": "R", "role": "reactant", "smiles": ["O"], "accessible": True},
            {"id": "P", "role": "product", "smiles": ["O"], "accessible": True},
        ],
        "edges": [{"id": "E1", "from": "R", "to": "P", "bond_changes": {"break": [], "form": []}, "accessible": True}],
    }
    (sandbox / "mechanism_graph.json").write_text(json.dumps(graph))
    (sandbox / "sub").mkdir()
    (sandbox / "sub" / "my_graph.json").write_text(json.dumps(graph))
    (sandbox / "input.gjf").write_text(
        "%nproc=4\n#p sp b3lyp/6-31g(d)\n\nt\n\n0 1\nO 0 0 0\nH 0 0.757 -0.469\nH 0 -0.757 -0.469\n\n"
    )

    files = scan_evidence_files(sandbox)
    paths = {f.path for f in files}
    assert "mechanism_graph.json" not in paths
    assert "sub/my_graph.json" not in paths          # 图 JSON 不得自我绑定
    assert "input.gjf" in paths                      # 输入文件在扫描范围内……
    # ……但手写输入文件不带 smiles 注释、绑不上图节点，物理自检判未覆盖
    integ = audit_integrity(sandbox)
    report = audit_self_consistency(
        integ.delivered_graph, integ.node_bindings, files, sandbox
    )
    assert not any(c.covered for c in report.checks if c.kind == "species"), report.notes
    assert report.passed is False

    # 手写输入文件的 smiles 注释不构成协议证据（gjf 由 writer 写 expected_smiles 注释）
    assert integ.graph_found and integ.graph_parseable


def test_xyz_smiles_annotation_second_line_binds(tmp_path):
    """XYZ 的 smiles 注释放合法第二行即绑定；缺失注释的文件不产生绑定。"""
    from cloudra.benchmark.integrity import audit_integrity

    graph = {
        "nodes": [
            {"id": "R", "role": "reactant", "smiles": ["O"], "accessible": True},
        ],
        "edges": [],
    }
    ok_sandbox = tmp_path / "ok"
    ok_sandbox.mkdir()
    (ok_sandbox / "mechanism_graph.json").write_text(json.dumps(graph))
    (ok_sandbox / "r.xyz").write_text(
        "3\nsmiles: O\nO 0.0 0.0 0.1173\nH 0.0 0.7572 -0.4692\nH 0.0 -0.7572 -0.4692\n"
    )
    ok = audit_integrity(ok_sandbox)
    assert ok.binding_quality == 1.0, ok.notes
    assert all(b.matched for b in ok.node_bindings)

    missing_sandbox = tmp_path / "missing"
    missing_sandbox.mkdir()
    (missing_sandbox / "mechanism_graph.json").write_text(json.dumps(graph))
    (missing_sandbox / "r.xyz").write_text(
        "3\nwater\nO 0.0 0.0 0.1173\nH 0.0 0.7572 -0.4692\nH 0.0 -0.7572 -0.4692\n"
    )
    missing = audit_integrity(missing_sandbox)
    assert missing.binding_quality == 0.0, missing.notes
    assert not any(b.matched for b in missing.node_bindings)


def test_native_xtb_run_capability_vs_scoring_gap(tmp_path):
    """原生 xTB：运行能力已具备（真实引擎 + guard/calculator 透传），但评分侧
    物理自检只覆盖 gaussian/orca——现状特征化（是否扩展属科学验收，需用户确认）。"""
    from cloudra.benchmark.integrity import scan_evidence_files
    from cloudra.benchmark.selfconsistency import audit_self_consistency

    sandbox = tmp_path / "sandbox"
    sandbox.mkdir()
    (sandbox / "xtb_sp.out").write_bytes(_XTB_FIXTURE.read_bytes())
    files = scan_evidence_files(sandbox)
    kinds = {f.path: f.kind for f in files}
    # 现状：xtb 日志被归类为通用 "log"（引擎嗅探只认 Gaussian/ORCA）
    assert kinds["xtb_sp.out"] == "log", kinds
    # 缺口记录：xtb 证据不可解析，即使绑到节点上也不构成可用证据
    graph = GoldMechanismGraph.model_validate({
        "nodes": [{"id": "R", "role": "reactant", "smiles": ["O"]}],
        "edges": [],
    })
    bindings = [
        NodeBinding(node_id="R", bound_files=["xtb_sp.out"], matched=True, quality=1.0),
    ]
    report = audit_self_consistency(graph, bindings, files, sandbox)
    assert report.checks[0].covered is False, report.notes
    assert report.passed is False


@pytest.mark.skipif(
    __import__("shutil").which("xtb") is None,
    reason="native xtb not installed — run capability unverified",
)
def test_real_xtb_engine_run(tmp_path):
    """第 3 层本机引擎契约：真实 xtb 通过 calculator.sh 跑通并写下终止标记。"""
    import subprocess

    from cloudra.infra.compute_utils import _default_calculator_path
    from cloudra.infra.platform_utils import get_bash_path

    workdir = tmp_path / "xtb job"
    workdir.mkdir()
    xyz = workdir / "water.xyz"
    xyz.write_text(
        "3\nwater\nO 0.000000 0.000000 0.117300\n"
        "H 0.000000 0.757200 -0.469200\nH 0.000000 -0.757200 -0.469200\n",
        encoding="utf-8",
    )
    proc = subprocess.run(
        [get_bash_path(), _default_calculator_path(), str(xyz), "xtb",
         "--chrg", "0", "--uhf", "0", "--task", "sp", "--parallel", "1"],
        capture_output=True, text=True, cwd=workdir, timeout=300,
    )
    assert proc.returncode == 0, proc.stderr[-500:]
    out = (workdir / "water.out").read_text(encoding="utf-8", errors="replace")
    assert "normal termination of xtb" in out, out[-500:]


@pytest.mark.skipif(
    not Path("/Users/cloudrayyy/opt/orca_6_1_1/orca").exists()
    or __import__("shutil").which("mace") is None
    or not _MACE_MODEL.is_file(),
    reason="external ProgExt stack (ORCA + mace + model) absent — external interface unverified",
)
def test_real_orca_progext_external_interface(tmp_path):
    """外部 MLIP 路由（ORCA `! ExtOpt` + %method ProgExt）的真实接口验收：
    与原生 xTB 运行能力是两项独立能力，不能互相替代。"""
    import subprocess

    from cloudra.infra.compute_utils import _default_calculator_path
    from cloudra.infra.platform_utils import get_bash_path

    workdir = tmp_path / "progext job"
    workdir.mkdir()
    mace_bin = __import__("shutil").which("mace")
    inp = workdir / "water_ext.inp"
    inp.write_text(
        "! ExtOpt\n"
        "%pal nprocs 1 end\n"
        "%method\n"
        f'  ProgExt "{mace_bin}"\n'
        f'  Ext_Params "--model {_MACE_MODEL} --device cpu --dtype float64"\n'
        "end\n"
        "* xyz 0 1\n"
        "O  0.000000  0.000000  0.117300\n"
        "H  0.000000  0.757200 -0.469200\n"
        "H  0.000000 -0.757200 -0.469200\n"
        "*\n",
        encoding="utf-8",
    )
    # 输出重定向到文件而不是管道：ORCA 拉起的外部 MACE 进程会继承管道且迟迟
    # 不退出，管道方式会让父进程读不到 EOF 而永久阻塞（首次实测即卡住 30 分钟
    # ——ORCA 其实早已算完并写下 property/bibtex）。文件重定向 + 直接子进程
    # 超时是唯一稳的写法，绝不能靠"等管道关闭"判定引擎结束。
    capture = workdir / "engine_stdout.log"
    with capture.open("wb") as sink:
        completed = subprocess.run(
            [get_bash_path(), _default_calculator_path(), str(inp), "orca"],
            stdout=sink, stderr=subprocess.STDOUT, cwd=workdir, timeout=1800,
        )
    assert completed.returncode == 0, completed.returncode
    combined = capture.read_text(encoding="utf-8", errors="replace")
    assert "ORCA TERMINATED NORMALLY" in combined, combined[-2000:]
    assert "ProgExt" in combined or "EXTERNAL" in combined.upper(), combined[-2000:]
    assert (workdir / "water_ext.property.txt").is_file()


# ---------------------------------------------------------------------------
# 评分口径整改：交付物（log + 交付 JSON）是唯一评分来源，散文一律不参与
# ---------------------------------------------------------------------------

_SYNTHETIC_DIR = _FIXTURE_DIR / "benchmark_synthetic"
_MIN_LOG = _SYNTHETIC_DIR / "minimum_freq.out"
_TS_LOG = _SYNTHETIC_DIR / "ts_freq.out"


def _delivery_task(gold_barrier: float) -> TaskSpec:
    """单步交付任务：R → P 经 TS，gold 能垒由调用方按合成日志推算值给出。"""
    from cloudra.benchmark.schema import (
        AccuracyRubric,
        GoldSpec,
        IntegrityRubric,
        RubricSpec,
        SelfConsistencyRubric,
    )

    graph = {
        "nodes": [
            {"id": "R", "role": "reactant", "smiles": ["O"], "accessible": True},
            {"id": "TS", "role": "transition_state", "smiles": [], "accessible": True},
            {"id": "P", "role": "product", "smiles": ["O"], "accessible": True},
        ],
        "edges": [
            {
                "id": "E1",
                "from": "R",
                "to": "P",
                "via": "TS",
                "bond_changes": {"break": [], "form": []},
                "accessible": True,
            }
        ],
    }
    graph["edges"][0]["barrier_kcal_mol"] = gold_barrier
    return _tiny_task().model_copy(
        update={
            "gold": GoldSpec(
                mechanism_graph=GoldMechanismGraph.model_validate(graph),
            ),
            "rubric": RubricSpec(
                integrity=IntegrityRubric(),
                self_consistency=SelfConsistencyRubric(
                    ts_first_order_saddle=False, irc_connects_endpoints=False
                ),
                accuracy=AccuracyRubric(sigma_kcal_mol=3.0, max_penalty_fraction=0.3),
            ),
        }
    )


def _write_delivery(sandbox: Path, *, declared: float | None) -> None:
    """写出合成交付：TS 日志（1 虚频）+ 最小值日志 + 声明能垒的交付图。"""
    sandbox.mkdir(parents=True, exist_ok=True)
    (sandbox / "ts_freq.out").write_bytes(_TS_LOG.read_bytes())
    (sandbox / "minimum_freq.out").write_bytes(_MIN_LOG.read_bytes())
    edge = {
        "id": "E1",
        "from": "R",
        "to": "P",
        "via": "TS",
        "bond_changes": {"break": [], "form": []},
        "accessible": True,
    }
    if declared is not None:
        edge["barrier_kcal_mol"] = declared
    graph = {
        "nodes": [
            {"id": "R", "role": "reactant", "smiles": ["O"], "accessible": True},
            {"id": "TS", "role": "transition_state", "smiles": [], "accessible": True},
            {"id": "P", "role": "product", "smiles": ["O"], "accessible": True},
        ],
        "edges": [edge],
    }
    (sandbox / "mechanism_graph.json").write_text(json.dumps(graph), encoding="utf-8")


def _derived_barrier(sandbox: Path) -> float:
    from cloudra.benchmark.barrier_evidence import collect_barrier_evidence

    evidence = collect_barrier_evidence(sandbox)
    assert len(evidence.steps) == 1, (evidence.steps, evidence.notes)
    return evidence.steps[0].barrier_kcal_mol


def test_barrier_is_derived_from_logs_and_must_be_declared(tmp_path):
    """能垒来自交付日志（TS 与起点最小值），且交付 JSON 必须逐条声明。"""
    from cloudra.benchmark.runner import BenchmarkRunner

    probe = tmp_path / "probe"
    _write_delivery(probe, declared=None)
    derived = _derived_barrier(probe)
    assert derived == pytest.approx(19.955, abs=0.05)  # 合成平移量 ≈ +0.0318 Ha

    # 未声明 → 0 分并写明原因
    undeclared = BenchmarkRunner(tmp_path / "bench_u").score_sandbox(
        _delivery_task(derived), probe
    )
    assert undeclared.accuracy_score == 0.0
    assert any("declares no barrier_kcal_mol" in n for n in undeclared.notes)

    # 逐条声明且与日志一致 → 与 gold（同值）满分
    ok_dir = tmp_path / "ok"
    _write_delivery(ok_dir, declared=derived)
    ok = BenchmarkRunner(tmp_path / "bench_ok").score_sandbox(
        _delivery_task(derived), ok_dir
    )
    assert ok.accuracy_score == 1.0, ok.notes
    assert any("edge E1" in n for n in ok.notes), ok.notes
    # 全绑全对 + sc 直通（rubric 双开关关闭）-> final = 0.1·1 + 0.3·1 + 0.6·1 = 1.0
    assert ok.graph_score == pytest.approx(1.0), ok.notes
    assert ok.selfconsistency_passed, ok.notes
    assert ok.final_score == pytest.approx(1.0), ok.notes


def test_declared_barrier_must_match_logs(tmp_path):
    """无据声明且证据对不上参考 → accuracy 记 0（fail-loud，不给部分分）；
    若证据里有能对上参考的组合，则按答案定义差异小扣分（另一用例覆盖）。"""
    from cloudra.benchmark.runner import BenchmarkRunner

    probe = tmp_path / "probe"
    _write_delivery(probe, declared=None)
    derived = _derived_barrier(probe)

    # gold = derived（证据能对上参考）→ 声明错但答案在证据里 → 小扣分
    evidence_ok = tmp_path / "definition_mismatch"
    _write_delivery(evidence_ok, declared=derived + 25.0)
    res_ok = BenchmarkRunner(tmp_path / "bench_ok").score_sandbox(
        _delivery_task(derived), evidence_ok
    )
    assert res_ok.accuracy_score == pytest.approx(0.9)
    assert any("answer-definition mismatch" in n for n in res_ok.notes), res_ok.notes

    # gold 与证据相差 30 → 声明既不成立、证据也對不上参考 → fail-loud 归零
    sandbox = tmp_path / "conflict"
    _write_delivery(sandbox, declared=derived + 25.0)
    res = BenchmarkRunner(tmp_path / "bench").score_sandbox(
        _delivery_task(derived + 30.0), sandbox
    )
    assert res.accuracy_score == 0.0
    assert any("disagreement" in n for n in res.notes), res.notes
    # fail-loud 短路：final = 0.1×图分（自洽/accuracy 分量清零）；交付图=gold
    assert res.graph_score == pytest.approx(1.0), res.notes
    assert res.final_score == pytest.approx(0.1), res.notes
    assert any("final keeps the graph component only" in n for n in res.notes)


def test_declared_node_energy_identifies_the_delivered_minimum(tmp_path):
    """同物种多份合法极小值日志：节点声明的 energy_hartree 指认交付的是哪一份，
    即使它与"鞍点下方能量最高者"启发式相反。"""
    from cloudra.benchmark.barrier_evidence import collect_barrier_evidence

    sandbox = tmp_path / "sb"
    sandbox.mkdir()
    (sandbox / "ts_freq.out").write_bytes(_TS_LOG.read_bytes())
    text = _MIN_LOG.read_text()
    folded, open_conf = "-184.757766163554", "-184.740000000000"  # 折叠(深) / 舒展(浅)
    assert text.count(folded) == 1
    (sandbox / "min_folded.out").write_text(text, encoding="utf-8")
    (sandbox / "min_open.out").write_text(text.replace(folded, open_conf), encoding="utf-8")
    graph = {
        "nodes": [
            {
                "id": "R", "role": "reactant", "smiles": ["O"], "accessible": True,
                # 声明交的是折叠构象（min_folded）；启发式会选鞍点下方较浅的 min_open
                "properties": {"energy_hartree": float(folded)},
            },
            {"id": "TS", "role": "transition_state", "smiles": [], "accessible": True},
            {"id": "P", "role": "product", "smiles": ["O"], "accessible": True},
        ],
        "edges": [
            {
                "id": "E1", "from": "R", "to": "P", "via": "TS",
                "bond_changes": {"break": [], "form": []}, "accessible": True,
            }
        ],
    }
    (sandbox / "mechanism_graph.json").write_text(json.dumps(graph), encoding="utf-8")

    evidence = collect_barrier_evidence(sandbox)
    assert len(evidence.steps) == 1, (evidence.steps, evidence.notes)
    step = evidence.steps[0]
    assert step.base_path.endswith("min_folded.out"), step.base_path
    assert any("matches the node's declared energy_hartree" in n for n in evidence.notes)
    # 用声明的那份 → 19.96 kcal；若按启发式（min_open）则只有 8.81 kcal
    assert step.barrier_kcal_mol == pytest.approx(19.955, abs=0.05)


def test_declared_ts_energy_identifies_the_delivered_saddle(tmp_path):
    """同节点绑定多份鞍点日志：TS 节点声明的 energy_hartree 指认交付的那一份
    （优先于文件名/路径序启发式）。"""
    from cloudra.benchmark.barrier_evidence import collect_barrier_evidence

    sandbox = tmp_path / "sb_ts"
    sandbox.mkdir()
    (sandbox / "min_freq.out").write_bytes(_MIN_LOG.read_bytes())
    ts_text = _TS_LOG.read_text()
    ts_energy = "-184.72596616"
    assert ts_text.count(ts_energy) >= 1
    # 名字序上 "aaa" 在前（旧规则会选它），声明指向 "zzz"
    (sandbox / "aaa_ts.out").write_text(
        ts_text.replace(ts_energy, "-184.60000000"), encoding="utf-8"
    )
    (sandbox / "zzz_ts.out").write_text(ts_text, encoding="utf-8")
    graph = {
        "nodes": [
            {"id": "R", "role": "reactant", "smiles": ["O"], "accessible": True},
            {
                "id": "TS", "role": "transition_state", "smiles": [], "accessible": True,
                "properties": {"energy_hartree": float(ts_energy)},
            },
            {"id": "P", "role": "product", "smiles": ["O"], "accessible": True},
        ],
        "edges": [
            {
                "id": "E1", "from": "R", "to": "P", "via": "TS",
                "bond_changes": {"break": [], "form": []}, "accessible": True,
            }
        ],
    }
    (sandbox / "mechanism_graph.json").write_text(json.dumps(graph), encoding="utf-8")

    evidence = collect_barrier_evidence(sandbox)
    assert len(evidence.steps) == 1, (evidence.steps, evidence.notes)
    assert evidence.steps[0].ts_path.endswith("zzz_ts.out")
    assert any(
        "saddle logs bound to TS" in n and "declared" in n for n in evidence.notes
    )


def test_scoring_ignores_prose_barrier(tmp_path):
    """散文里的能垒数字既不参与判定也不能替代声明（本次整改的核心回归）。"""
    from cloudra.benchmark.runner import BenchmarkRunner

    probe = tmp_path / "probe"
    _write_delivery(probe, declared=None)
    derived = _derived_barrier(probe)

    # 交付里只有散文在喊能垒（无 JSON 声明）→ 0 分，散文不被采信
    prose_only = tmp_path / "prose"
    _write_delivery(prose_only, declared=None)
    (prose_only / "notes.md").write_text(
        "RDS barrier is 19.96 kcal/mol (I stand behind this number).", encoding="utf-8"
    )
    res = BenchmarkRunner(tmp_path / "bench_p").score_sandbox(
        _delivery_task(derived), prose_only
    )
    assert res.accuracy_score == 0.0
    assert any("declares no barrier_kcal_mol" in n for n in res.notes), res.notes

    # 声明正确、散文献乱数 → 仍按交付物满分（散文不污染评分）
    polluted = tmp_path / "polluted"
    _write_delivery(polluted, declared=derived)
    (polluted / "final_summary.txt").write_text(
        "The barrier is 999.0 kcal/mol.", encoding="utf-8"
    )
    good = BenchmarkRunner(tmp_path / "bench_g").score_sandbox(
        _delivery_task(derived), polluted
    )
    assert good.accuracy_score == 1.0, good.notes


def test_barrier_requires_a_saddle_log(tmp_path):
    """没有一阶鞍点日志（只有最小值）→ 能垒不可推 → 0 分并写明原因。"""
    from cloudra.benchmark.runner import BenchmarkRunner

    sandbox = tmp_path / "no_ts"
    sandbox.mkdir()
    (sandbox / "minimum_freq.out").write_bytes(_MIN_LOG.read_bytes())
    (sandbox / "mechanism_graph.json").write_text(json.dumps({
        "nodes": [
            {"id": "R", "role": "reactant", "smiles": ["O"], "accessible": True},
            {"id": "TS", "role": "transition_state", "smiles": [], "accessible": True},
            {"id": "P", "role": "product", "smiles": ["O"], "accessible": True},
        ],
        "edges": [{
            "id": "E1", "from": "R", "to": "P", "via": "TS",
            "bond_changes": {"break": [], "form": []}, "accessible": True,
            "barrier_kcal_mol": 20.0,
        }],
    }))
    res = BenchmarkRunner(tmp_path / "bench").score_sandbox(
        _delivery_task(20.0), sandbox
    )
    assert res.accuracy_score == 0.0
    assert any("no step barrier" in n for n in res.notes), res.notes


def test_scoring_modules_do_not_import_regex():
    """护栏：评分/校验链路不得引入正则（AGENTS.md 禁止校验路径用正则）。"""
    import ast
    from pathlib import Path as _Path

    modules = [
        "cloudra/benchmark/accuracy.py",
        "cloudra/benchmark/runner.py",
        "cloudra/benchmark/backend.py",
        "cloudra/benchmark/barrier_evidence.py",
        "cloudra/benchmark/batch.py",
    ]
    root = _Path(__file__).resolve().parents[1]
    offenders = []
    for rel in modules:
        tree = ast.parse((root / rel).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import) and any(a.name == "re" for a in node.names):
                offenders.append(f"{rel}: import re")
            if isinstance(node, ast.ImportFrom) and node.module == "re":
                offenders.append(f"{rel}: from re import ...")
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if isinstance(node.func.value, ast.Name) and node.func.value.id == "re":
                    offenders.append(f"{rel}: re.{node.func.attr}()")
    assert offenders == [], offenders


def test_relative_evidence_reference_does_not_cross_tasks(tmp_path):
    """相对证据引用不跨题：同一沙箱内的相对引用解析到本题，`../` 或指向别的
    题目目录的引用（含绝对路径）一律拒绝，评分侧同样按不可用处理。"""
    from cloudra.benchmark.barrier_evidence import _engine_energy_kcal
    from cloudra.dag.evidence_ingest import snapshot_evidence_file

    task_a = tmp_path / "sandbox" / "T1"
    task_b = tmp_path / "sandbox" / "T2"
    for sandbox in (task_a, task_b):
        (sandbox / "calc").mkdir(parents=True)
        (sandbox / "calc" / "input.log").write_bytes(_ORCA_MIN_FIXTURE.read_bytes())

    # 1) 生产 ingestion：相对引用只在本题目录内解析
    snapshot = snapshot_evidence_file("calc/input.log", workspace_root=task_a)
    assert snapshot.sha256 and snapshot.file_size > 0

    # 2) 相对逃逸与指向另一题的绝对路径都被拒（即便文件真实存在）
    with pytest.raises(ValueError):
        snapshot_evidence_file("../T2/calc/input.log", workspace_root=task_a)
    with pytest.raises(ValueError):
        snapshot_evidence_file(str(task_b / "calc" / "input.log"), workspace_root=task_a)

    # 3) 符号链接引用被拒（不得借链接把别的题目的产物当成本题证据）
    link = task_a / "calc" / "linked.log"
    try:
        link.symlink_to(task_b / "calc" / "input.log")
    except OSError:
        link = None  # 环境不允许 symlink：跳过这一条（其余断言仍生效）
    if link is not None:
        with pytest.raises(ValueError):
            snapshot_evidence_file("calc/linked.log", workspace_root=task_a)

    # 4) 评分侧防线：越界引用按不可用处理，且不读取别的题目的日志
    energy, reason = _engine_energy_kcal(task_a, "../T2/calc/input.log")
    assert energy is None
    assert "escapes this task's sandbox" in reason, reason
    inside, _ = _engine_energy_kcal(task_a, "calc/input.log")
    assert inside is not None


def test_generators_read_whitelist_from_global_config(monkeypatch):
    """方法白名单的内容源是全局 config：覆盖 method_policy.allowed_methods 后，
    easy 生成器产出的任务白名单跟随（默认路径被 regenerate 守卫钉死）。"""
    from cloudra.benchmark import gen_easy_tasks
    from cloudra.infra.config import get_config

    monkeypatch.setattr(get_config().method_policy, "allowed_methods", ["xtb"])
    tasks = gen_easy_tasks.parse_easy_md(gen_easy_tasks.DEFAULT_SRC)
    assert tasks, "generator produced no tasks"
    assert all(t.method_policy.allowed_methods == ["xtb"] for t in tasks)


# --- 持久化：append-only / 批次溯源 / 沙箱按批保留 ---


def test_runs_are_append_only(tmp_path):
    """同一 task_id 复跑只增不删：两次 record 两行俱在（benchmark 数据珍贵，
    "每题最新"只是查询语义，不落为破坏性写）。"""
    from cloudra.benchmark.runner import BenchmarkRunner, RunResult

    runner = BenchmarkRunner(tmp_path / "bench")
    for score in (0.5, 0.8):
        runner.db.record(RunResult(
            task_id="T1", sandbox="s", final_score=score,
            orchestration_mode="dag_guided",
        ))
    rows = runner.db.list_runs_for("")
    assert len(rows) == 2
    assert sorted(r["final_score"] for r in rows) == [0.5, 0.8]
    assert all(r["orchestration_mode"] == "dag_guided" for r in rows)


def test_runs_migration_preserves_old_rows(tmp_path):
    """旧 12 列 schema（含 integrity_passed/outcome）的库重开：迁移按新 10 列
    重建——outcome/integrity_passed 两列丢弃、新旧交集列的旧行值保留、幂等
    （再开不再重建），迁移后新旧行可共存写入。"""
    import sqlite3

    db_path = tmp_path / "bench" / "benchmark.db"
    db_path.parent.mkdir(parents=True)
    with sqlite3.connect(str(db_path)) as c:
        # 旧 12 列：新 10 列 + integrity_passed + outcome（列序亦不同）
        c.execute("""CREATE TABLE runs (
            task_id TEXT, sandbox TEXT,
            integrity_passed INTEGER, graph_score REAL,
            selfconsistency_passed INTEGER, accuracy_score REAL,
            final_score REAL, outcome TEXT, notes TEXT, ts INTEGER,
            batch_id TEXT, orchestration_mode TEXT
        )""")
        c.execute(
            "INSERT INTO runs VALUES ('T9','s',1,0.9,1,0.8,0.87,"
            "'answered','[\"note1\"]',123,'batch_old','dag_record')"
        )
    from cloudra.benchmark.runner import _RUNS_COLS, BenchmarkDB, RunResult

    db = BenchmarkDB(db_path)
    with sqlite3.connect(str(db_path)) as c:
        cols = [row[1] for row in c.execute("PRAGMA table_info(runs)")]
    assert cols == list(_RUNS_COLS)  # outcome/integrity_passed 已丢弃
    rows = db.list_runs_for("batch_old")
    assert len(rows) == 1
    row = rows[0]
    # 交集列旧值原样保留
    assert row["task_id"] == "T9" and row["sandbox"] == "s"
    assert row["graph_score"] == 0.9 and row["selfconsistency_passed"] is True
    assert row["accuracy_score"] == 0.8 and row["final_score"] == 0.87
    assert row["notes"] == ["note1"] and row["ts"] == 123
    assert row["orchestration_mode"] == "dag_record"

    # 幂等：列集已一致，再开不重建、旧行不丢
    BenchmarkDB(db_path)
    assert len(db.list_runs_for("batch_old")) == 1

    # 迁移后新行照常写入
    db.record(RunResult(task_id="T9", sandbox="s2", orchestration_mode="standard"))
    assert len(db.list_runs_for("batch_old")) == 1
    new_rows = db.list_runs_for("")
    assert len(new_rows) == 1
    assert new_rows[0]["orchestration_mode"] == "standard"


def test_runs_migration_drops_missing_new_columns_as_empty(tmp_path):
    """更旧的库（连 orchestration_mode 都没有）：迁移后新列落空串兜底。"""
    import sqlite3

    db_path = tmp_path / "bench" / "benchmark.db"
    db_path.parent.mkdir(parents=True)
    with sqlite3.connect(str(db_path)) as c:
        c.execute("""CREATE TABLE runs (
            task_id TEXT, sandbox TEXT,
            integrity_passed INTEGER, graph_score REAL,
            selfconsistency_passed INTEGER, accuracy_score REAL,
            final_score REAL, outcome TEXT, notes TEXT, ts INTEGER,
            batch_id TEXT
        )""")
        c.execute(
            "INSERT INTO runs VALUES ('T8','s',1,0.9,1,0.8,0.87,'answered','[]',7,'b0')"
        )
    from cloudra.benchmark.runner import BenchmarkDB

    db = BenchmarkDB(db_path)
    rows = db.list_runs_for("b0")
    assert len(rows) == 1
    assert rows[0]["task_id"] == "T8"
    assert rows[0]["final_score"] == 0.87
    assert rows[0]["orchestration_mode"] == ""


def test_sandbox_scoped_by_batch_and_preserved(tmp_path):
    """沙箱按批分目录；复跑（新批次）不删上一批交付物。"""
    from cloudra.benchmark.runner import BenchmarkRunner

    def _backend(task, sandbox):
        (sandbox / "deliverable.txt").write_text(f"run in {sandbox.name}", encoding="utf-8")

    task = _tiny_task()
    r1 = BenchmarkRunner(tmp_path / "bench", backend=_backend, batch_id="batch_A")
    r2 = BenchmarkRunner(tmp_path / "bench", backend=_backend, batch_id="batch_B")
    res1 = r1.run_task(task)
    res2 = r2.run_task(task)

    assert res1.sandbox != res2.sandbox
    assert res1.batch_id == "batch_A" and res2.batch_id == "batch_B"
    assert (r1.sandboxes / "BENCH_T" / "batch_A" / "deliverable.txt").is_file()
    assert (r1.sandboxes / "BENCH_T" / "batch_B" / "deliverable.txt").is_file()


def test_cli_records_batch_with_provenance(tmp_path):
    """CLI 每次调用也是一个批次：batches 行带溯源快照（backend/models/
    orchestration_modes），runs 行带同一 batch_id——CLI 与 Web 结果可并排。"""
    from cloudra.benchmark.__main__ import main

    tasks_dir = tmp_path / "tasks"
    tasks_dir.mkdir()
    (tasks_dir / "BENCH_T.json").write_text(_tiny_task().model_dump_json(), encoding="utf-8")
    data_dir = tmp_path / "bench"
    rc = main(["--tasks-dir", str(tasks_dir), "--data-dir", str(data_dir)])
    assert rc == 0

    from cloudra.benchmark.runner import BenchmarkDB

    db = BenchmarkDB(data_dir / "benchmark.db")
    batches = db.list_batches()
    assert len(batches) == 1
    batch = batches[0]
    assert batch["status"] == "done"
    assert batch["config"]["backend"] == "cli"
    assert batch["config"]["orchestration_modes"] == {"BENCH_T": "standard"}
    # 溯源只记 provider/model，绝不记 API key
    for slot in ("coordinator", "follower"):
        assert set(batch["config"]["models"][slot]) == {"provider", "model"}
    runs = db.list_runs_for(batch["batch_id"])
    assert [r["task_id"] for r in runs] == ["BENCH_T"]
    assert runs[0]["orchestration_mode"] == "standard"


def test_backend_persists_events_to_store(tmp_path, monkeypatch):
    """CLI 后端接 RuntimeStore：题目事件落盘（llm.chunk 除外），崩溃后事件
    历史与 token 遥测仍可查。"""
    import sqlite3

    from cloudra.benchmark.backend import RuntimeV2Backend
    from cloudra.runtime_v2.adapters import legacy_default_runtime_settings
    from cloudra.runtime_v2.schemas import InvocationProtocol
    from cloudra.runtime_v2.turn_pipeline import LLMResponse

    monkeypatch.setattr(
        "cloudra.runtime_v2.adapters.legacy_default_runtime_settings",
        lambda: legacy_default_runtime_settings().model_copy(
            update={"invocation_protocol": InvocationProtocol.TRADITIONAL}
        ),
    )
    llm = _ScriptedLLM([LLMResponse(content="done")])
    store_path = tmp_path / "runtime" / "runtime-v2.db"
    backend = RuntimeV2Backend(
        llm=llm,
        tools=_RecordingTools(),
        start_scheduler=False,
        poll_interval_s=0.01,
        run_timeout_s=30.0,
        stuck_grace_s=5.0,
        store_path=store_path,
    )
    backend(_tiny_task(), tmp_path / "sandbox")

    with sqlite3.connect(str(store_path)) as c:
        n_events = c.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        n_chunks = c.execute(
            "SELECT COUNT(*) FROM events WHERE type = 'llm.chunk'"
        ).fetchone()[0]
    assert n_events > 0
    assert n_chunks == 0
