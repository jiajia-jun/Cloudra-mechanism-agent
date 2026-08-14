"""executor 统一收尾路径（session_store.finalize_task）的行为钉板测试。

背景：executor.run_executor 中三段几乎相同的收尾代码已合并为
session_store.finalize_task 单一路径（executor 只保留薄封装 _finalize_task）。
这里钉住合并后可观察的行为：
1. subagent_requests / session 两张表分别写入哪些列（state、exit_code、
   error、finished_at，以及 finished_at 一律 COALESCE 保留首个终态时间戳）。
2. 通过 ContextManager.inject_event 注入给 Coordinator 的唤醒事件内容
   （直接查 context_events 表断言，不 mock）。

合并时的 deliberate unification（与旧行为的三处差异，均属有意统一）：
- 旧 mark_done 不写 session.state（假定 reAct.run 已写）→ 统一收尾永远写
  session.state（done 映射为 completed）。
- 旧 mark_failed 无条件覆盖 finished_at，done/cancelled 用 COALESCE → 统一
  一律 COALESCE（首个终态时间戳生效）。
- result/error 的事件内容 500 字符截断保持不变。
"""

import json
from types import SimpleNamespace

import pytest

from cloudra.persistence.database import ConversationDB


class _FakeAgent:
    """可用于实例化的 Agent 替身类。"""

    def __init__(self, query=None, conversation_id=None, **kwargs):
        self.name = "fake-agent"
        self.query = query
        self.conversation_id = conversation_id
        self.session_id = None
        self.working_directory = None
        self.context_manager = None
        self.temperature = 0.7

    async def get_context(self):
        return []

    async def update_context(self, block):
        pass


class _ContextDelegatingAgent(_FakeAgent):
    """把 update_context 交给真实 ContextManager，用于检查落盘的 user 行。"""

    def __init__(self, query=None, conversation_id=None, **kwargs):
        super().__init__(query=query, conversation_id=conversation_id, **kwargs)
        self.id = "a-fake"
        self.prompt = "stock role prompt"

    async def _report_compaction_progress(self, progress):
        return None

    def _ensure_context_manager(self):
        if self.context_manager is None:
            from cloudra.persistence.context_manager import ContextManager

            self.context_manager = ContextManager(
                agent_id=self.id,
                conversation_id=self.conversation_id,
                prompt=self.prompt,
                query=self.query,
                session_id=self.session_id,
                on_compaction_progress=self._report_compaction_progress,
            )
        return self.context_manager

    async def get_context(self):
        return await self._ensure_context_manager().load()

    async def update_context(self, block):
        await self._ensure_context_manager().append(block)


def _make_fake_react(result=None, exc=None):
    """构造 reAct 替身类：run() 返回固定结果或抛出固定异常。"""

    class FakeReAct:
        def __init__(self, agent, session_id=None, parent_session_id=None):
            self.agent = agent
            self.log = SimpleNamespace(is_main=False)

        async def run(self):
            if exc is not None:
                raise exc
            return result

    return FakeReAct


def _setup_executor_env(
    tmp_path, monkeypatch, run_result=None, run_exc=None, *, input_extra=None, agent_cls=None
):
    """准备临时 DB（1 条 running 请求 + 1 条 running session）并替换 Subagent_hash / reAct。"""
    import os
    from pathlib import Path

    runtime_dir = Path(f"/tmp/cr{os.getpid()}e")
    runtime_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(runtime_dir))
    db_path = str(tmp_path / "test.db")
    db = ConversationDB.from_path(db_path).init()
    input_data = {
        "agent_id": "a-fake",
        "query": "测试任务",
        "conversation_id": "conv-1",
        "session_id": "s-1",
    }
    if input_extra:
        input_data.update(input_extra)
    with db.connect() as con:
        con.execute(
            "INSERT INTO subagent_requests (id, state, input_data, conversation_id, session_id) "
            "VALUES (1, 'running', ?, 'conv-1', 's-1')",
            (json.dumps(input_data),),
        )
        con.execute("INSERT INTO session (session_id, state) VALUES ('s-1', 'running')")
        con.commit()

    cls = agent_cls or _FakeAgent
    agent_hash = type("AgentHash", (), {"get": lambda self, k: {"a-fake": cls}.get(k)})()
    monkeypatch.setattr("cloudra.runtime.executor.Subagent_hash", lambda: agent_hash)
    monkeypatch.setattr(
        "cloudra.runtime.executor.reAct", _make_fake_react(result=run_result, exc=run_exc)
    )
    return db_path


