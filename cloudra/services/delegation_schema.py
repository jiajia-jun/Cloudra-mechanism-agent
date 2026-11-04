"""Wire types shared by the Cloudra HTTP service and its MCP adapter."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from typing_extensions import NotRequired, TypedDict

from cloudra.runtime_v2.completion import RunOutcome, VerificationLabel

NonBlank = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
ProjectName = Annotated[NonBlank, StringConstraints(max_length=200)]
TranscriptFilter = Annotated[NonBlank, StringConstraints(max_length=4000)]
HistoryLimit = Annotated[int, Field(ge=1, le=50, strict=True)]
MAX_RESULT_WAIT = 20


class MessageBatch(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    recipients: list[NonBlank] = Field(min_length=1)
    content: NonBlank


class ProjectRef(TypedDict):
    project_id: str
    name: str
    created_at: str


class ProjectList(TypedDict):
    projects: list[ProjectRef]


class TaskRef(TypedDict):
    project_id: str
    session_id: str


ErrorCode = Literal["invalid_request", "not_found", "forbidden", "state_conflict", "unavailable"]


class ErrorInfo(TypedDict):
    code: ErrorCode
    message: str
    project_id: NotRequired[str]


class Delivered(TypedDict):
    session_id: str
    message_event_id: str


class DeliveryError(TypedDict):
    session_id: str
    error: ErrorInfo


class MessageDeliveries(TypedDict):
    deliveries: list[Delivered | DeliveryError]


class AnswerAccepted(TypedDict):
    accepted: Literal[True]


class AgentProgress(TypedDict):
    session_id: str
    name: str
    role_id: str
    parent_session_id: str | None
    activity: Literal[
        "queued", "running", "waiting_background", "waiting_input", "waiting_approval",
        "waiting_review", "idle", "failed", "cancelled",
    ]
    detail: str | None
    updated_at: str
    active_job_ids: list[int]


class Question(TypedDict):
    kind: Literal["question"]
    session_id: str
    interaction_id: str
    prompt: str


class Approval(TypedDict):
    kind: Literal["approval"]
    session_id: str
    approval_id: str
    summary: str


class Review(TypedDict):
    kind: Literal["review"]
    session_id: str
    summary: str


Pending = Question | Approval | Review


class Excerpt(TypedDict):
    text: str
    truncated: bool


class ProcessExcerpt(Excerpt):
    updated_at: str


class ProjectProgress(TypedDict):
    project_id: str
    observed_at: str
    agents: list[AgentProgress]
    pending: list[Pending]
    process: ProcessExcerpt | None


class ContextItem(Excerpt):
    event_id: str
    kind: Literal["assistant", "incoming", "tool", "error", "reasoning"]
    at: str
    tool_name: str | None
    status: Literal[
        "queued", "running", "waiting", "blocked", "completed", "failed", "cancelled", "interrupted", "unknown",
    ] | None


class AgentContext(TypedDict):
    agent: AgentProgress
    pending: list[Pending]
    messages: list[ContextItem]
    history_truncated: bool


class ArtifactRef(TypedDict):
    artifact_id: str
    name: str
    mime_type: str
    size: int
    uri: str


class Outcome(TypedDict):
    terminal_event_id: str
    run_outcome: RunOutcome
    summary: str | None
    verification_label: VerificationLabel
    completion_basis: str | None
    unresolved: list[str]
    artifacts: list[ArtifactRef]


class FinishedResult(TypedDict):
    status: Literal["finished"]
    result: Outcome


class PendingResult(TypedDict):
    status: Literal["pending"]
    agent: AgentProgress
    pending: list[Pending]


CurrentResult = FinishedResult | PendingResult
