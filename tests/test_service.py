import asyncio
import sqlite3
import time
from datetime import datetime, timedelta, timezone

import pytest

from cloudra.service import CloudraService, SessionRunner, validate_conversation_id


async def _wait_terminal_state(runner, conversation_id, session_id, timeout=5.0):
    """等待 _execute 协程落终态（DB 写已移入线程，不能假设固定 sleep 次数）。"""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        record = runner.get(conversation_id, session_id)
        if record is not None and record.state not in {"queued", "running"}:
            return record
        await asyncio.sleep(0.01)
    return runner.get(conversation_id, session_id)


def test_validate_conversation_id_rejects_path_traversal():
    with pytest.raises(ValueError):
        validate_conversation_id("../../outside")


def test_session_reads_migrate_legacy_database_before_select(tmp_path, monkeypatch):
    """TUI startup must open pre-route-schema conversations without crashing."""
    from cloudra.config import get_config, reload_config
    from cloudra.database import SCHEMA_VERSION, ConversationDB

    data_dir = tmp_path / "data"
    monkeypatch.setenv("CLOUDRA_DATA_DIR", str(data_dir))
    reload_config()
    get_config().data_dir = data_dir
    db = ConversationDB("conv_legacy_tui").ensure_dir()
    with sqlite3.connect(db.path) as con:
        con.execute(
            "CREATE TABLE session(session_id TEXT PRIMARY KEY, state TEXT, result TEXT)"
        )
        con.execute(
            "CREATE TABLE schema_migrations(version INTEGER PRIMARY KEY, applied_at TEXT)"
        )
        con.execute("INSERT INTO schema_migrations VALUES (6, datetime('now'))")
        con.execute(
            "INSERT INTO session VALUES ('legacy-1', 'completed', 'old result')"
        )
        con.commit()

    runner = SessionRunner(object())
    records = runner.list("conv_legacy_tui")
    assert len(records) == 1
    assert records[0].session_id == "legacy-1"
    assert records[0].result == "old result"
    assert records[0].node_id is None
    assert runner.get("conv_legacy_tui", "legacy-1") == records[0]
    assert runner.events("conv_legacy_tui", "legacy-1") == []
    with sqlite3.connect(db.path) as con:
        columns = {row[1] for row in con.execute("PRAGMA table_info(session)")}
        version = con.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0]
    assert {"node_id", "workspace_id", "working_directory"} <= columns
    assert version == SCHEMA_VERSION


@pytest.mark.asyncio
async def test_session_runner_persists_completed_result(tmp_path, monkeypatch):
    from cloudra.config import get_config, reload_config
    from cloudra.conversation_class import Conversation

    data_dir = tmp_path / "data"
    monkeypatch.setenv("CLOUDRA_DATA_DIR", str(data_dir))
    reload_config()
    get_config().data_dir = data_dir
    get_config()._ensure_dirs()
    conversation = Conversation()

    class Service:
        async def run_task(self, query, conversation_id, session_id=None, **_kwargs):
            return "saved"

    runner = SessionRunner(Service())
    record = runner.submit("hello", conversation.id)
    await _wait_terminal_state(runner, conversation.id, record.session_id)

    reloaded = SessionRunner(Service()).get(conversation.id, record.session_id)
    assert reloaded is not None
    assert reloaded.state == "completed"
    assert reloaded.result == "saved"
    assert reloaded.agent_type == "coordinator"


@pytest.mark.asyncio
async def test_session_runner_tracks_failure(tmp_path, monkeypatch):
    from cloudra.config import get_config, reload_config
    from cloudra.conversation_class import Conversation

    data_dir = tmp_path / "data"
    monkeypatch.setenv("CLOUDRA_DATA_DIR", str(data_dir))
    reload_config()
    get_config().data_dir = data_dir
    get_config()._ensure_dirs()
    conversation = Conversation()

    class Service:
        async def run_task(self, query, conversation_id, session_id=None, **_kwargs):
            raise RuntimeError("boom")

    runner = SessionRunner(Service())
    record = runner.submit("hello", conversation.id)
    saved = await _wait_terminal_state(runner, conversation.id, record.session_id)

    assert saved is not None
    assert saved.state == "failed"
    assert saved.error == "boom"


