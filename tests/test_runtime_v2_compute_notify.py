"""Compute job 完成通知：中央 compute.db 纯轮询补投 -> agent.message（v2 native path）。"""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path

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
    assert f"Job {job_id}," in events[0].data["content"]
    assert "agent_hub" not in events[0].data["content"]
    texts = _inbox_texts(core, coordinator.id)
    assert any(f"Job {job_id}," in t for t in texts)
    assert _notified_at(job_id) is not None

    # notified_at 去重：再扫一轮不再投递
    await broker._poll_project(project.id)
    assert (
        len(core.event_log.query_session(coordinator.id, types={"agent.message_injected"})) == 1
    )


@pytest.mark.asyncio
async def test_failed_job_notice_keeps_failure_and_next_without_repeating_workflow_instructions():
    core, project, coordinator = await _setup_core()
    job_id = _insert_terminal_job(
        project.id, session_id=coordinator.id, state="failed",
        last_error="SCF did not converge",
    )
    broker = ComputeNotifyBroker(core)

    await broker._poll_project(project.id)

    notices = core.event_log.query_session(
        coordinator.id, types={"agent.message_injected"}
    )
    assert len(notices) == 1
    content = notices[0].data["content"]
    assert f"Job {job_id}," in content
    assert "SCF did not converge" in content
    assert "NEXT:" in content and "query_compute_job" in content
    assert "agent_hub" not in content
    assert "email the user" not in content


@pytest.mark.asyncio
async def test_cancelled_job_notice_requires_new_user_request_before_resubmission():
    core, project, coordinator = await _setup_core()
    job_id = _insert_terminal_job(
        project.id, session_id=coordinator.id, state="cancelled"
    )
    broker = ComputeNotifyBroker(core)

    await broker._poll_project(project.id)

    notices = core.event_log.query_session(
        coordinator.id, types={"agent.message_injected"}
    )
    assert len(notices) == 1
    content = notices[0].data["content"]
    assert f"Job {job_id}," in content
    assert "state=cancelled" in content
    assert "Do not resubmit" in content
    assert "new explicit user request" in content
    assert "Failure reason" not in content
    assert "email the user" not in content


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
    assert f"Job {job_id}," in events[0].data["content"]


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
async def test_poll_project_delivers_immediately():
    """项目级投递不必等待下一次后台 tick。"""
    core, project, coordinator = await _setup_core()
    job_id = _insert_terminal_job(project.id, session_id=coordinator.id)
    broker = ComputeNotifyBroker(core, poll_interval=999.0)

    await broker._poll_project(project.id)

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
async def test_failed_job_does_not_expand_notice_with_automatic_knowledge_suggestions():
    """失败原因和下一步足够；知识检索保留为按需工具。"""
    register_knowledge_provider(_KBProvider())
    core, project, coordinator = await _setup_core()
    _insert_terminal_job(
        project.id, session_id=coordinator.id, state="failed", last_error="SCF did not converge"
    )
    broker = ComputeNotifyBroker(core, poll_interval=0.05)

    await broker._poll_project(project.id)

    content = _delivered_content(core, coordinator.id)
    assert "SCF did not converge" in content and "NEXT:" in content
    assert "SCF convergence fix" not in content
    assert "Knowledge base suggestions" not in content


@pytest.mark.asyncio
async def test_done_job_does_not_expand_notice_with_automatic_knowledge_suggestions():
    """成功通知保留证据入口，避免无关知识卡塞进收件箱。"""
    register_knowledge_provider(_KBProvider())
    core, project, coordinator = await _setup_core()
    _insert_terminal_job(project.id, session_id=coordinator.id, state="done")
    broker = ComputeNotifyBroker(core, poll_interval=0.05)

    await broker._poll_project(project.id)

    content = _delivered_content(core, coordinator.id)
    assert "log_parser" in content and "NEXT:" in content
    assert "SCF convergence fix" not in content
    assert "Knowledge base suggestions" not in content


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
    """内部照常登记快照；通知只给证据入口，不展示内部artifact/hash。"""
    core, project, coordinator = await _setup_core()

    workdir = tmp_path / "calc_snap"
    workdir.mkdir()
    inp = workdir / "opt.gjf"
    inp.write_text("%chk=opt\n#p b3lyp/def2svp opt\n", encoding="utf-8")
    job_id = _insert_terminal_job(project.id, session_id=coordinator.id, path=str(inp))

    broker = ComputeNotifyBroker(core, poll_interval=0.05)
    await broker._poll_project(project.id)

    content = _delivered_content(core, coordinator.id)
    assert "opt.gjf" in content
    assert "[Evidence snapshot]" not in content and "sha256" not in content
    # 惯例预测的日志未落盘：标注但不误报 unavailable、不进重试
    assert "Native output is not available yet" in content
    assert job_id not in broker._snapshot_retries

    from cloudra.persistence.artifacts import ArtifactService

    artifacts = ArtifactService().list(project.id)
    assert any(a.source_path == str(inp.resolve()) for a in artifacts)

    # 同一路径同一内容的后续作业：复用 hash，不重复拷贝
    _insert_terminal_job(project.id, session_id=coordinator.id, path=str(inp))
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
    assert "Evidence could not be recorded: late.inp" in content
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


