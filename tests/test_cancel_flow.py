"""打断（cancel）链路测试：cancel_requested 状态机与 executor 兜底标记。"""

import sqlite3

import pytest

from cloudra.database import ConversationDB


def _make_react(tmp_path, monkeypatch, conv_id="test-cancel"):
    """构造一个使用临时 DB 的 reAct 实例。"""
    from cloudra.agent import Follower
    from cloudra.react import reAct

    db_path = str(tmp_path / "test.db")
    ConversationDB.from_path(db_path).init()
    monkeypatch.setattr("cloudra.react.get_database_path", lambda _conv_id: db_path)

    agent = Follower(
        id="a-test",
        name="tester",
        prompt="测试",
        query="测试问题",
        conversation_id=conv_id,
    )
    react = reAct(agent)
    return react, db_path


@pytest.mark.asyncio
class TestCancelRequested:
    async def test_check_cancellation_raises(self, tmp_path, monkeypatch):
        from cloudra.react import AgentCancelled

        react, db_path = _make_react(tmp_path, monkeypatch)
        # 默认 running：不应触发
        react._check_cancel_event()
        # 置位 cancel 事件：应抛出
        react._cancel_event.set()
        with pytest.raises(AgentCancelled):
            react._check_cancel_event()

    async def test_run_marks_cancelled(self, tmp_path, monkeypatch):
        from cloudra.react import AgentCancelled

        react, db_path = _make_react(tmp_path, monkeypatch)
        # IPC 事件驱动：直接置位本地 cancel 事件
        react._cancel_event.set()

        with pytest.raises(AgentCancelled):
            await react.run()

        with sqlite3.connect(db_path) as con:
            row = con.execute(
                "SELECT state, finished_at FROM session WHERE session_id=?",
                (react.session.id,),
            ).fetchone()
        assert row[0] == "cancelled"
        assert row[1] is not None


class TestExecutorCancelledFallback:
    def test_mark_cancelled_sync(self, tmp_path):
        from cloudra.runtime.executor import _mark_cancelled_sync

        db_path = str(tmp_path / "test.db")
        db = ConversationDB.from_path(db_path).init()
        with db.connect() as con:
            con.execute(
                "INSERT INTO subagent_requests (id, state, input_data, conversation_id) VALUES (1, 'running', '{}', 'c')"
            )
            con.execute("INSERT INTO session (session_id, state) VALUES ('s-1', 'running')")
            con.commit()

        _mark_cancelled_sync(db_path, 1, "s-1")

        with db.connect() as con:
            req_state = con.execute("SELECT state FROM subagent_requests WHERE id=1").fetchone()[0]
            sess_state = con.execute("SELECT state FROM session WHERE session_id='s-1'").fetchone()[0]
        assert req_state == "cancelled"
        assert sess_state == "cancelled"


@pytest.mark.asyncio
class TestServiceCancel:
    async def test_cancel_sets_cancel_requested_first(self, tmp_path, monkeypatch):
        """API 进程内任务：cancel 先落 cancel_requested，再取消协程。"""
        import asyncio

        from cloudra.service import CloudraService

        service = CloudraService()
        conv_id = "test-cancel-svc"
        db_path = str(tmp_path / "svc.db")
        db = ConversationDB.from_path(db_path).init()

        session_id = "a-0_test"
        with db.connect() as con:
            con.execute(
                "INSERT INTO session (session_id, agent_id, agent_type, state, created_at) VALUES (?, 'a-0', 'coordinator', 'running', 'now')",
                (session_id,),
            )
            con.commit()

        runner = service.session_runner
        # 绕过 submit（它会启动真实任务）：直接挂一个假协程
        async def fake_task():
            try:
                await asyncio.sleep(3600)
            except asyncio.CancelledError:
                runner._update(conv_id, session_id, state="cancelled")
                raise

        # 让 runner 的 DB 操作都指向临时库
        monkeypatch.setattr(
            "cloudra.service.ConversationDB",
            lambda _cid: ConversationDB.from_path(db_path),
        )
        task = asyncio.create_task(fake_task())
        runner._running[(conv_id, session_id)] = task
        await asyncio.sleep(0)  # 让协程先进入 sleep，cancel 才会走 CancelledError 路径

        record = await runner.cancel(conv_id, session_id)
        try:
            await task
        except asyncio.CancelledError:
            pass

        assert record is not None
        events = runner.events(conv_id, session_id)
        event_types = [e["event_type"] for e in events]
        assert "cancel_requested" in event_types
        final = runner.get(conv_id, session_id)
        assert final.state == "cancelled"
