"""GoalSet：per-agent 目标锚点工具。

长任务中模型容易在中途丢失原始目标（尤其上下文压缩之后）。设定 goal 后
会作为带标记的 system 消息固定在上下文中（重复设定会替换旧锚点，不累积），
Supervisor 审查与后续推理都能持续看到。
"""

from typing import Any

from pydantic import Field

from cloudra.base.session_class import Session
from cloudra.base.tools_class import Tool, input_schema, output_schema
from cloudra.core.agent import Agent
from cloudra.tools.Plantool._store import agent_store_path, save_json

# 目标锚点消息的内容前缀：重复设定时据此识别并替换旧锚点
GOAL_MARKER = "[Task goal]"


class GoalSet_input_schema(input_schema):
    objective: str = Field(description="One sentence: what this task should achieve.")
    completion_criteria: str = Field(
        default="",
        description="Verifiable completion criteria (what counts as done). Recommended, to keep the goal concrete.",
    )
    current_focus: str = Field(
        default="",
        description="Focus of the current stage (optional; used to correct direction mid-task).",
    )


class GoalSet_output_schema(output_schema):
    result: str = Field(description="Tool result.")
    goal: dict = Field(description="The updated full goal anchor.")


class GoalSet(Tool):
    tool_id: str = 't-41'
    tool_name: str = 'goal_set'
    tool_description: str = (
        "Set or update the current task's goal anchor.\n"
        "Use when: a long task starts and you need a clear objective and completion criteria; "
        "or when direction changes or a new stage begins. "
        "Once set, the goal is pinned as a system message (a later set replaces the old anchor), "
        "so it remains available even after history is compacted.\n"
        "Do not use this tool for a simple one-step task."
    )
    input_schema: Any = GoalSet_input_schema
    output_schema: Any = GoalSet_output_schema
    subagent: Agent = None

    @staticmethod
    def _format(goal: dict) -> str:
        lines = [f"{GOAL_MARKER} {goal['objective']}"]
        if goal.get("completion_criteria"):
            lines.append(f"Completion criteria: {goal['completion_criteria']}")
        if goal.get("current_focus"):
            lines.append(f"Current focus: {goal['current_focus']}")
        return "\n".join(lines)

    async def tool_call(
        self,
        user_input: GoalSet_input_schema,
        session: Session,
    ) -> GoalSet_output_schema:
        goal = {
            "objective": user_input.objective,
            "completion_criteria": user_input.completion_criteria,
            "current_focus": user_input.current_focus,
        }
        save_json(agent_store_path(self.subagent, "goal.json"), goal)
        await self.record_session_event(session, "goal_updated", {"goal": goal})
        return GoalSet_output_schema(
            result=f"Goal anchor set:\n{self._format(goal)}",
            goal=goal,
        )


def get_class():
    return GoalSet