@pytest.mark.asyncio
async def test_subagent_compute_job_does_not_notify_or_wake_coordinator():
    """子 Agent 提交的计算作业终态通知只投递给该子 Agent，绝不抄送 Coordinator，更不唤醒 Coordinator。"""
    core, project, coordinator = await _setup_core()
    bus = CommandBus(core)
    res = await bus.execute(
        Command(
            type="agent.spawn",
            target={"project_id": project.id},
            payload={"role_id": "small_mol", "parent_session_id": coordinator.id},
        )
    )
    subagent = res.data
    job_id = _insert_terminal_job(project.id, session_id=subagent.id)
    broker = ComputeNotifyBroker(core, poll_interval=0.05)

    await broker._poll_project(project.id)

    # 子 Agent 收到通知
    sub_events = core.event_log.query_session(subagent.id, types={"agent.message_injected"})
    assert len(sub_events) == 1
    assert f"Job {job_id}," in sub_events[0].data["content"]

    # Coordinator 绝不收到该通知
    coord_events = core.event_log.query_session(coordinator.id, types={"agent.message_injected"})
    assert len(coord_events) == 0
    assert _inbox_texts(core, coordinator.id) == []


@pytest.mark.asyncio
@pytest.mark.parametrize("state", ["done", "failed", "cancelled"])
async def test_subagent_receives_results_while_other_owned_jobs_run(state):
    """A long-running batch must not delay processing completed jobs or repairs."""
    core, project, coordinator = await _setup_core()
    child = (
        await CommandBus(core).execute(
            Command(
                type="agent.spawn",
                target={"project_id": project.id},
                payload={"role_id": "small_mol", "parent_session_id": coordinator.id},
            )
        )
    ).data
    await core.agent_host.start_run(child)
    await core.agent_host.finish_run(child, outcome="succeeded")
    finished = [
        _insert_terminal_job(project.id, session_id=child.id, state=state, path=f"/tmp/done-{i}.gjf")
        for i in range(2)
    ]
    pending = _insert_terminal_job(project.id, session_id=child.id, path="/tmp/pending.gjf")
    with ComputeDB().connect() as con:
        con.execute("UPDATE compute_jobs SET state='running' WHERE id=?", (pending,))
        con.commit()
    wakes = []

    class FakeRunner:
        def schedule(self, session_id):
            wakes.append(session_id)

    core.runner = FakeRunner()
    broker = ComputeNotifyBroker(core, poll_interval=0.05)

    await broker._poll_project(project.id)

    assert child.state.value == "running"
    assert wakes == [child.id]
    assert all(_notified_at(job_id) is not None for job_id in finished)
    assert len(core.event_log.query_session(child.id, types={"agent.message_injected"})) == 2

    _inbox_texts(core, child.id)
    await core.agent_host.finish_run(child, outcome="succeeded")

    with ComputeDB().connect() as con:
        con.execute("UPDATE compute_jobs SET state='done' WHERE id=?", (pending,))
        con.commit()
    await broker._poll_project(project.id)

    assert wakes == [child.id, child.id]
    assert child.state.value == "running"
    assert _notified_at(pending) is not None
    assert len(core.event_log.query_session(child.id, types={"agent.message_injected"})) == 3


@pytest.mark.asyncio
async def test_same_poll_batch_wakes_subagent_once():
    core, project, coordinator = await _setup_core()
    child = (
        await CommandBus(core).execute(
            Command(
                type="agent.spawn",
                target={"project_id": project.id},
                payload={"role_id": "small_mol", "parent_session_id": coordinator.id},
            )
        )
    ).data
    await core.agent_host.start_run(child)
    await core.agent_host.finish_run(child, outcome="succeeded")
    job_ids = [
        _insert_terminal_job(project.id, session_id=child.id, path=f"/tmp/batch-{i}.gjf")
        for i in range(2)
    ]
    wakes = []

    class FakeRunner:
        def schedule(self, session_id):
            wakes.append(session_id)

    core.runner = FakeRunner()
    broker = ComputeNotifyBroker(core, poll_interval=0.05)

    await broker._poll_project(project.id)

    assert wakes == [child.id]
    assert all(_notified_at(job_id) is not None for job_id in job_ids)
    assert len(core.event_log.query_session(child.id, types={"agent.message_injected"})) == 2


