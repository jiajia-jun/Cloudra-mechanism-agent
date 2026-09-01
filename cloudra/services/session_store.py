"""Session 状态与遥测事件（session_events）的唯一写入入口。

所有对 ``session`` / ``session_events`` 表的写操作都必须经过本模块，
调用方不再内联 SQL。连接统一由
:class:`cloudra.persistence.database.ConversationDB` 提供（WAL + busy_timeout），
短时写操作统一经 ``retry_on_locked`` / ``aretry_on_locked`` 重试。
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from cloudra.persistence.database import ConversationDB, aretry_on_locked, retry_on_locked


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


_META_TOUCH_INTERVAL_SECONDS = 60.0
_last_meta_touch: dict[str, float] = {}


def _touch_conversation_meta(db: ConversationDB) -> None:
    """Best-effort 刷新 meta.json 的 last_active（会话列表按它排序）。

    节流到每分钟一次；直接读写 db 旁边的 meta.json，不依赖全局配置的
    data_dir 解析。读-改-写与 Conversation._save_meta 存在理论竞争，
    但只动 last_active 一个字段且频率极低，失败静默。
    """
    try:
        db_dir = Path(db.path).parent
        # 标准布局是 conversations/<conv>/tasks/database.db，meta.json 在
        # conversations/<conv>/ 下；from_path 的自定义路径也兼容查父目录。
        meta_path = next(
            (p for p in (db_dir / "meta.json", db_dir.parent / "meta.json") if p.is_file()),
            None,
        )
        if meta_path is None:
            return
        key = str(meta_path)
        now = time.time()
        if now - _last_meta_touch.get(key, 0.0) < _META_TOUCH_INTERVAL_SECONDS:
            return
        _last_meta_touch[key] = now
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        if not isinstance(meta, dict):
            return
        meta["last_active"] = datetime.now().isoformat()
        from cloudra.persistence.fs_utils import atomic_write_json

        atomic_write_json(str(meta_path), meta)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Session 生命周期
# ---------------------------------------------------------------------------

def create_session_record(
    db: ConversationDB,
    *,
    session_id: str,
    agent_id: Optional[str],
    agent_type: Optional[str],
    parent_session_id: Optional[str],
    query: str,
    created_at: str,
    pid: Optional[int] = None,
    worker_id: Optional[str] = None,
    orchestration_mode: str = "standard",
    orchestration_config: dict | None = None,
) -> None:
    """创建即入库（reAct.session_create）：INSERT OR IGNORE + COALESCE 补齐元数据。"""
    from cloudra.dag.models import normalize_orchestration_mode

    pid = os.getpid() if pid is None else pid
    worker_id = worker_id or f"process:{pid}"
    now = _utc_now()
    normalized_mode = normalize_orchestration_mode(orchestration_mode).value
    serialized_config = json.dumps(
        orchestration_config or {},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )

    def write() -> None:
        with db.connect() as con:
            con.execute(
                """INSERT OR IGNORE INTO session
                (session_id, agent_id, agent_type, parent_session_id, query, state, result, pid,
                 worker_id, created_at, started_at, heartbeat_at,
                 orchestration_mode, orchestration_config)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    session_id, agent_id, agent_type, parent_session_id, query,
                    "running", "", pid, worker_id, created_at, now, now,
                    normalized_mode, serialized_config,
                ),
            )
            con.execute(
                """UPDATE session SET
                agent_id = COALESCE(agent_id, ?),
                agent_type = COALESCE(agent_type, ?),
                parent_session_id = COALESCE(parent_session_id, ?),
                query = COALESCE(query, ?),
                state = 'running',
                pid = ?,
                worker_id = ?,
                started_at = COALESCE(started_at, ?)
                WHERE session_id = ?""",
                (agent_id, agent_type, parent_session_id, query, pid, worker_id, now, session_id),
            )
            con.commit()

    retry_on_locked(write)
    _touch_conversation_meta(db)


# finalize_session 的 UPDATE 语句：
# finished_at 永远 COALESCE（首个终态时间戳生效），result/error 仅在提供时覆盖。
_FINALIZE_SESSION_SQL = """UPDATE session SET state=?,
    result=COALESCE(?, result),
    error=COALESCE(?, error),
    finished_at=COALESCE(finished_at, ?)
    WHERE session_id=?"""


