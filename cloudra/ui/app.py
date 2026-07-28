"""Cloudra Flet GUI。

提供对话列表、流式 Session 事件、审批对话框、取消任务等核心能力。
GUI 直接调用 CloudraService，不依赖浏览器，也不依赖 api.py 的 HTTP 层。
"""

from __future__ import annotations

import asyncio
import re
from pathlib import Path

from cloudra import events
from cloudra.mobile_storage import AppStorage, configure_app_storage
from cloudra.runtime_profile import is_mobile_runtime
from cloudra.service import CloudraService

try:
    import flet as ft
except ImportError:  # pragma: no cover - 仅在没有安装 flet 的精简环境中
    ft = None

FLET_AVAILABLE = ft is not None
_MessageBubbleBase = ft.Container if FLET_AVAILABLE else object

_USER_BUBBLE_BG = "#e3f2fd"
_EVENT_BUBBLE_BG = "#f5f5f5"
_SYSTEM_BUBBLE_BG = "#fff3e0"
_FILE_EVENT_TITLES = {
    "file_change_proposed": "候选文件变更",
    "file_change_applied": "文件变更已写入",
    "file_change_declined": "文件变更已拒绝",
    "file_change_failed": "文件变更失败",
    "turn_diff_updated": "本轮文件差异",
}
_MAX_UI_DIFF_CHARS = 80_000
_COMPACT_WIDTH = 720


def _is_compact_width(width: float | int | None, *, mobile_default: bool = False) -> bool:
    """Return whether the two-pane desktop shell should collapse."""

    if width is None:
        return mobile_default
    return width < _COMPACT_WIDTH


def _show_dialog(page, dialog) -> None:
    if hasattr(page, "show_dialog"):
        page.show_dialog(dialog)
    else:  # pragma: no cover - compatibility with Flet 0.x
        page.open(dialog)


def _close_dialog(page, dialog) -> None:
    if hasattr(page, "pop_dialog"):
        page.pop_dialog()
    else:  # pragma: no cover - compatibility with Flet 0.x
        page.close(dialog)


def _markdown_inline_code(text: str) -> str:
    text = str(text)
    longest_run = max((len(run) for run in re.findall(r"`+", text)), default=0)
    fence = "`" * max(1, longest_run + 1)
    padding = " " if text.startswith("`") or text.endswith("`") else ""
    return f"{fence}{padding}{text}{padding}{fence}"


def _markdown_diff_block(diff: str) -> str:
    diff = diff or ""
    truncated = len(diff) > _MAX_UI_DIFF_CHARS
    if truncated:
        diff = diff[:_MAX_UI_DIFF_CHARS] + "\n… 界面预览已截断 …"
    longest_run = max((len(run) for run in re.findall(r"`+", diff)), default=0)
    fence = "`" * max(3, longest_run + 1)
    return f"{fence}diff\n{diff.rstrip()}\n{fence}"


def _format_file_event(event_type: str, data: dict) -> str | None:
    title = _FILE_EVENT_TITLES.get(event_type)
    if title is None:
        return None

    path = data.get("path", "")
    additions = data.get("additions")
    deletions = data.get("deletions")
    summary_parts = [_markdown_inline_code(path)] if path else []
    if additions is not None and deletions is not None:
        summary_parts.append(f"+{additions} / -{deletions}")
    message = data.get("message")
    if message:
        summary_parts.append(str(message))

    sections = [f"**{title}**"]
    if summary_parts:
        sections.append(" · ".join(summary_parts))
    diff = data.get("diff", "")
    if diff and event_type in {
        "file_change_proposed",
        "file_change_declined",
        "file_change_failed",
        "turn_diff_updated",
    }:
        sections.append(_markdown_diff_block(diff))
    return "\n\n".join(sections)


def _format_event_content(event_type: str, data: dict) -> str:
    if formatted := _format_file_event(event_type, data):
        return formatted

    if event_type == "llm_stream_end" or event_type == "llm_chunk":
        return ""

    if event_type == "tool_started":
        tool = data.get("tool", "?")
        return f"🔧 `{tool}`"

    if event_type == "tool_finished":
        tool = data.get("tool", "?")
        result = data.get("result", "")
        lines = [f"✅ `{tool}`"]
        if result:
            result_str = str(result)
            if len(result_str) > 200:
                result_str = result_str[:200] + "…"
            lines.append("```\n" + result_str + "\n```")
        return "\n".join(lines)

    if event_type == "supervisor_review":
        verdict = data.get("verdict", "")
        reasoning = data.get("reasoning", "")
        parts = [f"**审查: {verdict}**"]
        if reasoning:
            parts.append(f"> {reasoning[:300]}")
        return "\n\n".join(parts)

    if event_type in ("completed", "failed", "cancelled", "killed", "interrupted"):
        return f"**{event_type}**"

    return ""


