"""Runtime v2 persistence: event table + state snapshots + incremental replay.

SQLite is used synchronously behind ``asyncio.to_thread`` only; this module
never runs on the event-loop thread.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from cloudra.runtime_v2.schemas import (
    AgentSession,
    EventEnvelope,
    Project,
    RoleProfile,
    RuntimeSettings,
    RuntimeSettingsPatch,
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


def _strip_computed_fields(value: Any) -> Any:
    """Remove computed-only keys (currently api_key_set) before persistence."""
    if isinstance(value, dict):
        return {k: _strip_computed_fields(v) for k, v in value.items() if k != "api_key_set"}
    if isinstance(value, list):
        return [_strip_computed_fields(item) for item in value]
    return value


def _strip_removed_agent_fields(data: dict[str, Any]) -> dict[str, Any]:
    """Drop agent fields removed after older snapshots/events were written.

    AgentSession validates with extra="forbid", so a pre-removal snapshot
    carrying ``state_since`` or ``current_run.current_tool`` would fail to
    restore; both fields had no readers, so dropping them is lossless.
    """
    data = {k: v for k, v in data.items() if k != "state_since"}
    run = data.get("current_run")
    if isinstance(run, dict):
        data["current_run"] = {k: v for k, v in run.items() if k != "current_tool"}
    return data


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
        last_seq: int,
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
                "INSERT OR REPLACE INTO meta(key, value) VALUES ('last_seq', ?)",
                (str(last_seq),),
            )

    def load_snapshot(self) -> tuple[dict[str, Any], int]:
        with self._connect() as con:
            row = con.execute(
                "SELECT data FROM objects WHERE kind='snapshot' AND obj_id='state'"
            ).fetchone()
            meta = con.execute(
                "SELECT value FROM meta WHERE key='last_seq'"
            ).fetchone()
        data = json.loads(row[0]) if row else None
        last_seq = int(meta[0]) if meta else 0
        return data, last_seq

    def events_after(self, last_seq: int) -> list[dict[str, Any]]:
        with self._connect() as con:
            rows = con.execute(
                """
                SELECT event_id, stream, project_id, session_id, run_id, seq, session_seq, type, data, created_at
                FROM events WHERE seq > ? ORDER BY seq
                """,
                (last_seq,),
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


def restore_core(core: Any, store: RuntimeStore) -> int:
    """Load the latest snapshot, then replay state-relevant events after it.

    Returns the last replayed project seq.  Events are appended back into the
    in-memory log with their original seq so new events continue monotonically.
    """

    snapshot, last_seq = store.load_snapshot()
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

    raw_events = store.events_after(last_seq)
    envelopes = [EventEnvelope.model_validate(raw) for raw in raw_events]
    # Backfill the full event history into the in-memory log so transcripts
    # and per-session queries survive restarts; only post-snapshot events
    # drive state replay.  restore() keeps seq counters monotonic via max().
    backfill = [EventEnvelope.model_validate(raw) for raw in store.events_after(0)]
    core.event_log.restore(backfill)
    for envelope in envelopes:
        _replay_event(core, envelope)
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
    for envelope in new_events:
        store.append_event(envelope)
    if new_events:
        store.save_snapshot(
            projects=core.projects,
            agents=core.agents,
            roles=core.roles._roles,
            runtime_defaults=core.runtime_defaults,
            last_seq=core.event_log.last_seq,
        )
    return envelopes[-1].seq if envelopes else last_seq


def _replay_event(core: Any, envelope: EventEnvelope) -> None:
    data = envelope.data
    event_type = envelope.type
    if event_type == "project.created":
        project = Project.model_validate(data)
        core.projects[project.id] = project
    elif event_type == "project.updated":
        project = core.require_project(envelope.project_id)
        changes = data.get("changes", {})
        project = project.model_copy(update=changes)
        project.touch()
        core.projects[project.id] = project
    elif event_type == "project.settings_changed":
        project = core.require_project(envelope.project_id)
        from cloudra.runtime_v2.schemas import ProjectSettings

        settings = ProjectSettings.model_validate(data["changes"])
        project = project.model_copy(update={"settings": settings})
        project.touch()
        core.projects[project.id] = project
    elif event_type == "agent.spawned":
        agent = AgentSession.model_validate(_strip_removed_agent_fields(data))
        core.agents[agent.id] = agent
        core.mailbox.ensure_inbox(agent.id)
    elif event_type == "agent.settings_changed":
        agent = core.require_agent(envelope.session_id or "")
        changes = {k: v for k, v in data.get("changes", {}).items() if k != "api_key_set"}
        agent.settings = agent.settings.apply(RuntimeSettingsPatch.model_validate(changes))
        agent.settings_revision = int(data.get("settings_revision", agent.settings_revision))
        agent.touch()
    elif event_type == "agent.state_changed":
        agent = core.require_agent(envelope.session_id or "")
        from cloudra.runtime_v2.schemas import AgentState

        agent.state = AgentState(data["to"])
        agent.touch()
    elif event_type == "run.started":
        agent = core.require_agent(envelope.session_id or "")
        from cloudra.runtime_v2.schemas import CurrentRun

        agent.current_run = CurrentRun(run_id=envelope.run_id or "", started_at=envelope.created_at)
        agent.touch()
    elif event_type in {"run.finished", "agent.cancelled"}:
        agent = core.require_agent(envelope.session_id or "")
        agent.current_run = None
        agent.touch()
    elif event_type == "role.updated":
        core.roles.update(data["role_id"], data["changes"])
