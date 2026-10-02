"""Terminal-state watcher for benchmark agents (GH #30).

The dag_guided runner parks an agent in non-terminal states whose meaning the
old benchmark loop misread:

- ``wait_background``: the stop was a suspension because children / compute
  jobs are still running.  The runner calls ``finish_run(succeeded)`` — the
  agent sleeps in ``SUCCEEDED`` until a completion notice wakes it into a new
  run.  ``SUCCEEDED`` therefore is NOT "the task is done": the watcher waits
  for the notice and for a later final run before scoring.
- ``wait_review``: the coordinator parks in ``WAITING_APPROVAL`` (reason
  ``wait_review``) awaiting the project's internal Supervisor exit decision.
  That is not a human-approval hang and must not hit the 300s "nobody to
  answer" cancel.  It follows a liveness rule: if the project has no live
  Supervisor left, nobody will ever decide, so the stuck grace applies.

Decisions read durable state (``core.agents``, the event log, compute.db) and
live runner tasks whose terminal completion reports may still be in flight.
The watcher remembers which parked runs it has resumed after their background
peers drained, preventing a missing notice from causing a resume loop. That
per-run memory is only needed for this benchmark process.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Awaitable, Callable, Literal, Optional

from cloudra.runtime_v2.dispatcher import latest_state_reason
from cloudra.runtime_v2.schemas import AgentState

logger = logging.getLogger(__name__)

WAIT_REVIEW_REASON = "wait_review"

# 终态集合：这些状态之后不会再有任何运行（失败/取消不复活）。
_TERMINAL_STATES = frozenset({AgentState.FAILED, AgentState.CANCELLED})

# 督导存活判定：SUCCEEDED 也算死——退出裁决请求的通知已在挂起前发出且只发
# 一次，督导沉睡期间不会有人再唤醒它去裁决本次请求（park 后的短暂窗口由
# stuck_grace 吸收）。
_SUPERVISOR_DEAD_STATES = frozenset(
    {AgentState.SUCCEEDED, AgentState.FAILED, AgentState.CANCELLED}
)

# wait_review 之外的无应答挂起：benchmark 无人值守，没有任何人会响应。
_UNANSWERED_STATES = frozenset({AgentState.WAITING_INPUT, AgentState.WAITING_APPROVAL})


@dataclass(frozen=True)
class WaitDecision:
    """One poll of the watcher: wait, resume a parked run, finish, or cancel."""

    kind: Literal["continue", "resume", "done", "cancel"]
    reason: str = ""
    drained_run_id: str | None = None


def has_live_supervisor(core, project_id: str) -> bool:
    """项目内是否存在仍可能裁决的 Supervisor（非终态/非沉睡即活）。"""
    from cloudra.runtime_v2.supervision import find_project_supervisor

    supervisor = find_project_supervisor(core, project_id)
    if supervisor is None:
        return False
    return supervisor.state not in _SUPERVISOR_DEAD_STATES


def has_running_peers(core, agent, *, final_cache: dict | None = None) -> bool:
    """Project peers include children parked after a background-wait run."""
    from cloudra.runtime_v2.subagent_bridge import build_child_completion_index

    parked_children = []
    task_for = getattr(getattr(core, "runner", None), "task_for", None)
    for peer in core.agents.values():
        if peer.id == agent.id or peer.project_id != agent.project_id:
            continue
        # A terminal projection can precede the completion report and its wake.
        # Wait for the real peer task to finish that delivery before scoring.
        task = task_for(peer.id) if task_for is not None else None
        if task is not None and not task.done():
            return True
        if peer.state not in {AgentState.SUCCEEDED, AgentState.FAILED, AgentState.CANCELLED}:
            return True
        if peer.state is AgentState.SUCCEEDED and peer.parent_session_id:
            key = (peer.state, peer.updated_at)
            cached = final_cache.get(peer.id) if final_cache is not None else None
            if cached is not None and cached[0] == key:
                if not cached[1]:
                    return True
            else:
                parked_children.append(peer)
    if parked_children:
        index = build_child_completion_index(core)
        for peer in parked_children:
            final = peer.id in index.terminal_by_session
            if final_cache is not None:
                final_cache[peer.id] = ((peer.state, peer.updated_at), final)
            if not final:
                return True
    return False


class RunWatcher:
    """Waits for one benchmark agent to genuinely finish its task.

    ``pending_background`` 是可注入的额外后台判定（compute.db 未竟作业 /
    reminders）：判定为真时 SUCCEEDED 仍视为未完成，继续等唤醒。
    """

    def __init__(
        self,
        *,
        stuck_grace_s: float,
        poll_interval_s: float,
        pending_background: Optional[Callable[[], Awaitable[bool]]] = None,
        resume_background: Optional[Callable[[], Awaitable[None]]] = None,
        stop_event: asyncio.Event | None = None,
    ) -> None:
        self.stuck_grace_s = stuck_grace_s
        self.poll_interval_s = poll_interval_s
        self.pending_background = pending_background
        self.resume_background = resume_background
        self.stop_event = stop_event
        self._gate_cache: tuple[tuple[str, object], str | None] | None = None
        self._peer_final_cache: dict[str, tuple[object, bool]] = {}
        self._drained_resumes: set[tuple[str, str]] = set()

    def _parked_for_background(self, core, agent) -> str | None:
        """Return the current parked run id, if its gate is wait_background."""
        key = (agent.id, agent.updated_at)
        if self._gate_cache is not None and self._gate_cache[0] == key:
            return self._gate_cache[1]
        events = core.event_log.query_session(
            agent.id, types={"agent.completion_gate", "run.finished"}, limit=20,
        )
        finished = next((e for e in reversed(events) if e.type == "run.finished"), None)
        gate = next((
            e for e in reversed(events)
            if e.type == "agent.completion_gate"
            and finished is not None and e.run_id == finished.run_id
        ), None)
        parked = bool(
            finished is not None and finished.data.get("outcome") == "succeeded"
            and gate is not None and gate.data.get("action") == "wait_background"
        )
        parked_run_id = finished.run_id if parked else None
        self._gate_cache = (key, parked_run_id)
        return parked_run_id

    async def _background_pending(self, core, agent) -> bool:
        if self.pending_background is not None:
            if await self.pending_background():
                return True
        return has_running_peers(core, agent, final_cache=self._peer_final_cache)

    async def decide(self, core, agent) -> WaitDecision:
        """纯投影判定一步：done / cancel（给出理由）/ continue。"""
        snapshot = (
            agent.state, agent.updated_at,
            agent.current_run.run_id if agent.current_run is not None else None,
        )
        state = snapshot[0]
        if state in _TERMINAL_STATES:
            return WaitDecision("done")
        if state is AgentState.SUCCEEDED:
            # wait_background 收尾 = 当前 run 休眠等唤醒，不是交付（GH #30/C1）。
            if await self._background_pending(core, agent):
                return WaitDecision("continue")
            # DB probes yield: a notice can wake this session, or a new run can
            # even finish, before they return. Re-evaluate on the next poll.
            current = (
                agent.state, agent.updated_at,
                agent.current_run.run_id if agent.current_run is not None else None,
            )
            if current != snapshot:
                return WaitDecision("continue", "agent changed during background probe")
            parked_run_id = self._parked_for_background(core, agent)
            if parked_run_id:
                inbox = core.mailbox.inbox(agent.id)
                if inbox is not None and not inbox.empty():
                    return WaitDecision("resume", "background notice awaits this agent")
                if (agent.id, parked_run_id) not in self._drained_resumes:
                    # A peer may finish after its first final report was sent.
                    # Its later terminal transition clears the background
                    # work without producing another inbox message. Recheck
                    # the coordinator gate once when that happens.
                    return WaitDecision(
                        "resume", "background work drained without a new notice",
                        drained_run_id=parked_run_id,
                    )
                return WaitDecision("continue", "waiting for background notice")
            return WaitDecision("done")
        if state in _UNANSWERED_STATES:
            reason = latest_state_reason(core, agent.id)
            if state is AgentState.WAITING_APPROVAL and reason == WAIT_REVIEW_REASON:
                # 等内部 Supervisor 裁决（GH #30/NI1）：不是人工卡死；只有
                # 督导已死（无人会裁决）才落入卡死取消。
                if has_live_supervisor(core, agent.project_id):
                    return WaitDecision("continue")
                return WaitDecision(
                    "cancel",
                    f"waiting for Supervisor exit review but no live supervisor "
                    f"remains in project {agent.project_id}",
                )
            return WaitDecision(
                "cancel",
                f"agent stuck in {state.value} with nobody to answer",
            )
        return WaitDecision("continue")

    async def wait(
        self,
        core,
        agent,
        cancel: Callable[[str], Awaitable[None]],
    ) -> str | None:
        """轮询直到 done，返回 None；取消时调用 ``cancel(reason)`` 并返回理由。

        cancel 类判定按同一 stuck_grace 宽限计时（连续处于该挂起超过
        stuck_grace_s 才取消）；运行和内部等待不设整体时长上限。
        """
        loop = asyncio.get_running_loop()
        stuck_since: float | None = None
        while True:
            if self.stop_event is not None and self.stop_event.is_set():
                return "benchmark batch stopped"
            now = loop.time()
            decision = await self.decide(core, agent)
            if decision.kind == "done":
                return None
            if decision.kind == "resume":
                if decision.drained_run_id is not None:
                    # The live runner owns the durable, per-run quiescence
                    # notice. Let it recheck the project and deliver that
                    # message before scheduling a new run; a bare wake would
                    # leave the run blocked on an empty inbox.
                    reconcile = getattr(
                        getattr(core, "runner", None), "maybe_wake_parked_delivery", None
                    )
                    if reconcile is not None:
                        await reconcile(agent.project_id)
                        self._drained_resumes.add((agent.id, decision.drained_run_id))
                        stuck_since = None
                        await self._poll_delay()
                        continue
                    self._drained_resumes.add((agent.id, decision.drained_run_id))
                if self.resume_background is not None:
                    await self.resume_background()
                stuck_since = None
                await self._poll_delay()
                continue
            if decision.kind == "cancel":
                if stuck_since is None:
                    stuck_since = now
                if now - stuck_since > self.stuck_grace_s:
                    await cancel(decision.reason)
                    return decision.reason
            else:
                stuck_since = None
            await self._poll_delay()

    async def _poll_delay(self) -> None:
        if self.stop_event is None:
            await asyncio.sleep(self.poll_interval_s)
            return
        try:
            await asyncio.wait_for(self.stop_event.wait(), timeout=self.poll_interval_s)
        except asyncio.TimeoutError:
            pass
