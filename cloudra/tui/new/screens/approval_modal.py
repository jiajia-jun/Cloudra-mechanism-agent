"""审批请求弹窗。"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Grid
from textual.screen import ModalScreen
from textual.widgets import Button, Label, Static


class ApprovalModal(ModalScreen[str | None]):
    """显示审批详情，返回 'approved'、'denied' 或 None（关闭）。"""

    BINDINGS = [
        ("y", "approve", "允许"),
        ("n", "deny", "拒绝"),
        ("escape", "close", "关闭"),
    ]

    def __init__(
        self,
        approval_id: int,
        agent_name: str,
        details: str,
        tool_name: str | None = None,
        arguments: str | None = None,
        risk_summary: str | None = None,
    ) -> None:
        super().__init__()
        self.approval_id = approval_id
        self.agent_name = agent_name
        self.details = details
        self.tool_name = tool_name or ""
        self.arguments = arguments or ""
        self.risk_summary = risk_summary or ""

    def compose(self) -> ComposeResult:
        with Grid(id="approval-dialog"):
            yield Label("※ 安全审批", id="approval-title")
            yield Static(f"来自: {self.agent_name}", id="approval-agent")
            yield Static(self.details, id="approval-details")
            if self.tool_name:
                yield Static(f"工具: {self.tool_name}", id="approval-tool")
            if self.arguments:
                yield Static(f"参数: {self.arguments}", id="approval-args")
            if self.risk_summary:
                yield Static(f"风险评估: {self.risk_summary}", id="approval-risk")
            with Grid(id="approval-buttons"):
                yield Button("允许 (Y)", variant="success", id="approve")
                yield Button("拒绝 (N)", variant="error", id="deny")
                yield Button("关闭", variant="default", id="close")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "approve":
            self.dismiss("approved")
        elif event.button.id == "deny":
            self.dismiss("denied")
        elif event.button.id == "close":
            self.dismiss(None)

    def action_approve(self) -> None:
        self.dismiss("approved")

    def action_deny(self) -> None:
        self.dismiss("denied")

    def action_close(self) -> None:
        self.dismiss(None)