@pytest.mark.asyncio
async def test_subagent_processes_results_before_terminal_backlog_is_drained():
    """A poll limit must not postpone already delivered results behind the backlog."""
    core, project, coordinator = await _setup_core()
    child = (
        await CommandBus(core).execute(
            Command(
                type="agent.spawn",
                target={"project_id": project.id},
                payload={"role_id": "small_mol", "parent_session_id": coordinator.id},
            )
        )
    ).data
    await core.agent_host.start_run(child)
    await core.agent_host.finish_run(child, outcome="succeeded")
    job_ids = [
        _insert_terminal_job(project.id, session_id=child.id, path="")
        for _ in range(51)
    ]
    wakes = []

    class FakeRunner:
        def schedule(self, session_id):
            wakes.append(session_id)

    core.runner = FakeRunner()
    broker = ComputeNotifyBroker(core, poll_interval=0.05)

    await broker._poll_project(project.id)

    assert wakes == [child.id]
    assert child.state.value == "running"
    assert all(_notified_at(job_id) is not None for job_id in job_ids[:50])
    assert _notified_at(job_ids[-1]) is None

    await broker._poll_project(project.id)

    assert wakes == [child.id]
    assert _notified_at(job_ids[-1]) is not None
    assert len(core.event_log.query_session(child.id, types={"agent.message_injected"})) == 51


@pytest.mark.asyncio
async def test_snapshot_recovery_wakes_despite_other_pending_jobs(monkeypatch):
    core, project, coordinator = await _setup_core()
    child = (
        await CommandBus(core).execute(
            Command(
                type="agent.spawn",
                target={"project_id": project.id},
                payload={"role_id": "small_mol", "parent_session_id": coordinator.id},
            )
        )
    ).data
    await core.agent_host.start_run(child)
    await core.agent_host.finish_run(child, outcome="succeeded")
    recovered_job = _insert_terminal_job(project.id, session_id=child.id, path="")
    other_job = _insert_terminal_job(project.id, session_id=child.id, path="")
    from cloudra.services.compute_store import mark_notified

    mark_notified(ComputeDB(), recovered_job)
    assert _notified_at(other_job) is None
    broker = ComputeNotifyBroker(core)
    broker._snapshot_retries[recovered_job] = (project.id, child.id, False)

    async def recovered(*_args):
        return "snapshot ready", True

    monkeypatch.setattr(broker, "_snapshot_core_evidence", recovered)
    await broker._retry_snapshots()

    assert child.state.value == "running"
    assert len(_inbox_texts(core, child.id)) == 1
    assert _notified_at(other_job) is None


@pytest.mark.asyncio
async def test_project_scan_and_periodic_scan_deliver_each_job_once(monkeypatch):
    core, project, coordinator = await _setup_core()
    job_id = _insert_terminal_job(project.id, session_id=coordinator.id, path="")
    broker = ComputeNotifyBroker(core)
    entered = asyncio.Event()
    release = asyncio.Event()
    original_deliver = broker._deliver

    async def delayed_deliver(*args, **kwargs):
        entered.set()
        await release.wait()
        return await original_deliver(*args, **kwargs)

    monkeypatch.setattr(broker, "_deliver", delayed_deliver)
    project_scan = asyncio.create_task(broker._poll_project(project.id))
    try:
        await asyncio.wait_for(entered.wait(), timeout=2)
        periodic_scan = asyncio.create_task(broker._poll_all())
        await asyncio.sleep(0.05)
    finally:
        release.set()
    await asyncio.gather(project_scan, periodic_scan)

    assert _notified_at(job_id) is not None
    events = core.event_log.query_session(
        coordinator.id, types={"agent.message_injected"}
    )
    assert len(events) == 1


