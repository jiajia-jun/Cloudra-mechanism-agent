"""reAct 消费外部事件：user_message 不得再写成【user_message】系统行。

inject 路径会另建 ContextManager 把 user 行落盘，再 inject_event 唤醒。
活着的 Agent 实例缓存过期时，必须看见那一行并跳过重复写入。
"""

import pytest

from cloudra.persistence.context_manager import ContextManager
from cloudra.persistence.database import ConversationDB


def _make_react(tmp_path, monkeypatch, *, conv_id, agent_id="a-4", session_id="a-4_task1"):
    import os
    from pathlib import Path

    from cloudra.core.agent import Follower
    from cloudra.core.react import reAct

    runtime_dir = Path(f"/tmp/cr{os.getpid()}x")
    runtime_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(runtime_dir))

    db = ConversationDB(conv_id).init()
    monkeypatch.setattr("cloudra.core.react.get_database_path", lambda _cid: db.path)

    agent = Follower(
        id=agent_id,
        name="tester",
        prompt="测试",
        query="原任务",
        conversation_id=conv_id,
        session_id=session_id,
    )
    agent._ensure_context_manager()
    return reAct(agent, session_id=session_id), agent, db.path


@pytest.mark.asyncio
async def test_user_message_already_on_disk_is_not_rewritten_as_system(tmp_path, monkeypatch):
    """另一 CM 已 append 的 user 行：consume 只计消费，不追加【user_message】。"""
    conv_id = "conv-user-inject"
    react, agent, db_path = _make_react(tmp_path, monkeypatch, conv_id=conv_id)
    live = agent.context_manager
    await live.load()  # 驻留过期缓存

    supplement = "用户从远程控制台补充要求：POZ 有虚频，用 chem 工具位移"
    other = ContextManager(
        agent_id="a-4",
        conversation_id=conv_id,
        prompt=None,
        query="",
        session_id="a-4_task1",
    )
    await other.append({"role": "user", "content": supplement})
    await ContextManager.inject_event(
        conversation_id=conv_id,
        agent_id="a-4",
        event_type="user_message",
        content=supplement,
        db_path=db_path,
        session_id="a-4_task1",
    )

    n = await react._consume_external_events()
    assert n > 0

    ctx = await live.load()
    user_hits = [
        m for m in ctx
        if m.get("role") == "user" and supplement in str(m.get("content", ""))
    ]
    system_hits = [
        m for m in ctx
        if m.get("role") == "system" and "【user_message】" in str(m.get("content", ""))
    ]
    assert len(user_hits) == 1
    assert system_hits == []


@pytest.mark.asyncio
async def test_user_message_event_lands_as_user_role(tmp_path, monkeypatch):
    """仅 inject_event、上下文里还没有该正文时，以 role=user 写入，不用系统包装。"""
    conv_id = "conv-user-only-event"
    react, agent, db_path = _make_react(tmp_path, monkeypatch, conv_id=conv_id)
    await agent.context_manager.load()

    content = "用户从远程控制台补充要求：先回答我虚频怎么处理"
    await ContextManager.inject_event(
        conversation_id=conv_id,
        agent_id="a-4",
        event_type="user_message",
        content=content,
        db_path=db_path,
        session_id="a-4_task1",
    )

    n = await react._consume_external_events()
    assert n > 0

    ctx = await agent.context_manager.load()
    user_hits = [
        m for m in ctx
        if m.get("role") == "user" and content in str(m.get("content", ""))
    ]
    system_hits = [
        m for m in ctx
        if m.get("role") == "system" and "【user_message】" in str(m.get("content", ""))
    ]
    assert len(user_hits) == 1
    assert system_hits == []


@pytest.mark.asyncio
async def test_non_user_events_still_use_system_wrapper(tmp_path, monkeypatch):
    conv_id = "conv-subagent-event"
    react, agent, db_path = _make_react(tmp_path, monkeypatch, conv_id=conv_id)
    await agent.context_manager.load()

    await ContextManager.inject_event(
        conversation_id=conv_id,
        agent_id="a-4",
        event_type="subagent",
        content="子任务完成",
        db_path=db_path,
        session_id="a-4_task1",
    )

    n = await react._consume_external_events()
    assert n > 0
    ctx = await agent.context_manager.load()
    assert any(
        m.get("role") == "system" and str(m.get("content", "")).startswith("[subagent]")
        for m in ctx
    )
