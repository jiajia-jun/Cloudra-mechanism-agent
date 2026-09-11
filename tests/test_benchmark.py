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
from cloudra.benchmark.integrity import EvidenceFile, audit_integrity, scan_evidence_files
from cloudra.benchmark.method_policy import (
    check_input_content,
    check_input_files,
    check_method,
    intercept,
)
from cloudra.benchmark.schema import (
    AccuracyRubric,
    BarrierReference,
    BondChangeSet,
    GoldMechanismGraph,
    MechanismEdge,
    MechanismNode,
    MethodPolicy,
    NodeRole,
    ReferenceComputation,
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
    assert tasks["C1"].system.charge == -1
    assert tasks["D1"].system.charge == 0
    assert tasks["D1"].system.reactants == ["C=CC=C", "C=C"]
    # degenerate M-group process: product falls back to reactant
    assert tasks["M1"].system.products == tasks["M1"].system.reactants


def test_easy_barrier_parsing_no_garbage():
    """能垒解析不得抓年份/键长/百分数：无锚点数字题 -> None；
    锚点数字取范围下界/正确抓取；DOI 含括号不得截断（见保留题集合内 DOI 题）。"""
    tasks = {t.task_id: t for t in gen_easy_tasks.parse_easy_md(gen_easy_tasks.DEFAULT_SRC)}
    ref = {tid: t.gold.reference_computation for tid, t in tasks.items()}
    assert ref["M3"].barrier_kcal_mol is not None
    assert ref["D1"].barrier_kcal_mol == 27.5
    assert ref["E1"].barrier_kcal_mol == 6.9  # 经典值（范围下界约定）
    for tid, t in tasks.items():
        b = t.gold.reference_computation.barrier_kcal_mol
        assert b is None or 0.0 <= b <= 200.0, f"{tid} implausible barrier {b}"
        assert t.name.isascii(), f"{tid} name not English: {t.name!r}"
        assert t.system.conditions.isascii()
        assert t.prompt.query.isascii() and "Determine the mechanism" in t.prompt.query


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


def test_easy_query_requires_structured_barrier_declaration():
    """accuracy 只读交付物：query 必须要求把每步能垒声明进交付 JSON，
    不再有"在最终总结里报数"这类散文契约。"""
    tasks = gen_easy_tasks.parse_easy_md(gen_easy_tasks.DEFAULT_SRC)
    for t in tasks:
        assert "as `barrier_kcal_mol` in mechanism_graph.json" in t.prompt.query
        assert "In your final summary you must report" not in t.prompt.query


def test_easy_gold_bond_changes_and_barrier_frame():
    """gold 边必须携带键变化（否则 agent 填了 bond_changes 反而被对称差扣分），
    且索引约定必须与 query 展示的原子映射 SMILES 一致；能垒口径统一
    central_complex（TS 相对反应物络合物）。"""
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
        ref = t.gold.reference_computation
        if ref.barrier_kcal_mol is not None:
            assert ref.barrier_reference == BarrierReference.CENTRAL, f"{tid} barrier frame"


# --- runner ---


def test_runner_rerun_starts_from_clean_sandbox(tmp_path):
    """复跑同一 task 时上一轮残留文件必须清掉，否则污染取证扫描。"""
    from cloudra.benchmark.runner import BenchmarkRunner

    tasks = gen_easy_tasks.parse_easy_md(gen_easy_tasks.DEFAULT_SRC)
    runner = BenchmarkRunner(tmp_path / "bench")
    sandbox = runner.sandbox_for(tasks[0].task_id)
    sandbox.mkdir(parents=True)
    (sandbox / "stale_evidence.log").write_text("smiles: C=CC=C\n")  # 上一轮残留
    runner.run_task(tasks[0])  # 默认 no-op backend
    assert not (sandbox / "stale_evidence.log").exists()


def test_runner_rerun_over_symlink_or_file_sandbox(tmp_path):
    """上一轮后端若在沙箱路径留下 symlink 或普通文件，复跑不得抛 OSError。"""
    import shutil

    from cloudra.benchmark.runner import BenchmarkRunner

    tasks = gen_easy_tasks.parse_easy_md(gen_easy_tasks.DEFAULT_SRC)
    runner = BenchmarkRunner(tmp_path / "bench")
    sandbox = runner.sandbox_for(tasks[0].task_id)

    target = tmp_path / "real_target"
    target.mkdir()
    (target / "stale.txt").write_text("x")
    try:
        sandbox.symlink_to(target, target_is_directory=True)
    except OSError:
        pytest.skip("当前平台不允许创建符号链接")
    runner.run_task(tasks[0])
    assert sandbox.is_dir() and not sandbox.is_symlink()
    assert (target / "stale.txt").exists()  # unlink 只删链接，不碰目标目录

    shutil.rmtree(sandbox)
    sandbox.write_text("leftover")  # 普通文件占位同理
    runner.run_task(tasks[0])
    assert sandbox.is_dir() and not sandbox.is_symlink()


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


def test_runner_rerun_keeps_single_runs_row(tmp_path):
    """runs 表是 latest-result-per-task：复跑同题只保留一行。"""
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
    assert len(rows) == 1


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


def test_ged_oversized_delivery_short_circuits():
    """对称 GED 诊断模式下，失控交付的超大图直接判最大差异（score 0.0），
    不调用 networkx——optimize_graph_edit_distance 最坏指数复杂度。
    （默认的子图打分模式是多项式的指派评估，不需要这个守卫。）"""
    gold = _graph(["C=CC=C", "C=C"], ["C1CC=CCC1"])  # 3 nodes -> 守卫上限 30
    big = GoldMechanismGraph(
        nodes=[
            MechanismNode(id=f"n{i}", role=NodeRole.INTERMEDIATE, smiles=["CC"])
            for i in range(31)
        ],
        edges=[],
    )
    res = mechanism_similarity(big, gold, GedConfig(subgraph_scoring=False))
    assert res.score == 0.0
    assert res.distance == res.max_distance
    assert any("short-circuited" in s for s in res.edit_script)


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
    # 产物错误（CCl4 而非 CF/Cl-）-> 产物节点替换代价 ≈1，边也随之配不上
    wrong_p = _graph(["[F-]", "CCl"], ["ClC(Cl)(Cl)Cl"])
    assert mechanism_similarity(wrong_p, gold, GedConfig()).score < 0.6


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


def test_accuracy_requires_both_sources_and_agreement():
    """交付物双来源门禁：log 推算值与交付 JSON 声明值都必须存在且一致。"""
    gold = ReferenceComputation(barrier_kcal_mol=27.5)
    r = AccuracyRubric(sigma_kcal_mol=3.0, max_penalty_fraction=0.3)

    exact = score_accuracy(evidence=_evidence([("E1", 27.5, 27.5)]), gold=gold, rubric=r)
    assert exact.gaussian_score == pytest.approx(1.0)
    assert exact.final_score == pytest.approx(1.0)

    near = score_accuracy(evidence=_evidence([("E1", 28.0, 28.4)]), gold=gold, rubric=r)
    assert near.gaussian_score > 0.95

    far = score_accuracy(evidence=_evidence([("E1", 100.0, 100.0)]), gold=gold, rubric=r)
    assert far.capped_penalty == pytest.approx(0.3)  # capped
    assert far.final_score == pytest.approx(0.7)

    from cloudra.benchmark.barrier_evidence import BarrierEvidence

    assert score_accuracy(evidence=BarrierEvidence(), gold=gold, rubric=r).final_score == 0.0
    undeclared = score_accuracy(evidence=_evidence([("E1", 27.5, None)]), gold=gold, rubric=r)
    assert undeclared.final_score == 0.0
    assert any("declares no barrier_kcal_mol" in n for n in undeclared.notes), undeclared.notes
    conflict = score_accuracy(evidence=_evidence([("E1", 27.5, 40.0)]), gold=gold, rubric=r)
    assert conflict.final_score == 0.0
    assert any("disagreement" in n for n in conflict.notes), conflict.notes


def test_accuracy_per_step_gate_and_rds_selection():
    """逐步门禁：任一步声明与日志冲突即 0；全部一致时 RDS（最高垒）对 gold 评分。"""
    gold = ReferenceComputation(barrier_kcal_mol=22.0)
    r = AccuracyRubric(sigma_kcal_mol=3.0, max_penalty_fraction=0.3)

    rds = score_accuracy(
        evidence=_evidence([("E1", 12.0, 12.0), ("E2", 22.0, 22.2), ("E3", 5.0, 5.0)]),
        gold=gold,
        rubric=r,
    )
    assert rds.rds_edge_id == "E2"
    assert rds.log_barrier_kcal == pytest.approx(22.0)
    assert rds.final_score == pytest.approx(1.0)

    polluted = score_accuracy(
        evidence=_evidence([("E1", 12.0, 30.0), ("E2", 22.0, 22.0)]), gold=gold, rubric=r
    )
    assert polluted.final_score == 0.0
    assert any("E1" in n for n in polluted.notes), polluted.notes


def test_accuracy_disabled_passthrough():
    gold = ReferenceComputation(barrier_kcal_mol=27.5)
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
            {"id": "R", "role": "reactant", "smiles": ["C=CC=C", "C=C"], "accessible": True, "label": "r"},
            {"id": "TS", "role": "transition_state", "smiles": [], "accessible": True, "label": "ts"},
            {"id": "P", "role": "product", "smiles": ["C1CC=CCC1"], "accessible": True, "label": "p"},
        ],
        "edges": [{"id": "E1", "from": "R", "to": "P", "via": "TS", "step_type": "da",
                    "bond_changes": {"break": [], "form": [[1, 2]]}, "accessible": True}],
    }
    (tmp_path / "mechanism_graph.json").write_text(json.dumps(g))
    (tmp_path / "r.log").write_text("smiles: C=CC=C\nsmiles: C=C\n")
    (tmp_path / "p.log").write_text("smiles: C1CC=CCC1\n")
    rep = audit_integrity(tmp_path)
    assert rep.graph_found and rep.graph_parseable
    assert rep.fraction_bound == 1.0
    assert rep.passed


