"""Conversation-scoped IPC event bus over Unix domain sockets or TCP loopback.

设计目标：让跨进程状态变化通过 socket 事件直接投递，数据库只保留持久化事实。

- 每个需要接收事件的进程为每个 conversation 绑定一个地址：
  POSIX 下是 <pid>.sock（Unix domain socket），Windows 下是 <pid>.port（TCP 端口文件）。
- 发送方扫描该 conversation 的 ipc/ 目录，把 JSON 行事件广播给所有 listener。
- 本进程内的订阅者直接投递，不走 socket（零拷贝、零延迟）。
- 接收方不在线时，事件静默丢弃；持久化表保证其上线后能从 DB 恢复状态。
"""

from __future__ import annotations

import asyncio
import atexit
import copy
import errno
import getpass
import hashlib
import json
import os
import socket
import tempfile
import threading
import time
import weakref
from collections import deque
from pathlib import Path
from typing import Any, Iterable

from cloudra.platform_utils import is_posix, is_windows

__all__ = [
    "ensure_listener",
    "aemit",
    "emit",
    "subscribe_async",
    "subscribe_thread",
    "shutdown_listener",
]


def _runtime_dir() -> Path:
    """返回短路径的 IPC 根目录（避开 Linux 108 字符 sun_path 限制）。"""
    base = os.environ.get("XDG_RUNTIME_DIR") or tempfile.gettempdir()
    uid = getattr(os, "getuid", lambda: 0)()
    path = Path(base) / f"cloudra-{uid}-{getpass.getuser()}"
    path.mkdir(parents=True, exist_ok=True)
    if is_posix():
        path.chmod(0o700)
    return path


def _ipc_dir(conversation_id: str) -> Path:
    """按 conversation 隔离 socket 目录，用 hash 避免超长路径。"""
    conv_hash = hashlib.sha1(conversation_id.encode("utf-8")).hexdigest()[:16]
    path = _runtime_dir() / "ipc" / conv_hash
    path.mkdir(parents=True, exist_ok=True)
    if is_posix():
        path.chmod(0o700)
    return path


def _listener_addr_files(conversation_id: str) -> tuple[str, Path]:
    """当前进程在该 conversation 下使用的 listener 地址。

    Returns:
        (transport_kind, address_path): transport_kind 为 "unix" 或 "tcp"；
        address_path 在 POSIX 下指向 .sock 文件，在 Windows 下指向 .port 文件。
    """
    ipc_dir = _ipc_dir(conversation_id)
    if is_windows():
        return "tcp", ipc_dir / f"{os.getpid()}.port"
    return "unix", ipc_dir / f"{os.getpid()}.sock"


class ThreadSub:
    """供同步线程使用的订阅句柄：任意 kind 命中即 set event。"""

    def __init__(self, kinds: tuple[str, ...]):
        self.kinds = set(kinds)
        self._event = threading.Event()
        self._payloads: list[dict] = []
        self._lock = threading.Lock()

    def wait(self, timeout: float | None = None) -> dict | None:
        """阻塞等待，返回一个 pending payload；超时返回 None。"""
        signaled = self._event.wait(timeout)
        if not signaled:
            return None
        with self._lock:
            if self._payloads:
                payload = self._payloads.pop(0)
                if self._payloads:
                    self._event.set()
                else:
                    self._event.clear()
                return payload
            self._event.clear()
            return None

    def _push(self, payload: dict) -> None:
        with self._lock:
            self._payloads.append(payload)
            self._event.set()


