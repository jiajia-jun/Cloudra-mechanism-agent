import os

import pytest

pytest.importorskip("rdkit", reason="未安装 chem 额外依赖（rdkit）")
pytest.importorskip("chemcoord", reason="未安装 chem 额外依赖（chemcoord）")
pytest.importorskip("ase", reason="未安装 chem 额外依赖（ase）")

from cloudra.tools.Chemtool.internal_coordinates import (
    InternalCoordinates,
    InternalCoordinates_input_schema,
)

WATER_XYZ = """3
water
O   0.000000   0.000000   0.000000
H   0.957000   0.000000   0.000000
H  -0.239000   0.927000   0.000000
"""

# MMFF 优化的丁烷（中心 C2-C3 扭转角约 -65°，gauche）
BUTANE_XYZ = """14
butane
C     -1.575217    0.469467    0.027091
C     -0.556942   -0.314570   -0.786290
C      0.648571   -0.778287    0.031876
C      1.505112    0.366682    0.550114
H     -1.162517    1.420101    0.377286
H     -1.909718   -0.104792    0.896806
H     -2.452692    0.695521   -0.587298
H     -0.220952    0.294308   -1.633701
H     -1.052250   -1.197697   -1.207185
H      0.313063   -1.392923    0.875311
H      1.271845   -1.421416   -0.600824
H      2.396656   -0.027206    1.048649
H      0.961547    0.976856    1.277361
H      1.833495    1.013955   -0.269196
"""

# 假过渡态：甲醇 C-O 拉长到 1.75 Å（ref 1.43 → elongated），
# 额外 H7 在 1.70 Å 处接近 O5（> O-H ref 0.96，< 0.75×vdW 2.04 → forming_candidate）
FAKE_TS_XYZ = """7
fake ts
C   0.000000   0.000000   0.000000
H  -0.363000   1.028000   0.000000
H  -0.363000  -0.514000   0.890000
H  -0.363000  -0.514000  -0.890000
O   1.750000   0.000000   0.000000
H   2.070000   0.905000   0.000000
H   3.450000   0.000000   0.000000
"""

# 椅式环己烷（Cremer–Pople θ ≈ 0）
CYCLOHEXANE_XYZ = """18
cyclohexane chair
C      1.413555   -0.201151   -0.371713
C      0.550931   -1.364158    0.110984
C     -0.927102   -1.131737   -0.190850
C     -1.413555    0.201151    0.371714
C     -0.550931    1.364158   -0.110985
C      0.927102    1.131737    0.190850
H      2.455758   -0.367658   -0.076984
H      1.393360   -0.163032   -1.467863
H      0.685996   -1.493806    1.191889
H      0.883316   -2.292926   -0.366181
H     -1.084165   -1.148032   -1.276424
H     -1.522700   -1.949393    0.230431
H     -1.393354    0.163033    1.467864
H     -2.455758    0.367658    0.076988
H     -0.685998    1.493804   -1.191889
H     -0.883317    2.292927    0.366177
H      1.084166    1.148033    1.276425
H      1.522699    1.949393   -0.230431
"""

# 水二聚体：O1-H2···O4 氢键（H2···O4 = 1.893 Å → forming_candidate）
WATER_DIMER_XYZ = """6
water dimer
O   0.000000   0.000000   0.000000
H   0.957000   0.000000   0.000000
H  -0.239000   0.927000   0.000000
O   2.850000   0.000000   0.000000
H   3.807000   0.000000   0.000000
H   2.611000   0.927000   0.000000
"""


def _parse_xyz_positions(xyz_text: str):
    """返回 [(symbol, (x, y, z)), ...]"""
    lines = [ln for ln in xyz_text.splitlines() if ln.strip()]
    out = []
    for ln in lines[2:]:
        tok = ln.split()
        out.append((tok[0], tuple(float(v) for v in tok[1:4])))
    return out


