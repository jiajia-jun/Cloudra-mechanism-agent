"""基于旧文本精确匹配的结构化文件编辑工具。"""

from __future__ import annotations

import asyncio
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from cloudra.session_class import Session
from cloudra.tools.core.workspace_mutation import (
    WorkspaceMutationOutput,
    execute_prepared_change,
    record_preparation_failure,
    workspace_for_tool,
)
from cloudra.tools_class import Tool, input_schema
from cloudra.workspace import TextEdit, WorkspaceConflictError, WorkspaceError


class EditOperation(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    old_text: str = Field(
        alias="old_str",
        description="需要替换的原文本；默认必须在当前文件中唯一匹配",
    )
    new_text: str = Field(
        alias="new_str",
        description="替换后的文本",
    )
    replace_all: bool = Field(
        default=False,
        description="是否替换全部匹配；默认 false，匹配多次时拒绝编辑",
    )


class EditFile_input_schema(input_schema):
    filepath: str = Field(description="相对 Agent 工作目录的目标文件路径")
    expected_sha256: str = Field(description="最近一次 text_reader 返回的完整文件 sha256")
    edits: list[EditOperation] = Field(description="按顺序执行的精确文本替换")


class EditFile_output_schema(WorkspaceMutationOutput):
    pass


class EditFile(Tool):
    tool_id: str = "t-edit"
    tool_name: str = "edit_file"
    tool_description: str = (
        "精确修改工作目录内已有文本文件。必须先调用 text_reader 获取最新 sha256；"
        "每个 old_text 默认只能匹配一次。不要使用 Bash、sed、重定向或临时脚本修改文件。"
    )
    input_schema: Any = EditFile_input_schema
    output_schema: Any = EditFile_output_schema

    def is_write(self) -> bool:
        return True

    async def tool_call(
        self,
        user_input: EditFile_input_schema,
        session: Session,
    ) -> EditFile_output_schema:
        service = workspace_for_tool(self)
        edits = [
            TextEdit(
                old_text=edit.old_text,
                new_text=edit.new_text,
                replace_all=edit.replace_all,
            )
            for edit in user_input.edits
        ]
        try:
            change = await asyncio.to_thread(
                service.prepare_edit,
                user_input.filepath,
                user_input.expected_sha256,
                edits,
            )
        except WorkspaceConflictError as exc:
            await record_preparation_failure(
                self,
                session,
                user_input.filepath,
                "conflict",
                str(exc),
            )
            return EditFile_output_schema(
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
            return EditFile_output_schema(
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
            action="精确编辑文本文件",
            tool_args=user_input.model_dump(mode="json"),
            output_class=EditFile_output_schema,
        )


def get_class():
    return EditFile
