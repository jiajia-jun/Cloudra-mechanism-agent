"""crest_runner：持久运行现场 + 分层失败分类。

分两层：

- **固定日志/假引擎**用例（不依赖真实 CREST）：用一枚假 ``crest`` 可执行文件走完整条
  subprocess 路径，覆盖全部终止类别、产物完整性（缺失/空/截断/不可解析）、超时与未知失败，
  并断言失败现场（命令行、输入、stdout/stderr、部分产物）全部持久保留。
- **真实引擎**用例（``shutil.which('crest')`` 缺失即 skip）：用
  tests/fixtures/chemtool_issue33/ 里逐字保存的真实输入复核"标记与结果一致"，
  其中 ``fcl_ccl`` 是本机实测会失败的互穿几何。
"""

import os
import shutil
import stat
import sys

import pytest

from cloudra.tools.core import crest_runner
from cloudra.tools.core.crest_runner import (
    CrestRunRequest,
    build_crest_command,
    run_crest,
)

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures", "chemtool_issue33")

# CI 只装 .[dev]，没有 RDKit：经 RDKit 的用例一律先探测再 skip（不硬断言）
try:  # noqa: SIM105 - 缺 RDKit 是合法环境，不是错误
    import rdkit  # noqa: F401

    _HAS_RDKIT = True
except ImportError:
    _HAS_RDKIT = False

requires_rdkit = pytest.mark.skipif(not _HAS_RDKIT, reason="未安装 RDKit（chem extra），跳过")

_FAKE_CREST = '''#!{python}
"""假 CREST：按 FAKE_CREST_MODE 复现本机 2.12 的各类输出与退出码。"""
import os
import sys
import time

mode = os.environ.get("FAKE_CREST_MODE", "normal_ok")

if "--version" in sys.argv:
    print("       Version 2.12,   Thu 19. Mai 16:32:32 CEST 2022")
    print("  Using the xTB program. Compatible with xTB version 6.4.0")
    sys.exit(0)

xyz = open("input.xyz", encoding="utf-8").read().splitlines()
natoms = int(xyz[0].strip())
coords = xyz[2:2 + natoms]


def frame(count, energy="        -11.39433938", body=None):
    out = ["  %d" % count, energy]
    out.extend(coords if body is None else body)
    return "\\n".join(out) + "\\n"


print(" -------------------------")
print(" xTB Geometry Optimization")
print(" -------------------------")

if mode == "initial_opt_failed":
    print("  Initial geometry optimization failed!")
    print("  Please check your input.")
    open("NOT_CONVERGED", "w").close()
    # 非零退出但仍留下**部分**构象文件：只能当证据，不能当成功
    open("crest_conformers.xyz", "w", encoding="utf-8").write(frame(1, body=coords[:-2]))
    sys.exit(1)

if mode == "topology_change":
    print(" Geometry successfully optimized.")
    print(" WARNING! Change in topology detected!")
    print(" The topology change was seen in the initial geometry optimization.")
    print("    B) Restart the same CREST call as before, but ignore the topology change")
    sys.exit(1)

if mode == "search_failed":
    print("  Trial MTD 3 did not converge!")
    sys.exit(1)

if mode == "unknown_failure":
    print("something nobody has seen before")
    sys.exit(2)

if mode == "sleep":
    time.sleep(120)

if mode == "normal_no_artifacts":
    print(" CREST terminated normally.")
    sys.exit(0)

if mode == "normal_empty_artifact":
    open("crest_conformers.xyz", "w").close()
    print(" CREST terminated normally.")
    sys.exit(0)

if mode == "normal_truncated":
    open("crest_conformers.xyz", "w", encoding="utf-8").write(frame(natoms, body=coords[:-1]))
    print(" CREST terminated normally.")
    sys.exit(0)

if mode == "normal_unparsable_energy":
    open("crest_conformers.xyz", "w", encoding="utf-8").write(frame(natoms, energy="   not-a-number"))
    print(" CREST terminated normally.")
    sys.exit(0)

if mode == "normal_wrong_atom_count":
    open("crest_conformers.xyz", "w", encoding="utf-8").write(frame(natoms + 1))
    print(" CREST terminated normally.")
    sys.exit(0)

# normal_ok：两帧完整产物
open("crest_conformers.xyz", "w", encoding="utf-8").write(
    frame(natoms) + frame(natoms, energy="        -11.39225789")
)
print(" CREST terminated normally.")
sys.exit(0)
'''


