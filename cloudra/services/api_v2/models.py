"""Pydantic request/response models for the v2 HTTP surface."""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


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
    language: Optional[str] = None


class MessagePost(BaseModel):
    content: str = Field(min_length=1)
    images: Optional[list[str]] = None
    image_artifact_ids: Optional[list[Optional[str]]] = None
    language: Optional[str] = None


class HubPostCreate(BaseModel):
    topic: str = Field(min_length=1)
    content: str = Field(min_length=1)
    kind: str = "finding"
    to_agent: Optional[str] = None
    parent_id: Optional[str] = None


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


class BenchmarkStart(BaseModel):
    """启动一批 benchmark 评测（GH #32）。tiers 选内置档位（easy/normal/hard/
    impossible，可多选），tasks_dirs 追加自定义目录；两者都空 = 内置 easy 档。"""

    tiers: list[str] = Field(default_factory=list)
    tasks_dirs: list[str] = Field(default_factory=list)
    only: str = ""
    concurrency: int = Field(default=1, ge=1, le=8)


class GoalSetRequest(BaseModel):
    objective: str = ""
    completion_criteria: str = ""
    current_focus: str = ""


class CompactRequest(BaseModel):
    """手动压缩请求：压缩范围固定为整个会话投影，无参数。"""

    model_config = ConfigDict(extra="forbid")


class ContextInjectRequest(BaseModel):
    kind: Literal["pin", "unpin", "push"] = "push"
    key: str = ""
    content: str = ""


class GlobalConfigFieldPatch(BaseModel):
    """Fields of one global LLM slot; ``key`` is write-only (empty clears)."""

    provider: Optional[str] = None
    model: Optional[str] = None
    url: Optional[str] = None
    key: Optional[str] = None
    supports_vision: Optional[bool] = None
    context_window: Optional[int] = Field(default=None, ge=1)
    timeout: Optional[int] = Field(default=None, ge=1)
    reasoning_effort: Optional[str] = None


class GlobalConfigPatch(BaseModel):
    slot: Literal["coordinator", "follower"]
    changes: GlobalConfigFieldPatch


class ToolDocumentLoadingPatch(BaseModel):
    model_config = ConfigDict(extra='forbid')
    strategy: Literal['llm', 'semantic'] | None = None
    semantic_backend: Literal['jev', 'reranker'] | None = None
    jev: dict[str, Any] | None = None
    reranker: dict[str, Any] | None = None


class OpenRouterExchangeRequest(BaseModel):
    code: str
    code_verifier: str
    slot: Optional[Literal["coordinator", "follower"]] = None


class CodexDevicePollRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    login_id: str = Field(min_length=1)


class CommandResponse(BaseModel):
    command_id: str
    accepted: bool
    event_id: str
    data: Any = None


def _command_payload(body: BaseModel) -> dict[str, Any]:
    return body.model_dump(exclude_unset=True)


class FsBrowseEntry(BaseModel):
    name: str
    path: str
    is_dir: bool = True
    mtime: Optional[float] = None


class FsBrowseShortcut(BaseModel):
    name: str
    path: str


class FsBrowseResponse(BaseModel):
    current: str
    parent: Optional[str] = None
    home: str
    cwd: str
    shortcuts: list[FsBrowseShortcut] = Field(default_factory=list)
    entries: list[FsBrowseEntry] = Field(default_factory=list)
    writable: bool = True


class FsMkdirRequest(BaseModel):
    path: str = Field(min_length=1)


class FsSystemPickerResponse(BaseModel):
    supported: bool
    path: Optional[str] = None
    canceled: bool = False

