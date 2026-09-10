"""Shared Pydantic schemas for the event-driven Cloudra runtime.

This module is the single source of truth for the v2 API wire types.  No
other runtime_v2 module may invent its own request/response shapes.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, computed_field


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class OrchestrationMode(str, Enum):
    STANDARD = "standard"
    DAG_RECORD = "dag_record"
    DAG_GUIDED = "dag_guided"


class InvocationProtocol(str, Enum):
    """How model tool calls are dispatched for one run.

    ``traditional``: each wire tool call executes directly.  ``javascript``:
    the model writes one bounded JS program per exchange whose inner tool
    calls go through the same invocation service.  The protocol is resolved
    when ``run.started`` is produced and frozen on ``CurrentRun`` — changing
    the setting affects the next run only, never a live one.
    """

    TRADITIONAL = "traditional"
    JAVASCRIPT = "javascript"


class AgentState(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    WAITING_INPUT = "waiting_input"
    WAITING_APPROVAL = "waiting_approval"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class RuntimeSettingsPatch(BaseModel):
    """Partial settings update; full RuntimeSettings extends this with defaults."""

    model_config = ConfigDict(extra="forbid")

    model: Optional[str] = None
    base_url: Optional[str] = None
    temperature: Optional[float] = Field(default=None, ge=0.0, le=2.0)
    max_tokens: Optional[int] = Field(default=None, ge=1)
    context_window: Optional[int] = Field(default=None, ge=1)
    top_p: Optional[float] = Field(default=None, gt=0.0, le=1.0)
    frequency_penalty: Optional[float] = Field(default=None, ge=-2.0, le=2.0)
    presence_penalty: Optional[float] = Field(default=None, ge=-2.0, le=2.0)
    timeout: Optional[int] = Field(default=None, ge=1)
    yolo: Optional[bool] = None
    # 无人值守运行（benchmark 评测等）：没有任何人类交互端。线缆投影隐藏
    # ask_user（tool_catalog._settings_hidden_tools），执行层由
    # policies/unattended.py 的 UnattendedStage fail-closed 拦截——绝不允许
    # 状态机流转到 waiting_input。yolo 只覆盖审批通道，不覆盖 ask_user。
    unattended: Optional[bool] = None
    schedule_mode: Optional[bool] = None
    visual_mode: Optional[bool] = None
    # Disable cross-task implicit context (global memory and AGENTS.md).
    # Same-agent event history/handover and explicit file reads remain available.
    clean_context: Optional[bool] = None
    native_search: Optional[str] = None
    native_search_params: Optional[dict[str, Any]] = None
    # 思考强度（OpenAI 兼容的 reasoning_effort）：取值集随 provider 而异
    # （minimal/low/medium/high 等），不做枚举校验，None = 完全不传该参数。
    reasoning_effort: Optional[str] = None
    orchestration_mode: Optional[OrchestrationMode] = None
    invocation_protocol: Optional[InvocationProtocol] = None
    api_key: Optional[str] = Field(default=None, repr=False)


class RuntimeSettings(RuntimeSettingsPatch):
    """Effective settings of one agent at one point in time.

    ``api_key`` is write-only on the wire: dumps never include it and the API
    only reports ``api_key_set``.
    """

    model: str = ""
    base_url: str = ""
    temperature: float = 1.0
    max_tokens: int = 32768
    context_window: int = 200000
    top_p: Optional[float] = None
    frequency_penalty: float = 0.0
    presence_penalty: float = 0.0
    timeout: int = 300
    yolo: bool = False
    unattended: bool = False
    schedule_mode: bool = False
    visual_mode: bool = True
    clean_context: bool = False
    native_search: str = "auto"
    native_search_params: dict[str, Any] = Field(default_factory=dict)
    orchestration_mode: OrchestrationMode = OrchestrationMode.STANDARD
    invocation_protocol: InvocationProtocol = InvocationProtocol.JAVASCRIPT

    api_key: str = Field(default="", repr=False, exclude=True)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def api_key_set(self) -> bool:
        return bool(self.api_key)

    def apply(self, patch: RuntimeSettingsPatch) -> "RuntimeSettings":
        data = self.model_dump()
        data.pop("api_key_set", None)  # computed field; not a constructor input
        # Explicit nulls carry no semantics in a patch (every field defaults
        # to None = unset); drop them so a round-tripped settings dict with
        # serialized nulls can never poison the result.
        patch_data = {k: v for k, v in patch.model_dump(exclude_unset=True).items() if v is not None}
        if patch.api_key is not None:
            patch_data["api_key"] = patch.api_key
        data.update(patch_data)
        return RuntimeSettings.model_validate(data)


class PermissionSet(BaseModel):
    model_config = ConfigDict(extra="forbid")

    read: bool = True
    write: bool = False
    manage: bool = False
    script: bool = False
    destructive: bool = False


class ToolPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    allow: list[str] = Field(default_factory=lambda: ["*"])
    deny: list[str] = Field(default_factory=list)


class RoleProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role_id: str = Field(min_length=1)
    display_name: str
    description: str = ""
    permissions: PermissionSet = Field(default_factory=PermissionSet)
    can_spawn: bool = False
    spawn_roles: Optional[list[str]] = None
    tool_policy: ToolPolicy = Field(default_factory=ToolPolicy)
    default_settings: RuntimeSettingsPatch = Field(default_factory=RuntimeSettingsPatch)
    builtin: bool = True


class AgentCapabilities(BaseModel):
    model_config = ConfigDict(extra="forbid")

    permissions: PermissionSet
    can_spawn: bool = False
    spawn_roles: Optional[list[str]] = None
    tools: list[str] = Field(default_factory=list)


class CurrentRun(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    started_at: datetime
    invocation_protocol: InvocationProtocol = InvocationProtocol.TRADITIONAL


class AgentSession(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    project_id: str
    role_id: str
    display_name: str
    parent_session_id: Optional[str] = None
    state: AgentState = AgentState.QUEUED
    settings: RuntimeSettings = Field(default_factory=RuntimeSettings)
    settings_revision: int = 0
    capabilities: AgentCapabilities = Field(
        default_factory=lambda: AgentCapabilities(permissions=PermissionSet())
    )
    current_run: Optional[CurrentRun] = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    def touch(self) -> None:
        self.updated_at = utc_now()


def configured_invocation_protocol(agent: AgentSession) -> InvocationProtocol:
    """The protocol the agent's *next* run will use (settings value)."""
    return agent.settings.invocation_protocol