@pytest.mark.asyncio
async def test_pipeline_advancement_failure_retries_without_losing_notice(monkeypatch):
    core, project, coordinator = await _setup_core()
    child = (
        await CommandBus(core).execute(
            Command(
                type="agent.spawn",
                target={"project_id": project.id},
                payload={"role_id": "small_mol", "parent_session_id": coordinator.id},
            )
        )
    ).data
    job_id = _insert_terminal_job(project.id, session_id=child.id)
    broker = ComputeNotifyBroker(core, poll_interval=0.05)

    def unavailable(*_args):
        raise RuntimeError("compute.db temporarily unavailable")

    with monkeypatch.context() as patcher:
        patcher.setattr(
            "cloudra.tools.core.ts_pipeline_driver.handle_process_job_terminal",
            unavailable,
        )
        await broker._poll_project(project.id)

    assert _notified_at(job_id) is None
    assert core.event_log.query_session(child.id, types={"agent.message_injected"}) == []
    await broker._poll_project(project.id)
    assert _notified_at(job_id) is not None
    assert len(core.event_log.query_session(child.id, types={"agent.message_injected"})) == 1


@pytest.mark.asyncio
async def test_notified_mark_failure_holds_later_notice_and_wake(monkeypatch):
    """A failed ack on the first job keeps the batch's final wake for retry."""
    from cloudra.services.compute_store import mark_notified as real_mark_notified

    core, project, coordinator = await _setup_core()
    child = (
        await CommandBus(core).execute(
            Command(
                type="agent.spawn",
                target={"project_id": project.id},
                payload={"role_id": "small_mol", "parent_session_id": coordinator.id},
            )
        )
    ).data
    await core.agent_host.start_run(child)
    await core.agent_host.finish_run(child, outcome="succeeded")
    job_ids = [
        _insert_terminal_job(project.id, session_id=child.id, path="")
        for _ in range(2)
    ]
    wakes = []

    class FakeRunner:
        def schedule(self, session_id):
            wakes.append(session_id)

    core.runner = FakeRunner()
    broker = ComputeNotifyBroker(core, poll_interval=0.05)

    def fail_first_mark(db, task_id):
        if task_id == job_ids[0]:
            raise OSError("compute.db temporarily read-only")
        return real_mark_notified(db, task_id)

    with monkeypatch.context() as patcher:
        patcher.setattr("cloudra.runtime_v2.compute_notify.mark_notified", fail_first_mark)
        await broker._poll_project(project.id)

    assert wakes == []
    assert child.state.value == "succeeded"
    assert [_notified_at(job_id) for job_id in job_ids] == [None, None]
    assert len(core.event_log.query_session(child.id, types={"agent.message_injected"})) == 1

    await broker._poll_project(project.id)

    assert wakes == [child.id]
    assert all(_notified_at(job_id) is not None for job_id in job_ids)
    # Retrying the DB ack reuses the already durable message.
    assert len(core.event_log.query_session(child.id, types={"agent.message_injected"})) == 2


@pytest.mark.asyncio
async def test_final_notice_ack_failure_does_not_wake_or_duplicate(monkeypatch):
    core, project, coordinator = await _setup_core()
    child = (
        await CommandBus(core).execute(
            Command(
                type="agent.spawn",
                target={"project_id": project.id},
                payload={"role_id": "small_mol", "parent_session_id": coordinator.id},
            )
        )
    ).data
    await core.agent_host.start_run(child)
    await core.agent_host.finish_run(child, outcome="succeeded")
    job_id = _insert_terminal_job(project.id, session_id=child.id, path="")
    wakes = []

    class FakeRunner:
        def schedule(self, session_id):
            wakes.append(session_id)

    core.runner = FakeRunner()
    broker = ComputeNotifyBroker(core)
    real_mark = broker._mark_notified

    def failed_mark(task_id):
        if task_id == job_id:
            raise OSError("compute.db temporarily read-only")
        return real_mark(task_id)

    with monkeypatch.context() as patcher:
        patcher.setattr(broker, "_mark_notified", failed_mark)
        await broker._poll_project(project.id)

    assert wakes == []
    assert child.state.value == "succeeded"
    assert _notified_at(job_id) is None
    assert len(core.event_log.query_session(child.id, types={"agent.message_injected"})) == 1

    await broker._poll_project(project.id)

    assert wakes == [child.id]
    assert _notified_at(job_id) is not None
    assert len(core.event_log.query_session(child.id, types={"agent.message_injected"})) == 1


