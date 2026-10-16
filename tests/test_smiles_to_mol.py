"""smiles_to_mol: RDKit SMILES → MOL conversion."""

import pytest

pytest.importorskip("rdkit", reason="smiles_to_mol requires RDKit (chem extra)")

from cloudra.tools.Chemtool.smiles_to_mol import SmilesToMol, SmilesToMol_input_schema


@pytest.mark.asyncio
async def test_smiles_to_mol_returns_mol_block():
    result = await SmilesToMol().tool_call(
        SmilesToMol_input_schema(smiles="CC(=O)O"),
        session=None,
    )
    assert result.is_success is True, result.message
    assert "V2000" in result.mol_content
    assert result.file_path == ""


@pytest.mark.asyncio
async def test_smiles_to_mol_3d_and_file_write(tmp_path):
    out = tmp_path / "acetic.mol"
    result = await SmilesToMol().tool_call(
        SmilesToMol_input_schema(smiles="CC(=O)O", output_path=str(out), generate_3d=True),
        session=None,
    )
    assert result.is_success is True, result.message
    assert result.file_path == str(out)
    assert out.read_text(encoding="utf-8") == result.mol_content


@pytest.mark.asyncio
async def test_smiles_to_mol_3d_exposes_xyz_from_the_same_build(tmp_path):
    """One 3D conversion makes its XYZ usable without another embedding run."""
    from rdkit import Chem

    result = await SmilesToMol().tool_call(
        SmilesToMol_input_schema(
            smiles="CC(=O)O", output_path=str(tmp_path / "acetic.mol"),
            generate_3d=True,
        ),
        session=None,
    )

    assert result.is_success is True, result.message
    xyz_path = tmp_path / "structure_build" / "acetic" / "prepared.xyz"
    assert result.xyz_path == str(xyz_path)
    xyz_lines = xyz_path.read_text(encoding="utf-8").splitlines()
    mol = Chem.MolFromMolBlock(result.mol_content, removeHs=False)
    assert mol is not None
    assert int(xyz_lines[0]) == mol.GetNumAtoms()
    assert [line.split()[0] for line in xyz_lines[2:]] == [
        atom.GetSymbol() for atom in mol.GetAtoms()
    ]


@pytest.mark.asyncio
async def test_smiles_to_mol_invalid_smiles():
    result = await SmilesToMol().tool_call(
        SmilesToMol_input_schema(smiles="c1cc("),
        session=None,
    )
    assert result.is_success is False
    assert "Invalid SMILES" in result.message


# ---------------------------------------------------------------------------
# F7（新契约）：3D 构建的力场优化状态必须反映在返回里，且"未优化"绝不当成功交付。
# 旧实现只把状态写进 message 却仍 is_success=True；现在坐标不可用就是失败。
# ---------------------------------------------------------------------------


import cloudra.tools.core.structure_builder as _builder  # noqa: E402


class _FailingForceField:
    """假力场：Minimize 直接抛异常，其余接口与真实力场同形。"""

    def __init__(self, mol, **_kwargs):
        self._mol = mol

    def Initialize(self, **_kwargs):
        return None

    def CalcEnergy(self, **_kwargs):
        return 0.0

    def CalcGrad(self, **_kwargs):
        return tuple(0.0 for _ in range(self._mol.GetNumAtoms() * 3))

    def Minimize(self, **_kwargs):
        raise RuntimeError("simulated optimizer crash")


@pytest.mark.asyncio
async def test_3d_optimization_exception_is_reported_and_not_delivered(monkeypatch, tmp_path):
    """力场优化抛异常时：不得静默，也不得把未优化几何当成品交付。"""
    monkeypatch.setattr(
        _builder.AllChem, "MMFFGetMoleculeForceField",
        lambda mol, *a, **kw: _FailingForceField(mol),
    )
    result = await SmilesToMol().tool_call(
        SmilesToMol_input_schema(
            smiles="CCO", generate_3d=True, artifact_dir=str(tmp_path / "nc"),
        ),
        session=None,
    )
    assert result.is_success is False
    assert "optimization_failed" in result.message
    assert result.mol_content == ""


@pytest.mark.asyncio
async def test_3d_force_field_unavailable_is_reported(monkeypatch, tmp_path):
    """MMFF 与 UFF 都缺参数时：披露"未优化"，不得冒充优化成功。"""
    monkeypatch.setattr(_builder, "_select_engine", lambda mol: None)
    result = await SmilesToMol().tool_call(
        SmilesToMol_input_schema(
            smiles="CCO", generate_3d=True, artifact_dir=str(tmp_path / "noparams"),
        ),
        session=None,
    )
    assert result.is_success is False
    assert "missing_parameters" in result.message
    assert "NOT optimized" in result.message


