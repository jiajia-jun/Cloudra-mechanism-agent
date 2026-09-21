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
    OrchestrationMode,
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
    "session dialogue context was reset by an explicit restart; "
    "continuity via goal/memory/workspace files"
)


def _settings_summary(settings: RuntimeSettings) -> dict[str, Any]:
    return {
        "model": settings.model,
        "yolo": settings.yolo,
        "orchestration_mode": settings.orchestration_mode.value,
        "invocation_protocol": settings.invocation_protocol.value,
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
            data={
                # The invocation protocol is resolved here and frozen onto
                # CurrentRun by _apply_run_started; mid-run settings changes
                # only affect the next run.
                "invocation_protocol": agent.settings.invocation_protocol.value,
                "settings_summary": _settings_summary(agent.settings),
            },
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

    跨 run 不再重置对话（Task 4）：会话上下文是 session 级投影，重开/唤醒
    沿用同一投影；只有显式 restart 命令才落 agent.context_reset 清投影。

    注意草稿是针对 agent 当前快照一次算全的（restart 后再 start_run 的中间
    态由本函数内部推导），调用方落日志前不得改动 agent。
    """
    state = agent.state
    if state is AgentState.RUNNING:
        return [], False
    drafts: list[EventDraft] = []
    if state in {AgentState.FAILED, AgentState.CANCELLED}:
        drafts.append(
            _transition_draft(agent, AgentState.QUEUED, reason="restart", run_id=None, from_state=state)
        )
        state = AgentState.QUEUED
    if state in {AgentState.QUEUED, AgentState.SUCCEEDED}:
        run_id = new_id("run")
        drafts.extend(_start_run_drafts(agent, state, run_id))
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


def resolve_orchestration_mode(
    project: Project,
    role: RoleProfile,
    override: RuntimeSettingsPatch | None,
) -> OrchestrationMode:
    """编排模式的唯一解析点：项目字段是可继承默认值，显式 patch 是覆盖。

    优先级（低→高）：``project.settings.defaults`` 里的冗余镜像 →
    ``project.settings.orchestration_mode``（项目级默认值的事实源）→
    ``role.default_settings`` → spawn/patch 显式 override。patch 里
    ``orchestration_mode=None`` 即"未设置"（继承），非 None 即显式覆盖——
    split-brain 在结构上不可能：只设项目字段的 API-only 客户端也会得到该
    模式的 agent。解析发生在 spawn（settings 是 agent 的快照，见
    ``effective_settings``）；切换活 agent 的模式走 ``agent.settings_update``
    显式 patch。
    """
    mode = OrchestrationMode.STANDARD
    if project.settings.defaults.orchestration_mode is not None:
        mode = project.settings.defaults.orchestration_mode
    # 专用字段是项目级默认值，压过 defaults patch 里的冗余镜像。
    mode = project.settings.orchestration_mode
    for patch in (role.default_settings, override):
        if patch is not None and patch.orchestration_mode is not None:
            mode = patch.orchestration_mode
    return mode


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
        base.orchestration_mode = resolve_orchestration_mode(project, role, override)
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
        # Supervisor 的工具面是 registry 的 supervisor_access 动态投影
        # （capabilities.supervisor_tool_names），静态 tool_policy 无法表达；
        # 收窄落在这里（能力与线缆投影同源），执行层另有
        # dag/supervisor_tools.py 的路径/动作守卫做第二道闸。
        if role.role_id == "supervisor":
            from cloudra.tools.capabilities import supervisor_tool_names

            tools = supervisor_tool_names()
        else:
            tools = list(role.tool_policy.allow)
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
                tools=tools,
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

    async def _execute_drafts_durable(
        self, drafts: list[EventDraft] | tuple[EventDraft, ...]
    ) -> None:
        """persist-then-apply：落库成功才投影，避免崩溃窗口内存超前。"""
        from cloudra.runtime_v2.event_writer import EventPersistenceError

        keep = len(self.event_log)
        envelopes = []
        for draft in drafts:
            envelopes.append(
                self.event_log.append(
                    draft.type,
                    stream=draft.stream,
                    project_id=draft.project_id,
                    session_id=draft.session_id,
                    run_id=draft.run_id,
                    data=draft.data,
                )
            )
        try:
            await self.core.event_writer.flush()
        except EventPersistenceError:
            self.core.event_writer.discard_unpersisted(keep=keep)
            raise
        for envelope in envelopes:
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

    async def start_run_durable(self, agent: AgentSession) -> str:
        run_id, drafts = plan_start_run(agent)
        await self._execute_drafts_durable(drafts)
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

    async def finish_run_durable(
        self, agent: AgentSession, *, outcome: str, error: str | None = None
    ) -> None:
        run_id = agent.current_run.run_id if agent.current_run else None
        if run_id is None:
            return
        target = AgentState.SUCCEEDED if outcome == "succeeded" else AgentState.FAILED
        drafts = [plan_transition(agent, target, reason=outcome, run_id=run_id)]
        drafts.append(
            EventDraft(
                "run.finished",
                stream="agent",
                project_id=agent.project_id,
                session_id=agent.id,
                run_id=run_id,
                data={"outcome": outcome, "error": error},
            )
        )
        await self._execute_drafts_durable(drafts)

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
