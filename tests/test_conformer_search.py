import json
import os
import shutil

import pytest

import cloudra.tools.Chemtool.conformer_search as conformer_mod
from cloudra.tools.Chemtool.conformer_search import ConformerSearch, ConformerSearch_input_schema

CREST_QCG_FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures", "crest_qcg")

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


# ---------------------------------------------------------------------------
# input_text 格式嗅探：结构化判定，不查子串
# ---------------------------------------------------------------------------


def test_sniff_xyz_with_v2000_in_comment_is_still_xyz():
    """xyz 注释行撞到 "V2000" 子串不得误判为 mol。"""
    text = ETHANOL_XYZ.replace("ethanol", "ethanol V2000 reference")
    assert conformer_mod._sniff_structure_text(text) == "xyz_text"


def test_sniff_mol_with_numeric_name_line_is_still_mol():
    """mol 首行（分子名）以数字开头是合法的，不得改判 xyz。"""
    mol_block = (
        "12345\n"
        "  cloudra\n"
        "\n"
        "  2  1  0  0  0  0            999 V2000\n"
        "    0.0000    0.0000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\n"
        "    1.0900    0.0000    0.0000 O   0  0  0  0  0  0  0  0  0  0  0  0\n"
        "  1  2  1  0\n"
        "M  END\n"
    )
    assert conformer_mod._sniff_structure_text(mol_block) == "mol_block"


def test_sniff_plain_xyz_and_v3000_mol():
    assert conformer_mod._sniff_structure_text(ETHANOL_XYZ) == "xyz_text"
    v3000 = (
        "name\n"
        "  cloudra\n"
        "\n"
        "  0  0  0  0  0  0            999 V3000\n"
        "M  V30 BEGIN CTAB\n"
        "M  V30 COUNTS 1 0 0 0 0\n"
        "M  V30 BEGIN ATOM\n"
        "M  V30 1 C 0.0 0.0 0.0 0\n"
        "M  V30 END ATOM\n"
        "M  V30 END CTAB\n"
        "M  END\n"
    )
    assert conformer_mod._sniff_structure_text(v3000) == "mol_block"


def test_sniff_unparseable_text_is_invalid_not_guessed():
    with pytest.raises(ValueError, match="neither a mol block"):
        conformer_mod._sniff_structure_text("CCO ethanol smiles-ish text")
    with pytest.raises(ValueError, match="neither a mol block"):
        conformer_mod._sniff_structure_text("")


# ---------------------------------------------------------------------------
# 聚类口径：RemoveHs 不保留 conformer id 时 fail-loud
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_removehs_id_loss_fails_loud_instead_of_switching_criterion(
    tool, mock_session, tmp_path, monkeypatch,
):
    """RemoveHs 丢 conformer id → 显式失败；绝不允许换成全原子 RMSD 口径继续出结果。"""
    from rdkit import Chem

    real_remove_hs = Chem.RemoveHs

    def _conformer_stripping_remove_hs(mol, **_kwargs):
        heavy = real_remove_hs(mol)
        heavy.RemoveAllConformers()
        return heavy

    monkeypatch.setattr(Chem, "RemoveHs", _conformer_stripping_remove_hs)
    result = await tool.safe_call(
        ConformerSearch_input_schema(smiles="CCCC", output_dir=str(tmp_path / "confs")),
        mock_session,
    )
    assert result.is_success is False
    assert "RemoveHs did not preserve conformer id" in result.message


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
async def test_guided_ring_search_returns_only_qualified_ts_seeds(tool, mock_session, tmp_path):
    result = await tool.safe_call(ConformerSearch_input_schema(
        smiles="CCCCCC", ring_order=[1, 2, 3, 4, 5, 6],
        distance_filters=[
            {"atoms": [1, 6], "min_ang": 3.5, "max_ang": 4.0},
            {"atoms": [2, 5], "min_ang": 3.2, "max_ang": 4.0},
        ],
        output_dir=str(tmp_path / "guided"),
    ), mock_session)
    assert result.is_success
    assert result.seed_kind == "constrained_preorganization"
    assert result.conformers and all(row["passes_filters"] for row in result.conformers)
    assert all("boltzmann_pct" not in row for row in result.conformers)
    assert "Boltzmann" not in result.table
    assert result.constraint_manifest_path
    assert {row["source"] for row in result.effective_windows} == {"explicit"}


