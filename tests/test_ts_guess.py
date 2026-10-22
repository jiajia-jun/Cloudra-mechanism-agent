"""ts_guess 工具测试（cloudra/tools/Chemtool/ts_guess.py）。

全部离线，不执行任何量化程序。fixture 为仓库已有的真实 Gaussian 输出：
- h2_scan_g09.log：G09 relaxed PES scan（opt=ModRedundant），101 点 H-H 键长扫描（0.60→1.60 Å）
- hcn_ts_irc_g16.log：G16 IRC，正/反向各 10 点 + TS
- water_opt_freq_g16.out：G16 opt+freq，极小点（无虚频）
"""

import math
from pathlib import Path

import pytest
from pydantic import ValidationError

pytest.importorskip("numpy")
pytest.importorskip("ase")
pytest.importorskip("cclib")

import ase.io
import numpy as np

from cloudra.tools.Chemtool.ts_guess import (
    KCAL_PER_HARTREE,
    TsGuess,
    TsGuess_input_schema,
    _idpp_relax,
    analyze_scan_profile,
)
from cloudra.tools.core.irc_path import (
    assign_irc_endpoints as _assign_irc_endpoints,
)
from cloudra.tools.core.irc_path import (
    evaluate_endpoint_between as _evaluate_endpoint_between,
)

FIXTURES = Path(__file__).parent / "fixtures" / "gaussian"
SCAN_LOG = FIXTURES / "h2_scan_g09.log"
IRC_LOG = FIXTURES / "hcn_ts_irc_g16.log"
OPT_FREQ_LOG = FIXTURES / "water_opt_freq_g16.out"


def _make_tool() -> TsGuess:
    return TsGuess()


@pytest.mark.parametrize('unused', ['freq_log', 'strict', 'reactant_logs', 'product_logs', 'n_images', 'spin', 'nprocs', 'memory_mb', 'job_name'])
def test_scan_schema_refuses_other_operation_fields(unused):
    arguments = dict(mode='scan_prepare', engine='orca', method='B3LYP', basis_set='def2SVP',
        input_text='2\nH2\nH 0 0 0\nH 0 0 .74\n',
        scans=[{'atoms': [0, 1], 'scan_end': 1.2, 'scan_steps': 5}], output_path='scan.inp')
    arguments[unused] = {
        'freq_log': 'freq.log', 'strict': True, 'n_images': 1000,
        'reactant_logs': ['reactant.log'], 'product_logs': ['product.log'],
        'spin': 1, 'nprocs': 8, 'memory_mb': 8192, 'job_name': 'old-scan',
    }[unused]
    with pytest.raises(ValidationError, match=unused):
        TsGuess_input_schema(**arguments)


def test_parse_schema_refuses_calculation_method_that_would_be_ignored():
    with pytest.raises(ValidationError, match='method'):
        TsGuess_input_schema(mode='scan_parse', log_path='scan.log', method='PBE0')


@pytest.mark.parametrize('surface', ['wire', 'model'])
@pytest.mark.parametrize('arguments', [
    dict(mode='scan_prepare', engine='orca', method='B3LYP', basis_set='def2-SVP',
         input_text='input XYZ', scans=[{'atoms': [0, 1], 'scan_end': 2, 'scan_steps': 5}],
         output_path='scan.inp', freq_log='freq.log'),
    dict(mode='scan_parse', log_path='scan.log', method='PBE0'),
])
def test_wire_schema_refuses_parameters_from_a_different_operation(surface, arguments):
    jsonschema = pytest.importorskip('jsonschema')
    schema = TsGuess_input_schema.to_parameters_schema() if surface == 'wire' else TsGuess_input_schema.model_json_schema()
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.Draft202012Validator(schema).validate(arguments)


@pytest.mark.parametrize('missing', ['engine', 'basis_set'])
def test_scan_schema_requires_explicit_calculation_fields(missing):
    arguments = dict(mode='scan_prepare', engine='orca', method='B3LYP', basis_set='def2-SVP',
        input_text='2\nH2\nH 0 0 0\nH 0 0 .74\n',
        scans=[{'atoms': [0, 1], 'scan_end': 1.2, 'scan_steps': 5}], output_path='scan.inp')
    arguments.pop(missing)
    with pytest.raises(ValidationError, match=missing):
        TsGuess_input_schema(**arguments)


@pytest.mark.usefixtures("rdkit_chemistry")
def test_scan_preparation_reports_written_method_without_reselection_hint(tmp_path):
    keywords = 'D3BJ RIJCOSX def2/J TightSCF CPCM(DCM)'
    target = tmp_path / 'scan.inp'
    request = TsGuess_input_schema(charge=0, mode='scan_prepare', engine='orca', method='B3LYP',
        basis_set='def2SVP', keywords=keywords, input_text='2\nH2\nH 0 0 0\nH 0 0 .74\n',
        scans=[{'atoms': [0, 1], 'scan_end': 1.2, 'scan_steps': 5}], output_path=str(target))
    result = TsGuess()._scan_prepare(request)
    assert result.is_success
    assert target.read_text().splitlines()[0] == '! B3LYP def2-SVP ' + keywords
    assert result.calculation.method == 'B3LYP' and result.calculation.keywords == keywords
    assert 'PM7' not in result.run_hint and 'GFN2' not in result.run_hint
    assert 'submit_compute_job' in result.run_hint and 'B3LYP' in result.message


@pytest.mark.usefixtures("rdkit_chemistry")
def test_scan_and_writer_preserve_native_method_slash_and_auxiliary_basis(tmp_path):
    from cloudra.tools.Chemtool.qm_input_writer import QmInputWriter, QmInputWriter_input_schema
    from cloudra.tools.core.molecule import read_molecule

    settings = dict(engine='orca', method='B3LYP/G', basis_set='def2-SVP',
                    keywords='D3BJ RIJCOSX def2/J TightSCF CPCM(DCM)')
    written = QmInputWriter._build_orca_input(QmInputWriter_input_schema(**settings,
        task_type=[], source_type='xyz_file', source_value='unused.xyz', output_path='unused.inp'),
        read_molecule(input_text='2\n\nH 0 0 0\nH 0 0 .74\n'))
    target = tmp_path / 'scan.inp'
    result = TsGuess()._scan_prepare(TsGuess_input_schema(charge=0, **settings, mode='scan_prepare',
        input_text='2\nH2\nH 0 0 0\nH 0 0 .74\n', output_path=str(target),
        scans=[{'atoms': [0, 1], 'scan_end': 1.2, 'scan_steps': 5}]))
    assert result.is_success
    assert written.splitlines()[0] == target.read_text().splitlines()[0]
    assert result.calculation.method == 'B3LYP/G'


def test_guess_requires_explicit_mode_before_accepting_endpoints(tmp_path):
    with pytest.raises(ValidationError, match="mode"):
        TsGuess_input_schema(
            reactant_path="reactant.xyz", product_path="product.xyz",
            output_dir=str(tmp_path / "guess"),
        )
    assert not (tmp_path / "guess").exists()


@pytest.mark.parametrize("arguments,missing", [
    ({"mode": "interpolate", "product_path": "product.xyz"}, "reactant"),
    ({"mode": "xtb_path", "reactant_path": "reactant.xyz"}, "product"),
    ({"mode": "scan_prepare", "method": "HF", "scans": [{"atoms": [1, 2], "scan_end": 2, "scan_steps": 1}], "output_path": "scan.gjf"}, "input"),
    ({"mode": "scan_prepare", "input_path": "input.xyz", "scans": [{"atoms": [1, 2], "scan_end": 2, "scan_steps": 1}], "output_path": "scan.gjf"}, "method"),
    ({"mode": "scan_prepare", "engine": "gaussian", "method": "HF", "basis_set": "", "input_path": "input.xyz", "output_path": "scan.gjf"}, "scans"),
    ({"mode": "scan_prepare", "engine": "gaussian", "method": "HF", "basis_set": "", "input_path": "input.xyz", "scans": [{"atoms": [1, 2], "scan_end": 2, "scan_steps": 1}]}, "output_path"),
    ({"mode": "scan_parse"}, "log_path"),
    ({"mode": "verify"}, "freq_log"),
    ({"mode": "scan", "engine": "gaussian", "method": "HF", "basis_set": "", "input_path": "input.xyz", "output_path": "scan.gjf"}, "scans"),
])
def test_guess_rejects_missing_mode_inputs_at_schema_boundary(arguments, missing):
    with pytest.raises(ValidationError, match=missing):
        TsGuess_input_schema(**arguments)


@pytest.mark.parametrize("surface", ["wire", "model"])
@pytest.mark.parametrize("arguments", [
    {"mode": "interpolate", "product_path": "product.xyz"},
    {"mode": "xtb_path", "reactant_path": "reactant.xyz"},
    {"mode": "scan_prepare", "input_path": "input.xyz", "output_path": "scan.gjf"},
    {"mode": "scan_parse"},
    {"mode": "verify"},
    {"mode": "scan", "log_path": None},
    {"mode": "scan", "log_path": ""},
])
def test_model_schema_rejects_incomplete_mode_requests(surface, arguments):
    jsonschema = pytest.importorskip("jsonschema")
    schema = (TsGuess_input_schema.to_parameters_schema() if surface == "wire"
              else TsGuess_input_schema.model_json_schema())
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.Draft202012Validator(schema).validate(arguments)


@pytest.mark.parametrize("surface", ["wire", "model"])
@pytest.mark.parametrize("arguments", [
    {"mode": "interpolate", "reactant_path": "r.xyz", "product_text": "product XYZ"},
    {"mode": "xtb_path", "reactant_text": "reactant XYZ", "product_path": "p.xyz"},
    {"mode": "scan_parse", "log_path": "scan.log"},
    {"mode": "verify", "freq_log": "frequency.out"},
    {"mode": "scan", "log_path": "scan.log"},
    *[dict(mode=mode, engine="gaussian", method="HF", basis_set="", input_text="input XYZ", output_path="scan.gjf",
           scans=[{"atoms": [1, 2], "scan_end": 2, "scan_steps": 1}], **extra)
      for mode, extra in [("scan_prepare", {}), ("scan", {}), ("scan", {"log_path": None}),
                          ("scan", {"log_path": ""})]],
])
def test_model_schema_accepts_complete_mode_requests(surface, arguments):
    jsonschema = pytest.importorskip("jsonschema")
    schema = (TsGuess_input_schema.to_parameters_schema() if surface == "wire"
              else TsGuess_input_schema.model_json_schema())
    jsonschema.Draft202012Validator.check_schema(schema)
    jsonschema.Draft202012Validator(schema).validate(arguments)


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
    out, _ = _idpp_relax(images, mode="light", max_iter=8)
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



