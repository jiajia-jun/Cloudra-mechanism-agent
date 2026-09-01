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

import json
import sqlite3
from pathlib import Path
from typing import Any

from cloudra.runtime_v2.apply import (
    _strip_computed_fields,
    _strip_removed_agent_fields,
    apply_event,
)
from cloudra.runtime_v2.schemas import (
    AgentSession,
    EventEnvelope,
    Project,
    RoleProfile,
    RuntimeSettings,
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


class RuntimeStore:
    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        self._init()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path, timeout=30.0)

    def _init(self) -> None:
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as con:
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
        last_seqs: dict[str, int],
    ) -> None:
        payload = _strip_computed_fields(
            {
                "projects": {k: v.model_dump(mode="json") for k, v in projects.items()},
                "agents": {k: v.model_dump(mode="json") for k, v in agents.items()},
                "roles": {k: v.model_dump(mode="json") for k, v in roles.items()},
                "runtime_defaults": runtime_defaults.model_dump(mode="json"),
            }
        )
        with self._connect() as con:
            con.execute(
                "INSERT OR REPLACE INTO objects(kind, obj_id, data) VALUES ('snapshot', 'state', ?)",
                (json.dumps(payload, ensure_ascii=False),),
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
    left open: zombie RUNNING/WAITING agents are finalized as failed, and
    orphaned pending approvals/interactions get explicit
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
        for agent in core.agents.values():
            core.mailbox.ensure_inbox(agent.id)

    raw_events = store.events_after(last_seqs)
    envelopes = [EventEnvelope.model_validate(raw) for raw in raw_events]
    # Backfill the full event history into the in-memory log so transcripts
    # and per-session queries survive restarts; only post-snapshot events
    # drive state replay.  restore() keeps seq counters monotonic via max().
    backfill = [EventEnvelope.model_validate(raw) for raw in store.events_after({})]
    core.event_log.restore(backfill)
    for envelope in envelopes:
        apply_event(core, envelope)
    # Notice pins are event-sourced too: rebuild them from the full
    # projection (one-shot pushes are intentionally not restored).
    core.notices.restore_from(core.event_log)

    # Runs live in memory only: an agent restored as RUNNING/WAITING died with
    # the previous process and has no runner anymore.  Mark the run failed so
    # the UI doesn't show a zombie "running" agent forever; a user message
    # reopens it (message-to-terminal auto-restart).
    from cloudra.runtime_v2.schemas import AgentState

    new_events = []
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
                agent, outcome="failed", error="interrupted by process restart"
            )
        else:
            core.agent_host.transition(
                agent, AgentState.FAILED, reason="interrupted by process restart"
            )
        new_events.extend(list(core.event_log)[before:])
    # Orphaned pending entries (a requested approval/interaction whose waiter
    # died with the previous process) get an explicit terminal
    # approval.expired / interaction.expired event, so a woken agent sees a
    # definite terminal state in the event stream instead of the request
    # silently vanishing.  Same append + apply + persist path as the zombie
    # finalization above (no hub publish: restore runs before subscribers).
    new_events.extend(core.pending.expire_orphans())
    for envelope in new_events:
        store.append_event(envelope)
    if new_events:
        store.save_snapshot(
            projects=core.projects,
            agents=core.agents,
            roles=core.roles._roles,
            runtime_defaults=core.runtime_defaults,
            last_seqs=core.event_log.high_watermarks,
        )
    return core.event_log.high_watermarks
