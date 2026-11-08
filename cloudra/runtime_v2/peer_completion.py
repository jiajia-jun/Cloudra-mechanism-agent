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

import asyncio
from dataclasses import dataclass, field
from typing import Any

from cloudra.runtime_v2.dispatcher import WakePolicy
from cloudra.runtime_v2.schemas import AgentSession, EventEnvelope

_TERMINAL_STATES = frozenset({"succeeded", "failed", "cancelled"})
_REPORT_KIND = "peer_call_completion"


@dataclass(slots=True)
class PeerCompletionIndex:
    """First-result obligation and current run facts, bounded by peer count."""

    terminal_by_session: dict[str, EventEnvelope] = field(default_factory=dict)
    final_message_by_session: dict[str, EventEnvelope] = field(default_factory=dict)
    finished_by_run: dict[tuple[str, str], EventEnvelope] = field(default_factory=dict)
    reported: set[tuple[str, str]] = field(default_factory=set)
    latest_gate_by_session: dict[str, tuple[str | None, str]] = field(default_factory=dict)
    latest_message_by_session: dict[str, EventEnvelope] = field(default_factory=dict)
    watermarks: dict[str, int] = field(default_factory=dict)

    def apply(self, event: EventEnvelope, core) -> None:
        if event.seq <= self.watermarks.get(event.project_id, 0):
            return
        self.watermarks[event.project_id] = event.seq
        session_id = event.session_id
        if event.type == "agent.message_injected" and session_id:
            manifest = event.data.get("manifest")
            if isinstance(manifest, dict) and manifest.get("kind") == _REPORT_KIND:
                peer_id = manifest.get("session_id")
                peer = core.agents.get(peer_id) if isinstance(peer_id, str) else None
                if peer is not None and peer.requested_by_session_id and peer.parent_session_id is None:
                    self.reported.add((session_id, peer_id))
        peer = core.agents.get(session_id)
        if peer is None or not peer.requested_by_session_id or peer.parent_session_id is not None:
            return
        terminal = self.terminal_by_session.get(peer.id)
        if event.type == "run.finished":
            if terminal is not None and event.run_id == terminal.run_id:
                self.finished_by_run[(peer.id, event.run_id or "")] = event
        elif terminal is None:
            if event.type == "run.started":
                self.latest_gate_by_session.pop(peer.id, None)
                self.latest_message_by_session.pop(peer.id, None)
            elif event.type == "agent.completion_gate" and event.run_id:
                self.latest_gate_by_session[peer.id] = (event.run_id, str(event.data.get("action") or ""))
            elif (
                event.type == "agent.message_emitted" and event.run_id and str(event.data.get("content") or "").strip()
            ):
                self.latest_message_by_session[peer.id] = event
            elif event.type == "agent.state_changed":
                state = event.data.get("to")
                if state not in _TERMINAL_STATES:
                    return
                if state == "succeeded" and self.latest_gate_by_session.get(peer.id) == (
                    event.run_id,
                    "wait_background",
                ):
                    return
                self.terminal_by_session[peer.id] = event
                final = self.latest_message_by_session.pop(peer.id, None)
                if final is not None and final.run_id == event.run_id:
                    self.final_message_by_session[peer.id] = final
                self.latest_gate_by_session.pop(peer.id, None)

    def snapshot(self) -> dict[str, Any]:
        return {
            "terminal_by_session": {
                sid: event.model_dump(mode="json") for sid, event in self.terminal_by_session.items()
            },
            "final_message_by_session": {
                sid: event.model_dump(mode="json") for sid, event in self.final_message_by_session.items()
            },
            "finished_by_run": [event.model_dump(mode="json") for event in self.finished_by_run.values()],
            "reported": [list(pair) for pair in sorted(self.reported)],
            "latest_gate_by_session": {sid: list(gate) for sid, gate in self.latest_gate_by_session.items()},
            "latest_message_by_session": {
                sid: event.model_dump(mode="json") for sid, event in self.latest_message_by_session.items()
            },
            "watermarks": dict(self.watermarks),
        }

    def restore(self, payload: dict[str, Any]) -> None:
        for name in ("terminal_by_session", "final_message_by_session", "latest_message_by_session"):
            setattr(
                self, name, {sid: EventEnvelope.model_validate(event) for sid, event in payload.get(name, {}).items()}
            )
        finished = [EventEnvelope.model_validate(event) for event in payload.get("finished_by_run", [])]
        self.finished_by_run = {(event.session_id, event.run_id or ""): event for event in finished}
        self.reported = {tuple(pair) for pair in payload.get("reported", [])}
        self.latest_gate_by_session = {
            sid: tuple(gate) for sid, gate in payload.get("latest_gate_by_session", {}).items()
        }
        self.watermarks = dict(payload.get("watermarks", {}))

    def prune(self, session_ids: set[str]) -> None:
        for mapping in (
            self.terminal_by_session,
            self.final_message_by_session,
            self.latest_gate_by_session,
            self.latest_message_by_session,
        ):
            for session_id in mapping.keys() - session_ids:
                mapping.pop(session_id)
        self.finished_by_run = {key: event for key, event in self.finished_by_run.items() if key[0] in session_ids}
        self.reported = {pair for pair in self.reported if pair[0] in session_ids and pair[1] in session_ids}


def build_peer_completion_index(core) -> PeerCompletionIndex:
    """Reuse the index fed by the common persist/replay path."""
    return core.peer_completions


def _manifest(core, peer: AgentSession, terminal: EventEnvelope, index: PeerCompletionIndex) -> dict[str, Any]:
    state = str(terminal.data["to"])
    run_id = terminal.run_id
    finished = index.finished_by_run.get((peer.id, run_id)) if run_id else None
    final = index.final_message_by_session.get(peer.id)
    gates = core.event_log.query_session(
        peer.id, run_id=run_id, before_session_seq=terminal.session_seq,
        types={"agent.completion_gate"}, limit=1,
    ) if state == "succeeded" and run_id else []
    if gates and "final_answer" in gates[-1].data:
        summary = gates[-1].data["final_answer"]
        summary_source = "agent.message_emitted"
    elif final is not None:
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
    manifest = _manifest(core, peer, terminal, index)
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
    message = await asyncio.to_thread(peer_completion_message, core, peer)
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
