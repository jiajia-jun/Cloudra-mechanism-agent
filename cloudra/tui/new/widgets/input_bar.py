"""底部输入栏 Widget。"""

from __future__ import annotations

import asyncio

from rich.style import Style
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.strip import Strip
from textual.widgets import Button, OptionList, Static, TextArea
from textual.widgets.option_list import Option

from cloudra.tui.new.commands import COMMAND_DESCRIPTIONS


def _input_bar_of(widget) -> "InputBar | None":
    """沿组件树向上找到所属的 InputBar。"""
    node = widget.parent
    while node is not None:
        if isinstance(node, InputBar):
            return node
        node = node.parent
    return None


class SubmitTextArea(TextArea):
    """Enter 发送，Ctrl+Enter / Ctrl+J 换行的多行输入框。

    标准 TextArea 的 Enter 固定是换行，且没有 Submitted 消息，
    这里用按键绑定显式区分「发送」和「换行」。
    Tab / Esc / Enter 在命令补全弹出时优先作用于补全。
    """

    BINDINGS = [
        Binding("enter", "submit_message", "发送", show=False, priority=True),
        Binding("ctrl+enter", "insert_newline", "换行", show=False),
        Binding("ctrl+j", "insert_newline", "换行", show=False),
        Binding("tab", "complete_command", "补全", show=False, priority=True),
        Binding("escape", "dismiss_suggest", "关闭补全", show=False, priority=True),
    ]

    class Submitted(Message):
        """用户按 Enter 请求发送。"""

        def __init__(self, text_area: "SubmitTextArea") -> None:
            super().__init__()
            self.text_area = text_area

    def action_submit_message(self) -> None:
        bar = _input_bar_of(self)
        if bar is not None and bar.suggest_visible:
            bar.accept_suggestion()
            return
        self.post_message(self.Submitted(self))

    def action_insert_newline(self) -> None:
        self.insert("\n")

    def action_complete_command(self) -> None:
        bar = _input_bar_of(self)
        if bar is not None and bar.suggest_visible:
            bar.accept_suggestion()
        else:
            # 无补全时保持 Tab 的默认行为：切换焦点
            self.app.action_focus_next()

    def action_dismiss_suggest(self) -> None:
        bar = _input_bar_of(self)
        if bar is not None and bar.suggest_visible:
            bar.hide_suggest()
        else:
            # 无补全时把 Esc 交还给屏幕（取消当前任务）
            cancel = getattr(self.screen, "action_cancel_current", None)
            if cancel is not None:
                result = cancel()
                if asyncio.iscoroutine(result):
                    asyncio.create_task(result)

    def action_copy(self) -> None:
        """输入框有自己的选区就复制它，否则委托给屏幕（复制聊天区拖选）。

        TextArea 的 ctrl+c 绑定优先于 Screen 的 copy_text，输入框又常是默认
        焦点，不转发的话聊天区拖选后按 Ctrl+C 会被这里静默吞掉。
        """
        if self.selected_text:
            super().action_copy()
        else:
            self.screen.action_copy_text()

    def _blank_strip(self, width: int = 0) -> Strip:
        style = self.rich_style or Style()
        return Strip.blank(max(0, width), style)

    def render_line(self, y: int) -> Strip:
        """窄终端下 content_width 会被 border/padding 吃成 0。

        Textual 对 placeholder 做 ``wrap(0)`` 会 ``ValueError: range() arg 3
        must not be zero``，整屏崩溃。宽度不够时画空行，不折 placeholder。
        """
        if self.content_size.width <= 0:
            return self._blank_strip(0)
        try:
            return super().render_line(y)
        except ValueError:
            return self._blank_strip(self.content_size.width)

    def render_lines(self, crop):
        try:
            return super().render_lines(crop)
        except (ValueError, AttributeError):
            return [self._blank_strip(crop.width) for _ in range(max(0, crop.height))]


