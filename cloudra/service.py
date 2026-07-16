"""Cloudra 应用服务层：供 CLI 和 HTTP API 共用。"""

from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import signal
import sqlite3
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from cloudra.config import get_config
from cloudra.conversation_class import Conversation
from cloudra.database import ConversationDB
from cloudra.main import run_task_async

_CONVERSATION_ID = re.compile(r"^[A-Za-z0-9_-]{1,100}$")
_SESSION_ID = re.compile(r"^[A-Za-z0-9_.:-]{1,160}$")


def validate_conversation_id(conversation_id: str) -> str:
    if not _CONVERSATION_ID.fullmatch(conversation_id):
        raise ValueError("会话 ID 只能包含字母、数字、下划线和连字符，长度不超过 100")
    return conversation_id


def validate_session_id(session_id: str) -> str:
    if not _SESSION_ID.fullmatch(session_id):
        raise ValueError("无效的 Session ID")
    return session_id


@dataclass
class SessionRecord:
    session_id: str
    agent_id: str | None
    agent_type: str | None
    parent_session_id: str | None
    query: str | None
    state: str
    result: str | None
    error: str | None
    pid: int | None
    worker_id: str | None
    created_at: str | None
    started_at: str | None
    heartbeat_at: str | None
    finished_at: str | None
    exit_code: int | None

    def to_dict(self) -> dict:
        return asdict(self)


_SESSION_COLUMNS = """session_id, agent_id, agent_type, parent_session_id, query,
state, result, error, pid, worker_id, created_at, started_at, heartbeat_at,
finished_at, exit_code"""


