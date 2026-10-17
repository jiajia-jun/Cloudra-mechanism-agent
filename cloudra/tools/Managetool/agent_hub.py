"""AgentHub：项目内所有 Agent 的共享论坛。

runtime_v2 的各 Agent 共享项目事件日志。本工具把事件日志变成一块"留言板"：
任何 Agent（包括只读的 explorer）都可以发帖分享发现、提问、回答，
或先查别人的帖子避免重复劳动。

帖子一律公开：to_agent 只是"点名"，帖子本身仍是全论坛可见的讨论痕迹；
被点名或被回复的 Agent 会收到持久 Mailbox 投递，是否唤醒由状态与权限决定。
检索为纯 Python 模糊匹配（英文按词、中文按 bigram 的 token 覆盖率），
不引入向量检索依赖。
"""

from typing import Any, Literal, Optional, Self

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from cloudra.base.session_class import Session
from cloudra.base.tools_class import Tool, input_schema, output_schema

# 模糊命中下限：query token 覆盖率低于该值视为不相关
_FUZZY_FLOOR = 0.34
# search 一次扫描的最近帖子数（论坛规模有限，Python 侧打分足够快）
_SEARCH_SCAN_LIMIT = 500


def _query_tokens(text: str) -> set[str]:
    """英文按词、中文按 bigram 切 token，供模糊检索。"""
    tokens: set[str] = set()
    run: list[str] = []
    kind = ""
    for char in text.lower() + " ":
        current = (
            "word" if char in "abcdefghijklmnopqrstuvwxyz0123456789_" else
            "cjk" if "一" <= char <= "鿿" else ""
        )
        if current != kind:
            if kind == "word" or (kind == "cjk" and len(run) == 1):
                tokens.add("".join(run))
            elif kind == "cjk":
                tokens.update("".join(run[i:i + 2]) for i in range(len(run) - 1))
            run = []
            kind = current
        if current:
            run.append(char)
    return tokens


def _fuzzy_score(query: str, text: str) -> float:
    """0~1 相关度：子串精确命中为 1，否则看 query token 在正文中的覆盖率。"""
    q = query.strip().lower()
    if not q:
        return 0.0
    if q in text.lower():
        return 1.0
    q_tokens = _query_tokens(q)
    if not q_tokens:
        return 0.0
    return len(q_tokens & _query_tokens(text)) / len(q_tokens)

description = (
    "AgentHub: a shared information forum for all parallel Agents. Every post is public to every Agent. You can:\n"
    "- **post**: publish a finding, question, answer, broadcast, or message; pass parent_id to reply to a post.\n"
    "- **Addressing and notifications**: on post you may set to_agent (session_id, semantic role_id such as small_mol, or display_name) "
    "to say who the content is mainly for — the post itself remains a public discussion trail anyone can read; "
    "the addressed Agent receives a durable mailbox notification, and the original author receives one when their post is replied to. "
    "Session IDs, parent aliases, and roles resolve first; otherwise the target is matched to a display_name, ignoring case and an optional @ prefix. "
    "Use distinct display names for same-role instances, or session_id to select one precisely. "
    "Delivery and wake-up are separate: failed/cancelled sessions and recipients you cannot wake keep the message parked. "
    "notifications reports the committed message_event_id and wake_status (requested / already_running / parked), "
    "which records the pre-delivery wake intent, not proof that a new run started.\n"
    "- **browse**: list recent topics and activity.\n"
    "- **read**: read posts for a topic (including Q&A threads).\n"
    "- **search**: search all posts by keyword (fuzzy match; exact wording not required).\n"
    "- **directory**: list project sessions with session_id, display_name, role, state, and parent_session_id (when dispatched as a sub-agent).\n"
    "- **call**: send a non-blocking message to an Agent session; an absent ordinary role creates an independent project peer (to + message, optional post_id). "
    "Check notifications for delivery/wake-up and settings for a new peer's effective configuration. "
    "The new peer sends its first task result to the caller, without a parent/child link.\n"
    "Discipline: before starting a subtask that may overlap with another Agent, browse/search to see if someone already did it; "
    "after you get a reusable conclusion (parameters, data, pitfalls), post it to the matching topic. Posts must be self-contained — "
    "others do not have your context. If you are unsure about data or tool behavior, post a question or address someone with to_agent; "
    "do not conclude from memory alone."
)


