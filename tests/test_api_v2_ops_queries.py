"""Ops 可观测查询路由：项目计算队列 + pending reminder 列表。

口径：
- ``GET /api/v2/projects/{id}/compute/jobs`` 默认只活跃态
  （ready/running/cancel_requested），按项目隔离，行带 session_id 归属；
- ``GET /api/v2/projects/{id}/reminders/pending`` 是
  reminder.scheduled/cancelled/fired 事件投影，行带 session_id 归属。
"""

from __future__ import annotations

import time

import pytest
from httpx import ASGITransport, AsyncClient

from cloudra.persistence.database import ComputeDB
from cloudra.runtime_v2.commands import CommandBus
from cloudra.runtime_v2.core import RuntimeCore
from cloudra.runtime_v2.schemas import Command
from cloudra.services.api_v2 import create_v2_app
from cloudra.services.compute_store import insert_compute_job


async def _make_project(core: RuntimeCore, name: str = "p"):
    return (
        await CommandBus(core).execute(
            Command(type="project.create", payload={"name": name})
        )
    ).data


def _insert_job(db: ComputeDB, *, conversation_id: str, state: str, session_id=None) -> int:
    return insert_compute_job(
        db,
        conversation_id=conversation_id,
        session_id=session_id,
        path="/tmp/input.inp",
        state=state,
        jobtype="orca",
        scheduler="local",
    )


@pytest.mark.asyncio
async def test_compute_jobs_defaults_to_active_states_and_project_scope():
    core = RuntimeCore(strict_events=True)
    project = await _make_project(core)
    other = await _make_project(core, "other")
    db = ComputeDB().init()
    _insert_job(db, conversation_id=project.id, state="ready", session_id="as_owner")
    _insert_job(db, conversation_id=project.id, state="running")
    _insert_job(db, conversation_id=project.id, state="done")
    _insert_job(db, conversation_id=other.id, state="ready")

    app = create_v2_app(core)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        resp = await client.get(f"/api/v2/projects/{project.id}/compute/jobs")
        assert resp.status_code == 200
        rows = resp.json()
        assert {r["state"] for r in rows} == {"ready", "running"}
        assert all(r["conversation_id"] == project.id for r in rows)
        owner = next(r for r in rows if r["state"] == "ready")
        assert owner["session_id"] == "as_owner"

        resp = await client.get(
            f"/api/v2/projects/{project.id}/compute/jobs",
            params={"active_only": False},
        )
        assert resp.status_code == 200
        assert "done" in {r["state"] for r in resp.json()}


@pytest.mark.asyncio
async def test_compute_jobs_unknown_project_is_404():
    app = create_v2_app(RuntimeCore(strict_events=True))
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        resp = await client.get("/api/v2/projects/prj_nope/compute/jobs")
        assert resp.status_code == 404


@pytest.mark.asyncio
async def test_pending_reminders_projection_and_project_scope():
    core = RuntimeCore(strict_events=True)
    project = await _make_project(core)
    other = await _make_project(core, "other")
    future = time.time() + 600
    core.event_log.append(
        "reminder.scheduled",
        stream="agent",
        project_id=project.id,
        session_id="as_owner",
        data={"message": "check IRC", "wake_at": "2099-01-01T00:00:00+00:00", "wake_ts": future},
    )
    fired = core.event_log.append(
        "reminder.scheduled",
        stream="agent",
        project_id=project.id,
        session_id="as_owner",
        data={"message": "already fired", "wake_at": "2020-01-01T00:00:00+00:00", "wake_ts": 1.0},
    )
    core.event_log.append(
        "reminder.fired",
        stream="agent",
        project_id=project.id,
        session_id="as_owner",
        data={"schedule_id": fired.seq, "message": "already fired"},
    )
    core.event_log.append(
        "reminder.scheduled",
        stream="agent",
        project_id=other.id,
        session_id="as_other",
        data={"message": "other project", "wake_at": "2099-01-01T00:00:00+00:00", "wake_ts": future},
    )

    app = create_v2_app(core)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        resp = await client.get(f"/api/v2/projects/{project.id}/reminders/pending")
        assert resp.status_code == 200
        rows = resp.json()
        assert len(rows) == 1
        row = rows[0]
        assert row["session_id"] == "as_owner"
        assert row["message"] == "check IRC"
        assert row["wake_ts"] == future

        resp = await client.get("/api/v2/projects/prj_nope/reminders/pending")
        assert resp.status_code == 404
