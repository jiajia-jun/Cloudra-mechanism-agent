"""Fixture-backed characterization tests for the legacy Textual presentation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.tui_visual_cases import VISUAL_CASES, VisualCaseApp, semantic_snapshot, write_snapshot


FIXTURE = Path(__file__).parent / "fixtures" / "tui_visual_baseline.json"


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
