"""AgentHub：子 Agent 之间的共享论坛。

并行的子 Agent 运行在各自独立的进程里，但共享同一个 conversation SQLite
数据库。本工具把数据库变成一块"留言板"：任何 Agent（包括只读的 explorer）
都可以发帖分享发现、提问、回答，或先查别人的帖子避免重复劳动。
"""

from datetime import datetime, timezone
from typing import Any, Optional

from pydantic import Field

from cloudra.database import ConversationDB, aretry_on_locked
from cloudra.session_class import Session
from cloudra.tools_class import Tool, _tool_db_path, input_schema, output_schema

description = (
    "AgentHub：所有并行 Agent 共享的信息论坛。你可以在这里：\n"
    "- **post**：发布发现（finding）、提问（question）、回答（answer）或广播（broadcast），"
    "供其他正在并行工作的 Agent 查看，避免重复劳动；回复某帖时传 parent_id。\n"
    "- **browse**：浏览最近有哪些主题（topic）及活跃度。\n"
    "- **read**：按主题读取帖子（含问答串）。\n"
    "- **search**：按关键词搜索所有帖子。\n"
    "使用纪律：开始一个与其他 Agent 可能重叠的子任务前，先 browse/search 看看有没有人已经做过；"
    "得到可复用的关键结论（参数、数据、坑）后，post 到对应主题。帖子内容要自包含，"
    "别人没有你的上下文。"
)


class AgentHub_input_schema(input_schema):
    action: str = Field(description="操作类型：post / browse / read / search")
    topic: str = Field(default="", description="主题名（post/read 必填），如 'CO2加氢-文献调研'")
    content: str = Field(default="", description="帖子内容（post 必填），要求自包含")
    kind: str = Field(
        default="finding",
        description="帖子类型：finding（发现）/ question（提问）/ answer（回答）/ broadcast（广播）"
    )
    parent_id: Optional[int] = Field(default=None, description="回复的帖子 ID（可选）")
    keyword: str = Field(default="", description="搜索关键词（search 必填）")
    limit: int = Field(default=20, description="最大返回条数")


class AgentHub_output_schema(output_schema):
    is_success: bool = Field(description="操作是否成功")
    posts: list = Field(default_factory=list, description="帖子列表（read/search/browse 结果）")
    post_id: int = Field(default=0, description="新帖 ID（post 结果）")
    message: str = Field(default="", description="状态说明")


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
            "parent_id": row[5],
            "content": row[6],
            "created_at": row[7],
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
        return AgentHub_output_schema(
            is_success=False,
            message=f"未知 action: {user_input.action}，可用：post / browse / read / search",
        )

    async def _post(self, db: ConversationDB, user_input: AgentHub_input_schema) -> AgentHub_output_schema:
        topic = user_input.topic.strip()
        content = user_input.content.strip()
        if not topic or not content:
            return AgentHub_output_schema(is_success=False, message="post 需要非空的 topic 和 content。")
        kind = user_input.kind.strip().lower() or "finding"
        if kind not in ("finding", "question", "answer", "broadcast"):
            return AgentHub_output_schema(is_success=False, message=f"未知 kind: {kind}")

        author_agent = getattr(self.subagent, 'name', None) or "unknown"
        author_session = getattr(self.subagent, 'session_id', None) or ""
        created_at = datetime.now(timezone.utc).isoformat()

        async def insert():
            async with db.aconnect() as con:
                cur = await con.execute(
                    "INSERT INTO hub_posts (topic, kind, author_agent, author_session, parent_id, content, created_at)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (topic, kind, author_agent, author_session, user_input.parent_id, content, created_at),
                )
                await con.commit()
                return cur.lastrowid

        post_id = await aretry_on_locked(insert)
        return AgentHub_output_schema(
            is_success=True,
            post_id=post_id,
            message=f"已发布到主题 '{topic}'（id={post_id}）。",
        )

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
                    "SELECT id, topic, kind, author_agent, author_session, parent_id, content, created_at"
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
        pattern = f"%{keyword}%"

        async def query():
            async with db.aconnect() as con:
                cur = await con.execute(
                    "SELECT id, topic, kind, author_agent, author_session, parent_id, content, created_at"
                    " FROM hub_posts WHERE content LIKE ? OR topic LIKE ? ORDER BY id DESC LIMIT ?",
                    (pattern, pattern, user_input.limit),
                )
                return await cur.fetchall()

        rows = await aretry_on_locked(query)
        posts = [self._row_to_dict(r) for r in rows]
        return AgentHub_output_schema(
            is_success=True,
            posts=posts,
            message=f"关键词 '{keyword}' 命中 {len(posts)} 帖。" if posts else f"关键词 '{keyword}' 无命中。",
        )


def get_class():
    return AgentHub