@pytest.mark.asyncio
async def test_coordinator_compute_job_delivered_silently_without_wake():
    """Coordinator 自身提交或 fallback 投递的计算通知静默存入信箱，绝不强制 schedule 唤醒。"""
    core, project, coordinator = await _setup_core()
    scheduled_sessions = []

    class FakeRunner:
        def schedule(self, session_id):
            scheduled_sessions.append(session_id)

    core.runner = FakeRunner()

    job_id = _insert_terminal_job(project.id, session_id=coordinator.id)
    broker = ComputeNotifyBroker(core, poll_interval=0.05)

    await broker._poll_project(project.id)

    # 存入信箱和事件日志
    events = core.event_log.query_session(coordinator.id, types={"agent.message_injected"})
    assert len(events) == 1
    assert f"Job {job_id}," in events[0].data["content"]
    assert any(f"Job {job_id}," in t for t in _inbox_texts(core, coordinator.id))

    # 绝不唤醒 Coordinator
    assert coordinator.id not in scheduled_sessions


@pytest.mark.asyncio
async def test_coordinator_notify_is_durable_before_notified_at(tmp_path):
    """Coordinator 静默投递必须先把 message_injected 落盘，再写 notified_at。

    否则进程在 mark_notified 之后、flush 之前死亡：账本不再重投，恢复路径
    也重建不出信箱。
    """
    from cloudra.runtime_v2.persistence import RuntimeStore, restore_core

    store = RuntimeStore(tmp_path / "notify.db")
    core, project, coordinator = await _setup_core()
    core.store = store
    await core.event_writer.flush()

    job_id = _insert_terminal_job(project.id, session_id=coordinator.id)
    broker = ComputeNotifyBroker(core, poll_interval=0.05)
    await broker._poll_project(project.id)

    assert _notified_at(job_id) is not None
    persisted = [row["type"] for row in store.events_after({})]
    assert "agent.message_injected" in persisted

    restored = RuntimeCore(strict_events=True)
    restore_core(restored, store)
    restored_events = restored.event_log.query_session(
        coordinator.id, types={"agent.message_injected"}
    )
    assert any(f"Job {job_id}," in e.data["content"] for e in restored_events)
    assert any(
        f"Job {job_id}," in t for t in _inbox_texts(restored, coordinator.id)
    )


@pytest.mark.asyncio
async def test_unacked_terminal_notice_is_not_duplicated_after_restore(tmp_path, monkeypatch):
    """The durable notice identifies its job when the DB ack died with the broker."""
    from cloudra.runtime_v2.persistence import RuntimeStore, restore_core

    store = RuntimeStore(tmp_path / "notify-restart.db")
    core, project, coordinator = await _setup_core()
    core.store = store
    await core.event_writer.flush()
    job_id = _insert_terminal_job(project.id, session_id=coordinator.id, path="")
    broker = ComputeNotifyBroker(core)

    def failed_mark(_task_id):
        raise OSError("database ack failed")

    with monkeypatch.context() as patcher:
        patcher.setattr(broker, "_mark_notified", failed_mark)
        await broker._poll_project(project.id)

    assert _notified_at(job_id) is None
    assert len(core.event_log.query_session(
        coordinator.id, types={"agent.message_injected"}
    )) == 1

    restored = RuntimeCore(strict_events=True)
    restore_core(restored, store)
    await ComputeNotifyBroker(restored)._poll_project(project.id)

    assert _notified_at(job_id) is not None
    events = restored.event_log.query_session(
        coordinator.id, types={"agent.message_injected"}
    )
    assert len(events) == 1
    assert events[0].data["manifest"] == {
        "kind": "compute_completion", "task_id": job_id,
    }
    assert sum(f"Job {job_id}," in text for text in _inbox_texts(
        restored, coordinator.id
    )) == 1


@pytest.mark.asyncio
async def test_system_compute_notify_does_not_wake_cancelled_subagent():
    """用户取消后，子 agent 的计算终态只驻留信箱，不得 plan_wake 复活。"""
    from cloudra.runtime_v2.schemas import AgentState

    core, project, coordinator = await _setup_core()
    bus = CommandBus(core)
    scheduled_sessions = []

    class FakeRunner:
        def schedule(self, session_id):
            scheduled_sessions.append(session_id)

        async def cancel(self, session_id):
            return None

    core.runner = FakeRunner()
    res = await bus.execute(
        Command(
            type="agent.spawn",
            target={"project_id": project.id},
            payload={"role_id": "small_mol", "parent_session_id": coordinator.id},
        )
    )
    subagent = res.data
    await bus.execute(Command(type="agent.cancel", target={"session_id": subagent.id}))
    assert subagent.state is AgentState.CANCELLED
    scheduled_sessions.clear()

    job_id = _insert_terminal_job(project.id, session_id=subagent.id)
    broker = ComputeNotifyBroker(core, poll_interval=0.05)
    await broker._poll_project(project.id)

    assert subagent.state is AgentState.CANCELLED
    assert subagent.id not in scheduled_sessions
    events = core.event_log.query_session(subagent.id, types={"agent.message_injected"})
    assert any(f"Job {job_id}," in e.data["content"] for e in events)


