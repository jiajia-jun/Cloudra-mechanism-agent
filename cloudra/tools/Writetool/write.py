import asyncio
from typing import Any

from pydantic import Field

from cloudra.base.session_class import Session
from cloudra.base.tools_class import Tool, input_schema
from cloudra.persistence.workspace import WorkspaceConflictError, WorkspaceError
from cloudra.tools.core.coord_guard import handwritten_coord_warning
from cloudra.tools.core.workspace_mutation import (
    WorkspaceMutationOutput,
    execute_prepared_change,
    record_preparation_failure,
    workspace_for_tool,
)

description = (
    "Create or wholesale-overwrite a UTF-8 text file in the Agent working directory; "
    "pass expected_sha256='missing' for a new file, and call text_reader first to get the latest sha256 before overwriting. "
    "Use for: creating a new file, or rewriting an existing file in full. "
    "Do not use for: local edits to an existing file (use text_reader + edit_file); never write files with bash redirection instead of this tool. "
    "Note: writing hand-typed coordinate blocks into .gjf/.xyz/.com triggers a harness warning — "
    "coordinates must come from tools such as smiles_to_mol / format_converter / qm_input_writer."
)


class Write_input_schema(input_schema):
    path: str = Field(description="Target file path relative to the Agent working directory")
    content: str = Field(description="Text content to write")
    expected_sha256: str = Field(
        default="missing",
        description="Pass missing for a new file; for overwrite, pass the sha256 returned by text_reader",
    )


class Write_output_schema(WorkspaceMutationOutput):
    pass


class Write(Tool):
    tool_id: str = 't-5'
    tool_name: str = 'write'
    tool_description: str = description
    input_schema: Any = Write_input_schema
    output_schema: Any = Write_output_schema

    def is_write(self) -> bool:
        return True

    def is_destructive(self) -> bool:
        # 写入文件通常仅需 WRITE 权限。
        # 之前设为 True 会导致没有 DESTRUCTIVE 权限的 Writer 等 Agent 无法看到此工具。
        return False

    async def tool_call(self, user_input: Write_input_schema, session: Session) -> Write_output_schema:
        # 手写坐标守卫：命中时**照常写入**，把警告附在返回消息里让模型意识到
        # 行为不当（不硬拦——改 gjf 关键词等正当编辑不该被误伤）。
        guard_warning = handwritten_coord_warning(user_input.content, path=user_input.path)
        service = workspace_for_tool(self)
        try:
            change = await asyncio.to_thread(
                service.prepare_write,
                user_input.path,
                user_input.content,
                user_input.expected_sha256,
            )
        except WorkspaceConflictError as exc:
            await record_preparation_failure(
                self,
                session,
                user_input.path,
                "conflict",
                str(exc),
            )
            return Write_output_schema(
                is_written=False,
                filepath=user_input.path,
                status="conflict",
                message=str(exc),
            )
        except (OSError, WorkspaceError) as exc:
            await record_preparation_failure(
                self,
                session,
                user_input.path,
                "failed",
                str(exc),
            )
            return Write_output_schema(
                is_written=False,
                filepath=user_input.path,
                status="failed",
                message=str(exc),
            )

        out = await execute_prepared_change(
            self,
            service,
            change,
            session,
            action="新建或整文件覆写文本",
            tool_args=user_input.model_dump(mode="json"),
            output_class=Write_output_schema,
        )
        if guard_warning and out.is_written:
            out.message = f"{guard_warning}\n\n{out.message}"
        return out


def get_class():
    return Write
