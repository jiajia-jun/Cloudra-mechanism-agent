"""Session / 子任务 / 审批状态迁移的唯一写入入口。

所有对 ``session`` / ``subagent_requests`` / ``approvals`` / ``session_events``
表的写操作都必须经过本模块，调用方不再内联 SQL。连接统一由
:class:`cloudra.persistence.database.ConversationDB` 提供（WAL + busy_timeout），
短时写操作统一经 ``retry_on_locked`` / ``aretry_on_locked`` 重试。
进程管理（poll/kill）与消息格式化仍留在调用方。
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Optional

from cloudra.infra import events
from cloudra.persistence.database import ConversationDB, aretry_on_locked, retry_on_locked

# executor 收尾时 subagent_requests.state → session.state 的映射：
# 请求表的 done 对应会话表的 completed（reAct 成功路径落库的词表）。
_REQUEST_TO_SESSION_STATE = {
    "done": "completed",
    "cancelled": "cancelled",
    "failed": "failed",
}
_REQUEST_TO_EXIT_CODE = {
    "done": 0,
    "cancelled": None,
    "failed": 1,
}

# update_session_fields 允许写入的列（键全部来自内部代码，白名单兜底防注入）。
_SESSION_WRITABLE_COLUMNS = frozenset({
    "state", "result", "error", "pid", "worker_id",
    "started_at", "heartbeat_at", "finished_at", "exit_code",
})


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _conv_id(db: ConversationDB) -> str:
    """从 ConversationDB 反推 conversation_id（兼容 from_path 构造）。"""
    if db.conversation_id:
        return db.conversation_id
    try:
        return Path(db.path).parent.parent.name
    except Exception:
        return "default"


def _emit(kind: str, db: ConversationDB, **payload: Any) -> None:
    """同步事件投递：失败静默，绝不能阻塞写库。"""
    try:
        events.emit(_conv_id(db), kind, **payload)
    except Exception:
        pass


async def _aemit(kind: str, db: ConversationDB, **payload: Any) -> None:
    """Deliver locally and enqueue bounded network broadcast before returning."""
    try:
        await _deliver_and_broadcast(_conv_id(db), kind, payload)
    except Exception:
        pass


async def _deliver_and_broadcast(conv_id: str, kind: str, payload: dict) -> None:
    try:
        await events.aemit(conv_id, kind, **payload)
    except Exception:
        pass


def _emit_session_state(db: ConversationDB, session_id: str, state: str, **extra: Any) -> None:
    _touch_conversation_meta(db)
    _emit("session_state", db, session_id=session_id, state=state, **extra)


async def _aemit_session_state(db: ConversationDB, session_id: str, state: str, **extra: Any) -> None:
    _touch_conversation_meta(db)
    await _aemit("session_state", db, session_id=session_id, state=state, **extra)


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


def _emit_task_finished(
    db: ConversationDB,
    *,
    task_id: int,
    kind: str,
    state: str,
    session_id: str | None = None,
) -> None:
    # 用 task_kind 作为子类型键，避免与 IPC 事件名 kind 冲突
    _emit("task_finished", db, task_id=task_id, task_kind=kind, state=state, session_id=session_id)


async def _aemit_task_finished(
    db: ConversationDB,
    *,
    task_id: int,
    kind: str,
    state: str,
    session_id: str | None = None,
) -> None:
    await _aemit("task_finished", db, task_id=task_id, task_kind=kind, state=state, session_id=session_id)


def sanitize_db_text(text: str) -> str:
    r"""清理字符串中的孤立代理符（surrogate），避免写库/打印时 UTF-8 编码失败。

    终端（如 WSL 中粘贴 GBK 编码的中文）会把无法按 UTF-8 解码的字节以
    surrogateescape 保留为 \udcXX；sqlite3 和 stdout 的严格 UTF-8 编码会
    拒绝这些字符（UnicodeEncodeError: surrogates not allowed）。
    统一替换为 '?'，保证审批等写库路径不被脏字节打死。
    """
    return text.encode("utf-8", errors="replace").decode("utf-8")


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
    _emit_session_state(db, session_id, "running")


# finalize_session / finalize_task 的 UPDATE 语句：
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
    _emit_session_state(db, session_id, state)


async def afinalize_session(
    db: ConversationDB,
    session_id: str,
    state: str,
    *,
    result: Optional[str] = None,
    error: Optional[str] = None,
) -> None:
    """落库 Session 终态（异步），语义同 :func:`finalize_session`。"""

    async def write() -> None:
        async with db.aconnect() as con:
            await con.execute(_FINALIZE_SESSION_SQL, (state, result, error, _utc_now(), session_id))
            await con.commit()

    await aretry_on_locked(write)
    await _aemit_session_state(db, session_id, state)


def update_session_fields(db: ConversationDB, session_id: str, values: dict) -> None:
    """通用 Session 字段更新（心跳、cancel_requested、interrupted 等）。"""
    if not values:
        return
    unknown = set(values) - _SESSION_WRITABLE_COLUMNS
    if unknown:
        raise ValueError(f"不允许写入的 session 列: {sorted(unknown)}")
    assignments = ", ".join(f"{name} = ?" for name in values)

    def write() -> None:
        with db.connect() as con:
            con.execute(
                f"UPDATE session SET {assignments} WHERE session_id = ?",
                (*values.values(), session_id),
            )
            con.commit()

    retry_on_locked(write)
    state = values.get("state")
    if state:
        _emit_session_state(db, session_id, state)
        if state == "cancel_requested":
            _emit("cancel_requested", db, session_id=session_id)


def transition_session_state(
    db: ConversationDB,
    session_id: str,
    *,
    expected: set[str],
    target: str,
) -> bool:
    """Compare-and-set a non-terminal Session state without clobbering cancel."""

    if not expected:
        return False
    placeholders = ",".join("?" for _ in expected)
    expected_values = sorted(expected)

    def write() -> bool:
        with db.connect() as con:
            cursor = con.execute(
                f"""UPDATE session SET state=?
                WHERE session_id=? AND state IN ({placeholders})""",
                (target, session_id, *expected_values),
            )
            con.commit()
            return cursor.rowcount == 1

    changed = retry_on_locked(write)
    if changed:
        _emit_session_state(db, session_id, target)
    return changed


async def atransition_session_state(
    db: ConversationDB,
    session_id: str,
    *,
    expected: set[str],
    target: str,
) -> bool:
    """Async compare-and-set counterpart without blocking the caller's loop."""
    if not expected:
        return False
    placeholders = ",".join("?" for _ in expected)
    expected_values = sorted(expected)

    async def write() -> bool:
        async with db.aconnect() as con:
            cursor = await con.execute(
                f"""UPDATE session SET state=?
                WHERE session_id=? AND state IN ({placeholders})""",
                (target, session_id, *expected_values),
            )
            await con.commit()
            return cursor.rowcount == 1

    changed = await aretry_on_locked(write)
    if changed:
        await _aemit_session_state(db, session_id, target)
    return changed


