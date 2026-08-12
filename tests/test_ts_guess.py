"""ts_guess 工具测试（cloudra/tools/Chemtool/ts_guess.py）。

全部离线，不执行任何量化程序。fixture 为仓库已有的真实 Gaussian 输出：
- h2_scan_g09.log：G09 relaxed PES scan（opt=ModRedundant），101 点 H-H 键长扫描（0.60→1.60 Å）
- hcn_ts_irc_g16.log：G16 IRC，正/反向各 10 点 + TS
- water_opt_freq_g16.out：G16 opt+freq，极小点（无虚频）
"""

import math
from pathlib import Path

import pytest

pytest.importorskip("numpy")
pytest.importorskip("ase")
pytest.importorskip("cclib")

import ase.io
import numpy as np

from cloudra.tools.Chemtool.ts_guess import (
    TsGuess,
    TsGuess_input_schema,
    _assign_irc_endpoints,
    _evaluate_endpoint_between,
    analyze_scan_profile,
)

FIXTURES = Path(__file__).parent / "fixtures" / "gaussian"
SCAN_LOG = FIXTURES / "h2_scan_g09.log"
IRC_LOG = FIXTURES / "hcn_ts_irc_g16.log"
OPT_FREQ_LOG = FIXTURES / "water_opt_freq_g16.out"


def _make_tool() -> TsGuess:
    return TsGuess()


# ---------------------------------------------------------------------------
# strict verify 几何纯函数
# ---------------------------------------------------------------------------

_STRICT_SYMBOLS = ["C", "N", "H"]
_STRICT_TS_POS = np.array([
    [0.0, 0.0, 0.0],
    [0.0, 0.0, 2.0],
    [0.0, 0.0, 1.0],
])
_STRICT_LEFT_END = np.array([
    [0.0, 0.0, 0.0],
    [0.0, 0.0, 2.0],
    [0.0, 0.0, 0.7],
])
_STRICT_LEFT_INTERMEDIATE = np.array([
    [0.0, 0.0, 0.0],
    [0.0, 0.0, 2.0],
    [0.0, 0.0, 0.1],
])
_STRICT_RIGHT_END = np.array([
    [0.0, 0.0, 0.0],
    [0.0, 0.0, 2.0],
    [0.0, 0.0, 1.3],
])
_STRICT_RIGHT_INTERMEDIATE = np.array([
    [0.0, 0.0, 0.0],
    [0.0, 0.0, 2.0],
    [0.0, 0.0, 1.9],
])
_STRICT_WATCH_PAIRS = [[1, 3], [2, 3]]


def test_strict_endpoint_between_uses_pair_distances():
    """若 IRC 端点沿 TS→优化中间体方向前进且尚未走到底，应判为中间值。"""
    result = _evaluate_endpoint_between(
        _STRICT_SYMBOLS,
        _STRICT_TS_POS,
        _STRICT_LEFT_END,
        _STRICT_LEFT_INTERMEDIATE,
        _STRICT_WATCH_PAIRS,
    )

    assert result["is_decidable"] is True
    assert result["is_between"] is True
    assert result["pairs"] == [(0, 2), (1, 2)]


def test_strict_endpoint_rejects_motion_away_from_intermediate():
    """若端点越过 TS 朝相反方向移动，不能被中间值容差放过。"""
    wrong_direction = _STRICT_TS_POS.copy()
    wrong_direction[2, 2] = 1.2

    result = _evaluate_endpoint_between(
        _STRICT_SYMBOLS,
        _STRICT_TS_POS,
        wrong_direction,
        _STRICT_LEFT_INTERMEDIATE,
        _STRICT_WATCH_PAIRS,
    )

    assert result["is_decidable"] is True
    assert result["is_between"] is False


def test_strict_endpoint_without_informative_pairs_is_inconclusive():
    """TS 与所谓中间体没有显著内坐标差异时，工具不能臆造反应方向。"""
    result = _evaluate_endpoint_between(
        _STRICT_SYMBOLS,
        _STRICT_TS_POS,
        _STRICT_LEFT_END,
        _STRICT_TS_POS.copy(),
        [],
    )

    assert result["is_decidable"] is False
    assert result["is_between"] is False


def test_strict_assignment_accepts_swapped_intermediate_order():
    """reactant/product 的传入顺序不应影响 IRC 两侧与中间体的无序配对。"""
    result = _assign_irc_endpoints(
        _STRICT_SYMBOLS,
        _STRICT_TS_POS,
        _STRICT_LEFT_END,
        _STRICT_RIGHT_END,
        _STRICT_RIGHT_INTERMEDIATE,
        _STRICT_LEFT_INTERMEDIATE,
        _STRICT_WATCH_PAIRS,
    )

    assert result["is_decidable"] is True
    assert result["is_match"] is True
    assert result["assignment"] == "swapped"


