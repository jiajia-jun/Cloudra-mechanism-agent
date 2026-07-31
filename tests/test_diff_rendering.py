from rich.console import Console

from cloudra.tui.render import EventRenderer, _diff_preview_lines
from cloudra.ui.app import _event_payload, _format_file_event


class _App:
    phase = ""
    session_id = "session"

    def invalidate(self):
        pass


def test_tui_turn_diff_uses_unified_diff_colors():
    console = Console(record=True, color_system="standard", width=120)
    renderer = EventRenderer(console, _App())
    renderer.dispatch(
        {
            "kind": "session_event",
            "event_type": "turn_diff_updated",
            "data": {
                "diff": "--- a/a.py\n+++ b/a.py\n@@ -1 +1 @@\n-old\n+new\n",
            },
        }
    )

    plain = console.export_text(clear=False)
    ansi = console.export_text(styles=True)
    assert "本轮文件差异" in plain
    assert "-old" in plain
    assert "+new" in plain
    assert "\x1b[31m-old" in ansi
    assert "\x1b[32m+new" in ansi


def test_tui_diff_preview_is_bounded():
    lines, truncated = _diff_preview_lines("\n".join(str(i) for i in range(200)), 10)
    assert len(lines) == 10
    assert truncated is True


def test_gui_file_event_formats_safe_markdown_diff():
    content = _format_file_event(
        "file_change_proposed",
        {
            "path": "strange`name.py",
            "additions": 1,
            "deletions": 1,
            "diff": "--- a/x\n+++ b/x\n-```\n+value\n",
        },
    )

    assert content is not None
    assert "**候选文件变更**" in content
    assert "strange`name.py" in content
    assert "````diff" in content
    assert "-```" in content


def test_non_file_event_falls_back_to_generic_rendering():
    assert _format_file_event("tool_started", {"tool": "x"}) is None


def test_gui_accepts_flat_and_legacy_nested_ipc_payloads():
    flat = {"kind": "session_event", "event_type": "llm_chunk", "data": {"delta": "x"}}
    nested = {"kind": "session_event", "payload": {"event_type": "llm_chunk"}}

    assert _event_payload(flat) is flat
    assert _event_payload(nested) == {"event_type": "llm_chunk"}
