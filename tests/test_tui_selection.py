"""Text selection support on the virtual chat log.

The chat log hooks into Textual's built-in selection machinery: rendered rows
carry content-offset metadata, ``get_selection`` extracts the selected text,
and copying goes through ``App.copy_to_clipboard`` (OSC52) without any external
clipboard tool.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

import pytest
from textual.app import App, ComposeResult
from textual.geometry import Offset
from textual.selection import SELECT_ALL, Selection

from cloudra.tui.new.widgets.virtual_chat_log import ChatLog as VirtualChatLog


class ChatOnlyApp(App[None]):
    def __init__(self) -> None:
        super().__init__()
        self.chat = VirtualChatLog(id="chat-log")

    def compose(self) -> ComposeResult:
        yield self.chat

    @asynccontextmanager
    async def run_test(self, *args, **kwargs):
        async with super().run_test(*args, **kwargs) as pilot:
            try:
                yield pilot
            finally:
                if self.chat.is_attached:
                    await self.chat.remove()
                if self.chat._close_task is not None:
                    await self.chat._close_task


@pytest.mark.asyncio
async def test_rendered_rows_carry_content_offset_metadata():
    """Every rendered cell must expose its (x, y) content offset for hit-testing."""
    app = ChatOnlyApp()
    async with app.run_test(size=(80, 24)):
        chat = app.chat
        handle = chat.append_system("s1", "hello world")
        await chat.ensure_compiled(handle.record_id)

        strip = chat.render_line(0)
        offsets = [
            segment.style.meta["offset"]
            for segment in strip
            if segment.style is not None and "offset" in segment.style.meta
        ]
        assert offsets, "rendered strip has no selection offset metadata"
        # Offsets start at column 0 of virtual row 0 and advance monotonically.
        assert offsets[0] == (0, 0)
        assert all(y == 0 for _, y in offsets)
        assert [x for x, _ in offsets] == sorted(x for x, _ in offsets)


@pytest.mark.asyncio
async def test_get_selection_extracts_single_line_span():
    app = ChatOnlyApp()
    async with app.run_test(size=(80, 24)):
        chat = app.chat
        handle = chat.append_system("s1", "hello world")
        await chat.ensure_compiled(handle.record_id)

        row, line_text = next(
            (y, chat.render_line(y).text.rstrip())
            for y in range(chat._heights.total)
            if "hello" in chat.render_line(y).text
        )
        start = line_text.index("hello")
        stop = start + len("hello")
        result = chat.get_selection(Selection(Offset(start, row), Offset(stop, row)))
        assert result is not None
        assert result[0] == "hello"


@pytest.mark.asyncio
async def test_get_selection_spans_multiple_records():
    app = ChatOnlyApp()
    async with app.run_test(size=(80, 24)):
        chat = app.chat
        first = chat.append_system("s1", "first message")
        second = chat.append_system("s1", "second message")
        await chat.ensure_compiled(first.record_id)
        await chat.ensure_compiled(second.record_id)

        total = chat._heights.total
        assert total >= 2
        # Select from the start of the first row to the end of the last row.
        result = chat.get_selection(SELECT_ALL)
        assert result is not None
        text = result[0]
        assert "first message" in text
        assert "second message" in text

        # A partial span starting mid-first-row must clip the prefix.
        first_row, first_line = next(
            (y, chat.render_line(y).text.rstrip())
            for y in range(total)
            if "first" in chat.render_line(y).text
        )
        start = first_line.index("first")
        last_line = chat.render_line(total - 1).text.rstrip()
        partial = chat.get_selection(
            Selection(Offset(start, first_row), Offset(len(last_line), total - 1))
        )
        assert partial is not None
        assert partial[0].startswith("first message")


@pytest.mark.asyncio
async def test_selection_highlight_is_applied_at_render_time():
    app = ChatOnlyApp()
    async with app.run_test(size=(80, 24)):
        chat = app.chat
        handle = chat.append_system("s1", "highlight me")
        await chat.ensure_compiled(handle.record_id)

        plain = chat.render_line(0)
        app.screen.selections = {chat: SELECT_ALL}
        highlighted = chat.render_line(0)
        try:
            selection_style = app.screen.get_component_rich_style("screen--selection")
            plain_bg = [
                segment.style.bgcolor for segment in plain if segment.style is not None
            ]
            highlighted_bg = [
                segment.style.bgcolor
                for segment in highlighted
                if segment.style is not None
            ]
            assert selection_style.bgcolor is not None
            assert any(bg == selection_style.bgcolor for bg in highlighted_bg)
            assert highlighted_bg != plain_bg
        finally:
            app.screen.selections = {}


@pytest.mark.asyncio
async def test_selection_preserves_line_content():
    """Regression: Strip.divide yields no trailing piece by itself; selecting a
    span must not drop the rest of the line (selected text "disappears")."""
    app = ChatOnlyApp()
    async with app.run_test(size=(80, 24)):
        chat = app.chat
        handle = chat.append_system("s1", "keep everything visible")
        await chat.ensure_compiled(handle.record_id)

        row, line_text = next(
            (y, chat.render_line(y).text)
            for y in range(chat._heights.total)
            if "keep" in chat.render_line(y).text
        )
        start = line_text.index("keep")
        stop = start + 4
        app.screen.selections = {
            chat: Selection(Offset(start, row), Offset(stop, row))
        }
        try:
            assert chat.render_line(row).text == line_text
        finally:
            app.screen.selections = {}


@pytest.mark.asyncio
async def test_highlight_cells_match_cjk_selection():
    """Regression: selection spans are character offsets while strip cuts are
    cell offsets — with CJK (wide) characters the highlight must still cover
    exactly the text that get_selection extracts."""
    from rich.cells import cell_len

    app = ChatOnlyApp()
    async with app.run_test(size=(80, 24)):
        chat = app.chat
        handle = chat.append_system("s1", "你好世界 hello 选中测试")
        await chat.ensure_compiled(handle.record_id)

        row, line_text = next(
            (y, chat.render_line(y).text.rstrip())
            for y in range(chat._heights.total)
            if "你好" in chat.render_line(y).text
        )
        start = line_text.index("世界")
        stop = line_text.index("选中")
        selection = Selection(Offset(start, row), Offset(stop, row))
        app.screen.selections = {chat: selection}
        try:
            extracted, _ = chat.get_selection(selection)
            assert extracted == "世界 hello "

            selection_style = app.screen.get_component_rich_style("screen--selection")
            highlighted_cells: list[int] = []
            x = 0
            for segment in chat.render_line(row):
                for char in segment.text:
                    if (
                        segment.style is not None
                        and segment.style.bgcolor == selection_style.bgcolor
                        and segment.style.color == selection_style.color
                    ):
                        highlighted_cells.append(x)
                    x += cell_len(char)
            expected = (cell_len(line_text[:start]), cell_len(line_text[:stop]))
            assert (min(highlighted_cells), max(highlighted_cells) + 1) == expected
        finally:
            app.screen.selections = {}


@pytest.mark.asyncio
async def test_selection_style_overrides_segment_colors():
    """Regression: the selection colors must sit on top of record/syntax
    colors, otherwise colored text stays invisible against the highlight."""
    app = ChatOnlyApp()
    async with app.run_test(size=(80, 24)):
        chat = app.chat
        code = chat.start_stream("s1", "Agent")
        chat.append_stream_chunk("s1", "```python\nprint('hi')  # 注释\n```")
        chat.end_stream("s1")
        await chat.ensure_compiled(code.record_id)

        row, line_text = next(
            (y, chat.render_line(y).text.rstrip())
            for y in range(chat._heights.total)
            if "print" in chat.render_line(y).text
        )
        start = line_text.index("print")
        app.screen.selections = {
            chat: Selection(Offset(start, row), Offset(start + 5, row))
        }
        try:
            selection_style = app.screen.get_component_rich_style("screen--selection")
            segment = next(
                segment
                for segment in chat.render_line(row)
                if "print" in segment.text
            )
            assert segment.style.bgcolor == selection_style.bgcolor
            assert segment.style.color == selection_style.color
        finally:
            app.screen.selections = {}


@pytest.mark.asyncio
async def test_screen_copy_text_routes_through_osc52_clipboard():
    """Screen's built-in ctrl+c path must copy the chat selection via the app."""
    app = ChatOnlyApp()
    async with app.run_test(size=(80, 24)):
        chat = app.chat
        handle = chat.append_system("s1", "copy me")
        await chat.ensure_compiled(handle.record_id)

        line_row, line_text = next(
            (y, chat.render_line(y).text.rstrip())
            for y in range(chat._heights.total)
            if "copy me" in chat.render_line(y).text
        )
        start = line_text.index("copy")
        app.screen.selections = {
            chat: Selection(Offset(start, line_row), Offset(start + len("copy me"), line_row))
        }
        selected = app.screen.get_selected_text()
        assert selected is not None and "copy me" in selected

        app.screen.action_copy_text()
        assert "copy me" in app.clipboard


