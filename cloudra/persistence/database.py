"""Conversation-scoped SQLite 数据库管理。

本模块提供 ``ConversationDB``（会话级 ``conversations/<id>/tasks/database.db``）
与 ``ComputeDB``（中央计算作业库 ``data_dir/compute.db``）作为数据库路径、
初始化、连接参数的唯一事实来源。所有需要访问 Cloudra 状态数据库的代码都应
通过这两个类，避免在多处硬编码路径或连接参数。
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import random
import re
import sqlite3
import threading
import time
import traceback
from typing import Awaitable, Callable, Optional, TypeVar

import aiosqlite

from cloudra.persistence import paths
from cloudra.persistence.paths import PathLike

logger = logging.getLogger(__name__)

DEFAULT_BUSY_TIMEOUT = 60.0
DEFAULT_LOCK_RETRIES = 4
SCHEMA_VERSION = 17
_T = TypeVar("_T")

_warned_sync_sites: set[str] = set()
_init_locks_guard = threading.Lock()
_init_locks: dict[str, threading.Lock] = {}


def _lock_for_init(path: str) -> threading.Lock:
    with _init_locks_guard:
        lock = _init_locks.get(path)
        if lock is None:
            lock = threading.Lock()
            _init_locks[path] = lock
        return lock


def _check_sync_on_loop(kind: str) -> None:
    """同步 SQLite 调用不得在事件循环线程上执行。

    busy 等待会冻结整个事件循环，使同进程 aiosqlite 连接上的未提交写
    永远无法 commit，曾造成跨进程 5 分钟级 "database is locked" 死锁。
    默认每个调用点告警一次；CLOUDRA_DB_SYNC_ON_LOOP=raise 时抛错
    （开发/调试用），=off 时完全关闭（测试夹具等确知安全的场景）。
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return  # 无 running loop：守护线程 / CLI / 测试等同步上下文，合法
    policy = os.environ.get("CLOUDRA_DB_SYNC_ON_LOOP", "warn").lower()
    if policy == "off":
        return
    caller = traceback.extract_stack(limit=3)[0]
    site = f"{caller.filename}:{caller.lineno}"
    msg = (
        f"sync SQLite {kind} on the asyncio event-loop thread at {site}; "
        "use the async variant or offload via asyncio.to_thread "
        "(set CLOUDRA_DB_SYNC_ON_LOOP=off to disable this guard)"
    )
    if policy == "raise":
        raise RuntimeError(msg)
    if site not in _warned_sync_sites:
        _warned_sync_sites.add(site)
        logger.warning(msg)


def _is_locked_error(exc: BaseException) -> bool:
    return isinstance(exc, sqlite3.OperationalError) and (
        "locked" in str(exc).lower() or "busy" in str(exc).lower()
    )


def retry_on_locked(
    operation: Callable[[], _T],
    *,
    retries: int = DEFAULT_LOCK_RETRIES,
    base_delay: float = 0.25,
) -> _T:
    """Retry a complete short SQLite operation when another writer owns the lock."""
    _check_sync_on_loop("write (retry_on_locked)")
    for attempt in range(retries + 1):
        try:
            return operation()
        except sqlite3.OperationalError as exc:
            if not _is_locked_error(exc) or attempt >= retries:
                raise
            time.sleep(base_delay * (2**attempt) + random.uniform(0, base_delay))
    raise RuntimeError("unreachable")


async def aretry_on_locked(
    operation: Callable[[], Awaitable[_T]],
    *,
    retries: int = DEFAULT_LOCK_RETRIES,
    base_delay: float = 0.25,
) -> _T:
    """Async counterpart of :func:`retry_on_locked`."""
    for attempt in range(retries + 1):
        try:
            return await operation()
        except sqlite3.OperationalError as exc:
            if not _is_locked_error(exc) or attempt >= retries:
                raise
            await asyncio.sleep(base_delay * (2**attempt) + random.uniform(0, base_delay))
    raise RuntimeError("unreachable")


