from typing import Any

from pydantic import Field

from cloudra.session_class import Session
from cloudra.tools_class import Tool, input_schema, output_schema

description = (
    "以文本形式读取本地文件，支持 md、txt、json、gjf、py、sh 等纯文本格式。"
    "支持指定起始行与结束行进行切片阅读。"
)


class TextReader_input_schema(input_schema):
    filepath: str = Field(description="要读取的文件绝对路径")
    start_line: int = Field(default=0, description="起始行号，左闭，从 0 开始")
    end_line: int = Field(default=-1, description="结束行号，左开；-1 表示读到末尾")


class TextReader_output_schema(output_schema):
    content: str = Field(description="读取到的文本内容")


class TextReader(Tool):
    tool_id: str = 't-2'
    tool_name: str = 'text_reader'
    tool_description: str = description
    input_schema: Any = TextReader_input_schema
    output_schema: Any = TextReader_output_schema

    def is_read(self) -> bool:
        return True

    async def tool_call(self, user_input: TextReader_input_schema, session: Session) -> TextReader_output_schema:
        path = user_input.filepath
        start_line = user_input.start_line
        end_line = user_input.end_line

        with open(path, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        total_lines = len(lines)

        # 修正切片逻辑
        actual_start = max(0, start_line)
        if end_line == -1:
            actual_end = total_lines
        else:
            actual_end = min(end_line, total_lines)

        if actual_start >= actual_end:
            return TextReader_output_schema(content=f'切片范围 [{actual_start}:{actual_end}] 无效或为空。')

        selected_lines = lines[actual_start:actual_end]
        # 直接拼接，因为 lines 已经包含了 \n
        content_str = ''.join(selected_lines)

        return TextReader_output_schema(content=content_str)


def get_class():
    return TextReader