@pytest.mark.asyncio
@pytest.mark.parametrize("recover_acknowledged", [False, True])
@pytest.mark.parametrize("ordinary_result", [False, True])
async def test_pipeline_intermediate_job_advances_without_agent_message(tmp_path, monkeypatch, recover_acknowledged, ordinary_result):
    from cloudra.services.compute_admission import AdmissionOutcome
    from cloudra.services.ts_pipeline_store import bind_stage_job, create_process
    from cloudra.tools.core.ts_process import TsJobStep, TsProcessRecord, save_record
    core, project, coordinator = await _setup_core()
    project.workspace_dir = str(tmp_path)
    child = (await CommandBus(core).execute(Command(
        type="agent.spawn", target={"project_id": project.id},
        payload={"role_id": "small_mol", "parent_session_id": coordinator.id},
    ))).data
    await core.agent_host.start_run(child)
    await core.agent_host.finish_run(child, outcome="succeeded")
    if ordinary_result:
        # This notice precedes a TS intermediate result suppressed by the driver.
        ordinary_job = await asyncio.to_thread(
            _insert_terminal_job, project.id, session_id=child.id, path="",
        )
    project.settings.method_policy = __import__('cloudra.runtime_v2.schemas',fromlist=['MethodPolicy']).MethodPolicy(allowed_methods=['b3lyp/def2svp'])
    db = await asyncio.to_thread(ComputeDB().init)
    from tests.ts_fixtures import calculation_input
    declaration = calculation_input(reactant_smiles='CC',product_smiles='CC',method='b3lyp/def2svp')
    process = await asyncio.to_thread(create_process, db, request_key='notify-ts', payload=dict(
        project_id=project.id,owner_id=child.id,workspace_dir=str(tmp_path),input=declaration.model_dump(mode="json")))
    await asyncio.to_thread((tmp_path/'ts.inp').write_text,'synthetic engine input')
    job = await asyncio.to_thread(bind_stage_job, db, process_id=process['process_id'],declaration_revision=1,
        stage_key='ts_opt',attempt=1,job_payload=dict(conversation_id=project.id,session_id=child.id,
        path=str(tmp_path/'ts.inp'),state='ready',jobtype='orca',node_id='fixture'))
    record = TsProcessRecord(run_id='notify',run_dir=str(tmp_path/'ts'/'notify'),workspace_dir=str(tmp_path),
        owner_conversation_id=project.id,owner_session_id=child.id,pipeline_id=process['process_id'],
        input=declaration,stage='refine',waiting_for=f'job:{job}',job_steps=[TsJobStep(purpose='ts_opt',job_id=job)])
    await asyncio.to_thread(Path(record.run_dir).mkdir, parents=True)
    await asyncio.to_thread(save_record, record)
    def complete():
        with db.connect() as con:
            con.execute("UPDATE compute_jobs SET state='done' WHERE id=?",(job,))
    await asyncio.to_thread(complete)
    def writer(record, directory):
        from pathlib import Path
        path=Path(directory)/'frequency.inp'
        path.write_text('! Freq B3LYP def2SVP\n* xyz 0 1\nO 0 0 0\n*\n')
        return '',str(path)
    monkeypatch.setattr('cloudra.tools.core.ts_process._write_frequency_input',writer)
    monkeypatch.setattr('cloudra.services.compute_admission.admit_job',lambda **_: AdmissionOutcome(ok=True,node_id='fixture',scheduler='local'))
    broker=ComputeNotifyBroker(core)
    if recover_acknowledged:
        await asyncio.to_thread(broker._mark_notified,job)
        await broker._poll_all()
    else:
        await broker._poll_project(project.id)
    messages = _inbox_texts(core, child.id)
    assert len(messages) == int(ordinary_result)
    assert child.state.value == ("running" if ordinary_result else "succeeded")
    assert _inbox_texts(core, coordinator.id) == []
    if ordinary_result:
        assert await asyncio.to_thread(_notified_at, ordinary_job) is not None
    assert await asyncio.to_thread(_notified_at,job) is not None
    def jobs():
        with db.connect() as con:
            return con.execute('SELECT COUNT(*) FROM compute_jobs').fetchone()[0]
    assert await asyncio.to_thread(jobs) == 2 + int(ordinary_result)


