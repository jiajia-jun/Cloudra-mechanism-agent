"""TodoRead：查看当前 agent 的任务清单与目标锚点。

与 todo_write / goal_set 配对：模型在长任务中会因上下文压缩或工具结果滚出
窗口而丢失清单记忆，todo_read 让它在任何阶段都能重新取回当前计划，
避免偏离目标、重复或遗漏步骤。
"""

from typing import Any

from pydantic import Field

from cloudra.base.session_class import Session
from cloudra.base.tools_class import Tool, input_schema, output_schema
from cloudra.core.agent import Agent
from cloudra.tools.Plantool._store import agent_store_path, load_json
from cloudra.tools.Plantool.goal import GoalSet
from cloudra.tools.Plantool.todo import TodoWrite


class TodoRead_input_schema(input_schema):
    """todo_read 无需参数。"""


class TodoRead_output_schema(output_schema):
    result: str = Field(description="Readable text of the goal anchor and task list.")
    todos: list = Field(default_factory=list, description="Task list.")
    goal: dict = Field(default_factory=dict, description="Goal anchor (empty dict if unset).")


class TodoRead(Tool):
    tool_id: str = 't-33'
    tool_name: str = 'todo_read'
    tool_description: str = (
        "Read the current todo list and goal anchor.\n"
        "Use when: at the start of a round in a multi-step task, to check the list you maintain and confirm the in-progress item; "
        "or after context compaction / a long run, to recover the plan and avoid drifting off the goal.\n"
        "Note: this tool is read-only; update the list with todo_write, set the goal with goal_set."
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
