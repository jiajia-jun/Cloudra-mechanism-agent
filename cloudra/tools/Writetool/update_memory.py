from typing import Any

from pydantic import Field

from cloudra.base.session_class import Session
from cloudra.base.tool_actor import ToolActorContext
from cloudra.base.tools_class import Tool, input_schema, output_schema
from cloudra.persistence.memory import get_memory_manager

description = (
    "Append lessons learned and best practices from this task to the Coordinator's long-term memory (MEMORY.md); "
    "memory is loaded into context when the Coordinator starts, and is compacted/archived when it exceeds the size threshold. "
    "Use for: capturing reusable experience after a task (e.g. pitfalls of a calculation class, usage notes for a tool) for later tasks. "
    "Do not use for: recording ephemeral intermediate results of this task (write workspace files with write) or loading an existing skill SOP (use get_skill). "
    "MEMORY.md is global — it is injected into EVERY project's Coordinator. Lessons must be project-agnostic: "
    "no absolute paths, project names, or job IDs; the guard rejects project-specific content and asks for a generic rewrite."
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
    is_success: bool = Field(default=True, description="Whether the memory write succeeded")
    result: str = Field(description="Memory-update result")
    word_count: int = Field(default=0, description="Estimated word count of the current MEMORY.md")


class UpdateMemory(Tool):
    tool_id: str = 't-34'
    tool_name: str = 'update_memory'
    tool_description: str = description
    input_schema: Any = UpdateMemory_input_schema
    output_schema: Any = UpdateMemory_output_schema
    subagent: ToolActorContext | None = None

    def is_write(self) -> bool:
        return True

    async def tool_call(
        self,
        user_input: UpdateMemory_input_schema,
        session: Session
    ) -> UpdateMemory_output_schema:
        from cloudra.tools.core.memory_scope_guard import find_project_specific_fragments

        fragments = find_project_specific_fragments(user_input.lesson)
        if fragments:
            return UpdateMemory_output_schema(
                is_success=False,
                result=(
                    "Rejected: MEMORY.md is global and injected into every project's Coordinator, "
                    "so lessons must be project-agnostic. These fragments look project-specific: "
                    + "; ".join(fragments)
                    + ". Rewrite the lesson in generic, reusable terms (no absolute paths, project "
                    "names, or job IDs) and call update_memory again."
                ),
            )
        conv_id = getattr(self.subagent, 'conversation_id', None) if self.subagent else None
        manager = get_memory_manager(conversation_id=conv_id)

        result = await manager.append_lesson(
            lesson=user_input.lesson,
            source=user_input.source,
            skill_name=user_input.skill_name,
        )

        return UpdateMemory_output_schema(
            is_success=True,
            result=result,
            word_count=manager._count_words(manager.load()),
        )