# ---------------------------------------------------------------------------
# analyze_scan_profile 纯函数
# ---------------------------------------------------------------------------

def test_profile_single_peak_middle():
    """峰在中部：无任何警告判定，barrier 与 ts_index 正确。"""
    result = analyze_scan_profile([0.0, 5.0, 10.0, 5.0, 0.0])
    assert result["ts_index"] == 2
    assert result["barrier_kcal"] == pytest.approx(10.0)
    assert result["verdicts"] == []


def test_profile_monotonic():
    """全程单调：提示可能无势垒或坐标选错；极值在末端同时触发边界判定。"""
    result = analyze_scan_profile([0.0, 1.0, 2.0, 3.0])
    assert result["ts_index"] == 3
    assert any("单调" in v for v in result["verdicts"])
    assert any("边界" in v for v in result["verdicts"])


def test_profile_peak_at_boundary():
    """峰在端点（首帧）：提示扩大扫描范围；barrier = max − 首点 = 0。"""
    result = analyze_scan_profile([5.0, 3.0, 1.0, 0.0])
    assert result["ts_index"] == 0
    assert result["barrier_kcal"] == pytest.approx(0.0)
    assert any("边界" in v for v in result["verdicts"])
    assert any("单调" in v for v in result["verdicts"])  # 单调递减同时触发单调判定


def test_profile_discontinuity():
    """相邻能量突跳 > 3×中位数且 > 2 kcal/mol：报滑谷/不连续。"""
    result = analyze_scan_profile([0.0, 0.1, 0.2, 5.0, 5.1])
    assert any("突跳" in v and "帧 2→3" in v for v in result["verdicts"])


def test_profile_no_false_jump():
    """均匀变化的剖面不应误报突跳。"""
    result = analyze_scan_profile([0.0, 5.0, 10.0, 5.0, 0.0])
    assert not any("突跳" in v for v in result["verdicts"])


def test_profile_multiple_peaks():
    """多峰：全部列出。"""
    result = analyze_scan_profile([0.0, 5.0, 2.0, 6.0, 1.0])
    assert result["ts_index"] == 3
    assert any("多个能量峰" in v and "1" in v and "3" in v for v in result["verdicts"])


# ---------------------------------------------------------------------------
# mode=interpolate
# ---------------------------------------------------------------------------

_R_XYZ = """3
reactant
H  0.0  0.0  0.0
H  1.8  0.0  0.0
H  2.8  0.0  0.0
"""

_P_XYZ = """3
product
H  0.0  0.0  0.0
H  1.0  0.0  0.0
H  1.8  0.0  0.0
"""


def _rotated_translated(xyz_text: str) -> str:
    """对 xyz 施加 90° 绕 z 旋转 + 平移（刚体变换，不改变内部几何）。"""
    atoms = ase.io.read(__import__("io").StringIO(xyz_text), format="xyz")
    theta = math.radians(90.0)
    rot = np.array([
        [math.cos(theta), -math.sin(theta), 0.0],
        [math.sin(theta), math.cos(theta), 0.0],
        [0.0, 0.0, 1.0],
    ])
    atoms.set_positions(atoms.get_positions() @ rot.T + np.array([5.0, -3.0, 2.0]))
    lines = [str(len(atoms)), "rotated"]
    for s, p in zip(atoms.get_chemical_symbols(), atoms.get_positions()):
        lines.append(f"{s} {p[0]:.8f} {p[1]:.8f} {p[2]:.8f}")
    return "\n".join(lines) + "\n"


def _read_distances(xyz_path: Path) -> np.ndarray:
    atoms = ase.io.read(str(xyz_path), format="xyz")
    return atoms.get_all_distances()


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["linear", "idpp"])
async def test_interpolate_frames_and_endpoints(tmp_path, mock_session, method):
    """linear/idpp：帧数正确、文件落盘、端点几何与两端一致、watch 距离单调。"""
    tool = _make_tool()
    out_dir = tmp_path / "imgs"
    result = await tool.safe_call(TsGuess_input_schema(**{
        "mode": "interpolate",
        "reactant_text": _R_XYZ,
        "product_text": _P_XYZ,
        "n_images": 6,
        "interp_method": method,
        "watch_pairs": [[1, 2]],
        "output_dir": str(out_dir),
    }), mock_session)

    assert result.is_success, result.message
    assert result.images_dir == str(out_dir)
    files = sorted(out_dir.glob("img_*.xyz"))
    assert len(files) == 6

    # 端点几何与反应物/产物一致（成对距离不变量，容差 1e-4）
    d_r = _read_distances(files[0])
    d_p = _read_distances(files[-1])
    d_r_ref = ase.io.read(__import__("io").StringIO(_R_XYZ), format="xyz").get_all_distances()
    d_p_ref = ase.io.read(__import__("io").StringIO(_P_XYZ), format="xyz").get_all_distances()
    assert np.allclose(d_r, d_r_ref, atol=1e-4)
    assert np.allclose(d_p, d_p_ref, atol=1e-4)

    # watch 对 (1,2) 距离从 1.8 单调降至 1.0
    d12 = [_read_distances(f)[0, 1] for f in files]
    assert d12[0] == pytest.approx(1.8, abs=1e-4)
    assert d12[-1] == pytest.approx(1.0, abs=1e-4)
    assert all(d12[i] >= d12[i + 1] - 1e-6 for i in range(len(d12) - 1))

    # 距离表 6 行 + 表头，TS 候选帧在合理范围
    assert len(result.distance_table.strip().splitlines()) == 7
    assert 0 <= result.ts_candidate_index < 6
    assert result.ts_candidate_path == str(out_dir / f"img_{result.ts_candidate_index:02d}.xyz")


