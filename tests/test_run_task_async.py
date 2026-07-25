"""测试 Coordinator 异步任务等待与事件唤醒机制。"""

import asyncio
import sqlite3
from unittest.mock import patch

import pytest

from cloudra.database import ConversationDB


@pytest.fixture
def isolated_db(tmp_path, monkeypatch):
    """使用临时数据目录隔离数据库和上下文。"""
    data_dir = tmp_path / "cloudra_data"
    data_dir.mkdir()

    from cloudra.config import get_config, reload_config

    monkeypatch.setenv("CLOUDRA_DATA_DIR", str(data_dir))
    reload_config()
    cfg = get_config()
    cfg.data_dir = data_dir
    cfg._ensure_dirs()

    from cloudra.database import ConversationDB

    # 初始化 conversation-scoped 数据库
    ConversationDB("test_conv").init()

    return str(data_dir)


@pytest.mark.asyncio
async def test_wait_for_background_tasks_blocks_on_compute_jobs(isolated_db):
    """_wait_for_background_tasks 应阻塞直到 compute_jobs 中无 running 任务。"""
    from cloudra.database import ConversationDB
    from cloudra.runtime.runner import _wait_for_background_tasks

    db_path = ConversationDB("test_conv").path
    conv_id = "test_conv"

    con = sqlite3.connect(db_path)
    cur = con.cursor()
    cur.execute(
        "INSERT INTO compute_jobs (conversation_id, state, path, jobtype) VALUES (?, ?, ?, ?)",
        (conv_id, "running", "/tmp/test.gjf", "gaussian"),
    )
    con.commit()
    con.close()

    waiter = asyncio.create_task(_wait_for_background_tasks(db_path, conv_id))
    await asyncio.sleep(0.2)
    assert not waiter.done(), "还有 running 计算任务时不应返回"

    con = sqlite3.connect(db_path)
    cur = con.cursor()
    cur.execute(
        "UPDATE compute_jobs SET state = ? WHERE conversation_id = ?",
        ("done", conv_id),
    )
    con.commit()
    con.close()

    await asyncio.wait_for(waiter, timeout=2)


@pytest.mark.asyncio
async def test_wait_for_background_tasks_blocks_on_subagent_requests(isolated_db):
    """_wait_for_background_tasks 应阻塞直到 subagent_requests 中无 running 任务。"""
    from cloudra.runtime.runner import _wait_for_background_tasks

    db_path = ConversationDB("test_conv").path
    conv_id = "test_conv"

    con = sqlite3.connect(db_path)
    cur = con.cursor()
    cur.execute(
        "INSERT INTO subagent_requests (conversation_id, state, input_data) VALUES (?, ?, ?)",
        (conv_id, "running", "{}"),
    )
    con.commit()
    con.close()

    waiter = asyncio.create_task(_wait_for_background_tasks(db_path, conv_id))
    await asyncio.sleep(0.2)
    assert not waiter.done(), "还有 running 子任务时不应返回"

    con = sqlite3.connect(db_path)
    cur = con.cursor()
    cur.execute(
        "UPDATE subagent_requests SET state = ? WHERE conversation_id = ?",
        ("done", conv_id),
    )
    con.commit()
    con.close()

    await asyncio.wait_for(waiter, timeout=2)


@pytest.mark.asyncio
async def test_run_task_async_wakes_up_on_compute_event(isolated_db):
    """Coordinator 第一轮结束后应休息，收到 guard 事件后再次运行。"""
    from cloudra.main import run_task_async

    call_count = 0
    pending_event_rounds = 1  # 第一次等待后有 pending 事件，第二次没有

    async def fake_react_run(self):
        nonlocal call_count
        call_count += 1
        return f"result_{call_count}"

    async def fake_wait(database, conv_id):
        # 后台任务等待函数：立即返回，不阻塞
        pass

    async def fake_has_pending(self):
        nonlocal pending_event_rounds
        if pending_event_rounds > 0:
            pending_event_rounds -= 1
            return True
        return False

    with patch("cloudra.runtime.runner.Coordinator_reAct.run", fake_react_run), \
         patch("cloudra.runtime.runner._wait_for_background_tasks", fake_wait), \
         patch("cloudra.context_manager.ContextManager.has_pending_events", fake_has_pending):
        result = await asyncio.wait_for(
            run_task_async("test query", conv_id="wake_test_conv", verbose=False),
            timeout=5,
        )

    assert call_count == 2, f"Coordinator 应被唤醒两次，实际 {call_count} 次"
    assert result == "result_2"


@pytest.mark.asyncio
async def test_run_task_async_exits_when_no_pending_events(isolated_db):
    """后台任务完成后没有 pending 事件，Coordinator 应直接结束。"""
    from cloudra.main import run_task_async

    call_count = 0

    async def fake_react_run(self):
        nonlocal call_count
        call_count += 1
        return "done result"

    async def fake_wait(database, conv_id):
        pass

    async def fake_has_pending(self):
        return False

    with patch("cloudra.runtime.runner.Coordinator_reAct.run", fake_react_run), \
         patch("cloudra.runtime.runner._wait_for_background_tasks", fake_wait), \
         patch("cloudra.context_manager.ContextManager.has_pending_events", fake_has_pending):
        result = await asyncio.wait_for(
            run_task_async("test query", conv_id="no_event_conv", verbose=False),
            timeout=5,
        )

    assert call_count == 1, f"无事件时不应再次唤醒，实际 {call_count} 次"
    assert result == "done result"