def test_stale_session_recovery_and_events(tmp_path, monkeypatch):
    from cloudra.config import get_config, reload_config
    from cloudra.conversation_class import Conversation
    from cloudra.database import ConversationDB

    data_dir = tmp_path / "data"
    monkeypatch.setenv("CLOUDRA_DATA_DIR", str(data_dir))
    reload_config()
    get_config().data_dir = data_dir
    get_config()._ensure_dirs()
    conversation = Conversation()
    db = ConversationDB(conversation.id).init()
    stale = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
    with db.connect() as conn:
        conn.execute(
            """INSERT INTO session
            (session_id, agent_id, agent_type, state, heartbeat_at, created_at)
            VALUES ('stale-1', 'a-0', 'coordinator', 'running', ?, ?)""",
            (stale, stale),
        )
        conn.commit()

    class Service:
        async def run_task(self, *args, **kwargs):
            return "unused"

    runner = SessionRunner(Service())
    assert runner.recover_stale_sessions(timeout_seconds=60) == 1
    assert runner.get(conversation.id, "stale-1").state == "interrupted"

    runner._emit(conversation.id, "stale-1", "test", {"value": 1})
    events = runner.events(conversation.id, "stale-1")
    assert events[-1]["event_type"] == "test"
    assert events[-1]["data"] == {"value": 1}


def test_session_runner_list_children(tmp_path, monkeypatch):
    from cloudra.config import get_config, reload_config
    from cloudra.conversation_class import Conversation
    from cloudra.database import ConversationDB

    data_dir = tmp_path / "data"
    monkeypatch.setenv("CLOUDRA_DATA_DIR", str(data_dir))
    reload_config()
    get_config().data_dir = data_dir
    get_config()._ensure_dirs()
    conversation = Conversation()
    db = ConversationDB(conversation.id).init()

    with db.connect() as conn:
        conn.execute(
            """INSERT INTO session
            (session_id, agent_id, agent_type, parent_session_id, query, state, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)""",
            ("parent-1", "a-0", "coordinator", None, "parent", "running", "2024-01-01T00:00:00"),
        )
        conn.execute(
            """INSERT INTO session
            (session_id, agent_id, agent_type, parent_session_id, query, state, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)""",
            ("child-1", "a-1", "explorer", "parent-1", "child1", "running", "2024-01-01T00:01:00"),
        )
        conn.execute(
            """INSERT INTO session
            (session_id, agent_id, agent_type, parent_session_id, query, state, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)""",
            ("child-2", "a-2", "writer", "parent-1", "child2", "queued", "2024-01-01T00:02:00"),
        )
        conn.execute(
            """INSERT INTO session
            (session_id, agent_id, agent_type, parent_session_id, query, state, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)""",
            ("orphan-1", "a-0", "coordinator", None, "orphan", "running", "2024-01-01T00:03:00"),
        )
        conn.commit()

    runner = SessionRunner(CloudraService())
    children = runner.list_children(conversation.id, "parent-1")
    assert [c.session_id for c in children] == ["child-1", "child-2"]
    assert {c.agent_id for c in children} == {"a-1", "a-2"}

    assert runner.list_children(conversation.id, "orphan-1") == []


@pytest.mark.asyncio
async def test_append_session_message_uses_target_agent_id(tmp_path, monkeypatch):
    """向子 Agent Session 追加消息时，inject_event 应使用子 Agent 的 agent_id。"""
    from cloudra.config import get_config, reload_config
    from cloudra.context_manager import ContextManager
    from cloudra.conversation_class import Conversation
    from cloudra.database import ConversationDB

    data_dir = tmp_path / "data"
    monkeypatch.setenv("CLOUDRA_DATA_DIR", str(data_dir))
    reload_config()
    get_config().data_dir = data_dir
    get_config()._ensure_dirs()
    conversation = Conversation()
    db = ConversationDB(conversation.id).init()

    with db.connect() as conn:
        conn.execute(
            """INSERT INTO session
            (session_id, agent_id, agent_type, state, created_at)
            VALUES (?, ?, ?, ?, ?)""",
            ("a-1_task42", "a-1", "explorer", "running", "2024-01-01T00:00:00"),
        )
        conn.commit()

    injected = []

    async def fake_inject(conversation_id, agent_id, event_type, content, db_path=None):
        injected.append((conversation_id, agent_id, event_type, content, db_path))

    monkeypatch.setattr(ContextManager, "inject_event", staticmethod(fake_inject))

    service = CloudraService()
    command, record = await service.append_session_message_command(
        command_id="test-cmd-1",
        conversation_id=conversation.id,
        session_id="a-1_task42",
        content="请在子 Agent 里补充这个",
    )

    assert record.session_id == "a-1_task42"
    assert len(injected) == 1
    _, agent_id, event_type, content, _ = injected[0]
    assert agent_id == "a-1"
    assert event_type == "user_message"
    assert "请在子 Agent 里补充这个" in content