class ConversationDB:
    """单个 conversation 的 SQLite 状态数据库。

    负责：
    1. 按 ``data_dir/conversations/<conv_id>/tasks/database.db`` 生成唯一路径
    2. 确保目录存在并初始化表结构
    3. 统一 WAL 模式、busy_timeout 等连接参数
    4. 提供同步/异步连接上下文
    """

    def __init__(self, conversation_id: Optional[str] = None, data_dir: Optional[PathLike] = None):
        self.conversation_id = conversation_id or "default"
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", self.conversation_id):
            raise ValueError("无效的 conversation_id")
        # data_dir 覆盖仅供测试/多实例场景注入；默认在构造时经 paths 惰性解析配置
        self.data_dir = data_dir
        self.path = str(paths.conversation_db_path(self.conversation_id, data_dir=data_dir))

    @classmethod
    def from_path(cls, path: str) -> "ConversationDB":
        """从已有路径构造 ConversationDB 实例（不验证 conversation_id）。"""
        instance = cls.__new__(cls)
        instance.conversation_id = ""
        instance.data_dir = None
        instance.path = path
        return instance

    def ensure_dir(self) -> "ConversationDB":
        """确保数据库所在目录存在。"""
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        return self

    def init(self) -> "ConversationDB":
        """初始化数据库：建目录、建表、启用 WAL。"""
        _check_sync_on_loop("init")
        with _lock_for_init(self.path):
            return self._init_unlocked()

    def _init_unlocked(self) -> "ConversationDB":
        self.ensure_dir()
        # journal_mode is persistent.  Switching it on every connection needs a
        # stronger lock and creates avoidable contention between worker processes.
        # 只在当前不是 WAL 时才切换：切换需要更强的锁，多进程并发时
        # 无谓的重复切换是 "database is locked" 的主要来源。
        with contextlib.closing(
            sqlite3.connect(self.path, timeout=DEFAULT_BUSY_TIMEOUT)
        ) as con:
            con.execute(f"PRAGMA busy_timeout={int(DEFAULT_BUSY_TIMEOUT * 1000)};")
            row = con.execute("PRAGMA journal_mode;").fetchone()
            if not row or str(row[0]).lower() != "wal":
                con.execute("PRAGMA journal_mode=WAL;")
            con.commit()
        with self.connect() as con:
            cur = con.cursor()
            cur.execute(_CREATE_SESSION)
            cur.execute(_CREATE_SESSION_EVENTS)
            cur.execute(_CREATE_ARTIFACTS)
            cur.execute(_CREATE_ARTIFACT_DOWNLOAD_TOKENS)
            cur.execute(_CREATE_DAG_GRAPHS)
            cur.execute(_CREATE_DAG_SPECIES)
            cur.execute(_CREATE_DAG_NODES)
            cur.execute(_CREATE_DAG_EDGES)
            cur.execute(_CREATE_DAG_EVIDENCE_BINDINGS)
            cur.execute(_CREATE_DAG_LINKS)
            cur.execute(_CREATE_DAG_EVIDENCE)
            cur.execute(_CREATE_DAG_EVIDENCE_FACTS)
            cur.execute(_CREATE_DAG_MUTATIONS)
            cur.execute(_CREATE_DAG_COVERAGE)
            cur.execute(_CREATE_DAG_DELIVERY_DISPOSITIONS)
            cur.execute(_CREATE_DAG_CALL_REVIEWS)
            cur.execute(_CREATE_DAG_CALL_REVIEWS_CALL_INDEX)
            cur.execute(_CREATE_DAG_CALL_REVIEWS_JOB_INDEX)
            cur.execute(_CREATE_DAG_DRAFTS)
            cur.execute(_CREATE_DAG_REVIEW_REQUESTS)
            cur.execute(_CREATE_DAG_REVIEW_DECISIONS)
            cur.execute(_CREATE_DAG_REVIEW_NOTIFICATIONS)
            cur.execute(_CREATE_ARTIFACTS_INDEX)
            cur.execute(_CREATE_SCHEMA_MIGRATIONS)
            self._migrate_session_schema(cur)
            self._migrate_related_schema(cur)
            cur.execute(
                "INSERT OR REPLACE INTO schema_migrations (version, applied_at) VALUES (?, datetime('now'))",
                (SCHEMA_VERSION,),
            )
            con.commit()
        return self

    def migrate_if_needed(self) -> bool:
        """Upgrade an existing database once; return False when it does not exist.

        Read paths use this before selecting newly added columns. Checking the
        version is read-only and avoids turning every TUI refresh into a schema
        write transaction.
        """
        if not os.path.isfile(self.path):
            return False
        try:
            with contextlib.closing(
                sqlite3.connect(self.path, timeout=DEFAULT_BUSY_TIMEOUT)
            ) as con:
                row = con.execute(
                    "SELECT MAX(version) FROM schema_migrations"
                ).fetchone()
                version = int(row[0] or 0) if row else 0
        except (sqlite3.Error, TypeError, ValueError):
            version = 0
        if version < SCHEMA_VERSION:
            self.init()
        return True

    def ensure_schema(self) -> "ConversationDB":
        """幂等确保数据库处于最新 schema：既有库升级、新库建表。

        旧库可能缺新版本才引入的表族（如 dag_review_*），而 write/read 路径
        不能假设调用方先 init()；统一经此入口补齐（CREATE IF NOT EXISTS 幂等）。
        """
        if os.path.isfile(self.path):
            self.migrate_if_needed()
        else:
            self.init()
        return self

    @contextlib.contextmanager
    def connect(self, timeout: float = DEFAULT_BUSY_TIMEOUT):
        """返回统一配置且退出时显式关闭的同步 SQLite 连接上下文。"""
        _check_sync_on_loop("connect")
        self.ensure_dir()
        con = sqlite3.connect(self.path, timeout=timeout)
        try:
            cur = con.cursor()
            cur.execute(f"PRAGMA busy_timeout={int(timeout * 1000)};")
            cur.execute("PRAGMA synchronous=NORMAL;")
            # 保留 sqlite3.Connection 原有的提交/回滚上下文语义。
            with con:
                yield con
        finally:
            con.close()

    @contextlib.asynccontextmanager
    async def aconnect(self, timeout: float = DEFAULT_BUSY_TIMEOUT):
        """返回一个统一配置 busy_timeout 的异步 SQLite 连接上下文。"""
        self.ensure_dir()
        con = await aiosqlite.connect(self.path, timeout=timeout)
        try:
            await con.execute(f"PRAGMA busy_timeout={int(timeout * 1000)};")
            await con.execute("PRAGMA synchronous=NORMAL;")
            yield con
        finally:
            await con.close()

    async def ainit(self) -> "ConversationDB":
        """异步初始化数据库。"""
        self.ensure_dir()
        async with self.aconnect() as con:
            # 与 init() 同理：journal_mode 是持久设置，已是 WAL 就不再切换，
            # 避免多进程并发时重复切换引发的锁竞争。
            cur = await con.execute("PRAGMA journal_mode;")
            row = await cur.fetchone()
            if not row or str(row[0]).lower() != "wal":
                await con.execute("PRAGMA journal_mode=WAL;")
            cur = await con.cursor()
            await cur.execute(_CREATE_SESSION)
            await cur.execute(_CREATE_SESSION_EVENTS)
            await cur.execute(_CREATE_ARTIFACTS)
            await cur.execute(_CREATE_ARTIFACT_DOWNLOAD_TOKENS)
            await cur.execute(_CREATE_DAG_GRAPHS)
            await cur.execute(_CREATE_DAG_SPECIES)
            await cur.execute(_CREATE_DAG_NODES)
            await cur.execute(_CREATE_DAG_EDGES)
            await cur.execute(_CREATE_DAG_EVIDENCE_BINDINGS)
            await cur.execute(_CREATE_DAG_LINKS)
            await cur.execute(_CREATE_DAG_EVIDENCE)
            await cur.execute(_CREATE_DAG_EVIDENCE_FACTS)
            await cur.execute(_CREATE_DAG_MUTATIONS)
            await cur.execute(_CREATE_DAG_COVERAGE)
            await cur.execute(_CREATE_DAG_DELIVERY_DISPOSITIONS)
            await cur.execute(_CREATE_DAG_CALL_REVIEWS)
            await cur.execute(_CREATE_DAG_CALL_REVIEWS_CALL_INDEX)
            await cur.execute(_CREATE_DAG_CALL_REVIEWS_JOB_INDEX)
            await cur.execute(_CREATE_DAG_DRAFTS)
            await cur.execute(_CREATE_DAG_REVIEW_REQUESTS)
            await cur.execute(_CREATE_DAG_REVIEW_DECISIONS)
            await cur.execute(_CREATE_DAG_REVIEW_NOTIFICATIONS)
            await cur.execute(_CREATE_ARTIFACTS_INDEX)
            await cur.execute(_CREATE_SCHEMA_MIGRATIONS)
            await self._amigrate_session_schema(cur)
            await self._amigrate_related_schema(cur)
            await cur.execute(
                "INSERT OR REPLACE INTO schema_migrations (version, applied_at) VALUES (?, datetime('now'))",
                (SCHEMA_VERSION,),
            )
            await con.commit()
        return self

    @staticmethod
    def _add_column(cur, table: str, name: str, definition: str) -> None:
        """ALTER ADD COLUMN, ignoring a concurrent duplicate-column race."""
        try:
            cur.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")
        except sqlite3.OperationalError as exc:
            if "duplicate column" not in str(exc).lower():
                raise

    @staticmethod
    async def _aadd_column(cur, table: str, name: str, definition: str) -> None:
        try:
            await cur.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")
        except sqlite3.OperationalError as exc:
            if "duplicate column" not in str(exc).lower():
                raise

    @staticmethod
    def _migrate_session_schema(cur) -> None:
        """为旧数据库补齐 Session 元数据列，不删除已有记录。"""
        existing = {row[1] for row in cur.execute("PRAGMA table_info(session)").fetchall()}
        for name, definition in _SESSION_EXTRA_COLUMNS.items():
            if name not in existing:
                ConversationDB._add_column(cur, "session", name, definition)

    @staticmethod
    async def _amigrate_session_schema(cur) -> None:
        await cur.execute("PRAGMA table_info(session)")
        existing = {row[1] for row in await cur.fetchall()}
        for name, definition in _SESSION_EXTRA_COLUMNS.items():
            if name not in existing:
                await ConversationDB._aadd_column(cur, "session", name, definition)

    @staticmethod
    def _migrate_related_schema(cur) -> None:
        for table, columns in _RELATED_EXTRA_COLUMNS.items():
            existing = {row[1] for row in cur.execute(f"PRAGMA table_info({table})").fetchall()}
            for name, definition in columns.items():
                if name not in existing:
                    ConversationDB._add_column(cur, table, name, definition)
        ConversationDB._migrate_dag_evidence_bindings(cur)
        ConversationDB._migrate_dag_evidence_source_keys(cur)
        # 反查索引依赖迁移列，必须建在列迁移之后。
        cur.execute(_CREATE_DAG_EVIDENCE_CALL_INDEX)
        cur.execute(_CREATE_DAG_EVIDENCE_JOB_INDEX)

    @staticmethod
    async def _amigrate_related_schema(cur) -> None:
        for table, columns in _RELATED_EXTRA_COLUMNS.items():
            await cur.execute(f"PRAGMA table_info({table})")
            existing = {row[1] for row in await cur.fetchall()}
            for name, definition in columns.items():
                if name not in existing:
                    await ConversationDB._aadd_column(cur, table, name, definition)
        await ConversationDB._amigrate_dag_evidence_bindings(cur)
        await ConversationDB._amigrate_dag_evidence_source_keys(cur)
        await cur.execute(_CREATE_DAG_EVIDENCE_CALL_INDEX)
        await cur.execute(_CREATE_DAG_EVIDENCE_JOB_INDEX)

    @staticmethod
    def evidence_source_keys(payload: str) -> tuple[str | None, str | None] | None:
        """从 evidence payload 提取反查键；payload 不可解析返回 None
        （保持 NULL 的 legacy 状态），可解析但无键返回 ("" , "")。"""
        try:
            data = json.loads(payload)
        except (ValueError, TypeError):
            return None
        if not isinstance(data, dict):
            return None
        tool_call_id = data.get("tool_call_id")
        compute_job_id = data.get("compute_job_id")
        return (
            str(tool_call_id) if tool_call_id else "",
            str(compute_job_id) if compute_job_id else "",
        )

    @staticmethod
    def _migrate_dag_evidence_source_keys(cur) -> None:
        """旧证据行反查键回填：只更新索引列，不改写 payload/hash；
        可解析但无键的行写空串哨兵（不再重复扫描）；不可解析行保持 NULL
        （legacy 来源状态，读取侧对 NULL 行回退 payload 扫描，语义与
        迁移前一致）。逐批进行，本批无进展即停。"""
        while True:
            rows = cur.execute(
                "SELECT evidence_id, payload FROM dag_evidence "
                "WHERE tool_call_id IS NULL AND compute_job_id IS NULL LIMIT 200"
            ).fetchall()
            if not rows:
                return
            progressed = False
            for evidence_id, payload in rows:
                keys = ConversationDB.evidence_source_keys(payload)
                if keys is None:
                    continue
                cur.execute(
                    "UPDATE dag_evidence SET tool_call_id = ?, compute_job_id = ? "
                    "WHERE evidence_id = ?",
                    (keys[0], keys[1], evidence_id),
                )
                progressed = True
            if not progressed:
                return

    @staticmethod
    async def _amigrate_dag_evidence_source_keys(cur) -> None:
        while True:
            await cur.execute(
                "SELECT evidence_id, payload FROM dag_evidence "
                "WHERE tool_call_id IS NULL AND compute_job_id IS NULL LIMIT 200"
            )
            rows = await cur.fetchall()
            if not rows:
                return
            progressed = False
            for evidence_id, payload in rows:
                keys = ConversationDB.evidence_source_keys(payload)
                if keys is None:
                    continue
                await cur.execute(
                    "UPDATE dag_evidence SET tool_call_id = ?, compute_job_id = ? "
                    "WHERE evidence_id = ?",
                    (keys[0], keys[1], evidence_id),
                )
                progressed = True
            if not progressed:
                return

    @staticmethod
    def _migrate_dag_evidence_bindings(cur) -> None:
        """一次性回填：v11 及之前证据引用内联在 dag_nodes/dag_edges 的
        refs JSON 列里，这里展开进关联表。仅在关联表为空时执行；
        主键 + INSERT OR IGNORE 保证重复 init 不重复插。"""
        if cur.execute("SELECT 1 FROM dag_evidence_bindings LIMIT 1").fetchone():
            return
        for target_type, table, id_col in (
            ("node", "dag_nodes", "node_id"),
            ("edge", "dag_edges", "edge_id"),
        ):
            rows = cur.execute(
                f"SELECT graph_id, {id_col}, refs, payload, created_revision "
                f"FROM {table} WHERE refs NOT IN ('[]', '')"
            ).fetchall()
            for row in rows:
                for params in ConversationDB._expand_inline_refs(target_type, row):
                    cur.execute(_INSERT_DAG_EVIDENCE_BINDING, params)

    @staticmethod
    async def _amigrate_dag_evidence_bindings(cur) -> None:
        await cur.execute("SELECT 1 FROM dag_evidence_bindings LIMIT 1")
        if await cur.fetchone():
            return
        for target_type, table, id_col in (
            ("node", "dag_nodes", "node_id"),
            ("edge", "dag_edges", "edge_id"),
        ):
            await cur.execute(
                f"SELECT graph_id, {id_col}, refs, payload, created_revision "
                f"FROM {table} WHERE refs NOT IN ('[]', '')"
            )
            for row in await cur.fetchall():
                for params in ConversationDB._expand_inline_refs(target_type, row):
                    await cur.execute(_INSERT_DAG_EVIDENCE_BINDING, params)

    @staticmethod
    def _expand_inline_refs(target_type: str, row) -> "list[tuple]":
        """把一行的内联 refs JSON 展开为关联表插入参数（同步/异步迁移共用）。"""
        graph_id, target_id, refs_json, payload_json, created_revision = row
        try:
            refs = json.loads(refs_json)
        except (TypeError, ValueError):
            return []
        if not isinstance(refs, list):
            return []
        # evidence_role 历史上只存在于变更日志的 op 里，回放代价大，留 NULL；
        # derived_level 从 payload 里的 evidence_level 推（没有就 NULL）。
        derived_level = None
        try:
            level = json.loads(payload_json).get("evidence_level")
        except (TypeError, ValueError, AttributeError):
            level = None
        if isinstance(level, str):
            derived_level = level
        return [
            (
                graph_id,
                target_type,
                str(target_id),
                str(ref["ref_id"]),
                derived_level,
                created_revision,
            )
            for ref in refs
            if isinstance(ref, dict) and ref.get("ref_id")
        ]


