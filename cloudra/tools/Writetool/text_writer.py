from pydantic import Field
from typing import Any

from cloudra.session_class import Session
from cloudra.tools_class import Tool, input_schema, output_schema


description = (
    "以文本形式写入或覆写本地文件，支持 md、txt、json、py、sh 等纯文本格式。"
    "适用于写入脚本、文档、配置文件等场景。"
)


class TextWriter_input_schema(input_schema):
    filepath: str = Field(description="目标文件的绝对路径")
    content: str = Field(description="要写入的文本内容")


class TextWriter_output_schema(output_schema):
    is_writed: bool = Field(description="是否写入成功")
    filepath: str = Field(description="实际写入的文件路径")


class TextWriter(Tool):
    tool_id: str = 't-5'
    tool_name: str = 'text_writer'
    tool_description: str = description
    input_schema: Any = TextWriter_input_schema
    output_schema: Any = TextWriter_output_schema

    def is_write(self) -> bool:
        return True

    def is_destructive(self) -> bool:
        return True

    async def tool_call(self, user_input: TextWriter_input_schema, session: Session) -> TextWriter_output_schema:
        path = user_input.filepath
        content = user_input.content

        # 构造详细的申请信息，将修改内容贴出来给用户看
        details = (
            f"【动作】: 覆写文件\n"
            f"【目标路径】: {path}\n"
            f"【写入内容】: \n"
            f"--- START ---\n"
            f"{content}\n"
            f"--- END ---"
        )

        # 触发安全检查
        if not await self.ensure_safety(session, details=details):
            return TextWriter_output_schema(is_writed=False, filepath=path)

        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)
        return TextWriter_output_schema(is_writed=True, filepath=path)


def get_class():
    return TextWriter
