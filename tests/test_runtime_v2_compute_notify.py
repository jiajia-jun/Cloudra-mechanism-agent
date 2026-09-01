"""Compute job 完成通知：中央 compute.db 纯轮询补投 -> agent.message（v2 native path）。"""

from __future__ import annotations

import asyncio
import json
import time

import pytest

from cloudra.persistence.database import ComputeDB
from cloudra.runtime_v2.commands import CommandBus
from cloudra.runtime_v2.compute_notify import ComputeNotifyBroker
from cloudra.runtime_v2.core import RuntimeCore
from cloudra.runtime_v2.schemas import Command


async def _setup_core():
    core = RuntimeCore(strict_events=True)
    bus = CommandBus(core)
    await bus.execute(Command(type="project.create", payload={"name": "compute"}))
    project = next(iter(core.projects.values()))
    result = await bus.execute(
        Command(
            type="agent.spawn",
            target={"project_id": project.id},
            payload={"role_id": "coordinator"},
        )
    )
    coordinator = result.data
    # Drain spawn query-less inbox noise if any.
    inbox = core.mailbox.inbox(coordinator.id)
    if inbox is not None:
        while not inbox.empty():
            inbox.get_nowait()
    return core, project, coordinator


def _inbox_texts(core, session_id: str) -> list[str]:
    inbox = core.mailbox.inbox(session_id)
    texts = []
    if inbox is not None:
        while not inbox.empty():
            texts.append(str(inbox.get_nowait().get("content", "")))
    return texts


def _insert_terminal_job(project_id: str, *, session_id: str | None, state: str = "done") -> int:
    """往中央 compute.db 写一条终态 compute_jobs 行（notified_at 留 NULL）。"""
    db = ComputeDB().init()
    with db.connect() as con:
        cur = con.execute(
            """INSERT INTO compute_jobs
            (conversation_id, session_id, path, state, jobtype,
             start_timestamp, end_timestamp, scheduler, scheduler_options)
            VALUES (?,?,?,?,?,?,?,?,?)""",
            (
                project_id, session_id, "/tmp/x.gjf", state, "gaussian",
                time.time() - 100, time.time(), "local",
                json.dumps({"type": "local"}),
            ),
        )
        job_id = int(cur.lastrowid)
        con.commit()
    return job_id


def _notified_at(job_id: int):
    db = ComputeDB()
    with db.connect() as con:
        row = con.execute(
            "SELECT notified_at FROM compute_jobs WHERE id=?", (job_id,)
        ).fetchone()
    return row[0] if row else None


@pytest.mark.asyncio
async def test_poll_delivers_agent_message_and_marks_notified():
    core, project, coordinator = await _setup_core()
    job_id = _insert_terminal_job(project.id, session_id=coordinator.id)
    broker = ComputeNotifyBroker(core, poll_interval=0.05)

    await broker._poll_project(project.id)

    events = core.event_log.query_session(
        coordinator.id, types={"agent.message_injected"}
    )
    assert len(events) == 1
    assert f"task_id={job_id}" in events[0].data["content"]
    texts = _inbox_texts(core, coordinator.id)
    assert any(f"task_id={job_id}" in t for t in texts)
    assert _notified_at(job_id) is not None

    # notified_at 去重：再扫一轮不再投递
    await broker._poll_project(project.id)
    assert (
        len(core.event_log.query_session(coordinator.id, types={"agent.message_injected"})) == 1
    )


@pytest.mark.asyncio
async def test_poll_falls_back_to_coordinator_for_unknown_session():
    core, project, coordinator = await _setup_core()
    job_id = _insert_terminal_job(project.id, session_id="ghost-agent")
    broker = ComputeNotifyBroker(core, poll_interval=0.05)

    await broker._poll_project(project.id)

    events = core.event_log.query_session(
        coordinator.id, types={"agent.message_injected"}
    )
    assert len(events) == 1
    assert f"task_id={job_id}" in events[0].data["content"]


@pytest.mark.asyncio
async def test_start_polls_automatically_until_close():
    core, project, coordinator = await _setup_core()
    job_id = _insert_terminal_job(project.id, session_id=coordinator.id)
    broker = ComputeNotifyBroker(core, poll_interval=0.05)
    await broker.start()
    try:
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline and _notified_at(job_id) is None:
            await asyncio.sleep(0.02)
        assert _notified_at(job_id) is not None
        assert (
            len(core.event_log.query_session(coordinator.id, types={"agent.message_injected"}))
            == 1
        )
    finally:
        await broker.close()


@pytest.mark.asyncio
async def test_poll_all_skips_unloaded_projects():
    """全局扫描只投递已加载项目；未加载项目的行跳过且不落 notified_at。"""
    core, project, coordinator = await _setup_core()
    loaded_job = _insert_terminal_job(project.id, session_id=coordinator.id)
    ghost_job = _insert_terminal_job("prj_unloaded", session_id=None)
    broker = ComputeNotifyBroker(core, poll_interval=0.05)

    await broker._poll_all()

    assert _notified_at(loaded_job) is not None
    assert _notified_at(ghost_job) is None


@pytest.mark.asyncio
async def test_ensure_project_scans_immediately():
    """项目打开时 ensure_project 立即扫该项目，不等下个 tick。"""
    core, project, coordinator = await _setup_core()
    job_id = _insert_terminal_job(project.id, session_id=coordinator.id)
    broker = ComputeNotifyBroker(core, poll_interval=999.0)

    await broker.ensure_project(project.id)

    assert _notified_at(job_id) is not None
    assert (
        len(core.event_log.query_session(coordinator.id, types={"agent.message_injected"}))
        == 1
    )