# SQL 建表语句统一放在这里，作为唯一表结构定义。
class ComputeDB:
    """中央计算作业库（``data_dir/compute.db``），compute_jobs 表的唯一宿主。

    提交（submit_compute_job）、认领（调度守护）、guard/Slurm 终态 CAS、
    完成通知轮询全部打这一份库。与 ConversationDB 同风格的连接参数
    （WAL + busy_timeout），但**无 schema 迁移**：beta 阶段 schema 新建即新版。
    """

    def __init__(self, data_dir: Optional[PathLike] = None):
        # data_dir 覆盖仅供测试/多实例场景注入；默认在构造时经 paths 惰性解析配置
        self.data_dir = data_dir
        self.path = str(paths.compute_db_path(data_dir))
        # 每实例一次的懒 schema 自愈标记：读路径（路由/轮询）只构造实例后
        # 直接 aconnect，从不 init/ainit——旧库缺新列时首批查询即
        # OperationalError（GH #40 线程，实机 /compute/jobs 500）。
        self._schema_checked = False

    @classmethod
    def from_path(cls, path: str) -> "ComputeDB":
        """从已有路径构造 ComputeDB 实例（guard/Slurm 子进程拿显式 --db_path）。"""
        instance = cls.__new__(cls)
        instance.data_dir = None
        instance.path = path
        instance._schema_checked = False
        return instance

    def ensure_dir(self) -> "ComputeDB":
        """确保数据库所在目录存在。"""
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        return self

    def _ensure_compute_schema(self) -> None:
        """连接前的一次性 schema 自愈：建表 + 幂等补列（与 init/ainit 同一套）。

        init/ainit 里的建表与迁移对只读消费方从不生效，故在首个连接上
        执行同一套幂等逻辑；每实例恰好一次（``_schema_checked``）。
        """
        with contextlib.closing(
            sqlite3.connect(self.path, timeout=DEFAULT_BUSY_TIMEOUT)
        ) as con:
            con.execute(f"PRAGMA busy_timeout={int(DEFAULT_BUSY_TIMEOUT * 1000)};")
            cur = con.cursor()
            cur.execute(_CREATE_COMPUTE_JOBS)
            cur.execute(_CREATE_COMPUTE_JOBS_CLAIM_INDEX)
            cur.execute(_CREATE_COMPUTE_JOBS_NOTIFY_INDEX)
            self._migrate_compute_schema(cur)
            con.commit()

    def init(self) -> "ComputeDB":
        """初始化数据库：建目录、建表、启用 WAL。"""
        _check_sync_on_loop("init")
        with _lock_for_init(self.path):
            self.ensure_dir()
            # journal_mode 是持久设置：只在当前不是 WAL 时才切换，避免多进程
            # 并发时无谓的重复切换引发锁竞争（与 ConversationDB 同理）。
            with contextlib.closing(
                sqlite3.connect(self.path, timeout=DEFAULT_BUSY_TIMEOUT)
            ) as con:
                con.execute(f"PRAGMA busy_timeout={int(DEFAULT_BUSY_TIMEOUT * 1000)};")
                row = con.execute("PRAGMA journal_mode;").fetchone()
                if not row or str(row[0]).lower() != "wal":
                    con.execute("PRAGMA journal_mode=WAL;")
                con.commit()
            with self.connect() as con:
                cur = con.cursor()
                cur.execute(_CREATE_COMPUTE_JOBS)
                cur.execute(_CREATE_COMPUTE_JOBS_CLAIM_INDEX)
                cur.execute(_CREATE_COMPUTE_JOBS_NOTIFY_INDEX)
                self._migrate_compute_schema(cur)
                con.commit()
        return self

    async def ainit(self) -> "ComputeDB":
        """异步初始化数据库（语义同 :meth:`init`）。

        与 init() 共用同一把 per-path 进程内锁：compute.db 是全部 agent 共
        写的单库，两个并发 submit 同时 ainit 会在 WAL 切换上撞
        ``database is locked``（并发项目测试测红）。异步路径把 acquire 卸载
        到线程，绝不在事件循环上同步等锁。
        """
        self.ensure_dir()
        lock = _lock_for_init(self.path)
        await asyncio.to_thread(lock.acquire)
        try:
            async with self.aconnect() as con:
                cur = await con.execute("PRAGMA journal_mode;")
                row = await cur.fetchone()
                if not row or str(row[0]).lower() != "wal":
                    await con.execute("PRAGMA journal_mode=WAL;")
                await con.execute(_CREATE_COMPUTE_JOBS)
                await con.execute(_CREATE_COMPUTE_JOBS_CLAIM_INDEX)
                await con.execute(_CREATE_COMPUTE_JOBS_NOTIFY_INDEX)
                await self._amigrate_compute_schema(cur)
                await con.commit()
        finally:
            lock.release()
        return self

    @staticmethod
    def _migrate_compute_schema(cur) -> None:
        """为既有中央库补齐 compute_jobs 的新列（幂等；列迁移语法复用会话库的守卫）。"""
        for ddl in (*_CREATE_CONFORMER_TABLES, *_CREATE_EXPLORATION_TABLES, *_CREATE_TS_PIPELINE_TABLES):
            cur.execute(ddl)
        existing = {row[1] for row in cur.execute("PRAGMA table_info(compute_jobs)").fetchall()}
        for name, definition in _COMPUTE_JOB_EXTRA_COLUMNS.items():
            if name not in existing:
                ConversationDB._add_column(cur, "compute_jobs", name, definition)

    @staticmethod
    async def _amigrate_compute_schema(cur) -> None:
        for ddl in (*_CREATE_CONFORMER_TABLES, *_CREATE_EXPLORATION_TABLES, *_CREATE_TS_PIPELINE_TABLES):
            await cur.execute(ddl)
        await cur.execute("PRAGMA table_info(compute_jobs)")
        existing = {row[1] for row in await cur.fetchall()}
        for name, definition in _COMPUTE_JOB_EXTRA_COLUMNS.items():
            if name not in existing:
                await ConversationDB._aadd_column(cur, "compute_jobs", name, definition)

    @contextlib.contextmanager
    def connect(self, timeout: float = DEFAULT_BUSY_TIMEOUT):
        """返回统一配置且退出时显式关闭的同步 SQLite 连接上下文。"""
        _check_sync_on_loop("connect")
        self.ensure_dir()
        if not self._schema_checked:
            self._ensure_compute_schema()
            self._schema_checked = True
        con = sqlite3.connect(self.path, timeout=timeout)
        try:
            cur = con.cursor()
            cur.execute(f"PRAGMA busy_timeout={int(timeout * 1000)};")
            cur.execute("PRAGMA synchronous=NORMAL;")
            # 保留 sqlite3.Connection 原有的提交/回滚上下文语义。
            with con:
                yield con
        finally:
            con.close()

    @contextlib.asynccontextmanager
    async def aconnect(self, timeout: float = DEFAULT_BUSY_TIMEOUT):
        """返回一个统一配置 busy_timeout 的异步 SQLite 连接上下文。"""
        self.ensure_dir()
        if not self._schema_checked:
            await asyncio.to_thread(self._ensure_compute_schema)
            self._schema_checked = True
        con = await aiosqlite.connect(self.path, timeout=timeout)
        try:
            await con.execute(f"PRAGMA busy_timeout={int(timeout * 1000)};")
            await con.execute("PRAGMA synchronous=NORMAL;")
            yield con
        finally:
            await con.close()


