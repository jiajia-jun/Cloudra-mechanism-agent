"""全局经验案例库（Case Bank）。

与 conversation-scoped 的 SQLite 不同，Case Bank 是全局共享的向量记忆库，
供 Supervisor 在所有 conversation 之间检索历史经验。

存储：
- 位置：`<data_dir>/case_bank.db`
- 向量：以 BLOB 形式保存 float32 embedding
- 检索：Supervisor 用 numpy 计算余弦相似度，取 top-k
"""

from __future__ import annotations

import contextlib
import sqlite3
import time
from pathlib import Path
from typing import Optional

import aiosqlite

from cloudra import paths
from cloudra.config import get_config


class CaseBank:
    """全局案例库，跨 conversation 共享经验。"""

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or self._default_path()

    @staticmethod
    def _default_path() -> str:
        """返回默认全局 case bank 路径。"""
        return str(paths.case_bank_path(data_dir=get_config().data_dir))

    def _ensure_dir(self) -> None:
        """确保数据库所在目录存在。"""
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

    @contextlib.contextmanager
    def connect(self, timeout: float = 30.0):
        """返回退出时显式关闭的同步 SQLite 连接上下文（WAL 模式）。"""
        self._ensure_dir()
        con = sqlite3.connect(self.db_path, timeout=timeout)
        try:
            cur = con.cursor()
            cur.execute("PRAGMA journal_mode=WAL;")
            cur.execute(f"PRAGMA busy_timeout={int(timeout * 1000)};")
            cur.execute("PRAGMA synchronous=NORMAL;")
            con.commit()
            # 保留 sqlite3.Connection 原有的提交/回滚上下文语义。
            with con:
                yield con
        finally:
            con.close()

    def aconnect(self, timeout: float = 30.0):
        """返回异步 SQLite 连接上下文。"""
        self._ensure_dir()
        return aiosqlite.connect(self.db_path, timeout=timeout)

    def init(self) -> "CaseBank":
        """初始化 case bank 表结构。"""
        self._ensure_dir()
        with self.connect() as con:
            cur = con.cursor()
            cur.execute(_CREATE_CASES)
            con.commit()
        return self

    async def ainit(self) -> "CaseBank":
        """异步初始化 case bank 表结构。"""
        self._ensure_dir()
        async with self.aconnect() as con:
            await con.execute(_CREATE_CASES)
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
        """同步写入一条全局 case，返回 case id。"""
        with self.connect() as con:
            cur = con.cursor()
            cur.execute(
                """
                INSERT INTO cases
                (session_id, task_summary, outcome, outcome_reason, lesson, embedding, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
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
        """异步写入一条全局 case，返回 case id。"""
        async with self.aconnect() as con:
            cur = await con.execute(
                """
                INSERT INTO cases
                (session_id, task_summary, outcome, outcome_reason, lesson, embedding, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
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
            if limit is not None:
                cur.execute(
                    "SELECT * FROM cases ORDER BY created_at DESC LIMIT ?",
                    (limit,),
                )
            else:
                cur.execute("SELECT * FROM cases ORDER BY created_at DESC")
            rows = cur.fetchall()
            return self._rows_to_cases(rows)

    async def aget_cases(self, limit: Optional[int] = None) -> list[dict]:
        """异步读取 cases，返回字典列表。"""
        async with self.aconnect() as con:
            if limit is not None:
                cur = await con.execute(
                    "SELECT * FROM cases ORDER BY created_at DESC LIMIT ?",
                    (limit,),
                )
            else:
                cur = await con.execute("SELECT * FROM cases ORDER BY created_at DESC")
            rows = await cur.fetchall()
            return self._rows_to_cases(rows)

    @staticmethod
    def _rows_to_cases(rows: list) -> list[dict]:
        """把 SQLite 行列表转换为 case 字典列表。"""
        cases = []
        for row in rows:
            cases.append(
                {
                    "id": row[0],
                    "session_id": row[1],
                    "task_summary": row[2],
                    "outcome": row[3],
                    "outcome_reason": row[4],
                    "lesson": row[5],
                    "embedding": row[6],
                    "created_at": row[7],
                }
            )
        return cases

    def case_count(self) -> int:
        """返回全局 case 数量。"""
        with self.connect() as con:
            cur = con.cursor()
            cur.execute("SELECT COUNT(*) FROM cases")
            row = cur.fetchone()
            return row[0] if row else 0


_CREATE_CASES = """
    CREATE TABLE IF NOT EXISTS cases(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id TEXT,
        task_summary TEXT,
        outcome TEXT,
        outcome_reason TEXT,
        lesson TEXT,
        embedding BLOB,
        created_at REAL
    )
"""


_CASE_BANK_CACHE: dict[str, "CaseBank"] = {}


def get_case_bank(db_path: Optional[str] = None) -> CaseBank:
    """工厂函数，返回已初始化的 CaseBank 实例（按路径缓存，避免重复 init 写事务）。"""
    bank = CaseBank(db_path)
    key = bank.db_path
    if key not in _CASE_BANK_CACHE:
        bank.init()
        _CASE_BANK_CACHE[key] = bank
    return _CASE_BANK_CACHE[key]
