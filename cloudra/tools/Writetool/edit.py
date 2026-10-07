"""基于旧文本精确匹配的结构化文件编辑工具。"""

from __future__ import annotations

import asyncio
from typing import Any

from pydantic import AliasChoices, BaseModel, ConfigDict, Field

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
        validation_alias=AliasChoices("old_string", "old_str", "old_text"),
        serialization_alias="old_string",
        description="Original text to replace; must match uniquely by default",
    )
    new_text: str = Field(
        validation_alias=AliasChoices("new_string", "new_str", "new_text"),
        serialization_alias="new_string",
        description="Replacement text",
    )
    replace_all: bool = Field(
        default=False,
        description="Whether to replace every match; default false, and the edit is rejected if there are multiple matches",
    )


class Edit_input_schema(input_schema):
    path: str = Field(description="Target file path relative to the Agent working directory")
    expected_sha256: str = Field(description="Full-file sha256 returned by the latest read call")
    edits: list[EditOperation] = Field(description="Exact text replacements to apply in order")


class Edit_output_schema(WorkspaceMutationOutput):
    pass


class Edit(Tool):
    tool_id: str = "t-edit"
    tool_name: str = "edit"
    tool_description: str = (
        "Structured edit of an existing text file by exact old-text match; each old_text must match once by default, and multiple matches are rejected. "
        "Use for: local edits to existing files — this is the preferred file-edit tool; call read first to get the latest sha256. "
        "Do not use for: creating a file or rewriting it wholesale (use write); never edit files with Bash, sed, redirection, or throwaway scripts. "
        "Note: writing hand-typed coordinate blocks into .gjf/.xyz/.com triggers a harness warning — coordinates must come from tools."
    )
    input_schema: Any = Edit_input_schema
    output_schema: Any = Edit_output_schema

    def is_write(self) -> bool:
        return True

    async def tool_call(
        self,
        user_input: Edit_input_schema,
        session: Session,
    ) -> Edit_output_schema:
        service = workspace_for_tool(self)
        # 手写坐标守卫：命中时**照常编辑**，把警告附在返回消息里（不硬拦）。
        guard_warning = next(
            (
                warning
                for edit in user_input.edits
                if (warning := handwritten_coord_warning(edit.new_text, path=user_input.path))
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
                user_input.path,
                user_input.expected_sha256,
                edits,
            )
        except WorkspaceConflictError as exc:
            await record_preparation_failure(
                self,
                session,
                user_input.path,
                "conflict",
                str(exc),
            )
            return Edit_output_schema(
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
            return Edit_output_schema(
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
            action="精确编辑文本文件",
            tool_args=user_input.model_dump(mode="json"),
            output_class=Edit_output_schema,
        )
        if guard_warning and out.is_written:
            out.message = f"{guard_warning}\n\n{out.message}"
        return out