_ACTION_REQUIRED_FIELDS = {
    "post": ("topic", "content"),
    "browse": (),
    "read": ("topic",),
    "search": ("keyword",),
    "directory": (),
    "call": ("to", "message"),
}


def _action_json_schema(schema: dict[str, Any]) -> None:
    """Refine shared flat fields with the conditions for each action."""
    branches = []
    for action, fields in _ACTION_REQUIRED_FIELDS.items():
        for message_post in ((False, True) if action == "post" else (False,)):
            required = ["action", *fields]
            names = list(fields)
            if action == "post":
                names.append("kind")
                if message_post:
                    names.append("to_agent")
            properties = {
                name: {
                    key: value for key, value in schema["properties"][name].items()
                    if key not in {"description", "title", "default"}
                }
                for name in names
            }
            properties["action"] = {"type": "string", "const": action}
            if action == "post":
                if message_post:
                    properties["kind"] = {"type": "string", "const": "message"}
                    required.extend(("kind", "to_agent"))
                else:
                    properties["kind"]["enum"] = ["finding", "question", "answer", "broadcast"]
            for field in required[1:]:
                if field != "kind":
                    properties[field]["minLength"] = 1
            branches.append({
                "type": "object", "properties": properties,
                "required": required,
            })
    schema["oneOf"] = branches


class AgentHub_input_schema(input_schema):
    model_config = ConfigDict(extra="forbid", json_schema_extra=_action_json_schema)

    action: Literal["post", "browse", "read", "search", "directory", "call"] = Field(
        description="Action: post / browse / read / search / directory / call",
    )
    topic: str = Field(default="", description="Topic name (non-whitespace text required for post/read), e.g. 'CO2 hydrogenation - literature'")
    content: str = Field(default="", description="Post body (non-whitespace text required for post); must be self-contained")
    kind: Literal["finding", "question", "answer", "broadcast", "message"] = Field(
        default="finding",
        description="Post kind: finding / question / answer / broadcast / message; all posts are public"
    )
    to_agent: str = Field(
        default="",
        description="Addressee: session_id, semantic role_id (e.g. small_mol), or display_name fallback; non-whitespace text required for kind=message posts; the post stays public"
    )
    to: str = Field(
        default="",
        description="Call target: session_id, semantic role_id (e.g. small_mol), or display_name fallback; non-whitespace text required for call",
    )
    message: str = Field(default="", description="What you say to the other side on call (not a role prompt); non-whitespace text required for call")
    post_id: Optional[str] = Field(
        default=None,
        description="Related post ID for call; for post, retry missing notifications on this same post ID with unchanged fields",
    )
    parent_id: Optional[str] = Field(default=None, description="Post ID to reply to (string event id)")
    keyword: str = Field(default="", description="Search keyword (non-whitespace text required for search); fuzzy match, synonyms/inexact phrasing OK")
    limit: int = Field(default=20, description="Maximum number of items to return")
    cursor: Optional[str] = Field(default=None, description="Opaque browse cursor returned by a previous browse page")

    @model_validator(mode="after")
    def require_action_fields(self) -> Self:
        fields = _ACTION_REQUIRED_FIELDS[self.action]
        if self.action == "post" and self.kind == "message":
            fields = (*fields, "to_agent")
        errors = []
        for field in fields:
            value = getattr(self, field)
            if not value.strip():
                error = ValueError(f"{field} must contain non-whitespace text for action={self.action}")
                errors.append({"type": "value_error", "loc": (field,), "input": value, "ctx": {"error": error}})
        if errors:
            raise ValidationError.from_exception_data(type(self).__name__, errors)
        return self

    @classmethod
    def to_parameters_schema(cls) -> dict:
        # The generic input projection only retains properties/required, which
        # would erase these action conditions for traditional tool calls.
        return cls.model_json_schema()


class HubPost(BaseModel):
    model_config = ConfigDict(extra="allow", strict=True)

    id: str
    seq: int
    created_at: str
    topic: str
    content: str
    kind: Literal["finding", "question", "answer", "broadcast", "message"]
    author_agent: str
    author_session: str | None
    to_agent: str | None = None
    parent_id: str | None = None
    score: float | None = None
    notification_target_ids: list[str] = Field(default_factory=list)
    addressed_session_id: str | None = None
    reply_session_id: str | None = None


class HubTopic(BaseModel):
    model_config = ConfigDict(extra="allow", strict=True)

    topic: str
    post_count: int
    latest_at: str
    latest_author: str
    preview: str
    latest_post_id: str | None


