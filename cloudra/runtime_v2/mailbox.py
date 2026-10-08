"""Uniform message payload shapes for the event log and the ephemeral inbox.

载荷形状的唯一事实来源在本模块（``message_data`` 事件载荷 /
``message_payload`` inbox 载荷）。Agent 间投递走
``MessageDispatcher.commit_and_deliver``（persist → enqueue → wake）；命令路径
的 ``agent.message`` 经 CommandBus 落 ``agent.message_injected`` 后再
``DeliverMessage`` 入队——两边都是持久化成功才可见，不再有「先入队、事后
flush」的第二条语义。

易失性（3e）与恢复语义：inbox 是进程内的内存队列（shell 私有），但**不是一次性的**。
它的权威来源是 ``agent.message_injected`` 事件，重建的唯一实现在
``persistence._rebuild_inboxes_from_events``（``restore_core`` 调用）：尚未进入会话
上下文投影的投递（按 message_id 判重）重新入队，所以「已持久化、还没被消费」的用户
消息与子 agent 回传跨重启不丢；CANCELLED agent 只补 peer 完成与 hub 定向通知。
重投只恢复「待消费」这一事实，**不重放唤醒**：恢复期不 wake 任何人（含休眠父），
载荷驻留信箱直到显式 resume 或下一条消息带来唤醒。
"""

from __future__ import annotations

import asyncio
from typing import Any

from cloudra.runtime_v2.events import EventLog


class Mailbox:
    def __init__(self, event_log: EventLog) -> None:
        self._event_log = event_log
        self._inboxes: dict[str, asyncio.Queue[dict[str, Any]]] = {}

    def ensure_inbox(self, session_id: str) -> asyncio.Queue[dict[str, Any]]:
        return self._inboxes.setdefault(session_id, asyncio.Queue())

    def inbox(self, session_id: str) -> asyncio.Queue[dict[str, Any]] | None:
        return self._inboxes.get(session_id)

    def drop_inbox(self, session_id: str) -> None:
        """丢弃指定 inbox（项目硬删除时清理；幂等，无此 inbox 也安全）。"""
        self._inboxes.pop(session_id, None)

    def prune_sessions(self, session_ids: set[str]) -> None:
        for session_id in self._inboxes.keys() - session_ids:
            self.drop_inbox(session_id)

    # ------------------------------------------------------- payload builders

    @staticmethod
    def message_data(
        *,
        message_id: str,
        sender: str,
        content: str,
        images: list[str] | None = None,
        image_artifact_ids: list[str | None] | None = None,
        post_id: str | None = None,
        manifest: dict[str, Any] | None = None,
        language: str | None = None,
    ) -> dict[str, Any]:
        """agent.message_injected 的事件载荷。"""
        data: dict[str, Any] = {"message_id": message_id, "sender": sender, "content": content}
        if manifest is not None:
            # 结构化完成回报（子 agent manifest）：事件/API 侧保留结构化数据，
            # inbox 载荷与父上下文只拿渲染后的文本。
            data["manifest"] = manifest
        if post_id:
            data["post_id"] = post_id
        if images:
            # Workspace-absolute image paths attached by the user; the runner
            # turns them into vision parts (or a text fallback) and the
            # frontend renders them on the user bubble.
            data["images"] = list(images)
        if image_artifact_ids:
            # Parallel to images: artifact ids let the frontend rebuild bubble
            # image URLs after a reload (paths alone are not HTTP-reachable).
            data["image_artifact_ids"] = list(image_artifact_ids)
        if language:
            data["language"] = language
        return data

    @staticmethod
    def message_payload(
        *,
        message_id: str,
        sender: str,
        content: str,
        images: list[str] | None = None,
        post_id: str | None = None,
    ) -> dict[str, Any]:
        """inbox 入队载荷（artifact id 只走事件，不进队列）。"""
        payload = {
            "type": "message",
            "message_id": message_id,
            "sender": sender,
            "content": content,
            **({"images": list(images)} if images else {}),
        }
        if post_id:
            payload["post_id"] = post_id
        return payload

    # ------------------------------------------------------------- delivery

    def enqueue(self, to_session_id: str, message: dict[str, Any]) -> None:
        """纯入队（事件已由调用方落日志）——DeliverMessage 效果的执行点。"""
        self.ensure_inbox(to_session_id).put_nowait(message)