def _read_states(db_path):
    db = ConversationDB.from_path(db_path)
    with db.connect() as con:
        req_state = con.execute(
            "SELECT state FROM subagent_requests WHERE id=1"
        ).fetchone()[0]
        sess = con.execute(
            "SELECT state, error, exit_code, finished_at FROM session WHERE session_id='s-1'"
        ).fetchone()
        events = con.execute(
            "SELECT conversation_id, agent_id, event_type, content, state FROM context_events"
        ).fetchall()
    return req_state, sess, events


@pytest.mark.asyncio
class TestMarkDone:
    async def test_db_state_and_wakeup_event(self, tmp_path, monkeypatch):
        from cloudra.runtime.executor import run_executor

        db_path = _setup_executor_env(tmp_path, monkeypatch, run_result="任务结论")
        await run_executor(1, db_path, "s-1")

        req_state, sess, events = _read_states(db_path)
        assert req_state == "done"
        # 统一收尾永远写 session.state（done 映射为 completed）；
        # 不写 error，exit_code=0，finished_at 落库
        assert sess[0] == "completed"
        assert sess[1] is None
        assert sess[2] == 0
        assert sess[3] is not None

        assert len(events) == 1
        conv_id, agent_id, event_type, content, ev_state = events[0]
        assert (conv_id, agent_id, event_type, ev_state) == (
            "conv-1", "a-0", "subagent", "pending",
        )
        assert content == "Sub-agent fake-agent (session=s-1, task_id=1) completed. Conclusion: 任务结论"

    async def test_event_content_truncates_result_to_500_chars(self, tmp_path, monkeypatch):
        from cloudra.runtime.executor import run_executor

        db_path = _setup_executor_env(tmp_path, monkeypatch, run_result="长" * 600)
        await run_executor(1, db_path, "s-1")

        _, _, events = _read_states(db_path)
        content = events[0][3]
        assert content.endswith("长" * 500)
        assert "长" * 501 not in content


@pytest.mark.asyncio
class TestMarkCancelled:
    async def test_db_state_and_wakeup_event(self, tmp_path, monkeypatch):
        from cloudra.core.react import AgentCancelled
        from cloudra.runtime.executor import run_executor

        db_path = _setup_executor_env(tmp_path, monkeypatch, run_exc=AgentCancelled("取消"))
        await run_executor(1, db_path, "s-1")

        req_state, sess, events = _read_states(db_path)
        assert req_state == "cancelled"
        # cancelled 路径会写 session.state，但不写 exit_code / error
        assert sess[0] == "cancelled"
        assert sess[1] is None
        assert sess[2] is None
        assert sess[3] is not None

        assert len(events) == 1
        assert events[0][3] == "Sub-agent fake-agent (session=s-1, task_id=1) was cancelled."

    async def test_finished_at_is_coalesced(self, tmp_path, monkeypatch):
        """cancelled 路径用 COALESCE：已有 finished_at 不被覆盖。"""
        from cloudra.core.react import AgentCancelled
        from cloudra.runtime.executor import run_executor

        db_path = _setup_executor_env(tmp_path, monkeypatch, run_exc=AgentCancelled("取消"))
        db = ConversationDB.from_path(db_path)
        with db.connect() as con:
            con.execute(
                "UPDATE session SET finished_at='2000-01-01T00:00:00' WHERE session_id='s-1'"
            )
            con.commit()

        await run_executor(1, db_path, "s-1")

        _, sess, _ = _read_states(db_path)
        assert sess[3] == "2000-01-01T00:00:00"


