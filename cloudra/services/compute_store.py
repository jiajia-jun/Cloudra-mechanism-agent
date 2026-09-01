"""compute_jobs 表（中央库 ``data_dir/compute.db``）的全部 SQL 入口。

compute_jobs 已从会话级 SQLite 迁到中央库：提交（submit_compute_job）、
认领（调度守护）、guard/Slurm 终态 CAS、完成通知轮询的读写一律经过本模块，
调用方不再内联 SQL。连接统一由
:class:`cloudra.persistence.database.ComputeDB` 提供（WAL + busy_timeout），
短时写操作统一经 ``retry_on_locked`` / ``aretry_on_locked`` 重试。

同步函数只能在守护线程 / CLI / 测试上下文使用；事件循环线程一律用
``a`` 前缀异步变体或 ``asyncio.to_thread`` 卸载。
"""

from __future__ import annotations

import os
import time
from typing import Any, Optional

from cloudra.persistence.database import ComputeDB, aretry_on_locked, retry_on_locked

# compute_jobs 全列（与 ComputeDB 的 DDL 一一对应）；dict 行统一按它投影。
_COMPUTE_JOB_COLUMNS = (
    "id", "conversation_id", "session_id", "state", "path",
    "start_timestamp", "end_timestamp", "jobtype", "scheduler",
    "scheduler_options", "scheduler_job_id", "scheduler_state",
    "scheduler_script", "last_error", "lease_owner", "lease_expires_at",
    "attempt_count", "priority", "req_cpus", "req_memory_mb",
    "guard_pid", "calc_pid", "notified_at",
)
_SELECT_COLUMNS = ", ".join(_COMPUTE_JOB_COLUMNS)

# list_compute_jobs 的排序键白名单（键全部来自内部代码，防注入）。
_LIST_ORDERS = {
    "id": "id",
    "recent": "id DESC",
    "priority": "priority DESC, id ASC",
    "ended": "end_timestamp DESC",
}

# 终态词表：完成通知轮询与队列视图的统一口径。
TERMINAL_STATES = ("done", "failed", "cancelled")


def _db_ready(db: ComputeDB) -> bool:
    """读路径不建库：中央库不存在或仍是空文件（从未提交过作业）即视为空。"""
    try:
        return os.path.isfile(db.path) and os.path.getsize(db.path) > 0
    except OSError:
        return False


def _row_dict(row) -> dict:
    return dict(zip(_COMPUTE_JOB_COLUMNS, row))


# ---------------------------------------------------------------------------
# 写入：提交
# ---------------------------------------------------------------------------

_INSERT_SQL = """INSERT INTO compute_jobs
    (conversation_id, session_id, path, state, jobtype,
     start_timestamp, end_timestamp, scheduler, scheduler_options,
     priority, req_cpus, req_memory_mb)
    VALUES (?,?,?,?,?,?,?,?,?,?,?,?)"""


def _insert_params(
    *,
    conversation_id: str,
    session_id: Optional[str],
    path: str,
    state: str,
    jobtype: str,
    scheduler: str,
    scheduler_options: str,
    priority: int,
    req_cpus: int,
    req_memory_mb: Optional[int],
    start_timestamp: float,
) -> tuple:
    if not conversation_id:
        raise ValueError("compute job 必须归属一个 conversation_id")
    return (
        conversation_id, session_id, path, state, jobtype,
        start_timestamp, -1, scheduler, scheduler_options,
        priority, req_cpus, req_memory_mb,
    )


def insert_compute_job(
    db: ComputeDB,
    *,
    conversation_id: str,
    session_id: Optional[str],
    path: str,
    state: str,
    jobtype: str,
    scheduler: str = "local",
    scheduler_options: str = "{}",
    priority: int = 0,
    req_cpus: int = 1,
    req_memory_mb: Optional[int] = None,
    start_timestamp: float = -1,
) -> int:
    """写入一条作业记录，返回 job id。conversation_id 必填（作业归属的项目）。"""
    params = _insert_params(
        conversation_id=conversation_id, session_id=session_id, path=path,
        state=state, jobtype=jobtype, scheduler=scheduler,
        scheduler_options=scheduler_options, priority=priority,
        req_cpus=req_cpus, req_memory_mb=req_memory_mb,
        start_timestamp=start_timestamp,
    )

    def write() -> int:
        with db.connect() as con:
            cur = con.execute(_INSERT_SQL, params)
            con.commit()
            return int(cur.lastrowid)

    return retry_on_locked(write)