@pytest.mark.asyncio
async def test_interpolate_rotation_translation_invariant(tmp_path, mock_session):
    """产物施加任意旋转/平移后，距离表与 TS 候选帧不变（验证 Kabsch 对齐）。"""
    tool = _make_tool()
    base = await tool.safe_call(TsGuess_input_schema(**{
        "mode": "interpolate",
        "reactant_text": _R_XYZ,
        "product_text": _P_XYZ,
        "n_images": 6,
        "interp_method": "linear",
        "output_dir": str(tmp_path / "a"),
    }), mock_session)
    moved = await tool.safe_call(TsGuess_input_schema(**{
        "mode": "interpolate",
        "reactant_text": _R_XYZ,
        "product_text": _rotated_translated(_P_XYZ),
        "n_images": 6,
        "interp_method": "linear",
        "output_dir": str(tmp_path / "b"),
    }), mock_session)

    assert base.is_success and moved.is_success
    assert base.distance_table == moved.distance_table
    assert base.ts_candidate_index == moved.ts_candidate_index


@pytest.mark.asyncio
async def test_interpolate_atom_map_equivalence(tmp_path, mock_session):
    """产物原子序打乱 + atom_map：结果与恒等映射等价；非法映射报错。"""
    r_xyz = """3
reactant
C  0.0  0.0  0.0
H  1.1  0.0  0.0
H  3.0  0.0  0.0
"""
    p_ordered = """3
product
C  0.0  0.0  0.0
H  1.1  0.0  0.0
H  2.0  0.0  0.0
"""
    # 打乱：产物第 1 个原子（H@2.0）对应反应物第 3 个原子，第 2（C）→1，第 3（H@1.1）→2
    p_shuffled = """3
product shuffled
H  2.0  0.0  0.0
C  0.0  0.0  0.0
H  1.1  0.0  0.0
"""
    tool = _make_tool()
    ref = await tool.safe_call(TsGuess_input_schema(**{
        "mode": "interpolate",
        "reactant_text": r_xyz,
        "product_text": p_ordered,
        "n_images": 5,
        "interp_method": "linear",
        "output_dir": str(tmp_path / "ref"),
    }), mock_session)
    mapped = await tool.safe_call(TsGuess_input_schema(**{
        "mode": "interpolate",
        "reactant_text": r_xyz,
        "product_text": p_shuffled,
        "atom_map": [3, 1, 2],
        "n_images": 5,
        "interp_method": "linear",
        "output_dir": str(tmp_path / "mapped"),
    }), mock_session)

    assert ref.is_success and mapped.is_success
    assert ref.distance_table == mapped.distance_table
    assert ref.ts_candidate_index == mapped.ts_candidate_index

    # 非法排列
    bad_perm = await tool.safe_call(TsGuess_input_schema(**{
        "mode": "interpolate",
        "reactant_text": r_xyz,
        "product_text": p_shuffled,
        "atom_map": [1, 1, 2],
        "output_dir": str(tmp_path / "bad1"),
    }), mock_session)
    assert not bad_perm.is_success
    assert "排列" in bad_perm.message

    # 元素不匹配（C 映射到 H）
    bad_elem = await tool.safe_call(TsGuess_input_schema(**{
        "mode": "interpolate",
        "reactant_text": r_xyz,
        "product_text": p_shuffled,
        "atom_map": [1, 2, 3],
        "output_dir": str(tmp_path / "bad2"),
    }), mock_session)
    assert not bad_elem.is_success
    assert "元素不匹配" in bad_elem.message


# ---------------------------------------------------------------------------
# mode=scan_prepare
# ---------------------------------------------------------------------------

_WATER_XYZ = """3
water
O  0.000000   0.000000   0.117300
H  0.000000   0.757200  -0.469200
H  0.000000  -0.757200  -0.469200
"""


