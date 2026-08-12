"""Cloudra 应用服务层：供 CLI 和 HTTP API 共用。"""

from __future__ import annotations

import asyncio
import hashlib
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

from cloudra.base.conversation_class import Conversation
from cloudra.dag.models import (
    OrchestrationMode,
    build_orchestration_config,
    normalize_orchestration_mode,
)
from cloudra.infra import events
from cloudra.infra.config import get_config
from cloudra.persistence import conversation_repo, paths
from cloudra.persistence.database import ConversationDB
from cloudra.persistence.workspace import resolve_working_directory
from cloudra.runtime.runner import run_task_async
from cloudra.services import control_store, session_store

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
    node_id: str | None = None
    workspace_id: str | None = None
    working_directory: str | None = None
    orchestration_mode: str = OrchestrationMode.STANDARD.value
    orchestration_config: str = "{}"

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class PreparedAppend:
    conversation_id: str
    session_id: str
    agent_id: str
    command_id: str
    mode: Literal["inject", "resume", "cancel", "existing"]
    content: str
    working_directory: str | None
    node_id: str | None
    workspace_id: str | None
    orchestration_mode: str = OrchestrationMode.STANDARD.value
    orchestration_config: str = "{}"
    command: control_store.ClientCommand | None = None
    existing_record: SessionRecord | None = None
    agent_type: str = "coordinator"
    parent_session_id: str | None = None


@dataclass(frozen=True, slots=True)
class PreparedCancel:
    conversation_id: str
    session_id: str
    command_id: str
    command: control_store.ClientCommand
    record: SessionRecord | None
    skip: bool


@dataclass(frozen=True, slots=True)
class PreparedInteraction:
    conversation_id: str
    command_id: str
    interaction_id: str
    response: str
    command: control_store.ClientCommand
    latest: control_store.Interaction | None
    skip: bool


@dataclass(frozen=True, slots=True)
class PreparedSessionCreate:
    """submit_session_command 的准备产物：DB 阶段（线程）与调度阶段（loop 线程）之间的交接。"""

    conversation_id: str
    session_id: str
    command_id: str
    query: str
    working_directory: str | None
    mode: OrchestrationMode
    orchestration_config: dict | None
    command: control_store.ClientCommand
    record: SessionRecord
    needs_schedule: bool
    needs_finish: bool


_SESSION_COLUMNS = """session_id, agent_id, agent_type, parent_session_id, query,
state, result, error, pid, worker_id, created_at, started_at, heartbeat_at,
finished_at, exit_code, node_id, workspace_id, working_directory"""
_SESSION_COLUMNS += ", orchestration_mode, orchestration_config"


