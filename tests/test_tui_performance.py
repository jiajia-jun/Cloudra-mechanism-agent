"""Integration coverage for the single-widget virtual transcript surface."""

from __future__ import annotations

import asyncio
import threading
from contextlib import asynccontextmanager

import pytest
from rich.segment import Segment
from textual.app import App, ComposeResult
from textual.events import Resize
from textual.geometry import Size
from textual.strip import Strip

from cloudra.tui.new import transcript_render
from cloudra.tui.new.virtual_lines import restore_anchor
from cloudra.tui.new.widgets.virtual_chat_log import ChatLog as VirtualChatLog


class ChatOnlyApp(App[None]):
    def __init__(self, chat: VirtualChatLog | None = None) -> None:
        super().__init__()
        self.chat = chat or VirtualChatLog(id="chat-log")

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
async def test_virtual_chat_mounts_history_appended_before_the_active_app_exists():
    """Offline history loads stay inert, then become visible during the first mount."""
    chat = VirtualChatLog(id="chat-log")
    handle = chat.append_system("s1", "loaded before mount")

    app = ChatOnlyApp(chat)
    async with app.run_test(size=(100, 36)) as pilot:
        await pilot.pause()

        assert handle.record_id == 1
        assert chat.record_count == 1
        assert chat.visible_record_ids == (handle.record_id,)
        assert chat.virtual_size.height >= 1


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
async def test_virtual_chat_tail_appends_do_not_rebuild_the_height_index(monkeypatch):
    """A long history append must be incremental, not re-filtered/re-indexed each time."""
    app = ChatOnlyApp()
    async with app.run_test(size=(100, 36)) as pilot:
        chat = app.query_one("#chat-log", VirtualChatLog)
        rebuilds = 0
        rebuild = chat._heights.rebuild

        def count_rebuild(heights):
            nonlocal rebuilds
            rebuilds += 1
            return rebuild(heights)

        chat._heights.rebuild = count_rebuild
        records_type = type(chat.store)

        def reject_full_snapshot(_store):
            raise AssertionError("tail append copied the complete transcript")

        monkeypatch.setattr(records_type, "records", property(reject_full_snapshot))
        for index in range(1_000):
            chat.append_system("s1", f"event-{index}")
        await pilot.pause()

        assert rebuilds == 0
        assert chat.record_count == len(chat.visible_record_ids) == 1_000


