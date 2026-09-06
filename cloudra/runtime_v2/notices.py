"""Unified per-session context injection for the v2 turn pipeline.

Two channels, collected only when ``TurnPipeline`` assembles the LLM
request:

- ``pin(session_id, key, content)`` / ``unpin``: idempotent-by-key resident
  injections rebuilt every turn (goal anchor, DAG projection, supervisor
  advice).  Re-pinning the same key replaces content and keeps registration
  order.
- ``push(session_id, content)``: one-shot; drained the next time
  ``collect`` runs, then gone.

``collect`` renders pins first (registration order), then drained pushes,
each as ``{"role": "system", "content": ...}``.  Tool-result attachments
(``[DAG]`` lines inside a ToolResult) stay on that channel.

Event sourcing: when ``attach``ed (RuntimeCore does this), every *change*
is also an event — ``context.pin_set`` / ``context.pin_cleared`` /
``context.injected`` — so injections are auditable, replayable, and
reachable from outside the process (the ``context.inject`` command).
Stages re-pin identical content every turn; those no-op writes are
deduplicated and produce no events, keeping the log sparse.  Pins are
restored from the event projection on startup (``restore_from``); pushes
are not restored — a one-shot hint that died unconsumed with the process
is gone, and its event remains as the audit record.
"""

from __future__ import annotations

from collections import OrderedDict, defaultdict
from typing import Callable

from cloudra.runtime_v2.events import EventLog


class NoticeManager:
    def __init__(self) -> None:
        self._pins: dict[str, OrderedDict[str, str]] = defaultdict(OrderedDict)
        self._pushes: dict[str, list[str]] = defaultdict(list)
        self._event_log: EventLog | None = None
        self._project_of: Callable[[str], str | None] | None = None

    def attach(
        self,
        event_log: EventLog,
        project_of: Callable[[str], str | None],
    ) -> None:
        """Wire persistence: pin/push changes become events.

        ``project_of`` resolves a session id to its project id (events are
        project-scoped); returning None skips the event (in-memory only).
        """
        self._event_log = event_log
        self._project_of = project_of

    def _emit(self, type: str, session_id: str, data: dict) -> None:
        if self._event_log is None or self._project_of is None:
            return
        project_id = self._project_of(session_id)
        if project_id is None:
            return
        self._event_log.append(
            type,
            stream="agent",
            project_id=project_id,
            session_id=session_id,
            data=data,
        )

    def restore_from(self, event_log: EventLog) -> None:
        """Rebuild pins from the event projection (see module docstring)."""
        self._pins.clear()
        for event in event_log:
            if event.session_id is None:
                continue
            if event.type == "context.pin_set":
                key = str(event.data.get("key") or "")
                if key:
                    self._pins[event.session_id][key] = str(event.data.get("content") or "")
            elif event.type == "context.pin_cleared":
                pins = self._pins.get(event.session_id)
                if pins is not None:
                    pins.pop(str(event.data.get("key") or ""), None)

    def pin(self, session_id: str, key: str, content: str) -> None:
        text = content if content is not None else ""
        pins = self._pins[session_id]
        # Dedup: stages re-pin identical content every turn; only actual
        # changes are worth an event.
        if pins.get(key) != text:
            self._emit("context.pin_set", session_id, {"key": key, "content": text})
        pins[key] = text

    def pin_content(self, session_id: str, key: str) -> str | None:
        """当前 pin 内容（无则 None）：一次性告警按内容指纹去重的读取口。

        pin 由事件投影恢复（restore_from），跨重启比较依然成立——内容不变
        就不应重复投递配套的一次性消息。
        """
        return self._pins.get(session_id, {}).get(key)

    def unpin(self, session_id: str, key: str) -> None:
        pins = self._pins.get(session_id)
        if pins is None:
            return
        if key in pins:
            self._emit("context.pin_cleared", session_id, {"key": key})
        pins.pop(key, None)
        if not pins:
            self._pins.pop(session_id, None)

    def push(self, session_id: str, content: str) -> None:
        if content:
            self._emit("context.injected", session_id, {"content": content})
            self._pushes[session_id].append(content)

    def collect(self, session_id: str) -> list[dict[str, str]]:
        messages: list[dict[str, str]] = []
        for content in self._pins.get(session_id, {}).values():
            if content:
                messages.append({"role": "system", "content": content})
        pushed = self._pushes.pop(session_id, [])
        for content in pushed:
            if content:
                messages.append({"role": "system", "content": content})
        return messages
