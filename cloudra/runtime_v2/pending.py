"""Pending approvals & interactions: v2-native user decisions.

The legacy runtime stores approval rows and ask_user interactions in the
conversation SQLite and waits on the legacy event bus.  Here the pending
state is kernel-native instead:

- a request appends ``approval.requested`` / ``interaction.requested`` and
  parks an ``asyncio.Future`` keyed by the request id;
- the user decision arrives as the ``approval.decide`` /
  ``interaction.respond`` commands, which append the decided/responded event
  and resolve the future;
- listing is a pure projection over the event log, so a restart still shows
  (stale) pending entries; deciding a dead entry is accepted and simply has
  no waiter left to wake;
- on restore (``persistence.restore_core``) every orphaned entry — a
  ``*.requested`` with no terminal event, i.e. a waiter that died with the
  previous process — is closed explicitly with ``approval.expired`` /
  ``interaction.expired`` (``reason="restart"``) via ``expire_orphans``, so
  the event stream shows a definite terminal state instead of the request
  silently vanishing.  Expired entries leave the pending projection, and the
  expiry events are themselves terminal, so re-restores are idempotent.

The ``_waiters`` futures are deliberately volatile (shell-private): a parked
waiter can only be woken inside this process, so the map is never rebuilt
from events — restore closes the orphan's projection entry instead.

Events are appended mid-turn (the run is blocked inside the tool call), so
the broker publishes them to the hub itself — the runner's per-turn flush
would only fire after the turn ends, which never happens while waiting.

While waiting, the agent flips to ``waiting_approval`` / ``waiting_input``
for UI visibility and flips back on resolution; a concurrent user message
may already have resumed the agent, so the flip-back is conditional.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

from cloudra.runtime_v2.apply import apply_event
from cloudra.runtime_v2.schemas import AgentSession, AgentState, CommandRejected, EventEnvelope, new_id

if TYPE_CHECKING:
    from cloudra.runtime_v2.core import RuntimeCore

logger = logging.getLogger(__name__)

_APPROVAL_TYPES = {"approval.requested", "approval.decided", "approval.expired"}
_INTERACTION_TYPES = {"interaction.requested", "interaction.responded", "interaction.expired"}


class PendingBroker:
    def __init__(self, core: "RuntimeCore") -> None:
        self.core = core
        self._waiters: dict[str, asyncio.Future] = {}

    # ------------------------------------------------------------------ events

    async def _emit(
        self, type: str, *, project_id: str, session_id: str, data: dict[str, Any], publish: bool
    ):
        envelope = self.core.event_log.append(
            type,
            stream="agent",
            project_id=project_id,
            session_id=session_id,
            run_id=self._run_id(session_id),
            data=data,
        )
        if publish:
            # Mid-turn requests must reach SSE/persistence now; decisions flow
            # through the command bus, which publishes new events itself.
            await self.core.event_writer.flush()
        return envelope

    def _run_id(self, session_id: str) -> str | None:
        agent = self.core.agents.get(session_id)
        if agent is not None and agent.current_run is not None:
            return agent.current_run.run_id
        return None

    async def _flip(self, agent: AgentSession, to: AgentState, reason: str) -> None:
        self.core.agent_host.transition(agent, to, reason=reason, run_id=self._run_id(agent.id))
        await self.core.event_writer.flush()

    async def _park(self, agent: AgentSession, state: AgentState, reason: str) -> None:
        if agent.state is AgentState.RUNNING:
            await self._flip(agent, state, reason)

    async def _wake(self, agent: AgentSession, state: AgentState) -> None:
        # A user message may already have resumed the agent mid-wait; only
        # flip back when we are still the ones holding it parked.
        if agent.state is state:
            await self._flip(agent, AgentState.RUNNING, "resolved")

    # ------------------------------------------------------------------ approvals

    async def request_approval(
        self,
        agent: AgentSession,
        *,
        tool_name: str,
        details: str,
        normalized_arguments: dict[str, Any],
        risk_summary: str,
        candidate_diff: str,
    ) -> tuple[bool, str]:
        """Hook for Tool.request_approval; returns (approved, denial_reason)."""
        from cloudra.runtime_v2.invocation_context import current_invocation_scope

        approval_id = new_id("apv")
        loop = asyncio.get_running_loop()
        future: asyncio.Future = loop.create_future()
        self._waiters[approval_id] = future
        scope = current_invocation_scope()
        await self._emit(
            "approval.requested",
            project_id=agent.project_id,
            session_id=agent.id,
            data={
                "approval_id": approval_id,
                "agent_name": agent.role_id,
                "tool_name": tool_name,
                "details": details,
                "risk_summary": risk_summary,
                "candidate_diff": candidate_diff,
                "normalized_arguments": normalized_arguments,
                # Host-stamped invocation correlation (None outside a tool).
                "tool_call_id": scope.tool_call_id if scope else None,
                "execution_id": scope.execution_id if scope else None,
            },
            publish=True,
        )
        await self._park(agent, AgentState.WAITING_APPROVAL, "approval")
        try:
            decision, reason = await future
            return decision == "approved", reason
        finally:
            self._waiters.pop(approval_id, None)
            await self._wake(agent, AgentState.WAITING_APPROVAL)
            if not future.done() or future.cancelled():
                # The run was cancelled while parked: expire the request so it
                # leaves the pending projection.
                await self._emit(
                    "approval.decided",
                    project_id=agent.project_id,
                    session_id=agent.id,
                    data={"approval_id": approval_id, "decision": "expired", "reason": "run cancelled"},
                    publish=True,
                )

    async def decide_approval(self, project_id: str, approval_id: str, decision: str, reason: str) -> None:
        pending = {p["id"] for p in self.list_pending_approvals(project_id)}
        if approval_id not in pending:
            raise CommandRejected("not_found", f"no pending approval {approval_id!r}")
        session_id = self._request_session(project_id, approval_id, "approval.requested", "approval_id")
        await self._emit(
            "approval.decided",
            project_id=project_id,
            session_id=session_id,
            data={"approval_id": approval_id, "decision": decision, "reason": reason},
            publish=False,  # the command bus flushes new events after the handler
        )
        # The decision must be durable before any parked waiter resolves.
        await self.core.event_writer.flush()
        future = self._waiters.get(approval_id)
        if future is not None and not future.done():
            future.set_result((decision, reason))

    def list_pending_approvals(self, project_id: str) -> list[dict[str, Any]]:
        requested: dict[str, dict[str, Any]] = {}
        decided: set[str] = set()
        for env in self.core.event_log.query_project(project_id, types=_APPROVAL_TYPES, limit=10_000):
            if env.type == "approval.requested":
                aid = str(env.data.get("approval_id") or "")
                requested[aid] = {
                    "id": aid,
                    "session_id": env.session_id,
                    "agent_name": env.data.get("agent_name", ""),
                    "tool_name": env.data.get("tool_name", ""),
                    "details": env.data.get("details", ""),
                    "risk_summary": env.data.get("risk_summary", ""),
                    "candidate_diff": env.data.get("candidate_diff", ""),
                    "tool_call_id": env.data.get("tool_call_id"),
                    "execution_id": env.data.get("execution_id"),
                    "state": "waiting_for_approval",
                    "created_at": env.created_at.isoformat(),
                }
            else:
                decided.add(str(env.data.get("approval_id") or ""))
        return [row for aid, row in requested.items() if aid not in decided]

    # ------------------------------------------------------------------ interactions

    async def request_interaction(self, agent: AgentSession, prompt: str) -> str:
        """Hook for ask_user's input handler; returns the raw user answer."""
        from cloudra.runtime_v2.invocation_context import current_invocation_scope

        interaction_id = new_id("ixn")
        loop = asyncio.get_running_loop()
        future: asyncio.Future = loop.create_future()
        self._waiters[interaction_id] = future
        scope = current_invocation_scope()
        await self._emit(
            "interaction.requested",
            project_id=agent.project_id,
            session_id=agent.id,
            data={
                "interaction_id": interaction_id,
                "agent_id": agent.role_id,
                "prompt": prompt,
                "tool_call_id": scope.tool_call_id if scope else None,
                "execution_id": scope.execution_id if scope else None,
            },
            publish=True,
        )
        await self._park(agent, AgentState.WAITING_INPUT, "ask_user")
        try:
            return await future
        finally:
            self._waiters.pop(interaction_id, None)
            await self._wake(agent, AgentState.WAITING_INPUT)
            if not future.done() or future.cancelled():
                await self._emit(
                    "interaction.responded",
                    project_id=agent.project_id,
                    session_id=agent.id,
                    data={
                        "interaction_id": interaction_id,
                        "response": "",
                        "expired": True,
                    },
                    publish=True,
                )

    async def respond_interaction(self, project_id: str, interaction_id: str, response: str) -> dict[str, Any]:
        pending = {p["interaction_id"] for p in self.list_pending_interactions(project_id)}
        if interaction_id not in pending:
            raise CommandRejected("not_found", f"no pending interaction {interaction_id!r}")
        session_id = self._request_session(project_id, interaction_id, "interaction.requested", "interaction_id")
        envelope = await self._emit(
            "interaction.responded",
            project_id=project_id,
            session_id=session_id,
            data={"interaction_id": interaction_id, "response": response},
            publish=False,  # the command bus flushes new events after the handler
        )
        # The response must be durable before any parked waiter resolves.
        await self.core.event_writer.flush()
        future = self._waiters.get(interaction_id)
        if future is not None and not future.done():
            future.set_result(response)
        return {
            "interaction_id": interaction_id,
            "session_id": session_id,
            "response": response,
            "state": "responded",
            "responded_at": envelope.created_at.isoformat(),
        }

    def list_pending_interactions(self, project_id: str) -> list[dict[str, Any]]:
        requested: dict[str, dict[str, Any]] = {}
        responded: set[str] = set()
        for env in self.core.event_log.query_project(project_id, types=_INTERACTION_TYPES, limit=10_000):
            if env.type == "interaction.requested":
                iid = str(env.data.get("interaction_id") or "")
                requested[iid] = {
                    "interaction_id": iid,
                    "session_id": env.session_id,
                    "agent_id": env.data.get("agent_id", ""),
                    "prompt": env.data.get("prompt", ""),
                    "tool_call_id": env.data.get("tool_call_id"),
                    "execution_id": env.data.get("execution_id"),
                    "state": "pending",
                    "created_at": env.created_at.isoformat(),
                }
            else:
                responded.add(str(env.data.get("interaction_id") or ""))
        return [row for iid, row in requested.items() if iid not in responded]

    # ------------------------------------------------------------------ restore

    def expire_orphans(self) -> list[EventEnvelope]:
        """Close every orphaned pending entry with an explicit terminal event.

        An orphan is a ``*.requested`` with no matching terminal event — the
        parked future died with the previous process, so no decide/respond
        will ever arrive.  Each orphan gets ``approval.expired`` /
        ``interaction.expired`` with ``reason="restart"``; the event goes
        through append + ``apply_event`` (a no-op notification for core state)
        like any other, and the caller (``persistence.restore_core``) persists
        the returned envelopes.  The expiry events are themselves terminal, so
        a second restore finds no orphans and appends nothing (idempotent).
        """
        orphans: list[tuple[str, str, dict[str, Any]]] = []
        for project_id in self.core.projects:
            for row in self.list_pending_approvals(project_id):
                orphans.append(("approval", project_id, row))
            for row in self.list_pending_interactions(project_id):
                orphans.append(("interaction", project_id, row))
        emitted: list[EventEnvelope] = []
        for kind, project_id, row in orphans:
            if kind == "approval":
                data = {
                    "approval_id": row["id"],
                    "agent_id": row["agent_name"],
                    "reason": "restart",
                }
            else:
                data = {
                    "interaction_id": row["interaction_id"],
                    "agent_id": row["agent_id"],
                    "reason": "restart",
                }
            envelope = self.core.event_log.append(
                f"{kind}.expired",
                stream="agent",
                project_id=project_id,
                session_id=row["session_id"],
                data=data,
            )
            apply_event(self.core, envelope)
            emitted.append(envelope)
        return emitted

    # ------------------------------------------------------------------ helpers

    def _request_session(self, project_id: str, request_id: str, type_: str, key: str) -> str:
        for env in self.core.event_log.query_project(project_id, types={type_}, limit=10_000):
            if str(env.data.get(key) or "") == request_id:
                return env.session_id or ""
        return ""
