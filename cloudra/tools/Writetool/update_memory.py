from pydantic import Field
from typing import Any

from cloudra.agent import Agent
from cloudra.memory import get_memory_manager
from cloudra.session_class import Session
from cloudra.tools_class import Tool, input_schema, output_schema


description = (
    "更新 Coordinator 的长期记忆（MEMORY.md）。当 Coordinator 在任务执行过程中"
    "获得新的技能提醒、经验教训或最佳实践时，调用此工具将其持久化。"
    "记忆会在 Coordinator 启动时自动加载到上下文中，帮助后续任务复用经验。"
    "当记忆字数超过阈值时，系统会自动压缩并归档。"
)


class UpdateMemory_input_schema(input_schema):
    lesson: str = Field(
        description=(
            "要记录的经验或技能提醒。应简洁、具体、可复用，例如："
            "'调用 Gaussian 做 TS 搜索前，必须先做柔性扫描并保存初猜结构；' "
            "'解析 VASP OUTCAR 时优先读取 MAGMOM 列来判断磁性。'"
        )
    )
    source: str = Field(
        default="",
        description="经验来源，例如子 Agent 名称、session_id 或任务描述。"
    )
    skill_name: str = Field(
        default="",
        description="可选的技能分类标签，例如 'dft-calculation'、'literature-search'。"
    )


class UpdateMemory_output_schema(output_schema):
    result: str = Field(description="记忆更新结果")
    word_count: int = Field(default=0, description="当前 MEMORY.md 的估算字数")


class UpdateMemory(Tool):
    tool_id: str = 't-26'
    tool_name: str = 'update_memory'
    tool_description: str = description
    input_schema: Any = UpdateMemory_input_schema
    output_schema: Any = UpdateMemory_output_schema
    subagent: Agent = None

    def is_write(self) -> bool:
        return True

    async def tool_call(
        self,
        user_input: UpdateMemory_input_schema,
        session: Session
    ) -> UpdateMemory_output_schema:
        conv_id = getattr(self.subagent, 'conversation_id', None) if self.subagent else None
        manager = get_memory_manager(conversation_id=conv_id)

        result = manager.append_lesson(
            lesson=user_input.lesson,
            source=user_input.source,
            skill_name=user_input.skill_name,
        )

        return UpdateMemory_output_schema(
            result=result,
            word_count=manager._count_words(manager.load()),
        )


def get_class():
    return UpdateMemory
