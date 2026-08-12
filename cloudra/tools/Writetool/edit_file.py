"""基于旧文本精确匹配的结构化文件编辑工具。"""

from __future__ import annotations

import asyncio
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from cloudra.base.session_class import Session
from cloudra.base.tools_class import Tool, input_schema
from cloudra.persistence.workspace import TextEdit, WorkspaceConflictError, WorkspaceError
from cloudra.tools.core.coord_guard import handwritten_coord_warning
from cloudra.tools.core.workspace_mutation import (
    WorkspaceMutationOutput,
    execute_prepared_change,
    record_preparation_failure,
    workspace_for_tool,
)


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
        "对已有文本文件做基于旧文本精确匹配的结构化修改；每个 old_text 默认只能匹配一次，多匹配会被拒绝。"
        "适用：修改已有文件的局部内容——这是改文件的首选工具；必须先调用 text_reader 获取最新 sha256。"
        "不适用：新建文件或整文件覆写（用 text_writer）；严禁用 Bash、sed、重定向或临时脚本改文件。"
        "注意：向 .gjf/.xyz/.com 写入逐字键入的坐标块会被 harness 警告——坐标必须来自工具。"
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
        # 手写坐标守卫：命中时**照常编辑**，把警告附在返回消息里（不硬拦）。
        guard_warning = next(
            (
                warning
                for edit in user_input.edits
                if (warning := handwritten_coord_warning(edit.new_text, path=user_input.filepath))
            ),
            None,
        )
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

        out = await execute_prepared_change(
            self,
            service,
            change,
            session,
            action="精确编辑文本文件",
            tool_args=user_input.model_dump(mode="json"),
            output_class=EditFile_output_schema,
        )
        if guard_warning and out.is_written:
            out.message = f"{guard_warning}\n\n{out.message}"
        return out


def get_class():
    return EditFile
