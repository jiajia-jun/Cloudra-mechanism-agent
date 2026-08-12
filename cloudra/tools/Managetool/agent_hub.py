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
    "AgentHub：所有并行 Agent 共享的信息论坛，一切帖子对全体 Agent 公开。你可以在这里：\n"
    "- **post**：发布发现（finding）、提问（question）、回答（answer）、广播（broadcast）或留言（message），"
    "回复某帖时传 parent_id。\n"
    "- **点名与通知**：post 时可填 to_agent（角色名如 small_mol、ID 如 a-4，或 coordinator）表示"
    "这条内容主要写给谁——帖子本身仍是公开的讨论痕迹，任何人都能读到；被点名的 Agent 会立即收到"
    "事件通知，帖子被回复时原作者同样会收到通知。\n"
    "- **browse**：浏览最近有哪些主题（topic）及活跃度。\n"
    "- **read**：按主题读取帖子（含问答串）。\n"
    "- **search**：按关键词检索所有帖子（模糊匹配，无需精确用词）。\n"
    "- **directory**：列出本对话所有 session（session_id、agent_id、state、task）。\n"
    "- **call**：向另一 Agent 发起实时来电（to + message，可选 post_id）。\n"
    "使用纪律：开始一个与其他 Agent 可能重叠的子任务前，先 browse/search 看看有没有人已经做过；"
    "得到可复用的关键结论（参数、数据、坑）后，post 到对应主题。帖子内容要自包含，"
    "别人没有你的上下文。对数据或工具行为有疑惑时，发 question 或用 to_agent 点名求助，"
    "不要独自凭记忆下结论。"
)


class AgentHub_input_schema(input_schema):
    action: str = Field(description="操作类型：post / browse / read / search / directory / call")
    topic: str = Field(default="", description="主题名（post/read 必填），如 'CO2加氢-文献调研'")
    content: str = Field(default="", description="帖子内容（post 必填），要求自包含")
    kind: str = Field(
        default="finding",
        description="帖子类型：finding（发现）/ question（提问）/ answer（回答）/ broadcast（广播）/ message（留言）；帖子一律公开"
    )
    to_agent: str = Field(
        default="",
        description="点名对象：角色名（如 small_mol）、Agent ID（如 a-4）或 coordinator；帖子仍公开，被点名者会收到事件通知"
    )
    to: str = Field(
        default="",
        description="call 目标：session_id、agent_id（如 a-4）、角色名（如 small_mol）或 coordinator",
    )
    message: str = Field(default="", description="call 时你要对对面说的话（不是角色 prompt）")
    post_id: Optional[int] = Field(default=None, description="call 时可选的对照帖子 ID")
    parent_id: Optional[int] = Field(default=None, description="回复的帖子 ID（可选）；回复会通知原作者")
    keyword: str = Field(default="", description="检索关键词（search 必填），模糊匹配，可用近义词/不精确措辞")
    limit: int = Field(default=20, description="最大返回条数")


class AgentHub_output_schema(output_schema):
    is_success: bool = Field(description="操作是否成功")
    posts: list = Field(default_factory=list, description="帖子列表（read/search/browse 结果）")
    post_id: int = Field(default=0, description="新帖 ID（post 结果）")
    message: str = Field(default="", description="状态说明")
    sessions: list = Field(default_factory=list, description="directory 结果")
    session_id: str = Field(default="", description="call 结果：对方 session_id")


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
                message=f"共 {len(rows)} 个 session。" if rows else "当前没有 session。",
            )
        if action == "call":
            return await self._call(db, user_input)
        return AgentHub_output_schema(
            is_success=False,
            message=f"未知 action: {user_input.action}，可用：post / browse / read / search / directory / call",
        )

    async def _call(self, db: ConversationDB, user_input: AgentHub_input_schema) -> AgentHub_output_schema:
        spoken = user_input.message.strip()
        if not spoken:
            return AgentHub_output_schema(is_success=False, message="call 需要非空的 message。")

        kind, data = await asyncio.to_thread(resolve_call_target, user_input.to, db=db)
        if kind == "error":
            return AgentHub_output_schema(is_success=False, message=data["message"])

        caller_agent = getattr(self.subagent, "id", None) or getattr(self.subagent, "name", "unknown")
        caller_session = getattr(self.subagent, "session_id", None) or ""
        post_line = None
        if user_input.post_id:
            post = await lookup_post(db, user_input.post_id)
            if post is not None:
                post_line = f"对照帖子 #{post['id']}（主题 {post['topic']}）。"
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
                message=f"已呼叫 {session_id}（不阻塞）。",
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
            message=f"已呼叫 {data['session_id']}（不阻塞）。",
        )

    async def _post(self, db: ConversationDB, user_input: AgentHub_input_schema) -> AgentHub_output_schema:
        topic = user_input.topic.strip()
        content = user_input.content.strip()
        if not topic or not content:
            return AgentHub_output_schema(is_success=False, message="post 需要非空的 topic 和 content。")
        kind = user_input.kind.strip().lower() or "finding"
        if kind not in ("finding", "question", "answer", "broadcast", "message"):
            return AgentHub_output_schema(is_success=False, message=f"未知 kind: {kind}")
        to_agent = user_input.to_agent.strip()
        target_id = None
        if to_agent:
            target_id = _resolve_agent_id(to_agent)
            if target_id is None:
                return AgentHub_output_schema(
                    is_success=False,
                    message=f"未知的 to_agent: {to_agent}（可用角色名如 small_mol、ID 如 a-4、coordinator）",
                )
        if kind == "message" and not to_agent:
            return AgentHub_output_schema(
                is_success=False, message="message 类帖子需要 to_agent 指明写给谁（帖子仍公开）。"
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
        message = f"已发布到主题 '{topic}'（id={post_id}）。"
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
                        f"{author_agent} 在 AgentHub 主题 '{user_input.topic.strip()}' 点名你"
                        f"（帖子 #{post_id}）：{user_input.content.strip()[:500]}"
                    ),
                    db_path=db_path,
                )
                notices.append(f"已通知 {user_input.to_agent.strip()}。")
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
                                f"{author_agent} 回复了你在 AgentHub 主题 '{parent['topic']}' 的帖子"
                                f" #{parent['id']}（回复 #{post_id}）：{user_input.content.strip()[:500]}"
                            ),
                            db_path=db_path,
                        )
                        notices.append(f"已通知原作者 {parent['author_agent']}。")
        except Exception:
            notices.append("（事件通知发送失败，帖子已公开保存）")
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
            message=f"共 {len(topics)} 个主题。" if topics else "论坛暂无帖子。",
        )

    async def _read(self, db: ConversationDB, user_input: AgentHub_input_schema) -> AgentHub_output_schema:
        topic = user_input.topic.strip()
        if not topic:
            return AgentHub_output_schema(is_success=False, message="read 需要指定 topic。")

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
            message=f"主题 '{topic}' 共 {len(posts)} 帖。" if posts else f"主题 '{topic}' 暂无帖子。",
        )

    async def _search(self, db: ConversationDB, user_input: AgentHub_input_schema) -> AgentHub_output_schema:
        keyword = user_input.keyword.strip()
        if not keyword:
            return AgentHub_output_schema(is_success=False, message="search 需要指定 keyword。")

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
                f"关键词 '{keyword}' 模糊命中 {len(posts)} 帖（扫描最近 {len(rows)} 帖）。"
                if posts else f"关键词 '{keyword}' 无命中。"
            ),
        )


def get_class():
    return AgentHub
