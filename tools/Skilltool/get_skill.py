from pydantic import Field
from typing import Any

from tools_class import Tool, input_schema, output_schema
from skill_class import skill_loader
from agent import Agent
from session_class import Session


class GetSkill_input_schema(input_schema):
    skill_name: str = Field(
        description="所需调用的Skill名称。"
    )
    other: str = Field(
        default="",
        description="在阅读skill后需要调用references时使用该参数，填入父skill中提到的ref名字。"
    )
    script_command: str = Field(
        default="",
        description="请根据你在skill中看到的指令来输入。"
    )
    RAG_keyword: str = Field(
        default="",
        description="暂不可用。在需要根据特定需求阅读长篇幅skill时，输入关键词检索有用的片段。"
    )


class GetSkill_output_schema(output_schema):
    content: str = Field(
        description="资料内容。"
    )
    result: str = Field(
        description="工具执行结果。"
    )


class GetSkill(Tool):

    tool_id: str = 't-5'
    tool_name: str = 'getskill'
    # NOTE: 这里先给一个静态兜底值，真正的动态描述在 __init__ 中根据 skills 目录内容拼接。
    # 由于 tool_schema_json 已改为实例方法，__init__ 里设置的 self.tool_description 会被 LLM 看到。
    tool_description: str = "通过这个工具获取skills。"
    input_schema: Any = GetSkill_input_schema
    output_schema: Any = GetSkill_output_schema

    def __init__(self, subagent: Agent = None, **data):
        super().__init__(**data)
        # NOTE: 在构造时扫描 skills 目录并动态生成 description，这样 LLM 每次看到的都是
        # 最新的可用 skills 列表。如果 skills 很多，这里可能会比较重；后续可考虑缓存。
        loader = skill_loader()
        skill_lst = loader.skill_datas_get()
        skill_metadata_str = ''
        for skill in skill_lst:
            skill_str = f'''
            name : {skill['name']}
            description: {skill['description']}
            \n
            '''
            skill_metadata_str += skill_str

        self.tool_description = f'''
        通过这个工具获取skills。以下是你能够调用的skills:
        {skill_metadata_str}
        '''

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
                content="",
                result=f"Skill '{skill_name}' 不存在。"
            )

        result = f"成功获取 Skill '{skill_name}' 的内容。"

        # NOTE: other 参数用于读取 skill 的 reference 附件。由于 reference 可能是文件或文件夹，
        # 这里直接把内容拼接到 content 里返回，让 LLM 在同一轮上下文里看到完整资料。
        if other:
            ref_content = loader.get_reference(skill_name, other)
            content += f"\n\n--- Reference: {other} ---\n\n{ref_content}"
            result += f" 并获取了 reference '{other}'。"

        return GetSkill_output_schema(
            content=content,
            result=result
        )


def get_class():
    return GetSkill
