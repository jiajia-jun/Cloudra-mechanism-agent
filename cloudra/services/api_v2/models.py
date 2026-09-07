"""Pydantic request/response models for the v2 HTTP surface."""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    workspace_dir: Optional[str] = None
    settings: dict[str, Any] = Field(default_factory=dict)


class ProjectPatch(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    workspace_dir: Optional[str] = None
    archived: Optional[bool] = None
    settings: Optional[dict[str, Any]] = None


class AgentSpawn(BaseModel):
    role_id: str
    parent_session_id: Optional[str] = None
    display_name: Optional[str] = None
    query: Optional[str] = None
    settings: dict[str, Any] = Field(default_factory=dict)


class MessagePost(BaseModel):
    content: str = Field(min_length=1)
    images: Optional[list[str]] = None
    image_artifact_ids: Optional[list[Optional[str]]] = None


class CancelPost(BaseModel):
    message: Optional[str] = None


class RestartPost(BaseModel):
    message: Optional[str] = None
    settings: dict[str, Any] = Field(default_factory=dict)


class RolePatch(BaseModel):
    permissions: Optional[dict[str, bool]] = None
    tool_policy: Optional[dict[str, Any]] = None
    can_spawn: Optional[bool] = None
    spawn_roles: Optional[list[str]] = None
    default_settings: Optional[dict[str, Any]] = None


class ApprovalDecision(BaseModel):
    decision: Literal["approve", "deny"]
    reason: str = ""


class InteractionResponse(BaseModel):
    response: str = Field(min_length=1)


class DagMutationRequest(BaseModel):
    operations: list[dict[str, Any]]
    base_revisions: dict[str, int] = Field(default_factory=dict)
    rationale: str = ""


class DagReplanRequest(BaseModel):
    note: str = ""


class GoalSetRequest(BaseModel):
    objective: str = ""
    completion_criteria: str = ""
    current_focus: str = ""


class CompactRequest(BaseModel):
    keep_recent: int = Field(default=20, ge=1, le=500)


class ContextInjectRequest(BaseModel):
    kind: Literal["pin", "unpin", "push"] = "push"
    key: str = ""
    content: str = ""


class GlobalConfigFieldPatch(BaseModel):
    """Fields of one global LLM slot; ``key`` is write-only (empty clears)."""

    model: Optional[str] = None
    url: Optional[str] = None
    key: Optional[str] = None
    context_window: Optional[int] = Field(default=None, ge=1)
    timeout: Optional[int] = Field(default=None, ge=1)
    reasoning_effort: Optional[str] = None


class GlobalConfigPatch(BaseModel):
    slot: Literal["coordinator", "follower"]
    changes: GlobalConfigFieldPatch


class CommandResponse(BaseModel):
    command_id: str
    accepted: bool
    event_id: str
    data: Any = None


def _command_payload(body: BaseModel) -> dict[str, Any]:
    return body.model_dump(exclude_unset=True)