class _EventListener:
    """绑定一个 conversation 的本地 listener：接收外部事件并分发给本进程订阅者。"""

    def __init__(self, conversation_id: str):
        self.conversation_id = conversation_id
        self.transport_kind, self.address_path = _listener_addr_files(conversation_id)
        self._server: asyncio.Server | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._subs: dict[str, list[asyncio.Queue | ThreadSub]] = {}
        self._lock = threading.Lock()
        self._closed = False

    async def start(self) -> None:
        if self._server is not None:
            return
        self._loop = asyncio.get_running_loop()
        self.address_path.parent.mkdir(parents=True, exist_ok=True)
        # 清理本进程在该 conversation 下可能残留的陈旧地址文件
        try:
            if self.address_path.exists():
                self.address_path.unlink()
        except OSError:
            pass

        if is_windows():
            self._server = await asyncio.start_server(
                self._on_client,
                "127.0.0.1",
                0,
            )
            port: int | None = None
            for sock in self._server.sockets:
                if sock.family == socket.AF_INET:
                    port = sock.getsockname()[1]
                    break
            if port is None:
                self._server.close()
                await self._server.wait_closed()
                self._server = None
                raise RuntimeError("无法获取 listener TCP 端口")
            self.address_path.write_text(str(port), encoding="utf-8")
        else:
            self._server = await asyncio.start_unix_server(
                self._on_client,
                path=str(self.address_path),
            )

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        server = self._server
        self._server = None
        if server is not None and self._loop is not None:
            server.close()
            if self._loop.is_running():
                asyncio.run_coroutine_threadsafe(server.wait_closed(), self._loop)
        try:
            if self.address_path.exists():
                self.address_path.unlink()
        except OSError:
            pass

    async def _on_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        while True:
            try:
                line = await reader.readline()
            except Exception:
                break
            if not line:
                break
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue
            kind = msg.get("kind")
            payload = msg.get("payload", {})
            if isinstance(kind, str):
                self._deliver(kind, payload, from_network=True)
        try:
            writer.close()
            await writer.wait_closed()
        except Exception:
            pass

    def _subscribe(self, kinds: Iterable[str], target: asyncio.Queue | ThreadSub) -> None:
        with self._lock:
            for kind in kinds:
                self._subs.setdefault(kind, []).append(target)

    def _unsubscribe(self, target: asyncio.Queue | ThreadSub) -> None:
        with self._lock:
            for targets in self._subs.values():
                if target in targets:
                    targets.remove(target)

    def _deliver(self, kind: str, payload: dict, from_network: bool = False) -> None:
        """把事件分发给本进程订阅者。允许从任意线程调用。"""
        # 外部投递默认 tag 来源，便于订阅方过滤
        if from_network:
            payload = {**payload, "_ipc_remote": True}

        with self._lock:
            targets = list(self._subs.get(kind, []))

        for target in targets:
            try:
                if isinstance(target, ThreadSub):
                    if kind in target.kinds:
                        # 同步订阅者不知道事件名，把事件名注入 payload
                        target._push({"_kind": kind, **payload})
                else:
                    if self._loop is None:
                        continue
                    # asyncio.Queue 不是线程安全：必须从 loop 线程 put
                    self._loop.call_soon_threadsafe(target.put_nowait, {"kind": kind, **payload})
            except Exception:
                # 投递失败不阻塞其他订阅者
                pass


# process-scoped listeners per conversation
_listeners: dict[str, _EventListener] = {}
_listeners_lock = threading.Lock()


def _stream_key(message: dict) -> tuple[str, str] | None:
    """Return the coalescing key for lossy LLM stream telemetry."""
    if message.get("kind") != "session_event":
        return None
    payload = message.get("payload") or {}
    if payload.get("event_type") != "llm_chunk":
        return None
    data = payload.get("data") or {}
    return str(payload.get("session_id", "")), str(data.get("stream", "content"))


