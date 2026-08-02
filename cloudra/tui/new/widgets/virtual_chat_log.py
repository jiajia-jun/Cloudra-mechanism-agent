"""A single-widget, line-API transcript view.

The durable ``TranscriptStore`` retains every record.  This widget retains only
the rows needed to paint the current viewport, so message history never becomes
Textual child widgets.
"""

from __future__ import annotations

import asyncio
import shutil
import subprocess
from collections import OrderedDict
from contextlib import contextmanager
from typing import Iterator

from rich.console import Console
from textual.events import Click, Key, Resize
from textual.geometry import Region, Size
from textual.scroll_view import ScrollView
from textual.strip import Strip

from cloudra.tui.new.clipboard import copy_to_clipboard
from cloudra.tui.new.frame_scheduler import FrameScheduler
from cloudra.tui.new.transcript import (
    TranscriptChange,
    TranscriptHandle,
    TranscriptRecord,
    TranscriptStore,
)
from cloudra.tui.new.transcript_render import (
    CompiledRecord,
    InteractionAction,
    InteractionRegion,
    PresentationCompiler,
    RenderContext,
)
from cloudra.tui.new.virtual_lines import HeightIndex, ScrollAnchor, restore_anchor


class ChatLog(ScrollView, can_focus=True):
    """A virtual transcript surface with the legacy append/stream facade."""

    MAX_CACHED_ROWS = 4_096
    OVERSCAN_ROWS = 24

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.store = TranscriptStore()
        self._visible_ids: list[int] = []
        self._positions: dict[int, int] = {}
        self._heights = HeightIndex()
        self._measured_heights: dict[int, int] = {}
        # Cache blocks rather than whole records.  A single very tall record must
        # never keep more than MAX_CACHED_ROWS of derived presentation state alive.
        self._compiled: OrderedDict[tuple[int, int, int, int], tuple[Strip, ...]] = OrderedDict()
        self._compiled_regions: dict[tuple[int, int, int], tuple[InteractionRegion, ...]] = {}
        self._cached_rows = 0
        self._compile_tasks: dict[int, asyncio.Task[None]] = {}
        self._compile_jobs: dict[int, tuple[TranscriptRecord, int, int]] = {}
        self._compile_queue: OrderedDict[int, tuple[TranscriptRecord, int, int]] = OrderedDict()
        self._wanted_blocks: dict[int, set[int]] = {}
        self._retiring_tasks: set[asyncio.Task[None]] = set()
        self._close_task: asyncio.Task[None] | None = None
        self._close_error: BaseException | None = None
        self._compiler = PresentationCompiler(max_workers=2, max_pending=2)
        self._generation = 0
        self._last_width = 0
        self._view_session_id: str | None = None
        self._view_agent_prefix: str | None = None
        self._batch_depth = 0
        self._batched_change: TranscriptChange | None = None
        self._mounted = False
        self._surface_closing = False
        self._frame_scheduler = FrameScheduler(self, self._flush_frame, max_fps=20)
        self._focus_regions: list[tuple[int, InteractionRegion]] = []
        self._focus_index: int | None = None

    @property
    def has_records(self) -> bool:
        return bool(self.store._records)

    @property
    def record_count(self) -> int:
        return len(self.store._records)

    @property
    def visible_record_ids(self) -> tuple[int, ...]:
        return tuple(self._visible_ids)

    @property
    def view_session_id(self) -> str | None:
        return self._view_session_id

    @view_session_id.setter
    def view_session_id(self, session_id: str | None) -> None:
        self.show_session(session_id)

    @property
    def view_agent_prefix(self) -> str | None:
        return self._view_agent_prefix

    @property
    def current_session_id(self) -> str | None:
        return self._view_session_id

    @current_session_id.setter
    def current_session_id(self, session_id: str | None) -> None:
        self.show_session(session_id)

    def on_mount(self) -> None:
        super().on_mount()
        self._mounted = True
        self._rebuild_visible(preserve_anchor=False)

    def on_resize(self, event: Resize) -> None:
        if not self._mounted or self._surface_closing:
            return
        width = self.scrollable_content_region.width
        if width and width != self._last_width:
            self._last_width = width
            self._generation += 1
            self._set_virtual_size()
            self.request_frame()

    def watch_scroll_y(self, old_value: float, new_value: float) -> None:
        super().watch_scroll_y(old_value, new_value)
        if self._mounted and not self._surface_closing and round(old_value) != round(new_value):
            self.request_frame()

    def on_unmount(self) -> None:
        if self._surface_closing:
            return
        self._surface_closing = True
        self._mounted = False
        self._frame_scheduler.cancel()
        self._compile_queue.clear()
        for record_id in tuple(self._compile_tasks):
            self._cancel_record_compile(record_id, retire=False)
        for task in tuple(self._retiring_tasks):
            task.cancel()
        self._retiring_tasks.clear()
        # Keep the close task independent from the widget message pump: Textual
        # may await that pump during remove(), but admitted render jobs must be
        # allowed to drain asynchronously.  The task and any failure remain
        # inspectable on the surface for lifecycle diagnostics.
        self._close_task = asyncio.create_task(self._close_compiler())
        self._close_task.add_done_callback(self._observe_close_task)

    async def _close_compiler(self) -> None:
        while True:
            try:
                await self._compiler.close()
                return
            except asyncio.CancelledError:
                close_task = self._compiler._close_task
                if close_task is None or close_task.cancelled():
                    raise
                current = asyncio.current_task()
                if current is not None:
                    current.uncancel()

    def _observe_close_task(self, task: asyncio.Task[None]) -> None:
        if task.cancelled():
            return
        self._close_error = task.exception()

    def set_timer(self, delay: float, callback=None, **kwargs):
        """Keep one-shot frames valid on Textual versions that reject zero timers."""
        return super().set_timer(max(delay, 0.001), callback, **kwargs)

    def render_line(self, y: int) -> Strip:
        width = self.scrollable_content_region.width
        absolute_y = int(self.scroll_y) + y
        try:
            index, row = self._heights.locate(absolute_y)
        except IndexError:
            return Strip.blank(width, self.rich_style)
        record_id = self._visible_ids[index]
        strip = self._cached_row(record_id, width, row)
        if strip is None:
            self._schedule_record(record_id, row=row)
            return Strip.blank(width, self.rich_style)
        return strip.apply_style(self.rich_style).crop_extend(0, width, self.rich_style)

    def ensure_session(self, session_id: str) -> None:
        """Compatibility no-op: sessions exist as soon as their first record does."""

    def records_for_session(self, session_id: str) -> tuple[TranscriptRecord, ...]:
        return self.store.records_for_session(session_id)

    def text_for_session(self, session_id: str) -> str:
        return "\n".join(
            text
            for record in self.records_for_session(session_id)
            for text in (record.reasoning, record.content)
            if text
        )

    def append_user(
        self, session_id: str, content: str, *, message_id: str | None = None
    ) -> TranscriptHandle:
        handle = self.store.append_user(session_id, content, message_id=message_id)
        self._accept_change(self.store.last_change, immediate=True)
        return handle

    def append_system(self, session_id: str, content: str) -> TranscriptHandle:
        return self._accept_handle(self.store.append_system(session_id, content))

    def append_tool(
        self,
        session_id: str,
        tool: str,
        arguments: str,
        finished: bool = False,
        result: str | None = None,
    ) -> TranscriptHandle:
        return self._accept_handle(
            self.store.append_tool(session_id, tool, arguments, finished, result)
        )

    def start_stream(self, session_id: str, agent_name: str = "Agent") -> TranscriptHandle:
        return self._accept_handle(self.store.start_stream(session_id, agent_name))

    def append_stream_chunk(
        self, session_id: str, delta: str, agent_name: str | None = None
    ) -> TranscriptHandle:
        return self._accept_handle(
            self.store.append_stream_chunk(session_id, delta, agent_name or "Agent")
        )

    def append_reasoning_chunk(
        self, session_id: str, delta: str, agent_name: str | None = None
    ) -> TranscriptHandle:
        return self._accept_handle(
            self.store.append_reasoning_chunk(session_id, delta, agent_name or "Agent")
        )

    def end_stream(self, session_id: str) -> TranscriptHandle | None:
        handle = self.store.end_stream(session_id)
        return None if handle is None else self._accept_handle(handle, immediate=True)

    def append_divider(self, session_id: str, text: str) -> TranscriptHandle:
        return self._accept_handle(self.store.append_divider(session_id, text))

    def append_alert(
        self, session_id: str, title: str, body: str, style: str = "red"
    ) -> TranscriptHandle:
        return self._accept_handle(self.store.append_alert(session_id, title, body, style=style))

    def append_file_change(
        self, session_id: str, path: str, status: str, diff: str | None = None
    ) -> TranscriptHandle:
        return self._accept_handle(self.store.append_file_change(session_id, path, status, diff))

    def append_supervisor_review(
        self, session_id: str, conclusion: str, reason: str
    ) -> TranscriptHandle:
        return self._accept_handle(
            self.store.append_supervisor_review(session_id, conclusion, reason)
        )

    def mark_send_failed(self, handle: TranscriptHandle | int) -> None:
        self._accept_change(self.store.mark_send_failed(handle), immediate=True)

    def show_session(self, session_id: str | None) -> None:
        self._view_session_id, self._view_agent_prefix = session_id, None
        self._rebuild_visible(preserve_anchor=True)

    def show_agent(self, agent_id: str | None) -> None:
        self._view_agent_prefix, self._view_session_id = agent_id, None
        self._rebuild_visible(preserve_anchor=True)

    def rename_session(self, old_session_id: str, new_session_id: str) -> None:
        self._accept_change(self.store.rename_session(old_session_id, new_session_id))

    def clear_session(self, session_id: str) -> None:
        self._accept_change(self.store.clear_session(session_id))

    def clear_all(self) -> None:
        self._accept_change(self.store.clear())

    @contextmanager
    def batch_update(self) -> Iterator["ChatLog"]:
        self._batch_depth += 1
        try:
            with self.store.batch():
                yield self
        finally:
            self._batch_depth -= 1
            if self._batch_depth == 0 and self._batched_change is not None:
                self._batched_change = None
                self._apply_change(self.store.last_change)

    def request_frame(self, *, immediate: bool = False) -> None:
        if not self._mounted or self._surface_closing:
            return
        self._frame_scheduler.request(immediate=immediate)

    async def reveal(self, record_id: int, *, force: bool = True) -> None:
        """Bring one visible record into view and prioritize its compilation."""
        del force  # The legacy parameter is kept for compatibility.
        index = self._positions.get(record_id)
        if index is None:
            return
        await self.ensure_compiled(record_id)
        row_start = self._heights.row_start(index)
        target = max(0, min(row_start, self.max_scroll_y))
        self.scroll_to(y=target, animate=False, immediate=True)
        self.request_frame()
        await asyncio.sleep(0)

    async def ensure_compiled(self, record_id: int) -> CompiledRecord | None:
        """Wait for the current width/revision rows for one visible record."""
        while record_id in self._positions:
            width = self._content_width()
            if width < 1:
                return None
            compiled = self._rebuild_compiled_record(record_id, width)
            if compiled is not None:
                return compiled
            self._schedule_record(record_id, row=0)
            task = self._compile_tasks.get(record_id)
            if task is not None:
                await asyncio.shield(task)
            else:
                await asyncio.sleep(0)
        return None

    def _accept_handle(
        self, handle: TranscriptHandle, *, immediate: bool = False
    ) -> TranscriptHandle:
        self._accept_change(self.store.last_change, immediate=immediate)
        return handle

    def _accept_change(self, change: TranscriptChange, *, immediate: bool = False) -> None:
        if self._batch_depth:
            self._batched_change = self._merge_changes(self._batched_change, change)
            return
        self._apply_change(change, immediate=immediate)

    def _apply_change(self, change: TranscriptChange, *, immediate: bool = False) -> None:
        if not self._mounted:
            return
        for record_id in change.record_ids:
            self._cancel_record_compile(record_id)
            self._discard_record_metadata(record_id)
        if self._can_append_incrementally(change):
            self._append_visible_tail(change.record_ids)
        elif change.order_changed or change.visibility_changed:
            self._rebuild_visible(preserve_anchor=True)
        else:
            for record_id in change.record_ids:
                if record_id in self._positions:
                    self._schedule_record(record_id)
            self.refresh(layout=False)
        self.request_frame(immediate=immediate)

    def _can_append_incrementally(self, change: TranscriptChange) -> bool:
        """Return true only when every changed record is newly appended in store order."""
        record_ids = change.record_ids
        records = self.store._records
        if not change.order_changed or not record_ids or len(records) < len(record_ids):
            return False
        return (
            tuple(record.record_id for record in records[-len(record_ids) :])
            == record_ids
        )

    def _append_visible_tail(self, record_ids: tuple[int, ...]) -> None:
        follow_tail = self._following_tail()
        for record_id in record_ids:
            record = self.store.get(record_id)
            if record_id in self._positions or not self._record_is_visible(record):
                continue
            self._positions[record_id] = len(self._visible_ids)
            self._visible_ids.append(record_id)
            self._heights.append(self._measured_heights.get(record_id, 1))
        self._set_virtual_size()
        if follow_tail:
            self.scroll_end(animate=False, immediate=True)
        self.refresh(layout=False)

    def _record_is_visible(self, record: TranscriptRecord) -> bool:
        if self._view_session_id is not None:
            return record.session_id == self._view_session_id
        return (
            self._view_agent_prefix is None
            or record.agent_id is not None
            and record.agent_id.startswith(self._view_agent_prefix)
        )

    def _rebuild_visible(self, *, preserve_anchor: bool) -> None:
        if not self._mounted:
            return
        anchor = self.capture_anchor() if preserve_anchor else None
        records = self.store.visible_records(
            agent_prefix=self._view_agent_prefix, session_id=self._view_session_id
        )
        self._visible_ids = [record.record_id for record in records]
        self._positions = {record_id: index for index, record_id in enumerate(self._visible_ids)}
        self._heights.rebuild(
            self._measured_heights.get(record_id, 1) for record_id in self._visible_ids
        )
        self._set_virtual_size()
        self._restore_or_follow(anchor)
        self.request_frame()
        self.refresh(layout=False)

    def _flush_frame(self) -> None:
        self._schedule_viewport()

    def _schedule_viewport(self) -> None:
        if not self._visible_ids or self._content_width() < 1:
            return
        first_row = max(0, int(self.scroll_y) - self.OVERSCAN_ROWS)
        last_row = min(
            self._heights.total - 1,
            int(self.scroll_y) + self.scrollable_content_region.height + self.OVERSCAN_ROWS,
        )
        try:
            first_index, _ = self._heights.locate(first_row)
            last_index, _ = self._heights.locate(last_row)
        except IndexError:
            return
        for index in range(first_index, last_index + 1):
            record_start = self._heights.row_start(index)
            record_end = record_start + self._heights.height(index) - 1
            first_block = (max(first_row, record_start) - record_start) // 128
            last_block = (min(last_row, record_end) - record_start) // 128
            for block in range(first_block, last_block + 1):
                self._schedule_record(self._visible_ids[index], row=block * 128)

    def _schedule_record(self, record_id: int, *, row: int = 0) -> None:
        position = self._positions.get(record_id)
        width = self._content_width()
        if position is None or width < 1:
            return
        record = self.store.get(record_id)
        block = row // 128
        if self._cached_block(record_id, width, block) is not None:
            return
        self._wanted_blocks.setdefault(record_id, set()).add(block)
        task = self._compile_tasks.get(record_id)
        if task is not None and not task.done():
            return
        self._compile_queue[record_id] = (record, width, self._generation)
        self._compile_queue.move_to_end(record_id, last=False)
        self._drain_compile_queue()

    def _drain_compile_queue(self) -> None:
        if self._surface_closing:
            return
        while self._active_compile_count() < 2 and self._compile_queue:
            record_id, (record, width, generation) = self._compile_queue.popitem(last=False)
            try:
                current = self.store.get(record_id)
            except KeyError:
                continue
            if (
                current.revision != record.revision
                or width != self._content_width()
                or generation != self._generation
                or record_id not in self._positions
            ):
                continue
            self._compile_jobs[record_id] = (record, width, generation)
            self._compile_tasks[record_id] = asyncio.create_task(
                self._compile_record(record, width, generation)
            )

    async def _compile_record(self, record: TranscriptRecord, width: int, generation: int) -> None:
        try:
            result = await self._compiler.compile(
                record, width, self._render_context(width), generation
            )
        except asyncio.CancelledError:
            # A cancellation is normally a revision replacement or teardown.
            # In either case it must not revive the frame scheduler.
            return
        except RuntimeError:
            return
        finally:
            task = self._compile_tasks.get(record.record_id)
            if task is asyncio.current_task():
                self._compile_tasks.pop(record.record_id, None)
                self._compile_jobs.pop(record.record_id, None)
            self._drain_compile_queue()

        try:
            current = self.store.get(result.record_id)
        except KeyError:
            return
        if (
            result.generation != self._generation
            or result.width != self._content_width()
            or current.revision != result.revision
            or result.record_id not in self._positions
        ):
            self.request_frame()
            return

        anchor = self.capture_anchor()
        self._cache_compiled(
            result.compiled, self._wanted_blocks.pop(result.record_id, {0})
        )
        position = self._positions[result.record_id]
        height = len(result.compiled.strips)
        self._measured_heights[result.record_id] = height
        if self._heights.height(position) != height:
            self._heights.replace(position, height)
            self._set_virtual_size()
            self._restore_or_follow(anchor)
        self.refresh(layout=False)
        self.request_frame()

    def _cached_block(
        self, record_id: int, width: int, block: int
    ) -> tuple[Strip, ...] | None:
        try:
            record = self.store.get(record_id)
        except KeyError:
            return None
        key = (record_id, record.revision, width, block)
        compiled = self._compiled.get(key)
        if compiled is not None:
            self._compiled.move_to_end(key)
        return compiled

    def _cached_row(self, record_id: int, width: int, row: int) -> Strip | None:
        block, offset = divmod(row, 128)
        rows = self._cached_block(record_id, width, block)
        return None if rows is None or offset >= len(rows) else rows[offset]

    def _cache_compiled(self, compiled: CompiledRecord, wanted_blocks: set[int]) -> None:
        self._compiled_regions[(compiled.record_id, compiled.revision, compiled.width)] = (
            compiled.regions
        )
        blocks = (
            range(len(compiled.blocks))
            if len(compiled.strips) <= self.MAX_CACHED_ROWS
            else wanted_blocks
        )
        for block in blocks:
            if not 0 <= block < len(compiled.blocks):
                continue
            key = (compiled.record_id, compiled.revision, compiled.width, block)
            previous = self._compiled.pop(key, None)
            if previous is not None:
                self._cached_rows -= len(previous)
            rows = compiled.blocks[block]
            self._compiled[key] = rows
            self._cached_rows += len(rows)
        while self._cached_rows > self.MAX_CACHED_ROWS:
            _, evicted = self._compiled.popitem(last=False)
            self._cached_rows -= len(evicted)

    def _rebuild_compiled_record(self, record_id: int, width: int) -> CompiledRecord | None:
        """Return a compiled record from cached blocks/regions, or None."""
        try:
            record = self.store.get(record_id)
        except KeyError:
            return None
        key = (record_id, record.revision, width)
        regions = self._compiled_regions.get(key)
        if regions is None:
            return None
        blocks: list[tuple[Strip, ...]] = []
        for block in range(0, self._measured_heights.get(record_id, 1), 128):
            rows = self._cached_block(record_id, width, block)
            if rows is None:
                break
            blocks.append(rows)
        if not blocks:
            return None
        return CompiledRecord(record_id, record.revision, width, tuple(blocks), regions)

    def _discard_cached_record(self, record_id: int) -> None:
        for key in tuple(self._compiled):
            if key[0] == record_id:
                self._cached_rows -= len(self._compiled.pop(key))
        for key in tuple(self._compiled_regions):
            if key[0] == record_id:
                self._compiled_regions.pop(key, None)

    def _discard_record_metadata(self, record_id: int) -> None:
        self._discard_cached_record(record_id)
        self._measured_heights.pop(record_id, None)
        self._wanted_blocks.pop(record_id, None)

    def _cancel_record_compile(self, record_id: int, *, retire: bool = True) -> None:
        self._compile_queue.pop(record_id, None)
        task = self._compile_tasks.pop(record_id, None)
        job = self._compile_jobs.pop(record_id, None)
        if task is not None:
            task.cancel()
            if retire and not self._surface_closing and job is not None:
                record, width, generation = job
                retirement = asyncio.create_task(
                    self._retire_compile(record, width, generation)
                )
                self._retiring_tasks.add(retirement)
                retirement.add_done_callback(self._retirement_done)

    def _retirement_done(self, task: asyncio.Task[None]) -> None:
        self._retiring_tasks.discard(task)
        self._drain_compile_queue()

    async def _retire_compile(
        self, record: TranscriptRecord, width: int, generation: int
    ) -> None:
        """Hold a surface slot until a cancelled compiler admission has drained."""
        try:
            await self._compiler.compile(record, width, self._render_context(width), generation)
        except (asyncio.CancelledError, RuntimeError):
            return
        finally:
            self._drain_compile_queue()

    def _active_compile_count(self) -> int:
        return len(self._compile_tasks) + len(self._retiring_tasks)

    def _set_virtual_size(self) -> None:
        self.virtual_size = Size(self._content_width(), self._heights.total)

    def _content_width(self) -> int:
        return self.scrollable_content_region.width

    def _render_context(self, width: int) -> RenderContext:
        return RenderContext(Console(width=width, force_terminal=True, color_system="truecolor"))

    def _following_tail(self) -> bool:
        try:
            return self.scroll_y >= self.max_scroll_y - 2
        except Exception:
            return True

    def _current_anchor(self) -> ScrollAnchor | None:
        try:
            position, row_offset = self._heights.locate(int(self.scroll_y))
        except IndexError:
            return None
        return ScrollAnchor(self._visible_ids[position], row_offset)

    def capture_anchor(self) -> ScrollAnchor | None:
        """Return the current viewport anchor, or None if following the tail."""
        if not self._visible_ids or self._following_tail():
            return None
        try:
            index, offset = self._heights.locate(int(self.scroll_y))
        except IndexError:
            return None
        return ScrollAnchor(self._visible_ids[index], offset)

    def _restore_or_follow(self, anchor: ScrollAnchor | None) -> None:
        if anchor is None:
            self.scroll_end(animate=False, immediate=True, x_axis=False)
        else:
            self.scroll_to(
                y=restore_anchor(anchor, self._visible_ids, self._heights),
                animate=False,
                immediate=True,
            )

    async def activate_region(
        self, handle: TranscriptHandle | int, action: InteractionAction
    ) -> None:
        """Activate a compiled interaction region (tool toggle or code copy)."""
        record_id = handle.record_id if isinstance(handle, TranscriptHandle) else handle
        if action is InteractionAction.TOGGLE_TOOL:
            self._accept_change(self.store.toggle_collapsed(record_id), immediate=True)
        elif action is InteractionAction.COPY_CODE:
            compiled = await self.ensure_compiled(record_id)
            if compiled is None:
                return
            region = next(
                (region for region in compiled.regions if region.action is action), None
            )
            if region is None:
                return
            await self._copy_code(region.payload)

    async def _copy_code(self, text: str) -> None:
        try:
            await asyncio.to_thread(copy_to_clipboard, text)
        except RuntimeError as exc:
            self.app.notify(str(exc), severity="error", timeout=4)
        else:
            self.app.notify("已复制到剪贴板", severity="information", timeout=2)

    async def on_click(self, event: Click) -> None:
        if not self._visible_ids or self._content_width() < 1:
            return
        virtual_row = event.offset.y + int(self.scroll_y)
        try:
            index, _ = self._heights.locate(virtual_row)
        except IndexError:
            return
        record_id = self._visible_ids[index]
        compiled = await self.ensure_compiled(record_id)
        if compiled is None or not compiled.regions:
            return
        record_start = self._heights.row_start(index)
        rel_y = virtual_row - record_start
        rel_x = event.offset.x
        for region in compiled.regions:
            if (
                region.x <= rel_x < region.x + region.width
                and region.y <= rel_y < region.y + region.height
            ):
                await self.activate_region(record_id, region.action)
                event.stop()
                return

    def _refresh_focus_regions(self) -> None:
        """Rebuild the ordered list of visible interaction regions."""
        regions: list[tuple[int, InteractionRegion]] = []
        width = self._content_width()
        for index, record_id in enumerate(self._visible_ids):
            compiled = self._rebuild_compiled_record(record_id, width)
            if compiled is None:
                continue
            record_start = self._heights.row_start(index)
            for region in compiled.regions:
                regions.append(
                    (record_id, region)
                )
        self._focus_regions = regions
        if self._focus_index is None or self._focus_index >= len(regions):
            self._focus_index = 0 if regions else None

    async def on_key(self, event: Key) -> None:
        if not self.has_focus or not self._visible_ids:
            return
        if event.key in ("tab", "shift+tab"):
            self._refresh_focus_regions()
            if self._focus_index is None:
                return
            if event.key == "tab":
                self._focus_index = (self._focus_index + 1) % len(self._focus_regions)
            else:
                self._focus_index = (self._focus_index - 1) % len(self._focus_regions)
            event.stop()
        elif event.key == "enter" and self._focus_index is not None:
            record_id, region = self._focus_regions[self._focus_index]
            await self.activate_region(record_id, region.action)
            event.stop()

    @staticmethod
    def _merge_changes(
        left: TranscriptChange | None, right: TranscriptChange
    ) -> TranscriptChange:
        if left is None:
            return right
        return TranscriptChange(
            tuple(dict.fromkeys((*left.record_ids, *right.record_ids))),
            order_changed=left.order_changed or right.order_changed,
            visibility_changed=left.visibility_changed or right.visibility_changed,
        )
