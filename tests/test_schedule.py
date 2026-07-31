import asyncio
import sqlite3

import pytest

from cloudra.agent import Coordinator
from cloudra.context_manager import ContextManager
from cloudra.database import ConversationDB
from cloudra.runtime.runner import _wait_for_background_tasks
from cloudra.session_class import Session
from cloudra.tools.Managetool.schedule import Schedule, ScheduleInput


@pytest.fixture
def schedule_db(tmp_path, monkeypatch):
    from cloudra import events
    from cloudra.config import get_config, reload_config

    events.shutdown_all_listeners()
    data_dir = tmp_path / "data"
    monkeypatch.setenv("CLOUDRA_DATA_DIR", str(data_dir))
    reload_config()
    get_config().data_dir = data_dir
    get_config()._ensure_dirs()
    db = ConversationDB("schedule_test").init()
    yield db
    events.shutdown_all_listeners()


def test_coordinator_can_list_and_cancel_schedules():
    agent = Coordinator(query="monitor", conversation_id="schedule_test")
    action_schema = ScheduleInput.model_json_schema()["properties"]["action"]

    assert agent.check_permission(Schedule(subagent=agent))
    assert set(action_schema["enum"]) == {"create", "list", "cancel"}


@pytest.mark.asyncio
async def test_schedule_create_and_fire_wakes_waiter(schedule_db):
    agent = Coordinator(query="monitor", conversation_id="schedule_test")
    tool = Schedule(subagent=agent)
    result = await tool.tool_call(
        ScheduleInput(delay_seconds=0.05, message="检查后台计算"),
        Session(id="schedule-session", path=str(schedule_db.path) + ".session.json"),
    )
    assert result.is_success

    await asyncio.wait_for(
        _wait_for_background_tasks(schedule_db.path, "schedule_test"),
        timeout=2,
    )

    with sqlite3.connect(schedule_db.path) as con:
        state = con.execute(
            "SELECT state FROM scheduled_reminders WHERE id=?", (result.schedule_id,)
        ).fetchone()[0]
        event = con.execute(
            "SELECT event_type, content FROM context_events WHERE conversation_id=?",
            ("schedule_test",),
        ).fetchone()
    assert state == "fired"
    assert event == ("scheduled_reminder", f"[提醒 #{result.schedule_id}] 检查后台计算")


@pytest.mark.asyncio
async def test_schedule_cancel_does_not_keep_task_alive(schedule_db):
    agent = Coordinator(query="monitor", conversation_id="schedule_test")
    tool = Schedule(subagent=agent)
    created = await tool.tool_call(
        ScheduleInput(delay_seconds=3600, message="稍后检查"),
        Session(id="schedule-session", path=str(schedule_db.path) + ".session.json"),
    )
    cancelled = await tool.tool_call(
        ScheduleInput(action="cancel", schedule_id=created.schedule_id),
        Session(id="schedule-session", path=str(schedule_db.path) + ".session.json"),
    )
    assert cancelled.is_success
    await asyncio.wait_for(
        _wait_for_background_tasks(schedule_db.path, "schedule_test"),
        timeout=0.5,
    )


@pytest.mark.asyncio
async def test_coordinator_prompt_includes_pending_schedule_and_cancel_guidance(schedule_db):
    agent = Coordinator(query="monitor", conversation_id="schedule_test")
    tool = Schedule(subagent=agent)
    created = await tool.tool_call(
        ScheduleInput(delay_seconds=3600, message="检查后台计算是否结束"),
        Session(id="schedule-session", path=str(schedule_db.path) + ".session.json"),
    )

    messages = await agent._build_messages()
    schedule_snapshot = next(
        message["content"]
        for message in messages
        if message["role"] == "system" and "【当前待触发 schedule】" in message["content"]
    )

    assert f"schedule_id={created.schedule_id}" in schedule_snapshot
    assert "检查后台计算是否结束" in schedule_snapshot
    assert "schedule(action='cancel', schedule_id=...)" in schedule_snapshot


@pytest.mark.asyncio
async def test_cancelled_schedule_is_removed_from_coordinator_prompt(schedule_db):
    agent = Coordinator(query="monitor", conversation_id="schedule_test")
    tool = Schedule(subagent=agent)
    session = Session(id="schedule-session", path=str(schedule_db.path) + ".session.json")
    created = await tool.tool_call(
        ScheduleInput(delay_seconds=3600, message="这条提醒稍后会被替代"),
        session,
    )
    cancelled = await tool.tool_call(
        ScheduleInput(action="cancel", schedule_id=created.schedule_id),
        session,
    )

    assert cancelled.is_success
    assert "当前待触发 schedule" not in agent._build_schedule_status_snapshot()


@pytest.mark.asyncio
async def test_user_event_wakes_waiter_without_cancelling_schedule(schedule_db):
    agent = Coordinator(query="monitor", conversation_id="schedule_test")
    created = await Schedule(subagent=agent).tool_call(
        ScheduleInput(delay_seconds=3600, message="稍后检查"),
        Session(id="schedule-session", path=str(schedule_db.path) + ".session.json"),
    )

    waiter = asyncio.create_task(
        _wait_for_background_tasks(schedule_db.path, "schedule_test")
    )
    await asyncio.sleep(0.05)
    await ContextManager.inject_event(
        "schedule_test", "a-0", "user", "先回答我现在的问题", db_path=schedule_db.path
    )
    await asyncio.wait_for(waiter, timeout=1)

    with sqlite3.connect(schedule_db.path) as con:
        state = con.execute(
            "SELECT state FROM scheduled_reminders WHERE id=?", (created.schedule_id,)
        ).fetchone()[0]
    assert state == "pending"


@pytest.mark.asyncio
async def test_tui_watcher_fires_schedule_after_wait_is_cancelled(
    schedule_db, monkeypatch
):
    from cloudra.tui.legacy_app import CloudraTUI

    agent = Coordinator(query="monitor", conversation_id="schedule_test")
    created = await Schedule(subagent=agent).tool_call(
        ScheduleInput(delay_seconds=0.1, message="继续检查"),
        Session(id="schedule-session", path=str(schedule_db.path) + ".session.json"),
    )

    tui = CloudraTUI()
    tui.conversation_id = "schedule_test"
    tui.phase = "waiting"
    waiting_task = asyncio.create_task(asyncio.sleep(3600))
    tui._running_task = waiting_task
    started = asyncio.Event()

    def fake_start(query):
        assert query == "处理刚刚到期的定时提醒。"
        started.set()

    monkeypatch.setattr(tui, "_start_task", fake_start)
    watcher = asyncio.create_task(tui._watch_schedules("schedule_test"))
    try:
        assert tui.request_cancel() is True
        with pytest.raises(asyncio.CancelledError):
            await waiting_task
        await asyncio.wait_for(started.wait(), timeout=2)
    finally:
        watcher.cancel()
        with pytest.raises(asyncio.CancelledError):
            await watcher

    with sqlite3.connect(schedule_db.path) as con:
        state = con.execute(
            "SELECT state FROM scheduled_reminders WHERE id=?", (created.schedule_id,)
        ).fetchone()[0]
    assert state == "fired"
