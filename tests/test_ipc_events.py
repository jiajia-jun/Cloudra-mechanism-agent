"""IPC 事件总线测试：验证同进程/跨进程投递、陈旧 socket 清理与 cancel 事件。"""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

import pytest

from cloudra import events


@pytest.fixture
def isolated_ipc(monkeypatch):
    """把 IPC 目录指到临时目录，避免测试间互相污染。"""
    with tempfile.TemporaryDirectory() as tmp:
        monkeypatch.setenv("XDG_RUNTIME_DIR", tmp)
        # 清除可能残留的全局 listener，保证每个测试从干净状态开始
        events.shutdown_all_listeners()
        yield tmp
        events.shutdown_all_listeners()


@pytest.mark.asyncio
async def test_async_subscribe_receive_in_process(isolated_ipc):
    """同进程内 async subscribe + emit 能立即收到。"""
    conv_id = "conv-async"
    sub = await events.subscribe_async(conv_id, ("task_finished",))

    events.emit(conv_id, "task_finished", task_id=42, state="done")

    msg = await asyncio.wait_for(sub.get(), timeout=2)
    assert msg["kind"] == "task_finished"
    assert msg["task_id"] == 42
    assert msg["state"] == "done"


def test_thread_subscribe_receive_in_process(isolated_ipc):
    """同进程内 thread subscribe + emit 能立即收到。"""
    conv_id = "conv-thread"
    sub = events.subscribe_thread(conv_id, ("approval_pending",))

    events.emit(conv_id, "approval_pending", req_id=7, details="test")

    msg = sub.wait(timeout=2)
    assert msg is not None
    assert msg["_kind"] == "approval_pending"
    assert msg["req_id"] == 7


@pytest.mark.asyncio
async def test_stale_socket_removed_on_ensure(isolated_ipc):
    """listener 启动时会清理本进程在该 conversation 下的陈旧 socket。"""
    conv_id = "conv-stale"
    # 预先伪造一个旧 socket
    from cloudra.ipc import _listener_addr_files

    kind, stale = _listener_addr_files(conv_id)
    if kind != "unix":
        pytest.skip("非 POSIX 平台使用 TCP 传输，无 unix socket 可清理")

    stale.parent.mkdir(parents=True, exist_ok=True)
    stale.write_text("")
    assert stale.exists()

    await events.ensure_listener(conv_id)
    # 启动后会删除并重新创建真正的 socket
    assert stale.exists() and stale.is_socket()


@pytest.mark.asyncio
async def test_cross_process_delivery(isolated_ipc):
    """主进程 emit 的事件能被独立子进程的 listener 收到。"""
    conv_id = "conv-cross"
    result_file = Path(isolated_ipc) / "cross_result.json"
    ready_file = Path(isolated_ipc) / "cross_ready"

    script = f"""
import asyncio
import json
import sys
import time
from pathlib import Path
sys.path.insert(0, {os.getcwd()!r})

from cloudra import events

conv_id = {conv_id!r}
result_path = Path({str(result_file)!r})
ready_path = Path({str(ready_file)!r})

async def main():
    await events.ensure_listener(conv_id)
    sub = await events.subscribe_async(conv_id, ("cancel_requested",))
    ready_path.write_text("ok")
    msg = await asyncio.wait_for(sub.get(), timeout=10)
    with open(result_path, "w", encoding="utf-8") as f:
        json.dump(msg, f)

asyncio.run(main())
"""
    proc = subprocess.Popen(
        [sys.executable, "-c", script],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    # 等待子进程 listener socket 就绪
    for _ in range(50):
        if ready_file.exists():
            break
        await asyncio.sleep(0.05)
    assert ready_file.exists(), "子进程 listener 未在预期时间内就绪"

    try:
        events.emit(conv_id, "cancel_requested", session_id="s-1", reason="timeout")
        stdout, stderr = await asyncio.wait_for(
            asyncio.to_thread(proc.communicate, timeout=15),
            timeout=18,
        )
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait()

    assert proc.returncode == 0, f"子进程异常退出: stderr={stderr}, stdout={stdout}"
    assert result_file.exists()
    import json

    msg = json.loads(result_file.read_text(encoding="utf-8"))
    assert msg["kind"] == "cancel_requested"
    assert msg["session_id"] == "s-1"


@pytest.mark.asyncio
async def test_cancel_event_reaches_react(isolated_ipc, tmp_path, monkeypatch):
    """cancel_requested 事件通过 IPC 投递到 reAct 实例并置位 cancel 事件。"""
    import asyncio

    from cloudra.agent import Follower
    from cloudra.database import ConversationDB
    from cloudra.react import reAct

    conv_id = "conv-cancel-ipc"
    db_path = str(tmp_path / "cancel_ipc.db")
    ConversationDB.from_path(db_path).init()
    monkeypatch.setattr("cloudra.react.get_database_path", lambda _cid: db_path)

    agent = Follower(
        id="a-test",
        name="tester",
        prompt="测试",
        query="测试问题",
        conversation_id=conv_id,
    )
    react = reAct(agent)

    await react._setup_event_subscriptions()
    await asyncio.sleep(0.1)

    events.emit(conv_id, "cancel_requested", session_id=react.session.id)
    await asyncio.wait_for(react._cancel_event.wait(), timeout=2)
    assert react._cancel_event.is_set()

    if react._cancel_task:
        react._cancel_task.cancel()
        try:
            await react._cancel_task
        except asyncio.CancelledError:
            pass


def test_broadcast_pump_is_bounded_and_coalesces_stream_chunks(monkeypatch):
    """Slow peers cannot create one thread/executor job per streamed chunk."""
    import cloudra.ipc as ipc

    gate = threading.Event()
    monkeypatch.setattr(ipc, "_broadcast_sync", lambda *_args: gate.wait(1))
    pump = ipc._BroadcastPump("bounded")
    try:
        for index in range(2_000):
            pump.enqueue(
                {
                    "kind": "session_event",
                    "payload": {
                        "session_id": f"s-{index % 4}",
                        "event_type": "llm_chunk",
                        "data": {"stream": "content", "delta": "x"},
                    },
                }
            )
        with pump._condition:
            assert len(pump._pending) <= pump.MAX_PENDING
    finally:
        gate.set()
        pump.close()