@pytest.mark.asyncio
async def test_submit_session_async_does_not_block_event_loop(tmp_path, monkeypatch):
    """submit_session_async 的同步 DB/控制存储阶段不能阻塞事件循环。"""
    from cloudra.config import get_config, reload_config

    data_dir = tmp_path / "data"
    monkeypatch.setenv("CLOUDRA_DATA_DIR", str(data_dir))
    reload_config()
    get_config().data_dir = data_dir
    get_config()._ensure_dirs()

    service = CloudraService()
    original = service.session_runner._prepare_submission

    def slow_prepare(*args, **kwargs):
        time.sleep(0.15)
        return original(*args, **kwargs)

    monkeypatch.setattr(service.session_runner, "_prepare_submission", slow_prepare)

    progressed = asyncio.Event()
    asyncio.get_running_loop().call_later(0.02, progressed.set)

    _, record = await asyncio.wait_for(
        service.submit_session_async("hello", "conv_async"),
        timeout=1.0,
    )
    await asyncio.wait_for(progressed.wait(), timeout=0.08)
    assert record.session_id.startswith("a-0_run_")


@pytest.mark.asyncio
async def test_append_session_message_async_does_not_block_event_loop(
    tmp_path, monkeypatch
):
    """append_session_message_command 的同步准备阶段不能阻塞事件循环。"""
    from cloudra import session_store
    from cloudra.config import get_config, reload_config
    from cloudra.database import ConversationDB

    data_dir = tmp_path / "data"
    monkeypatch.setenv("CLOUDRA_DATA_DIR", str(data_dir))
    reload_config()
    get_config().data_dir = data_dir
    get_config()._ensure_dirs()

    conversation_id = "conv_append_block"
    session_id = "a-0_run_append_block"
    db = ConversationDB(conversation_id).init()
    session_store.insert_queued_session(
        db,
        session_id=session_id,
        agent_id="a-0",
        agent_type="coordinator",
        query="任务",
    )
    session_store.update_session_fields(db, session_id, {"state": "running"})

    service = CloudraService()
    original = service._prepare_append_message

    def slow_prepare(request):
        time.sleep(0.15)
        return original(request)

    monkeypatch.setattr(service, "_prepare_append_message", slow_prepare)

    progressed = asyncio.Event()
    asyncio.get_running_loop().call_later(0.02, progressed.set)

    command, record = await asyncio.wait_for(
        service.append_session_message_command(
            command_id="cmd_append_block",
            conversation_id=conversation_id,
            session_id=session_id,
            content="补充",
        ),
        timeout=1.0,
    )
    await asyncio.wait_for(progressed.wait(), timeout=0.08)
    assert record.session_id == session_id
    assert command.state == "applied"


