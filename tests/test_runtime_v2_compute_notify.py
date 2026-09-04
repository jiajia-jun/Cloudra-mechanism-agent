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
from cloudra.runtime_v2.knowledge import (
    KnowledgeEntry,
    clear_knowledge_providers,
    register_knowledge_provider,
)
from cloudra.runtime_v2.schemas import Command


@pytest.fixture(autouse=True)
def _clean_registry():
    clear_knowledge_providers()
    yield
    clear_knowledge_providers()


class _KBProvider:
    name = "fake-kb"

    def search(self, query, *, limit=5):
        return [
            KnowledgeEntry(
                title="SCF convergence fix",
                content="switch to quadratically convergent SCF",
                evidence_level="L0",
                source="kb:1",
            )
        ]


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


def _insert_terminal_job(
    project_id: str,
    *,
    session_id: str | None,
    state: str = "done",
    last_error: str | None = None,
    path: str = "/tmp/x.gjf",
    jobtype: str = "gaussian",
) -> int:
    """往中央 compute.db 写一条终态 compute_jobs 行（notified_at 留 NULL）。"""
    db = ComputeDB().init()
    with db.connect() as con:
        cur = con.execute(
            """INSERT INTO compute_jobs
            (conversation_id, session_id, path, state, jobtype,
             start_timestamp, end_timestamp, scheduler, scheduler_options, last_error)
            VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (
                project_id, session_id, path, state, jobtype,
                time.time() - 100, time.time(), "local",
                json.dumps({"type": "local"}), last_error,
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


def _delivered_content(core, session_id: str) -> str:
    events = core.event_log.query_session(session_id, types={"agent.message_injected"})
    assert len(events) == 1
    return events[0].data["content"]


@pytest.mark.asyncio
async def test_failed_job_delivers_knowledge_suggestions():
    """失败终态自动检索知识库，命中建议拼进 agent.message。"""
    register_knowledge_provider(_KBProvider())
    core, project, coordinator = await _setup_core()
    _insert_terminal_job(
        project.id, session_id=coordinator.id, state="failed", last_error="SCF did not converge"
    )
    broker = ComputeNotifyBroker(core, poll_interval=0.05)

    await broker._poll_project(project.id)

    content = _delivered_content(core, coordinator.id)
    assert "SCF convergence fix" in content
    assert "Knowledge base suggestions" in content


@pytest.mark.asyncio
async def test_done_job_delivers_knowledge_suggestions():
    """成功终态同样自动检索（engine + input stem 作为 query）。"""
    register_knowledge_provider(_KBProvider())
    core, project, coordinator = await _setup_core()
    _insert_terminal_job(project.id, session_id=coordinator.id, state="done")
    broker = ComputeNotifyBroker(core, poll_interval=0.05)

    await broker._poll_project(project.id)

    content = _delivered_content(core, coordinator.id)
    assert "SCF convergence fix" in content
    assert "Knowledge base suggestions" in content


@pytest.mark.asyncio
async def test_no_provider_notification_unchanged():
    """无 provider（知识库未装）时通知文本不夹带知识建议。"""
    core, project, coordinator = await _setup_core()
    _insert_terminal_job(
        project.id, session_id=coordinator.id, state="failed", last_error="SCF did not converge"
    )
    broker = ComputeNotifyBroker(core, poll_interval=0.05)

    await broker._poll_project(project.id)

    content = _delivered_content(core, coordinator.id)
    assert "Knowledge base suggestions" not in content


@pytest.mark.asyncio
async def test_notification_log_path_prefers_guard_state_json(tmp_path):
    """GH #20：通知里的 log_path 与 guard 实际解析的日志一致——优先取
    state json 的 log_file（macOS ORCA 不落 .out，真实日志是
    .cloudra/calc-<id>.out.log），不再报不存在的预测路径。"""
    core, project, coordinator = await _setup_core()

    workdir = tmp_path / "calc_task"
    workdir.mkdir()
    inp = workdir / "acetaldehyde_opt.inp"
    inp.write_text("! ExtOpt Opt\n", encoding="utf-8")
    # 先建行拿 task_id，再按真实 id 落 state json / calc 落盘
    job_id = _insert_terminal_job(
        project.id, session_id=coordinator.id, path=str(inp), jobtype="orca"
    )
    run_dir = workdir / ".cloudra"
    run_dir.mkdir()
    captured = run_dir / f"calc-{job_id}.out.log"
    captured.write_text("ORCA TERMINATED NORMALLY\n", encoding="utf-8")
    (workdir / f"state_{job_id}.json").write_text(
        json.dumps({"log_file": str(captured)}), encoding="utf-8"
    )

    broker = ComputeNotifyBroker(core, poll_interval=0.05)
    await broker._poll_project(project.id)

    content = _delivered_content(core, coordinator.id)
    assert str(captured) in content
    assert f"{inp.stem}.out" not in content


@pytest.mark.asyncio
async def test_terminal_job_snapshots_core_evidence_before_notify(tmp_path):
    """终态通知前登记核心文件的 Artifact 快照；通知文本带快照引用。"""
    core, project, coordinator = await _setup_core()

    workdir = tmp_path / "calc_snap"
    workdir.mkdir()
    inp = workdir / "opt.gjf"
    inp.write_text("%chk=opt\n#p b3lyp/def2svp opt\n", encoding="utf-8")
    job_id = _insert_terminal_job(project.id, session_id=coordinator.id, path=str(inp))

    broker = ComputeNotifyBroker(core, poll_interval=0.05)
    await broker._poll_project(project.id)

    content = _delivered_content(core, coordinator.id)
    assert "[Evidence snapshot]" in content
    assert "opt.gjf" in content and "registered" in content
    # 惯例预测的日志未落盘：标注但不误报 unavailable、不进重试
    assert "log_not_collected" in content
    assert job_id not in broker._snapshot_retries

    from cloudra.persistence.artifacts import ArtifactService

    artifacts = ArtifactService().list(project.id)
    assert any(a.source_path == str(inp.resolve()) for a in artifacts)

    # 同一路径同一内容的后续作业：复用 hash，不重复拷贝
    job_id2 = _insert_terminal_job(project.id, session_id=coordinator.id, path=str(inp))
    await broker._poll_project(project.id)
    artifacts_after = ArtifactService().list(project.id)
    assert len(artifacts_after) == len(artifacts)


@pytest.mark.asyncio
async def test_unavailable_evidence_retried_without_resending(tmp_path):
    """核心文件暂不可读：通知照常投递并标 evidence_unavailable（不丢消息、
    不落 fake 可复查）；文件到位后静默重试，收齐一次性补发。"""
    core, project, coordinator = await _setup_core()

    workdir = tmp_path / "calc_late"
    workdir.mkdir()
    inp = workdir / "late.inp"
    job_id = _insert_terminal_job(
        project.id, session_id=coordinator.id, path=str(inp), jobtype="orca"
    )

    broker = ComputeNotifyBroker(core, poll_interval=0.05)
    await broker._poll_project(project.id)

    content = _delivered_content(core, coordinator.id)
    assert "evidence_unavailable" in content
    assert _notified_at(job_id) is not None  # 消息不丢
    assert job_id in broker._snapshot_retries

    # 文件到位：静默重试成功 → 一次性补发可复查通知，原通知不重复投递
    inp.write_text("! ExtOpt Opt\n", encoding="utf-8")
    events_before = len(
        core.event_log.query_session(coordinator.id, types={"agent.message_injected"})
    )
    await broker._retry_snapshots()
    assert job_id not in broker._snapshot_retries
    events = core.event_log.query_session(coordinator.id, types={"agent.message_injected"})
    assert len(events) == events_before + 1
    assert "now available for review" in events[-1].data["content"]
