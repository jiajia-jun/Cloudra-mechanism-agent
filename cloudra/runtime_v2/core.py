"""RuntimeCore: in-memory authoritative state assembled from events.

Projects, agents and role overrides live here.  SQLite projections are layered
on later; command handlers only talk to this object, never to storage.

状态外化契约（3e）——运行时状态分两类：
- 事件可推导（重启可重建）：projects/agents/roles/pending_compactions 由
  apply_event 投影（状态承载事件清单见 apply.py docstring）；notices pins、
  pending、reminders 由各 broker 对事件日志的投影重建（pending 孤儿由
  restore 落 approval.expired / interaction.expired 显式闭合）；
  ``session_contexts``（会话级 LLM 上下文投影，Task 4）同样由
  apply_event 从 context.prefix_installed/appended/compacted 重建——
  一个 session 一份上下文，run 只是执行生命周期。
- 刻意易失（shell 私有，重启即弃）：mailbox 的 inbox 队列、pipeline 的
  loop_guard 计数、notices 的 pending 批次（park 未确认，重启后由事件
  游标重算）、pending._waiters 的 future、reminders/email_listener 的
  asyncio 任务、policy stage 声明为易失的缓存（规则见 policies/base.py）。
明细见各宿主模块 docstring；write-only 秘密 api_key 永不进事件/快照。
"""

from __future__ import annotations

import asyncio
import logging
from collections import OrderedDict
from typing import Any

from cloudra.runtime_v2.agent_host import AgentHost
from cloudra.runtime_v2.dispatcher import MessageDispatcher
from cloudra.runtime_v2.email_listener import EmailListenerBroker
from cloudra.runtime_v2.events import EventHub, EventLog
from cloudra.runtime_v2.launch_groups import LaunchGroupManager
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
    SessionContext,
)


