"""当前 Session 上下文统计页面。"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.screen import Screen
from textual.widgets import Footer, Header, Label, Static

from cloudra.context_manager import ContextManager
from cloudra.service import CloudraService
from cloudra.token_estimator import TokenEstimator


class ContextScreen(Screen):
    """显示当前 Session 的上下文消息数、token 估算、文件路径等。"""

    BINDINGS = [
        ("escape", "dismiss", "关闭"),
        ("q", "dismiss", "关闭"),
    ]

    def __init__(
        self,
        conversation_id: str,
        session_id: str | None = None,
        agent_id: str | None = None,
    ) -> None:
        super().__init__()
        self.conversation_id = conversation_id
        self.session_id = session_id
        self.agent_id = agent_id or "a-0"

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with VerticalScroll(id="context-scroll"):
            yield Label("上下文统计", id="context-title")
            yield Static("加载中…", id="context-content")
        yield Footer()

    async def on_mount(self) -> None:
        content = await self._build_content()
        self.query_one("#context-content", Static).update(content)

    async def _build_content(self) -> str:
        import os

        state = "—"
        if self.session_id:
            service = CloudraService()
            record = service.session_runner.get(self.conversation_id, self.session_id)
            state = record.state if record else "未知"

        # 与后端一致：Coordinator（a-0）的上下文是对话级共享的（不按 session 隔离，
        # 任务结束也不清空，见 react.py 的 clear_context 分支）；
        # 只有子 Agent（非 a-0）的上下文按 session 隔离。
        shared = self.agent_id == "a-0"
        scoped_session = None if shared else self.session_id

        cm = ContextManager(
            agent_id=self.agent_id,
            conversation_id=self.conversation_id,
            prompt=None,
            query="",
            session_id=scoped_session,
        )
        try:
            context = await cm.load()
        except Exception as exc:
            return f"无法加载上下文: {exc}"

        scope_label = (
            "对话级共享（同一对话的所有 Coordinator 任务延续此上下文）"
            if shared
            else "任务级独立（子 Agent 任务结束后上下文会被释放）"
        )
        released = not shared and not os.path.exists(cm.context_file)

        token_count = TokenEstimator.estimate_messages(context)
        lines = [
            f"对话:    {self.conversation_id}",
            f"上下文:  {scope_label}",
            f"State:   {state}",
            f"Messages: {len(context)}",
            f"Estimated tokens: {token_count}",
            "",
        ]
        if released:
            lines.append("（该子 Agent 的上下文文件已释放，以下为初始状态）")
            lines.append("")
        lines.append("--- Messages ---")
        for i, msg in enumerate(context, 1):
            role = msg.get("role", "?")
            content_preview = self._preview(msg.get("content", ""))
            lines.append(f"{i}. [{role}] {content_preview}")

        return "\n".join(lines)

    @staticmethod
    def _preview(content) -> str:
        if content is None:
            return ""
        if isinstance(content, str):
            text = content
        elif isinstance(content, list):
            parts = []
            for p in content:
                if isinstance(p, dict):
                    if p.get("type") == "text":
                        parts.append(str(p.get("text", "")))
                    elif p.get("type") == "image_url":
                        parts.append("[图片]")
                else:
                    parts.append(str(p))
            text = " ".join(parts)
        else:
            text = str(content)
        text = text.replace("\n", " ")
        return text[:120] + ("…" if len(text) > 120 else "")

    def action_dismiss(self) -> None:
        self.dismiss()