@pytest.mark.asyncio
async def test_virtual_chat_bounds_a_single_huge_record_cache_by_128_row_chunks(monkeypatch):
    """One 5,000-row record cannot evade the 4,096-row derived-cache ceiling."""
    def compile_tall_record(record, width, _context):
        lines = record.content.splitlines()
        filler = Strip((Segment("filler"),), 6)
        rows = [filler] * len(lines)
        for index in (0, 2_560, 5_000):
            rows[index] = Strip((Segment(lines[index]),), len(lines[index]))
        blocks = tuple(tuple(rows[start : start + 128]) for start in range(0, len(rows), 128))
        return transcript_render.CompiledRecord(
            record.record_id, record.revision, width, blocks
        )

    monkeypatch.setattr(transcript_render, "compile_record", compile_tall_record)
    app = ChatOnlyApp()
    async with app.run_test(size=(100, 36)) as pilot:
        chat = app.query_one("#chat-log", VirtualChatLog)
        complete_content = "\n".join(f"line-{index}" for index in range(5_001))
        handle = chat.append_stream_chunk("s1", complete_content)
        chat.end_stream("s1")

        await asyncio.wait_for(chat.ensure_compiled(handle.record_id), timeout=5)
        await pilot.pause()
        await asyncio.wait_for(chat.ensure_compiled(handle.record_id), timeout=5)

        height = chat._heights.height(0)
        assert height == 5_001
        assert chat.store.get(handle).content == complete_content
        assert chat.store.get(handle).status == "finished"

        assert "line-0" in chat.render_line(0).text

        chat.scroll_y = 2_540
        chat._flush_frame()
        assert {19, 20} <= chat._wanted_blocks[handle.record_id]
        task = chat._compile_tasks.get(handle.record_id)
        assert task is not None
        await asyncio.wait_for(asyncio.shield(task), timeout=5)
        middle_viewport_row = 2_560 - int(chat.scroll_y)
        assert "line-2560" in chat.render_line(middle_viewport_row).text

        chat.scroll_y = chat.max_scroll_y
        chat._flush_frame()
        assert {38, 39} <= chat._wanted_blocks[handle.record_id]
        task = chat._compile_tasks.get(handle.record_id)
        assert task is not None
        await asyncio.wait_for(asyncio.shield(task), timeout=5)
        last_viewport_row = height - 1 - int(chat.scroll_y)
        assert "line-5000" in chat.render_line(last_viewport_row).text
        assert chat._cached_rows <= chat.MAX_CACHED_ROWS


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
                for y in range(
                    max(0, row_start - int(chat.scroll_y)),
                    row_start + 4 - int(chat.scroll_y),
                )
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
async def test_virtual_chat_limits_active_compiles_and_queues_the_rest():
    """Viewport work must remain in a surface queue instead of spawning one task per row."""
    app = ChatOnlyApp()
    async with app.run_test(size=(100, 400)) as pilot:
        chat = app.query_one("#chat-log", VirtualChatLog)
        for index in range(100):
            chat.append_system("s1", f"event-{index}")
        chat._flush_frame()

        assert len(chat._compile_tasks) <= 2
        assert len(chat._compile_queue) > 0

        for record_id in chat.visible_record_ids:
            assert await chat.ensure_compiled(record_id) is not None
            assert chat._active_compile_count() <= 2

        width = chat._content_width()
        assert all(
            chat._cached_block(record_id, width, 0) is not None
            for record_id in chat.visible_record_ids
        )
        assert "event-99" in "\n".join(
            row.text for rows in chat._compiled.values() for row in rows
        )


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
async def test_virtual_chat_replaces_a_queued_stale_revision_with_latest_work(monkeypatch):
    """A queued record is deduplicated and replaced before a worker slot opens."""
    loop = asyncio.get_running_loop()
    first_started, second_started = asyncio.Event(), asyncio.Event()
    release = threading.Event()
    original = transcript_render.compile_record

    def blocked_compile(record, *args):
        if record.content == "block-one":
            loop.call_soon_threadsafe(first_started.set)
            release.wait()
        elif record.content == "block-two":
            loop.call_soon_threadsafe(second_started.set)
            release.wait()
        return original(record, *args)

    monkeypatch.setattr(transcript_render, "compile_record", blocked_compile)
    app = ChatOnlyApp()
    async with app.run_test(size=(100, 36)):
        chat = app.query_one("#chat-log", VirtualChatLog)
        first = chat.append_system("s1", "block-one")
        second = chat.append_system("s2", "block-two")
        chat._schedule_record(first.record_id)
        chat._schedule_record(second.record_id)
        await asyncio.wait_for(first_started.wait(), timeout=1)
        await asyncio.wait_for(second_started.wait(), timeout=1)

        target = chat.append_stream_chunk("s3", "queued-old")
        chat._schedule_record(target.record_id)
        assert target.record_id in chat._compile_queue

        try:
            chat.append_stream_chunk("s3", "-new")
            queued_record, queued_width, queued_generation = chat._compile_queue[
                target.record_id
            ]
            current = chat.store.get(target)

            assert queued_record.revision == current.revision
            assert queued_record.content == "queued-old-new"
            assert queued_width == chat._content_width()
            assert queued_generation == chat._generation
            assert tuple(chat._compile_queue).count(target.record_id) == 1
        finally:
            release.set()

        assert await chat.ensure_compiled(target.record_id) is not None
        assert "queued-old-new" in "\n".join(
            row.text for rows in chat._compiled.values() for row in rows
        )


@pytest.mark.asyncio
async def test_virtual_chat_drains_latest_revision_after_a_cancelled_admission(monkeypatch):
    """A cancelled active render holds its slot until its worker admission drains."""
    loop = asyncio.get_running_loop()
    started, release = asyncio.Event(), threading.Event()
    original = transcript_render.compile_record

    def blocked_compile(*args):
        loop.call_soon_threadsafe(started.set)
        release.wait()
        return original(*args)

    monkeypatch.setattr(transcript_render, "compile_record", blocked_compile)
    app = ChatOnlyApp()
    async with app.run_test(size=(100, 36)) as pilot:
        chat = app.query_one("#chat-log", VirtualChatLog)
        handle = chat.append_stream_chunk("s1", "old")
        chat._flush_frame()
        await asyncio.wait_for(started.wait(), timeout=1)

        chat.append_stream_chunk("s1", " new")
        assert len(chat._compile_tasks) + len(chat._retiring_tasks) <= 2

        release.set()
        compiled = await chat.ensure_compiled(handle.record_id)

        assert compiled is not None
        assert "old new" in "\n".join(
            row.text for rows in chat._compiled.values() for row in rows
        )


