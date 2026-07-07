"""Conversation-scoped SQLite 数据库管理。

本模块提供 ``ConversationDB`` 作为数据库路径、初始化、连接参数的
唯一事实来源。所有需要访问 Cloudra 任务状态数据库的代码都应通过
此类，避免在多处硬编码 ``data_dir/.../database.db`` 路径或连接参数。
"""

from __future__ import annotations

import os
import sqlite3
import time
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
            cur.execute(_CREATE_CASES)
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
            await cur.execute(_CREATE_CASES)
            await con.commit()
        return self

    def add_case(
        self,
        session_id: str,
        task_summary: str,
        outcome: str,
        outcome_reason: str = "",
        lesson: str = "",
        embedding: Optional[bytes] = None,
    ) -> int:
        """同步写入一条 case，返回 case id。"""
        with self.connect() as con:
            cur = con.cursor()
            cur.execute(
                """
                INSERT INTO cases
                (conversation_id, session_id, task_summary, outcome, outcome_reason, lesson, embedding, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    self.conversation_id,
                    session_id,
                    task_summary,
                    outcome,
                    outcome_reason,
                    lesson,
                    embedding,
                    time.time(),
                ),
            )
            con.commit()
            return cur.lastrowid

    async def aadd_case(
        self,
        session_id: str,
        task_summary: str,
        outcome: str,
        outcome_reason: str = "",
        lesson: str = "",
        embedding: Optional[bytes] = None,
    ) -> int:
        """异步写入一条 case，返回 case id。"""
        async with self.aconnect() as con:
            cur = await con.execute(
                """
                INSERT INTO cases
                (conversation_id, session_id, task_summary, outcome, outcome_reason, lesson, embedding, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    self.conversation_id,
                    session_id,
                    task_summary,
                    outcome,
                    outcome_reason,
                    lesson,
                    embedding,
                    time.time(),
                ),
            )
            await con.commit()
            return cur.lastrowid

    def get_cases(self, limit: Optional[int] = None) -> list[dict]:
        """同步读取 cases，返回字典列表。"""
        with self.connect() as con:
            cur = con.cursor()
            sql = "SELECT * FROM cases ORDER BY created_at DESC"
            params = ()
            if limit is not None:
                sql += " LIMIT ?"
                params = (limit,)
            cur.execute(sql, params)
            rows = cur.fetchall()
            return self._rows_to_cases(rows)

    async def aget_cases(self, limit: Optional[int] = None) -> list[dict]:
        """异步读取 cases，返回字典列表。"""
        async with self.aconnect() as con:
            cur = await con.execute(
                "SELECT * FROM cases ORDER BY created_at DESC LIMIT ?",
                (limit if limit is not None else -1,),
            )
            rows = await cur.fetchall()
            return self._rows_to_cases(rows)

    @staticmethod
    def _rows_to_cases(rows: list) -> list[dict]:
        """把 SQLite 行列表转换为 case 字典列表。"""
        cases = []
        for row in rows:
            embedding = row[7]
            cases.append(
                {
                    "id": row[0],
                    "conversation_id": row[1],
                    "session_id": row[2],
                    "task_summary": row[3],
                    "outcome": row[4],
                    "outcome_reason": row[5],
                    "lesson": row[6],
                    "embedding": embedding,
                    "created_at": row[8],
                }
            )
        return cases

    def case_count(self) -> int:
        """返回当前 conversation 的 case 数量。"""
        with self.connect() as con:
            cur = con.cursor()
            cur.execute("SELECT COUNT(*) FROM cases")
            row = cur.fetchone()
            return row[0] if row else 0


# SQL 建表语句统一放在这里，作为唯一表结构定义。
_CREATE_SESSION = """
    CREATE TABLE IF NOT EXISTS session (
        session_id TEXT PRIMARY KEY,
        state TEXT,
        result TEXT
    )
"""

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

_CREATE_CASES = """
    CREATE TABLE IF NOT EXISTS cases(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        conversation_id TEXT,
        session_id TEXT,
        task_summary TEXT,
        outcome TEXT,
        outcome_reason TEXT,
        lesson TEXT,
        embedding BLOB,
        created_at REAL
    )
"""


def get_database_path(conversation_id: Optional[str] = None) -> str:
    """返回指定 conversation 的数据库路径（兼容旧接口）。"""
    return ConversationDB(conversation_id).path


def init_conversation_db(conversation_id: Optional[str] = None) -> ConversationDB:
    """初始化并返回指定 conversation 的数据库对象。"""
    return ConversationDB(conversation_id).init()
