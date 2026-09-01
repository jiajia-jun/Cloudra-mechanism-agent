"""RuntimeCore: in-memory authoritative state assembled from events.

Projects, agents and role overrides live here.  SQLite projections are layered
on later; command handlers only talk to this object, never to storage.

状态外化契约（3e）——运行时状态分两类：
- 事件可推导（重启可重建）：projects/agents/roles/pending_compactions 由
  apply_event 投影（状态承载事件清单见 apply.py docstring）；notices pins、
  pending、reminders 由各 broker 对事件日志的投影重建（pending 孤儿由
  restore 落 approval.expired / interaction.expired 显式闭合）。
- 刻意易失（shell 私有，重启即弃）：mailbox 的 inbox 队列、runner 的 LLM
  history（对话原文不跨 run）、pipeline 的 loop_guard 计数、notices 的
  one-shot pushes、pending._waiters 的 future、reminders/email_listener 的
  asyncio 任务、policy stage 声明为易失的缓存（规则见 policies/base.py）。
明细见各宿主模块 docstring；write-only 秘密 api_key 永不进事件/快照。
"""

from __future__ import annotations

from collections import OrderedDict
from typing import Any

from cloudra.runtime_v2.agent_host import AgentHost
from cloudra.runtime_v2.email_listener import EmailListenerBroker
from cloudra.runtime_v2.events import EventHub, EventLog
from cloudra.runtime_v2.mailbox import Mailbox
from cloudra.runtime_v2.notices import NoticeManager
from cloudra.runtime_v2.pending import PendingBroker
from cloudra.runtime_v2.reminders import ReminderBroker
from cloudra.runtime_v2.roles import BUILTIN_ROLES, RoleRegistry
from cloudra.runtime_v2.schemas import (
    AgentSession,
    Command,
    CommandRejected,
    CommandResult,
    Project,
    RuntimeSettings,
)


class RuntimeCore:
    def __init__(
        self,
        *,
        roles: tuple | None = None,
        strict_events: bool = False,
    ) -> None:
        self.event_log = EventLog(strict=strict_events)
        self.event_hub = EventHub()
        self.mailbox = Mailbox(self.event_log)
        self.agent_host = AgentHost(self)
        self.roles = RoleRegistry(roles if roles is not None else BUILTIN_ROLES)
        self.runtime_defaults = RuntimeSettings()
        self.projects: dict[str, Project] = {}
        self.agents: dict[str, AgentSession] = {}
        # Pending manual compactions (session_id -> keep_recent): an event
        # projection of compaction.requested — the single writer is
        # apply_event; run.started's apply expires entries (a new run's
        # in-memory history is unrelated), the runner consumes at turn
        # boundaries.  Rebuilt by event replay on restore.
        self.pending_compactions: dict[str, int] = {}
        # Pending approvals / ask_user interactions (events + futures).
        self.pending = PendingBroker(self)
        # v2-native schedule reminders (event projection + asyncio timers).
        self.reminders = ReminderBroker(self)
        # Session-level inbound email listener (IMAP poll -> email.received
        # event + agent.message to the active project's coordinator).
        self.email_listener = EmailListenerBroker(self)
        # Unified per-session LLM context injection (pins + one-shot pushes).
        self.notices = NoticeManager()
        # Event-sourced: pin/push changes land in the log (deduplicated), so
        # injections are auditable, replayable, and reachable via commands.
        self.notices.attach(self.event_log, self._project_of_session)
        # Attached by the API/embedder when live execution is desired; command
        # handlers keep working without a runner (pure state mode for tests).
        self.runner = None
        # Attached by the API/embedder when durability is desired.
        self.store = None
        # Idempotency window: recent command_id -> first CommandResult.
        self._command_results: OrderedDict[str, CommandResult] = OrderedDict()
        self._max_command_results = 1024

    # ------------------------------------------------------------------ lookups

    def _project_of_session(self, session_id: str) -> str | None:
        agent = self.agents.get(session_id)
        return agent.project_id if agent is not None else None

    def require_project(self, project_id: str) -> Project:
        project = self.projects.get(project_id)
        if project is None:
            raise CommandRejected("not_found", f"unknown project {project_id!r}")
        return project

    def require_agent(self, session_id: str) -> AgentSession:
        agent = self.agents.get(session_id)
        if agent is None:
            raise CommandRejected("not_found", f"unknown agent session {session_id!r}")
        return agent

    def list_project_agents(self, project_id: str) -> list[AgentSession]:
        self.require_project(project_id)
        return [agent for agent in self.agents.values() if agent.project_id == project_id]

    # ------------------------------------------------------------- event helpers

    def record(
        self,
        type: str,
        *,
        stream: str,
        project_id: str,
        session_id: str | None = None,
        run_id: str | None = None,
        data: dict[str, Any] | None = None,
    ):
        return self.event_log.append(
            type,
            stream=stream,
            project_id=project_id,
            session_id=session_id,
            run_id=run_id,
            data=data,
        )

    # ------------------------------------------------------------ idempotency

    def cached_result(self, command_id: str) -> CommandResult | None:
        result = self._command_results.get(command_id)
        if result is not None:
            self._command_results.move_to_end(command_id)
        return result

    def remember(self, command: Command, result: CommandResult) -> None:
        self._command_results[command.command_id] = result
        while len(self._command_results) > self._max_command_results:
            self._command_results.popitem(last=False)
