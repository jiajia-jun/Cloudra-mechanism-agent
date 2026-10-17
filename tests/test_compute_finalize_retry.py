"""A guard retries terminal bookkeeping without rerunning its calculation."""
from __future__ import annotations

import asyncio
import contextlib
import sqlite3

import pytest

from cloudra.persistence.database import ComputeDB, aretry_on_locked
from cloudra.services import compute_store


@pytest.fixture
def locked_job(tmp_path, monkeypatch):
    db = ComputeDB(data_dir=tmp_path / 'data').init()
    workdir = tmp_path / 'job'
    workdir.mkdir()
    source = workdir / 'input.gjf'
    source.write_text('%mem=1GB\n')
    job_id = compute_store.insert_compute_job(
        db, node_id='node-local', conversation_id='fixture', session_id='fixture',
        path=str(source), state='running', jobtype='gaussian', scheduler='local',
    )
    writer = sqlite3.connect(db.path, check_same_thread=False)
    writer.execute('BEGIN IMMEDIATE')
    original_connect = db.aconnect
    failed = asyncio.Event()
    attempts = []

    @contextlib.asynccontextmanager
    async def short_connection():
        attempts.append(None)
        try:
            async with original_connect(timeout=.01) as connection:
                yield connection
        except sqlite3.OperationalError:
            failed.set()
            raise

    async def fast_retry(operation):
        return await aretry_on_locked(operation, retries=2, base_delay=.005)

    monkeypatch.setattr(db, 'aconnect', short_connection)
    monkeypatch.setattr(compute_store, 'aretry_on_locked', fast_retry)
    yield db, job_id, workdir, source, writer, failed, attempts
    writer.close()


def guard_parser(monkeypatch):
    from cloudra.runtime import monitor

    parses, reviews = [], []

    async def parse(*_args, **_kwargs):
        parses.append(None)
        return {'is_success': True}, True

    async def review(job_id, state):
        reviews.append((job_id, state))

    monkeypatch.setattr(monitor, '_parse_log', parse)
    monkeypatch.setattr('cloudra.dag.controller.enqueue_compute_review', review)
    return monitor, parses, reviews


@pytest.mark.asyncio
@pytest.mark.parametrize('cancel_during_retry', [False, True])
async def test_guard_commits_after_transient_lock_without_reparsing(locked_job, monkeypatch, cancel_during_retry):
    db, job_id, workdir, _source, writer, failed, attempts = locked_job
    monitor, parses, reviews = guard_parser(monkeypatch)
    pending = asyncio.create_task(monitor._finalize(
        db, job_id, workdir / 'unused.log', str(workdir), 1, 'gaussian', 0,
    ))
    await asyncio.wait_for(failed.wait(), timeout=1)
    if cancel_during_retry:
        await asyncio.to_thread(writer.execute,
                                "UPDATE compute_jobs SET state='cancel_requested' WHERE id=?", (job_id,))
        await asyncio.to_thread(writer.commit)
    else:
        await asyncio.to_thread(writer.rollback)
    await pending

    job = await asyncio.to_thread(compute_store.get_compute_job, db, job_id)
    assert job['state'] == ('cancel_requested' if cancel_during_retry else 'done')
    assert len(attempts) >= 2
    assert parses == [None]
    assert reviews == ([] if cancel_during_retry else [(job_id, 'done')])
    assert (workdir / f'state_{job_id}.json').exists() is not cancel_during_retry


@pytest.mark.asyncio
async def test_finalize_cancellation_propagates_without_terminal_write(locked_job):
    db, job_id, _workdir, _source, writer, failed, attempts = locked_job
    pending = asyncio.create_task(compute_store.afinalize_compute_job(db, job_id, 'done'))
    await asyncio.wait_for(failed.wait(), timeout=1)
    pending.cancel()
    with pytest.raises(asyncio.CancelledError):
        await pending
    count_at_cancel = len(attempts)
    await asyncio.to_thread(writer.rollback)
    await asyncio.sleep(.03)
    assert len(attempts) == count_at_cancel
    job = await asyncio.to_thread(compute_store.get_compute_job, db, job_id)
    assert job['state'] == 'running'


@pytest.mark.asyncio
async def test_retry_exhaustion_preserves_error_and_existing_adoption(locked_job, monkeypatch, capsys):
    db, job_id, workdir, source, writer, _failed, attempts = locked_job
    monitor, parses, reviews = guard_parser(monkeypatch)
    with pytest.raises(sqlite3.OperationalError, match='database is locked'):
        await compute_store.afinalize_compute_job(db, job_id, 'done')
    assert len(attempts) == 3

    await monitor._finalize(db, job_id, workdir / 'unused.log', str(workdir), 1, 'gaussian', 0)
    assert '[guard] 更新数据库失败：database is locked' in capsys.readouterr().out
    assert len(attempts) == 6
    assert parses == [None] and reviews == []
    assert not (workdir / f'state_{job_id}.json').exists()
    job = await asyncio.to_thread(compute_store.get_compute_job, db, job_id)
    assert job['state'] == 'running'

    await asyncio.to_thread(writer.rollback)
    await monitor.run_adopt(job_id, str(source), 'fixture', 1, db.path, 'gaussian')
    job = await asyncio.to_thread(compute_store.get_compute_job, db, job_id)
    assert job['state'] == 'done'
    assert reviews == [(job_id, 'done')]
