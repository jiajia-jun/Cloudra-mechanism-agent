"""main.py 后台回收与审批写入、run_task_async 外层契约的行为钉板测试。

覆盖：
1. reap_exited_executors 的状态迁移矩阵：只有 state='running' 的
   subagent_requests / session 会被回收为 failed，其余状态不动；
   session.error 用 COALESCE 保留已有值。
2. apply_approval_decision 的写入结果，包括对孤立代理符（surrogate）
   拒绝原因的净化行为。
3. run_task_async 的外层契约（agent / LLM 全部 mock）：会话与 session
   记录的创建、conversation 状态迁移、返回值。
"""

import json
import os
from types import SimpleNamespace
from unittest.mock import patch

import pytest


def _setup_data_dir(tmp_path, monkeypatch):
    from cloudra.config import get_config, reload_config

    data_dir = tmp_path / "data"
    monkeypatch.setenv("CLOUDRA_DATA_DIR", str(data_dir))
    reload_config()
    get_config().data_dir = data_dir
    get_config()._ensure_dirs()
    return data_dir


def _insert_running(db, req_id, session_id, req_state="running", sess_state="running"):
    with db.connect() as con:
        con.execute(
            "INSERT OR IGNORE INTO session (session_id, agent_id, agent_type, state) "
            "VALUES (?, 'a-2', 'follower', ?)",
            (session_id, sess_state),
        )
        con.execute(
            "INSERT INTO subagent_requests (id, state, input_data, conversation_id, session_id) "
            "VALUES (?, ?, '{}', 'conv-reap', ?)",
            (req_id, req_state, session_id),
        )
        con.commit()


class TestReapExitedExecutors:
    def test_only_running_rows_are_reaped(self, tmp_path, monkeypatch):
        """已退出进程：running 请求 → failed；非 running 请求原样保留且不进返回列表。"""
        from cloudra.database import ConversationDB
        from cloudra.runtime.workers import reap_exited_executors

        _setup_data_dir(tmp_path, monkeypatch)
        db = ConversationDB("conv-reap").init()
        _insert_running(db, 1, "s-run")                    # running + running → 回收
        _insert_running(db, 2, "s-done", req_state="done", sess_state="done")  # 已自报终态

        active = {
            1: SimpleNamespace(poll=lambda: 0),
            2: SimpleNamespace(poll=lambda: 0),
        }
        reaped = reap_exited_executors(db.path, active)

        # 两个进程都会从 active 中移除，但只有真正改了行的进 reaped 列表
        assert reaped == [1]
        assert active == {}
        with db.connect() as con:
            states = dict(con.execute("SELECT id, state FROM subagent_requests").fetchall())
            sess = dict(con.execute("SELECT session_id, state FROM session").fetchall())
        assert states == {1: "failed", 2: "done"}
        assert sess == {"s-run": "failed", "s-done": "done"}

    def test_ready_request_not_reaped(self, tmp_path, monkeypatch):
        """ready 状态的请求即使进程已退出也不回收（rowcount=0，不进返回列表）。

        统一后的语义（session_store.reap_exited_requests）：只有请求行确实被
        回收（running → failed）时才连带标记其 Session；请求未被回收时不再
        无条件把 running Session 标 failed——历史实现不看请求回收结果、
        无条件标 Session 的怪癖已随统一修正。
        """
        from cloudra.database import ConversationDB
        from cloudra.runtime.workers import reap_exited_executors

        _setup_data_dir(tmp_path, monkeypatch)
        db = ConversationDB("conv-reap").init()
        _insert_running(db, 1, "s-ready", req_state="ready", sess_state="running")

        active = {1: SimpleNamespace(poll=lambda: 1)}
        reaped = reap_exited_executors(db.path, active)

        assert reaped == []
        assert 1 not in active
        with db.connect() as con:
            req_state = con.execute("SELECT state FROM subagent_requests WHERE id=1").fetchone()[0]
            sess_state = con.execute("SELECT state FROM session WHERE session_id='s-ready'").fetchone()[0]
        assert req_state == "ready"
        assert sess_state == "running"

    def test_existing_session_error_preserved(self, tmp_path, monkeypatch):
        """session.error 用 COALESCE：已有错误信息不被默认文案覆盖。"""
        from cloudra.database import ConversationDB
        from cloudra.runtime.workers import reap_exited_executors

        _setup_data_dir(tmp_path, monkeypatch)
        db = ConversationDB("conv-reap").init()
        _insert_running(db, 1, "s-err")
        with db.connect() as con:
            con.execute("UPDATE session SET error='原始错误' WHERE session_id='s-err'")
            con.commit()

        active = {1: SimpleNamespace(poll=lambda: 137)}
        assert reap_exited_executors(db.path, active) == [1]

        with db.connect() as con:
            state, error, finished_at = con.execute(
                "SELECT state, error, finished_at FROM session WHERE session_id='s-err'"
            ).fetchone()
        assert state == "failed"
        assert error == "原始错误"
        assert finished_at is not None

    def test_no_exited_processes_is_noop(self, tmp_path, monkeypatch):
        """没有退出进程时不触碰数据库，active 原样保留。"""
        from cloudra.database import ConversationDB
        from cloudra.runtime.workers import reap_exited_executors

        _setup_data_dir(tmp_path, monkeypatch)
        db = ConversationDB("conv-reap").init()
        _insert_running(db, 1, "s-live")

        active = {1: SimpleNamespace(poll=lambda: None)}
        assert reap_exited_executors(db.path, active) == []
        assert 1 in active
        with db.connect() as con:
            assert con.execute("SELECT state FROM subagent_requests WHERE id=1").fetchone()[0] == "running"
            assert con.execute("SELECT state FROM session WHERE session_id='s-live'").fetchone()[0] == "running"