@pytest.mark.asyncio
async def test_scan_prepare_gaussian(tmp_path, mock_session):
    """Gaussian gjf：modredundant 扫描块、路由、电荷自旋、步长符号正确，无 QST。"""
    tool = _make_tool()
    out = tmp_path / "scan.gjf"
    result = await tool.safe_call(TsGuess_input_schema(**{
        "mode": "scan_prepare",
        "input_text": _WATER_XYZ,
        "engine": "gaussian",
        "coord_type": "bond",
        "atoms": [1, 2],
        "scan_end": 2.0,
        "scan_steps": 10,
        "output_path": str(out),
        "job_name": "h2o_scan",
    }), mock_session)

    assert result.is_success, result.message
    assert result.input_file_path == str(out)
    assert "submit_compute_job" in result.run_hint and "gaussian" in result.run_hint
    content = out.read_text()
    assert "qst" not in content.lower()
    assert "%chk=h2o_scan.chk" in content
    assert "opt=(modredundant,maxstep=10)" in content
    assert "b3lyp/def2svp" in content
    assert "\n0 1\n" in content
    # 当前 O-H 键长 ≈ 0.9589 Å，步长 = (2.0 - 0.9589)/10 ≈ +0.104
    m = __import__("re").search(r"^B 1 2 S 10 ([-\d.]+)$", content, __import__("re").M)
    assert m, content
    start = math.dist((0.0, 0.0, 0.1173), (0.0, 0.7572, -0.4692))
    assert float(m.group(1)) == pytest.approx((2.0 - start) / 10, abs=1e-5)


@pytest.mark.asyncio
async def test_scan_prepare_orca(tmp_path, mock_session):
    """ORCA inp：%geom Scan 块、原子序号 0-based、%pal，无 QST。"""
    tool = _make_tool()
    out = tmp_path / "scan.inp"
    result = await tool.safe_call(TsGuess_input_schema(**{
        "mode": "scan_prepare",
        "input_text": _WATER_XYZ,
        "engine": "orca",
        "coord_type": "angle",
        "atoms": [2, 1, 3],
        "scan_start": 90.0,
        "scan_end": 120.0,
        "scan_steps": 6,
        "nprocs": 8,
        "output_path": str(out),
    }), mock_session)

    assert result.is_success, result.message
    assert "orca" in result.run_hint
    content = out.read_text()
    assert "qst" not in content.lower()
    assert "%pal nprocs 8 end" in content
    assert "%geom" in content
    # 原子序号 0-based：输入 [2,1,3] → 输出 1 0 2
    assert "Scan A 1 0 2 = 90.000000, 120.000000, 6 end" in content
    assert content.startswith("! OPT b3lyp def2svp")
    assert "* xyz 0 1" in content


@pytest.mark.asyncio
async def test_scan_prepare_atoms_validation(tmp_path, mock_session):
    """原子个数/序号校验：bond 需要 2 个原子。"""
    tool = _make_tool()
    result = await tool.safe_call(TsGuess_input_schema(**{
        "mode": "scan_prepare",
        "input_text": _WATER_XYZ,
        "coord_type": "dihedral",
        "atoms": [1, 2, 3],
        "scan_end": 180.0,
        "scan_steps": 5,
        "output_path": str(tmp_path / "x.gjf"),
    }), mock_session)
    assert not result.is_success
    assert "4 个原子" in result.message


# ---------------------------------------------------------------------------
# mode=scan_parse（真实 G09 扫描日志 fixture）
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_scan_parse_h2_fixture(tmp_path, mock_session):
    """h2_scan_g09.log：101 点剖面、势垒人工核对值、边界判定、TS 初猜几何提取。

    人工核对（Summary of Optimized Potential Surface Scan 表，Eigenvalues 单位 Eh）：
    - 首点（帧 0，R=0.60 Å）：-1.15022
    - 最高点（帧 100，R=1.60 Å）：-1.04070
    - 势垒 = (-1.04070 - (-1.15022)) × 627.5095 = 0.10952 Eh × 627.5095 ≈ 68.72 kcal/mol
    能量从帧 15（R=0.75 Å，极小 -1.17060）之后单调上升至末端，最高点在扫描边界。
    """
    tool = _make_tool()
    ts_path = tmp_path / "h2_ts_guess.xyz"
    result = await tool.safe_call(TsGuess_input_schema(**{
        "mode": "scan_parse",
        "log_path": str(SCAN_LOG),
        "engine": "gaussian",
        "ts_candidate_path": str(ts_path),
    }), mock_session)

    assert result.is_success, result.message

    # 剖面长度：101 个点 + 表头
    rows = result.profile_table.strip().splitlines()
    assert len(rows) == 102

    # 势垒人工核对值（5 位小数表值）
    expected = (-1.04070 - (-1.15022)) * 627.5095
    assert result.barrier_kcal == pytest.approx(expected, abs=1e-3)

    # 最高点在末帧 → 边界判定
    assert result.ts_candidate_index == 100
    assert any("边界" in v for v in result.verdicts)

    # TS 初猜 xyz：2 个 H，键长 ≈ 1.60 Å（末帧扫描点几何）
    assert ts_path.is_file()
    assert result.ts_candidate_path == str(ts_path)
    atoms = ase.io.read(str(ts_path), format="xyz")
    assert len(atoms) == 2
    assert atoms.get_chemical_symbols() == ["H", "H"]
    assert atoms.get_distance(0, 1) == pytest.approx(1.60, abs=1e-3)


