"""Native cancellation uses the execution owner's synthetic process group only."""

from __future__ import annotations

import asyncio
import os
import signal
import sys
import time
from types import SimpleNamespace

import pytest

from cloudra.infra.compute_utils import calc_lock_path, guard_lock_path
from cloudra.infra.flocks import is_lock_held, try_acquire_lock
from cloudra.persistence.database import ComputeDB
from cloudra.services.compute_store import get_compute_job, insert_compute_job

pytestmark = pytest.mark.skipif(os.name != "posix", reason="owned sessions require POSIX")


def _set_state(db, job_id, state):
    with db.connect() as con:
        con.execute("UPDATE compute_jobs SET state=? WHERE id=?", (state, job_id))
        con.commit()


def _set_pid(db, job_id, pid):
    with db.connect() as con:
        con.execute("UPDATE compute_jobs SET calc_pid=? WHERE id=?", (pid, job_id))
        con.commit()


async def _until(predicate, timeout=4):
    deadline = time.monotonic() + timeout
    while not await asyncio.to_thread(predicate):
        if time.monotonic() >= deadline:
            raise AssertionError("synthetic calculation did not reach the expected state")
        await asyncio.sleep(0.02)


async def _stop_test_process(proc):
    """Only synthetic sessions created by this test are ever signalled here."""
    if proc.returncode is None:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    await proc.wait()


@pytest.fixture
def synthetic_job(tmp_path, monkeypatch):
    from cloudra.runtime import monitor

    monkeypatch.setenv("GAUSS_SCRDIR", str(tmp_path / "scratch"))
    monkeypatch.setattr(monitor, "_ADOPT_POLL_SECONDS", 0.02)
    monkeypatch.setattr(monitor, "_CANCEL_POLL_SECONDS", 0.02, raising=False)
    script = tmp_path / "synthetic.py"
    script.write_text(
        "import os, pathlib, signal, subprocess, sys, time\n"
        "root = pathlib.Path(sys.argv[1])\n"
        "role = sys.argv[2] if len(sys.argv) > 2 else 'calculator'\n"
        "def stop(*args):\n"
        "    (root / (role + '.terminated')).write_text('term')\n"
        "    raise SystemExit(0)\n"
        "signal.signal(signal.SIGTERM, stop)\n"
        "if role == 'calculator':\n"
        "    subprocess.Popen([sys.executable, __file__, str(root), 'link'], close_fds=False)\n"
        "(root / (role + '.ready')).write_text(str(os.getpid()))\n"
        "while True: time.sleep(0.05)\n",
        encoding="utf-8",
    )
    inp = tmp_path / "input.gjf"
    inp.write_text("synthetic test input\n", encoding="utf-8")
    db = ComputeDB().init()
    job_id = insert_compute_job(
        db, node_id="node-local", conversation_id="guard-test", session_id="s",
        path=str(inp), state="running", jobtype="gaussian", scheduler="local",
    )
    monkeypatch.setattr(monitor, "check_job_type", lambda *_: (True, ""))
    monkeypatch.setattr(
        monitor, "build_calculator_cmd",
        lambda *_args, **_kwargs: (True, [sys.executable, str(script), str(tmp_path)], ""),
    )
    created = []
    real_spawn = asyncio.create_subprocess_exec

    async def capture_spawn(*args, **kwargs):
        proc = await real_spawn(*args, **kwargs)
        created.append(proc)
        return proc

    monkeypatch.setattr(asyncio, "create_subprocess_exec", capture_spawn)

    def run():
        return asyncio.create_task(monitor.run_guard(
            taskid=job_id, path=str(inp), conv_id="guard-test", parse_timeout=1,
            db_path=db.path, job_type="gaussian",
        ))

    return SimpleNamespace(
        db=db, id=job_id, root=tmp_path, input=inp, created=created, run=run,
        script=script,
        scratch=lambda: list((tmp_path / "scratch").glob("cloudra_g16_*")),
    )


@pytest.mark.asyncio
async def test_explicit_cancel_stops_owned_calculator_and_link_only(synthetic_job):
    job = synthetic_job
    unrelated = await asyncio.create_subprocess_exec(
        sys.executable, "-c", "import time; time.sleep(30)", start_new_session=True,
    )
    guard = job.run()
    try:
        await _until(lambda: (job.root / "link.ready").exists())
        await asyncio.to_thread(_set_state, job.db, job.id, "cancel_requested")
        done, _ = await asyncio.wait({guard}, timeout=3)
        assert guard in done, "cancel request must be consumed by the native owner"
        await guard
        assert (job.root / "calculator.terminated").is_file()
        assert (job.root / "link.terminated").is_file()
        assert unrelated.returncode is None
        assert (await asyncio.to_thread(get_compute_job, job.db, job.id))["state"] == "cancelled"
        assert not await asyncio.to_thread(is_lock_held, calc_lock_path(str(job.root), job.id))
        assert not job.scratch()
        assert not (job.root / f"state_{job.id}.json").exists()
    finally:
        guard.cancel()
        await asyncio.gather(guard, return_exceptions=True)
        for proc in job.created:
            await _stop_test_process(proc)


