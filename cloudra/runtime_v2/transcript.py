"""Human-readable full transcript of a project's event stream.

Built for offline diagnosis and ablation analysis: every persisted event is
rendered in chronological order with its FULL payload — messages, thinking
chains, tool arguments/results, compaction summaries, context-tree snapshots
— nothing is truncated.  ``llm.chunk`` deltas are transient by design (never
persisted); the per-turn ``agent.thinking`` events carry the complete
reasoning, so no content is lost.

The output is a single Markdown document: ``##`` for run boundaries, ``###``
blocks (fenced, full content) for messages/thinking/tools, and one-line
entries for lifecycle metadata.  Pure functions — no I/O, no async.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from cloudra.runtime_v2.schemas import AgentSession, EventEnvelope, Project

# Transient or hub-only control markers: no diagnostic value in a static dump.
_SKIP_TYPES = frozenset({"llm.chunk", "project.synced"})


def _fence(text: str) -> str:
    """Backtick fence guaranteed longer than any run inside ``text``."""
    longest = run = 0
    for ch in text:
        run = run + 1 if ch == "`" else 0
        longest = max(longest, run)
    return "`" * max(3, longest + 1)


def _stamp(event: EventEnvelope) -> str:
    return event.created_at.astimezone(timezone.utc).isoformat(timespec="seconds")


def _json_block(lines: list[str], value: Any) -> None:
    text = json.dumps(value, ensure_ascii=False, indent=2, default=str)
    fence = _fence(text)
    lines.append(fence)
    lines.append(text)
    lines.append(fence)


def _text_block(lines: list[str], text: str) -> None:
    fence = _fence(text)
    lines.append(fence)
    lines.append(text)
    lines.append(fence)


def render_project_transcript(
    project: Project,
    agents: dict[str, AgentSession],
    events: list[EventEnvelope],
) -> str:
    """Render one project's events as a single Markdown document."""

    def label(session_id: str | None) -> str:
        agent = agents.get(session_id or "")
        if agent is None:
            return session_id or "system"
        return f"{agent.display_name} ({agent.role_id})"

    lines: list[str] = [
        f"# Cloudra transcript — {project.name}",
        "",
        f"- project_id: `{project.id}`",
        f"- generated_at: {datetime.now(timezone.utc).isoformat(timespec='seconds')}",
        f"- events: {len(events)}",
        "",
        "Agents:",
    ]
    for agent in agents.values():
        if agent.project_id == project.id:
            lines.append(f"- `{agent.id}` — {agent.display_name} ({agent.role_id})")
    lines.append("")

    pending_tools: dict[str, EventEnvelope] = {}
    for event in events:
        if event.type in _SKIP_TYPES:
            continue
        data = event.data if isinstance(event.data, dict) else {}
        who = label(event.session_id)
        head = f"[{_stamp(event)} seq={event.seq}]"

        if event.type == "run.started":
            lines.append(f"## ▶ Run `{event.run_id}` — {who} started")
            settings = data.get("settings_summary")
            if settings:
                lines.append(f"- settings: `{json.dumps(settings, ensure_ascii=False, default=str)}`")
            lines.append("")
        elif event.type == "run.finished":
            outcome = data.get("outcome", "?")
            lines.append(f"## ■ Run `{event.run_id}` finished — **{outcome}**")
            if data.get("error"):
                lines.append(f"- error: {data['error']}")
            lines.append("")
        elif event.type == "agent.message_injected":
            sender = data.get("sender", "?")
            lines.append(f"### 💬 {head} {sender} → {who}")
            _text_block(lines, str(data.get("content") or ""))
            images = data.get("images") or []
            if images:
                lines.append(f"- attached images: {', '.join(str(p) for p in images)}")
            lines.append("")
        elif event.type == "agent.message_emitted":
            lines.append(f"### 🤖 {head} {who}")
            _text_block(lines, str(data.get("content") or ""))
            lines.append("")
        elif event.type == "agent.thinking":
            lines.append(f"### 🧠 {head} thinking — {who}")
            _text_block(lines, str(data.get("content") or ""))
            lines.append("")
        elif event.type == "tool.started":
            pending_tools[str(data.get("tool_call_id") or "")] = event
        elif event.type == "tool.finished":
            call_id = str(data.get("tool_call_id") or "")
            started = pending_tools.pop(call_id, None)
            name = data.get("tool_name", "?")
            status = "ok" if data.get("is_success") else "FAILED"
            duration = data.get("duration_ms")
            suffix = f" · {duration}ms" if duration is not None else ""
            lines.append(f"### 🔧 {head} `{name}` — {status}{suffix} · {who}")
            arguments = (started.data if started else {}).get("arguments_summary")
            if arguments is not None:
                lines.append("arguments:")
                _json_block(lines, arguments)
            summary = str(data.get("result_summary") or "")
            if summary:
                lines.append("result:")
                _text_block(lines, summary)
            if data.get("artifact_id"):
                lines.append(f"- artifact: `{data['artifact_id']}`")
            lines.append("")
        elif event.type == "tool.blocked":
            lines.append(
                f"### ⛔ {head} `{data.get('tool_name', '?')}` blocked by {data.get('stage', '?')} · {who}"
            )
            _text_block(lines, str(data.get("message") or ""))
            lines.append("")
        elif event.type in {"compaction.requested", "compaction.started"}:
            lines.append(f"- {head} **{event.type}** · {who} · `{json.dumps(data, ensure_ascii=False, default=str)}`")
        elif event.type == "compaction.finished":
            lines.append(f"### 🗜 {head} compaction finished — {who}")
            stats = {k: v for k, v in data.items() if k != "summary"}
            lines.append(f"- stats: `{json.dumps(stats, ensure_ascii=False, default=str)}`")
            if data.get("summary"):
                lines.append("summary:")
                _text_block(lines, str(data["summary"]))
            lines.append("")
        elif event.type == "context.run_summarized":
            outcome = data.get("outcome", "?")
            fallback = " (fallback)" if data.get("fallback") else ""
            lines.append(f"### 🗂 {head} run summary — {who} · {outcome}{fallback}")
            seq_range = data.get("seq_range")
            if seq_range:
                lines.append(f"- raw events: session_seq {seq_range.get('start')}–{seq_range.get('end')}")
            _text_block(lines, str(data.get("summary") or ""))
            lines.append("")
        elif event.type == "context.handover_updated":
            lines.append(f"### 📦 {head} HANDOVER updated — {who} · revision {data.get('revision', '?')}")
            _text_block(lines, str(data.get("handover") or ""))
            lines.append("")
        elif event.type == "context.pin_set":
            lines.append(f"### 📌 {head} notice pin set — {who} · key `{data.get('key', '?')}`")
            _text_block(lines, str(data.get("content") or ""))
            lines.append("")
        elif event.type == "context.pin_cleared":
            lines.append(f"- {head} **context.pin_cleared** · {who} · key `{data.get('key', '?')}`")
        elif event.type == "context.injected":
            lines.append(f"### 💉 {head} one-shot notice injected — {who}")
            _text_block(lines, str(data.get("content") or ""))
            lines.append("")
        elif event.type in {"approval.requested", "interaction.requested"}:
            lines.append(f"### ✋ {head} {event.type} — {who}")
            _text_block(lines, str(data.get("message") or data.get("question") or json.dumps(data, ensure_ascii=False, default=str)))
            lines.append("")
        elif event.type in {"approval.decided", "interaction.responded"}:
            lines.append(f"- {head} **{event.type}** · {who} · `{json.dumps(data, ensure_ascii=False, default=str)}`")
        elif event.type == "email.received":
            lines.append(f"### 📧 {head} email — {data.get('sender', '?')}: {data.get('subject', '')}")
            _text_block(lines, str(data.get("body") or ""))
            lines.append("")
        elif event.type == "hub.posted":
            lines.append(f"### 📣 {head} hub post — {who}")
            _text_block(lines, str(data.get("content") or ""))
            lines.append("")
        elif event.type in {"llm.completed", "llm.failed", "llm.request_started", "run.retry",
                            "agent.state_changed", "loop.detected", "agent.warning",
                            "agent.context_reset", "reminder.scheduled", "reminder.fired",
                            "reminder.cancelled"}:
            lines.append(f"- {head} **{event.type}** · {who} · `{json.dumps(data, ensure_ascii=False, default=str)}`")
        elif event.type.startswith(("agent.", "project.", "role.", "command.")):
            # spawn/cancel/restart/settings and other lifecycle one-liners
            lines.append(f"- {head} **{event.type}** · {who} · `{json.dumps(data, ensure_ascii=False, default=str)}`")
        else:
            lines.append(f"### ❓ {head} {event.type} · {who}")
            _json_block(lines, data)
            lines.append("")
    return "\n".join(lines) + "\n"