# ---------------------------------------------------------------------------
# mode=verify
# ---------------------------------------------------------------------------

# 合成 Gaussian 频率输出片段：1 个虚频（负值）+ 正常终止，走工具的正则回退解析
_TS_FREQ_SNIPPET = """\
 Harmonic frequencies (cm**-1), IR intensities (KM/Mole), Raman scattering
                      1                      2                      3
                      A                      A                      A
 Frequencies --   -915.3388               1200.0000              1300.0000
 Red. masses --      1.0078                 1.0078                 1.0078
  Atom  AN      X      Y      Z        X      Y      Z        X      Y      Z
     1   6     0.05   0.00   0.00     0.00   0.10   0.00     0.00   0.00   0.10
     2   7    -0.05   0.00   0.00     0.00  -0.10   0.00     0.00   0.00  -0.10
     3   1     0.80   0.00   0.00     0.00   0.00   0.10     0.00   0.10   0.00
 Normal termination of Gaussian 16 at Sat Mar 22 18:44:39 2025.
"""

# 虚频模式：H 相对 C/N 大幅位移（与 watch_pairs C-H、N-H 一致）
_TS_FREQ_WITH_GEOMETRY = """\
 Standard orientation:
 ---------------------------------------------------------------------
 Center     Atomic      Atomic             Coordinates (Angstroms)
 Number     Number       Type             X           Y           Z
 ---------------------------------------------------------------------
      1          6           0        0.427601   -0.595125    0.000000
      2          7           0       -0.354874    0.327913    0.000000
      3          1           0       -0.680027   -1.045650    0.000000
 ---------------------------------------------------------------------
 Harmonic frequencies (cm**-1), IR intensities (KM/Mole), Raman scattering
                      1                      2                      3
                      A                      A                      A
 Frequencies --   -915.3388               1200.0000              1300.0000
 Red. masses --      1.0078                 1.0078                 1.0078
  Atom  AN      X      Y      Z        X      Y      Z        X      Y      Z
     1   6     0.05   0.00   0.00     0.00   0.10   0.00     0.00   0.00   0.10
     2   7    -0.05   0.00   0.00     0.00  -0.10   0.00     0.00   0.00  -0.10
     3   1     0.80   0.00   0.00     0.00   0.00   0.10     0.00   0.10   0.00
 Normal termination of Gaussian 16 at Sat Mar 22 18:44:39 2025.
"""

# 虚频模式：主要是 C–N 相对伸缩，H 几乎不动（与声明反应坐标不符）
_TS_FREQ_WRONG_MODE = """\
 Standard orientation:
 ---------------------------------------------------------------------
 Center     Atomic      Atomic             Coordinates (Angstroms)
 Number     Number       Type             X           Y           Z
 ---------------------------------------------------------------------
      1          6           0        0.427601   -0.595125    0.000000
      2          7           0       -0.354874    0.327913    0.000000
      3          1           0       -0.680027   -1.045650    0.000000
 ---------------------------------------------------------------------
 Harmonic frequencies (cm**-1), IR intensities (KM/Mole), Raman scattering
                      1                      2                      3
                      A                      A                      A
 Frequencies --   -915.3388               1200.0000              1300.0000
 Red. masses --      1.0078                 1.0078                 1.0078
  Atom  AN      X      Y      Z        X      Y      Z        X      Y      Z
     1   6     1.00   0.00   0.00     0.00   0.10   0.00     0.00   0.00   0.10
     2   7    -1.00   0.00   0.00     0.00  -0.10   0.00     0.00   0.00  -0.10
     3   1     0.00   0.00   0.00     0.00   0.00   0.10     0.00   0.10   0.00
 Normal termination of Gaussian 16 at Sat Mar 22 18:44:39 2025.
"""

# 有虚频但无简正模式位移块
_TS_FREQ_NO_DISPS = """\
 Standard orientation:
 ---------------------------------------------------------------------
 Center     Atomic      Atomic             Coordinates (Angstroms)
 Number     Number       Type             X           Y           Z
 ---------------------------------------------------------------------
      1          6           0        0.427601   -0.595125    0.000000
      2          7           0       -0.354874    0.327913    0.000000
      3          1           0       -0.680027   -1.045650    0.000000
 ---------------------------------------------------------------------
 Harmonic frequencies (cm**-1), IR intensities (KM/Mole), Raman scattering
 Frequencies --   -915.3388               1200.0000              1300.0000
 Normal termination of Gaussian 16 at Sat Mar 22 18:44:39 2025.
"""

