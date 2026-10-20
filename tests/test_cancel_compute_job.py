"""Scoped cancellation is an execution request, never a failure verdict."""

import asyncio
import os
from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient

from cloudra.persistence.database import ComputeDB
from cloudra.runtime_v2.core import RuntimeCore
from cloudra.runtime_v2.schemas import Project
from cloudra.services.api_v2 import create_v2_app
from cloudra.services.compute_store import get_compute_job, insert_compute_job


def _job(db, tmp_path, *, state="running", project="own", scheduler="local"):
    return insert_compute_job(
        db, node_id="node-local", conversation_id=project, session_id="producer",
        path=str(tmp_path / "input.inp"), state=state, jobtype="orca", scheduler=scheduler,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("scheduler", ["local", "slurm", "ssh_local", "ssh_slurm"])
@pytest.mark.parametrize("state,expected", [("ready", "cancelled"), ("running", "cancel_requested")])
async def test_scoped_api_requests_cancellation_without_terminalizing_live_work(tmp_path, scheduler, state, expected):
    db = await ComputeDB().ainit()
    job_id = await asyncio.to_thread(_job, db, tmp_path, state=state, scheduler=scheduler)
    other = await asyncio.to_thread(_job, db, tmp_path, state="running", project="other")
    core = RuntimeCore(strict_events=True)
    core.projects["own"] = Project(id="own", name="own")
    app = create_v2_app(core)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        result = await client.post(f"/api/v2/projects/own/compute/jobs/{job_id}/cancel", json={"reason": "replace this trial"})
    assert result.status_code == 200
    assert result.json()["is_success"] is True
    assert result.json()["previous_state"] == state
    assert result.json()["state"] == expected
    row = (await asyncio.to_thread(get_compute_job, db, job_id))
    assert row["state"] == expected
    assert row["last_error"] == "replace this trial"
    assert (row["end_timestamp"] > 0) is (state == "ready")
    assert (await asyncio.to_thread(get_compute_job, db, other))["state"] == "running"


@pytest.mark.asyncio
async def test_scoped_api_does_not_cancel_foreign_job(tmp_path):
    db = await ComputeDB().ainit()
    job_id = await asyncio.to_thread(_job, db, tmp_path, project="other")
    core = RuntimeCore(strict_events=True)
    core.projects["own"] = Project(id="own", name="own")
    async with AsyncClient(transport=ASGITransport(app=create_v2_app(core)), base_url="http://testserver") as client:
        result = await client.post(f"/api/v2/projects/own/compute/jobs/{job_id}/cancel", json={"reason": "cancel"})
    assert result.status_code == 404
    assert (await asyncio.to_thread(get_compute_job, db, job_id))["state"] == "running"


@pytest.mark.asyncio
@pytest.mark.parametrize("state", ["done", "failed", "cancelled", "cancel_requested"])
async def test_public_tool_reports_existing_state_without_rewriting_it(tmp_path, state):
    from cloudra.tools.Chemtool.cancel_compute_job import CancelComputeJob, CancelComputeJob_input_schema

    db = await ComputeDB().ainit()
    job_id = await asyncio.to_thread(_job, db, tmp_path, state=state)
    tool = CancelComputeJob(subagent=SimpleNamespace(conversation_id="own"))
    result = await tool.tool_call(CancelComputeJob_input_schema(job_id=job_id, reason="cancel trial"), session=None)
    assert result.is_success is (state in {"cancelled", "cancel_requested"})
    assert result.state == state
    assert result.previous_state == state
    assert (await asyncio.to_thread(get_compute_job, db, job_id))["state"] == state


@pytest.mark.asyncio
async def test_public_tool_preserves_live_locks_and_requests_owner_cancellation(tmp_path):
    from cloudra.infra.compute_utils import calc_lock_path, guard_lock_path
    from cloudra.infra.flocks import is_lock_held, try_acquire_lock
    from cloudra.tools.Chemtool.cancel_compute_job import CancelComputeJob, CancelComputeJob_input_schema

    db = await ComputeDB().ainit()
    job_id = await asyncio.to_thread(_job, db, tmp_path)
    paths = [await asyncio.to_thread(helper, str(tmp_path), job_id) for helper in (calc_lock_path, guard_lock_path)]
    fds = [await asyncio.to_thread(try_acquire_lock, path) for path in paths]
    assert all(fd is not None for fd in fds)
    try:
        tool = CancelComputeJob(subagent=SimpleNamespace(conversation_id="own"))
        result = await tool.tool_call(CancelComputeJob_input_schema(job_id=job_id, reason="stop this trial"), session=None)
        assert result.is_success
        assert result.state == "cancel_requested"
        assert (await asyncio.to_thread(get_compute_job, db, job_id))["state"] == "cancel_requested"
        assert all([await asyncio.to_thread(is_lock_held, path) for path in paths])
    finally:
        for fd in fds:
            await asyncio.to_thread(os.close, fd)


@pytest.mark.asyncio
async def test_public_tool_cannot_cancel_foreign_job(tmp_path):
    from cloudra.tools.Chemtool.cancel_compute_job import CancelComputeJob, CancelComputeJob_input_schema

    db = await ComputeDB().ainit()
    job_id = await asyncio.to_thread(_job, db, tmp_path, project="other")
    tool = CancelComputeJob(subagent=SimpleNamespace(conversation_id="own"))
    result = await tool.tool_call(CancelComputeJob_input_schema(job_id=job_id, reason="cancel"), session=None)
    assert not result.is_success
    assert (await asyncio.to_thread(get_compute_job, db, job_id))["state"] == "running"