async def ainsert_compute_job(
    db: ComputeDB,
    *,
    conversation_id: str,
    session_id: Optional[str],
    path: str,
    state: str,
    jobtype: str,
    scheduler: str = "local",
    scheduler_options: str = "{}",
    priority: int = 0,
    req_cpus: int = 1,
    req_memory_mb: Optional[int] = None,
    start_timestamp: float = -1,
) -> int:
    """异步写入一条作业记录；语义同 :func:`insert_compute_job`。"""
    params = _insert_params(
        conversation_id=conversation_id, session_id=session_id, path=path,
        state=state, jobtype=jobtype, scheduler=scheduler,
        scheduler_options=scheduler_options, priority=priority,
        req_cpus=req_cpus, req_memory_mb=req_memory_mb,
        start_timestamp=start_timestamp,
    )

    async def write() -> int:
        async with db.aconnect() as con:
            cur = await con.execute(_INSERT_SQL, params)
            await con.commit()
            return int(cur.lastrowid)

    return await aretry_on_locked(write)


# ---------------------------------------------------------------------------
# 只读查询
# ---------------------------------------------------------------------------

def get_compute_job(db: ComputeDB, task_id: int) -> Optional[dict]:
    """按 id 读一整行（dict，全列）；不存在返回 None。"""

    def read() -> Optional[dict]:
        with db.connect() as con:
            row = con.execute(
                f"SELECT {_SELECT_COLUMNS} FROM compute_jobs WHERE id=?",
                (task_id,),
            ).fetchone()
        return _row_dict(row) if row else None

    return retry_on_locked(read)


async def aget_compute_job(db: ComputeDB, task_id: int) -> Optional[dict]:
    """异步读一整行；语义同 :func:`get_compute_job`。"""

    async def read() -> Optional[dict]:
        async with db.aconnect() as con:
            cur = await con.execute(
                f"SELECT {_SELECT_COLUMNS} FROM compute_jobs WHERE id=?",
                (task_id,),
            )
            row = await cur.fetchone()
        return _row_dict(row) if row else None

    return await aretry_on_locked(read)


def _list_sql(
    *,
    states: Optional[tuple[str, ...]],
    conversation_id: Optional[str],
    order: str,
    limit: Optional[int],
) -> tuple[str, list]:
    clauses: list[str] = []
    params: list[Any] = []
    if states:
        clauses.append(f"state IN ({','.join('?' * len(states))})")
        params.extend(states)
    if conversation_id is not None:
        clauses.append("conversation_id=?")
        params.append(conversation_id)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    sql = (
        f"SELECT {_SELECT_COLUMNS} FROM compute_jobs {where} "
        f"ORDER BY {_LIST_ORDERS[order]}"
    )
    if limit is not None:
        sql += " LIMIT ?"
        params.append(max(1, int(limit)))
    return sql, params


def list_compute_jobs(
    db: ComputeDB,
    *,
    states: Optional[tuple[str, ...]] = None,
    conversation_id: Optional[str] = None,
    order: str = "id",
    limit: Optional[int] = None,
) -> list[dict]:
    """通用列表查询：按状态集合/归属会话过滤，排序键限 _LIST_ORDERS 白名单。"""
    sql, params = _list_sql(
        states=states, conversation_id=conversation_id, order=order, limit=limit
    )

    def read() -> list[dict]:
        with db.connect() as con:
            return [_row_dict(row) for row in con.execute(sql, params).fetchall()]

    return retry_on_locked(read)


async def alist_compute_jobs(
    db: ComputeDB,
    *,
    states: Optional[tuple[str, ...]] = None,
    conversation_id: Optional[str] = None,
    order: str = "id",
    limit: Optional[int] = None,
) -> list[dict]:
    """异步列表查询；语义同 :func:`list_compute_jobs`。"""
    sql, params = _list_sql(
        states=states, conversation_id=conversation_id, order=order, limit=limit
    )

    async def read() -> list[dict]:
        async with db.aconnect() as con:
            cur = await con.execute(sql, params)
            return [_row_dict(row) for row in await cur.fetchall()]

    return await aretry_on_locked(read)


