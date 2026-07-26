"""Cloudra Flet GUI。

提供对话列表、流式 Session 事件、审批对话框、取消任务等核心能力。
GUI 直接调用 CloudraService，不依赖浏览器，也不依赖 api.py 的 HTTP 层。
"""

from __future__ import annotations

import asyncio
import json
import os

from cloudra import events
from cloudra.service import CloudraService

try:
    import flet as ft
except ImportError:  # pragma: no cover - 仅在没有安装 flet 的精简环境中
    ft = None

FLET_AVAILABLE = ft is not None

_USER_BUBBLE_BG = "#e3f2fd"
_EVENT_BUBBLE_BG = "#f5f5f5"
_SYSTEM_BUBBLE_BG = "#fff3e0"


class _MessageBubble(ft.Container):
    """单条消息气泡。"""

    def __init__(self, role: str, content: str):
        super().__init__()
        self.role = role
        self.content = content
        self._build()

    def _build(self):
        if self.role == "user":
            title = "你"
            bg = _USER_BUBBLE_BG
        elif self.role == "assistant":
            title = "Coordinator"
            bg = _EVENT_BUBBLE_BG
        elif self.role == "event":
            title = "事件"
            bg = _EVENT_BUBBLE_BG
        else:
            title = self.role
            bg = _SYSTEM_BUBBLE_BG

        children: list[ft.Control] = [
            ft.Text(
                title,
                size=12,
                weight="bold",
                color="primary",
            )
        ]
        # Flet 的 Markdown 不一定总在所有版本可用，兜底用 Text
        if FLET_AVAILABLE and hasattr(ft, "Markdown"):
            children.append(
                ft.Markdown(
                    self.content,
                    selectable=True,
                    extension_set=ft.MarkdownExtensionSet.GITHUB_WEB
                    if hasattr(ft, "MarkdownExtensionSet")
                    else None,
                )
            )
        else:
            children.append(ft.Text(self.content, selectable=True, size=14))

        self.content = ft.Column(children, spacing=4)
        self.padding = 12
        self.border_radius = 12
        self.bgcolor = bg
        self.width = None  # 自适应列宽
        self.alignment = ft.alignment.top_left