# SQL 建表语句统一放在这里，作为唯一表结构定义。
_CREATE_SESSION = """
    CREATE TABLE IF NOT EXISTS session (
        session_id TEXT PRIMARY KEY,
        agent_id TEXT,
        agent_type TEXT,
        parent_session_id TEXT,
        query TEXT,
        state TEXT NOT NULL DEFAULT 'queued',
        result TEXT,
        error TEXT,
        pid INTEGER,
        worker_id TEXT,
        created_at TEXT,
        started_at TEXT,
        heartbeat_at TEXT,
        finished_at TEXT,
        exit_code INTEGER,
        node_id TEXT,
        workspace_id TEXT,
        working_directory TEXT,
        orchestration_mode TEXT NOT NULL DEFAULT 'standard',
        orchestration_config TEXT NOT NULL DEFAULT '{}'
    )
"""

_SESSION_EXTRA_COLUMNS = {
    "agent_id": "TEXT",
    "agent_type": "TEXT",
    "parent_session_id": "TEXT",
    "query": "TEXT",
    "error": "TEXT",
    "pid": "INTEGER",
    "worker_id": "TEXT",
    "created_at": "TEXT",
    "started_at": "TEXT",
    "heartbeat_at": "TEXT",
    "finished_at": "TEXT",
    "exit_code": "INTEGER",
    "node_id": "TEXT",
    "workspace_id": "TEXT",
    "working_directory": "TEXT",
    "orchestration_mode": "TEXT NOT NULL DEFAULT 'standard'",
    "orchestration_config": "TEXT NOT NULL DEFAULT '{}'",
}

