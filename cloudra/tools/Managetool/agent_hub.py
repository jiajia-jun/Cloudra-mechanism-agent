"""AgentHub：项目内所有 Agent 的共享论坛。

runtime_v2 的各 Agent 共享项目事件日志。本工具把事件日志变成一块"留言板"：
任何 Agent（包括只读的 explorer）都可以发帖分享发现、提问、回答，
或先查别人的帖子避免重复劳动。

帖子一律公开：to_agent 只是"点名"，帖子本身仍是全论坛可见的讨论痕迹；
被点名或被回复的 Agent 会收到 Mailbox 投递与唤醒。
检索为纯 Python 模糊匹配（英文按词、中文按 bigram 的 token 覆盖率），
不引入向量检索依赖。
"""

import re
from typing import Any, Optional

from pydantic import Field

from cloudra.base.session_class import Session
from cloudra.base.tools_class import Tool, input_schema, output_schema

# 模糊命中下限：query token 覆盖率低于该值视为不相关
_FUZZY_FLOOR = 0.34
# search 一次扫描的最近帖子数（论坛规模有限，Python 侧打分足够快）
_SEARCH_SCAN_LIMIT = 500


def _query_tokens(text: str) -> set[str]:
    """英文按词、中文按 bigram 切 token，供模糊检索。"""
    tokens = set(re.findall(r"[a-z0-9_]+", text.lower()))
    for run in re.findall(r"[一-鿿]+", text):
        if len(run) == 1:
            tokens.add(run)
        else:
            tokens.update(run[i : i + 2] for i in range(len(run) - 1))
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
    "- **Addressing and notifications**: on post you may set to_agent (role name such as small_mol, ID such as a-4, or coordinator) "
    "to say who the content is mainly for — the post itself remains a public discussion trail anyone can read; "
    "the addressed Agent is notified immediately, and the original author is notified when their post is replied to.\n"
    "- **browse**: list recent topics and activity.\n"
    "- **read**: read posts for a topic (including Q&A threads).\n"
    "- **search**: search all posts by keyword (fuzzy match; exact wording not required).\n"
    "- **directory**: list project sessions with role, state, and parent_session_id (when dispatched as a sub-agent).\n"
    "- **call**: send a non-blocking message to an Agent session; an absent ordinary role creates an independent project peer (to + message, optional post_id). The new peer sends its first task result to the caller, without a parent/child link.\n"
    "Discipline: before starting a subtask that may overlap with another Agent, browse/search to see if someone already did it; "
    "after you get a reusable conclusion (parameters, data, pitfalls), post it to the matching topic. Posts must be self-contained — "
    "others do not have your context. If you are unsure about data or tool behavior, post a question or address someone with to_agent; "
    "do not conclude from memory alone."
)


class AgentHub_input_schema(input_schema):
    action: str = Field(description="Action: post / browse / read / search / directory / call")
    topic: str = Field(default="", description="Topic name (required for post/read), e.g. 'CO2 hydrogenation - literature'")
    content: str = Field(default="", description="Post body (required for post); must be self-contained")
    kind: str = Field(
        default="finding",
        description="Post kind: finding / question / answer / broadcast / message; all posts are public"
    )
    to_agent: str = Field(
        default="",
        description="Addressee: role name (e.g. small_mol), Agent ID (e.g. a-4), or coordinator; the post stays public and the addressee is notified"
    )
    to: str = Field(
        default="",
        description="call target: session_id, agent_id (e.g. a-4), role name (e.g. small_mol), or coordinator",
    )
    message: str = Field(default="", description="What you say to the other side on call (not a role prompt)")
    post_id: Optional[str] = Field(
        default=None,
        description="Related post ID for call; for post, retry missing notifications on this same post ID with unchanged fields",
    )
    parent_id: Optional[str] = Field(default=None, description="Post ID to reply to (string event id; old integer ids are accepted by the bridge)")
    keyword: str = Field(default="", description="Search keyword (required for search); fuzzy match, synonyms/inexact phrasing OK")
    limit: int = Field(default=20, description="Maximum number of items to return")
    cursor: Optional[str] = Field(default=None, description="Opaque browse cursor returned by a previous browse page")


class AgentHub_output_schema(output_schema):
    is_success: bool = Field(description="Whether the action succeeded")
    posts: list = Field(default_factory=list, description="Post list (read/search/browse results)")
    post_id: Optional[str] = Field(default=None, description="New post ID (post result)")
    notified_count: int = Field(default=0, description="Number of sessions notified for this post")
    failed_session_ids: list[str] = Field(default_factory=list, description="Recipients still missing a post notification")
    next_cursor: Optional[str] = Field(default=None, description="Opaque cursor for the next browse page")
    sources_status: dict = Field(default_factory=dict, description="Search source status (posts/library availability)")
    message: str = Field(default="", description="Status note")
    sessions: list = Field(default_factory=list, description="directory result")
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


def get_class():
    return AgentHub