class _BroadcastPump:
    """One bounded network broadcaster shared by all conversations.

    Local subscribers are still notified synchronously. Cross-process traffic is
    serialized here so token streaming cannot create an unbounded number of
    executor jobs. Adjacent chunks for one session/stream are merged.
    """

    MAX_PENDING = 256

    def __init__(self, conversation_id: str | None = None):
        self.conversation_id = conversation_id
        self._pending: deque[tuple[str, dict]] = deque()
        self._condition = threading.Condition()
        self._closed = False
        self._thread = threading.Thread(
            target=self._run,
            name="cloudra-ipc-broadcast",
            daemon=True,
        )
        self._thread.start()

    def enqueue(self, message: dict, *, conversation_id: str | None = None) -> None:
        # Coalescing mutates queued deltas; detach them from in-process Queue
        # payloads that have already been delivered to UI consumers.
        message = copy.deepcopy(message)
        target = conversation_id or self.conversation_id
        if not target:
            raise ValueError("conversation_id is required")
        stream_key = (target, _stream_key(message)) if _stream_key(message) else None
        with self._condition:
            if self._closed:
                return
            if stream_key and self._pending:
                previous_target, previous = self._pending[-1]
                previous_key = _stream_key(previous)
                if previous_key and (previous_target, previous_key) == stream_key:
                    previous_data = previous["payload"]["data"]
                    new_data = message["payload"]["data"]
                    previous_data["delta"] = (
                        str(previous_data.get("delta", ""))
                        + str(new_data.get("delta", ""))
                    )
                    return
            if len(self._pending) >= self.MAX_PENDING:
                # Prefer discarding an old recoverable stream chunk. Durable
                # state/approval events remain recoverable from SQLite too, but
                # should only be displaced when the queue contains no chunks.
                drop_index = next(
                    (
                        i
                        for i, (_target, item) in enumerate(self._pending)
                        if _stream_key(item)
                    ),
                    None,
                )
                if stream_key and drop_index is None:
                    return
                if drop_index is None:
                    self._pending.popleft()
                else:
                    del self._pending[drop_index]
            self._pending.append((target, message))
            self._condition.notify()

    def _run(self) -> None:
        while True:
            with self._condition:
                self._condition.wait_for(lambda: self._pending or self._closed)
                if not self._pending and self._closed:
                    return
                target, message = self._pending.popleft()
            _broadcast_sync(target, message)

    def close(self) -> None:
        with self._condition:
            self._closed = True
            self._condition.notify_all()
        self._thread.join(timeout=0.5)


_broadcast_pump: _BroadcastPump | None = None
_broadcast_pumps_lock = threading.Lock()


def _enqueue_broadcast(conversation_id: str, message: dict) -> None:
    global _broadcast_pump
    with _broadcast_pumps_lock:
        if _broadcast_pump is None:
            _broadcast_pump = _BroadcastPump()
        pump = _broadcast_pump
    pump.enqueue(message, conversation_id=conversation_id)


def _get_listener(conversation_id: str) -> _EventListener:
    with _listeners_lock:
        listener = _listeners.get(conversation_id)
        if listener is None:
            listener = _EventListener(conversation_id)
            _listeners[conversation_id] = listener
        return listener


async def ensure_listener(conversation_id: str) -> _EventListener:
    """确保当前进程在该 conversation 上有一个 listener。幂等。

    如果运行 loop 发生变化（常见于测试隔离），关闭旧 listener 并重建，
    避免 asyncio.Queue 被绑定到已废弃的 loop 上导致事件无法投递。
    """
    current_loop = asyncio.get_running_loop()
    with _listeners_lock:
        listener = _listeners.get(conversation_id)
        if listener is not None and listener._loop is not current_loop:
            listener.close()
            listener = None
            _listeners.pop(conversation_id, None)
    listener = _get_listener(conversation_id)
    await listener.start()
    return listener


def shutdown_listener(conversation_id: str) -> None:
    """关闭并清理当前进程在该 conversation 的 listener 地址文件。"""
    with _listeners_lock:
        listener = _listeners.pop(conversation_id, None)
    if listener is not None:
        listener.close()


def shutdown_all_listeners() -> None:
    global _broadcast_pump
    with _listeners_lock:
        listeners = list(_listeners.values())
        _listeners.clear()
    for listener in listeners:
        listener.close()
    with _broadcast_pumps_lock:
        pump = _broadcast_pump
        _broadcast_pump = None
    if pump is not None:
        pump.close()


atexit.register(shutdown_all_listeners)