def test_integrity_missing_graph_fails(tmp_path):
    rep = audit_integrity(tmp_path)
    assert not rep.graph_found
    assert not rep.passed


def test_integrity_ts_bound_via_endpoints(tmp_path):
    """TS 节点不再无条件通过：仅当经由它的边的两端物种都有证据时才算绑定。"""
    base_nodes = [
        {"id": "R", "role": "reactant", "smiles": ["C=CC=C", "C=C"]},
        {"id": "TS", "role": "transition_state", "smiles": []},
        {"id": "P", "role": "product", "smiles": ["C1CC=CCC1"]},
    ]
    edge = {"id": "E1", "from": "R", "to": "P", "via": "TS"}

    # 只有 R 端有证据：P 与 TS 都不应绑定
    (tmp_path / "mechanism_graph.json").write_text(
        json.dumps({"nodes": base_nodes, "edges": [edge]})
    )
    (tmp_path / "r.log").write_text("smiles: C=CC=C\nsmiles: C=C\n")
    rep = audit_integrity(tmp_path)
    matched = {b.node_id: b.matched for b in rep.node_bindings}
    assert matched == {"R": True, "TS": False, "P": False}
    assert not rep.passed

    # 两端证据补齐后 TS 经端点间接绑定
    (tmp_path / "p.log").write_text("smiles: C1CC=CCC1\n")
    rep = audit_integrity(tmp_path)
    matched = {b.node_id: b.matched for b in rep.node_bindings}
    assert matched == {"R": True, "TS": True, "P": True}
    assert rep.passed

    # TS 未被任何边经由：即使物种证据齐全也不应绑定
    orphan = {
        "nodes": base_nodes,
        "edges": [{"id": "E1", "from": "R", "to": "P", "via": None}],
    }
    (tmp_path / "mechanism_graph.json").write_text(json.dumps(orphan))
    rep = audit_integrity(tmp_path)
    matched = {b.node_id: b.matched for b in rep.node_bindings}
    assert matched["TS"] is False
    assert not rep.passed