@pytest.mark.asyncio
async def test_guard_task_cancellation_preserves_calculation_and_scratch(synthetic_job):
    job = synthetic_job
    guard = job.run()
    try:
        await _until(lambda: (job.root / "link.ready").exists())
        guard.cancel()
        with pytest.raises(asyncio.CancelledError):
            await guard
        assert job.created[0].returncode is None
        assert not (job.root / "calculator.terminated").exists()
        assert not (job.root / "link.terminated").exists()
        assert await asyncio.to_thread(is_lock_held, calc_lock_path(str(job.root), job.id))
        assert job.scratch(), "cancelling the observer must preserve live Gaussian scratch"
    finally:
        for proc in job.created:
            await _stop_test_process(proc)


@pytest.mark.asyncio
async def test_ledger_read_failure_never_signals_or_deletes_scratch(synthetic_job, monkeypatch):
    from cloudra.runtime import monitor

    job = synthetic_job
    original_read = monitor.aget_compute_job

    async def read(db, task_id):
        if (job.root / "link.ready").exists():
            raise OSError("synthetic database read failure")
        return await original_read(db, task_id)

    monkeypatch.setattr(monitor, "aget_compute_job", read)
    guard = job.run()
    try:
        done, _ = await asyncio.wait({guard}, timeout=3)
        assert guard in done, "ledger failure must stop the observer without harming calculation"
        with pytest.raises(OSError, match="synthetic database read failure"):
            await guard
        assert job.created[0].returncode is None
        assert not (job.root / "calculator.terminated").exists()
        assert not (job.root / "link.terminated").exists()
        assert job.scratch()
    finally:
        guard.cancel()
        await asyncio.gather(guard, return_exceptions=True)
        for proc in job.created:
            await _stop_test_process(proc)


@pytest.mark.asyncio
async def test_cancel_ignored_by_engine_link_keeps_request_pending_and_scratch(synthetic_job):
    job = synthetic_job
    job.script.write_text(job.script.read_text().replace(
        "signal.signal(signal.SIGTERM, stop)",
        "signal.signal(signal.SIGTERM, signal.SIG_IGN if role == 'link' else stop)",
    ))
    guard = job.run()
    try:
        await _until(lambda: (job.root / "link.ready").exists())
        await asyncio.to_thread(_set_state, job.db, job.id, "cancel_requested")
        await _until(lambda: (job.root / "calculator.terminated").exists())
        await asyncio.sleep(0.1)
        assert job.created[0].returncode is None, "owned group leader must outlive remaining engine links"
        assert not guard.done(), "parent exit cannot stand in for engine link exit"
        assert (await asyncio.to_thread(get_compute_job, job.db, job.id))["state"] == "cancel_requested"
        assert await asyncio.to_thread(is_lock_held, calc_lock_path(str(job.root), job.id))
        assert job.scratch()
        assert not (job.root / f"state_{job.id}.json").exists()
    finally:
        guard.cancel()
        await asyncio.gather(guard, return_exceptions=True)
        for proc in job.created:
            await _stop_test_process(proc)


@pytest.mark.asyncio
@pytest.mark.parametrize("close_fds", [True, False], ids=["closed_lock", "inherited_lock"])
async def test_cancel_waits_for_term_ignoring_link_to_stop(synthetic_job, close_fds):
    job = synthetic_job
    job.script.write_text(job.script.read_text().replace(
        "close_fds=False", f"close_fds={close_fds}",
    ).replace(
        "signal.signal(signal.SIGTERM, stop)",
        "signal.signal(signal.SIGTERM, signal.SIG_IGN if role == 'link' else stop)",
    ).replace(
        "while True: time.sleep(0.05)",
        "while True:\n"
        "    if role == 'link': (root / 'link.heartbeat').write_text(str(time.monotonic_ns()))\n"
        "    time.sleep(0.01)",
    ))
    heartbeat = job.root / "link.heartbeat"
    guard = job.run()
    try:
        await _until(heartbeat.exists)
        await asyncio.to_thread(_set_state, job.db, job.id, "cancel_requested")
        done, _ = await asyncio.wait({guard}, timeout=3)
        assert guard in done, "explicit cancellation must terminate remaining engine links"
        await guard
        assert (job.root / "calculator.terminated").is_file()
        assert (await asyncio.to_thread(get_compute_job, job.db, job.id))["state"] == "cancelled"
        previous_heartbeat = heartbeat.read_text()
        await asyncio.sleep(0.1)
        assert heartbeat.read_text() == previous_heartbeat, (
            "cancellation acknowledgement must wait until engine links stop executing"
        )
        assert not await asyncio.to_thread(is_lock_held, calc_lock_path(str(job.root), job.id))
        assert not job.scratch()
    finally:
        guard.cancel()
        await asyncio.gather(guard, return_exceptions=True)
        for proc in job.created:
            await _stop_test_process(proc)


