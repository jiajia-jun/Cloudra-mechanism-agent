from typing import Optional

from cloudra.database import ConversationDB


class SessionManager:
    """
    以数据库为单一事实来源的 Session 管理器。
    不再扫描文件系统，所有查询直接走 SQLite。
    Session JSON 文件仍由 Session 类写入，仅作为日志/调试用途。
    """

    def __init__(self, database_path: str):
        self.database_path = database_path
        self._db = ConversationDB.from_path(database_path)

    COLUMNS = (
        "session_id, agent_id, agent_type, parent_session_id, query, state, "
        "result, error, pid, worker_id, created_at, started_at, heartbeat_at, "
        "finished_at, exit_code"
    )
    KEYS = [
        "session_id", "agent_id", "agent_type", "parent_session_id", "query",
        "state", "result", "error", "pid", "worker_id", "created_at",
        "started_at", "heartbeat_at", "finished_at", "exit_code",
    ]

    @classmethod
    def _row(cls, row) -> dict:
        return dict(zip(cls.KEYS, row))

    def get_by_state(self, state: str) -> list[dict]:
        """按状态查询 session 列表。"""
        with self._db.connect() as con:
            cur = con.cursor()
            cur.execute(f"SELECT {self.COLUMNS} FROM session WHERE state = ?", (state,))
            rows = cur.fetchall()
        return [
            self._row(row) for row in rows
        ]

    def get(self, session_id: str) -> Optional[dict]:
        """查询单个 session。"""
        with self._db.connect() as con:
            cur = con.cursor()
            cur.execute(f"SELECT {self.COLUMNS} FROM session WHERE session_id = ?", (session_id,))
            row = cur.fetchone()
        if row:
            return self._row(row)
        return None

    def list_all(self) -> list[dict]:
        """列出所有 session。"""
        with self._db.connect() as con:
            cur = con.cursor()
            cur.execute(f"SELECT {self.COLUMNS} FROM session ORDER BY created_at DESC")
            rows = cur.fetchall()
        return [
            self._row(row) for row in rows
        ]
