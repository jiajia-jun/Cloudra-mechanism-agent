"""Conversation-scoped SQLite 数据库管理。

本模块提供 ``ConversationDB`` 作为数据库路径、初始化、连接参数的
唯一事实来源。所有需要访问 Cloudra 任务状态数据库的代码都应通过
此类，避免在多处硬编码 ``data_dir/.../database.db`` 路径或连接参数。
"""

from __future__ import annotations

import os
import re
import sqlite3
from typing import Optional

import aiosqlite

from cloudra.config import get_config


class ConversationDB:
    """单个 conversation 的 SQLite 状态数据库。

    负责：
    1. 按 ``data_dir/conversations/<conv_id>/tasks/database.db`` 生成唯一路径
    2. 确保目录存在并初始化表结构
    3. 统一 WAL 模式、busy_timeout 等连接参数
    4. 提供同步/异步连接上下文
    """

    def __init__(self, conversation_id: Optional[str] = None):
        self.conversation_id = conversation_id or "default"
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", self.conversation_id):
            raise ValueError("无效的 conversation_id")
        self.path = self._build_path(self.conversation_id)

    @staticmethod
    def _build_path(conversation_id: str) -> str:
        data_dir = get_config().data_dir
        return str(data_dir / "conversations" / conversation_id / "tasks" / "database.db")

    @classmethod
    def from_path(cls, path: str) -> "ConversationDB":
        """从已有路径构造 ConversationDB 实例（不验证 conversation_id）。"""
        instance = cls.__new__(cls)
        instance.conversation_id = ""
        instance.path = path
        return instance

    def ensure_dir(self) -> "ConversationDB":
        """确保数据库所在目录存在。"""
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        return self

    def init(self) -> "ConversationDB":
        """初始化数据库：建目录、建表、启用 WAL。"""
        self.ensure_dir()
        with self.connect() as con:
            cur = con.cursor()
            cur.execute(_CREATE_SESSION)
            cur.execute(_CREATE_SUBAGENT_REQUESTS)
            cur.execute(_CREATE_APPROVALS)
            cur.execute(_CREATE_COMPUTE_JOBS)
            cur.execute(_CREATE_CONTEXT_EVENTS)
            cur.execute(_CREATE_SESSION_EVENTS)
            cur.execute(_CREATE_SCHEMA_MIGRATIONS)
            self._migrate_session_schema(cur)
            self._migrate_related_schema(cur)
            cur.execute(
                "INSERT OR REPLACE INTO schema_migrations (version, applied_at) VALUES (2, datetime('now'))"
            )
            con.commit()
        return self

    def connect(self, timeout: float = 30.0):
        """返回一个已配置 WAL/busy_timeout 的同步 SQLite 连接。"""
        self.ensure_dir()
        con = sqlite3.connect(self.path, timeout=timeout)
        cur = con.cursor()
        cur.execute("PRAGMA journal_mode=WAL;")
        cur.execute(f"PRAGMA busy_timeout={int(timeout * 1000)};")
        cur.execute("PRAGMA synchronous=NORMAL;")
        con.commit()
        return con

    def aconnect(self, timeout: float = 30.0):
        """返回一个已配置 WAL/busy_timeout 的异步 SQLite 连接上下文。"""
        self.ensure_dir()
        return aiosqlite.connect(self.path, timeout=timeout)

    async def ainit(self) -> "ConversationDB":
        """异步初始化数据库。"""
        self.ensure_dir()
        async with self.aconnect() as con:
            cur = await con.cursor()
            await cur.execute(_CREATE_SESSION)
            await cur.execute(_CREATE_SUBAGENT_REQUESTS)
            await cur.execute(_CREATE_APPROVALS)
            await cur.execute(_CREATE_COMPUTE_JOBS)
            await cur.execute(_CREATE_CONTEXT_EVENTS)
            await cur.execute(_CREATE_SESSION_EVENTS)
            await cur.execute(_CREATE_SCHEMA_MIGRATIONS)
            await self._amigrate_session_schema(cur)
            await self._amigrate_related_schema(cur)
            await cur.execute(
                "INSERT OR REPLACE INTO schema_migrations (version, applied_at) VALUES (2, datetime('now'))"
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
        exit_code INTEGER
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
}

_RELATED_EXTRA_COLUMNS = {
    "subagent_requests": {
        "session_id": "TEXT",
        "parent_session_id": "TEXT",
    },
    "compute_jobs": {"session_id": "TEXT"},
}

_CREATE_SUBAGENT_REQUESTS = """
    CREATE TABLE IF NOT EXISTS subagent_requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        state TEXT,
        input_data TEXT,
        conversation_id TEXT
    )
"""

_CREATE_APPROVALS = """
    CREATE TABLE IF NOT EXISTS approvals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id TEXT,
        agent_name TEXT,
        details TEXT,
        state TEXT DEFAULT 'pending',
        denial_reason TEXT DEFAULT ''
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
        jobtype TEXT DEFAULT 'gaussian'
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

_CREATE_SESSION_EVENTS = """
    CREATE TABLE IF NOT EXISTS session_events(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id TEXT NOT NULL,
        event_type TEXT NOT NULL,
        data TEXT NOT NULL DEFAULT '{}',
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
