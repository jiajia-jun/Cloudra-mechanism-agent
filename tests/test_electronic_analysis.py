import os
import shutil

import pytest

from cloudra.tools.Chemtool.electronic_analysis import ElectronicAnalysis, ElectronicAnalysis_input_schema

WATER_XYZ = """3
water
O  0.000000  0.000000  0.000000
H  0.000000  0.758602  0.504284
H  0.000000  0.758602 -0.504284
"""


@pytest.fixture
def tool():
    pytest.importorskip("pyscf", reason="未安装 chem 额外依赖（pyscf）")
    return ElectronicAnalysis()


@pytest.mark.asyncio
async def test_water_hf_sto3g(tool, mock_session, tmp_path):
    """水分子 HF/sto-3g 全分析：能量、能隙、电荷、Mayer 键级、IBO Lewis 图像。"""
    out_dir = str(tmp_path / "ea_out")
    result = await tool.safe_call(
        ElectronicAnalysis_input_schema(
            input_text=WATER_XYZ, method="hf", basis="sto-3g", output_dir=out_dir,
        ),
        mock_session,
    )
    assert result.is_success is True

    # 数值摘要
    assert result.summary["total_energy_eh"] < -70.0  # HF/sto-3g 水约 -74.88 Eh
    assert result.summary["gap_ev"] > 0.0
    assert result.summary["dipole_debye"] > 1.0
    assert result.summary["scf_converged"] is True

    report = result.report
    for section in ("Summary", "Frontier Orbitals", "Charges", "Bond Orders", "IBO Lewis Picture", "Notes"):
        assert section in report

    # 氧电荷为负、氢为正
    charges_section = report.split("=== Charges")[1].split("=== Bond Orders")[0]
    o_line = next(ln for ln in charges_section.splitlines() if ln.strip().startswith("O1"))
    assert float(o_line.split()[-1]) < 0.0

    # Mayer 键级：两条 O-H 键，BO 接近 1
    assert report.count("O1-H") >= 2

    # IBO Lewis 图像：2 个 O-H 键 + 2 对氧孤对（允许分类文本匹配，断言放宽）
    ibo_section = report.split("=== IBO Lewis Picture ===")[1].split("=== Notes ===")[0]
    lp_lines = [ln for ln in ibo_section.splitlines() if ln.strip().startswith("LP on O1")]
    assert len(lp_lines) == 2
    bond_lines = [ln for ln in ibo_section.splitlines()
                  if ln.strip().startswith("O1-H") and "%" in ln]
    assert len(bond_lines) == 2

    # 落盘文件
    assert result.molden_path and os.path.isfile(result.molden_path)
    assert result.log_path and os.path.isfile(result.log_path)


@pytest.mark.asyncio
async def test_reactive_atoms_focus(tool, mock_session):
    """reactive_atoms 聚焦输出不应报错，并在电荷节给出聚焦列表。"""
    result = await tool.safe_call(
        ElectronicAnalysis_input_schema(
            input_text=WATER_XYZ, method="hf", basis="sto-3g", reactive_atoms=[1],
        ),
        mock_session,
    )
    assert result.is_success is True
    assert "Reactive atoms and bonded neighbors" in result.report


@pytest.mark.asyncio
async def test_missing_pyscf_message(mock_session, monkeypatch):
    """缺 PySCF 时返回安装提示而不是抛异常。"""
    import cloudra.tools.Chemtool.electronic_analysis as mod

    monkeypatch.setattr(mod, "_PYSCF_AVAILABLE", False)
    tool = ElectronicAnalysis()
    result = await tool.safe_call(
        ElectronicAnalysis_input_schema(input_text=WATER_XYZ), mock_session,
    )
    assert result.is_success is False
    assert "pip install pyscf" in result.message or "cloudra[chem]" in result.message


@pytest.mark.asyncio
async def test_xtb_backend(mock_session, tmp_path):
    """xTB 后端集成测试：环境无 xtb 时跳过。"""
    if shutil.which("xtb") is None:
        pytest.skip("未安装 xtb，跳过 xTB 后端集成测试")
    tool = ElectronicAnalysis()
    result = await tool.safe_call(
        ElectronicAnalysis_input_schema(
            input_text=WATER_XYZ, backend="xtb", output_dir=str(tmp_path / "xtb_out"),
        ),
        mock_session,
    )
    assert result.is_success is True
    assert result.summary["total_energy_eh"] < 0.0
    assert "gap_ev" in result.summary
    assert "Charges" in result.report


