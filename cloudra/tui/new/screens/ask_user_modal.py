"""Agent 提问弹窗。"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Grid
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, Static


class AskUserModal(ModalScreen[str | None]):
    """显示 Agent 提问，返回用户输入文本或 None（关闭）。"""

    BINDINGS = [
        ("escape", "close", "关闭"),
    ]

    def __init__(
        self,
        interaction_id: str,
        agent_name: str,
        prompt: str,
        default_answer: str | None = None,
    ) -> None:
        super().__init__()
        self.interaction_id = interaction_id
        self.agent_name = agent_name
        self.prompt = prompt
        self.default_answer = default_answer or ""

    def compose(self) -> ComposeResult:
        with Grid(id="ask-dialog"):
            yield Label("? Agent 提问", id="ask-title")
            yield Static(f"来自: {self.agent_name}", id="ask-agent")
            yield Static(self.prompt, id="ask-prompt")
            yield Input(
                value=self.default_answer,
                placeholder="请输入回答…",
                id="ask-input",
            )
            with Grid(id="ask-buttons"):
                yield Button("提交", variant="primary", id="submit")
                yield Button("关闭", variant="default", id="close")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "submit":
            self._submit()
        elif event.button.id == "close":
            self.dismiss(None)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self._submit()

    def _submit(self) -> None:
        value = self.query_one("#ask-input", Input).value.strip()
        if value:
            self.dismiss(value)

    def action_close(self) -> None:
        self.dismiss(None)