def finalize_session(
    db: ConversationDB,
    session_id: str,
    state: str,
    *,
    result: Optional[str] = None,
    error: Optional[str] = None,
) -> None:
    """落库 Session 终态（同步）。finished_at 永远 COALESCE：首个终态时间戳生效。"""

    def write() -> None:
        with db.connect() as con:
            con.execute(_FINALIZE_SESSION_SQL, (state, result, error, _utc_now(), session_id))
            con.commit()

    retry_on_locked(write)
    _touch_conversation_meta(db)


# ---------------------------------------------------------------------------
# 遥测事件（session_events）
# ---------------------------------------------------------------------------

async def arecord_event(db: ConversationDB, session_id: str, event_type: str, data: dict) -> None:
    """Write best-effort telemetry without waiting behind long user transactions.

    The caller already treats telemetry as droppable. A 60-second SQLite busy
    timeout here used to stall every streaming Agent behind one writer.
    """
    now = _utc_now()

    async def write() -> None:
        async with db.aconnect(timeout=0.5) as con:
            await con.execute(
                "UPDATE session SET heartbeat_at=? WHERE session_id=?",
                (now, session_id),
            )
            await con.execute(
                "INSERT INTO session_events (session_id, event_type, data, created_at) VALUES (?, ?, ?, ?)",
                (session_id, event_type, json.dumps(data, ensure_ascii=False), now),
            )
            await con.commit()

    await aretry_on_locked(write, retries=2, base_delay=0.05)


def insert_session_event(db: ConversationDB, session_id: str, event_type: str, data: dict) -> None:
    """只插入一条 session_events（不刷心跳）。"""

    def write() -> None:
        with db.connect() as con:
            con.execute(
                "INSERT INTO session_events (session_id, event_type, data, created_at) VALUES (?, ?, ?, ?)",
                (session_id, event_type, json.dumps(data, ensure_ascii=False), _utc_now()),
            )
            con.commit()

    retry_on_locked(write)


async def ainsert_session_event(
    db: ConversationDB, session_id: str, event_type: str, data: dict
) -> None:
    """Async event insertion for API/Agent hot paths."""
    async def write() -> None:
        async with db.aconnect() as con:
            await con.execute(
                "INSERT INTO session_events (session_id, event_type, data, created_at) VALUES (?, ?, ?, ?)",
                (session_id, event_type, json.dumps(data, ensure_ascii=False), _utc_now()),
            )
            await con.commit()

    await aretry_on_locked(write)


# ---------------------------------------------------------------------------
# 只读查询 / 会话行兜底
# ---------------------------------------------------------------------------

def get_session_row(db: ConversationDB, session_id: str) -> dict | None:
    """Read-only: one session row's identity fields, or None."""
    with db.connect() as con:
        row = con.execute(
            "SELECT agent_id, agent_type, state FROM session WHERE session_id = ?",
            (session_id,),
        ).fetchone()
    if row is None:
        return None
    return {"agent_id": row[0], "agent_type": row[1], "state": row[2]}


def ensure_session_record(db: ConversationDB, session_id: str, agent_id: str | None) -> None:
    """Get-or-create the legacy session row backing artifact/event writes.

    runtime_v2 agents have no reAct-era session row, but ArtifactService and
    session_event writers refuse to work against a missing one.  Also makes
    sure the database itself is initialized: a bare ``connect()`` creates an
    empty file, so "file exists" never implies "tables exist".
    """
    if not db.migrate_if_needed():
        db.init()
    if get_session_row(db, session_id) is None:
        create_session_record(
            db,
            session_id=session_id,
            agent_id=agent_id,
            agent_type=None,
            parent_session_id=None,
            query="",
            created_at=_utc_now(),
        )


def list_session_events(db: ConversationDB, session_id: str, *, limit: int = 2000) -> list[dict]:
    """Raw session_events rows for one session, in insertion order."""
    with db.connect() as con:
        rows = con.execute(
            "SELECT id, event_type, data, created_at FROM session_events WHERE session_id = ? ORDER BY id LIMIT ?",
            (session_id, limit),
        ).fetchall()
    out = []
    for row in rows:
        try:
            data = json.loads(row[2])
        except (json.JSONDecodeError, TypeError):
            data = {}
        out.append({"id": row[0], "event_type": row[1], "data": data, "created_at": row[3]})
    return out
