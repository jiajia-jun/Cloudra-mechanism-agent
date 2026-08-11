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
GOAL_MARKER = "【任务目标】"


class GoalSet_input_schema(input_schema):
    objective: str = Field(description="一句话说明当前任务要达成什么。")
    completion_criteria: str = Field(
        default="",
        description="可验证的完成判据（什么样算做完）。建议填写，避免目标含糊。",
    )
    current_focus: str = Field(
        default="",
        description="当前阶段的聚焦点（可选，用于长任务中途校正方向）。",
    )


class GoalSet_output_schema(output_schema):
    result: str = Field(description="工具执行结果。")
    goal: dict = Field(description="更新后的完整目标锚点。")


class GoalSet(Tool):
    tool_id: str = 't-41'
    tool_name: str = 'goal_set'
    tool_description: str = (
        "设定或更新当前任务的目标锚点。\n"
        "适用场景：长任务开始时明确目标与完成判据；方向调整或阶段切换时更新。"
        "设定后目标会作为系统提示固定在上下文中（重复设定替换旧锚点），"
        "即使历史被压缩也能持续参考。\n"
        "单步即可完成的简单任务不要使用本工具。"
    )
    input_schema: Any = GoalSet_input_schema
    output_schema: Any = GoalSet_output_schema
    subagent: Agent = None

    @staticmethod
    def _format(goal: dict) -> str:
        lines = [f"{GOAL_MARKER} {goal['objective']}"]
        if goal.get("completion_criteria"):
            lines.append(f"完成判据: {goal['completion_criteria']}")
        if goal.get("current_focus"):
            lines.append(f"当前聚焦: {goal['current_focus']}")
        return "\n".join(lines)

    async def _pin_to_context(self, goal: dict) -> None:
        """把目标锚点写入上下文（替换旧锚点）；上下文未初始化时跳过。"""
        if self.subagent is None:
            return
        cm = getattr(self.subagent, "context_manager", None)
        if cm is None:
            return
        context = await cm.load()
        context = [
            msg for msg in context
            if not (
                msg.get("role") == "system"
                and str(msg.get("content", "")).startswith(GOAL_MARKER)
            )
        ]
        context.append({"role": "system", "content": self._format(goal)})
        await cm.replace(context)

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
        await self._pin_to_context(goal)
        await self.record_session_event(session, "goal_updated", {"goal": goal})
        return GoalSet_output_schema(
            result=f"目标锚点已设定：\n{self._format(goal)}",
            goal=goal,
        )


def get_class():
    return GoalSet