class CloudraUI:
    def __init__(self, page: ft.Page):
        if not FLET_AVAILABLE:
            raise RuntimeError("Flet 未安装，无法启动 GUI")
        self.page = page
        self.service = CloudraService()
        self.current_conversation_id: str | None = None
        self.current_session_id: str | None = None
        self._event_task: asyncio.Task | None = None
        self._approval_task: asyncio.Task | None = None
        self._build_ui()
        self.page.run_task(self._load_sidebar)

    def _build_ui(self):
        self.page.title = "Cloudra"
        self.page.theme_mode = ft.ThemeMode.LIGHT
        self.page.padding = 0

        # 侧边栏
        self.sidebar = ft.ListView(expand=True, spacing=4)
        self.new_conv_btn = ft.ElevatedButton(
            "新建对话",
            on_click=lambda _: self.page.run_task(self._new_conversation),
        )
        sidebar_col = ft.Column(
            [
                ft.Container(
                    content=ft.Row(
                        [ft.Text("Cloudra", size=18, weight="bold"), self.new_conv_btn],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    ),
                    padding=16,
                ),
                self.sidebar,
            ],
            width=280,
            expand=False,
        )

        # 主聊天区
        self.messages = ft.ListView(expand=True, spacing=8, auto_scroll=True)
        self.status_text = ft.Text("就绪", size=12, color="grey")
        self.input_field = ft.TextField(
            hint_text="输入任务...",
            expand=True,
            multiline=True,
            min_lines=1,
            max_lines=6,
            on_submit=lambda _: self.page.run_task(self._on_send),
        )
        self.send_btn = ft.ElevatedButton(
            "发送", on_click=lambda _: self.page.run_task(self._on_send)
        )
        self.cancel_btn = ft.ElevatedButton(
            "取消",
            on_click=lambda _: self.page.run_task(self._on_cancel),
            visible=False,
        )

        main_col = ft.Column(
            [
                ft.Container(
                    content=ft.Text("会话", size=18, weight="bold"),
                    padding=16,
                ),
                self.messages,
                ft.Container(
                    content=ft.Column(
                        [
                            self.status_text,
                            ft.Row(
                                [self.input_field, self.send_btn, self.cancel_btn],
                                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                            ),
                        ],
                        spacing=8,
                    ),
                    padding=16,
                ),
            ],
            expand=True,
        )

        self.page.add(
            ft.Row([sidebar_col, ft.VerticalDivider(width=1), main_col], expand=True)
        )

    # ------------------------------------------------------------------
    # 数据/渲染
    # ------------------------------------------------------------------
    async def _load_sidebar(self):
        conversations = self.service.list_conversations()
        controls: list[ft.Control] = []
        for conv in conversations:
            cid = conv.get("id", "未知")
            last = conv.get("last_active", "")
            controls.append(
                ft.ListTile(
                    title=ft.Text(str(cid), size=13, no_wrap=False),
                    subtitle=ft.Text(str(last), size=11),
                    on_click=lambda e, cid=cid: self.page.run_task(
                        self._select_conversation, cid
                    ),
                )
            )
        if not controls:
            controls.append(
                ft.Container(
                    content=ft.Text("暂无对话，点击“新建对话”开始", color="grey"),
                    padding=16,
                )
            )
        self.sidebar.controls = controls
        self.sidebar.update()

    async def _new_conversation(self):
        conv = self.service.create_conversation()
        await self._select_conversation(conv.id)
        await self._load_sidebar()

    async def _select_conversation(self, conversation_id: str):
        self.current_conversation_id = conversation_id
        self.current_session_id = None
        self._stop_event_listener()
        self.messages.controls = []

        # 加载历史消息（system/user/assistant）
        for msg in self.service.get_conversation_messages(conversation_id):
            role = msg.get("role", "event")
            content = msg.get("content", "")
            self.messages.controls.append(_MessageBubble(role, content))

        # 显示当前会话列表，找出 running 的 session
        running = [
            rec
            for rec in self.service.session_runner.list(conversation_id)
            if rec.state in ("queued", "running", "cancel_requested")
        ]
        if running:
            self.current_session_id = running[0].session_id
            self._set_running_state(True)
            self._start_event_listener(conversation_id)
        else:
            self._set_running_state(False)

        # 检查是否已有 pending 审批
        self.page.run_task(self._check_pending_approvals)
        self.messages.update()

    def _set_running_state(self, running: bool):
        self.send_btn.disabled = running
        self.cancel_btn.visible = running
        self.input_field.disabled = running
        self.status_text.value = "运行中..." if running else "就绪"
        self.page.update()

    def _add_event_message(self, event_type: str, data: dict):
        try:
            text = json.dumps(data, ensure_ascii=False, indent=2)
        except Exception:
            text = str(data)
        content = f"**{event_type}**\n\n{text}"
        self.messages.controls.append(_MessageBubble("event", content))
        self.messages.update()

    # ------------------------------------------------------------------
    # 发送 / 取消
    # ------------------------------------------------------------------
    async def _on_send(self):
        query = self.input_field.value.strip()
        if not query:
            return
        if self.current_conversation_id is None:
            conv = self.service.create_conversation()
            self.current_conversation_id = conv.id
            await self._load_sidebar()

        self.input_field.value = ""
        self.messages.controls.append(_MessageBubble("user", query))
        self.messages.update()

        wd = os.getcwd()  # 默认使用当前工作目录
        cid, record = self.service.submit_session(
            query,
            conversation_id=self.current_conversation_id,
            working_directory=wd,
            yolo=False,
        )
        self.current_session_id = record.session_id
        self._set_running_state(True)
        self._start_event_listener(cid)

    async def _on_cancel(self):
        if not self.current_conversation_id or not self.current_session_id:
            return
        await self.service.session_runner.cancel(
            self.current_conversation_id, self.current_session_id
        )
        self.status_text.value = "已请求取消"
        self.page.update()

    # ------------------------------------------------------------------
    # 事件订阅
    # ------------------------------------------------------------------
    def _start_event_listener(self, conversation_id: str):
        self._stop_event_listener()
        self._event_task = self.page.run_task(self._event_loop, conversation_id)
        self._approval_task = self.page.run_task(
            self._approval_loop, conversation_id
        )

    def _stop_event_listener(self):
        for task in (self._event_task, self._approval_task):
            if task is not None and not task.done():
                task.cancel()
        self._event_task = None
        self._approval_task = None

    async def _event_loop(self, conversation_id: str):
        await events.ensure_listener(conversation_id)
        queue = await events.subscribe_async(
            conversation_id,
            ("session_event", "session_state", "compute_job"),
        )
        while True:
            try:
                msg = await queue.get()
            except asyncio.CancelledError:
                break
            kind = msg.get("kind")
            payload = msg.get("payload", {})
            if kind == "session_event":
                event_type = payload.get("event_type", "session_event")
                data = payload.get("data", {})
                self._add_event_message(event_type, data)
            elif kind == "compute_job":
                self._add_event_message("计算任务", payload)
            elif kind == "session_state":
                state = payload.get("state")
                self._add_event_message(f"状态: {state}", payload)
                if state in ("completed", "failed", "cancelled", "killed", "interrupted"):
                    self._set_running_state(False)
                    self._stop_event_listener()
                    break
            self.page.update()

    async def _approval_loop(self, conversation_id: str):
        """监听 approval_pending 事件并弹出审批对话框。"""
        await events.ensure_listener(conversation_id)
        queue = await events.subscribe_async(
            conversation_id, ("approval_pending", "approval_decided")
        )
        while True:
            try:
                msg = await queue.get()
            except asyncio.CancelledError:
                break
            kind = msg.get("kind")
            payload = msg.get("payload", {})
            if kind == "approval_pending":
                await self._show_approval_dialog(payload)

    async def _check_pending_approvals(self):
        for approval in await self.service.list_pending_approvals():
            if approval.get("conversation_id") == self.current_conversation_id:
                await self._show_approval_dialog(approval)
                break

    async def _show_approval_dialog(self, payload: dict):
        approval_id = payload.get("approval_id") or payload.get("id")
        details = payload.get("details", "")
        agent_name = payload.get("agent_name", "未知 Agent")

        reason_field = ft.TextField(label="拒绝原因（可选）", expand=True)

        async def on_approve(_):
            await self.service.decide_approval(
                self.current_conversation_id,
                approval_id,
                decision="approved",
            )
            self.page.close(dialog)

        async def on_deny(_):
            await self.service.decide_approval(
                self.current_conversation_id,
                approval_id,
                decision="denied",
                denial_reason=reason_field.value or "",
            )
            self.page.close(dialog)

        dialog = ft.AlertDialog(
            title=ft.Text(f"审批请求 - {agent_name}"),
            content=ft.Column(
                [
                    ft.Text(details, selectable=True),
                    reason_field,
                ],
                tight=True,
                spacing=16,
            ),
            actions=[
                ft.ElevatedButton("拒绝", on_click=lambda e: self.page.run_task(on_deny, e)),
                ft.ElevatedButton("批准", on_click=lambda e: self.page.run_task(on_approve, e)),
            ],
        )
        self.page.open(dialog)


def main(page: ft.Page):
    CloudraUI(page)
