"""子 Agent executor 的 schedule 复活等待 + guard 终态事件路由测试。

- `_run_with_reminder_waits`：子 Agent 主循环结束后，若还有 pending 提醒，
  挂起等待并在提醒触发后复活续跑；无提醒时立即返回（行为与原来一致）。
- `monitor._resolve_submitter`：终态事件按 compute_jobs.session_id 路由到
  提交者 agent_id，查不到回退 a-0。
"""

import time
from types import SimpleNamespace

import pytest

from cloudra.persistence.database import ConversationDB
from cloudra.runtime.executor import (
    _pending_reminder_count,
    _run_with_reminder_waits,
    _seconds_until_own_reminder,
)
from cloudra.runtime.monitor import _resolve_submitter


@pytest.fixture
def db(tmp_path):
    return ConversationDB.from_path(str(tmp_path / "exec.db")).init()


async def _insert_reminder(db, conv_id, agent_id, wake_at, content="检查计算", session_id="s-1"):
    async with db.aconnect() as con:
        cur = await con.execute(
            """
            INSERT INTO scheduled_reminders
            (conversation_id, agent_id, session_id, content, wake_at, state, created_at)
            VALUES (?, ?, ?, ?, ?, 'pending', ?)
            """,
            (conv_id, agent_id, session_id, content, wake_at, time.time()),
        )
        await con.commit()
        return cur.lastrowid


class _FakeReAct:
    """最小 react 替身：run 按脚本返回，drain 按脚本返回。"""

    def __init__(self, run_results, drain_results, session_id="s-1"):
        self._run_results = list(run_results)
        self._drain_results = list(drain_results)
        self._continue = True
        self.run_calls = 0
        self.session = SimpleNamespace(id=session_id)

    async def run(self):
        self.run_calls += 1
        return self._run_results.pop(0)

    async def drain_pending_external_events(self) -> bool:
        return self._drain_results.pop(0) if self._drain_results else False


@pytest.mark.asyncio
class TestRunWithReminderWaits:
    async def test_no_pending_reminders_returns_immediately(self, db):
        """无 pending 提醒：只跑一次 run()，立即返回。"""
        react = _FakeReAct(["done"], [])
        result = await _run_with_reminder_waits(react, db, "conv-x", "a-4")
        assert result == "done"
        assert react.run_calls == 1

    async def test_pending_reminder_resurrects_run(self, db, monkeypatch):
        """有 pending 提醒：挂起等待，提醒触发后 drain 到事件则复活续跑。"""
        # 提醒已到期（wake_at 在过去），第一轮等待循环应立即认领触发
        await _insert_reminder(db, "conv-x", "a-4", time.time() - 1)

        # IPC listener 需要可用；fire 后的 inject_event 走 aemit，无 listener 会报错
        from cloudra.infra import events

        await events.ensure_listener("conv-x")
        react = _FakeReAct(["第一轮", "复活后收尾"], [True])
        result = await _run_with_reminder_waits(react, db, "conv-x", "a-4")
        assert result == "复活后收尾"
        assert react.run_calls == 2
        assert react._continue is True
        # 提醒已被触发（fired），循环随之退出
        assert await _pending_reminder_count(db, "conv-x", "a-4", "s-1") == 0
        events.shutdown_all_listeners()

    async def test_other_agents_reminders_do_not_hold_session(self, db):
        """别人的 pending 提醒不影响本 Agent 的退出。"""
        await _insert_reminder(db, "conv-x", "a-0", time.time() + 3600)
        react = _FakeReAct(["done"], [])
        result = await _run_with_reminder_waits(react, db, "conv-x", "a-4")
        assert result == "done"
        assert react.run_calls == 1

    async def test_other_sessions_reminders_do_not_hold_session(self, db):
        """并行子任务复用同一 agent_id 时：别的 session 的提醒不唤醒、不续命本 session。"""
        await _insert_reminder(db, "conv-x", "a-4", time.time() + 3600, session_id="s-2")
        react = _FakeReAct(["done"], [], session_id="s-1")
        result = await _run_with_reminder_waits(react, db, "conv-x", "a-4")
        assert result == "done"
        assert react.run_calls == 1
        # 别的 session 的提醒仍在，且不属于本 session
        assert await _pending_reminder_count(db, "conv-x", "a-4", "s-1") == 0
        assert await _pending_reminder_count(db, "conv-x", "a-4", "s-2") == 1

    async def test_legacy_null_session_reminder_still_counts(self, db):
        """无 session_id 的旧提醒视为会话级广播，任何 session 都能等到。"""
        await _insert_reminder(db, "conv-x", "a-4", time.time() + 100, session_id=None)
        assert await _pending_reminder_count(db, "conv-x", "a-4", "s-1") == 1
        assert await _seconds_until_own_reminder(db, "conv-x", "a-4", "s-1") > 90

    async def test_seconds_until_own_reminder(self, db):
        await _insert_reminder(db, "conv-x", "a-4", time.time() + 100)
        await _insert_reminder(db, "conv-x", "a-6", time.time() + 5)
        assert await _seconds_until_own_reminder(db, "conv-x", "a-4", "s-1") > 90
        assert await _seconds_until_own_reminder(db, "conv-x", "a-5", "s-1") is None
        # 同 agent 不同 session 的提醒不参与本 session 的计算
        assert await _seconds_until_own_reminder(db, "conv-x", "a-4", "s-2") is None


@pytest.mark.asyncio
class TestResolveSubmitter:
    async def test_routes_to_submitting_agent(self, db):
        async with db.aconnect() as con:
            await con.execute(
                "INSERT INTO session (session_id, agent_id, state) VALUES (?, ?, 'running')",
                ("a-4_task1", "a-4"),
            )
            await con.execute(
                """
                INSERT INTO compute_jobs
                (conversation_id, session_id, path, state, jobtype, start_timestamp, end_timestamp, scheduler, scheduler_options)
                VALUES ('conv-x', 'a-4_task1', '/tmp/x.gjf', 'running', 'gaussian', -1, -1, 'local', '{}')
                """,
            )
            await con.commit()
            task_id = (await (await con.execute("SELECT last_insert_rowid()")).fetchone())[0]

        assert await _resolve_submitter(db, task_id) == "a-4"

    async def test_falls_back_to_coordinator(self, db):
        async with db.aconnect() as con:
            await con.execute(
                """
                INSERT INTO compute_jobs
                (conversation_id, session_id, path, state, jobtype, start_timestamp, end_timestamp, scheduler, scheduler_options)
                VALUES ('conv-x', NULL, '/tmp/x.gjf', 'running', 'gaussian', -1, -1, 'local', '{}')
                """,
            )
            await con.commit()
            task_id = (await (await con.execute("SELECT last_insert_rowid()")).fetchone())[0]

        assert await _resolve_submitter(db, task_id) == "a-0"
        # 不存在的 task 同样回退
        assert await _resolve_submitter(db, 99999) == "a-0"
