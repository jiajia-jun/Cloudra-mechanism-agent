"""Conversation-scoped SQLite 数据库管理。

本模块提供 ``ConversationDB`` 作为数据库路径、初始化、连接参数的
唯一事实来源。所有需要访问 Cloudra 任务状态数据库的代码都应通过
此类，避免在多处硬编码 ``data_dir/.../database.db`` 路径或连接参数。
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
SCHEMA_VERSION = 13
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
            cur.execute(_CREATE_SUBAGENT_REQUESTS)
            cur.execute(_CREATE_APPROVALS)
            cur.execute(_CREATE_COMPUTE_JOBS)
            cur.execute(_CREATE_CONTEXT_EVENTS)
            cur.execute(_CREATE_SCHEDULED_REMINDERS)
            cur.execute(_CREATE_SESSION_EVENTS)
            cur.execute(_CREATE_CLIENT_COMMANDS)
            cur.execute(_CREATE_INTERACTIONS)
            cur.execute(_CREATE_ARTIFACTS)
            cur.execute(_CREATE_ARTIFACT_DOWNLOAD_TOKENS)
            cur.execute(_CREATE_HUB_POSTS)
            cur.execute(_CREATE_HUB_POSTS_TOPIC_INDEX)
            cur.execute(_CREATE_HUB_POSTS_PARENT_INDEX)
            cur.execute(_CREATE_DAG_GRAPHS)
            cur.execute(_CREATE_DAG_SPECIES)
            cur.execute(_CREATE_DAG_NODES)
            cur.execute(_CREATE_DAG_EDGES)
            cur.execute(_CREATE_DAG_EVIDENCE_BINDINGS)
            cur.execute(_CREATE_DAG_LINKS)
            cur.execute(_CREATE_DAG_EVIDENCE)
            cur.execute(_CREATE_DAG_MUTATIONS)
            cur.execute(_CREATE_DAG_COVERAGE)
            cur.execute(_CREATE_DAG_DELIVERY_DISPOSITIONS)
            cur.execute(_CREATE_DAG_CALL_REVIEWS)
            cur.execute(_CREATE_DAG_DRAFTS)
            cur.execute(_CREATE_CLIENT_COMMANDS_INDEX)
            cur.execute(_CREATE_INTERACTIONS_INDEX)
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
            await cur.execute(_CREATE_SUBAGENT_REQUESTS)
            await cur.execute(_CREATE_APPROVALS)
            await cur.execute(_CREATE_COMPUTE_JOBS)
            await cur.execute(_CREATE_CONTEXT_EVENTS)
            await cur.execute(_CREATE_SCHEDULED_REMINDERS)
            await cur.execute(_CREATE_SESSION_EVENTS)
            await cur.execute(_CREATE_CLIENT_COMMANDS)
            await cur.execute(_CREATE_INTERACTIONS)
            await cur.execute(_CREATE_ARTIFACTS)
            await cur.execute(_CREATE_ARTIFACT_DOWNLOAD_TOKENS)
            await cur.execute(_CREATE_HUB_POSTS)
            await cur.execute(_CREATE_HUB_POSTS_TOPIC_INDEX)
            await cur.execute(_CREATE_HUB_POSTS_PARENT_INDEX)
            await cur.execute(_CREATE_DAG_GRAPHS)
            await cur.execute(_CREATE_DAG_SPECIES)
            await cur.execute(_CREATE_DAG_NODES)
            await cur.execute(_CREATE_DAG_EDGES)
            await cur.execute(_CREATE_DAG_EVIDENCE_BINDINGS)
            await cur.execute(_CREATE_DAG_LINKS)
            await cur.execute(_CREATE_DAG_EVIDENCE)
            await cur.execute(_CREATE_DAG_MUTATIONS)
            await cur.execute(_CREATE_DAG_COVERAGE)
            await cur.execute(_CREATE_DAG_DELIVERY_DISPOSITIONS)
            await cur.execute(_CREATE_DAG_CALL_REVIEWS)
            await cur.execute(_CREATE_DAG_DRAFTS)
            await cur.execute(_CREATE_CLIENT_COMMANDS_INDEX)
            await cur.execute(_CREATE_INTERACTIONS_INDEX)
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

    @staticmethod
    async def _amigrate_related_schema(cur) -> None:
        for table, columns in _RELATED_EXTRA_COLUMNS.items():
            await cur.execute(f"PRAGMA table_info({table})")
            existing = {row[1] for row in await cur.fetchall()}
            for name, definition in columns.items():
                if name not in existing:
                    await ConversationDB._aadd_column(cur, table, name, definition)
        await ConversationDB._amigrate_dag_evidence_bindings(cur)

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
    "hub_posts": {
        "to_agent": "TEXT",
    },
    "subagent_requests": {
        "session_id": "TEXT",
        "parent_session_id": "TEXT",
        "lease_owner": "TEXT",
        "lease_expires_at": "REAL",
        "attempt_count": "INTEGER DEFAULT 0",
    },
    "compute_jobs": {
        "session_id": "TEXT",
        "scheduler": "TEXT DEFAULT 'local'",
        "scheduler_options": "TEXT DEFAULT '{}'",
        "scheduler_job_id": "TEXT",
        "scheduler_state": "TEXT",
        "scheduler_script": "TEXT",
        "last_error": "TEXT",
        "lease_owner": "TEXT",
        "lease_expires_at": "REAL",
        "attempt_count": "INTEGER DEFAULT 0",
    },
    "context_events": {
        "session_id": "TEXT",
    },
    "approvals": {
        "tool_name": "TEXT DEFAULT ''",
        "normalized_arguments": "TEXT DEFAULT '{}'",
        "risk_summary": "TEXT DEFAULT ''",
        "candidate_diff": "TEXT DEFAULT ''",
        "requested_at": "TEXT",
        "expires_at": "TEXT",
        "decided_by": "TEXT",
        "decided_at": "TEXT",
    },
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
}

_CREATE_SUBAGENT_REQUESTS = """
    CREATE TABLE IF NOT EXISTS subagent_requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        state TEXT,
        input_data TEXT,
        conversation_id TEXT,
        lease_owner TEXT,
        lease_expires_at REAL,
        attempt_count INTEGER DEFAULT 0
    )
