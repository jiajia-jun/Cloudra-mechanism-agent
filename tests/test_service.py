import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from cloudra.service import CloudraService, SessionRunner, validate_conversation_id


def test_validate_conversation_id_rejects_path_traversal():
    with pytest.raises(ValueError):
        validate_conversation_id("../../outside")


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
        async def run_task(self, query, conversation_id, session_id=None):
            return "saved"

    runner = SessionRunner(Service())
    record = runner.submit("hello", conversation.id)
    await asyncio.sleep(0)
    await asyncio.sleep(0)

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
        async def run_task(self, query, conversation_id, session_id=None):
            raise RuntimeError("boom")

    runner = SessionRunner(Service())
    record = runner.submit("hello", conversation.id)
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    saved = runner.get(conversation.id, record.session_id)
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
