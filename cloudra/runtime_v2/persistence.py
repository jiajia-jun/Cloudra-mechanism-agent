"""Runtime v2 persistence: event table + state snapshots + incremental replay.

SQLite is used synchronously behind ``asyncio.to_thread`` only; this module
never runs on the event-loop thread.

快照是缓存不是权威：权威是 events 表，快照只是 restore 的加速点。
``seq`` 是 per-project 计数（见 events.py），所以快照 meta 存**每项目高水
位** ``last_seqs: {project_id: seq}``，``events_after`` 按项目过滤——单个
全局 max 水位会让多项目交错时快照后他项目的新事件（seq ≤ max）被永久漏
重放（3b 修复的丢事件 bug，等价门禁场景 D 守这条）。beta 不留兼容：旧
库只有 ``last_seq`` meta、没有 ``last_seqs``，水位按空处理——快照载荷
照装，但尾巴退化为全量重放（投影幂等，终态与纯重放一致）。
"""

from __future__ import annotations

import contextlib
import json
import sqlite3
from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterator

if TYPE_CHECKING:
    from cloudra.runtime_v2.core import RuntimeCore

from cloudra.runtime_v2.apply import (
    _strip_computed_fields,
    _strip_removed_agent_fields,
    apply_event,
)
from cloudra.runtime_v2.effects import EventDraft
from cloudra.runtime_v2.failures import RunFailureKind
from cloudra.runtime_v2.schemas import (
    AgentSession,
    AgentState,
    EventEnvelope,
    Project,
    RoleProfile,
    RuntimeSettings,
    SessionContext,
    new_id,
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    event_id TEXT PRIMARY KEY,
    stream TEXT NOT NULL,
    project_id TEXT NOT NULL,
    session_id TEXT,
    run_id TEXT,
    seq INTEGER NOT NULL,
    session_seq INTEGER,
    type TEXT NOT NULL,
    data TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS objects (
    kind TEXT NOT NULL,
    obj_id TEXT NOT NULL,
    data TEXT NOT NULL,
    PRIMARY KEY (kind, obj_id)
);
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


# ------------------------------------------------------------- recovery scan

# Tool/program lifecycle state is derivable from the event history alone:
# restore never re-runs an executor, a JS process or a scheduler job — it
# only appends terminal interruption facts for what the dead process left
# open.  This pure planner maps one full restored history to those drafts.

_INTERRUPTED_MESSAGE = "interrupted by process restart"


#: 恢复时用于「child session 状态对账」的终态集合。
_TERMINAL_AGENT_STATES = {AgentState.SUCCEEDED, AgentState.FAILED, AgentState.CANCELLED}


def plan_interrupted_invocations(events: list[EventEnvelope]) -> list[EventDraft]:
    """Pure scan: terminal EventDrafts for unfinished tool/program lifecycles.

    - requested only            -> tool.finished(interrupted, not_started)
    - started, no raw result    -> tool.finished(interrupted, unknown)
    - raw result, no finished   -> tool.finished(interrupted, completed) —
      the effect completed; only postprocessing was interrupted.
    - submitted, no finished    -> program.finished(interrupted) after every
      child of that execution is closed (children close first).

    Idempotent by construction: the appended terminals make the next scan
    empty, so a repeated restore adds nothing.
    """

    by_call: dict[str, dict[str, EventEnvelope]] = {}
    programs: dict[str, dict[str, Any]] = {}
    for envelope in events:
        data = envelope.data or {}
        if envelope.type.startswith("tool."):
            call_id = data.get("tool_call_id")
            if isinstance(call_id, str) and call_id:
                by_call.setdefault(call_id, {})[envelope.type] = envelope
        elif envelope.type == "program.submitted":
            execution_id = data.get("execution_id")
            if isinstance(execution_id, str) and execution_id:
                programs[execution_id] = {"submitted": envelope, "finished": False}
        elif envelope.type == "program.finished":
            execution_id = data.get("execution_id")
            if isinstance(execution_id, str) and execution_id in programs:
                programs[execution_id]["finished"] = True

    drafts: list[EventDraft] = []
    closed: dict[str, dict[str, Any]] = {}  # call_id -> terminal projection
    for call_id, kinds in by_call.items():
        finished = kinds.get("tool.finished")
        if finished is not None:
            data = finished.data
            closed[call_id] = {
                "status": data.get("status"),
                "effect_state": data.get("effect_state"),
                "raw_result_event_id": data.get("raw_result_event_id"),
            }
            continue
        requested = kinds.get("tool.requested")
        if requested is None:
            continue  # orphan mid-lifecycle rows cannot be scoped reliably
        recorded = kinds.get("tool.result_recorded")
        started = kinds.get("tool.started")
        if recorded is not None:
            effect_state = "completed"
        elif started is not None:
            effect_state = "unknown"
        else:
            effect_state = "not_started"
        data = {
            "tool_call_id": call_id,
            "tool_name": requested.data.get("tool_name"),
            "execution_id": requested.data.get("execution_id"),
            "status": "interrupted",
            "effect_state": effect_state,
            "is_success": False,
            "result_summary": _INTERRUPTED_MESSAGE,
            "duration_ms": 0,
            "raw_result_event_id": recorded.event_id if recorded is not None else None,
            "error": {"code": "interrupted", "message": _INTERRUPTED_MESSAGE},
        }
        closed[call_id] = {
            "status": "interrupted",
            "effect_state": effect_state,
            "raw_result_event_id": data["raw_result_event_id"],
        }
        drafts.append(
            EventDraft(
                "tool.finished",
                requested.stream,
                requested.project_id,
                requested.session_id,
                requested.run_id,
                data,
            )
        )

    for execution_id, info in programs.items():
        if info["finished"]:
            continue
        submitted = info["submitted"]
        receipts = []
        for call_id, kinds in by_call.items():
            requested = kinds.get("tool.requested")
            if requested is None or requested.data.get("execution_id") != execution_id:
                continue
            terminal = closed.get(call_id) or {}
            receipts.append(
                {
                    "call_id": call_id,
                    "tool_name": requested.data.get("tool_name"),
                    "status": terminal.get("status") or "interrupted",
                    "effect_state": terminal.get("effect_state") or "not_started",
                    "raw_result_event_id": terminal.get("raw_result_event_id"),
                }
            )
        drafts.append(
            EventDraft(
                "program.finished",
                submitted.stream,
                submitted.project_id,
                submitted.session_id,
                submitted.run_id,
                {
                    "execution_id": execution_id,
                    "outer_tool_call_id": submitted.data.get("outer_tool_call_id"),
                    "status": "interrupted",
                    "duration_ms": 0,
                    "error": {"code": "interrupted", "message": _INTERRUPTED_MESSAGE},
                    "calls": receipts,
                },
            )
        )
    return drafts


class RuntimeStore:
    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        self._init()

    @contextlib.contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        con = sqlite3.connect(self.path, timeout=30.0)
        try:
            con.execute("PRAGMA busy_timeout=30000;")
            con.execute("PRAGMA synchronous=NORMAL;")
            with con:
                yield con
        finally:
            con.close()

    def _init(self) -> None:
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as con:
            # journal_mode 是持久设置：只在当前不是 WAL 时才切换，避免多进程
            # 并发时无谓的重复切换引发锁竞争（与 ConversationDB 同理）。
            # 回滚日志模式下 telemetry 只读全表扫会堵死事件写入（"database is
            # locked"），WAL 下读写不互斥。
            row = con.execute("PRAGMA journal_mode;").fetchone()
            if not row or str(row[0]).lower() != "wal":
                con.execute("PRAGMA journal_mode=WAL;")
            con.executescript(_SCHEMA)

    def append_event(self, envelope: EventEnvelope) -> None:
        with self._connect() as con:
            con.execute(
                """
                INSERT OR IGNORE INTO events
                (event_id, stream, project_id, session_id, run_id, seq, session_seq, type, data, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    envelope.event_id,
                    envelope.stream,
                    envelope.project_id,
                    envelope.session_id,
                    envelope.run_id,
                    envelope.seq,
                    envelope.session_seq,
                    envelope.type,
                    json.dumps(envelope.data, ensure_ascii=False),
                    envelope.created_at.isoformat(),
                ),
            )

    def save_snapshot(
        self,
        *,
        projects: dict[str, Project],
        agents: dict[str, AgentSession],
        roles: dict[str, RoleProfile],
        runtime_defaults: RuntimeSettings,
        session_contexts: dict[str, SessionContext] | None = None,
        pending_compactions: set[str] | None = None,
        last_seqs: dict[str, int],
    ) -> None:
        payload = {
            "projects": {k: v.model_dump(mode="json") for k, v in projects.items()},
            "agents": {k: v.model_dump(mode="json") for k, v in agents.items()},
            "roles": {k: v.model_dump(mode="json") for k, v in roles.items()},
            "runtime_defaults": runtime_defaults.model_dump(mode="json"),
            # 会话级 LLM 上下文投影（Task 4）：快照是缓存，权威是 events
            # 表——快照点之前的 context.* 事件不参与增量重放，必须随快照
            # 落地，否则重启后投影丢失。
            "session_contexts": {
                k: v.model_dump(mode="json") for k, v in (session_contexts or {}).items()
            },
            # pending_compactions 是 compaction.requested 的事件投影；
            # 快照水位越过该事件后增量重放看不到它，必须随快照落地。
            "pending_compactions": sorted(pending_compactions or ()),
        }
        self.write_snapshot_payload(payload, last_seqs)

    def write_snapshot_payload(
        self, payload: dict[str, Any], last_seqs: dict[str, int]
    ) -> None:
        """Persist an already-frozen snapshot blob.

        Callers that hold live core dicts must ``model_dump`` on the event
        loop first — this method may run in a worker thread.
        """
        frozen = _strip_computed_fields(payload)
        with self._connect() as con:
            con.execute(
                "INSERT OR REPLACE INTO objects(kind, obj_id, data) VALUES ('snapshot', 'state', ?)",
                (json.dumps(frozen, ensure_ascii=False),),
            )
            con.execute(
                "INSERT OR REPLACE INTO meta(key, value) VALUES ('last_seqs', ?)",
                (json.dumps(last_seqs),),
            )

    def load_snapshot(self) -> tuple[dict[str, Any] | None, dict[str, int]]:
        with self._connect() as con:
            row = con.execute(
                "SELECT data FROM objects WHERE kind='snapshot' AND obj_id='state'"
            ).fetchone()
            meta = con.execute(
                "SELECT value FROM meta WHERE key='last_seqs'"
            ).fetchone()
        data = json.loads(row[0]) if row else None
        last_seqs = {str(k): int(v) for k, v in json.loads(meta[0]).items()} if meta else {}
        return data, last_seqs

    def events_after(self, last_seqs: dict[str, int]) -> list[dict[str, Any]]:
        """Events past the per-project high watermarks, in append (rowid) order.

        Projects absent from ``last_seqs`` are replayed from their beginning
        (they postdate the snapshot); ``{}`` therefore means "everything".
        rowid order preserves the global append order across projects, so the
        replayed tail is causally ordered (and the full backfill no longer
        interleaves projects by their independent seq counters).
        """
        params: list[Any] = []
        if not last_seqs:
            where = "1=1"
        else:
            clauses = []
            for project_id, seq in last_seqs.items():
                clauses.append("(project_id = ? AND seq > ?)")
                params.extend([project_id, seq])
            placeholders = ",".join("?" for _ in last_seqs)
            clauses.append(f"project_id NOT IN ({placeholders})")
            params.extend(last_seqs.keys())
            where = " OR ".join(clauses)
        with self._connect() as con:
            rows = con.execute(
                f"""
                SELECT event_id, stream, project_id, session_id, run_id, seq, session_seq, type, data, created_at
                FROM events WHERE {where} ORDER BY rowid
                """,
                params,
            ).fetchall()
        events = []
        for row in rows:
            events.append(
                {
                    "event_id": row[0],
                    "stream": row[1],
                    "project_id": row[2],
                    "session_id": row[3],
                    "run_id": row[4],
                    "seq": row[5],
                    "session_seq": row[6],
                    "type": row[7],
                    "data": json.loads(row[8]),
                    "created_at": row[9],
                }
            )
        return events

    def query_project_events(self, project_id: str, limit: int = 500) -> list[dict[str, Any]]:
        with self._connect() as con:
            rows = con.execute(
                """
                SELECT event_id, stream, project_id, session_id, run_id, seq, session_seq, type, data, created_at
                FROM events WHERE project_id = ? ORDER BY seq DESC LIMIT ?
                """,
                (project_id, limit),
            ).fetchall()
        return [dict(zip(
            ("event_id", "stream", "project_id", "session_id", "run_id", "seq", "session_seq", "type", "data", "created_at"),
            row,
        )) for row in reversed(rows)]


def restore_core(core: Any, store: RuntimeStore) -> dict[str, int]:
    """Load the latest snapshot, then replay state-relevant events after it.

    Returns the per-project high watermarks after restore.  Events are
    appended back into the in-memory log with their original seq so new
    events continue monotonically.  Restore also closes what the dead process
    left open: zombie RUNNING/WAITING agents are finalized as failed (and a
    zombie child's terminal state is delivered to its parent's mailbox
    without waking a sleeping parent — explicit resume only), and orphaned
    pending approvals/interactions get explicit
    approval.expired / interaction.expired terminal events (3c).
    """

    snapshot, last_seqs = store.load_snapshot()
    if snapshot:
        core.projects = {
            pid: Project.model_validate(data)
            for pid, data in snapshot.get("projects", {}).items()
        }
        core.agents = {
            sid: AgentSession.model_validate(_strip_removed_agent_fields(data))
            for sid, data in snapshot.get("agents", {}).items()
        }
        # 快照角色是内置角色表上的覆盖层（携带 role.update 补丁），不能整个
        # 替换注册表——否则旧快照会丢掉后加的内置角色（如 supervisor）。
        from cloudra.runtime_v2.roles import BUILTIN_ROLES

        merged = {role.role_id: role for role in BUILTIN_ROLES}
        for data in snapshot.get("roles", {}).values():
            role = RoleProfile.model_validate(data)
            merged[role.role_id] = role
        core.roles = type(core.roles)(tuple(merged.values()))
        core.runtime_defaults = RuntimeSettings.model_validate(
            snapshot.get("runtime_defaults", {})
        )
        # 会话级 LLM 上下文投影随快照恢复（快照点之后的 context.* 事件由
        # 下面的增量重放经 apply_event 补上）。
        core.session_contexts = {
            sid: SessionContext.model_validate(data)
            for sid, data in snapshot.get("session_contexts", {}).items()
        }
        core.pending_compactions = {
            str(session_id)
            for session_id in snapshot.get("pending_compactions") or []
            if session_id
        }
        for agent in core.agents.values():
            core.mailbox.ensure_inbox(agent.id)

    raw_events = store.events_after(last_seqs)
    envelopes = [EventEnvelope.model_validate(raw) for raw in raw_events]
    # Backfill the full event history into the in-memory log so transcripts
    # and per-session queries survive restarts; only post-snapshot events
    # drive state replay.  restore() keeps seq counters monotonic via max().
    backfill = [EventEnvelope.model_validate(raw) for raw in store.events_after({})]
    core.event_log.restore(backfill)
    # The backfilled history is already durable and was published by the dead
    # process: keep the shared writer from re-persisting/re-publishing it.
    # Recovery events appended below this point stay live for the writer.
    core.event_writer.mark_restored()
    for envelope in envelopes:
        apply_event(core, envelope)
    # Notice pins are event-sourced too: rebuild them from the full
    # projection (未消费的 push 变更同样恢复；已消费的由游标挡回——见
    # notices.restore_from 的批次/游标语义）。
    core.notices.restore_from(core.event_log)
    _rebuild_inboxes_from_events(core)

    # Unfinished tool/program lifecycles left by the dead process close as
    # interrupted (children before programs) — facts only, never a replay of
    # executors, JS processes or scheduler jobs.
    new_events = []
    for draft in plan_interrupted_invocations(list(core.event_log)):
        envelope = core.event_log.append(
            draft.type,
            stream=draft.stream,
            project_id=draft.project_id,
            session_id=draft.session_id,
            run_id=draft.run_id,
            data=draft.data,
        )
        apply_event(core, envelope)
        new_events.append(envelope)

    # Runs live in memory only: an agent restored as RUNNING/WAITING died with
    # the previous process and has no runner anymore.  Mark the run failed so
    # the UI doesn't show a zombie "running" agent forever; a user message
    # reopens it (message-to-terminal auto-restart).
    from cloudra.runtime_v2.schemas import AgentState

    zombies = []
    for agent in core.agents.values():
        if agent.state not in {
            AgentState.RUNNING,
            AgentState.WAITING_INPUT,
            AgentState.WAITING_APPROVAL,
        }:
            continue
        before = len(core.event_log)
        if agent.current_run is not None:
            core.agent_host.finish_run(
                agent,
                outcome="failed",
                error="interrupted by process restart",
                failure_kind=RunFailureKind.RUNTIME_INTERRUPTED,
            )
        else:
            core.agent_host.transition(
                agent, AgentState.FAILED, reason="interrupted by process restart"
            )
        new_events.extend(list(core.event_log)[before:])
        zombies.append(agent)
    # 跨重启子终态回传：僵尸子的父还在等它的结果（is_wait=False 派发只有这
    # 一条通知通道），与普通完成回传同一载荷构造送达父信箱；恢复路径不 wake
    # （包括 succeeded 休眠父）——runner 已装时 wake 会真实打进 LLM，把
    # 旧项目的协调者/探索者在 API 重启时烧起来（issue #35）。通知驻留信箱，
    # 显式 resume 后首轮即可读到。
    #
    # 次序与 MessageDispatcher 一致（append → durable → enqueue）；恢复阶段没有
    # 事件循环，用本函数末尾的一次性落库屏障代替逐条 commit：先收齐全部恢复
    # 事件，落库成功后才入队。
    from cloudra.runtime_v2.mailbox import Mailbox
    from cloudra.runtime_v2.subagent_bridge import child_completion_message

    pending_inbox: list[tuple[str, dict[str, Any]]] = []
    for agent in zombies:
        message = child_completion_message(core, agent)
        if message is None:
            continue
        parent_id, content, manifest = message
        message_id = new_id("msg")
        new_events.append(
            core.event_log.append(
                "agent.message_injected",
                stream="project",
                project_id=agent.project_id,
                session_id=parent_id,
                data=Mailbox.message_data(
                    message_id=message_id,
                    sender=agent.role_id,
                    content=content,
                    manifest=manifest,
                ),
            )
        )
        pending_inbox.append(
            (
                parent_id,
                Mailbox.message_payload(
                    message_id=message_id, sender=agent.role_id, content=content
                ),
            )
        )
    # Orphaned pending entries (a requested approval/interaction whose waiter
    # died with the previous process) get an explicit terminal
    # approval.expired / interaction.expired event, so a woken agent sees a
    # definite terminal state in the event stream instead of the request
    # silently vanishing.  Same append + apply + persist path as the zombie
    # finalization above (no hub publish: restore runs before subscribers).
    new_events.extend(core.pending.expire_orphans())
    # launch group（评审 5.2）：组清单随事件重放重建，但**绝不重放外部副作用**——
    # 重启不会重新 spawn 任何 child。非终态的组在这里显式收口为 interrupted：
    # 未派发的 queued item 保持 queued（用户可显式重新派发），已存在的 child
    # session 只做状态对账（从活 agent 的终态取值，不猜）。
    for group in core.launch_groups.groups():
        if group.state != "running":
            continue
        envelope = core.event_log.append(
            "launch_group.finished",
            stream="agent",
            project_id=group.project_id,
            session_id=group.parent_session_id,
            data={
                "group_id": group.group_id,
                "state": "interrupted",
                "reason": "process restart: group worker is gone; re-dispatch explicitly",
            },
        )
        apply_event(core, envelope)
        new_events.append(envelope)
        for item in group.items:
            if item.state != "running":
                continue
            child = core.agents.get(item.child_session_id)
            if child is None or child.state not in _TERMINAL_AGENT_STATES:
                continue
            item.state = (  # type: ignore[assignment]
                "succeeded"
                if child.state is AgentState.SUCCEEDED
                else "failed" if child.state is AgentState.FAILED else "cancelled"
            )
    for envelope in new_events:
        store.append_event(envelope)
    # 落库成功之后才把恢复期组装的完成回传放进父信箱（持久化先于可见）。
    for session_id, payload in pending_inbox:
        core.mailbox.ensure_inbox(session_id).put_nowait(payload)
    if new_events:
        store.save_snapshot(
            projects=core.projects,
            agents=core.agents,
            roles=core.roles._roles,
            runtime_defaults=core.runtime_defaults,
            session_contexts=core.session_contexts,
            pending_compactions=core.pending_compactions,
            last_seqs=core.event_log.high_watermarks,
        )
    return core.event_log.high_watermarks


def _rebuild_inboxes_from_events(core: RuntimeCore) -> None:
    """从已持久化但尚未进入 session_contexts 的 agent.message_injected 重建信箱。

    解决二次崩溃/休眠 agent 丢信问题：给休眠父的子完成通知、提醒唤醒、未读用户消息，
    只要尚未进入 LLM 上下文投影（按 message_id 判重），重启后重新入队 inbox。
    """
    from cloudra.runtime_v2.mailbox import Mailbox
    from cloudra.runtime_v2.schemas import AgentState

    known_by_session: dict[str, set[str]] = {}
    for sid, ctx in core.session_contexts.items():
        known_by_session[sid] = {
            str(m.get("message_id"))
            for m in ctx.messages
            if m.get("role") == "user" and m.get("message_id")
        }

    seen_enqueued: dict[str, set[str]] = {}
    for envelope in core.event_log:
        if envelope.type != "agent.message_injected":
            continue
        session_id = envelope.session_id
        if not session_id or session_id not in core.agents:
            continue
        agent = core.agents[session_id]
        if agent.state is AgentState.CANCELLED:
            continue
        data = envelope.data or {}
        msg_id = str(data.get("message_id") or "")
        if not msg_id:
            continue
        known = known_by_session.get(session_id, set())
        if msg_id in known:
            continue
        enqueued = seen_enqueued.setdefault(session_id, set())
        if msg_id in enqueued:
            continue
        enqueued.add(msg_id)
        payload = Mailbox.message_payload(
            message_id=msg_id,
            sender=str(data.get("sender") or ""),
            content=str(data.get("content") or ""),
            images=data.get("images"),
        )
        core.mailbox.ensure_inbox(session_id).put_nowait(payload)

