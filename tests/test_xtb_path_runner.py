"""xtb_path_runner：MTD 路径搜索（SOP `guess` 阶段的便宜端）。

分两层：

- **假 xtb** 用例（不依赖真实引擎）：走完整 subprocess 路径，覆盖端点自检、缺引擎、
  成功、失败、超时、产物不完整、运行目录持久化。
- **真实引擎** 用例（缺 `xtb` 即 skip）：用真实 MTD 跑一遍水分子 O–H 拉伸，并把
  ``xtbpath_ts.xyz`` 的注释能量与单点计算**对账**——这条是本机实测两个文件能量单位不同
  的回归护栏。
"""

import os
import shutil
import stat
import subprocess
import sys

import pytest

from cloudra.tools.core.xtb_path_runner import (
    PATH_KIND_IDPP,
    XtbPathRequest,
    build_xtb_path_command,
    run_xtb_path,
)

WATER = """3
water
O      0.000000    0.000000    0.000000
H      0.960000    0.000000    0.000000
H     -0.240000    0.930000    0.000000
"""

STRETCHED = """3
stretched
O      0.000000    0.000000    0.000000
H      2.600000    0.000000    0.000000
H     -0.240000    0.930000    0.000000
"""

_FAKE_XTB = '''#!{python}
"""假 xtb：按 FAKE_XTB_MODE 复现 6.7.1 的路径搜索输出与退出码。"""
import os
import sys
import time

mode = os.environ.get("FAKE_XTB_MODE", "ok")

if "--version" in sys.argv:
    print("   * xtb version 6.7.1 (fake) compiled by test")
    sys.exit(0)

reactant = open("reactant.xyz", encoding="utf-8").read().splitlines()
count = int(reactant[0].strip())
body = reactant[2:2 + count]
tail = " xtb: 6.7.1 (fake)"


def frame(energy):
    return "\\n".join([str(count), " energy: " + energy + tail] + body) + "\\n"


print("          | TOTAL ENERGY               -5.070383095219 Eh   |")

if mode == "crash":
    print("malformed input, nobody has seen this before")
    sys.exit(2)

if mode == "timeout":
    time.sleep(120)

if mode == "no_path_marker":
    # 有正常终止标记但从不打印 path finder 块 -> 不能只凭退出码判成功
    print("normal termination of xtb", file=sys.stderr)
    print(" * finished run on 2026/01/01 at 00:00:00.000")
    sys.exit(0)

if mode == "no_normal_marker":
    # 有 path finder 块但没有正常终止标记
    print(" path finder:")
    print(" * finished run on 2026/01/01 at 00:00:00.000")
    sys.exit(0)

open("xtbpath.xyz", "w", encoding="utf-8").write(
    frame("0.000000000000") + frame("52.271000000000") + frame("0.500000000000")
)
if mode == "no_ts":
    pass
elif mode == "truncated_ts":
    open("xtbpath_ts.xyz", "w", encoding="utf-8").write(
        str(count) + "\\n energy: -4.987083865354" + tail + "\\n" + body[0] + "\\n"
    )
elif mode == "bad_comment":
    open("xtbpath_ts.xyz", "w", encoding="utf-8").write(
        "\\n".join([str(count), "not an energy line"] + body) + "\\n"
    )
else:
    open("xtbpath_ts.xyz", "w", encoding="utf-8").write(frame("-4.987083865354"))

print("normal termination of xtb", file=sys.stderr)
print(" * finished run on 2026/01/01 at 00:00:00.000")
print(" path finder:")
print(" * wall-time: 0 d, 0 h, 0 min, 0.543 sec")
sys.exit(0)
'''