def list_running_jobs(db: ComputeDB) -> list[dict]:
    """对账用：全部 running 作业（id/conversation_id/path/jobtype/scheduler）。"""

    def read() -> list[dict]:
        with db.connect() as con:
            rows = con.execute(
                """SELECT id, conversation_id, path, jobtype, scheduler
                FROM compute_jobs WHERE state='running'"""
            ).fetchall()
        return [
            {
                "id": int(r[0]),
                "conversation_id": r[1],
                "path": r[2],
                "jobtype": r[3],
                "scheduler": r[4],
            }
            for r in rows
        ]

    return retry_on_locked(read)


def pending_terminal_jobs(
    db: ComputeDB,
    *,
    window_seconds: float,
    limit: int,
    conversation_id: Optional[str] = None,
) -> list[tuple[str, int, str, Optional[str]]]:
    """终态且未通知的作业：(conversation_id, id, state, session_id)。

    限 ``window_seconds`` 补投窗口防历史刷屏。读路径不建库：中央库文件
    不存在（从未提交过作业）时返回空，不创建空文件。
    """
    if not _db_ready(db):
        return []
    cutoff = time.time() - window_seconds

    def read() -> list[tuple[str, int, str, Optional[str]]]:
        clauses = (
            "state IN ('done','failed','cancelled') "
            "AND notified_at IS NULL AND end_timestamp>=?"
        )
        params: list[Any] = [cutoff]
        if conversation_id is not None:
            clauses += " AND conversation_id=?"
            params.append(conversation_id)
        with db.connect() as con:
            return [
                (str(r[0]), int(r[1]), str(r[2]), r[3])
                for r in con.execute(
                    f"""SELECT conversation_id, id, state, session_id FROM compute_jobs
                    WHERE {clauses} ORDER BY id LIMIT ?""",
                    (*params, limit),
                ).fetchall()
            ]

    return retry_on_locked(read)


async def acount_pending_compute_jobs(db: ComputeDB, conversation_id: str) -> int:
    """指定会话的未竟作业数（ready/running）——stop 门禁的挂起判定口径。

    读路径不建库：中央库不存在（从未提交过作业）即 0。
    """
    if not _db_ready(db):
        return 0

    async def read() -> int:
        async with db.aconnect() as con:
            cur = await con.execute(
                "SELECT COUNT(*) FROM compute_jobs "
                "WHERE state IN ('ready', 'running') AND conversation_id = ?",
                (conversation_id,),
            )
            row = await cur.fetchone()
            return int(row[0]) if row else 0

    return await aretry_on_locked(read)


def compute_inflight_usage(
    db: ComputeDB,
    *,
    default_mem: int,
) -> tuple[int, int, int]:
    """统计租约有效的 running 作业在用量：(槽位数, CPU, 内存MB)。

    中央库单库后，本库在用量即全节点在用量（无需再跨库汇总）。
    """

    def read() -> tuple[int, int, int]:
        now = time.time()
        with db.connect() as con:
            row = con.execute(
                """SELECT COUNT(*), COALESCE(SUM(req_cpus), 0),
                   COALESCE(SUM(COALESCE(req_memory_mb, ?)), 0)
                   FROM compute_jobs
                   WHERE state='running' AND lease_expires_at>=?""",
                (default_mem, now),
            ).fetchone()
        return int(row[0]), int(row[1]), int(row[2])

    return retry_on_locked(read)


# ---------------------------------------------------------------------------
# 认领 / 租约（调度守护）
# ---------------------------------------------------------------------------

