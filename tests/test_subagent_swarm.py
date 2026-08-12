"""SubAgentSwarm (t-47) 批量并行派发测试 + Plantool session 级存储隔离测试。

不允许真实 LLM 调用：monkeypatch cloudra.runtime.executor.run_executor 为假实现，
直接从 subagent_requests 的 payload 取 query，往 session 表写 result 后 finalize。
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from cloudra.persistence.database import ConversationDB
from cloudra.services import session_store


@pytest.fixture
def isolated_runtime(tmp_path, monkeypatch):
    """隔离数据目录，并强制桌面 in-process 模式（屏蔽外部环境变量）。"""
    from cloudra.infra.config import get_config

    monkeypatch.setenv("CLOUDRA_MOBILE_MODE", "false")
    monkeypatch.delenv("CLOUDRA_SUBAGENT_MODE", raising=False)
    cfg = get_config()
    monkeypatch.setattr(cfg, "data_dir", tmp_path)
    cfg._ensure_dirs()
    ConversationDB("swarm-parent").init()
    return tmp_path


def _make_tool():
    from cloudra.tools.Managetool.subagent_swarm import SubAgentSwarm

    tool = SubAgentSwarm()
    tool.subagent = SimpleNamespace(
        conversation_id="swarm-parent",
        working_directory="/tmp",
    )
    return tool


def _make_input(**overrides):
    from cloudra.tools.Managetool.subagent_swarm import SubAgentSwarm_input_schema

    defaults = dict(
        agent_id="a-1",
        prompt_template="在 /tmp 下检查目录 {{item}} 并汇报。只读，禁止写入。",
        items=["alpha", "beta", "gamma"],
        is_wait=True,
    )
    defaults.update(overrides)
    return SubAgentSwarm_input_schema(**defaults)


def _install_fake_executor(monkeypatch, sleep: float = 0.0, concurrency_log: dict | None = None):
    """假 executor：读 payload 的 query，写 result=RESULT::<query> 后 finalize。"""

    async def fake_run_executor(task_id: int, database_path: str, session_id: str, **_kwargs):
        if concurrency_log is not None:
            concurrency_log["active"] += 1
            concurrency_log["peak"] = max(concurrency_log["peak"], concurrency_log["active"])
        try:
            db = ConversationDB.from_path(database_path)

            def _read_query() -> str:
                with db.connect() as con:
                    row = con.execute(
                        "SELECT input_data FROM subagent_requests WHERE id = ?", (task_id,)
                    ).fetchone()
                return json.loads(row[0])["query"] if row else ""

            # 同步 sqlite 调用一律放到工作线程：直接等在事件循环线程上会与
            # 其他协程的异步写事务互锁（对齐 executor 中 to_thread 构造 reAct 的修法）。
            query = await asyncio.to_thread(_read_query)
            if sleep:
                await asyncio.sleep(sleep)
            await asyncio.to_thread(
                session_store.create_session_record,
                db,
                session_id=session_id,
                agent_id="a-1",
                agent_type="explorer",
                parent_session_id=None,
                query=query,
                created_at=datetime.now(timezone.utc).isoformat(),
            )
            await session_store.afinalize_session(db, session_id, "completed", result=f"RESULT::{query}")
            await session_store.afinalize_task(db, task_id, session_id, "done")
        finally:
            if concurrency_log is not None:
                concurrency_log["active"] -= 1

    monkeypatch.setattr("cloudra.runtime.executor.run_executor", fake_run_executor)


def _request_rows():
    db = ConversationDB("swarm-parent")
    with db.connect() as con:
        return con.execute(
            "SELECT session_id, state FROM subagent_requests ORDER BY id"
        ).fetchall()


class TestValidation:
    @pytest.mark.asyncio
    async def test_template_without_placeholder_rejected(self, isolated_runtime):
        tool = _make_tool()
        out = await tool.tool_call(
            _make_input(prompt_template="没有占位符的模板", items=["a", "b"]), session=None
        )
        assert out.session_ids == []
        assert "{{item}}" in out.result

    @pytest.mark.asyncio
    async def test_duplicate_expansion_rejected_with_items(self, isolated_runtime):
        tool = _make_tool()
        out = await tool.tool_call(
            _make_input(items=["alpha", "alpha", "beta"]), session=None
        )
        assert out.session_ids == []
        assert "重复" in out.result
        assert "alpha" in out.result

    @pytest.mark.asyncio
    async def test_items_count_bounds(self, isolated_runtime):
        tool = _make_tool()
        out = await tool.tool_call(_make_input(items=["only-one"]), session=None)
        assert out.session_ids == []
        assert "2" in out.result and "128" in out.result

    @pytest.mark.asyncio
    async def test_unknown_agent_id_rejected(self, isolated_runtime):
        tool = _make_tool()
        out = await tool.tool_call(_make_input(agent_id="a-999"), session=None)
        assert out.session_ids == []
        assert "not found" in out.result
        assert "a-1" in out.result  # 列出可用 id


@pytest.mark.asyncio
class TestWaitingSwarm:
    async def test_dispatch_three_items_unique_sessions_and_rows(self, isolated_runtime, monkeypatch):
        _install_fake_executor(monkeypatch)
        tool = _make_tool()
        out = await tool.tool_call(_make_input(), session=None)

        assert len(out.session_ids) == 3
        assert len(set(out.session_ids)) == 3  # 3 个不同 session_id
        assert all(sid.startswith("a-1_task") for sid in out.session_ids)

        rows = _request_rows()
        assert len(rows) == 3  # DB 中 3 行记录
        assert {r[0] for r in rows} == set(out.session_ids)
        assert all(r[1] == "done" for r in rows)

    async def test_aggregation_report_contains_each_result_and_status(self, isolated_runtime, monkeypatch):
        _install_fake_executor(monkeypatch)
        tool = _make_tool()
        items = ["alpha", "beta", "gamma"]
        out = await tool.tool_call(_make_input(items=items), session=None)

        assert "Swarm 完成: 3/3 个成功" in out.result
        for index, item in enumerate(items, start=1):
            assert f"=== Item {index}/3: {item} ===" in out.result
            assert f"检查目录 {item}" in out.result  # 该项的 RESULT 进入报告
        assert out.result.count("状态: 成功") == 3

    async def test_max_concurrency_limits_parallelism(self, isolated_runtime, monkeypatch):
        log = {"active": 0, "peak": 0}
        _install_fake_executor(monkeypatch, sleep=0.05, concurrency_log=log)
        tool = _make_tool()
        out = await tool.tool_call(
            _make_input(items=["a", "b", "c", "d"], max_concurrency=2), session=None
        )

        assert len(out.session_ids) == 4
        assert "4/4 个成功" in out.result
        assert 1 <= log["peak"] <= 2  # 峰值并发不超过上限

    async def test_executor_failure_aggregated_as_failed_section(self, isolated_runtime, monkeypatch):
        async def boom(task_id: int, database_path: str, session_id: str):
            raise RuntimeError("executor exploded")

        monkeypatch.setattr("cloudra.runtime.executor.run_executor", boom)
        tool = _make_tool()
        out = await tool.tool_call(_make_input(items=["a", "b"]), session=None)

        # _run_subagent_in_process 兜底落库 failed，报告分节标记失败
        assert "0/2 个成功" in out.result
        assert out.result.count("状态: 失败") == 2


@pytest.mark.asyncio
class TestFireAndForget:
    async def test_returns_immediately_with_all_session_ids(self, isolated_runtime, monkeypatch):
        scheduled: list = []

        def fake_create_mobile_task(coro):
            scheduled.append(coro)
            coro.close()  # 不真正执行，避免 "never awaited" 警告
            return None

        monkeypatch.setattr(
            "cloudra.runtime.mobile_tasks.create_mobile_task", fake_create_mobile_task
        )

        tool = _make_tool()
        out = await tool.tool_call(_make_input(is_wait=False), session=None)

        assert len(scheduled) == 3
        assert len(out.session_ids) == 3
        assert len(set(out.session_ids)) == 3
        assert all(sid in out.result for sid in out.session_ids)

        rows = _request_rows()
        assert len(rows) == 3
        assert all(r[1] == "running" for r in rows)  # in-process 异步：挂 running


class TestRegistry:
    def test_swarm_registered(self):
        from cloudra.tools import get_tools_lst

        names = {e.tool_name for e in get_tools_lst()}
        assert "SubAgentSwarm" in names
        assert "SubAgentLauncher" in names


@pytest.mark.asyncio
class TestPlanStoreSessionIsolation:
    """同角色并行实例（不同 session_id）的 todos/goal 互不覆盖；无 session_id 保持旧路径。"""

    def _make_agent(self, session_id):
        from cloudra.core.agent import Follower

        agent = Follower(
            id="a-6",
            name="dft",
            prompt="测试",
            query="测试问题",
            conversation_id="swarm-plan",
        )
        if session_id is not None:
            agent.session_id = session_id
        return agent

    async def test_parallel_instances_isolated(self, isolated_runtime, mock_session):
        from cloudra.tools.Plantool.todo import TodoWrite, TodoWrite_input_schema
        from cloudra.tools.Plantool.todo_read import TodoRead, TodoRead_input_schema

        agent_a = self._make_agent("a-6_task1")
        agent_b = self._make_agent("a-6_task2")

        await TodoWrite(subagent=agent_a).tool_call(
            TodoWrite_input_schema(todos=[{"content": "实例A的任务"}]), mock_session
        )
        await TodoWrite(subagent=agent_b).tool_call(
            TodoWrite_input_schema(todos=[{"content": "实例B的任务"}]), mock_session
        )

        out_a = await TodoRead(subagent=agent_a).tool_call(TodoRead_input_schema(), mock_session)
        out_b = await TodoRead(subagent=agent_b).tool_call(TodoRead_input_schema(), mock_session)

        assert [t["content"] for t in out_a.todos] == ["实例A的任务"]
        assert [t["content"] for t in out_b.todos] == ["实例B的任务"]
        # agent 侧提醒读取也走同一键控：各自只看到自己的清单
        assert agent_a._todo_reminder() and agent_b._todo_reminder()

    async def test_no_session_id_keeps_legacy_path_and_unseen_by_sessions(self, isolated_runtime, mock_session):
        from cloudra.tools.Plantool._store import agent_store_path
        from cloudra.tools.Plantool.todo import TodoWrite, TodoWrite_input_schema
        from cloudra.tools.Plantool.todo_read import TodoRead, TodoRead_input_schema

        legacy = self._make_agent(None)
        sessioned = self._make_agent("a-6_task9")

        # 旧行为：路径不含 session_id，文件名仍是 {agent_id}_{filename}
        assert agent_store_path(legacy, "todos.json").endswith("a-6_todos.json")
        assert "a-6_task9" in agent_store_path(sessioned, "todos.json")

        await TodoWrite(subagent=legacy).tool_call(
            TodoWrite_input_schema(todos=[{"content": "主 agent 的任务"}]), mock_session
        )
        # 带 session_id 的实例看不到主 agent 的清单，反之亦然
        out_s = await TodoRead(subagent=sessioned).tool_call(TodoRead_input_schema(), mock_session)
        out_l = await TodoRead(subagent=legacy).tool_call(TodoRead_input_schema(), mock_session)
        assert out_s.todos == []
        assert [t["content"] for t in out_l.todos] == ["主 agent 的任务"]