@pytest.mark.asyncio
async def test_virtual_chat_drains_queue_when_a_retirement_releases_one_of_two_slots(
    monkeypatch,
):
    """A retired revision must immediately hand its free slot to queued latest work."""
    loop = asyncio.get_running_loop()
    first_started, second_started, latest_started = (
        asyncio.Event(),
        asyncio.Event(),
        asyncio.Event(),
    )
    first_release, second_release = threading.Event(), threading.Event()
    original = transcript_render.compile_record

    def blocked_compile(record, *args):
        if record.content == "first-old":
            loop.call_soon_threadsafe(first_started.set)
            first_release.wait()
        elif record.content == "second-blocked":
            loop.call_soon_threadsafe(second_started.set)
            second_release.wait()
        elif record.content == "first-old-new":
            loop.call_soon_threadsafe(latest_started.set)
        return original(record, *args)

    monkeypatch.setattr(transcript_render, "compile_record", blocked_compile)
    app = ChatOnlyApp()
    async with app.run_test(size=(100, 36)):
        chat = app.query_one("#chat-log", VirtualChatLog)
        first = chat.append_stream_chunk("s1", "first-old")
        second = chat.append_system("s2", "second-blocked")
        chat._schedule_record(first.record_id)
        chat._schedule_record(second.record_id)
        await asyncio.wait_for(first_started.wait(), timeout=1)
        await asyncio.wait_for(second_started.wait(), timeout=1)

        try:
            chat.append_stream_chunk("s1", "-new")
            assert first.record_id in chat._compile_queue
            first_release.set()

            await asyncio.wait_for(latest_started.wait(), timeout=1)
            assert not second_release.is_set()
            assert chat._active_compile_count() <= 2
        finally:
            first_release.set()
            second_release.set()

        compiled = await chat.ensure_compiled(first.record_id)
        assert compiled is not None
        assert await chat.ensure_compiled(second.record_id) is not None
        assert chat.store.get(first).content == "first-old-new"


@pytest.mark.asyncio
async def test_virtual_chat_clear_removes_height_chunk_and_cache_metadata():
    """Cleared records cannot remain as invisible measured or cached rows."""
    app = ChatOnlyApp()
    async with app.run_test(size=(100, 36)) as pilot:
        chat = app.query_one("#chat-log", VirtualChatLog)
        first = chat.append_system("s1", "first")
        second = chat.append_system("s2", "second")
        await pilot.pause()
        await chat.ensure_compiled(first.record_id)
        await chat.ensure_compiled(second.record_id)

        chat.clear_session("s1")

        assert first.record_id not in chat._measured_heights
        assert first.record_id not in chat._wanted_blocks
        assert all(key[0] != first.record_id for key in chat._compiled)
        assert first.record_id not in chat._compile_queue
        assert first.record_id not in chat._compile_jobs
        assert chat.visible_record_ids == (second.record_id,)

        chat.clear_all()

        assert chat._measured_heights == {}
        assert chat._wanted_blocks == {}
        assert chat._compiled == {}
        assert chat._cached_rows == 0
        assert chat._compile_queue == {}
        assert chat._compile_jobs == {}
        assert chat.visible_record_ids == ()
        assert chat._positions == {}
        assert chat._heights.total == 0


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
async def test_virtual_chat_remove_returns_before_an_admitted_compile_finishes(monkeypatch):
    """A real unmount gates frames, then closes the admitted worker after its release."""
    loop = asyncio.get_running_loop()
    started, release = asyncio.Event(), threading.Event()
    original = transcript_render.compile_record

    def blocked_compile(*args):
        loop.call_soon_threadsafe(started.set)
        release.wait()
        return original(*args)

    monkeypatch.setattr(transcript_render, "compile_record", blocked_compile)
    app = ChatOnlyApp()
    async with app.run_test(size=(100, 36)):
        try:
            chat = app.query_one("#chat-log", VirtualChatLog)
            scheduler_events = []
            original_request = chat._frame_scheduler.request
            original_cancel = chat._frame_scheduler.cancel

            def record_request(*args, **kwargs):
                scheduler_events.append("request")
                return original_request(*args, **kwargs)

            def record_cancel():
                scheduler_events.append("cancel")
                return original_cancel()

            chat._frame_scheduler.request = record_request
            chat._frame_scheduler.cancel = record_cancel
            chat.append_system("s1", "close safely")
            chat._flush_frame()
            await asyncio.wait_for(started.wait(), timeout=1)
            scheduler_events.clear()
            await asyncio.wait_for(chat.remove(), timeout=1)
            assert chat._surface_closing
            assert scheduler_events == ["cancel"]
            assert not chat._frame_scheduler.pending
            assert chat._close_task is not None
            while chat._compiler._close_task is None:
                await asyncio.sleep(0)

            shutdown_calls = []
            executor = chat._compiler._executor
            original_shutdown = executor.shutdown

            def nonblocking_shutdown(*args, **kwargs):
                shutdown_calls.append((args, kwargs))

            executor.shutdown = nonblocking_shutdown
            chat._close_task.cancel()
            responsive = asyncio.Event()
            loop.call_soon(responsive.set)
            await asyncio.wait_for(responsive.wait(), timeout=1)
            await asyncio.sleep(0)
            assert shutdown_calls == []
            assert not chat._close_task.done()
        finally:
            if "executor" in locals():
                executor.shutdown = original_shutdown
            release.set()

        await chat._close_task
        assert chat._close_error is None
        assert not any(
            thread.name.startswith("cloudra-tui-render")
            for thread in threading.enumerate()
        )


