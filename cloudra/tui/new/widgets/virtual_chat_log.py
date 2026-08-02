"""A single-widget, line-API transcript view.

The durable ``TranscriptStore`` retains every record.  This widget retains only
the rows needed to paint the current viewport, so message history never becomes
Textual child widgets.
"""

from __future__ import annotations

import asyncio
from collections import OrderedDict
from contextlib import contextmanager
from typing import Iterator

from rich.console import Console
from textual.events import Resize
from textual.geometry import Size
from textual.scroll_view import ScrollView
from textual.strip import Strip

from cloudra.tui.new.frame_scheduler import FrameScheduler
from cloudra.tui.new.transcript import (
    TranscriptChange,
    TranscriptHandle,
    TranscriptRecord,
    TranscriptStore,
)
from cloudra.tui.new.transcript_render import (
    CompiledRecord,
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
        self._compiled: OrderedDict[tuple[int, int, int], CompiledRecord] = OrderedDict()
        self._cached_rows = 0
        self._compile_tasks: dict[int, asyncio.Task[None]] = {}
        self._compiler = PresentationCompiler(max_workers=2, max_pending=2)
        self._generation = 0
        self._last_width = 0
        self._view_session_id: str | None = None
        self._view_agent_prefix: str | None = None
        self._batch_depth = 0
        self._batched_change: TranscriptChange | None = None
        self._frame_scheduler = FrameScheduler(self, self._flush_frame, max_fps=20)

    @property
    def has_records(self) -> bool:
        return bool(self.store.records)

    @property
    def record_count(self) -> int:
        return len(self.store.records)

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
        self._rebuild_visible(preserve_anchor=False)

    def on_resize(self, event: Resize) -> None:
        width = self.scrollable_content_region.width
        if width and width != self._last_width:
            self._last_width = width
            self._generation += 1
            self._set_virtual_size()
            self.request_frame()

    def watch_scroll_y(self, old_value: float, new_value: float) -> None:
        super().watch_scroll_y(old_value, new_value)
        if round(old_value) != round(new_value):
            self.request_frame()

    async def on_unmount(self) -> None:
        self._frame_scheduler.cancel()
        for task in self._compile_tasks.values():
            task.cancel()
        self._compile_tasks.clear()
        # ``close`` waits asynchronously, so Textual can keep servicing the
        # loop while admitted worker jobs finish and release their threads.
        await self._compiler.close()

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
        compiled = self._compiled_for(self._visible_ids[index], width)
        return (
            Strip.blank(width, self.rich_style)
            if compiled is None
            else compiled.row(row)
            .apply_style(self.rich_style)
            .crop_extend(0, width, self.rich_style)
        )

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
        self._frame_scheduler.request(immediate=immediate)

    async def reveal(self, record_id: int) -> None:
        """Bring one visible record to the top and prioritize its compilation."""
        index = self._positions.get(record_id)
        if index is None:
            return
        self.scroll_to(y=self._heights.row_start(index), animate=False, immediate=True)
        self._schedule_record(record_id)
        self.request_frame()
        await asyncio.sleep(0)

    async def ensure_compiled(self, record_id: int) -> CompiledRecord | None:
        """Wait for the current width/revision rows for one visible record."""
        while record_id in self._positions:
            width = self._content_width()
            if width < 1:
                return None
            compiled = self._compiled_for(record_id, width)
            if compiled is not None:
                return compiled
            self._schedule_record(record_id)
            task = self._compile_tasks.get(record_id)
            if task is not None:
                await asyncio.shield(task)
            else:
                await asyncio.sleep(0)
        return None

    def _accept_handle(self, handle: TranscriptHandle, *, immediate: bool = False) -> TranscriptHandle:
        self._accept_change(self.store.last_change, immediate=immediate)
        return handle

    def _accept_change(self, change: TranscriptChange, *, immediate: bool = False) -> None:
        if self._batch_depth:
            self._batched_change = self._merge_changes(self._batched_change, change)
            return
        self._apply_change(change, immediate=immediate)

    def _apply_change(self, change: TranscriptChange, *, immediate: bool = False) -> None:
        for record_id in change.record_ids:
            self._cancel_record_compile(record_id)
            self._discard_cached_record(record_id)
        if change.order_changed or change.visibility_changed:
            self._rebuild_visible(preserve_anchor=True)
        else:
            for record_id in change.record_ids:
                if record_id in self._positions:
                    self._schedule_record(record_id)
            self.refresh(layout=False)
        self.request_frame(immediate=immediate)

    def _rebuild_visible(self, *, preserve_anchor: bool) -> None:
        follow_tail = self._following_tail()
        anchor = self._current_anchor() if preserve_anchor and not follow_tail else None
        records = self.store.visible_records(
            agent_prefix=self._view_agent_prefix, session_id=self._view_session_id
        )
        self._visible_ids = [record.record_id for record in records]
        self._positions = {record_id: index for index, record_id in enumerate(self._visible_ids)}
        self._heights.rebuild(self._measured_heights.get(record_id, 1) for record_id in self._visible_ids)
        self._set_virtual_size()
        if follow_tail:
            self.scroll_end(animate=False, immediate=True)
        elif anchor is not None:
            self.scroll_to(
                y=restore_anchor(anchor, self._visible_ids, self._heights),
                animate=False,
                immediate=True,
            )
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
        for record_id in self._visible_ids[first_index : last_index + 1]:
            self._schedule_record(record_id)

    def _schedule_record(self, record_id: int) -> None:
        position = self._positions.get(record_id)
        width = self._content_width()
        if position is None or width < 1:
            return
        record = self.store.get(record_id)
        if self._compiled_for(record_id, width) is not None:
            return
        task = self._compile_tasks.get(record_id)
        if task is not None and not task.done():
            return
        self._compile_tasks[record_id] = asyncio.create_task(
            self._compile_record(record, width, self._generation)
        )

    async def _compile_record(self, record: TranscriptRecord, width: int, generation: int) -> None:
        try:
            result = await self._compiler.compile(
                record, width, self._render_context(width), generation
            )
        except (asyncio.CancelledError, RuntimeError):
            self.request_frame()
            return
        finally:
            task = self._compile_tasks.get(record.record_id)
            if task is asyncio.current_task():
                self._compile_tasks.pop(record.record_id, None)

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

        follow_tail = self._following_tail()
        anchor = self._current_anchor() if not follow_tail else None
        self._cache_compiled(result.compiled)
        position = self._positions[result.record_id]
        height = len(result.compiled.strips)
        self._measured_heights[result.record_id] = height
        if self._heights.height(position) != height:
            self._heights.replace(position, height)
            self._set_virtual_size()
            if follow_tail:
                self.scroll_end(animate=False, immediate=True)
            elif anchor is not None:
                self.scroll_to(
                    y=restore_anchor(anchor, self._visible_ids, self._heights),
                    animate=False,
                    immediate=True,
                )
        self.refresh(layout=False)
        self.request_frame()

    def _compiled_for(self, record_id: int, width: int) -> CompiledRecord | None:
        try:
            record = self.store.get(record_id)
        except KeyError:
            return None
        key = (record_id, record.revision, width)
        compiled = self._compiled.get(key)
        if compiled is not None:
            self._compiled.move_to_end(key)
        return compiled

    def _cache_compiled(self, compiled: CompiledRecord) -> None:
        self._discard_cached_record(compiled.record_id)
        key = (compiled.record_id, compiled.revision, compiled.width)
        self._compiled[key] = compiled
        self._cached_rows += len(compiled.strips)
        while self._cached_rows > self.MAX_CACHED_ROWS and len(self._compiled) > 1:
            _, evicted = self._compiled.popitem(last=False)
            self._cached_rows -= len(evicted.strips)

    def _discard_cached_record(self, record_id: int) -> None:
        for key in tuple(self._compiled):
            if key[0] == record_id:
                self._cached_rows -= len(self._compiled.pop(key).strips)

    def _cancel_record_compile(self, record_id: int) -> None:
        task = self._compile_tasks.pop(record_id, None)
        if task is not None:
            task.cancel()

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
