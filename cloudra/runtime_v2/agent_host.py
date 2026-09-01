"""Agent lifecycle: spawn / cancel / restart / state transitions.

AgentSession is a persistent identity.  ``restart`` keeps the id and opens a
new run.  Execution handles (LLM loops, subprocesses) are attached later by
the turn pipeline; the state machine itself is handle-agnostic.

状态机知识只住在本模块，分两层（FP 内核化 3b）：

- **纯规划器**（模块级 ``plan_*`` 函数）：守卫校验（非法迁移抛
  ``CommandRejected``）+ 产出 ``EventDraft`` 列表。零 IO、零 mutate——
  命令侧（``commands.py`` 的 decide）据此组装 Decision，由 CommandBus
  统一落日志/投影。
- **命令式方法**（``AgentHost``）：``plan + event_log.append + apply_event``
  的薄执行壳，供非命令路径（runner / pending 翻状态 / restore 僵尸收尾 /
  dag_stage 督导壳 / hub_bridge 点对点消息）使用。

两条路径共享同一份守卫表与事件形状，杜绝双实现漂移。状态的唯一事实来源是
事件日志，应用器只有 ``cloudra.runtime_v2.apply.apply_event`` 一个。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from cloudra.runtime_v2.apply import apply_event
from cloudra.runtime_v2.effects import EventDraft
from cloudra.runtime_v2.events import EventLog
from cloudra.runtime_v2.schemas import (
    AgentCapabilities,
    AgentSession,
    AgentState,
    CommandRejected,
    Project,
    RoleProfile,
    RuntimeSettings,
    RuntimeSettingsPatch,
    new_id,
)

if TYPE_CHECKING:
    from cloudra.runtime_v2.core import RuntimeCore

# Allowed (from, to) transitions.  Messages may wake SUCCEEDED into RUNNING.
_TRANSITIONS: dict[AgentState, frozenset[AgentState]] = {
    AgentState.QUEUED: frozenset({AgentState.RUNNING, AgentState.CANCELLED}),
    AgentState.RUNNING: frozenset(
        {
            AgentState.WAITING_INPUT,
            AgentState.WAITING_APPROVAL,
            AgentState.SUCCEEDED,
            AgentState.FAILED,
            AgentState.CANCELLED,
        }
    ),
    AgentState.WAITING_INPUT: frozenset({AgentState.RUNNING, AgentState.CANCELLED, AgentState.FAILED}),
    AgentState.WAITING_APPROVAL: frozenset({AgentState.RUNNING, AgentState.CANCELLED, AgentState.FAILED}),
    AgentState.SUCCEEDED: frozenset({AgentState.RUNNING, AgentState.QUEUED}),
    AgentState.FAILED: frozenset({AgentState.QUEUED}),
    AgentState.CANCELLED: frozenset({AgentState.QUEUED}),
}

_CONTEXT_RESET_NOTE = (
    "dialogue history was reset; continuity via "
    "context tree (handover + run summaries), "
    "goal/memory/workspace files"
)


def _settings_summary(settings: RuntimeSettings) -> dict[str, Any]:
    return {
        "model": settings.model,
        "yolo": settings.yolo,
        "orchestration_mode": settings.orchestration_mode.value,
        "temperature": settings.temperature,
    }


# --------------------------------------------------------------------- planners


def _transition_draft(
    agent: AgentSession,
    to: AgentState,
    *,
    reason: str,
    run_id: str | None,
    from_state: AgentState,
) -> EventDraft:
    allowed = _TRANSITIONS.get(from_state, frozenset())
    if to not in allowed:
        raise CommandRejected(
            "state_conflict",
            f"agent {agent.id} cannot move {from_state.value} -> {to.value}",
        )
    return EventDraft(
        "agent.state_changed",
        stream="agent",
        project_id=agent.project_id,
        session_id=agent.id,
        run_id=run_id,
        data={"from": from_state.value, "to": to.value, "reason": reason},
    )


def plan_transition(
    agent: AgentSession, to: AgentState, *, reason: str, run_id: str | None = None
) -> EventDraft:
    """Guard + draft one state transition against the agent's live state."""
    return _transition_draft(agent, to, reason=reason, run_id=run_id, from_state=agent.state)