@pytest.mark.asyncio
async def test_guided_ring_fallback_is_visible(tool, mock_session, tmp_path):
    result = await tool.safe_call(ConformerSearch_input_schema(
        smiles="CCO.O", ring_order=[1, 2, 3, 10],
        distance_filters=[{"atoms": [3, 10], "min_ang": 2.5, "max_ang": 3.8}],
        output_dir=str(tmp_path / "fallback"),
    ), mock_session)
    assert any(row["source"] == "fallback" for row in result.effective_windows)
    assert "1-10" in result.message


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["qcg", "protonate", "deprotonate", "tautomerize"])
async def test_guided_ring_rejects_species_changing_modes(tool, mock_session, tmp_path, mode):
    result = await tool.safe_call(ConformerSearch_input_schema(
        smiles="CCC", ring_order=[1, 2, 3], backend="crest", mode=mode,
        output_dir=str(tmp_path / mode),
    ), mock_session)
    assert not result.is_success
    assert "ring_order" in result.message and "unsupported" in result.message


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
    assert result.counts["retained"] == len(passing)
    assert len(passing) >= 1 and len(failing) == 0
    assert all(3.5 <= c["achieved_distances"]["1-4"] <= 4.5 for c in passing)
    # 通过过滤的是最低能（anti）构象
    assert passing[0]["conf_id"] == 0
    assert result.seed_kind == "constrained_preorganization"


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
    """CREST 后端集成测试：环境无 crest 或 chem 额外依赖（rdkit）时跳过。"""
    if shutil.which("crest") is None:
        pytest.skip("未安装 crest，跳过 CREST 后端集成测试")
    pytest.importorskip("rdkit", reason="未安装 chem 额外依赖（rdkit）")
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
    # Task 3：CREST 现场必须持久保留（命令行/输入/版本/日志/中间产物），不再跑完即删
    runs_root = tmp_path / "crest_out" / "crest_runs"
    run_dirs = sorted(p for p in runs_root.iterdir() if p.is_dir())
    assert run_dirs, "CREST 运行目录必须保留"
    run_dir = run_dirs[0]
    for name in ("command.txt", "input.xyz", "versions.txt", "stdout.log", "stderr.log",
                 "crest_conformers.xyz"):
        assert (run_dir / name).is_file(), f"CREST 现场缺少 {name}"


def test_tool_metadata():
    tool = ConformerSearch()
    assert tool.tool_name == "conformer_search"
    assert tool.is_write() is True


# ---------- issue #19：带电多碎片输入的全零能量与碎片叠放 ----------

MULTI_FRAG_SMILES = "[O-]C=C.O.CC=O"


@pytest.mark.asyncio
async def test_multifragment_input_returns_assembled_complex_candidates(tool, mock_session, tmp_path):
    """issue #19/#33 复现输入：多碎片体系的构象系综**就是组装**。

    过去返回的是逐碎片独立嵌入的坐标（实测碎片间 0.1–0.2 Å 互穿），或仅靠平移拉开的叠加；
    现在经用户批准的组装方案（刚性放置采样 + 碰撞剔除 + 力场弛豫）产出真正的复合物候选：
    每个候选都必须满足 1.0 Å 片间最小原子距，且系综文件里不含互穿几何。
    """
    import numpy as np

    out_dir = tmp_path / "confs_reactant"
    result = await tool.safe_call(
        ConformerSearch_input_schema(
            smiles=MULTI_FRAG_SMILES,
            charge=-1,
            num_confs=40,
            distance_filters=[{"atoms": [2, 6], "min_ang": 1.5, "max_ang": 5.0}],
            output_dir=str(out_dir),
        ),
        mock_session,
    )
    assert result.is_success is True, result.message
    assert result.conformers, "多碎片输入必须产出组装候选"
    assert result.counts["generated"] >= result.counts["retained"]
    assert result.seed_kind == "constrained_preorganization"
    assert result.ensemble_path.endswith(".xyz")
    assert (out_dir / "guided_assembly" / "assembly" / "assembly.json").is_file()

    # 系综文件里每一帧都不得含亚 1 Å 的片间接触。
    # 碎片分组取自构建器自己记录的**稳定身份表**（component_id），不靠重新推导——
    # 构建器逐组分加氢，输出原子顺序与 Chem.AddHs(MolFromSmiles(...)) 并不相同。
    prepared = json.loads(
        (out_dir / "guided_assembly" / "prepared_structure.json").read_text(encoding="utf-8")
    )
    component_ids = [identity["component_id"] for identity in prepared["atom_identities"]]
    frag_of = {index: int(cid.removeprefix("frag")) for index, cid in enumerate(component_ids)}
    assert len(set(frag_of.values())) == 3, component_ids
    lines = open(result.ensemble_path, encoding="utf-8").read().splitlines()
    index = 0
    frames = 0
    while index < len(lines):
        count = int(lines[index].strip())
        pos = np.asarray(
            [[float(v) for v in ln.split()[1:4]] for ln in lines[index + 2: index + 2 + count]],
            dtype=float,
        )
        worst = min(
            float(np.linalg.norm(pos[i] - pos[j]))
            for i in range(count) for j in range(i + 1, count)
            if frag_of[i] != frag_of[j]
        )
        assert worst >= 1.0, f"系综第 {frames} 帧含亚 1 Å 片间接触：{worst:.3f} Å"
        frames += 1
        index += 2 + count
    assert frames == len(result.conformers)
    assert result.constraint_manifest_path
    assert all(row["passes_filters"] for row in result.conformers)


