"""一键取消全部 compute job（账本级取消，绝不杀进程）的存储层与 API 测试。

状态分桶语义（services/compute_store.acancel_all_compute_jobs）：
- ready → cancelled；running + slurm → cancel_requested（既有 poll 循环
  走 scancel 收尾）；running + 本地 → cancelled（guard 终态 CAS no-op）；
- 终态行不动；中央库不存在即全零、不建库。
"""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient

from cloudra.infra.config import _reset_for_tests
from cloudra.persistence.database import ComputeDB
from cloudra.runtime_v2.core import RuntimeCore
from cloudra.services.api_v2 import create_v2_app
from cloudra.services.compute_store import (
    acancel_all_compute_jobs,
    get_compute_job,
    insert_compute_job,
)

_ZERO = {"ready_cancelled": 0, "slurm_cancel_requested": 0, "local_cancelled": 0}


def _insert(db: ComputeDB, *, state: str, scheduler: str = "local") -> int:
    return insert_compute_job(
        db,
        conversation_id="prj-test",
        session_id=None,
        path="/tmp/input.gjf",
        state=state,
        jobtype="gaussian",
        scheduler=scheduler,
    )


@pytest.mark.asyncio
async def test_cancel_all_state_transitions_and_counts():
    db = ComputeDB().init()
    ready_id = _insert(db, state="ready")
    slurm_id = _insert(db, state="running", scheduler="slurm")
    local_id = _insert(db, state="running", scheduler="local")
    done_id = _insert(db, state="done")

    counts = await acancel_all_compute_jobs(db)

    assert counts == {"ready_cancelled": 1, "slurm_cancel_requested": 1, "local_cancelled": 1}
    ready = get_compute_job(db, ready_id)
    assert ready["state"] == "cancelled"
    assert ready["end_timestamp"] > 0
    assert ready["last_error"] == "cancelled by cancel-all"
    # Slurm 作业只置 cancel_requested：scancel 收尾是租约持有方 poll 循环的职责
    assert get_compute_job(db, slurm_id)["state"] == "cancel_requested"
    local = get_compute_job(db, local_id)
    assert local["state"] == "cancelled"
    assert "ledger-only" in local["last_error"]
    # 终态行不动
    assert get_compute_job(db, done_id)["state"] == "done"


@pytest.mark.asyncio
async def test_cancel_all_without_db_returns_zeros_and_creates_nothing():
    db = ComputeDB()
    assert await acancel_all_compute_jobs(db) == _ZERO
    assert not os.path.exists(db.path)


@pytest.mark.asyncio
async def test_cancel_all_endpoint_returns_counts():
    db = ComputeDB().init()
    _insert(db, state="ready")
    _insert(db, state="running")
    app = create_v2_app(RuntimeCore(strict_events=True))
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.post("/api/v2/compute/cancel-all")
        assert resp.status_code == 200
        assert resp.json() == {"ready_cancelled": 1, "slurm_cancel_requested": 0, "local_cancelled": 1}
        # 幂等：再来一遍全零（所有未竟作业已是终态/cancel_requested）
        resp = await client.post("/api/v2/compute/cancel-all")
        assert resp.json() == _ZERO


def test_cancel_all_endpoint_requires_token(monkeypatch):
    monkeypatch.setenv("CLOUDRA_API_TOKEN", "test-secret-token")
    try:
        client = TestClient(create_v2_app())
        assert client.post("/api/v2/compute/cancel-all").status_code == 401
        resp = client.post(
            "/api/v2/compute/cancel-all",
            headers={"Authorization": "Bearer test-secret-token"},
        )
        assert resp.status_code == 200
        assert resp.json() == _ZERO
    finally:
        _reset_for_tests()
