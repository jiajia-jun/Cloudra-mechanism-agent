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
    KCAL_PER_HARTREE,
    TsGuess,
    TsGuess_input_schema,
    _assign_irc_endpoints,
    _evaluate_endpoint_between,
    _idpp_relax,
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
    assert any("monotonic" in v for v in result["verdicts"])
    assert any("boundary" in v for v in result["verdicts"])


def test_profile_peak_at_boundary():
    """峰在端点（首帧）：提示扩大扫描范围；barrier = max − 首点 = 0。"""
    result = analyze_scan_profile([5.0, 3.0, 1.0, 0.0])
    assert result["ts_index"] == 0
    assert result["barrier_kcal"] == pytest.approx(0.0)
    assert any("boundary" in v for v in result["verdicts"])
    assert any("monotonic" in v for v in result["verdicts"])  # 单调递减同时触发单调判定


def test_profile_discontinuity():
    """相邻能量突跳 > 3×中位数且 > 2 kcal/mol：报滑谷/不连续。"""
    result = analyze_scan_profile([0.0, 0.1, 0.2, 5.0, 5.1])
    assert any("jump" in v and "frames 2→3" in v for v in result["verdicts"])


def test_profile_no_false_jump():
    """均匀变化的剖面不应误报突跳。"""
    result = analyze_scan_profile([0.0, 5.0, 10.0, 5.0, 0.0])
    assert not any("jump" in v for v in result["verdicts"])


def test_profile_multiple_peaks():
    """多峰：全部列出。"""
    result = analyze_scan_profile([0.0, 5.0, 2.0, 6.0, 1.0])
    assert result["ts_index"] == 3
    assert any("Multiple energy peaks" in v and "1" in v and "3" in v for v in result["verdicts"])


# ---------------------------------------------------------------------------
# mode=interpolate
# ---------------------------------------------------------------------------

def test_idpp_relax_broadcasts_when_pair_count_is_not_three():
    """C6H10 一类体系 npair=n(n-1)/2 ≠ 3 时，旧实现 (npair,)*(npair,3) 广播崩溃。"""
    rng = np.random.default_rng(0)
    images = rng.normal(size=(5, 4, 3))
    out = _idpp_relax(images, max_iter=8)
    assert out.shape == (5, 4, 3)
    assert np.allclose(out[0], images[0])
    assert np.allclose(out[-1], images[-1])


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
    assert "permutation" in bad_perm.message

    # 元素不匹配（C 映射到 H）
    bad_elem = await tool.safe_call(TsGuess_input_schema(**{
        "mode": "interpolate",
        "reactant_text": r_xyz,
        "product_text": p_shuffled,
        "atom_map": [1, 2, 3],
        "output_dir": str(tmp_path / "bad2"),
    }), mock_session)
    assert not bad_elem.is_success
    assert "element mismatch" in bad_elem.message


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
        "scans": [{
            "coord_type": "bond",
            "atoms": [1, 2],
            "scan_end": 2.0,
            "scan_steps": 10,
        }],
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
async def test_scan_prepare_gaussian_two_coupled_coordinates(tmp_path, mock_session):
    """Gaussian 双坐标耦合扫描：两个 S 行（2D 网格），各自步长独立。"""
    tool = _make_tool()
    out = tmp_path / "scan2d.gjf"
    result = await tool.safe_call(TsGuess_input_schema(**{
        "mode": "scan_prepare",
        "input_text": _WATER_XYZ,
        "engine": "gaussian",
        "scans": [
            {"coord_type": "bond", "atoms": [1, 2], "scan_end": 2.0, "scan_steps": 10},
            {"coord_type": "bond", "atoms": [1, 3], "scan_end": 1.2, "scan_steps": 8},
        ],
        "output_path": str(out),
    }), mock_session)

    assert result.is_success, result.message
    content = out.read_text()
    lines = [ln for ln in content.splitlines() if ln.startswith("B 1")]
    assert len(lines) == 2, content
    assert lines[0].startswith("B 1 2 S 10")
    assert lines[1].startswith("B 1 3 S 8")
    assert "2D coupled" in result.run_hint


