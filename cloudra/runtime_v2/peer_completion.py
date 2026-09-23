"""One-shot completion notification for a peer created by AgentHub call.

The requester is a notification address, never a parent.  The obligation is
derived from the peer's durable spawn projection and its first *final* terminal
transition.  A run parked for background work has state ``succeeded`` but is
not a result; a later run can fulfill the same call.  Subsequent unrelated
runs are not forwarded to the original requester.  A durable
``agent.message_injected`` carrying a peer completion manifest is the delivery
marker used by live and restore paths.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from cloudra.runtime_v2.dispatcher import WakePolicy
from cloudra.runtime_v2.schemas import AgentSession, EventEnvelope

_TERMINAL_STATES = frozenset({"succeeded", "failed", "cancelled"})
_REPORT_KIND = "peer_call_completion"


@dataclass(slots=True)
class PeerCompletionIndex:
    """One pass over the event log for every peer pending a first result."""

    terminal_by_session: dict[str, EventEnvelope]
    final_message_by_session: dict[str, EventEnvelope]
    finished_by_run: dict[tuple[str, str], EventEnvelope]
    reported: set[tuple[str, str]]


def build_peer_completion_index(core) -> PeerCompletionIndex:
    """Index restore/live facts in one log pass, with storage bounded by peer runs."""
    peer_ids = {
        agent.id
        for agent in core.agents.values()
        if agent.requested_by_session_id and agent.parent_session_id is None
    }
    terminal_by_session: dict[str, EventEnvelope] = {}
    final_message_by_session: dict[str, EventEnvelope] = {}
    finished_by_run: dict[tuple[str, str], EventEnvelope] = {}
    reported: set[tuple[str, str]] = set()
    latest_gate_by_run: dict[tuple[str, str], str] = {}
    latest_message_by_run: dict[tuple[str, str], EventEnvelope] = {}
    if not peer_ids:
        return PeerCompletionIndex(
            terminal_by_session=terminal_by_session,
            final_message_by_session=final_message_by_session,
            finished_by_run=finished_by_run,
            reported=reported,
        )

    for event in core.event_log:
        session_id = event.session_id
        if event.type == "agent.message_injected" and session_id:
            manifest = event.data.get("manifest")
            if isinstance(manifest, dict) and manifest.get("kind") == _REPORT_KIND:
                peer_id = manifest.get("session_id")
                if isinstance(peer_id, str) and peer_id in peer_ids:
                    reported.add((session_id, peer_id))
        if session_id not in peer_ids:
            continue
        run_key = (session_id, event.run_id or "")
        if event.type == "run.finished":
            terminal = terminal_by_session.get(session_id)
            if terminal is not None and event.run_id == terminal.run_id:
                finished_by_run[run_key] = event
        elif event.type == "agent.completion_gate" and event.run_id:
            if session_id not in terminal_by_session:
                latest_gate_by_run[run_key] = str(event.data.get("action") or "")
        elif event.type == "agent.message_emitted" and event.run_id:
            if session_id not in terminal_by_session and str(event.data.get("content") or "").strip():
                latest_message_by_run[run_key] = event
        elif event.type == "agent.state_changed" and session_id not in terminal_by_session:
            state = event.data.get("to")
            if state not in _TERMINAL_STATES:
                continue
            # wait_background parks a run as SUCCEEDED; the peer owes its
            # requester the result of a later final run.
            if state == "succeeded" and latest_gate_by_run.get(run_key) == "wait_background":
                continue
            terminal_by_session[session_id] = event
            final = latest_message_by_run.get(run_key)
            if final is not None:
                final_message_by_session[session_id] = final

    return PeerCompletionIndex(
        terminal_by_session=terminal_by_session,
        final_message_by_session=final_message_by_session,
        finished_by_run=finished_by_run,
        reported=reported,
    )


def _manifest(peer: AgentSession, terminal: EventEnvelope, index: PeerCompletionIndex) -> dict[str, Any]:
    state = str(terminal.data["to"])
    run_id = terminal.run_id
    finished = index.finished_by_run.get((peer.id, run_id)) if run_id else None
    final = index.final_message_by_session.get(peer.id)
    if final is not None:
        summary = str(final.data["content"]).strip()
        summary_source = "agent.message_emitted"
    elif state == "cancelled":
        summary = "Peer was cancelled before returning a result."
        summary_source = "terminal_state"
    elif state == "failed":
        summary = "Peer failed without a final answer."
        summary_source = "terminal_state"
    else:
        summary = "Peer finished without a final answer."
        summary_source = "terminal_state"
    return {
        "kind": _REPORT_KIND,
        "session_id": peer.id,
        "role_id": peer.role_id,
        "requested_by_session_id": peer.requested_by_session_id,
        "state": state,
        "terminal_event_id": terminal.event_id,
        "run_id": run_id,
        "outcome": finished.data.get("outcome") if finished else state,
        "failure_kind": finished.data.get("failure_kind") if finished else None,
        "final_summary": summary,
        "final_summary_source": summary_source,
    }


def peer_completion_message(
    core, peer: AgentSession, *, index: PeerCompletionIndex | None = None
) -> tuple[str, str, dict[str, Any]] | None:
    """Build one pending report from durable events; never mutate or deliver."""
    recipient_id = peer.requested_by_session_id
    if not recipient_id or peer.parent_session_id is not None:
        return None
    recipient = core.agents.get(recipient_id)
    if recipient is None or recipient.project_id != peer.project_id:
        return None
    if index is None:
        index = build_peer_completion_index(core)
    terminal = index.terminal_by_session.get(peer.id)
    if terminal is None or (recipient_id, peer.id) in index.reported:
        return None
    manifest = _manifest(peer, terminal, index)
    content = (
        f"[Peer finished] role={peer.role_id} session_id={peer.id} "
        f"state={manifest['state']}\n"
        f"run_id={manifest['run_id'] or '(none)'} "
        f"failure_kind={manifest['failure_kind'] or '(none)'}\n"
        f"summary:\n{manifest['final_summary']}"
    )
    return recipient_id, content, manifest


async def deliver_peer_completion(core, peer: AgentSession, *, wake: bool = True) -> None:
    """Commit a peer's first completion report and then enqueue/wake its caller."""
    message = peer_completion_message(core, peer)
    if message is None:
        return
    recipient_id, content, manifest = message
    await core.dispatcher.commit_and_deliver(
        to_session_id=recipient_id,
        project_id=peer.project_id,
        content=content,
        sender=peer.role_id,
        manifest=manifest,
        wake=WakePolicy.PARK_TERMINAL if wake else WakePolicy.NEVER,
    )