@pytest.mark.asyncio
@pytest.mark.parametrize("close_fds", [True, False], ids=["closed_lock", "inherited_lock"])
async def test_cancel_stops_owned_session_child_in_another_process_group(synthetic_job, close_fds):
    job = synthetic_job
    job.script.write_text(job.script.read_text().replace(
        "close_fds=False", f"close_fds={close_fds}, preexec_fn=os.setpgrp",
    ).replace(
        "signal.signal(signal.SIGTERM, stop)",
        "signal.signal(signal.SIGTERM, signal.SIG_IGN if role == 'link' else stop)",
    ).replace(
        "while True: time.sleep(0.05)",
        "while not (root / 'finish').exists():\n"
        "    if role == 'link': (root / 'link.heartbeat').write_text(str(time.monotonic_ns()))\n"
        "    time.sleep(0.01)",
    ))
    unrelated = await asyncio.create_subprocess_exec(
        sys.executable, "-c", "import time; time.sleep(30)", start_new_session=True,
    )
    guard = job.run()
    try:
        heartbeat = job.root / "link.heartbeat"
        await _until(heartbeat.exists)
        child_pid = int((job.root / "link.ready").read_text())
        owner_sid = os.getsid(child_pid)
        owner = next(proc for proc in job.created if proc.pid == owner_sid)
        assert owner.pid != unrelated.pid
        assert os.getpgid(child_pid) != owner.pid
        await asyncio.to_thread(_set_state, job.db, job.id, "cancel_requested")
        done, _ = await asyncio.wait({guard}, timeout=4)
        assert guard in done, "cancellation must reach owned MPI-like child groups"
        await guard
        final_heartbeat = heartbeat.read_text()
        await asyncio.sleep(0.15)
        assert heartbeat.read_text() == final_heartbeat, "cancelled must not leave an owned child executing"
        assert unrelated.returncode is None
        assert get_compute_job(job.db, job.id)["state"] == "cancelled"
        assert not is_lock_held(calc_lock_path(str(job.root), job.id))
    finally:
        # A finish marker also cleans up the pre-fix child outside the old PGID.
        (job.root / "finish").touch()
        await asyncio.sleep(0.15)
        guard.cancel()
        await asyncio.gather(guard, return_exceptions=True)
        for proc in job.created:
            await _stop_test_process(proc)
        await _stop_test_process(unrelated)


@pytest.mark.asyncio
async def test_adopt_delivers_cancel_to_original_owner_without_using_stored_pid(synthetic_job):
    from cloudra.runtime import monitor

    job = synthetic_job
    guard = job.run()
    unrelated = await asyncio.create_subprocess_exec(
        sys.executable, "-c", "import time; time.sleep(30)", start_new_session=True,
    )
    adopt = None
    try:
        await _until(lambda: (job.root / "link.ready").exists())
        guard.cancel()
        await asyncio.gather(guard, return_exceptions=True)
        assert any(proc.pid != unrelated.pid and proc.returncode is None for proc in job.created)
        await asyncio.to_thread(_set_pid, job.db, job.id, unrelated.pid)
        await asyncio.to_thread(_set_state, job.db, job.id, "cancel_requested")
        adopt = asyncio.create_task(monitor.run_adopt(
            taskid=job.id, path=str(job.input), conv_id="guard-test", parse_timeout=1,
            db_path=job.db.path, job_type="gaussian",
        ))
        done, _ = await asyncio.wait({adopt}, timeout=4)
        assert adopt in done, "adoption must forward cancellation to the original live owner"
        await adopt
        assert (job.root / "calculator.terminated").exists()
        assert (job.root / "link.terminated").exists()
        assert unrelated.returncode is None
        assert get_compute_job(job.db, job.id)["state"] == "cancelled"
        assert not is_lock_held(calc_lock_path(str(job.root), job.id))
    finally:
        guard.cancel()
        if adopt is not None:
            adopt.cancel()
            await asyncio.gather(adopt, return_exceptions=True)
        await asyncio.gather(guard, return_exceptions=True)
        for proc in job.created:
            await _stop_test_process(proc)
        await _stop_test_process(unrelated)