@pytest.mark.asyncio
async def test_cancel_session_command_async_does_not_block_event_loop(
    tmp_path, monkeypatch
):
    """cancel_session_command 的同步准备阶段不能阻塞事件循环。"""
    from cloudra import session_store
    from cloudra.config import get_config, reload_config
    from cloudra.database import ConversationDB

    data_dir = tmp_path / "data"
    monkeypatch.setenv("CLOUDRA_DATA_DIR", str(data_dir))
    reload_config()
    get_config().data_dir = data_dir
    get_config()._ensure_dirs()

    conversation_id = "conv_cancel_block"
    session_id = "a-0_run_cancel_block"
    db = ConversationDB(conversation_id).init()
    session_store.insert_queued_session(
        db,
        session_id=session_id,
        agent_id="a-0",
        agent_type="coordinator",
        query="任务",
    )
    session_store.finalize_session(db, session_id, "completed", result="done")

    service = CloudraService()
    original = service._prepare_cancel_command

    def slow_prepare(*args):
        time.sleep(0.15)
        return original(*args)

    monkeypatch.setattr(service, "_prepare_cancel_command", slow_prepare)

    progressed = asyncio.Event()
    asyncio.get_running_loop().call_later(0.02, progressed.set)

    command, record = await asyncio.wait_for(
        service.cancel_session_command(
            command_id="cmd_cancel_block",
            conversation_id=conversation_id,
            session_id=session_id,
        ),
        timeout=1.0,
    )
    await asyncio.wait_for(progressed.wait(), timeout=0.08)
    assert command.state == "applied"
    assert record is not None
    assert record.state == "completed"


@pytest.mark.asyncio
async def test_respond_interaction_command_async_does_not_block_event_loop(
    tmp_path, monkeypatch
):
    """respond_interaction_command 的同步准备阶段不能阻塞事件循环。"""
    from cloudra import control_store, session_store
    from cloudra.config import get_config, reload_config
    from cloudra.database import ConversationDB

    data_dir = tmp_path / "data"
    monkeypatch.setenv("CLOUDRA_DATA_DIR", str(data_dir))
    reload_config()
    get_config().data_dir = data_dir
    get_config()._ensure_dirs()

    conversation_id = "conv_interaction_block"
    session_id = "a-0_run_interaction_block"
    db = ConversationDB(conversation_id).init()
    session_store.insert_queued_session(
        db,
        session_id=session_id,
        agent_id="a-0",
        agent_type="coordinator",
        query="任务",
    )
    session_store.update_session_fields(db, session_id, {"state": "running"})
    interaction = control_store.create_interaction(
        db, session_id=session_id, agent_id="a-0", prompt="请选择"
    )

    service = CloudraService()
    original = service._prepare_respond_interaction

    def slow_prepare(*args):
        time.sleep(0.15)
        return original(*args)

    monkeypatch.setattr(service, "_prepare_respond_interaction", slow_prepare)

    progressed = asyncio.Event()
    asyncio.get_running_loop().call_later(0.02, progressed.set)

    command, latest = await asyncio.wait_for(
        service.respond_interaction_command(
            command_id="cmd_interaction_block",
            conversation_id=conversation_id,
            interaction_id=interaction.interaction_id,
            response="A",
        ),
        timeout=1.0,
    )
    await asyncio.wait_for(progressed.wait(), timeout=0.08)
    assert command.state == "applied"
    assert latest.state == "answered"


@pytest.mark.asyncio
async def test_decide_approval_async_does_not_block_event_loop(tmp_path, monkeypatch):
    """decide_approval 的首段同步 DB 工作不能阻塞事件循环。"""
    from cloudra import session_store
    from cloudra.config import get_config, reload_config
    from cloudra.database import ConversationDB

    data_dir = tmp_path / "data"
    monkeypatch.setenv("CLOUDRA_DATA_DIR", str(data_dir))
    reload_config()
    get_config().data_dir = data_dir
    get_config()._ensure_dirs()

    conversation_id = "conv_approval_block"
    session_id = "a-0_run_approval_block"
    db = ConversationDB(conversation_id).init()
    session_store.insert_queued_session(
        db,
        session_id=session_id,
        agent_id="a-0",
        agent_type="coordinator",
        query="危险操作",
    )
    approval_id = session_store.insert_approval(
        db, session_id, "【动作】: 执行", "Coordinator"
    )

    service = CloudraService()
    original = service._approval_db

    def slow_approval_db(cid):
        time.sleep(0.15)
        return original(cid)

    monkeypatch.setattr(service, "_approval_db", slow_approval_db)

    progressed = asyncio.Event()
    asyncio.get_running_loop().call_later(0.02, progressed.set)

    ok = await asyncio.wait_for(
        service.decide_approval(conversation_id, approval_id, "approved"),
        timeout=1.0,
    )
    await asyncio.wait_for(progressed.wait(), timeout=0.08)
    assert ok is True
