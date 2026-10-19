"""query_compute_job / query_compute_queue: anti-polling guidance on non-terminal results."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from cloudra.persistence.database import ComputeDB
from cloudra.tools.Chemtool.query_compute_job import (
    QueryComputeJob,
    QueryComputeJob_input_schema,
    QueryComputeJob_output_schema,
)
from cloudra.tools.Chemtool.query_compute_queue import (
    QueryComputeQueue,
    QueryComputeQueue_input_schema,
)

_GUIDANCE_NEEDLE = "STOP POLLING"
_QUEUE_GUIDANCE_NEEDLE = "STOP POLLING"


def test_compute_job_output_rejects_invalid_job_id():
    row = {
        "job_id": "not-a-job-id", "state": "running", "node_id": "node-1",
        "scheduler": "local", "scheduler_state": "", "jobtype": "gaussian",
        "path": "", "log_path": "", "started_at": "", "ended_at": "",
        "last_error": "", "attempt_count": 0,
    }
    with pytest.raises(ValidationError):
        QueryComputeJob_output_schema(is_success=True, jobs=[row])


def _insert_job(db: ComputeDB, *, state: str = "running") -> int:
    with db.connect() as con:
        cur = con.execute(
            """INSERT INTO compute_jobs
            (conversation_id, session_id, path, state, jobtype,
             start_timestamp, end_timestamp, scheduler, scheduler_options)
            VALUES (?,?,?,?,?,?,?,?,?)""",
            (
                "default", "sess-1", "/tmp/h2.gjf", state, "gaussian",
                -1, -1, "local", json.dumps({"type": "local"}),
            ),
        )
        job_id = int(cur.lastrowid)
        con.commit()
    return job_id


def _freeze_native_irc(path: Path, engine: str, job_id: int) -> str:
    """Freeze native-shaped IRC parser fixtures; no QM calculation is run."""
    from cloudra.infra.compute_utils import complete_execution_evidence, prepare_execution_evidence

    prepare_execution_evidence(str(path), engine, job_id, ComputeDB())
    native = path.with_suffix('.log' if engine == 'gaussian' else '.out')
    if engine == 'gaussian':
        fixture = Path(__file__).parent / 'fixtures/gaussian/hcn_ts_irc_g16.log'
        native.write_bytes(fixture.read_bytes())
    else:
        from tests.test_orca_frames import _IRC_ENDPOINT_XYZ, _write_synthetic_irc_log

        text = _write_synthetic_irc_log(path.parent, path.stem).read_text()
        native.write_text('O   R   C   A\n' + text + '\n****ORCA TERMINATED NORMALLY****\n')
        for side in ('F', 'B'):
            (path.parent / f'{path.stem}_IRC_{side}.xyz').write_text(_IRC_ENDPOINT_XYZ)
    return complete_execution_evidence(str(path), engine, job_id)


@pytest.mark.asyncio
@pytest.mark.parametrize('engine', ['gaussian', 'orca'])
async def test_done_irc_query_returns_bound_endpoints_without_writing(tmp_path, engine):
    import asyncio
    import hashlib

    db = await ComputeDB().ainit()
    job = await asyncio.to_thread(_insert_job, db, state='done')
    path = tmp_path / ('irc.gjf' if engine == 'gaussian' else 'irc.inp')
    path.write_text('#p hf/3-21g IRC\n' if engine == 'gaussian' else '! HF STO-3G IRC\n')
    async with db.aconnect() as con:
        await con.execute('UPDATE compute_jobs SET path=?,jobtype=? WHERE id=?', (str(path), engine, job))
        await con.commit()
    log_path = await asyncio.to_thread(_freeze_native_irc, path, engine, job)

    def contents():
        return {str(p): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in tmp_path.rglob('*') if p.is_file()}

    before = await asyncio.to_thread(contents)
    result = await QueryComputeJob().tool_call(QueryComputeJob_input_schema(job_id=job), None)
    assert result.is_success, result.message
    row = result.jobs[0]
    assert row['log_path'] == log_path
    assert Path(row['irc_end_a_path']).is_file()
    assert Path(row['irc_end_b_path']).is_file()
    assert row['irc_end_a_path'] != row['irc_end_b_path']
    assert await asyncio.to_thread(contents) == before  # Querying never refreshes the endpoint receipt.


@pytest.mark.asyncio
@pytest.mark.parametrize('state,engine', [
    ('running', 'gaussian'), ('failed', 'gaussian'), ('cancelled', 'orca'),
    ('done', 'shell'), ('done', 'xtb'),
])
async def test_job_without_completed_qm_state_does_not_read_irc_endpoints(monkeypatch, state, engine):
    import asyncio

    from cloudra.tools.core import irc_endpoint_artifacts

    def unexpected_read(_):
        pytest.fail('Only a completed job can expose continuation artifacts')

    monkeypatch.setattr(irc_endpoint_artifacts, 'read_irc_endpoint_artifacts', unexpected_read)
    db = await ComputeDB().ainit()
    job = await asyncio.to_thread(_insert_job, db, state=state)
    async with db.aconnect() as con:
        await con.execute('UPDATE compute_jobs SET jobtype=? WHERE id=?', (engine, job))
        await con.commit()
    result = await QueryComputeJob().tool_call(QueryComputeJob_input_schema(job_id=job), None)
    assert result.is_success, result.message
    assert 'irc_end_a_path' not in result.jobs[0]
    assert 'irc_end_b_path' not in result.jobs[0]


@pytest.mark.asyncio
async def test_done_qm_query_does_not_create_unbound_endpoint_exports(tmp_path):
    import asyncio
    import hashlib

    db = await ComputeDB().ainit()
    job = await asyncio.to_thread(_insert_job, db, state='done')
    path = tmp_path / 'minimum.gjf'
    path.write_text('#p hf/3-21g Opt\n')
    fixture = Path(__file__).parent / 'fixtures/gaussian/water_opt_freq_g16.out'
    path.with_suffix('.log').write_bytes(fixture.read_bytes())
    async with db.aconnect() as con:
        await con.execute('UPDATE compute_jobs SET path=? WHERE id=?', (str(path), job))
        await con.commit()

    def contents():
        return {str(p): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in tmp_path.rglob('*') if p.is_file()}

    before = await asyncio.to_thread(contents)
    result = await QueryComputeJob().tool_call(QueryComputeJob_input_schema(job_id=job), None)
    assert result.is_success, result.message
    assert 'irc_end_a_path' not in result.jobs[0] and 'irc_end_b_path' not in result.jobs[0]
    assert await asyncio.to_thread(contents) == before


@pytest.mark.asyncio
async def test_non_terminal_job_appends_anti_polling_guidance():
    db = ComputeDB().init()
    job_id = _insert_job(db, state="running")

    result = await QueryComputeJob().tool_call(
        QueryComputeJob_input_schema(job_id=job_id), session=None,
    )

    assert result.is_success is True, result.message
    assert _GUIDANCE_NEEDLE in result.message
    assert "one-shot read-only check_command" in result.message


@pytest.mark.asyncio
async def test_terminal_job_has_no_guidance():
    db = ComputeDB().init()
    job_id = _insert_job(db, state="done")

    result = await QueryComputeJob().tool_call(
        QueryComputeJob_input_schema(job_id=job_id), session=None,
    )

    assert result.is_success is True, result.message
    assert _GUIDANCE_NEEDLE not in result.message


@pytest.mark.asyncio
async def test_queue_with_in_flight_jobs_appends_guidance():
    db = ComputeDB().init()
    _insert_job(db, state="running")

    result = await QueryComputeQueue().tool_call(
        QueryComputeQueue_input_schema(), session=None,
    )

    assert result.is_success is True, result.message
    assert _QUEUE_GUIDANCE_NEEDLE in result.message


@pytest.mark.asyncio
async def test_idle_queue_has_no_guidance():
    ComputeDB().init()

    result = await QueryComputeQueue().tool_call(
        QueryComputeQueue_input_schema(), session=None,
    )

    assert result.is_success is True, result.message
    assert _QUEUE_GUIDANCE_NEEDLE not in result.message
