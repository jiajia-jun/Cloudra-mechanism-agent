"""Integration coverage for the single-widget virtual transcript surface."""

from __future__ import annotations

import asyncio
import threading

import pytest
from textual.app import App, ComposeResult

from cloudra.tui.new.widgets.virtual_chat_log import ChatLog as VirtualChatLog


class ChatOnlyApp(App[None]):
    def compose(self) -> ComposeResult:
        yield VirtualChatLog(id="chat-log")


@pytest.mark.asyncio
async def test_virtual_chat_dom_is_constant_for_one_thousand_records():
    """Message history stays addressable without growing Textual's DOM."""
    app = ChatOnlyApp()
    async with app.run_test(size=(100, 36)) as pilot:
        chat = app.query_one("#chat-log", VirtualChatLog)
        for index in range(1_000):
            chat.append_system(f"a-{index % 16}_task", f"event-{index}")

        await pilot.pause()

        assert chat.record_count == 1_000
        assert len(chat.children) == 0
        assert chat.virtual_size.height >= 1_000
        assert "event-999" in "\n".join(record.content for record in chat.store.records)


@pytest.mark.asyncio
async def test_virtual_chat_renders_first_middle_and_last_records_at_their_virtual_rows():
    """Breaking row lookup would make a virtual position render a blank or wrong record."""
    app = ChatOnlyApp()
    async with app.run_test(size=(100, 36)) as pilot:
        chat = app.query_one("#chat-log", VirtualChatLog)
        for index in range(1_000):
            chat.append_system("s1", f"event-{index}")

        await pilot.pause()
        for record_index in (0, 500, 999):
            record_id = chat.visible_record_ids[record_index]
            await chat.reveal(record_id)
            await chat.ensure_compiled(record_id)
            row_start = chat._heights.row_start(record_index)
            rows = "\n".join(
                "".join(segment.text for segment in chat.render_line(y))
                for y in range(max(0, row_start - int(chat.scroll_y)), row_start + 4 - int(chat.scroll_y))
            )
            assert f"event-{record_index}" in rows


@pytest.mark.asyncio
async def test_virtual_chat_queues_compilation_when_the_viewport_scrolls():
    """A user scroll must request rows for the newly exposed virtual region."""
    app = ChatOnlyApp()
    async with app.run_test(size=(100, 36)) as pilot:
        chat = app.query_one("#chat-log", VirtualChatLog)
        for index in range(100):
            chat.append_system("s1", f"event-{index}")
        await pilot.pause()

        chat._frame_scheduler.cancel()
        chat.scroll_to(y=chat._heights.row_start(50), animate=False, immediate=True)

        assert chat._frame_scheduler.pending


@pytest.mark.asyncio
async def test_virtual_chat_cancels_stale_compile_when_a_record_revision_changes():
    """A renamed streaming record cannot leave an obsolete render task active."""
    app = ChatOnlyApp()
    async with app.run_test(size=(100, 36)) as pilot:
        chat = app.query_one("#chat-log", VirtualChatLog)
        handle = chat.append_stream_chunk("pending", "draft")
        await pilot.pause()
        stale = asyncio.create_task(asyncio.sleep(60))
        chat._compile_tasks[handle.record_id] = stale

        chat.rename_session("pending", "s1")
        await asyncio.sleep(0)

        assert stale.cancelled()


@pytest.mark.asyncio
async def test_virtual_chat_batch_preserves_the_append_and_filter_facade():
    """Batched legacy writes still expose complete session records without children."""
    app = ChatOnlyApp()
    async with app.run_test(size=(100, 36)) as pilot:
        chat = app.query_one("#chat-log", VirtualChatLog)
        with chat.batch_update():
            chat.append_user("s1", "question", message_id="m1")
            chat.append_reasoning_chunk("s1", "thinking", "Agent")
            chat.append_stream_chunk("s1", "answer", "Agent")
            chat.end_stream("s1")
            chat.append_tool("s2", "Bash", "pwd", finished=True, result="/tmp")

        await pilot.pause()
        assert len(chat.visible_record_ids) == 3
        chat.show_session("s1")

        assert chat.has_records
        assert chat.record_count == 3
        assert [record.content for record in chat.records_for_session("s1")] == [
            "question",
            "answer",
        ]
        assert chat.text_for_session("s1") == "question\nthinking\nanswer"
        assert len(chat.visible_record_ids) == 2
        assert len(chat.children) == 0


@pytest.mark.asyncio
async def test_virtual_chat_unmount_releases_its_compiler_threads():
    """A closed app must not leak render workers into the next Textual session."""
    app = ChatOnlyApp()
    async with app.run_test(size=(100, 36)) as pilot:
        chat = app.query_one("#chat-log", VirtualChatLog)
        for index in range(1_000):
            chat.append_system("s1", f"close safely {index}")
        await pilot.pause()

    assert not any(thread.name.startswith("cloudra-tui-render") for thread in threading.enumerate())
