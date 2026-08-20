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
    is_written: bool = Field(description="Whether the file write completed")
    filepath: str = Field(description="File path relative to the working directory")
    status: str = Field(description="applied, declined, conflict, or failed")
    change_id: str = Field(default="", description="ID of this file change")
    before_sha256: str | None = Field(default=None, description="File hash before the change")
    after_sha256: str | None = Field(default=None, description="Candidate or post-write file hash")
    diff: str = Field(default="", description="Unified diff of this change")
    message: str = Field(default="", description="Status or error message")


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
        diff_preview = diff_preview[:12_000] + "\n... diff preview truncated ...\n"
    return (
        f"Action: {action}\n"
        f"Path: {change.relative_path}\n"
        f"Scale: +{change.additions} lines, -{change.deletions} lines\n"
        f"SHA256: {change.after_sha256[:12]} (before: {change.before_sha256[:12] if change.before_sha256 else 'new file'})\n"
        f"Unified Diff:\n{diff_preview}"
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
        message = denial_reason or (
            "User declined the file change. "
            "Next: explain to the user why the change was needed, adjust the content, "
            "or choose a different approach."
        )
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
        message="File change written atomically",
    )
