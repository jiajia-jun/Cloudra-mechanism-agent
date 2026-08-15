import asyncio
import sqlite3

import pytest

from cloudra.base.session_class import Session
from cloudra.core.agent import Coordinator
from cloudra.persistence.context_manager import ContextManager
from cloudra.persistence.database import ConversationDB
from cloudra.runtime.runner import _wait_for_background_tasks
from cloudra.tools.Managetool.schedule import Schedule, ScheduleInput


@pytest.fixture
def schedule_db(tmp_path, monkeypatch):
    from cloudra.infra import events
    from cloudra.infra.config import get_config, reload_config

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


def test_schedule_visible_to_all_subagents():
    """schedule 是全体 Agent 的时间通道：只读的 explorer 与计算类子 Agent 都应可用。"""
    from cloudra.core.agent import Follower
    from cloudra.subagents.explorer import explorer

    for agent in (
        explorer(query="q", conversation_id="schedule_test"),
        Follower(id="a-4", name="small_mol", prompt="p", query="q", conversation_id="schedule_test"),
    ):
        assert agent.check_permission(Schedule(subagent=agent)), agent.name
        names = {t.tool_name for t in agent.get_available_tools()}
        assert "schedule" in names


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
    event_type, event_content = event
    assert event_type == "scheduled_reminder"
    assert event_content.startswith(f"[Reminder #{result.schedule_id}] 检查后台计算")
    # 唤醒事件须携带自提示引导：提醒不是新任务、无事可做就 stop
    assert "timed reminder you set for yourself" in event_content
    assert "stop" in event_content


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
        if message["role"] == "system" and "[Pending schedules]" in message["content"]
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
