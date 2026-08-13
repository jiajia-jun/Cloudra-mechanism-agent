from typing import Any

from pydantic import Field

from cloudra.base.session_class import Session
from cloudra.base.tools_class import Tool, input_schema, output_schema
from cloudra.core.agent import Agent
from cloudra.persistence.memory import get_memory_manager

description = (
    "Append lessons learned and best practices from this task to the Coordinator's long-term memory (MEMORY.md); "
    "memory is loaded into context when the Coordinator starts, and is compacted/archived when it exceeds the size threshold. "
    "Use for: capturing reusable experience after a task (e.g. pitfalls of a calculation class, usage notes for a tool) for later tasks. "
    "Do not use for: recording ephemeral intermediate results of this task (write workspace files with text_writer) or loading an existing skill SOP (use getskill)."
)


class UpdateMemory_input_schema(input_schema):
    lesson: str = Field(
        description=(
            "The lesson or skill reminder to record. Keep it concise, specific, and reusable, e.g.: "
            "'Before a Gaussian TS search, run a relaxed scan and save the guess geometry;' "
            "'When parsing a VASP OUTCAR, prefer the MAGMOM column to judge magnetism.'"
        )
    )
    source: str = Field(
        default="",
        description="Source of the lesson, e.g. a sub-agent name, session_id, or task description."
    )
    skill_name: str = Field(
        default="",
        description="Optional skill category tag, e.g. 'dft-calculation', 'literature-search'."
    )


class UpdateMemory_output_schema(output_schema):
    result: str = Field(description="Memory-update result")
    word_count: int = Field(default=0, description="Estimated word count of the current MEMORY.md")


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

        result = await manager.append_lesson(
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
