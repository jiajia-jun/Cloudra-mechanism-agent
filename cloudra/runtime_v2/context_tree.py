"""Event-sourced context tree: run summaries + system-maintained handover.

The event log already persists the raw trajectory of every run
(``agent.message_injected`` / ``tool.started`` / ``tool.finished`` /
``agent.message_emitted``, keyed by session_id + run_id).  The context tree
layers two derived event types on top instead of a separate store:

- ``context.run_summarized`` — appended when a run ends.  The summary is the
  compressed trajectory of that run (the segment between user requests);
  ``seq_range`` points back at the raw events for deep dives.
- ``context.handover_updated`` — the latest system-maintained HANDOVER: a
  project-state snapshot rewritten after each completed run.  Agents never
  maintain handoff files themselves.

On a fresh run the runner seeds the LLM history from ``build_seed_context``:
the newest HANDOVER plus, in chronological order, every injected instruction
(user messages, spawn queries, peer/email/reminder deliveries) kept verbatim,
paired with the compressed summaries of past runs — instructions keep full
weight, the agent's own output is reduced to its trajectory summary.  A run
that died with the process never got its ``context.run_summarized`` event; the
seed derives a deterministic summary from its raw events so that work is not
invisible to the next run.
"""

from __future__ import annotations

from typing import Any, Iterable

from cloudra.runtime_v2.events import EventLog

# Prefix of the seed block's leading system message.  The runner uses it to
# recognize (and exclude) a still-intact seed when serializing a finished run,
# so summaries never summarize earlier summaries.
SEED_MARKER = "[Context restored]"

RUN_LOG_MARKER = "[RUN LOG]"
HANDOVER_MARKER = "[HANDOVER]"

# Seed budget (characters).  User messages are always kept verbatim (each
# capped); when the total exceeds the budget, the oldest run summaries
# degrade to one-line pointers at the raw event range.
SEED_TOTAL_BUDGET = 24000
HANDOVER_BUDGET = 8000
USER_MESSAGE_CAP = 4000
# Cap for summary text stored inside compaction.finished / run event data.
SUMMARY_EVENT_CAP = 8000

RUN_SUMMARY_INSTRUCTION = (
    "You are maintaining an agent's long-term context tree. The agent just "
    "finished one run (the segment of work triggered by the latest user "
    "message). Produce exactly two sections in this format:\n"
    f"{RUN_LOG_MARKER}\n"
    "A compact trajectory of THIS run only: what the user asked, the main "
    "actions taken, tool/compute results that matter (paths, values, job "
    "states), errors encountered, and how the run ended. Ignore any leading "
    "restored-context block that describes earlier runs.\n"
    f"{HANDOVER_MARKER}\n"
    "The updated project-state snapshot: goal and progress, key artifacts and "
    "file paths, pending work, and the next concrete step. Rewrite it fresh — "
    "merge the previous handover with what this run changed and drop what is "
    "no longer relevant. It is the only continuity the agent gets after a "
    "restart, so it must stand alone.\n"
    "Write in the same language as the source messages. Be concise."
)


def session_events(
    event_log: EventLog, session_id: str, types: Iterable[str]
) -> list:
    """Chronological projection of one session's events of the given types."""
    wanted = frozenset(types)
    return [
        event
        for event in event_log
        if event.session_id == session_id and event.type in wanted
    ]


def latest_handover(event_log: EventLog, session_id: str) -> tuple[str, int] | None:
    """(handover_text, revision) of the newest handover event, or None."""
    events = session_events(event_log, session_id, {"context.handover_updated"})
    if not events:
        return None
    text = str(events[-1].data.get("handover") or "")
    return text, len(events)


def build_summary_messages(
    previous_handover: str | None, run_text: str
) -> list[dict[str, str]]:
    """LLM request for the run-end summary + handover rewrite."""
    parts = []
    if previous_handover:
        parts.append(
            "Previous handover (project state before this run):\n" + previous_handover
        )
    parts.append("This run's conversation:\n" + run_text)
    return [
        {"role": "system", "content": RUN_SUMMARY_INSTRUCTION},
        {"role": "user", "content": "\n\n".join(parts)},
    ]


def parse_summary_output(text: str) -> tuple[str, str | None]:
    """Split LLM output into (run_log, handover).

    Missing markers degrade gracefully: the whole text becomes the run log
    and the previous handover is kept (None).
    """
    run_log = ""
    handover: str | None = None
    if RUN_LOG_MARKER in text:
        after = text.split(RUN_LOG_MARKER, 1)[1]
        if HANDOVER_MARKER in after:
            run_log, hand = after.split(HANDOVER_MARKER, 1)
            handover = hand.strip() or None
        else:
            run_log = after
    elif HANDOVER_MARKER in text:
        handover = (text.split(HANDOVER_MARKER, 1)[1]).strip() or None
    else:
        run_log = text
    return run_log.strip(), handover


def fallback_run_summary(events: list) -> str:
    """Deterministic trajectory summary from a run's raw events (no LLM).

    Used when the summarizer fails, or for failed/cancelled runs where an
    extra LLM call is not warranted.  Never raises on odd event shapes.
    """
    lines: list[str] = []
    total = 0
    for event in events:
        data = event.data if isinstance(event.data, dict) else {}
        if event.type == "tool.finished":
            name = data.get("tool_name", "?")
            status = "ok" if data.get("is_success") else "failed"
            summary = str(data.get("result_summary") or "")[:200]
            line = f"- tool `{name}` ({status}): {summary}".rstrip()
        elif event.type == "agent.message_emitted":
            content = str(data.get("content") or "")[:300].strip()
            if not content:
                continue
            line = f"- final message: {content}"
        elif event.type == "run.finished":
            outcome = str(data.get("outcome") or "?")
            error = str(data.get("error") or "")[:200]
            line = f"- run finished ({outcome})" + (f": {error}" if error else "")
        else:
            continue
        if total + len(line) > SUMMARY_EVENT_CAP:
            lines.append("- ... (further events truncated; see event log)")
            break
        lines.append(line)
        total += len(line)
    return "\n".join(lines) or "(no recorded activity)"


