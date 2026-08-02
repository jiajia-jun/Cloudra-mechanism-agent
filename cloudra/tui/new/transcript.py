"""Immutable, ordered presentation records for the Textual transcript."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, replace
from enum import StrEnum
from typing import Iterator


class RecordKind(StrEnum):
    SYSTEM = "system"
    USER = "user"
    DIVIDER = "divider"
    ALERT = "alert"
    ASSISTANT = "assistant"
    TOOL = "tool"
    FILE_CHANGE = "file_change"
    SUPERVISOR = "supervisor"


@dataclass(frozen=True, slots=True)
class TranscriptHandle:
    record_id: int


@dataclass(frozen=True, slots=True)
class TranscriptRecord:
    record_id: int
    session_id: str
    agent_id: str | None
    kind: RecordKind
    content: str = ""
    reasoning: str = ""
    title: str = ""
    tool_name: str = ""
    arguments: str = ""
    result: str | None = None
    status: str = ""
    message_id: str | None = None
    collapsed: bool = False
    send_failed: bool = False
    revision: int = 0


@dataclass(frozen=True, slots=True)
class TranscriptChange:
    record_ids: tuple[int, ...] = ()
    order_changed: bool = False
    visibility_changed: bool = False


class TranscriptStore:
    """The complete transcript and its lookup indexes, without UI state."""

    def __init__(self) -> None:
        self._records: list[TranscriptRecord] = []
        self._positions: dict[int, int] = {}
        self._session_ids: dict[str, list[int]] = {}
        self._message_ids: dict[str, int] = {}
        self._derived_agent_ids: set[int] = set()
        self._active_streams: dict[str, int] = {}
        self._next_record_id = 1
        self._last_change = TranscriptChange()
        self._batch_depth = 0
        self._batched_record_ids: list[int] = []
        self._batched_order_changed = False
        self._batched_visibility_changed = False

    @property
    def records(self) -> tuple[TranscriptRecord, ...]:
        return tuple(self._records)

    @property
    def last_change(self) -> TranscriptChange:
        return self._last_change

    def append(
        self,
        session_id: str,
        kind: RecordKind,
        *,
        agent_id: str | None = None,
        content: str = "",
        reasoning: str = "",
        title: str = "",
        tool_name: str = "",
        arguments: str = "",
        result: str | None = None,
        status: str = "",
        message_id: str | None = None,
        collapsed: bool = False,
        send_failed: bool = False,
    ) -> TranscriptHandle:
        if message_id is not None:
            existing_id = self._message_ids.get(message_id)
            if existing_id is not None:
                self._publish_change(TranscriptChange())
                return TranscriptHandle(existing_id)

        record_id = self._next_record_id
        self._next_record_id += 1
        derived_agent_id = agent_id is None
        record = TranscriptRecord(
            record_id=record_id,
            session_id=session_id,
            agent_id=self._agent_id(session_id) if derived_agent_id else agent_id,
            kind=kind,
            content=content,
            reasoning=reasoning,
            title=title,
            tool_name=tool_name,
            arguments=arguments,
            result=result,
            status=status,
            message_id=message_id,
            collapsed=collapsed,
            send_failed=send_failed,
        )
        self._positions[record_id] = len(self._records)
        self._records.append(record)
        self._session_ids.setdefault(session_id, []).append(record_id)
        if derived_agent_id:
            self._derived_agent_ids.add(record_id)
        if message_id is not None:
            self._message_ids[message_id] = record_id
        self._publish_change(
            TranscriptChange((record_id,), order_changed=True, visibility_changed=True)
        )
        return TranscriptHandle(record_id)

    def append_system(self, session_id: str, content: str) -> TranscriptHandle:
        return self.append(session_id, RecordKind.SYSTEM, title="系统", content=content)

    def append_user(
        self, session_id: str, content: str, *, message_id: str | None = None
    ) -> TranscriptHandle:
        return self.append(
            session_id,
            RecordKind.USER,
            content=content,
            message_id=message_id,
        )

    def append_divider(self, session_id: str, text: str) -> TranscriptHandle:
        return self.append(session_id, RecordKind.DIVIDER, content=text)

    def append_alert(
        self, session_id: str, title: str, body: str, *, style: str = ""
    ) -> TranscriptHandle:
        return self.append(
            session_id,
            RecordKind.ALERT,
            title=title,
            content=body,
            status=style,
        )

    def append_file_change(
        self,
        session_id: str,
        path: str,
        status: str,
        diff: str | None = None,
    ) -> TranscriptHandle:
        return self.append(
            session_id,
            RecordKind.FILE_CHANGE,
            title=path,
            content=diff or status,
            status=status,
        )

    def append_supervisor_review(
        self, session_id: str, conclusion: str, reason: str
    ) -> TranscriptHandle:
        return self.append(
            session_id,
            RecordKind.SUPERVISOR,
            title="Supervisor 审查",
            content=reason,
            status=conclusion,
        )

    def start_stream(self, session_id: str, agent_name: str = "Agent") -> TranscriptHandle:
        with self.batch():
            self.end_stream(session_id)
            handle = self.append(
                session_id,
                RecordKind.ASSISTANT,
                title=agent_name,
                status="streaming",
            )
        self._active_streams[session_id] = handle.record_id
        return handle

    def active_stream(self, session_id: str) -> TranscriptHandle | None:
        record_id = self._active_streams.get(session_id)
        return TranscriptHandle(record_id) if record_id is not None else None

    def append_stream_chunk(
        self, session_id: str, delta: str, agent_name: str = "Agent"
    ) -> TranscriptHandle:
        with self.batch():
            record_id = self._active_streams.get(session_id)
            if record_id is None:
                record_id = self.start_stream(session_id, agent_name).record_id
            record = self.get(record_id)
            self._replace(record_id, content=record.content + delta)
            self._publish_change(TranscriptChange((record_id,)))
        return TranscriptHandle(record_id)

    def append_reasoning_chunk(
        self, session_id: str, delta: str, agent_name: str = "Agent"
    ) -> TranscriptHandle:
        with self.batch():
            record_id = self._active_streams.get(session_id)
            if record_id is None:
                record_id = self.start_stream(session_id, agent_name).record_id
            record = self.get(record_id)
            self._replace(record_id, reasoning=record.reasoning + delta)
            self._publish_change(TranscriptChange((record_id,)))
        return TranscriptHandle(record_id)

    def end_stream(self, session_id: str) -> TranscriptHandle | None:
        record_id = self._active_streams.pop(session_id, None)
        if record_id is None:
            self._publish_change(TranscriptChange())
            return None
        self._replace(record_id, status="finished")
        self._publish_change(TranscriptChange((record_id,)))
        return TranscriptHandle(record_id)

    def append_tool(
        self,
        session_id: str,
        tool: str,
        arguments: str,
        finished: bool = False,
        result: str | None = None,
    ) -> TranscriptHandle:
        if finished:
            for record_id in reversed(self._session_ids.get(session_id, ())):
                record = self.get(record_id)
                if (
                    record.kind is RecordKind.TOOL
                    and record.tool_name == tool
                    and record.status == "running"
                ):
                    self._replace(
                        record_id,
                        arguments=arguments,
                        result=result,
                        status="finished",
                        collapsed=self._tool_result_is_collapsible(result),
                    )
                    self._publish_change(TranscriptChange((record_id,)))
                    return TranscriptHandle(record_id)

        return self.append(
            session_id,
            RecordKind.TOOL,
            tool_name=tool,
            arguments=arguments,
            result=result,
            status="finished" if finished else "running",
            collapsed=finished and self._tool_result_is_collapsible(result),
        )

    def toggle_collapsed(self, handle: TranscriptHandle | int) -> TranscriptChange:
        record_id = self._record_id(handle)
        record = self.get(record_id)
        self._replace(record_id, collapsed=not record.collapsed)
        change = TranscriptChange((record_id,))
        self._publish_change(change)
        return change

    @contextmanager
    def batch(self) -> Iterator[TranscriptStore]:
        if self._batch_depth == 0:
            self._batched_record_ids.clear()
            self._batched_order_changed = False
            self._batched_visibility_changed = False
        self._batch_depth += 1
        try:
            yield self
        finally:
            self._batch_depth -= 1
            if self._batch_depth == 0:
                self._last_change = TranscriptChange(
                    tuple(self._batched_record_ids),
                    order_changed=self._batched_order_changed,
                    visibility_changed=self._batched_visibility_changed,
                )

    def get(self, handle: TranscriptHandle | int) -> TranscriptRecord:
        record_id = self._record_id(handle)
        return self._records[self._positions[record_id]]

    def records_for_session(self, session_id: str) -> tuple[TranscriptRecord, ...]:
        return tuple(self.get(record_id) for record_id in self._session_ids.get(session_id, ()))

    def visible_records(
        self,
        *,
        agent_prefix: str | None = None,
        session_id: str | None = None,
    ) -> tuple[TranscriptRecord, ...]:
        if session_id is not None:
            candidates = self.records_for_session(session_id)
        else:
            candidates = self.records
        if agent_prefix is None:
            return candidates
        return tuple(
            record
            for record in candidates
            if record.agent_id is not None and record.agent_id.startswith(agent_prefix)
        )

    def rename_session(self, old_session_id: str, new_session_id: str) -> TranscriptChange:
        record_ids = tuple(self._session_ids.get(old_session_id, ()))
        if old_session_id == new_session_id or not record_ids:
            self._publish_change(TranscriptChange())
            return self._last_change

        new_agent_id = self._agent_id(new_session_id)
        for record_id in record_ids:
            changes: dict[str, object] = {"session_id": new_session_id}
            if record_id in self._derived_agent_ids:
                changes["agent_id"] = new_agent_id
            self._replace(record_id, **changes)
        self._rebuild_indexes()
        active_stream = self._active_streams.pop(old_session_id, None)
        if active_stream is not None:
            self._active_streams[new_session_id] = active_stream
        self._publish_change(TranscriptChange(record_ids, visibility_changed=True))
        return self._last_change

    def mark_send_failed(self, handle: TranscriptHandle | int) -> TranscriptChange:
        record_id = self._record_id(handle)
        self._replace(record_id, send_failed=True)
        self._publish_change(TranscriptChange((record_id,)))
        return self._last_change

    def clear_session(self, session_id: str) -> TranscriptChange:
        removed_ids = tuple(self._session_ids.get(session_id, ()))
        if not removed_ids:
            self._publish_change(TranscriptChange())
            return self._last_change

        removed = set(removed_ids)
        self._records = [record for record in self._records if record.record_id not in removed]
        self._rebuild_indexes()
        self._active_streams.pop(session_id, None)
        self._publish_change(
            TranscriptChange(removed_ids, order_changed=True, visibility_changed=True)
        )
        return self._last_change

    def clear(self) -> TranscriptChange:
        removed_ids = tuple(record.record_id for record in self._records)
        self._records.clear()
        self._positions.clear()
        self._session_ids.clear()
        self._message_ids.clear()
        self._derived_agent_ids.clear()
        self._active_streams.clear()
        self._publish_change(
            TranscriptChange(
                removed_ids, order_changed=bool(removed_ids), visibility_changed=bool(removed_ids)
            )
        )
        return self._last_change

    def _replace(self, record_id: int, **changes: object) -> TranscriptRecord:
        position = self._positions[record_id]
        record = self._records[position]
        updated = replace(record, revision=record.revision + 1, **changes)
        self._records[position] = updated
        return updated

    def _publish_change(self, change: TranscriptChange) -> None:
        if self._batch_depth == 0:
            self._last_change = change
            return
        for record_id in change.record_ids:
            if record_id not in self._batched_record_ids:
                self._batched_record_ids.append(record_id)
        self._batched_order_changed = self._batched_order_changed or change.order_changed
        self._batched_visibility_changed = (
            self._batched_visibility_changed or change.visibility_changed
        )

    @staticmethod
    def _tool_result_is_collapsible(result: str | None) -> bool:
        return result is not None and len(result.splitlines()) > 8

    def _rebuild_indexes(self) -> None:
        self._positions.clear()
        self._session_ids.clear()
        self._message_ids.clear()
        for position, record in enumerate(self._records):
            self._positions[record.record_id] = position
            self._session_ids.setdefault(record.session_id, []).append(record.record_id)
            if record.message_id is not None:
                self._message_ids[record.message_id] = record.record_id
        self._derived_agent_ids.intersection_update(self._positions)

    @staticmethod
    def _agent_id(session_id: str) -> str | None:
        agent_id, separator, _ = session_id.partition("_")
        return agent_id if separator and agent_id.startswith("a-") else None

    @staticmethod
    def _record_id(handle: TranscriptHandle | int) -> int:
        return handle.record_id if isinstance(handle, TranscriptHandle) else handle
