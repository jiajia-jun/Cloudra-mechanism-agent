"""并发与状态一致性回归测试。

背景：并发子 Agent 场景下曾出现 SQLite 写锁错误；此外 executor 进程
非正常死亡曾导致 subagent_requests 永久停留在 'running'，使
_wait_for_background_tasks 无限等待。本文件覆盖：

1. 多线程并发写入（事件上报 + 心跳 + 原子抢占）不产生锁错误，
   且每个 ready 任务恰好被一个 worker 抢占。
2. recover_stale_sessions 会把心跳过期 Session 的孤儿 running 请求
   一并标记为 failed，而心跳正常的请求不受影响。
3. decide_approval / apply_approval_decision 的 pending 守卫保证
   审批决定幂等（双通道不会互相覆盖）。
4. reap_exited_executors 能回收非正常退出的 executor 进程。
"""

import threading
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest


def _setup_data_dir(tmp_path, monkeypatch):
    from cloudra.config import get_config, reload_config

    data_dir = tmp_path / "data"
    monkeypatch.setenv("CLOUDRA_DATA_DIR", str(data_dir))
    reload_config()
    get_config().data_dir = data_dir
    get_config()._ensure_dirs()
    return data_dir


def _utc_now():
    return datetime.now(timezone.utc).isoformat()


def test_concurrent_writers_no_lock_errors(tmp_path, monkeypatch):
    """8 个 worker 并发抢占/写事件/写心跳：无锁错误，任务不重复抢占。"""
    from cloudra.database import ConversationDB, retry_on_locked

    _setup_data_dir(tmp_path, monkeypatch)
    db = ConversationDB("stress").init()

    # 预置 20 个 ready 任务
    with db.connect() as con:
        for i in range(20):
            con.execute(
                "INSERT INTO subagent_requests (state, input_data, conversation_id) VALUES ('ready', '{}', 'stress')"
            )
        con.commit()

    errors = []
    n_workers = 8

    def worker(worker_id: int):
        local = ConversationDB.from_path(db.path)
        session_id = f"s-{worker_id}"

        def init_session():
            with local.connect() as con:
                con.execute(
                    "INSERT OR IGNORE INTO session (session_id, state, heartbeat_at) VALUES (?, 'running', ?)",
                    (session_id, _utc_now()),
                )
                con.commit()

        try:
            retry_on_locked(init_session)
            for _ in range(15):
                def claim():
                    with local.connect() as con:
                        cur = con.execute(
                            """UPDATE subagent_requests SET state='running'
                            WHERE id IN (SELECT id FROM subagent_requests WHERE state='ready' LIMIT 1)
                            RETURNING id"""
                        )
                        row = cur.fetchone()
                        con.commit()
                        return row

                retry_on_locked(claim)

                def write_event():
                    with local.connect() as con:
                        con.execute(
                            "UPDATE session SET heartbeat_at=? WHERE session_id=?",
                            (_utc_now(), session_id),
                        )
                        con.execute(
                            "INSERT INTO session_events (session_id, event_type, data, created_at) VALUES (?, 'phase', '{}', ?)",
                            (session_id, _utc_now()),
                        )
                        con.commit()

                retry_on_locked(write_event)
        except Exception as exc:  # noqa: BLE001 - 测试需要捕获一切
            errors.append(f"worker {worker_id}: {exc!r}")

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(n_workers)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)

    assert not errors, f"并发写入出现错误: {errors}"
    with db.connect() as con:
        claimed = con.execute(
            "SELECT COUNT(*) FROM subagent_requests WHERE state='running'"
        ).fetchone()[0]
        events = con.execute("SELECT COUNT(*) FROM session_events").fetchone()[0]
    assert claimed == 20, "每个 ready 任务应恰好被抢占一次"
    assert events == n_workers * 15


def test_recover_stale_sessions_reaps_orphan_requests(tmp_path, monkeypatch):
    """心跳过期的 running Session，其关联的 running 子任务被标记 failed。"""
    from cloudra.database import ConversationDB
    from cloudra.service import SessionRunner

    _setup_data_dir(tmp_path, monkeypatch)
    db = ConversationDB("conv-orphan").init()
    stale = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
    fresh = _utc_now()
    with db.connect() as con:
        # 死掉的 executor：session 心跳过期 + 请求仍 running
        con.execute(
            "INSERT INTO session (session_id, agent_id, agent_type, state, heartbeat_at, created_at) VALUES ('dead-sub', 'a-2', 'follower', 'running', ?, ?)",
            (stale, stale),
        )
        con.execute(
            "INSERT INTO subagent_requests (id, state, input_data, conversation_id, session_id) VALUES (1, 'running', '{}', 'conv-orphan', 'dead-sub')"
        )
        # 活着的 executor：心跳正常
        con.execute(
            "INSERT INTO session (session_id, agent_id, agent_type, state, heartbeat_at, created_at) VALUES ('live-sub', 'a-2', 'follower', 'running', ?, ?)",
            (fresh, fresh),
        )
        con.execute(
            "INSERT INTO subagent_requests (id, state, input_data, conversation_id, session_id) VALUES (2, 'running', '{}', 'conv-orphan', 'live-sub')"
        )
        # 还没被抢占的 ready 任务不受影响
        con.execute(
            "INSERT INTO subagent_requests (id, state, input_data, conversation_id, session_id) VALUES (3, 'ready', '{}', 'conv-orphan', 'queued-sub')"
        )
        con.commit()

    class Service:
        async def run_task(self, *args, **kwargs):
            return "unused"

    changed = SessionRunner(Service()).recover_stale_sessions(timeout_seconds=60)
    assert changed == 1  # 只有 dead-sub 这一个 Session 被标记

    with db.connect() as con:
        states = dict(
            con.execute("SELECT id, state FROM subagent_requests").fetchall()
        )
        session_states = dict(
            con.execute("SELECT session_id, state FROM session").fetchall()
        )
    assert states[1] == "failed", "孤儿 running 任务应被回收"
    assert states[2] == "running", "心跳正常的任务不应被误杀"
    assert states[3] == "ready", "ready 任务不应受影响"
    assert session_states["dead-sub"] == "interrupted"
    assert session_states["live-sub"] == "running"