@pytest.mark.asyncio
async def test_analyze_water_report_sections(mock_session, tmp_path):
    """水分子：报告含全部分节，zmat 文件生成，默认路径规则正确。"""
    xyz_file = tmp_path / "water.xyz"
    xyz_file.write_text(WATER_XYZ)

    tool = InternalCoordinates()
    result = await tool.safe_call(
        InternalCoordinates_input_schema(mode="analyze", input_path=str(xyz_file)),
        mock_session,
    )
    assert result.is_success is True
    for section in ("== Summary ==", "== Stereochemistry ==", "== Rings ==",
                    "== Rotatable Dihedrals ==", "== Abnormal Bonds ==",
                    "== Abnormal Angles ==", "== Equivalent Atoms ==", "== Notes =="):
        assert section in result.report
    assert "H2O" in result.report
    # 默认 zmat 路径：input_path 同目录 <stem>.zmat
    assert result.zmat_path == str(tmp_path / "water.zmat")
    assert os.path.isfile(result.zmat_path)
    assert result.zmat_lines > 0
    # 正常结构不应有键异常
    assert all(a["status"] not in ("elongated", "compressed", "breaking_suspect")
               for a in result.anomalies)


@pytest.mark.asyncio
async def test_analyze_butane_rotatable_and_equivalence(mock_session, tmp_path):
    """丁烷：可旋转二面角分类（gauche/synclinal），等价原子组，反应分节存在。"""
    tool = InternalCoordinates()
    result = await tool.safe_call(
        InternalCoordinates_input_schema(
            mode="analyze", input_text=BUTANE_XYZ,
            zmat_path=str(tmp_path / "butane.zmat"),
        ),
        mock_session,
    )
    assert result.is_success is True
    assert "== Rotatable Dihedrals ==" in result.report
    assert "gauche/synclinal" in result.report
    # 等价原子：两个端甲基碳、两个亚甲基碳各自等价
    assert "== Equivalent Atoms ==" in result.report
    eq_section = result.report.split("== Equivalent Atoms ==")[1].split("==")[0]
    assert "C1" in eq_section and "C4" in eq_section


@pytest.mark.asyncio
async def test_analyze_fake_ts_anomalies(mock_session, tmp_path):
    """假 TS：拉长 C-O 判为 elongated，接近的 H···O 判为 forming_candidate，反应中心块生效。"""
    tool = InternalCoordinates()
    result = await tool.safe_call(
        InternalCoordinates_input_schema(
            mode="analyze", input_text=FAKE_TS_XYZ,
            reactive_atoms=[5], watch_pairs=[[5, 7]],
            zmat_path=str(tmp_path / "ts.zmat"),
        ),
        mock_session,
    )
    assert result.is_success is True

    statuses = {(tuple(sorted(a["atoms"])), a["status"]) for a in result.anomalies}
    assert any(a["status"] == "elongated" and set(a["atoms"]) == {"C1", "O5"}
               for a in result.anomalies), statuses
    assert any(a["status"] == "forming_candidate" and set(a["atoms"]) == {"O5", "H7"}
               for a in result.anomalies), statuses

    assert "== Reactive Center ==" in result.report
    assert "O5" in result.report.split("== Reactive Center ==")[1]
    assert "形成中" in result.report


@pytest.mark.asyncio
async def test_analyze_cyclohexane_ring(mock_session, tmp_path):
    """椅式环己烷：检测到 6 元环并给出 Cremer–Pople 椅式提示。"""
    tool = InternalCoordinates()
    result = await tool.safe_call(
        InternalCoordinates_input_schema(
            mode="analyze", input_text=CYCLOHEXANE_XYZ,
            zmat_path=str(tmp_path / "cyclohexane.zmat"),
        ),
        mock_session,
    )
    assert result.is_success is True
    assert "== Rings ==" in result.report
    rings_section = result.report.split("== Rings ==")[1].split("==")[0]
    assert "6 元环" in rings_section
    assert "CP:" in rings_section
    assert "椅式" in rings_section


