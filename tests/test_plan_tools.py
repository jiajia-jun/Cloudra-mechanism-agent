"""Plantool 规划工具（todo_write / goal_set）钉板测试：

- todo_write：整体替换语义、id 自动分配与保留、in_progress 唯一软约束、清空、落盘持久化
- goal_set：目标落盘、锚点注入上下文、重复设定替换旧锚点（不累积）、无上下文时不崩
- 注册表：两个工具对 Coordinator 与 Follower 均可见
"""

import json

import pytest

from cloudra.core.agent import Follower
from cloudra.tools import get_tools_lst
from cloudra.tools.Plantool._store import agent_store_path
from cloudra.tools.Plantool.goal import GOAL_MARKER, GoalSet, GoalSet_input_schema
from cloudra.tools.Plantool.todo import TodoWrite, TodoWrite_input_schema
from cloudra.tools.Plantool.todo_read import TodoRead, TodoRead_input_schema


@pytest.fixture
def agent():
    return Follower(
        id="a-plan",
        name="planner",
        prompt="测试",
        query="测试问题",
        conversation_id="test-plan",
    )


def _read_store(agent, filename):
    with open(agent_store_path(agent, filename), encoding="utf-8") as f:
        return json.load(f)


class TestRegistry:
    def test_plan_tools_registered_and_visible_to_follower(self, agent):
        entries = get_tools_lst()
        names = {e.tool_name for e in entries}
        assert "todo_write" in names
        assert "goal_set" in names
        assert "todo_read" in names
        # Follower（默认仅 read 权限）也必须可见：规划工具权限为 NONE，人人可用
        visible = {e.tool_name for e in agent.get_available_tools(entries)}
        assert "todo_write" in visible
        assert "goal_set" in visible
        assert "todo_read" in visible


@pytest.mark.asyncio
class TestTodoWrite:
    async def test_write_assigns_ids_and_persists(self, agent, mock_session):
        tool = TodoWrite(subagent=agent)
        out = await tool.tool_call(TodoWrite_input_schema(todos=[
            {"content": "查文献", "status": "in_progress"},
            {"content": "跑计算", "status": "pending"},
        ]), mock_session)

        assert len(out.todos) == 2
        assert out.todos[0]["id"]  # 自动分配 id
        assert "Progress: 0/2 done" in out.result
        # 落盘
        stored = _read_store(agent, "todos.json")
        assert [t["content"] for t in stored] == ["查文献", "跑计算"]

    async def test_update_is_full_replace_and_keeps_ids(self, agent, mock_session):
        tool = TodoWrite(subagent=agent)
        first = await tool.tool_call(TodoWrite_input_schema(todos=[
            {"content": "查文献", "status": "in_progress"},
            {"content": "跑计算", "status": "pending"},
        ]), mock_session)
        todo_id = first.todos[0]["id"]

        second = await tool.tool_call(TodoWrite_input_schema(todos=[
            {"content": "查文献", "status": "done", "id": todo_id},
            {"content": "写报告", "status": "in_progress"},
        ]), mock_session)

        assert [t["content"] for t in second.todos] == ["查文献", "写报告"]  # 跑计算被替换掉
        assert second.todos[0]["id"] == todo_id  # 原 id 保留
        assert second.todos[1]["id"] != todo_id

    async def test_multiple_in_progress_demoted(self, agent, mock_session):
        tool = TodoWrite(subagent=agent)
        out = await tool.tool_call(TodoWrite_input_schema(todos=[
            {"content": "任务一", "status": "in_progress"},
            {"content": "任务二", "status": "in_progress"},
        ]), mock_session)

        statuses = [t["status"] for t in out.todos]
        assert statuses == ["in_progress", "pending"]

    async def test_empty_list_clears(self, agent, mock_session):
        tool = TodoWrite(subagent=agent)
        await tool.tool_call(TodoWrite_input_schema(todos=[
            {"content": "查文献", "status": "pending"},
        ]), mock_session)
        out = await tool.tool_call(TodoWrite_input_schema(todos=[]), mock_session)

        assert out.todos == []
        assert _read_store(agent, "todos.json") == []


