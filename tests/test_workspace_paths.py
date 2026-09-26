"""resolve_existing_tool_path：输入路径的相对/绝对存在性兜底。"""

from types import SimpleNamespace

import pytest

from cloudra.persistence.workspace import resolve_existing_tool_path


def _tool(working_directory):
    return SimpleNamespace(subagent=SimpleNamespace(working_directory=str(working_directory)))


def test_absolute_path_returned_as_is(tmp_path):
    target = tmp_path / "a.png"
    target.write_bytes(b"x")
    assert resolve_existing_tool_path(_tool(tmp_path / "ws"), str(target)) == str(target)


def test_absolute_missing_raises_with_candidate(tmp_path):
    missing = tmp_path / "nope.png"
    with pytest.raises(FileNotFoundError) as exc:
        resolve_existing_tool_path(_tool(tmp_path / "ws"), str(missing))
    assert str(missing) in str(exc.value)


def test_relative_prefers_working_directory(tmp_path, monkeypatch):
    ws = tmp_path / "ws"
    ws.mkdir()
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    (ws / "img.png").write_bytes(b"ws")
    (cwd / "img.png").write_bytes(b"cwd")
    monkeypatch.chdir(cwd)
    # 双候选都存在 → 工作目录优先（既有语义）
    assert resolve_existing_tool_path(_tool(ws), "img.png") == str((ws / "img.png").resolve())


def test_relative_falls_back_to_cwd(tmp_path, monkeypatch):
    ws = tmp_path / "ws"
    ws.mkdir()
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    (cwd / "img.png").write_bytes(b"cwd")
    monkeypatch.chdir(cwd)
    assert resolve_existing_tool_path(_tool(ws), "img.png") == str((cwd / "img.png").resolve())


def test_missing_everywhere_lists_all_candidates(tmp_path, monkeypatch):
    ws = tmp_path / "ws"
    ws.mkdir()
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    monkeypatch.chdir(cwd)
    with pytest.raises(FileNotFoundError) as exc:
        resolve_existing_tool_path(_tool(ws), "nope.png")
    message = str(exc.value)
    assert str((ws / "nope.png").resolve()) in message
    assert str((cwd / "nope.png").resolve()) in message


def test_missing_file_suggests_existing_close_matches(tmp_path, monkeypatch):
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "orca_opt.out").write_text("done", encoding="utf-8")
    monkeypatch.chdir(ws)

    with pytest.raises(FileNotFoundError) as exc:
        resolve_existing_tool_path(_tool(ws), "orca_opt.log")
    message = str(exc.value)
    assert "Did you mean:" in message
    assert "orca_opt.out" in message

