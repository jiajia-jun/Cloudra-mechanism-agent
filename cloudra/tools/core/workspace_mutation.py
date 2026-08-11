"""文件变更工具共享的审批、应用与事件流水线。"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import TypeVar

from pydantic import Field

from cloudra.base.session_class import Session
from cloudra.base.tools_class import Tool, output_schema
from cloudra.persistence.workspace import (
    PreparedFileChange,
    WorkspaceConflictError,
    WorkspaceError,
    WorkspaceService,
    turn_diff_tracker,
)


class WorkspaceMutationOutput(output_schema):
    is_written: bool = Field(description="是否完成文件写入")
    filepath: str = Field(description="相对工作目录的文件路径")
    status: str = Field(description="applied、declined、conflict 或 failed")
    change_id: str = Field(default="", description="本次文件变更 ID")
    before_sha256: str | None = Field(default=None, description="修改前文件哈希")
    after_sha256: str | None = Field(default=None, description="候选或写入后的文件哈希")
    diff: str = Field(default="", description="本次变更的 unified diff")
    message: str = Field(default="", description="状态或错误信息")


_OutputT = TypeVar("_OutputT", bound=WorkspaceMutationOutput)


def workspace_for_tool(tool: Tool) -> WorkspaceService:
    root = getattr(tool.subagent, "working_directory", None)
    if not root:
        import os

        root = os.getcwd()
    return WorkspaceService(root)


def _approval_details(action: str, change: PreparedFileChange) -> str:
    diff_preview = change.diff
    if len(diff_preview) > 12_000:
        diff_preview = diff_preview[:12_000] + "\n... 审批预览已截断，完整 diff 可在界面查看 ...\n"
    return (
        f"【动作】: {action}\n"
        f"【相对路径】: {change.relative_path}\n"
        f"【变更规模】: +{change.additions} -{change.deletions}\n"
        f"【修改前 SHA256】: {change.before_sha256 or 'missing'}\n"
        f"【修改后 SHA256】: {change.after_sha256}\n"
        f"【Unified Diff】:\n{diff_preview}"
    )


async def record_preparation_failure(
    tool: Tool,
    session: Session,
    relative_path: str,
    status: str,
    message: str,
) -> None:
    await tool.record_session_event(
        session,
        "file_change_failed",
        {
            "path": relative_path,
            "status": status,
            "diff": "",
            "message": message,
        },
    )


async def execute_prepared_change(
    tool: Tool,
    service: WorkspaceService,
    change: PreparedFileChange,
    session: Session,
    action: str,
    tool_args: dict,
    output_class: type[_OutputT],
) -> _OutputT:
    await tool.record_session_event(
        session,
        "file_change_proposed",
        change.event_data("proposed"),
    )
    approved, denial_reason = await tool.ensure_safety(
        session,
        details=_approval_details(action, change),
        tool_args=tool_args,
    )
    if not approved:
        message = denial_reason or "用户拒绝了文件变更"
        await tool.record_session_event(
            session,
            "file_change_declined",
            change.event_data("declined", message),
        )
        return output_class(
            is_written=False,
            filepath=change.relative_path,
            status="declined",
            change_id=change.change_id,
            before_sha256=change.before_sha256,
            after_sha256=change.after_sha256,
            diff=change.diff,
            message=message,
        )

    try:
        await asyncio.to_thread(service.apply, change)
    except WorkspaceConflictError as exc:
        message = str(exc)
        await tool.record_session_event(
            session,
            "file_change_failed",
            change.event_data("conflict", message),
        )
        return output_class(
            is_written=False,
            filepath=change.relative_path,
            status="conflict",
            change_id=change.change_id,
            before_sha256=change.before_sha256,
            after_sha256=change.after_sha256,
            diff=change.diff,
            message=message,
        )
    except (OSError, WorkspaceError) as exc:
        message = str(exc)
        await tool.record_session_event(
            session,
            "file_change_failed",
            change.event_data("failed", message),
        )
        return output_class(
            is_written=False,
            filepath=change.relative_path,
            status="failed",
            change_id=change.change_id,
            before_sha256=change.before_sha256,
            after_sha256=change.after_sha256,
            diff=change.diff,
            message=message,
        )

    await tool.record_session_event(
        session,
        "file_change_applied",
        change.event_data("applied"),
    )
    conversation_id = getattr(tool.subagent, "conversation_id", "default")
    from cloudra.persistence.database import ConversationDB

    if Path(ConversationDB(conversation_id).path).is_file():
        try:
            from cloudra.persistence.artifacts import ArtifactService

            await asyncio.to_thread(
                ArtifactService().register_file,
                conversation_id=conversation_id,
                session_id=session.id,
                source=change.absolute_path,
                allowed_root=service.root,
                name=change.relative_path,
            )
        except (OSError, ValueError) as exc:
            await tool.record_session_event(
                session,
                "artifact_registration_failed",
                {
                    "path": change.relative_path,
                    "message": str(exc),
                },
            )
    session_key = f"{conversation_id}:{session.id}"
    aggregate_diff = turn_diff_tracker.record_applied(session_key, service, change)
    await tool.record_session_event(
        session,
        "turn_diff_updated",
        {
            "change_id": change.change_id,
            "path": change.relative_path,
            "status": "updated",
            "diff": aggregate_diff,
        },
    )
    return output_class(
        is_written=True,
        filepath=change.relative_path,
        status="applied",
        change_id=change.change_id,
        before_sha256=change.before_sha256,
        after_sha256=change.after_sha256,
        diff=change.diff,
        message="文件变更已原子写入",
    )
