"""query_compute_job / query_compute_queue: anti-polling guidance on non-terminal results."""

import json

import pytest

from cloudra.persistence.database import ComputeDB
from cloudra.tools.Chemtool.query_compute_job import (
    QueryComputeJob,
    QueryComputeJob_input_schema,
)
from cloudra.tools.Chemtool.query_compute_queue import (
    QueryComputeQueue,
    QueryComputeQueue_input_schema,
)

_GUIDANCE_NEEDLE = "pushed to you automatically"
_QUEUE_GUIDANCE_NEEDLE = "pushed to the owning agent automatically"


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


@pytest.mark.asyncio
async def test_non_terminal_job_appends_anti_polling_guidance():
    db = ComputeDB().init()
    job_id = _insert_job(db, state="running")

    result = await QueryComputeJob().tool_call(
        QueryComputeJob_input_schema(job_id=job_id), session=None,
    )

    assert result.is_success is True, result.message
    assert _GUIDANCE_NEEDLE in result.message
    assert "one-shot reminder" in result.message


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