class ContextBroker:
    """会话级 LLM 上下文投影的唯一写口（Task 4：一个 session 一份上下文）。

    写路径拍序与 CommandBus 一致：event_log.append → flush → apply_event
    （持久化失败丢未持久化尾巴，不投影）。恢复路径经 restore_core（快照
    + 增量重放）走同一批 applier 重建投影，绝不执行工具/JS/计算。
    """

    def __init__(self, core: "RuntimeCore") -> None:
        self.core = core

    def current_messages(self, session_id: str) -> list[dict]:
        ctx = self.core.session_contexts.get(session_id)
        return list(ctx.messages) if ctx is not None else []

    def prefix_state(self, session_id: str) -> dict | None:
        """ContextPrefix owner 跨 run/重启回灌素材：安装元数据 + 投影全文。"""
        ctx = self.core.session_contexts.get(session_id)
        if ctx is None or ctx.prefix_meta is None:
            return None
        return {"meta": dict(ctx.prefix_meta), "messages": list(ctx.messages)}

    def filter_pending_input(
        self, session_id: str, inbox_messages: list[dict]
    ) -> list[dict]:
        """剔除已进入投影的输入消息（按 message_id）：LLM 重试/重启恢复后
        同一条 inbox 消息不重复进上下文；无 message_id 的条目（测试）原样保留。"""
        ctx = self.core.session_contexts.get(session_id)
        if ctx is None:
            return list(inbox_messages)
        known = {
            str(message.get("message_id"))
            for message in ctx.messages
            if message.get("role") == "user" and message.get("message_id")
        }
        return [
            item
            for item in inbox_messages
            if not item.get("message_id") or str(item["message_id"]) not in known
        ]

    async def commit_input(
        self, *, agent: AgentSession, run_id: str, context_prefix, notices, user_messages: list[dict]
    ) -> None:
        """发送 LLM 请求前，把本轮输入落进会话上下文投影（恰好一次）。

        顺序：前缀 install/refresh 增量 → inbox 用户消息 → 通知批次。
        ``user_messages`` 由 TurnPipeline 成形（与请求里的条目逐字节一致，
        含 message_id 锚点）。通知正文与消费游标在同一 context.appended
        事件内提交，避免恢复时只看到消费标记。事件全部持久化（flush）后
        调用方才发送请求。
        """
        install: tuple = ()
        appends: tuple = ()
        if context_prefix is not None:
            install, appends = context_prefix.drain_pending()
        notice_messages, notices_through = (
            notices.pending_batch(agent.id) if notices is not None else ([], None)
        )
        events: list[tuple[str, dict]] = []
        if install:
            events.append(
                (
                    "context.prefix_installed",
                    {"messages": list(install), "meta": context_prefix.snapshot_meta()},
                )
            )
        appended = [*appends, *user_messages, *notice_messages]
        if appended or notices_through is not None:
            data = {"messages": appended}
            if notices_through is not None:
                data["notices_through"] = notices_through
            events.append(("context.appended", data))
        if not events:
            return
        await self._persist_then_apply(
            agent=agent, run_id=run_id, events=events
        )

    async def append_output(self, *, agent: AgentSession, run_id: str, messages: list[dict]) -> None:
        """响应落上下文：完整的 assistant/tool 消息（文本、工具配对、
        reasoning、稳定媒体引用）追加进投影。"""
        if not messages:
            return
        await self._persist_then_apply(
            agent=agent,
            run_id=run_id,
            events=[("context.appended", {"messages": list(messages)})],
        )

    async def install_compacted(
        self, *, agent: AgentSession, run_id: str, messages: list[dict],
        prefix_meta: dict | None, expected_version: int, trigger: str,
    ) -> bool:
        """compact 候选的原子安装：一条事件整体替换会话上下文投影。

        版本守卫：``expected_version`` 是候选输入冻结时的投影长度；不一致
        说明压缩期间有新消息进入投影——放弃候选（返回 False，不落事件），
        绝不覆盖新增的用户纠正。调用方只在摘要完整成功时调用本方法。
        """
        ctx = self.core.session_contexts.get(agent.id)
        current_version = len(ctx.messages) if ctx is not None else 0
        if current_version != expected_version:
            return False
        await self._persist_then_apply(
            agent=agent,
            run_id=run_id,
            events=[
                (
                    "context.compacted",
                    {
                        "messages": list(messages),
                        "prefix_meta": dict(prefix_meta) if prefix_meta else None,
                        "expected_version": expected_version,
                        "trigger": trigger,
                    },
                )
            ],
        )
        return True

    async def _persist_then_apply(
        self,
        *,
        agent: "AgentSession",
        run_id: str,
        events: list[tuple[str, dict]],
    ) -> None:
        from cloudra.runtime_v2.apply import apply_event
        from cloudra.runtime_v2.event_writer import EventPersistenceError

        core = self.core
        keep = len(core.event_log)
        envelopes = []
        for event_type, data in events:
            envelopes.append(
                core.event_log.append(
                    event_type,
                    stream="agent",
                    project_id=agent.project_id,
                    session_id=agent.id,
                    run_id=run_id,
                    data=data,
                )
            )
        try:
            await core.event_writer.flush()
        except EventPersistenceError:
            core.event_writer.discard_unpersisted(keep=keep)
            raise
        for envelope in envelopes:
            apply_event(core, envelope)


class _TaskReentrantLock:
    """asyncio.Lock that the same task may re-enter.

    CommandBus.flush publishes to hub subscribers that may nested-execute
    another command on the same core; a plain Lock would deadlock that path
    (see test_nested_subscriber_commands_do_not_deadlock). Concurrent tasks
    still serialize.
    """

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._owner: asyncio.Task | None = None
        self._depth = 0

    async def __aenter__(self):
        task = asyncio.current_task()
        if task is not None and self._owner is task:
            self._depth += 1
            return self
        await self._lock.acquire()
        self._owner = task
        self._depth = 1
        return self

    async def __aexit__(self, *_exc) -> None:
        self._depth -= 1
        if self._depth <= 0:
            self._depth = 0
            self._owner = None
            self._lock.release()