class InputBar(Vertical):
    """命令补全弹层 + 输入框 + 发送按钮。Enter 发送，Ctrl+Enter 换行。"""

    class SendMessage(Message):
        """用户点击发送或回车时发出。"""

        def __init__(self, content: str) -> None:
            super().__init__()
            self.content = content

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._follow_up = False
        self._target_name: str | None = None
        # 当前补全候选的命令名（与 OptionList 选项一一对应）
        self._suggest_cmds: list[str] = []

    def compose(self):
        suggest = OptionList(id="command-suggest")
        suggest.display = False  # CSS 之外也默认隐藏（裸 widget 场景无样式表）
        yield suggest
        with Horizontal(id="input-row"):
            yield Static("新任务", id="session-label")
            yield SubmitTextArea(placeholder="输入任务或补充要求… (方向键移动光标, Enter 发送, Ctrl+Enter 换行, / 补全命令)", id="message-input")
            yield Button("发送", id="send-button", variant="primary")

    # ------------------------------------------------------------------
    # 标签：新任务 / 补充要求 / 定向到指定 Agent
    # ------------------------------------------------------------------

    @property
    def follow_up(self) -> bool:
        """True = 发送内容将作为补充要求注入运行中的任务。"""
        return self._follow_up

    @follow_up.setter
    def follow_up(self, value: bool) -> None:
        self._follow_up = value
        self._refresh_label()

    @property
    def target_name(self) -> str | None:
        """当前输入定向的 Agent 名；None = 自动（主 Agent / 新任务）。"""
        return self._target_name

    @target_name.setter
    def target_name(self, value: str | None) -> None:
        self._target_name = value
        self._refresh_label()

    def _refresh_label(self) -> None:
        label = self.query_one("#session-label", Static)
        if self._target_name:
            label.update(f"→ {self._target_name}")
        else:
            label.update("补充要求" if self._follow_up else "新任务")

    # ------------------------------------------------------------------
    # 斜杠命令补全
    # ------------------------------------------------------------------

    @property
    def suggest_visible(self) -> bool:
        return self.query_one("#command-suggest", OptionList).display

    def on_text_area_changed(self, event: TextArea.Changed) -> None:
        text = event.text_area.text
        body = text[1:] if text.startswith("/") else None
        if body is None or "\n" in body or " " in body:
            self.hide_suggest()
            return
        matches = [
            (cmd, desc)
            for cmd, desc in COMMAND_DESCRIPTIONS
            if cmd.startswith(body) and cmd != body
        ]
        if not matches:
            self.hide_suggest()
            return
        suggest = self.query_one("#command-suggest", OptionList)
        suggest.clear_options()
        suggest.add_options(
            [Option(f"/{cmd}  {desc}", id=cmd) for cmd, desc in matches]
        )
        self._suggest_cmds = [cmd for cmd, _ in matches]
        suggest.highlighted = 0
        suggest.display = True

    def hide_suggest(self) -> None:
        suggest = self.query_one("#command-suggest", OptionList)
        suggest.display = False
        self._suggest_cmds = []

    def accept_suggestion(self) -> None:
        """把高亮的补全项写入输入框。"""
        if not self._suggest_cmds:
            return
        suggest = self.query_one("#command-suggest", OptionList)
        index = suggest.highlighted if suggest.highlighted is not None else 0
        index = min(index, len(self._suggest_cmds) - 1)
        cmd = self._suggest_cmds[index]
        textarea = self.query_one("#message-input", TextArea)
        textarea.text = f"/{cmd} "
        textarea.move_cursor((0, len(textarea.text)))
        self.hide_suggest()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        if event.option_list.id == "command-suggest":
            self.accept_suggestion()

    # ------------------------------------------------------------------
    # 发送
    # ------------------------------------------------------------------

    def focus_input(self) -> None:
        """把焦点移到输入框。"""
        self.query_one("#message-input", TextArea).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "send-button":
            self._send()

    def on_submit_text_area_submitted(self, event: SubmitTextArea.Submitted) -> None:
        """Enter 提交。"""
        self._send()

    def _send(self) -> None:
        textarea = self.query_one("#message-input", TextArea)
        content = textarea.text.strip()
        if not content:
            return
        textarea.text = ""
        self.hide_suggest()
        self.post_message(self.SendMessage(content))
