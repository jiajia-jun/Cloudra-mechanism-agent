import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from cloudra.service import SessionRunner, validate_conversation_id


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