async def asuspend_session(
    db: ConversationDB,
    session_id: str,
    *,
    result: Optional[str] = None,
) -> None:
    """挂起：后台（子任务/计算/提醒）未排空时的 stop。

    非终态：写 ``waiting``、保留/更新 result 预览，但绝不写 ``finished_at``，
    也不进 Case Bank。唤醒时由 :func:`aresume_session` 转回 running。
    """

    async def write() -> None:
        async with db.aconnect() as con:
            await con.execute(
                "UPDATE session SET state='waiting', "
                "result=COALESCE(?, result), finished_at=NULL "
                "WHERE session_id=?",
                (result, session_id),
            )
            await con.commit()

    await aretry_on_locked(write)
    await _aemit_session_state(db, session_id, "waiting")


async def aresume_session(db: ConversationDB, session_id: str) -> bool:
    """复活语义：被定时提醒/外部事件重新唤醒时，把挂起/误留的终态转回 running。

    stop 在后台未排空时落库 ``waiting``；历史路径也可能误写 ``completed``。
    runner/executor 再次调用 run() 续跑前必须撤回，否则 UI 会显示"已完成"
    而模型仍在工作。只复活 waiting/completed——cancelled / failed 是用户或
    系统的明确终态，绝不被唤醒覆盖。
    """

    async def write() -> bool:
        async with db.aconnect() as con:
            cursor = await con.execute(
                "UPDATE session SET state='running', finished_at=NULL "
                "WHERE session_id=? AND state IN ('completed', 'waiting')",
                (session_id,),
            )
            await con.commit()
            return cursor.rowcount == 1

    changed = await aretry_on_locked(write)
    if changed:
        await _aemit_session_state(db, session_id, "running")
    return changed


async def aheartbeat(db: ConversationDB, session_id: str) -> None:
    """刷新 Session 心跳（异步）。"""
    now = _utc_now()

    async def write() -> None:
        async with db.aconnect() as con:
            await con.execute(
                "UPDATE session SET heartbeat_at=? WHERE session_id=?",
                (now, session_id),
            )
            await con.commit()

    await aretry_on_locked(write)


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
    await _aemit("session_event", db, session_id=session_id, event_type=event_type, data=data)


def insert_session_event(db: ConversationDB, session_id: str, event_type: str, data: dict) -> None:
    """只插入一条 session_events（不刷心跳；SessionRunner 状态事件用）。"""

    def write() -> None:
        with db.connect() as con:
            con.execute(
                "INSERT INTO session_events (session_id, event_type, data, created_at) VALUES (?, ?, ?, ?)",
                (session_id, event_type, json.dumps(data, ensure_ascii=False), _utc_now()),
            )
            con.commit()

    retry_on_locked(write)
    _emit("session_event", db, session_id=session_id, event_type=event_type, data=data)


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
    await _aemit("session_event", db, session_id=session_id, event_type=event_type, data=data)


# ---------------------------------------------------------------------------
# 只读查询（v2 API 的 legacy 子 Agent 视图）
# ---------------------------------------------------------------------------