def _start_run_drafts(agent: AgentSession, from_state: AgentState, run_id: str) -> list[EventDraft]:
    return [
        _transition_draft(agent, AgentState.RUNNING, reason="run_started", run_id=run_id, from_state=from_state),
        EventDraft(
            "run.started",
            stream="agent",
            project_id=agent.project_id,
            session_id=agent.id,
            run_id=run_id,
            data={"settings_summary": _settings_summary(agent.settings)},
        ),
    ]


def plan_start_run(agent: AgentSession) -> tuple[str, list[EventDraft]]:
    """Guard + drafts for opening a new run on a queued/succeeded agent."""
    if agent.state not in {AgentState.QUEUED, AgentState.SUCCEEDED}:
        raise CommandRejected(
            "state_conflict",
            f"cannot start a run while agent is {agent.state.value}",
        )
    run_id = new_id("run")
    return run_id, _start_run_drafts(agent, agent.state, run_id)


def plan_restart(agent: AgentSession) -> tuple[str, list[EventDraft]]:
    """Guard + drafts for resetting a terminal agent back to queued.

    Returns the restart's reference run_id (carried by restarted/context_reset
    and the optional restart message); the actual run opened later by
    ``plan_start_run`` gets its own id.
    """
    if agent.state not in {AgentState.FAILED, AgentState.CANCELLED, AgentState.SUCCEEDED}:
        raise CommandRejected(
            "state_conflict",
            "restart requires a terminal state; cancel a running agent first",
        )
    draft = _transition_draft(agent, AgentState.QUEUED, reason="restart", run_id=None, from_state=agent.state)
    return new_id("run"), [draft]


def plan_resume(agent: AgentSession) -> tuple[str, list[EventDraft]]:
    """Guard + drafts for resuming the current run after an external wakeup."""
    if agent.state not in {AgentState.WAITING_INPUT, AgentState.WAITING_APPROVAL}:
        raise CommandRejected(
            "state_conflict",
            f"agent {agent.id} is {agent.state.value}, not waiting",
        )
    if agent.current_run is None:
        raise CommandRejected("state_conflict", "waiting agent has no active run")
    run_id = agent.current_run.run_id
    return run_id, [
        _transition_draft(agent, AgentState.RUNNING, reason="resumed", run_id=run_id, from_state=agent.state)
    ]


def plan_cancel(agent: AgentSession) -> list[EventDraft]:
    """Guard + drafts for cancelling; empty plan when already cancelled."""
    if agent.state is AgentState.CANCELLED:
        return []
    if agent.state in {AgentState.SUCCEEDED, AgentState.FAILED}:
        raise CommandRejected(
            "state_conflict",
            f"agent {agent.id} is already terminal ({agent.state.value})",
        )
    run_id = agent.current_run.run_id if agent.current_run else None
    # current_run 的清空由随后的 agent.cancelled 事件落地（apply_event），
    # 草稿只承载 state_changed。
    return [_transition_draft(agent, AgentState.CANCELLED, reason="cancel", run_id=run_id, from_state=agent.state)]


def plan_wake(agent: AgentSession) -> tuple[list[EventDraft], bool]:
    """Pure plan of ``wake``: drafts + whether the runner should be scheduled.

    A RUNNING agent is left alone — its next turn already drains the inbox.
    Terminal agents (failed/cancelled) are reopened into a fresh run,
    succeeded/queued agents start a new run, and waiting agents resume the
    current one.

    Reopening a terminal agent resets the run-local dialogue history, so an
    ``agent.context_reset`` event marks the boundary explicitly: continuity
    now comes from the goal pin, memory, DAG and workspace files.

    注意草稿是针对 agent 当前快照一次算全的（restart 后再 start_run 的中间
    态由本函数内部推导），调用方落日志前不得改动 agent。
    """
    state = agent.state
    if state is AgentState.RUNNING:
        return [], False
    previous = state
    drafts: list[EventDraft] = []
    if state in {AgentState.FAILED, AgentState.CANCELLED}:
        drafts.append(
            _transition_draft(agent, AgentState.QUEUED, reason="restart", run_id=None, from_state=state)
        )
        state = AgentState.QUEUED
    if state in {AgentState.QUEUED, AgentState.SUCCEEDED}:
        run_id = new_id("run")
        drafts.extend(_start_run_drafts(agent, state, run_id))
        if previous in {
            AgentState.FAILED,
            AgentState.CANCELLED,
            AgentState.SUCCEEDED,
        }:
            drafts.append(
                EventDraft(
                    "agent.context_reset",
                    stream="agent",
                    project_id=agent.project_id,
                    session_id=agent.id,
                    run_id=run_id,
                    data={
                        "reason": "auto_reopen",
                        "previous_outcome": previous.value,
                        "note": _CONTEXT_RESET_NOTE,
                    },
                )
            )
        return drafts, True
    # WAITING_INPUT / WAITING_APPROVAL: resume the parked run.
    if agent.current_run is None:
        raise CommandRejected("state_conflict", "waiting agent has no active run")
    drafts.append(
        _transition_draft(
            agent,
            AgentState.RUNNING,
            reason="resumed",
            run_id=agent.current_run.run_id,
            from_state=state,
        )
    )
    return drafts, True