def test_integrity_evidence_smiles_tolerant_formats(tmp_path):
    """证据 SMILES 注释容忍 JSON/YAML 引号与注释前缀（交付协议的注释行会
    出现在 .gjf 标题、日志回显、JSON 摘要等各种格式里）。"""
    g = {
        "nodes": [
            {"id": "R", "role": "reactant", "smiles": ["C=CC=C", "C=C"]},
            {"id": "P", "role": "product", "smiles": ["C1CC=CCC1"]},
        ],
        "edges": [{"id": "E1", "from": "R", "to": "P"}],
    }
    (tmp_path / "mechanism_graph.json").write_text(json.dumps(g))
    (tmp_path / "r.log").write_text('title\n{"smiles": "C=CC=C"}\n# smiles: C=C\n')
    (tmp_path / "p.log").write_text("smiles: 'C1CC=CCC1'\n")
    rep = audit_integrity(tmp_path)
    assert rep.passed, rep.notes


def test_integrity_evidence_bracket_smiles_not_truncated(tmp_path):
    """离子 bracket SMILES（[F-]、[Cl-]）必须完整捕获——正则排除集若误含
    方括号会把 [Cl-] 截成 [Cl- 导致永远绑不上（干跑实测抓出）。"""
    g = {
        "nodes": [
            {"id": "R", "role": "reactant", "smiles": ["[F-]", "CCl"]},
            {"id": "P", "role": "product", "smiles": ["CF", "[Cl-]"]},
        ],
        "edges": [{"id": "E1", "from": "R", "to": "P"}],
    }
    (tmp_path / "mechanism_graph.json").write_text(json.dumps(g))
    (tmp_path / "r.gjf").write_text("# title\nsmiles: [F-]\nsmiles: CCl\n")
    (tmp_path / "p_summary.json").write_text(json.dumps({"smiles": ["CF", "[Cl-]"]}))
    rep = audit_integrity(tmp_path)
    assert rep.passed, rep.notes


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
    assert not rep.passed


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
    assert rep.passed