def _path_mol(xyz_text: str) -> str:
    """Explicit mapped graph for the geometric path fixtures."""
    Chem = pytest.importorskip("rdkit.Chem")
    mol = Chem.MolFromSmiles("[H:1][O:2][F:3]", sanitize=False)
    Chem.SanitizeMol(mol)
    atoms = ase.io.read(__import__("io").StringIO(xyz_text), format="xyz")
    conf = Chem.Conformer(3)
    for index, position in enumerate(atoms.get_positions()):
        conf.SetAtomPosition(index, position)
    mol.AddConformer(conf)
    return Chem.MolToMolBlock(mol)


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
        "reactant_text": _path_mol(_R_XYZ),
        "product_text": _path_mol(_P_XYZ),
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
        "reactant_text": _path_mol(_R_XYZ),
        "product_text": _path_mol(_P_XYZ),
        "n_images": 6,
        "interp_method": "linear",
        "output_dir": str(tmp_path / "a"),
    }), mock_session)
    moved = await tool.safe_call(TsGuess_input_schema(**{
        "mode": "interpolate",
        "reactant_text": _path_mol(_R_XYZ),
        "product_text": _path_mol(_rotated_translated(_P_XYZ)),
        "n_images": 6,
        "interp_method": "linear",
        "output_dir": str(tmp_path / "b"),
    }), mock_session)

    assert base.is_success and moved.is_success
    assert base.distance_table == moved.distance_table
    assert base.ts_candidate_index == moved.ts_candidate_index


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
async def test_scan_prepare_accepts_declared_mol_geometry(tmp_path, mock_session):
    """The input boundary reads MOL directly instead of requesting a lossy XYZ conversion."""
    pytest.importorskip("rdkit", reason="requires RDKit (chem extra)")
    from rdkit import Chem
    from rdkit.Chem import AllChem

    mol = Chem.AddHs(Chem.MolFromSmiles("O"))
    assert AllChem.EmbedMolecule(mol, randomSeed=1) == 0
    source = tmp_path / "water.mol"
    source.write_text(Chem.MolToMolBlock(mol), encoding="utf-8")
    output = tmp_path / "scan.inp"

    result = await _make_tool().safe_call(TsGuess_input_schema(basis_set='def2svp',
        mode="scan_prepare",
        method='b3lyp',
        input_path=str(source),
        engine="orca",
        scans=[{"coord_type": "bond", "atoms": [1, 2], "scan_end": 2.0, "scan_steps": 8}],
        output_path=str(output),
    ), mock_session)

    assert result.is_success, result.message
    assert output.is_file()
    assert "* xyz 0 1" in output.read_text()


@pytest.mark.asyncio
@pytest.mark.usefixtures("rdkit_chemistry")
async def test_scan_prepare_gaussian(tmp_path, mock_session):
    """Gaussian gjf：modredundant 扫描块、路由、电荷自旋、步长符号正确，无 QST。"""
    tool = _make_tool()
    out = tmp_path / "scan.gjf"
    result = await tool.safe_call(TsGuess_input_schema(charge=0, **{'basis_set': 'def2svp',
        "mode": "scan_prepare",
        "method": 'b3lyp',
        "input_text": _WATER_XYZ,
        "engine": "gaussian",
        "scans": [{
            "coord_type": "bond",
            "atoms": [1, 2],
            "scan_end": 2.0,
            "scan_steps": 10,
        }],
        "output_path": str(out),
    }), mock_session)

    assert result.is_success, result.message
    assert result.input_file_path == str(out)
    assert "submit_compute_job" in result.run_hint and "gaussian" in result.run_hint
    assert result.calculation.method == 'b3lyp' and result.calculation.basis_set == 'def2svp'
    assert 'PM7' not in result.run_hint and 'GFN2-xTB' not in result.run_hint
    content = out.read_text()
    assert "qst" not in content.lower()
    assert f"%chk={out.with_suffix('.chk')}\n" in content
    assert "opt=modredundant" in content
    assert "b3lyp/def2svp" in content
    assert "\n0 1\n" in content
    # 当前 O-H 键长 ≈ 0.9589 Å，步长 = (2.0 - 0.9589)/10 ≈ +0.104
    m = __import__("re").search(r"^B 1 2 S 10 ([-\d.]+)$", content, __import__("re").M)
    assert m, content
    start = math.dist((0.0, 0.0, 0.1173), (0.0, 0.7572, -0.4692))
    assert float(m.group(1)) == pytest.approx((2.0 - start) / 10, abs=1e-5)


