"""mark_compute_job_failed: reconcile orphaned compute jobs."""

import json

import pytest

from cloudra.persistence.database import ComputeDB
from cloudra.tools.Chemtool.mark_compute_job_failed import (
    MarkComputeJobFailed,
    MarkComputeJobFailed_input_schema,
)


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
async def test_running_job_marked_failed_with_reason():
    # 工具 subagent 为 None 时落到 "default" 会话归属
    db = ComputeDB().init()
    job_id = _insert_job(db, state="running")

    result = await MarkComputeJobFailed().tool_call(
        MarkComputeJobFailed_input_schema(job_id=job_id, reason="guard process dead"),
        session=None,
    )

    assert result.is_success is True, result.message
    assert result.previous_state == "running"
    with db.connect() as con:
        row = con.execute(
            "SELECT state, last_error FROM compute_jobs WHERE id=?", (job_id,)
        ).fetchone()
    assert row[0] == "failed"
    assert row[1] == "guard process dead"


@pytest.mark.asyncio
async def test_terminal_job_marking_refused():
    db = ComputeDB().init()
    job_id = _insert_job(db, state="done")

    result = await MarkComputeJobFailed().tool_call(
        MarkComputeJobFailed_input_schema(job_id=job_id, reason="cleanup"),
        session=None,
    )
    assert result.is_success is False
    assert result.previous_state == "done"
    assert "already terminal" in result.message


@pytest.mark.asyncio
async def test_reason_is_required():
    result = await MarkComputeJobFailed().tool_call(
        MarkComputeJobFailed_input_schema(job_id=1, reason="  "),
        session=None,
    )
    assert result.is_success is False
    assert "reason is required" in result.message