@pytest.mark.asyncio
async def test_multifragment_charge_mismatch_is_refused(tool, mock_session, tmp_path):
    """总电荷与形式电荷不符时先报电荷问题，不进入任何搜索。"""
    result = await tool.safe_call(
        ConformerSearch_input_schema(
            smiles=MULTI_FRAG_SMILES, charge=0, output_dir=str(tmp_path / "cm"),
        ),
        mock_session,
    )
    assert result.is_success is False
    assert "charge_mismatch" in result.message
    assert "sum to -1" in result.message


@pytest.mark.asyncio
async def test_mmff_failure_falls_back_to_uff(tool, mock_session, tmp_path, monkeypatch):
    """MMFF 优化全部失败（flag!=0, E=0.0）时回退 UFF；0.0 不得被当作能量。"""
    monkeypatch.setattr(
        conformer_mod.AllChem, "MMFFOptimizeMoleculeConfs",
        lambda mol, **kw: [(1, 0.0)] * mol.GetNumConformers(),
    )
    monkeypatch.setattr(conformer_mod.AllChem, "MMFFOptimizeMolecule", lambda mol, **kw: 1)
    result = await tool.safe_call(
        ConformerSearch_input_schema(smiles="CCCC", num_confs=30, output_dir=str(tmp_path / "uff_fallback")),
        mock_session,
    )
    assert result.is_success is True
    assert "UFF" in result.message
    rel = [c["rel_energy_kcal"] for c in result.conformers]
    assert max(rel) > 1e-3


@pytest.mark.asyncio
async def test_all_forcefield_failures_return_error(tool, mock_session, tmp_path, monkeypatch):
    """MMFF 与 UFF 都失败：必须 is_success=False，绝不输出全零能量表。"""
    monkeypatch.setattr(
        conformer_mod.AllChem, "MMFFOptimizeMoleculeConfs",
        lambda mol, **kw: [(1, 0.0)] * mol.GetNumConformers(),
    )
    monkeypatch.setattr(conformer_mod.AllChem, "MMFFOptimizeMolecule", lambda mol, **kw: 1)
    monkeypatch.setattr(conformer_mod.AllChem, "UFFOptimizeMolecule", lambda mol, **kw: 1)
    result = await tool.safe_call(
        ConformerSearch_input_schema(smiles="CCCC", num_confs=10, output_dir=str(tmp_path / "all_fail")),
        mock_session,
    )
    assert result.is_success is False
    assert "UFF" in result.message