@pytest.mark.asyncio
@pytest.mark.usefixtures("rdkit_chemistry")
async def test_scan_prepare_gaussian_two_grid_coordinates(tmp_path, mock_session):
    """Gaussian 双坐标耦合扫描：两个 S 行（2D 网格），各自步长独立。"""
    tool = _make_tool()
    out = tmp_path / "scan2d.gjf"
    result = await tool.safe_call(TsGuess_input_schema(charge=0, **{'basis_set': 'def2svp',
        "mode": "scan_prepare",
        "method": 'b3lyp',
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
    assert "2D" in result.run_hint and "grid" in result.run_hint


@pytest.mark.asyncio
@pytest.mark.usefixtures("rdkit_chemistry")
async def test_scan_prepare_orca(tmp_path, mock_session):
    """ORCA inp：%geom Scan 块、原子序号 0-based、%pal，无 QST。"""
    tool = _make_tool()
    out = tmp_path / "scan.inp"
    result = await tool.safe_call(TsGuess_input_schema(charge=0, **{'basis_set': 'def2svp',
        "mode": "scan_prepare",
        "method": 'b3lyp',
        "input_text": _WATER_XYZ,
        "engine": "orca",
        "scans": [{
            "coord_type": "angle",
            "atoms": [1, 0, 2],
            "scan_start": 90.0,
            "scan_end": 120.0,
            "scan_steps": 6,
        }],
        "nproc": 8,
        "output_path": str(out),
    }), mock_session)

    assert result.is_success, result.message
    assert "orca" in result.run_hint
    content = out.read_text()
    assert "qst" not in content.lower()
    assert "%pal nprocs 8 end" in content
    assert "%geom" in content
    # 原子序号 0-based：输入 [2,1,3] → 输出 1 0 2
    assert "Scan\n        A 1 0 2 = 90.000000, 120.000000, 6\n    end" in content
    # 组合条目拼写 b3lyp/def2svp 必须落成 ORCA 原生基组拼写 def2-SVP
    assert content.startswith("! Opt b3lyp def2-SVP")
    assert "* xyz 0 1" in content


@pytest.mark.asyncio
@pytest.mark.usefixtures("rdkit_chemistry")
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
    result = await tool.safe_call(TsGuess_input_schema(charge=0, **{'basis_set': '',
        "mode": "scan_prepare",
        "input_text": _WATER_XYZ,
        "engine": "orca",
        "method": "ExtOpt",
        "scans": [{"coord_type": "bond", "atoms": [0, 1], "scan_end": 2.0, "scan_steps": 10}],
        "orca_blocks": prog_block,
        "output_path": str(out),
    }), mock_session)

    assert result.is_success, result.message
    content = out.read_text()
    assert content.startswith("! ExtOpt\n")
    assert "Scan\n        B 0 1 = " in content
    assert "ProgExt" in content and "--model" in content
    # %method 块位于坐标块之前
    assert content.index("%method") < content.index("* xyz")


@pytest.mark.asyncio
async def test_scan_prepare_rejects_independent_multi_coord_on_orca(tmp_path, mock_session):
    """ORCA双坐标需要显式grid或concerted意图；省略不得偷偷转换。"""
    tool = _make_tool()
    result = await tool.safe_call(TsGuess_input_schema(charge=0, **{'basis_set': 'def2svp',
        "mode": "scan_prepare",
        "method": 'b3lyp',
        "input_text": _WATER_XYZ,
        "engine": "orca",
        "scans": [
            {"coord_type": "bond", "atoms": [0, 1], "scan_end": 2.0, "scan_steps": 10},
            {"coord_type": "bond", "atoms": [0, 2], "scan_end": 1.2, "scan_steps": 10},
        ],
        "output_path": str(tmp_path / "x.inp"),
    }), mock_session)
    assert not result.is_success
    assert "concerted" in result.message


@pytest.mark.asyncio
async def test_scan_prepare_atoms_validation(tmp_path, mock_session):
    """原子个数/序号校验：dihedral 需要 4 个原子。"""
    with pytest.raises(ValueError, match="4 distinct"):
        TsGuess_input_schema(charge=0, **{'engine': 'gaussian', 'basis_set': 'def2svp',
        "mode": "scan_prepare",
        "method": 'b3lyp',
        "input_text": _WATER_XYZ,
        "scans": [{
            "coord_type": "dihedral",
            "atoms": [1, 2, 3],
            "scan_end": 180.0,
            "scan_steps": 5,
        }],
        "output_path": str(tmp_path / "x.gjf"),
        })


@pytest.mark.asyncio
@pytest.mark.parametrize("mode,method", [
    ("scan_prepare", None), ("scan_prepare", ""),
    ("scan_prepare", "  "), ("scan", None),
])
async def test_scan_prepare_requires_explicit_method(tmp_path, mock_session, mode, method):
    out = tmp_path / "scan.gjf"
    args = {
        "mode": mode,
        "input_text": _WATER_XYZ,
        "scans": [{"coord_type": "bond", "atoms": [1, 2], "scan_end": 2.0,
                   "scan_steps": 5}],
        "output_path": str(out),
    }
    if method is not None:
        args["method"] = method
    with pytest.raises(ValidationError, match="explicit method"):
        TsGuess_input_schema(**args)
    assert not out.exists()


@pytest.mark.asyncio
async def test_scan_prepare_explicit_null_method_rejected(tmp_path, mock_session):
    with pytest.raises(ValidationError, match="explicit method"):
        TsGuess_input_schema(charge=0, **{'engine': 'gaussian', 'basis_set': '',
            "mode": "scan_prepare", "method": None, "input_text": _WATER_XYZ,
            "scans": [{"atoms": [1, 2], "scan_end": 2.0, "scan_steps": 5}],
            "output_path": str(tmp_path / "scan.gjf"),
        })


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
    assert result.scan_has_internal_peak is False


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
    assert result.scan_has_internal_peak is False
    assert "NOT a TS candidate" in result.message
    # profile 表不标 TS guess
    assert "TS guess" not in result.profile_table


@pytest.mark.asyncio
async def test_scan_parse_missing_energy_profile_has_unknown_peak_status(tmp_path, mock_session):
    log = tmp_path / "unparseable_scan.log"
    log.write_text("The scan did not produce a potential surface summary.\n")
    result = await _make_tool().safe_call(TsGuess_input_schema(**{
        "mode": "scan_parse", "engine": "gaussian", "log_path": str(log),
    }), mock_session)
    assert not result.is_success
    assert result.scan_has_internal_peak is None


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


def _gaussian_orientation(xyz):
    rows = xyz.strip().splitlines()[2:]
    atomic_numbers = {"C": 6, "N": 7, "H": 1}
    coordinates = []
    for index, row in enumerate(rows, 1):
        symbol, x, y, z = row.split()
        coordinates.append(f"{index:7d} {atomic_numbers[symbol]:10d} 0 {float(x):15.8f} {float(y):15.8f} {float(z):15.8f}")
    return "\n".join([
        " Standard orientation:",
        " ---------------------------------------------------------------------",
        " Center     Atomic      Atomic             Coordinates (Angstroms)",
        " Number     Number       Type             X           Y           Z",
        " ---------------------------------------------------------------------",
        *coordinates,
        " ---------------------------------------------------------------------",
    ]) + "\n"


def _endpoint_optimization_logs(tmp_path, *, combined=True, reactant_xyz=_HCN_XYZ, product_xyz=_HNC_XYZ):
    """Native Opt first frames are the actual HCN IRC terminal frames, in both directions."""
    starts = {
        "reactant": "3\nforward outer frame\nC .410015 -.464572 0\nN -.320837 .486161 0\nH -.423925 -1.223669 0\n",
        "product": "3\nbackward outer frame\nC .480862 -.459245 0\nN -.349123 .435401 0\nH -.874843 -.581264 0\n",
    }
    logs = {}
    for role, minimum in (("reactant", reactant_xyz), ("product", product_xyz)):
        optimization = " # B3LYP/6-31G(d) Opt\n" + _gaussian_orientation(starts[role])
        optimization += _gaussian_orientation(minimum) + " Optimization completed.\n"
        frequency = _gaussian_orientation(minimum) + " Harmonic frequencies (cm**-1)\n Frequencies -- 300.0 1200.0 1300.0\n"
        normal = " Normal termination of Gaussian 16.\n"
        opt_path = tmp_path / f"{role}_opt.log"
        opt_path.write_text(optimization + (frequency if combined else "") + normal)
        logs[role] = [str(opt_path)]
        if not combined:
            freq_path = tmp_path / f"{role}_freq.log"
            freq_path.write_text(" # B3LYP/6-31G(d) Freq\n" + frequency + normal)
            logs[role].append(str(freq_path))
    return logs


@pytest.mark.asyncio
@pytest.mark.usefixtures("rdkit_chemistry")
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
    assert result.verification_status == "candidate"
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
    assert result.verification_status == "fail"
    assert any("minimum" in c for c in result.checks)


@pytest.mark.asyncio
@pytest.mark.parametrize("strict", [False, True])
@pytest.mark.parametrize("frequency_text,status,n_imag", [
    (_TS_FREQ_SNIPPET.replace("-915.3388", "915.3388"), "fail", 0),
    (_TS_FREQ_SNIPPET, "inconclusive", 1),
    (_TS_FREQ_SNIPPET.replace("Normal termination of Gaussian 16", "Error termination of Gaussian 16"),
     "inconclusive", 1),
], ids=["minimum", "first_order_saddle", "unfinished_frequency"])
async def test_verify_bad_reference_preserves_structured_frequency_result(
    tmp_path, mock_session, strict, frequency_text, status, n_imag,
):
    freq_log = tmp_path / "frequency.log"
    freq_log.write_text(frequency_text)
    result = await _make_tool().safe_call(TsGuess_input_schema(
        mode="verify", strict=strict, freq_log=str(freq_log), irc_log=str(IRC_LOG),
        reactant_text="not xyz", product_text=_HNC_XYZ,
    ), mock_session)

    assert result.is_success, result.message
    assert result.verification_status == status
    assert result.n_imag == n_imag
    if n_imag == 0 or "Error termination" in frequency_text:
        assert not any("not xyz" in check for check in result.checks)


@pytest.mark.asyncio
@pytest.mark.parametrize("strict", [False, True])
@pytest.mark.usefixtures("rdkit_chemistry")
async def test_verify_without_irc_uses_declared_molecule_charge(
    tmp_path, mock_session, monkeypatch, strict,
):
    from rdkit import Chem

    import cloudra.tools.Chemtool.ts_guess as ts_module

    mol = Chem.MolFromSmiles("[O-]C")
    conf = Chem.Conformer(2)
    conf.SetAtomPosition(0, (0, 0, 0))
    conf.SetAtomPosition(1, (1.43, 0, 0))
    mol.AddConformer(conf)
    freq_log = tmp_path / "frequency.log"
    freq_log.write_text(_TS_FREQ_WITH_GEOMETRY)
    assessed_charges = []
    assess = ts_module._assess_imag_mode_alignment

    def record_assessment(*args, **kwargs):
        assessed_charges.append(kwargs["charge"])
        return assess(*args, **kwargs)

    monkeypatch.setattr(ts_module, "_assess_imag_mode_alignment", record_assessment)
    result = await _make_tool().safe_call(TsGuess_input_schema(
        mode="verify", strict=strict, freq_log=str(freq_log), reactant_text=Chem.MolToMolBlock(mol),
    ), mock_session)

    assert result.is_success, result.message
    assert result.n_imag == 1
    assert assessed_charges == [-1]


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
@pytest.mark.usefixtures("rdkit_chemistry")
async def test_verify_strict_geometry_interval_without_optimization_logs_is_inconclusive(tmp_path, mock_session):
    """几何区间相符不能代替真实端点优化和零虚频证据。"""
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
    assert result.verdict.startswith("inconclusive")
    assert result.verification_status == "inconclusive"
    assert result.irc_end_a_path and result.irc_end_b_path


@pytest.mark.asyncio
@pytest.mark.parametrize("combined", [True, False], ids=["optfreq", "separate_opt_freq"])
@pytest.mark.usefixtures("rdkit_chemistry")
async def test_verify_strict_accepts_irc_outer_frames_optimized_to_verified_minima(
    tmp_path, mock_session, combined,
):
    from types import SimpleNamespace

    freq_log = tmp_path / "ts_freq.log"
    freq_log.write_text(_TS_FREQ_WITH_GEOMETRY)
    logs = _endpoint_optimization_logs(tmp_path, combined=combined)
    if not combined:
        logs = {role: [Path(path).name for path in paths] for role, paths in logs.items()}
    tool = TsGuess(subagent=SimpleNamespace(working_directory=str(tmp_path)))
    result = await tool.tool_call(TsGuess_input_schema(
        mode="verify", strict=True, freq_log=freq_log.name, irc_log=str(IRC_LOG),
        reactant_text=_HCN_XYZ, product_text=_HNC_XYZ,
        reactant_logs=logs["reactant"], product_logs=logs["product"],
        watch_pairs=[[1, 3], [2, 3]], output_dir=str(tmp_path / "verified"),
    ), mock_session)
    assert result.is_success, result.message
    assert result.verification_status == "pass", result.checks
    assert result.verdict.startswith("pass")
    assert result.irc_end_a_path and result.irc_end_b_path


@pytest.mark.asyncio
@pytest.mark.usefixtures("rdkit_chemistry")
async def test_verify_strict_rejects_optimized_endpoint_with_wrong_identity(tmp_path, mock_session):
    freq_log = tmp_path / "ts_freq.log"
    freq_log.write_text(_TS_FREQ_WITH_GEOMETRY)
    logs = _endpoint_optimization_logs(tmp_path, product_xyz=_HCN_XYZ)
    result = await _make_tool().safe_call(TsGuess_input_schema(
        mode="verify", strict=True, freq_log=str(freq_log), irc_log=str(IRC_LOG),
        reactant_text=_HCN_XYZ, product_text=_HNC_XYZ,
        reactant_logs=logs["reactant"], product_logs=logs["product"],
        watch_pairs=[[1, 3], [2, 3]], output_dir=str(tmp_path / "wrong_identity"),
    ), mock_session)
    assert result.is_success, result.message
    assert result.verification_status == "fail", result.checks


@pytest.mark.asyncio
@pytest.mark.usefixtures("rdkit_chemistry")
async def test_verify_strict_accepts_optimized_minima_but_warns_about_failed_interval(tmp_path, mock_session):
    freq_log = tmp_path / "ts_freq.log"
    freq_log.write_text(_TS_FREQ_WITH_GEOMETRY)
    logs = _endpoint_optimization_logs(tmp_path, reactant_xyz=_HCN_XYZ.replace("-1.07", "-1.36"))
    result = await _make_tool().safe_call(TsGuess_input_schema(
        mode="verify", strict=True, freq_log=str(freq_log), irc_log=str(IRC_LOG),
        reactant_text=_HCN_XYZ, product_text=_HNC_XYZ,
        reactant_logs=logs["reactant"], product_logs=logs["product"],
        watch_pairs=[[1, 3], [2, 3]], output_dir=str(tmp_path / "interval_warning"),
    ), mock_session)
    assert result.is_success, result.message
    assert result.verification_status == "pass", result.checks
    assert any("[warning]" in check and "interval" in check for check in result.checks)


@pytest.mark.asyncio
@pytest.mark.usefixtures("rdkit_chemistry")
async def test_verify_strict_unresolved_xyz_identity_is_inconclusive(tmp_path, mock_session):
    freq_log = tmp_path / "ts_freq.log"
    freq_log.write_text(_TS_FREQ_WITH_GEOMETRY)
    logs = _endpoint_optimization_logs(tmp_path)
    result = await _make_tool().safe_call(TsGuess_input_schema(
        mode="verify", strict=True, freq_log=str(freq_log), irc_log=str(IRC_LOG),
        reactant_text="3\nno resolvable graph\nC 0 0 0\nN 0 0 100\nH 0 0 200\n",
        product_text=_HNC_XYZ, reactant_logs=logs["reactant"], product_logs=logs["product"],
        watch_pairs=[[1, 3], [2, 3]], output_dir=str(tmp_path / "unknown_identity"),
    ), mock_session)
    assert result.is_success, result.message
    assert result.verification_status == "inconclusive", result.checks
    assert any("MOL/SDF" in check for check in result.checks)


@pytest.mark.asyncio
async def test_verify_strict_without_optimized_intermediates_is_inconclusive(tmp_path, mock_session, monkeypatch):
    """strict 缺少优化中间体时证据不足，不能沿用默认模式的候选结论。"""
    import sys

    monkeypatch.setitem(sys.modules, "rdkit", None)
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
    assert result.verification_status == "inconclusive"


@pytest.mark.asyncio
async def test_verify_strict_wrong_reference_geometry_without_logs_is_inconclusive(tmp_path, mock_session):
    """预期几何不相符仍不能代替缺失的实际端点优化证据。"""
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
    assert result.verdict.startswith("inconclusive")
    assert result.verification_status == "inconclusive"


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
@pytest.mark.usefixtures("rdkit_chemistry")
async def test_verify_strict_reordered_intermediate_is_aligned(tmp_path, mock_session):
    """原子序重排但组成相同的中间体：距离指纹 + Hungarian 对齐后照常判定
    （对应层就是为此存在的，重排不再是 inconclusive 的理由）。"""
    tool = _make_tool()
    freq_log = tmp_path / "ts_freq_with_geometry.log"
    freq_log.write_text(_TS_FREQ_WITH_GEOMETRY)
    logs = _endpoint_optimization_logs(tmp_path)

    result = await tool.safe_call(TsGuess_input_schema(**{
        "mode": "verify",
        "strict": True,
        "freq_log": str(freq_log),
        "irc_log": str(IRC_LOG),
        "reactant_text": _HCN_REORDERED_XYZ,
        "product_text": _HNC_XYZ,
        "reactant_logs": logs["reactant"],
        "product_logs": logs["product"],
        "output_dir": str(tmp_path / "strict_order_mismatch"),
    }), mock_session)

    assert result.is_success, result.message
    assert result.verdict.startswith("pass"), result.verdict


@pytest.mark.asyncio
async def test_verify_strict_element_mismatch_is_inconclusive(tmp_path, mock_session):
    """元素组成不同（原子数/元素多重集不等）的结构进不了判定层。"""
    tool = _make_tool()
    freq_log = tmp_path / "ts_freq_with_geometry.log"
    freq_log.write_text(_TS_FREQ_WITH_GEOMETRY)

    result = await tool.safe_call(TsGuess_input_schema(**{
        "mode": "verify",
        "strict": True,
        "freq_log": str(freq_log),
        "irc_log": str(IRC_LOG),
        "reactant_text": "2\n\nO 0.0 0.0 0.0\nO 0.0 0.0 1.2\n",
        "product_text": _HNC_XYZ,
        "output_dir": str(tmp_path / "strict_element_mismatch"),
    }), mock_session)

    assert result.is_success, result.message
    assert result.verdict.startswith("inconclusive")


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
@pytest.mark.usefixtures("rdkit_chemistry")
async def test_verify_strict_endpoint_proof_overrides_misaligned_mode_warning(tmp_path, mock_session):
    """模式比例可疑时仍核验真实端点，不让启发式否决已成立的方向证明。"""
    tool = _make_tool()
    freq_log = tmp_path / "ts_freq_wrong_mode.log"
    freq_log.write_text(_TS_FREQ_WRONG_MODE)
    logs = _endpoint_optimization_logs(tmp_path)

    result = await tool.safe_call(TsGuess_input_schema(**{
        "mode": "verify",
        "strict": True,
        "freq_log": str(freq_log),
        "irc_log": str(IRC_LOG),
        "reactant_text": _HCN_XYZ,
        "product_text": _HNC_XYZ,
        "reactant_logs": logs["reactant"],
        "product_logs": logs["product"],
        "watch_pairs": [[1, 3], [2, 3]],
        "output_dir": str(tmp_path / "strict_bad_mode"),
    }), mock_session)

    assert result.is_success, result.message
    assert result.verification_status == "pass", result.checks
    assert any("[warning]" in check and "mode" in check for check in result.checks)
    assert result.imag_mode_aligned is False
    assert result.irc_end_a_path and result.irc_end_b_path


@pytest.mark.asyncio
@pytest.mark.usefixtures("rdkit_chemistry")
async def test_verify_strict_endpoint_proof_overrides_missing_mode_warning(tmp_path, mock_session):
    """缺模式位移不等于缺端点证据；真实端点方向证明仍可通过。"""
    tool = _make_tool()
    freq_log = tmp_path / "ts_freq_no_disps.log"
    freq_log.write_text(_TS_FREQ_NO_DISPS)
    logs = _endpoint_optimization_logs(tmp_path)

    result = await tool.safe_call(TsGuess_input_schema(**{
        "mode": "verify",
        "strict": True,
        "freq_log": str(freq_log),
        "irc_log": str(IRC_LOG),
        "reactant_text": _HCN_XYZ,
        "product_text": _HNC_XYZ,
        "reactant_logs": logs["reactant"],
        "product_logs": logs["product"],
        "watch_pairs": [[1, 3], [2, 3]],
        "output_dir": str(tmp_path / "strict_no_disps"),
    }), mock_session)

    assert result.is_success, result.message
    assert result.verification_status == "pass", result.checks
    assert any("[warning]" in check and "normal-mode displacements" in check for check in result.checks)
    assert result.imag_mode_aligned is None
    assert result.irc_end_a_path and result.irc_end_b_path


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
    assert result.verification_status == "candidate"
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
    assert result.scan_has_internal_peak is True
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
    assert result.scan_has_internal_peak is False
    assert "NOT a TS candidate" in result.message
    assert "TS guess" not in result.profile_table
    # G4：无内部峰时 barrier_kcal 置 None，且不得声称 "TS-guess geometry is ..."
    assert result.barrier_kcal is None
    assert not any("TS-guess geometry" in v for v in result.verdicts)


def _write_h2_scan_sidecar(tmp_path, missing=None):
    dat = tmp_path / "h2.relaxscanact.dat"
    dat.write_text("0.70 -1.0\n1.00 -0.9\n1.40 -0.8\n", encoding="utf-8")
    for number, distance in enumerate((0.70, 1.00, 1.40), start=1):
        if number != missing:
            (tmp_path / f"h2.{number:03d}.xyz").write_text(
                f"2\nframe {number}\nH 0 0 0\nH 0 0 {distance}\n", encoding="utf-8",
            )


@pytest.mark.asyncio
async def test_scan_parse_no_peak_reports_h_distances_and_heuristic_change(tmp_path, mock_session):
    _write_h2_scan_sidecar(tmp_path)
    result = await _make_tool().safe_call(TsGuess_input_schema(**{
        "mode": "scan_parse", "engine": "orca", "log_path": str(tmp_path / "h2.out"),
        "watch_pairs": [[0, 1]],
    }), mock_session)
    assert result.is_success, result.message
    assert result.candidate is None
    assert result.barrier_kcal is None
    assert "H0-H1" in result.distance_table
    assert "0  observed  0.7000" in result.distance_table
    assert "2  observed  1.4000" in result.distance_table
    assert any("Frames 0->1: perceived connectivity" in v and "H0-H1" in v
               for v in result.verdicts)
    assert any("do not prove" in v for v in result.verdicts)


@pytest.mark.asyncio
async def test_scan_parse_missing_middle_frame_has_no_bridged_topology(tmp_path, mock_session):
    _write_h2_scan_sidecar(tmp_path, missing=2)
    result = await _make_tool().safe_call(TsGuess_input_schema(**{
        "mode": "scan_parse", "engine": "orca", "log_path": str(tmp_path / "h2.out"),
        "watch_pairs": [[0, 1]],
    }), mock_session)
    assert result.is_success, result.message
    assert result.candidate_unavailable
    assert "1  unavailable/invalid" in result.distance_table
    assert "2  observed  1.4000" in result.distance_table
    assert any("Frames 0->1: connectivity comparison unavailable" in v for v in result.verdicts)
    assert any("Frames 1->2: connectivity comparison unavailable" in v for v in result.verdicts)
    assert not any("perceived connectivity formed" in v for v in result.verdicts)
    assert not list(tmp_path.glob("*_ts_guess.xyz"))


@pytest.mark.asyncio
async def test_scan_parse_rejects_invalid_watch_pair(tmp_path, mock_session):
    _write_h2_scan_sidecar(tmp_path)
    result = await _make_tool().safe_call(TsGuess_input_schema(**{
        "mode": "scan_parse", "engine": "orca", "log_path": str(tmp_path / "h2.out"),
        "watch_pairs": [[1, 3]],
    }), mock_session)
    assert not result.is_success
    assert "out of range" in result.message


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
    assert result.scan_has_internal_peak is True
    assert result.candidate is None
    assert result.candidate_unavailable is True
    assert not result.ts_candidate_path
    assert "NOT" in result.message or "not replaced" in result.message
    # 不得有任何用其它帧写出的 TS-guess 几何
    assert not list(tmp_path.glob("*_ts_guess.xyz"))
    assert "9  unavailable/invalid" in result.distance_table
    assert "10  observed" in result.distance_table
    assert any("Frames 8->9: connectivity comparison unavailable" in v for v in result.verdicts)


@pytest.mark.asyncio
@pytest.mark.parametrize("bad_frame,expect_candidate", [(1, True), (15, True), (10, False)])
async def test_scan_parse_misaligned_frame_preserves_only_trustworthy_peak(
        tmp_path, mock_session, bad_frame, expect_candidate):
    _copy_scan_fixture_with_peak(tmp_path)
    path = tmp_path / f"ts_scan.{bad_frame:03d}.xyz"
    lines = path.read_text(encoding="utf-8").splitlines()
    fields = lines[2].split()
    fields[0] = "He" if fields[0] != "He" else "Ne"
    lines[2] = "  ".join(fields)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    result = await _make_tool().safe_call(TsGuess_input_schema(**{
        "mode": "scan_parse", "engine": "orca",
        "log_path": str(tmp_path / "ts_scan.out"),
    }), mock_session)
    assert result.is_success, result.message
    assert any(line.split() == [str(bad_frame - 1), "unavailable/invalid"]
               for line in result.distance_table.splitlines())
    assert (result.candidate is not None) is expect_candidate
    assert result.candidate_unavailable is (not expect_candidate)
    assert bool(list(tmp_path.glob("*_ts_guess.xyz"))) is expect_candidate


@pytest.mark.asyncio
@pytest.mark.usefixtures("rdkit_chemistry")
async def test_scan_prepare_gaussian_scan_start_mismatch_rejected(tmp_path, mock_session):
    """Gaussian：scan_start 与当前几何值不同 → start_geometry_mismatch，
    而不是静默只调增量扫错区间。"""
    tool = _make_tool()
    out = tmp_path / "scan.gjf"
    result = await tool.safe_call(TsGuess_input_schema(charge=0, **{'basis_set': 'def2svp',
        "mode": "scan_prepare",
        "method": 'b3lyp',
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
@pytest.mark.usefixtures("rdkit_chemistry")
async def test_scan_prepare_gaussian_scan_start_matching_current_accepted(tmp_path, mock_session):
    """scan_start 与当前几何值一致（容差内）时不误伤。"""
    import math as _math

    tool = _make_tool()
    out = tmp_path / "scan.gjf"
    current = _math.dist((0.0, 0.0, 0.1173), (0.0, 0.7572, -0.4692))
    result = await tool.safe_call(TsGuess_input_schema(charge=0, **{'basis_set': 'def2svp',
        "mode": "scan_prepare",
        "method": 'b3lyp',
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


def test_orca_irc_endpoints_unconverged_side_uses_outermost_frame(tmp_path):
    """未收敛方向不再留缺口：与 Gaussian 通道同口径，轨迹末帧仍是合法的
    部分端点，收敛与否只记 note；方向是否成立交给几何区间证明。"""
    log = _orca_irc_log_with_sidecars(tmp_path, backward_converged=False)
    checks: list[str] = []
    result = TsGuess._extract_orca_irc_endpoints(
        str(log), checks, output_dir=str(tmp_path / "out"), require_two_sides=True,
    )

    assert result is not None
    assert Path(result["path_a"]).exists()
    assert Path(result["path_b"]).exists()
    assert result["meta"]["forward_converged"] is True
    assert result["meta"]["backward_converged"] is False
    assert any("backward" in c and "WITHOUT converging" in c for c in checks)
    assert any("partial endpoint" in c for c in checks)


def test_orca_irc_endpoints_converged_short_path_needs_no_padding(tmp_path):
    """两侧收敛（即使点数很少）→ 端点可提取，且明确 F/B 不等于 R/P。"""
    log = _orca_irc_log_with_sidecars(tmp_path, backward_converged=True)
    out_dir = tmp_path / "out"
    checks: list[str] = []
    result = TsGuess._extract_orca_irc_endpoints(
        str(log), checks, output_dir=str(out_dir), require_two_sides=True,
    )

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
    freq_log.write_text("O   R   C   A\nplaceholder (freq parsing stubbed)\n", encoding="utf-8")
    monkeypatch.setattr(ts_mod, "_parse_freq_log", lambda path, engine: {
        "vibfreqs": [-512.3, 100.0, 200.0],
        "vibdisps": None,
        "normal_termination": True,
        "opt_converged": None,
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
    assert result.scan_has_internal_peak is False
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
    assert result.candidate["source"] == "orca_log_text"


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
        assert parsed["normal_termination"] is True
        assert parsed["opt_converged"] is True


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
        "O   R   C   A\nTHE OPTIMIZATION HAS CONVERGED\n" + freq_block + "****ORCA TERMINATED NORMALLY****\n",
        encoding="utf-8",
    )
    parsed = ts_mod._parse_freq_log(str(converged_log), "orca")
    assert parsed["normal_termination"] is True
    assert parsed["opt_converged"] is True

    # 跑满最大步数未收敛的优化仍可能正常终止——收敛判定必须为 False
    unconv_log = tmp_path / "unconv.out"
    unconv_log.write_text(
        "O   R   C   A\nThe optimization did not converge\n" + freq_block + "****ORCA TERMINATED NORMALLY****\n",
        encoding="utf-8",
    )
    parsed = ts_mod._parse_freq_log(str(unconv_log), "orca")
    assert parsed["normal_termination"] is True
    assert parsed["opt_converged"] is False


@pytest.mark.asyncio
@pytest.mark.usefixtures("rdkit_chemistry")
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
    res_prep = await tool.safe_call(TsGuess_input_schema(charge=0, **{'engine': 'gaussian', 'basis_set': 'def2svp',
        "mode": "scan",
        "method": 'b3lyp',
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
if mode == "fail_with_cycles":
    print("terminated because max. # cycles reached")
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
async def test_explicit_xtb_path_reports_path_kind(fake_xtb_for_ts, tmp_path, mock_session):
    """显式选择 xTB MTD 路径，并写明 path_kind。"""
    fake_xtb_for_ts("ok")
    out_dir = tmp_path / "guess_default"
    res = await _make_tool().safe_call(TsGuess_input_schema(**{
        "mode": "xtb_path",
        "reactant_text": _path_mol(_R_XYZ),
        "product_text": _path_mol(_P_XYZ),
        "output_dir": str(out_dir),
    }), mock_session)
    assert res.is_success, res.message
    assert res.path_kind == "xtb_path"
    assert res.refinement_termination == "converged"
    assert res.path_termination_reason == "completed"
    assert res.images_dir == str(out_dir)
    assert res.ts_candidate_path and Path(res.ts_candidate_path).is_file()
    # 路径帧落盘
    frames = sorted(Path(out_dir).glob("img_*.xyz"))
    assert len(frames) == 3
    # 初猜 ≠ 已验证
    assert "not verified" in res.message.lower() or "guess" in res.message.lower()


@pytest.mark.asyncio
@pytest.mark.parametrize("idpp_mode", ["standard", "light"])
async def test_xtb_missing_falls_back_to_idpp_and_says_so(tmp_path, monkeypatch, mock_session, idpp_mode):
    """xTB 缺失时退回 IDPP 插值，但**必须显式标注**走了兜底，不许静默降级。"""
    empty = tmp_path / "empty-path"
    empty.mkdir()
    monkeypatch.setenv("PATH", str(empty))
    out_dir = tmp_path / "guess_fallback"
    res = await _make_tool().safe_call(TsGuess_input_schema(**{
        "mode": "xtb_path",
        "reactant_text": _path_mol(_R_XYZ),
        "product_text": _path_mol(_P_XYZ),
        "n_images": 4,
        "idpp_mode": idpp_mode,
        "output_dir": str(out_dir),
    }), mock_session)
    assert res.is_success, res.message
    assert res.path_kind == "idpp_fallback"
    assert "fallback" in res.message.lower() or "idpp" in res.message.lower()
    assert res.ts_candidate_path and Path(res.ts_candidate_path).is_file()

    assert res.interpolation["idpp_mode"] == idpp_mode
    assert "convergence=" in res.message


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
        "mode": "xtb_path",
        "reactant_text": _path_mol(_R_XYZ),
        "product_text": _path_mol(_P_XYZ),
        "output_dir": str(out_dir),
    }), mock_session)
    assert not res.is_success
    assert res.refinement_termination == "cycles_exhausted"
    assert res.path_termination_reason == "path_not_converged"
    assert Path(res.images_dir).is_dir()
    assert Path(res.images_dir) != out_dir
    assert Path(res.images_dir).is_relative_to(out_dir)
    assert res.path_kind == ""
    assert "refinement_runs" in res.message
    assert "truncated" in res.message.lower()


@pytest.mark.asyncio
async def test_xtb_failure_is_reported_not_silently_replaced(fake_xtb_for_ts, tmp_path, mock_session):
    """xTB 存在但跑失败：报出分类，**不得**偷偷换成 IDPP 插值充数。"""
    fake_xtb_for_ts("fail")
    res = await _make_tool().safe_call(TsGuess_input_schema(**{
        "mode": "xtb_path",
        "reactant_text": _path_mol(_R_XYZ),
        "product_text": _path_mol(_P_XYZ),
        "output_dir": str(tmp_path / "guess_fail"),
    }), mock_session)
    assert res.is_success is False
    assert res.path_kind == ""
    assert "xtb" in res.message.lower()
    assert "bad things happened" in res.message or "failed" in res.message.lower()


@pytest.mark.asyncio
async def test_xtb_cycles_marker_with_failed_process_is_not_path_nonconvergence(
    fake_xtb_for_ts, tmp_path, mock_session,
):
    fake_xtb_for_ts("fail_with_cycles")
    res = await _make_tool().safe_call(TsGuess_input_schema(**{
        "mode": "xtb_path", "reactant_text": _path_mol(_R_XYZ), "product_text": _path_mol(_P_XYZ),
        "output_dir": str(tmp_path / "guess_failed_with_marker"),
    }), mock_session)
    assert not res.is_success
    assert res.refinement_termination == "cycles_exhausted"
    assert res.path_termination_reason == "failed"
    assert Path(res.images_dir).is_dir()


def test_legacy_xtb_neb_alias_is_gone():
    """误导性的 xtb_neb 别名已删除（它只是映射到 interpolate，不跑 NEB）。"""
    import pytest as _pytest

    with _pytest.raises(Exception):
        TsGuess_input_schema(**{
            "mode": "xtb_neb",
            "reactant_text": _path_mol(_R_XYZ),
            "product_text": _path_mol(_P_XYZ),
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
        result = await _make_tool().tool_call(TsGuess_input_schema(
            mode="xtb_path", reactant_text=_R_XYZ, product_text=_P_XYZ,
        ), mock_session)
    finally:
        stop = True
        await ticker_task
    assert result.is_success is True
    # 若阻塞发生在事件循环线程上，0.4s 的冻结期里 ticker 只会前进寥寥几步
    assert ticks > 5, f"event loop was frozen during tool_call (ticks={ticks})"


# ---------------------------------------------------------------------------
# 监测对选择：复用 irc_path.classify_watch_pairs 的闸门对（键图 diff ∪ top5）
# ---------------------------------------------------------------------------


def test_select_watch_pairs_uses_bond_diff_gate():
    """键翻转对进监测对；距离不变的对不再被纯距离 top-5 白占名额。"""
    from cloudra.tools.Chemtool.ts_guess import _select_watch_pairs

    symbols = ["C", "N", "H"]
    # TS 侧 C-H 成键、产物侧 N-H 成键（质子转移）；C-N 距离不变
    d_start = np.array([[0.0, 2.0, 1.1], [2.0, 0.0, 2.1], [1.1, 2.1, 0.0]])
    d_end = np.array([[0.0, 2.0, 2.1], [2.0, 0.0, 1.0], [2.1, 1.0, 0.0]])
    pairs = _select_watch_pairs(symbols, d_start, d_end, [])
    assert pairs == [(0, 2), (1, 2)]

    # 显式 watch_pairs 路径不变（1-based 校验照旧）
    assert _select_watch_pairs(symbols, d_start, d_end, [[1, 2]]) == [(0, 1)]
    with pytest.raises(ValueError):
        _select_watch_pairs(symbols, d_start, d_end, [[1, 9]])


# ---------------------------------------------------------------------------
# 虚频模式对齐：非键对主导（扭转/角主导模式）降级 undecidable
# ---------------------------------------------------------------------------

# C,N,H TS 几何（C-N、C-H 成键；N···H 1.41 Å 不成键）
_NONBONDED_TS_POS = [
    [0.427601, -0.595125, 0.000000],
    [-0.354874, 0.327913, 0.000000],
    [-0.680027, -1.045650, 0.000000],
]

# 虚频模式：N···H 非键对主导（阻转/锥形反转式位移），C 几乎不动
_TS_FREQ_NONBONDED_MODE = """\
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
     1   6     0.00   0.00   0.00     0.00   0.10   0.00     0.00   0.00   0.10
     2   7     0.80   0.00   0.00     0.00  -0.10   0.00     0.00   0.00  -0.10
     3   1    -0.80   0.00   0.00     0.00   0.00   0.10     0.00   0.10   0.00
 Normal termination of Gaussian 16 at Sat Mar 22 18:44:39 2025.
"""


def test_imag_mode_alignment_nonbonded_dominant_is_undecidable():
    """主导位移对两端不成键时：pair-distance 对齐材料不足以判方向，
    status=undecidable（不是 misaligned——扭转/角主导模式键对距离本就不动）。"""
    from cloudra.tools.Chemtool.ts_guess import _assess_imag_mode_alignment

    vibfreqs = [-915.0, 1200.0, 1300.0]
    vibdisps = np.array([
        [[0.0, 0.0, 0.0], [0.8, 0.0, 0.0], [-0.8, 0.0, 0.0]],
        [[0.0, 0.1, 0.0], [0.0, -0.1, 0.0], [0.0, 0.0, 0.1]],
        [[0.0, 0.0, 0.1], [0.0, 0.0, -0.1], [0.0, 0.1, 0.0]],
    ], dtype=float)
    result = _assess_imag_mode_alignment(
        vibfreqs, vibdisps, watch_pairs=[[1, 2]],
        symbols=["C", "N", "H"], positions=_NONBONDED_TS_POS, charge=0,
    )
    assert result["status"] == "undecidable"
    assert result["aligned"] is None
    assert "NON-BONDED" in result["message"]

    # 主导对是键对（C-N 伸缩）时维持 misaligned 原规则
    bonded_disps = np.array([
        [[1.0, 0.0, 0.0], [-1.0, 0.0, 0.0], [0.0, 0.0, 0.0]],
        [[0.0, 0.1, 0.0], [0.0, -0.1, 0.0], [0.0, 0.0, 0.1]],
        [[0.0, 0.0, 0.1], [0.0, 0.0, -0.1], [0.0, 0.1, 0.0]],
    ], dtype=float)
    bonded = _assess_imag_mode_alignment(
        vibfreqs, bonded_disps, watch_pairs=[[1, 3]],
        symbols=["C", "N", "H"], positions=_NONBONDED_TS_POS, charge=0,
    )
    assert bonded["status"] == "misaligned"
    assert bonded["aligned"] is False

    # 无 TS 几何时无法判成键性：同样维持原规则（不猜）
    no_geo = _assess_imag_mode_alignment(
        vibfreqs, vibdisps, watch_pairs=[[1, 2]],
    )
    assert no_geo["status"] == "misaligned"


@pytest.mark.asyncio
@pytest.mark.usefixtures("rdkit_chemistry")
async def test_verify_strict_endpoint_proof_overrides_undecidable_mode_warning(tmp_path, mock_session):
    """模式比例不能判断扭转/角方向时，实际端点优化证据仍决定验收。"""
    tool = _make_tool()
    freq_log = tmp_path / "ts_freq_nonbonded_mode.log"
    freq_log.write_text(_TS_FREQ_NONBONDED_MODE)
    logs = _endpoint_optimization_logs(tmp_path)

    result = await tool.safe_call(TsGuess_input_schema(**{
        "mode": "verify",
        "strict": True,
        "freq_log": str(freq_log),
        "irc_log": str(IRC_LOG),
        "reactant_text": _HCN_XYZ,
        "product_text": _HNC_XYZ,
        "reactant_logs": logs["reactant"],
        "product_logs": logs["product"],
        "watch_pairs": [[1, 2]],
        "output_dir": str(tmp_path / "strict_nonbonded"),
    }), mock_session)

    assert result.is_success, result.message
    assert result.verification_status == "pass", result.checks
    assert result.imag_mode_aligned is None
    assert any("[warning]" in check and "NON-BONDED" in check for check in result.checks)
    assert result.irc_end_a_path and result.irc_end_b_path


@pytest.mark.asyncio
@pytest.mark.parametrize("frequency_text,watch_pairs", [
    (_TS_FREQ_WRONG_MODE, [[1, 3], [2, 3]]),
    (_TS_FREQ_NO_DISPS, [[1, 3], [2, 3]]),
    (_TS_FREQ_NONBONDED_MODE, [[1, 2]]),
], ids=["misaligned", "missing_mode", "undecidable"])
@pytest.mark.parametrize("endpoint_problem,expected_status", [
    ("missing_logs", "inconclusive"),
    ("wrong_outer_frame", "fail"),
])
@pytest.mark.usefixtures("rdkit_chemistry")
async def test_verify_strict_mode_advisory_cannot_replace_endpoint_proof(
    tmp_path, mock_session, frequency_text, watch_pairs, endpoint_problem, expected_status,
):
    freq_log = tmp_path / "ts_freq.log"
    freq_log.write_text(frequency_text)
    logs = _endpoint_optimization_logs(tmp_path)
    if endpoint_problem == "missing_logs":
        logs["reactant"] = []
    else:
        opt_log = Path(logs["reactant"][0])
        opt_log.write_text(opt_log.read_text().replace("-1.22366900", "-1.52366900", 1))
    result = await _make_tool().safe_call(TsGuess_input_schema(
        mode="verify", strict=True, freq_log=str(freq_log), irc_log=str(IRC_LOG),
        reactant_text=_HCN_XYZ, product_text=_HNC_XYZ,
        reactant_logs=logs["reactant"], product_logs=logs["product"], watch_pairs=watch_pairs,
        output_dir=str(tmp_path / "invalid_endpoint"),
    ), mock_session)

    assert result.is_success, result.message
    assert result.verification_status == expected_status, result.checks
    assert result.irc_end_a_path and result.irc_end_b_path
    assert any("[warning]" in check and "mode" in check for check in result.checks)


@pytest.mark.asyncio
@pytest.mark.usefixtures("rdkit_chemistry")
async def test_verify_non_strict_nonbonded_dominant_mode_is_undecidable(tmp_path, mock_session):
    """默认档：非键对主导的虚频模式不再回 imag_mode_aligned=False（不再暗示方向不符），
    只把 undecidable 记进 checks；建议语义仍是 candidate。"""
    tool = _make_tool()
    freq_log = tmp_path / "ts_freq_nonbonded_mode.log"
    freq_log.write_text(_TS_FREQ_NONBONDED_MODE)

    result = await tool.safe_call(TsGuess_input_schema(**{
        "mode": "verify",
        "freq_log": str(freq_log),
        "irc_log": str(IRC_LOG),
        "reactant_text": _HCN_XYZ,
        "product_text": _HNC_XYZ,
        "watch_pairs": [[1, 2]],
        "output_dir": str(tmp_path / "non_strict_nonbonded"),
    }), mock_session)

    assert result.is_success, result.message
    assert result.verdict.startswith("candidate")
    assert result.imag_mode_aligned is None
    assert any("NON-BONDED" in c for c in result.checks)
    assert any("connectivity is consistent" in c for c in result.checks)


# ---------------------------------------------------------------------------
# 默认档 IRC 连通性：perceive_bonds 键感知 + 弱接触分级 + 不可判显式化
# ---------------------------------------------------------------------------

_WATER_A = """3
endpoint A
O  0.00  0.00  0.00
H  0.96  0.00  0.00
H  -0.24  0.93  0.00
"""

_WATER_B_STRETCHED = """3
endpoint B
O  0.00  0.00  0.00
H  1.10  0.00  0.00
H  -0.24  0.93  0.00
"""

_WATER_B_DISSOCIATED = """3
endpoint B
O  0.00  0.00  0.00
H  3.00  0.00  0.00
H  -0.24  0.93  0.00
"""

_WATER_P_WEAK = """3
product
O  0.00  0.00  0.00
H  1.50  0.00  0.00
H  -0.24  0.93  0.00
"""

_WATER_P_COVALENT = """3
product
O  0.00  0.00  0.00
H  0.96  0.00  0.00
H  -0.24  0.93  0.00
"""


def _connectivity_input(reactant_text, product_text):
    from types import SimpleNamespace

    return SimpleNamespace(
        reactant_path=None, reactant_text=reactant_text,
        product_path=None, product_text=product_text,
        charge=0, engine="gaussian",
    )


def _frame(xyz):
    from types import SimpleNamespace

    return SimpleNamespace(xyz=xyz)


def _connectivity_verdict(request, end_a, end_b, checks):
    from cloudra.tools.Chemtool.ts_guess import _reference_molecules

    return TsGuess._check_irc_connectivity(request, end_a, end_b, checks, _reference_molecules(request))


@pytest.mark.usefixtures("rdkit_chemistry")
def test_reference_mol_graph_is_not_reperceived(monkeypatch):
    from rdkit import Chem

    import cloudra.tools.Chemtool.ts_guess as ts_module

    mol = Chem.MolFromSmiles("[Na+].[O-][13CH3:7]")
    conf = Chem.Conformer(3)
    for i, position in enumerate([(0.7, 1, 0), (0, 0, 0), (1.43, 0, 0)]):
        conf.SetAtomPosition(i, position)
    mol.AddConformer(conf)
    block = Chem.MolToMolBlock(mol)
    request = TsGuess_input_schema(mode="verify", freq_log="unused.log", reactant_text=block, product_text=block)
    calls = []

    def perceive(*args):
        calls.append(args)
        return {(1, 2): 1.0}, "rdDetermineBonds"

    monkeypatch.setattr(ts_module, "_perceive_bonds", perceive)
    references = ts_module._reference_molecules(request)
    frame = _frame("3\nendpoint\nNa .7 1 0\nO 0 0 0\nC 1.43 0 0\n")
    checks = []
    assert TsGuess._check_irc_connectivity(request, frame, frame, checks, references) is True
    assert len(calls) == 2
    assert references["reactant"].GetAtomWithIdx(2).GetIsotope() == 13
    assert references["reactant"].GetAtomWithIdx(2).GetAtomMapNum() == 7


@pytest.mark.parametrize("engine,base", [("gaussian", 1), ("orca", 0)])
@pytest.mark.usefixtures("rdkit_chemistry")
def test_scan_reads_mol_and_uses_molecule_charge(tmp_path, engine, base):
    from rdkit import Chem

    mol = Chem.MolFromSmiles("[O-]C")
    conf = Chem.Conformer(2)
    conf.SetAtomPosition(0, (0, 0, 0))
    conf.SetAtomPosition(1, (1.43, 0, 0))
    mol.AddConformer(conf)
    path = tmp_path / "source.mol"
    path.write_text(Chem.MolToMolBlock(mol))
    output = tmp_path / ("scan.inp" if engine == "orca" else "scan.gjf")
    result = TsGuess()._scan_prepare(TsGuess_input_schema(
        mode="scan_prepare", engine=engine, method="B3LYP", basis_set="def2-SVP",
        input_path=str(path), output_path=str(output),
        scans=[{"atoms": [base, base + 1], "scan_end": 2.0, "scan_steps": 5}],
    ))
    assert result.is_success, result.message
    assert ("* xyz -1 1" if engine == "orca" else "\n-1 1\n") in output.read_text()


@pytest.mark.usefixtures("rdkit_chemistry")
def test_check_irc_connectivity_weak_contact_is_warning_not_failure():
    """键集差异在预期结构侧是弱接触（>1.25×共价半径和）时只记 warning、不判负。"""
    checks: list[str] = []
    verdict = _connectivity_verdict(
        _connectivity_input(_WATER_A, _WATER_P_WEAK),
        _frame(_WATER_A), _frame(_WATER_B_STRETCHED), checks,
    )
    assert verdict is True, checks
    assert any("[warning]" in c and "weak-contact" in c for c in checks)
    assert any("connectivity is consistent" in c for c in checks)


@pytest.mark.usefixtures("rdkit_chemistry")
def test_check_irc_connectivity_covalent_difference_still_fails():
    """预期结构侧仍是共价键的键集差异：照旧判负（不降级）。"""
    checks: list[str] = []
    verdict = _connectivity_verdict(
        _connectivity_input(_WATER_A, _WATER_P_COVALENT),
        _frame(_WATER_A), _frame(_WATER_B_DISSOCIATED), checks,
    )
    assert verdict is False, checks
    assert any("covalent" in c and "inconsistent" in c for c in checks)


@pytest.mark.usefixtures("rdkit_chemistry")
def test_check_irc_connectivity_endpoint_order_mismatch_is_inconclusive():
    """两端点帧的原子序/元素不一致：连通性不可判（不拿 A 的元素配 B 的坐标硬算键）。"""
    checks: list[str] = []
    verdict = _connectivity_verdict(
        _connectivity_input(_WATER_A, _WATER_A),
        _frame(_WATER_A),
        _frame("3\nendpoint B\nH  0.96  0.00  0.00\nO  0.00  0.00  0.00\nH -0.24  0.93  0.00\n"),
        checks,
    )
    assert verdict == "inconclusive", checks
    assert any("undecidable" in c for c in checks)


@pytest.mark.usefixtures("rdkit_chemistry")
def test_check_irc_connectivity_uses_perceive_bonds_channel(monkeypatch):
    """端点/预期结构的键图来自 perceive_bonds（rdDetermineBonds 主通道），不是共价半径距离判据。

    注入一张把 3.0 Å 的 O-H 也报成键的键图（距离判据绝不可能给出）时，判定必须
    跟着感知通道走；同一几何退回距离判据（感知通道不可用）时结论相反——证明这条
    通路消费的是 perceive_bonds，而不是 bond_pairs_from_dist。
    """
    from cloudra.tools.core import irc_path

    monkeypatch.setattr(irc_path, "_rdkit_bonds", lambda *a: {(0, 1): 1.0, (0, 2): 1.0})
    checks: list[str] = []
    verdict = _connectivity_verdict(
        _connectivity_input(_WATER_A, _WATER_A),
        _frame(_WATER_B_DISSOCIATED), _frame(_WATER_B_DISSOCIATED), checks,
    )
    assert verdict is True, checks

    monkeypatch.setattr(irc_path, "_rdkit_bonds", lambda *a: None)
    checks = []
    verdict = _connectivity_verdict(
        _connectivity_input(_WATER_A, _WATER_A),
        _frame(_WATER_B_DISSOCIATED), _frame(_WATER_B_DISSOCIATED), checks,
    )
    assert verdict is False, checks


@pytest.mark.asyncio
@pytest.mark.usefixtures("rdkit_chemistry")
async def test_verify_atom_order_mismatch_is_inconclusive_not_candidate(tmp_path, mock_session):
    """预期结构原子序与 IRC 作业不符：连通性不可判 → inconclusive，
    不再静默跳过成 candidate。"""
    tool = _make_tool()
    freq_log = tmp_path / "ts_freq.log"
    freq_log.write_text(_TS_FREQ_SNIPPET)

    result = await tool.safe_call(TsGuess_input_schema(**{
        "mode": "verify",
        "freq_log": str(freq_log),
        "irc_log": str(IRC_LOG),
        "reactant_text": _HCN_REORDERED_XYZ,
        "product_text": _HNC_XYZ,
        "output_dir": str(tmp_path / "verify_order_mismatch"),
    }), mock_session)

    assert result.is_success, result.message
    assert result.verdict.startswith("inconclusive")
    assert any("undecidable" in c for c in result.checks)


# ---------------------------------------------------------------------------
# scan_parse（Gaussian）：Standard orientation 块与扫描点对不齐时拒发几何
# ---------------------------------------------------------------------------


def _gaussian_scan_log(n_block_rs: list[float]) -> str:
    """合成 Gaussian relaxed-scan 日志：3 点扫描（峰在中点），
    给定 R 值的 Standard orientation 块若干（块数可与点数不同）。"""
    blocks = []
    for r in n_block_rs:
        blocks.append(f"""\
 Standard orientation:
 ---------------------------------------------------------------------
 Center     Atomic      Atomic             Coordinates (Angstroms)
 Number     Number       Type             X           Y           Z
 ---------------------------------------------------------------------
      1          1           0        0.000000    0.000000    0.000000
      2          1           0        0.000000    0.000000    {r:.6f}
 ---------------------------------------------------------------------
""")
    return "".join(blocks) + """\
 Summary of Optimized Potential Surface Scan:
 Eigenvalues --  -100.00000  -99.99000  -100.00000
"""


@pytest.mark.asyncio
async def test_scan_parse_gaussian_no_peak_still_reports_distances(tmp_path, mock_session, monkeypatch):
    monkeypatch.setattr("cclib.io.ccread", lambda *a, **_kw: None)
    log = tmp_path / "scan.log"
    log.write_text(_gaussian_scan_log([0.70, 1.00, 1.40]).replace(
        "-100.00000  -99.99000  -100.00000",
        "-100.00000  -99.99000  -99.98000",
    ), encoding="utf-8")
    result = await _make_tool().safe_call(TsGuess_input_schema(**{
        "mode": "scan_parse", "engine": "gaussian", "log_path": str(log),
        "watch_pairs": [[1, 2]],
    }), mock_session)
    assert result.is_success, result.message
    assert result.candidate is None
    assert "H1-H2" in result.distance_table
    assert "0  observed  0.7000" in result.distance_table
    assert "2  observed  1.4000" in result.distance_table
    assert any("Frames 0->1: perceived connectivity" in v for v in result.verdicts)


@pytest.mark.asyncio
async def test_scan_parse_gaussian_ungroupable_blocks_refuses_candidate(tmp_path, mock_session, monkeypatch):
    """cclib 取不到 scancoords 且块数≠点数（2 块对 3 点）：严禁按块均分或
    拿末块顶替——candidate_unavailable=True，拒发几何（与 ORCA 同口径，GH #G1）。"""
    monkeypatch.setattr("cclib.io.ccread", lambda *a, **_kw: None)
    tool = _make_tool()
    log = tmp_path / "scan.log"
    log.write_text(_gaussian_scan_log([0.70, 1.30]))
    ts_path = tmp_path / "ts_guess.xyz"

    result = await tool.safe_call(TsGuess_input_schema(**{
        "mode": "scan_parse",
        "log_path": str(log),
        "engine": "gaussian",
        "ts_candidate_path": str(ts_path),
    }), mock_session)

    assert result.is_success, result.message
    assert result.candidate_unavailable is True
    assert result.scan_has_internal_peak is True
    assert result.candidate is None
    assert result.ts_candidate_path == ""
    assert result.barrier_kcal is None
    assert not ts_path.exists()
    assert any("NOT derived by equal-split" in v for v in result.verdicts)
    # 剖面仍照常给出（3 点 + 表头）
    assert len(result.profile_table.strip().splitlines()) == 4


@pytest.mark.asyncio
async def test_scan_parse_gaussian_one_block_per_point_uses_peak_block(tmp_path, mock_session, monkeypatch):
    """块数==点数（每点恰一块）：可靠对齐，峰值帧几何照常发出。"""
    monkeypatch.setattr("cclib.io.ccread", lambda *a, **_kw: None)
    tool = _make_tool()
    log = tmp_path / "scan.log"
    log.write_text(_gaussian_scan_log([0.70, 0.90, 1.30]))
    ts_path = tmp_path / "ts_guess.xyz"

    result = await tool.safe_call(TsGuess_input_schema(**{
        "mode": "scan_parse",
        "log_path": str(log),
        "engine": "gaussian",
        "ts_candidate_path": str(ts_path),
    }), mock_session)

    assert result.is_success, result.message
    assert result.candidate_unavailable is False
    assert result.candidate is not None
    assert result.candidate["source"] == "gaussian_log:std_orientation"
    assert result.candidate["scan_index"] == 1
    assert result.barrier_kcal == pytest.approx(6.2751, abs=1e-3)
    content = ts_path.read_text(encoding="utf-8")
    assert "0.900000" in content

# ---------------------------------------------------------------------------
# ORCA 解析缺口回归（改动 1）：NORMAL MODES 位移块 + 重命名 stdout 日志的 IRC 端点
# ---------------------------------------------------------------------------

_ORCA_FREQ_LOG = """\
Program Version 6.1.1  -  RELEASE

VIBRATIONAL FREQUENCIES
-----------------------

   0:       0.00 cm**-1
   1:       0.00 cm**-1
   2:       0.00 cm**-1
   3:       0.00 cm**-1
   4:       0.00 cm**-1
   5:       0.00 cm**-1
   6:    -915.34 cm**-1  ***imaginary mode***
   7:     500.00 cm**-1
   8:    1000.00 cm**-1

------------
NORMAL MODES
------------

These modes are the Cartesian displacements weighted by the diagonal matrix
M(i,i)=1/sqrt(m[i]) where m[i] is the mass of the displaced atom
Thus, these vectors are normalized but *not* orthogonal

                  0          1          2          3          4          5
      0       0.000000   0.000000   0.000000   0.000000   0.000000   0.000000
      1       0.000000   0.000000   0.000000   0.000000   0.000000   0.000000
      2       0.000000   0.000000   0.000000   0.000000   0.000000   0.000000
      3       0.000000   0.000000   0.000000   0.000000   0.000000   0.000000
      4       0.000000   0.000000   0.000000   0.000000   0.000000   0.000000
      5       0.000000   0.000000   0.000000   0.000000   0.000000   0.000000
      6       0.000000   0.000000   0.000000   0.000000   0.000000   0.000000
      7       0.000000   0.000000   0.000000   0.000000   0.000000   0.000000
      8       0.000000   0.000000   0.000000   0.000000   0.000000   0.000000
                  6          7          8
      0       1.000000   0.000000   0.000000
      1       0.000000   0.000000   0.000000
      2       0.000000   0.000000   0.000000
      3       0.000000   0.000000   0.000000
      4       0.000000   0.000000   0.000000
      5       0.000000   0.000000   0.000000
      6      -1.000000   0.000000   0.000000
      7       0.000000   0.000000   0.000000
      8       0.000000   0.000000   0.000000

CARTESIAN COORDINATES (ANGSTROEM)
---------------------------------
  C      0.000000    0.000000    0.000000
  N      0.000000    0.000000    2.000000
  H      0.000000    0.000000    1.000000
"""


@pytest.mark.asyncio
@pytest.mark.parametrize("engine_args", [{}, {"engine": None}, {"engine": "orca"}])
async def test_verify_detects_orca_when_cclib_fails(tmp_path, mock_session, monkeypatch, engine_args):
    def cclib_crash(*_args, **_kwargs):
        raise IndexError("ORCA 6.1 parser failure")

    monkeypatch.setattr("cclib.io.ccread", cclib_crash)
    freq_log = tmp_path / "frequency.log"
    freq_log.write_text("O   R   C   A\n" + _ORCA_FREQ_LOG + "\nORCA TERMINATED NORMALLY\n")
    irc_log = _orca_irc_log_with_sidecars(tmp_path, backward_converged=True)
    result = await _make_tool().safe_call(TsGuess_input_schema(
        mode="verify", freq_log=str(freq_log), irc_log=str(irc_log),
        watch_pairs=[[0, 2]], **engine_args,
    ), mock_session)

    assert result.is_success, result.message
    assert result.n_imag == 1
    assert result.imag_freqs == pytest.approx([-915.34])
    assert result.imag_mode_aligned is True
    assert Path(result.irc_end_a_path).is_file()
    assert Path(result.irc_end_b_path).is_file()


@pytest.mark.asyncio
@pytest.mark.parametrize("text,engine", [
    ("O   R   C   A\n" + _ORCA_FREQ_LOG, "gaussian"),
    (_TS_FREQ_SNIPPET, "orca"),
    (_TS_FREQ_SNIPPET, "xtb"),
], ids=["orca-as-gaussian", "gaussian-as-orca", "gaussian-as-xtb"])
async def test_verify_rejects_explicit_engine_mismatch(tmp_path, mock_session, text, engine):
    freq_log = tmp_path / "frequency.log"
    freq_log.write_text(text)
    result = await _make_tool().safe_call(TsGuess_input_schema(
        mode="verify", freq_log=str(freq_log), engine=engine,
    ), mock_session)
    assert not result.is_success
    assert "engine" in result.message.lower()
    assert "mismatch" in result.message.lower()
    assert result.n_imag is None


@pytest.mark.asyncio
@pytest.mark.parametrize("text", [
    "Frequencies -- -100.0 200.0 300.0\nNormal termination\n",
    "O   R   C   A\nVIBRATIONAL FREQUENCIES\ncorrupt block\n",
    "xtb version 6.7.1\n",
], ids=["unknown", "corrupt-orca", "unsupported-xtb"])
async def test_verify_rejects_unknown_unsupported_or_corrupt_log(tmp_path, mock_session, text):
    freq_log = tmp_path / "frequency.log"
    freq_log.write_text(text)
    result = await _make_tool().safe_call(TsGuess_input_schema(
        mode="verify", freq_log=str(freq_log),
    ), mock_session)
    assert not result.is_success
    assert result.n_imag is None


def test_orca_vibdisps_from_text_parses_normal_modes_block():
    """改动 1a：ORCA NORMAL MODES 位移块可解析，形状与 Gaussian 通道一致。

    版式为「模式号表头 + 3N 行笛卡尔分量」，第 m 列填回第 m 个模式；虚频模式 6
    的 C1(+x) 与 H3(-x) 反向位移必须落在 disps[6]。
    """
    from cloudra.tools.core import orca_frames

    vd = orca_frames.vibdisps_from_text(_ORCA_FREQ_LOG, 9, 3)
    assert vd is not None
    assert vd.shape == (9, 3, 3)
    # 模式 6：原子 0 (C) 沿 +x、原子 2 (H) 沿 -x
    assert vd[6, 0, 0] == pytest.approx(1.0)
    assert vd[6, 2, 0] == pytest.approx(-1.0)
    assert vd[6, 1].tolist() == pytest.approx([0.0, 0.0, 0.0])
    # 频率数与 3N 不一致时拒答（保持「缺位移」语义）
    assert orca_frames.vibdisps_from_text(_ORCA_FREQ_LOG, 8, 3) is None


def test_parse_freq_log_orca_text_vibdisps_and_orientation(tmp_path, monkeypatch):
    """改动 1a：cclib 对 ORCA 6.x 崩溃时，频率/位移/末帧几何全部走文本回退，
    且虚频模式参与方向判定（watch_pairs 对齐 / 不对齐）。"""
    import cclib

    from cloudra.tools.Chemtool.ts_guess import (
        _assess_imag_mode_alignment,
        _parse_freq_log,
    )

    def _boom(*_a, **_k):
        raise IndexError("simulated cclib ORCA 6.x crash")

    monkeypatch.setattr(cclib.io, "ccread", _boom)
    log = tmp_path / "calc-10.out.log"
    log.write_text('O   R   C   A\n' + _ORCA_FREQ_LOG, encoding="utf-8")

    freq = _parse_freq_log(str(log), "orca")
    assert len(freq["vibfreqs"]) == 9
    assert freq["vibdisps"] is not None and freq["vibdisps"].shape == (9, 3, 3)
    assert freq["symbols"] == ["C", "N", "H"]
    assert freq["positions"] is not None

    aligned = _assess_imag_mode_alignment(
        freq["vibfreqs"], freq["vibdisps"], [[1, 3]],
        symbols=freq["symbols"], positions=freq["positions"], charge=0,
    )
    assert aligned["status"] == "aligned"
    assert aligned["aligned"] is True

    # 监视对不覆盖主导位移对 (C1,H3) → 不判对齐（方向判定确实吃到了位移块）
    wrong = _assess_imag_mode_alignment(freq["vibfreqs"], freq["vibdisps"], [[2, 3]])
    assert wrong["status"] == "misaligned"


def _renamed_orca_irc_log(tmp_path, name):
    """合成被 harness 重命名的 stdout 日志：无 NAME 输入回显、stem 不是 ORCA 作业名。"""
    log = tmp_path / name
    log.write_text(
        "* FORWARD IRC *\n"
        " 0 -100.123694 -0.987880 0.009347 0.001949\n"
        "THE IRC HAS CONVERGED\n"
        "* BACKWARD IRC *\n"
        " 0 -100.123694 -0.987880 0.009347 0.001949\n"
        "THE IRC HAS CONVERGED\n",
        encoding="utf-8",
    )
    return log


_IRC_ENDPOINT_XYZ = "3\nsidecar\nC 0.0 0.0 0.0\nN 0.0 0.0 1.2\nH 0.0 0.0 2.2\n"


def test_orca_irc_endpoints_use_native_name_for_renamed_log(tmp_path):
    """A renamed stdout log must declare the native job name to bind sidecars."""
    from cloudra.tools.core import orca_frames

    job_dir = tmp_path / "job"
    job_dir.mkdir()
    log = _renamed_orca_irc_log(job_dir, "calc-99.out.log")
    log.write_text('NAME = realjob.inp\n' + log.read_text(), encoding='utf-8')
    (job_dir / "realjob_IRC_F.xyz").write_text(_IRC_ENDPOINT_XYZ, encoding="utf-8")
    (job_dir / "realjob_IRC_B.xyz").write_text(_IRC_ENDPOINT_XYZ, encoding="utf-8")

    endpoints = orca_frames.extract_irc_endpoints(str(log))
    assert endpoints["forward"]["availability"] == "available"
    assert endpoints["backward"]["availability"] == "available"
    assert endpoints["forward"]["origin"] == "final_endpoint_file"
    assert endpoints["backward"]["origin"] == "final_endpoint_file"
    assert orca_frames.read_endpoint_geometry(endpoints["forward"]) is not None
    assert orca_frames.read_endpoint_geometry(endpoints["backward"]) is not None


@pytest.mark.parametrize('prefixes', [('aaa',), ('aaa', 'bbb')])
def test_orca_irc_endpoints_refuse_unbound_sidecars(tmp_path, prefixes):
    """Even a unique unrelated sidecar is not evidence of this renamed job."""
    from cloudra.tools.core import orca_frames

    job_dir = tmp_path / "job"
    job_dir.mkdir()
    log = _renamed_orca_irc_log(job_dir, "calc-99.out.log")
    for prefix in prefixes:
        (job_dir / f"{prefix}_IRC_F.xyz").write_text(_IRC_ENDPOINT_XYZ, encoding="utf-8")
        (job_dir / f"{prefix}_IRC_B.xyz").write_text(_IRC_ENDPOINT_XYZ, encoding="utf-8")

    endpoints = orca_frames.extract_irc_endpoints(str(log))
    assert endpoints["forward"]["availability"] == "unavailable"
    assert endpoints["backward"]["availability"] == "unavailable"


@pytest.mark.asyncio
@pytest.mark.usefixtures("rdkit_chemistry")
async def test_verify_strict_non_pass_appends_endpoint_optimization_remedy(tmp_path, mock_session):
    """不通过（材料不足 / 方向不符）时 checks 必须带「补做端点优化」的可操作提示，
    且 verdict 语义（fail / inconclusive 前缀）不变（只加文本，不改判据/阈值）。"""
    from cloudra.tools.Chemtool.ts_guess import _IRC_TRUNCATION_REMEDY

    tool = _make_tool()
    freq_log = tmp_path / "ts_freq_with_geometry.log"
    freq_log.write_text(_TS_FREQ_WITH_GEOMETRY)

    # 分支 A：缺端点优化中间体
    res_missing = await tool.safe_call(TsGuess_input_schema(**{
        "mode": "verify",
        "strict": True,
        "freq_log": str(freq_log),
        "irc_log": str(IRC_LOG),
        "output_dir": str(tmp_path / "remedy_missing"),
    }), mock_session)
    assert res_missing.is_success, res_missing.message
    assert res_missing.verdict.startswith("inconclusive")
    assert any(_IRC_TRUNCATION_REMEDY in c for c in res_missing.checks)
    assert _IRC_TRUNCATION_REMEDY in res_missing.verdict

    # 分支 B：实际优化结果与声明的端点身份不符。
    logs = _endpoint_optimization_logs(tmp_path)
    res_fail = await tool.safe_call(TsGuess_input_schema(**{
        "mode": "verify",
        "strict": True,
        "freq_log": str(freq_log),
        "irc_log": str(IRC_LOG),
        "reactant_text": _HCN_XYZ,
        "product_text": _HCN_XYZ,
        "reactant_logs": logs["reactant"],
        "product_logs": logs["product"],
        "watch_pairs": [[1, 3], [2, 3]],
        "output_dir": str(tmp_path / "remedy_fail"),
    }), mock_session)
    assert res_fail.is_success, res_fail.message
    assert res_fail.verdict.startswith("fail")
    assert any(_IRC_TRUNCATION_REMEDY in c for c in res_fail.checks)
    assert _IRC_TRUNCATION_REMEDY in res_fail.verdict


@pytest.mark.asyncio
async def test_ts_guess_unknown_mode_fuzzy_suggestion(mock_session):
    tool = _make_tool()
    res = await tool.tool_call(TsGuess_input_schema.model_construct(mode="interp"), mock_session)
    assert res.is_success is False
    assert "Did you mean 'interpolate'?" in res.message
    assert "Allowed modes:" in res.message

