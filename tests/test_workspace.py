import codecs
import hashlib
from pathlib import Path
from types import SimpleNamespace

import pytest

from cloudra.base.session_class import Session
from cloudra.base.tools_class import Tool
from cloudra.persistence.workspace import (
    TextEdit,
    TurnDiffTracker,
    WorkspaceConflictError,
    WorkspaceError,
    WorkspaceService,
    resolve_working_directory,
)
from cloudra.tools.Searchtool.read import (
    Read,
    Read_input_schema,
)
from cloudra.tools.Writetool.edit_file import (
    EditFile,
    EditFile_input_schema,
)
from cloudra.tools.Writetool.text_writer import (
    TextWriter,
    TextWriter_input_schema,
)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _subagent(root: Path) -> SimpleNamespace:
    return SimpleNamespace(
        working_directory=str(root),
        conversation_id=f"test-{root.name}",
        name="coder",
    )


def test_resolve_working_directory_defaults_to_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert resolve_working_directory(None) == str(tmp_path.resolve())
    nested = tmp_path / "proj"
    nested.mkdir()
    assert resolve_working_directory(str(nested)) == str(nested.resolve())


def test_workspace_rejects_absolute_escape_and_symlink_paths(tmp_path):
    service = WorkspaceService(tmp_path)

    with pytest.raises(WorkspaceError, match="relative"):
        service.resolve_path(str(tmp_path / "file.txt"))
    with pytest.raises(WorkspaceError, match="escapes"):
        service.resolve_path("../outside.txt")

    outside = tmp_path.parent / f"{tmp_path.name}-outside"
    outside.mkdir()
    link = tmp_path / "linked"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except (NotImplementedError, OSError):
        pytest.skip("当前文件系统不支持创建符号链接")
    with pytest.raises(WorkspaceError, match="symlink"):
        service.resolve_path("linked/file.txt")


def test_read_snapshot_returns_full_hash_and_line_slice(tmp_path):
    raw = "第一行\nsecond\nthird\n".encode()
    (tmp_path / "sample.txt").write_bytes(raw)
    service = WorkspaceService(tmp_path)

    snapshot, content, total, start, end = service.read_text("sample.txt", 1, 3)

    assert snapshot.sha256 == _sha256(raw)
    assert content == "second\nthird\n"
    assert (total, start, end) == (3, 1, 3)


def test_exact_edit_preserves_bom_crlf_final_newline_and_mode(tmp_path):
    path = tmp_path / "script.txt"
    path.write_bytes(codecs.BOM_UTF8 + b"one\r\ntwo\r\n")
    path.chmod(0o750)
    service = WorkspaceService(tmp_path)
    before = service.snapshot("script.txt")

    change = service.prepare_edit(
        "script.txt",
        before.sha256,
        [TextEdit(old_text="two\n", new_text="three")],
    )
    service.apply(change)

    assert path.read_bytes() == codecs.BOM_UTF8 + b"one\r\nthree\r\n"
    assert path.stat().st_mode & 0o777 == 0o750
    assert change.additions == 1
    assert change.deletions == 1
    assert "--- a/script.txt" in change.diff
    assert "+++ b/script.txt" in change.diff


def test_edit_requires_unique_match_unless_replace_all(tmp_path):
    (tmp_path / "repeat.txt").write_text("x\nx\n", encoding="utf-8")
    service = WorkspaceService(tmp_path)
    before = service.snapshot("repeat.txt")

    with pytest.raises(WorkspaceConflictError, match="matched 2 times"):
        service.prepare_edit(
            "repeat.txt",
            before.sha256,
            [TextEdit(old_text="x", new_text="y")],
        )

    change = service.prepare_edit(
        "repeat.txt",
        before.sha256,
        [TextEdit(old_text="x", new_text="y", replace_all=True)],
    )
    service.apply(change)
    assert (tmp_path / "repeat.txt").read_text(encoding="utf-8") == "y\ny\n"


def test_apply_detects_file_change_after_preview(tmp_path):
    path = tmp_path / "race.txt"
    path.write_text("before\n", encoding="utf-8")
    service = WorkspaceService(tmp_path)
    before = service.snapshot("race.txt")
    change = service.prepare_edit(
        "race.txt",
        before.sha256,
        [TextEdit(old_text="before", new_text="agent")],
    )

    path.write_text("user\n", encoding="utf-8")

    with pytest.raises(WorkspaceConflictError, match="changed during approval"):
        service.apply(change)
    assert path.read_text(encoding="utf-8") == "user\n"


def test_diff_keeps_no_final_newline_changes_on_separate_lines(tmp_path):
    path = tmp_path / "no-newline.txt"
    path.write_text("old", encoding="utf-8")
    service = WorkspaceService(tmp_path)
    before = service.snapshot("no-newline.txt")

    change = service.prepare_edit(
        "no-newline.txt",
        before.sha256,
        [TextEdit(old_text="old", new_text="new")],
    )

    assert "\n-old\n+new\n" in change.diff