@pytest.mark.asyncio
async def test_uff_fallback_energies_rescored_with_mmff(tool, mock_session, tmp_path, monkeypatch):
    """C1：MMFF 优化不收敛、UFF 回退的构象，其能量必须是 UFF 几何上的 MMFF 单点（同一零点），
    UFF 能量值不得进入排序/能窗/Boltzmann。"""
    monkeypatch.setattr(
        conformer_mod.AllChem, "MMFFOptimizeMoleculeConfs",
        lambda mol, **kw: [(1, 0.0)] * mol.GetNumConformers(),
    )
    monkeypatch.setattr(conformer_mod.AllChem, "MMFFOptimizeMolecule", lambda mol, **kw: 1)
    out_dir = tmp_path / "uff_rescored"
    result = await tool.safe_call(
        ConformerSearch_input_schema(smiles="CCCC", num_confs=30, output_dir=str(out_dir)),
        mock_session,
    )
    assert result.is_success is True
    assert "UFF" in result.message
    assert "single-point" in result.message or "single point" in result.message

    # 独立复算：conf0 的落盘几何做 MMFF 单点，必须与表内 abs 能量一致（MMFF 零点）；
    # 同一几何的 UFF 能量（零点差 ~17 kcal）绝不允许出现。SDF 的 MolToMolBlock 坐标
    # 只写 ~1e-3 Å 精度，回读几何的 MMFF 单点与表内高精度值允许 0.05 kcal 偏差
    # （远小于 MMFF/UFF 的 ~17 kcal 零点差）。
    from rdkit import Chem as _Chem
    from rdkit.Chem import AllChem as _AllChem

    suppl = _Chem.SDMolSupplier(str(out_dir / "confs.sdf"), removeHs=False)
    m0 = next(m for m in suppl if m is not None)
    props = _AllChem.MMFFGetMoleculeProperties(m0, mmffVariant="MMFF94")
    expected_mmff = float(_AllChem.MMFFGetMoleculeForceField(m0, props).CalcEnergy())
    uff_e = float(_AllChem.UFFGetMoleculeForceField(m0).CalcEnergy())
    reported = float(m0.GetProp("energy"))
    assert abs(reported - expected_mmff) < 0.05
    assert abs(reported - uff_e) > 1.0


@pytest.mark.asyncio
async def test_missing_mmff_params_fails_loud(tool, mock_session, tmp_path, monkeypatch):
    """C1：分子缺 MMFF 参数时无法把 UFF 几何重估到同一零点——显式拒收并披露原因，绝不输出 UFF 能量表。"""
    monkeypatch.setattr(conformer_mod.AllChem, "MMFFHasAllMoleculeParams", lambda mol: False)
    result = await tool.safe_call(
        ConformerSearch_input_schema(smiles="CCCC", num_confs=10, output_dir=str(tmp_path / "no_mmff")),
        mock_session,
    )
    assert result.is_success is False
    assert "MMFF" in result.message


# ---------- C2：CREST multiplicity 透传 + temperature 校验 ----------

def test_schema_multiplicity_field():
    """C2：schema 暴露 multiplicity（默认 1），开壳层输入不再被静默按闭壳层处理。"""
    assert ConformerSearch_input_schema(smiles="CCCC").multiplicity == 1
    assert ConformerSearch_input_schema(smiles="CCCC", multiplicity=3).multiplicity == 3


@pytest.mark.asyncio
async def test_rdkit_backend_rejects_open_shell(tool, mock_session, tmp_path):
    """Valid open-shell declarations still cannot enter RDKit force-field energy ranking."""
    result = await tool.safe_call(
        ConformerSearch_input_schema(smiles="[CH3]", multiplicity=2, output_dir=str(tmp_path / "rad")),
        mock_session,
    )
    assert result.is_success is False
    assert "force-field" in result.message.lower()
    assert "crest" in result.message.lower()


@pytest.mark.asyncio
async def test_nonpositive_temperature_rejected(tool, mock_session, tmp_path):
    """C2：temperature<=0 会产生 NaN 布居，必须拒收。"""
    for t in (0.0, -10.0):
        result = await tool.safe_call(
            ConformerSearch_input_schema(smiles="CCCC", temperature=t, output_dir=str(tmp_path / "t0")),
            mock_session,
        )
        assert result.is_success is False
        assert "temperature" in result.message.lower()




# ---------------------------------------------------------------------------
# 构建产物目录命名：三个入口必须一致（否则工作区会同时出现多种名字）
# ---------------------------------------------------------------------------


def test_build_artifact_dir_naming_is_shared_by_all_entry_points():
    """唯一命名规则：``<base>/structure_build[/<slug>]``，三个入口共用同一份实现。"""
    from cloudra.tools.Chemtool.conformer_search import _BUILD_DIR_NAME
    from cloudra.tools.core.structure_builder import BUILD_DIR_NAME, build_artifact_dir

    assert _BUILD_DIR_NAME == BUILD_DIR_NAME == "structure_build"
    assert build_artifact_dir("/w") == "/w/structure_build"
    # 同一父目录下并存多个结构时用 slug 隔开，避免互相覆盖
    assert build_artifact_dir("/w", "CO2") == "/w/structure_build/CO2"
    assert build_artifact_dir("/w", "H2O") != build_artifact_dir("/w", "CO2")