@pytest.mark.asyncio
async def test_3d_charge_mismatch_is_refused_with_the_actual_sum(tmp_path):
    """总电荷与 SMILES 形式电荷不一致时必须报出实际总和，便于直接改正。"""
    result = await SmilesToMol().tool_call(
        SmilesToMol_input_schema(
            smiles="[F-].CCl", generate_3d=True, charge=0, artifact_dir=str(tmp_path / "cm"),
        ),
        session=None,
    )
    assert result.is_success is False
    assert "charge_mismatch" in result.message
    assert "sum to -1" in result.message


# ---------------------------------------------------------------------------
# 多碎片 SMILES 的 3D 构建必须交付共享构建器组装出的配套 MOL/XYZ
# 复现材料见 tests/fixtures/chemtool_issue33/（实测 F–C 0.1392 Å）
# ---------------------------------------------------------------------------

import numpy as np  # noqa: E402


def _min_interfragment_distance(mol_block: str, frag_groups: list[list[int]]) -> float:
    """从 MOL block 读坐标，返回不同碎片原子对的最小距离（Å）。"""
    from rdkit import Chem

    mol = Chem.MolFromMolBlock(mol_block, removeHs=False)
    conf = mol.GetConformer()
    pos = np.asarray(conf.GetPositions(), dtype=float)
    frag_of = {atom: fi for fi, frag in enumerate(frag_groups) for atom in frag}
    best = float("inf")
    for i in range(len(pos)):
        for j in range(i + 1, len(pos)):
            if frag_of[i] != frag_of[j]:
                best = min(best, float(np.linalg.norm(pos[i] - pos[j])))
    return best


@pytest.mark.asyncio
@pytest.mark.parametrize("smiles,charge,fragments,charged_atoms", [
    ("[F-].CCl", -1, 2, [-1]),
    ("[Na+:7].[O-:1][H:6].[CH3:2][O:3][CH:4]=[O:5]", 0, 3, [-1, 1]),
])
async def test_multifragment_3d_returns_paired_mol_and_xyz(
    tmp_path, smiles, charge, fragments, charged_atoms,
):
    """已成功组装的复合物应可取回，保留键表、电荷和同一候选的坐标。"""
    from rdkit import Chem

    from cloudra.tools.core.structure_artifacts import read_xyz_atoms

    output = tmp_path / "complex.mol"
    result = await SmilesToMol().tool_call(
        SmilesToMol_input_schema(
            smiles=smiles, generate_3d=True, charge=charge,
            artifact_dir=str(tmp_path / "build"), output_path=str(output),
        ),
        session=None,
    )
    assert result.is_success is True, result.message
    assert result.file_path == str(output)
    assert output.read_text(encoding="utf-8") == result.mol_content

    mol = Chem.MolFromMolBlock(result.mol_content, removeHs=False)
    assert mol is not None
    assert len(Chem.GetMolFrags(mol)) == fragments
    assert sorted(atom.GetFormalCharge() for atom in mol.GetAtoms()
                  if atom.GetFormalCharge()) == charged_atoms
    xyz = read_xyz_atoms(result.xyz_path)
    assert [symbol for symbol, _ in xyz] == [atom.GetSymbol() for atom in mol.GetAtoms()]
    assert np.allclose(mol.GetConformer().GetPositions(),
                       [position for _, position in xyz], atol=1e-4)


@pytest.mark.asyncio
async def test_multifragment_2d_still_depicts_without_fragment_overlap(tmp_path):
    """2D 展示路径不走力场，故多碎片仍可用；且碎片不得被叠在同一处。"""
    result = await SmilesToMol().tool_call(
        SmilesToMol_input_schema(smiles="[F-].CCl", generate_3d=False),
        session=None,
    )
    assert result.is_success is True, result.message
    distance = _min_interfragment_distance(result.mol_content, [[0], [1, 2, 3, 4, 5]])
    assert distance > 1.0, f"2D 描绘把碎片叠在了一起：最小碎片间距离 {distance:.3f} Å"


@pytest.mark.asyncio
async def test_single_molecule_3d_leaves_builder_trajectory(tmp_path):
    """单分子 3D 构建经共享构建器完成，并留下逐迭代力场轨迹现场。"""
    out = tmp_path / "prep"
    result = await SmilesToMol().tool_call(
        SmilesToMol_input_schema(
            smiles="CCO", generate_3d=True, artifact_dir=str(out), output_path=str(tmp_path / "c.mol"),
        ),
        session=None,
    )
    assert result.is_success is True, result.message
    assert (out / "trajectories.json").is_file(), (
        "共享构建器必须留下轨迹清单（构建可追溯性的载体）"
    )
    assert (out / "prepared_structure.json").is_file()
