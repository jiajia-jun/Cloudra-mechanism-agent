"""Agent lifecycle: spawn / cancel / restart / state transitions.

AgentSession is a persistent identity.  ``restart`` keeps the id and opens a
new run.  Execution handles (LLM loops, subprocesses) are attached later by
the turn pipeline; the state machine itself is handle-agnostic.
"""

from __future__ import annotations

from typing import Any

from cloudra.runtime_v2.events import EventLog
from cloudra.runtime_v2.schemas import (
    AgentCapabilities,
    AgentSession,
    AgentState,
    CommandRejected,
    CurrentRun,
    Project,
    RoleProfile,
    RuntimeSettings,
    RuntimeSettingsPatch,
    new_id,
    utc_now,
)

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


class AgentHost:
    def __init__(self, event_log: EventLog) -> None:
        self.event_log = event_log

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

    def transition(
        self,
        agent: AgentSession,
        to: AgentState,
        *,
        reason: str,
        run_id: str | None = None,
    ) -> None:
        allowed = _TRANSITIONS.get(agent.state, frozenset())
        if to not in allowed:
            raise CommandRejected(
                "state_conflict",
                f"agent {agent.id} cannot move {agent.state.value} -> {to.value}",
            )
        previous = agent.state
        agent.state = to
        agent.touch()
        self.event_log.append(
            "agent.state_changed",
            stream="agent",
            project_id=agent.project_id,
            session_id=agent.id,
            run_id=run_id,
            data={"from": previous.value, "to": to.value, "reason": reason},
        )

    def start_run(self, agent: AgentSession) -> str:
        if agent.state not in {AgentState.QUEUED, AgentState.SUCCEEDED}:
            raise CommandRejected(
                "state_conflict",
                f"cannot start a run while agent is {agent.state.value}",
            )
        run_id = new_id("run")
        agent.current_run = CurrentRun(run_id=run_id, started_at=utc_now())
        agent.touch()
        self.transition(agent, AgentState.RUNNING, reason="run_started", run_id=run_id)
        self.event_log.append(
            "run.started",
            stream="agent",
            project_id=agent.project_id,
            session_id=agent.id,
            run_id=run_id,
            data={"settings_summary": self._settings_summary(agent.settings)},
        )
        return run_id

    def finish_run(self, agent: AgentSession, *, outcome: str, error: str | None = None) -> None:
        run_id = agent.current_run.run_id if agent.current_run else None
        if run_id is None:
            return
        target = AgentState.SUCCEEDED if outcome == "succeeded" else AgentState.FAILED
        self.transition(agent, target, reason=outcome, run_id=run_id)
        agent.current_run = None
        agent.touch()
        self.event_log.append(
            "run.finished",
            stream="agent",
            project_id=agent.project_id,
            session_id=agent.id,
            run_id=run_id,
            data={"outcome": outcome, "error": error},
        )

    def resume(self, agent: AgentSession) -> str:
        """Resume the existing run after an external wakeup (message/response)."""
        if agent.state not in {AgentState.WAITING_INPUT, AgentState.WAITING_APPROVAL}:
            raise CommandRejected(
                "state_conflict",
                f"agent {agent.id} is {agent.state.value}, not waiting",
            )
        if agent.current_run is None:
            raise CommandRejected("state_conflict", "waiting agent has no active run")
        run_id = agent.current_run.run_id
        self.transition(agent, AgentState.RUNNING, reason="resumed", run_id=run_id)
        return run_id

    def cancel(self, agent: AgentSession) -> None:
        if agent.state is AgentState.CANCELLED:
            return
        if agent.state in {AgentState.SUCCEEDED, AgentState.FAILED}:
            raise CommandRejected(
                "state_conflict",
                f"agent {agent.id} is already terminal ({agent.state.value})",
            )
        run_id = agent.current_run.run_id if agent.current_run else None
        self.transition(agent, AgentState.CANCELLED, reason="cancel", run_id=run_id)
        agent.current_run = None

    def restart(self, agent: AgentSession) -> str:
        if agent.state not in {AgentState.FAILED, AgentState.CANCELLED, AgentState.SUCCEEDED}:
            raise CommandRejected(
                "state_conflict",
                "restart requires a terminal state; cancel a running agent first",
            )
        self.transition(agent, AgentState.QUEUED, reason="restart")
        return new_id("run")

    def wake(self, agent: AgentSession, runner: Any = None) -> None:
        """Wake a sleeping or idle agent so pending inbox messages take effect.

        A RUNNING agent is left alone — its next turn already drains the inbox.
        Terminal agents (failed/cancelled) are reopened into a fresh run,
        succeeded/queued agents start a new run, and waiting agents resume the
        current one.  ``runner`` is optional so command handlers still work in
        pure state mode (no live execution).

        Reopening a terminal agent resets the run-local dialogue history, so an
        ``agent.context_reset`` event marks the boundary explicitly: continuity
        now comes from the goal pin, memory, DAG and workspace files.
        """
        if agent.state is AgentState.RUNNING:
            return
        previous = agent.state
        if agent.state in {AgentState.FAILED, AgentState.CANCELLED}:
            self.restart(agent)
        if agent.state in {AgentState.QUEUED, AgentState.SUCCEEDED}:
            run_id = self.start_run(agent)
            if previous in {
                AgentState.FAILED,
                AgentState.CANCELLED,
                AgentState.SUCCEEDED,
            }:
                self.event_log.append(
                    "agent.context_reset",
                    stream="agent",
                    project_id=agent.project_id,
                    session_id=agent.id,
                    run_id=run_id,
                    data={
                        "reason": "auto_reopen",
                        "previous_outcome": previous.value,
                        "note": (
                            "dialogue history was reset; continuity via "
                            "goal/memory/workspace files"
                        ),
                    },
                )
            if runner is not None:
                runner.schedule(agent.id)
        elif agent.state in {AgentState.WAITING_INPUT, AgentState.WAITING_APPROVAL}:
            if runner is not None:
                self.resume(agent)
                runner.schedule(agent.id)

    @staticmethod
    def patch_settings(agent: AgentSession, patch: RuntimeSettingsPatch) -> AgentSession:
        agent.settings = agent.settings.apply(patch)
        agent.settings_revision += 1
        agent.touch()
        return agent

    @staticmethod
    def _settings_summary(settings: RuntimeSettings) -> dict[str, Any]:
        return {
            "model": settings.model,
            "yolo": settings.yolo,
            "orchestration_mode": settings.orchestration_mode.value,
            "temperature": settings.temperature,
        }
