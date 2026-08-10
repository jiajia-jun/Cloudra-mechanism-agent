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