@pytest.mark.asyncio
async def test_cancelled_compile_cannot_request_a_frame_after_the_closing_gate():
    """Teardown cancellation must not resurrect the frame scheduler."""
    chat = VirtualChatLog()
    handle = chat.store.append_system("s1", "closing")
    record = chat.store.get(handle)
    started = asyncio.Event()
    calls = []

    async def blocked_compile(*_args):
        started.set()
        await asyncio.Event().wait()

    chat._compiler.compile = blocked_compile
    chat.request_frame = lambda **_kwargs: calls.append("frame")
    task = asyncio.create_task(chat._compile_record(record, 80, 0))
    await started.wait()
    chat._surface_closing = True
    task.cancel()
    await task

    assert calls == []


from cloudra.tui.new.transcript_render import InteractionAction


@pytest.mark.asyncio
async def test_virtual_tool_toggle_and_code_copy(monkeypatch):
    """Compiled interaction regions must drive tool expansion and code copying."""
    copied: list[str] = []
    monkeypatch.setattr(
        "cloudra.tui.new.widgets.virtual_chat_log.copy_to_clipboard", copied.append
    )
    app = ChatOnlyApp()
    async with app.run_test(size=(100, 36)) as pilot:
        chat = app.query_one("#chat-log", VirtualChatLog)
        tool = chat.append_tool(
            "s1", "Bash", "ls", finished=True, result="\n".join(map(str, range(30)))
        )
        code = chat.start_stream("s1", "Agent")
        chat.append_stream_chunk("s1", "```python\nprint('hi')\n```")
        chat.end_stream("s1")
        await chat.ensure_compiled(tool.record_id)
        await chat.ensure_compiled(code.record_id)

        assert chat.store.get(tool.record_id).collapsed
        await chat.activate_region(tool.record_id, InteractionAction.TOGGLE_TOOL)
        assert not chat.store.get(tool.record_id).collapsed

        await chat.activate_region(code.record_id, InteractionAction.COPY_CODE)
        assert copied == ["print('hi')"]


@pytest.mark.asyncio
async def test_virtual_append_while_scrolled_up_preserves_anchor():
    """Background output must not steal the viewport when the user scrolled up."""
    app = ChatOnlyApp()
    async with app.run_test(size=(100, 36)) as pilot:
        chat = app.query_one("#chat-log", VirtualChatLog)
        for index in range(50):
            chat.append_system("s1", f"event-{index}")
        await pilot.pause()
        anchor_record = chat.visible_record_ids[25]
        await chat.reveal(anchor_record)
        anchor_y = int(chat.scroll_y)
        if anchor_y == 0:
            # reveal() aligns the target at the top; for short records this can be 0.
            chat.scroll_to(y=50, animate=False, immediate=True)
            await pilot.pause()
            anchor_y = int(chat.scroll_y)
        assert anchor_y > 0

        for index in range(50, 100):
            chat.append_system("s1", f"event-{index}")
        await pilot.pause()

        assert abs(int(chat.scroll_y) - anchor_y) <= 1


