"""Uniform delivery for user and peer messages.

Every message is one event + one inbox enqueue.  The runtime never inspects
sender authority beyond the caller-provided actor: the command layer performs
authorization before calling deliver.

载荷形状的唯一事实来源在本模块（``message_data`` 事件载荷 /
``message_payload`` inbox 载荷）：命令侧 decide 用它们组装
``agent.message_injected`` 草稿与 ``DeliverMessage`` 效果，事件先于投递落地
且 message_id 一致；非命令路径（hub_bridge 等）继续用 ``deliver`` 一步走。

易失性（3e）：inbox 是**刻意易失**的内存队列（shell 私有，重启即弃）——
run 只活在内存，重启后没有消费者在等队列里的载荷；``agent.message_injected``
事件是投递的审计记录，但不据此重建队列（恢复后由新发消息驱动唤醒）。
"""

from __future__ import annotations

import asyncio
from typing import Any

from cloudra.runtime_v2.events import EventLog
from cloudra.runtime_v2.schemas import EventEnvelope, new_id


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

    def deliver(
        self,
        *,
        to_session_id: str,
        project_id: str,
        content: str,
        sender: str,
        run_id: str | None = None,
        images: list[str] | None = None,
        image_artifact_ids: list[str | None] | None = None,
        post_id: str | None = None,
        manifest: dict[str, Any] | None = None,
    ) -> EventEnvelope:
        message_id = new_id("msg")
        envelope = self._event_log.append(
            "agent.message_injected",
            stream="project",
            project_id=project_id,
            session_id=to_session_id,
            run_id=run_id,
            data=self.message_data(
                message_id=message_id,
                sender=sender,
                content=content,
                images=images,
                image_artifact_ids=image_artifact_ids,
                post_id=post_id,
                manifest=manifest,
            ),
        )
        self.enqueue(
            to_session_id,
            self.message_payload(
                message_id=message_id,
                sender=sender,
                content=content,
                images=images,
                post_id=post_id,
            ),
        )
        return envelope