@pytest.mark.asyncio
@pytest.mark.parametrize("outcome,verified", [("verified", True), ("candidate_only", False), ("blocked", None)])
@pytest.mark.parametrize("model_calls", [0, 2])
async def test_ts_outcome_wakes_owner_while_high_throughput_jobs_run(tmp_path, outcome, verified, model_calls):
    from cloudra.runtime_v2.persistence import RuntimeStore
    from cloudra.services.ts_pipeline_store import bind_stage_job, create_process, save_process_record
    from cloudra.tools.core.ts_process import TsJobStep, _block, _terminal
    from tests.test_ts_stage_inputs import record_fixture

    core, project, coordinator = await _setup_core()
    store = await asyncio.to_thread(RuntimeStore, tmp_path / "ts-notice.db")
    core.store = store
    await core.event_writer.flush()
    child = (await CommandBus(core).execute(Command(
        type="agent.spawn", target={"project_id": project.id},
        payload={"role_id": "small_mol", "parent_session_id": coordinator.id},
    ))).data
    await core.agent_host.start_run(child)
    await core.agent_host.finish_run(child, outcome="succeeded")
    await asyncio.to_thread(_insert_terminal_job, project.id, session_id=child.id, state="running", path="")

    def completed_pipeline():
        from cloudra.services.exploration_budget_store import (
            CostEstimate,
            ExplorationBudget,
            configure_budget,
            reserve_actions,
        )

        db = ComputeDB().init()
        record = record_fixture(tmp_path, owner_conversation_id=project.id, owner_session_id=child.id)
        process = create_process(db, request_key="verdict-notice", payload=dict(project_id=project.id,
            owner_id=child.id, workspace_dir=str(tmp_path), input=record.input.model_dump(mode="json")))
        configure_budget(db, process_id=process["process_id"], project_id=project.id,
            owner_id=child.id, budget=ExplorationBudget(source="explicit_user", max_compute_actions=2, max_model_calls=4))
        if model_calls:
            reserve_actions(db, process_id=process["process_id"], decision_id="fixture-model-usage", estimates=[
                CostEstimate(action_key=f"model:{i}", action_kind="model", source="fixture")
                for i in range(model_calls)])
        source = tmp_path / "frequency.inp"
        source.write_text("Recorded native input")
        job = bind_stage_job(db, process_id=process["process_id"], declaration_revision=1,
            stage_key="product_frequency", attempt=1, job_payload=dict(conversation_id=project.id,
            session_id=child.id, path=str(source), state="ready", jobtype="orca", node_id="fixture"))
        record.pipeline_id = process["process_id"]
        record.job_steps = [TsJobStep(purpose="product_frequency", job_id=job, state="done", input_path=str(source))]
        if outcome == "blocked":
            _block(record, "refine", "wrong_mode", "Recorded endpoint direction judgement", needs=["verification.frequency"])
        else:
            _terminal(record, "verdict", outcome, "Recorded endpoint direction judgement")
        save_process_record(db, process_id=process["process_id"], record=record.model_dump(mode="json"))
        with db.connect() as con:
            con.execute("UPDATE compute_jobs SET state='done' WHERE id=?", (job,))
        return job
    job = await asyncio.to_thread(completed_pipeline)
    broker = ComputeNotifyBroker(core)
    await broker._poll_project(project.id)
    messages = _inbox_texts(core, child.id)
    assert child.state.value == "running"
    assert _inbox_texts(core, coordinator.id) == []
    assert len(messages) == 1
    content = messages[0]
    assert "TS state:" not in content
    if outcome != "blocked":
        assert f"outcome={outcome}" in content
    else:
        assert "state=done" in content and "outcome=blocked" not in content
    assert f"verified={str(verified is True).lower()}" in content
    assert content.count("Recorded endpoint direction judgement") == 1
    assert "NEXT:" in content
    if outcome != "verified":
        assert "ts_inspect" in content
    assert await asyncio.to_thread(_notified_at, job) is not None
    assert await asyncio.to_thread(broker._pending_terminal_jobs, project.id) == []
    notices = core.event_log.query_session(child.id, types={"agent.message_injected"})
    assert [event.data["manifest"]["task_id"] for event in notices] == [job]
    persisted = await asyncio.to_thread(store.events_after, {})
    assert any(row["event_id"] == notices[0].event_id for row in persisted)
    await broker._poll_project(project.id)
    assert len(core.event_log.query_session(child.id, types={"agent.message_injected"})) == 1
    reflections = [event for event in core.event_log.query_session(child.id, types={"context.pin_set"})
                   if event.data["key"].startswith("guidance-scientific-reflection:")]
    assert len(reflections) == int(outcome != "verified")
    if reflections:
        assert str(tmp_path) in reflections[0].data["content"]
        persisted = await asyncio.to_thread(store.events_after, {})
        pin_index = next(index for index, row in enumerate(persisted)
                         if row["type"] == "context.pin_set" and row["session_id"] == child.id)
        message_index = next(index for index, row in enumerate(persisted)
                             if row["type"] == "agent.message_injected" and row["session_id"] == child.id)
        assert pin_index < message_index
        await broker._poll_project(project.id)
        assert len(core.event_log.query_session(child.id, types={"context.pin_set"})) == 1
    assert not core.event_log.query_session(coordinator.id, types={"context.pin_set"})


