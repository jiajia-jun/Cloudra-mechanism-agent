"""对话级上下文统计页面（按 agent 分列）。"""

from __future__ import annotations

import asyncio

from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.screen import Screen
from textual.widgets import Footer, Header, Label, Static

from cloudra.persistence.context_stats import (
    collect_conversation_context_stats,
    format_context_report,
)
from cloudra.services.service import CloudraService


class ContextScreen(Screen):
    """显示当前对话下各 Agent 的上下文消息数与 token 统计。"""

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
            yield Static("加载中…", id="context-content", markup=False)
        yield Footer()

    async def on_mount(self) -> None:
        content = await self._build_content()
        self.query_one("#context-content", Static).update(content)

    async def _build_content(self) -> str:
        try:
            service = CloudraService()
            records = await asyncio.to_thread(
                service.session_runner.list, self.conversation_id
            )
        except Exception:
            records = []

        try:
            stats = await asyncio.to_thread(
                collect_conversation_context_stats,
                self.conversation_id,
                session_records=records,
            )
        except Exception as exc:
            return f"无法加载上下文统计: {exc}"

        focus_key = self.agent_id
        if self.session_id and self.agent_id not in ("a-0", "supervisor"):
            focus_key = f"{self.agent_id}/{self.session_id}"
        return format_context_report(stats, focus_key=focus_key)

    def action_dismiss(self) -> None:
        self.dismiss()