@pytest.mark.asyncio
async def test_analyze_water_dimer_fragments(mock_session, tmp_path):
    """双分子碎片体系：不崩溃，识别 2 个碎片与氢键 forming_candidate。"""
    tool = InternalCoordinates()
    result = await tool.safe_call(
        InternalCoordinates_input_schema(
            mode="analyze", input_text=WATER_DIMER_XYZ,
            zmat_path=str(tmp_path / "dimer.zmat"),
        ),
        mock_session,
    )
    assert result.is_success is True
    assert "碎片数: 2" in result.report
    assert any(a["status"] == "forming_candidate" and set(a["atoms"]) == {"H2", "O4"}
               for a in result.anomalies)
    # 多碎片 zmat 也能生成并可 round-trip 还原坐标
    import numpy as np

    assert os.path.isfile(result.zmat_path)
    rt = await tool.safe_call(
        InternalCoordinates_input_schema(
            mode="zmatrix_to_cartesian", zmatrix_path=result.zmat_path,
        ),
        mock_session,
    )
    assert rt.is_success is True
    orig = _parse_xyz_positions(WATER_DIMER_XYZ)
    back = _parse_xyz_positions(rt.xyz_text)
    p_orig = np.array([p for _, p in orig])
    p_back = np.array([p for _, p in back])
    rmsd = float(np.sqrt(((p_orig - p_back) ** 2).sum(axis=1).mean()))
    assert rmsd < 0.05


@pytest.mark.asyncio
async def test_roundtrip_zmatrix_to_cartesian(mock_session, tmp_path):
    """analyze → zmatrix_to_cartesian round-trip：坐标 RMSD < 0.05 Å。"""
    import numpy as np

    tool = InternalCoordinates()
    analyze_result = await tool.safe_call(
        InternalCoordinates_input_schema(
            mode="analyze", input_text=BUTANE_XYZ,
            zmat_path=str(tmp_path / "butane.zmat"),
        ),
        mock_session,
    )
    assert analyze_result.is_success is True

    rt_result = await tool.safe_call(
        InternalCoordinates_input_schema(
            mode="zmatrix_to_cartesian",
            zmatrix_path=analyze_result.zmat_path,
            output_path=str(tmp_path / "butane_rt.xyz"),
        ),
        mock_session,
    )
    assert rt_result.is_success is True
    assert os.path.isfile(str(tmp_path / "butane_rt.xyz"))

    orig = _parse_xyz_positions(BUTANE_XYZ)
    back = _parse_xyz_positions(rt_result.xyz_text)
    assert len(orig) == len(back)
    assert [s for s, _ in orig] == [s for s, _ in back]
    p_orig = np.array([p for _, p in orig])
    p_back = np.array([p for _, p in back])
    rmsd = float(np.sqrt(((p_orig - p_back) ** 2).sum(axis=1).mean()))
    assert rmsd < 0.05


@pytest.mark.asyncio
async def test_zmatrix_text_input(mock_session):
    """zmatrix_text 直接传文本也能还原坐标。"""
    zmatrix_text = """# Z-matrix test
  1  O1    | origin   r=0.0000 | e_z    a=0.00 | e_x    d=0.00
  2  H2    | O1       r=0.9570 | e_z    a=90.00 | e_x    d=90.00
  3  H3    | O1       r=0.9570 | H2     a=104.50 | e_x    d=0.00
"""
    tool = InternalCoordinates()
    result = await tool.safe_call(
        InternalCoordinates_input_schema(
            mode="zmatrix_to_cartesian", zmatrix_text=zmatrix_text,
        ),
        mock_session,
    )
    assert result.is_success is True
    atoms = _parse_xyz_positions(result.xyz_text)
    assert len(atoms) == 3
    import numpy as np

    pos = np.array([p for _, p in atoms])
    # O-H 键长应约 0.957
    assert abs(np.linalg.norm(pos[1] - pos[0]) - 0.957) < 1e-3
    assert abs(np.linalg.norm(pos[2] - pos[0]) - 0.957) < 1e-3
