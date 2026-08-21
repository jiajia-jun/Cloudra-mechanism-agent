"""Manual context compaction for the runner's in-memory history.

runtime_v2 keeps an agent's LLM history in memory (AgentRunner._run local),
so compaction rewrites that list directly: the older head is summarized by a
one-off LLM call into a handoff message, the recent tail is kept verbatim.
The tail split is aligned to tool-call pairs so no dangling tool messages are
left without their assistant parent (or vice versa).
"""

from __future__ import annotations

from typing import Any, Awaitable, Callable

from cloudra.runtime_v2.schemas import AgentSession

# messages -> summary text
Summarizer = Callable[[list[dict[str, Any]]], Awaitable[str]]

_COMPACT_INSTRUCTION = (
    "You are compacting an agent's conversation history. Summarize the "
    "following earlier messages into a concise handoff for the same agent: "
    "keep the task goal, decisions made, tool results that matter (paths, "
    "computed values, error states), and the current state of the work. "
    "Drop chit-chat and superseded attempts. Write in the same language as "
    "the source messages."
)

_MAX_HEAD_CHARS = 12000
_PER_MESSAGE_CHARS = 2000


def _split_tail_start(history: list[dict[str, Any]], keep_recent: int) -> int:
    start = max(0, len(history) - keep_recent)
    # Never start the tail on a tool message: its assistant parent (with the
    # matching tool_calls) would end up in the compacted head.
    while start < len(history) and history[start].get("role") == "tool":
        start += 1
    return start


def _content_to_text(content: Any) -> str:
    """Flatten message content to plain text for the summarizer.

    Visual-mode histories carry parts lists (text + image_url with a base64
    data URL).  Feeding the raw list into ``str()`` would dump the whole
    base64 payload into the summarization call, so image parts degrade to a
    one-line text fallback here.
    """
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        texts = []
        for part in content:
            if not isinstance(part, dict):
                texts.append(str(part))
                continue
            if part.get("type") == "image_url":
                url = str((part.get("image_url") or {}).get("url") or "")
                mime = url[5:].split(";", 1)[0] if url.startswith("data:") else "external"
                texts.append(f"[Image: {mime} attachment omitted during compaction]")
            else:
                texts.append(str(part.get("text") or ""))
        return " ".join(text for text in texts if text)
    return str(content)


def _serialize(messages: list[dict[str, Any]]) -> str:
    lines = []
    total = 0
    for message in messages:
        role = message.get("role", "?")
        content = _content_to_text(message.get("content"))
        if message.get("tool_calls"):
            names = ", ".join(str(c.get("name", "?")) for c in message["tool_calls"])
            content = f"{content} [tool_calls: {names}]".strip()
        line = f"{role}: {content[:_PER_MESSAGE_CHARS]}"
        if total + len(line) > _MAX_HEAD_CHARS:
            lines.append(f"... ({len(messages) - len(lines)} earlier messages omitted)")
            break
        lines.append(line)
        total += len(line)
    return "\n".join(lines)


async def summarize_with_agent_settings(
    agent: AgentSession, messages: list[dict[str, Any]]
) -> str:
    """Default summarizer: one non-streaming call on the agent's own model."""
    from cloudra.infra.llm_client import LLMClient
    from cloudra.runtime_v2.adapters import legacy_default_settings

    settings = legacy_default_settings(agent)
    client = LLMClient(
        api_key=settings.api_key,
        base_url=settings.base_url,
        timeout=settings.timeout,
    )
    response = await client.create_with_retry(
        model=settings.model,
        messages=messages,
        temperature=0.2,
        stream=False,
    )
    choices = getattr(response, "choices", None) or []
    if not choices:
        return ""
    return getattr(getattr(choices[0], "message", None), "content", None) or ""


async def compact_history(
    history: list[dict[str, Any]],
    keep_recent: int,
    summarize: Summarizer,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Compact ``history`` in place semantics: returns (new_history, stats).

    ``stats["compacted"]`` is False when the history is already short enough.
    """
    start = _split_tail_start(history, keep_recent)
    if start == 0:
        return history, {"compacted": False, "keep_recent": keep_recent}
    head, tail = history[:start], history[start:]
    summary = (
        await summarize(
            [
                {"role": "system", "content": _COMPACT_INSTRUCTION},
                {"role": "user", "content": _serialize(head)},
            ]
        )
    ).strip() or "(no summary produced)"
    handoff = {
        "role": "user",
        "content": (
            f"[Context compact] The earlier conversation ({len(head)} messages) "
            f"was compacted into this summary. Continue from it.\n{summary}"
        ),
    }
    return [handoff, *tail], {
        "compacted": True,
        "before_messages": len(history),
        "after_messages": 1 + len(tail),
    }
