import asyncio

import pytest

from cloudra import control_store, events, session_store
from cloudra.config import get_config, reload_config
from cloudra.database import ConversationDB
from cloudra.interactions import wait_for_user_response
from cloudra.service import CloudraService


@pytest.fixture
def isolated_service(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    monkeypatch.setenv("CLOUDRA_DATA_DIR", str(data_dir))
    reload_config()
    get_config().data_dir = data_dir
    service = CloudraService()
    yield service
    events.shutdown_all_listeners()


def test_command_store_replay_and_key_reuse_conflict(tmp_path):
    db = ConversationDB("conv_command", data_dir=tmp_path).init()
    command, created = control_store.receive_command(
        db,
        command_id="cmd_replay_12345678",
        conversation_id="conv_command",
        session_id="session_1",
        command_type="session.message.append",
        payload={"content": "一次"},
    )
    replay, replay_created = control_store.receive_command(
        db,
        command_id="cmd_replay_12345678",
        conversation_id="conv_command",
        session_id="session_1",
        command_type="session.message.append",
        payload={"content": "一次"},
    )

    assert created is True
    assert replay_created is False
    assert command == replay
    assert control_store.claim_command(db, command.command_id) is True
    assert control_store.claim_command(db, command.command_id) is False
    applied = control_store.finish_command(
        db,
        command.command_id,
        result={"session_id": "session_1"},
    )
    assert applied.state == "applied"

    with pytest.raises(control_store.CommandConflict):
        control_store.receive_command(
            db,
            command_id="cmd_replay_12345678",
            conversation_id="conv_command",
            session_id="session_1",
            command_type="session.message.append",
            payload={"content": "另一条"},
        )


@pytest.mark.asyncio
async def test_supplemental_message_replay_is_injected_once(isolated_service):
    conversation_id = "conv_append"
    session_id = "a-0_run_append"
    db = ConversationDB(conversation_id).init()
    session_store.insert_queued_session(
        db,
        session_id=session_id,
        agent_id="a-0",
        agent_type="coordinator",
        query="初始任务",
    )
    session_store.update_session_fields(db, session_id, {"state": "running"})

    first_command, first_record = (
        await isolated_service.append_session_message_command(
            command_id="cmd_append_12345678",
            conversation_id=conversation_id,
            session_id=session_id,
            content="补充要求",
        )
    )
    replay_command, replay_record = (
        await isolated_service.append_session_message_command(
            command_id="cmd_append_12345678",
            conversation_id=conversation_id,
            session_id=session_id,
            content="补充要求",
        )
    )

    assert first_command.state == replay_command.state == "applied"
    assert first_record.session_id == replay_record.session_id == session_id
    with db.connect() as con:
        pending = con.execute(
            """SELECT event_type, content FROM context_events
            WHERE state='pending'"""
        ).fetchall()
        command_count = con.execute(
            "SELECT COUNT(*) FROM client_commands"
        ).fetchone()[0]
        user_events = con.execute(
            """SELECT data FROM session_events
            WHERE session_id=? AND event_type='user_message'""",
            (session_id,),
        ).fetchall()
    assert pending == [
        (
            "user_message",
            "用户从远程控制台补充要求：补充要求",
        )
    ]
    assert command_count == 1
    assert len(user_events) == 1
    assert '"content": "补充要求"' in user_events[0][0]


@pytest.mark.asyncio
async def test_persistent_interaction_answer_wakes_session_once(isolated_service):
    conversation_id = "conv_interaction"
    session_id = "a-0_run_interaction"
    db = ConversationDB(conversation_id).init()
    session_store.insert_queued_session(
        db,
        session_id=session_id,
        agent_id="a-0",
        agent_type="coordinator",
        query="需要澄清",
    )
    session_store.update_session_fields(db, session_id, {"state": "running"})

    waiter = asyncio.create_task(
        isolated_service.session_runner._wait_for_interaction(
            conversation_id,
            session_id,
            "请选择计算方法",
        )
    )
    interactions = []
    for _ in range(100):
        interactions = isolated_service.list_pending_interactions(
            conversation_id,
            session_id=session_id,
        )
        if interactions:
            break
        await asyncio.sleep(0.01)
    assert len(interactions) == 1
    interaction_id = interactions[0]["interaction_id"]
    assert isolated_service.session_runner.get(
        conversation_id,
        session_id,
    ).state == "waiting_for_user"

    command, interaction = (
        await isolated_service.respond_interaction_command(
            command_id="cmd_answer_12345678",
            conversation_id=conversation_id,
            interaction_id=interaction_id,
            response="B3LYP",
        )
    )

    assert await asyncio.wait_for(waiter, timeout=2) == "B3LYP"
    assert command.state == "applied"
    assert interaction.state == "answered"
    assert isolated_service.session_runner.get(
        conversation_id,
        session_id,
    ).state == "running"

    replay_command, replay_interaction = (
        await isolated_service.respond_interaction_command(
            command_id="cmd_answer_12345678",
            conversation_id=conversation_id,
            interaction_id=interaction_id,
            response="B3LYP",
        )
    )
    assert replay_command.state == "applied"
    assert replay_interaction.response == "B3LYP"

    with pytest.raises(control_store.InteractionConflict):
        await isolated_service.respond_interaction_command(
            command_id="cmd_answer_other_12345678",
            conversation_id=conversation_id,
            interaction_id=interaction_id,
            response="HF",
        )


def test_session_create_command_replay_returns_same_session(
    isolated_service,
    monkeypatch,
):
    calls = []

    def fake_submit(
        query,
        conversation_id,
        working_directory=None,
        yolo=False,
        session_id=None,
        node_id=None,
        workspace_id=None,
    ):
        calls.append(session_id)
        db = ConversationDB(conversation_id).init()
        session_store.insert_queued_session(
            db,
            session_id=session_id,
            agent_id="a-0",
            agent_type="coordinator",
            query=query,
        )
        return isolated_service.session_runner.get(conversation_id, session_id)

    monkeypatch.setattr(isolated_service.session_runner, "submit", fake_submit)

    first_command, first_record = isolated_service.submit_session_command(
        command_id="cmd_create_12345678",
        query="执行任务",
        conversation_id="conv_create",
    )
    replay_command, replay_record = isolated_service.submit_session_command(
        command_id="cmd_create_12345678",
        query="执行任务",
        conversation_id="conv_create",
    )

    assert first_command.state == replay_command.state == "applied"
    assert first_record.session_id == replay_record.session_id
    assert calls == [first_record.session_id]

    with pytest.raises(control_store.CommandConflict):
        isolated_service.submit_session_command(
            command_id="cmd_create_12345678",
            query="不同任务",
            conversation_id="conv_create",
        )


@pytest.mark.asyncio
async def test_message_to_terminal_session_wakes_one_new_session(
    isolated_service,
    monkeypatch,
):
    conversation_id = "conv_wake"
    old_session_id = "a-0_run_completed"
    db = ConversationDB(conversation_id).init()
    session_store.insert_queued_session(
        db,
        session_id=old_session_id,
        agent_id="a-0",
        agent_type="coordinator",
        query="旧任务",
        node_id="hpc-login",
        workspace_id="project-a",
        working_directory="/shared/project-a",
    )
    session_store.finalize_session(
        db,
        old_session_id,
        "completed",
        result="旧结果",
    )
    submitted = []

    async def fake_submit(
        query,
        conversation_id,
        working_directory=None,
        yolo=False,
        session_id=None,
        node_id=None,
        workspace_id=None,
    ):
        submitted.append(
            (query, session_id, working_directory, node_id, workspace_id)
        )
        session_store.insert_queued_session(
            db,
            session_id=session_id,
            agent_id="a-0",
            agent_type="coordinator",
            query=query,
            node_id=node_id,
            workspace_id=workspace_id,
            working_directory=working_directory,
        )
        return isolated_service.session_runner.get(conversation_id, session_id)

    monkeypatch.setattr(
        isolated_service.session_runner, "submit_async", fake_submit
    )

    command, record = await isolated_service.append_session_message_command(
        command_id="cmd_wake_12345678",
        conversation_id=conversation_id,
        session_id=old_session_id,
        content="继续检查溶剂效应",
    )
    replay, replay_record = await isolated_service.append_session_message_command(
        command_id="cmd_wake_12345678",
        conversation_id=conversation_id,
        session_id=old_session_id,
        content="继续检查溶剂效应",
    )

    assert command.state == replay.state == "applied"
    assert record.session_id == replay_record.session_id
    assert record.session_id != old_session_id
    assert command.result == {
        "session_id": record.session_id,
        "resumed_from": old_session_id,
    }
    assert submitted == [
        (
            "继续检查溶剂效应",
            record.session_id,
            "/shared/project-a",
            "hpc-login",
            "project-a",
        )
    ]
    assert record.node_id == "hpc-login"
    assert record.workspace_id == "project-a"


@pytest.mark.asyncio
async def test_interaction_timeout_expires_and_restores_running_state(
    isolated_service,
):
    conversation_id = "conv_interaction_timeout"
    session_id = "a-0_run_timeout"
    db = ConversationDB(conversation_id).init()
    session_store.insert_queued_session(
        db,
        session_id=session_id,
        agent_id="a-0",
        agent_type="coordinator",
        query="等待回答",
    )
    session_store.update_session_fields(db, session_id, {"state": "running"})

    with pytest.raises(TimeoutError, match="等待用户回答超时"):
        await wait_for_user_response(
            conversation_id=conversation_id,
            session_id=session_id,
            agent_id="a-0",
            prompt="是否继续？",
            timeout_seconds=0.01,
        )

    assert isolated_service.session_runner.get(
        conversation_id,
        session_id,
    ).state == "running"
    with db.connect() as con:
        interaction_state = con.execute(
            "SELECT state FROM interactions"
        ).fetchone()[0]
        event_types = [
            row[0]
            for row in con.execute(
                "SELECT event_type FROM session_events ORDER BY id"
            ).fetchall()
        ]
    assert interaction_state == "expired"
    assert "interaction_expired" in event_types


@pytest.mark.asyncio
async def test_cancel_command_replay_has_one_audit_record(isolated_service):
    conversation_id = "conv_cancel_command"
    session_id = "a-0_run_cancelled"
    db = ConversationDB(conversation_id).init()
    session_store.insert_queued_session(
        db,
        session_id=session_id,
        agent_id="a-0",
        agent_type="coordinator",
        query="已经完成",
    )
    session_store.finalize_session(db, session_id, "completed", result="done")

    first, first_record = await isolated_service.cancel_session_command(
        command_id="cmd_cancel_12345678",
        conversation_id=conversation_id,
        session_id=session_id,
    )
    replay, replay_record = await isolated_service.cancel_session_command(
        command_id="cmd_cancel_12345678",
        conversation_id=conversation_id,
        session_id=session_id,
    )

    assert first.state == replay.state == "applied"
    assert first_record.state == replay_record.state == "completed"
    with db.connect() as con:
        count = con.execute(
            "SELECT COUNT(*) FROM client_commands"
        ).fetchone()[0]
    assert count == 1


@pytest.mark.asyncio
async def test_approval_decision_command_is_idempotent_and_audited(
    isolated_service,
):
    conversation_id = "conv_remote_approval"
    session_id = "a-0_run_approval"
    db = ConversationDB(conversation_id).init()
    session_store.insert_queued_session(
        db,
        session_id=session_id,
        agent_id="a-0",
        agent_type="coordinator",
        query="危险操作",
    )
    approval_id = session_store.insert_approval(
        db,
        session_id,
        "【动作】: 删除\n【相对路径】: build/",
        "Coordinator",
    )

    pending = isolated_service.list_pending_approvals_for_conversation(
        conversation_id
    )
    first, first_approval = await isolated_service.decide_approval_command(
        command_id="cmd_approval_12345678",
        conversation_id=conversation_id,
        approval_id=approval_id,
        decision="denied",
        denial_reason="路径过宽",
    )
    replay, replay_approval = await isolated_service.decide_approval_command(
        command_id="cmd_approval_12345678",
        conversation_id=conversation_id,
        approval_id=approval_id,
        decision="denied",
        denial_reason="路径过宽",
    )

    assert pending[0]["details"].startswith("【动作】")
    assert first.state == replay.state == "applied"
    assert first_approval["state"] == replay_approval["state"] == "denied"
    assert first_approval["denial_reason"] == "路径过宽"
    assert (
        isolated_service.list_pending_approvals_for_conversation(
            conversation_id
        )
        == []
    )

    with pytest.raises(control_store.CommandConflict):
        await isolated_service.decide_approval_command(
            command_id="cmd_approval_other_12345678",
            conversation_id=conversation_id,
            approval_id=approval_id,
            decision="approved",
        )
    with db.connect() as con:
        events_in_db = [
            row[0]
            for row in con.execute(
                """SELECT event_type FROM session_events
                WHERE event_type LIKE 'approval_%' ORDER BY id"""
            ).fetchall()
        ]
    assert events_in_db == ["approval_pending", "approval_decided"]


@pytest.mark.asyncio
async def test_expired_approval_cannot_be_decided_and_is_persisted(
    isolated_service,
):
    conversation_id = "conv_expired_approval"
    session_id = "a-0_run_expired_approval"
    db = ConversationDB(conversation_id).init()
    session_store.insert_queued_session(
        db,
        session_id=session_id,
        agent_id="a-0",
        agent_type="coordinator",
        query="过期审批",
    )
    approval_id = session_store.insert_approval(
        db,
        session_id,
        "【动作】: 执行危险终端命令",
        "Coordinator",
        tool_name="bashtools",
        normalized_arguments={"command": "rm output.tmp"},
        risk_summary="执行危险终端命令",
    )
    with db.connect() as con:
        con.execute(
            """UPDATE approvals SET expires_at=
            '2000-01-01T00:00:00+00:00' WHERE id=?""",
            (approval_id,),
        )
        con.commit()

    assert (
        isolated_service.list_pending_approvals_for_conversation(
            conversation_id
        )
        == []
    )
    with pytest.raises(control_store.CommandConflict, match="过期"):
        await isolated_service.decide_approval_command(
            command_id="cmd_expired_approval_12345678",
            conversation_id=conversation_id,
            approval_id=approval_id,
            decision="approved",
        )

    with db.connect() as con:
        state = con.execute(
            "SELECT state FROM approvals WHERE id=?",
            (approval_id,),
        ).fetchone()[0]
        events_in_db = [
            row[0]
            for row in con.execute(
                """SELECT event_type FROM session_events
                WHERE event_type LIKE 'approval_%' ORDER BY id"""
            ).fetchall()
        ]
    assert state == "expired"
    assert events_in_db == ["approval_pending", "approval_expired"]