# HCN → HNC 异构化：与 IRC 作业同原子序（C, N, H）
_HCN_XYZ = """3
HCN reactant
C  0.0  0.0  0.0
N  0.0  0.0  1.16
H  0.0  0.0  -1.07
"""

_HNC_XYZ = """3
HNC product
C  0.0  0.0  0.0
N  0.0  0.0  1.17
H  0.0  0.0  2.17
"""

_TS_GEOMETRY_XYZ = """3
TS geometry
C   0.427601  -0.595125  0.000000
N  -0.354874   0.327913  0.000000
H  -0.680027  -1.045650  0.000000
"""

_HCN_REORDERED_XYZ = """3
HCN with incompatible atom order
N  0.0  0.0  1.16
C  0.0  0.0  0.0
H  0.0  0.0  -1.07
"""


@pytest.mark.asyncio
async def test_verify_ts_positive(tmp_path, mock_session):
    """默认 verify 只提供方向建议，即使频率与端点相符也只返回 candidate。"""
    tool = _make_tool()
    freq_log = tmp_path / "ts_freq.log"
    freq_log.write_text(_TS_FREQ_SNIPPET)
    out_dir = tmp_path / "verify"

    result = await tool.safe_call(TsGuess_input_schema(**{
        "mode": "verify",
        "freq_log": str(freq_log),
        "irc_log": str(IRC_LOG),
        "reactant_text": _HCN_XYZ,
        "product_text": _HNC_XYZ,
        "output_dir": str(out_dir),
    }), mock_session)

    assert result.is_success, result.message
    assert result.n_imag == 1
    assert result.imag_freqs == [pytest.approx(-915.34, abs=0.01)]
    assert result.verdict.startswith("candidate")
    assert any("1 个虚频" in c for c in result.checks)
    assert any("连通性一致" in c for c in result.checks)

    # IRC 端点落盘，各 3 原子
    for p in (result.irc_end_a_path, result.irc_end_b_path):
        atoms = ase.io.read(p, format="xyz")
        assert len(atoms) == 3


@pytest.mark.asyncio
async def test_verify_minimum_negative(tmp_path, mock_session):
    """默认 verify 是建议模式：无虚频时报告 unlikely，而不是严肃验收。"""
    tool = _make_tool()
    result = await tool.safe_call(TsGuess_input_schema(**{
        "mode": "verify",
        "freq_log": str(OPT_FREQ_LOG),
    }), mock_session)

    assert result.is_success, result.message
    assert result.n_imag == 0
    assert result.imag_freqs == []
    assert result.verdict.startswith("unlikely")
    assert any("极小点" in c for c in result.checks)


@pytest.mark.asyncio
async def test_verify_high_order_saddle(tmp_path, mock_session):
    """默认 verify 是建议模式：2 个虚频时报告 unlikely。"""
    tool = _make_tool()
    freq_log = tmp_path / "bad_ts_freq.log"
    freq_log.write_text(
        " Harmonic frequencies (cm**-1)\n"
        " Frequencies --   -915.3388               -200.0000              1300.0000\n"
        " Normal termination of Gaussian 16 at Sat Mar 22 18:44:39 2025.\n"
    )
    result = await tool.safe_call(TsGuess_input_schema(**{
        "mode": "verify",
        "freq_log": str(freq_log),
    }), mock_session)

    assert result.is_success, result.message
    assert result.n_imag == 2
    assert result.verdict.startswith("unlikely")
    assert any("高阶鞍点" in c for c in result.checks)


@pytest.mark.asyncio
async def test_verify_irc_endpoints_without_expected(tmp_path, mock_session):
    """提供 IRC 但不给预期结构：只提取端点并报告成键表，不判连通性。"""
    tool = _make_tool()
    freq_log = tmp_path / "ts_freq.log"
    freq_log.write_text(_TS_FREQ_SNIPPET)

    result = await tool.safe_call(TsGuess_input_schema(**{
        "mode": "verify",
        "freq_log": str(freq_log),
        "irc_log": str(IRC_LOG),
        "output_dir": str(tmp_path / "verify"),
    }), mock_session)

    assert result.is_success, result.message
    assert result.n_imag == 1
    assert result.verdict.startswith("candidate")
    assert any("成键" in c for c in result.checks)
    assert not any("不一致" in c for c in result.checks)