class SessionRunner:
    """为 API 启动 Coordinator Session，并管理当前进程中的异步执行句柄。"""

    def __init__(self, service: "CloudraService") -> None:
        self.service = service
        self._running: dict[tuple[str, str], asyncio.Task] = {}
        self.worker_id = f"api:{os.getpid()}:{uuid.uuid4().hex[:8]}"

    def submit(
        self, query: str, conversation_id: str, working_directory: str | None = None
    ) -> SessionRecord:
        session_id = f"a-0_run_{uuid.uuid4().hex}"
        now = datetime.now(timezone.utc).isoformat()
        db = ConversationDB(conversation_id).init()
        with db.connect() as conn:
            conn.execute(
                """INSERT INTO session
                (session_id, agent_id, agent_type, query, state, created_at)
                VALUES (?, ?, ?, ?, ?, ?)""",
                (session_id, "a-0", "coordinator", query, "queued", now),
            )
            conn.commit()
        self._emit(conversation_id, session_id, "queued", {"query": query})
        task = asyncio.create_task(
            self._execute(query, conversation_id, session_id, working_directory)
        )
        self._running[(conversation_id, session_id)] = task
        return self.get(conversation_id, session_id)

    async def _execute(
        self,
        query: str,
        conversation_id: str,
        session_id: str,
        working_directory: str | None = None,
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        if not self._claim(conversation_id, session_id, now):
            return
        heartbeat = asyncio.create_task(self._heartbeat(conversation_id, session_id))
        try:
            if working_directory is None:
                result = await self.service.run_task(
                    query, conversation_id, session_id=session_id
                )
            else:
                result = await self.service.run_task(
                    query,
                    conversation_id,
                    session_id=session_id,
                    working_directory=working_directory,
                )
            self._update(
                conversation_id,
                session_id,
                state="completed",
                result=result,
                finished_at=datetime.now(timezone.utc).isoformat(),
                exit_code=0,
            )
            self._emit(conversation_id, session_id, "completed", {"result": result})
        except asyncio.CancelledError:
            self._update(
                conversation_id,
                session_id,
                state="cancelled",
                finished_at=datetime.now(timezone.utc).isoformat(),
            )
            self._emit(conversation_id, session_id, "cancelled", {})
            raise
        except Exception as exc:
            self._update(
                conversation_id,
                session_id,
                state="failed",
                error=str(exc),
                finished_at=datetime.now(timezone.utc).isoformat(),
                exit_code=1,
            )
            self._emit(conversation_id, session_id, "failed", {"error": str(exc)})
        finally:
            heartbeat.cancel()
            self._running.pop((conversation_id, session_id), None)

    def _claim(self, conversation_id: str, session_id: str, now: str) -> bool:
        db = ConversationDB(conversation_id)
        with db.connect() as conn:
            cursor = conn.execute(
                """UPDATE session SET state='running', pid=?, worker_id=?,
                started_at=COALESCE(started_at, ?), heartbeat_at=?
                WHERE session_id=? AND state='queued'""",
                (os.getpid(), self.worker_id, now, now, session_id),
            )
            conn.commit()
        if cursor.rowcount == 1:
            self._emit(conversation_id, session_id, "running", {"worker_id": self.worker_id})
            return True
        return False

    async def _heartbeat(self, conversation_id: str, session_id: str) -> None:
        while True:
            await asyncio.sleep(5)
            self._update(
                conversation_id,
                session_id,
                heartbeat_at=datetime.now(timezone.utc).isoformat(),
            )

    def _update(self, conversation_id: str, session_id: str, **values) -> None:
        if not values:
            return
        assignments = ", ".join(f"{name} = ?" for name in values)
        db = ConversationDB(conversation_id)
        with db.connect() as conn:
            conn.execute(
                f"UPDATE session SET {assignments} WHERE session_id = ?",
                (*values.values(), session_id),
            )
            conn.commit()

    def _emit(self, conversation_id: str, session_id: str, event_type: str, data: dict) -> None:
        # 库已在 submit() 时初始化；不要在这里重复 init()——建表+迁移是写事务，
        # 并发子 Agent 高频上报事件时会放大写锁竞争。
        db = ConversationDB(conversation_id)
        with db.connect() as conn:
            conn.execute(
                "INSERT INTO session_events (session_id, event_type, data, created_at) VALUES (?, ?, ?, ?)",
                (session_id, event_type, json.dumps(data, ensure_ascii=False), datetime.now(timezone.utc).isoformat()),
            )
            conn.commit()

    def events(self, conversation_id: str, session_id: str, after_id: int = 0, conn=None) -> list[dict]:
        validate_conversation_id(conversation_id)
        validate_session_id(session_id)

        def _fetch(c) -> list[dict]:
            rows = c.execute(
                """SELECT id, event_type, data, created_at FROM session_events
                WHERE session_id=? AND id>? ORDER BY id""",
                (session_id, after_id),
            ).fetchall()
            return [
                {"id": row[0], "event_type": row[1], "data": json.loads(row[2]), "created_at": row[3]}
                for row in rows
            ]

        if conn is not None:
            # 复用调用方持有的连接（如 SSE 轮询），跳过路径检查、不新开连接
            return _fetch(conn)
        db = ConversationDB(conversation_id)
        if not Path(db.path).is_file():
            return []
        with db.connect() as owned:
            return _fetch(owned)

    def recover_stale_sessions(self, timeout_seconds: int = 60) -> int:
        """把失去心跳的 running Session 标为 interrupted，避免永久假运行。"""
        cutoff = datetime.fromtimestamp(
            datetime.now(timezone.utc).timestamp() - timeout_seconds,
            tz=timezone.utc,
        ).isoformat()
        changed = 0
        root = get_config().data_dir / "conversations"
        for entry in root.iterdir() if root.exists() else []:
            if not entry.is_dir() or not _CONVERSATION_ID.fullmatch(entry.name):
                continue
            db = ConversationDB(entry.name)
            if not Path(db.path).is_file():
                continue
            try:
                db.init()
                with db.connect() as conn:
                    cursor = conn.execute(
                        """UPDATE session SET state='interrupted',
                        error=COALESCE(error, 'worker heartbeat expired'), finished_at=?
                        WHERE state='running' AND (heartbeat_at IS NULL OR heartbeat_at < ?)""",
                        (datetime.now(timezone.utc).isoformat(), cutoff),
                    )
                    conn.commit()
                    changed += cursor.rowcount
                    # 状态一致性：子 Agent 请求若仍挂在 'running'，但其 executor 的
                    # Session 已死（心跳过期/不存在/非 running），一并标记 failed，
                    # 避免等待方（_wait_for_background_tasks 等）永久阻塞。
                    conn.execute(
                        """UPDATE subagent_requests SET state='failed'
                        WHERE state='running' AND (
                            session_id IS NULL
                            OR session_id NOT IN (SELECT session_id FROM session)
                            OR session_id IN (
                                SELECT session_id FROM session
                                WHERE state != 'running' OR heartbeat_at IS NULL OR heartbeat_at < ?
                            )
                        )""",
                        (cutoff,),
                    )
                    conn.commit()
            except (OSError, sqlite3.Error):
                continue
        return changed

    def get(self, conversation_id: str, session_id: str, conn=None) -> SessionRecord | None:
        validate_conversation_id(conversation_id)
        validate_session_id(session_id)

        def _fetch(c) -> SessionRecord | None:
            row = c.execute(
                f"SELECT {_SESSION_COLUMNS} FROM session WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            return SessionRecord(*row) if row else None

        if conn is not None:
            # 复用调用方持有的连接（如 SSE 轮询），跳过路径检查、不新开连接
            return _fetch(conn)
        db_path = Path(ConversationDB(conversation_id).path)
        if not db_path.is_file():
            return None
        with ConversationDB(conversation_id).connect() as owned:
            return _fetch(owned)

    def list(self, conversation_id: str) -> list[SessionRecord]:
        validate_conversation_id(conversation_id)
        db_path = Path(ConversationDB(conversation_id).path)
        if not db_path.is_file():
            return []
        with ConversationDB(conversation_id).connect() as conn:
            rows = conn.execute(
                f"SELECT {_SESSION_COLUMNS} FROM session ORDER BY created_at DESC"
            ).fetchall()
        return [SessionRecord(*row) for row in rows]

    def cancel(self, conversation_id: str, session_id: str) -> SessionRecord | None:
        record = self.get(conversation_id, session_id)
        if record is None:
            return None
        task = self._running.get((conversation_id, session_id))
        if task and not task.done():
            task.cancel()
        elif record.state == "running" and record.pid and record.agent_type != "coordinator":
            try:
                os.kill(record.pid, signal.SIGTERM)
                self._update(conversation_id, session_id, state="cancelled")
                self._emit(conversation_id, session_id, "cancelled", {"signal": "SIGTERM"})
            except (ProcessLookupError, PermissionError):
                self._update(conversation_id, session_id, state="interrupted")
        self._cancel_descendants(conversation_id, session_id)
        return record

    def _cancel_descendants(self, conversation_id: str, parent_session_id: str) -> None:
        """取消父 Session 派生的子 Agent 请求、子 Session 和计算任务。"""
        db = ConversationDB(conversation_id)
        with db.connect() as conn:
            children = conn.execute(
                """SELECT session_id, pid FROM session
                WHERE parent_session_id=? AND state IN ('queued', 'running')""",
                (parent_session_id,),
            ).fetchall()
            for child_id, pid in children:
                if pid and pid != os.getpid():
                    try:
                        os.kill(pid, signal.SIGTERM)
                    except (ProcessLookupError, PermissionError):
                        pass
                conn.execute(
                    """UPDATE session SET state='cancelled', finished_at=?
                    WHERE session_id=?""",
                    (datetime.now(timezone.utc).isoformat(), child_id),
                )
            conn.execute(
                """UPDATE subagent_requests SET state='cancelled'
                WHERE parent_session_id=? AND state IN ('ready', 'running')""",
                (parent_session_id,),
            )
            conn.execute(
                """UPDATE compute_jobs SET state='cancelled'
                WHERE session_id=? AND state IN ('ready', 'running')""",
                (parent_session_id,),
            )
            conn.commit()


class CloudraService:
    """CLI 和 API 共用的 Cloudra 业务入口。"""

    def __init__(self) -> None:
        self.config = get_config()
        self.session_runner = SessionRunner(self)

    def create_conversation(self) -> Conversation:
        return Conversation()

    async def run_task(
        self,
        query: str,
        conversation_id: str | None = None,
        verbose: bool = False,
        session_id: str | None = None,
        working_directory: str | None = None,
        interactive_approval: bool = False,
    ) -> str:
        if conversation_id is not None:
            validate_conversation_id(conversation_id)
        if session_id is not None:
            validate_session_id(session_id)
        # interactive_approval 默认 False：API 路径没有 stdin，不能启动 input() 审批线程，
        # 审批走 Web/API 通道；CLI 入口需显式传 True
        return await run_task_async(
            query,
            conv_id=conversation_id,
            verbose=verbose,
            session_id=session_id,
            working_directory=working_directory,
            interactive_approval=interactive_approval,
        )

    def submit_session(
        self,
        query: str,
        conversation_id: str | None = None,
        working_directory: str | None = None,
    ) -> tuple[str, SessionRecord]:
        if conversation_id is None:
            conversation_id = self.create_conversation().id
        else:
            validate_conversation_id(conversation_id)
        return conversation_id, self.session_runner.submit(
            query, conversation_id, working_directory
        )

    def list_conversations(self) -> list[dict]:
        root = self.config.data_dir / "conversations"
        result = []
        for entry in root.iterdir() if root.exists() else []:
            meta_path = entry / "meta.json"
            if not entry.is_dir() or not meta_path.is_file():
                continue
            try:
                result.append(json.loads(meta_path.read_text(encoding="utf-8")))
            except (OSError, json.JSONDecodeError):
                continue
        return sorted(result, key=lambda item: item.get("last_active", ""), reverse=True)

    def delete_all_conversations(self) -> int:
        """删除所有会话数据（包括消息、Session、审批等）。"""
        root = self.config.data_dir / "conversations"
        count = 0
        if root.exists():
            for entry in list(root.iterdir()):
                if entry.is_dir() and _CONVERSATION_ID.fullmatch(entry.name):
                    shutil.rmtree(entry, ignore_errors=True)
                    count += 1
        return count

    def get_conversation_messages(self, conversation_id: str) -> list[dict]:
        validate_conversation_id(conversation_id)
        path = self.config.data_dir / "conversations" / conversation_id / "contexts" / "a-0.json"
        if not path.is_file():
            return []
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            raise ValueError("会话消息文件格式错误")
        return data

    async def list_pending_approvals(self) -> list[dict]:
        results = []
        for conversation in self.list_conversations():
            # 非 running 的会话不可能产生新的 pending 审批，跳过以省去开库查询
            if conversation.get("state") != "running":
                continue
            conversation_id = conversation.get("id", "")
            try:
                validate_conversation_id(conversation_id)
            except ValueError:
                continue
            db = ConversationDB(conversation_id)
            if not Path(db.path).is_file():
                continue
            async with db.aconnect() as conn:
                cursor = await conn.execute(
                    "SELECT id, session_id, agent_name, details FROM approvals WHERE state = 'pending'"
                )
                rows = await cursor.fetchall()
            for row in rows:
                results.append({
                    "id": row[0],
                    "conversation_id": conversation_id,
                    "session_id": row[1],
                    "agent_name": row[2],
                    "details": row[3],
                })
        return results

    async def decide_approval(
        self,
        conversation_id: str,
        approval_id: int,
        decision: Literal["approved", "denied"],
        denial_reason: str = "",
    ) -> bool:
        validate_conversation_id(conversation_id)
        db = ConversationDB(conversation_id)
        if not Path(db.path).is_file():
            return False
        async with db.aconnect() as conn:
            cursor = await conn.execute(
                "UPDATE approvals SET state = ?, denial_reason = ? WHERE id = ? AND state = 'pending'",
                (decision, denial_reason, approval_id),
            )
            await conn.commit()
            return cursor.rowcount == 1
