"""AgentHub：子 Agent 之间的共享论坛。

并行的子 Agent 运行在各自独立的进程里，但共享同一个 conversation SQLite
数据库。本工具把数据库变成一块"留言板"：任何 Agent（包括只读的 explorer）
都可以发帖分享发现、提问、回答，或先查别人的帖子避免重复劳动。

帖子一律公开：to_agent 只是"点名"，帖子本身仍是全论坛可见的讨论痕迹；
被点名或被回复的 Agent 会收到事件通知（ContextManager.inject_event）。
检索为纯 Python 模糊匹配（英文按词、中文按 bigram 的 token 覆盖率），
不引入向量检索依赖。
"""

import asyncio
import re
from datetime import datetime, timezone
from typing import Any, Optional

from pydantic import Field

from cloudra.base.session_class import Session
from cloudra.base.tools_class import Tool, _tool_db_path, input_schema, output_schema
from cloudra.persistence.database import ConversationDB, aretry_on_locked
from cloudra.tools.Managetool._hub_call import (
    deliver_incoming_call,
    format_incoming_call,
    list_directory,
    lookup_post,
    resolve_agent_id,
    resolve_call_target,
    resume_follower_if_idle,
    spawn_from_call,
)


def _resolve_agent_id(target: str) -> str | None:
    return resolve_agent_id(target)


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
    "- **directory**: list all sessions in this conversation (session_id, agent_id, state, task).\n"
    "- **call**: place a live call to another Agent (to + message, optional post_id).\n"
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
    post_id: Optional[int] = Field(default=None, description="Optional related post ID for call")
    parent_id: Optional[int] = Field(default=None, description="Post ID to reply to (optional); a reply notifies the original author")
    keyword: str = Field(default="", description="Search keyword (required for search); fuzzy match, synonyms/inexact phrasing OK")
    limit: int = Field(default=20, description="Maximum number of items to return")