@pytest.mark.asyncio
class TestTodoRead:
    async def test_read_returns_goal_and_todos(self, agent, mock_session):
        await GoalSet(subagent=agent).tool_call(
            GoalSet_input_schema(objective="完成 XX 体系的 DFT 计算"), mock_session
        )
        await TodoWrite(subagent=agent).tool_call(
            TodoWrite_input_schema(todos=[{"content": "查文献", "status": "in_progress"}]),
            mock_session,
        )

        out = await TodoRead(subagent=agent).tool_call(TodoRead_input_schema(), mock_session)
        assert "[Task goal] 完成 XX 体系的 DFT 计算" in out.result
        assert "查文献" in out.result
        assert out.todos[0]["content"] == "查文献"
        assert out.goal["objective"] == "完成 XX 体系的 DFT 计算"

    async def test_read_empty_when_no_plan(self, agent, mock_session):
        out = await TodoRead(subagent=agent).tool_call(TodoRead_input_schema(), mock_session)
        assert "empty list" in out.result
        assert out.todos == []
        assert out.goal == {}


@pytest.mark.asyncio
class TestTodoReminder:
    async def test_reminder_only_when_list_exists(self, agent, mock_session):
        assert agent._todo_reminder() == ""
        await TodoWrite(subagent=agent).tool_call(
            TodoWrite_input_schema(todos=[{"content": "查文献"}]),
            mock_session,
        )
        reminder = agent._todo_reminder()
        assert reminder
        assert "todo_read" in reminder

    async def test_injection_throttled_every_10_rounds(self, agent, mock_session):
        """提醒每 10 轮注入一次；无清单时不注入。"""
        await TodoWrite(subagent=agent).tool_call(
            TodoWrite_input_schema(todos=[{"content": "查文献"}]),
            mock_session,
        )
        agent._build_messages = __import__("unittest.mock").mock.AsyncMock(
            return_value=[{"role": "user", "content": "hi"}]
        )
        agent._get_tools_schema = lambda: []

        def _has_reminder(kwargs) -> bool:
            return any(
                m.get("role") == "system" and "todo_read" in str(m.get("content", ""))
                for m in kwargs["messages"]
            )

        hits = []
        for _round in range(1, 22):  # 模拟 21 轮推理
            kwargs = await agent._build_request_kwargs()
            hits.append(_has_reminder(kwargs))
        # 第 10、20 轮命中，其余不命中
        assert hits == [r % 10 == 0 for r in range(1, 22)]

    async def test_supervisor_opposition_forces_reminder(self, agent, mock_session):
        """supervisor 反对（force 标记）时，下一轮无条件注入提醒。"""
        await TodoWrite(subagent=agent).tool_call(
            TodoWrite_input_schema(todos=[{"content": "查文献"}]),
            mock_session,
        )
        agent._build_messages = __import__("unittest.mock").mock.AsyncMock(
            return_value=[{"role": "user", "content": "hi"}]
        )
        agent._get_tools_schema = lambda: []

        # 第 1 轮：不命中（非 10 的倍数）
        kwargs = await agent._build_request_kwargs()
        assert not any("todo_read" in str(m.get("content", "")) for m in kwargs["messages"])

        # supervisor 反对 → 第 2 轮强制命中
        agent._todo_reminder_force = True
        kwargs = await agent._build_request_kwargs()
        assert any("todo_read" in str(m.get("content", "")) for m in kwargs["messages"])
        # force 是一次性的：第 3 轮回到节流（不命中）
        kwargs = await agent._build_request_kwargs()
        assert not any("todo_read" in str(m.get("content", "")) for m in kwargs["messages"])

    async def test_request_kwargs_include_reminder_when_list_exists(self, agent, mock_session):
        from unittest.mock import AsyncMock

        await TodoWrite(subagent=agent).tool_call(
            TodoWrite_input_schema(todos=[{"content": "查文献"}]),
            mock_session,
        )
        agent._build_messages = AsyncMock(return_value=[{"role": "user", "content": "hi"}])
        agent._get_tools_schema = lambda: []
        # 强制在第 1 轮就注入，避免依赖 10 轮节流
        agent._todo_reminder_force = True

        kwargs = await agent._build_request_kwargs()
        reminder_msgs = [
            m for m in kwargs["messages"]
            if m.get("role") == "system" and "todo_read" in str(m.get("content", ""))
        ]
        assert reminder_msgs


