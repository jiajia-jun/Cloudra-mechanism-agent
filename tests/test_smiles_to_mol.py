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