def test_tool_metadata():
    tool = ElectronicAnalysis()
    assert tool.tool_id == "t-44"
    assert tool.tool_name == "electronic_analysis"
    assert tool.is_write() is True


CH3_RADICAL_XYZ = """4
methyl radical
C  0.000000  0.000000  0.000000
H  1.090000  0.000000  0.000000
H -0.363000  1.027000  0.000000
H -0.363000 -1.027000  0.000000
"""

O2_TRIPLET_XYZ = """2
oxygen triplet
O  0.000000  0.000000  0.000000
O  0.000000  0.000000  1.210000
"""


@pytest.mark.asyncio
async def test_methyl_radical_uhf(tool, mock_session):
    """甲基自由基（spin=2）：非限制性分支、自旋布居定位自由基中心、<S^2> 检查。"""
    result = await tool.safe_call(
        ElectronicAnalysis_input_schema(
            input_text=CH3_RADICAL_XYZ, spin=2, method="hf", basis="sto-3g",
        ),
        mock_session,
    )
    assert result.is_success is True

    # UHF 分支与自旋信息
    assert "UHF" in result.report
    assert "<S^2>" in result.report
    assert abs(result.summary["spin_squared"] - 0.75) < 0.1  # 双重态理想值 0.75

    # 自旋布居：碳为自由基中心
    spin = result.summary["spin_population"]
    assert spin["C1"] > 0.3
    assert abs(sum(spin.values()) - 1.0) < 0.05  # α-β 电子数为 1
    assert "Spin population top-3" in result.report

    # 键级：C-H 应接近单键
    bo_section = result.report.split("=== Bond Orders")[1].split("=== IBO")[0]
    ch_lines = [ln for ln in bo_section.splitlines() if "C1" in ln and "BO=" in ln]
    assert ch_lines and all(0.6 < float(ln.split("BO=")[1].split()[0]) < 1.4 for ln in ch_lines)

    # IBO 按自旋通道标记
    assert "(α)" in result.report and "(β)" in result.report


@pytest.mark.asyncio
async def test_o2_triplet_uhf(tool, mock_session):
    """O2 三重态（spin=3）：经典开壳层体系，自旋布居两氧均分。"""
    result = await tool.safe_call(
        ElectronicAnalysis_input_schema(
            input_text=O2_TRIPLET_XYZ, spin=3, method="hf", basis="sto-3g",
        ),
        mock_session,
    )
    assert result.is_success is True
    assert abs(result.summary["spin_squared"] - 2.0) < 0.15  # 三重态理想值 2.0
    spin = result.summary["spin_population"]
    assert spin["O1"] > 0.3 and spin["O2"] > 0.3
    assert abs(sum(spin.values()) - 2.0) < 0.05  # 两个未成对电子


@pytest.mark.asyncio
async def test_o2_triplet_mayer_bond_order_includes_spin_term(tool, mock_session):
    """O2 三重态 b3lyp/def2-svp：开壳层 Mayer 键级必须叠加自旋密度项。

    缺 Ps 项时 O-O BO≈1.37（被误判为 TS-like 部分键）；补全后 BO≈1.85（正确双键）。
    """
    result = await tool.safe_call(
        ElectronicAnalysis_input_schema(
            input_text=O2_TRIPLET_XYZ, spin=3, method="b3lyp", basis="def2-svp",
        ),
        mock_session,
    )
    assert result.is_success is True

    bo_section = result.report.split("=== Bond Orders")[1].split("=== IBO")[0]
    oo_lines = [ln for ln in bo_section.splitlines() if "O1" in ln and "O2" in ln and "BO=" in ln]
    assert oo_lines
    bo = float(oo_lines[0].split("BO=")[1].split()[0])
    assert 1.7 < bo < 2.0
    assert "partial bond" not in oo_lines[0]
    assert "Partial bond (TS-like) detected" not in result.report