class TestApplyApprovalDecision:
    def _make_pending(self, tmp_path, monkeypatch):
        from cloudra.database import ConversationDB

        _setup_data_dir(tmp_path, monkeypatch)
        db = ConversationDB("conv-appr").init()
        with db.connect() as con:
            con.execute(
                "INSERT INTO approvals (session_id, agent_name, details, state) "
                "VALUES ('s-1', 'a-2', 'op', 'pending')"
            )
            req_id = con.execute("SELECT id FROM approvals").fetchone()[0]
            con.commit()
        return db, req_id

    def test_approve_writes_empty_reason(self, tmp_path, monkeypatch):
        from cloudra.runtime.workers import apply_approval_decision

        db, req_id = self._make_pending(tmp_path, monkeypatch)
        assert apply_approval_decision(db.path, req_id, "approved") is True
        with db.connect() as con:
            state, reason = con.execute(
                "SELECT state, denial_reason FROM approvals WHERE id=?", (req_id,)
            ).fetchone()
        assert (state, reason) == ("approved", "")

    def test_surrogate_reason_is_sanitized(self, tmp_path, monkeypatch):
        """终端粘贴的 GBK 字节以孤立代理符残留；写库前被替换，不会抛 UnicodeEncodeError。"""
        from cloudra.runtime.workers import apply_approval_decision

        db, req_id = self._make_pending(tmp_path, monkeypatch)
        dirty = "理由" + "中文".encode("gbk").decode("utf-8", errors="surrogateescape")
        assert apply_approval_decision(db.path, req_id, "denied", dirty) is True
        with db.connect() as con:
            state, reason = con.execute(
                "SELECT state, denial_reason FROM approvals WHERE id=?", (req_id,)
            ).fetchone()
        assert state == "denied"
        assert reason == "理由????"  # 4 个孤立代理符被替换为 '?'
        reason.encode("utf-8")  # 净化后的文本必须可安全编码

    def test_unknown_id_returns_false(self, tmp_path, monkeypatch):
        from cloudra.runtime.workers import apply_approval_decision

        db, _ = self._make_pending(tmp_path, monkeypatch)
        assert apply_approval_decision(db.path, 9999, "approved") is False


