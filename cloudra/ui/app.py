"""Cloudra Flet GUI。

提供对话列表、流式 Session 事件、审批对话框、取消任务等核心能力。
桌面使用 LocalCloudraBackend；Android 默认使用 RemoteCloudraBackend。
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import re
from pathlib import Path

from cloudra.backends import (
    TERMINAL_STATES,
    BackendError,
    CloudraBackend,
    LocalCloudraBackend,
    RemoteCloudraBackend,
    ServerProfile,
    create_default_backend,
)
from cloudra.device.runtime import DeviceRuntime, DeviceStateStore
from cloudra.mobile_storage import AppStorage, configure_app_storage
from cloudra.native_bridge import (
    CloudraNative,
    NativeBridgeError,
    credential_key,
)
from cloudra.runtime_profile import is_mobile_runtime
from cloudra.tool_presentation import format_tool_payload

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
_MAX_TOOL_RESULT_CHARS = 8_000
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


def _render_tool_result(value) -> str:
    """把工具返回值渲染成脱敏、无裸 JSON 的有限长度摘要。"""
    return format_tool_payload(value, is_result=True, max_chars=_MAX_TOOL_RESULT_CHARS)


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
            result_str = _render_tool_result(result)
            if len(result_str) > _MAX_TOOL_RESULT_CHARS:
                result_str = (
                    result_str[:_MAX_TOOL_RESULT_CHARS]
                    + "\n… 结果预览已截断 …"
                )
            lines.append(result_str)
        return "\n".join(lines)

    if event_type == "supervisor_review":
        verdict = data.get("verdict", "")
        reasoning = data.get("reasoning", "")
        parts = [f"**审查: {verdict}**"]
        if reasoning:
            parts.append(f"> {reasoning[:300]}")
        return "\n\n".join(parts)

    if event_type == "artifact_created":
        name = data.get("name", "artifact")
        size = data.get("size", 0)
        return f"📦 **新产物可下载**\n\n`{name}` · {size} bytes"

    if event_type == "device_tool_state":
        tool = data.get("tool", "device tool")
        state = data.get("state", "")
        labels = {
            "queued": "已排队",
            "acknowledged": "设备已接收",
            "waiting_for_local_approval": "等待 Android 本地审批",
            "running": "设备执行中",
            "succeeded": "设备执行成功",
            "failed": "设备执行失败",
            "declined": "Android 用户已拒绝",
            "expired": "设备调用已过期",
            "cancelled": "设备调用已取消",
        }
        return f"📱 `{tool}` · {labels.get(state, state)}"

    if event_type in ("completed", "failed", "cancelled", "killed", "interrupted"):
        details = data.get("result") or data.get("error") or ""
        if details:
            details = _render_tool_result(details)
            if len(details) > 20_000:
                details = details[:20_000] + "\n… 结果预览已截断 …"
            return f"**{event_type}**\n\n{details}"
        return f"**{event_type}**"

    return ""


def _event_payload(message: dict) -> dict:
    """Compatibility helper for legacy flat and nested event payloads."""
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
    def __init__(
        self,
        page: ft.Page,
        storage: AppStorage | None = None,
        backend: CloudraBackend | None = None,
    ):
        if not FLET_AVAILABLE:
            raise RuntimeError("Flet 未安装，无法启动 GUI")
        self.page = page
        self.storage = storage or configure_app_storage()
        self.backend = backend or create_default_backend(self.storage)
        self.working_directory = str(self.storage.workspace)
        self.current_conversation_id: str | None = None
        self.current_session_id: str | None = None
        self._event_task: asyncio.Task | None = None
        self._approval_task: asyncio.Task | None = None
        self._interaction_task: asyncio.Task | None = None
        self._displayed_approvals: set[int] = set()
        self._pending_user_echoes: list[str] = []
        self._device_task: asyncio.Task | None = None
        self._device_runtime: DeviceRuntime | None = None
        self._device_state_store = DeviceStateStore(
            self.storage.data_dir / "device-state.json"
        )
        self._native_bridge = (
            CloudraNative() if is_mobile_runtime() else None
        )
        self._app_background = False
        self._compact = False
        self._session_active = False
        self._shown_interactions: set[str] = set()
        self._streaming_bubble: _MessageBubble | None = None
        self._streaming_text: str = ""
        self._build_ui()
        if hasattr(self.page, "on_disconnect"):
            self.page.on_disconnect = lambda _: self.page.run_task(self._shutdown)
        if hasattr(self.page, "on_close"):
            self.page.on_close = lambda _: self.page.run_task(self._shutdown)
        if hasattr(self.page, "on_app_lifecycle_state_change"):
            self.page.on_app_lifecycle_state_change = (
                self._on_app_lifecycle_state_change
            )
        self.page.run_task(self._initialize)

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
            "远程模式" if self.backend.mode == "remote" else "就绪",
            size=12,
            color="grey",
        )
        self.workspace_text = ft.Text(
            self._workspace_label(),
            size=11,
            color="grey",
            no_wrap=True,
            tooltip=(
                self.backend.profile.server_url
                if isinstance(self.backend, RemoteCloudraBackend)
                else self.working_directory
            ),
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
            visible=self.backend.mode == "local",
            on_click=lambda _: self.page.run_task(self._choose_workspace),
        )
        self.device_caps_btn = ft.IconButton(
            icon=ft.Icons.PHONE_ANDROID,
            tooltip="Android 设备能力与文档授权",
            visible=(
                self.backend.mode == "remote" and is_mobile_runtime()
            ),
            on_click=lambda _: self.page.run_task(
                self._show_device_capabilities
            ),
        )
        self.settings_btn = ft.IconButton(
            icon=ft.Icons.SETTINGS,
            tooltip=(
                "服务器连接"
                if self.backend.mode == "remote"
                else "模型设置"
            ),
            on_click=lambda _: self.page.run_task(self._show_settings),
        )
        self.artifacts_btn = ft.IconButton(
            icon=ft.Icons.DOWNLOAD,
            tooltip="服务器产物",
            on_click=lambda _: self.page.run_task(self._show_artifacts),
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
            [
                self.artifacts_btn,
                self.device_caps_btn,
                self.workspace_btn,
                self.settings_btn,
            ],
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
        if isinstance(self.backend, RemoteCloudraBackend):
            target = (
                self.backend.profile.display_name
                or self.backend.profile.server_url
                or "尚未配置服务器"
            )
            route = self.backend.profile.workspace_id or "default"
            if self.backend.profile.node_id:
                route = f"{self.backend.profile.node_id} / {route}"
            return f"远程服务器：{target} · {route}"
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
    async def _initialize(self):
        await self._restore_remote_credentials()
        await self._load_sidebar()

    async def _restore_remote_credentials(self) -> None:
        backend = self.backend
        native = self._native_bridge
        if (
            not isinstance(backend, RemoteCloudraBackend)
            or native is None
            or not backend.profile.server_url
        ):
            return
        try:
            token = await native.secure_get(
                credential_key(
                    "server",
                    backend.profile.server_url,
                )
            )
        except NativeBridgeError as exc:
            self.status_text.value = f"Android 安全存储不可用：{exc}"
            return
        if not token:
            return
        profile = ServerProfile(
            server_url=backend.profile.server_url,
            display_name=backend.profile.display_name,
            token=token,
            allow_insecure_http=backend.profile.allow_insecure_http,
        )
        try:
            await backend.reconfigure(profile)
            server = await backend.probe()
        except BackendError as exc:
            self.status_text.value = f"已恢复 Server Token，等待重连：{exc}"
            return
        backend.profile.display_name = server.get(
            "display_name",
            backend.profile.display_name,
        )
        backend.state_store.save_profile(backend.profile)
        self.workspace_text.value = self._workspace_label()
        self.workspace_text.tooltip = backend.profile.server_url
        self.status_text.value = (
            f"已从 Android Keystore 恢复连接 · "
            f"v{server.get('server_version', '?')}"
        )
        if self._device_state_store.runtime_enabled():
            try:
                await self._restore_device_runtime()
            except (BackendError, NativeBridgeError, ValueError) as exc:
                self.status_text.value = f"设备 Runtime 恢复失败：{exc}"

    async def _load_sidebar(self):
        try:
            conversations = await self.backend.list_conversations()
        except BackendError as exc:
            self.status_text.value = str(exc)
            conversations = []
        controls = self._conversation_controls(conversations)
        if not controls:
            controls.append(
                ft.Container(
                    content=ft.Text(
                        (
                            "请先配置 Cloudra Server"
                            if self.backend.mode == "remote"
                            else "暂无对话，点击“新建对话”开始"
                        ),
                        color="grey",
                    ),
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
        try:
            conversations = await self.backend.list_conversations()
        except BackendError as exc:
            self.status_text.value = str(exc)
            self.page.update()
            return
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
        if not isinstance(self.backend, LocalCloudraBackend):
            return
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
        self.backend.set_workspace(path)
        self.workspace_text.value = self._workspace_label()
        self.workspace_text.tooltip = self.working_directory
        self.status_text.value = "本地工作区已切换"
        self.page.update()

    async def _show_settings(self):
        if isinstance(self.backend, RemoteCloudraBackend):
            await self._show_remote_settings()
            return
        if not isinstance(self.backend, LocalCloudraBackend):
            return

        settings = self.backend.get_model_settings()
        coordinator_model = ft.TextField(
            label="Coordinator 模型",
            value=settings["coordinator_model"],
        )
        coordinator_url = ft.TextField(
            label="Coordinator API 地址",
            value=settings["coordinator_url"],
        )
        coordinator_key = ft.TextField(
            label="Coordinator API Key",
            value=settings["coordinator_key"],
            password=True,
            can_reveal_password=True,
        )
        follower_model = ft.TextField(
            label="子 Agent 模型",
            value=settings["follower_model"],
        )
        follower_url = ft.TextField(
            label="子 Agent API 地址",
            value=settings["follower_url"],
        )
        follower_key = ft.TextField(
            label="子 Agent API Key",
            value=settings["follower_key"],
            password=True,
            can_reveal_password=True,
        )
        dialog = None

        async def save_settings():
            self.backend.save_model_settings(
                {
                    "coordinator_model": coordinator_model.value.strip(),
                    "coordinator_url": coordinator_url.value.strip(),
                    "coordinator_key": coordinator_key.value.strip(),
                    "follower_model": follower_model.value.strip(),
                    "follower_url": follower_url.value.strip(),
                    "follower_key": follower_key.value.strip(),
                }
            )
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

    async def _show_remote_settings(self):
        backend = self.backend
        if not isinstance(backend, RemoteCloudraBackend):
            return
        profile = backend.profile
        registered = backend.state_store.load_profiles()
        profile_selector = ft.Dropdown(
            label="已注册服务器",
            value=profile.profile_id if profile.server_url else None,
            options=[
                ft.DropdownOption(
                    key=item.profile_id,
                    text=f"{item.display_name} · {item.server_url}",
                )
                for item in registered
            ],
            visible=bool(registered),
        )
        server_url = ft.TextField(
            label="Cloudra Server 地址",
            value=profile.server_url,
            hint_text="https://cloudra.example.com",
        )
        token = ft.TextField(
            label=(
                (
                    "新 Server Token（留空保留 Keystore 中的现有值）"
                    if profile.token
                    else "Server Token（保存到 Android Keystore）"
                )
                if self._native_bridge is not None
                else "Server Token（仅保留到本次 App 退出）"
            ),
            # Never copy a restored long-lived token back into the Flet control
            # tree: debug builds log control patches. Users can replace it by
            # typing a new value or remove it with the explicit checkbox below.
            value="",
            password=True,
            can_reveal_password=True,
        )
        clear_token = ft.Checkbox(
            label="删除当前服务器已保存的 Token",
            value=False,
            visible=bool(profile.token),
        )
        allow_http = ft.Checkbox(
            label="允许局域网明文 HTTP（仅开发环境）",
            value=profile.allow_insecure_http,
        )
        enable_device = ft.Checkbox(
            label="保持 Android 设备 Runtime 后台在线（显示常驻通知）",
            value=self._device_state_store.runtime_enabled(),
        )
        route_records: dict[str, tuple[str, str]] = {}
        try:
            nodes, workspaces = await asyncio.gather(
                backend.list_nodes(),
                backend.list_workspaces(),
            )
            node_names = {
                str(item.get("node_id", "")): str(
                    item.get("display_name") or item.get("node_id") or "节点"
                )
                for item in nodes
            }
            for item in workspaces:
                node_id = str(item.get("node_id", ""))
                workspace_id = str(item.get("workspace_id", ""))
                if not node_id or not workspace_id:
                    continue
                key = f"{node_id}\n{workspace_id}"
                route_records[key] = (node_id, workspace_id)
        except BackendError:
            pass
        selected_route = f"{profile.node_id}\n{profile.workspace_id}"
        route_selector = ft.Dropdown(
            label="节点 / 工作区",
            value=selected_route if selected_route in route_records else None,
            options=[
                ft.DropdownOption(
                    key=key,
                    text=f"{node_names.get(node_id, node_id)} · {workspace_id}",
                )
                for key, (node_id, workspace_id) in route_records.items()
            ],
            visible=bool(route_records),
        )
        dialog = None

        def choose_registered_server(event):
            selected = backend.state_store.load_profile(event.control.value)
            server_url.value = selected.server_url
            allow_http.value = selected.allow_insecure_http
            clear_token.value = False
            selected_key = f"{selected.node_id}\n{selected.workspace_id}"
            route_selector.value = (
                selected_key if selected_key in route_records else None
            )
            server_url.update()
            allow_http.update()
            clear_token.update()
            route_selector.update()

        profile_selector.on_select = choose_registered_server

        async def save_remote_settings():
            entered_token = token.value.strip()
            clear_saved_token = bool(clear_token.value)
            old_server_url = profile.server_url
            new_server_url = server_url.value.strip()
            same_origin = bool(
                old_server_url
                and new_server_url
                and credential_key("server", old_server_url)
                == credential_key("server", new_server_url)
            )
            if clear_saved_token:
                selected_token = ""
            elif entered_token:
                selected_token = entered_token
            elif same_origin:
                selected_token = profile.token
            elif self._native_bridge is not None and new_server_url:
                try:
                    selected_token = await self._native_bridge.secure_get(
                        credential_key("server", new_server_url)
                    )
                except NativeBridgeError as exc:
                    self.status_text.value = f"无法读取服务器 Token：{exc}"
                    self.page.update()
                    return
            else:
                # A credential is origin-bound. An empty field while changing
                # servers must never carry the old server's token forward.
                selected_token = ""
            selected_node = profile.node_id
            selected_workspace = profile.workspace_id
            if route_selector.value in route_records:
                selected_node, selected_workspace = route_records[
                    route_selector.value
                ]
            stored_profile = next(
                (
                    item
                    for item in registered
                    if item.server_url.rstrip("/") == new_server_url.rstrip("/")
                ),
                None,
            )
            if not same_origin and stored_profile is not None:
                selected_node = stored_profile.node_id
                selected_workspace = stored_profile.workspace_id
            new_profile = ServerProfile(
                server_url=new_server_url,
                display_name=profile.display_name,
                token=selected_token,
                allow_insecure_http=bool(allow_http.value),
                node_id=selected_node,
                workspace_id=selected_workspace,
            )
            # Stop the old device transport before changing origins so an
            # existing device credential can never be sent to a newly entered
            # server URL during the probe window.
            await self._stop_device_runtime(explicit=False)
            try:
                await backend.reconfigure(new_profile)
                server = await backend.probe()
            except BackendError as exc:
                # reconfigure persists the candidate before probing. Roll the
                # active route back so a typo or offline node cannot strand the
                # next app launch on a half-configured server.
                with contextlib.suppress(BackendError):
                    await backend.reconfigure(profile)
                self.status_text.value = str(exc)
                self.page.update()
                return
            backend.profile.display_name = server.get(
                "display_name",
                "Cloudra Server",
            )
            backend.state_store.save_profile(backend.profile)
            secret_message = ""
            if self._native_bridge is not None:
                try:
                    server_key = credential_key(
                        "server",
                        backend.profile.server_url,
                    )
                    if entered_token:
                        await self._native_bridge.secure_set(
                            server_key,
                            backend.profile.token,
                        )
                        secret_message = " · Token 已保存到 Keystore"
                    elif clear_saved_token:
                        await self._native_bridge.secure_remove(server_key)
                        secret_message = " · 已删除 Keystore Token"
                    elif same_origin and profile.token:
                        secret_message = " · Keystore Token 已保留"
                    elif selected_token:
                        secret_message = " · 已恢复该服务器的 Keystore Token"
                    else:
                        await self._native_bridge.secure_remove(server_key)
                except NativeBridgeError as exc:
                    self.status_text.value = (
                        f"服务器连接成功，但 Token 无法安全保存：{exc}"
                    )
                    self.page.update()
                    return
            device_message = ""
            if enable_device.value:
                try:
                    await self._pair_device_runtime()
                    device_message = " · 设备 Runtime 在线"
                except (BackendError, NativeBridgeError, ValueError) as exc:
                    device_message = f" · 设备配对失败：{exc}"
            else:
                await self._stop_device_runtime(explicit=True)
            self.workspace_text.value = self._workspace_label()
            self.workspace_text.tooltip = backend.profile.server_url
            self.status_text.value = (
                f"已连接 {backend.profile.display_name} · "
                f"v{server.get('server_version', '?')}"
                f"{secret_message}{device_message}"
            )
            token.value = ""
            _close_dialog(self.page, dialog)
            await self._load_sidebar()
            self.page.update()

        async def remove_registered_server():
            selected = next(
                (
                    item
                    for item in backend.state_store.load_profiles()
                    if item.server_url.rstrip("/") == server_url.value.strip().rstrip("/")
                ),
                None,
            )
            if selected is None:
                self.status_text.value = "当前地址尚未注册，无需移除"
                self.page.update()
                return
            identity = self._device_state_store.identity(selected.profile_id)
            remote_revoked = False
            if (
                selected.profile_id == backend.profile.profile_id
                and identity.get("device_id")
            ):
                try:
                    await backend.revoke_device(str(identity["device_id"]))
                    remote_revoked = True
                except BackendError:
                    # Local credentials must still be removable while offline;
                    # the server-side record remains visible to an operator.
                    pass
            await self._stop_device_runtime(explicit=True)
            if self._native_bridge is not None:
                try:
                    await self._native_bridge.secure_remove(
                        credential_key("server", selected.server_url)
                    )
                    if identity.get("device_id"):
                        await self._native_bridge.secure_remove(
                            credential_key(
                                "device",
                                selected.server_url,
                                str(identity["device_id"]),
                            )
                        )
                except NativeBridgeError as exc:
                    self.status_text.value = f"无法删除 Keystore 凭据：{exc}"
                    self.page.update()
                    return
            self._device_state_store.remove_identity(selected.profile_id)
            backend.state_store.remove_profile(selected.profile_id)
            await backend.close()
            remaining = backend.state_store.load_profiles()
            if remaining:
                next_profile = backend.state_store.load_profile()
                if self._native_bridge is not None:
                    next_profile.token = await self._native_bridge.secure_get(
                        credential_key("server", next_profile.server_url)
                    )
                backend.profile = next_profile
            else:
                backend.profile = ServerProfile()
            self.workspace_text.value = self._workspace_label()
            self.workspace_text.tooltip = backend.profile.server_url or None
            suffix = " · 设备已在服务器撤销" if remote_revoked else ""
            self.status_text.value = f"已移除服务器：{selected.display_name}{suffix}"
            _close_dialog(self.page, dialog)
            await self._load_sidebar()
            self.page.update()

        dialog = ft.AlertDialog(
            title=ft.Text("服务器连接"),
            content=ft.Container(
                content=ft.Column(
                    [
                        profile_selector,
                        server_url,
                        token,
                        clear_token,
                        allow_http,
                        route_selector,
                        enable_device,
                        ft.Text(
                            "Android 不保存也不需要模型 API Key。"
                            "Server Token 和设备凭据只写入 Android Keystore。"
                            "App 私有工作区与经系统选择器持久授权的文档目录"
                            "彼此隔离；写入、文件选择、相机与分享均在本机逐次审批。",
                            size=11,
                            color="grey",
                        ),
                    ],
                    spacing=12,
                    tight=True,
                ),
                width=440,
            ),
            actions=[
                ft.TextButton(
                    "移除此服务器",
                    on_click=lambda _: self.page.run_task(remove_registered_server),
                    visible=bool(registered),
                ),
                ft.Button(
                    "连接",
                    on_click=lambda _: self.page.run_task(
                        save_remote_settings
                    ),
                )
            ],
        )
        _show_dialog(self.page, dialog)

    async def _show_device_capabilities(self) -> None:
        native = self._native_bridge
        if native is None:
            return
        try:
            tree = await native.get_document_tree()
            notification = await native.notification_permission_status()
        except NativeBridgeError as exc:
            self.status_text.value = str(exc)
            self.page.update()
            return

        if tree.get("authorized") and not tree.get("readable", True):
            tree_label = "文档目录：授权仍在，但文档提供者当前不可用"
        elif tree.get("authorized"):
            tree_label = f"文档目录：{tree.get('display_name', '已授权')}"
        else:
            tree_label = "文档目录：尚未授权"
        tree_text = ft.Text(tree_label, selectable=True)
        runtime_text = ft.Text(
            "设备 Runtime：在线"
            if self._device_runtime is not None
            else "设备 Runtime：未运行"
        )
        notification_text = ft.Text(
            "通知：已授权"
            if notification.get("granted")
            else "通知：未授权（后台服务只会出现在系统活跃服务列表）"
        )

        async def authorize_tree():
            try:
                selected = await native.select_document_tree()
            except NativeBridgeError as exc:
                tree_text.value = f"文档目录授权失败：{exc}"
            else:
                if selected.get("status") == "cancelled":
                    tree_text.value = "文档目录：用户取消了选择"
                else:
                    tree_text.value = (
                        "文档目录："
                        + str(selected.get("display_name", "已持久授权"))
                    )
            self.page.update()

        async def revoke_tree():
            try:
                await native.revoke_document_tree()
                tree_text.value = "文档目录：授权已撤销"
            except NativeBridgeError as exc:
                tree_text.value = f"撤销失败：{exc}"
            self.page.update()

        async def request_notifications():
            try:
                permission = await native.request_notification_permission()
                notification_text.value = (
                    "通知：已授权"
                    if permission.get("granted")
                    else "通知：用户未授权"
                )
            except NativeBridgeError as exc:
                notification_text.value = f"通知权限请求失败：{exc}"
            self.page.update()

        async def enable_runtime():
            try:
                if self._device_runtime is None:
                    identity = self._device_state_store.identity(
                        backend.profile.profile_id
                    )
                    if identity:
                        try:
                            await self._restore_device_runtime()
                        except NativeBridgeError as exc:
                            if exc.status != "credential_missing":
                                raise
                            await self._pair_device_runtime()
                    else:
                        await self._pair_device_runtime()
                runtime_text.value = "设备 Runtime：在线"
            except (BackendError, NativeBridgeError, ValueError) as exc:
                runtime_text.value = f"设备 Runtime 启动失败：{exc}"
            self.page.update()

        async def disable_runtime():
            await self._stop_device_runtime(explicit=True)
            runtime_text.value = "设备 Runtime：已由用户停止"
            self.page.update()

        dialog = ft.AlertDialog(
            title=ft.Text("Android 设备能力"),
            content=ft.Container(
                content=ft.Column(
                    [
                        runtime_text,
                        notification_text,
                        tree_text,
                        ft.Text(
                            "文档目录授权由 Android 系统选择器签发并持久保存，"
                            "重启后仍会校验系统 grant；Cloudra 不把 content URI "
                            "或任何 Token 写入普通配置。",
                            size=11,
                            color="grey",
                        ),
                        ft.Row(
                            [
                                ft.Button(
                                    "授权文档目录",
                                    on_click=lambda _: self.page.run_task(
                                        authorize_tree
                                    ),
                                ),
                                ft.Button(
                                    "撤销目录授权",
                                    on_click=lambda _: self.page.run_task(
                                        revoke_tree
                                    ),
                                ),
                            ],
                            wrap=True,
                        ),
                        ft.Row(
                            [
                                ft.Button(
                                    "请求通知权限",
                                    on_click=lambda _: self.page.run_task(
                                        request_notifications
                                    ),
                                ),
                                ft.Button(
                                    "启用 Runtime",
                                    on_click=lambda _: self.page.run_task(
                                        enable_runtime
                                    ),
                                ),
                                ft.Button(
                                    "停止 Runtime",
                                    on_click=lambda _: self.page.run_task(
                                        disable_runtime
                                    ),
                                ),
                            ],
                            wrap=True,
                        ),
                    ],
                    spacing=12,
                    tight=True,
                ),
                width=520,
            ),
            actions=[
                ft.Button(
                    "关闭",
                    on_click=lambda _: _close_dialog(self.page, dialog),
                )
            ],
        )
        _show_dialog(self.page, dialog)

    def _on_device_status(self, status_text: str) -> None:
        if self._device_runtime is None:
            return
        with contextlib.suppress(Exception):
            self.page.run_task(
                self._sync_device_status,
                status_text,
            )

    async def _sync_device_status(self, status_text: str) -> None:
        if status_text != "设备在线" or self._app_background:
            self.status_text.value = status_text
            with contextlib.suppress(Exception):
                self.page.update()
        if self._native_bridge is None:
            return
        notification_text = (
            "后台在线，点按返回 Cloudra"
            if self._app_background and status_text == "设备在线"
            else status_text
        )
        try:
            await self._native_bridge.update_foreground_runtime(
                text=notification_text,
            )
        except NativeBridgeError as exc:
            if exc.status != "not_running" or self._device_runtime is None:
                return
            await self._stop_device_runtime(explicit=False)
            self.status_text.value = (
                "Android 前台服务已停止；设备 Runtime 已转为离线"
            )
            with contextlib.suppress(Exception):
                self.page.update()

    def _on_app_lifecycle_state_change(self, event) -> None:
        state = getattr(getattr(event, "state", None), "value", "")
        self._app_background = state in {"hide", "pause"}
        if self._device_runtime is not None:
            self.page.run_task(
                self._sync_device_status,
                "设备在线",
            )

    def _new_device_runtime(self) -> DeviceRuntime:
        if not isinstance(self.backend, RemoteCloudraBackend):
            raise RuntimeError("远程后端未配置")
        return DeviceRuntime(
            self.backend,
            self._device_state_store,
            self.storage.workspace,
            status_callback=self._on_device_status,
            approval_handler=self._show_device_approval,
            native_bridge=self._native_bridge,
            credential_handler=self._save_device_credential,
        )

    async def _save_device_credential(
        self,
        device_id: str,
        device_token: str,
    ) -> None:
        if (
            self._native_bridge is None
            or not isinstance(self.backend, RemoteCloudraBackend)
        ):
            raise NativeBridgeError(
                "unavailable",
                "Android Keystore 不可用，拒绝持久化设备凭据",
            )
        await self._native_bridge.secure_set(
            credential_key(
                "device",
                self.backend.profile.server_url,
                device_id,
            ),
            device_token,
        )

    async def _pair_device_runtime(self) -> None:
        if not isinstance(self.backend, RemoteCloudraBackend):
            return
        await self._stop_device_runtime(explicit=False)
        runtime = self._new_device_runtime()
        self._device_runtime = runtime
        permission_warning = ""
        if self._native_bridge is not None:
            permission = (
                await self._native_bridge.request_notification_permission()
            )
            if not permission.get("granted"):
                permission_warning = "（通知权限未授予）"
            await self._native_bridge.start_foreground_runtime(
                text="正在与 Cloudra Server 配对",
            )
        try:
            await runtime.pair()
            await runtime.announce()
        except Exception:
            if self._native_bridge is not None:
                with contextlib.suppress(NativeBridgeError):
                    await self._native_bridge.stop_foreground_runtime()
            self._device_runtime = None
            raise
        self._device_state_store.set_runtime_enabled(True)
        self._device_task = self.page.run_task(runtime.run)
        if permission_warning:
            self.status_text.value = (
                f"设备 Runtime 在线{permission_warning}；"
                "系统仍会在活跃服务列表显示它"
            )

    async def _restore_device_runtime(self) -> None:
        if (
            not isinstance(self.backend, RemoteCloudraBackend)
            or self._native_bridge is None
        ):
            return
        identity = self._device_state_store.identity(
            self.backend.profile.profile_id
        )
        device_id = str(identity.get("device_id", "")).strip()
        if not device_id:
            self._device_state_store.set_runtime_enabled(False)
            return
        token = await self._native_bridge.secure_get(
            credential_key(
                "device",
                self.backend.profile.server_url,
                device_id,
            )
        )
        if not token:
            self._device_state_store.set_runtime_enabled(False)
            raise NativeBridgeError(
                "credential_missing",
                "Keystore 中没有这台设备的凭据，请重新配对",
            )
        await self._stop_device_runtime(explicit=False)
        runtime = self._new_device_runtime()
        runtime.restore_pairing(
            device_id,
            token,
            display_name=str(identity.get("display_name", "")),
        )
        self._device_runtime = runtime
        await self._native_bridge.start_foreground_runtime(
            text="正在恢复 Cloudra 设备 Runtime",
        )
        try:
            await runtime.announce()
        except Exception:
            with contextlib.suppress(NativeBridgeError):
                await self._native_bridge.stop_foreground_runtime()
            self._device_runtime = None
            raise
        self._device_task = self.page.run_task(runtime.run)

    async def _stop_device_runtime(self, *, explicit: bool) -> None:
        runtime = self._device_runtime
        if runtime is not None:
            runtime.stop()
        device_task = self._device_task
        if device_task is not None and not device_task.done():
            device_task.cancel()
            if runtime is not None:
                with contextlib.suppress(
                    asyncio.CancelledError,
                    TimeoutError,
                ):
                    await asyncio.wait_for(
                        runtime.wait_stopped(),
                        timeout=5,
                    )
        elif runtime is not None:
            with contextlib.suppress(asyncio.CancelledError, TimeoutError):
                await asyncio.wait_for(
                    runtime.wait_stopped(),
                    timeout=5,
                )
        self._device_task = None
        self._device_runtime = None
        if explicit:
            self._device_state_store.set_runtime_enabled(False)
        if self._native_bridge is not None:
            with contextlib.suppress(NativeBridgeError):
                await self._native_bridge.stop_foreground_runtime()

    async def _show_device_approval(
        self,
        call: dict,
        preview: dict,
    ) -> tuple[bool, str]:
        tool_name = str(
            preview.get("tool", call.get("tool", "设备操作"))
        )
        if self._native_bridge is not None:
            with contextlib.suppress(NativeBridgeError):
                await self._native_bridge.update_foreground_runtime(
                    text=f"等待本地审批：{tool_name}",
                    route=(
                        "cloudra://runtime/approval/"
                        + str(call.get("tool_call_id", ""))
                    ),
                )
        if self._native_bridge is not None and self._app_background:
            with contextlib.suppress(NativeBridgeError):
                await self._native_bridge.show_approval_notification(
                    tool_call_id=str(call.get("tool_call_id", "")),
                    tool_name=tool_name,
                )
        decision = asyncio.get_running_loop().create_future()
        reason_field = ft.TextField(label="拒绝原因（可选）")
        server_name = (
            self.backend.profile.display_name
            if isinstance(self.backend, RemoteCloudraBackend)
            else "Cloudra Server"
        )
        controls = [
            ft.Text(f"服务器：{server_name}"),
            ft.Text(f"工具：{preview.get('tool', call.get('tool', ''))}"),
            ft.Text(
                f"风险：{preview.get('risk_summary', '修改本机数据')}",
                weight="bold",
            ),
        ]
        if preview.get("path"):
            controls.append(ft.Text(f"路径：{preview['path']}"))
        if preview.get("diff"):
            diff = str(preview["diff"])
            if len(diff) > _MAX_UI_DIFF_CHARS:
                diff = diff[:_MAX_UI_DIFF_CHARS] + "\n… diff 已截断 …"
            controls.append(ft.Text(diff, selectable=True))
        if preview.get("old_values") is not None:
            controls.append(
                ft.Text(
                    "旧值：\n"
                    + json.dumps(
                        preview.get("old_values", {}),
                        ensure_ascii=False,
                        indent=2,
                    ),
                    selectable=True,
                )
            )
            controls.append(
                ft.Text(
                    "新值：\n"
                    + json.dumps(
                        preview.get("new_values", {}),
                        ensure_ascii=False,
                        indent=2,
                    ),
                    selectable=True,
                )
            )
        displayed = {
            "tool",
            "risk_summary",
            "path",
            "diff",
            "old_values",
            "new_values",
        }
        extra_preview = {
            key: value
            for key, value in preview.items()
            if key not in displayed
        }
        if extra_preview:
            controls.append(
                ft.Text(
                    "操作详情：\n"
                    + json.dumps(
                        extra_preview,
                        ensure_ascii=False,
                        indent=2,
                    ),
                    selectable=True,
                )
            )
        controls.append(reason_field)
        dialog_closed = False

        def finish(approved: bool):
            nonlocal dialog_closed
            if not decision.done():
                decision.set_result(
                    (
                        approved,
                        "" if approved else (reason_field.value or ""),
                    )
                )
            if not dialog_closed:
                dialog_closed = True
                _close_dialog(self.page, dialog)

        def dismissed(_=None):
            nonlocal dialog_closed
            dialog_closed = True
            if not decision.done():
                decision.set_result((False, "用户关闭了本地审批"))

        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("Android 本地操作审批"),
            content=ft.Container(
                content=ft.Column(
                    controls,
                    tight=True,
                    spacing=12,
                    scroll=ft.ScrollMode.AUTO,
                ),
                width=560,
                height=520,
            ),
            actions=[
                ft.Button("拒绝", on_click=lambda _: finish(False)),
                ft.Button("批准并继续", on_click=lambda _: finish(True)),
            ],
            on_dismiss=dismissed,
        )
        _show_dialog(self.page, dialog)
        tool_call_id = str(call.get("tool_call_id", ""))
        try:
            answer = await decision
        finally:
            if not dialog_closed:
                dialog_closed = True
                with contextlib.suppress(Exception):
                    _close_dialog(self.page, dialog)
            if self._native_bridge is not None:
                if tool_call_id:
                    with contextlib.suppress(
                        NativeBridgeError,
                        TimeoutError,
                    ):
                        await asyncio.wait_for(
                            self._native_bridge.cancel_notification(
                                tool_call_id
                            ),
                            timeout=2,
                        )
                with contextlib.suppress(
                    NativeBridgeError,
                    TimeoutError,
                ):
                    await asyncio.wait_for(
                        self._native_bridge.update_foreground_runtime(
                            text=(
                                "后台在线，点按返回 Cloudra"
                                if self._app_background
                                else "设备在线"
                            ),
                        ),
                        timeout=2,
                    )
        return answer

    async def _new_conversation(self):
        try:
            conversation = await self.backend.create_conversation()
        except BackendError as exc:
            self.status_text.value = str(exc)
            self.page.update()
            return
        await self._select_conversation(conversation["id"])
        await self._load_sidebar()

    async def _select_conversation(self, conversation_id: str):
        self.current_conversation_id = conversation_id
        self.current_session_id = None
        self._stop_event_listener()
        self.messages.controls = []
        self._pending_user_echoes.clear()

        try:
            history = await self.backend.get_conversation_messages(
                conversation_id
            )
            sessions = await self.backend.list_sessions(conversation_id)
        except BackendError as exc:
            self.status_text.value = str(exc)
            self.page.update()
            return

        # 加载服务器权威历史（system/user/assistant）
        for msg in history:
            role = msg.get("role", "event")
            content = msg.get("content", "")
            self.messages.controls.append(_MessageBubble(role, content))

        if sessions:
            latest = sessions[0]
            self.current_session_id = latest["session_id"]
            running = latest.get("state") in (
                "queued",
                "running",
                "waiting_for_user",
                "waiting_for_approval",
                "waiting_for_device",
                "cancel_requested",
            )
            self._set_running_state(running)
            # 终态 Session 也会从已保存 cursor 补拉 App 离线期间的事件。
            self._start_event_listener(conversation_id)
        else:
            self._set_running_state(False)

        if self.backend.supports_approvals:
            self.page.run_task(self._check_pending_approvals)
        self.page.run_task(self._check_pending_interactions)
        self.messages.update()

    def _set_running_state(self, running: bool):
        self._session_active = running
        self.send_btn.disabled = False
        self.send_btn.visible = True
        self.send_btn.tooltip = "补充要求" if running else "发送"
        self.cancel_btn.visible = running
        self.input_field.disabled = False
        self.input_field.hint_text = (
            "向运行中的 Agent 补充要求..."
            if running
            else "输入任务..."
        )
        self.status_text.value = "运行中..." if running else "就绪"
        self.page.update()

    def _add_event_message(self, event_type: str, data: dict):
        if event_type == "user_message":
            content = str(data.get("content") or "").strip()
            if not content:
                return
            if content in self._pending_user_echoes:
                self._pending_user_echoes.remove(content)
                return
            self.messages.controls.append(_MessageBubble("user", content))
            self.messages.update()
            return
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
            try:
                conversation = await self.backend.create_conversation()
            except BackendError as exc:
                self.status_text.value = str(exc)
                self.page.update()
                return
            self.current_conversation_id = conversation["id"]
            await self._load_sidebar()

        self.input_field.value = ""
        self._streaming_bubble = None
        self._streaming_text = ""
        self.messages.controls.append(_MessageBubble("user", query))
        self._pending_user_echoes.append(query)
        self._pending_user_echoes = self._pending_user_echoes[-32:]
        self.messages.update()

        self.status_text.value = "命令已发送"
        self.page.update()
        try:
            if self._session_active and self.current_session_id is not None:
                record = await self.backend.append_session_message(
                    self.current_conversation_id,
                    self.current_session_id,
                    query,
                )
                cid = self.current_conversation_id
            else:
                cid, record = await self.backend.submit_session(
                    query,
                    conversation_id=self.current_conversation_id,
                    working_directory=(
                        self.working_directory
                        if self.backend.mode == "local"
                        else None
                    ),
                )
        except BackendError as exc:
            if query in self._pending_user_echoes:
                self._pending_user_echoes.remove(query)
            self.status_text.value = str(exc)
            self.page.update()
            return
        previous_session_id = self.current_session_id
        self.current_session_id = record["session_id"]
        self._set_running_state(True)
        command_state = (record.get("command") or {}).get("state")
        if command_state == "applied":
            self.status_text.value = "服务器已接收 · 已生效"
            self.page.update()
        if (
            previous_session_id != self.current_session_id
            or self._event_task is None
            or self._event_task.done()
        ):
            self._start_event_listener(cid)

    async def _on_cancel(self):
        if not self.current_conversation_id or not self.current_session_id:
            return
        try:
            await self.backend.cancel_session(
                self.current_conversation_id,
                self.current_session_id,
            )
        except BackendError as exc:
            self.status_text.value = str(exc)
            self.page.update()
            return
        self.status_text.value = "已请求取消"
        self.page.update()

    # ------------------------------------------------------------------
    # 事件订阅
    # ------------------------------------------------------------------
    def _start_event_listener(self, conversation_id: str):
        self._stop_event_listener()
        self._event_task = self.page.run_task(self._event_loop, conversation_id)
        self._interaction_task = self.page.run_task(
            self._interaction_loop,
            conversation_id,
        )
        if self.backend.supports_approvals:
            self._approval_task = self.page.run_task(
                self._approval_loop,
                conversation_id,
            )

    def _stop_event_listener(self):
        for task in (
            self._event_task,
            self._approval_task,
            self._interaction_task,
        ):
            if task is not None and not task.done():
                task.cancel()
        self._event_task = None
        self._approval_task = None
        self._interaction_task = None

    async def _shutdown(self):
        """Close client transports only; the authoritative server Session keeps running."""
        self._stop_event_listener()
        await self._stop_device_runtime(explicit=False)
        if isinstance(self.backend, RemoteCloudraBackend):
            await self.backend.close()

    def _finish_event_listener(self):
        if self._approval_task is not None and not self._approval_task.done():
            self._approval_task.cancel()
        if self._interaction_task is not None and not self._interaction_task.done():
            self._interaction_task.cancel()
        self._approval_task = None
        self._interaction_task = None
        self._event_task = None

    async def _event_loop(self, conversation_id: str):
        session_id = self.current_session_id
        if session_id is None:
            return
        cursor = self.backend.load_cursor(conversation_id, session_id)
        try:
            async for event in self.backend.stream_events(
                conversation_id,
                session_id,
                after_cursor=cursor,
            ):
                # The cursor advances only after the event was applied to UI state.
                if event.event_type == "interaction_requested":
                    await self._show_interaction_dialog(event.data)
                elif event.event_type == "waiting_for_user":
                    self._set_running_state(True)
                    self.status_text.value = "等待你的回答"
                elif event.event_type == "waiting_for_approval":
                    self._set_running_state(True)
                    self.status_text.value = "等待危险操作审批"
                    await self._check_pending_approvals()
                elif event.event_type == "waiting_for_device":
                    self._set_running_state(True)
                    self.status_text.value = "等待 Android 设备工具"
                elif (
                    event.event_type == "device_tool_state"
                    and event.data.get("state")
                    == "waiting_for_local_approval"
                ):
                    self.status_text.value = "等待 Android 本地写操作审批"
                elif event.event_type == "artifact_created":
                    self.status_text.value = "有新的服务器产物可下载"
                self._add_event_message(event.event_type, event.data)
                self.backend.save_cursor(
                    conversation_id,
                    session_id,
                    event.cursor,
                )
                if event.event_type in TERMINAL_STATES:
                    self._set_running_state(False)
                self.page.update()
        except asyncio.CancelledError:
            return
        except BackendError as exc:
            self.status_text.value = str(exc)
            self.page.update()
            self._finish_event_listener()
            return

        # A reconnect may start after the terminal event's cursor. Confirm
        # authoritative state even when the stream has no newer event to replay.
        try:
            record = await self.backend.get_session(
                conversation_id,
                session_id,
            )
        except BackendError as exc:
            self.status_text.value = str(exc)
            self.page.update()
            self._finish_event_listener()
            return
        if record and record.get("state") in TERMINAL_STATES:
            self._set_running_state(False)
        self._finish_event_listener()

    async def _approval_loop(self, conversation_id: str):
        """Low-frequency durable fallback for child-Agent approval events."""
        displayed: set[int] = set()
        while True:
            try:
                approvals = await self.backend.list_pending_approvals(
                    conversation_id
                )
            except asyncio.CancelledError:
                return
            except BackendError:
                await asyncio.sleep(1)
                continue
            for approval in approvals:
                approval_id = approval.get("approval_id") or approval.get("id")
                if (
                    approval.get("conversation_id") == conversation_id
                    and approval_id not in displayed
                ):
                    displayed.add(approval_id)
                    await self._show_approval_dialog(approval)
            await asyncio.sleep(30)

    async def _interaction_loop(self, conversation_id: str):
        """Low-frequency durable fallback for child-Agent questions."""

        while True:
            try:
                interactions = await self.backend.list_pending_interactions(
                    conversation_id,
                )
            except asyncio.CancelledError:
                return
            except BackendError:
                await asyncio.sleep(1)
                continue
            for interaction in interactions:
                await self._show_interaction_dialog(interaction)
            await asyncio.sleep(30)

    async def _check_pending_approvals(self):
        if self.current_conversation_id is None:
            return
        for approval in await self.backend.list_pending_approvals(
            self.current_conversation_id
        ):
            if approval.get("conversation_id") == self.current_conversation_id:
                await self._show_approval_dialog(approval)
                break

    async def _check_pending_interactions(self):
        if self.current_conversation_id is None:
            return
        try:
            interactions = await self.backend.list_pending_interactions(
                self.current_conversation_id,
            )
        except BackendError as exc:
            self.status_text.value = str(exc)
            self.page.update()
            return
        for interaction in interactions:
            await self._show_interaction_dialog(interaction)

    async def _show_interaction_dialog(self, payload: dict):
        interaction_id = str(payload.get("interaction_id", ""))
        if not interaction_id or interaction_id in self._shown_interactions:
            return
        self._shown_interactions.add(interaction_id)
        prompt = str(payload.get("prompt", "Agent 正在等待你的回答"))
        prompt_field = ft.TextField(
            value=prompt,
            read_only=True,
            multiline=True,
            min_lines=1,
            max_lines=12,
            border=ft.InputBorder.NONE,
            bgcolor="transparent",
            text_size=14,
            selectable=True,
        )
        answer_field = ft.TextField(
            label="回答",
            multiline=True,
            min_lines=1,
            max_lines=5,
            autofocus=True,
        )

        async def submit_answer(_):
            try:
                await self.backend.respond_interaction(
                    self.current_conversation_id,
                    interaction_id,
                    answer_field.value or "",
                )
            except BackendError as exc:
                self.status_text.value = str(exc)
                self.page.update()
                return
            self._shown_interactions.discard(interaction_id)
            _close_dialog(self.page, dialog)
            self.status_text.value = "回答已生效，Agent 继续运行"
            self.page.update()

        dialog = ft.AlertDialog(
            title=ft.Text("Agent 需要你的回答"),
            content=ft.Column(
                [
                    prompt_field,
                    answer_field,
                ],
                tight=True,
                spacing=16,
            ),
            actions=[
                ft.Button(
                    "提交回答",
                    on_click=lambda event: self.page.run_task(
                        submit_answer,
                        event,
                    ),
                ),
            ],
        )
        _show_dialog(self.page, dialog)

    async def _download_artifact(self, artifact: dict):
        if self.current_conversation_id is None:
            return
        try:
            path = await self.backend.download_artifact(
                self.current_conversation_id,
                artifact["artifact_id"],
                self.storage.data_dir / "downloads",
            )
        except BackendError as exc:
            self.status_text.value = str(exc)
            self.page.update()
            return
        self.status_text.value = f"已下载：{path.name}"
        self.page.update()

    async def _show_artifacts(self):
        if self.current_conversation_id is None:
            self.status_text.value = "请先选择一个会话"
            self.page.update()
            return
        try:
            artifacts = await self.backend.list_artifacts(
                self.current_conversation_id,
            )
        except BackendError as exc:
            self.status_text.value = str(exc)
            self.page.update()
            return

        controls = []
        for artifact in artifacts:
            controls.append(
                ft.Row(
                    [
                        ft.Column(
                            [
                                ft.Text(
                                    str(artifact.get("name", "artifact")),
                                    weight="bold",
                                ),
                                ft.Text(
                                    (
                                        f"{artifact.get('size', 0)} bytes · "
                                        f"{str(artifact.get('sha256', ''))[:12]}"
                                    ),
                                    size=11,
                                    color="grey",
                                ),
                            ],
                            expand=True,
                            spacing=2,
                        ),
                        ft.Button(
                            "下载",
                            on_click=(
                                lambda _event, item=artifact:
                                self.page.run_task(
                                    self._download_artifact,
                                    item,
                                )
                            ),
                        ),
                    ],
                )
            )
        if not controls:
            controls.append(ft.Text("这个会话还没有登记产物。"))
        dialog = ft.AlertDialog(
            title=ft.Text("服务器产物"),
            content=ft.Column(
                controls,
                tight=True,
                spacing=12,
                scroll=ft.ScrollMode.AUTO,
                height=400,
            ),
            actions=[
                ft.Button(
                    "关闭",
                    on_click=lambda _: _close_dialog(self.page, dialog),
                )
            ],
        )
        _show_dialog(self.page, dialog)

    async def _show_approval_dialog(self, payload: dict):
        approval_id = payload.get("approval_id") or payload.get("id")
        if approval_id in self._displayed_approvals:
            return
        self._displayed_approvals.add(approval_id)
        details = payload.get("details", "")
        agent_name = payload.get("agent_name", "未知 Agent")
        tool_name = payload.get("tool_name") or "未知工具"
        risk_summary = payload.get("risk_summary") or "高风险工具调用"
        arguments = payload.get("normalized_arguments")
        if not isinstance(arguments, dict):
            arguments = {}
        candidate_diff = str(payload.get("candidate_diff") or "")
        server_name = (
            self.backend.profile.display_name
            if isinstance(self.backend, RemoteCloudraBackend)
            else "本机 Cloudra"
        )

        reason_field = ft.TextField(label="拒绝原因（可选）", expand=True)

        async def submit_decision(decision: str):
            try:
                changed = await self.backend.decide_approval(
                    self.current_conversation_id,
                    approval_id,
                    decision=decision,
                    denial_reason=(
                        reason_field.value or ""
                        if decision == "denied"
                        else ""
                    ),
                )
            except BackendError as exc:
                self._displayed_approvals.discard(approval_id)
                self.status_text.value = str(exc)
                self.page.update()
                return
            if not changed:
                self._displayed_approvals.discard(approval_id)
                self.status_text.value = "这条审批已决定或已过期"
                self.page.update()
                return
            _close_dialog(self.page, dialog)
            self._displayed_approvals.discard(approval_id)
            self.status_text.value = (
                "审批已批准" if decision == "approved" else "审批已拒绝"
            )
            self.page.update()

        metadata_controls = [
            ft.Text(f"服务器：{server_name}"),
            ft.Text(f"Agent：{agent_name}"),
            ft.Text(f"工具：{tool_name}"),
            ft.Text(f"风险：{risk_summary}", weight="bold"),
        ]
        if arguments:
            metadata_controls.append(
                ft.Text(
                    "参数：\n"
                    + json.dumps(
                        arguments,
                        ensure_ascii=False,
                        indent=2,
                    ),
                    selectable=True,
                )
            )
        metadata_controls.append(ft.Text(str(details), selectable=True))
        if candidate_diff and candidate_diff not in str(details):
            metadata_controls.append(
                ft.Text(
                    f"候选 diff：\n{candidate_diff}",
                    selectable=True,
                )
            )
        metadata_controls.append(reason_field)

        dialog = ft.AlertDialog(
            title=ft.Text(f"审批请求 - {agent_name}"),
            content=ft.Container(
                content=ft.Column(
                    metadata_controls,
                    tight=True,
                    spacing=12,
                    scroll=ft.ScrollMode.AUTO,
                ),
                width=560,
                height=520,
            ),
            actions=[
                ft.Button(
                    "拒绝",
                    on_click=lambda _: self.page.run_task(
                        submit_decision,
                        "denied",
                    ),
                ),
                ft.Button(
                    "批准",
                    on_click=lambda _: self.page.run_task(
                        submit_decision,
                        "approved",
                    ),
                ),
            ],
        )
        _show_dialog(self.page, dialog)


def main(page: ft.Page):
    CloudraUI(page, configure_app_storage())
