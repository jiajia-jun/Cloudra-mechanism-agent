"""Plantool 规划工具（todo_write / goal_set）钉板测试：

- todo_write：整体替换语义、id 自动分配与保留、in_progress 唯一软约束、清空、落盘持久化
- goal_set：目标落盘、重复设定覆盖 goal.json、无 message_history 时不崩
- 注册表：两个工具对 Coordinator 与 Follower 均可见
"""

import json

import pytest

from cloudra.tools import get_tools_lst
from cloudra.tools.Plantool._store import agent_store_path
from cloudra.tools.Plantool.goal import GoalSet, GoalSet_input_schema
from cloudra.tools.Plantool.todo import TodoWrite, TodoWrite_input_schema
from tests.dag_identity import make_session, make_subagent, projected_tool_names


@pytest.fixture
def agent():
    return make_subagent("test-plan", "small_mol")


def _read_store(agent, filename):
    with open(agent_store_path(agent, filename), encoding="utf-8") as f:
        return json.load(f)


class TestRegistry:
    def test_plan_tools_registered_and_visible_to_follower(self, agent):
        entries = get_tools_lst()
        names = {e.tool_name for e in entries}
        assert "todo_write" in names
        assert "goal_set" in names
        # 规划工具权限为 NONE，任何角色都可见：断言走线缆投影（唯一可见性口径）。
        visible = projected_tool_names(
            make_session("test-plan-visible", "small_mol", protocol="traditional")
        )
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


_TODO_REMINDER_MARKER = "maintaining a todo list"


@pytest.mark.asyncio
class TestGoalSet:
    async def test_goal_persisted(self, agent, mock_session):
        tool = GoalSet(subagent=agent)
        out = await tool.tool_call(GoalSet_input_schema(
            objective="完成 XX 体系的 DFT 计算",
            completion_criteria="能量收敛且报告写入 report.md",
        ), mock_session)

        assert out.goal["objective"] == "完成 XX 体系的 DFT 计算"
        assert _read_store(agent, "goal.json")["completion_criteria"] == "能量收敛且报告写入 report.md"

    async def test_second_set_replaces_goal_json(self, agent, mock_session):
        """重复设定直接覆盖 goal.json。"""
        tool = GoalSet(subagent=agent)
        await tool.tool_call(GoalSet_input_schema(objective="旧目标"), mock_session)
        await tool.tool_call(GoalSet_input_schema(objective="新目标"), mock_session)

        assert _read_store(agent, "goal.json")["objective"] == "新目标"

    async def test_no_conversation_history_dependency(self, agent, mock_session):
        """规划工具只落盘、不依赖会话历史：工具身份上没有 message_history 也要能跑。"""
        tool = GoalSet(subagent=agent)
        assert not hasattr(agent, "message_history")
        out = await tool.tool_call(GoalSet_input_schema(objective="目标"), mock_session)
        assert out.goal["objective"] == "目标"
