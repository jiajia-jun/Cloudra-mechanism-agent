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

import asyncio
import logging
import os
import time
from typing import Any, Mapping, Optional, Sequence

from cloudra.persistence.database import ComputeDB, aretry_on_locked, retry_on_locked

logger = logging.getLogger(__name__)

# 认领时跳过"节点已从注册表消失"的作业：每次发现只在首次记一条 WARNING，
# 否则轮询每 tick 都会刷屏（诊断口径由 query_compute_queue 展示给用户）。
_warned_unknown_nodes: set[str] = set()

# compute_jobs 全列（与 ComputeDB 的 DDL 一一对应）；dict 行统一按它投影。
_COMPUTE_JOB_COLUMNS = (
    "id", "conversation_id", "session_id", "state", "path",
    "start_timestamp", "end_timestamp", "jobtype", "node_id", "scheduler",
    "scheduler_options", "scheduler_job_id", "scheduler_state",
    "scheduler_script", "last_error", "lease_owner", "lease_expires_at",
    "attempt_count", "priority", "req_cpus", "req_memory_mb",
    "charge", "multiplicity", "xtb_task", "xtb_solvent",
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
ACTIVE_STATES = ("ready", "running", "cancel_requested")


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
     start_timestamp, end_timestamp, node_id, scheduler, scheduler_options,
     priority, req_cpus, req_memory_mb,
     charge, multiplicity, xtb_task, xtb_solvent)
    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"""


def _insert_params(
    *,
    conversation_id: str,
    session_id: Optional[str],
    path: str,
    state: str,
    jobtype: str,
    node_id: str,
    scheduler: str,
    scheduler_options: str,
    priority: int,
    req_cpus: int,
    req_memory_mb: Optional[int],
    charge: int,
    multiplicity: int,
    xtb_task: str,
    xtb_solvent: Optional[str],
    start_timestamp: float,
) -> tuple:
    if not conversation_id:
        raise ValueError("compute job 必须归属一个 conversation_id")
    if not node_id:
        raise ValueError("compute job 必须归属一个注册节点（容量按节点分池记账）")
    return (
        conversation_id, session_id, path, state, jobtype,
        start_timestamp, -1, node_id, scheduler, scheduler_options,
        priority, req_cpus, req_memory_mb,
        charge, multiplicity, xtb_task, xtb_solvent,
    )


def insert_compute_job_in_transaction(con, **kwargs) -> int:
    """Insert into a caller-owned transaction; never commits or opens a queue."""
    params = _insert_params(**kwargs)
    return int(con.execute(_INSERT_SQL, params).lastrowid)


def insert_compute_job(
    db: ComputeDB,
    *,
    conversation_id: str,
    session_id: Optional[str],
    path: str,
    state: str,
    jobtype: str,
    node_id: str,
    scheduler: str = "local",
    scheduler_options: str = "{}",
    priority: int = 0,
    req_cpus: int = 1,
    req_memory_mb: Optional[int] = None,
    charge: int = 0,
    multiplicity: int = 1,
    xtb_task: str = "sp",
    xtb_solvent: Optional[str] = None,
    start_timestamp: float = -1,
) -> int:
    """写入一条作业记录，返回 job id。conversation_id 必填（作业归属的项目）。"""
    params = _insert_params(
        conversation_id=conversation_id, session_id=session_id, path=path,
        state=state, jobtype=jobtype, node_id=node_id, scheduler=scheduler,
        scheduler_options=scheduler_options, priority=priority,
        req_cpus=req_cpus, req_memory_mb=req_memory_mb,
        charge=charge, multiplicity=multiplicity,
        xtb_task=xtb_task, xtb_solvent=xtb_solvent,
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
    node_id: str,
    scheduler: str = "local",
    scheduler_options: str = "{}",
    priority: int = 0,
    req_cpus: int = 1,
    req_memory_mb: Optional[int] = None,
    charge: int = 0,
    multiplicity: int = 1,
    xtb_task: str = "sp",
    xtb_solvent: Optional[str] = None,
    start_timestamp: float = -1,
) -> int:
    """异步写入一条作业记录；语义同 :func:`insert_compute_job`。"""
    params = _insert_params(
        conversation_id=conversation_id, session_id=session_id, path=path,
        state=state, jobtype=jobtype, node_id=node_id, scheduler=scheduler,
        scheduler_options=scheduler_options, priority=priority,
        req_cpus=req_cpus, req_memory_mb=req_memory_mb,
        charge=charge, multiplicity=multiplicity,
        xtb_task=xtb_task, xtb_solvent=xtb_solvent,
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
    """对账用：running 与 cancel_requested（Slurm scancel 重挂也靠这一条）。"""

    def read() -> list[dict]:
        with db.connect() as con:
            rows = con.execute(
                """SELECT id, conversation_id, path, jobtype, scheduler,
                scheduler_job_id, state, start_timestamp
                FROM compute_jobs WHERE state IN ('running', 'cancel_requested')"""
            ).fetchall()
        return [
            {
                "id": int(r[0]),
                "conversation_id": r[1],
                "path": r[2],
                "jobtype": r[3],
                "scheduler": r[4],
                "scheduler_job_id": r[5],
                "state": r[6],
                "start_timestamp": r[7],
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
    conversation_ids: Optional[Sequence[str]] = None,
) -> list[tuple[str, int, str, Optional[str]]]:
    """终态且未通知的作业：(conversation_id, id, state, session_id)。

    ``window_seconds`` 保留给调用方，查询本身不按结束时间截断。读路径
    不建库：中央库文件不存在（从未提交过作业）时返回空，不创建空文件。
    ``conversation_ids`` 限制在已加载项目内扫描，避免未打开项目的积压
    占满 LIMIT、挡住开着的项目。
    """
    if not _db_ready(db):
        return []
    _ = window_seconds
    if conversation_ids is not None and not conversation_ids:
        return []

    def read() -> list[tuple[str, int, str, Optional[str]]]:
        clauses = (
            "state IN ('done','failed','cancelled') "
            "AND notified_at IS NULL"
        )
        params: list[Any] = []
        if conversation_ids is not None:
            placeholders = ",".join("?" * len(conversation_ids))
            clauses += f" AND conversation_id IN ({placeholders})"
            params.extend(conversation_ids)
        elif conversation_id is not None:
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
    """指定会话的未竟作业数（含待取消）——stop 门禁的挂起判定口径。

    读路径不建库：中央库不存在（从未提交过作业）即 0。
    """
    if not _db_ready(db):
        return 0

    async def read() -> int:
        async with db.aconnect() as con:
            cur = await con.execute(
                "SELECT COUNT(*) FROM compute_jobs "
                "WHERE state IN ('ready', 'running', 'cancel_requested') "
                "AND conversation_id = ?",
                (conversation_id,),
            )
            row = await cur.fetchone()
            return int(row[0]) if row else 0

    return await aretry_on_locked(read)


async def acount_waitable_compute_jobs_for_session(
    db: ComputeDB, conversation_id: str, session_id: str
) -> int:
    """Owned jobs that still owe an agent either execution or a terminal notice.

    A job can become terminal between the agent's stop call and the broker's
    next poll. Until ``notified_at`` is set, the agent must stay parked so it
    cannot report completion before seeing that job's result.
    """
    if not _db_ready(db):
        return 0

    async def read() -> int:
        async with db.aconnect() as con:
            cur = await con.execute(
                "SELECT COUNT(*) FROM compute_jobs "
                "WHERE conversation_id = ? AND session_id = ? AND ("
                "state IN ('ready', 'running', 'cancel_requested') OR "
                "(state IN ('done', 'failed', 'cancelled') AND notified_at IS NULL))",
                (conversation_id, session_id),
            )
            row = await cur.fetchone()
            return int(row[0]) if row else 0

    return await aretry_on_locked(read)


async def acount_active_compute_job_states(
    db: ComputeDB, conversation_id: str
) -> dict[str, int]:
    """指定会话非终态作业按状态计数（ready/running/cancel_requested）。

    读路径不建库：中央库不存在（从未提交过作业）即空字典。
    """
    if not _db_ready(db):
        return {}

    async def read() -> dict[str, int]:
        async with db.aconnect() as con:
            cur = await con.execute(
                "SELECT state, COUNT(*) FROM compute_jobs "
                "WHERE state IN ('ready', 'running', 'cancel_requested') "
                "AND conversation_id = ? GROUP BY state",
                (conversation_id,),
            )
            rows = await cur.fetchall()
        return {str(state): int(count) for state, count in rows}

    return await aretry_on_locked(read)


def active_jobs_delete_message(counts: Mapping[str, int]) -> str:
    """硬删除被非终态作业挡住时的错误文本（API 与 CommandBus 共用）。"""
    total = sum(int(n) for n in counts.values())
    if total <= 0:
        return "project has 0 active compute job(s)"
    if set(counts) <= {"cancel_requested"}:
        n = int(counts.get("cancel_requested", 0))
        return (
            f"project has {n} cancel_requested compute job(s); "
            "wait for Slurm jobs to finish cancelling"
        )
    return (
        f"project has {total} active compute job(s); "
        "run POST /api/v2/compute/cancel-all first"
    )


async def acount_active_compute_jobs(db: ComputeDB, conversation_id: str) -> int:
    """指定会话的非终态作业数（ready/running/cancel_requested）——项目硬删除的门禁口径。

    读路径不建库：中央库不存在（从未提交过作业）即 0。
    """
    counts = await acount_active_compute_job_states(db, conversation_id)
    return sum(counts.values())


def _fair_share_mb(capacity: Mapping[str, Any]) -> int:
    """节点公平份额：未声明内存的作业按 ``memory_mb // max_concurrent`` 记账。"""
    cap_slots = max(1, int(capacity.get("max_concurrent", 1)))
    return max(1, int(capacity.get("memory_mb", 1024)) // cap_slots)


def _usage_by_node(
    con,
    *,
    now: float,
    default_node_id: str,
    fair_share_mb: Mapping[str, int],
) -> dict[str, list[int]]:
    """租约有效 running 行的**按节点**在用量：``{node_id: [槽位, CPU, 内存MB]}``。

    ``node_id`` 为 NULL 的行归属 ``default_node_id``（旧行升级路径）。不在
    ``fair_share_mb`` 里的节点（已从注册表消失）拿不到公平份额，按声明值或 0
    记账——它的额度本就不存在，认领也不会认到它。
    """
    rows = con.execute(
        """SELECT COALESCE(node_id, ?) AS node, req_cpus, req_memory_mb
           FROM compute_jobs
           WHERE state IN ('running', 'cancel_requested')""",
        (default_node_id,),
    ).fetchall()
    usage: dict[str, list[int]] = {}
    for node, req_cpus, req_mem in rows:
        key = str(node)
        acc = usage.setdefault(key, [0, 0, 0])
        acc[0] += 1
        acc[1] += int(req_cpus or 1)
        acc[2] += int(req_mem if req_mem is not None else fair_share_mb.get(key, 0))
    return usage


def compute_inflight_usage_by_node(
    db: ComputeDB,
    *,
    default_node_id: str,
    fair_share_mb: Mapping[str, int],
) -> dict[str, dict]:
    """各节点在用量视图（展示/诊断用）：``{node_id: {slots, cpus, memory_mb}}``。

    认领路径不用它——认领在同一事务里现算一遍，避免读写之间的额度漂移。
    读路径不建库：中央库不存在（从未提交过作业）即空视图。
    """
    if not _db_ready(db):
        return {}

    def read() -> dict[str, dict]:
        with db.connect() as con:
            usage = _usage_by_node(
                con,
                now=time.time(),
                default_node_id=default_node_id,
                fair_share_mb=fair_share_mb,
            )
        return {
            node: {"slots": value[0], "cpus": value[1], "memory_mb": value[2]}
            for node, value in usage.items()
        }

    return retry_on_locked(read)


def sync_local_fits_capacity(
    db: ComputeDB,
    *,
    node_id: str,
    cpus: int,
    memory_mb: Optional[int],
    node_resources: Mapping[str, Any],
) -> bool:
    """同步本机提交的容量闸门：与认领同一套在用量（running + cancel_requested）。"""
    fair_share = {str(node_id): _fair_share_mb(node_resources)}
    usage = compute_inflight_usage_by_node(
        db, default_node_id=str(node_id), fair_share_mb=fair_share
    )
    used = usage.get(str(node_id), {"slots": 0, "cpus": 0, "memory_mb": 0})
    cap_slots = max(1, int(node_resources.get("max_concurrent", 1)))
    cap_cpus = max(1, int(node_resources.get("cpus", 1)))
    cap_mem = max(1, int(node_resources.get("memory_mb", 1024)))
    r_cpus = max(1, int(cpus or 1))
    r_mem = int(
        memory_mb if memory_mb is not None else fair_share[str(node_id)]
    )
    return (
        used["slots"] + 1 <= cap_slots
        and used["cpus"] + r_cpus <= cap_cpus
        and used["memory_mb"] + r_mem <= cap_mem
    )


# ---------------------------------------------------------------------------
# 认领 / 租约（调度守护）
# ---------------------------------------------------------------------------

def claim_ready_compute_job_with_capacity(
    db: ComputeDB,
    *,
    worker_id: str,
    capacities: Mapping[str, dict],
    default_node_id: str,
    lease_seconds: int = 120,
    max_attempts: int = 3,
) -> Optional[int]:
    """按节点分池的容量感知原子认领：priority DESC, id ASC。

    ``capacities`` = ``{node_id: {"max_concurrent", "cpus", "memory_mb"}}``：
    每个节点只在自己额度内认领，**本地额度与云端额度互不吃**（解耦容量池）。
    在用量 = 中央库租约有效的 running 行按节点分组；未声明内存的作业按该节点
    公平份额（``memory_mb // max_concurrent``）记账。作业的节点不在
    ``capacities`` 里（已从注册表消失）则**跳过不认领**——绝不改投到别的机器上
    跑。排序仍是全库统一的，某节点放不下的作业跳过、不阻塞别的节点能放下的
    小作业；某节点槽位满则该节点后续作业直接跳过。
    """
    caps: dict[str, tuple[int, int, int]] = {}
    fair_share: dict[str, int] = {}
    for node_id, capacity in capacities.items():
        caps[str(node_id)] = (
            max(1, int(capacity.get("max_concurrent", 1))),
            max(1, int(capacity.get("cpus", 1))),
            max(1, int(capacity.get("memory_mb", 1024))),
        )
        fair_share[str(node_id)] = _fair_share_mb(capacity)

    def write() -> Optional[int]:
        now = time.time()
        expires = now + max(10, int(lease_seconds))
        with db.connect() as con:
            usage = _usage_by_node(
                con, now=now, default_node_id=default_node_id, fair_share_mb=fair_share
            )
            candidates = con.execute(
                """SELECT id, req_cpus, req_memory_mb, COALESCE(node_id, ?) AS node
                FROM compute_jobs
                WHERE state='ready'
                AND COALESCE(attempt_count, 0) < ?
                ORDER BY priority DESC, id ASC""",
                (default_node_id, max_attempts),
            ).fetchall()
            picked: Optional[int] = None
            for cid, req_cpus, req_mem, node in candidates:
                node_key = str(node)
                limits = caps.get(node_key)
                if limits is None:
                    if node_key not in _warned_unknown_nodes:
                        _warned_unknown_nodes.add(node_key)
                        logger.warning(
                            "compute job %s targets node %r which is not in the node "
                            "registry; leaving it queued (re-register the node or "
                            "cancel the job)",
                            cid,
                            node_key,
                        )
                    continue
                cap_slots, cap_cpus, cap_mem = limits
                used = usage.get(node_key, [0, 0, 0])
                if used[0] + 1 > cap_slots:
                    continue  # 该节点槽位满：后面属于它的作业同样放不下
                r_cpus = int(req_cpus or 1)
                r_mem = int(req_mem if req_mem is not None else fair_share[node_key])
                if used[1] + r_cpus > cap_cpus or used[2] + r_mem > cap_mem:
                    continue  # 该节点放不下，试试后面的小作业
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
                WHERE id=? AND state='ready'
                RETURNING id""",
                (worker_id, expires, now, picked),
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


def take_compute_lease(
    db: ComputeDB, task_id: int, worker_id: str, seconds: int
) -> None:
    """对账重挂时改写租约持有者，避免调度器 PID 变化后续租失败。"""

    def write() -> None:
        with db.connect() as con:
            con.execute(
                """UPDATE compute_jobs SET lease_owner=?, lease_expires_at=?
                WHERE id=? AND state IN ('running', 'cancel_requested')""",
                (worker_id, time.time() + max(10, int(seconds)), task_id),
            )
            con.commit()

    retry_on_locked(write)


def extend_compute_lease(db: ComputeDB, task_id: int, seconds: int) -> None:
    """无条件（不限 owner）延长 running 作业的租约：guard 拉起后/对账续租用。"""

    def write() -> None:
        with db.connect() as con:
            con.execute(
                "UPDATE compute_jobs SET lease_expires_at=? "
                "WHERE id=? AND state IN ('running', 'cancel_requested')",
                (time.time() + max(10, int(seconds)), task_id),
            )
            con.commit()

    retry_on_locked(write)


async def aextend_compute_lease(db: ComputeDB, task_id: int, seconds: int) -> None:
    """异步延租；语义同 :func:`extend_compute_lease`。"""
    async with db.aconnect() as con:
        await con.execute(
            "UPDATE compute_jobs SET lease_expires_at=? "
            "WHERE id=? AND state IN ('running', 'cancel_requested')",
            (time.time() + max(10, int(seconds)), task_id),
        )
        await con.commit()


def _compute_job_failure_refusal(job: Mapping[str, Any]) -> str | None:
    """Shared facts required before controller-side orphan failure."""
    from cloudra.infra.compute_utils import calc_lock_path, guard_lock_path
    from cloudra.infra.flocks import is_lock_held

    task_id = int(job["id"])
    workdir = os.path.dirname(job.get("path") or "")
    if workdir and os.path.isdir(os.path.join(workdir, ".cloudra")):
        for lock_path in (guard_lock_path(workdir, task_id), calc_lock_path(workdir, task_id)):
            if os.path.isfile(lock_path) and is_lock_held(lock_path):
                return f"job {task_id} still holds a calculator or guard lock; failure was not recorded"
    if (job.get("scheduler") or "local") != "local" and job.get("scheduler_job_id"):
        return (
            f"job {task_id} has a submitted remote/scheduler execution; "
            "local lock absence cannot establish its exit; leave finalization to its execution poller"
        )
    return None


def reap_exhausted_compute_leases(
    db: ComputeDB,
    *,
    max_attempts: int = 3,
) -> list[int]:
    """Fail expired compute jobs that consumed their retry budget; 返回被 reap 的 id。

    存活以 flock 为准：guard 或 calculator 仍持锁的作业不算死，即使租约过期
    也不落 failed。已提交的远端作业由其 poller 确认，不能凭本机无锁判死。
    """
    now = time.time()
    compute_ids: list[int] = []

    def write() -> None:
        with db.connect() as con:
            candidates = con.execute(
                f"""SELECT {_SELECT_COLUMNS} FROM compute_jobs WHERE state='running'
                AND lease_expires_at<? AND COALESCE(attempt_count, 0)>=?""",
                (now, max_attempts),
            ).fetchall()
            dead = [
                int(row[0])
                for row in candidates
                if _compute_job_failure_refusal(_row_dict(row)) is None
            ]
            if not dead:
                return
            compute_ids.extend(dead)
            con.execute(
                f"""UPDATE compute_jobs SET state='failed', end_timestamp=?,
                last_error='worker lease retry budget exhausted'
                WHERE state='running' AND id IN ({",".join("?" * len(dead))})""",
                (now, *dead),
            )
            con.commit()

    retry_on_locked(write)
    # 终态已落库：由 ComputeNotifyBroker 轮询补投，不再发进程间事件。
    return compute_ids


# ---------------------------------------------------------------------------
# 取消请求（执行端确认退出后才写终态）
# ---------------------------------------------------------------------------

def request_compute_cancellations_in_transaction(
    con, job_ids: Sequence[int], *, reason: str,
) -> dict[str, int]:
    """Request cancellation under the caller's transaction; never signal execution."""
    counts = {"ready_cancelled": 0, "cancel_requested": 0}
    if not job_ids:
        return counts
    placeholders = ",".join("?" for _ in job_ids)
    cur = con.execute(
        "UPDATE compute_jobs SET state='cancelled', end_timestamp=?, last_error=? "
        f"WHERE state='ready' AND id IN ({placeholders})",
        (time.time(), reason[:500], *job_ids),
    )
    counts["ready_cancelled"] = cur.rowcount
    cur = con.execute(
        "UPDATE compute_jobs SET state='cancel_requested', last_error=? "
        f"WHERE state='running' AND id IN ({placeholders})",
        (reason[:500], *job_ids),
    )
    counts["cancel_requested"] = cur.rowcount
    return counts


async def arequest_compute_job_cancellation(
    db: ComputeDB, task_id: int, *, project_id: str, reason: str,
) -> dict[str, Any]:
    """Cancel one project-owned job; running work awaits its execution owner."""
    reason = reason.strip()
    if not reason:
        raise ValueError("cancellation reason is required")
    if not project_id or not await asyncio.to_thread(_db_ready, db):
        raise LookupError("compute job not found")

    def write() -> dict[str, Any]:
        with db.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            row = con.execute(
                "SELECT state FROM compute_jobs WHERE id=? AND conversation_id=?",
                (task_id, project_id),
            ).fetchone()
            if row is None:
                raise LookupError("compute job not found")
            previous = row[0]
            request_compute_cancellations_in_transaction(con, [task_id], reason=reason)
            state = con.execute("SELECT state FROM compute_jobs WHERE id=?", (task_id,)).fetchone()[0]
            con.commit()
        success = state in {"cancelled", "cancel_requested"}
        if state == "cancel_requested":
            message = "Cancellation requested; the execution owner must confirm that the calculation has exited."
        elif state == "cancelled":
            message = "Job is cancelled."
        else:
            message = f"Job is already terminal ({state}); its result was not changed."
        return dict(is_success=success, job_id=task_id, previous_state=previous, state=state, message=message)

    return await asyncio.to_thread(retry_on_locked, write)


async def acancel_project_compute_jobs(
    db: ComputeDB, project_ids: Sequence[str], *, reason: str,
) -> dict[str, int]:
    """Request cancellation only for the supplied projects (explicit batch stop)."""
    if not project_ids or not await asyncio.to_thread(_db_ready, db):
        return {"ready_cancelled": 0, "cancel_requested": 0}

    def write() -> dict[str, int]:
        with db.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            placeholders = ",".join("?" for _ in project_ids)
            ids = [row[0] for row in con.execute(
                "SELECT id FROM compute_jobs WHERE state IN ('ready', 'running') "
                f"AND conversation_id IN ({placeholders})", tuple(project_ids),
            )]
            counts = request_compute_cancellations_in_transaction(con, ids, reason=reason)
            con.commit()
            return counts

    return await asyncio.to_thread(retry_on_locked, write)


async def acancel_all_compute_jobs(db: ComputeDB) -> dict[str, int]:
    """取消排队作业，并向所有运行中作业发出账本取消请求。

    running → cancel_requested 保留容量占用；只有执行端确认计算退出才能
    落 cancelled。控制面不发信号。中央库不存在时返回全零且不建库。
    """
    counts = {"ready_cancelled": 0, "cancel_requested": 0}
    if not await asyncio.to_thread(_db_ready, db):
        return counts
    def write() -> dict[str, int]:
        with db.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            ids = [row[0] for row in con.execute(
                "SELECT id FROM compute_jobs WHERE state IN ('ready', 'running')",
            )]
            result = request_compute_cancellations_in_transaction(con, ids, reason="cancelled by cancel-all")
            con.commit()
            return result

    return await asyncio.to_thread(retry_on_locked, write)


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
    async def write() -> bool:
        async with db.aconnect() as con:
            cur = await con.execute(sql, (state, time.time(), last_error, task_id))
            await con.commit()
            return cur.rowcount == 1

    return await aretry_on_locked(write)


async def afail_compute_job(db: ComputeDB, task_id: int, message: str) -> bool:
    """Fail an unowned orphan/startup error; held locks/submitted remote jobs refuse.

    False means the CAS state is no longer ready/running. A refusal explains why
    execution is still protected; neither its lease nor its review is changed.
    """
    def write() -> bool:
        with db.connect() as con:
            row = con.execute(
                f"SELECT {_SELECT_COLUMNS} FROM compute_jobs WHERE id=? AND state IN ('ready', 'running')",
                (task_id,),
            ).fetchone()
            if row is None:
                return False
            refusal = _compute_job_failure_refusal(_row_dict(row))
            if refusal is not None:
                raise ValueError(refusal)
            cur = con.execute(
                "UPDATE compute_jobs SET state='failed', end_timestamp=?, "
                "last_error=?, lease_expires_at=0 WHERE id=? AND state IN ('ready', 'running')",
                (time.time(), message[:500], task_id),
            )
            con.commit()
            return cur.rowcount == 1

    return await asyncio.to_thread(retry_on_locked, write)


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

def mark_slurm_submitted(
    db: ComputeDB, task_id: int, scheduler_job_id: str, script_path: str = ""
) -> None:
    """sbatch 成功（或对账按 job-name 找回）后回写 Slurm 句柄并置 PENDING。"""

    def write() -> None:
        with db.connect() as con:
            con.execute(
                """UPDATE compute_jobs SET scheduler_job_id=?, scheduler_script=?,
                scheduler_state='PENDING', start_timestamp=? WHERE id=?""",
                (scheduler_job_id, script_path, time.time(), task_id),
            )
            con.commit()

    retry_on_locked(write)


async def amark_slurm_submitted(
    db: ComputeDB, task_id: int, scheduler_job_id: str, script_path: str
) -> None:
    """sbatch 成功后回写 Slurm 句柄（job id/脚本路径）并置 PENDING。"""
    await asyncio.to_thread(mark_slurm_submitted, db, task_id, scheduler_job_id, script_path)


async def aupdate_scheduler_state(db: ComputeDB, task_id: int, scheduler_state: str) -> None:
    """sacct 轮询到的 Slurm 侧状态回写。"""
    async with db.aconnect() as con:
        await con.execute(
            "UPDATE compute_jobs SET scheduler_state=? WHERE id=?",
            (scheduler_state, task_id),
        )
        await con.commit()


def cancel_compute_job(db: ComputeDB, task_id: int) -> bool:
    """执行端确认计算退出（或确认尚未启动）后，落 cancelled。

    只覆盖 running / cancel_requested，不得把 done/failed 改成 cancelled。
    """
    def write() -> bool:
        with db.connect() as con:
            cur = con.execute(
                """UPDATE compute_jobs SET state='cancelled',
                scheduler_state='CANCELLED', end_timestamp=?
                WHERE id=? AND state IN ('running', 'cancel_requested')""",
                (time.time(), task_id),
            )
            con.commit()
            return cur.rowcount == 1

    return retry_on_locked(write)


async def acancel_compute_job(db: ComputeDB, task_id: int) -> None:
    """执行端确认取消完成后落 cancelled；发出停止请求本身不算完成。

    只覆盖 running / cancel_requested，不得把 done/failed 改成 cancelled。
    """
    await asyncio.to_thread(cancel_compute_job, db, task_id)


# ---------------------------------------------------------------------------
# 完成通知（ComputeNotifyBroker）
# ---------------------------------------------------------------------------

def mark_notified(db: ComputeDB, task_id: int) -> None:
    """投递完成后落 notified_at——去重只认它（notified_at IS NULL 过滤）。"""

    def write() -> None:
        with db.connect() as con:
            con.execute(
                "UPDATE compute_jobs SET notified_at=? WHERE id=? AND notified_at IS NULL",
                (time.time(), task_id),
            )
            con.commit()

    retry_on_locked(write)
