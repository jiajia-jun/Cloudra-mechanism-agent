"""Project user requests for Supervisors, read from the durable event history."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cloudra.runtime_v2.core import RuntimeCore
    from cloudra.runtime_v2.schemas import AgentSession


SUPERVISOR_TASK_PIN_KEY = "supervisor-project-task"


def project_task_context(core: RuntimeCore, project_id: str) -> str:
    """Read complete user inputs without importing any Agent's reasoning.

    EventLog's existing lazy reader includes evicted durable history. Callers on
    the event loop must offload this read, because that prefix can live in SQLite.
    Sender provenance, not message wording, identifies user instructions.
    """
    events = core.event_log.query_project(
        project_id,
        types={"agent.message_injected", "hub.posted"},
        limit=None,
        tail=False,
    )
    requests = []
    for event in events:
        content = event.data.get("content")
        if not content:
            continue
        if event.type == "hub.posted" and event.data.get("author_agent") == "user":
            requests.append(f"[User forum post: {event.data.get('topic', '')}]\n{content}")
        elif (event.type == "agent.message_injected" and event.data.get("sender") == "user"
              and not event.data.get("post_id")):
            # Forum notifications are copies of the durable original above.
            requests.append(content)
    heading = "[Project user request and constraints]"
    if not requests:
        return (
            f"{heading}\nNo user request is recorded for this project. "
            "Do not infer missing user requirements from assistant reasoning "
            "or research notes."
        )
    sections = [
        heading,
        "The project's recorded direct user messages and user forum posts are reproduced in order "
        "and without truncation. Later user updates supersede earlier "
        "requests where they conflict. These are task inputs, not prior "
        "assistant conclusions.",
    ]
    sections.extend(
        f"[User request {index}]\n{content}"
        for index, content in enumerate(requests, start=1)
    )
    return "\n\n".join(sections)


async def sync_supervisor_task_context(core: RuntimeCore, agent: AgentSession) -> None:
    """Refresh the existing task pin; unchanged content is deduplicated by notices."""
    content = await asyncio.to_thread(project_task_context, core, agent.project_id)
    core.notices.pin(agent.id, SUPERVISOR_TASK_PIN_KEY, content)