def claim_ready_compute_job_with_capacity(
    db: ComputeDB,
    *,
    worker_id: str,
    capacity: dict,
    lease_seconds: int = 120,
    max_attempts: int = 3,
) -> Optional[int]:
    """容量感知的原子认领：priority DESC, id ASC，取第一个能放进剩余容量的作业。

    capacity = {"max_concurrent": int, "cpus": int, "memory_mb": int}。
    在用量 = 中央库租约有效的 running 行（单库即全节点视图）。
    未声明内存的作业按节点公平份额（memory_mb // max_concurrent）记账。
    槽位满时直接返回；CPU/内存放不下的作业跳过、不阻塞后面的小作业。
    """
    cap_slots = max(1, int(capacity.get("max_concurrent", 1)))
    cap_cpus = max(1, int(capacity.get("cpus", 1)))
    cap_mem = max(1, int(capacity.get("memory_mb", 1024)))
    default_mem = max(1, cap_mem // cap_slots)

    def write() -> Optional[int]:
        now = time.time()
        expires = now + max(10, int(lease_seconds))
        with db.connect() as con:
            inflight = con.execute(
                """SELECT COUNT(*), COALESCE(SUM(req_cpus), 0),
                   COALESCE(SUM(COALESCE(req_memory_mb, ?)), 0)
                   FROM compute_jobs
                   WHERE state='running' AND lease_expires_at>=?""",
                (default_mem, now),
            ).fetchone()
            used_slots = int(inflight[0])
            used_cpus = int(inflight[1])
            used_mem = int(inflight[2])
            candidates = con.execute(
                """SELECT id, req_cpus, req_memory_mb FROM compute_jobs
                WHERE (state='ready' OR (state='running' AND lease_expires_at<?))
                AND COALESCE(attempt_count, 0) < ?
                ORDER BY priority DESC, id ASC""",
                (now, max_attempts),
            ).fetchall()
            picked: Optional[int] = None
            for cid, req_cpus, req_mem in candidates:
                if used_slots + 1 > cap_slots:
                    break  # 槽位满，后面每个作业都要槽位
                r_cpus = int(req_cpus or 1)
                r_mem = int(req_mem if req_mem is not None else default_mem)
                if used_cpus + r_cpus > cap_cpus or used_mem + r_mem > cap_mem:
                    continue  # 太大放不下，试试后面的小作业
                picked = int(cid)
                break
            if picked is None:
                con.rollback()
                return None
            row = con.execute(
                """UPDATE compute_jobs SET state='running', lease_owner=?,
                lease_expires_at=?, attempt_count=COALESCE(attempt_count, 0)+1,
                start_timestamp=CASE WHEN start_timestamp IS NULL OR start_timestamp<=0
                    THEN ? ELSE start_timestamp END
                WHERE id=? AND (state='ready' OR (state='running' AND lease_expires_at<?))
                RETURNING id""",
                (worker_id, expires, now, picked, now),
            ).fetchone()
            if row:
                con.commit()
            else:
                con.rollback()
            return int(row[0]) if row else None

    return retry_on_locked(write)


def reset_compute_attempt_count(db: ComputeDB, task_id: int, worker_id: str) -> None:
    """作业成功拉起（guard/spawn 或 Slurm attach）后清零重试计数。

    attempt_count 只累计"真失败"（认领后没能拉起）；服务重启导致的重认领
    不应消耗重试预算，否则 Slurm 作业会在数次服务重启后被误判 failed。
    """

    def write() -> None:
        with db.connect() as con:
            con.execute(
                """UPDATE compute_jobs SET attempt_count=0
                WHERE id=? AND state='running' AND lease_owner=?""",
                (task_id, worker_id),
            )
            con.commit()

    retry_on_locked(write)


def renew_compute_lease(
    db: ComputeDB,
    *,
    task_id: int,
    worker_id: str,
    lease_seconds: int = 60,
) -> bool:
    """Renew only the current owner's live lease; stale owners fail closed."""
    renewed = False

    def write() -> None:
        nonlocal renewed
        with db.connect() as con:
            cursor = con.execute(
                """UPDATE compute_jobs SET lease_expires_at=?
                WHERE id=? AND state='running' AND lease_owner=?""",
                (time.time() + max(10, int(lease_seconds)), task_id, worker_id),
            )
            renewed = cursor.rowcount == 1
            con.commit()

    retry_on_locked(write)
    return renewed


def extend_compute_lease(db: ComputeDB, task_id: int, seconds: int) -> None:
    """无条件（不限 owner）延长 running 作业的租约：guard 拉起后/对账续租用。"""

    def write() -> None:
        with db.connect() as con:
            con.execute(
                "UPDATE compute_jobs SET lease_expires_at=? WHERE id=? AND state='running'",
                (time.time() + max(10, int(seconds)), task_id),
            )
            con.commit()

    retry_on_locked(write)


async def aextend_compute_lease(db: ComputeDB, task_id: int, seconds: int) -> None:
    """异步延租；语义同 :func:`extend_compute_lease`。"""
    async with db.aconnect() as con:
        await con.execute(
            "UPDATE compute_jobs SET lease_expires_at=? WHERE id=? AND state='running'",
            (time.time() + max(10, int(seconds)), task_id),
        )
        await con.commit()


def reap_exhausted_compute_leases(
    db: ComputeDB,
    *,
    max_attempts: int = 3,
) -> list[int]:
    """Fail expired compute jobs that consumed their retry budget; 返回被 reap 的 id。"""
    now = time.time()
    compute_ids: list[int] = []

    def write() -> None:
        with db.connect() as con:
            compute_ids.extend(
                int(row[0])
                for row in con.execute(
                    """SELECT id FROM compute_jobs WHERE state='running'
                    AND lease_expires_at<? AND COALESCE(attempt_count, 0)>=?""",
                    (now, max_attempts),
                ).fetchall()
            )
            con.execute(
                """UPDATE compute_jobs SET state='failed', end_timestamp=?,
                last_error='worker lease retry budget exhausted'
                WHERE state='running' AND lease_expires_at<?
                AND COALESCE(attempt_count, 0)>=?""",
                (now, now, max_attempts),
            )
            con.commit()

    retry_on_locked(write)
    # 终态已落库：由 ComputeNotifyBroker 轮询补投，不再发进程间事件。
    return compute_ids


# ---------------------------------------------------------------------------
# 终态落库（guard / Slurm / executor / 手动标记）
# ---------------------------------------------------------------------------

async def afinalize_compute_job(
    db: ComputeDB,
    task_id: int,
    state: str,
    *,
    last_error: Optional[str] = None,
    only_running: bool = True,
) -> bool:
    """终态 CAS 落库；only_running=True 时仅覆盖 running（双写竞态防护）。

    返回是否真的写入（CAS 失败说明其他收尾方已写终态）。
    """
    sql = "UPDATE compute_jobs SET state=?, end_timestamp=?, last_error=? WHERE id=?"
    if only_running:
        sql += " AND state='running'"
    async with db.aconnect() as con:
        cur = await con.execute(sql, (state, time.time(), last_error, task_id))
        await con.commit()
        return cur.rowcount == 1


async def afail_compute_job(db: ComputeDB, task_id: int, message: str) -> None:
    """无条件标记 failed（executor 拉起失败 / agent 手动标记），顺带清租约。"""
    async with db.aconnect() as con:
        await con.execute(
            "UPDATE compute_jobs SET state='failed', end_timestamp=?, "
            "last_error=?, lease_expires_at=0 WHERE id=?",
            (time.time(), message[:500], task_id),
        )
        await con.commit()


async def aupdate_compute_pid(db: ComputeDB, task_id: int, column: str, pid: int) -> None:
    """登记 guard/calc PID。仅作观测取证，不参与存活判定。"""
    if column not in {"guard_pid", "calc_pid"}:
        raise ValueError("unsupported pid column")
    async with db.aconnect() as con:
        await con.execute(
            f"UPDATE compute_jobs SET {column}=? WHERE id=?", (pid, task_id)
        )
        await con.commit()


# ---------------------------------------------------------------------------
# Slurm 链路
# ---------------------------------------------------------------------------

async def amark_slurm_submitted(
    db: ComputeDB, task_id: int, scheduler_job_id: str, script_path: str
) -> None:
    """sbatch 成功后回写 Slurm 句柄（job id/脚本路径）并置 PENDING。"""
    async with db.aconnect() as con:
        await con.execute(
            """UPDATE compute_jobs SET scheduler_job_id=?, scheduler_script=?,
            scheduler_state='PENDING', start_timestamp=? WHERE id=?""",
            (scheduler_job_id, script_path, time.time(), task_id),
        )
        await con.commit()


async def aupdate_scheduler_state(db: ComputeDB, task_id: int, scheduler_state: str) -> None:
    """sacct 轮询到的 Slurm 侧状态回写。"""
    async with db.aconnect() as con:
        await con.execute(
            "UPDATE compute_jobs SET scheduler_state=? WHERE id=?",
            (scheduler_state, task_id),
        )
        await con.commit()


async def acancel_compute_job(db: ComputeDB, task_id: int) -> None:
    """显式取消（cancel_requested → scancel 后）落 cancelled 终态。"""
    async with db.aconnect() as con:
        await con.execute(
            """UPDATE compute_jobs SET state='cancelled',
            scheduler_state='CANCELLED', end_timestamp=? WHERE id=?""",
            (time.time(), task_id),
        )
        await con.commit()


# ---------------------------------------------------------------------------
# 完成通知（ComputeNotifyBroker）
# ---------------------------------------------------------------------------

def mark_notified(db: ComputeDB, task_id: int) -> None:
    """投递完成后落 notified_at——去重只认它（notified_at IS NULL 过滤）。"""

    def write() -> None:
        with db.connect() as con:
            con.execute(
                "UPDATE compute_jobs SET notified_at=? WHERE id=?",
                (time.time(), task_id),
            )
            con.commit()

    retry_on_locked(write)
