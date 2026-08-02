"""Fixture-backed characterization tests for the legacy Textual presentation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from rich.console import Console

from cloudra.tui.new.transcript import RecordKind, TranscriptStore
from cloudra.tui.new.transcript_render import RenderContext, compile_record, semantic_segments
from tests.tui_visual_cases import VISUAL_CASES, VisualCaseApp, semantic_snapshot, write_snapshot


FIXTURE = Path(__file__).parent / "fixtures" / "tui_visual_baseline.json"


def _compiled_case_records(name: str):
    """Build the immutable-record equivalent of each frozen ChatLog case."""
    store = TranscriptStore()
    if name == "assistant_plain":
        handles = [store.append("s1", RecordKind.ASSISTANT, content="普通 assistant 回复。", status="finished")]
    elif name == "markdown":
        handles = [store.append("s1", RecordKind.ASSISTANT, content="# 结果\n\n- 能量降低\n- 构象稳定", status="finished")]
    elif name == "reasoning":
        handles = [store.append("s1", RecordKind.ASSISTANT, reasoning="先检查收敛条件。", content="计算已完成。", status="finished")]
    elif name == "tool_running":
        handles = [store.append_tool("s1", "Bash", "pwd")]
    elif name == "tool_finished":
        handles = [store.append_tool("s1", "Bash", "pwd", finished=True, result="/tmp/project")]
    elif name in {"tool_collapsed", "tool_expanded"}:
        handle = store.append_tool("s1", "Bash", "pytest", finished=True, result="\n".join(f"line {index}" for index in range(12)))
        if name == "tool_expanded":
            store.toggle_collapsed(handle)
        handles = [handle]
    elif name == "decoded_json":
        handles = [store.append("s1", RecordKind.ASSISTANT, content='{"energy": -154.23, "unit": "kcal/mol"}', status="finished")]
    elif name == "code_copy":
        handles = [store.append("s1", RecordKind.ASSISTANT, content="```python\nprint('hello cloudra')\n```", status="finished")]
    elif name == "file_states":
        handles = [store.append_file_change("s1", f"calc/{status}.py", status) for status in ("applied", "proposed", "declined", "failed")]
    elif name == "supervisor":
        handles = [store.append_supervisor_review("s1", "通过", "计算设置与结果一致。")]
    elif name == "alert":
        handles = [store.append_alert("s1", "任务失败", "Gaussian 未收敛。", style="red")]
    elif name == "stream_preview":
        handle = store.start_stream("s1", "coordinator")
        store.append_reasoning_chunk("s1", "r" * 824)
        store.append_stream_chunk("s1", "c" * 2024)
        handles = [handle]
    else:
        raise ValueError(name)
    return tuple(store.get(handle) for handle in handles)


def _normalise_pairs(pairs):
    """Compare semantic content/styles, ignoring render-only padding and widget ids."""
    normalised: list[tuple[str, str]] = []
    for text, style in pairs:
        if not text.strip():
            continue
        copy_label = text.strip() == "复制"
        # Textual serialises its CSS bright_black token as ANSI colour 8;
        # Rich retains the named style.  They are the same frozen colour.
        style = style.replace("color(8)", "bright_black")
        # The legacy snapshot sees a Button before CSS styling; the compiler
        # intentionally supplies the primary treatment required by the virtual surface.
        if copy_label:
            text = "复制"
            style = ""
        if normalised and normalised[-1][1] == style and not copy_label:
            normalised[-1] = (normalised[-1][0] + text, style)
        else:
            normalised.append((text, style))
    return tuple(normalised)


def _fixture_semantics(snapshot):
    return _normalise_pairs(
        (segment["text"], segment["style"])
        for row in snapshot
        for segment in row["segments"]
    )


def _compiled_semantics(records):
    context = RenderContext(Console(width=100, force_terminal=False, color_system=None))
    return _normalise_pairs(
        pair
        for record in records
        for row in semantic_segments(compile_record(record, 100, context))
        for pair in row
    )


@pytest.mark.asyncio
async def test_current_chat_visual_contract():
    """The legacy widgets continue to render the frozen semantic baseline."""
    expected = json.loads(FIXTURE.read_text(encoding="utf-8"))
    actual = {}
    for name, build in VISUAL_CASES.items():
        app = VisualCaseApp(build)
        async with app.run_test(size=(100, 36)) as pilot:
            await pilot.pause()
            actual[name] = semantic_snapshot(app)
    assert actual == expected


def test_compiled_record_semantics_match_the_frozen_chat_cases():
    """Virtual rows preserve every frozen ChatLog case without widget allocation."""
    expected = json.loads(FIXTURE.read_text(encoding="utf-8"))
    cases = (
        "assistant_plain",
        "markdown",
        "reasoning",
        "tool_running",
        "tool_finished",
        "tool_collapsed",
        "tool_expanded",
        "decoded_json",
        "code_copy",
        "file_states",
        "supervisor",
        "alert",
        "stream_preview",
    )
    for name in cases:
        assert _compiled_semantics(_compiled_case_records(name)) == _fixture_semantics(expected[name]), name


def test_write_snapshot_requires_explicit_update_opt_in(tmp_path, monkeypatch):
    """An imported writer cannot mutate a baseline outside the update command."""
    target = tmp_path / "baseline.json"
    snapshots = {"case": [{"segments": [{"style": "", "text": "frozen"}], "widget": "Static#"}]}

    monkeypatch.delenv("CLOUDRA_UPDATE_TUI_SNAPSHOT", raising=False)
    with pytest.raises(PermissionError, match="CLOUDRA_UPDATE_TUI_SNAPSHOT=1"):
        write_snapshot(target, snapshots)
    assert not target.exists()

    monkeypatch.setenv("CLOUDRA_UPDATE_TUI_SNAPSHOT", "1")
    write_snapshot(target, snapshots)
    assert json.loads(target.read_text(encoding="utf-8")) == snapshots


@pytest.mark.asyncio
async def test_profile_harness_reports_a_bounded_workload():
    """The baseline profiler exposes the fixed legacy workload measurements."""
    from scripts.profile_textual_tui import run_profile

    result = await run_profile(history_count=2, stream_count=2, rounds=2)

    assert result.elapsed_seconds >= 0
    assert result.python_calls > 0
    assert result.max_commit_seconds >= 0
    assert result.input_p95_seconds >= 0
    assert result.child_count > 0
    assert result.record_count == 4


@pytest.mark.asyncio
async def test_profile_harness_drives_an_input_submission_each_round(monkeypatch):
    """The input latency sample includes the real submitted-input event path."""
    from scripts import profile_textual_tui as profile

    handled: list[str] = []
    original = getattr(profile._ProfileApp, "on_input_submitted", None)

    def capture_submission(self, event) -> None:
        handled.append(event.value)
        if original is not None:
            original(self, event)

    monkeypatch.setattr(profile._ProfileApp, "on_input_submitted", capture_submission, raising=False)
    await profile.run_profile(history_count=2, stream_count=2, rounds=2)

    assert handled == ["profile input 0", "profile input 1"]