class AgentHost:
    def __init__(self, core: RuntimeCore) -> None:
        self.core = core
        self.event_log: EventLog = core.event_log

    def effective_settings(
        self,
        project: Project,
        role: RoleProfile,
        override: RuntimeSettingsPatch | None,
    ) -> RuntimeSettings:
        base = RuntimeSettings()
        base = base.apply(project.settings.defaults)
        base = base.apply(role.default_settings)
        if override is not None:
            base = base.apply(override)
        return base

    def build(
        self,
        *,
        project: Project,
        role: RoleProfile,
        parent_session_id: str | None,
        display_name: str | None,
        settings: RuntimeSettings,
    ) -> AgentSession:
        agent = AgentSession(
            id=new_id("as"),
            project_id=project.id,
            role_id=role.role_id,
            display_name=display_name or role.display_name,
            parent_session_id=parent_session_id,
            settings=settings,
            capabilities=AgentCapabilities(
                permissions=role.permissions,
                can_spawn=role.can_spawn,
                spawn_roles=list(role.spawn_roles) if role.spawn_roles is not None else None,
                tools=list(role.tool_policy.allow),
            ),
        )
        return agent

    # ------------------------------------------------------- imperative shells

    def _execute_drafts(self, drafts: list[EventDraft] | tuple[EventDraft, ...]) -> None:
        """plan 的命令式落地：逐条 append + apply_event（事件先于状态）。"""
        for draft in drafts:
            envelope = self.event_log.append(
                draft.type,
                stream=draft.stream,
                project_id=draft.project_id,
                session_id=draft.session_id,
                run_id=draft.run_id,
                data=draft.data,
            )
            apply_event(self.core, envelope)

    def transition(
        self,
        agent: AgentSession,
        to: AgentState,
        *,
        reason: str,
        run_id: str | None = None,
    ) -> None:
        self._execute_drafts([plan_transition(agent, to, reason=reason, run_id=run_id)])

    def start_run(self, agent: AgentSession) -> str:
        run_id, drafts = plan_start_run(agent)
        self._execute_drafts(drafts)
        return run_id

    def finish_run(self, agent: AgentSession, *, outcome: str, error: str | None = None) -> None:
        run_id = agent.current_run.run_id if agent.current_run else None
        if run_id is None:
            return
        target = AgentState.SUCCEEDED if outcome == "succeeded" else AgentState.FAILED
        self.transition(agent, target, reason=outcome, run_id=run_id)
        envelope = self.event_log.append(
            "run.finished",
            stream="agent",
            project_id=agent.project_id,
            session_id=agent.id,
            run_id=run_id,
            data={"outcome": outcome, "error": error},
        )
        apply_event(self.core, envelope)

    def resume(self, agent: AgentSession) -> str:
        """Resume the existing run after an external wakeup (message/response)."""
        run_id, drafts = plan_resume(agent)
        self._execute_drafts(drafts)
        return run_id

    def restart(self, agent: AgentSession) -> str:
        run_id, drafts = plan_restart(agent)
        self._execute_drafts(drafts)
        return run_id

    def wake(self, agent: AgentSession, runner: Any = None) -> None:
        """Wake a sleeping or idle agent so pending inbox messages take effect.

        命令式薄壳（plan_wake 的执行版），供 hub_bridge 等非命令路径使用；
        命令侧走 decide 产出同一份草稿。``runner`` 可空，纯状态模式（测试）
        只落事件不调度。
        """
        drafts, should_schedule = plan_wake(agent)
        self._execute_drafts(drafts)
        if should_schedule and runner is not None:
            runner.schedule(agent.id)
