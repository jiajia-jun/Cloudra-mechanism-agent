"""Plantool 规划工具（todo_write / goal_set）钉板测试：

- todo_write：整体替换语义、id 自动分配与保留、in_progress 唯一软约束、清空、落盘持久化
- goal_set：目标落盘、锚点注入上下文、重复设定替换旧锚点（不累积）、无上下文时不崩
- 注册表：两个工具对 Coordinator 与 Follower 均可见
"""

import json

import pytest

from cloudra.agent import Follower
from cloudra.tools import get_tools_lst
from cloudra.tools.Plantool._store import agent_store_path
from cloudra.tools.Plantool.goal import GOAL_MARKER, GoalSet, GoalSet_input_schema
from cloudra.tools.Plantool.todo import TodoWrite, TodoWrite_input_schema


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
        # Follower（默认仅 read 权限）也必须可见：规划工具权限为 NONE，人人可用
        visible = {e.tool_name for e in agent.get_available_tools(entries)}
        assert "todo_write" in visible
        assert "goal_set" in visible


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
        assert "进度: 0/2 已完成" in out.result
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
        assert "完成判据" in goals[0]["content"]

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
