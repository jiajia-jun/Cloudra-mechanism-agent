import asyncio
from typing import Any

from pydantic import Field

from cloudra.base.session_class import Session
from cloudra.base.tools_class import Tool, input_schema, output_schema
from cloudra.persistence.workspace import WorkspaceError, WorkspaceService

description = (
    "Safely read a UTF-8 text file in the Agent working directory; returns a content slice and the full-file sha256. "
    "Supports slicing by start and end line. "
    "Use for: viewing code, logs, configs, and other text files; also required before edit_file / text_writer. "
    "Do not use for: binary documents (PDF/Word via pdf2md) or images (use image_reader). "
    "Note: you must call this tool to get the latest sha256 before modifying a file. "
    "Oversized slices are truncated; page through large files with start_line/end_line."
)

# 超大切片护栏：单次返回超过阈值就截断并提示按行分页，
# 避免整文件返回把上下文顶爆触发有损压缩。
MAX_CONTENT_CHARS = 30_000


class TextReader_input_schema(input_schema):
    filepath: str = Field(description="File path relative to the Agent working directory")
    start_line: int = Field(default=0, description="Start line, inclusive, 0-based")
    end_line: int = Field(default=-1, description="End line, exclusive; -1 means read to EOF")


class TextReader_output_schema(output_schema):
    is_success: bool = Field(default=True, description="Whether the read succeeded; False means content is empty and message holds the error")
    content: str = Field(default="", description="Text content that was read")
    filepath: str = Field(default="", description="Normalized workspace-relative path")
    sha256: str = Field(default="", description="SHA256 of the full file's raw bytes")
    total_lines: int = Field(default=0, description="Total line count of the full file")
    start_line: int = Field(default=0, description="Actual slice start line")
    end_line: int = Field(default=0, description="Actual slice end line")
    message: str = Field(default="", description="Error or status message")


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
                is_success=False,
                filepath=user_input.filepath,
                message=str(exc),
            )
        message = ""
        if len(content) > MAX_CONTENT_CHARS:
            content = (
                content[:MAX_CONTENT_CHARS]
                + f"\n[Truncated: slice is {total} lines; showing first {MAX_CONTENT_CHARS} chars. "
                "Page through the rest with start_line/end_line.]"
            )
            message = (
                f"Content truncated to {MAX_CONTENT_CHARS} chars; "
                "use start_line/end_line to page through the file."
            )
        return TextReader_output_schema(
            content=content,
            filepath=snapshot.relative_path,
            sha256=snapshot.sha256,
            total_lines=total,
            start_line=start,
            end_line=end,
            message=message,
        )


def get_class():
    return TextReader