def test_integrity_delivered_graph_postel_aliases(tmp_path):
    """GH #29：agent 按常规图论字段交付（type/source/target、字符串 SMILES）也
    必须可解析：type→role、source→from、target→to、str smiles→[smiles]。"""
    g = {
        "nodes": [
            {"id": "rc", "type": "reactant", "label": "pre-reaction complex", "smiles": "[F-].CCl"},
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
    assert rep.fraction_bound == 0.0
    assert not rep.passed


# --- self-consistency ---

FIXTURES = Path(__file__).parent / "fixtures"


def test_selfconsistency_real_fixtures_split_roles(tmp_path):
    """真实日志：minimum 不再被误判为鞍点；IRC 元数据按真实解析器形状判定。"""
    import shutil

    shutil.copy(FIXTURES / "gaussian" / "water_opt_freq_g16.out", tmp_path / "reactant.log")
    shutil.copy(FIXTURES / "orca" / "hcn_irc_orca60.out", tmp_path / "ts_irc.log")
    files = scan_evidence_files(tmp_path)
    rep = audit_self_consistency(files, tmp_path)
    assert len(rep.ts_checks) == 1 and len(rep.min_checks) == 1
    ts, mn = rep.ts_checks[0], rep.min_checks[0]
    # ORCA IRC 日志无频率块 -> 不给鞍点判定；双向收敛 -> IRC 连通
    assert ts.is_first_order_saddle is None
    assert ts.irc_connects is True
    # 水 opt+freq 是 minimum
    assert mn.is_minimum is True
    assert rep.all_minima is True
    assert rep.all_irc_connect is True
    # 没有含频率块的 TS 证据 -> 鞍点证据缺失，整体判负
    assert rep.all_first_order is False
    assert rep.passed is False


def _fake_ts_frames(imag_freqs, irc_meta):
    frames = [FrameRecord(frame=0, frequencies_cm=imag_freqs + [100.0, 200.0])]
    return frames, irc_meta


@pytest.mark.parametrize(
    "imag_freqs,irc_meta,want_saddle,want_irc",
    [
        # 一阶鞍点 + 双向收敛 IRC -> 通过
        ([-500.0], {"num_points_forward": 3, "num_points_backward": 3,
                    "forward_converged": True, "backward_converged": True}, True, True),
        # 两个虚频 -> 非一阶鞍点
        ([-500.0, -300.0], {"num_points_forward": 3, "num_points_backward": 3,
                            "forward_converged": True, "backward_converged": True}, False, True),
        # 单个虚频即为合法一阶鞍点：虚频大小不再是判负条件（用户决策），
        # 是否"合适"交由 IRC 连通性判定，此处双向收敛 -> 通过
        ([-50.0], {"num_points_forward": 3, "num_points_backward": 3,
                   "forward_converged": True, "backward_converged": True}, True, True),
        # 鞍点成立但 IRC 只有一个方向 -> IRC 判负
        ([-500.0], {"num_points_forward": 3, "num_points_backward": 0,
                    "forward_converged": True, "backward_converged": False}, True, False),
    ],
)
def test_selfconsistency_saddle_logic(monkeypatch, imag_freqs, irc_meta, want_saddle, want_irc):
    monkeypatch.setattr(
        selfconsistency, "_frames_for", lambda path: _fake_ts_frames(imag_freqs, irc_meta)
    )
    files = [EvidenceFile(path="ts_opt.log", kind="gaussian")]
    rep = audit_self_consistency(files, Path("."))
    chk = rep.ts_checks[0]
    assert chk.is_first_order_saddle is (len(imag_freqs) == 1)
    assert rep.all_first_order is want_saddle
    assert rep.all_irc_connect is want_irc
    assert rep.passed is (want_saddle and want_irc)


def test_selfconsistency_ts_numbered_filenames(monkeypatch):
    """ts1.log / TS2.out 这类编号命名也是 TS 证据（reactants/products 不算）。"""
    monkeypatch.setattr(
        selfconsistency, "_frames_for",
        lambda path: _fake_ts_frames([-500.0], None),
    )
    files = [
        EvidenceFile(path="ts1.log", kind="gaussian"),
        EvidenceFile(path="TS2.out", kind="orca"),
        EvidenceFile(path="reactants.log", kind="gaussian"),
        EvidenceFile(path="products.log", kind="orca"),
    ]
    rep = audit_self_consistency(files, Path("."))
    assert len(rep.ts_checks) == 2
    assert len(rep.min_checks) == 2  # reactants/products 按极小值检查


# --- 题库可复现性 ---


def test_easy_tasks_regenerate_identically():
    """版本化题库必须与生成器输出一致（generator 是唯一事实来源）。"""
    tasks = gen_easy_tasks.parse_easy_md(gen_easy_tasks.DEFAULT_SRC)
    for t in tasks:
        committed = gen_easy_tasks.DEFAULT_OUT / f"{t.task_id}.json"
        assert committed.is_file(), f"missing committed task file: {committed}"
        regenerated = json.loads(json.dumps(t.model_dump(mode="json", by_alias=True)))
        assert json.loads(committed.read_text(encoding="utf-8")) == regenerated
        # easy/normal/hard 共用 xtb+b3lyp/def2svp 组合白名单（基组钉进许可）；impossible 保持 xtb-only
        assert t.method_policy.allowed_methods == ["xtb", "b3lyp/def2svp"]


def test_normal_tasks_regenerate_identically():
    """normal 档题库（v3：10 题多步网络）必须与生成器输出一致。"""
    pytest.importorskip("rdkit")  # 生成器的映射校验依赖 RDKit；CI 只装 dev extra
    from cloudra.benchmark import gen_normal_tasks

    tasks = gen_normal_tasks.parse_normal_md(gen_normal_tasks.DEFAULT_SRC)
    assert len(tasks) == 10
    for t in tasks:
        committed = gen_normal_tasks.DEFAULT_OUT / f"{t.task_id}.json"
        assert committed.is_file(), f"missing committed task file: {committed}"
        regenerated = json.loads(json.dumps(t.model_dump(mode="json", by_alias=True)))
        assert json.loads(committed.read_text(encoding="utf-8")) == regenerated
        assert t.method_policy.allowed_methods == ["xtb", "b3lyp/def2svp"]


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
        assert t.method_policy.allowed_methods == ["xtb", "b3lyp/def2svp"]


def test_impossible_tasks_regenerate_identically():
    """impossible 档题库（v3：10 拒答题 + 10 兄弟对照题）必须与生成器输出一致。

    同时锚定结构性纪律：I/S 配对双向互指、I 题 correct_refusal 且带
    impossible_case（至少一个不可达节点）、S 题 mechanism_found 且全图可达、
    refusal.should_refuse 的 ground truth 与 expected_outcome 对齐。"""
    pytest.importorskip("rdkit")  # 生成器的映射校验依赖 RDKit；CI 只装 dev extra
    from cloudra.benchmark import gen_impossible_tasks
    from cloudra.benchmark.refusal import should_refuse
    from cloudra.benchmark.schema import ExpectedOutcome

    tasks = gen_impossible_tasks.parse_impossible_md(gen_impossible_tasks.DEFAULT_SRC)
    assert len(tasks) == 20
    by_id = {t.task_id: t for t in tasks}
    assert sum(t.task_id.startswith("I") for t in tasks) == 10
    assert sum(t.task_id.startswith("S") for t in tasks) == 10
    for t in tasks:
        committed = gen_impossible_tasks.DEFAULT_OUT / f"{t.task_id}.json"
        assert committed.is_file(), f"missing committed task file: {committed}"
        regenerated = json.loads(json.dumps(t.model_dump(mode="json", by_alias=True)))
        assert json.loads(committed.read_text(encoding="utf-8")) == regenerated
        # impossible 保持 xtb-only：I 系靠单参考方法边界触发科学拒答，开 DFT 会破坏该校准
        assert t.method_policy.allowed_methods == ["xtb"]
        # 配对双向互指
        assert by_id[t.pair_id].pair_id == t.task_id
        graph = t.gold.mechanism_graph
        if t.task_id.startswith("I"):
            assert t.rubric.expected_outcome is ExpectedOutcome.CORRECT_REFUSAL
            assert t.rubric.impossible_case is not None
            inaccessible = {n.id for n in graph.nodes if not n.accessible}
            assert inaccessible
            assert set(t.rubric.impossible_case.gold_inaccessible_nodes) == inaccessible
            assert should_refuse(t)
        else:
            assert t.rubric.expected_outcome is ExpectedOutcome.MECHANISM_FOUND
            assert t.rubric.impossible_case is None
            assert all(n.accessible for n in graph.nodes)
            assert not should_refuse(t)


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
    from cloudra.benchmark.schema import BarrierType, GoldSpec, SelectivityReference

    gold = GoldSpec(
        mechanism_graph=GoldMechanismGraph(nodes=[]),
        selectivity=SelectivityReference(
            spread_kcal_mol=2.0,
            spread_type=BarrierType.DE,
            minor_channel="inward rotation -> (Z)-diene",
        ),
    )
    dumped = gold.model_dump(mode="json")
    assert dumped["selectivity"]["spread_kcal_mol"] == 2.0
    assert dumped["selectivity"]["spread_type"] == "ΔE‡"
    assert dumped["reference_computation"]["barrier_kcal_mol"] is None
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


async def _stub_summarizer(messages):
    return "[RUN LOG]\nstub\n[HANDOVER]\nstub"


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
        run_summarizer=_stub_summarizer,
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
        run_summarizer=_stub_summarizer,
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


def test_integrity_report_binding_quality_and_runner_multiplier(tmp_path):
    """端到端：质子化变体证据 -> integrity 通过但 binding_quality<1，
    runner composite 被乘性扣减而不是判零。"""
    pytest.importorskip("rdkit")  # 同上：质子化 partial 通道依赖 RDKit
    from cloudra.benchmark.runner import BenchmarkRunner
    from cloudra.benchmark.schema import GoldSpec, PromptSpec, SystemSpec, TaskSpec

    graph = _graph_with_ts(["[OH3+]"], ["CC(=O)[O-]"])
    (tmp_path / "mechanism_graph.json").write_text(graph.model_dump_json(by_alias=True))
    (tmp_path / "rc.log").write_text("gaussian log\n# smiles: O\n")
    (tmp_path / "pc.log").write_text("gaussian log\n# smiles: CC(=O)O\n")

    rep = audit_integrity(tmp_path)
    assert rep.passed
    assert rep.fraction_bound == 1.0
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
    # graph=1.0（交付=gold），sc 无 QM 证据判负，accuracy 无 gold barrier 记 1.0
    # blend = 0.5*1.0 + 0.2*0 + 0.3*1.0 = 0.8；× 0.75 = 0.6
    assert res.integrity_passed
    assert res.final_score == pytest.approx(0.8 * 0.75, abs=1e-4)
    assert any("binding quality" in n for n in res.notes)


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
    assert rep.fraction_bound == 0.0 and not rep.passed


def test_edit_script_reflects_missing_ts():
    """2a：缺 TS 的交付在诊断 diff 里可见（步骤键含 has_ts）。"""
    gold = _graph(["C=CC=C", "C=C"], ["C1CC=CCC1"], with_ts=True)
    agent = _graph(["C=CC=C", "C=C"], ["C1CC=CCC1"], with_ts=False)
    res = mechanism_similarity(agent, gold, GedConfig())
    assert res.score < 1.0
    assert any("step_missing" in s or "step_removed" in s for s in res.edit_script)


def test_selfconsistency_skips_oversized_logs(tmp_path, monkeypatch):
    """2c：超过共享上限的 QM 日志两层都不整读（用 monkeypatch 缩小上限模拟）。"""
    from cloudra.benchmark import selfconsistency as sc_mod

    big = tmp_path / "ts_opt.log"
    big.write_text(" Entering Gaussian System\n" + "x" * 100)
    monkeypatch.setattr(sc_mod, "MAX_SCAN_BYTES", 10)
    files = [EvidenceFile(path="ts_opt.log", kind="gaussian", size=big.stat().st_size)]
    rep = sc_mod.audit_self_consistency(files, tmp_path)
    assert rep.ts_checks == []  # 超限文件被跳过，不产生 TS 检查项


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
    """缺部分证据：按 binding_quality 比例扣，不是判零也不是倒扣。"""
    from cloudra.benchmark.runner import BenchmarkRunner

    graph = _graph_with_ts(["C"], ["O"])
    task = _runner_task(graph)
    (tmp_path / "mechanism_graph.json").write_text(graph.model_dump_json(by_alias=True))
    (tmp_path / "rc.log").write_text("gaussian log\n# smiles: C\n")  # 只绑上 R

    runner = BenchmarkRunner(tmp_path / "data")
    res = runner.score_sandbox(task, tmp_path)
    # R 全绑 1.0，P/TS 未绑 0 -> quality = 1/3；blend = 0.5*1 + 0 + 0.3*1 = 0.8
    assert res.final_score == pytest.approx(0.8 / 3, abs=1e-4)
    assert res.final_score > 0.0


def test_composite_full_evidence_full_blend(tmp_path):
    """证据完整 + 机理正确（交付=gold）-> 满分通道不受新语义影响。"""
    from cloudra.benchmark.runner import BenchmarkRunner

    graph = _graph_with_ts(["C"], ["O"])
    task = _runner_task(graph)
    (tmp_path / "mechanism_graph.json").write_text(graph.model_dump_json(by_alias=True))
    (tmp_path / "rc.log").write_text("gaussian log\n# smiles: C\n")
    (tmp_path / "pc.log").write_text("gaussian log\n# smiles: O\n")

    runner = BenchmarkRunner(tmp_path / "data")
    res = runner.score_sandbox(task, tmp_path)
    assert res.final_score == pytest.approx(0.8, abs=1e-4)  # sc 无频率证据判负，其余满


# --- 受控并行 ---


def test_run_all_parallel_controlled(tmp_path):
    """concurrency>1：结果按提交顺序返回、崩溃隔离保持、DB 每题一行、
    并行确实比串行快。"""
    import sqlite3
    import time

    from cloudra.benchmark.runner import BenchmarkRunner

    tasks = gen_easy_tasks.parse_easy_md(gen_easy_tasks.DEFAULT_SRC)[:5]

    def backend(task, sandbox):
        sandbox.mkdir(parents=True, exist_ok=True)
        if task.task_id == tasks[1].task_id:
            raise RuntimeError("boom")
        time.sleep(0.3)
        return None

    runner = BenchmarkRunner(tmp_path / "bench", backend=backend)
    t0 = time.monotonic()
    results = runner.run_all(tasks, concurrency=3)
    dt = time.monotonic() - t0
    assert [r.task_id for r in results] == [t.task_id for t in tasks]
    assert any("boom" in n for n in results[1].notes)
    assert results[1].final_score == 0.0  # 崩溃题 0 分，不是 no_evidence_penalty
    # 串行 4×0.3s=1.2s+；并发 3 应明显更快（阈值留足 CI 抖动余量）
    assert dt < 1.0
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
        ReferenceComputation,
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
                    "integrity": IntegrityRubric(
                        require_graph_json=True, require_evidence_files=True
                    ),
                    "self_consistency": sc,
                    "accuracy": AccuracyRubric(),
                }
            ),
            "gold": task.gold.model_copy(
                update={
                    "reference_computation": ReferenceComputation(
                        barrier_kcal_mol=10.0, level_of_theory="b3lyp/test"
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
    # Layer 1：证据绑定到交付图（smiles 注释行是唯一绑定来源）
    assert result.integrity_passed, result.notes
    # Layer 2：真实 opt+freq 日志被物理自检读成极小值（rubric 未要求鞍点）
    assert result.selfconsistency_passed, result.notes
    # Layer 3：本条交付没有 via/TS 日志 → 能垒不可评分（fail-loud 0 分）
    assert result.accuracy_score == 0.0, result.notes
    assert any("no step barrier" in n for n in result.notes), result.notes
    # 图相似度的化学指纹依赖 RDKit（可选依赖）：缺失时该层退化，CI（只装
    # dev extra）就属于这种情况，因此只在 RDKit 可用时断言图分
    if _RDKIT_AVAILABLE:
        assert result.graph_score > 0.0, result.notes
    # 落库（每题一行；score_sandbox 只算不落库，落库由 runner/批次负责）
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

    report = audit_self_consistency(files, sandbox)
    assert report.min_checks, report.notes
    assert report.min_checks[0].is_minimum is True, report.notes

    # 反例：同一位置放"未完成/无频率"的日志（opt 日志截断），不得满足物理验证
    bad_sandbox = tmp_path / "bad"
    (bad_sandbox / ".cloudra").mkdir(parents=True)
    (bad_sandbox / ".cloudra" / "calc-8.out.log").write_bytes(
        _ORCA_OPT_FIXTURE.read_bytes()
    )
    bad_files = scan_evidence_files(bad_sandbox)
    assert any(f.path.startswith(".cloudra/") for f in bad_files)
    bad_report = audit_self_consistency(bad_files, bad_sandbox)
    assert not any(
        c.is_minimum is True for c in bad_report.min_checks
    ), bad_report.notes
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
    report = audit_self_consistency(files, sandbox)
    assert not any(c.is_minimum is True for c in report.min_checks), report.notes
    assert report.min_checks or report.notes         # ……但物理自检不通过

    integ = audit_integrity(sandbox)
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
    assert ok.fraction_bound == 1.0, ok.notes
    assert ok.passed

    missing_sandbox = tmp_path / "missing"
    missing_sandbox.mkdir()
    (missing_sandbox / "mechanism_graph.json").write_text(json.dumps(graph))
    (missing_sandbox / "r.xyz").write_text(
        "3\nwater\nO 0.0 0.0 0.1173\nH 0.0 0.7572 -0.4692\nH 0.0 -0.7572 -0.4692\n"
    )
    missing = audit_integrity(missing_sandbox)
    assert missing.fraction_bound == 0.0, missing.notes
    assert missing.passed is False


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
    report = audit_self_consistency(files, sandbox)
    # 缺口记录：xtb 证据不进任何物理自检集合（只收 gaussian/orca）
    assert report.ts_checks == [] and report.min_checks == [], report.notes
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
        ReferenceComputation,
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
    return _tiny_task().model_copy(
        update={
            "gold": GoldSpec(
                mechanism_graph=GoldMechanismGraph.model_validate(graph),
                reference_computation=ReferenceComputation(barrier_kcal_mol=gold_barrier),
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
    assert any("RDS E1" in n for n in ok.notes), ok.notes


def test_declared_barrier_must_match_logs(tmp_path):
    """声明值与日志推算值冲突（超过 sigma）→ accuracy 记 0（不给部分分）。"""
    from cloudra.benchmark.runner import BenchmarkRunner

    probe = tmp_path / "probe"
    _write_delivery(probe, declared=None)
    derived = _derived_barrier(probe)

    sandbox = tmp_path / "conflict"
    _write_delivery(sandbox, declared=derived + 25.0)
    res = BenchmarkRunner(tmp_path / "bench").score_sandbox(
        _delivery_task(derived), sandbox
    )
    assert res.accuracy_score == 0.0
    assert any("disagreement" in n for n in res.notes), res.notes


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
        "cloudra/benchmark/refusal.py",
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