def _event_payload(message: dict) -> dict:
    """兼容当前扁平 IPC 消息与旧版嵌套 payload 消息。"""
    payload = message.get("payload")
    return payload if isinstance(payload, dict) else message


class _MessageBubble(_MessageBubbleBase):
    """单条消息气泡。"""

    def __init__(self, role: str, content: str):
        if not FLET_AVAILABLE:
            raise RuntimeError("Flet 未安装，无法创建消息气泡")
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
        self.alignment = (
            ft.Alignment.TOP_LEFT
            if hasattr(ft, "Alignment")
            else ft.alignment.top_left
        )


class CloudraUI:
    def __init__(self, page: ft.Page, storage: AppStorage | None = None):
        if not FLET_AVAILABLE:
            raise RuntimeError("Flet 未安装，无法启动 GUI")
        self.page = page
        self.storage = storage or configure_app_storage()
        self.service = CloudraService()
        self.working_directory = str(self.storage.workspace)
        self.current_conversation_id: str | None = None
        self.current_session_id: str | None = None
        self._event_task: asyncio.Task | None = None
        self._approval_task: asyncio.Task | None = None
        self._compact = False
        self._streaming_bubble: _MessageBubble | None = None
        self._streaming_text: str = ""
        self._build_ui()
        self.page.run_task(self._load_sidebar)

    def _build_ui(self):
        self.page.title = "Cloudra"
        self.page.theme_mode = ft.ThemeMode.LIGHT
        self.page.padding = 0

        # 侧边栏
        self.sidebar = ft.ListView(expand=True, spacing=4)
        self.new_conv_btn = ft.Button(
            "新建对话",
            on_click=lambda _: self.page.run_task(self._new_conversation),
        )
        self.sidebar_col = ft.Column(
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
        self.sidebar_divider = ft.VerticalDivider(width=1)

        # 主聊天区
        self.messages = ft.ListView(expand=True, spacing=8, auto_scroll=True)
        self.status_text = ft.Text(
            "手机本地模式" if is_mobile_runtime() else "就绪",
            size=12,
            color="grey",
        )
        self.workspace_text = ft.Text(
            self._workspace_label(),
            size=11,
            color="grey",
            no_wrap=True,
            tooltip=self.working_directory,
        )
        self.mobile_sessions_btn = ft.IconButton(
            icon=ft.Icons.MENU,
            tooltip="会话",
            visible=False,
            on_click=lambda _: self.page.run_task(self._show_conversations),
        )
        self.workspace_btn = ft.IconButton(
            icon=ft.Icons.FOLDER_OPEN,
            tooltip="选择本地工作区",
            on_click=lambda _: self.page.run_task(self._choose_workspace),
        )
        self.settings_btn = ft.IconButton(
            icon=ft.Icons.SETTINGS,
            tooltip="模型设置",
            on_click=lambda _: self.page.run_task(self._show_settings),
        )
        self.input_field = ft.TextField(
            hint_text="输入任务...",
            expand=True,
            multiline=True,
            min_lines=1,
            max_lines=6,
            on_submit=lambda _: self.page.run_task(self._on_send),
        )
        self.send_btn = ft.IconButton(
            icon=ft.Icons.SEND,
            tooltip="发送",
            on_click=lambda _: self.page.run_task(self._on_send),
        )
        self.cancel_btn = ft.IconButton(
            icon=ft.Icons.STOP_CIRCLE_OUTLINED,
            tooltip="取消任务",
            on_click=lambda _: self.page.run_task(self._on_cancel),
            visible=False,
        )
        self.header_actions = ft.Row(
            [self.workspace_btn, self.settings_btn],
            spacing=0,
            tight=True,
        )

        self.main_col = ft.Column(
            [
                ft.Container(
                    content=ft.Column(
                        [
                            ft.Row(
                                [
                                    self.mobile_sessions_btn,
                                    ft.Text("Cloudra", size=18, weight="bold"),
                                    self.header_actions,
                                ],
                                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                                spacing=8,
                            ),
                            self.workspace_text,
                        ],
                        spacing=4,
                    ),
                    padding=12,
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

        self.root_row = ft.Row(
            [self.sidebar_col, self.sidebar_divider, self.main_col],
            expand=True,
            spacing=0,
        )
        self.page.add(ft.SafeArea(content=self.root_row, expand=True))

        if hasattr(self.page, "on_resize"):
            self.page.on_resize = self._on_resize
        else:  # pragma: no cover - compatibility with Flet 0.x
            self.page.on_resized = self._on_resize
        self._apply_responsive_layout(update=True)

    def _workspace_label(self) -> str:
        path = Path(self.working_directory)
        return f"本地工作区：{path.name or path}"

    def _on_resize(self, _=None):
        self._apply_responsive_layout(update=True)

    def _apply_responsive_layout(self, *, update: bool = False):
        compact = _is_compact_width(
            getattr(self.page, "width", None),
            mobile_default=is_mobile_runtime(),
        )
        self._compact = compact
        self.sidebar_col.visible = not compact
        self.sidebar_divider.visible = not compact
        self.mobile_sessions_btn.visible = compact
        if compact:
            page_width = getattr(self.page, "width", None) or _COMPACT_WIDTH
            self.input_field.expand = False
            self.input_field.width = max(180, page_width - 96)
        else:
            self.input_field.expand = True
            self.input_field.width = None
        if update:
            self.page.update()

    # ------------------------------------------------------------------
    # 数据/渲染
    # ------------------------------------------------------------------
    async def _load_sidebar(self):
        conversations = self.service.list_conversations()
        controls = self._conversation_controls(conversations)
        if not controls:
            controls.append(
                ft.Container(
                    content=ft.Text("暂无对话，点击“新建对话”开始", color="grey"),
                    padding=16,
                )
            )
        self.sidebar.controls = controls
        self.sidebar.update()

    def _conversation_controls(self, conversations, on_select=None) -> list:
        controls: list[ft.Control] = []
        on_select = on_select or self._select_conversation
        for conv in conversations:
            cid = conv.get("id", "未知")
            last = conv.get("last_active", "")
            controls.append(
                ft.ListTile(
                    title=ft.Text(str(cid), size=13, no_wrap=False),
                    subtitle=ft.Text(str(last), size=11),
                    on_click=lambda _e, cid=cid: self.page.run_task(on_select, cid),
                )
            )
        return controls

    async def _show_conversations(self):
        conversations = self.service.list_conversations()
        dialog = None

        async def select_and_close(conversation_id: str):
            _close_dialog(self.page, dialog)
            await self._select_conversation(conversation_id)

        async def create_and_close():
            _close_dialog(self.page, dialog)
            await self._new_conversation()

        controls = self._conversation_controls(conversations, select_and_close)
        if not controls:
            controls = [ft.Text("暂无对话", color="grey")]
        dialog = ft.AlertDialog(
            title=ft.Text("会话"),
            content=ft.Container(
                content=ft.ListView(controls=controls, spacing=4),
                width=340,
                height=420,
            ),
            actions=[
                ft.Button(
                    "新建对话",
                    on_click=lambda _: self.page.run_task(create_and_close),
                ),
            ],
        )
        _show_dialog(self.page, dialog)

    async def _choose_workspace(self):
        try:
            selected = await ft.FilePicker().get_directory_path(
                dialog_title="选择 Cloudra 本地工作目录",
                initial_directory=self.working_directory,
            )
        except Exception as exc:
            self.status_text.value = f"无法打开目录选择器：{exc}"
            self.page.update()
            return
        if not selected:
            return

        path = Path(selected).expanduser()
        if not path.is_dir():
            self.status_text.value = "这个目录目前无法由 App 读取"
            self.page.update()
            return

        self.working_directory = str(path.resolve())
        self.service.config.workspace_dir = path.resolve()
        self.service.config.save()
        self.workspace_text.value = self._workspace_label()
        self.workspace_text.tooltip = self.working_directory
        self.status_text.value = "本地工作区已切换"
        self.page.update()

    async def _show_settings(self):
        config = self.service.config
        coordinator_model = ft.TextField(
            label="Coordinator 模型", value=config.coordinator.model
        )
        coordinator_url = ft.TextField(
            label="Coordinator API 地址", value=config.coordinator.url
        )
        coordinator_key = ft.TextField(
            label="Coordinator API Key",
            value=config.coordinator.key,
            password=True,
            can_reveal_password=True,
        )
        follower_model = ft.TextField(
            label="子 Agent 模型", value=config.follower.model
        )
        follower_url = ft.TextField(
            label="子 Agent API 地址", value=config.follower.url
        )
        follower_key = ft.TextField(
            label="子 Agent API Key",
            value=config.follower.key,
            password=True,
            can_reveal_password=True,
        )
        dialog = None

        async def save_settings():
            config.coordinator.model = coordinator_model.value.strip()
            config.coordinator.url = coordinator_url.value.strip()
            config.coordinator.key = coordinator_key.value.strip()
            config.follower.model = follower_model.value.strip()
            config.follower.url = follower_url.value.strip()
            config.follower.key = follower_key.value.strip()
            config.save()
            _close_dialog(self.page, dialog)
            self.status_text.value = "模型设置已保存在本机"
            self.page.update()

        dialog = ft.AlertDialog(
            title=ft.Text("模型设置"),
            content=ft.Container(
                content=ft.Column(
                    [
                        coordinator_model,
                        coordinator_url,
                        coordinator_key,
                        follower_model,
                        follower_url,
                        follower_key,
                    ],
                    spacing=12,
                    scroll=ft.ScrollMode.AUTO,
                ),
                width=440,
                height=520,
            ),
            actions=[
                ft.Button(
                    "保存",
                    on_click=lambda _: self.page.run_task(save_settings),
                )
            ],
        )
        _show_dialog(self.page, dialog)

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
        self.send_btn.visible = not running
        self.cancel_btn.visible = running
        self.input_field.disabled = running
        self.status_text.value = "运行中..." if running else "就绪"
        self.page.update()

    def _add_event_message(self, event_type: str, data: dict):
        if event_type == "llm_chunk":
            delta = data.get("delta", "")
            if not delta:
                return
            self._streaming_text += delta
            if self._streaming_bubble is None:
                self._streaming_bubble = _MessageBubble("assistant", delta)
                self.messages.controls.append(self._streaming_bubble)
            else:
                self._streaming_bubble.content = self._streaming_text
                self._streaming_bubble._build()
            self.messages.update()
            return
        if event_type == "llm_stream_end":
            self._streaming_bubble = None
            self._streaming_text = ""
            self.messages.update()
            return
        if event_type in ("phase", "turn_diff_updated", "file_change_proposed"):
            return
        content = _format_event_content(event_type, data)
        if not content:
            return
        self._streaming_bubble = None
        self._streaming_text = ""
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
        self._streaming_bubble = None
        self._streaming_text = ""
        self.messages.controls.append(_MessageBubble("user", query))
        self.messages.update()

        cid, record = self.service.submit_session(
            query,
            conversation_id=self.current_conversation_id,
            working_directory=self.working_directory,
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
            payload = _event_payload(msg)
            if kind == "session_event":
                event_type = payload.get("event_type", "session_event")
                data = payload.get("data", {})
                self._add_event_message(event_type, data)
            elif kind == "compute_job":
                self._add_event_message("计算任务", payload)
            elif kind == "session_state":
                state = payload.get("state")
                self._add_event_message(f"状态: {state}", payload)
                if (
                    payload.get("session_id") == self.current_session_id
                    and state
                    in ("completed", "failed", "cancelled", "killed", "interrupted")
                ):
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
            payload = _event_payload(msg)
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
            _close_dialog(self.page, dialog)

        async def on_deny(_):
            await self.service.decide_approval(
                self.current_conversation_id,
                approval_id,
                decision="denied",
                denial_reason=reason_field.value or "",
            )
            _close_dialog(self.page, dialog)

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
                ft.Button("拒绝", on_click=lambda e: self.page.run_task(on_deny, e)),
                ft.Button("批准", on_click=lambda e: self.page.run_task(on_approve, e)),
            ],
        )
        _show_dialog(self.page, dialog)


def main(page: ft.Page):
    CloudraUI(page, configure_app_storage())