@pytest.mark.asyncio
class TestGoalConfirm:
    async def test_goal_confirm_is_one_shot(self, agent, mock_session):
        """设过目标后，force 标记触发一次提醒文案。"""
        await GoalSet(subagent=agent).tool_call(
            GoalSet_input_schema(objective="完成计算"), mock_session
        )
        assert agent._goal_confirm_reminder() == ""
        agent._goal_confirm_force = True
        reminder = agent._goal_confirm_reminder()
        assert reminder
        assert "stop" in reminder
        assert "goal" in reminder
        # 一次性：force 已被消费
        assert agent._goal_confirm_reminder() == ""

    async def test_goal_confirm_requires_goal(self, agent):
        """未设过目标锚点时，即使 force 置位也不注入提醒。"""
        agent._goal_confirm_force = True
        assert agent._goal_confirm_reminder() == ""

    async def test_request_kwargs_include_goal_confirm(self, agent, mock_session):
        """reAct 无工具轮置 force 后，下一轮请求应携带目标确认提醒。"""
        from unittest.mock import AsyncMock

        await GoalSet(subagent=agent).tool_call(
            GoalSet_input_schema(objective="完成计算"), mock_session
        )
        agent._build_messages = AsyncMock(return_value=[{"role": "user", "content": "hi"}])
        agent._get_tools_schema = lambda: []
        agent._goal_confirm_force = True

        kwargs = await agent._build_request_kwargs()
        assert any(
            m.get("role") == "system" and "stop" in str(m.get("content", ""))
            for m in kwargs["messages"]
        )

    async def test_revived_after_stop_notice_injected(self, agent):
        """stop 后被唤醒的复核轮：提示优先回应用户，无用户要求才再次 stop。"""
        from unittest.mock import AsyncMock

        agent._build_messages = AsyncMock(return_value=[{"role": "user", "content": "hi"}])
        agent._get_tools_schema = lambda: []
        agent._revived_after_stop = True

        kwargs = await agent._build_request_kwargs()
        notices = [
            m for m in kwargs["messages"]
            if m.get("role") == "system" and "call stop again" in str(m.get("content", ""))
        ]
        assert notices
        text = str(notices[0].get("content", ""))
        assert "Answer the user first" in text
        assert "user" in text.lower()
        assert "Incoming call" in text
        # 非一次性：下一轮仍应注入（直到模型再次 stop）
        kwargs2 = await agent._build_request_kwargs()
        assert any(
            m.get("role") == "system" and "call stop again" in str(m.get("content", ""))
            for m in kwargs2["messages"]
        )

    async def test_revived_after_stop_notice_absent_by_default(self, agent):
        """未 stop 过的正常轮次不注入复核轮提示。"""
        from unittest.mock import AsyncMock

        agent._build_messages = AsyncMock(return_value=[{"role": "user", "content": "hi"}])
        agent._get_tools_schema = lambda: []

        kwargs = await agent._build_request_kwargs()
        assert not any(
            "call stop again" in str(m.get("content", "")) for m in kwargs["messages"]
        )


@pytest.mark.asyncio
class TestGoalSet:
    async def test_goal_persisted_and_pinned_to_context(self, agent, mock_session):
        await agent.get_context()  # 初始化 context_manager
        tool = GoalSet(subagent=agent)
        out = await tool.tool_call(GoalSet_input_schema(
            objective="完成 XX 体系的 DFT 计算",
            completion_criteria="能量收敛且报告写入 report.md",
        ), mock_session)

        assert out.goal["objective"] == "完成 XX 体系的 DFT 计算"
        assert _read_store(agent, "goal.json")["completion_criteria"] == "能量收敛且报告写入 report.md"

        context = await agent.get_context()
        goals = [
            m for m in context
            if m.get("role") == "system" and str(m.get("content", "")).startswith(GOAL_MARKER)
        ]
        assert len(goals) == 1
        assert "Completion criteria" in goals[0]["content"]

    async def test_second_set_replaces_old_anchor(self, agent, mock_session):
        await agent.get_context()
        tool = GoalSet(subagent=agent)
        await tool.tool_call(GoalSet_input_schema(objective="旧目标"), mock_session)
        await tool.tool_call(GoalSet_input_schema(objective="新目标"), mock_session)

        context = await agent.get_context()
        goals = [
            m for m in context
            if m.get("role") == "system" and str(m.get("content", "")).startswith(GOAL_MARKER)
        ]
        assert len(goals) == 1
        assert "新目标" in goals[0]["content"]
        assert _read_store(agent, "goal.json")["objective"] == "新目标"

    async def test_no_context_manager_does_not_crash(self, agent, mock_session):
        """上下文未初始化时只落盘，不注入、不报错。"""
        tool = GoalSet(subagent=agent)
        assert agent.context_manager is None
        out = await tool.tool_call(GoalSet_input_schema(objective="目标"), mock_session)
        assert out.goal["objective"] == "目标"
