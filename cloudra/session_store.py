"""Session / 子任务 / 审批状态迁移的唯一写入入口。

所有对 ``session`` / ``subagent_requests`` / ``approvals`` / ``session_events``
表的写操作都必须经过本模块，调用方不再内联 SQL。连接统一由
:class:`cloudra.database.ConversationDB` 提供（WAL + busy_timeout），
短时写操作统一经 ``retry_on_locked`` / ``aretry_on_locked`` 重试。
进程管理（poll/kill）与消息格式化仍留在调用方。
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from cloudra.database import ConversationDB, aretry_on_locked, retry_on_locked

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
) -> None:
    """创建即入库（reAct.session_create）：INSERT OR IGNORE + COALESCE 补齐元数据。"""
    pid = os.getpid() if pid is None else pid
    worker_id = worker_id or f"process:{pid}"
    now = _utc_now()

    def write() -> None:
        with db.connect() as con:
            con.execute(
                """INSERT OR IGNORE INTO session
                (session_id, agent_id, agent_type, parent_session_id, query, state, result, pid,
                 worker_id, created_at, started_at, heartbeat_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    session_id, agent_id, agent_type, parent_session_id, query,
                    "running", "", pid, worker_id, created_at, now, now,
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
    """写入遥测事件并刷新心跳（reAct._record_event 的语义：同事务、同时间戳）。"""
    now = _utc_now()

    async def write() -> None:
        async with db.aconnect() as con:
            await con.execute(
                "UPDATE session SET heartbeat_at=? WHERE session_id=?",
                (now, session_id),
            )
            await con.execute(
                "INSERT INTO session_events (session_id, event_type, data, created_at) VALUES (?, ?, ?, ?)",
                (session_id, event_type, json.dumps(data, ensure_ascii=False), now),
            )
            await con.commit()

    await aretry_on_locked(write)


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

    return await aretry_on_locked(write)


def claim_ready_request(db: ConversationDB) -> Optional[tuple[int, Any]]:
    """原子抢占一个 ready 子任务（乐观锁），返回 (id, input_data)；没有则返回 None。

    空闲降级：先只读探测，没有 ready 任务就不发起写事务，
    避免空转时每秒的 UPDATE...RETURNING 也抢占写锁。
    """

    def write() -> Optional[tuple[int, Any]]:
        with db.connect() as con:
            cur = con.cursor()
            cur.execute("SELECT id FROM subagent_requests WHERE state = 'ready' LIMIT 1")
            if cur.fetchone() is None:
                con.rollback()
                return None
            # 原子操作：先尝试把状态从 ready 改为 running，并返回被修改的 id 和 input_data；
            # 如果别的线程已经改了，这个 UPDATE 就会返回空，从而避免冲突。
            cur.execute("""
                UPDATE subagent_requests
                SET state = 'running'
                WHERE id IN (
                    SELECT id FROM subagent_requests WHERE state = 'ready' LIMIT 1
                )
                RETURNING id, input_data
            """)
            claimed = cur.fetchone()
            if claimed:
                con.commit()  # 确认修改
            else:
                con.rollback()
            return claimed

    return retry_on_locked(write)


def fail_request(db: ConversationDB, request_id: int) -> None:
    """把子任务请求标记为 failed（如 executor 进程刚启动就崩溃的回滚）。"""

    def write() -> None:
        with db.connect() as con:
            con.execute("UPDATE subagent_requests SET state = 'failed' WHERE id = ?", (request_id,))
            con.commit()

    retry_on_locked(write)


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
    reaped = []

    def write() -> None:
        with db.connect() as con:
            cur = con.cursor()
            for rid in request_ids:
                cur.execute(
                    "UPDATE subagent_requests SET state='failed' WHERE id=? AND state='running'",
                    (rid,),
                )
                if not cur.rowcount:
                    continue
                reaped.append(rid)
                cur.execute(
                    """UPDATE session SET state='failed',
                    error=COALESCE(error, 'executor process exited unexpectedly'), finished_at=?
                    WHERE state='running' AND session_id=(
                        SELECT session_id FROM subagent_requests WHERE id=?
                    )""",
                    (now, rid),
                )
            con.commit()

    retry_on_locked(write)
    return reaped


def recover_stale(db: ConversationDB, *, cutoff: str) -> int:
    """把失去心跳的 running Session 标为 interrupted，并回收其孤儿 running 请求。

    返回被标记 interrupted 的 Session 数。``cutoff`` 为心跳过期阈值（ISO 时间串）。
    """
    now = _utc_now()
    changed = 0

    def write() -> None:
        nonlocal changed
        with db.connect() as con:
            cursor = con.execute(
                """UPDATE session SET state='interrupted',
                error=COALESCE(error, 'worker heartbeat expired'), finished_at=?
                WHERE state='running' AND (heartbeat_at IS NULL OR heartbeat_at < ?)""",
                (now, cutoff),
            )
            changed = cursor.rowcount
            # 状态一致性：子 Agent 请求若仍挂在 'running'，但其 executor 的
            # Session 已死（心跳过期/不存在/非 running），一并标记 failed，
            # 避免等待方（_wait_for_background_tasks 等）永久阻塞。
            con.execute(
                """UPDATE subagent_requests SET state='failed'
                WHERE state='running' AND (
                    session_id IS NULL
                    OR session_id NOT IN (SELECT session_id FROM session)
                    OR session_id IN (
                        SELECT session_id FROM session
                        WHERE state != 'running' OR heartbeat_at IS NULL OR heartbeat_at < ?
                    )
                )""",
                (cutoff,),
            )
            con.commit()

    retry_on_locked(write)
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

    def write() -> None:
        with db.connect() as con:
            children = con.execute(
                """SELECT session_id, pid FROM session
                WHERE parent_session_id=? AND state IN ('queued', 'running', 'cancel_requested')""",
                (parent_session_id,),
            ).fetchall()
            for child_id, pid in children:
                con.execute(
                    """UPDATE session SET state='cancel_requested'
                    WHERE session_id=? AND state IN ('queued', 'running')""",
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
) -> None:
    """SessionRunner.submit：先入队一条 queued Session。"""

    def write() -> None:
        with db.connect() as con:
            con.execute(
                """INSERT INTO session
                (session_id, agent_id, agent_type, query, state, created_at)
                VALUES (?, ?, ?, ?, ?, ?)""",
                (session_id, agent_id, agent_type, query, "queued", _utc_now()),
            )
            con.commit()

    retry_on_locked(write)


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
    return claimed


# ---------------------------------------------------------------------------
# 审批（approvals）
# ---------------------------------------------------------------------------

def insert_approval(
    db: ConversationDB,
    session_id: str,
    details: str,
    agent_name: Optional[str] = None,
) -> int:
    """插入一条 pending 审批记录，返回 approval_id；details 写库前做孤立代理符净化。"""

    def write() -> int:
        with db.connect() as con:
            cur = con.execute(
                "INSERT INTO approvals (session_id, agent_name, details, state) VALUES (?, ?, ?, 'pending')",
                (session_id, agent_name, sanitize_db_text(details)),
            )
            con.commit()
            return cur.lastrowid

    return retry_on_locked(write)


async def ainsert_approval(
    db: ConversationDB,
    session_id: str,
    details: str,
    agent_name: Optional[str] = None,
) -> int:
    """异步插入一条 pending 审批记录，返回 approval_id；语义同 :func:`insert_approval`。"""

    async def write() -> int:
        async with db.aconnect() as con:
            cur = await con.execute(
                "INSERT INTO approvals (session_id, agent_name, details, state) VALUES (?, ?, ?, 'pending')",
                (session_id, agent_name, sanitize_db_text(details)),
            )
            await con.commit()
            return cur.lastrowid

    return await aretry_on_locked(write)


def list_pending_approvals(db: ConversationDB) -> list[tuple[int, str, str, str]]:
    """读取指定数据库中所有 pending 状态的审批记录。

    返回 ``(id, session_id, agent_name, details)`` 元组列表。
    """

    def read() -> list:
        with db.connect() as con:
            cur = con.execute(
                "SELECT id, session_id, agent_name, details FROM approvals WHERE state = 'pending'"
            )
            return cur.fetchall()

    return retry_on_locked(read)


async def aread_approval_status(db: ConversationDB, approval_id: int) -> Optional[tuple[str, str]]:
    """异步读取单条审批的 ``(state, denial_reason)``；不存在时返回 None。"""

    async def read() -> Optional[tuple]:
        async with db.aconnect() as con:
            cur = await con.execute(
                "SELECT state, denial_reason FROM approvals WHERE id = ?", (approval_id,)
            )
            return await cur.fetchone()

    return await aretry_on_locked(read)


def decide_approval(db: ConversationDB, approval_id: int, state: str, denial_reason: str = "") -> bool:
    """写入审批决定（同步），仅当审批仍处于 pending 时生效。

    防止 CLI 与 Web/API 双通道同时审批时互相覆盖而不自知。
    denial_reason 写库前统一做孤立代理符净化。
    """

    def write() -> bool:
        with db.connect() as con:
            cur = con.execute(
                "UPDATE approvals SET state = ?, denial_reason = ? WHERE id = ? AND state = 'pending'",
                (state, sanitize_db_text(denial_reason), approval_id),
            )
            con.commit()
            return cur.rowcount == 1

    return retry_on_locked(write)


async def adecide_approval(db: ConversationDB, approval_id: int, state: str, denial_reason: str = "") -> bool:
    """写入审批决定（异步），语义同 :func:`decide_approval`。"""

    async def write() -> bool:
        async with db.aconnect() as con:
            cur = await con.execute(
                "UPDATE approvals SET state = ?, denial_reason = ? WHERE id = ? AND state = 'pending'",
                (state, sanitize_db_text(denial_reason), approval_id),
            )
            await con.commit()
            return cur.rowcount == 1

    return await aretry_on_locked(write)
