"""Context compaction for the runner's in-memory history.

The compaction *unit* is the agent/tool tail after the last instruction
message.  Instruction messages are user turns and schedule wake-ups
(``[Reminder] ...``); a compact handoff itself is not an instruction, so a
later compact still folds against the same user/schedule boundary.

Cadence:
- each ``stop`` folds that tail once (keep_recent=0)
- a 400/413 context-window overflow still emergency-compacts once and retries
- ``/compact`` uses the same unit, optionally keeping a recent verbatim tail

The handoff is an **assistant** summary, never ``role: user``: injecting a
user message made the model treat compact as a new turn and stop working.
"""

from __future__ import annotations

from typing import Any, Awaitable, Callable

from cloudra.runtime_v2.schemas import AgentSession

# messages -> summary text
Summarizer = Callable[[list[dict[str, Any]]], Awaitable[str]]

_COMPACT_MARKER = "[Context compact]"
_REMINDER_PREFIX = "[Reminder]"

_COMPACT_INSTRUCTION = (
    "You are compacting an agent's work after the last user or schedule "
    "(reminder) message. Summarize the following agent/tool messages into a "
    "concise handoff for the same agent: keep the task goal, decisions made, "
    "tool results that matter (paths, computed values, error states), and the "
    "current state of the work. Drop chit-chat and superseded attempts. Write "
    "in the same language as the source messages."
)

_MAX_HEAD_CHARS = 12000
_PER_MESSAGE_CHARS = 2000


def is_instruction_message(message: dict[str, Any]) -> bool:
    """True for a user turn or schedule wake-up; false for compact handoffs."""
    content = _content_to_text(message.get("content"))
    if content.startswith(_COMPACT_MARKER):
        return False
    if content.startswith(_REMINDER_PREFIX):
        return True
    return message.get("role") == "user"


def _last_instruction_index(history: list[dict[str, Any]]) -> int:
    for i in range(len(history) - 1, -1, -1):
        if is_instruction_message(history[i]):
            return i
    return -1


def _split_tail_start(history: list[dict[str, Any]], keep_recent: int) -> int:
    start = max(0, len(history) - keep_recent)
    # Never start the tail on a tool message: its assistant parent (with the
    # matching tool_calls) would end up in the compacted head.
    while start < len(history) and history[start].get("role") == "tool":
        start += 1
    return start


def _split_compact_range(history: list[dict[str, Any]], keep_recent: int) -> tuple[int, int]:
    """Return ``(dropped_start, tail_start)`` after the last instruction.

    Prefix ``history[:dropped_start]`` is kept verbatim (includes the last
    user/schedule message).  ``keep_recent <= 0`` folds the whole agent tail.
    """
    dropped_start = _last_instruction_index(history) + 1
    if keep_recent <= 0:
        return dropped_start, len(history)
    tail_start = max(_split_tail_start(history, keep_recent), dropped_start)
    return dropped_start, tail_start


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
        # temperature=1: a growing set of models rejects anything else.
        temperature=1.0,
        stream=False,
    )
    choices = getattr(response, "choices", None) or []
    if not choices:
        return ""
    return getattr(getattr(choices[0], "message", None), "content", None) or ""


def _handoff_text(dropped_count: int, summary: str, trigger: str) -> str:
    body = (
        f"{_COMPACT_MARKER} {dropped_count} agent messages after the last "
        f"user/schedule message were compacted into this summary."
    )
    if trigger == "context_overflow":
        body += (
            " Continue the current task by calling tools; this is not a new "
            "user request."
        )
    return f"{body}\n{summary}"


async def compact_history(
    history: list[dict[str, Any]],
    keep_recent: int,
    summarize: Summarizer,
    *,
    trigger: str = "manual",
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Compact the agent tail after the last user/schedule message.

    ``stats["compacted"]`` is False when that tail is already within
    ``keep_recent`` (or empty).
    """
    dropped_start, tail_start = _split_compact_range(history, keep_recent)
    dropped = history[dropped_start:tail_start]
    if not dropped:
        return history, {"compacted": False, "keep_recent": keep_recent}
    summary = (
        await summarize(
            [
                {"role": "system", "content": _COMPACT_INSTRUCTION},
                {"role": "user", "content": _serialize(dropped)},
            ]
        )
    ).strip() or "(no summary produced)"
    handoff = {"role": "assistant", "content": _handoff_text(len(dropped), summary, trigger)}
    new_history = [*history[:dropped_start], handoff, *history[tail_start:]]
    return new_history, {
        "compacted": True,
        "before_messages": len(history),
        "after_messages": len(new_history),
        "handoff_index": dropped_start,
        "keep_recent": keep_recent,
    }