def test_edit_result_cannot_exceed_workspace_text_limit(tmp_path):
    path = tmp_path / "small.txt"
    path.write_text("x", encoding="utf-8")
    service = WorkspaceService(tmp_path, max_file_bytes=8)
    before = service.snapshot("small.txt")

    with pytest.raises(WorkspaceError, match="too large"):
        service.prepare_edit(
            "small.txt",
            before.sha256,
            [TextEdit(old_text="x", new_text="0123456789")],
        )


def test_write_requires_missing_for_create_and_hash_for_overwrite(tmp_path):
    service = WorkspaceService(tmp_path)

    create = service.prepare_write("new.txt", "first\n", "missing")
    service.apply(create)
    assert create.kind == "add"

    with pytest.raises(WorkspaceConflictError, match="already exists"):
        service.prepare_write("new.txt", "unsafe\n", "missing")
    with pytest.raises(WorkspaceConflictError, match="has changed"):
        service.prepare_write("new.txt", "unsafe\n", "0" * 64)

    current = service.snapshot("new.txt")
    overwrite = service.prepare_write("new.txt", "second\n", current.sha256)
    service.apply(overwrite)
    assert (tmp_path / "new.txt").read_text(encoding="utf-8") == "second\n"


def test_turn_diff_uses_first_agent_touch_as_base(tmp_path):
    path = tmp_path / "tracked.txt"
    path.write_text("pre-existing user state\n", encoding="utf-8")
    service = WorkspaceService(tmp_path)
    tracker = TurnDiffTracker()
    before = service.snapshot("tracked.txt")
    change = service.prepare_edit(
        "tracked.txt",
        before.sha256,
        [TextEdit(old_text="state", new_text="state plus agent")],
    )
    service.apply(change)

    diff = tracker.record_applied("session", service, change)

    assert "-pre-existing user state" in diff
    assert "+pre-existing user state plus agent" in diff
    assert str(tmp_path) not in diff


@pytest.mark.asyncio
async def test_read_tool_uses_relative_workspace_path(tmp_path, mock_session):
    (tmp_path / "readme.md").write_text("hello\n", encoding="utf-8")
    tool = Read(subagent=_subagent(tmp_path))

    result = await tool.tool_call(
        Read_input_schema(path="readme.md"),
        mock_session,
    )
    rejected = await tool.tool_call(
        Read_input_schema(path=str(tmp_path / "readme.md")),
        mock_session,
    )

    assert result.content == "hello\n"
    assert result.path == "readme.md"
    assert len(result.sha256) == 64
    assert rejected.content == ""
    assert "relative" in rejected.message


@pytest.mark.asyncio
async def test_edit_tool_records_preview_apply_and_turn_diff(
    tmp_path,
    mock_session: Session,
    monkeypatch,
):
    path = tmp_path / "agent.txt"
    path.write_text("old\n", encoding="utf-8")
    snapshot = WorkspaceService(tmp_path).snapshot("agent.txt")
    events: list[tuple[str, dict]] = []

    async def approve(self, session, details, tool_args=None):
        assert "Unified Diff" in details
        assert tool_args["filepath"] == "agent.txt"
        return True, ""

    async def record(self, session, event_type, data):
        events.append((event_type, data))

    monkeypatch.setattr(Tool, "ensure_safety", approve)
    monkeypatch.setattr(Tool, "record_session_event", record)
    tool = EditFile(subagent=_subagent(tmp_path))

    result = await tool.tool_call(
        EditFile_input_schema(
            filepath="agent.txt",
            expected_sha256=snapshot.sha256,
            edits=[{"old_text": "old", "new_text": "new"}],
        ),
        mock_session,
    )

    assert result.is_written is True
    assert result.status == "applied"
    assert path.read_text(encoding="utf-8") == "new\n"
    assert [event_type for event_type, _ in events] == [
        "file_change_proposed",
        "file_change_applied",
        "turn_diff_updated",
    ]
    assert "+new" in events[-1][1]["diff"]


@pytest.mark.asyncio
async def test_text_writer_tool_returns_structured_conflict(
    tmp_path,
    mock_session,
    monkeypatch,
):
    (tmp_path / "exists.txt").write_text("keep\n", encoding="utf-8")
    tool = TextWriter(subagent=_subagent(tmp_path))
    events: list[tuple[str, dict]] = []

    async def record(self, session, event_type, data):
        events.append((event_type, data))

    monkeypatch.setattr(Tool, "record_session_event", record)

    result = await tool.tool_call(
        TextWriter_input_schema(
            filepath="exists.txt",
            content="replace\n",
            expected_sha256="missing",
        ),
        mock_session,
    )

    assert result.is_written is False
    assert result.status == "conflict"
    assert "already exists" in result.message
    assert (tmp_path / "exists.txt").read_text(encoding="utf-8") == "keep\n"
    assert events == [
        (
            "file_change_failed",
            {
                "path": "exists.txt",
                "status": "conflict",
                "diff": "",
                "message": result.message,
            },
        )
    ]