@pytest.mark.asyncio
class TestMarkFailed:
    async def test_db_state_and_wakeup_event(self, tmp_path, monkeypatch):
        from cloudra.runtime.executor import run_executor

        db_path = _setup_executor_env(tmp_path, monkeypatch, run_exc=RuntimeError("爆炸了"))
        await run_executor(1, db_path, "s-1")

        req_state, sess, events = _read_states(db_path)
        assert req_state == "failed"
        # failed 路径写 state/error/finished_at/exit_code 四列
        assert sess[0] == "failed"
        assert sess[1] == "爆炸了"
        assert sess[2] == 1
        assert sess[3] is not None

        assert len(events) == 1
        assert events[0][3].startswith("Sub-agent fake-agent (session=s-1, task_id=1) failed: 爆炸了")
        assert "session.error" in events[0][3]
        assert "get_subagent_report" in events[0][3]

    async def test_finished_at_is_coalesced(self, tmp_path, monkeypatch):
        """统一收尾一律 COALESCE：failed 路径也不再覆盖已有 finished_at（首个终态时间戳生效）。"""
        from cloudra.runtime.executor import run_executor

        db_path = _setup_executor_env(tmp_path, monkeypatch, run_exc=RuntimeError("boom"))
        db = ConversationDB.from_path(db_path)
        with db.connect() as con:
            con.execute(
                "UPDATE session SET finished_at='2000-01-01T00:00:00' WHERE session_id='s-1'"
            )
            con.commit()

        await run_executor(1, db_path, "s-1")

        _, sess, _ = _read_states(db_path)
        assert sess[3] == "2000-01-01T00:00:00"

    async def test_event_content_truncates_error_to_500_chars(self, tmp_path, monkeypatch):
        from cloudra.runtime.executor import run_executor

        db_path = _setup_executor_env(tmp_path, monkeypatch, run_exc=RuntimeError("错" * 600))
        await run_executor(1, db_path, "s-1")

        _, sess, events = _read_states(db_path)
        # session.error 保存完整错误，事件内容截断到 500 字符（之后附根因排查指引）
        assert sess[1] == "错" * 600
        assert "错" * 500 in events[0][3]
        assert "错" * 501 not in events[0][3]


@pytest.mark.asyncio
class TestExecutorWorkers:
    """进程内 run_executor 必须自己 acquire compute workers。

    隔离 TUI 下 follower 走 run_subagent_in_process → run_executor，
    不再经过 run_task_async。Coordinator 进程死后 jobs 会永远停在 ready。
    """

    async def test_acquires_and_releases_when_idle(self, tmp_path, monkeypatch):
        from unittest.mock import patch

        from cloudra.runtime.executor import run_executor

        db_path = _setup_executor_env(tmp_path, monkeypatch, run_result="ok")
        acquired = []
        released = []

        with patch("cloudra.runtime.workers.acquire_workers", lambda db, *a, **k: acquired.append(db)), \
             patch("cloudra.runtime.workers.release_workers", lambda db, *a, **k: released.append(db)):
            await run_executor(1, db_path, "s-1")

        assert acquired == [db_path]
        assert released == [db_path]

    async def test_keeps_workers_when_compute_pending(self, tmp_path, monkeypatch):
        from unittest.mock import patch

        from cloudra.runtime.executor import run_executor

        db_path = _setup_executor_env(tmp_path, monkeypatch, run_result="ok")
        db = ConversationDB.from_path(db_path)
        with db.connect() as con:
            con.execute(
                "INSERT INTO compute_jobs (conversation_id, state, path, jobtype) "
                "VALUES ('conv-1', 'ready', '/tmp/x.gjf', 'gaussian')"
            )
            con.commit()

        acquired = []
        released = []
        with patch("cloudra.runtime.workers.acquire_workers", lambda db, *a, **k: acquired.append(db)), \
             patch("cloudra.runtime.workers.release_workers", lambda db, *a, **k: released.append(db)):
            await run_executor(1, db_path, "s-1")

        assert acquired == [db_path]
        assert released == []