def effective_invocation_protocol(agent: AgentSession) -> InvocationProtocol:
    """The protocol in force: frozen on the active run, else the configured one."""
    current_run = getattr(agent, "current_run", None)
    if current_run is not None:
        return current_run.invocation_protocol
    return agent.settings.invocation_protocol


class MethodPolicy(BaseModel):
    """Whitelisted computation levels: any method not in `allowed_methods` is
    blocked. A blacklist can always be bypassed, so interception is strictly
    positive (whitelist) matching, wired in at the layers named by
    `intercept_layers`:
    - `qm_input_writer`: structured computation entry with an explicit
      method field.
    - `submit_compute_job`: submits a prepared input file, so interception
      parses that file's content (Gaussian route card / ORCA keyword lines).
    - `bash`: the *content* of QM input files being written or executed is
      parsed the same way — the raw command text is never keyword-scanned.

    The benchmark whitelist (xTB) has no basis-set concept at all,
    so the policy carries no basis fields. Whitelist matching happens at
    method-*family* granularity (any token containing `xtb` matches the xTB entry).
    Attempting a non-whitelisted method is intercepted, never penalized.

    benchmark 任务与 per-project live 设置共用本模型；live 侧项目未显式
    设置（`ProjectSettings.method_policy is None`）时完全不启用拦截。"""

    model_config = ConfigDict(extra="forbid")

    allowed_methods: list[str] = Field(
        default_factory=lambda: ["xtb"]
    )
    intercept_layers: list[str] = Field(
        default_factory=lambda: ["bash", "submit_compute_job", "qm_input_writer"]
    )


class ProjectSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    orchestration_mode: OrchestrationMode = OrchestrationMode.STANDARD
    defaults: RuntimeSettingsPatch = Field(default_factory=RuntimeSettingsPatch)
    # 方法白名单（GH #25）：None = 不启用拦截；设置后由 policies 的
    # MethodPolicyStage 在 intercept_layers 声明的工具层拦截。
    method_policy: Optional[MethodPolicy] = None


class Project(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str = Field(min_length=1, max_length=200)
    workspace_dir: Optional[str] = None
    archived: bool = False
    settings: ProjectSettings = Field(default_factory=ProjectSettings)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    def touch(self) -> None:
        self.updated_at = utc_now()


class Command(BaseModel):
    """A user/system operation entering the command pipeline.

    Append the event first; only then apply the command to in-memory state.
    """

    model_config = ConfigDict(extra="forbid")

    command_id: str = Field(default_factory=lambda: new_id("cmd"))
    type: str = Field(min_length=1)
    target: dict[str, str] = Field(default_factory=dict)
    payload: dict[str, Any] = Field(default_factory=dict)
    actor: Literal["user", "system"] = "user"


class CommandResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    command_id: str
    accepted: bool = True
    event_id: str
    data: Any = None


class CommandRejected(Exception):
    def __init__(self, code: str, message: str, *, events: tuple = ()):
        super().__init__(message)
        self.code = code
        self.message = message
        # 拒绝前的领域审计草稿（如 agent.spawn_requested / agent.spawn_rejected /
        # agent.restart_requested）：decide 是纯函数不能自行落日志，把草稿挂在
        # 异常上，CommandBus 的拒绝路径先落这些再落 command.rejected。
        # 类型为 tuple[EventDraft, ...]（effects.py，避免 schemas->effects 之外的回环）。
        self.events: tuple = events


class EventEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stream: Literal["agent", "project"]
    event_id: str = Field(default_factory=lambda: new_id("evt"))
    project_id: str
    session_id: Optional[str] = None
    run_id: Optional[str] = None
    seq: int
    session_seq: Optional[int] = None
    type: str
    data: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)
