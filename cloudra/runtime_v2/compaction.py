"""Context compaction for the runner's in-memory history.

The compaction *unit* is the agent/tool tail after the last instruction
message.  Instruction messages are user turns and schedule wake-ups
(``[Reminder] ...``); a compact handoff itself is not an instruction, so a
later compact still folds against the same user/schedule boundary.

Cadence:
- ``stop`` after a ``[Reminder]`` folds that tail (keep_recent=0)
- ``stop`` after a user message does not compact
- a 400/413 overflow first folds earlier completed user turns, then the
  current tail (keep_recent), then fails
- ``/compact`` uses the last-instruction unit, optionally keeping a verbatim tail

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


def is_reminder_message(message: dict[str, Any]) -> bool:
    """True for a schedule wake-up (``[Reminder] ...``), not a compact handoff."""
    content = _content_to_text(message.get("content"))
    if content.startswith(_COMPACT_MARKER):
        return False
    return content.startswith(_REMINDER_PREFIX)


def is_instruction_message(message: dict[str, Any]) -> bool:
    """True for a user turn or schedule wake-up; false for compact handoffs."""
    if is_reminder_message(message):
        return True
    content = _content_to_text(message.get("content"))
    if content.startswith(_COMPACT_MARKER):
        return False
    return message.get("role") == "user"


def last_instruction_is_reminder(history: list[dict[str, Any]]) -> bool:
    idx = _last_instruction_index(history)
    return idx >= 0 and is_reminder_message(history[idx])


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


def _instruction_chapters(history: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    """Split history into chapters that start at each instruction message."""
    chapters: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    for message in history:
        if is_instruction_message(message):
            if current:
                chapters.append(current)
            current = [message]
        elif current:
            current.append(message)
        else:
            current = [message]
    if current:
        chapters.append(current)
    return chapters


def _handoff_text_prior_turns(dropped_count: int, summary: str, trigger: str) -> str:
    body = (
        f"{_COMPACT_MARKER} {dropped_count} agent messages from earlier user "
        f"turns were compacted into this summary."
    )
    if trigger == "context_overflow":
        body += (
            " Continue the current task by calling tools; this is not a new "
            "user request."
        )
    return f"{body}\n{summary}"


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


def _prior_turn_dropped(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    chapters = _instruction_chapters(history)
    last_instr = None
    for index, chapter in enumerate(chapters):
        if chapter and is_instruction_message(chapter[0]):
            last_instr = index
    if last_instr is None:
        return []
    dropped: list[dict[str, Any]] = []
    for chapter in chapters[:last_instr]:
        if chapter and is_instruction_message(chapter[0]):
            dropped.extend(chapter[1:])
    return dropped


def can_compact_completed_user_turns(history: list[dict[str, Any]]) -> bool:
    return bool(_prior_turn_dropped(history))


async def compact_completed_user_turns(
    history: list[dict[str, Any]],
    summarize: Summarizer,
    *,
    trigger: str = "context_overflow",
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Fold agent tails of completed instruction chapters; keep the current turn.

    Instruction messages (user / reminder) stay verbatim.  A leading
    non-instruction prefix (the restored-context seed) is kept as-is.
    ``stats["compacted"]`` is False when there is no prior chapter tail.
    """
    chapters = _instruction_chapters(history)
    last_instr = None
    for index, chapter in enumerate(chapters):
        if chapter and is_instruction_message(chapter[0]):
            last_instr = index
    dropped = _prior_turn_dropped(history)
    if last_instr is None or not dropped:
        return history, {"compacted": False, "keep_recent": 0}
    summary = (
        await summarize(
            [
                {"role": "system", "content": _COMPACT_INSTRUCTION},
                {"role": "user", "content": _serialize(dropped)},
            ]
        )
    ).strip() or "(no summary produced)"
    handoff = {
        "role": "assistant",
        "content": _handoff_text_prior_turns(len(dropped), summary, trigger),
    }
    new_history: list[dict[str, Any]] = []
    for index, chapter in enumerate(chapters):
        if index == last_instr:
            new_history.append(handoff)
            new_history.extend(chapter)
        elif chapter and is_instruction_message(chapter[0]):
            new_history.append(chapter[0])
        else:
            new_history.extend(chapter)
    handoff_index = new_history.index(handoff)
    return new_history, {
        "compacted": True,
        "before_messages": len(history),
        "after_messages": len(new_history),
        "handoff_index": handoff_index,
        "keep_recent": 0,
        "unit": "prior_turns",
    }