@pytest.mark.asyncio
class TestRunTaskAsyncContract:
    async def test_session_conversation_and_return_value(self, tmp_path, monkeypatch):
        """pin 外层契约：conversation 恢复/创建、session 入库、状态迁移、返回值。"""
        from cloudra.database import ConversationDB
        from cloudra.main import run_task_async

        data_dir = _setup_data_dir(tmp_path, monkeypatch)

        async def fake_run(self):
            return "最终结果"

        async def fake_wait(database, conv_id):
            pass

        async def fake_no_pending(self):
            return False

        with patch("cloudra.runtime.runner.Coordinator_reAct.run", fake_run), \
             patch("cloudra.runtime.runner._wait_for_background_tasks", fake_wait), \
             patch("cloudra.runtime.runner.Coordinator_reAct.drain_pending_external_events", fake_no_pending):
            result = await run_task_async(
                "我的查询", conv_id="conv-contract", verbose=False, interactive_approval=False
            )

        assert result == "最终结果"

        # conversation 目录与元数据：任务结束后状态为 sleeping
        conv_dir = os.path.join(str(data_dir), "conversations", "conv-contract")
        assert os.path.isdir(conv_dir)
        with open(os.path.join(conv_dir, "meta.json"), encoding="utf-8") as f:
            meta = json.load(f)
        assert meta["state"] == "sleeping"

        # coordinator session 已入库（reAct.session_create），初始状态 running
        db = ConversationDB("conv-contract")
        with db.connect() as con:
            rows = con.execute(
                "SELECT agent_id, agent_type, state, query FROM session"
            ).fetchall()
        assert len(rows) == 1
        assert rows[0] == ("a-0", "coordinator", "running", "我的查询")

    async def test_failed_run_still_releases_conversation_to_sleeping(self, tmp_path, monkeypatch):
        """reAct.run 抛异常时异常向外传播，但 conversation 仍被置回 sleeping。"""
        from cloudra.conversation_class import Conversation
        from cloudra.main import run_task_async

        _setup_data_dir(tmp_path, monkeypatch)

        async def fake_run(self):
            raise RuntimeError("LLM 挂了")

        with patch("cloudra.runtime.runner.Coordinator_reAct.run", fake_run):
            with pytest.raises(RuntimeError, match="LLM 挂了"):
                await run_task_async(
                    "查询", conv_id="conv-fail", verbose=False, interactive_approval=False
                )

        assert Conversation("conv-fail").state == "sleeping"

    async def test_query_not_duplicated_in_context(self, tmp_path, monkeypatch):
        """同一 query 连续两次调用：上下文中只出现一次（去重逻辑钉板）。"""
        from cloudra.main import run_task_async

        _setup_data_dir(tmp_path, monkeypatch)

        async def fake_run(self):
            return "r"

        async def fake_wait(database, conv_id):
            pass

        async def fake_no_pending(self):
            return False

        patches = [
            patch("cloudra.runtime.runner.Coordinator_reAct.run", fake_run),
            patch("cloudra.runtime.runner._wait_for_background_tasks", fake_wait),
            patch("cloudra.runtime.runner.Coordinator_reAct.drain_pending_external_events", fake_no_pending),
        ]
        with patches[0], patches[1], patches[2]:
            await run_task_async("同一查询", conv_id="conv-dup", verbose=False, interactive_approval=False)
            await run_task_async("同一查询", conv_id="conv-dup", verbose=False, interactive_approval=False)

        ctx_path = os.path.join(
            str(tmp_path / "data"), "conversations", "conv-dup", "contexts", "a-0.json"
        )
        from cloudra.context_manager import read_context_file
        context = read_context_file(ctx_path)
        occurrences = sum(
            1 for m in context if m.get("role") == "user" and m.get("content") == "同一查询"
        )
        assert occurrences == 1
