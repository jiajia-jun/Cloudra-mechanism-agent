import os
import shutil

import pytest

import cloudra.tools.Chemtool.conformer_search as conformer_mod
from cloudra.tools.Chemtool.conformer_search import ConformerSearch, ConformerSearch_input_schema

ETHANOL_XYZ = """9
ethanol
C      0.0000    0.0000    0.0000
C      1.4700    0.0000    0.0000
O      2.1000    1.2000    0.0000
H     -0.3800   -1.0200    0.0000
H     -0.3800    0.5100   -0.8800
H     -0.3800    0.5100    0.8800
H      1.8500   -0.5100    0.8800
H      1.8500   -0.5100   -0.8800
H      3.0500    1.1000    0.0000
"""


@pytest.fixture
def tool():
    pytest.importorskip("rdkit", reason="未安装 chem 额外依赖（rdkit）")
    return ConformerSearch()


def test_energy_window_keeps_lowest_energy_reactive_candidate():
    """全局最低能 reactive conformer 即使落在普通能窗外，也不能被预筛选抹掉。"""
    selected = conformer_mod._select_energy_window_candidates(
        candidate_ids=[0, 1, 2],
        rel_energies={0: 0.0, 1: 7.0, 2: 9.0},
        passes_filters={0: False, 1: True, 2: True},
        energy_window_kcal=6.0,
        preserve_reactive=True,
    )

    assert selected == [0, 1]


def test_cluster_keeps_ordinary_and_lowest_energy_reactive_representatives():
    """混合簇保留最低能代表；若它不反应，再额外保留簇内最低能 reactive 成员。"""
    selected = conformer_mod._select_cluster_representatives(
        clusters=[[0, 1, 2], [3]],
        rel_energies={0: 0.0, 1: 0.8, 2: 1.2, 3: 2.0},
        passes_filters={0: False, 1: True, 2: True, 3: False},
        preserve_reactive=True,
    )

    assert selected == [0, 1, 3]


def test_cluster_does_not_duplicate_reactive_lowest_energy_representative():
    selected = conformer_mod._select_cluster_representatives(
        clusters=[[0, 1], [2]],
        rel_energies={0: 0.0, 1: 0.8, 2: 2.0},
        passes_filters={0: True, 1: True, 2: False},
        preserve_reactive=True,
    )

    assert selected == [0, 2]


@pytest.mark.asyncio
async def test_butane_smiles_ensemble(tool, mock_session, tmp_path):
    """丁烷构象搜索：应得到 anti/gauche 至少 2 个聚类，anti（最低能）布居占优，Boltzmann 合计约 100%。"""
    out_dir = str(tmp_path / "butane_confs")
    result = await tool.safe_call(
        ConformerSearch_input_schema(smiles="CCCC", num_confs=50, output_dir=out_dir),
        mock_session,
    )
    assert result.is_success is True
    assert result.counts["generated"] > 0
    assert result.counts["clusters"] >= 2

    # 按能量排序后 conf0 即 anti，其 Boltzmann 布居应显著占优（MMFF 下 anti/gauche 差约 0.8 kcal/mol）
    assert result.conformers[0]["conf_id"] == 0
    assert result.conformers[0]["rel_energy_kcal"] == 0.0
    assert result.conformers[0]["boltzmann_pct"] > 50.0
    assert result.conformers[1]["rel_energy_kcal"] > 0.0

    total_pct = sum(c["boltzmann_pct"] for c in result.conformers)
    assert abs(total_pct - 100.0) < 1.0

    # 输出文件存在且不含坐标进上下文（table 中只有数值列）
    assert result.ensemble_path.endswith("confs.sdf")
    assert os.path.isfile(result.ensemble_path)
    assert os.path.isfile(os.path.join(out_dir, "confs.xyz"))
    assert "conf_id" in result.table and "Boltzmann" in result.table


@pytest.mark.asyncio
async def test_distance_filters(tool, mock_session, tmp_path):
    """反应距离过滤：丁烷 C1-C4 距离区间应只让 anti（~3.9 Å）通过，gauche（~3.0 Å）被滤掉。"""
    result = await tool.safe_call(
        ConformerSearch_input_schema(
            smiles="CCCC",
            num_confs=50,
            output_dir=str(tmp_path / "butane_filt"),
            distance_filters=[{"atoms": [1, 4], "min_ang": 3.5, "max_ang": 4.5}],
        ),
        mock_session,
    )
    assert result.is_success is True
    passing = [c for c in result.conformers if c["passes_filters"]]
    failing = [c for c in result.conformers if not c["passes_filters"]]
    assert result.counts["passing_filters"] == len(passing)
    assert len(passing) >= 1 and len(failing) >= 1
    # 通过过滤的是最低能（anti）构象
    assert passing[0]["conf_id"] == 0
    assert "reactive conformer" in result.message


@pytest.mark.asyncio
async def test_xyz_input_path(tool, mock_session, tmp_path):
    """xyz 文件输入：rdDetermineBonds 推断键级后正常搜索，默认输出目录为 <stem>_confs/。"""
    xyz_file = tmp_path / "ethanol.xyz"
    xyz_file.write_text(ETHANOL_XYZ)
    result = await tool.safe_call(
        ConformerSearch_input_schema(input_path=str(xyz_file), num_confs=20),
        mock_session,
    )
    assert result.is_success is True
    assert result.counts["clusters"] >= 1
    expected_dir = tmp_path / "ethanol_confs"
    assert os.path.isfile(str(expected_dir / "confs.sdf"))
    assert os.path.isfile(str(expected_dir / "confs.xyz"))


@pytest.mark.asyncio
async def test_missing_rdkit_message(mock_session, monkeypatch):
    """缺 RDKit 时返回安装提示而不是抛异常。"""
    import cloudra.tools.Chemtool.conformer_search as mod

    monkeypatch.setattr(mod, "_RDKIT_AVAILABLE", False)
    tool = ConformerSearch()
    result = await tool.safe_call(ConformerSearch_input_schema(smiles="CCCC"), mock_session)
    assert result.is_success is False
    assert "cloudra[chem]" in result.message


@pytest.mark.asyncio
async def test_crest_backend(mock_session, tmp_path):
    """CREST 后端集成测试：环境无 crest 时跳过。"""
    if shutil.which("crest") is None:
        pytest.skip("未安装 crest，跳过 CREST 后端集成测试")
    tool = ConformerSearch()
    result = await tool.safe_call(
        ConformerSearch_input_schema(
            smiles="CCCC", backend="crest", output_dir=str(tmp_path / "crest_out"), timeout=600,
        ),
        mock_session,
    )
    assert result.is_success is True
    assert result.counts["clusters"] >= 1
    assert result.ensemble_path.endswith("confs.xyz")
    assert os.path.isfile(result.ensemble_path)


def test_tool_metadata():
    tool = ConformerSearch()
    assert tool.tool_id == "t-43"
    assert tool.tool_name == "conformer_search"
    assert tool.is_write() is True
