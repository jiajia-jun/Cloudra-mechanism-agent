"""用户唤醒沉睡子 Agent：completed/waiting 可续跑 follower，不误开 Coordinator。"""

from __future__ import annotations

import asyncio

import pytest

from cloudra.infra import events
from cloudra.infra.config import get_config, reload_config
from cloudra.persistence.database import ConversationDB
from cloudra.services import session_store
from cloudra.services.service import CloudraService


@pytest.fixture
def isolated_service(tmp_path, monkeypatch):
    import os
    from pathlib import Path

    data_dir = tmp_path / "data"
    runtime_dir = Path(f"/tmp/crfw{os.getpid()}")
    runtime_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("CLOUDRA_DATA_DIR", str(data_dir))
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(runtime_dir))
    reload_config()
    get_config().data_dir = data_dir
    service = CloudraService()
    yield service
    events.shutdown_all_listeners()


@pytest.mark.asyncio
async def test_message_to_completed_follower_resumes_same_session(
    isolated_service, monkeypatch
):
    conversation_id = "conv_follower_wake"
    old_session_id = "a-4_task9"
    db = ConversationDB(conversation_id).init()
    session_store.create_session_record(
        db,
        session_id=old_session_id,
        agent_id="a-4",
        agent_type="follower",
        parent_session_id="a-0_parent",
        query="optimize reactant",
        created_at="2026-08-10T00:00:00+00:00",
        orchestration_mode="dag_record",
    )
    session_store.finalize_session(
        db,
        old_session_id,
        "completed",
        result="旧结论",
    )

    resumed = []

    async def fake_resume(prepared):
        resumed.append(prepared)
        session_store.update_session_fields(
            db, old_session_id, {"state": "running"}
        )
        return isolated_service.session_runner.get(conversation_id, old_session_id)

    monkeypatch.setattr(
        isolated_service, "_resume_follower_session", fake_resume
    )

    command, record = await isolated_service.append_session_message_command(
        command_id="cmd_follower_wake_12345678",
        conversation_id=conversation_id,
        session_id=old_session_id,
        content="改用 B3LYP 再算一次",
    )

    assert command.state == "applied"
    assert record.session_id == old_session_id
    assert record.agent_id == "a-4"
    assert len(resumed) == 1
    assert resumed[0].content == "改用 B3LYP 再算一次"
    assert resumed[0].agent_id == "a-4"
    assert command.result == {
        "session_id": old_session_id,
        "resumed_from": old_session_id,
    }


@pytest.mark.asyncio
async def test_message_to_killed_follower_resumes_same_session(
    isolated_service, monkeypatch
):
    """killed/cancelled/failed 也可唤醒——用户要求任意 agent 可重新唤起。"""
    conversation_id = "conv_follower_killed"
    session_id = "a-3_task2"
    db = ConversationDB(conversation_id).init()
    session_store.create_session_record(
        db,
        session_id=session_id,
        agent_id="a-3",
        agent_type="follower",
        parent_session_id="a-0_parent",
        query="lit review",
        created_at="2026-08-10T00:00:00+00:00",
    )
    session_store.finalize_session(db, session_id, "killed", result="停")

    resumed = []

    async def fake_resume(prepared):
        resumed.append(prepared)
        session_store.update_session_fields(
            db, session_id, {"state": "running"}
        )
        return isolated_service.session_runner.get(conversation_id, session_id)

    monkeypatch.setattr(
        isolated_service, "_resume_follower_session", fake_resume
    )

    command, record = await isolated_service.append_session_message_command(
        command_id="cmd_follower_killed_12345678",
        conversation_id=conversation_id,
        session_id=session_id,
        content="继续",
    )

    assert command.state == "applied"
    assert record.session_id == session_id
    assert len(resumed) == 1
    assert resumed[0].content == "继续"


@pytest.mark.asyncio
async def test_message_to_cancelled_follower_resumes(
    isolated_service, monkeypatch
):
    conversation_id = "conv_follower_cancel"
    session_id = "a-3_task2"
    db = ConversationDB(conversation_id).init()
    session_store.create_session_record(
        db,
        session_id=session_id,
        agent_id="a-3",
        agent_type="follower",
        parent_session_id="a-0_parent",
        query="lit review",
        created_at="2026-08-10T00:00:00+00:00",
    )
    session_store.finalize_session(db, session_id, "cancelled", result="停")

    resumed = []

    async def fake_resume(prepared):
        resumed.append(prepared)
        session_store.update_session_fields(
            db, session_id, {"state": "running"}
        )
        return isolated_service.session_runner.get(conversation_id, session_id)

    monkeypatch.setattr(
        isolated_service, "_resume_follower_session", fake_resume
    )

    command, record = await isolated_service.append_session_message_command(
        command_id="cmd_follower_cancel_12345678",
        conversation_id=conversation_id,
        session_id=session_id,
        content="继续",
    )
    assert command.state == "applied"
    assert record.session_id == session_id
    assert len(resumed) == 1


@pytest.mark.asyncio
async def test_resume_follower_session_schedules_executor(
    isolated_service, monkeypatch
):
    """真实 _resume_follower_session：复用 session_id 建 subagent_request 并调度。"""
    conversation_id = "conv_follower_exec"
    session_id = "a-1_task3"
    db = ConversationDB(conversation_id).init()
    session_store.create_session_record(
        db,
        session_id=session_id,
        agent_id="a-1",
        agent_type="follower",
        parent_session_id="a-0_root",
        query="explore",
        created_at="2026-08-10T00:00:00+00:00",
        orchestration_mode="standard",
    )
    session_store.finalize_session(db, session_id, "completed", result="done")

    from cloudra.services.service import PreparedAppend

    prepared = PreparedAppend(
        conversation_id=conversation_id,
        session_id=session_id,
        agent_id="a-1",
        command_id="cmd_exec_wake_12345678",
        mode="resume",
        content="再看一下 src/",
        working_directory="/work",
        node_id=None,
        workspace_id=None,
        orchestration_mode="standard",
        orchestration_config="{}",
        agent_type="follower",
        parent_session_id="a-0_root",
    )

    scheduled = []

    async def fake_run(task_id, db_path, sid):
        scheduled.append((task_id, sid))

    monkeypatch.setattr(
        "cloudra.tools.Managetool._subagent_dispatch.run_subagent_in_process",
        fake_run,
    )

    record = await isolated_service._resume_follower_session(prepared)
    await asyncio.sleep(0.05)

    assert record.session_id == session_id
    assert scheduled and scheduled[0][1] == session_id
    with db.connect() as con:
        row = con.execute(
            "SELECT id, session_id, state FROM subagent_requests WHERE session_id=?",
            (session_id,),
        ).fetchone()
    assert row is not None
    assert row[1] == session_id
