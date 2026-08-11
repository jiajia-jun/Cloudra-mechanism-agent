import asyncio
from typing import Any

from pydantic import Field

from cloudra.base.session_class import Session
from cloudra.base.tools_class import Tool, input_schema, output_schema
from cloudra.persistence.workspace import WorkspaceError, WorkspaceService

description = (
    "安全读取 Agent 工作目录内的 UTF-8 文本文件，返回内容切片与完整文件 sha256；"
    "支持指定起始行与结束行进行切片。"
    "适用：查看代码、日志、配置等文本文件；也是 edit_file / text_writer 修改前的必经步骤。"
    "不适用：二进制文档（PDF/Word 用 pdf2md）、图片（用 image_reader）。"
    "注意：修改文件前必须先调用本工具获取最新 sha256。"
)


class TextReader_input_schema(input_schema):
    filepath: str = Field(description="相对 Agent 工作目录的文件路径")
    start_line: int = Field(default=0, description="起始行号，左闭，从 0 开始")
    end_line: int = Field(default=-1, description="结束行号，左开；-1 表示读到末尾")


class TextReader_output_schema(output_schema):
    content: str = Field(description="读取到的文本内容")
    filepath: str = Field(default="", description="规范化后的工作区相对路径")
    sha256: str = Field(default="", description="完整文件原始字节的 SHA256")
    total_lines: int = Field(default=0, description="完整文件总行数")
    start_line: int = Field(default=0, description="实际切片起始行")
    end_line: int = Field(default=0, description="实际切片结束行")
    message: str = Field(default="", description="错误或状态信息")


class TextReader(Tool):
    tool_id: str = 't-2'
    tool_name: str = 'text_reader'
    tool_description: str = description
    input_schema: Any = TextReader_input_schema
    output_schema: Any = TextReader_output_schema

    def is_read(self) -> bool:
        return True

    async def tool_call(self, user_input: TextReader_input_schema, session: Session) -> TextReader_output_schema:
        root = getattr(self.subagent, "working_directory", None)
        if not root:
            import os

            root = os.getcwd()
        try:
            service = WorkspaceService(root)
            snapshot, content, total, start, end = await asyncio.to_thread(
                service.read_text,
                user_input.filepath,
                user_input.start_line,
                user_input.end_line,
            )
        except (OSError, WorkspaceError) as exc:
            return TextReader_output_schema(
                content="",
                filepath=user_input.filepath,
                message=str(exc),
            )
        return TextReader_output_schema(
            content=content,
            filepath=snapshot.relative_path,
            sha256=snapshot.sha256,
            total_lines=total,
            start_line=start,
            end_line=end,
        )


def get_class():
    return TextReader
