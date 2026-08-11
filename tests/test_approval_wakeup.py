from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from cloudra.base.tools_class import Tool
from cloudra.persistence.database import ConversationDB
from cloudra.services import session_store


@pytest.mark.asyncio
async def test_approval_decision_wakes_waiter_without_poll_delay(tmp_path):
    conversation_id = "approval-wakeup"
    session_id = "a-1_task1"
    db = ConversationDB(conversation_id, data_dir=tmp_path).init()
    session_store.insert_queued_session(
        db,
        session_id=session_id,
        agent_id="a-1",
        agent_type="explorer",
        query="test",
    )
    session_store.transition_session_state(
        db, session_id, expected={"queued"}, target="running"
    )
    tool = Tool(
        subagent=SimpleNamespace(
            conversation_id=conversation_id,
            name="worker",
        )
    )
    waiter = asyncio.create_task(
        tool.request_approval(str(db.path), session_id, "test approval")
    )
    approval_id = None
    for _ in range(100):
        records = await session_store.alist_pending_approval_records(db)
        if records:
            approval_id = records[0]["approval_id"]
            break
        await asyncio.sleep(0.01)
    assert approval_id is not None

    loop = asyncio.get_running_loop()
    started = loop.time()
    assert await session_store.adecide_approval(db, approval_id, "approved")
    decided = loop.time()
    assert await asyncio.wait_for(waiter, timeout=1) == (True, "")
    assert loop.time() - decided < 0.2
    assert loop.time() - started < 1.5
