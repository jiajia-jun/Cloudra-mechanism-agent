"""带复制按钮的代码块 Widget。"""

from __future__ import annotations

import subprocess

from rich.panel import Panel
from rich.syntax import Syntax
from textual.containers import Horizontal
from textual.widgets import Button, Static


class CodeBlock(Horizontal):
    """显示代码块并提供复制按钮。"""

    def __init__(self, code: str, language: str = "text", *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.code = code
        self.language = language

    def compose(self):
        syntax = Syntax(self.code, self.language, theme="monokai", word_wrap=True)
        panel = Panel(syntax, title=self.language or "code")
        yield Static(panel, id="code-static")
        yield Button("复制", id="copy-button", variant="primary")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "copy-button":
            try:
                self._copy_to_clipboard(self.code)
                self.app.notify("已复制到剪贴板", severity="information")
            except Exception as exc:
                self.app.notify(f"复制失败: {exc}", severity="error")

    @staticmethod
    def _copy_to_clipboard(text: str) -> None:
        """尝试把文本写入系统剪贴板。"""
        # 尝试 xclip / xsel / pbcopy / clip
        commands = [
            ["xclip", "-selection", "clipboard"],
            ["xsel", "--clipboard", "--input"],
            ["pbcopy"],
            ["clip"],
        ]
        for cmd in commands:
            try:
                subprocess.run(cmd, input=text, text=True, check=True)
                return
            except Exception:
                continue
        raise RuntimeError("未找到可用的剪贴板工具（xclip/xsel/pbcopy/clip）")