@pytest.fixture
def fake_xtb(tmp_path, monkeypatch):
    bindir = tmp_path / "fakebin"
    bindir.mkdir()
    script = bindir / "xtb"
    script.write_text(_FAKE_XTB.format(python=sys.executable), encoding="utf-8")
    script.chmod(script.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    monkeypatch.setenv("PATH", f"{bindir}{os.pathsep}{os.environ['PATH']}")

    def set_mode(mode: str) -> None:
        monkeypatch.setenv("FAKE_XTB_MODE", mode)

    return set_mode


def _request(tmp_path, **overrides) -> XtbPathRequest:
    payload = {
        "reactant_xyz": WATER,
        "product_xyz": STRETCHED,
        "output_dir": str(tmp_path / "out"),
        "charge": 0,
        "multiplicity": 1,
        "timeout": 600,
    }
    payload.update(overrides)
    return XtbPathRequest(**payload)


# ---------------------------------------------------------------------------
# 命令行与端点自检
# ---------------------------------------------------------------------------


def test_command_passes_charge_and_uhf_explicitly(tmp_path):
    cmd = build_xtb_path_command(_request(tmp_path, charge=-1, multiplicity=3))
    assert cmd[:4] == ["xtb", "reactant.xyz", "--path", "product.xyz"]
    assert cmd[cmd.index("--chrg") + 1] == "-1"
    assert cmd[cmd.index("--uhf") + 1] == "2"
    with pytest.raises(ValueError):
        build_xtb_path_command(_request(tmp_path, multiplicity=0))


def test_inconsistent_endpoints_are_rejected_before_spending_compute(fake_xtb, tmp_path):
    """元素序列不一致时先自检，不跑引擎；现场照样留下（端点 + 命令行）。"""
    fake_xtb("ok")
    bad_product = "3\nbad\nO 0 0 0\nH 2.6 0 0\nC -0.24 0.93 0\n"
    result = run_xtb_path(_request(tmp_path, product_xyz=bad_product))
    assert result.usable_as_guess is False
    assert result.termination_reason == "invalid_endpoints"
    assert os.path.isfile(result.command_path)
    assert os.path.isfile(result.reactant_path)
    assert not os.path.exists(result.path_xyz_path)
    assert any("element sequences differ" in d for d in result.diagnostics)


def test_malformed_endpoint_is_rejected(fake_xtb, tmp_path):
    fake_xtb("ok")
    result = run_xtb_path(_request(tmp_path, reactant_xyz="not-an-xyz\n"))
    assert result.termination_reason == "invalid_endpoints"


def test_missing_executable_reports_the_fallback(monkeypatch, tmp_path):
    """无 xtb：明确报出应退回 IDPP 并标注 path_kind，不静默降级。"""
    empty = tmp_path / "empty-path"
    empty.mkdir()
    monkeypatch.setenv("PATH", str(empty))
    result = run_xtb_path(_request(tmp_path))
    assert result.usable_as_guess is False
    assert result.termination_reason == "executable_missing"
    assert result.returncode is None
    assert any(PATH_KIND_IDPP in d for d in result.diagnostics)


# ---------------------------------------------------------------------------
# 成功路径与两个文件的单位分离
# ---------------------------------------------------------------------------


def test_successful_path_search_reports_frames_and_ts_candidate(fake_xtb, tmp_path):
    fake_xtb("ok")
    result = run_xtb_path(_request(tmp_path))
    assert result.usable_as_guess is True
    assert result.termination_reason == "completed"
    assert result.returncode == 0
    assert result.path_kind == "xtb_path"
    assert [f.frame_index for f in result.frames] == [0, 1, 2]
    assert all(len(f.positions) == 3 for f in result.frames)
    assert result.symbols == ["O", "H", "H"]
    assert any("normal termination of xtb" in line for line in result.evidence)
    assert any("path finder:" in line for line in result.evidence)
    # 初猜 ≠ 已验证
    assert any("NOT verified" in d for d in result.diagnostics)


def test_path_and_ts_energies_are_kept_in_separate_fields(fake_xtb, tmp_path):
    """核心回归：两个文件的注释能量**单位不同**，绝不能进同一个字段。

    本机实测：``xtbpath.xyz`` 的注释是**相对 kcal/mol**（某帧 52.271 对应真实能量差
    52.272 kcal/mol），``xtbpath_ts.xyz`` 的注释是**绝对 Eh**（与单点一致到 1e-12）。
    """
    fake_xtb("ok")
    result = run_xtb_path(_request(tmp_path))
    # 路径帧：相对 kcal/mol，原样来自各自文件的注释
    assert [f.rel_energy_kcal for f in result.frames] == [0.0, 52.271, 0.5]
    # TS 候选：绝对 Eh
    assert result.ts_candidate_energy_eh == pytest.approx(-4.987083865354)
    # 两者不相等、不混用
    assert result.ts_candidate_energy_eh != result.frames[1].rel_energy_kcal
    assert any("RELATIVE kcal/mol" in d and "ABSOLUTE Eh" in d for d in result.diagnostics)


# ---------------------------------------------------------------------------
# 失败分层
# ---------------------------------------------------------------------------


def test_nonzero_exit_keeps_the_log_and_does_not_guess(fake_xtb, tmp_path):
    fake_xtb("crash")
    result = run_xtb_path(_request(tmp_path))
    assert result.usable_as_guess is False
    assert result.returncode == 2
    assert result.termination_reason == "failed"
    assert os.path.isfile(result.stdout_path)
    assert "nobody has seen this before" in open(result.stdout_path, encoding="utf-8").read()
    assert any("nobody has seen this before" in d for d in result.diagnostics)


def test_exit_zero_without_the_path_marker_is_not_success(fake_xtb, tmp_path):
    """退出码 0 不构成成功判据：没有 path finder 标记就不算跑过路径搜索。"""
    fake_xtb("no_path_marker")
    result = run_xtb_path(_request(tmp_path))
    assert result.usable_as_guess is False
    assert result.termination_reason == "unknown_failure"
    assert any("path-finder timing block" in d for d in result.diagnostics)


def test_exit_zero_without_the_normal_termination_marker_is_not_success(fake_xtb, tmp_path):
    """缺正常终止标记同样不算成功——标记在 stderr，必须在两个流上一起扫。"""
    fake_xtb("no_normal_marker")
    result = run_xtb_path(_request(tmp_path))
    assert result.usable_as_guess is False
    assert result.termination_reason == "unknown_failure"
    assert any("normal-termination marker" in d for d in result.diagnostics)


@pytest.mark.parametrize("mode", ["no_ts", "truncated_ts", "bad_comment"])
def test_incomplete_artifacts_are_reported_not_accepted(fake_xtb, tmp_path, mode):
    fake_xtb(mode)
    result = run_xtb_path(_request(tmp_path))
    assert result.usable_as_guess is False
    assert result.termination_reason == "incomplete_artifacts"
    assert result.frames == []
    assert result.ts_candidate_energy_eh is None
    assert any("unusable" in d for d in result.diagnostics)


def test_timeout_keeps_the_site(fake_xtb, tmp_path):
    fake_xtb("timeout")
    result = run_xtb_path(_request(tmp_path, timeout=3))
    assert result.usable_as_guess is False
    assert result.termination_reason == "timeout"
    for path in (result.command_path, result.reactant_path, result.product_path,
                 result.stdout_path, result.stderr_path):
        assert os.path.isfile(path), path
    assert any("process group" in d for d in result.diagnostics)


def test_run_directories_are_persistent_and_numbered(fake_xtb, tmp_path):
    fake_xtb("ok")
    first = run_xtb_path(_request(tmp_path, run_label="guess"))
    second = run_xtb_path(_request(tmp_path, run_label="guess"))
    assert first.run_dir.endswith("guess_0001")
    assert second.run_dir.endswith("guess_0002")
    for result in (first, second):
        assert os.path.isdir(result.run_dir)
        assert os.path.isfile(result.versions_path)
        assert any(a.name == "xtbpath.xyz" for a in result.artifacts)


# ---------------------------------------------------------------------------
# 真实引擎验收
# ---------------------------------------------------------------------------


@pytest.mark.skipif(shutil.which("xtb") is None, reason="未安装 xtb，跳过真实引擎验收")
def test_real_xtb_path_energies_match_single_points(tmp_path):
    """真实 MTD 路径：把 TS 候选的注释能量与单点计算对账。

    这条护栏的意义：本机实测两个文件的能量注释单位不同（路径帧 = 相对 kcal/mol，
    TS 候选 = 绝对 Eh）。如果哪天 xTB 改了格式或解析错位，这条会直接红。
    """
    result = run_xtb_path(_request(tmp_path, timeout=900))
    assert result.usable_as_guess is True, result.diagnostics
    assert len(result.frames) >= 2

    ts_xyz = os.path.join(result.run_dir, "xtbpath_ts.xyz")
    single = subprocess.run(
        ["xtb", ts_xyz, "--sp", "--chrg", "0", "--uhf", "0"],
        cwd=result.run_dir, capture_output=True, text=True, timeout=600,
    )
    assert single.returncode == 0
    total = None
    for line in (single.stdout or "").splitlines():
        if "TOTAL ENERGY" in line:
            total = float(line.split("TOTAL ENERGY")[1].split()[0])
            break
    assert total is not None, single.stdout[-2000:]
    assert result.ts_candidate_energy_eh == pytest.approx(total, abs=1e-8)

    # 路径帧的相对能量应当远小于 1 Eh 量级（kcal/mol 才会是这个尺度）
    assert all(
        f.rel_energy_kcal is None or abs(f.rel_energy_kcal) < 200.0 for f in result.frames
    )