_RELATED_EXTRA_COLUMNS = {
    "dag_mutations": {
        "session_id": "TEXT NOT NULL DEFAULT ''",
        "rationale": "TEXT NOT NULL DEFAULT ''",
        "base_revisions": "TEXT NOT NULL DEFAULT '{}'",
        "resulting_revisions": "TEXT NOT NULL DEFAULT '{}'",
        "accepted": "INTEGER NOT NULL DEFAULT 1",
        "rejection_code": "TEXT",
        "rejection_reason": "TEXT",
    },
    # delivery 元素的阶段契约（StageState 列表 JSON）；旧行为 '[]'，
    # 读取侧按 evidence_level 一次性映射（models.map_legacy_stages）。
    "dag_nodes": {
        "stages": "TEXT NOT NULL DEFAULT '[]'",
    },
    "dag_edges": {
        "stages": "TEXT NOT NULL DEFAULT '[]'",
    },
    "dag_call_reviews": {
        "source_path": "TEXT NOT NULL DEFAULT ''",
        "result_kind": "TEXT NOT NULL DEFAULT ''",
        "suggested_stage": "TEXT NOT NULL DEFAULT ''",
        # §5 显式送审：主张/理由/提交者/快照身份；旧行全部为空。
        "claim": "TEXT NOT NULL DEFAULT ''",
        "rationale": "TEXT NOT NULL DEFAULT ''",
        "submitter": "TEXT NOT NULL DEFAULT ''",
        "evidence_id": "TEXT NOT NULL DEFAULT ''",
        # 旧行无法可靠识别来源 ⇒ 一律 legacy_auto（不消费、审计保留）。
        "source": "TEXT NOT NULL DEFAULT 'legacy_auto'",
    },
    # 证据登记的反查键（Task 4）：新行写入时从 payload 提取；旧行由
    # _migrate_dag_evidence_source_keys 逐批回填，不可解析行保持 NULL。
    "dag_evidence": {
        "tool_call_id": "TEXT",
        "compute_job_id": "TEXT",
    },
    # 计算终态快照的来源路径（Task 4）：同名文件被覆盖 ⇒ hash 变化 ⇒
    # 新 artifact；同一路径同一内容复用既有 artifact，不重复拷贝。
    "artifacts": {
        "source_path": "TEXT NOT NULL DEFAULT ''",
    },
    # 草稿的交付契约（contract_version=2）：ClaimSpec JSON；空串=旧契约。
    "dag_drafts": {
        "claim_spec": "TEXT NOT NULL DEFAULT ''",
    },
    # 结构化审查请求的历史租约列（Task 7 review worker 已删除）：列保留供
    # 旧库读取，新代码不再写入/判定 owner/claim_token/lease。
    "dag_review_requests": {
        "owner": "TEXT",
        "claim_token": "INTEGER NOT NULL DEFAULT 0",
        "lease_expires_at": "TEXT",
    },
    # 裁决通知泛化（v17）：三类裁决共用同一投递通道；旧行默认
    # review_decision + 空 payload（渲染走 dag_review_decisions 查表）。
    "dag_review_notifications": {
        "kind": "TEXT NOT NULL DEFAULT 'review_decision'",
        "payload": "TEXT NOT NULL DEFAULT '{}'",
    },
}

# compute_jobs 只住在中央库（ComputeDB，data_dir/compute.db）；会话库不再建此表。
# 既有中央库的补列（幂等 ALTER）：建表语句只对新库生效，旧库靠这里升级。
# 必须与 _CREATE_COMPUTE_JOBS 的列定义保持同步——charge/multiplicity/xtb_*
# 入 DDL 时漏登此表，旧库首查即 OperationalError（GH #40 线程，
# 实机 /compute/jobs 500）。
_COMPUTE_JOB_EXTRA_COLUMNS = {
    # 多节点容量池（v2）：作业归属的注册节点，容量按它分池记账。
    "node_id": "TEXT",
    # xtb 显式任务参数（xtb 是 CLI 标志驱动，.xyz 不携带这些语义）
    "charge": "INTEGER NOT NULL DEFAULT 0",
    "multiplicity": "INTEGER NOT NULL DEFAULT 1",
    "xtb_task": "TEXT NOT NULL DEFAULT 'sp'",
    "xtb_solvent": "TEXT",
}