@pytest.mark.asyncio
@pytest.mark.parametrize("restore", [False, True])
async def test_consumed_unacked_notice_reuses_indexed_receipt_without_history_scan(tmp_path, monkeypatch, restore):
    from cloudra.runtime_v2.effects import EventDraft
    from cloudra.runtime_v2.persistence import RuntimeStore, restore_core

    core, project, coordinator = await _setup_core()
    core.store = RuntimeStore(tmp_path / "indexed-notice.db")
    await core.event_writer.flush()
    job_id = await asyncio.to_thread(_insert_terminal_job, project.id, session_id=coordinator.id, path="")
    broker = ComputeNotifyBroker(core)

    def failed_ack(_job_id):
        raise OSError("ack interrupted after delivery")

    with monkeypatch.context() as patcher:
        patcher.setattr(broker, "_mark_notified", failed_ack)
        await broker._poll_project(project.id)
    notice = core.event_log.query_session(coordinator.id, types={"agent.message_injected"})[-1]
    await core.event_writer.commit(EventDraft(
        "context.appended", stream="agent", project_id=project.id, session_id=coordinator.id,
        data={"messages": [{"role": "user", "message_id": notice.data["message_id"], "content": notice.data["content"]}]},
    ))
    assert core.mailbox.unread() == []
    if restore:
        restored = RuntimeCore(strict_events=True)
        restore_core(restored, core.store)
        core = restored

    def reject_scan(*args, **kwargs):
        raise AssertionError("compute receipt lookup must not replay event history")

    monkeypatch.setattr(core.event_log, "iter_events", reject_scan)
    await ComputeNotifyBroker(core)._poll_project(project.id)
    assert await asyncio.to_thread(_notified_at, job_id) is not None
    notices = core.event_log.query_session(coordinator.id, types={"agent.message_injected"})
    assert len(notices) == 1


def test_compute_delivery_lookup_is_scoped_to_project_and_manifest(tmp_path):
    from cloudra.runtime_v2.events import EventLog
    from cloudra.runtime_v2.persistence import RuntimeStore

    log = EventLog(strict=True)
    store = RuntimeStore(tmp_path / "receipt-scope.db")
    assert store.compute_delivery_target("p", 7) is None
    for project, target, kind, task in [
        ("p", "first", "compute_completion", 7),
        ("p", "second", "compute_completion", 7),
        ("other", "foreign", "compute_completion", 7),
        ("p", "other-job", "compute_completion", 8),
        ("p", "other-kind", "child_completion", 7),
        ("p", "string-id", "compute_completion", "7"),
        ("p", None, "compute_completion", 7),
    ]:
        store.append_event(log.append(
            "agent.message_injected", stream="project", project_id=project, session_id=target,
            data={"manifest": {"kind": kind, "task_id": task}},
        ))
    assert store.compute_delivery_target("p", 7) == "second"
    assert store.compute_delivery_target("other", 7) == "foreign"


@pytest.mark.asyncio
async def test_deleted_project_ack_uses_existing_tombstone_projection(monkeypatch):
    from cloudra.runtime_v2.apply import apply_event

    core, project, coordinator = await _setup_core()
    job = await asyncio.to_thread(_insert_terminal_job, project.id, session_id=coordinator.id, path="")
    deleted = core.event_log.append("project.deleted", stream="project", project_id=project.id)
    apply_event(core, deleted)
    assert project.id in core.deleted_project_ids

    def reject_scan(*args, **kwargs):
        raise AssertionError("deleted projects are already projected; no history replay is needed")

    monkeypatch.setattr(core.event_log, "iter_events", reject_scan)
    await ComputeNotifyBroker(core)._poll_all()
    assert await asyncio.to_thread(_notified_at, job) is not None
