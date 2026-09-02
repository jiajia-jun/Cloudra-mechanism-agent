# tests/test_read.py — text + image cases
import pytest

from cloudra.tools.Searchtool.read import Read, Read_input_schema


def _subagent(root):
    return type("A", (), {"working_directory": str(root)})()

@pytest.mark.asyncio
async def test_read_text_relative_path_returns_sha256(tmp_path, mock_session):
    (tmp_path / "readme.md").write_text("hello\n", encoding="utf-8")
    tool = Read(subagent=_subagent(tmp_path))
    result = await tool.tool_call(Read_input_schema(path="readme.md"), mock_session)
    assert result.is_success
    assert result.kind == "text"
    assert result.content == "hello\n"
    assert result.path == "readme.md"
    assert len(result.sha256) == 64
    assert result.offset == 1

@pytest.mark.asyncio
async def test_read_rejects_absolute_path(tmp_path, mock_session):
    (tmp_path / "readme.md").write_text("hello\n", encoding="utf-8")
    tool = Read(subagent=_subagent(tmp_path))
    rejected = await tool.tool_call(
        Read_input_schema(path=str(tmp_path / "readme.md")), mock_session
    )
    assert rejected.is_success is False
    assert "relative" in rejected.message.lower()

@pytest.mark.asyncio
async def test_read_offset_limit_are_one_based(tmp_path, mock_session):
    (tmp_path / "n.txt").write_text("a\nb\nc\nd\n", encoding="utf-8")
    tool = Read(subagent=_subagent(tmp_path))
    result = await tool.tool_call(
        Read_input_schema(path="n.txt", offset=2, limit=2), mock_session
    )
    assert result.content == "b\nc\n"
    assert result.offset == 2
    assert result.limit == 2
    assert result.total_lines == 4

@pytest.mark.asyncio
async def test_read_does_not_silently_truncate_text(tmp_path, mock_session):
    body = ("line-of-text\n" * 4000)
    (tmp_path / "big.log").write_text(body, encoding="utf-8")
    tool = Read(subagent=_subagent(tmp_path))
    result = await tool.tool_call(Read_input_schema(path="big.log"), mock_session)
    assert result.is_success
    assert "[Truncated" not in result.content
    # Either full body in content, or offloaded with a workspace path and full file intact
    if result.content != body:
        assert ".cloudra/tool_output/" in result.message or ".cloudra/tool_output/" in result.content
        assert (tmp_path / "big.log").read_text(encoding="utf-8") == body

@pytest.mark.asyncio
async def test_read_png_sets_image_path(tmp_path, mock_session):
    png = tmp_path / "s.png"
    png.write_bytes(
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00"
        b"\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    tool = Read(subagent=_subagent(tmp_path))
    result = await tool.tool_call(Read_input_schema(path="s.png"), mock_session)
    assert result.is_success
    assert result.kind == "image"
    assert result.image_path.endswith("s.png")
    assert result.image_paths == [result.image_path]


@pytest.mark.asyncio
async def test_read_pdf_fails_until_document_branch(tmp_path, mock_session):
    (tmp_path / "paper.pdf").write_bytes(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    tool = Read(subagent=_subagent(tmp_path))
    result = await tool.tool_call(Read_input_schema(path="paper.pdf"), mock_session)
    assert result.is_success is False
    assert "pdf" in result.message.lower()
    assert "document" in result.message.lower()
    assert "pdf2md" not in result.message.lower()