_CREATE_COMPUTE_JOBS = """
    CREATE TABLE IF NOT EXISTS compute_jobs(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        conversation_id TEXT NOT NULL,
        session_id TEXT,
        state TEXT,
        path TEXT,
        start_timestamp INTEGER,
        end_timestamp INTEGER DEFAULT -1,
        jobtype TEXT DEFAULT 'gaussian',
        -- 作业归属的注册节点（services/nodes.py 的 node_id）：容量按节点分池
        -- 记账的唯一依据；NULL 视为注册表的 default_node_id（旧行升级路径）。
        node_id TEXT,
        scheduler TEXT DEFAULT 'local',
        scheduler_options TEXT DEFAULT '{}',
        scheduler_job_id TEXT,
        scheduler_state TEXT,
        scheduler_script TEXT,
        last_error TEXT,
        lease_owner TEXT,
        lease_expires_at REAL,
        attempt_count INTEGER DEFAULT 0,
        -- 调度器：排队优先级与 agent 声明的资源申请（核心链路不解析输入文件）
        priority INTEGER NOT NULL DEFAULT 0,
        req_cpus INTEGER NOT NULL DEFAULT 1,
        req_memory_mb INTEGER,
        -- xtb 显式任务参数（xtb 是 CLI 标志驱动，.xyz 不携带这些语义）：
        -- submit 时校验入库，guard/Slurm 据此拼 --chrg/--uhf/--opt/--hess/
        -- --ohess/--alpb/--parallel，绝不回退裸单点
        charge INTEGER NOT NULL DEFAULT 0,
        multiplicity INTEGER NOT NULL DEFAULT 1,
        xtb_task TEXT NOT NULL DEFAULT 'sp',
        xtb_solvent TEXT,
        -- 观测/取证用进程号（存活判定的权威是 .cloudra/ 下的 flock，不读 PID）
        guard_pid INTEGER,
        calc_pid INTEGER,
        -- 完成通知投递标记（ComputeNotifyBroker 补投对账依据）
        notified_at REAL
    )
"""

_CREATE_COMPUTE_JOBS_CLAIM_INDEX = """
    CREATE INDEX IF NOT EXISTS idx_compute_jobs_claim
    ON compute_jobs(state, lease_expires_at)
"""

_CREATE_COMPUTE_JOBS_NOTIFY_INDEX = """
    CREATE INDEX IF NOT EXISTS idx_compute_jobs_notify
    ON compute_jobs(state, notified_at)
"""

_CREATE_SESSION_EVENTS = """
    CREATE TABLE IF NOT EXISTS session_events(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id TEXT NOT NULL,
        event_type TEXT NOT NULL,
        data TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL
    )
"""

_CREATE_ARTIFACTS = """
    CREATE TABLE IF NOT EXISTS artifacts(
        artifact_id TEXT PRIMARY KEY,
        session_id TEXT NOT NULL,
        name TEXT NOT NULL,
        mime_type TEXT NOT NULL,
        size INTEGER NOT NULL,
        sha256 TEXT NOT NULL,
        storage_path TEXT NOT NULL,
        source_path TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL
    )
"""

_CREATE_ARTIFACTS_INDEX = """
    CREATE INDEX IF NOT EXISTS idx_artifacts_session
    ON artifacts(session_id, created_at)
"""

_CREATE_ARTIFACT_DOWNLOAD_TOKENS = """
    CREATE TABLE IF NOT EXISTS artifact_download_tokens(
        token_hash TEXT PRIMARY KEY,
        artifact_id TEXT NOT NULL,
        expires_at TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
"""

_CREATE_DAG_GRAPHS = """
    CREATE TABLE IF NOT EXISTS dag_graphs(
        graph_id TEXT PRIMARY KEY,
        graph_kind TEXT NOT NULL UNIQUE CHECK(graph_kind IN ('process', 'delivery')),
        revision INTEGER NOT NULL DEFAULT 0 CHECK(revision >= 0),
        metadata TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
"""

_CREATE_DAG_SPECIES = """
    CREATE TABLE IF NOT EXISTS dag_species(
        species_id TEXT PRIMARY KEY,
        canonical_key TEXT NOT NULL UNIQUE,
        charge INTEGER NOT NULL,
        multiplicity INTEGER NOT NULL CHECK(multiplicity >= 1),
        identifiers TEXT NOT NULL DEFAULT '{}',
        metadata TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL
    )
"""

_CREATE_DAG_NODES = """
    CREATE TABLE IF NOT EXISTS dag_nodes(
        graph_id TEXT NOT NULL,
        node_id TEXT NOT NULL,
        node_type TEXT NOT NULL,
        label TEXT NOT NULL DEFAULT '',
        refs TEXT NOT NULL DEFAULT '[]',
        payload TEXT NOT NULL DEFAULT '{}',
        stages TEXT NOT NULL DEFAULT '[]',
        created_revision INTEGER NOT NULL,
        updated_revision INTEGER NOT NULL,
        PRIMARY KEY(graph_id, node_id),
        FOREIGN KEY(graph_id) REFERENCES dag_graphs(graph_id)
    )
"""

_CREATE_DAG_EDGES = """
    CREATE TABLE IF NOT EXISTS dag_edges(
        graph_id TEXT NOT NULL,
        edge_id TEXT NOT NULL,
        source_node_id TEXT NOT NULL,
        target_node_id TEXT NOT NULL,
        edge_type TEXT NOT NULL,
        label TEXT NOT NULL DEFAULT '',
        refs TEXT NOT NULL DEFAULT '[]',
        payload TEXT NOT NULL DEFAULT '{}',
        stages TEXT NOT NULL DEFAULT '[]',
        created_revision INTEGER NOT NULL,
        updated_revision INTEGER NOT NULL,
        PRIMARY KEY(graph_id, edge_id),
        FOREIGN KEY(graph_id) REFERENCES dag_graphs(graph_id)
    )
"""

_CREATE_DAG_EVIDENCE_BINDINGS = """
    CREATE TABLE IF NOT EXISTS dag_evidence_bindings(
        graph_id TEXT NOT NULL,
        target_type TEXT NOT NULL CHECK(target_type IN ('node', 'edge')),
        target_id TEXT NOT NULL,
        evidence_id TEXT NOT NULL,
        evidence_role TEXT,
        derived_level TEXT,
        created_revision INTEGER NOT NULL,
        PRIMARY KEY(graph_id, target_type, target_id, evidence_id),
        FOREIGN KEY(graph_id) REFERENCES dag_graphs(graph_id)
    )
"""

# 迁移回填专用：evidence_role 无历史来源，固定 NULL（见 _expand_inline_refs）。
_INSERT_DAG_EVIDENCE_BINDING = """
    INSERT OR IGNORE INTO dag_evidence_bindings(
        graph_id, target_type, target_id, evidence_id,
        evidence_role, derived_level, created_revision
    ) VALUES (?, ?, ?, ?, NULL, ?, ?)
"""

