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
"""

from __future__ import annotations

from collections import OrderedDict, defaultdict


class NoticeManager:
    def __init__(self) -> None:
        self._pins: dict[str, OrderedDict[str, str]] = defaultdict(OrderedDict)
        self._pushes: dict[str, list[str]] = defaultdict(list)

    def pin(self, session_id: str, key: str, content: str) -> None:
        text = content if content is not None else ""
        pins = self._pins[session_id]
        if key in pins:
            pins[key] = text
        else:
            pins[key] = text

    def unpin(self, session_id: str, key: str) -> None:
        pins = self._pins.get(session_id)
        if pins is None:
            return
        pins.pop(key, None)
        if not pins:
            self._pins.pop(session_id, None)

    def push(self, session_id: str, content: str) -> None:
        if content:
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