# Event types fallback_run_summary knows how to render.  A run carrying these
# but no context.run_summarized died before finalization (process kill); its
# trajectory is folded into the seed as an auto-derived summary.
_ACTIVITY_EVENT_TYPES = frozenset({"tool.finished", "agent.message_emitted", "run.finished"})


def build_seed_context(
    event_log: EventLog,
    session_id: str,
    *,
    budget: int = SEED_TOTAL_BUDGET,
    exclude_message_ids: frozenset | None = None,
) -> list[dict[str, Any]]:
    """Rebuilt opening context for a fresh run, or [] for the very first run.

    Structure: one system message carrying the newest HANDOVER, then the
    chronological merge of every injected instruction message (role user) and
    each past run's compressed summary (role assistant).  Over budget, the
    oldest summaries degrade to pointer lines naming the raw event seq range.
    ``exclude_message_ids`` skips the messages the current turn is about to
    receive — they arrive through the inbox and must not appear twice.

    Runs that ended without a summary event (the process died mid-run, so the
    detached finalizer never ran) contribute a deterministic event-derived
    summary instead of vanishing from the seed.
    """
    summarized_run_ids = {
        event.run_id
        for event in event_log
        if event.session_id == session_id
        and event.type == "context.run_summarized"
        and event.run_id
    }
    merged: list[dict[str, Any]] = []
    orphan_run_id: str | None = None
    orphan_events: list = []

    def flush_orphan() -> None:
        nonlocal orphan_run_id, orphan_events
        if not orphan_events:
            orphan_run_id = None
            return
        seqs = [e.session_seq for e in orphan_events if e.session_seq is not None]
        seq_range = {"start": min(seqs), "end": max(seqs)} if seqs else None
        merged.append(
            {
                "role": "assistant",
                "content": (
                    f"[Run summary — run {orphan_run_id} ended without a final "
                    f"summary; auto-derived from raw events]\n"
                    f"{fallback_run_summary(orphan_events)}"
                ),
                # Temporary budgeting metadata; stripped before returning.
                "_pointer": (
                    f"[Unsummarized run {orphan_run_id} omitted for budget; "
                    f"raw events at seq {_fmt_seq_range(seq_range)} in the event log]"
                ),
            }
        )
        orphan_run_id = None
        orphan_events = []

    for event in event_log:
        if event.session_id != session_id:
            continue
        if (
            event.type in _ACTIVITY_EVENT_TYPES
            and event.run_id
            and event.run_id not in summarized_run_ids
        ):
            # Runs within a session are sequential; a run-id change (or the
            # end of the log) closes the previous unsummarized run.
            if orphan_run_id != event.run_id:
                flush_orphan()
                orphan_run_id = event.run_id
            orphan_events.append(event)
            continue
        if event.type == "agent.message_injected":
            if exclude_message_ids and event.data.get("message_id") in exclude_message_ids:
                continue
            content = str(event.data.get("content") or "").strip()
            if not content:
                continue
            if len(content) > USER_MESSAGE_CAP:
                content = (
                    content[:USER_MESSAGE_CAP]
                    + "\n[... truncated; full text in the event log]"
                )
            merged.append({"role": "user", "content": content})
        elif event.type == "context.run_summarized":
            summary = str(event.data.get("summary") or "").strip()
            if not summary:
                continue
            # A summarized run closes any earlier unsummarized one.
            flush_orphan()
            merged.append(
                {
                    "role": "assistant",
                    "content": f"[Run summary — compressed trajectory of run {event.run_id}]\n{summary}",
                    # Temporary budgeting metadata; stripped before returning.
                    "_pointer": (
                        f"[Earlier run {event.run_id} summary omitted for budget; "
                        f"raw events at seq {_fmt_seq_range(event.data.get('seq_range'))} "
                        "in the event log]"
                    ),
                }
            )
    flush_orphan()
    if not any(m["role"] == "assistant" for m in merged):
        # No run summary yet: nothing has ever completed, so a seed would only
        # duplicate messages the live history already carries.
        return []

    handover_text = ""
    handover = latest_handover(event_log, session_id)
    if handover is not None:
        handover_text = handover[0][:HANDOVER_BUDGET]
    header = (
        f"{SEED_MARKER} This agent ran before; its dialogue history was reset. "
        "Restored context follows: the system-maintained HANDOVER (current "
        "project state), every user message verbatim, and compressed summaries "
        "of past runs. Raw trajectories remain in the event log."
    )
    if handover_text:
        header += f"\n\n{HANDOVER_MARKER} — current project state\n{handover_text}"

    def total() -> int:
        return len(header) + sum(len(m["content"]) for m in merged)

    # Shrink the oldest summaries to pointer lines until within budget.
    for message in merged:
        if total() <= budget:
            break
        pointer = message.pop("_pointer", None)
        if pointer is not None and len(pointer) < len(message["content"]):
            message["content"] = pointer
    for message in merged:
        message.pop("_pointer", None)

    return [{"role": "system", "content": header}, *merged]


def _fmt_seq_range(seq_range: Any) -> str:
    if isinstance(seq_range, dict):
        return f"{seq_range.get('start', '?')}–{seq_range.get('end', '?')}"
    return "unknown"
