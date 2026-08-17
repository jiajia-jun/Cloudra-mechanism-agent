"""Incoming-call message template shared with runtime_v2's hub bridge.

The legacy AgentHub directory/call machinery (SQLite lookups, spawn-from-call,
follower resume) was removed with the v1 runtime; v2 reimplements call
semantics in ``runtime_v2/hub_bridge.py`` over Mailbox + CommandBus.
"""

from __future__ import annotations

INCOMING_CALL_TEMPLATE = (
    "[Incoming call] {caller_agent_id} is calling you (session={caller_session_id}). "
    "Answer this call first (prose or agent_hub call/post); "
    "do not check compute, change reminders, or stop first.\n\n"
)


def format_incoming_call(
    *,
    caller_agent_id: str,
    caller_session_id: str,
    message: str,
    post_line: str | None = None,
) -> str:
    # Spoken message is concatenated, not passed through str.format — braces
    # in user speech (e.g. {"freq": -1} or a lone "{") must stay literal.
    text = INCOMING_CALL_TEMPLATE.format(
        caller_agent_id=caller_agent_id,
        caller_session_id=caller_session_id or "unknown",
    ) + message.strip()
    if post_line:
        text = f"{text}\n{post_line}"
    return text
