import json
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

from cloudra import session_store
from cloudra.database import ConversationDB
from cloudra.runtime import workers


class _NeverWait:
    def wait(self, timeout=None):
        raise AssertionError("startup recovery should stop before waiting")


def test_subagent_worker_drains_ready_rows_on_startup(tmp_path, monkeypatch):
    db = ConversationDB("worker-subagent", data_dir=tmp_path).init()
    with db.connect() as con:
        con.execute(
            """INSERT INTO subagent_requests
            (state, input_data, conversation_id) VALUES ('ready', ?, ?)""",
            (json.dumps({"agent_id": "a-1"}), "worker-subagent"),
        )
        con.commit()
    stop = threading.Event()
    started = []

    monkeypatch.setattr(workers, "subscribe_thread", lambda *_args, **_kwargs: _NeverWait())

    def fake_start(database_path, request_id, input_data, active_processes, worker_id):
        started.append((database_path, request_id, input_data))
        stop.set()

    monkeypatch.setattr(workers, "_start_subagent_executor", fake_start)
    workers.checking_task(db.path, stop)

    assert started[0][1:] == (1, {"agent_id": "a-1"})
    with db.connect() as con:
        assert con.execute(
            "SELECT state FROM subagent_requests WHERE id=1"
        ).fetchone()[0] == "running"


def test_compute_worker_drains_all_ready_rows_on_startup(tmp_path, monkeypatch):
    db = ConversationDB("worker-compute", data_dir=tmp_path).init()
    with db.connect() as con:
        con.executemany(
            """INSERT INTO compute_jobs
            (conversation_id, state, path) VALUES (?, 'ready', ?)""",
            [("worker-compute", "/tmp/a.gjf"), ("worker-compute", "/tmp/b.gjf")],
        )
        con.commit()
    stop = threading.Event()
    started = []
    monkeypatch.setattr(workers, "subscribe_thread", lambda *_args, **_kwargs: _NeverWait())

    def fake_start(database_path, task_id, active_processes, worker_id):
        started.append((database_path, task_id))
        if len(started) == 2:
            stop.set()

    monkeypatch.setattr(workers, "_start_compute_executor", fake_start)
    workers.check_compute(db.path, stop)

    assert [task_id for _path, task_id in started] == [1, 2]
    with db.connect() as con:
        states = con.execute(
            "SELECT state FROM compute_jobs ORDER BY id"
        ).fetchall()
    assert states == [("running",), ("running",)]


def test_task_leases_are_exclusive_renewable_and_reclaim_expired(tmp_path):
    db = ConversationDB("worker-leases", data_dir=tmp_path).init()
    with db.connect() as con:
        con.execute(
            """INSERT INTO subagent_requests
            (state, input_data, conversation_id) VALUES ('ready', '{}', ?)""",
            ("worker-leases",),
        )
        con.execute(
            """INSERT INTO compute_jobs
            (conversation_id, state, path) VALUES (?, 'ready', '/tmp/a.gjf')""",
            ("worker-leases",),
        )
        con.commit()

    assert session_store.claim_ready_request(db, worker_id="worker-a")[0] == 1
    assert session_store.claim_ready_request(db, worker_id="worker-b") is None
    assert session_store.renew_task_lease(
        db,
        table="subagent_requests",
        task_id=1,
        worker_id="worker-a",
    ) is True
    assert session_store.renew_task_lease(
        db,
        table="subagent_requests",
        task_id=1,
        worker_id="worker-b",
    ) is False

    assert session_store.claim_ready_compute_job(db, worker_id="worker-a") == 1
    assert session_store.claim_ready_compute_job(db, worker_id="worker-b") is None
    with db.connect() as con:
        con.execute(
            "UPDATE compute_jobs SET lease_expires_at=0 WHERE id=1"
        )
        con.commit()
    assert session_store.claim_ready_compute_job(db, worker_id="worker-b") == 1
    with db.connect() as con:
        assert con.execute(
            "SELECT lease_owner, attempt_count FROM compute_jobs WHERE id=1"
        ).fetchone() == ("worker-b", 2)


def test_exhausted_worker_lease_becomes_auditable_failure(tmp_path):
    db = ConversationDB("worker-exhausted", data_dir=tmp_path).init()
    with db.connect() as con:
        con.execute(
            """INSERT INTO compute_jobs
            (conversation_id, state, path, lease_owner, lease_expires_at,
             attempt_count) VALUES (?, 'running', '/tmp/a.gjf', 'dead', 0, 3)""",
            ("worker-exhausted",),
        )
        con.commit()

    assert session_store.reap_exhausted_leases(db) == ([], [1])
    with db.connect() as con:
        assert con.execute(
            "SELECT state, last_error FROM compute_jobs WHERE id=1"
        ).fetchone() == ("failed", "worker lease retry budget exhausted")


def test_concurrent_workers_claim_compute_job_exactly_once(tmp_path):
    db = ConversationDB("worker-race", data_dir=tmp_path).init()
    with db.connect() as con:
        con.execute(
            """INSERT INTO compute_jobs
            (conversation_id, state, path) VALUES (?, 'ready', '/tmp/a.gjf')""",
            ("worker-race",),
        )
        con.commit()

    def claim(index):
        return session_store.claim_ready_compute_job(
            db, worker_id=f"worker-{index}"
        )

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(claim, range(8)))
    assert results.count(1) == 1
    assert results.count(None) == 7
    with db.connect() as con:
        assert con.execute(
            "SELECT state, attempt_count FROM compute_jobs WHERE id=1"
        ).fetchone() == ("running", 1)


def test_recovery_interrupts_unclaimed_session_and_its_compute_job(tmp_path):
    db = ConversationDB("worker-orphan", data_dir=tmp_path).init()
    stale = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    with db.connect() as con:
        con.execute(
            """INSERT INTO session
            (session_id, state, query, created_at) VALUES (?, 'queued', ?, ?)""",
            ("session-orphan", "run", stale),
        )
        con.execute(
            """INSERT INTO compute_jobs
            (conversation_id, session_id, state, path)
            VALUES (?, ?, 'ready', ?)""",
            ("worker-orphan", "session-orphan", "/tmp/orphan.gjf"),
        )
        con.commit()

    assert session_store.recover_stale(db, cutoff=cutoff) == 1
    with db.connect() as con:
        session_state = con.execute(
            "SELECT state FROM session WHERE session_id='session-orphan'"
        ).fetchone()[0]
        compute_state = con.execute(
            "SELECT state FROM compute_jobs WHERE id=1"
        ).fetchone()[0]
    assert session_state == "interrupted"
    assert compute_state == "failed"
