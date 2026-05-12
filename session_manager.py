import sqlite3
from typing import Optional


class SessionManager:
    """
    以数据库为单一事实来源的 Session 管理器。
    不再扫描文件系统，所有查询直接走 SQLite。
    Session JSON 文件仍由 Session 类写入，仅作为日志/调试用途。
    """

    def __init__(self, database_path: str):
        self.database_path = database_path

    def get_by_state(self, state: str) -> list[dict]:
        """按状态查询 session 列表。"""
        con = sqlite3.connect(self.database_path)
        cur = con.cursor()
        cur.execute("SELECT session_id, state, result FROM session WHERE state = ?", (state,))
        rows = cur.fetchall()
        con.close()
        return [
            {'session_id': r[0], 'state': r[1], 'result': r[2]}
            for r in rows
        ]

    def get(self, session_id: str) -> Optional[dict]:
        """查询单个 session。"""
        con = sqlite3.connect(self.database_path)
        cur = con.cursor()
        cur.execute("SELECT session_id, state, result FROM session WHERE session_id = ?", (session_id,))
        row = cur.fetchone()
        con.close()
        if row:
            return {'session_id': row[0], 'state': row[1], 'result': row[2]}
        return None

    def list_all(self) -> list[dict]:
        """列出所有 session。"""
        con = sqlite3.connect(self.database_path)
        cur = con.cursor()
        cur.execute("SELECT session_id, state, result FROM session")
        rows = cur.fetchall()
        con.close()
        return [
            {'session_id': r[0], 'state': r[1], 'result': r[2]}
            for r in rows
        ]
