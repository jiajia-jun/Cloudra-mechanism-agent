"""执行面 flock 语义：calc 锁跨 exec 持有、guard 防重、adopt 接管、对账矩阵。"""

from __future__ import annotations

import asyncio
import os
import signal
import subprocess
import sys
import time

import pytest

from cloudra.infra.flocks import is_lock_held, try_acquire_lock
from cloudra.persistence.database import ComputeDB

pytestmark = pytest.mark.skipif(os.name != "posix", reason="fcntl flock is POSIX-only")

_CP2K_OK_OUT = """\
 GLOBAL| Run type  ENERGY_FORCE
 ENERGY| Total FORCE_EVAL ( QS ) energy [a.u.]              -76.384555551223
 PROGRAM ENDED IN 0.13 SECONDS
"""


def _wrapper_cmd(lock: str, *cmd: str) -> list[str]:
    return [
        sys.executable, "-m", "cloudra.runtime.calc_lock_wrapper", lock, "--", *cmd,
    ]


def _insert_running(db: ComputeDB, path: str, jobtype: str = "cp2k") -> int:
    with db.connect() as con:
        cur = con.execute(
            """INSERT INTO compute_jobs
            (conversation_id, session_id, path, state, jobtype, start_timestamp,
             end_timestamp, scheduler, scheduler_options)
            VALUES (?,?,?,?,?,?,?,?,?)""",
            ("conv-locks", "sess-1", path, "running", jobtype,
             time.time(), -1, "local", "{}"),
        )
        con.commit()
        return int(cur.lastrowid)


def _state(db: ComputeDB, job_id: int) -> str:
    with db.connect() as con:
        return con.execute("SELECT state FROM compute_jobs WHERE id=?", (job_id,)).fetchone()[0]


def test_calc_lock_held_across_exec_and_released_on_exit(tmp_path):
    """wrapper exec 的子进程存续期间锁被持有；退出后内核放锁。"""
    lock = str(tmp_path / "calc-1.lock")
    proc = subprocess.Popen(
        _wrapper_cmd(lock, sys.executable, "-c", "import time; time.sleep(2)")
    )
    try:
        time.sleep(0.5)
        assert is_lock_held(lock) is True
    finally:
        proc.wait(timeout=10)
    assert proc.returncode == 0
    assert is_lock_held(lock) is False


def test_calc_lock_wrapper_refuses_when_held(tmp_path):
    """锁被占用时 wrapper 以退出码 3 拒绝启动（OS 级防重）。"""
    lock = str(tmp_path / "calc-2.lock")
    fd = try_acquire_lock(lock)
    assert fd is not None
    try:
        rc = subprocess.run(
            _wrapper_cmd(lock, sys.executable, "-c", f"from pathlib import Path; Path({str(tmp_path / 'started')!r}).touch()"),
            capture_output=True, timeout=10,
        ).returncode
        assert rc == 3
        assert not (tmp_path / "started").exists()
    finally:
        os.close(fd)


def test_wrapper_term_handler_does_not_make_engine_ignore_term(tmp_path):
    ready = tmp_path / "ready"
    proc = subprocess.Popen(_wrapper_cmd(
        str(tmp_path / "term.lock"), sys.executable, "-c",
        f"from pathlib import Path; import time; Path({str(ready)!r}).touch(); time.sleep(30)",
    ), start_new_session=True)
    try:
        deadline = time.monotonic() + 3
        while not ready.exists():
            assert time.monotonic() < deadline
            time.sleep(0.02)
        os.kill(proc.pid, signal.SIGTERM)
        time.sleep(0.1)
        assert proc.poll() is None, "wrapper must retain ownership when only it receives TERM"
        os.killpg(proc.pid, signal.SIGTERM)
        proc.wait(timeout=3)
        assert proc.returncode != 0, "exec child must retain default TERM handling"
        assert not is_lock_held(str(tmp_path / "term.lock"))
    finally:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        proc.wait(timeout=3)


