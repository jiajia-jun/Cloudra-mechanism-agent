"""image_to_smiles 工具测试。

覆盖审计发现 F3：识别结果零校验——非法 SMILES 与纯空白结果必须 is_success=False，
不得把 DECIMER 的胡话/空串当成功。全部用 monkeypatch 注入假 DECIMER，不依赖网络/模型。
"""

import pytest

pytest.importorskip("rdkit", reason="image_to_smiles 校验需要 RDKit")

import cloudra.tools.Chemtool.image_to_smiles as img_mod  # noqa: E402
from cloudra.tools.Chemtool.image_to_smiles import ImageToSmiles, ImageToSmiles_input_schema  # noqa: E402


@pytest.fixture
def fake_image(tmp_path):
    p = tmp_path / "struct.png"
    p.write_bytes(b"\x89PNG\r\n\x1a\nnotreallyapng")
    return str(p)


async def _run(img, monkeypatch, predict_result=None):
    monkeypatch.setattr(img_mod, "_load_predict_func", lambda: (lambda p: predict_result, ""))
    return await ImageToSmiles().tool_call(
        ImageToSmiles_input_schema(image_path=img), session=None,
    )


@pytest.mark.asyncio
async def test_valid_smiles_accepted(fake_image, monkeypatch):
    result = await _run(fake_image, monkeypatch, "CCO")
    assert result.is_success is True
    assert result.smiles == "CCO"


@pytest.mark.asyncio
async def test_invalid_smiles_rejected(fake_image, monkeypatch):
    """F3：DECIMER 返回非法 SMILES（如 'C(C(C'）必须 is_success=False。"""
    result = await _run(fake_image, monkeypatch, "C(C(C")
    assert result.is_success is False
    assert "not a valid SMILES" in result.message
    assert result.smiles == ""


@pytest.mark.asyncio
async def test_whitespace_result_rejected(fake_image, monkeypatch):
    """F3：strip 前判空会让纯空白结果漏过——strip 后再判空。"""
    for junk in ("", "   ", "\t\n "):
        result = await _run(fake_image, monkeypatch, junk)
        assert result.is_success is False
        assert "empty" in result.message
        assert result.smiles == ""


@pytest.mark.asyncio
async def test_blocking_model_load_does_not_freeze_event_loop(fake_image, monkeypatch):
    """DECIMER 的 import 即在进程内加载 TF SavedModel（分钟级同步 CPU 工作），
    tool_call 必须把它卸载出事件循环——曾把整个 API 冻结到所有请求超时。
    用阻塞 loader + 并发 ticker 探测：ticker 停滞即事件循环被冻结。"""
    import asyncio
    import time

    def blocking_loader():
        time.sleep(0.4)
        return (lambda p: "CCO"), ""

    monkeypatch.setattr(img_mod, "_load_predict_func", blocking_loader)

    ticks = 0
    stop = False

    async def ticker():
        nonlocal ticks
        while not stop:
            ticks += 1
            await asyncio.sleep(0.02)

    ticker_task = asyncio.create_task(ticker())
    try:
        result = await ImageToSmiles().tool_call(
            ImageToSmiles_input_schema(image_path=fake_image), session=None,
        )
    finally:
        stop = True
        await ticker_task
    assert result.is_success is True
    # 若阻塞发生在事件循环线程上，0.4s 的冻结期里 ticker 只会前进寥寥几步
    assert ticks > 5, f"event loop was frozen during tool_call (ticks={ticks})"


@pytest.mark.asyncio
async def test_whitespace_padded_valid_smiles_stripped(fake_image, monkeypatch):
    """带首尾空白的合法 SMILES 应 strip 后成功。"""
    result = await _run(fake_image, monkeypatch, "  CCO  ")
    assert result.is_success is True
    assert result.smiles == "CCO"


@pytest.mark.asyncio
async def test_non_text_result_rejected(fake_image, monkeypatch):
    result = await _run(fake_image, monkeypatch, ["CCO"])
    assert result.is_success is False
    assert "non-text" in result.message


@pytest.mark.asyncio
async def test_missing_file(fake_image, tmp_path):
    result = await ImageToSmiles().tool_call(
        ImageToSmiles_input_schema(image_path=str(tmp_path / "nope.png")), session=None,
    )
    assert result.is_success is False
    assert "File not found" in result.message
    assert str(tmp_path / "nope.png") in result.message


@pytest.mark.asyncio
async def test_decimer_not_installed_message(monkeypatch, fake_image):
    monkeypatch.setattr(img_mod, "_load_predict_func", lambda: (None, "boom"))
    result = await ImageToSmiles().tool_call(
        ImageToSmiles_input_schema(image_path=fake_image), session=None,
    )
    assert result.is_success is False
    assert "DECIMER is not installed" in result.message


def test_tool_metadata():
    tool = ImageToSmiles()
    assert tool.tool_name == "image_to_smiles"
    assert tool.is_read() is True


@pytest.mark.asyncio
async def test_relative_image_path_resolves_against_working_directory(tmp_path, monkeypatch):
    """路径兜底：相对路径同时试工作目录与 cwd；工作目录候选优先。"""
    from types import SimpleNamespace

    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "struct.png").write_bytes(b"\x89PNG\r\n\x1a\nx")
    monkeypatch.setattr(img_mod, "_load_predict_func", lambda: (lambda p: "CCO", ""))
    tool = ImageToSmiles()
    tool.subagent = SimpleNamespace(working_directory=str(ws))
    result = await tool.tool_call(
        ImageToSmiles_input_schema(image_path="struct.png"), session=None,
    )
    assert result.is_success is True
    assert result.smiles == "CCO"


@pytest.mark.asyncio
async def test_missing_image_lists_tried_candidates(tmp_path):
    """找不到时列出全部尝试过的候选路径，不再只回一句 does not exist。"""
    from types import SimpleNamespace

    tool = ImageToSmiles()
    tool.subagent = SimpleNamespace(working_directory=str(tmp_path))
    result = await tool.tool_call(
        ImageToSmiles_input_schema(image_path="nope.png"), session=None,
    )
    assert result.is_success is False
    assert "Tried:" in result.message
    assert str((tmp_path / "nope.png").resolve()) in result.message
