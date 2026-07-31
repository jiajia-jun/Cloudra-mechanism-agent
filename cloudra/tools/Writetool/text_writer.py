import asyncio
from typing import Any

from pydantic import Field

from cloudra.session_class import Session
from cloudra.tools.core.workspace_mutation import (
    WorkspaceMutationOutput,
    execute_prepared_change,
    record_preparation_failure,
    workspace_for_tool,
)
from cloudra.tools_class import Tool, input_schema
from cloudra.workspace import WorkspaceConflictError, WorkspaceError

description = (
    "在 Agent 工作目录内新建或整文件覆写 UTF-8 文本；"
    "新建传 expected_sha256='missing'，覆写前必须先用 text_reader 获取最新 sha256。"
    "适用：创建新文件，或对已有文件做整体重写。"
    "不适用：已有文件的局部修改（用 text_reader + edit_file）；严禁用 bash 重定向代替本工具写文件。"
)


class TextWriter_input_schema(input_schema):
    filepath: str = Field(description="相对 Agent 工作目录的目标文件路径")
    content: str = Field(description="要写入的文本内容")
    expected_sha256: str = Field(
        default="missing",
        description="新建文件传 missing；覆写已有文件传 text_reader 返回的 sha256",
    )


class TextWriter_output_schema(WorkspaceMutationOutput):
    pass


class TextWriter(Tool):
    tool_id: str = 't-5'
    tool_name: str = 'text_writer'
    tool_description: str = description
    input_schema: Any = TextWriter_input_schema
    output_schema: Any = TextWriter_output_schema

    def is_write(self) -> bool:
        return True

    def is_destructive(self) -> bool:
        # 写入文件通常仅需 WRITE 权限。
        # 之前设为 True 会导致没有 DESTRUCTIVE 权限的 Writer 等 Agent 无法看到此工具。
        return False

    async def tool_call(self, user_input: TextWriter_input_schema, session: Session) -> TextWriter_output_schema:
        service = workspace_for_tool(self)
        try:
            change = await asyncio.to_thread(
                service.prepare_write,
                user_input.filepath,
                user_input.content,
                user_input.expected_sha256,
            )
        except WorkspaceConflictError as exc:
            await record_preparation_failure(
                self,
                session,
                user_input.filepath,
                "conflict",
                str(exc),
            )
            return TextWriter_output_schema(
                is_written=False,
                filepath=user_input.filepath,
                status="conflict",
                message=str(exc),
            )
        except (OSError, WorkspaceError) as exc:
            await record_preparation_failure(
                self,
                session,
                user_input.filepath,
                "failed",
                str(exc),
            )
            return TextWriter_output_schema(
                is_written=False,
                filepath=user_input.filepath,
                status="failed",
                message=str(exc),
            )

        return await execute_prepared_change(
            self,
            service,
            change,
            session,
            action="新建或整文件覆写文本",
            tool_args=user_input.model_dump(mode="json"),
            output_class=TextWriter_output_schema,
        )


def get_class():
    return TextWriter