@pytest.mark.parametrize("during_spawn", [False, True], ids=["before_spawn", "spawn_window"])
def test_wrapper_records_early_term_and_covers_spawn_window(tmp_path, monkeypatch, during_spawn):
    from cloudra.runtime import calc_lock_wrapper as wrapper

    handlers = {}
    launches = []
    signals = []

    def install(sig, handler):
        previous = handlers.get(sig, signal.SIG_DFL)
        handlers[sig] = handler
        if not during_spawn and callable(handler):
            handler(signal.SIGTERM, None)
        return previous

    class Calculator:
        def wait(self):
            return 0

    def spawn(*args, **kwargs):
        launches.append("popen")
        handlers[signal.SIGTERM](signal.SIGTERM, None)
        return Calculator()

    def forward(group, sig):
        signals.append((group, sig))
        handlers[signal.SIGTERM](signal.SIGTERM, None)

    monkeypatch.setattr(signal, "signal", install)
    monkeypatch.setattr(wrapper.os, "getsid", lambda _pid: os.getpid())
    monkeypatch.setattr(wrapper.os, "getpgrp", os.getpid)
    monkeypatch.setattr(wrapper.os, "killpg", forward)
    monkeypatch.setattr(subprocess, "Popen", spawn)
    monkeypatch.setattr(wrapper.os, "execvp", lambda *_args: launches.append("exec"))
    rc = wrapper.main([str(tmp_path / "early.lock"), "--", "synthetic"])
    if during_spawn:
        assert launches == ["popen"]
        assert signals == [(os.getpid(), signal.SIGTERM)]
    else:
        assert launches == [], "accepted pre-spawn cancellation must not start an engine"
        assert rc != 0
        assert signals == []
    assert not is_lock_held(str(tmp_path / "early.lock"))


def test_wrapper_cannot_launch_or_signal_when_session_isolation_fails(tmp_path, monkeypatch):
    from cloudra.runtime import calc_lock_wrapper as wrapper

    def cannot_isolate():
        raise PermissionError("synthetic session isolation failure")

    monkeypatch.setattr(signal, "signal", lambda *_args: signal.SIG_DFL)
    monkeypatch.setattr(wrapper.os, "getsid", lambda _pid: -1)
    monkeypatch.setattr(wrapper.os, "getpgrp", lambda: -1)
    monkeypatch.setattr(wrapper.os, "setsid", cannot_isolate)
    monkeypatch.setattr(subprocess, "Popen", lambda *_a, **_kw: pytest.fail("engine started without session ownership"))
    monkeypatch.setattr(wrapper.os, "killpg", lambda *_a: pytest.fail("signal sent without session ownership"))
    lock = tmp_path / "unowned.lock"
    assert wrapper.main([str(lock), "--", "synthetic"]) == 1
    assert not lock.exists()


@pytest.mark.asyncio
async def test_guard_exits_when_lock_already_held(tmp_path):
    """第二个 guard 抢不到锁直接退出，不碰数据库（防重复执行）。"""
    from cloudra.infra.compute_utils import guard_lock_path
    from cloudra.runtime.monitor import run_guard

    inp = tmp_path / "x.inp"
    inp.write_text("&GLOBAL\n&END\n", encoding="utf-8")
    db = ComputeDB().init()
    job_id = _insert_running(db, str(inp))

    fd = try_acquire_lock(guard_lock_path(str(tmp_path), job_id))
    assert fd is not None
    try:
        await run_guard(
            taskid=job_id, path=str(inp), conv_id="lock-guard",
            parse_timeout=60, db_path=db.path, job_type="cp2k",
        )
    finally:
        os.close(fd)
    assert _state(db, job_id) == "running"  # 未被触碰


@pytest.mark.asyncio
async def test_adopt_finalizes_when_calc_finished(tmp_path):
    """calc 锁空闲 + 日志可解析 → adopt 直接收尾落 done。"""
    from cloudra.runtime.monitor import run_adopt

    inp = tmp_path / "x.inp"
    inp.write_text("&GLOBAL\n&END\n", encoding="utf-8")
    (tmp_path / "x.out").write_text(_CP2K_OK_OUT, encoding="utf-8")
    db = ComputeDB().init()
    job_id = _insert_running(db, str(inp))

    await run_adopt(
        taskid=job_id, path=str(inp), conv_id="lock-adopt",
        parse_timeout=60, db_path=db.path, job_type="cp2k",
    )
    assert _state(db, job_id) == "done"
    assert (tmp_path / f"state_{job_id}.json").is_file()