@pytest.mark.asyncio
async def test_scan_prepare_orca(tmp_path, mock_session):
    """ORCA inp：%geom Scan 块、原子序号 0-based、%pal，无 QST。"""
    tool = _make_tool()
    out = tmp_path / "scan.inp"
    result = await tool.safe_call(TsGuess_input_schema(**{
        "mode": "scan_prepare",
        "input_text": _WATER_XYZ,
        "engine": "orca",
        "scans": [{
            "coord_type": "angle",
            "atoms": [2, 1, 3],
            "scan_start": 90.0,
            "scan_end": 120.0,
            "scan_steps": 6,
        }],
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
    # 组合条目拼写 b3lyp/def2svp 必须落成 ORCA 原生基组拼写 def2-SVP
    assert content.startswith("! OPT b3lyp def2-SVP")
    assert "* xyz 0 1" in content


@pytest.mark.asyncio
async def test_scan_prepare_orca_extopt_mlip_blocks(tmp_path, mock_session):
    """ORCA external/MLIP 势通道：method='ExtOpt' + orca_blocks 注入 %method ProgExt 块。"""
    tool = _make_tool()
    out = tmp_path / "scan_mlip.inp"
    prog_block = (
        "%method\n"
        '  ProgExt "/Users/x/envs/chemai/bin/mace"\n'
        '  Ext_Params "--model /Users/x/mace.model --device cpu --dtype float64"\n'
        "end"
    )
    result = await tool.safe_call(TsGuess_input_schema(**{
        "mode": "scan_prepare",
        "input_text": _WATER_XYZ,
        "engine": "orca",
        "method": "ExtOpt",
        "scans": [{"coord_type": "bond", "atoms": [1, 2], "scan_end": 2.0, "scan_steps": 10}],
        "orca_blocks": prog_block,
        "output_path": str(out),
    }), mock_session)

    assert result.is_success, result.message
    content = out.read_text()
    assert content.startswith("! OPT ExtOpt")
    assert "Scan B 0 1 = " in content
    assert "ProgExt" in content and "--model" in content
    # %method 块位于坐标块之前
    assert content.index("%method") < content.index("* xyz")


@pytest.mark.asyncio
async def test_scan_prepare_rejects_multi_coord_on_orca(tmp_path, mock_session):
    """ORCA relaxed scan 是 1D：两个扫描坐标报错并提示用 Gaussian。"""
    tool = _make_tool()
    result = await tool.safe_call(TsGuess_input_schema(**{
        "mode": "scan_prepare",
        "input_text": _WATER_XYZ,
        "engine": "orca",
        "scans": [
            {"coord_type": "bond", "atoms": [1, 2], "scan_end": 2.0, "scan_steps": 10},
            {"coord_type": "bond", "atoms": [1, 3], "scan_end": 1.2, "scan_steps": 8},
        ],
        "output_path": str(tmp_path / "x.inp"),
    }), mock_session)
    assert not result.is_success
    assert "1D" in result.message


@pytest.mark.asyncio
async def test_scan_prepare_atoms_validation(tmp_path, mock_session):
    """原子个数/序号校验：dihedral 需要 4 个原子。"""
    tool = _make_tool()
    result = await tool.safe_call(TsGuess_input_schema(**{
        "mode": "scan_prepare",
        "input_text": _WATER_XYZ,
        "scans": [{
            "coord_type": "dihedral",
            "atoms": [1, 2, 3],
            "scan_end": 180.0,
            "scan_steps": 5,
        }],
        "output_path": str(tmp_path / "x.gjf"),
    }), mock_session)
    assert not result.is_success
    assert "4 atom indices" in result.message


# ---------------------------------------------------------------------------
# mode=scan_parse（真实 G09 扫描日志 fixture）
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_scan_parse_h2_fixture(tmp_path, mock_session):
    """h2_scan_g09.log：101 点剖面、势垒人工核对值、边界判定、单调无峰不产 TS 初猜。

    人工核对（Summary of Optimized Potential Surface Scan 表，Eigenvalues 单位 Eh）：
    - 首点（帧 0，R=0.60 Å）：-1.15022
    - 最高点（帧 100，R=1.60 Å）：-1.04070
    - 势垒 = (-1.04070 - (-1.15022)) × 627.5095 = 0.10952 Eh × 627.5095 ≈ 68.72 kcal/mol
    能量从帧 15（R=0.75 Å，极小 -1.17060）之后单调上升至末端，最高点在扫描边界。
    H2 均裂解离无鞍点：边界极大不是 TS 候选，工具必须拒绝产出 TS-guess。
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

    # 势垒人工核对值（5 位小数表值）——H2 均裂剖面的端点间能量跨度仍呈现在表内：
    # 最高点（末帧，R=1.60 Å，-1.04070）相对首点 = (-1.04070 - (-1.15022)) × 627.5 ≈ 68.72 kcal/mol
    expected = (-1.04070 - (-1.15022)) * 627.5095
    rel_vals = [float(ln.split()[1]) for ln in rows[1:]]
    assert max(rel_vals) == pytest.approx(expected, abs=1e-3)
    # G4：无内部峰（最高点在扫描边界）时 barrier_kcal 置 None——端点"最高点−首点"
    # 不是能垒，不允许在 barrier 字段里报成势垒。
    assert result.barrier_kcal is None

    # 最高点在末帧 → 边界判定
    assert any("boundary" in v for v in result.verdicts)

    # H2 解离剖面单调无内部峰：端点最高不是 TS 候选 —— 不写 TS-guess 文件，
    # 并给出明确告警（防止把解离扫描端点误当 TS 初猜提交 OptTS）。
    assert result.ts_candidate_index is None
    assert result.ts_candidate_path == ""
    assert not ts_path.exists()
    assert any("no internal energy peak" in v for v in result.verdicts)
    assert "NOT a TS candidate" in result.message
    # profile 表不标 TS guess
    assert "TS guess" not in result.profile_table


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
    assert any("1 imaginary frequency" in c for c in result.checks)
    assert any("connectivity is consistent" in c for c in result.checks)

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
    assert any("minimum" in c for c in result.checks)


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
    assert any("higher-order saddle" in c for c in result.checks)


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
    assert any("bonds" in c for c in result.checks)
    assert not any("inconsistent" in c for c in result.checks)


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
    assert any("intermediate" in check for check in result.checks)
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
    assert any("atom order" in check for check in result.checks)


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
    assert any("imaginary mode" in check or "reaction coordinate" in check for check in result.checks)
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
    assert any("normal-mode displacements" in check for check in result.checks)
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
    assert any("imaginary mode" in check or "reaction coordinate" in check for check in result.checks)
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


# ---------------------------------------------------------------------------
# mode=scan_parse（ORCA relaxed-scan sidecar：能量最高帧优先于末帧）
# ---------------------------------------------------------------------------

_ORCA_SCAN_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "orca" / "cope_relaxed_scan"


@pytest.mark.asyncio
async def test_scan_parse_orca_sidecar_picks_energy_max_frame(tmp_path, mock_session):
    """ORCA relaxed scan：TS 候选几何 = relaxscanact.dat 能量最高帧（.out 缺失也可）。

    把第 10 帧（1-based）能量改为全场最高（+300）→ 能量最高点落在帧 10，
    TS-guess xyz 必须等于 ts_scan.010.xyz 的几何，而不是 rfind 末帧（帧 20）。
    """
    import shutil

    shutil.copy(_ORCA_SCAN_FIXTURE / "ts_scan.relaxscanact.dat", tmp_path / "ts_scan.relaxscanact.dat")
    for p in sorted(_ORCA_SCAN_FIXTURE.glob("ts_scan.[0-9][0-9][0-9].xyz")):
        shutil.copy(p, tmp_path / p.name)

    dat = tmp_path / "ts_scan.relaxscanact.dat"
    lines = dat.read_text(encoding="utf-8").splitlines()
    fields = lines[9].split()
    fields[1] = "300.0"
    lines[9] = "  ".join(fields)
    dat.write_text("\n".join(lines) + "\n", encoding="utf-8")

    tool = _make_tool()
    result = await tool.safe_call(TsGuess_input_schema(**{
        "mode": "scan_parse",
        "engine": "orca",
        "log_path": str(tmp_path / "ts_scan.out"),  # .out 不存在 → 走 sidecar
    }), mock_session)

    assert result.is_success, result.message
    assert result.ts_candidate_index == 9
    guess = Path(result.ts_candidate_path)
    assert guess.exists()
    assert "frame=9" in guess.read_text(encoding="utf-8").splitlines()[1]
    assert result.barrier_kcal is not None  # 内部峰存在才报 barrier

    expected = (tmp_path / "ts_scan.010.xyz").read_text(encoding="utf-8").splitlines()[2:]
    actual = guess.read_text(encoding="utf-8").splitlines()[2:]
    assert len(actual) == len(expected) == 16
    for a_line, e_line in zip(actual, expected):
        a = [float(v) for v in a_line.split()[1:]]
        e = [float(v) for v in e_line.split()[1:]]
        assert a == pytest.approx(e, abs=1e-6)
    assert any("sidecar" in v for v in result.verdicts)


@pytest.mark.asyncio
async def test_scan_parse_orca_sidecar_monotonic_profile_max_at_last_frame(tmp_path, mock_session):
    """不改能量：真实剖面沿扫描坐标单调升——无内部峰，不产出 TS-guess（端点帧不是候选）。"""
    import shutil

    shutil.copy(_ORCA_SCAN_FIXTURE / "ts_scan.relaxscanact.dat", tmp_path / "ts_scan.relaxscanact.dat")
    for p in sorted(_ORCA_SCAN_FIXTURE.glob("ts_scan.[0-9][0-9][0-9].xyz")):
        shutil.copy(p, tmp_path / p.name)

    tool = _make_tool()
    result = await tool.safe_call(TsGuess_input_schema(**{
        "mode": "scan_parse",
        "engine": "orca",
        "log_path": str(tmp_path / "ts_scan.out"),
    }), mock_session)

    assert result.is_success, result.message
    # 单调剖面（无论升/降）无内部峰：不产出 TS-guess，端点帧不得当候选
    assert result.ts_candidate_index is None
    assert result.ts_candidate_path == ""
    assert any("no internal energy peak" in v for v in result.verdicts)
    assert "NOT a TS candidate" in result.message
    assert "TS guess" not in result.profile_table
    # G4：无内部峰时 barrier_kcal 置 None，且不得声称 "TS-guess geometry is ..."
    assert result.barrier_kcal is None
    assert not any("TS-guess geometry" in v for v in result.verdicts)


# ---------------------------------------------------------------------------
# mode=scan_parse（GH #23：ORCA 外部 MLIP ExtOpt 松弛扫描解析）
# ---------------------------------------------------------------------------

_EXTOPT_SCAN_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "orca" / "extopt_relaxed_scan"


def _copy_extopt_log(tmp_path: Path, name: str = "extopt_scan.out") -> Path:
    import shutil

    dst = tmp_path / name
    # 带 RELAXED SURFACE SCAN STEP 标记的片段：文本回退按扫描步分组解析
    shutil.copy(_EXTOPT_SCAN_FIXTURE / "scan_extopt_grouped.out", dst)
    return dst


@pytest.mark.asyncio
async def test_scan_parse_orca_extopt_text_parses_external_program_energies(tmp_path, mock_session):
    """ExtOpt 日志的能量行带 "(From external program)" 后缀，文本路径必须能解析；
    且 TS-guess 几何取能量最高帧（帧 3，0-based 2）的坐标块，不是 rfind 末帧。"""
    log = _copy_extopt_log(tmp_path)

    tool = _make_tool()
    result = await tool.safe_call(TsGuess_input_schema(**{
        "mode": "scan_parse",
        "engine": "orca",
        "log_path": str(log),
    }), mock_session)

    assert result.is_success, result.message
    # 5 帧能量 [-100.500, -100.490, -100.470, -100.480, -100.495] Eh，内部峰在帧 2
    assert result.ts_candidate_index == 2
    assert result.barrier_kcal == pytest.approx(0.030 * KCAL_PER_HARTREE, abs=1e-3)
    guess_lines = Path(result.ts_candidate_path).read_text(encoding="utf-8").splitlines()
    assert "frame=2" in guess_lines[1]
    # 帧 2 的最后一块（每帧 2 块，块索引 5）：C(2.1, 0, 0) / H(3.19, 0, 0) / N(0, 3.5, 0.1)
    rows = [[float(v) for v in line.split()[1:]] for line in guess_lines[2:]]
    assert rows[0] == pytest.approx([2.1, 0.0, 0.0], abs=1e-6)
    assert rows[1] == pytest.approx([3.19, 0.0, 0.0], abs=1e-6)
    assert rows[2] == pytest.approx([0.0, 3.5, 0.1], abs=1e-6)


@pytest.mark.asyncio
async def test_scan_parse_orca_sidecar_stem_derived_from_log_name(tmp_path, mock_session):
    """harness 真实布局：日志在 .cloudra/calc-99.out.log（stem 与作业名不符），
    sidecar 在工作目录；应从日志里的 NAME = <作业>.inp 记录推导真实 stem。"""
    import shutil

    workdir = tmp_path / "work"
    logdir = workdir / ".cloudra"
    logdir.mkdir(parents=True)
    log = logdir / "calc-99.out.log"
    log.write_text(
        f"NAME = {workdir / 'ts2_scan.inp'}\n\n"
        "FINAL SINGLE POINT ENERGY (From external program)      -383.038699298900\n",
        encoding="utf-8",
    )
    shutil.copy(_ORCA_SCAN_FIXTURE / "ts_scan.relaxscanact.dat", workdir / "ts2_scan.relaxscanact.dat")
    for p in sorted(_ORCA_SCAN_FIXTURE.glob("ts_scan.[0-9][0-9][0-9].xyz")):
        shutil.copy(p, workdir / p.name.replace("ts_scan", "ts2_scan", 1))

    # 第 10 帧改为全场最高 → 内部峰，验证确实走了 sidecar 路径
    dat = workdir / "ts2_scan.relaxscanact.dat"
    lines = dat.read_text(encoding="utf-8").splitlines()
    fields = lines[9].split()
    fields[1] = "300.0"
    lines[9] = "  ".join(fields)
    dat.write_text("\n".join(lines) + "\n", encoding="utf-8")

    tool = _make_tool()
    result = await tool.safe_call(TsGuess_input_schema(**{
        "mode": "scan_parse",
        "engine": "orca",
        "log_path": str(log),
    }), mock_session)

    assert result.is_success, result.message
    assert result.ts_candidate_index == 9
    assert any("sidecar" in v for v in result.verdicts)


@pytest.mark.asyncio
async def test_scan_parse_orca_sidecar_unique_glob_fallback(tmp_path, mock_session):
    """日志无 NAME 记录且 stem 不匹配：日志目录/工作目录只有唯一 sidecar 时可定位。"""
    import shutil

    workdir = tmp_path / "work"
    logdir = workdir / ".cloudra"
    logdir.mkdir(parents=True)
    log = logdir / "calc-99.out.log"
    log.write_text("FINAL SINGLE POINT ENERGY (From external program)      -383.038699298900\n", encoding="utf-8")
    shutil.copy(_ORCA_SCAN_FIXTURE / "ts_scan.relaxscanact.dat", workdir / "ts2_scan.relaxscanact.dat")
    for p in sorted(_ORCA_SCAN_FIXTURE.glob("ts_scan.[0-9][0-9][0-9].xyz")):
        shutil.copy(p, workdir / p.name.replace("ts_scan", "ts2_scan", 1))

    dat = workdir / "ts2_scan.relaxscanact.dat"
    lines = dat.read_text(encoding="utf-8").splitlines()
    fields = lines[9].split()
    fields[1] = "300.0"
    lines[9] = "  ".join(fields)
    dat.write_text("\n".join(lines) + "\n", encoding="utf-8")

    tool = _make_tool()
    result = await tool.safe_call(TsGuess_input_schema(**{
        "mode": "scan_parse",
        "engine": "orca",
        "log_path": str(log),
    }), mock_session)

    assert result.is_success, result.message
    assert result.ts_candidate_index == 9
    assert any("sidecar" in v for v in result.verdicts)


@pytest.mark.asyncio
async def test_scan_parse_orca_sidecar_ambiguous_glob_refuses_to_guess(tmp_path, mock_session):
    """同目录出现多个 *.relaxscanact.dat 时拒绝猜测，回退 .out 文本解析。"""
    import shutil

    workdir = tmp_path / "work"
    logdir = workdir / ".cloudra"
    logdir.mkdir(parents=True)
    log = logdir / "calc-99.out.log"
    shutil.copy(_EXTOPT_SCAN_FIXTURE / "scan_extopt_grouped.out", log)
    # 抹掉 NAME 行，迫使走 glob；两个 sidecar → 不得猜测
    log.write_text(log.read_text(encoding="utf-8").replace("NAME = /work/ts2_scan.inp\n", ""), encoding="utf-8")
    for stem in ("job_a", "job_b"):
        shutil.copy(_ORCA_SCAN_FIXTURE / "ts_scan.relaxscanact.dat", workdir / f"{stem}.relaxscanact.dat")

    tool = _make_tool()
    result = await tool.safe_call(TsGuess_input_schema(**{
        "mode": "scan_parse",
        "engine": "orca",
        "log_path": str(log),
    }), mock_session)

    assert result.is_success, result.message
    assert result.ts_candidate_index == 2  # 文本路径按能量最高帧选帧
    assert not any("sidecar used" in v for v in result.verdicts)


# ---------------------------------------------------------------------------
# Task 3 回归：candidate 结构、缺帧不顶替、scan_start 守卫、ORCA IRC 端点
# ---------------------------------------------------------------------------


def _copy_scan_fixture_with_peak(tmp_path, peak_lineno=9, peak_energy="300.0"):
    """复制 cope_relaxed_scan sidecar，把第 peak_lineno（0-based）行能量调到全场最高。"""
    import shutil

    shutil.copy(_ORCA_SCAN_FIXTURE / "ts_scan.relaxscanact.dat", tmp_path / "ts_scan.relaxscanact.dat")
    for p in sorted(_ORCA_SCAN_FIXTURE.glob("ts_scan.[0-9][0-9][0-9].xyz")):
        shutil.copy(p, tmp_path / p.name)
    dat = tmp_path / "ts_scan.relaxscanact.dat"
    lines = dat.read_text(encoding="utf-8").splitlines()
    fields = lines[peak_lineno].split()
    fields[1] = peak_energy
    lines[peak_lineno] = "  ".join(fields)
    dat.write_text("\n".join(lines) + "\n", encoding="utf-8")


@pytest.mark.asyncio
async def test_scan_parse_candidate_carries_provenance_fields(tmp_path, mock_session):
    """内部峰存在时 candidate 必须同时带 scan_index/energy/geometry_ref/source。"""
    _copy_scan_fixture_with_peak(tmp_path)

    tool = _make_tool()
    result = await tool.safe_call(TsGuess_input_schema(**{
        "mode": "scan_parse",
        "engine": "orca",
        "log_path": str(tmp_path / "ts_scan.out"),
    }), mock_session)

    assert result.is_success, result.message
    assert result.candidate_unavailable is False
    candidate = result.candidate
    assert candidate is not None
    assert candidate["scan_index"] == 9
    assert candidate["energy"] == pytest.approx(300.0)
    assert candidate["geometry_ref"] == result.ts_candidate_path
    assert Path(candidate["geometry_ref"]).exists()
    assert candidate["source"] == "orca_relaxed_scan_sidecar"


@pytest.mark.asyncio
async def test_scan_parse_missing_peak_frame_never_substitutes_last_frame(tmp_path, mock_session):
    """峰值帧 sidecar 丢失：candidate=null + candidate_unavailable，严禁用末帧顶替。"""
    _copy_scan_fixture_with_peak(tmp_path)
    (tmp_path / "ts_scan.010.xyz").unlink()  # 峰值帧（1-based 10）丢失

    tool = _make_tool()
    result = await tool.safe_call(TsGuess_input_schema(**{
        "mode": "scan_parse",
        "engine": "orca",
        "log_path": str(tmp_path / "ts_scan.out"),
    }), mock_session)

    assert result.is_success, result.message  # 剖面仍可读，但候选不可得
    assert result.candidate is None
    assert result.candidate_unavailable is True
    assert not result.ts_candidate_path
    assert "NOT" in result.message or "not replaced" in result.message
    # 不得有任何用其它帧写出的 TS-guess 几何
    assert not list(tmp_path.glob("*_ts_guess.xyz"))


@pytest.mark.asyncio
async def test_scan_prepare_gaussian_scan_start_mismatch_rejected(tmp_path, mock_session):
    """Gaussian：scan_start 与当前几何值不同 → start_geometry_mismatch，
    而不是静默只调增量扫错区间。"""
    tool = _make_tool()
    out = tmp_path / "scan.gjf"
    result = await tool.safe_call(TsGuess_input_schema(**{
        "mode": "scan_prepare",
        "input_text": _WATER_XYZ,
        "engine": "gaussian",
        "scans": [{
            "coord_type": "bond",
            "atoms": [1, 2],
            "scan_start": 1.5,  # 当前 O-H ≈ 0.9589 Å，差距远超容差
            "scan_end": 2.0,
            "scan_steps": 10,
        }],
        "output_path": str(out),
    }), mock_session)

    assert not result.is_success
    assert "start_geometry_mismatch" in result.message
    assert not out.exists()


@pytest.mark.asyncio
async def test_scan_prepare_gaussian_scan_start_matching_current_accepted(tmp_path, mock_session):
    """scan_start 与当前几何值一致（容差内）时不误伤。"""
    import math as _math

    tool = _make_tool()
    out = tmp_path / "scan.gjf"
    current = _math.dist((0.0, 0.0, 0.1173), (0.0, 0.7572, -0.4692))
    result = await tool.safe_call(TsGuess_input_schema(**{
        "mode": "scan_prepare",
        "input_text": _WATER_XYZ,
        "engine": "gaussian",
        "scans": [{
            "coord_type": "bond",
            "atoms": [1, 2],
            "scan_start": current,
            "scan_end": 2.0,
            "scan_steps": 10,
        }],
        "output_path": str(out),
    }), mock_session)

    assert result.is_success, result.message
    assert out.exists()


def _orca_irc_log_with_sidecars(tmp_path, backward_converged):
    """合成 ORCA IRC 日志 + F/B final endpoint 边文件，返回日志路径。"""
    log = tmp_path / "calc-1.out.log"
    backward_marker = "THE IRC HAS CONVERGED\n" if backward_converged else ""
    log.write_text(
        f"NAME = {tmp_path / 'ircjob'}.inp\n"
        "* FORWARD IRC *\n"
        " 0 -100.123694 -0.987880 0.009347 0.001949\n"
        "THE IRC HAS CONVERGED\n"
        "* BACKWARD IRC *\n"
        " 0 -100.123694 -0.987880 0.009347 0.001949\n"
        f"{backward_marker}",
        encoding="utf-8",
    )
    xyz = "3\nend\nC 0.0 0.0 0.0\nN 0.0 0.0 1.2\nH 0.0 0.0 2.2\n"
    (tmp_path / "ircjob_IRC_F.xyz").write_text(xyz, encoding="utf-8")
    (tmp_path / "ircjob_IRC_B.xyz").write_text(xyz, encoding="utf-8")
    return log


def test_orca_irc_endpoints_unconverged_side_keeps_gap_in_strict(tmp_path):
    """strict：一侧已终止但未收敛 → 保持缺口（返回 None），不把未验证端点当路径证据。"""
    from types import SimpleNamespace

    log = _orca_irc_log_with_sidecars(tmp_path, backward_converged=False)
    user_input = SimpleNamespace(
        irc_log=str(log), output_dir=str(tmp_path / "out"), freq_log=str(log),
    )
    checks: list[str] = []
    result = TsGuess._extract_orca_irc_endpoints(user_input, checks, require_two_sides=True)

    assert result is None
    assert any("backward" in c and "WITHOUT converging" in c for c in checks)
    assert any("gap stays open" in c for c in checks)


def test_orca_irc_endpoints_converged_short_path_needs_no_padding(tmp_path):
    """两侧收敛（即使点数很少）→ 端点可提取，且明确 F/B 不等于 R/P。"""
    from types import SimpleNamespace

    log = _orca_irc_log_with_sidecars(tmp_path, backward_converged=True)
    out_dir = tmp_path / "out"
    user_input = SimpleNamespace(
        irc_log=str(log), output_dir=str(out_dir), freq_log=str(log),
    )
    checks: list[str] = []
    result = TsGuess._extract_orca_irc_endpoints(user_input, checks, require_two_sides=True)

    assert result is not None
    assert Path(result["path_a"]).exists()
    assert Path(result["path_b"]).exists()
    assert result["meta"]["forward_converged"] is True
    assert result["meta"]["backward_converged"] is True
    assert any("NOT reactant/product" in c for c in checks)
    assert any("needs no padding" in c for c in checks)


@pytest.mark.asyncio
async def test_verify_orca_engine_dispatches_native_irc_endpoints(tmp_path, mock_session, monkeypatch):
    """verify(engine=orca) 端到端：走 orca_frames 原生端点提取并落盘两侧几何。"""
    import cloudra.tools.Chemtool.ts_guess as ts_mod

    log = _orca_irc_log_with_sidecars(tmp_path, backward_converged=True)
    freq_log = tmp_path / "ts_freq.out"
    freq_log.write_text("placeholder (freq parsing stubbed)\n", encoding="utf-8")
    monkeypatch.setattr(ts_mod, "_parse_freq_log", lambda path, engine: {
        "vibfreqs": [-512.3, 100.0, 200.0],
        "vibdisps": None,
        "converged": True,
        "symbols": None,
        "positions": None,
    })

    tool = _make_tool()
    result = await tool.safe_call(TsGuess_input_schema(**{
        "mode": "verify",
        "engine": "orca",
        "freq_log": str(freq_log),
        "irc_log": str(log),
        "output_dir": str(tmp_path / "verify"),
    }), mock_session)

    assert result.is_success, result.message
    assert result.n_imag == 1
    assert Path(result.irc_end_a_path).exists()
    assert Path(result.irc_end_b_path).exists()
    assert any("NOT reactant/product" in c for c in result.checks)


# ---------------------------------------------------------------------------
# 工具面审计 G1–G4：ORCA 扫描文本回退按步分组、verify 引擎分派、
# barrier 语义与候选注释一致性（真实日志在 toolfix_verify/orca/）。
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parent.parent
_TOOLFIX_ORCA = _REPO_ROOT / "toolfix_verify" / "orca"
_ORCA_SCAN_REAL = _TOOLFIX_ORCA / "scan_h2o2" / "scan.out"
_ORCA_OPTFREQ_WATER = _TOOLFIX_ORCA / "optfreq_water" / "optfreq.out"
_ORCA_OPTFREQ_ENOLATE = _TOOLFIX_ORCA / "optfreq_enolate" / "optfreq.out"
_HAS_TOOLFIX_LOGS = all(
    p.is_file() for p in (_ORCA_SCAN_REAL, _ORCA_OPTFREQ_WATER, _ORCA_OPTFREQ_ENOLATE)
)
# 与 scan_h2o2/scan.relaxscanact.dat 逐行对账的真实 10 点剖面（Eh）
_REAL_SCAN_STEP_ENERGIES_EH = [
    -151.35505443, -151.35517436, -151.35551226, -151.35588417, -151.35577007,
    -151.35431781, -151.35113608, -151.34712547, -151.34392136, -151.34271998,
]


@pytest.mark.skipif(not _HAS_TOOLFIX_LOGS, reason="toolfix_verify 真实 ORCA 日志缺失")
def test_parse_orca_scan_real_relaxed_log_groups_per_scan_step():
    """G1：真实 ORCA 6.1.1 relaxed scan（10 扫描点）文本回退必须按扫描步分组。

    日志里 'FINAL SINGLE POINT ENERGY' 共 55 条（每步含多个优化周期）；按步取
    收敛后的最后一条能量，才能还原 10 点剖面（与 relaxscanact.dat 一致），而不是
    把每个优化周期的能量当扫描点拼出垃圾剖面。
    """
    import cloudra.tools.Chemtool.ts_guess as ts_mod

    text = _ORCA_SCAN_REAL.read_text(encoding="utf-8", errors="replace")
    steps = ts_mod._parse_orca_scan(text)
    assert len(steps) == 10
    assert [s["energy_hartree"] for s in steps] == pytest.approx(_REAL_SCAN_STEP_ENERGIES_EH, abs=1e-6)
    # 每步几何都是该步收敛结构（H2O2：4 原子）
    assert all(len(s["geom"]) == 4 for s in steps)


@pytest.mark.skipif(not _HAS_TOOLFIX_LOGS, reason="toolfix_verify 真实 ORCA 日志缺失")
@pytest.mark.asyncio
async def test_scan_parse_orca_real_log_no_sidecar_refuses_endpoint_max(tmp_path, mock_session):
    """G1/G4：无 sidecar 时真实日志文本回退产出 10 点剖面；真实极大值在扫描端点
    （180°，末帧）→ 无内部峰 → 不产候选、barrier_kcal=None，注释不得自相矛盾。"""
    import shutil

    shutil.copy(_ORCA_SCAN_REAL, tmp_path / "scan.out")
    tool = _make_tool()
    result = await tool.safe_call(TsGuess_input_schema(**{
        "mode": "scan_parse",
        "engine": "orca",
        "log_path": str(tmp_path / "scan.out"),
    }), mock_session)

    assert result.is_success, result.message
    assert "10 points" in result.message
    assert result.ts_candidate_index is None
    assert result.ts_candidate_path == ""
    assert result.candidate is None
    assert result.barrier_kcal is None  # G4：无内部峰不填 barrier
    assert any("no internal energy peak" in v for v in result.verdicts)
    # G4：拒发候选时不得再声称 "TS-guess geometry is ..."
    assert not any("TS-guess geometry" in v for v in result.verdicts)
    assert not list(tmp_path.glob("*_ts_guess.xyz"))
    # 剖面表恰好 10 个数据行
    data_rows = [ln for ln in result.profile_table.splitlines() if ln.strip() and ln.split()[0].isdigit()]
    assert len(data_rows) == 10


def _write_orca_scan_log_with_variable_cycles(tmp_path: Path) -> Path:
    """合成带 RELAXED SURFACE SCAN STEP 标记、每步优化周期数不等的 ORCA relaxed scan。

    每周期 = 一行几何 + 一条 FINAL SINGLE POINT ENERGY；每步只应取最后（收敛）
    那条能量：剖面帧能量 = [-100.490, -100.470, -100.485] Eh → 内部峰在帧 1，
    TS-guess 几何 = 帧 1 收敛几何（C x=2.1）。
    """
    log = tmp_path / "scan.out"
    text: list[str] = []

    def cart(x: float) -> None:
        text.append("CARTESIAN COORDINATES (ANGSTROEM)")
        text.append("---------------------------------")
        text.append(f"  C      {x:.1f}000000    0.000000    0.000000")
        text.append(f"  H      {x + 1:.1f}000000    0.000000    0.000000")
        text.append("  N      0.000000    1.500000    0.000000")

    text.append("         *               RELAXED SURFACE SCAN STEP   1               *")
    cart(0.0)
    text.append("FINAL SINGLE POINT ENERGY      -100.500000000000")
    cart(0.1)
    text.append("FINAL SINGLE POINT ENERGY      -100.490000000000")
    text.append("         *               RELAXED SURFACE SCAN STEP   2               *")
    cart(1.0)
    text.append("FINAL SINGLE POINT ENERGY      -100.480000000000")
    cart(2.1)
    text.append("FINAL SINGLE POINT ENERGY      -100.470000000000")
    text.append("         *               RELAXED SURFACE SCAN STEP   3               *")
    cart(3.0)
    text.append("FINAL SINGLE POINT ENERGY      -100.485000000000")
    log.write_text("\n".join(text) + "\n", encoding="utf-8")
    return log


@pytest.mark.asyncio
async def test_scan_parse_orca_text_groups_by_step_with_variable_cycles(tmp_path, mock_session):
    """G1：按扫描步分组 + 每步取收敛后最后一条能量——优化周期能量不算扫描点。"""
    log = _write_orca_scan_log_with_variable_cycles(tmp_path)

    tool = _make_tool()
    result = await tool.safe_call(TsGuess_input_schema(**{
        "mode": "scan_parse",
        "engine": "orca",
        "log_path": str(log),
    }), mock_session)

    assert result.is_success, result.message
    assert "3 points" in result.message
    data_rows = [ln for ln in result.profile_table.splitlines() if ln.strip() and ln.split()[0].isdigit()]
    assert len(data_rows) == 3
    assert result.ts_candidate_index == 1
    assert result.barrier_kcal == pytest.approx(0.020 * KCAL_PER_HARTREE, abs=1e-2)
    guess = Path(result.ts_candidate_path)
    assert guess.exists()
    rows = [[float(v) for v in ln.split()[1:]] for ln in guess.read_text(encoding="utf-8").splitlines()[2:]]
    assert rows[0] == pytest.approx([2.1, 0.0, 0.0], abs=1e-6)
    assert rows[1] == pytest.approx([3.1, 0.0, 0.0], abs=1e-6)
    assert rows[2] == pytest.approx([0.0, 1.5, 0.0], abs=1e-6)
    assert any("TS-guess geometry is the energy-maximum frame 1" in v for v in result.verdicts)


@pytest.mark.skipif(not _HAS_TOOLFIX_LOGS, reason="toolfix_verify 真实 ORCA 日志缺失")
def test_parse_freq_log_orca_real_logs_frequencies_and_convergence(tmp_path):
    """G2/G3：cclib 1.8.1 对 ORCA 6.1.1 日志全灭（IndexError）时，频率文本回退走
    orca_frames 原生 VIBRATIONAL FREQUENCIES 块；收敛判定按引擎分派。"""
    import cloudra.tools.Chemtool.ts_guess as ts_mod

    for path, n_modes in ((_ORCA_OPTFREQ_WATER, 9), (_ORCA_OPTFREQ_ENOLATE, 18)):
        parsed = ts_mod._parse_freq_log(str(path), "orca")
        assert parsed["vibfreqs"] is not None
        assert len(parsed["vibfreqs"]) == n_modes
        assert all(f >= 0 for f in parsed["vibfreqs"])  # 极小值：0 虚频
        assert parsed["converged"] is True  # G3：ORCA 标记（非 Gaussian "Normal termination"）


@pytest.mark.skipif(not _HAS_TOOLFIX_LOGS, reason="toolfix_verify 真实 ORCA 日志缺失")
@pytest.mark.asyncio
async def test_verify_orca_real_water_log_reports_minimum(tmp_path, mock_session):
    """G2/G3 端到端：真实 ORCA 6.1.1 OptFreq 水（极小值）verify 必须成功并判为无虚频。"""
    tool = _make_tool()
    result = await tool.safe_call(TsGuess_input_schema(**{
        "mode": "verify",
        "engine": "orca",
        "freq_log": str(_ORCA_OPTFREQ_WATER),
    }), mock_session)

    assert result.is_success, result.message
    assert result.n_imag == 0
    assert "minimum" in result.verdict
    assert not any("did not converge" in c for c in result.checks)


def test_parse_freq_log_orca_convergence_dispatched_by_engine_markers(tmp_path):
    """G3：收敛回退不得用 Gaussian 的 'Normal termination' 判 ORCA 日志——ORCA 自报
    'ORCA TERMINATED NORMALLY'；优化收敛与否另有 'THE OPTIMIZATION HAS CONVERGED' /
    'The optimization did not converge' 标记。"""
    import cloudra.tools.Chemtool.ts_guess as ts_mod

    freq_block = (
        "VIBRATIONAL FREQUENCIES\n"
        "     0:      -350.00 cm**-1\n"
        "     1:      1200.00 cm**-1\n"
    )
    converged_log = tmp_path / "conv.out"
    converged_log.write_text(
        "THE OPTIMIZATION HAS CONVERGED\n" + freq_block + "****ORCA TERMINATED NORMALLY****\n",
        encoding="utf-8",
    )
    parsed = ts_mod._parse_freq_log(str(converged_log), "orca")
    assert parsed["converged"] is True

    # 跑满最大步数未收敛的优化仍可能正常终止——收敛判定必须为 False
    unconv_log = tmp_path / "unconv.out"
    unconv_log.write_text(
        "The optimization did not converge\n" + freq_block + "****ORCA TERMINATED NORMALLY****\n",
        encoding="utf-8",
    )
    parsed = ts_mod._parse_freq_log(str(unconv_log), "orca")
    assert parsed["converged"] is False


@pytest.mark.asyncio
async def test_ts_guess_mode_aliases(tmp_path, mock_session):
    """测试 scan 别名映射至 scan_parse / scan_prepare。

    ``xtb_neb`` 这个别名已按批准删除：它只是映射到 ``interpolate``（不跑 NEB），
    名字具误导性；现在 ``xtb_path`` 是真模式（真跑 xTB MTD 路径搜索），见本文件末尾的
    guess 阶段用例。
    """
    tool = _make_tool()

    # scan 别名带 log_path 映射到 scan_parse
    res_scan = await tool.safe_call(TsGuess_input_schema(**{
        "mode": "scan",
        "log_path": str(SCAN_LOG),
    }), mock_session)
    assert res_scan.is_success, res_scan.message
    assert len(res_scan.verdicts) > 0

    # scan 别名无 log_path 映射到 scan_prepare
    out_gjf = tmp_path / "scan.gjf"
    res_prep = await tool.safe_call(TsGuess_input_schema(**{
        "mode": "scan",
        "input_text": _R_XYZ,
        "scans": [{"coord_type": "bond", "atoms": [1, 2], "scan_end": 2.0, "scan_steps": 5}],
        "output_path": str(out_gjf),
    }), mock_session)
    assert res_prep.is_success, res_prep.message
    assert out_gjf.is_file()


# ---------------------------------------------------------------------------
# guess 阶段（SOP）：默认走 xTB MTD 路径；xTB 缺失才退回 IDPP，且必须显式标注
# ---------------------------------------------------------------------------

_FAKE_XTB_FOR_TS = '''#!{python}
"""假 xtb：复现 6.7.1 的 --path 输出。注意成功标记写在 **stderr**（与真实构建一致）。"""
import os
import sys

mode = os.environ.get("FAKE_XTB_FOR_TS_MODE", "ok")

if "--version" in sys.argv:
    print("   * xtb version 6.7.1 (fake) compiled by test")
    sys.exit(0)

reactant = open("reactant.xyz", encoding="utf-8").read().splitlines()
count = int(reactant[0].strip())
body = reactant[2:2 + count]
tail = " xtb: 6.7.1 (fake)"


def frame(energy):
    return "\\n".join([str(count), " energy: " + energy + tail] + body) + "\\n"


if mode == "fail":
    print("bad things happened")
    sys.exit(3)

print("          | TOTAL ENERGY               -5.070383095219 Eh   |")
open("xtbpath.xyz", "w", encoding="utf-8").write(
    frame("0.000000000000") + frame("52.271000000000") + frame("0.500000000000")
)
open("xtbpath_ts.xyz", "w", encoding="utf-8").write(frame("-4.987083865354"))
print("forward  barrier (kcal)  :    18.299")
if mode == "path_truncated":
    print("terminated because max. # cycles reached")
else:
    print("terminated because grad at TS <threshold")
print("normal termination of xtb", file=sys.stderr)
print(" * finished run on 2026/01/01 at 00:00:00.000")
print(" path finder:")
sys.exit(0)
'''


@pytest.fixture
def fake_xtb_for_ts(tmp_path, monkeypatch):
    """把假 xtb 装进 PATH；返回设置模式的函数。"""
    import os
    import stat
    import sys as _sys

    bindir = tmp_path / "fakebin"
    bindir.mkdir()
    script = bindir / "xtb"
    script.write_text(_FAKE_XTB_FOR_TS.format(python=_sys.executable), encoding="utf-8")
    script.chmod(script.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    monkeypatch.setenv("PATH", f"{bindir}{os.pathsep}{os.environ['PATH']}")

    def set_mode(mode: str) -> None:
        monkeypatch.setenv("FAKE_XTB_FOR_TS_MODE", mode)

    return set_mode


@pytest.mark.asyncio
async def test_guess_defaults_to_xtb_path_and_reports_path_kind(fake_xtb_for_ts, tmp_path, mock_session):
    """默认模式（不给 mode）走 xTB MTD 路径，并写明 path_kind。"""
    fake_xtb_for_ts("ok")
    out_dir = tmp_path / "guess_default"
    res = await _make_tool().safe_call(TsGuess_input_schema(**{
        "reactant_text": _R_XYZ,
        "product_text": _P_XYZ,
        "output_dir": str(out_dir),
    }), mock_session)
    assert res.is_success, res.message
    assert res.path_kind == "xtb_path"
    assert res.refinement_termination == "converged"
    assert res.images_dir == str(out_dir)
    assert res.ts_candidate_path and Path(res.ts_candidate_path).is_file()
    # 路径帧落盘
    frames = sorted(Path(out_dir).glob("img_*.xyz"))
    assert len(frames) == 3
    # 初猜 ≠ 已验证
    assert "not verified" in res.message.lower() or "guess" in res.message.lower()


@pytest.mark.asyncio
async def test_xtb_missing_falls_back_to_idpp_and_says_so(tmp_path, monkeypatch, mock_session):
    """xTB 缺失时退回 IDPP 插值，但**必须显式标注**走了兜底，不许静默降级。"""
    empty = tmp_path / "empty-path"
    empty.mkdir()
    monkeypatch.setenv("PATH", str(empty))
    out_dir = tmp_path / "guess_fallback"
    res = await _make_tool().safe_call(TsGuess_input_schema(**{
        "reactant_text": _R_XYZ,
        "product_text": _P_XYZ,
        "n_images": 4,
        "output_dir": str(out_dir),
    }), mock_session)
    assert res.is_success, res.message
    assert res.path_kind == "idpp_fallback"
    assert "fallback" in res.message.lower() or "idpp" in res.message.lower()
    assert res.ts_candidate_path and Path(res.ts_candidate_path).is_file()


@pytest.mark.asyncio
async def test_truncated_path_refinement_is_reported_with_the_remedy(
    fake_xtb_for_ts, tmp_path, mock_session
):
    """触到精修轮数上限 = 路径被截断：不许当可用初猜交出去，并**点名补救办法**。

    实测（docs/evidence/ts_guess_mtd_artifact/）：内建默认 3 轮的路径最高帧落在反应物自己的
    盆地里（离起点 21°），拿去做 ORCA OptTS 跑 56 轮都不收敛；把上限放开后引擎自己判收敛，
    同一帧 9 轮即收敛到一阶鞍点。所以这里必须报出来，并叫调用方把 refinement_runs 调大。
    """
    fake_xtb_for_ts("path_truncated")
    out_dir = tmp_path / "guess_truncated"
    res = await _make_tool().safe_call(TsGuess_input_schema(**{
        "reactant_text": _R_XYZ,
        "product_text": _P_XYZ,
        "output_dir": str(out_dir),
    }), mock_session)
    assert not res.is_success
    assert res.refinement_termination == "cycles_exhausted"
    assert res.path_kind == ""
    assert "refinement_runs" in res.message
    assert "truncated" in res.message.lower()


@pytest.mark.asyncio
async def test_xtb_failure_is_reported_not_silently_replaced(fake_xtb_for_ts, tmp_path, mock_session):
    """xTB 存在但跑失败：报出分类，**不得**偷偷换成 IDPP 插值充数。"""
    fake_xtb_for_ts("fail")
    res = await _make_tool().safe_call(TsGuess_input_schema(**{
        "reactant_text": _R_XYZ,
        "product_text": _P_XYZ,
        "output_dir": str(tmp_path / "guess_fail"),
    }), mock_session)
    assert res.is_success is False
    assert res.path_kind == ""
    assert "xtb" in res.message.lower()
    assert "bad things happened" in res.message or "failed" in res.message.lower()


def test_legacy_xtb_neb_alias_is_gone():
    """误导性的 xtb_neb 别名已删除（它只是映射到 interpolate，不跑 NEB）。"""
    import pytest as _pytest

    with _pytest.raises(Exception):
        TsGuess_input_schema(**{
            "mode": "xtb_neb",
            "reactant_text": _R_XYZ,
            "product_text": _P_XYZ,
        })


@pytest.mark.asyncio
async def test_blocking_handler_does_not_freeze_event_loop(monkeypatch, mock_session):
    """xtb_path 等 handler 会同步等 xTB 子进程（proc.communicate(timeout=900)），
    tool_call 必须把 handler 分发卸载出事件循环（image_to_smiles 同款事故的审计同类）。
    用 time.sleep(0.4) 的假 handler + 并发 ticker 探活：ticker 停滞即事件循环被冻结。"""
    import asyncio
    import time

    from cloudra.tools.Chemtool.ts_guess import TsGuess_output_schema

    def fake_handler(self, user_input):
        time.sleep(0.4)
        return TsGuess_output_schema(is_success=True, message="ok")

    monkeypatch.setattr(TsGuess, "_xtb_path", fake_handler)

    ticks = 0
    stop = False

    async def ticker():
        nonlocal ticks
        while not stop:
            ticks += 1
            await asyncio.sleep(0.02)

    ticker_task = asyncio.create_task(ticker())
    try:
        result = await _make_tool().tool_call(TsGuess_input_schema(), mock_session)
    finally:
        stop = True
        await ticker_task
    assert result.is_success is True
    # 若阻塞发生在事件循环线程上，0.4s 的冻结期里 ticker 只会前进寥寥几步
    assert ticks > 5, f"event loop was frozen during tool_call (ticks={ticks})"
