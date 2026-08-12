"""Coordinator 历史回放事件截断：优先保留非 stream 事件。"""

from cloudra.tui.new.screens.main_screen import _select_history_events


def test_select_history_events_prefers_tools_over_chunks():
    events = []
    for i in range(200):
        events.append({"event_type": "llm_chunk", "data": {"i": i}})
    events.append({"event_type": "tool_started", "data": {"tool": "stop"}})
    events.append({"event_type": "tool_finished", "data": {"tool": "stop"}})
    events.append({"event_type": "phase", "data": {"phase": "waiting"}})

    selected = _select_history_events(events, limit=10)
    types = [e["event_type"] for e in selected]

    assert "tool_started" in types
    assert "tool_finished" in types
    assert "phase" in types
    assert types.count("llm_chunk") == 7
    # 保持原始相对顺序
    assert types.index("tool_started") < types.index("tool_finished")
    assert types.index("tool_finished") < types.index("phase")
