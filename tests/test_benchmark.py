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

import json
from pathlib import Path

import pytest

from cloudra.benchmark import gen_easy_tasks, selfconsistency
from cloudra.benchmark.accuracy import score_accuracy
from cloudra.benchmark.graph_similarity import GedConfig, mechanism_similarity
from cloudra.benchmark.integrity import EvidenceFile, audit_integrity, scan_evidence_files
from cloudra.benchmark.method_policy import check_input_content, check_input_files, intercept
from cloudra.benchmark.schema import (
    AccuracyRubric,
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
    assert len(tasks) == 30
    for t in tasks:
        dumped = t.model_dump(mode="json", by_alias=True)
        rt = TaskSpec.model_validate(dumped)
        assert rt.task_id == t.task_id


def test_easy_charge_and_smiles():
    tasks = {t.task_id: t for t in gen_easy_tasks.parse_easy_md(gen_easy_tasks.DEFAULT_SRC)}
    assert tasks["C1"].system.charge == -1
    assert tasks["M12"].system.charge == 1
    assert tasks["D1"].system.reactants == ["C=CC=C", "C=C"]
    # degenerate M-group process: product falls back to reactant
    assert tasks["M6"].system.products == ["CC"]


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


# --- accuracy ---


def test_accuracy_gaussian_and_cap():
    gold = ReferenceComputation(barrier_kcal_mol=27.5)
    r = AccuracyRubric(sigma_kcal_mol=3.0, max_penalty_fraction=0.3)
    assert score_accuracy(27.5, gold, r).gaussian_score == pytest.approx(1.0)
    near = score_accuracy(28.0, gold, r)
    assert near.gaussian_score > 0.95
    far = score_accuracy(100.0, gold, r)
    assert far.capped_penalty == pytest.approx(0.3)  # capped
    assert far.final_score == pytest.approx(0.7)
    missing = score_accuracy(None, gold, r)
    assert missing.final_score == pytest.approx(0.7)


def test_accuracy_disabled_passthrough():
    gold = ReferenceComputation(barrier_kcal_mol=27.5)
    r = AccuracyRubric(enabled=False)
    assert score_accuracy(None, gold, r).final_score == 1.0


# --- method policy ---

# qm_input_writer：method 字段精确白名单；缺 method 字段 fail-closed
@pytest.mark.parametrize(
    "tool,args,allowed",
    [
        ("qm_input_writer", {"method": "mace-omol25"}, True),
        ("qm_input_writer", {"method": "xtb"}, True),
        ("qm_input_writer", {"method": "wb97m-v"}, False),
        ("qm_input_writer", {"method": "ccsd(t)"}, False),
        ("qm_input_writer", {}, False),
        ("read_file", {"path": "x"}, True),
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
    ],
)
def test_method_policy_bash_content(command, allowed):
    assert intercept("bash", {"command": command}, MethodPolicy()).allowed is allowed


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
        # 虚频低于阈值（构象假 TS）-> 判负
        ([-50.0], {"num_points_forward": 3, "num_points_backward": 3,
                   "forward_converged": True, "backward_converged": True}, False, True),
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


# --- 题库可复现性 ---


def test_easy_tasks_regenerate_identically():
    """版本化题库必须与生成器输出一致（generator 是唯一事实来源）。"""
    tasks = gen_easy_tasks.parse_easy_md(gen_easy_tasks.DEFAULT_SRC)
    for t in tasks:
        committed = gen_easy_tasks.DEFAULT_OUT / f"{t.task_id}.json"
        assert committed.is_file(), f"missing committed task file: {committed}"
        regenerated = json.loads(json.dumps(t.model_dump(mode="json", by_alias=True)))
        assert json.loads(committed.read_text(encoding="utf-8")) == regenerated