class AgentHub_output_schema(output_schema):
    is_success: bool = Field(description="Whether the action succeeded")
    posts: list = Field(default_factory=list, description="Post list (read/search/browse results)")
    post_id: int = Field(default=0, description="New post ID (post result)")
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
        # 消息板是 Agent 间的通信渠道，不涉及文件系统/系统状态变更，
        # 只读权限的 Agent（如 explorer）也应能发帖与浏览。
        return True

    def _db(self) -> ConversationDB:
        db = ConversationDB.from_path(_tool_db_path(self.subagent))
        return db

    @staticmethod
    def _row_to_dict(row) -> dict:
        return {
            "id": row[0],
            "topic": row[1],
            "kind": row[2],
            "author_agent": row[3],
            "author_session": row[4],
            "to_agent": row[5],
            "parent_id": row[6],
            "content": row[7],
            "created_at": row[8],
        }

    async def tool_call(self, user_input: AgentHub_input_schema, session: Session) -> AgentHub_output_schema:
        db = self._db()
        await db.ainit()
        action = user_input.action.strip().lower()

        if action == "post":
            return await self._post(db, user_input)
        if action == "browse":
            return await self._browse(db, user_input)
        if action == "read":
            return await self._read(db, user_input)
        if action == "search":
            return await self._search(db, user_input)
        if action == "directory":
            rows = await list_directory(db)
            return AgentHub_output_schema(
                is_success=True,
                sessions=rows,
                message=f"{len(rows)} session(s)." if rows else "No sessions right now.",
            )
        if action == "call":
            return await self._call(db, user_input)
        return AgentHub_output_schema(
            is_success=False,
            message=f"Unknown action: {user_input.action}. Available: post / browse / read / search / directory / call",
        )

    async def _call(self, db: ConversationDB, user_input: AgentHub_input_schema) -> AgentHub_output_schema:
        spoken = user_input.message.strip()
        if not spoken:
            return AgentHub_output_schema(is_success=False, message="call requires a non-empty message.")

        kind, data = await asyncio.to_thread(resolve_call_target, user_input.to, db=db)
        if kind == "error":
            return AgentHub_output_schema(is_success=False, message=data["message"])

        caller_agent = getattr(self.subagent, "id", None) or getattr(self.subagent, "name", "unknown")
        caller_session = getattr(self.subagent, "session_id", None) or ""
        post_line = None
        if user_input.post_id:
            post = await lookup_post(db, user_input.post_id)
            if post is not None:
                post_line = f"Related post #{post['id']} (topic {post['topic']})."
        text = format_incoming_call(
            caller_agent_id=str(caller_agent),
            caller_session_id=str(caller_session),
            message=spoken,
            post_line=post_line,
        )
        if kind == "spawn":
            try:
                session_id = await spawn_from_call(
                    agent_id=data["agent_id"],
                    message=spoken,
                    incoming_text=text,
                    conversation_id=getattr(self.subagent, "conversation_id", "default") or "default",
                    working_directory=getattr(self.subagent, "working_directory", None),
                    parent_session_id=caller_session or None,
                    parent_orchestration_mode=getattr(self.subagent, "orchestration_mode", "standard"),
                    caller_agent_id=str(caller_agent),
                    caller_session_id=str(caller_session),
                )
            except ValueError as exc:
                return AgentHub_output_schema(is_success=False, message=str(exc))
            return AgentHub_output_schema(
                is_success=True,
                session_id=session_id,
                message=f"Called {session_id} (non-blocking).",
            )

        await deliver_incoming_call(
            conversation_id=getattr(self.subagent, "conversation_id", "default") or "default",
            callee_agent_id=data["agent_id"],
            callee_session_id=data["session_id"],
            text=text,
            db_path=_tool_db_path(self.subagent),
        )
        await resume_follower_if_idle(
            db=db,
            conversation_id=getattr(self.subagent, "conversation_id", "default") or "default",
            session_id=data["session_id"],
            agent_id=data["agent_id"],
            working_directory=getattr(self.subagent, "working_directory", None),
            orchestration_mode=getattr(self.subagent, "orchestration_mode", "standard"),
            parent_session_id=caller_session or None,
            caller_agent_id=str(caller_agent),
            caller_session_id=str(caller_session),
        )
        return AgentHub_output_schema(
            is_success=True,
            session_id=data["session_id"],
            message=f"Called {data['session_id']} (non-blocking).",
        )

    async def _post(self, db: ConversationDB, user_input: AgentHub_input_schema) -> AgentHub_output_schema:
        topic = user_input.topic.strip()
        content = user_input.content.strip()
        if not topic or not content:
            return AgentHub_output_schema(is_success=False, message="post requires non-empty topic and content.")
        kind = user_input.kind.strip().lower() or "finding"
        if kind not in ("finding", "question", "answer", "broadcast", "message"):
            return AgentHub_output_schema(is_success=False, message=f"Unknown kind: {kind}")
        to_agent = user_input.to_agent.strip()
        target_id = None
        if to_agent:
            target_id = _resolve_agent_id(to_agent)
            if target_id is None:
                return AgentHub_output_schema(
                    is_success=False,
                    message=f"Unknown to_agent: {to_agent} (use a role name such as small_mol, an ID such as a-4, or coordinator)",
                )
        if kind == "message" and not to_agent:
            return AgentHub_output_schema(
                is_success=False, message="message posts need to_agent to name the addressee (the post is still public)."
            )

        author_agent = getattr(self.subagent, 'name', None) or "unknown"
        author_session = getattr(self.subagent, 'session_id', None) or ""
        created_at = datetime.now(timezone.utc).isoformat()

        async def insert():
            async with db.aconnect() as con:
                cur = await con.execute(
                    "INSERT INTO hub_posts (topic, kind, author_agent, author_session, to_agent, parent_id, content, created_at)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (topic, kind, author_agent, author_session, to_agent or None, user_input.parent_id, content, created_at),
                )
                await con.commit()
                return cur.lastrowid

        post_id = await aretry_on_locked(insert)
        notice = await self._notify(
            db,
            user_input=user_input,
            author_agent=author_agent,
            post_id=post_id,
            target_id=target_id,
        )
        message = f"Posted to topic '{topic}' (id={post_id})."
        if notice:
            message += notice
        return AgentHub_output_schema(
            is_success=True,
            post_id=post_id,
            message=message,
        )

    @staticmethod
    async def _get_post(db: ConversationDB, post_id: int) -> dict | None:
        async def query():
            async with db.aconnect() as con:
                cur = await con.execute(
                    "SELECT id, topic, kind, author_agent, author_session, to_agent, parent_id, content, created_at"
                    " FROM hub_posts WHERE id = ?",
                    (post_id,),
                )
                return await cur.fetchone()

        row = await aretry_on_locked(query)
        return AgentHub._row_to_dict(row) if row else None

    async def _notify(
        self,
        db: ConversationDB,
        *,
        user_input: AgentHub_input_schema,
        author_agent: str,
        post_id: int,
        target_id: str | None,
    ) -> str:
        """被点名（to_agent）或被回复（parent_id 的原作者）时注入事件通知。

        通知是 best-effort：帖子已落库且公开可查，通知失败不阻断发帖。
        """
        conversation_id = getattr(self.subagent, "conversation_id", "default") or "default"
        db_path = _tool_db_path(self.subagent)
        # 延迟导入，避免工具加载期拖入 ContextManager 依赖链
        from cloudra.persistence.context_manager import ContextManager

        notices = []
        try:
            if target_id is not None:
                await ContextManager.inject_event(
                    conversation_id=conversation_id,
                    agent_id=target_id,
                    event_type="hub_message",
                    content=(
                        f"{author_agent} mentioned you in AgentHub topic '{user_input.topic.strip()}' "
                        f"(post #{post_id}): {user_input.content.strip()[:500]}"
                    ),
                    db_path=db_path,
                )
                notices.append(f"Notified {user_input.to_agent.strip()}.")
            if user_input.parent_id is not None:
                parent = await self._get_post(db, user_input.parent_id)
                if parent is not None and parent["author_agent"] != author_agent:
                    parent_target = _resolve_agent_id(parent["author_agent"])
                    if parent_target is not None and parent_target != target_id:
                        await ContextManager.inject_event(
                            conversation_id=conversation_id,
                            agent_id=parent_target,
                            event_type="hub_reply",
                            content=(
                                f"{author_agent} replied to your AgentHub post in topic '{parent['topic']}' "
                                f"#{parent['id']} (reply #{post_id}): {user_input.content.strip()[:500]}"
                            ),
                            db_path=db_path,
                        )
                        notices.append(f"Notified original author {parent['author_agent']}.")
        except Exception:
            notices.append("(event notify failed; the post was saved publicly)")
        return " " + " ".join(notices) if notices else ""

    async def _browse(self, db: ConversationDB, user_input: AgentHub_input_schema) -> AgentHub_output_schema:
        async def query():
            async with db.aconnect() as con:
                cur = await con.execute(
                    "SELECT topic, COUNT(*) AS n, MAX(created_at) AS latest"
                    " FROM hub_posts GROUP BY topic ORDER BY latest DESC LIMIT ?",
                    (user_input.limit,),
                )
                return await cur.fetchall()

        rows = await aretry_on_locked(query)
        topics = [{"topic": r[0], "post_count": r[1], "latest_at": r[2]} for r in rows]
        return AgentHub_output_schema(
            is_success=True,
            posts=topics,
            message=f"{len(topics)} topic(s)." if topics else "The forum has no posts yet.",
        )

    async def _read(self, db: ConversationDB, user_input: AgentHub_input_schema) -> AgentHub_output_schema:
        topic = user_input.topic.strip()
        if not topic:
            return AgentHub_output_schema(is_success=False, message="read requires a topic.")

        async def query():
            async with db.aconnect() as con:
                cur = await con.execute(
                    "SELECT id, topic, kind, author_agent, author_session, to_agent, parent_id, content, created_at"
                    " FROM hub_posts WHERE topic = ? ORDER BY id ASC LIMIT ?",
                    (topic, user_input.limit),
                )
                return await cur.fetchall()

        rows = await aretry_on_locked(query)
        posts = [self._row_to_dict(r) for r in rows]
        return AgentHub_output_schema(
            is_success=True,
            posts=posts,
            message=f"Topic '{topic}' has {len(posts)} post(s)." if posts else f"Topic '{topic}' has no posts yet.",
        )

    async def _search(self, db: ConversationDB, user_input: AgentHub_input_schema) -> AgentHub_output_schema:
        keyword = user_input.keyword.strip()
        if not keyword:
            return AgentHub_output_schema(is_success=False, message="search requires a keyword.")

        # 模糊检索：取最近一批帖子在 Python 侧打分——子串精确命中排最前，
        # 其余按 query token（英文按词、中文按 bigram）在主题/正文中的覆盖率排序。
        async def query():
            async with db.aconnect() as con:
                cur = await con.execute(
                    "SELECT id, topic, kind, author_agent, author_session, to_agent, parent_id, content, created_at"
                    " FROM hub_posts ORDER BY id DESC LIMIT ?",
                    (_SEARCH_SCAN_LIMIT,),
                )
                return await cur.fetchall()

        rows = await aretry_on_locked(query)
        scored = []
        for row in rows:
            post = self._row_to_dict(row)
            score = max(
                _fuzzy_score(keyword, post["topic"]),
                _fuzzy_score(keyword, post["content"]) * 0.9,
            )
            if score >= _FUZZY_FLOOR:
                post["score"] = round(score, 3)
                scored.append((score, post["id"], post))
        scored.sort(key=lambda item: (-item[0], -item[1]))
        posts = [post for _, _, post in scored[: user_input.limit]]
        return AgentHub_output_schema(
            is_success=True,
            posts=posts,
            message=(
                f"Keyword '{keyword}' fuzzy-matched {len(posts)} post(s) (scanned the latest {len(rows)})."
                if posts else f"Keyword '{keyword}' had no hits."
            ),
        )


def get_class():
    return AgentHub
