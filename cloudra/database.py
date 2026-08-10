"""Conversation-scoped SQLite 数据库管理。

本模块提供 ``ConversationDB`` 作为数据库路径、初始化、连接参数的
唯一事实来源。所有需要访问 Cloudra 任务状态数据库的代码都应通过
此类，避免在多处硬编码 ``data_dir/.../database.db`` 路径或连接参数。
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import random
import re
import sqlite3
import time
from typing import Awaitable, Callable, Optional, TypeVar

import aiosqlite

from cloudra import paths
from cloudra.paths import PathLike

DEFAULT_BUSY_TIMEOUT = 60.0
DEFAULT_LOCK_RETRIES = 4
SCHEMA_VERSION = 10
_T = TypeVar("_T")


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
        self.ensure_dir()
        # journal_mode is persistent.  Switching it on every connection needs a
        # stronger lock and creates avoidable contention between worker processes.
        with contextlib.closing(
            sqlite3.connect(self.path, timeout=DEFAULT_BUSY_TIMEOUT)
        ) as con:
            con.execute(f"PRAGMA busy_timeout={int(DEFAULT_BUSY_TIMEOUT * 1000)};")
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
            cur.execute(_CREATE_DAG_LINKS)
            cur.execute(_CREATE_DAG_EVIDENCE)
            cur.execute(_CREATE_DAG_MUTATIONS)
            cur.execute(_CREATE_DAG_COVERAGE)
            cur.execute(_CREATE_DAG_DELIVERY_DISPOSITIONS)
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
            await cur.execute(_CREATE_DAG_LINKS)
            await cur.execute(_CREATE_DAG_EVIDENCE)
            await cur.execute(_CREATE_DAG_MUTATIONS)
            await cur.execute(_CREATE_DAG_COVERAGE)
            await cur.execute(_CREATE_DAG_DELIVERY_DISPOSITIONS)
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
    def _migrate_session_schema(cur) -> None:
        """为旧数据库补齐 Session 元数据列，不删除已有记录。"""
        existing = {row[1] for row in cur.execute("PRAGMA table_info(session)").fetchall()}
        for name, definition in _SESSION_EXTRA_COLUMNS.items():
            if name not in existing:
                cur.execute(f"ALTER TABLE session ADD COLUMN {name} {definition}")

    @staticmethod
    async def _amigrate_session_schema(cur) -> None:
        await cur.execute("PRAGMA table_info(session)")
        existing = {row[1] for row in await cur.fetchall()}
        for name, definition in _SESSION_EXTRA_COLUMNS.items():
            if name not in existing:
                await cur.execute(f"ALTER TABLE session ADD COLUMN {name} {definition}")

    @staticmethod
    def _migrate_related_schema(cur) -> None:
        for table, columns in _RELATED_EXTRA_COLUMNS.items():
            existing = {row[1] for row in cur.execute(f"PRAGMA table_info({table})").fetchall()}
            for name, definition in columns.items():
                if name not in existing:
                    cur.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")

    @staticmethod
    async def _amigrate_related_schema(cur) -> None:
        for table, columns in _RELATED_EXTRA_COLUMNS.items():
            await cur.execute(f"PRAGMA table_info({table})")
            existing = {row[1] for row in await cur.fetchall()}
            for name, definition in columns.items():
                if name not in existing:
                    await cur.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")


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
        created_revision INTEGER NOT NULL,
        updated_revision INTEGER NOT NULL,
        PRIMARY KEY(graph_id, edge_id),
        FOREIGN KEY(graph_id) REFERENCES dag_graphs(graph_id)
    )
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