@pytest.mark.asyncio
async def test_virtual_resize_preserves_anchor_inside_long_record():
    """Resizing while scrolled inside a tall message must not jump to an unrelated record."""
    app = ChatOnlyApp()
    async with app.run_test(size=(100, 36)) as pilot:
        chat = app.query_one("#chat-log", VirtualChatLog)
        long = chat.append_stream_chunk(
            "s1", "\n".join(f"line-{index}" for index in range(200))
        )
        chat.end_stream("s1")
        await chat.ensure_compiled(long.record_id)
        await pilot.pause()

        chat.scroll_to(y=chat._heights.row_start(0) + 100, animate=False, immediate=True)
        await pilot.pause()
        anchor = chat.capture_anchor()
        assert anchor is not None

        await pilot.resize_terminal(80, 36)
        await pilot.pause()

        restored_y = restore_anchor(anchor, chat.visible_record_ids, chat._heights)
        assert abs(int(chat.scroll_y) - restored_y) <= 1


@pytest.mark.asyncio
async def test_virtual_long_final_response_reaches_both_ends():
    """A finalized response longer than 20,000 characters keeps every row reachable."""
    app = ChatOnlyApp()
    async with app.run_test(size=(100, 36)) as pilot:
        chat = app.query_one("#chat-log", VirtualChatLog)
        text = "BEGIN-" + "x" * 25_000 + "-END"
        handle = chat.start_stream("s1", "Agent")
        chat.append_stream_chunk("s1", text)
        chat.end_stream("s1")
        await pilot.pause()
        await chat.ensure_compiled(handle.record_id)

        record = chat.store.get(handle.record_id)
        assert record.content.startswith("BEGIN-") and record.content.endswith("-END")
        height = chat._heights.height(0)
        assert height > 100

        await chat.reveal(handle.record_id)
        assert "BEGIN-" in chat.render_line(0).text

        chat.scroll_y = chat.max_scroll_y
        chat._flush_frame()
        await asyncio.sleep(0)
        await chat.ensure_compiled(handle.record_id)
        last_viewport_row = height - 1 - int(chat.scroll_y)
        assert "-END" in chat.render_line(last_viewport_row).text


@pytest.mark.asyncio
async def test_virtual_optimistic_user_reveal_scrolls_into_view():
    """An optimistic local user message is explicitly revealed before any DB wait."""
    app = ChatOnlyApp()
    async with app.run_test(size=(100, 36)) as pilot:
        chat = app.query_one("#chat-log", VirtualChatLog)
        for index in range(50):
            chat.append_system("s1", f"event-{index}")
        await pilot.pause()
        chat.scroll_to(y=0, animate=False, immediate=True)

        handle = chat.append_user("s1", "new question")
        await chat.reveal(handle.record_id)

        assert handle.record_id in chat.visible_record_ids
        row_start = chat._heights.row_start(chat._positions[handle.record_id])
        assert row_start <= int(chat.scroll_y) + chat.scrollable_content_region.height


from scripts.profile_textual_tui import run_profile


@pytest.mark.asyncio
async def test_reference_workload_meets_virtual_tui_contract():
    """The reference profile must keep history out of the DOM and remain bounded."""
    result = await run_profile(history_count=1_000, stream_count=16, rounds=30)

    assert result.child_count == 0
    assert result.record_count >= 1_016
    # Latency thresholds are generous to stay stable across CI machines; the
    # enforced contract is bounded latency and zero DOM growth.
    assert result.max_commit_seconds < 0.8
    assert result.input_p95_seconds < 0.8
    assert result.elapsed_seconds < 15.0


@pytest.mark.asyncio
async def test_active_stream_count_matches_the_number_of_sources():
    """16 concurrent streams must produce 16 mutable records, not hundreds of widgets."""
    app = ChatOnlyApp()
    async with app.run_test(size=(100, 36)) as pilot:
        chat = app.query_one("#chat-log", VirtualChatLog)
        for round_index in range(10):
            for stream_index in range(16):
                chat.append_stream_chunk(f"stream-{stream_index}", f"r{round_index} ")
        await pilot.pause()

        active_records = [
            record for record in chat.store.records if record.status == "streaming"
        ]
        assert len(active_records) == 16
        assert len(chat.children) <= 4
        assert len(chat._compile_tasks) + len(chat._compile_queue) <= 20
