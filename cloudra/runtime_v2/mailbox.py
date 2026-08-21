"""Uniform delivery for user and peer messages.

Every message is one event + one inbox enqueue.  The runtime never inspects
sender authority beyond the caller-provided actor: the command layer performs
authorization before calling deliver.
"""

from __future__ import annotations

import asyncio
from typing import Any

from cloudra.runtime_v2.events import EventLog
from cloudra.runtime_v2.schemas import EventEnvelope, new_id


class Mailbox:
    def __init__(self, event_log: EventLog) -> None:
        self._event_log = event_log
        self._inboxes: dict[str, asyncio.Queue[dict[str, Any]]] = {}

    def ensure_inbox(self, session_id: str) -> asyncio.Queue[dict[str, Any]]:
        return self._inboxes.setdefault(session_id, asyncio.Queue())

    def inbox(self, session_id: str) -> asyncio.Queue[dict[str, Any]] | None:
        return self._inboxes.get(session_id)

    def deliver(
        self,
        *,
        to_session_id: str,
        project_id: str,
        content: str,
        sender: str,
        run_id: str | None = None,
        images: list[str] | None = None,
        image_artifact_ids: list[str | None] | None = None,
    ) -> EventEnvelope:
        message_id = new_id("msg")
        data: dict[str, Any] = {"message_id": message_id, "sender": sender, "content": content}
        if images:
            # Workspace-absolute image paths attached by the user; the runner
            # turns them into vision parts (or a text fallback) and the
            # frontend renders them on the user bubble.
            data["images"] = list(images)
        if image_artifact_ids:
            # Parallel to images: artifact ids let the frontend rebuild bubble
            # image URLs after a reload (paths alone are not HTTP-reachable).
            data["image_artifact_ids"] = list(image_artifact_ids)
        envelope = self._event_log.append(
            "agent.message_injected",
            stream="project",
            project_id=project_id,
            session_id=to_session_id,
            run_id=run_id,
            data=data,
        )
        inbox = self.ensure_inbox(to_session_id)
        inbox.put_nowait(
            {
                "type": "message",
                "message_id": message_id,
                "sender": sender,
                "content": content,
                **({"images": list(images)} if images else {}),
            }
        )
        return envelope
