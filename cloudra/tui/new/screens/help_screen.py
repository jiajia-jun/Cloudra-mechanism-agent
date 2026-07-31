"""帮助页面。"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.screen import Screen
from textual.widgets import Footer, Header, Static

_HELP_TEXT = """
[b]Cloudra TUI 快捷键与命令[/b]

[b]核心概念：对话（conversation）[/b]
  对话是持久上下文，多次任务共享记忆（状态栏显示"对话 …xxxxxx"与"记忆 N条≈Tk"）。
  任务完成后再输入，会在[b]同一对话[/b]里开启新任务，上下文自动延续。
  想换个话题互不干扰时，用 /new 开新对话、/conv 切换、/list 查看历史。

[b]侧栏（Ctrl+B 或 /agents）[/b]
  Agent 区：主 Agent 与各子 Agent 的输出互相独立。
    选中某个 Agent 后，聊天区只显示它的输出，输入框显示"→ agent名"，
    此时发送的消息会直接插入该 Agent 的运行上下文（可指挥子 Agent）。
    选"全部"回到完整对话视图。
  对话区：点击切换对话，首项"＋ 新建对话"。
  任务运行中不能切换/新建对话（先 Esc 打断）。

[b]全局[/b]
  [b]?[/b]           显示本帮助
  [b]Tab[/b]         切换焦点（命令补全弹出时为确认补全）
  [b]Esc[/b]         取消当前任务 / 关闭弹窗 / 关闭补全
  [b]Ctrl+B[/b]      打开/收起侧栏
  [b]Ctrl+T[/b]      对话上下文（记忆）统计
  [b]q[/b]           退出 TUI（输入框聚焦时请先 Tab 移出）

[b]输入框（底部）[/b]
  [b]Enter[/b]       发送消息（补全弹出时为确认补全）
  [b]Ctrl+Enter / Ctrl+J[/b]  换行
  输入 [b]/[/b] 自动弹出命令补全，Tab/Enter/点击确认

[b]斜杠命令[/b]
  [b]/new[/b]        新建对话（任务运行中不可用）
  [b]/list[/b]       列出历史对话
  [b]/conv [id][/b]  切换对话；无参时打开侧栏
  [b]/agents[/b]     打开/收起侧栏（同 Ctrl+B）
  [b]/compact [N][/b] 压缩对话上下文（保留最近 N 条，默认 4）
  [b]/context[/b]    对话上下文（记忆）统计（同 Ctrl+T）
  [b]/yolo [on|off][/b] 查看/切换自动审批模式
  [b]/cancel[/b]     取消当前任务（同 Esc）
  [b]/quit[/b]       退出

[b]运行逻辑[/b]
  • 没有运行中任务时发送消息：在当前对话启动新任务
  • 任务运行中发送消息：作为"用户补充要求"注入该任务（输入框左侧显示"补充要求"）
  • 侧栏选中子 Agent 后发送：直接插入该子 Agent 的运行上下文
  • 启动/切换对话时，该对话的历史问答会自动回放到聊天区
"""


class HelpScreen(Screen):
    """显示 TUI 帮助信息。"""

    BINDINGS = [
        ("escape", "dismiss", "关闭帮助"),
        ("q", "dismiss", "关闭帮助"),
    ]

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with VerticalScroll(id="help-scroll"):
            yield Static(_HELP_TEXT, id="help-content")
        yield Footer()

    def action_dismiss(self) -> None:
        self.dismiss()
