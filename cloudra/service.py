"""Cloudra 应用服务层：供 CLI 和 HTTP API 共用。"""

from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import signal
import sqlite3
import time
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from cloudra import conversation_repo, events, paths, session_store
from cloudra.config import get_config
from cloudra.conversation_class import Conversation
from cloudra.database import ConversationDB
from cloudra.runtime.runner import run_task_async

_CONVERSATION_ID = re.compile(r"^[A-Za-z0-9_-]{1,100}$")
_SESSION_ID = re.compile(r"^[A-Za-z0-9_.:-]{1,160}$")
_TERMINAL_STATES = frozenset({"completed", "failed", "cancelled", "interrupted", "killed"})


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
        self,
        query: str,
        conversation_id: str,
        working_directory: str | None = None,
        yolo: bool = False,
    ) -> SessionRecord:
        session_id = f"a-0_run_{uuid.uuid4().hex}"
        db = ConversationDB(conversation_id).init()
        session_store.insert_queued_session(
            db,
            session_id=session_id,
            agent_id="a-0",
            agent_type="coordinator",
            query=query,
        )
        self._emit(conversation_id, session_id, "queued", {"query": query, "yolo": yolo})
        task = asyncio.create_task(
            self._execute(query, conversation_id, session_id, working_directory, yolo)
        )
        self._running[(conversation_id, session_id)] = task
        return self.get(conversation_id, session_id)

    async def _execute(
        self,
        query: str,
        conversation_id: str,
        session_id: str,
        working_directory: str | None = None,
        yolo: bool = False,
    ) -> None:
        # Session 级 YOLO 开关：只作用于本会话任务及其派生协程
        from cloudra.yolo_guard import set_session_yolo
        set_session_yolo(yolo)
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
        if session_store.claim_session(db, session_id, pid=os.getpid(), worker_id=self.worker_id):
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
        db = ConversationDB(conversation_id)
        session_store.update_session_fields(db, session_id, values)

    def _emit(self, conversation_id: str, session_id: str, event_type: str, data: dict) -> None:
        # 库已在 submit() 时初始化；不要在这里重复 init()——建表+迁移是写事务，
        # 并发子 Agent 高频上报事件时会放大写锁竞争。
        db = ConversationDB(conversation_id)
        session_store.insert_session_event(db, session_id, event_type, data)

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
        root = paths.conversations_dir()
        for entry in root.iterdir() if root.exists() else []:
            if not entry.is_dir() or not _CONVERSATION_ID.fullmatch(entry.name):
                continue
            db = ConversationDB(entry.name)
            if not Path(db.path).is_file():
                continue
            try:
                db.init()
                changed += session_store.recover_stale(db, cutoff=cutoff)
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

    async def _wait_terminal(self, conversation_id: str, session_id: str, timeout: float) -> SessionRecord | None:
        """等待 session 进入终态事件（最多 timeout 秒），返回最新记录。"""
        await events.ensure_listener(conversation_id)
        queue = await events.subscribe_async(conversation_id, "session_state")
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            try:
                msg = await asyncio.wait_for(queue.get(), timeout=remaining)
            except asyncio.TimeoutError:
                break
            if msg.get("session_id") == session_id and msg.get("state") in _TERMINAL_STATES:
                return self.get(conversation_id, session_id)
        return self.get(conversation_id, session_id)

    async def cancel(self, conversation_id: str, session_id: str) -> SessionRecord | None:
        """请求打断 Session：先置 cancel_requested 让 Agent 自行退出，子进程超时再 SIGTERM。"""
        record = self.get(conversation_id, session_id)
        if record is None:
            return None
        if record.state in ("queued", "running"):
            # Agent 通过 IPC 订阅 cancel_requested 事件实现即时打断
            self._update(conversation_id, session_id, state="cancel_requested")
            self._emit(conversation_id, session_id, "cancel_requested", {})
        task = self._running.get((conversation_id, session_id))
        if task and not task.done():
            # API 进程内协程任务：取消协程，CancelledError 路径会落 cancelled
            task.cancel()
            # 给协程一点时间落到终态，但最长 3s
            record = await self._wait_terminal(conversation_id, session_id, 3.0)
        elif record.pid and record.state in ("queued", "running", "cancel_requested"):
            # 子进程任务：通过事件等待终态，3s 超时后 SIGTERM
            current = await self._wait_terminal(conversation_id, session_id, 3.0)
            if current is not None and current.state == "cancel_requested":
                try:
                    os.kill(record.pid, signal.SIGTERM)
                    # executor 的 SIGTERM 处理器会自行落 cancelled
                except (ProcessLookupError, PermissionError, OSError):
                    self._update(conversation_id, session_id, state="interrupted")
        self._cancel_descendants(conversation_id, session_id)
        return self.get(conversation_id, session_id)

    def _cancel_descendants(self, conversation_id: str, parent_session_id: str) -> None:
        """级联打断父 Session 派生的子 Agent 请求、子 Session 和计算任务。"""
        db = ConversationDB(conversation_id)

        def terminate(pid: int) -> None:
            if pid == os.getpid():
                return
            try:
                # executor 安装了 SIGTERM 处理器，会自行落 cancelled
                os.kill(pid, signal.SIGTERM)
            except (ProcessLookupError, PermissionError, OSError):
                pass

        session_store.cancel_descendants(db, parent_session_id, terminate)


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
        yolo: bool = False,
    ) -> tuple[str, SessionRecord]:
        if conversation_id is None:
            conversation_id = self.create_conversation().id
        else:
            validate_conversation_id(conversation_id)
        return conversation_id, self.session_runner.submit(
            query, conversation_id, working_directory, yolo
        )

    def list_conversations(self) -> list[dict]:
        return conversation_repo.list_conversations()

    def delete_all_conversations(self) -> int:
        """删除所有会话数据（包括消息、Session、审批等）。"""
        root = paths.conversations_dir()
        count = 0
        if root.exists():
            for entry in list(root.iterdir()):
                if entry.is_dir() and _CONVERSATION_ID.fullmatch(entry.name):
                    shutil.rmtree(entry, ignore_errors=True)
                    count += 1
        return count

    def get_conversation_messages(self, conversation_id: str) -> list[dict]:
        validate_conversation_id(conversation_id)
        return conversation_repo.conversation_messages(conversation_id)

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
            for row in session_store.list_pending_approvals(db):
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
        return await session_store.adecide_approval(db, approval_id, decision, denial_reason)