@pytest.mark.asyncio
async def test_closed_shell_mayer_bo_regression_water(tool, mock_session):
    """闭壳层回归：水 O-H Mayer 键级仍接近 1，开壳层公式扩展不影响闭壳层路径。"""
    result = await tool.safe_call(
        ElectronicAnalysis_input_schema(input_text=WATER_XYZ, method="hf", basis="sto-3g"),
        mock_session,
    )
    assert result.is_success is True
    bo_section = result.report.split("=== Bond Orders")[1].split("=== IBO")[0]
    oh_lines = [ln for ln in bo_section.splitlines() if "O1" in ln and "BO=" in ln]
    assert len(oh_lines) == 2
    for ln in oh_lines:
        bo = float(ln.split("BO=")[1].split()[0])
        assert 0.8 < bo < 1.2
        assert "partial bond" not in ln


def test_core_orbital_count_heavy_elements(tool):
    """核芯轨道计数按周期表电子排布：Kr→9、Xe→18、Rn→27、Og→43（旧实现对 Z>36 封顶 9）。"""
    cases = {
        "H": 0, "He": 0,
        "Li": 1, "Ne": 1,
        "Na": 5, "Ar": 5,
        "K": 9, "Kr": 9,
        "Rb": 18, "Xe": 18,
        "Cs": 27, "Rn": 27,
        "Fr": 43, "Og": 43,
    }
    for symbol, expected in cases.items():
        assert ElectronicAnalysis._core_orbital_count(symbol) == expected, symbol


@pytest.mark.asyncio
async def test_closed_shell_unaffected_by_openshell_changes(tool, mock_session):
    """闭壳层报告不出现自旋相关字段，且默认启用密度拟合不改变结论。"""
    result = await tool.safe_call(
        ElectronicAnalysis_input_schema(input_text=WATER_XYZ, method="hf", basis="sto-3g"),
        mock_session,
    )
    assert result.is_success is True
    assert "spin_squared" not in result.summary
    assert "UHF" not in result.report
    assert result.summary["total_energy_eh"] < -70.0


# ---------------------------------------------------------------------------
# 共享判据/原语（无需 PySCF 的纯函数测试）
# ---------------------------------------------------------------------------


def test_bond_pairs_use_shared_connectivity_factor():
    """_bond_pairs 必须引用 internal_coordinates 的 DISTANCE_CONNECTIVITY_FACTOR
    （1.25），不再自带 1.3 字面量：H-H 键长 0.79 Å 落 (1.25, 1.3]×(ri+rj) 区间，
    旧判据成键、共享判据不成键——同一分子两处结论必须一致。"""
    from cloudra.tools.Chemtool.internal_coordinates import DISTANCE_CONNECTIVITY_FACTOR

    assert DISTANCE_CONNECTIVITY_FACTOR == 1.25
    # H 共价半径 0.31：1.25×(0.31+0.31)=0.775 < 0.79 < 0.806=1.3×(0.31+0.31)
    near = ElectronicAnalysis._bond_pairs(["H", "H"], [[0.0, 0.0, 0.0], [0.0, 0.0, 0.79]])
    assert near == []
    bonded = ElectronicAnalysis._bond_pairs(["H", "H"], [[0.0, 0.0, 0.0], [0.0, 0.0, 0.77]])
    assert len(bonded) == 1


@pytest.mark.asyncio
async def test_open_shell_report_lists_alpha_beta_frontier_orbitals(tool, mock_session):
    """开壳层（甲基自由基 UHF）：Frontier Orbitals 节必须显式给出 α/β 两套
    HOMO/LUMO（SOMO 语义），summary 带 per-spin 通道与 gap_status。"""
    result = await tool.safe_call(
        ElectronicAnalysis_input_schema(
            input_text=CH3_RADICAL_XYZ, spin=2, method="hf", basis="sto-3g",
        ),
        mock_session,
    )
    assert result.is_success is True

    fo_section = result.report.split("=== Frontier Orbitals ===")[1].split("=== Charges")[0]
    assert "α-HOMO (SOMO)" in fo_section
    assert "α-LUMO" in fo_section
    assert "β-HOMO (SOMO)" in fo_section
    assert "β-LUMO" in fo_section

    summary = result.summary
    assert summary["alpha_homo_eh"] is not None
    assert summary["beta_homo_eh"] is not None
    assert "gap_status" in summary
    if summary["gap_status"] == "undecidable_spin_crossover":
        assert summary["gap_ev"] is None
        assert "undecidable" in fo_section
    else:
        assert summary["gap_ev"] is not None and summary["gap_ev"] >= 0.0
