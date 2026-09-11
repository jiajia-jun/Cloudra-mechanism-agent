"""pymol_render tool tests.

Rendering tests are environment-probed: they skip unless the pymol module or
a system pymol binary is available.  Input-validation and availability-error
paths run everywhere.
"""

from __future__ import annotations

import pytest

from cloudra.tools.Chemtool import pymol_render
from cloudra.tools.Chemtool.pymol_render import (
    PymolRender,
    PymolRender_input_schema,
    pymol_available,
)

_HAS_PYMOL = pymol_available()

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
    assert "read" in result.message


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
    assert "File not found" in result.message


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


# ---------------------------------------------------------------------------
# F8：output_path 不带 .png 时产物路径对齐（PyMOL 会自动补 .png）
# ---------------------------------------------------------------------------


def test_expected_png_path_helper():
    """产物路径 = 用户路径，或用户路径 + '.png'（大小写无关）。"""
    assert pymol_render._expected_png_path("/tmp/a.png") == "/tmp/a.png"
    assert pymol_render._expected_png_path("/tmp/a.PNG") == "/tmp/a.PNG"
    assert pymol_render._expected_png_path("/tmp/a") == "/tmp/a.png"
    assert pymol_render._expected_png_path("out") == "out.png"


@pytest.mark.asyncio
async def test_output_without_png_extension_succeeds(tmp_path, pdb_file, mock_session, monkeypatch):
    """output_path 不带 .png：PyMOL 写到 <path>.png，工具必须按真实产物检查与返回。"""
    monkeypatch.setattr(pymol_render.shutil, "which", lambda name: "/usr/bin/fake-pymol")
    out = str(tmp_path / "gly")

    def fake_render(binary, commands):
        # 从 png 命令行解析目标基名，PyMOL 会在其后加 .png
        png_line = next(c for c in commands if c.startswith("png "))
        target = png_line[4:].split(",", 1)[0].strip().strip('"')
        from pathlib import Path as _Path
        _Path(target + ".png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 32)

    monkeypatch.setattr(pymol_render, "_render_with_binary", fake_render)
    tool = PymolRender()
    result = await tool.tool_call(
        PymolRender_input_schema(structure_path=pdb_file, output_path=out, ray=False),
        mock_session,
    )
    assert result.is_success, result.message
    assert result.image_path.endswith("gly.png")
    assert result.image_path != out  # 返回真实产物路径，而非请求的无扩展名路径
    assert (tmp_path / "gly.png").stat().st_size > 0