class SessionRunner:
    """为 API 启动 Coordinator Session，并管理当前进程中的异步执行句柄。"""

    def __init__(self, service: "CloudraService") -> None:
        self.service = service
        self._running: dict[tuple[str, str], asyncio.Task] = {}
        self.worker_id = f"api:{os.getpid()}:{uuid.uuid4().hex[:8]}"

    def _prepare_submission(
        self,
        query: str,
        conversation_id: str,
        session_id: str,
        **route,
    ) -> tuple[SessionRecord, bool]:
        """Synchronous DB/control-store phase of submission.

        Returns ``(record, created)``.  When ``created`` is ``False`` the caller
        must not schedule a new execution task.
        """
        db = ConversationDB(conversation_id).init()
        mode = normalize_orchestration_mode(route.get("orchestration_mode"))
        orchestration_config = route.get("orchestration_config")
        if orchestration_config is None:
            orchestration_config = build_orchestration_config(mode)
        existing = self.get(conversation_id, session_id)
        if existing is not None:
            return existing, False
        try:
            session_store.insert_queued_session(
                db,
                session_id=session_id,
                agent_id="a-0",
                agent_type="coordinator",
                query=query,
                node_id=route.get("node_id"),
                workspace_id=route.get("workspace_id"),
                working_directory=route.get("working_directory"),
                orchestration_mode=mode.value,
                orchestration_config=orchestration_config,
            )
        except sqlite3.IntegrityError:
            # A concurrent replay of the same idempotent create command won.
            existing = self.get(conversation_id, session_id)
            if existing is not None:
                return existing, False
            raise
        self._emit(
            conversation_id,
            session_id,
            "queued",
            {
                "query": query,
                "yolo": route.get("yolo", False),
                "orchestration_mode": mode.value,
            },
        )
        return self.get(conversation_id, session_id), True

    def _schedule_execution(
        self,
        query: str,
        conversation_id: str,
        session_id: str,
        working_directory: str | None,
        yolo: bool,
        mode: OrchestrationMode,
        orchestration_config: dict | None,
    ) -> None:
        """调度已 prepare 的 Session 执行；只能在有 running loop 的线程调用。

        asyncio.create_task 要求 running loop——to_thread 工作线程里调用会
        炸 RuntimeError: no running event loop（HTTP 层表现为提交被
        500/409 拒绝），所以 DB 阶段与调度必须分开。
        """
        task = asyncio.create_task(
            self._execute(
                query,
                conversation_id,
                session_id,
                working_directory,
                yolo,
                mode,
                orchestration_config,
            )
        )
        self._running[(conversation_id, session_id)] = task

    async def submit_async(
        self,
        query: str,
        conversation_id: str,
        **kwargs,
    ) -> SessionRecord:
        session_id = kwargs.pop("session_id", None) or f"a-0_run_{uuid.uuid4().hex}"
        mode = normalize_orchestration_mode(kwargs.get("orchestration_mode"))
        kwargs["orchestration_mode"] = mode
        kwargs["working_directory"] = resolve_working_directory(
            kwargs.get("working_directory")
        )
        if kwargs.get("orchestration_config") is None:
            kwargs["orchestration_config"] = build_orchestration_config(mode)
        record, created = await asyncio.to_thread(
            self._prepare_submission, query, conversation_id, session_id, **kwargs
        )
        if created:
            self._schedule_execution(
                query,
                conversation_id,
                session_id,
                kwargs.get("working_directory"),
                kwargs.get("yolo", False),
                kwargs.get("orchestration_mode", OrchestrationMode.STANDARD),
                kwargs.get("orchestration_config"),
            )
        return record

    def submit(
        self,
        query: str,
        conversation_id: str,
        working_directory: str | None = None,
        yolo: bool = False,
        session_id: str | None = None,
        node_id: str | None = None,
        workspace_id: str | None = None,
        orchestration_mode: str | OrchestrationMode = OrchestrationMode.STANDARD,
        orchestration_config: dict | None = None,
    ) -> SessionRecord:
        session_id = session_id or f"a-0_run_{uuid.uuid4().hex}"
        mode = normalize_orchestration_mode(orchestration_mode)
        if orchestration_config is None:
            orchestration_config = build_orchestration_config(mode)
        working_directory = resolve_working_directory(working_directory)
        record, created = self._prepare_submission(
            query,
            conversation_id,
            session_id,
            working_directory=working_directory,
            yolo=yolo,
            node_id=node_id,
            workspace_id=workspace_id,
            orchestration_mode=mode,
            orchestration_config=orchestration_config,
        )
        if created:
            self._schedule_execution(
                query,
                conversation_id,
                session_id,
                working_directory,
                yolo,
                mode,
                orchestration_config,
            )
        return record

    async def _execute(
        self,
        query: str,
        conversation_id: str,
        session_id: str,
        working_directory: str | None = None,
        yolo: bool = False,
        orchestration_mode: str | OrchestrationMode = OrchestrationMode.STANDARD,
        orchestration_config: dict | None = None,
    ) -> None:
        # Session 级 YOLO 开关：只作用于本会话任务及其派生协程
        from cloudra.infra.yolo_guard import set_session_yolo
        set_session_yolo(yolo)
        now = datetime.now(timezone.utc).isoformat()
        # 同步 SQLite 写（含 time.sleep 锁退避）一律进线程，避免卡住事件循环
        if not await asyncio.to_thread(self._claim, conversation_id, session_id, now):
            return
        heartbeat = asyncio.create_task(self._heartbeat(conversation_id, session_id))
        try:
            from cloudra.tools.Interactool.ask_user import use_input_handler

            async def wait_for_user(prompt: str) -> str:
                return await self._wait_for_interaction(
                    conversation_id,
                    session_id,
                    prompt,
                )

            with use_input_handler(wait_for_user):
                if working_directory is None:
                    result = await self.service.run_task(
                        query,
                        conversation_id,
                        session_id=session_id,
                        orchestration_mode=orchestration_mode,
                        orchestration_config=orchestration_config,
                    )
                else:
                    result = await self.service.run_task(
                        query,
                        conversation_id,
                        session_id=session_id,
                        working_directory=working_directory,
                        orchestration_mode=orchestration_mode,
                        orchestration_config=orchestration_config,
                    )
            await asyncio.to_thread(
                self._update,
                conversation_id,
                session_id,
                state="completed",
                result=result,
                finished_at=datetime.now(timezone.utc).isoformat(),
                exit_code=0,
            )
            await asyncio.to_thread(
                self._emit, conversation_id, session_id, "completed", {"result": result}
            )
        except asyncio.CancelledError:
            current = self.get(conversation_id, session_id)
            if current is None or current.state not in (
                "cancelled",
                "killed",
                "failed",
                "completed",
                "interrupted",
            ):
                await asyncio.to_thread(
                    self._update,
                    conversation_id,
                    session_id,
                    state="cancelled",
                    finished_at=datetime.now(timezone.utc).isoformat(),
                )
                await asyncio.to_thread(
                    self._emit, conversation_id, session_id, "cancelled", {}
                )
            raise
        except Exception as exc:
            await asyncio.to_thread(
                self._update,
                conversation_id,
                session_id,
                state="failed",
                error=str(exc),
                finished_at=datetime.now(timezone.utc).isoformat(),
                exit_code=1,
            )
            await asyncio.to_thread(
                self._emit, conversation_id, session_id, "failed", {"error": str(exc)}
            )
        finally:
            heartbeat.cancel()
            self._running.pop((conversation_id, session_id), None)

    async def _wait_for_interaction(
        self,
        conversation_id: str,
        session_id: str,
        prompt: str,
    ) -> str:
        """Persist an Agent question and wait for exactly one remote response."""

        from cloudra.services.interactions import wait_for_user_response

        return await wait_for_user_response(
            conversation_id=conversation_id,
            session_id=session_id,
            agent_id="a-0",
            prompt=prompt,
        )

    def _claim(self, conversation_id: str, session_id: str, now: str) -> bool:
        db = ConversationDB(conversation_id)
        if session_store.claim_session(db, session_id, pid=os.getpid(), worker_id=self.worker_id):
            self._emit(conversation_id, session_id, "running", {"worker_id": self.worker_id})
            return True
        return False

    async def _heartbeat(self, conversation_id: str, session_id: str) -> None:
        while True:
            await asyncio.sleep(5)
            await asyncio.to_thread(
                self._update,
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
        if not db.migrate_if_needed():
            return []
        with db.connect() as owned:
            return _fetch(owned)

    def recover_stale_sessions(self, timeout_seconds: int = 60) -> int:
        """把失去心跳的 running/waiting/cancel_requested Session 标为 interrupted，避免永久假运行。"""
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
                from cloudra.infra.slurm import cancel_interrupted_jobs

                cancel_interrupted_jobs(db)
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
        db = ConversationDB(conversation_id)
        if not db.migrate_if_needed():
            return None
        with db.connect() as owned:
            return _fetch(owned)

    def list(self, conversation_id: str) -> list[SessionRecord]:
        validate_conversation_id(conversation_id)
        db = ConversationDB(conversation_id)
        if not db.migrate_if_needed():
            return []
        with db.connect() as conn:
            rows = conn.execute(
                f"SELECT {_SESSION_COLUMNS} FROM session ORDER BY created_at DESC"
            ).fetchall()
        return [SessionRecord(*row) for row in rows]

    def list_children(self, conversation_id: str, parent_session_id: str) -> list[SessionRecord]:
        """查询指定父 Session 的直接子 Session（用于 TUI 绘制 Agent 树）。"""
        validate_conversation_id(conversation_id)
        validate_session_id(parent_session_id)
        db = ConversationDB(conversation_id)
        if not db.migrate_if_needed():
            return []
        with db.connect() as conn:
            rows = conn.execute(
                f"""SELECT {_SESSION_COLUMNS} FROM session
                WHERE parent_session_id = ? ORDER BY created_at ASC""",
                (parent_session_id,),
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
        if record.state in (
            "queued",
            "running",
            "waiting",
            "waiting_for_user",
            "waiting_for_approval",
            "waiting_for_device",
        ):
            # Agent 通过 IPC 订阅 cancel_requested 事件实现即时打断
            await asyncio.to_thread(
                self._update, conversation_id, session_id, state="cancel_requested"
            )
            await asyncio.to_thread(
                self._emit, conversation_id, session_id, "cancel_requested", {}
            )
        task = self._running.get((conversation_id, session_id))
        if task and not task.done():
            # API 进程内协程任务：取消协程，CancelledError 路径会落 cancelled
            task.cancel()
            # 给协程一点时间落到终态，但最长 3s
            record = await self._wait_terminal(conversation_id, session_id, 3.0)
            if record is not None and record.state == "cancel_requested":
                # 协程卡在不可中断的阻塞点（如线程中的同步调用）时，不能永远
                # 停在 cancel_requested——否则该会话再也发不出消息（卡死）。
                await asyncio.to_thread(
                    self._update,
                    conversation_id,
                    session_id,
                    state="cancelled",
                    finished_at=datetime.now(timezone.utc).isoformat(),
                )
                await asyncio.to_thread(
                    self._emit, conversation_id, session_id, "cancelled", {}
                )
                record = self.get(conversation_id, session_id)
        elif record.pid and record.state in (
            "queued",
            "running",
            "waiting",
            "waiting_for_user",
            "waiting_for_approval",
            "waiting_for_device",
            "cancel_requested",
        ):
            # 子进程任务：通过事件等待终态，3s 超时后 SIGTERM
            current = await self._wait_terminal(conversation_id, session_id, 3.0)
            if current is not None and current.state == "cancel_requested":
                try:
                    os.kill(record.pid, signal.SIGTERM)
                    # executor 的 SIGTERM 处理器会自行落 cancelled
                except (ProcessLookupError, PermissionError, OSError):
                    await asyncio.to_thread(
                        self._update, conversation_id, session_id, state="interrupted"
                    )
        await asyncio.to_thread(
            self._cancel_descendants, conversation_id, session_id
        )
        return self.get(conversation_id, session_id)

    async def force_cancel(
        self, conversation_id: str, session_id: str
    ) -> SessionRecord | None:
        """强制终止：立刻取消协程、SIGTERM 子进程，并落 ``killed``。

        与 ``cancel`` 的区别：不等待优雅退出；本进程内的 Coordinator
        （``pid == os.getpid()``）只 ``task.cancel()``，绝不 SIGTERM 自己。
        """
        record = self.get(conversation_id, session_id)
        if record is None:
            return None
        activeish = (
            "queued",
            "running",
            "waiting",
            "waiting_for_user",
            "waiting_for_approval",
            "waiting_for_device",
            "cancel_requested",
        )
        if record.state not in activeish:
            return record
        if record.state != "cancel_requested":
            await asyncio.to_thread(
                self._update, conversation_id, session_id, state="cancel_requested"
            )
            await asyncio.to_thread(
                self._emit, conversation_id, session_id, "cancel_requested", {}
            )
        task = self._running.get((conversation_id, session_id))
        if task and not task.done():
            task.cancel()
        await asyncio.to_thread(self._cancel_descendants, conversation_id, session_id)
        if record.pid and record.pid != os.getpid():
            try:
                os.kill(record.pid, signal.SIGTERM)
            except (ProcessLookupError, PermissionError, OSError):
                pass
        finished = datetime.now(timezone.utc).isoformat()
        await asyncio.to_thread(
            self._update,
            conversation_id,
            session_id,
            state="killed",
            finished_at=finished,
        )
        await asyncio.to_thread(
            self._emit, conversation_id, session_id, "killed", {}
        )
        self._running.pop((conversation_id, session_id), None)
        # 子 Agent 被强制终止时通知 Coordinator（与 executor 收尾一致）
        if (
            (record.agent_id or "a-0") != "a-0"
            or record.parent_session_id
            or (record.agent_type or "").lower() in {"follower", "subagent"}
        ):
            try:
                from cloudra.persistence.context_manager import ContextManager
                from cloudra.persistence.database import get_database_path

                label = record.agent_id or session_id
                await ContextManager.inject_event(
                    conversation_id=conversation_id,
                    agent_id="a-0",
                    event_type="subagent",
                    content=(
                        f"子 Agent {label} (session={session_id}) 已被强制终止（killed）。"
                    ),
                    db_path=get_database_path(conversation_id),
                )
            except Exception:
                pass
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
        from cloudra.persistence.artifacts import ArtifactService
        from cloudra.services.device_broker import DeviceBroker

        self.config = get_config()
        self.artifacts = ArtifactService(Path(self.config.data_dir))
        self.device_broker = DeviceBroker(Path(self.config.data_dir))
        self.session_runner = SessionRunner(self)

    def create_conversation(self) -> Conversation:
        return Conversation()

    def _dag_read_context(self, conversation_id: str):
        """Return existing DAG objects without creating a bundle on a read path."""
        from cloudra.dag.engine import DagEngine
        from cloudra.dag.store import DagStore, GraphBundleNotFound

        validate_conversation_id(conversation_id)
        db = ConversationDB(conversation_id)
        if not Path(db.path).is_file():
            return None
        db.migrate_if_needed()
        store = DagStore(db)
        try:
            store.load_bundle()
        except GraphBundleNotFound:
            return None
        return store, DagEngine(store)

    def _dag_conversation_mode(self, conversation_id: str) -> OrchestrationMode:
        """读取会话真实的编排模式（session 创建时写入、之后不可变）。

        优先取最新一条 coordinator session 的 orchestration_mode；没有任何
        session 记录（如图谱由测试直接创建）时保持历史默认 dag_record。
        """
        db = ConversationDB(conversation_id)
        with db.connect() as conn:
            row = conn.execute(
                "SELECT orchestration_mode FROM session"
                " WHERE agent_type = 'coordinator'"
                " ORDER BY created_at DESC, rowid DESC LIMIT 1"
            ).fetchone()
            if row is None:
                row = conn.execute(
                    "SELECT orchestration_mode FROM session"
                    " ORDER BY created_at DESC, rowid DESC LIMIT 1"
                ).fetchone()
        if row is None or not row[0]:
            return OrchestrationMode.DAG_RECORD
        return normalize_orchestration_mode(row[0])

    def dag_projection(self, conversation_id: str) -> dict | None:
        from cloudra.dag.completion import build_projection

        context = self._dag_read_context(conversation_id)
        if context is None:
            return None
        store, engine = context
        projection = build_projection(
            engine.snapshot(),
            mode=self._dag_conversation_mode(conversation_id),
            contract=store.load_coverage_contract(),
            history=engine.history(limit=8),
        )
        return projection.model_dump(mode="json")

    def dag_graph(self, conversation_id: str, graph_kind: str) -> dict | None:
        from cloudra.dag.models import GraphKind

        kind = GraphKind(graph_kind)
        context = self._dag_read_context(conversation_id)
        if context is None:
            return None
        _store, engine = context
        snapshot = engine.snapshot()
        graph = snapshot.process if kind is GraphKind.PROCESS else snapshot.delivery
        return graph.model_dump(mode="json")

    def dag_delivery_report(self, conversation_id: str) -> dict | None:
        from cloudra.dag.completion import evaluate_delivery

        context = self._dag_read_context(conversation_id)
        if context is None:
            return None
        store, engine = context
        report = evaluate_delivery(
            engine.snapshot().delivery,
            store.load_coverage_contract(),
        )
        return report.model_dump(mode="json")

    def dag_history(
        self,
        conversation_id: str,
        *,
        after_revision: int = 0,
    ) -> list[dict] | None:
        context = self._dag_read_context(conversation_id)
        if context is None:
            return None
        _store, engine = context
        rows = engine.history(limit=500)
        if after_revision <= 0:
            return rows
        return [
            row
            for row in rows
            if max(row.get("resulting_revisions", {}).values(), default=0)
            > after_revision
        ]

    def dag_apply_user_mutation(
        self,
        conversation_id: str,
        operations: list[dict],
        base_revisions: dict[str, int],
        rationale: str = "",
    ) -> dict | None:
        """Apply one user-initiated mutation batch (actor=USER) via the engine.

        Returns the MutationResult dump, or None when no DAG bundle exists.
        The engine enforces atomicity, acyclicity, reference resolution, and
        the user privilege boundary (only users may waive gates or lower
        coverage requirements; evidence-derived levels stay harness-only).
        """
        from cloudra.dag.models import GraphActor, MutationBatch, parse_graph_operation

        context = self._dag_read_context(conversation_id)
        if context is None:
            return None
        _store, engine = context
        batch = MutationBatch(
            session_id="user",
            actor=GraphActor.USER,
            actor_id="user",
            base_revisions=base_revisions,
            operations=[parse_graph_operation(op) for op in operations],
            rationale=rationale,
        )
        result = engine.apply_batch(batch)
        return result.model_dump(mode="json")

    async def dag_request_replan(
        self,
        conversation_id: str,
        note: str = "",
    ) -> dict | None:
        """用户主动请求 Supervisor 重新规划（trigger=user_replan）。

        仅 dag_guided 会话可用：其他模式抛 ValueError（API 映射为 422）。
        无 DAG bundle 时返回 None。返回 Supervisor 结果摘要；Supervisor 未
        运行或运行失败（顾问角色，异常在 DagController 内吞掉）时 result
        为 None，也返回带说明的摘要。
        """
        from cloudra.core.supervisor import GraphSupervisor
        from cloudra.dag.controller import DagController

        context = self._dag_read_context(conversation_id)
        if context is None:
            return None
        mode = self._dag_conversation_mode(conversation_id)
        if mode is not OrchestrationMode.DAG_GUIDED:
            raise ValueError(
                f"重新规划仅在 dag_guided 模式可用（当前会话: {mode.value}）"
            )
        db = ConversationDB(conversation_id)
        db.migrate_if_needed()
        controller = DagController(
            db,
            "user_replan",
            mode,
            conversation_id=conversation_id,
            supervisor=GraphSupervisor(conversation_id=conversation_id),
        )
        # initialize() 不再自动督导；这里显式加载契约后走 user_replan。
        controller.contract = controller.store.load_coverage_contract()
        controller._initialized = True
        result = await controller.maybe_supervise(
            "user_replan", coordinator_request=note or None
        )
        if result is None:
            return {
                "trigger": "user_replan",
                "supervised": False,
                "summary": "Supervisor 未产出结果（运行失败或未触发，详见日志）",
            }
        accepted = sum(1 for m in result.mutations if m.get("accepted"))
        summary = (
            f"rounds={result.rounds} "
            f"mutations={accepted}/{len(result.mutations)}"
        )
        if result.note:
            summary += f" note={result.note}"
        return {
            "trigger": result.trigger,
            "supervised": True,
            "rounds": result.rounds,
            "mutations_accepted": accepted,
            "mutations_total": len(result.mutations),
            "note": result.note,
            "summary": summary,
        }

    async def run_task(
        self,
        query: str,
        conversation_id: str | None = None,
        verbose: bool = False,
        session_id: str | None = None,
        working_directory: str | None = None,
        interactive_approval: bool = False,
        orchestration_mode: str | OrchestrationMode = OrchestrationMode.STANDARD,
        orchestration_config: dict | None = None,
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
            orchestration_mode=orchestration_mode,
            orchestration_config=orchestration_config,
        )

    def submit_session(
        self,
        query: str,
        conversation_id: str | None = None,
        working_directory: str | None = None,
        yolo: bool = False,
        orchestration_mode: str | OrchestrationMode = OrchestrationMode.STANDARD,
        orchestration_config: dict | None = None,
    ) -> tuple[str, SessionRecord]:
        if conversation_id is None:
            conversation_id = self.create_conversation().id
        else:
            validate_conversation_id(conversation_id)
        return conversation_id, self.session_runner.submit(
            query,
            conversation_id,
            working_directory=working_directory,
            yolo=yolo,
            orchestration_mode=orchestration_mode,
            orchestration_config=orchestration_config,
        )

    async def submit_session_async(
        self,
        query: str,
        conversation_id: str | None = None,
        working_directory: str | None = None,
        yolo: bool = False,
        orchestration_mode: str | OrchestrationMode = OrchestrationMode.STANDARD,
        orchestration_config: dict | None = None,
    ) -> tuple[str, SessionRecord]:
        if conversation_id is None:
            conversation = await asyncio.to_thread(self.create_conversation)
            conversation_id = conversation.id
        else:
            validate_conversation_id(conversation_id)
        record = await self.session_runner.submit_async(
            query,
            conversation_id,
            working_directory=working_directory,
            yolo=yolo,
            orchestration_mode=orchestration_mode,
            orchestration_config=orchestration_config,
        )
        return conversation_id, record

    @staticmethod
    def _command_session_id(command_id: str, prefix: str = "cmd") -> str:
        digest = hashlib.sha256(command_id.encode("utf-8")).hexdigest()[:32]
        return f"a-0_{prefix}_{digest}"

    def _prepare_session_command(
        self,
        *,
        command_id: str,
        query: str,
        conversation_id: str,
        working_directory: str | None = None,
        node_id: str = "node-local",
        workspace_id: str = "default",
        orchestration_mode: str | OrchestrationMode = OrchestrationMode.STANDARD,
        orchestration_config: dict | None = None,
    ) -> PreparedSessionCreate:
        """submit_session_command 的同步 DB 阶段（可在 to_thread 工作线程里跑）。"""

        validate_conversation_id(conversation_id)
        mode = normalize_orchestration_mode(orchestration_mode)
        if orchestration_config is None:
            orchestration_config = build_orchestration_config(mode)
        session_id = self._command_session_id(command_id)
        db = ConversationDB(conversation_id).init()
        command, _ = control_store.receive_command(
            db,
            command_id=command_id,
            conversation_id=conversation_id,
            session_id=session_id,
            command_type="session.create",
            payload={
                "query": query,
                "node_id": node_id,
                "workspace_id": workspace_id,
                "yolo": False,
                "orchestration_mode": mode.value,
                "orchestration_config": orchestration_config,
            },
        )
        if command.state == "failed":
            raise RuntimeError(command.error or "创建 Session 的控制命令失败")
        if command.state == "applied":
            record = self.session_runner.get(conversation_id, session_id)
            if record is None:
                raise RuntimeError("控制命令已生效，但对应 Session 不存在")
            return PreparedSessionCreate(
                conversation_id=conversation_id,
                session_id=session_id,
                command_id=command_id,
                query=query,
                working_directory=working_directory,
                mode=mode,
                orchestration_config=orchestration_config,
                command=command,
                record=record,
                needs_schedule=False,
                needs_finish=False,
            )

        if control_store.claim_command(db, command_id):
            try:
                record, created = self.session_runner._prepare_submission(
                    query,
                    conversation_id,
                    session_id,
                    working_directory=working_directory,
                    yolo=False,
                    node_id=node_id,
                    workspace_id=workspace_id,
                    orchestration_mode=mode,
                    orchestration_config=orchestration_config,
                )
            except Exception as exc:
                control_store.finish_command(db, command_id, error=str(exc))
                raise
            return PreparedSessionCreate(
                conversation_id=conversation_id,
                session_id=session_id,
                command_id=command_id,
                query=query,
                working_directory=working_directory,
                mode=mode,
                orchestration_config=orchestration_config,
                command=command,
                record=record,
                needs_schedule=created,
                needs_finish=True,
            )

        # A concurrent replay is already applying the deterministic Session.
        record = self.session_runner.get(conversation_id, session_id)
        if record is None:
            raise RuntimeError("控制命令正在生效，请稍后查询")
        command = control_store.finish_command(
            db,
            command_id,
            result={"session_id": session_id},
        )
        return PreparedSessionCreate(
            conversation_id=conversation_id,
            session_id=session_id,
            command_id=command_id,
            query=query,
            working_directory=working_directory,
            mode=mode,
            orchestration_config=orchestration_config,
            command=command,
            record=record,
            needs_schedule=False,
            needs_finish=False,
        )

    def _finish_session_command(
        self,
        prepared: PreparedSessionCreate,
    ) -> control_store.ClientCommand:
        """session.create 命令的收尾（事件 + finish，同步 DB，可在线程里跑）。"""
        self.session_runner._emit(
            prepared.conversation_id,
            prepared.session_id,
            "client_command_received",
            {"command_id": prepared.command_id, "command_type": "session.create"},
        )
        command = control_store.finish_command(
            ConversationDB(prepared.conversation_id).init(),
            prepared.command_id,
            result={"session_id": prepared.session_id},
        )
        self.session_runner._emit(
            prepared.conversation_id,
            prepared.session_id,
            "client_command_applied",
            {"command_id": prepared.command_id, "command_type": "session.create"},
        )
        return command

    def _apply_prepared_session_command(
        self,
        prepared: PreparedSessionCreate,
    ) -> tuple[control_store.ClientCommand, SessionRecord]:
        """调度 + 收尾；调度只能在有 running loop 的线程做（见 _schedule_execution）。"""
        if prepared.needs_schedule:
            self.session_runner._schedule_execution(
                prepared.query,
                prepared.conversation_id,
                prepared.session_id,
                prepared.working_directory,
                False,
                prepared.mode,
                prepared.orchestration_config,
            )
        if prepared.needs_finish:
            return self._finish_session_command(prepared), prepared.record
        return prepared.command, prepared.record

    def submit_session_command(
        self,
        *,
        command_id: str,
        query: str,
        conversation_id: str,
        working_directory: str | None = None,
        node_id: str = "node-local",
        workspace_id: str = "default",
        orchestration_mode: str | OrchestrationMode = OrchestrationMode.STANDARD,
        orchestration_config: dict | None = None,
    ) -> tuple[control_store.ClientCommand, SessionRecord]:
        """Create one Session for an idempotent remote command.

        只能在有 running loop 的线程调用（CLI/测试上下文）；HTTP 路由与
        异步调用方必须用 submit_session_command_async——本方法在 to_thread
        工作线程里跑会在调度阶段炸 RuntimeError: no running event loop。
        """
        prepared = self._prepare_session_command(
            command_id=command_id,
            query=query,
            conversation_id=conversation_id,
            working_directory=working_directory,
            node_id=node_id,
            workspace_id=workspace_id,
            orchestration_mode=orchestration_mode,
            orchestration_config=orchestration_config,
        )
        return self._apply_prepared_session_command(prepared)

    async def submit_session_command_async(
        self,
        *,
        command_id: str,
        query: str,
        conversation_id: str,
        working_directory: str | None = None,
        node_id: str = "node-local",
        workspace_id: str = "default",
        orchestration_mode: str | OrchestrationMode = OrchestrationMode.STANDARD,
        orchestration_config: dict | None = None,
    ) -> tuple[control_store.ClientCommand, SessionRecord]:
        """submit_session_command 的事件循环安全变体：DB 阶段卸载到线程，调度留在 loop 线程。"""
        prepared = await asyncio.to_thread(
            self._prepare_session_command,
            command_id=command_id,
            query=query,
            conversation_id=conversation_id,
            working_directory=working_directory,
            node_id=node_id,
            workspace_id=workspace_id,
            orchestration_mode=orchestration_mode,
            orchestration_config=orchestration_config,
        )
        return self._apply_prepared_session_command(prepared)

    def _prepare_append_message(
        self,
        request: dict,
    ) -> PreparedAppend:
        validate_conversation_id(request["conversation_id"])
        validate_session_id(request["session_id"])
        db = ConversationDB(request["conversation_id"]).init()
        target = self.session_runner.get(
            request["conversation_id"], request["session_id"]
        )
        if target is None:
            raise ValueError("Session 不存在")
        command, _ = control_store.receive_command(
            db,
            command_id=request["command_id"],
            conversation_id=request["conversation_id"],
            session_id=request["session_id"],
            command_type="session.message.append",
            payload={"content": request["content"]},
        )
        if command.state == "failed":
            raise RuntimeError(command.error or "追加消息失败")
        if command.state == "applied":
            result_session_id = (command.result or {}).get(
                "session_id", request["session_id"]
            )
            record = self.session_runner.get(
                request["conversation_id"], result_session_id
            )
            if record is None:
                raise RuntimeError("追加消息已生效，但目标 Session 不存在")
            return PreparedAppend(
                conversation_id=request["conversation_id"],
                session_id=request["session_id"],
                agent_id=target.agent_id or "a-0",
                command_id=request["command_id"],
                mode="existing",
                content=request["content"],
                working_directory=request.get("working_directory")
                or target.working_directory,
                node_id=target.node_id,
                workspace_id=target.workspace_id,
                command=command,
                existing_record=record,
                agent_type=target.agent_type or "coordinator",
                parent_session_id=target.parent_session_id,
            )
        if not control_store.claim_command(db, request["command_id"]):
            raise RuntimeError("控制命令正在生效，请稍后查询")

        self.session_runner._emit(
            request["conversation_id"],
            request["session_id"],
            "client_command_received",
            {
                "command_id": request["command_id"],
                "command_type": "session.message.append",
            },
        )
        if target.state == "cancel_requested":
            return PreparedAppend(
                conversation_id=request["conversation_id"],
                session_id=request["session_id"],
                agent_id=target.agent_id or "a-0",
                command_id=request["command_id"],
                mode="cancel",
                content=request["content"],
                working_directory=request.get("working_directory")
                or target.working_directory,
                node_id=target.node_id,
                workspace_id=target.workspace_id,
                orchestration_mode=target.orchestration_mode
                or OrchestrationMode.STANDARD.value,
                orchestration_config=target.orchestration_config or "{}",
                agent_type=target.agent_type or "coordinator",
                parent_session_id=target.parent_session_id,
            )
        mode: Literal["inject", "resume"] = (
            "resume" if target.state in _TERMINAL_STATES else "inject"
        )
        # DB 仍标 running/waiting 但本进程已无活 runner（崩溃、隔离 TUI、
        # 假 completed→waiting 残留）时，纯 inject 只会把事件停在 pending。
        if mode == "inject" and not self._session_has_live_runner(
            request["conversation_id"], request["session_id"]
        ):
            mode = "resume"
        return PreparedAppend(
            conversation_id=request["conversation_id"],
            session_id=request["session_id"],
            agent_id=target.agent_id or "a-0",
            command_id=request["command_id"],
            mode=mode,
            content=request["content"],
            working_directory=request.get("working_directory")
            or target.working_directory,
            node_id=target.node_id,
            workspace_id=target.workspace_id,
            orchestration_mode=target.orchestration_mode
            or OrchestrationMode.STANDARD.value,
            orchestration_config=target.orchestration_config or "{}",
            agent_type=target.agent_type or "coordinator",
            parent_session_id=target.parent_session_id,
        )

    def _existing_append_result(
        self,
        prepared: PreparedAppend,
    ) -> tuple[control_store.ClientCommand, SessionRecord]:
        assert prepared.command is not None
        assert prepared.existing_record is not None
        return prepared.command, prepared.existing_record

    def _finish_append_message(
        self,
        prepared: PreparedAppend,
        record: SessionRecord,
    ) -> tuple[control_store.ClientCommand, SessionRecord]:
        db = ConversationDB(prepared.conversation_id).init()
        try:
            if prepared.mode == "cancel":
                raise ValueError("Session 正在取消，不能追加消息")
            if prepared.mode == "resume":
                result = {
                    "session_id": record.session_id,
                    "resumed_from": prepared.session_id,
                }
            else:
                result = {"session_id": prepared.session_id}
            command = control_store.finish_command(
                db,
                prepared.command_id,
                result=result,
            )
            self.session_runner._emit(
                prepared.conversation_id,
                record.session_id,
                "client_command_applied",
                {
                    "command_id": prepared.command_id,
                    "command_type": "session.message.append",
                },
            )
            return command, record
        except Exception as exc:
            control_store.finish_command(db, prepared.command_id, error=str(exc))
            raise

    def _session_has_live_runner(
        self, conversation_id: str, session_id: str
    ) -> bool:
        task = self.session_runner._running.get((conversation_id, session_id))
        return task is not None and not task.done()

    @staticmethod
    def _append_supplement_text(content: str) -> str:
        return f"用户从远程控制台补充要求：{content}"

    def _is_follower_session(self, prepared: PreparedAppend) -> bool:
        """目标是否为子 Agent session（非 Coordinator）。"""
        if prepared.agent_id == "a-0":
            return False
        agent_type = (prepared.agent_type or "").lower()
        return agent_type in {"follower", "subagent"} or bool(
            prepared.parent_session_id
        )

    async def _resume_follower_session(
        self, prepared: PreparedAppend
    ) -> SessionRecord:
        """唤醒沉睡的子 Agent：复用原 session_id，经 subagent 执行路径续跑。"""
        from cloudra.infra.yolo_guard import is_yolo_enabled
        from cloudra.persistence.context_manager import ContextManager
        from cloudra.persistence.database import get_database_path
        from cloudra.tools.Managetool._subagent_dispatch import (
            run_subagent_in_process,
        )

        supplement = self._append_supplement_text(prepared.content)
        cm = ContextManager(
            agent_id=prepared.agent_id,
            conversation_id=prepared.conversation_id,
            prompt=None,
            query="",
            session_id=prepared.session_id,
        )
        await cm.append({"role": "user", "content": supplement})

        db = ConversationDB(prepared.conversation_id).init()
        payload = {
            "agent_id": prepared.agent_id,
            "query": prepared.content,
            "context": [],
            "conversation_id": prepared.conversation_id,
            "parent_session_id": prepared.parent_session_id,
            "working_directory": prepared.working_directory,
            "orchestration_mode": prepared.orchestration_mode,
            "yolo": is_yolo_enabled(),
        }
        session_id = prepared.session_id
        task_id, _, _ = await session_store.acreate_subagent_request(
            db,
            state="running",
            payload=payload,
            conversation_id=prepared.conversation_id,
            parent_session_id=prepared.parent_session_id,
            session_id_fn=lambda _tid: session_id,
        )
        db_path = get_database_path(prepared.conversation_id)
        task = asyncio.create_task(
            run_subagent_in_process(task_id, db_path, session_id)
        )
        self.session_runner._running[
            (prepared.conversation_id, session_id)
        ] = task
        self.session_runner._emit(
            prepared.conversation_id,
            session_id,
            "user_message",
            {
                "message_id": prepared.command_id,
                "command_id": prepared.command_id,
                "content": prepared.content,
                "agent_id": prepared.agent_id,
            },
        )
        record = await asyncio.to_thread(
            self.session_runner.get,
            prepared.conversation_id,
            session_id,
        )
        if record is None:
            raise RuntimeError("子 Agent 唤醒后 Session 不存在")
        return record

    async def append_session_message_command(
        self,
        *,
        command_id: str,
        conversation_id: str,
        session_id: str,
        content: str,
        working_directory: str | None = None,
    ) -> tuple[control_store.ClientCommand, SessionRecord]:
        """Inject a supplemental user message once, or wake a terminal task."""

        request = {
            "command_id": command_id,
            "conversation_id": conversation_id,
            "session_id": session_id,
            "content": content,
            "working_directory": working_directory,
        }
        prepared = await asyncio.to_thread(self._prepare_append_message, request)
        if prepared.mode == "existing":
            return await asyncio.to_thread(self._existing_append_result, prepared)
        if prepared.mode == "resume":
            if self._is_follower_session(prepared):
                record = await self._resume_follower_session(prepared)
            else:
                try:
                    orch_config = json.loads(prepared.orchestration_config or "{}")
                except (TypeError, ValueError, json.JSONDecodeError):
                    orch_config = None
                if not isinstance(orch_config, dict):
                    orch_config = None
                record = await self.session_runner.submit_async(
                    prepared.content,
                    prepared.conversation_id,
                    session_id=self._command_session_id(
                        prepared.command_id, "resume"
                    ),
                    working_directory=prepared.working_directory,
                    node_id=prepared.node_id,
                    workspace_id=prepared.workspace_id,
                    orchestration_mode=prepared.orchestration_mode,
                    orchestration_config=orch_config,
                )
        elif prepared.mode == "inject":
            from cloudra.persistence.context_manager import ContextManager

            supplement = self._append_supplement_text(prepared.content)
            # Coordinator 上下文是对话级 a-0.json；子 Agent 才按 session 分文件。
            context_session_id = (
                None if prepared.agent_id == "a-0" else prepared.session_id
            )
            cm = ContextManager(
                agent_id=prepared.agent_id,
                conversation_id=prepared.conversation_id,
                prompt=None,
                query="",
                session_id=context_session_id,
            )
            await cm.append({"role": "user", "content": supplement})
            await ContextManager.inject_event(
                conversation_id=prepared.conversation_id,
                agent_id=prepared.agent_id,
                event_type="user_message",
                content=supplement,
                db_path=ConversationDB(prepared.conversation_id).path,
                session_id=prepared.session_id,
            )
            self.session_runner._emit(
                prepared.conversation_id,
                prepared.session_id,
                "user_message",
                {
                    "message_id": prepared.command_id,
                    "command_id": prepared.command_id,
                    "content": prepared.content,
                    "agent_id": prepared.agent_id,
                },
            )
            record = await asyncio.to_thread(
                self.session_runner.get,
                prepared.conversation_id,
                prepared.session_id,
            )
        else:  # cancel
            record = await asyncio.to_thread(
                self.session_runner.get,
                prepared.conversation_id,
                prepared.session_id,
            )
        return await asyncio.to_thread(self._finish_append_message, prepared, record)

    def _prepare_cancel_command(
        self,
        command_id: str,
        conversation_id: str,
        session_id: str,
    ) -> PreparedCancel:
        validate_conversation_id(conversation_id)
        validate_session_id(session_id)
        db = ConversationDB(conversation_id).init()
        command, _ = control_store.receive_command(
            db,
            command_id=command_id,
            conversation_id=conversation_id,
            session_id=session_id,
            command_type="session.cancel",
            payload={},
        )
        if command.state == "applied":
            return PreparedCancel(
                conversation_id=conversation_id,
                session_id=session_id,
                command_id=command_id,
                command=command,
                record=self.session_runner.get(conversation_id, session_id),
                skip=True,
            )
        if command.state == "failed":
            raise RuntimeError(command.error or "取消命令失败")
        if not control_store.claim_command(db, command_id):
            return PreparedCancel(
                conversation_id=conversation_id,
                session_id=session_id,
                command_id=command_id,
                command=control_store.get_command(db, command_id),
                record=self.session_runner.get(conversation_id, session_id),
                skip=True,
            )
        return PreparedCancel(
            conversation_id=conversation_id,
            session_id=session_id,
            command_id=command_id,
            command=command,
            record=None,
            skip=False,
        )

    def _finish_cancel_command(
        self,
        prepared: PreparedCancel,
        record: SessionRecord | None,
    ) -> tuple[control_store.ClientCommand, SessionRecord | None]:
        db = ConversationDB(prepared.conversation_id).init()
        command = control_store.finish_command(
            db,
            prepared.command_id,
            result={
                "session_id": prepared.session_id,
                "state": record.state if record is not None else "missing",
            },
        )
        return command, record

    def _finish_cancel_command_error(
        self,
        prepared: PreparedCancel,
        error: str,
    ) -> None:
        db = ConversationDB(prepared.conversation_id).init()
        control_store.finish_command(db, prepared.command_id, error=error)

    async def cancel_session_command(
        self,
        *,
        command_id: str,
        conversation_id: str,
        session_id: str,
    ) -> tuple[control_store.ClientCommand, SessionRecord | None]:
        prepared = await asyncio.to_thread(
            self._prepare_cancel_command,
            command_id,
            conversation_id,
            session_id,
        )
        if prepared.skip:
            return prepared.command, prepared.record
        try:
            record = await self.session_runner.cancel(
                prepared.conversation_id, prepared.session_id
            )
            return await asyncio.to_thread(
                self._finish_cancel_command, prepared, record
            )
        except Exception as exc:
            await asyncio.to_thread(
                self._finish_cancel_command_error, prepared, str(exc)
            )
            raise

    def list_pending_interactions(
        self,
        conversation_id: str,
        *,
        session_id: str | None = None,
    ) -> list[dict]:
        validate_conversation_id(conversation_id)
        db = ConversationDB(conversation_id)
        if not Path(db.path).is_file():
            return []
        return [
            interaction.to_dict()
            for interaction in control_store.list_pending_interactions(
                db,
                session_id=session_id,
            )
        ]

    def _prepare_respond_interaction(
        self,
        command_id: str,
        conversation_id: str,
        interaction_id: str,
        response: str,
    ) -> PreparedInteraction:
        validate_conversation_id(conversation_id)
        db = ConversationDB(conversation_id).init()
        interaction = control_store.get_interaction(db, interaction_id)
        if interaction is None:
            raise ValueError("Interaction 不存在")
        command, _ = control_store.receive_command(
            db,
            command_id=command_id,
            conversation_id=conversation_id,
            session_id=interaction.session_id,
            command_type="interaction.respond",
            payload={"interaction_id": interaction_id, "response": response},
        )
        if command.state == "applied":
            latest = control_store.get_interaction(db, interaction_id)
            if latest is None:  # pragma: no cover - defensive invariant
                raise RuntimeError("Interaction 记录意外丢失")
            return PreparedInteraction(
                conversation_id=conversation_id,
                command_id=command_id,
                interaction_id=interaction_id,
                response=response,
                command=command,
                latest=latest,
                skip=True,
            )
        if command.state == "failed":
            raise control_store.InteractionConflict(
                command.error or "Interaction 已被回答"
            )
        if not control_store.claim_command(db, command_id):
            raise RuntimeError("控制命令正在生效，请稍后查询")
        return PreparedInteraction(
            conversation_id=conversation_id,
            command_id=command_id,
            interaction_id=interaction_id,
            response=response,
            command=command,
            latest=None,
            skip=False,
        )

    def _apply_respond_interaction(
        self,
        prepared: PreparedInteraction,
    ) -> tuple[control_store.ClientCommand, control_store.Interaction]:
        db = ConversationDB(prepared.conversation_id).init()
        latest, changed = control_store.respond_interaction(
            db,
            prepared.interaction_id,
            prepared.response,
        )
        if latest is None:
            control_store.finish_command(
                db,
                prepared.command_id,
                error="Interaction 不存在",
            )
            raise ValueError("Interaction 不存在")
        if not changed:
            error = "Interaction 已被回答或已过期"
            control_store.finish_command(db, prepared.command_id, error=error)
            raise control_store.InteractionConflict(error)
        command = control_store.finish_command(
            db,
            prepared.command_id,
            result={
                "interaction_id": prepared.interaction_id,
                "state": latest.state,
            },
        )
        self.session_runner._emit(
            prepared.conversation_id,
            latest.session_id,
            "interaction_responded",
            latest.to_dict(),
        )
        return command, latest

    async def respond_interaction_command(
        self,
        *,
        command_id: str,
        conversation_id: str,
        interaction_id: str,
        response: str,
    ) -> tuple[control_store.ClientCommand, control_store.Interaction]:
        prepared = await asyncio.to_thread(
            self._prepare_respond_interaction,
            command_id,
            conversation_id,
            interaction_id,
            response,
        )
        if prepared.skip:
            assert prepared.latest is not None
            return prepared.command, prepared.latest
        command, latest = await asyncio.to_thread(
            self._apply_respond_interaction, prepared
        )
        await events.aemit(
            prepared.conversation_id,
            "interaction_answered",
            interaction_id=prepared.interaction_id,
            session_id=latest.session_id,
        )
        return command, latest

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
        conversations = await asyncio.to_thread(self.list_conversations)
        for conversation in conversations:
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
            for record in await session_store.alist_pending_approval_records(db):
                record["conversation_id"] = conversation_id
                results.append(record)
        return results

    def list_pending_approvals_for_conversation(
        self,
        conversation_id: str,
    ) -> list[dict]:
        validate_conversation_id(conversation_id)
        db = ConversationDB(conversation_id)
        if not Path(db.path).is_file():
            return []
        records = session_store.list_pending_approval_records(db)
        for record in records:
            record["conversation_id"] = conversation_id
        return records

    async def alist_pending_approvals_for_conversation(
        self, conversation_id: str
    ) -> list[dict]:
        validate_conversation_id(conversation_id)
        db = ConversationDB(conversation_id)
        if not Path(db.path).is_file():
            return []
        records = await session_store.alist_pending_approval_records(db)
        for record in records:
            record["conversation_id"] = conversation_id
        return records

    def _approval_db(
        self,
        conversation_id: str,
    ) -> ConversationDB | None:
        validate_conversation_id(conversation_id)
        db = ConversationDB(conversation_id)
        if not Path(db.path).is_file():
            return None
        return db

    async def decide_approval(
        self,
        conversation_id: str,
        approval_id: int,
        decision: Literal["approved", "denied"],
        denial_reason: str = "",
    ) -> bool:
        db = await asyncio.to_thread(self._approval_db, conversation_id)
        if db is None:
            return False
        return await session_store.adecide_approval(
            db, approval_id, decision, denial_reason
        )

    async def decide_approval_command(
        self,
        *,
        command_id: str,
        conversation_id: str,
        approval_id: int,
        decision: Literal["approved", "denied"],
        denial_reason: str = "",
    ) -> tuple[control_store.ClientCommand, dict]:
        validate_conversation_id(conversation_id)
        db = await asyncio.to_thread(ConversationDB(conversation_id).init)
        async with db.aconnect() as con:
            cursor = await con.execute(
                """SELECT session_id, agent_name, details, state,
                denial_reason, tool_name, normalized_arguments, risk_summary,
                candidate_diff, requested_at, expires_at, decided_by,
                decided_at FROM approvals WHERE id=?""",
                (approval_id,),
            )
            row = await cursor.fetchone()
        if row is None:
            raise ValueError("Approval 不存在")
        (
            session_id,
            agent_name,
            details,
            approval_state,
            existing_reason,
            tool_name,
            normalized_arguments,
            risk_summary,
            candidate_diff,
            requested_at,
            expires_at,
            decided_by,
            decided_at,
        ) = row
        try:
            normalized_arguments = json.loads(normalized_arguments or "{}")
        except (TypeError, ValueError):
            normalized_arguments = {}

        def approval_payload(state: str, reason: str) -> dict:
            return {
                "approval_id": approval_id,
                "conversation_id": conversation_id,
                "session_id": session_id,
                "agent_name": agent_name,
                "details": details,
                "tool_name": tool_name or "",
                "normalized_arguments": normalized_arguments,
                "risk_summary": risk_summary or "",
                "candidate_diff": candidate_diff or "",
                "requested_at": requested_at,
                "expires_at": expires_at,
                "state": state,
                "denial_reason": reason or "",
                "decided_by": decided_by,
                "decided_at": decided_at,
            }
        command, _ = await asyncio.to_thread(
            control_store.receive_command,
            db,
            command_id=command_id,
            conversation_id=conversation_id,
            session_id=session_id,
            command_type="approval.decide",
            payload={"approval_id": approval_id, "decision": decision, "denial_reason": denial_reason},
        )
        if command.state == "applied":
            return command, approval_payload(
                approval_state,
                existing_reason,
            )
        if command.state == "failed":
            raise control_store.CommandConflict(
                command.error or "Approval 已被决定"
            )
        if not await asyncio.to_thread(control_store.claim_command, db, command_id):
            raise RuntimeError("控制命令正在生效，请稍后查询")

        changed = await session_store.adecide_approval(
            db,
            approval_id,
            decision,
            denial_reason,
            decided_by="remote_client",
        )
        if not changed:
            error = "Approval 已被决定或已过期"
            await asyncio.to_thread(control_store.finish_command, db, command_id, error=error)
            raise control_store.CommandConflict(error)
        command = await asyncio.to_thread(
            control_store.finish_command, db, command_id,
            result={"approval_id": approval_id, "state": decision},
        )
        payload = approval_payload(decision, denial_reason)
        payload["decided_by"] = "remote_client"
        payload["decided_at"] = datetime.now(timezone.utc).isoformat()
        return command, payload
