"""TodoRead：查看当前 agent 的任务清单与目标锚点。

与 todo_write / goal_set 配对：模型在长任务中会因上下文压缩或工具结果滚出
窗口而丢失清单记忆，todo_read 让它在任何阶段都能重新取回当前计划，
避免偏离目标、重复或遗漏步骤。
"""

from typing import Any

from pydantic import Field

from cloudra.agent import Agent
from cloudra.session_class import Session
from cloudra.tools.Plantool._store import agent_store_path, load_json
from cloudra.tools.Plantool.goal import GoalSet
from cloudra.tools.Plantool.todo import TodoWrite
from cloudra.tools_class import Tool, input_schema, output_schema


class TodoRead_input_schema(input_schema):
    """todo_read 无需参数。"""


class TodoRead_output_schema(output_schema):
    result: str = Field(description="目标锚点与任务清单的可读文本。")
    todos: list = Field(default_factory=list, description="任务清单。")
    goal: dict = Field(default_factory=dict, description="目标锚点（未设定时为空 dict）。")


class TodoRead(Tool):
    tool_id: str = 't-42'
    tool_name: str = 'todo_read'
    tool_description: str = (
        "查看当前任务清单（todo list）与目标锚点。\n"
        "适用场景：多步骤任务中每轮开始前查看自己维护的清单，确认当前进行中的任务；"
        "上下文被压缩或长时间执行后重新取回计划，避免偏离目标。\n"
        "注意：本工具只读不写；更新清单请用 todo_write，设定目标请用 goal_set。"
    )
    input_schema: Any = TodoRead_input_schema
    output_schema: Any = TodoRead_output_schema
    subagent: Agent = None

    def is_read(self) -> bool:
        return True

    async def tool_call(
        self,
        user_input: TodoRead_input_schema,
        session: Session,
    ) -> TodoRead_output_schema:
        todos = load_json(agent_store_path(self.subagent, "todos.json"), default=[])
        goal = load_json(agent_store_path(self.subagent, "goal.json"), default={})

        parts: list[str] = []
        if goal:
            parts.append(GoalSet._format(goal))
        parts.append(TodoWrite._format(todos))
        result = "\n\n".join(parts)

        await self.record_session_event(session, "todo_read", {"todos": todos, "goal": goal})
        return TodoRead_output_schema(result=result, todos=todos, goal=goal)


def get_class():
    return TodoRead