@pytest.fixture
def fake_crest(tmp_path, monkeypatch):
    """把假 crest 装进 PATH；返回设置模式的函数。"""
    bindir = tmp_path / "fakebin"
    bindir.mkdir()
    script = bindir / "crest"
    script.write_text(_FAKE_CREST.format(python=sys.executable), encoding="utf-8")
    script.chmod(script.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    monkeypatch.setenv("PATH", f"{bindir}{os.pathsep}{os.environ['PATH']}")

    def set_mode(mode: str) -> None:
        monkeypatch.setenv("FAKE_CREST_MODE", mode)

    return set_mode


WATER_XYZ = """3
water
O      0.0000    0.0000    0.0000
H      0.9600    0.0000    0.0000
H     -0.2400    0.9300    0.0000
"""


def _request(tmp_path, **overrides) -> CrestRunRequest:
    payload = {
        "xyz_text": WATER_XYZ,
        "output_dir": str(tmp_path / "out"),
        "charge": 0,
        "multiplicity": 1,
        "timeout": 600,
    }
    payload.update(overrides)
    return CrestRunRequest(**payload)


# ---------------------------------------------------------------------------
# 命令行
# ---------------------------------------------------------------------------


def test_command_passes_charge_and_uhf_explicitly(tmp_path):
    """电荷与自旋显式透传：--uhf = multiplicity - 1（与 xtb 通道口径一致）。"""
    cmd = build_crest_command(_request(tmp_path, charge=-1, multiplicity=3))
    assert cmd[cmd.index("--uhf") + 1] == "2"
    assert cmd[cmd.index("--chrg") + 1] == "-1"
    assert cmd[0] == "crest" and cmd[1] == "input.xyz"
    assert "-gfn2" in cmd and "--quick" in cmd
    with pytest.raises(ValueError):
        build_crest_command(_request(tmp_path, multiplicity=0))


# ---------------------------------------------------------------------------
# 失败分层：非零退出、产物完整性
# ---------------------------------------------------------------------------


def test_nonzero_exit_with_partial_conformers_is_not_success(fake_crest, tmp_path):
    """核心回归：退出码非零时**即使**磁盘上有部分 crest_conformers.xyz 也不得报成功。"""
    fake_crest("initial_opt_failed")
    result = run_crest(_request(tmp_path))
    assert result.scientific_success is False
    assert result.returncode == 1
    assert result.termination_reason == "initial_optimization_failed"
    assert result.stage == "initial_optimization"
    assert result.conformers == []
    assert result.conformer_count == 0
    assert any("partial" in d and "crest_conformers.xyz" in d for d in result.diagnostics)
    # 标记行原样保留
    assert any("Initial geometry optimization failed!" in line for line in result.evidence)


def test_initial_topology_change_is_its_own_class(fake_crest, tmp_path):
    """初始拓扑变化与初始优化失败是两类，不得混为一谈。"""
    fake_crest("topology_change")
    result = run_crest(_request(tmp_path))
    assert result.scientific_success is False
    assert result.termination_reason == "initial_topology_change"
    assert result.stage == "initial_optimization"
    assert any("Change in topology detected!" in line for line in result.evidence)


def test_search_stage_failure_is_its_own_class(fake_crest, tmp_path):
    fake_crest("search_failed")
    result = run_crest(_request(tmp_path))
    assert result.scientific_success is False
    assert result.termination_reason == "search_failed"
    assert result.stage == "search"


@pytest.mark.parametrize(
    "mode,expected_problem",
    [
        ("normal_no_artifacts", "missing"),
        ("normal_empty_artifact", "empty"),
        ("normal_truncated", "truncated"),
        ("normal_unparsable_energy", "not a number"),
        ("normal_wrong_atom_count", "declares"),
    ],
)
def test_incomplete_artifacts_are_reported_not_treated_as_success(
    fake_crest, tmp_path, mode, expected_problem,
):
    """正常终止标记 + 产物品缺失/空/截断/不可解析：都必须是 incomplete_artifacts，不是成功。"""
    fake_crest(mode)
    result = run_crest(_request(tmp_path))
    assert result.scientific_success is False
    assert result.termination_reason == "incomplete_artifacts"
    assert result.stage == "artifact_check"
    assert result.conformers == []
    assert any(expected_problem in d for d in result.diagnostics), result.diagnostics


def test_complete_artifacts_report_success(fake_crest, tmp_path):
    fake_crest("normal_ok")
    result = run_crest(_request(tmp_path))
    assert result.scientific_success is True
    assert result.termination_reason == "completed"
    assert result.returncode == 0
    assert result.conformer_count == 2
    assert [c.frame_index for c in result.conformers] == [0, 1]
    assert result.conformers[0].energy_eh == pytest.approx(-11.39433938)
    assert all(len(c.positions) == 3 for c in result.conformers)
    assert any("CREST terminated normally." in line for line in result.evidence)


def test_unknown_failure_keeps_raw_text_and_does_not_guess(fake_crest, tmp_path):
    """未命中任何已知标记的非零退出：落 unknown_failure，保留原文，不猜原因。"""
    fake_crest("unknown_failure")
    result = run_crest(_request(tmp_path))
    assert result.scientific_success is False
    assert result.termination_reason == "unknown_failure"
    assert any("something nobody has seen before" in d for d in result.diagnostics)
    assert result.stdout_path and os.path.isfile(result.stdout_path)
    assert "something nobody has seen before" in open(result.stdout_path, encoding="utf-8").read()


def test_timeout_keeps_logs_input_and_command(fake_crest, tmp_path):
    """超时后：现场（命令行/输入/stdout/stderr）必须仍可读，且进程被回收。"""
    fake_crest("sleep")
    result = run_crest(_request(tmp_path, timeout=3))
    assert result.scientific_success is False
    assert result.termination_reason == "timeout"
    for path in (result.command_path, result.input_path, result.stdout_path, result.stderr_path):
        assert os.path.isfile(path), path
    assert "input.xyz" in open(result.command_path, encoding="utf-8").read()
    assert any("process group" in d for d in result.diagnostics)


# ---------------------------------------------------------------------------
# 现场持久化
# ---------------------------------------------------------------------------


def test_run_directories_are_persistent_and_numbered(fake_crest, tmp_path):
    """每次运行独立且永久的运行目录；编号单调递增，现场不被删除。"""
    fake_crest("normal_ok")
    first = run_crest(_request(tmp_path, run_label="crest"))
    second = run_crest(_request(tmp_path, run_label="crest"))
    assert first.run_dir.endswith("crest_0001")
    assert second.run_dir.endswith("crest_0002")
    for result in (first, second):
        assert os.path.isdir(result.run_dir)
        assert os.path.isfile(result.input_path)
        assert os.path.isfile(result.versions_path)
        assert os.path.isfile(result.conformers_path)
        assert any(a.name == "crest_conformers.xyz" for a in result.artifacts)


def test_versions_file_records_the_engine(fake_crest, tmp_path):
    fake_crest("normal_ok")
    result = run_crest(_request(tmp_path))
    text = open(result.versions_path, encoding="utf-8").read()
    assert "Version 2.12" in text
    assert "xTB" in text


def test_missing_executable_reports_without_running(monkeypatch, tmp_path):
    """无 crest 时不静默、不假装运行，明确报出可执行文件缺失。"""
    monkeypatch.setenv("PATH", str(tmp_path / "empty-path"))
    (tmp_path / "empty-path").mkdir()
    result = run_crest(_request(tmp_path))
    assert result.scientific_success is False
    assert result.termination_reason == "executable_missing"
    assert result.returncode is None
    assert any("crest" in d and "PATH" in d for d in result.diagnostics)


def test_request_rejects_unparsable_input_xyz(tmp_path):
    with pytest.raises(ValueError):
        run_crest(_request(tmp_path, xyz_text="not-an-xyz\n"))


# ---------------------------------------------------------------------------
# 真实 CREST 日志（Task 1 逐字现场）的分类一致性
# ---------------------------------------------------------------------------


def test_scan_markers_classifies_recorded_real_logs():
    """把 Task 1 逐字保存的真实日志喂给分类器：标记 → 类别必须与实测一致。"""
    cases = {
        "fcl_ccl": "initial_optimization_failed",
        "enol_water_ald": "initial_optimization_failed",
        "topo_change": "initial_topology_change",
        "single_ref": "completed",
    }
    for case, expected in cases.items():
        path = os.path.join(FIXTURES, case, "crest_stdout.log")
        with open(path, encoding="utf-8") as handle:
            lines = handle.read().splitlines()
        _, termination, stage = crest_runner._scan_markers(lines)
        assert termination == expected, f"{case}: {termination} != {expected}"
        expected_stage = "done" if expected == "completed" else "initial_optimization"
        assert stage == expected_stage, f"{case}: stage {stage}"


@requires_rdkit
def test_fixture_inputs_still_show_the_reported_overlap():
    """Task 1 的复现事实：两个失败输入的碎片间接触 < 0.2 Å，单分子对照无碎片。"""
    import numpy as np
    from rdkit import Chem

    cases = {"fcl_ccl": "[F-].CCl", "enol_water_ald": "[O-]C=C.O.CC=O"}
    for case, smiles in cases.items():
        mol = Chem.AddHs(Chem.MolFromSmiles(smiles))
        frag_of = {a: i for i, frag in enumerate(Chem.GetMolFrags(mol)) for a in frag}
        lines = open(
            os.path.join(FIXTURES, case, "input.xyz"), encoding="utf-8",
        ).read().splitlines()
        count = int(lines[0])
        pos = np.asarray(
            [[float(v) for v in line.split()[1:4]] for line in lines[2: 2 + count]], dtype=float,
        )
        best = min(
            float(np.linalg.norm(pos[i] - pos[j]))
            for i in range(count) for j in range(i + 1, count)
            if frag_of[i] != frag_of[j]
        )
        assert best < 0.2, f"{case}: 碎片间最小距离 {best:.4f} Å，复现事实已变"


@pytest.mark.skipif(shutil.which("crest") is None, reason="未安装 crest，跳过真实引擎验收")
def test_real_crest_normal_run_persists_its_site(tmp_path):
    """真实引擎：正常完成时返回成功，且运行目录里的现场可读。"""
    xyz = open(os.path.join(FIXTURES, "single_ref", "input.xyz"), encoding="utf-8").read()
    result = run_crest(_request(tmp_path, xyz_text=xyz, timeout=900))
    assert result.scientific_success is True, result.diagnostics
    assert result.termination_reason == "completed"
    assert result.conformer_count >= 1
    assert os.path.isfile(result.versions_path)


@pytest.mark.skipif(shutil.which("crest") is None, reason="未安装 crest，跳过真实引擎验收")
def test_real_crest_reproduces_initial_optimization_failure(tmp_path):
    """真实引擎：用 Task 1 逐字保存的互穿几何复核标记与分类一致（issue #33 缺陷面）。"""
    xyz = open(os.path.join(FIXTURES, "fcl_ccl", "input.xyz"), encoding="utf-8").read()
    result = run_crest(_request(tmp_path, xyz_text=xyz, charge=-1, timeout=900))
    assert result.scientific_success is False
    assert result.termination_reason == "initial_optimization_failed"
    assert result.returncode != 0
    # 现场完整可读：底层 xTB 输出与哨兵文件都留在运行目录里
    names = {a.name for a in result.artifacts}
    assert "xtb.out" in names
    assert "NOT_CONVERGED" in names
    assert os.path.isfile(result.stdout_path)


# ---------------------------------------------------------------------------
# Task 4：拓扑变更**只记录不判定**
# ---------------------------------------------------------------------------


def test_compare_topology_records_formed_and_broken_with_scope():
    """逐条记录增/减键，并标注片内/片间；不作任何"允许与否"的判定。"""
    from cloudra.tools.core.topology_change import compare_topology

    # 三原子：初始 C0-C1 与 C1-O2 成键；变化后 C0-O2 成键、C1-O2 断开（C0-C1 保持）
    before = (["C", "C", "O"], [[0.0, 0.0, 0.0], [1.5, 0.0, 0.0], [1.5, 1.4, 0.0]])
    after = (["C", "C", "O"], [[0.0, 0.0, 0.0], [1.5, 0.5, 0.0], [-0.1, 1.4, 0.0]])
    report = compare_topology(
        before_path="in.xyz", after_path="xtbopt.log", before=before, after=after,
    )
    kinds = {(c.kind, c.atoms) for c in report.formed + report.broken}
    assert ("formed", (0, 2)) in kinds
    assert ("broken", (1, 2)) in kinds
    assert (0, 1) not in {c.atoms for c in report.formed + report.broken}
    assert report.total_changes == 2
    # 变化前 1-2/2-3 相连 → 同一组分，故两条都是片内变化
    assert report.intra_component_changes == 2
    assert report.inter_component_changes == 0
    assert any("RECORDED ONLY" in n for n in report.notes)
    assert report.matches_expected_product is None
    assert any("NOT determined" in n for n in report.notes)


def test_compare_topology_flags_inter_component_changes():
    """片间成键必须被标成 inter_component（碎片开始反应的关键事实）。"""
    from cloudra.tools.core.topology_change import compare_topology

    # 两个相隔 4 Å 的碳（两个组分）在"变化后"靠近到 1.5 Å
    before = (["C", "C"], [[0.0, 0.0, 0.0], [4.0, 0.0, 0.0]])
    after = (["C", "C"], [[0.0, 0.0, 0.0], [1.5, 0.0, 0.0]])
    report = compare_topology(
        before_path="in.xyz", after_path="xtbopt.log", before=before, after=after,
    )
    assert report.component_of_atom == [0, 1]
    assert [(c.kind, c.scope) for c in report.formed] == [("formed", "inter_component")]
    assert report.inter_component_changes == 1
    assert report.intra_component_changes == 0
    assert report.formed[0].distance_after == pytest.approx(1.5)


def test_compare_topology_rejects_different_systems():
    """元素序列不一致时 fail-loud：那说明对比的不是同一体系。"""
    from cloudra.tools.core.topology_change import compare_topology

    with pytest.raises(ValueError):
        compare_topology(
            before_path="a.xyz", after_path="b.xyz",
            before=(["C", "C"], [[0.0, 0.0, 0.0], [1.5, 0.0, 0.0]]),
            after=(["C", "O"], [[0.0, 0.0, 0.0], [1.2, 0.0, 0.0]]),
        )


def test_compare_topology_with_expected_product_is_comparison_not_verdict():
    """给出预期产物时只做连接表一致性对比，并明确说明这不是"变化被允许"。"""
    from cloudra.tools.core.topology_change import compare_topology

    before = (["C", "C"], [[0.0, 0.0, 0.0], [4.0, 0.0, 0.0]])
    after = (["C", "C"], [[0.0, 0.0, 0.0], [1.5, 0.0, 0.0]])
    report = compare_topology(
        before_path="in.xyz", after_path="xtbopt.log", before=before, after=after,
        expected_product_path="product.xyz", expected_product=after,
    )
    assert report.matches_expected_product is True
    assert any("not a verdict" in n for n in report.notes)


def test_read_last_xtbopt_frame_reads_the_recorded_fixture():
    """读回 Task 1 保存的真实 xTB 优化轨迹末帧。"""
    from cloudra.tools.core.topology_change import read_last_xtbopt_frame

    path = os.path.join(FIXTURES, "topo_change", "xtbopt_trajectory_head.log")
    symbols, positions = read_last_xtbopt_frame(path)
    assert len(symbols) == 6
    assert len(positions) == 6
    assert symbols[0].upper() == "F"


@pytest.mark.skipif(shutil.which("crest") is None, reason="未安装 crest，跳过真实引擎验收")
def test_real_crest_topology_change_is_reported_not_judged(tmp_path):
    """真实引擎：碎片已分离仍触发初始拓扑变化时，报告逐条变化但不下判定。"""
    xyz = open(os.path.join(FIXTURES, "topo_change", "input.xyz"), encoding="utf-8").read()
    result = run_crest(_request(tmp_path, xyz_text=xyz, charge=-1, timeout=900))
    assert result.termination_reason == "initial_topology_change"
    assert result.scientific_success is False
    report = result.topology_change
    assert report is not None, "CREST 留下了 xtbopt.log，必须给出变化前后对比"
    assert report.total_changes >= 1
    assert report.before_path.endswith("input.xyz")
    assert report.after_path.endswith("xtbopt.log")
    assert any("RECORDED ONLY" in note for note in report.notes)
    # 变化必须区分片内/片间，且计数与清单一致
    assert report.intra_component_changes + report.inter_component_changes == report.total_changes


# ---------------------------------------------------------------------------
# Task 4 门（用户批准）：多碎片输入默认 --noreftopo，只关初始拓扑检查
# ---------------------------------------------------------------------------


def test_noreftopo_is_opt_in_on_the_command_and_never_notopo(tmp_path):
    """--noreftopo 只在显式要求时出现；绝不与 -notopo 混用（后者关掉 CREGEN 全部拓扑检查）。"""
    default = build_crest_command(_request(tmp_path))
    assert "--noreftopo" not in default
    assert "-notopo" not in default and "--notopo" not in default

    enabled = build_crest_command(_request(tmp_path, noreftopo=True))
    assert "--noreftopo" in enabled
    assert "-notopo" not in enabled and "--notopo" not in enabled


def test_noreftopo_use_is_recorded_in_the_result(fake_crest, tmp_path):
    """用了 --noreftopo 必须显式记录（不得静默地把"没检查初始拓扑"当成"拓扑没问题"）。"""
    fake_crest("topology_change")
    result = run_crest(_request(tmp_path, noreftopo=True))
    assert "--noreftopo" in result.command
    assert any("--noreftopo was used" in d for d in result.diagnostics)
    assert any("INITIAL topology check" in d for d in result.diagnostics)
    assert any("-notopo was deliberately NOT passed" in d for d in result.diagnostics)
    # 即便关掉了初始检查，拓扑变化仍然被记录（只记录不判定）
    assert result.topology_change is not None or result.termination_reason != "completed"


def test_real_crest_noreftopo_lets_the_search_start(tmp_path):
    """真实引擎：同一互穿之外的合法种子，加了 --noreftopo 后不再因初始拓扑检查而中止。"""
    import shutil as _shutil

    if _shutil.which("crest") is None:
        pytest.skip("未安装 crest，跳过真实引擎验收")
    xyz = open(os.path.join(FIXTURES, "topo_change", "input.xyz"), encoding="utf-8").read()
    without = run_crest(_request(tmp_path, xyz_text=xyz, charge=-1, timeout=900))
    assert without.termination_reason == "initial_topology_change"
    with_option = run_crest(_request(tmp_path, xyz_text=xyz, charge=-1, timeout=900, noreftopo=True))
    assert with_option.termination_reason != "initial_topology_change", with_option.diagnostics