@pytest.mark.asyncio
async def test_right_click_copies_selection_and_clears_it():
    """Right click copies the active selection (OSC52) then clears the highlight."""
    app = ChatOnlyApp()
    async with app.run_test(size=(80, 24)) as pilot:
        chat = app.chat
        handle = chat.append_system("s1", "right click copy test")
        await chat.ensure_compiled(handle.record_id)
        await pilot.pause()

        row, line_text = next(
            (y, chat.render_line(y).text)
            for y in range(chat._heights.total)
            if "right click" in chat.render_line(y).text
        )
        col = line_text.index("right click")
        await pilot.mouse_down(chat, offset=(col, row))
        await pilot.hover(chat, offset=(col + 11, row))
        await pilot.mouse_up(chat, offset=(col + 11, row))
        await pilot.pause()
        assert app.screen.selections

        app._clipboard = ""
        await pilot.mouse_down(chat, offset=(col, row), button=3)
        await pilot.mouse_up(chat, offset=(col, row))
        await pilot.pause()
        assert "right click" in app.clipboard
        assert not app.screen.selections


def test_cloudra_theme_defines_readable_selection_colors():
    """Regression: without explicit variables both selection colors collapse to
    the theme primary and selected text becomes invisible."""
    from cloudra.tui.new.app import _CLOUDRA_THEME

    background = _CLOUDRA_THEME.variables.get("screen-selection-background")
    foreground = _CLOUDRA_THEME.variables.get("screen-selection-foreground")
    assert background and foreground
    assert background != foreground


@pytest.mark.asyncio
async def test_ctrl_c_with_input_focused_copies_chat_selection(tmp_path, monkeypatch):
    """The input box owns ctrl+c when focused; it must fall through to the chat
    selection when the input itself has no selection, then clear the highlight."""
    from cloudra.config import get_config, reload_config
    from cloudra.tui.new.app import CloudraTextualApp

    monkeypatch.setenv("CLOUDRA_DATA_DIR", str(tmp_path / "data"))
    reload_config()
    get_config()._ensure_dirs()

    app = CloudraTextualApp()
    async with app.run_test(size=(90, 30)) as pilot:
        screen = app.screen
        chat = screen.query_one("#chat-log", VirtualChatLog)
        handle = chat.append_system("s1", "copy via input focus")
        await chat.ensure_compiled(handle.record_id)
        await pilot.pause()

        screen.selections = {chat: SELECT_ALL}
        # The input box holds the default focus and swallows ctrl+c without the
        # delegation in SubmitTextArea.action_copy.
        await pilot.press("ctrl+c")
        await pilot.pause()
        assert "copy via input focus" in app.clipboard
        assert not screen.selections