@pytest.mark.asyncio
async def test_cancel_after_calculator_exit_stops_remaining_owned_link(synthetic_job):
    job = synthetic_job
    job.script.write_text(job.script.read_text().replace(
        "while True: time.sleep(0.05)",
        "if role == 'calculator':\n"
        "    while not (root / 'link.ready').exists(): time.sleep(0.01)\n"
        "    (root / 'calculator.exited').write_text('exit')\n"
        "    raise SystemExit(0)\n"
        "while True: time.sleep(0.05)",
    ))
    guard = job.run()
    try:
        await _until(lambda: (job.root / "calculator.exited").exists())
        await asyncio.to_thread(_set_state, job.db, job.id, "cancel_requested")
        done, _ = await asyncio.wait({guard}, timeout=3)
        assert guard in done, "calculator exit must not close the owned group's cancellation window"
        await guard
        assert (job.root / "link.terminated").is_file()
        assert (await asyncio.to_thread(get_compute_job, job.db, job.id))["state"] == "cancelled"
        assert not await asyncio.to_thread(is_lock_held, calc_lock_path(str(job.root), job.id))
        assert not job.scratch()
    finally:
        guard.cancel()
        await asyncio.gather(guard, return_exceptions=True)
        for proc in job.created:
            await _stop_test_process(proc)


@pytest.mark.asyncio
@pytest.mark.parametrize("cancel_guard", [False, True], ids=["ledger_request", "observer_cancel"])
async def test_cancellation_during_spawn_preserves_execution_ownership(
    synthetic_job, monkeypatch, cancel_guard,
):
    job = synthetic_job
    spawn_ready = asyncio.Event()
    release_spawn = asyncio.Event()
    original_spawn = asyncio.create_subprocess_exec

    async def delayed_spawn(*args, **kwargs):
        proc = await original_spawn(*args, **kwargs)
        spawn_ready.set()
        await release_spawn.wait()
        return proc

    monkeypatch.setattr(asyncio, "create_subprocess_exec", delayed_spawn)
    guard = job.run()
    try:
        await asyncio.wait_for(spawn_ready.wait(), 3)
        await _until(lambda: (job.root / "link.ready").exists())
        if cancel_guard:
            guard.cancel()
        else:
            await asyncio.to_thread(_set_state, job.db, job.id, "cancel_requested")
        release_spawn.set()
        if cancel_guard:
            with pytest.raises(asyncio.CancelledError):
                await guard
            assert job.created[0].returncode is None
            assert not (job.root / "calculator.terminated").exists()
            assert not (job.root / "link.terminated").exists()
            assert job.scratch()
        else:
            done, _ = await asyncio.wait({guard}, timeout=3)
            assert guard in done
            await guard
            assert (await asyncio.to_thread(get_compute_job, job.db, job.id))["state"] == "cancelled"
            assert (job.root / "calculator.terminated").is_file()
            assert (job.root / "link.terminated").is_file()
    finally:
        release_spawn.set()
        guard.cancel()
        await asyncio.gather(guard, return_exceptions=True)
        for proc in job.created:
            await _stop_test_process(proc)


@pytest.mark.asyncio
async def test_cancel_before_launch_does_not_spawn(synthetic_job):
    job = synthetic_job
    await asyncio.to_thread(_set_state, job.db, job.id, "cancel_requested")
    guard = job.run()
    try:
        done, _ = await asyncio.wait({guard}, timeout=1)
        assert guard in done, "pre-launch cancellation must settle without calculation"
        await guard
        assert job.created == []
        assert (await asyncio.to_thread(get_compute_job, job.db, job.id))["state"] == "cancelled"
    finally:
        guard.cancel()
        await asyncio.gather(guard, return_exceptions=True)
        for proc in job.created:
            await _stop_test_process(proc)


@pytest.mark.asyncio
async def test_cancel_during_launch_setup_cleans_only_unused_scratch(synthetic_job, monkeypatch):
    from cloudra.runtime import monitor

    job = synthetic_job

    def check(*_args):
        _set_state(job.db, job.id, "cancel_requested")
        return True, ""

    monkeypatch.setattr(monitor, "check_job_type", check)
    await job.run()
    assert job.created == []
    assert (await asyncio.to_thread(get_compute_job, job.db, job.id))["state"] == "cancelled"
    assert not job.scratch()