def list_subagent_sessions(db: ConversationDB, *, limit: int = 200) -> list[dict]:
    """Follower/supervisor sessions of this conversation, newest first."""
    with db.connect() as con:
        rows = con.execute(
            """
            SELECT session_id, agent_id, agent_type, parent_session_id, query,
                   state, result, error, created_at, finished_at, orchestration_mode
            FROM session
            WHERE agent_type IN ('follower', 'supervisor')
            ORDER BY created_at DESC LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [
        {
            "session_id": row[0],
            "agent_id": row[1],
            "agent_type": row[2],
            "parent_session_id": row[3],
            "query": (row[4] or "")[:200],
            "state": row[5],
            "has_result": bool(row[6]),
            "error": row[7],
            "created_at": row[8],
            "finished_at": row[9],
            "orchestration_mode": row[10],
        }
        for row in rows
    ]


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


# ---------------------------------------------------------------------------
# 子任务（subagent_requests）生命周期
# ---------------------------------------------------------------------------

def _finalize_task_params(status: str, error: Optional[str], now: str) -> tuple:
    """统一收尾的 SQL 参数。

    与历史实现的三处 deliberate unification：
    1. 收尾永远写 session.state（done 映射为 completed，不再假定 reAct 已写）；
    2. finished_at 永远 COALESCE（首个终态时间戳生效，failed 不再无条件覆盖）；
    3. error 仅在提供时写入（COALESCE 保留旧值）。
    """
    return (
        _REQUEST_TO_SESSION_STATE[status],
        error,
        _REQUEST_TO_EXIT_CODE[status],
        now,
    )


_FINALIZE_TASK_SESSION_SQL = """UPDATE session SET state=?,
    error=COALESCE(?, error),
    exit_code=COALESCE(?, exit_code),
    finished_at=COALESCE(finished_at, ?)
    WHERE session_id=?"""


def finalize_task(
    db: ConversationDB,
    task_id: int,
    session_id: str,
    status: str,
    *,
    error: Optional[str] = None,
    retries: Optional[int] = None,
) -> None:
    """统一收尾（同步）：同时落库 subagent_requests 与 session 的终态。"""
    now = _utc_now()

    def write() -> None:
        with db.connect() as con:
            con.execute("UPDATE subagent_requests SET state=? WHERE id=?", (status, task_id))
            con.execute(_FINALIZE_TASK_SESSION_SQL, (*_finalize_task_params(status, error, now), session_id))
            con.commit()

    if retries is None:
        retry_on_locked(write)
    else:
        retry_on_locked(write, retries=retries)
    _emit_task_finished(db, task_id=task_id, kind="subagent", state=status, session_id=session_id)
    _emit_session_state(db, session_id, _REQUEST_TO_SESSION_STATE.get(status, status))


async def afinalize_task(
    db: ConversationDB,
    task_id: int,
    session_id: str,
    status: str,
    *,
    error: Optional[str] = None,
) -> None:
    """统一收尾（异步），语义同 :func:`finalize_task`。"""
    now = _utc_now()

    async def write() -> None:
        async with db.aconnect() as con:
            await con.execute("UPDATE subagent_requests SET state=? WHERE id=?", (status, task_id))
            await con.execute(_FINALIZE_TASK_SESSION_SQL, (*_finalize_task_params(status, error, now), session_id))
            await con.commit()

    await aretry_on_locked(write)
    await _aemit_task_finished(db, task_id=task_id, kind="subagent", state=status, session_id=session_id)
    await _aemit_session_state(db, session_id, _REQUEST_TO_SESSION_STATE.get(status, status))


async def acreate_subagent_request(
    db: ConversationDB,
    *,
    state: str,
    payload: dict,
    conversation_id: str,
    parent_session_id: Optional[str],
    session_id_fn: Callable[[int], str],
) -> tuple[int, str, dict]:
    """插入子任务请求并回写 session_id（单事务）。

    先插入记录拿 task_id，再用 ``session_id_fn(task_id)`` 生成 session_id
    并把它写回 payload 与专属列。返回 (task_id, session_id, 最终 payload)。
    """

    async def write() -> tuple[int, str, dict]:
        async with db.aconnect() as con:
            cur = await con.execute(
                "INSERT INTO subagent_requests (state, input_data, conversation_id) VALUES (?, ?, ?)",
                (state, json.dumps(payload), conversation_id),
            )
            task_id = cur.lastrowid
            session_id = session_id_fn(task_id)
            final_payload = dict(payload, session_id=session_id)
            await con.execute(
                """UPDATE subagent_requests
                SET input_data = ?, session_id = ?, parent_session_id = ? WHERE id = ?""",
                (json.dumps(final_payload), session_id, parent_session_id, task_id),
            )
            await con.commit()
            return task_id, session_id, final_payload

    task_id, session_id, final_payload = await aretry_on_locked(write)
    if state == "ready":
        await _aemit(
            "subagent_request_ready",
            db,
            task_id=task_id,
            session_id=session_id,
            parent_session_id=parent_session_id,
        )
    return task_id, session_id, final_payload


def claim_ready_request(
    db: ConversationDB,
    *,
    worker_id: str = "legacy-worker",
    lease_seconds: int = 60,
    max_attempts: int = 3,
) -> Optional[tuple[int, Any]]:
    """原子抢占一个 ready 子任务（乐观锁），返回 (id, input_data)；没有则返回 None。

    空闲降级：先只读探测，没有 ready 任务就不发起写事务，
    避免空转时每秒的 UPDATE...RETURNING 也抢占写锁。
    """

    def write() -> Optional[tuple[int, Any]]:
        now = time.time()
        expires = now + max(10, int(lease_seconds))
        with db.connect() as con:
            cur = con.cursor()
            cur.execute(
                """SELECT id FROM subagent_requests
                WHERE (state='ready' OR (state='running' AND lease_expires_at<?))
                AND COALESCE(attempt_count, 0) < ? ORDER BY id LIMIT 1""",
                (now, max_attempts),
            )
            if cur.fetchone() is None:
                con.rollback()
                return None
            # 原子操作：先尝试把状态从 ready 改为 running，并返回被修改的 id 和 input_data；
            # 如果别的线程已经改了，这个 UPDATE 就会返回空，从而避免冲突。
            cur.execute("""
                UPDATE subagent_requests
                SET state='running', lease_owner=?, lease_expires_at=?,
                    attempt_count=COALESCE(attempt_count, 0)+1
                WHERE id IN (
                    SELECT id FROM subagent_requests
                    WHERE (state='ready' OR (state='running' AND lease_expires_at<?))
                    AND COALESCE(attempt_count, 0) < ? ORDER BY id LIMIT 1
                )
                RETURNING id, input_data
            """, (worker_id, expires, now, max_attempts))
            claimed = cur.fetchone()
            if claimed:
                con.commit()  # 确认修改
            else:
                con.rollback()
            return claimed

    return retry_on_locked(write)


def claim_ready_compute_job(
    db: ConversationDB,
    *,
    worker_id: str,
    lease_seconds: int = 60,
    max_attempts: int = 3,
) -> Optional[int]:
    """Atomically claim ready or lease-expired compute work."""
    def write() -> Optional[int]:
        now = time.time()
        expires = now + max(10, int(lease_seconds))
        with db.connect() as con:
            peek = con.execute(
                """SELECT id FROM compute_jobs
                WHERE (state='ready' OR (state='running' AND lease_expires_at<?))
                AND COALESCE(attempt_count, 0) < ? ORDER BY id LIMIT 1""",
                (now, max_attempts),
            ).fetchone()
            if peek is None:
                con.rollback()
                return None
            row = con.execute(
                """UPDATE compute_jobs SET state='running', lease_owner=?,
                lease_expires_at=?, attempt_count=COALESCE(attempt_count, 0)+1,
                start_timestamp=CASE WHEN start_timestamp IS NULL OR start_timestamp<=0
                    THEN ? ELSE start_timestamp END
                WHERE id IN (SELECT id FROM compute_jobs
                    WHERE (state='ready' OR (state='running' AND lease_expires_at<?))
                    AND COALESCE(attempt_count, 0) < ? ORDER BY id LIMIT 1)
                RETURNING id""",
                (worker_id, expires, now, now, max_attempts),
            ).fetchone()
            if row:
                con.commit()
            else:
                con.rollback()
            return int(row[0]) if row else None

    return retry_on_locked(write)


def renew_task_lease(
    db: ConversationDB,
    *,
    table: str,
    task_id: int,
    worker_id: str,
    lease_seconds: int = 60,
) -> bool:
    """Renew only the current owner's live lease; stale owners fail closed."""
    if table not in {"subagent_requests", "compute_jobs"}:
        raise ValueError("unsupported lease table")
    renewed = False

    def write() -> None:
        nonlocal renewed
        with db.connect() as con:
            cursor = con.execute(
                f"""UPDATE {table} SET lease_expires_at=?
                WHERE id=? AND state='running' AND lease_owner=?""",
                (time.time() + max(10, int(lease_seconds)), task_id, worker_id),
            )
            renewed = cursor.rowcount == 1
            con.commit()

    retry_on_locked(write)
    return renewed


def reap_exhausted_leases(
    db: ConversationDB,
    *,
    max_attempts: int = 3,
) -> tuple[list[int], list[int]]:
    """Fail expired work that consumed its retry budget and emit terminal events."""
    now = time.time()
    subagent_ids: list[int] = []
    compute_ids: list[int] = []
    session_ids: list[str] = []

    def write() -> None:
        with db.connect() as con:
            subagent_rows = con.execute(
                """SELECT id, session_id FROM subagent_requests
                WHERE state='running' AND lease_expires_at<?
                AND COALESCE(attempt_count, 0)>=?""",
                (now, max_attempts),
            ).fetchall()
            compute_rows = con.execute(
                """SELECT id FROM compute_jobs WHERE state='running'
                AND lease_expires_at<? AND COALESCE(attempt_count, 0)>=?""",
                (now, max_attempts),
            ).fetchall()
            subagent_ids.extend(int(row[0]) for row in subagent_rows)
            session_ids.extend(str(row[1]) for row in subagent_rows if row[1])
            compute_ids.extend(int(row[0]) for row in compute_rows)
            con.execute(
                """UPDATE subagent_requests SET state='failed'
                WHERE state='running' AND lease_expires_at<?
                AND COALESCE(attempt_count, 0)>=?""",
                (now, max_attempts),
            )
            con.execute(
                """UPDATE compute_jobs SET state='failed', end_timestamp=?,
                last_error='worker lease retry budget exhausted'
                WHERE state='running' AND lease_expires_at<?
                AND COALESCE(attempt_count, 0)>=?""",
                (now, now, max_attempts),
            )
            for session_id in session_ids:
                con.execute(
                    """UPDATE session SET state='failed', finished_at=?,
                    error=COALESCE(error, 'worker lease retry budget exhausted')
                    WHERE session_id=? AND state NOT IN
                    ('completed','failed','cancelled','killed','interrupted')""",
                    (_utc_now(), session_id),
                )
            con.commit()

    retry_on_locked(write)
    for task_id in subagent_ids:
        _emit_task_finished(db, task_id=task_id, kind="subagent", state="failed")
    for task_id in compute_ids:
        _emit_task_finished(db, task_id=task_id, kind="compute", state="failed")
    for session_id in session_ids:
        _emit_session_state(db, session_id, "failed")
    return subagent_ids, compute_ids


def fail_request(db: ConversationDB, request_id: int) -> None:
    """把子任务请求标记为 failed（如 executor 进程刚启动就崩溃的回滚）。"""

    def write() -> None:
        with db.connect() as con:
            con.execute("UPDATE subagent_requests SET state = 'failed' WHERE id = ?", (request_id,))
            con.commit()

    retry_on_locked(write)
    # 尝试获取 session_id 用于事件投递
    try:
        with db.connect() as con:
            row = con.execute(
                "SELECT session_id FROM subagent_requests WHERE id=?", (request_id,)
            ).fetchone()
        session_id = row[0] if row else None
    except Exception:
        session_id = None
    _emit_task_finished(db, task_id=request_id, kind="subagent", state="failed", session_id=session_id)


def reap_exited_requests(db: ConversationDB, request_ids: list[int]) -> list[int]:
    """回收已退出 executor 进程对应的 running 请求，标记 failed；返回被回收的 id 列表。

    executor 正常结束时会自行把 subagent_requests 写成 done/failed；
    这里只处理进程非正常死亡（如被 kill）留下的 'running' 残迹。
    统一的语义：只有请求行确实被回收（running → failed）时，才连带把其
    running Session 标为 failed——请求未被回收说明它已自报终态或不归这里管，
    此时不动 Session（历史实现不看请求回收结果、无条件标 Session，已修正）。
    """
    if not request_ids:
        return []
    now = _utc_now()
    reaped: list[int] = []
    reaped_sessions: list[str] = []

    def write() -> None:
        with db.connect() as con:
            cur = con.cursor()
            for rid in request_ids:
                cur.execute(
                    "SELECT session_id FROM subagent_requests WHERE id=? AND state='running'",
                    (rid,),
                )
                row = cur.fetchone()
                session_id = row[0] if row else None
                cur.execute(
                    "UPDATE subagent_requests SET state='failed' WHERE id=? AND state='running'",
                    (rid,),
                )
                if not cur.rowcount:
                    continue
                reaped.append(rid)
                if session_id:
                    reaped_sessions.append(session_id)
                cur.execute(
                    """UPDATE session SET state='failed',
                    error=COALESCE(error, 'executor process exited unexpectedly'), finished_at=?
                    WHERE state='running' AND session_id=?""",
                    (now, session_id),
                )
            con.commit()

    retry_on_locked(write)
    for rid in reaped:
        _emit_task_finished(db, task_id=rid, kind="subagent", state="failed")
    for session_id in set(reaped_sessions):
        _emit_session_state(db, session_id, "failed")
    return reaped


def recover_stale(db: ConversationDB, *, cutoff: str) -> int:
    """把失去心跳或未被认领的 Session 标为 interrupted。

    返回被标记 interrupted 的 Session 数。``cutoff`` 为心跳过期阈值（ISO 时间串）。
    覆盖 running/waiting/cancel_requested/waiting_for_*：waiting（挂起等唤醒）
    与 cancel_requested（取消半途）的属主进程死后同样会成为永久僵尸，
    活体由各自的心跳保活（service 侧 5s 心跳；子 agent executor 进程内
    心跳任务），心跳过期才回收，不会误杀合法的挂起等待。
    """
    now = _utc_now()
    changed = 0

    with db.connect() as con:
        stale_sessions = [
            row[0] for row in con.execute(
                """SELECT session_id FROM session
                WHERE (
                    state IN ('running', 'waiting', 'cancel_requested',
                    'waiting_for_user', 'waiting_for_device', 'waiting_for_approval')
                    AND (heartbeat_at IS NULL OR heartbeat_at < ?)
                ) OR (
                    state='queued'
                    AND (created_at IS NULL OR created_at < ?)
                )""",
                (cutoff, cutoff),
            ).fetchall()
        ]
        stale_compute_jobs = [
            row[0] for row in con.execute(
                """SELECT id FROM compute_jobs
                WHERE state IN ('ready', 'running') AND session_id IN (
                    SELECT session_id FROM session WHERE (
                        state IN ('running', 'waiting', 'cancel_requested',
                        'waiting_for_user', 'waiting_for_device', 'waiting_for_approval')
                        AND (heartbeat_at IS NULL OR heartbeat_at < ?)
                    ) OR (
                        state='queued'
                        AND (created_at IS NULL OR created_at < ?)
                    )
                )""",
                (cutoff, cutoff),
            ).fetchall()
        ]
        orphan_requests = [
            row[0] for row in con.execute(
                """SELECT id FROM subagent_requests WHERE state='running' AND (
                    session_id IS NULL
                    OR session_id NOT IN (SELECT session_id FROM session)
                    OR session_id IN (
                        SELECT session_id FROM session
                        WHERE state NOT IN ('running', 'waiting_for_user',
                        'waiting_for_device', 'waiting_for_approval')
                        OR heartbeat_at IS NULL OR heartbeat_at < ?
                    )
                )""",
                (cutoff,),
            ).fetchall()
        ]

    def write() -> None:
        nonlocal changed
        with db.connect() as con:
            cursor = con.execute(
                """UPDATE session SET state='interrupted',
                error=COALESCE(error, 'worker heartbeat expired'), finished_at=?
                WHERE (
                    state IN ('running', 'waiting', 'cancel_requested',
                    'waiting_for_user', 'waiting_for_device', 'waiting_for_approval')
                    AND (heartbeat_at IS NULL OR heartbeat_at < ?)
                ) OR (
                    state='queued'
                    AND (created_at IS NULL OR created_at < ?)
                )""",
                (now, cutoff, cutoff),
            )
            changed = cursor.rowcount
            con.execute(
                """UPDATE subagent_requests SET state='failed'
                WHERE state='running' AND (
                    session_id IS NULL
                    OR session_id NOT IN (SELECT session_id FROM session)
                    OR session_id IN (
                        SELECT session_id FROM session
                        WHERE state NOT IN ('running', 'waiting_for_user',
                        'waiting_for_device', 'waiting_for_approval')
                        OR heartbeat_at IS NULL OR heartbeat_at < ?
                    )
                )""",
                (cutoff,),
            )
            con.execute(
                """UPDATE compute_jobs SET state='failed', end_timestamp=?,
                last_error=COALESCE(last_error, 'parent session heartbeat expired')
                WHERE state IN ('ready', 'running') AND session_id IN (
                    SELECT session_id FROM session WHERE state='interrupted'
                    AND finished_at=?
                )""",
                (time.time(), now),
            )
            con.commit()

    retry_on_locked(write)
    for session_id in stale_sessions:
        _emit_session_state(db, session_id, "interrupted")
    for rid in orphan_requests:
        _emit_task_finished(db, task_id=rid, kind="subagent", state="failed")
    for job_id in stale_compute_jobs:
        _emit_task_finished(db, task_id=job_id, kind="compute", state="failed")
    return changed


def cancel_descendants(
    db: ConversationDB,
    parent_session_id: str,
    terminate: Callable[[int], None],
) -> None:
    """级联打断父 Session 派生的子 Session、子 Agent 请求和计算任务（单事务）。

    ``terminate`` 回调负责进程管理（如 SIGTERM），由调用方提供；
    对每个子 Session 先置 cancel_requested 给子进程自行退出的机会，再落 cancelled。
    """
    now = _utc_now()

    with db.connect() as con:
        children = con.execute(
            """SELECT session_id, pid FROM session
            WHERE parent_session_id=? AND state IN
            ('queued', 'running', 'waiting_for_user',
             'waiting_for_approval', 'waiting_for_device',
             'cancel_requested')""",
            (parent_session_id,),
        ).fetchall()
    children_ids = [child_id for child_id, _pid in children]

    def write() -> None:
        with db.connect() as con:
            for child_id, pid in children:
                con.execute(
                    """UPDATE session SET state='cancel_requested'
                    WHERE session_id=? AND state IN
                    ('queued', 'running', 'waiting_for_user',
                     'waiting_for_approval', 'waiting_for_device')""",
                    (child_id,),
                )
                if pid:
                    terminate(pid)
                con.execute(
                    """UPDATE session SET state='cancelled', finished_at=?
                    WHERE session_id=? AND state NOT IN ('cancelled', 'failed', 'completed')""",
                    (now, child_id),
                )
            con.execute(
                """UPDATE subagent_requests SET state='cancelled'
                WHERE parent_session_id=? AND state IN ('ready', 'running')""",
                (parent_session_id,),
            )
            con.execute(
                """UPDATE compute_jobs SET state='cancelled'
                WHERE session_id=? AND state IN ('ready', 'running')""",
                (parent_session_id,),
            )
            con.commit()

    retry_on_locked(write)
    for child_id in children_ids:
        _emit("cancel_requested", db, session_id=child_id)
        _emit_session_state(db, child_id, "cancel_requested")
        _emit_session_state(db, child_id, "cancelled")


# ---------------------------------------------------------------------------
# API 侧 SessionRunner 的 Session 写入
# ---------------------------------------------------------------------------

def insert_queued_session(
    db: ConversationDB,
    *,
    session_id: str,
    agent_id: str,
    agent_type: str,
    query: str,
    node_id: str | None = None,
    workspace_id: str | None = None,
    working_directory: str | None = None,
    orchestration_mode: str = "standard",
    orchestration_config: dict | None = None,
) -> None:
    """SessionRunner.submit：先入队一条 queued Session。"""

    from cloudra.dag.models import normalize_orchestration_mode

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
                """INSERT INTO session
                (session_id, agent_id, agent_type, query, state, created_at,
                 node_id, workspace_id, working_directory,
                 orchestration_mode, orchestration_config)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    session_id, agent_id, agent_type, query, "queued", _utc_now(),
                    node_id, workspace_id, working_directory,
                    normalized_mode, serialized_config,
                ),
            )
            con.commit()

    retry_on_locked(write)
    _emit_session_state(db, session_id, "queued")


def claim_session(db: ConversationDB, session_id: str, *, pid: int, worker_id: str) -> bool:
    """把 queued Session 原子认领为 running；认领成功返回 True。"""
    now = _utc_now()
    claimed = False

    def write() -> None:
        nonlocal claimed
        with db.connect() as con:
            cursor = con.execute(
                """UPDATE session SET state='running', pid=?, worker_id=?,
                started_at=COALESCE(started_at, ?), heartbeat_at=?
                WHERE session_id=? AND state='queued'""",
                (pid, worker_id, now, now, session_id),
            )
            con.commit()
            claimed = cursor.rowcount == 1

    retry_on_locked(write)
    if claimed:
        _emit_session_state(db, session_id, "running")
    return claimed


# ---------------------------------------------------------------------------
# 审批（approvals）
# ---------------------------------------------------------------------------

def insert_approval(
    db: ConversationDB,
    session_id: str,
    details: str,
    agent_name: Optional[str] = None,
    *,
    tool_name: str = "",
    normalized_arguments: dict | None = None,
    risk_summary: str = "",
    candidate_diff: str = "",
    ttl_seconds: int = 86_400,
) -> int:
    """插入一条 pending 审批记录，返回 approval_id；details 写库前做孤立代理符净化。"""

    requested_at = datetime.now(timezone.utc)
    expires_at = requested_at + timedelta(
        seconds=min(max(int(ttl_seconds), 1), 604_800)
    )
    safe_details = sanitize_db_text(details)
    safe_arguments = sanitize_db_text(
        json.dumps(normalized_arguments or {}, ensure_ascii=False, sort_keys=True)
    )
    safe_risk = sanitize_db_text(risk_summary)
    safe_diff = sanitize_db_text(candidate_diff)

    def write() -> int:
        with db.connect() as con:
            cur = con.execute(
                """INSERT INTO approvals
                (session_id, agent_name, details, state, tool_name,
                 normalized_arguments, risk_summary, candidate_diff,
                 requested_at, expires_at)
                VALUES (?, ?, ?, 'pending', ?, ?, ?, ?, ?, ?)""",
                (
                    session_id,
                    agent_name,
                    safe_details,
                    tool_name,
                    safe_arguments,
                    safe_risk,
                    safe_diff,
                    requested_at.isoformat(),
                    expires_at.isoformat(),
                ),
            )
            con.commit()
            return cur.lastrowid

    approval_id = retry_on_locked(write)
    payload = {
        "approval_id": approval_id,
        "agent_name": agent_name,
        "details": safe_details,
        "tool_name": tool_name,
        "normalized_arguments": normalized_arguments or {},
        "risk_summary": safe_risk,
        "candidate_diff": safe_diff,
        "requested_at": requested_at.isoformat(),
        "expires_at": expires_at.isoformat(),
    }
    _emit(
        "approval_pending",
        db,
        session_id=session_id,
        **payload,
    )
    insert_session_event(
        db,
        session_id,
        "approval_pending",
        payload,
    )
    return approval_id


async def ainsert_approval(
    db: ConversationDB,
    session_id: str,
    details: str,
    agent_name: Optional[str] = None,
    *,
    tool_name: str = "",
    normalized_arguments: dict | None = None,
    risk_summary: str = "",
    candidate_diff: str = "",
    ttl_seconds: int = 86_400,
) -> int:
    """异步插入一条 pending 审批记录，返回 approval_id；语义同 :func:`insert_approval`。"""

    requested_at = datetime.now(timezone.utc)
    expires_at = requested_at + timedelta(
        seconds=min(max(int(ttl_seconds), 1), 604_800)
    )
    safe_details = sanitize_db_text(details)
    safe_arguments = sanitize_db_text(
        json.dumps(normalized_arguments or {}, ensure_ascii=False, sort_keys=True)
    )
    safe_risk = sanitize_db_text(risk_summary)
    safe_diff = sanitize_db_text(candidate_diff)

    async def write() -> int:
        async with db.aconnect() as con:
            cur = await con.execute(
                """INSERT INTO approvals
                (session_id, agent_name, details, state, tool_name,
                 normalized_arguments, risk_summary, candidate_diff,
                 requested_at, expires_at)
                VALUES (?, ?, ?, 'pending', ?, ?, ?, ?, ?, ?)""",
                (
                    session_id,
                    agent_name,
                    safe_details,
                    tool_name,
                    safe_arguments,
                    safe_risk,
                    safe_diff,
                    requested_at.isoformat(),
                    expires_at.isoformat(),
                ),
            )
            await con.commit()
            return cur.lastrowid

    approval_id = await aretry_on_locked(write)
    payload = {
        "approval_id": approval_id,
        "agent_name": agent_name,
        "details": safe_details,
        "tool_name": tool_name,
        "normalized_arguments": normalized_arguments or {},
        "risk_summary": safe_risk,
        "candidate_diff": safe_diff,
        "requested_at": requested_at.isoformat(),
        "expires_at": expires_at.isoformat(),
    }
    await _aemit(
        "approval_pending",
        db,
        session_id=session_id,
        **payload,
    )
    await ainsert_session_event(
        db,
        session_id,
        "approval_pending",
        payload,
    )
    return approval_id


def list_pending_approvals(db: ConversationDB) -> list[tuple[int, str, str, str]]:
    """读取指定数据库中所有 pending 状态的审批记录。

    返回 ``(id, session_id, agent_name, details)`` 元组列表。
    """

    expire_pending_approvals(db)

    def read() -> list:
        with db.connect() as con:
            cur = con.execute(
                "SELECT id, session_id, agent_name, details FROM approvals WHERE state = 'pending'"
            )
            return cur.fetchall()

    return retry_on_locked(read)


def list_pending_approval_records(db: ConversationDB) -> list[dict]:
    """返回远程客户端需要的结构化审批记录。"""

    expire_pending_approvals(db)

    def read() -> list:
        with db.connect() as con:
            return con.execute(
                """SELECT id, session_id, agent_name, details, tool_name,
                normalized_arguments, risk_summary, candidate_diff,
                requested_at, expires_at FROM approvals
                WHERE state='pending' ORDER BY id"""
            ).fetchall()

    records = []
    for row in retry_on_locked(read):
        try:
            arguments = json.loads(row[5] or "{}")
        except (TypeError, ValueError):
            arguments = {}
        records.append(
            {
                "id": row[0],
                "approval_id": row[0],
                "session_id": row[1],
                "agent_name": row[2],
                "details": row[3],
                "tool_name": row[4] or "",
                "normalized_arguments": (
                    arguments if isinstance(arguments, dict) else {}
                ),
                "risk_summary": row[6] or "",
                "candidate_diff": row[7] or "",
                "requested_at": row[8],
                "expires_at": row[9],
                "state": "pending",
            }
        )
    return records


def expire_pending_approvals(
    db: ConversationDB,
    *,
    approval_id: int | None = None,
) -> list[int]:
    """将到期审批持久化为 expired，并产生可恢复事件。"""

    now = _utc_now()

    def write() -> list[tuple[int, str]]:
        with db.connect() as con:
            query = (
                """SELECT id, session_id FROM approvals
                WHERE state='pending' AND expires_at IS NOT NULL
                AND expires_at<=?"""
            )
            params: list[Any] = [now]
            if approval_id is not None:
                query += " AND id=?"
                params.append(approval_id)
            rows = con.execute(query, params).fetchall()
            expired = []
            for row_id, session_id in rows:
                cursor = con.execute(
                    """UPDATE approvals SET state='expired', decided_at=?
                    WHERE id=? AND state='pending'""",
                    (now, row_id),
                )
                if cursor.rowcount == 1:
                    expired.append((row_id, session_id))
            con.commit()
            return expired

    expired = retry_on_locked(write)
    for row_id, session_id in expired:
        _emit(
            "approval_expired",
            db,
            approval_id=row_id,
            session_id=session_id,
        )
        if session_id:
            insert_session_event(
                db,
                session_id,
                "approval_expired",
                {"approval_id": row_id, "state": "expired"},
            )
    return [row_id for row_id, _ in expired]


async def aexpire_pending_approvals(
    db: ConversationDB,
    *,
    approval_id: int | None = None,
) -> list[int]:
    now = _utc_now()

    async def write() -> list[tuple[int, str]]:
        async with db.aconnect() as con:
            query = (
                """SELECT id, session_id FROM approvals
                WHERE state='pending' AND expires_at IS NOT NULL
                AND expires_at<=?"""
            )
            params: list[Any] = [now]
            if approval_id is not None:
                query += " AND id=?"
                params.append(approval_id)
            cursor = await con.execute(query, params)
            rows = await cursor.fetchall()
            expired = []
            for row_id, session_id in rows:
                cursor = await con.execute(
                    """UPDATE approvals SET state='expired', decided_at=?
                    WHERE id=? AND state='pending'""",
                    (now, row_id),
                )
                if cursor.rowcount == 1:
                    expired.append((row_id, session_id))
            await con.commit()
            return expired

    expired = await aretry_on_locked(write)
    for row_id, session_id in expired:
        await _aemit(
            "approval_expired",
            db,
            approval_id=row_id,
            session_id=session_id,
        )
        if session_id:
            await ainsert_session_event(
                db,
                session_id,
                "approval_expired",
                {"approval_id": row_id, "state": "expired"},
            )
    return [row_id for row_id, _ in expired]


async def alist_pending_approval_records(db: ConversationDB) -> list[dict]:
    """Async structured approval inbox used by HTTP/UI event loops."""
    await aexpire_pending_approvals(db)

    async def read() -> list:
        async with db.aconnect() as con:
            cursor = await con.execute(
                """SELECT id, session_id, agent_name, details, tool_name,
                normalized_arguments, risk_summary, candidate_diff,
                requested_at, expires_at FROM approvals
                WHERE state='pending' ORDER BY id"""
            )
            return await cursor.fetchall()

    rows = await aretry_on_locked(read)
    records = []
    for row in rows:
        try:
            arguments = json.loads(row[5] or "{}")
        except (TypeError, ValueError):
            arguments = {}
        records.append(
            {
                "id": row[0],
                "approval_id": row[0],
                "session_id": row[1],
                "agent_name": row[2],
                "details": row[3],
                "tool_name": row[4] or "",
                "normalized_arguments": arguments if isinstance(arguments, dict) else {},
                "risk_summary": row[6] or "",
                "candidate_diff": row[7] or "",
                "requested_at": row[8],
                "expires_at": row[9],
                "state": "pending",
            }
        )
    return records


async def aread_approval_status(db: ConversationDB, approval_id: int) -> Optional[tuple[str, str]]:
    """异步读取单条审批的 ``(state, denial_reason)``；不存在时返回 None。"""

    await aexpire_pending_approvals(db, approval_id=approval_id)

    async def read() -> Optional[tuple]:
        async with db.aconnect() as con:
            cur = await con.execute(
                "SELECT state, denial_reason FROM approvals WHERE id = ?", (approval_id,)
            )
            return await cur.fetchone()

    return await aretry_on_locked(read)


def decide_approval(
    db: ConversationDB,
    approval_id: int,
    state: str,
    denial_reason: str = "",
    *,
    decided_by: str = "local_user",
) -> bool:
    """写入审批决定（同步），仅当审批仍处于 pending 时生效。

    防止 CLI 与 Web/API 双通道同时审批时互相覆盖而不自知。
    denial_reason 写库前统一做孤立代理符净化。
    """

    if state not in {"approved", "denied"}:
        raise ValueError("无效的审批决定")
    expire_pending_approvals(db, approval_id=approval_id)
    decided_at = _utc_now()

    def write() -> bool:
        with db.connect() as con:
            cur = con.execute(
                """UPDATE approvals SET state=?, denial_reason=?,
                decided_by=?, decided_at=?
                WHERE id=? AND state='pending'""",
                (
                    state,
                    sanitize_db_text(denial_reason),
                    sanitize_db_text(decided_by),
                    decided_at,
                    approval_id,
                ),
            )
            con.commit()
            return cur.rowcount == 1

    updated = retry_on_locked(write)
    if updated:
        _emit(
            "approval_decided",
            db,
            approval_id=approval_id,
            state=state,
            decided_by=decided_by,
            decided_at=decided_at,
            denial_reason=sanitize_db_text(denial_reason),
        )
        with db.connect() as con:
            row = con.execute(
                "SELECT session_id FROM approvals WHERE id=?",
                (approval_id,),
            ).fetchone()
        if row and row[0]:
            insert_session_event(
                db,
                row[0],
                "approval_decided",
                {
                    "approval_id": approval_id,
                    "state": state,
                    "denial_reason": sanitize_db_text(denial_reason),
                    "decided_by": sanitize_db_text(decided_by),
                    "decided_at": decided_at,
                },
            )
    return updated


async def adecide_approval(
    db: ConversationDB,
    approval_id: int,
    state: str,
    denial_reason: str = "",
    *,
    decided_by: str = "local_user",
) -> bool:
    """写入审批决定（异步），语义同 :func:`decide_approval`。"""

    if state not in {"approved", "denied"}:
        raise ValueError("无效的审批决定")
    await aexpire_pending_approvals(db, approval_id=approval_id)
    decided_at = _utc_now()

    async def write() -> bool:
        async with db.aconnect() as con:
            cur = await con.execute(
                """UPDATE approvals SET state=?, denial_reason=?,
                decided_by=?, decided_at=?
                WHERE id=? AND state='pending'""",
                (
                    state,
                    sanitize_db_text(denial_reason),
                    sanitize_db_text(decided_by),
                    decided_at,
                    approval_id,
                ),
            )
            await con.commit()
            return cur.rowcount == 1

    updated = await aretry_on_locked(write)
    if updated:
        await _aemit(
            "approval_decided",
            db,
            approval_id=approval_id,
            state=state,
            decided_by=decided_by,
            decided_at=decided_at,
            denial_reason=sanitize_db_text(denial_reason),
        )
        async with db.aconnect() as con:
            cursor = await con.execute(
                "SELECT session_id FROM approvals WHERE id=?",
                (approval_id,),
            )
            row = await cursor.fetchone()
        if row and row[0]:
            await ainsert_session_event(
                db,
                row[0],
                "approval_decided",
                {
                    "approval_id": approval_id,
                    "state": state,
                    "denial_reason": sanitize_db_text(denial_reason),
                    "decided_by": sanitize_db_text(decided_by),
                    "decided_at": decided_at,
                },
            )
    return updated
