"""统一的 Agent 上下文管理器。

ContextManager 是 Agent 上下文的唯一真相来源，负责：
1. 从 JSON 文件加载/持久化上下文
2. 提供异步 append/replace 接口
3. 接收外部事件（邮件、计算任务状态变化等）并注入上下文
4. 轮询待处理的外部事件
"""

import os
import json
import time
from typing import Optional

import aiosqlite

from cloudra.config import get_config


def _context_file_path(agent_id: str, conversation_id: str) -> str:
    """返回指定 agent 在指定 conversation 下的上下文文件路径。"""
    data_dir = get_config().data_dir
    if conversation_id and conversation_id != 'default':
        base = os.path.join(data_dir, 'conversations', conversation_id, 'contexts')
    else:
        base = os.path.join(data_dir, 'contexts')
    os.makedirs(base, exist_ok=True)
    return os.path.join(base, f"{agent_id}.json")


def _db_path() -> str:
    """返回任务数据库路径。"""
    return os.path.join(get_config().data_dir, 'tasks', 'database.db')


class ContextManager:
    """管理单个 Agent 的上下文生命周期与外部事件注入。"""

    def __init__(
        self,
        agent_id: str,
        conversation_id: str,
        prompt: str,
        query: str,
        db_path: Optional[str] = None,
    ):
        self.agent_id = agent_id
        self.conversation_id = conversation_id or 'default'
        self.prompt = prompt
        self.query = query
        self.context_file = _context_file_path(agent_id, self.conversation_id)
        self.db_path = db_path or _db_path()

    def _initial_context(self) -> list:
        """构造初始上下文：system prompt + user query。"""
        return [
            {"role": "system", "content": self.prompt},
            {"role": "user", "content": self.query},
        ]

    async def load(self) -> list:
        """从文件加载上下文；若文件不存在则初始化并保存。"""
        if os.path.isfile(self.context_file):
            try:
                with open(self.context_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except json.JSONDecodeError as e:
                # 文件损坏时回退到初始上下文，避免直接崩溃
                print(f"[ContextManager] 上下文文件解析失败，已重置: {self.context_file}, 错误: {e}")

        context = self._initial_context()
        await self.replace(context)
        return context

    async def replace(self, context: list) -> None:
        """全量替换上下文并持久化到文件。"""
        os.makedirs(os.path.dirname(self.context_file), exist_ok=True)
        with open(self.context_file, 'w', encoding='utf-8') as f:
            json.dump(context, f, ensure_ascii=False, indent=4)

    async def append(self, new_block: dict) -> None:
        """追加一条消息到上下文，并持久化。"""
        if 'role' not in new_block:
            new_block['role'] = 'user'

        # 提取 image_path（如果存在），构建 OpenAI 标准 image_url 结构
        image_path = new_block.pop('image_path', None)
        if image_path:
            text_content = new_block.get('content', "查看此图片内容：")
            new_block['content'] = [
                {"type": "text", "text": text_content if text_content else "查看此图片内容："},
                {"type": "image_url", "image_url": {"url": image_path}},
            ]
        elif 'content' not in new_block:
            new_block['content'] = str(new_block)

        context = await self.load()
        context.append(new_block)
        await self.replace(context)

    async def clear(self) -> None:
        """清空上下文文件（用于任务结束后释放上下文）。"""
        await self.replace([])

    # ------------------------------------------------------------------
    # 外部事件接口
    # ------------------------------------------------------------------

    @staticmethod
    async def inject_event(
        conversation_id: str,
        agent_id: str,
        event_type: str,
        content: str,
        db_path: Optional[str] = None,
    ) -> None:
        """外部生产者调用，将事件写入 context_events 表。

        该方法是静态方法，因为生产者通常不持有目标 Agent 的 ContextManager 实例。
        """
        path = db_path or _db_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        async with aiosqlite.connect(path, timeout=10) as con:
            await con.execute(
                """
                INSERT INTO context_events (conversation_id, agent_id, event_type, content, state, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (conversation_id, agent_id, event_type, content, 'pending', time.time())
            )
            await con.commit()

    async def poll_external_events(self) -> list[dict]:
        """轮询属于本 agent 的 pending 外部事件，标记为 delivered 后返回。"""
        events = []
        async with aiosqlite.connect(self.db_path, timeout=10) as con:
            cur = await con.execute(
                """
                SELECT id, event_type, content FROM context_events
                WHERE conversation_id = ? AND agent_id = ? AND state = 'pending'
                ORDER BY created_at ASC
                """,
                (self.conversation_id, self.agent_id)
            )
            rows = await cur.fetchall()
            if rows:
                event_ids = [r[0] for r in rows]
                await con.execute(
                    "UPDATE context_events SET state = 'delivered' WHERE id IN ({})".format(
                        ','.join('?' * len(event_ids))
                    ),
                    event_ids
                )
                await con.commit()
                events = [
                    {"id": r[0], "event_type": r[1], "content": r[2]}
                    for r in rows
                ]
        return events

    async def has_pending_events(self) -> bool:
        """检查是否有待处理的外部事件。"""
        async with aiosqlite.connect(self.db_path, timeout=10) as con:
            cur = await con.execute(
                """
                SELECT COUNT(*) FROM context_events
                WHERE conversation_id = ? AND agent_id = ? AND state = 'pending'
                """,
                (self.conversation_id, self.agent_id)
            )
            row = await cur.fetchone()
            return row[0] > 0 if row else False