@pytest.mark.asyncio
async def test_decide_approval_is_idempotent(tmp_path, monkeypatch):
    """同一个审批只能被决定一次；双通道第二次决定返回 False 且不覆盖。"""
    from cloudra.database import ConversationDB
    from cloudra.service import CloudraService

    _setup_data_dir(tmp_path, monkeypatch)
    db = ConversationDB("conv-approval").init()
    with db.connect() as con:
        con.execute(
            "INSERT INTO approvals (session_id, agent_name, details, state) VALUES ('s-1', 'a-2', 'rm -rf x', 'pending')"
        )
        req_id = con.execute("SELECT id FROM approvals").fetchone()[0]
        con.commit()

    service = CloudraService()
    assert await service.decide_approval("conv-approval", req_id, "approved") is True
    assert await service.decide_approval("conv-approval", req_id, "denied", "改主意了") is False

    with db.connect() as con:
        state, reason = con.execute(
            "SELECT state, denial_reason FROM approvals WHERE id=?", (req_id,)
        ).fetchone()
    assert state == "approved"
    assert reason == ""
    assert await service.list_pending_approvals() == []


def test_apply_approval_decision_guard(tmp_path, monkeypatch):
    """CLI 侧的审批写入同样具备 pending 守卫。"""
    from cloudra.database import ConversationDB
    from cloudra.main import apply_approval_decision

    _setup_data_dir(tmp_path, monkeypatch)
    db = ConversationDB("conv-cli-approval").init()
    with db.connect() as con:
        con.execute(
            "INSERT INTO approvals (session_id, agent_name, details, state) VALUES ('s-1', 'a-2', 'write file', 'pending')"
        )
        req_id = con.execute("SELECT id FROM approvals").fetchone()[0]
        con.commit()

    assert apply_approval_decision(db.path, req_id, "denied", "太危险") is True
    assert apply_approval_decision(db.path, req_id, "approved") is False
    with db.connect() as con:
        state, reason = con.execute(
            "SELECT state, denial_reason FROM approvals WHERE id=?", (req_id,)
        ).fetchone()
    assert (state, reason) == ("denied", "太危险")


def test_reap_exited_executors(tmp_path, monkeypatch):
    """已退出但未自报终态的 executor 进程被回收，活着的进程不动。"""
    from cloudra.database import ConversationDB
    from cloudra.main import reap_exited_executors

    _setup_data_dir(tmp_path, monkeypatch)
    db = ConversationDB("conv-reap").init()
    with db.connect() as con:
        con.execute(
            "INSERT INTO session (session_id, agent_id, agent_type, state, heartbeat_at) VALUES ('sub-dead', 'a-2', 'follower', 'running', ?)",
            (_utc_now(),),
        )
        con.execute(
            "INSERT INTO subagent_requests (id, state, input_data, conversation_id, session_id) VALUES (1, 'running', '{}', 'conv-reap', 'sub-dead')"
        )
        con.execute(
            "INSERT INTO subagent_requests (id, state, input_data, conversation_id, session_id) VALUES (2, 'running', '{}', 'conv-reap', 'sub-live')"
        )
        con.commit()

    active = {
        1: SimpleNamespace(poll=lambda: 1),   # 已退出，退出码 1
        2: SimpleNamespace(poll=lambda: None),  # 仍在运行
    }
    reaped = reap_exited_executors(db.path, active)

    assert reaped == [1]
    assert 1 not in active and 2 in active
    with db.connect() as con:
        req_states = dict(con.execute("SELECT id, state FROM subagent_requests").fetchall())
        sess_state, sess_error = con.execute(
            "SELECT state, error FROM session WHERE session_id='sub-dead'"
        ).fetchone()
    assert req_states[1] == "failed"
    assert req_states[2] == "running"
    assert sess_state == "failed"
    assert sess_error == "executor process exited unexpectedly"
