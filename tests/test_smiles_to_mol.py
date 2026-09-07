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
async def test_smiles_to_mol_invalid_smiles():
    result = await SmilesToMol().tool_call(
        SmilesToMol_input_schema(smiles="c1cc("),
        session=None,
    )
    assert result.is_success is False
    assert "Invalid SMILES" in result.message


# ---------------------------------------------------------------------------
# F7：3D MMFF 优化状态必须反映在 message（未收敛不得静默）
# ---------------------------------------------------------------------------

import rdkit.Chem.AllChem as _RdkitAllChem  # noqa: E402


@pytest.mark.asyncio
async def test_3d_mmff_not_converged_reported(monkeypatch):
    """MMFFOptimizeMolecule 返回 1（达迭代上限未收敛）时，message 必须披露。"""
    monkeypatch.setattr(_RdkitAllChem, "MMFFOptimizeMolecule", lambda mol, **kw: 1)
    result = await SmilesToMol().tool_call(
        SmilesToMol_input_schema(smiles="CCO", generate_3d=True),
        session=None,
    )
    assert result.is_success is True, result.message
    assert "did not converge" in result.message


@pytest.mark.asyncio
async def test_3d_mmff_unavailable_reported(monkeypatch):
    """MMFF 对分子不可用（抛异常）时披露，不静默。"""
    def boom(mol, **kw):
        raise RuntimeError("no MMFF params")

    monkeypatch.setattr(_RdkitAllChem, "MMFFOptimizeMolecule", boom)
    result = await SmilesToMol().tool_call(
        SmilesToMol_input_schema(smiles="CCO", generate_3d=True),
        session=None,
    )
    assert result.is_success is True, result.message
    assert "MMFF" in result.message
    assert "left as-is" in result.message