"""

_CREATE_APPROVALS = """
    CREATE TABLE IF NOT EXISTS approvals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id TEXT,
        agent_name TEXT,
        details TEXT,
        state TEXT DEFAULT 'pending',
        denial_reason TEXT DEFAULT '',
        tool_name TEXT DEFAULT '',
        normalized_arguments TEXT DEFAULT '{}',
        risk_summary TEXT DEFAULT '',
        candidate_diff TEXT DEFAULT '',
        requested_at TEXT,
        expires_at TEXT,
        decided_by TEXT,
        decided_at TEXT
    )
"""

_CREATE_COMPUTE_JOBS = """
    CREATE TABLE IF NOT EXISTS compute_jobs(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        conversation_id TEXT,
        state TEXT,
        path TEXT,
        start_timestamp INTEGER,
        end_timestamp INTEGER DEFAULT -1,
        jobtype TEXT DEFAULT 'gaussian',
        scheduler TEXT DEFAULT 'local',
        scheduler_options TEXT DEFAULT '{}',
        scheduler_job_id TEXT,
        scheduler_state TEXT,
        scheduler_script TEXT,
        last_error TEXT,
        lease_owner TEXT,
        lease_expires_at REAL,
        attempt_count INTEGER DEFAULT 0
    )
"""

_CREATE_CONTEXT_EVENTS = """
    CREATE TABLE IF NOT EXISTS context_events(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        conversation_id TEXT,
        agent_id TEXT,
        session_id TEXT,
        event_type TEXT,
        content TEXT,
        state TEXT DEFAULT 'pending',
        created_at REAL
    )
"""

_CREATE_SCHEDULED_REMINDERS = """
    CREATE TABLE IF NOT EXISTS scheduled_reminders(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        conversation_id TEXT NOT NULL,
        agent_id TEXT NOT NULL,
        session_id TEXT,
        content TEXT NOT NULL,
        wake_at REAL NOT NULL,
        state TEXT NOT NULL DEFAULT 'pending',
        created_at REAL NOT NULL,
        fired_at REAL
    )
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

_CREATE_CLIENT_COMMANDS = """
    CREATE TABLE IF NOT EXISTS client_commands(
        command_id TEXT PRIMARY KEY,
        conversation_id TEXT NOT NULL,
        session_id TEXT,
        command_type TEXT NOT NULL,
        payload TEXT NOT NULL DEFAULT '{}',
        state TEXT NOT NULL DEFAULT 'received',
        result TEXT,
        error TEXT,
        created_at TEXT NOT NULL,
        applied_at TEXT
    )
"""

_CREATE_CLIENT_COMMANDS_INDEX = """
    CREATE INDEX IF NOT EXISTS idx_client_commands_session
    ON client_commands(session_id, created_at)
"""

_CREATE_INTERACTIONS = """
    CREATE TABLE IF NOT EXISTS interactions(
        interaction_id TEXT PRIMARY KEY,
        session_id TEXT NOT NULL,
        agent_id TEXT NOT NULL,
        prompt TEXT NOT NULL,
        state TEXT NOT NULL DEFAULT 'pending',
        response TEXT,
        created_at TEXT NOT NULL,
        responded_at TEXT
    )
"""

_CREATE_INTERACTIONS_INDEX = """
    CREATE INDEX IF NOT EXISTS idx_interactions_pending
    ON interactions(state, session_id, created_at)
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

_CREATE_HUB_POSTS = """
    CREATE TABLE IF NOT EXISTS hub_posts(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        topic TEXT NOT NULL,
        kind TEXT NOT NULL DEFAULT 'finding',
        author_agent TEXT NOT NULL,
        author_session TEXT NOT NULL DEFAULT '',
        to_agent TEXT,
        parent_id INTEGER,
        content TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
"""

_CREATE_HUB_POSTS_TOPIC_INDEX = """
    CREATE INDEX IF NOT EXISTS idx_hub_posts_topic
    ON hub_posts(topic, created_at)
"""

_CREATE_HUB_POSTS_PARENT_INDEX = """
    CREATE INDEX IF NOT EXISTS idx_hub_posts_parent
    ON hub_posts(parent_id)
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
        compute_job_id TEXT,
        suggested_target_id TEXT,
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
