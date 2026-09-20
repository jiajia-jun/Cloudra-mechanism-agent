"""guard 终态：CAS 失败不得写成功产物、不得入 DAG 收件箱。"""

from __future__ import annotations

from pathlib import Path

import pytest

from cloudra.persistence.database import ComputeDB
from cloudra.services.compute_store import get_compute_job, insert_compute_job


@pytest.mark.asyncio
async def test_finalize_skips_artifact_and_review_when_ledger_already_cancelled(
    tmp_path, monkeypatch
):
    from cloudra.runtime import monitor

    workdir = tmp_path / "job"
    workdir.mkdir()
    inp = workdir / "input.gjf"
    inp.write_text("%chk=x\n")
    db = ComputeDB().init()
    task_id = insert_compute_job(
        db,
        node_id="node-local",
        conversation_id="prj",
        session_id="s1",
        path=str(inp),
        state="cancelled",
        jobtype="gaussian",
        scheduler="local",
    )

    async def fake_parse(*_args, **_kwargs):
        return {"energy": -76.0}, True

    reviews: list[tuple[int, str]] = []

    async def fake_enqueue(taskid: int, state: str) -> None:
        reviews.append((taskid, state))

    monkeypatch.setattr(monitor, "_parse_log", fake_parse)
    monkeypatch.setattr(
        "cloudra.dag.controller.enqueue_compute_review", fake_enqueue
    )

    await monitor._finalize(
        db,
        task_id,
        Path("unused.log"),
        str(workdir),
        parse_timeout=1,
        job_type="gaussian",
        returncode=0,
    )

    row = get_compute_job(db, task_id)
    assert row["state"] == "cancelled"
    assert not (workdir / f"state_{task_id}.json").exists()
    assert reviews == []


@pytest.mark.asyncio
async def test_finalize_commits_running_job(tmp_path, monkeypatch):
    from cloudra.runtime import monitor

    workdir = tmp_path / "job"
    workdir.mkdir()
    inp = workdir / "input.gjf"
    inp.write_text("%chk=x\n")
    db = ComputeDB().init()
    task_id = insert_compute_job(
        db,
        node_id="node-local",
        conversation_id="prj",
        session_id="s1",
        path=str(inp),
        state="running",
        jobtype="gaussian",
        scheduler="local",
    )

    async def fake_parse(*_args, **_kwargs):
        return {"energy": -76.0}, True

    reviews: list[tuple[int, str]] = []

    async def fake_enqueue(taskid: int, state: str) -> None:
        reviews.append((taskid, state))

    monkeypatch.setattr(monitor, "_parse_log", fake_parse)
    monkeypatch.setattr(
        "cloudra.dag.controller.enqueue_compute_review", fake_enqueue
    )

    await monitor._finalize(
        db,
        task_id,
        Path("unused.log"),
        str(workdir),
        parse_timeout=1,
        job_type="gaussian",
        returncode=0,
    )

    row = get_compute_job(db, task_id)
    assert row["state"] == "done"
    assert (workdir / f"state_{task_id}.json").is_file()
    assert reviews == [(task_id, "done")]


@pytest.mark.asyncio
async def test_gaussian_text_marker_not_cclib_decides_success(tmp_path, monkeypatch):
    from cloudra.runtime import monitor

    log = tmp_path / "job.log"
    log.write_text("junk coords missing\n Normal termination of Gaussian 16 at ...\n")

    async def no_cclib(_target):
        return None

    monkeypatch.setattr(monitor, "_cclib_parse", no_cclib)
    data, ok = await monitor._parse_log(log, 1, job_type="gaussian")
    assert ok is True
    assert data["is_success"] is True

    log.write_text("Error termination via Lnk1e in ...\n")
    data, ok = await monitor._parse_log(log, 1, job_type="gaussian")
    assert ok is False