@pytest.mark.asyncio
async def test_hub_call_origin_has_exactly_one_incoming_user_line(tmp_path, monkeypatch):
    """hub_call spawn：上下文只有一条[Incoming call]user 行，前面不能再有裸 query。"""
    from cloudra.persistence.context_manager import ContextManager
    from cloudra.runtime.executor import run_executor
    from cloudra.tools.Managetool._hub_call import format_incoming_call

    spoken = "帮我看虚频"
    incoming = format_incoming_call(
        caller_agent_id="a-0",
        caller_session_id="a-0_run1",
        message=spoken,
    )
    db_path = _setup_executor_env(
        tmp_path,
        monkeypatch,
        run_result="ok",
        input_extra={
            "query": spoken,
            "origin": "hub_call",
            "context": [{"role": "user", "content": incoming}],
            "caller_agent_id": "a-0",
            "caller_session_id": "a-0_run1",
        },
        agent_cls=_ContextDelegatingAgent,
    )
    await run_executor(1, db_path, "s-1")

    stored = await ContextManager(
        agent_id="a-fake",
        conversation_id="conv-1",
        prompt=None,
        query="",
        session_id="s-1",
    ).load()
    user_msgs = [m for m in stored if m.get("role") == "user"]
    assert len(user_msgs) == 1
    assert "[Incoming call]" in user_msgs[0]["content"]
    assert user_msgs[0]["content"] == incoming
    assert stored[0]["content"] != spoken


@pytest.mark.asyncio
class TestHubCallHangup:
    async def test_hub_call_origin_does_not_wake_coordinator_as_delivery(
        self, tmp_path, monkeypatch
    ):
        from cloudra.persistence.context_manager import ContextManager
        from cloudra.runtime.executor import run_executor

        db_path = _setup_executor_env(
            tmp_path,
            monkeypatch,
            run_result="闲聊结论",
            agent_cls=_ContextDelegatingAgent,
        )
        db = ConversationDB.from_path(db_path)
        with db.connect() as con:
            row = con.execute("SELECT input_data FROM subagent_requests WHERE id=1").fetchone()
            payload = json.loads(row[0])
            payload["origin"] = "hub_call"
            payload["caller_agent_id"] = "a-0"
            payload["caller_session_id"] = "a-0_run1"
            con.execute(
                "UPDATE subagent_requests SET input_data=? WHERE id=1",
                (json.dumps(payload),),
            )
            con.commit()
        await run_executor(1, db_path, "s-1")
        _, _, events = _read_states(db_path)
        contents = [e[3] for e in events]
        assert not any("completed. Conclusion" in (c or "") for c in contents)

        hangups = [
            e
            for e in events
            if e[2] == "user_message" and "[Call ended]" in (e[3] or "")
        ]
        assert len(hangups) == 1
        conv_id, agent_id, event_type, content, ev_state = hangups[0]
        assert (conv_id, agent_id, event_type, ev_state) == (
            "conv-1",
            "a-0",
            "user_message",
            "pending",
        )
        assert "fake-agent" in content
        assert "session=s-1" in content
        assert "hung up" in content
        assert not any(e[2] == "subagent" for e in events)

        caller_cm = ContextManager(
            agent_id="a-0",
            conversation_id="conv-1",
            prompt=None,
            query="",
        )
        caller_stored = await caller_cm.load()
        caller_user = [
            m
            for m in caller_stored
            if m.get("role") == "user" and "[Call ended]" in str(m.get("content", ""))
        ]
        assert len(caller_user) == 1
        assert "fake-agent" in caller_user[0]["content"]
        assert "session=s-1" in caller_user[0]["content"]

    async def test_hangup_inject_failure_keeps_task_done(self, tmp_path, monkeypatch):
        from cloudra.runtime.executor import run_executor

        db_path = _setup_executor_env(
            tmp_path, monkeypatch, run_result="闲聊结论", agent_cls=_ContextDelegatingAgent
        )
        db = ConversationDB.from_path(db_path)
        with db.connect() as con:
            row = con.execute("SELECT input_data FROM subagent_requests WHERE id=1").fetchone()
            payload = json.loads(row[0])
            payload["origin"] = "hub_call"
            payload["caller_agent_id"] = "a-0"
            payload["caller_session_id"] = "a-0_run1"
            con.execute(
                "UPDATE subagent_requests SET input_data=? WHERE id=1",
                (json.dumps(payload),),
            )
            con.commit()

        async def boom(**_kwargs):
            raise RuntimeError("inject failed")

        monkeypatch.setattr(
            "cloudra.tools.Managetool._hub_call.deliver_incoming_call",
            boom,
        )
        await run_executor(1, db_path, "s-1")
        req_state, sess, events = _read_states(db_path)
        assert req_state == "done"
        assert sess[0] == "completed"
        assert not any("completed. Conclusion" in (c or "") for c in (e[3] for e in events))