class HubSession(BaseModel):
    model_config = ConfigDict(extra="allow", strict=True)

    session_id: str
    agent_id: str
    agent_type: Literal["system", "subagent", "peer"]
    parent_session_id: str | None
    role_id: str
    state: str
    display_name: str


class HubNotification(BaseModel):
    model_config = ConfigDict(extra="allow", strict=True)

    session_id: str
    message_event_id: str = Field(description="Committed agent.message_injected event: the message is durably delivered")
    delivery: Literal["delivered", "parked"] = Field(
        description="Both values confirm durable mailbox delivery; parked records the pre-delivery intent to leave the recipient sleeping",
    )
    wake_status: Literal["requested", "already_running", "parked"] = Field(
        description="Pre-delivery wake intent from target_state and wake_policy; requested does not confirm a new run started, and already_running/parked do not confirm final state",
    )
    wake_policy: Literal["park_terminal", "park_waiting", "idle_only", "never"]
    target_state: str = Field(description="Recipient state immediately before delivery")


class HubLibraryHit(BaseModel):
    model_config = ConfigDict(extra="allow", strict=True)

    title: str
    content: str
    evidence_level: Literal["L0", "L1", "L2"]
    source: str
    falsified: bool
    score: float
    tags: list[str]
    provider: str


class HubSkillHit(BaseModel):
    model_config = ConfigDict(extra="allow", strict=True)

    name: str
    description: str


class HubPeerSettings(BaseModel):
    model_config = ConfigDict(extra="allow", strict=True)

    session_id: str
    role_id: str
    model: str | None
    invocation_protocol: Literal["traditional", "javascript"]
    orchestration_mode: Literal["standard", "dag_record", "dag_guided"]
    unattended: bool
    visual_mode: bool
    yolo: bool
    schedule_mode: bool
    clean_context: bool
    sources: dict[str, Literal["role_default", "project_default", "schema_default"]]


class AgentHub_output_schema(output_schema):
    model_config = ConfigDict(extra="allow", strict=True)

    is_success: bool = Field(description="Whether the action succeeded")
    posts: list[HubPost | HubTopic] = Field(default_factory=list, description="Full post rows for read/search, topic summaries for browse")
    post_id: Optional[str] = Field(default=None, description="New post ID (post result)")
    notified_count: int = Field(default=0, description="Number of sessions notified for this post")
    failed_session_ids: list[str] = Field(default_factory=list, description="Recipients still missing a post notification")
    next_cursor: Optional[str] = Field(default=None, description="Opaque cursor for the next browse page")
    notifications: list[HubNotification] = Field(default_factory=list, description="Receipts for notifications delivered during this call; separate from wake intent, and notified_count may include earlier retries")
    library: list[HubLibraryHit] = Field(default_factory=list, description="Search results from registered knowledge providers")
    skills: list[HubSkillHit] = Field(default_factory=list, description="Search results for domain skills; load using get_skill(skill_name)")
    settings: HubPeerSettings | None = Field(default=None, description="Effective settings and value sources for a newly called peer")
    sources_status: dict[str, str] = Field(default_factory=dict, description="Search source status (project_posts/library/skills availability)")
    message: str = Field(default="", description="Status note")
    sessions: list[HubSession] = Field(default_factory=list, description="Project session rows returned by directory")
    session_id: str = Field(default="", description="call result: the other party's session_id")


class AgentHub(Tool):
    tool_id: str = 't-hub'
    tool_name: str = 'agent_hub'
    tool_description: str = description
    input_schema: Any = AgentHub_input_schema
    output_schema: Any = AgentHub_output_schema

    def is_read(self) -> bool:
        # 旧工具权限接口用 is_read 区分通用可用能力；AgentHub 是所有
        # Agent 平等使用的协作通道。v2 的 post/call 仍经事件写口/CommandBus。
        return True

    async def tool_call(self, user_input: AgentHub_input_schema, session: Session) -> AgentHub_output_schema:
        # Legacy 论坛存储（hub_posts 表 + 旧上下文通知）已随 v1 删除；
        # runtime_v2 的 LegacyToolExecutor 按工具名拦截到 hub_bridge，此 body 只是兜底。
        return AgentHub_output_schema(
            is_success=False,
            message="agent_hub is handled by runtime_v2; the legacy forum storage no longer exists.",
        )
