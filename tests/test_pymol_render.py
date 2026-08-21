"""pymol_render tool tests.

Rendering tests are environment-probed: they skip unless the pymol module or
a system pymol binary is available.  Input-validation and availability-error
paths run everywhere.
"""

from __future__ import annotations

import importlib.util
import shutil

import pytest

from cloudra.tools.Chemtool import pymol_render
from cloudra.tools.Chemtool.pymol_render import PymolRender, PymolRender_input_schema

_HAS_PYMOL = importlib.util.find_spec("pymol") is not None or shutil.which("pymol") is not None

_MINIMAL_PDB = """\
ATOM      1  N   GLY A   1       0.000   0.000   0.000  1.00  0.00           N
ATOM      2  CA  GLY A   1       1.458   0.000   0.000  1.00  0.00           C
ATOM      3  C   GLY A   1       2.009   1.420   0.000  1.00  0.00           C
ATOM      4  O   GLY A   1       1.251   2.390   0.000  1.00  0.00           O
END
"""


@pytest.fixture
def pdb_file(tmp_path):
    path = tmp_path / "gly.pdb"
    path.write_text(_MINIMAL_PDB)
    return str(path)


@pytest.mark.asyncio
async def test_render_minimal_pdb(tmp_path, pdb_file, mock_session):
    if not _HAS_PYMOL:
        pytest.skip("pymol module/binary not available")
    tool = PymolRender()
    output = str(tmp_path / "out.png")
    result = await tool.tool_call(
        PymolRender_input_schema(structure_path=pdb_file, output_path=output, ray=False),
        mock_session,
    )
    assert result.is_success, result.message
    assert result.image_path == output
    with open(output, "rb") as fh:
        assert fh.read(8) == b"\x89PNG\r\n\x1a\n"
    assert "image_reader" in result.message


@pytest.mark.asyncio
async def test_default_output_path_uses_workspace_visual_dir(tmp_path, pdb_file, mock_session):
    if not _HAS_PYMOL:
        pytest.skip("pymol module/binary not available")

    class _Sub:
        working_directory = str(tmp_path)

    tool = PymolRender(subagent=_Sub())
    result = await tool.tool_call(
        PymolRender_input_schema(structure_path=pdb_file, ray=False),
        mock_session,
    )
    assert result.is_success, result.message
    assert result.image_path.startswith(str(tmp_path / ".cloudra" / "visual"))
    assert result.image_path.endswith(".png")


@pytest.mark.asyncio
async def test_unsupported_format_rejected(tmp_path, mock_session):
    bad = tmp_path / "mol.ini"
    bad.write_text("nope")
    tool = PymolRender()
    result = await tool.tool_call(
        PymolRender_input_schema(structure_path=str(bad), output_path=str(tmp_path / "o.png")),
        mock_session,
    )
    assert not result.is_success
    assert "unsupported structure format" in result.message


@pytest.mark.asyncio
async def test_missing_file_rejected(tmp_path, mock_session):
    tool = PymolRender()
    result = await tool.tool_call(
        PymolRender_input_schema(
            structure_path=str(tmp_path / "ghost.pdb"), output_path=str(tmp_path / "o.png")
        ),
        mock_session,
    )
    assert not result.is_success
    assert "does not exist" in result.message


@pytest.mark.asyncio
async def test_unknown_style_rejected(pdb_file, mock_session):
    tool = PymolRender()
    result = await tool.tool_call(
        PymolRender_input_schema(structure_path=pdb_file, style="ribbonz"),
        mock_session,
    )
    assert not result.is_success
    assert "unknown style" in result.message


@pytest.mark.asyncio
async def test_missing_pymol_reports_install_hint(pdb_file, mock_session, monkeypatch):
    monkeypatch.setattr(pymol_render, "_PYMOL_MODULE_AVAILABLE", False)
    monkeypatch.setattr(pymol_render.shutil, "which", lambda _name: None)
    tool = PymolRender()
    result = await tool.tool_call(
        PymolRender_input_schema(structure_path=pdb_file),
        mock_session,
    )
    assert not result.is_success
    assert "cloudra[visual]" in result.message