@pytest.mark.asyncio
async def test_cancel_after_natural_exit_skips_scientific_finalization(synthetic_job, monkeypatch):
    from cloudra.runtime import monitor

    job = synthetic_job
    monkeypatch.setattr(
        monitor, "build_calculator_cmd", lambda *_a, **_kw: (True, [sys.executable, "-c", "pass"], ""),
    )
    original_read = monitor.aget_compute_job
    requested = False

    async def read(db, task_id):
        nonlocal requested
        if not requested and job.created and job.created[0].returncode is not None:
            requested = True
            await asyncio.to_thread(_set_state, job.db, job.id, "cancel_requested")
        return await original_read(db, task_id)

    async def parse(*_args, **_kwargs):
        pytest.fail("accepted cancellation must skip scientific result parsing")

    monkeypatch.setattr(monitor, "aget_compute_job", read)
    monkeypatch.setattr(monitor, "_parse_log", parse)
    await job.run()
    assert (await asyncio.to_thread(get_compute_job, job.db, job.id))["state"] == "cancelled"
    assert not (job.root / f"state_{job.id}.json").exists()


@pytest.mark.asyncio
async def test_adopt_cancel_waits_for_lock_and_never_uses_stored_pid(synthetic_job):
    from cloudra.runtime import monitor

    job = synthetic_job
    await asyncio.to_thread(_set_state, job.db, job.id, "cancel_requested")
    unrelated = await asyncio.create_subprocess_exec(
        sys.executable, "-c", "import time; time.sleep(30)", start_new_session=True,
    )
    await asyncio.to_thread(_set_pid, job.db, job.id, unrelated.pid)
    fd = await asyncio.to_thread(try_acquire_lock, calc_lock_path(str(job.root), job.id))
    assert fd is not None
    adopt = asyncio.create_task(monitor.run_adopt(
        taskid=job.id, path=str(job.input), conv_id="guard-test", parse_timeout=1,
        db_path=job.db.path, job_type="gaussian",
    ))
    try:
        await asyncio.sleep(0.15)
        assert not adopt.done()
        assert (await asyncio.to_thread(get_compute_job, job.db, job.id))["state"] == "cancel_requested"
        assert unrelated.returncode is None
        os.close(fd)
        fd = None
        await asyncio.wait_for(adopt, 3)
        assert (await asyncio.to_thread(get_compute_job, job.db, job.id))["state"] == "cancelled"
        assert not (job.root / f"state_{job.id}.json").exists()
    finally:
        if fd is not None:
            os.close(fd)
        adopt.cancel()
        await asyncio.gather(adopt, return_exceptions=True)
        await _stop_test_process(unrelated)


@pytest.mark.asyncio
async def test_cancel_during_final_parse_does_not_publish_success(synthetic_job, monkeypatch):
    from cloudra.runtime import monitor

    job = synthetic_job
    monkeypatch.setattr(
        monitor, "build_calculator_cmd", lambda *_a, **_kw: (True, [sys.executable, "-c", "pass"], ""),
    )

    async def parse(*_a, **_kw):
        await asyncio.to_thread(_set_state, job.db, job.id, "cancel_requested")
        return {"energy": -76.0}, True

    monkeypatch.setattr(monitor, "_parse_log", parse)
    await job.run()
    assert (await asyncio.to_thread(get_compute_job, job.db, job.id))["state"] == "cancelled"
    assert not (job.root / f"state_{job.id}.json").exists()


def test_scheduler_keeps_native_cancel_request_leased_and_adopts_when_needed(
    synthetic_job, monkeypatch,
):
    from cloudra.scheduler import daemon

    job = synthetic_job
    _set_state(job.db, job.id, "cancel_requested")
    with job.db.connect() as con:
        con.execute("UPDATE compute_jobs SET start_timestamp=?, lease_expires_at=0 WHERE id=?", (time.time() - 120, job.id))
        con.commit()
    spawned = []
    monkeypatch.setattr(daemon, "spawn_detached", lambda cmd, _log: spawned.append(cmd))
    lock = guard_lock_path(str(job.root), job.id)
    fd = try_acquire_lock(lock)
    assert fd is not None
    try:
        assert daemon.SchedulerDaemon()._reconcile_central() == []
        assert spawned == []
        assert get_compute_job(job.db, job.id)["lease_expires_at"] > time.time() + 1800
    finally:
        os.close(fd)
    assert daemon.SchedulerDaemon()._reconcile_central() == []
    assert len(spawned) == 1 and "--adopt" in spawned[0]
    assert get_compute_job(job.db, job.id)["state"] == "cancel_requested"