@pytest.mark.asyncio
async def test_adopt_waits_for_calc_lock_then_finalizes(tmp_path, monkeypatch):
    """calc 锁被持有（计算还在跑）时 adopt 阻塞等待，释放后收尾。"""
    from cloudra.infra.compute_utils import calc_lock_path
    from cloudra.runtime import monitor

    monkeypatch.setattr(monitor, "_ADOPT_POLL_SECONDS", 0.05)

    inp = tmp_path / "x.inp"
    inp.write_text("&GLOBAL\n&END\n", encoding="utf-8")
    db = ComputeDB().init()
    job_id = _insert_running(db, str(inp))

    lock = calc_lock_path(str(tmp_path), job_id)
    fd = try_acquire_lock(lock)
    assert fd is not None

    async def _release_soon():
        await asyncio.sleep(0.3)
        # 模拟 calculator 写完日志后退出（内核放锁）
        (tmp_path / "x.out").write_text(_CP2K_OK_OUT, encoding="utf-8")
        os.close(fd)

    releaser = asyncio.create_task(_release_soon())
    await monitor.run_adopt(
        taskid=job_id, path=str(inp), conv_id="lock-wait",
        parse_timeout=60, db_path=db.path, job_type="cp2k",
    )
    await releaser
    assert _state(db, job_id) == "done"


@pytest.mark.asyncio
async def test_adopt_marks_failed_when_log_missing(tmp_path):
    """calc 锁空闲但无日志 → 确定性判 failed（等价 agent 手动 mark_compute_job_failed）。"""
    from cloudra.runtime.monitor import run_adopt

    inp = tmp_path / "x.inp"
    inp.write_text("&GLOBAL\n&END\n", encoding="utf-8")
    db = ComputeDB().init()
    job_id = _insert_running(db, str(inp))

    await run_adopt(
        taskid=job_id, path=str(inp), conv_id="lock-nolog",
        parse_timeout=60, db_path=db.path, job_type="cp2k",
    )
    assert _state(db, job_id) == "failed"


def test_reconcile_spawns_adopt_only_when_guard_dead(tmp_path, monkeypatch):
    """对账矩阵：guard 锁被持有→续租不动；空闲→spawn adopt；slurm→跳过。"""
    from cloudra.infra.compute_utils import guard_lock_path
    from cloudra.scheduler import daemon as daemon_mod

    spawned: list[list[str]] = []
    monkeypatch.setattr(daemon_mod, "spawn_detached", lambda cmd, log: spawned.append(cmd))

    db = ComputeDB().init()
    alive = _insert_running(db, str(tmp_path / "a.inp"))
    dead = _insert_running(db, str(tmp_path / "b.inp"))
    slurm = _insert_running(db, str(tmp_path / "c.inp"))
    with db.connect() as con:
        con.execute("UPDATE compute_jobs SET scheduler='slurm' WHERE id=?", (slurm,))
        # 死 guard 的 start 必须落在启动宽限之外，否则对账会当成同步提交窗口。
        con.execute(
            "UPDATE compute_jobs SET start_timestamp=? WHERE id=?",
            (time.time() - 120, dead),
        )
        con.commit()

    guard_fd = try_acquire_lock(guard_lock_path(str(tmp_path), alive))
    assert guard_fd is not None
    try:
        daemon_mod.SchedulerDaemon()._reconcile_central()
    finally:
        os.close(guard_fd)

    assert len(spawned) == 1
    assert "--adopt" in spawned[0] and str(dead) in spawned[0]
    # guard 存活的作业租约被续到 ~1h，防重领
    with db.connect() as con:
        lease = con.execute(
            "SELECT lease_expires_at FROM compute_jobs WHERE id=?", (alive,)
        ).fetchone()[0]
    assert lease > time.time() + 1800


def test_reconcile_does_not_adopt_fresh_sync_submit(tmp_path, monkeypatch):
    """同步提交刚写入 running、guard 还没持锁：对账不得立刻 spawn adopt。"""
    from cloudra.scheduler import daemon as daemon_mod

    spawned: list[list[str]] = []
    monkeypatch.setattr(daemon_mod, "spawn_detached", lambda cmd, log: spawned.append(cmd))

    db = ComputeDB().init()
    _insert_running(db, str(tmp_path / "fresh.inp"))
    daemon_mod.SchedulerDaemon()._reconcile_central()
    assert spawned == []