@pytest.mark.asyncio
async def test_verify_strict_accepts_partial_irc_between_ts_and_intermediates(tmp_path, mock_session):
    """IRC 两侧均因 maxsteps 未走到底，但处于 TS 与优化中间体之间时 strict 应通过。"""
    tool = _make_tool()
    freq_log = tmp_path / "ts_freq_with_geometry.log"
    freq_log.write_text(_TS_FREQ_WITH_GEOMETRY)

    result = await tool.safe_call(TsGuess_input_schema(**{
        "mode": "verify",
        "strict": True,
        "freq_log": str(freq_log),
        "irc_log": str(IRC_LOG),
        "reactant_text": _HCN_XYZ,
        "product_text": _HNC_XYZ,
        "watch_pairs": [[1, 3], [2, 3]],
        "output_dir": str(tmp_path / "strict_verify"),
    }), mock_session)

    assert result.is_success, result.message
    assert result.verdict.startswith("pass")
    assert any("中间" in check for check in result.checks)
    assert result.irc_end_a_path and result.irc_end_b_path


@pytest.mark.asyncio
async def test_verify_strict_without_optimized_intermediates_is_inconclusive(tmp_path, mock_session):
    """strict 缺少优化中间体时证据不足，不能沿用默认模式的候选结论。"""
    tool = _make_tool()
    freq_log = tmp_path / "ts_freq_with_geometry.log"
    freq_log.write_text(_TS_FREQ_WITH_GEOMETRY)

    result = await tool.safe_call(TsGuess_input_schema(**{
        "mode": "verify",
        "strict": True,
        "freq_log": str(freq_log),
        "irc_log": str(IRC_LOG),
        "output_dir": str(tmp_path / "strict_missing"),
    }), mock_session)

    assert result.is_success, result.message
    assert result.verdict.startswith("inconclusive")


@pytest.mark.asyncio
async def test_verify_strict_rejects_wrong_intermediate_pair(tmp_path, mock_session):
    """材料完整但两个预期结构都在同一侧时，另一侧 IRC 明确朝错方向，应 fail。"""
    tool = _make_tool()
    freq_log = tmp_path / "ts_freq_with_geometry.log"
    freq_log.write_text(_TS_FREQ_WITH_GEOMETRY)

    result = await tool.safe_call(TsGuess_input_schema(**{
        "mode": "verify",
        "strict": True,
        "freq_log": str(freq_log),
        "irc_log": str(IRC_LOG),
        "reactant_text": _HCN_XYZ,
        "product_text": _HCN_XYZ,
        "watch_pairs": [[1, 3], [2, 3]],
        "output_dir": str(tmp_path / "strict_wrong"),
    }), mock_session)

    assert result.is_success, result.message
    assert result.verdict.startswith("fail")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("frequency_line", "expected_n_imag"),
    [
        ("Frequencies --   300.0  1200.0  1300.0", 0),
        ("Frequencies --  -915.0  -200.0  1300.0", 2),
    ],
)
async def test_verify_strict_rejects_non_first_order_stationary_points(
    tmp_path, mock_session, frequency_line, expected_n_imag,
):
    """strict 对正常结束的极小点或高阶鞍点给出明确 fail。"""
    tool = _make_tool()
    freq_log = tmp_path / f"strict_{expected_n_imag}_imag.log"
    freq_log.write_text(f"{frequency_line}\nNormal termination of Gaussian 16.\n")

    result = await tool.safe_call(TsGuess_input_schema(**{
        "mode": "verify",
        "strict": True,
        "freq_log": str(freq_log),
    }), mock_session)

    assert result.is_success, result.message
    assert result.n_imag == expected_n_imag
    assert result.verdict.startswith("fail")


@pytest.mark.asyncio
async def test_verify_strict_atom_order_mismatch_is_inconclusive(tmp_path, mock_session):
    """距离坐标依赖原子映射；结构原子序不一致时不能武断判错路径。"""
    tool = _make_tool()
    freq_log = tmp_path / "ts_freq_with_geometry.log"
    freq_log.write_text(_TS_FREQ_WITH_GEOMETRY)

    result = await tool.safe_call(TsGuess_input_schema(**{
        "mode": "verify",
        "strict": True,
        "freq_log": str(freq_log),
        "irc_log": str(IRC_LOG),
        "reactant_text": _HCN_REORDERED_XYZ,
        "product_text": _HNC_XYZ,
        "output_dir": str(tmp_path / "strict_order_mismatch"),
    }), mock_session)

    assert result.is_success, result.message
    assert result.verdict.startswith("inconclusive")
    assert any("原子顺序不一致" in check for check in result.checks)


@pytest.mark.asyncio
async def test_verify_strict_no_informative_pair_is_inconclusive(tmp_path, mock_session):
    """两个所谓中间体都与 TS 相同，自动选不到变化原子对时证据不足。"""
    tool = _make_tool()
    freq_log = tmp_path / "ts_freq_with_geometry.log"
    freq_log.write_text(_TS_FREQ_WITH_GEOMETRY)

    result = await tool.safe_call(TsGuess_input_schema(**{
        "mode": "verify",
        "strict": True,
        "freq_log": str(freq_log),
        "irc_log": str(IRC_LOG),
        "reactant_text": _TS_GEOMETRY_XYZ,
        "product_text": _TS_GEOMETRY_XYZ,
        "output_dir": str(tmp_path / "strict_no_pairs"),
    }), mock_session)

    assert result.is_success, result.message
    assert result.verdict.startswith("inconclusive")


