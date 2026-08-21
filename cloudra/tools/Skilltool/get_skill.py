from typing import Any

from pydantic import Field

from cloudra.base.session_class import Session
from cloudra.base.skill_class import skill_loader
from cloudra.base.tools_class import Tool, input_schema, output_schema


class GetSkill_input_schema(input_schema):
    skill_name: str = Field(
        description="Name of the skill to load."
    )
    other: str = Field(
        default="",
        description="After reading a skill, pass this to load a reference mentioned in the parent skill (the ref name)."
    )


class GetSkill_output_schema(output_schema):
    is_success: bool = Field(
        description="Whether the skill content was loaded."
    )
    content: str = Field(
        description="Loaded skill content."
    )
    result: str = Field(
        description="Tool result."
    )


class GetSkill(Tool):

    tool_id: str = 't-25'
    tool_name: str = 'getskill'
    # NOTE: description 保持惰性，不内嵌 skill 清单——system prompt 的
    # "Current skill manifest" 区块已对所有角色注入同一份清单，
    # 这里再列一遍会让每个请求带上双份。
    tool_description: str = (
        "Load the full SOP for a named skill. A skill carries domain knowledge and workflow: "
        "before starting any task that has a matching skill (e.g. DFT, molecular dynamics, paper writing, literature search), "
        "you must call this tool to load that skill and follow its procedure, completion criteria, and caveats. "
        "See the \"Current skill manifest\" section of the system prompt for the available skill names "
        "and pass one as skill_name. "
        "When the skill mentions references, pass the ref name in other to read the corresponding reference file."
    )
    input_schema: Any = GetSkill_input_schema
    output_schema: Any = GetSkill_output_schema

    def is_read(self) -> bool:
        return True

    async def tool_call(
        self,
        user_input: GetSkill_input_schema,
        session: Session
    ) -> GetSkill_output_schema:
        loader = skill_loader()
        skill_name = user_input.skill_name
        other = user_input.other

        content = loader.get_content(skill_name)
        if content == 'skill不存在。':
            return GetSkill_output_schema(
                is_success=False,
                content="",
                result=f"Skill '{skill_name}' does not exist."
            )

        result = f"Loaded skill '{skill_name}'."

        # NOTE: other 参数用于读取 skill 的 reference 附件。由于 reference 可能是文件或文件夹，
        # 这里直接把内容拼接到 content 里返回，让 LLM 在同一轮上下文里看到完整资料。
        if other:
            ref_content = loader.get_reference(skill_name, other)
            content += f"\n\n--- Reference: {other} ---\n\n{ref_content}"
            result += f" Also loaded reference '{other}'."

        return GetSkill_output_schema(
            is_success=True,
            content=content,
            result=result
        )


def get_class():
    return GetSkill
