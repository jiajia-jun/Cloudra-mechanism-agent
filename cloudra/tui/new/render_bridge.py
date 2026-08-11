"""IPC 事件 → Textual widget 更新的适配层。"""

from __future__ import annotations

import asyncio
import copy
import json
import logging
from typing import Iterable

from cloudra.infra import events

logger = logging.getLogger(__name__)

# 回放历史时跳过的事件类型（内部状态/命令，无可显示内容）
_REPLAY_SKIP = {
    "queued",
    "running",
    "cancel_requested",
    "client_command_received",
    "client_command_applied",
    "phase",
}

# 终态取消类事件 → 聊天区提示文案
_CANCEL_LABELS = {
    "cancelled": "已取消",
    "interrupted": "已打断",
    "killed": "已终止",
}


def _display_text(value) -> str:
    """把任意工具参数/结果转成可展示的字符串：字符串原样返回，其他序列化为 JSON。"""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False, indent=2, default=str)
    except (TypeError, ValueError):
        return str(value)


MAX_BATCH_SECONDS = 0.004
MAX_BATCH_MESSAGES = 256


def stream_key(message: dict) -> tuple[str, str, str] | None:
    """Return the key for adjacent chunk merging, or None for non-chunk events."""
    if message.get("kind") != "session_event" or message.get("event_type") != "llm_chunk":
        return None
    data = message.get("data") or {}
    return (
        str(message.get("session_id") or ""),
        str(data.get("stream") or "content"),
        str(data.get("agent_name") or "Agent"),
    )


def reduce_event_batch(messages: Iterable[dict]) -> list[dict]:
    """Merge adjacent compatible stream deltas while preserving all ordering boundaries."""
    reduced: list[dict] = []
    for message in messages:
        key = stream_key(message)
        if reduced and key is not None and stream_key(reduced[-1]) == key:
            merged = copy.deepcopy(reduced[-1])
            merged["data"]["delta"] = str(merged["data"].get("delta", "")) + str(
                (message.get("data") or {}).get("delta", "")
            )
            reduced[-1] = merged
        else:
            reduced.append(message)
    return reduced


