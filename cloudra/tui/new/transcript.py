"""Immutable, ordered presentation records for the Textual transcript."""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum


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
        self._next_record_id = 1
        self._last_change = TranscriptChange()

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
                self._last_change = TranscriptChange()
                return TranscriptHandle(existing_id)

        record_id = self._next_record_id
        self._next_record_id += 1
        record = TranscriptRecord(
            record_id=record_id,
            session_id=session_id,
            agent_id=self._agent_id(session_id) if agent_id is None else agent_id,
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
        if message_id is not None:
            self._message_ids[message_id] = record_id
        self._last_change = TranscriptChange((record_id,), order_changed=True, visibility_changed=True)
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
            self._last_change = TranscriptChange()
            return self._last_change

        for record_id in record_ids:
            self._replace(record_id, session_id=new_session_id)
        self._rebuild_indexes()
        self._last_change = TranscriptChange(record_ids, visibility_changed=True)
        return self._last_change

    def mark_send_failed(self, handle: TranscriptHandle | int) -> TranscriptChange:
        record_id = self._record_id(handle)
        self._replace(record_id, send_failed=True)
        self._last_change = TranscriptChange((record_id,))
        return self._last_change

    def clear_session(self, session_id: str) -> TranscriptChange:
        removed_ids = tuple(self._session_ids.get(session_id, ()))
        if not removed_ids:
            self._last_change = TranscriptChange()
            return self._last_change

        removed = set(removed_ids)
        self._records = [record for record in self._records if record.record_id not in removed]
        self._rebuild_indexes()
        self._last_change = TranscriptChange(
            removed_ids, order_changed=True, visibility_changed=True
        )
        return self._last_change

    def clear(self) -> TranscriptChange:
        removed_ids = tuple(record.record_id for record in self._records)
        self._records.clear()
        self._positions.clear()
        self._session_ids.clear()
        self._message_ids.clear()
        self._last_change = TranscriptChange(
            removed_ids, order_changed=bool(removed_ids), visibility_changed=bool(removed_ids)
        )
        return self._last_change

    def _replace(self, record_id: int, **changes: object) -> TranscriptRecord:
        position = self._positions[record_id]
        record = self._records[position]
        updated = replace(record, revision=record.revision + 1, **changes)
        self._records[position] = updated
        return updated

    def _rebuild_indexes(self) -> None:
        self._positions.clear()
        self._session_ids.clear()
        self._message_ids.clear()
        for position, record in enumerate(self._records):
            self._positions[record.record_id] = position
            self._session_ids.setdefault(record.session_id, []).append(record.record_id)
            if record.message_id is not None:
                self._message_ids[record.message_id] = record.record_id

    @staticmethod
    def _agent_id(session_id: str) -> str | None:
        agent_id, separator, _ = session_id.partition("_")
        return agent_id if separator and agent_id.startswith("a-") else None

    @staticmethod
    def _record_id(handle: TranscriptHandle | int) -> int:
        return handle.record_id if isinstance(handle, TranscriptHandle) else handle