# ---------------------------------------------------------------------------
# CREST 特殊 runtype：nci / qcg / protonate / deprotonate / tautomerize
# ---------------------------------------------------------------------------

requires_crest = pytest.mark.skipif(shutil.which("crest") is None, reason="未安装 crest，跳过 CREST 集成测试")


@pytest.mark.asyncio
async def test_mode_requires_crest_backend(tool, mock_session, tmp_path):
    """非 conformers 的 mode 配 rdkit 后端必须 fail-loud，不静默换后端。"""
    result = await tool.safe_call(
        ConformerSearch_input_schema(
            smiles="CCO", backend="rdkit", mode="nci", output_dir=str(tmp_path / "m"),
        ),
        mock_session,
    )
    assert result.is_success is False
    assert "backend='crest'" in result.message


@pytest.mark.asyncio
async def test_qcg_requires_solvent_and_nsolv(tool, mock_session, tmp_path):
    for kwargs in ({"nsolv": 3}, {"solvent_smiles": "O"}):
        result = await tool.safe_call(
            ConformerSearch_input_schema(
                smiles="CC(=O)O", backend="crest", mode="qcg", output_dir=str(tmp_path / "q"),
                **kwargs,
            ),
            mock_session,
        )
        assert result.is_success is False
        assert "qcg" in result.message
    # solvent/nsolv 只配 qcg
    result = await tool.safe_call(
        ConformerSearch_input_schema(
            smiles="CCO", backend="crest", mode="nci", solvent_smiles="O",
            output_dir=str(tmp_path / "q2"),
        ),
        mock_session,
    )
    assert result.is_success is False
    assert "mode='qcg'" in result.message


@pytest.mark.asyncio
async def test_protonate_family_refuses_multi_component(tool, mock_session, tmp_path):
    result = await tool.safe_call(
        ConformerSearch_input_schema(
            smiles="CC(=O)O.O", backend="crest", mode="protonate",
            output_dir=str(tmp_path / "p"),
        ),
        mock_session,
    )
    assert result.is_success is False
    assert "components" in result.message


@requires_crest
@pytest.mark.asyncio
async def test_nci_mode_samples_noncovalent_network(tool, mock_session, tmp_path):
    """--nci：水二聚体的氢键网络采样（壁势下的非共价系综）。"""
    out_dir = tmp_path / "nci_out"
    result = await tool.safe_call(
        ConformerSearch_input_schema(
            smiles="O.O", backend="crest", mode="nci", output_dir=str(out_dir), timeout=900,
        ),
        mock_session,
    )
    assert result.is_success is True, result.message
    assert "--nci" in result.message
    assert os.path.isfile(result.ensemble_path)
    # 每帧 6 原子（两个水）；氢键网络意味着存在片间 O...H 近距离接触的构象
    lines = open(result.ensemble_path, encoding="utf-8").read().splitlines()
    assert int(lines[0].strip()) == 6


@requires_crest
@pytest.mark.asyncio
async def test_protonate_mode_adds_one_proton_and_warns(tool, mock_session, tmp_path):
    """--protonate：产物帧原子数 = 输入+1；返回文案必须含伪结构审查警告。"""
    out_dir = tmp_path / "prot_out"
    result = await tool.safe_call(
        ConformerSearch_input_schema(
            smiles="CC(=O)O", backend="crest", mode="protonate",
            output_dir=str(out_dir), timeout=900,
        ),
        mock_session,
    )
    assert result.is_success is True, result.message
    assert "pseudo-structures" in result.message
    assert "DIFFERENT CHEMICAL SPECIES" in result.message
    lines = open(result.ensemble_path, encoding="utf-8").read().splitlines()
    assert int(lines[0].strip()) == 9  # 乙酸 8 原子 + 1 质子


@requires_crest
@pytest.mark.asyncio
async def test_tautomerize_mode_finds_tautomers_and_warns(tool, mock_session, tmp_path):
    """--tautomerize：乙醛应至少给出烯醇式互变异构体（≥2 条），原子数不变。"""
    out_dir = tmp_path / "taut_out"
    result = await tool.safe_call(
        ConformerSearch_input_schema(
            smiles="CC=O", backend="crest", mode="tautomerize",
            output_dir=str(out_dir), timeout=900,
        ),
        mock_session,
    )
    assert result.is_success is True, result.message
    assert "pseudo-structures" in result.message
    assert result.counts["generated"] >= 2
    lines = open(result.ensemble_path, encoding="utf-8").read().splitlines()
    assert int(lines[0].strip()) == 7