class RenderBridge:
    """订阅 conversation 级 IPC 事件，并按 session_id 分发给对应 widget。"""

    MAX_BATCH_SECONDS = MAX_BATCH_SECONDS
    MAX_BATCH_MESSAGES = MAX_BATCH_MESSAGES

    def __init__(
        self,
        conversation_id: str,
        chat_log,
        status_bar=None,
        on_approval=None,
        on_ask_user=None,
        on_context_dirty=None,
        on_session_state=None,
        on_token_usage=None,
        on_plan_dirty=None,
        on_compaction_progress=None,
    ):
        self.conversation_id = conversation_id
        self.chat_log = chat_log
        self.status_bar = status_bar
        self.on_approval = on_approval
        self.on_ask_user = on_ask_user
        # Coordinator（a-0）上下文发生变化时触发（流式结束/任务终态）
        self.on_context_dirty = on_context_dirty
        # session 状态变化或首次见到某 session 时触发（供 Agent 列表刷新）
        self.on_session_state = on_session_state
        # 每轮推理的真实 token usage（累计值）到达时触发
        self.on_token_usage = on_token_usage
        # todo_write / goal_set 更新了计划文件时触发
        self.on_plan_dirty = on_plan_dirty
        self.on_compaction_progress = on_compaction_progress
        # 已经有流式正文上屏的 session（completed 事件据此决定是否补显示 result）
        self._streamed: set[str] = set()
        self._known_sessions: set[str] = set()
        self._queue: asyncio.Queue | None = None
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        """启动事件监听循环。"""
        self._queue = await events.subscribe_async(
            self.conversation_id,
            (
                "session_event",
                "session_state",
                "approval_pending",
                "interaction_requested",
                "context_compaction",
            ),
        )
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        """停止事件监听。"""
        task = self._task
        self._task = None
        self._queue = None
        if task is not None:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    async def _loop(self) -> None:
        while True:
            queue = self._queue
            if queue is None:
                return
            batch = [await queue.get()]
            loop = asyncio.get_running_loop()
            deadline = loop.time() + self.MAX_BATCH_SECONDS
            while len(batch) < self.MAX_BATCH_MESSAGES and loop.time() < deadline:
                try:
                    batch.append(queue.get_nowait())
                except asyncio.QueueEmpty:
                    break
            for message in reduce_event_batch(batch):
                try:
                    self._dispatch(message)
                except Exception:
                    logger.exception(
                        "TUI event dispatch failed: %s",
                        message.get("event_type") or message.get("kind"),
                    )
            if queue.empty():
                await asyncio.sleep(0)
            else:
                # Yield control so key/mouse/cancellation events are serviced.
                await asyncio.sleep(0)

    def _dispatch(self, msg: dict) -> None:
        kind = msg.get("kind")
        if kind == "session_event":
            self._on_session_event(msg)
        elif kind == "session_state":
            self._on_session_state(msg)
        elif kind == "approval_pending":
            self._on_approval_pending(msg)
        elif kind == "interaction_requested":
            self._on_interaction(msg)
        elif kind == "context_compaction":
            if self.on_compaction_progress:
                self.on_compaction_progress(msg)

    def replay_event(self, session_id: str, event_type: str, data: dict) -> None:
        """回放一条历史事件到 ChatLog（不触碰状态栏/审批弹窗）。"""
        if event_type in _REPLAY_SKIP:
            return
        self._on_session_event(
            {"session_id": session_id, "event_type": event_type, "data": data or {}}
        )

    def _on_session_event(self, msg: dict) -> None:
        session_id = msg.get("session_id")
        event_type = msg.get("event_type")
        data = msg.get("data") or {}
        if session_id is None or event_type is None:
            return

        # 确保 chat_log 知道这个 session
        self.chat_log.ensure_session(session_id)
        if session_id not in self._known_sessions:
            self._known_sessions.add(session_id)
            self._notify_session_state(session_id, None)

        if event_type == "llm_chunk":
            agent_name = data.get("agent_name", "Agent")
            stream = data.get("stream")
            delta = data.get("delta", "")
            if stream == "reasoning":
                self.chat_log.append_reasoning_chunk(session_id, delta)
            else:
                if delta:
                    self._streamed.add(session_id)
                self.chat_log.append_stream_chunk(session_id, delta, agent_name)
        elif event_type == "llm_stream_end":
            self.chat_log.end_stream(session_id)
            self._mark_context_dirty(session_id)
        elif event_type == "failed":
            # 失败必须可见：否则用户看到的是"agent 不回答"
            self.chat_log.append_alert(
                session_id,
                "任务失败",
                _display_text(data.get("error") or "未知错误"),
                style="red",
            )
        elif event_type in _CANCEL_LABELS:
            self.chat_log.append_alert(
                session_id, f"任务{_CANCEL_LABELS[event_type]}", "", style="yellow"
            )
        elif event_type == "completed":
            # 流式正文已上屏则不重复；无流式输出（如空回复/纯工具任务）时
            # 补显示 result，避免"完成了但什么都看不到"。
            if session_id not in self._streamed:
                result = _display_text(data.get("result")).strip()
                if result:
                    self.chat_log.start_stream(session_id, data.get("agent_name", "Agent"))
                    self.chat_log.append_stream_chunk(session_id, result)
                    self.chat_log.end_stream(session_id)
                else:
                    self.chat_log.append_system(session_id, "任务完成（无文本输出）")
        elif event_type == "tool_started":
            self.chat_log.append_tool(
                session_id,
                tool=data.get("tool", "tool"),
                arguments=_display_text(data.get("arguments", "")),
            )
        elif event_type == "tool_finished":
            self.chat_log.append_tool(
                session_id,
                tool=data.get("tool", "tool"),
                arguments=_display_text(data.get("arguments", "")),
                finished=True,
                result=_display_text(data.get("result")),
            )
        elif event_type == "user_message":
            content = _display_text(data.get("content", "")).strip()
            if content:
                self.chat_log.append_user(
                    session_id,
                    content,
                    message_id=data.get("message_id") or data.get("command_id"),
                )
        elif event_type == "file_change_proposed":
            self.chat_log.append_file_change(
                session_id,
                path=data.get("path", ""),
                status="proposed",
                diff=data.get("diff"),
            )
        elif event_type == "file_change_applied":
            self.chat_log.append_file_change(
                session_id,
                path=data.get("path", ""),
                status="applied",
                diff=data.get("diff"),
            )
        elif event_type == "file_change_declined":
            self.chat_log.append_file_change(
                session_id,
                path=data.get("path", ""),
                status="declined",
            )
        elif event_type == "file_change_failed":
            self.chat_log.append_file_change(
                session_id,
                path=data.get("path", ""),
                status="failed",
                diff=data.get("error"),
            )
        elif event_type == "supervisor_review":
            self.chat_log.append_supervisor_review(
                session_id,
                conclusion=data.get("conclusion", ""),
                reason=data.get("reason", ""),
            )
        elif event_type == "phase":
            # phase 只更新状态栏，不显示在聊天区
            if self.status_bar is not None and self.status_bar.session_id == session_id:
                self.status_bar.phase = data.get("phase", "")
        elif event_type == "llm_status":
            kind = data.get("kind")
            if kind == "web_search":
                query = data.get("query")
                line = f"[联网搜索] {query}" if query else "[联网搜索]"
                # 流式进行中：并入「思考过程」面板；否则退化为系统提示，避免孤立的空流。
                if self.chat_log.store.active_stream(session_id) is not None:
                    self.chat_log.append_reasoning_chunk(session_id, f"\n{line}")
                else:
                    self.chat_log.append_system(session_id, line)
        elif event_type == "token_usage":
            if self.on_token_usage:
                self.on_token_usage(session_id, data)
        elif event_type in ("todo_updated", "goal_updated"):
            if self.on_plan_dirty:
                self.on_plan_dirty()

    def _on_session_state(self, msg: dict) -> None:
        session_id = msg.get("session_id")
        state = msg.get("state")
        if session_id and state:
            if self.status_bar is not None and self.status_bar.session_id == session_id:
                self.status_bar.session_state = state
            if state in ("completed", "failed", "cancelled", "interrupted", "killed"):
                self._mark_context_dirty(session_id)
            self._notify_session_state(session_id, state)

    def _notify_session_state(self, session_id: str, state: str | None) -> None:
        if self.on_session_state:
            self.on_session_state(session_id, state)

    def _mark_context_dirty(self, session_id: str) -> None:
        """只有 Coordinator（a-0 前缀）的事件会影响对话级共享上下文。"""
        if self.on_context_dirty and session_id.startswith("a-0"):
            self.on_context_dirty()

    def _on_approval_pending(self, msg: dict) -> None:
        if self.on_approval:
            self.on_approval(msg)

    def _on_interaction(self, msg: dict) -> None:
        if self.on_ask_user:
            self.on_ask_user(msg)
