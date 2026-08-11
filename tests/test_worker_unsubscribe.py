"""workers 线程订阅清理：release_workers 后 listener 不残留 ThreadSub。"""

from __future__ import annotations

import tempfile
import time

import pytest

from cloudra.infra import events, ipc
from cloudra.persistence.database import ConversationDB
from cloudra.runtime import workers


@pytest.fixture
def isolated_ipc(monkeypatch):
    """把 IPC 目录指到临时目录，避免测试间互相污染。"""
    with tempfile.TemporaryDirectory() as tmp:
        monkeypatch.setenv("XDG_RUNTIME_DIR", tmp)
        events.shutdown_all_listeners()
        yield tmp
        events.shutdown_all_listeners()


def _thread_sub_count(conv_id: str) -> int:
    listener = ipc._listeners.get(conv_id)
    if listener is None:
        return 0
    with listener._lock:
        return len(
            {
                id(target)
                for targets in listener._subs.values()
                for target in targets
                if isinstance(target, ipc.ThreadSub)
            }
        )


def _wait_for(predicate, timeout: float = 5.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.05)
    return predicate()


def test_release_workers_unsubscribes_thread_subs(tmp_path, isolated_ipc):
    db = ConversationDB("worker-unsub", data_dir=tmp_path).init()
    conv_id = workers._conv_id_from_db_path(db.path)

    workers.acquire_workers(db.path, interactive_approval=False)
    try:
        # checking_task + check_compute 各订阅一次
        assert _wait_for(lambda: _thread_sub_count(conv_id) == 2)
    finally:
        workers.release_workers(db.path)

    assert _wait_for(lambda: _thread_sub_count(conv_id) == 0)

    # 重复 acquire/release 不累积订阅
    workers.acquire_workers(db.path, interactive_approval=False)
    try:
        assert _wait_for(lambda: _thread_sub_count(conv_id) == 2)
    finally:
        workers.release_workers(db.path)
    assert _wait_for(lambda: _thread_sub_count(conv_id) == 0)


def test_thread_sub_close_unsubscribes_and_is_idempotent(isolated_ipc):
    conv_id = "conv-thread-close"
    sub = events.subscribe_thread(conv_id, ("approval_pending",))
    listener = ipc._get_listener(conv_id)

    with listener._lock:
        assert any(sub in targets for targets in listener._subs.values())

    sub.close()
    with listener._lock:
        assert not any(sub in targets for targets in listener._subs.values())

    # 幂等；且 close 后事件不再投递进 payloads
    sub.close()
    events.emit(conv_id, "approval_pending", req_id=1, details="x")
    assert sub.wait(timeout=0.2) is None