def _broadcast_sync(conversation_id: str, message: dict) -> None:
    """同步广播到同一 conversation 的其他进程（socket 发送）。"""
    sock_dir = _ipc_dir(conversation_id)
    if not sock_dir.exists():
        return
    data = json.dumps(message, ensure_ascii=False).encode("utf-8") + b"\n"
    own_kind, own_path = _listener_addr_files(conversation_id)

    if is_windows():
        for entry in sock_dir.iterdir():
            if entry == own_path or entry.suffix != ".port":
                continue
            try:
                port = int(entry.read_text(encoding="utf-8").strip())
            except (ValueError, OSError):
                try:
                    entry.unlink()
                except OSError:
                    pass
                continue
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.settimeout(0.15)
                    s.connect(("127.0.0.1", port))
                    s.sendall(data)
            except (FileNotFoundError, ConnectionRefusedError):
                try:
                    entry.unlink()
                except OSError:
                    pass
            except OSError as exc:
                if exc.errno in (errno.ECONNREFUSED, errno.ENOENT):
                    try:
                        entry.unlink()
                    except OSError:
                        pass
            except Exception:
                pass
        return

    # POSIX: Unix domain sockets
    for entry in sock_dir.iterdir():
        if not entry.is_socket() or entry == own_path:
            continue
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
                s.settimeout(0.15)
                s.connect(str(entry))
                s.sendall(data)
        except (FileNotFoundError, ConnectionRefusedError):
            try:
                entry.unlink()
            except OSError:
                pass
        except OSError as exc:
            if exc.errno in (errno.ECONNREFUSED, errno.ENOENT):
                try:
                    entry.unlink()
                except OSError:
                    pass
        except Exception:
            pass


def emit(conversation_id: str, kind: str, **payload: Any) -> None:
    """同步发送事件：本进程订阅者立即收到，跨进程投递在后台线程完成。"""
    listener = _get_listener(conversation_id)
    listener._deliver(kind, payload)
    message = {"kind": kind, "payload": payload}
    _enqueue_broadcast(conversation_id, message)


async def aemit(conversation_id: str, kind: str, **payload: Any) -> None:
    """异步发送事件；入有界广播队列后立即返回，不占用默认线程池。"""
    listener = _get_listener(conversation_id)
    listener._deliver(kind, payload)
    _enqueue_broadcast(conversation_id, {"kind": kind, "payload": payload})


async def subscribe_async(
    conversation_id: str,
    kinds: str | Iterable[str],
) -> asyncio.Queue:
    """在该 conversation 上订阅一个或多个事件 kind，返回 asyncio.Queue。"""
    if isinstance(kinds, str):
        kinds = (kinds,)
    listener = await ensure_listener(conversation_id)
    queue: asyncio.Queue = asyncio.Queue()
    listener._subscribe(kinds, queue)
    # 用弱引用在 queue 被回收时自动取消订阅；注意 finalizer 不能强引用 queue 自身。
    queue_ref = weakref.ref(queue)
    def _cleanup(ref: weakref.ref):
        q = ref()
        if q is not None:
            listener._unsubscribe(q)
    weakref.finalize(queue, _cleanup, queue_ref)
    return queue


def subscribe_thread(
    conversation_id: str,
    kinds: str | Iterable[str],
) -> ThreadSub:
    """在该 conversation 上订阅一个或多个事件 kind，返回 ThreadSub（供同步线程使用）。"""
    if isinstance(kinds, str):
        kinds = (kinds,)
    # 同步订阅也可能需要启动 listener；但 listener 必须跑在 asyncio loop 上。
    # 调用方通常已经持有 loop（如 acquire_workers 在 main 线程时），这里不自动启动 loop。
    listener = _get_listener(conversation_id)
    sub = ThreadSub(tuple(kinds))
    listener._subscribe(kinds, sub)
    return sub


# 工具：等待多个事件之一（测试/同步代码辅助）
def wait_any(*subs: ThreadSub, timeout: float | None = None) -> tuple[ThreadSub | None, dict | None]:
    """等待任意 ThreadSub 被触发，返回 (sub, payload)；超时返回 (None, None)。"""
    deadline = None if timeout is None else time.monotonic() + timeout
    while True:
        for sub in subs:
            payload = sub.wait(0.05)
            if payload is not None:
                return sub, payload
        if deadline is not None and time.monotonic() >= deadline:
            return None, None
