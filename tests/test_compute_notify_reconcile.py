"""完成通知补投对账：终态未通知的作业被扫出，投递后 notified_at 落库幂等。"""

from __future__ import annotations

import time

from cloudra.persistence.database import ComputeDB
from cloudra.runtime_v2.compute_notify import ComputeNotifyBroker


def _insert_terminal(db: ComputeDB, *, state="done", ended=None) -> int:
    with db.connect() as con:
        cur = con.execute(
            """INSERT INTO compute_jobs
            (conversation_id, session_id, path, state, jobtype, start_timestamp,
             end_timestamp, scheduler, scheduler_options)
            VALUES (?,?,?,?,?,?,?,?,?)""",
            (
                "notify-conv", "sess-1", "/tmp/x.gjf", state, "gaussian",
                time.time() - 100, ended if ended is not None else time.time(),
                "local", "{}",
            ),
        )
        con.commit()
        return int(cur.lastrowid)


def test_pending_terminal_jobs_found_and_marked():
    db = ComputeDB().init()
    job = _insert_terminal(db)

    pending = ComputeNotifyBroker._pending_terminal_jobs()
    assert [row[1] for row in pending] == [job]

    ComputeNotifyBroker._mark_notified(job)
    assert ComputeNotifyBroker._pending_terminal_jobs() == []


def test_pending_terminal_jobs_skip_running_and_old():
    db = ComputeDB().init()
    running = _insert_terminal(db, state="running")
    old = _insert_terminal(db, ended=time.time() - 8 * 24 * 3600)  # 超出 7 天补投窗口
    recent = _insert_terminal(db, state="failed")

    pending = [row[1] for row in ComputeNotifyBroker._pending_terminal_jobs()]
    assert recent in pending
    assert running not in pending
    assert old not in pending


def test_pending_terminal_jobs_filter_by_conversation():
    """ensure_project 的项目级立即扫：按 conversation_id 过滤。"""
    db = ComputeDB().init()
    mine = _insert_terminal(db)  # conversation_id='notify-conv'
    with db.connect() as con:
        con.execute(
            """INSERT INTO compute_jobs
            (conversation_id, session_id, path, state, jobtype, start_timestamp,
             end_timestamp, scheduler, scheduler_options)
            VALUES ('other-conv', 'sess-1', '/tmp/y.gjf', 'done', 'gaussian',
                    ?, ?, 'local', '{}')""",
            (time.time() - 100, time.time()),
        )
        other = int(con.execute("SELECT last_insert_rowid()").fetchone()[0])
        con.commit()

    pending = ComputeNotifyBroker._pending_terminal_jobs("notify-conv")
    assert [row[1] for row in pending] == [mine]
    # 全局扫描两者皆见
    assert {row[1] for row in ComputeNotifyBroker._pending_terminal_jobs()} == {mine, other}