_CREATE_DAG_LINKS = """
    CREATE TABLE IF NOT EXISTS dag_links(
        link_id TEXT PRIMARY KEY,
        process_node_id TEXT NOT NULL,
        delivery_element_type TEXT NOT NULL CHECK(delivery_element_type IN ('node', 'edge')),
        delivery_element_id TEXT NOT NULL,
        payload TEXT NOT NULL DEFAULT '{}',
        created_revision INTEGER NOT NULL
    )
"""

_CREATE_DAG_EVIDENCE = """
    CREATE TABLE IF NOT EXISTS dag_evidence(
        evidence_id TEXT PRIMARY KEY,
        session_id TEXT NOT NULL,
        source_type TEXT NOT NULL,
        source_name TEXT NOT NULL,
        content_hash TEXT NOT NULL,
        payload TEXT NOT NULL,
        created_at TEXT NOT NULL,
        UNIQUE(source_type, source_name, content_hash)
    )
"""

# 证据登记反查索引（tool_call_id / compute_job_id 为可空列，见
# _RELATED_EXTRA_COLUMNS；旧行由 _migrate_dag_evidence_source_keys 回填，
# 不可解析行保持 NULL 的 legacy 状态，不改写 payload/hash）。
_CREATE_DAG_EVIDENCE_CALL_INDEX = """
    CREATE INDEX IF NOT EXISTS idx_dag_evidence_tool_call
    ON dag_evidence(tool_call_id)
"""

_CREATE_DAG_EVIDENCE_JOB_INDEX = """
    CREATE INDEX IF NOT EXISTS idx_dag_evidence_compute_job
    ON dag_evidence(compute_job_id)
"""

# 类型化证据事实（contract_version=2）：不可变 payload + adapter_version；
# dedup_key 保证"同一来源 + 同一实际尝试 + 同一解析版本"幂等。
_CREATE_DAG_EVIDENCE_FACTS = """
    CREATE TABLE IF NOT EXISTS dag_evidence_facts(
        fact_id TEXT PRIMARY KEY,
        check_name TEXT NOT NULL,
        outcome TEXT NOT NULL CHECK(outcome IN ('supports', 'refutes', 'inconclusive')),
        subject TEXT NOT NULL DEFAULT '{}',
        source_refs TEXT NOT NULL DEFAULT '[]',
        details TEXT NOT NULL DEFAULT '{}',
        adapter_version TEXT NOT NULL,
        dedup_key TEXT NOT NULL,
        created_at TEXT NOT NULL,
        UNIQUE(dedup_key)
    )
"""

_CREATE_DAG_CALL_REVIEWS_CALL_INDEX = """
    CREATE INDEX IF NOT EXISTS idx_dag_call_reviews_tool_call
    ON dag_call_reviews(tool_call_id)
"""

_CREATE_DAG_CALL_REVIEWS_JOB_INDEX = """
    CREATE INDEX IF NOT EXISTS idx_dag_call_reviews_compute_job
    ON dag_call_reviews(compute_job_id)
"""

_CREATE_DAG_MUTATIONS = """
    CREATE TABLE IF NOT EXISTS dag_mutations(
        mutation_id TEXT PRIMARY KEY,
        graph_id TEXT NOT NULL,
        base_revision INTEGER NOT NULL,
        resulting_revision INTEGER NOT NULL,
        actor_type TEXT NOT NULL,
        actor_id TEXT NOT NULL,
        session_id TEXT NOT NULL DEFAULT '',
        rationale TEXT NOT NULL DEFAULT '',
        base_revisions TEXT NOT NULL DEFAULT '{}',
        resulting_revisions TEXT NOT NULL DEFAULT '{}',
        operations TEXT NOT NULL,
        accepted INTEGER NOT NULL DEFAULT 1,
        rejection_code TEXT,
        rejection_reason TEXT,
        created_at TEXT NOT NULL,
        FOREIGN KEY(graph_id) REFERENCES dag_graphs(graph_id)
    )
"""

_CREATE_DAG_COVERAGE = """
    CREATE TABLE IF NOT EXISTS dag_coverage(
        graph_id TEXT PRIMARY KEY,
        revision INTEGER NOT NULL DEFAULT 0,
        coverage TEXT NOT NULL DEFAULT '{}',
        updated_at TEXT NOT NULL,
        FOREIGN KEY(graph_id) REFERENCES dag_graphs(graph_id)
    )
"""

_CREATE_DAG_DELIVERY_DISPOSITIONS = """
    CREATE TABLE IF NOT EXISTS dag_delivery_dispositions(
        disposition_id TEXT PRIMARY KEY,
        session_id TEXT NOT NULL,
        disposition TEXT NOT NULL CHECK(disposition IN ('complete', 'partial', 'user_terminated')),
        graph_revision INTEGER NOT NULL,
        report TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
"""

# CallReview 收件箱（D12）：仅追加/状态翻转，不经 DagEngine 版本化 mutation。
_CREATE_DAG_CALL_REVIEWS = """
    CREATE TABLE IF NOT EXISTS dag_call_reviews(
        review_id TEXT PRIMARY KEY,
        tool_call_id TEXT NOT NULL DEFAULT '',
        tool_name TEXT NOT NULL,
        is_success INTEGER NOT NULL DEFAULT 0,
        caller_session_id TEXT NOT NULL DEFAULT '',
        caller_role_id TEXT NOT NULL DEFAULT '',
        caller_legacy_id TEXT NOT NULL DEFAULT '',
        arguments_digest TEXT NOT NULL DEFAULT '',
        result_summary TEXT NOT NULL DEFAULT '',
        source_path TEXT NOT NULL DEFAULT '',
        result_kind TEXT NOT NULL DEFAULT '',
        compute_job_id TEXT,
        suggested_target_id TEXT,
        suggested_stage TEXT NOT NULL DEFAULT '',
        state TEXT NOT NULL DEFAULT 'pending'
            CHECK(state IN ('pending', 'reviewed', 'ignored')),
        created_at TEXT NOT NULL
    )
"""

# 机理草稿（D4）：mechanism_accepted = EXISTS(state='accepted')，随库存续。
_CREATE_DAG_DRAFTS = """
    CREATE TABLE IF NOT EXISTS dag_drafts(
        draft_id TEXT PRIMARY KEY,
        state TEXT NOT NULL DEFAULT 'open'
            CHECK(state IN ('open', 'accepted', 'rejected')),
        rationale TEXT NOT NULL DEFAULT '',
        operations TEXT NOT NULL,
        stage_contracts TEXT NOT NULL DEFAULT '{}',
        actor_id TEXT NOT NULL DEFAULT '',
        reject_reason TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL,
        decided_at TEXT
    )
"""

