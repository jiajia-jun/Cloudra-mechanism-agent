"""Terminal-state watcher for benchmark agents (GH #30).

The dag_guided runner parks an agent in non-terminal states whose meaning the
old benchmark loop misread:

- ``wait_background``: the stop was a suspension because children / compute
  jobs are still running.  The runner calls ``finish_run(succeeded)`` — the
  agent sleeps in ``SUCCEEDED`` until a child completion wakes it into a new
  run.  ``SUCCEEDED`` therefore is NOT "the task is done": the watcher keeps
  waiting while background work is still pending (live siblings, reminders,
  non-terminal compute jobs) and only declares the task done when the sandbox
  can no longer change.
- ``wait_review``: the coordinator parks in ``WAITING_APPROVAL`` (reason
  ``wait_review``) awaiting the project's internal Supervisor exit decision.
  That is not a human-approval hang and must not hit the 300s "nobody to
  answer" cancel.  It is bounded by the overall run timeout, and additionally
  by a liveness rule: if the project has no live Supervisor left, nobody will
  ever decide, so the stuck grace applies.

Everything here is a projection of durable state (``core.agents``, the event
log, compute.db); the watcher keeps no state of its own except the volatile
stuck timer, which is meaningless across restarts by construction.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Awaitable, Callable, Literal, Optional

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
    """One poll of the watcher: keep waiting, declare done, or cancel stuck."""

    kind: Literal["continue", "done", "cancel"]
    reason: str = ""


def latest_state_reason(core, session_id: str) -> str:
    """最近一次 ``agent.state_changed`` 的 reason（挂起原因的唯一持久来源）。"""
    events = core.event_log.query_session(
        session_id, types={"agent.state_changed"}, limit=20
    )
    if not events:
        return ""
    return str((events[-1].data or {}).get("reason") or "")


def has_live_supervisor(core, project_id: str) -> bool:
    """项目内是否存在仍可能裁决的 Supervisor（非终态/非沉睡即活）。"""
    from cloudra.runtime_v2.supervision import find_project_supervisor

    supervisor = find_project_supervisor(core, project_id)
    if supervisor is None:
        return False
    return supervisor.state not in _SUPERVISOR_DEAD_STATES


def has_running_peers(core, agent) -> bool:
    """项目内是否还有未终态的其他 agent（纯 core.agents 投影读）。"""
    from cloudra.dag.stop_audit import has_running_siblings

    return has_running_siblings(
        core, project_id=agent.project_id, session_id=agent.id
    )


class RunWatcher:
    """Waits for one benchmark agent to genuinely finish its task.

    ``pending_background`` 是可注入的额外后台判定（compute.db 未竟作业 /
    reminders）：判定为真时 SUCCEEDED 仍视为未完成，继续等唤醒。
    """

    def __init__(
        self,
        *,
        run_timeout_s: float,
        stuck_grace_s: float,
        poll_interval_s: float,
        pending_background: Optional[Callable[[], Awaitable[bool]]] = None,
    ) -> None:
        self.run_timeout_s = run_timeout_s
        self.stuck_grace_s = stuck_grace_s
        self.poll_interval_s = poll_interval_s
        self.pending_background = pending_background

    async def _background_pending(self, core, agent) -> bool:
        if has_running_peers(core, agent):
            return True
        if self.pending_background is not None:
            return bool(await self.pending_background())
        return False

    async def decide(self, core, agent) -> WaitDecision:
        """纯投影判定一步：done / cancel（给出理由）/ continue。"""
        state = agent.state
        if state in _TERMINAL_STATES:
            return WaitDecision("done")
        if state is AgentState.SUCCEEDED:
            # wait_background 收尾 = 当前 run 休眠等唤醒，不是交付（GH #30/C1）。
            if await self._background_pending(core, agent):
                return WaitDecision("continue")
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
        stuck_grace_s 才取消）；整体由 run_timeout_s 无条件封顶。
        """
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self.run_timeout_s
        stuck_since: float | None = None
        while True:
            now = loop.time()
            if now > deadline:
                reason = f"benchmark run timeout ({self.run_timeout_s}s)"
                await cancel(reason)
                return reason
            decision = await self.decide(core, agent)
            if decision.kind == "done":
                return None
            if decision.kind == "cancel":
                if stuck_since is None:
                    stuck_since = now
                if now - stuck_since > self.stuck_grace_s:
                    await cancel(decision.reason)
                    return decision.reason
            else:
                stuck_since = None
            await asyncio.sleep(self.poll_interval_s)
