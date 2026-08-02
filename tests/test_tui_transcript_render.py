"""Behavioral contracts for immutable transcript row compilation."""

from __future__ import annotations

import pytest
from rich.console import Console

from cloudra.tui.new.transcript import RecordKind, TranscriptStore
from cloudra.tui.new.transcript_render import (
    InteractionAction,
    RenderContext,
    compile_record,
    semantic_segments,
)


def render_context() -> RenderContext:
    return RenderContext(Console(width=92, force_terminal=True, color_system="truecolor"))


def rendered_text(compiled) -> str:
    return "\n".join(strip.text for strip in compiled.strips)


def rendered_styles(compiled) -> str:
    return " ".join(style for row in semantic_segments(compiled) for _, style in row)


def test_tool_json_is_decoded_collapsed_and_clickable():
    """A formatted long result remains toggleable instead of exposing escapes."""
    store = TranscriptStore()
    handle = store.append_tool(
        "s1",
        "SubAgentLauncher",
        '{"query":"调研"}',
        finished=True,
        result='{"result":"\\u6211\\u5b8c\\u6210\\u4e86\\n' + "x\\n" * 12 + '"}',
    )

    compiled = compile_record(store.get(handle), 92, render_context())

    text = rendered_text(compiled)
    assert "我完成了" in text and "\\u" not in text and "点击展开/收起" in text
    assert any(region.action is InteractionAction.TOGGLE_TOOL for region in compiled.regions)


def test_code_block_has_highlighted_rows_and_copy_region():
    """Fenced code keeps syntax styling and exposes the actual source to copy."""
    store = TranscriptStore()
    handle = store.start_stream("s1", "Agent")
    store.append_stream_chunk("s1", "```python\nprint('hi')\n```")
    store.end_stream("s1")

    compiled = compile_record(store.get(handle), 92, render_context())

    assert any("print" in strip.text for strip in compiled.strips)
    assert "#272822" in rendered_styles(compiled)
    regions = [region for region in compiled.regions if region.action is InteractionAction.COPY_CODE]
    assert len(regions) == 1 and regions[0].payload == "print('hi')"
    copy_region = regions[0]
    copy_row = compiled.row(copy_region.y)
    assert "复制" in copy_row.text
    assert copy_region.x == compiled.width - 4 and copy_region.width == 4


def test_system_user_divider_and_alert_keep_their_legacy_semantics():
    """Changing a record kind must not collapse its distinct presentation treatment."""
    store = TranscriptStore()
    system = store.append_system("s1", "准备计算")
    user = store.append_user("s1", "请继续")
    store.mark_send_failed(user)
    divider = store.append_divider("s1", "── 新任务 ──")
    alert = store.append_alert("s1", "任务失败", "Gaussian 未收敛。", style="red")

    compiled_system = compile_record(store.get(system), 92, render_context())
    compiled_user = compile_record(store.get(user), 92, render_context())
    compiled_divider = compile_record(store.get(divider), 92, render_context())
    compiled_alert = compile_record(store.get(alert), 92, render_context())

    assert "系统" in rendered_text(compiled_system) and "准备计算" in rendered_text(compiled_system)
    assert "blue" in rendered_styles(compiled_system)
    assert rendered_text(compiled_user).strip() == "» 请继续"
    assert "dim" in rendered_styles(compiled_user) and "strike" in rendered_styles(compiled_user)
    assert rendered_text(compiled_divider).strip() == "── 新任务 ──"
    assert "bright_black" in rendered_styles(compiled_divider)
    assert "任务失败" in rendered_text(compiled_alert) and "Gaussian 未收敛。" in rendered_text(compiled_alert)
    assert "red" in rendered_styles(compiled_alert)


def test_assistant_reasoning_markdown_and_stream_preview_keep_their_distinct_forms():
    """Final content renders fully, whereas only active streams use tail previews."""
    store = TranscriptStore()
    finished = store.start_stream("s1", "Agent")
    store.append_reasoning_chunk("s1", "先检查收敛条件。")
    store.append_stream_chunk("s1", "# 结果\n\n- 能量降低")
    store.end_stream("s1")
    streaming = store.start_stream("s2", "Agent")
    store.append_reasoning_chunk("s2", "old-" + "r" * 900)
    store.append_stream_chunk("s2", "old-" + "c" * 2100)

    compiled_finished = compile_record(store.get(finished), 92, render_context())
    compiled_streaming = compile_record(store.get(streaming), 92, render_context())

    assert "思考过程" in rendered_text(compiled_finished)
    assert "italic bright_black" in rendered_styles(compiled_finished)
    assert "结果" in rendered_text(compiled_finished) and "bold underline" in rendered_styles(compiled_finished)
    assert "能量降低" in rendered_text(compiled_finished)
    stream_text = rendered_text(compiled_streaming)
    assert "… 较早的思考过程已暂时折叠 …" in stream_text
    assert "… 正在生成，仅显示末尾 …" in stream_text
    assert "old-" not in stream_text


@pytest.mark.parametrize(
    ("status", "icon", "style"),
    [
        ("applied", "√", "green"),
        ("proposed", "※", "yellow"),
        ("declined", "○", "dim"),
        ("failed", "×", "red"),
    ],
)
def test_file_statuses_keep_their_panel_icon_and_colour(status, icon, style):
    """Each file outcome remains distinguishable when widgets are removed."""
    store = TranscriptStore()
    handle = store.append_file_change("s1", "calc/result.py", status)

    compiled = compile_record(store.get(handle), 92, render_context())

    assert f"{icon} calc/result.py" in rendered_text(compiled)
    assert style in rendered_styles(compiled)


def test_supervisor_and_tool_states_keep_their_legacy_cards():
    """Tool state, short results, and expanded long results stay semantically separate."""
    store = TranscriptStore()
    supervisor = store.append_supervisor_review("s1", "通过", "计算设置与结果一致。")
    running = store.append_tool("s1", "Bash", "pwd")
    short = store.append_tool("s1", "Bash", "echo", finished=True, result="/tmp/project")
    long = store.append_tool("s1", "Bash", "pytest", finished=True, result="\n".join(f"line {i}" for i in range(12)))
    store.toggle_collapsed(long)

    compiled_supervisor = compile_record(store.get(supervisor), 92, render_context())
    compiled_running = compile_record(store.get(running), 92, render_context())
    compiled_short = compile_record(store.get(short), 92, render_context())
    compiled_long = compile_record(store.get(long), 92, render_context())

    assert "Supervisor 审查" in rendered_text(compiled_supervisor)
    assert "结论: 通过" in rendered_text(compiled_supervisor) and "magenta" in rendered_styles(compiled_supervisor)
    assert "▶ Bash" in rendered_text(compiled_running) and "yellow" in rendered_styles(compiled_running)
    assert "/tmp/project" in rendered_text(compiled_short) and "√ Bash" in rendered_text(compiled_short)
    assert "line 11" in rendered_text(compiled_long)
    assert "点击展开/收起" not in rendered_text(compiled_long)
    assert any(region.action is InteractionAction.TOGGLE_TOOL for region in compiled_long.regions)


def test_compiled_rows_are_immutable_128_row_blocks_after_a_large_result():
    """Large derived output is chunked without changing the stored record."""
    store = TranscriptStore()
    handle = store.append("s1", RecordKind.ASSISTANT, content="\n".join(f"line {i}" for i in range(300)), status="finished")
    record = store.get(handle)

    compiled = compile_record(record, 92, render_context())

    assert tuple(len(block) for block in compiled.blocks[:-1]) == (128, 128)
    assert compiled.row(299).text.strip() == "line 299"
    assert store.get(handle) == record
