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
async def test_read_absolute_path_inside_workspace_accepted(tmp_path, mock_session):
    """工作区内的绝对路径经兜底解析回落为相对读取（不再一刀切拒绝）。"""
    (tmp_path / "readme.md").write_text("hello\n", encoding="utf-8")
    tool = Read(subagent=_subagent(tmp_path))
    result = await tool.tool_call(
        Read_input_schema(path=str(tmp_path / "readme.md")), mock_session
    )
    assert result.is_success
    assert result.content == "hello\n"


@pytest.mark.asyncio
async def test_read_absolute_path_outside_workspace_refused(tmp_path, mock_session):
    """工作区外的绝对路径仍拒绝（沙箱不变），但报错要说清文件在哪。"""
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.md").write_text("x\n", encoding="utf-8")
    ws = tmp_path / "ws"
    ws.mkdir()
    tool = Read(subagent=_subagent(ws))
    result = await tool.tool_call(
        Read_input_schema(path=str(outside / "secret.md")), mock_session
    )
    assert result.is_success is False
    assert "outside the working directory" in result.message
    assert str(outside / "secret.md") in result.message


@pytest.mark.asyncio
async def test_read_missing_file_lists_tried_candidates(tmp_path, mock_session):
    """找不到时列出全部尝试过的候选，agent 不必换基准目录盲试。"""
    tool = Read(subagent=_subagent(tmp_path))
    result = await tool.tool_call(Read_input_schema(path="nope.md"), mock_session)
    assert result.is_success is False
    assert "Tried:" in result.message
    assert str((tmp_path / "nope.md").resolve()) in result.message

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


def _pdf_with_text(path):
    fitz = pytest.importorskip("fitz")
    doc = fitz.open()
    page = doc.new_page()
    # insert_text clips to page width; stack lines so scan (sum < 200 or avg < 50) does not fire.
    for i, line in enumerate(["Hello paper body"] + ["The paper continues with results. " * 2] * 8):
        page.insert_text((72, 72 + i * 14), line)
    doc.save(str(path))
    doc.close()

def _pdf_scan(path):
    fitz = pytest.importorskip("fitz")
    doc = fitz.open()
    page = doc.new_page()
    # 1x1 pixmap painted, no text layer
    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 8, 8), False)
    pix.clear_with(127)
    page.insert_image(page.rect, pixmap=pix)
    doc.save(str(path))
    doc.close()

@pytest.mark.asyncio
async def test_read_pdf_auto_returns_text_and_figure_inventory(tmp_path, mock_session):
    _pdf_with_text(tmp_path / "p.pdf")
    tool = Read(subagent=_subagent(tmp_path))
    result = await tool.tool_call(Read_input_schema(path="p.pdf"), mock_session)
    assert result.is_success
    assert result.kind == "document"
    assert "Hello paper body" in result.content
    assert result.image_paths == []  # auto + text layer: do not inject figures
    # images inventory may be empty if insert_text created no xrefs; that's fine

@pytest.mark.asyncio
async def test_read_pdf_docx_is_rejected(tmp_path, mock_session):
    (tmp_path / "x.docx").write_bytes(b"PK\x03\x04not-a-pdf")
    tool = Read(subagent=_subagent(tmp_path))
    result = await tool.tool_call(Read_input_schema(path="x.docx"), mock_session)
    assert result.is_success is False
    assert "pdf" in result.message.lower()

@pytest.mark.asyncio
async def test_read_scan_pdf_injects_every_page(tmp_path, mock_session):
    _pdf_scan(tmp_path / "s.pdf")
    # make 3 pages
    fitz = pytest.importorskip("fitz")
    doc = fitz.open(tmp_path / "s.pdf")
    doc.new_page()
    doc.new_page()
    doc.save(tmp_path / "s3.pdf")
    doc.close()
    tool = Read(subagent=_subagent(tmp_path))
    result = await tool.tool_call(Read_input_schema(path="s3.pdf", focus="auto"), mock_session)
    assert result.is_success
    assert len(result.image_paths) == 3
    assert len(result.images) == 3
    assert result.image_path == result.image_paths[0]

@pytest.mark.asyncio
async def test_read_scan_focus_text_does_not_inject_images(tmp_path, mock_session):
    _pdf_scan(tmp_path / "s.pdf")
    tool = Read(subagent=_subagent(tmp_path))
    result = await tool.tool_call(Read_input_schema(path="s.pdf", focus="text"), mock_session)
    assert result.is_success
    assert result.image_paths == []
    assert "text layer" in result.message.lower() or "no text" in result.message.lower()

@pytest.mark.asyncio
async def test_explorer_can_read_pdf(tmp_path, mock_session):
    _pdf_with_text(tmp_path / "p.pdf")
    tool = Read(subagent=_subagent(tmp_path))
    assert tool.is_read() is True
    assert tool.is_script() is False
    result = await tool.tool_call(Read_input_schema(path="p.pdf"), mock_session)
    assert result.is_success