@requires_crest
@pytest.mark.asyncio
async def test_qcg_without_xtbiff_fails_loud(tool, mock_session, tmp_path):
    """--qcg 依赖外部 xtb-IFF：本机缺失时必须落到专属终止类别并在消息里说明，不猜不绕。"""
    if shutil.which("xtbiff"):
        pytest.skip("已安装 xtb-IFF，无法复现缺失路径")
    result = await tool.safe_call(
        ConformerSearch_input_schema(
            smiles="CC(=O)O", backend="crest", mode="qcg", solvent_smiles="O", nsolv=2,
            output_dir=str(tmp_path / "qcg_out"), timeout=900,
        ),
        mock_session,
    )
    assert result.is_success is False
    assert "qcg_xtbiff_missing" in result.message
    assert "xtb-IFF" in result.message


def test_official_qcg_example_fixtures_match_docs():
    """官网 QCG 示例输入必须在仓里、原子数与文档一致（不跑引擎）。"""
    e1 = open(os.path.join(CREST_QCG_FIXTURES, "example_1", "bacillaene.xyz"), encoding="utf-8").read()
    e2 = open(os.path.join(CREST_QCG_FIXTURES, "example_2", "benzoic_acid.xyz"), encoding="utf-8").read()
    water = open(os.path.join(CREST_QCG_FIXTURES, "example_2", "water.xyz"), encoding="utf-8").read()
    solute = open(os.path.join(CREST_QCG_FIXTURES, "example_3", "solute.xyz"), encoding="utf-8").read()
    solvent = open(os.path.join(CREST_QCG_FIXTURES, "example_3", "solvent.xyz"), encoding="utf-8").read()
    xcontrol = open(os.path.join(CREST_QCG_FIXTURES, "example_3", ".xcontrol"), encoding="utf-8").read()
    pentanol = open(os.path.join(CREST_QCG_FIXTURES, "example_4", "pentanol.xyz"), encoding="utf-8").read()
    benzene = open(os.path.join(CREST_QCG_FIXTURES, "example_4", "benzene.coord"), encoding="utf-8").read()
    struc = open(os.path.join(CREST_QCG_FIXTURES, "example_5", "struc.xyz"), encoding="utf-8").read()
    directed = open(os.path.join(CREST_QCG_FIXTURES, "example_5", "directed.list"), encoding="utf-8").read()
    assert int(e1.splitlines()[0].strip()) == 90
    assert int(e2.splitlines()[0].strip()) == 15
    water_lines = water.splitlines()
    assert int(water_lines[0].strip()) == 3
    # 官网 xyz：第 1 行原子数、第 2 行注释（可空）、其后才是原子
    assert water_lines[2].split()[0] == "O"
    assert int(solute.splitlines()[0].strip()) == 23
    assert int(solvent.splitlines()[0].strip()) == 6
    assert "$constrain" in xcontrol
    assert int(pentanol.splitlines()[0].strip()) == 18
    assert benzene.splitlines()[0].strip() == "$coord"
    assert int(struc.splitlines()[0].strip()) == 34
    assert "23,24 5" in directed


@requires_crest
@pytest.mark.asyncio
async def test_qcg_grows_explicit_solvent_shell(tool, mock_session, tmp_path):
    """官网例 2 输入：苯甲酸 + 3 水 grow；产物帧 = 溶质 15 + 3×3 = 24 原子。"""
    if not shutil.which("xtbiff"):
        pytest.skip("未安装 xtb-IFF，跳过 QCG 成功路径集成测试")
    solute = tmp_path / "benzoic_acid.xyz"
    shutil.copy(
        os.path.join(CREST_QCG_FIXTURES, "example_2", "benzoic_acid.xyz"),
        solute,
    )
    out_dir = tmp_path / "qcg_ok"
    result = await tool.safe_call(
        ConformerSearch_input_schema(
            input_path=str(solute), backend="crest", mode="qcg", solvent_smiles="O", nsolv=3,
            output_dir=str(out_dir), timeout=1800,
        ),
        mock_session,
    )
    assert result.is_success is True, result.message
    assert "micro-solvated cluster" in result.message
    assert os.path.isfile(result.ensemble_path)
    lines = open(result.ensemble_path, encoding="utf-8").read().splitlines()
    assert int(lines[0].strip()) == 24  # 官网苯甲酸 15 原子 + 3 个水