class RuntimeCore:
    def __init__(
        self,
        *,
        roles: tuple | None = None,
        strict_events: bool = False,
    ) -> None:
        self.event_log = EventLog(strict=strict_events)
        self.event_hub = EventHub()
        # Attached by the API/embedder when durability is desired.
        self.store = None
        # Shared write-ahead event writer (persist-before-publish), resolved
        # against the live store on every flush because the store attaches
        # after construction.
        from cloudra.runtime_v2.event_writer import EventWriter

        self.event_writer = EventWriter(
            self.event_log, self.event_hub, store_provider=lambda: self.store
        )
        self.mailbox = Mailbox(self.event_log)
        # 组生命周期是事件投影（launch_group.* 事件）：apply_event 的唯一写入点，
        # 恢复重放据此重建组清单（worker 任务不重放）。
        self.launch_groups = LaunchGroupManager(core=self)
        # 消息提交/投递唯一入口（评审 5.2）：持久化成功才入队、再按策略唤醒。
        self.dispatcher = MessageDispatcher(self)
        self.agent_host = AgentHost(self)
        self.roles = RoleRegistry(roles if roles is not None else BUILTIN_ROLES)
        self.runtime_defaults = RuntimeSettings()
        self.projects: dict[str, Project] = {}
        self.agents: dict[str, AgentSession] = {}
        # Pending manual compactions (session ids): an event projection of
        # compaction.requested — the single writer is apply_event.  The
        # context is a session-level projection, so a request survives run
        # boundaries until the runner consumes it at a turn boundary.
        # Rebuilt by event replay on restore.
        self.pending_compactions: set[str] = set()
        # Pending approvals / ask_user interactions (events + futures).
        self.pending = PendingBroker(self)
        # v2-native schedule reminders (event projection + asyncio timers /
        # optional read-only check pollers).
        self.reminders = ReminderBroker(self)
        # Session-level inbound email listener (IMAP poll -> email.received
        # event + agent.message to the active project's coordinator).
        self.email_listener = EmailListenerBroker(self)
        # Unified per-session LLM context injection (pins + one-shot pushes).
        self.notices = NoticeManager()
        # Event-sourced: pin/push changes land in the log (deduplicated), so
        # injections are auditable, replayable, and reachable via commands.
        self.notices.attach(self.event_log, self._project_of_session)
        from cloudra.runtime_v2.task_describer import TaskDescriber

        self.task_describer = TaskDescriber(self)
        # 会话级 LLM 上下文投影（Task 4）：session_id -> SessionContext，
        # 由 apply_event 从 context.* 事件重建；ContextBroker 是唯一写口。
        self.session_contexts: dict[str, SessionContext] = {}
        self.contexts = ContextBroker(self)
        # Attached by the API/embedder when live execution is desired; command
        # handlers keep working without a runner (pure state mode for tests).
        self.runner = None
        # launch group 管理器在 __init__ 就装配（见上）：组清单是 launch_group.*
        # 事件投影，apply_event 需要它常驻；worker 任务才是进程内的。
        # Idempotency window: recent command_id -> first CommandResult.
        self._command_results: OrderedDict[str, CommandResult] = OrderedDict()
        self._max_command_results = 1024
        # Same-task re-entry: hub subscribers may nested-execute during flush.
        # Concurrent tasks (API vs reminder vs compute notify) still serialize.
        self.command_lock = _TaskReentrantLock()

    # ------------------------------------------------------------- shutdown

    def prune_orphaned_state(self) -> None:
        """Release projections and local resources whose project/session was deleted.

        Called by the tombstone applier and after snapshot/event restoration.
        Audit events remain durable; this only drops their unused live projections.
        """
        sessions = set(self.agents)
        projects = set(self.projects)
        for session_id in self.session_contexts.keys() - sessions:
            self.session_contexts.pop(session_id)
        self.pending_compactions.intersection_update(sessions)
        self.mailbox.prune_sessions(sessions)
        self.notices.prune_sessions(sessions)
        self.launch_groups.prune_projects(projects, sessions)
        self.reminders.prune_projects(projects)
        self.task_describer.prune_sessions(sessions)
        if self.runner is not None:
            self.runner.prune_orphaned_state()

    async def aclose(self) -> None:
        """服务关闭唯一入口（停止语义契约 3）：取消并 await 全部 runner 与
        已登记收尾后台任务（含 finalize），再回收本 core 拥有的 JS host。

        准入停止（拒绝新任务/守护拉起）由调用方先行（api_v2 lifespan 停
        watchdog + ``request_daemons_shutdown``）。已发出的远端 LLM 请求
        不可撤回（契约 4）；本地读取/重试/新请求随 runner 取消链停止。
        不触碰 scheduler/guard/QM 计算进程（契约 5 与执行面铁律）。
        """
        runner = self.runner
        # 组管理器随 core 常驻：先按组收敛状态，再由 cancel_all 取消并 await
        # 全部 run/后台任务。
        await self.launch_groups.cancel_all()
        if runner is not None:
            await runner.cancel_all()
            js_runtime = getattr(getattr(runner, "pipeline", None), "js_runtime", None)
            if js_runtime is not None:
                try:
                    await js_runtime.aclose()
                except Exception:
                    logging.getLogger(__name__).warning(
                        "js runtime shutdown failed", exc_info=True
                    )
        if getattr(self, "task_describer", None) is not None:
            self.task_describer.close()

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