@pytest.mark.asyncio
async def test_verify_strict_rejects_imag_mode_misaligned_with_watch_pairs(tmp_path, mock_session):
    """strict：虚频模式主要不在声明的反应中心原子对上时，应 fail。"""
    tool = _make_tool()
    freq_log = tmp_path / "ts_freq_wrong_mode.log"
    freq_log.write_text(_TS_FREQ_WRONG_MODE)

    result = await tool.safe_call(TsGuess_input_schema(**{
        "mode": "verify",
        "strict": True,
        "freq_log": str(freq_log),
        "irc_log": str(IRC_LOG),
        "reactant_text": _HCN_XYZ,
        "product_text": _HNC_XYZ,
        "watch_pairs": [[1, 3], [2, 3]],
        "output_dir": str(tmp_path / "strict_bad_mode"),
    }), mock_session)

    assert result.is_success, result.message
    assert result.verdict.startswith("fail")
    assert any("虚频模式" in check or "反应坐标" in check for check in result.checks)
    assert result.imag_mode_aligned is False


@pytest.mark.asyncio
async def test_verify_strict_missing_vibdisps_is_inconclusive(tmp_path, mock_session):
    """strict：频率日志无简正模式位移时无法核对虚频方向，应 inconclusive。"""
    tool = _make_tool()
    freq_log = tmp_path / "ts_freq_no_disps.log"
    freq_log.write_text(_TS_FREQ_NO_DISPS)

    result = await tool.safe_call(TsGuess_input_schema(**{
        "mode": "verify",
        "strict": True,
        "freq_log": str(freq_log),
        "irc_log": str(IRC_LOG),
        "reactant_text": _HCN_XYZ,
        "product_text": _HNC_XYZ,
        "watch_pairs": [[1, 3], [2, 3]],
        "output_dir": str(tmp_path / "strict_no_disps"),
    }), mock_session)

    assert result.is_success, result.message
    assert result.verdict.startswith("inconclusive")
    assert any("简正模式位移" in check for check in result.checks)
    assert result.imag_mode_aligned is None


@pytest.mark.asyncio
async def test_verify_non_strict_reports_mode_alignment_without_changing_verdict(
    tmp_path, mock_session,
):
    """非 strict：模式不对齐只写入 checks，仍保持 candidate 语义。"""
    tool = _make_tool()
    freq_log = tmp_path / "ts_freq_wrong_mode.log"
    freq_log.write_text(_TS_FREQ_WRONG_MODE)

    result = await tool.safe_call(TsGuess_input_schema(**{
        "mode": "verify",
        "freq_log": str(freq_log),
        "watch_pairs": [[1, 3], [2, 3]],
        "output_dir": str(tmp_path / "non_strict_mode"),
    }), mock_session)

    assert result.is_success, result.message
    assert result.verdict.startswith("candidate")
    assert any("虚频模式" in check or "反应坐标" in check for check in result.checks)
    assert result.imag_mode_aligned is False


def test_imag_mode_alignment_helper_uses_relative_displacement_ratio():
    from cloudra.tools.Chemtool.ts_guess import _assess_imag_mode_alignment

    vibfreqs = [-900.0, 1200.0, 1300.0]
    vibdisps = np.array([
        [[0.05, 0.0, 0.0], [-0.05, 0.0, 0.0], [0.80, 0.0, 0.0]],
        [[0.0, 0.1, 0.0], [0.0, -0.1, 0.0], [0.0, 0.0, 0.1]],
        [[0.0, 0.0, 0.1], [0.0, 0.0, -0.1], [0.0, 0.1, 0.0]],
    ], dtype=float)
    ok = _assess_imag_mode_alignment(
        vibfreqs, vibdisps, watch_pairs=[[1, 3], [2, 3]], **{}
    )
    assert ok["status"] == "aligned"
    assert ok["aligned"] is True

    bad_disps = np.array([
        [[1.0, 0.0, 0.0], [-1.0, 0.0, 0.0], [0.0, 0.0, 0.0]],
        [[0.0, 0.1, 0.0], [0.0, -0.1, 0.0], [0.0, 0.0, 0.1]],
        [[0.0, 0.0, 0.1], [0.0, 0.0, -0.1], [0.0, 0.1, 0.0]],
    ], dtype=float)
    bad = _assess_imag_mode_alignment(
        vibfreqs, bad_disps, watch_pairs=[[1, 3], [2, 3]], **{}
    )
    assert bad["status"] == "misaligned"
    assert bad["aligned"] is False

    missing = _assess_imag_mode_alignment(
        vibfreqs, None, watch_pairs=[[1, 3]], **{}
    )
    assert missing["status"] == "missing"
    assert missing["aligned"] is None
