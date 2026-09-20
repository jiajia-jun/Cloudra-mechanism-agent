"""Frontend SSE listener list must cover live event types the UI consumes."""

from pathlib import Path

_API_TS = Path(__file__).resolve().parents[1] / "frontend" / "src" / "api.ts"


def test_sse_whitelist_includes_tool_requested_and_program_lifecycle():
    text = _API_TS.read_text(encoding="utf-8")
    start = text.index("const KNOWN_EVENT_TYPES")
    block = text[start : text.index("];", start)]
    for event_type in (
        "tool.requested",
        "tool.result_recorded",
        "program.submitted",
        "program.started",
        "program.output",
        "program.finished",
        "agent.completion_gate",
    ):
        assert f"'{event_type}'" in block, event_type