# 结构化审查请求/裁决（contract_version=2）：请求与 CallReview 收件箱正交，
# 一个请求可以带多目标、多证据与 proposal；裁决按 request+basis 幂等落账。
_CREATE_DAG_REVIEW_REQUESTS = """
    CREATE TABLE IF NOT EXISTS dag_review_requests(
        request_id TEXT PRIMARY KEY,
        kind TEXT NOT NULL CHECK(kind IN ('draft', 'evidence', 'exception', 'exit')),
        requester TEXT NOT NULL,
        target_ids TEXT NOT NULL DEFAULT '[]',
        question TEXT NOT NULL,
        supporting_refs TEXT NOT NULL DEFAULT '[]',
        counterevidence_refs TEXT NOT NULL DEFAULT '[]',
        proposal TEXT NOT NULL DEFAULT '{}',
        basis_fingerprint TEXT NOT NULL,
        state TEXT NOT NULL DEFAULT 'queued'
            CHECK(state IN ('queued', 'resolved', 'superseded')),
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
"""

_CREATE_DAG_REVIEW_DECISIONS = """
    CREATE TABLE IF NOT EXISTS dag_review_decisions(
        decision_id TEXT PRIMARY KEY,
        request_id TEXT NOT NULL,
        basis_fingerprint TEXT NOT NULL,
        verdict TEXT NOT NULL CHECK(verdict IN ('accept', 'reject', 'needs_evidence')),
        reason TEXT NOT NULL,
        evidence_refs TEXT NOT NULL DEFAULT '[]',
        findings TEXT NOT NULL DEFAULT '[]',
        next_action TEXT,
        claim_token INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL
    )
"""

# 审查裁决通知（Task 7）：subject 幂等，恢复后补投不重复影响流程。
# v17 泛化为三类裁决共用同一通道（flush_review_notifications 唯一投递口）：
# review_decision（结构化请求裁决，decision_id=decision_id，payload 为空、
# 文本由 dag_review_decisions 查得）、call_verdict（per-CallReview 裁决，
# decision_id=review_id）、draft_verdict（机理草稿裁决，decision_id=draft_id）。
# 后两类的渲染材料全在 payload JSON（裁决行本身不落 verdict 列）。
_CREATE_DAG_REVIEW_NOTIFICATIONS = """
    CREATE TABLE IF NOT EXISTS dag_review_notifications(
        notification_id TEXT PRIMARY KEY,
        kind TEXT NOT NULL DEFAULT 'review_decision'
            CHECK(kind IN ('review_decision', 'call_verdict', 'draft_verdict')),
        decision_id TEXT NOT NULL,
        request_id TEXT NOT NULL DEFAULT '',
        recipient_session_id TEXT NOT NULL DEFAULT '',
        payload TEXT NOT NULL DEFAULT '{}',
        state TEXT NOT NULL DEFAULT 'pending'
            CHECK(state IN ('pending', 'sent')),
        created_at TEXT NOT NULL
    )
"""

_CREATE_SCHEMA_MIGRATIONS = """
    CREATE TABLE IF NOT EXISTS schema_migrations(
        version INTEGER PRIMARY KEY,
        applied_at TEXT NOT NULL
    )
"""

def get_database_path(conversation_id: Optional[str] = None) -> str:
    """返回指定 conversation 的数据库路径（兼容旧接口）。"""
    return ConversationDB(conversation_id).path


def init_conversation_db(conversation_id: Optional[str] = None) -> ConversationDB:
    """初始化并返回指定 conversation 的数据库对象。"""
    return ConversationDB(conversation_id).init()


# Append-only candidate archives; no second compute queue.
_CREATE_CONFORMER_TABLES = (
    "CREATE TABLE IF NOT EXISTS conformer_catalogs (catalog_id TEXT PRIMARY KEY, project_id TEXT NOT NULL, owner_id TEXT NOT NULL)",
    "CREATE TABLE IF NOT EXISTS conformer_candidates (candidate_id TEXT PRIMARY KEY, catalog_id TEXT NOT NULL, payload TEXT NOT NULL)",
    "CREATE INDEX IF NOT EXISTS idx_conformer_catalog ON conformer_candidates(catalog_id)",
    "CREATE TABLE IF NOT EXISTS conformer_regions (catalog_id TEXT NOT NULL, revision TEXT NOT NULL, payload TEXT NOT NULL, PRIMARY KEY(catalog_id,revision))",
)

_CREATE_EXPLORATION_TABLES = (
    'CREATE TABLE IF NOT EXISTS exploration_released_actions ('
    'process_id TEXT NOT NULL, action_key TEXT NOT NULL, reason TEXT NOT NULL, '
    'PRIMARY KEY(process_id,action_key))',
    "CREATE TABLE IF NOT EXISTS exploration_budgets (process_id TEXT PRIMARY KEY, project_id TEXT NOT NULL, owner_id TEXT NOT NULL, payload TEXT NOT NULL)",
    "CREATE TABLE IF NOT EXISTS exploration_reservations (reservation_id TEXT PRIMARY KEY, process_id TEXT NOT NULL, decision_id TEXT NOT NULL, payload TEXT NOT NULL, UNIQUE(process_id,decision_id))",
    "CREATE TABLE IF NOT EXISTS exploration_actions (process_id TEXT NOT NULL, action_key TEXT NOT NULL, reservation_id TEXT NOT NULL, estimate TEXT NOT NULL, job_id INTEGER UNIQUE, actual TEXT, PRIMARY KEY(process_id,action_key))",
)

_CREATE_TS_PIPELINE_TABLES = (
    'CREATE TABLE IF NOT EXISTS ts_pipeline_revision_receipts ('
    'process_id TEXT NOT NULL, request_key TEXT NOT NULL, payload TEXT NOT NULL, '
    'PRIMARY KEY(process_id,request_key))',
    "CREATE TABLE IF NOT EXISTS ts_pipeline_inputs (job_id INTEGER PRIMARY KEY, input_digest TEXT NOT NULL)",
    'CREATE TABLE IF NOT EXISTS ts_pipeline_declarations ('
    'process_id TEXT NOT NULL, declaration_revision INTEGER NOT NULL, payload TEXT NOT NULL, '
    'PRIMARY KEY(process_id,declaration_revision))',
    'CREATE TABLE IF NOT EXISTS ts_pipeline_processes ('
    'process_id TEXT PRIMARY KEY, request_key TEXT NOT NULL, project_id TEXT NOT NULL, owner_id TEXT, '
    'payload TEXT NOT NULL, declaration_revision INTEGER NOT NULL, revision INTEGER NOT NULL, '
    'status TEXT NOT NULL, record TEXT)',
    'CREATE TABLE IF NOT EXISTS ts_pipeline_stages ('
    'process_id TEXT NOT NULL, declaration_revision INTEGER NOT NULL, stage_key TEXT NOT NULL, '
    'attempt INTEGER NOT NULL, job_id INTEGER NOT NULL UNIQUE, input_hash TEXT NOT NULL, evidence TEXT, '
    'PRIMARY KEY(process_id,declaration_revision,stage_key,attempt))',
)
