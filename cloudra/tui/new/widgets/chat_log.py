"""聊天/输出显示区域 Widget。"""

from __future__ import annotations

from rich.markdown import Markdown
from rich.panel import Panel
from rich.text import Text
from textual.containers import VerticalScroll
from textual.widgets import Static

from cloudra.tui.new.widgets.code_block import CodeBlock
from cloudra.tool_presentation import format_tool_payload

_WELCOME_TEXT = """\
[bold green]Cloudra[/bold green]  [dim]AI 化学科研助手[/dim]

输入任务，Enter 发送 · Ctrl+Enter 换行 · 输入 / 自动补全命令
运行中可直接输入补充要求，Esc 打断当前任务

[bold]两个概念[/bold]
  [cyan]对话[/cyan] = 持久上下文，多次任务共享记忆（/conv 切换、/new 新建）
  [cyan]任务[/cyan] = 一次执行；任务完成后再输入，会在同一对话里开启新任务

[bold]侧栏（Ctrl+B 或 /agents）[/bold]
  Agent 列表：切换查看主 Agent / 各子 Agent 的独立输出，
            选中某个 Agent 后输入会直接插入它的运行上下文
  对话列表：点击切换或新建对话

[bold]斜杠命令[/bold]
  /conv <id> 切换对话 · /compact 压缩上下文 · /yolo 自动审批
  /help 完整帮助
"""

# 工具结果折叠阈值（行）
_TOOL_COLLAPSE_LINES = 8


def _format_tool_payload(text: str, *, is_result: bool = False) -> str:
    """兼容旧调用点；实际展示规则由共享格式化器统一管理。"""
    return format_tool_payload(text, is_result=is_result)


class ToolCard(Static):
    """工具调用卡片；结果过长时默认折叠，点击展开/收起。"""

    def __init__(
        self,
        tool: str,
        body: str,
        finished: bool,
        *,
        collapsed_hint: str | None = None,
        full_body: str | None = None,
    ) -> None:
        super().__init__()
        self._tool = tool
        self._finished = finished
        self._full_body = full_body or body
        self._collapsed = collapsed_hint is not None
        self._collapsed_body = body if self._collapsed else None
        self._collapsed_hint = collapsed_hint
        self._refresh()

    def _refresh(self) -> None:
        icon = "√" if self._finished else "▶"
        style = "green" if self._finished else "yellow"
        if self._collapsed:
            body = f"{self._collapsed_body}\n{self._collapsed_hint}"
        else:
            body = self._full_body
        self.update(Panel(Text(body), title=f"{icon} {self._tool}", border_style=style))

    def on_click(self) -> None:
        if self._collapsed_body is None:
            return
        self._collapsed = not self._collapsed
        self._refresh()

    def finish(
        self,
        body: str,
        *,
        collapsed_hint: str | None = None,
        full_body: str | None = None,
    ) -> None:
        """Finish a running card in place instead of mounting a duplicate."""
        self._finished = True
        self._full_body = full_body or body
        self._collapsed = collapsed_hint is not None
        self._collapsed_body = body if self._collapsed else None
        self._collapsed_hint = collapsed_hint
        self._refresh()


class ChatLog(VerticalScroll):
    """统一对话视图：默认按时间顺序显示所有 session 的输出（像旧 TUI），

    ``view_session_id`` 设为某个 session 时则只显示该 session（深入查看）。
    """

    # 流式渲染节流间隔（秒）：chunk 先累积进缓冲区，到点统一刷新 widget，
    # 避免每个 token 都触发一次整段文本的重绘和滚动。
    STREAM_FLUSH_INTERVAL = 0.50
    STREAM_CONTENT_WINDOW = 2_000
    STREAM_REASONING_WINDOW = 800
    MAX_WIDGETS = 320
    SCROLL_FLUSH_INTERVAL = 0.20

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # session_id -> list of message widgets
        self._messages: dict[str, list] = {}
        # 全局时间顺序：[ (session_id, widget), ... ]
        self._order: list[tuple[str, object]] = []
        # session_id -> current streaming message widget (assistant)
        self._stream_widget: dict[str, Static | None] = {}
        # session_id -> accumulated streaming text（正文与 reasoning 分开）
        self._stream_content: dict[str, list[str]] = {}
        self._stream_reasoning: dict[str, list[str]] = {}
        # 有待刷新内容的流式 session
        self._dirty_streams: set[str] = set()
        self._flush_scheduled = False
        self._scroll_scheduled = False
        # Durable user-message event id -> (session_id, widget). Optimistic
        # local echo and IPC replay share the id, so one message is shown once.
        self._user_message_widgets: dict[str, tuple[str, Static]] = {}
        # None = 显示全部 session（默认）
        self._view_session_id: str | None = None
        # None = 不按 agent 过滤；设为 "a-3" 时只显示该 agent 的所有 session
        self._view_agent_prefix: str | None = None

    def on_mount(self) -> None:
        self._show_welcome_if_empty()

    @property
    def view_session_id(self) -> str | None:
        return self._view_session_id

    @view_session_id.setter
    def view_session_id(self, session_id: str | None) -> None:
        self._view_session_id = session_id
        self._view_agent_prefix = None
        self.refresh_view()

    @property
    def view_agent_prefix(self) -> str | None:
        return self._view_agent_prefix

    # 向后兼容别名（旧代码/测试用 current_session_id 读写视图）
    @property
    def current_session_id(self) -> str | None:
        return self._view_session_id

    @current_session_id.setter
    def current_session_id(self, session_id: str | None) -> None:
        self.view_session_id = session_id

    def ensure_session(self, session_id: str) -> None:
        """确保某 session 有消息列表。"""
        if session_id not in self._messages:
            self._messages[session_id] = []
            self._stream_widget[session_id] = None
            self._stream_content[session_id] = []
            self._stream_reasoning[session_id] = []

    def _is_visible(self, session_id: str) -> bool:
        if self._view_session_id is not None:
            return self._view_session_id == session_id
        if self._view_agent_prefix is not None:
            prefix = self._view_agent_prefix
            return session_id == prefix or session_id.startswith(f"{prefix}_")
        return True

    def append_system(self, session_id: str, content: str) -> Static:
        """追加一条系统提示。"""
        self.ensure_session(session_id)
        widget = Static(Panel(content, border_style="blue", title="系统"))
        self._add_widget(session_id, widget)
        return widget

    def append_user(
        self,
        session_id: str,
        content: str,
        *,
        message_id: str | None = None,
    ) -> Static:
        """追加一条用户消息（返回 widget，便于失败时标记）。"""
        self.ensure_session(session_id)
        if message_id and message_id in self._user_message_widgets:
            return self._user_message_widgets[message_id][1]
        widget = Static(Text(f"» {content}", style="bold green"))
        if message_id:
            self._user_message_widgets[message_id] = (session_id, widget)
        self._add_widget(session_id, widget)
        return widget

    def append_divider(self, session_id: str, text: str) -> Static:
        """追加一条分隔线（用于标记新任务开始等）。"""
        self.ensure_session(session_id)
        widget = Static(Text(text, style="bright_black"))
        self._add_widget(session_id, widget)
        return widget

    def append_alert(self, session_id: str, title: str, body: str, style: str = "red") -> Static:
        """追加一条告警卡片（任务失败/取消等终态提示）。"""
        self.ensure_session(session_id)
        if body:
            body = _format_tool_payload(body)
            widget = Static(Panel(Text(body), title=title, border_style=style))
        else:
            widget = Static(Panel(title, border_style=style))
        self._add_widget(session_id, widget)
        return widget

    def start_stream(self, session_id: str, agent_name: str) -> None:
        """开始一条新的 assistant 流式消息。"""
        self.ensure_session(session_id)
        # 结束上一条流式消息（如果有）
        self.end_stream(session_id)
        text = Text(f"● {agent_name}: ", style="bold cyan")
        widget = Static(text)
        self._stream_widget[session_id] = widget
        self._add_widget(session_id, widget)

    def append_stream_chunk(self, session_id: str, delta: str, agent_name: str | None = None) -> None:
        """追加流式输出片段（节流刷新，不立即重绘）。"""
        self.ensure_session(session_id)
        if self._stream_widget.get(session_id) is None:
            self.start_stream(session_id, agent_name or "Agent")
        self._stream_content[session_id].append(delta)
        self._dirty_streams.add(session_id)
        self._schedule_stream_flush()

    def append_reasoning_chunk(self, session_id: str, delta: str, agent_name: str | None = None) -> None:
        """追加 reasoning 内容（与正文分开，渲染为暗色斜体）。"""
        self.ensure_session(session_id)
        if self._stream_widget.get(session_id) is None:
            self.start_stream(session_id, agent_name or "Agent")
        self._stream_reasoning[session_id].append(delta)
        self._dirty_streams.add(session_id)
        self._schedule_stream_flush()

    def _schedule_stream_flush(self) -> None:
        if self._flush_scheduled:
            return
        self._flush_scheduled = True
        self.set_timer(self.STREAM_FLUSH_INTERVAL, self._flush_streams)

    def _flush_streams(self) -> None:
        """到点统一把累积的流式文本刷新到 widget。"""
        self._flush_scheduled = False
        dirty = self._dirty_streams
        self._dirty_streams = set()
        for session_id in dirty:
            widget = self._stream_widget.get(session_id)
            if widget is None or not self._is_visible(session_id):
                continue
            widget.update(self._combined_stream_text(session_id))
        if any(self._is_visible(sid) for sid in dirty):
            self._maybe_scroll_end()

    def _combined_stream_text(self, session_id: str) -> Text:
        reasoning, reasoning_clipped = self._tail_text(
            self._stream_reasoning.get(session_id, []),
            self.STREAM_REASONING_WINDOW,
        )
        content, content_clipped = self._tail_text(
            self._stream_content.get(session_id, []),
            self.STREAM_CONTENT_WINDOW,
        )
        text = Text()
        if reasoning:
            if reasoning_clipped:
                text.append("… 较早的思考过程已暂时折叠 …\n", style="bright_black")
            text.append(f"[思考] {reasoning}\n", style="bright_black italic")
        if content_clipped:
            text.append("… 正在生成，仅显示末尾 …\n", style="bright_black")
        text.append(content)
        return text

    @staticmethod
    def _tail_text(chunks: list[str], limit: int) -> tuple[str, bool]:
        """Join at most ``limit`` trailing characters without joining full history."""
        if not chunks:
            return "", False
        selected: list[str] = []
        size = 0
        for chunk in reversed(chunks):
            selected.append(chunk)
            size += len(chunk)
            if size >= limit:
                break
        text = "".join(reversed(selected))
        clipped = len(selected) < len(chunks) or len(text) > limit
        return text[-limit:], clipped

    def end_stream(self, session_id: str) -> None:
        """结束流式消息：reasoning 单独成块，正文做 Markdown/代码块渲染。

        最终化的消息插回流式占位 widget 原来的位置，而不是追加到末尾——
        否则正文/思考过程会跳到流式期间产生的工具卡片之后。
        """
        self.ensure_session(session_id)
        widget = self._stream_widget.get(session_id)
        if widget is None:
            return
        reasoning = "".join(self._stream_reasoning.get(session_id, []))
        content = "".join(self._stream_content.get(session_id, []))
        if not content and not reasoning:
            return

        # 记录占位 widget 的位置，最终化消息插回原位
        order_idx = next(
            (i for i, (_, w) in enumerate(self._order) if w is widget), None
        )
        msg_list = self._messages.get(session_id, [])
        msg_idx = msg_list.index(widget) if widget in msg_list else None

        # 移除流式占位 widget
        if msg_idx is not None:
            msg_list.remove(widget)
        self._order = [(sid, w) for sid, w in self._order if w is not widget]
        if widget in self.children:
            widget.remove()
        self._stream_widget[session_id] = None
        self._stream_content[session_id] = []
        self._stream_reasoning[session_id] = []
        self._dirty_streams.discard(session_id)

        new_widgets: list = []
        if reasoning:
            new_widgets.append(
                Static(
                    Panel(
                        Text(reasoning, style="bright_black italic"),
                        title="思考过程",
                        border_style="bright_black",
                    )
                )
            )
        # 解析代码块并分别渲染
        if content:
            new_widgets.extend(self._build_message_widgets(content))

        # 原位插回 _messages / _order
        if msg_idx is not None:
            msg_list[msg_idx:msg_idx] = new_widgets
        else:
            msg_list.extend(new_widgets)
        if order_idx is not None:
            self._order[order_idx:order_idx] = [
                (session_id, w) for w in new_widgets
            ]
        else:
            self._order.extend((session_id, w) for w in new_widgets)

        # DOM：插到原位置之后第一个 widget 之前；没有则追加到末尾。
        # 所有 widget 始终挂载，可见性由 display 控制。
        anchor = None
        if order_idx is not None:
            following = self._order[order_idx + len(new_widgets):]
            if following:
                anchor = following[0][1]
        for w in new_widgets:
            w.display = self._is_visible(session_id)
            if anchor is not None:
                self.mount(w, before=anchor)
            else:
                self.mount(w)
        if self._is_visible(session_id):
            self._maybe_scroll_end()
        self._prune_widgets()

    def _build_message_widgets(self, content: str) -> list:
        """把内容拆分为文本/代码块，分别用 Markdown 或 CodeBlock 渲染。"""
        widgets: list[Static] = []
        stripped = content.strip()
        if stripped and stripped[0] in ("{", "["):
            rendered = format_tool_payload(stripped)
            if rendered != stripped:
                widgets.append(Static(Text(rendered)))
                return widgets
        if "```" not in content:
            if self._looks_like_markdown(content):
                widgets.append(Static(Markdown(content)))
            else:
                widgets.append(Static(Text(content)))
            return widgets

        parts = content.split("```")
        for i, part in enumerate(parts):
            if not part.strip():
                continue
            if i % 2 == 0:
                # 普通文本
                if self._looks_like_markdown(part):
                    widgets.append(Static(Markdown(part)))
                else:
                    widgets.append(Static(Text(part)))
            else:
                # 代码块：第一行是语言，剩余是代码
                lines = part.split("\n", 1)
                language = lines[0].strip() or "text"
                code = lines[1] if len(lines) > 1 else ""
                # 去掉末尾的 ``` 如果存在
                code = code.rstrip("`").rstrip()
                widgets.append(CodeBlock(code, language))
        return widgets

    def append_tool(
        self,
        session_id: str,
        tool: str,
        arguments: str,
        finished: bool = False,
        result: str | None = None,
    ) -> None:
        """追加工具调用卡片；长结果默认折叠，点击展开。"""
        self.ensure_session(session_id)
        arguments = _format_tool_payload(arguments)
        if result is not None:
            result = _format_tool_payload(result, is_result=True)
        body = f"{tool}({arguments})"
        collapsed_hint = None
        full_body = None
        if finished and result is not None:
            full_body = f"{body}\n\n{result}"
            lines = result.split("\n")
            if len(lines) > _TOOL_COLLAPSE_LINES:
                preview = "\n".join(lines[:_TOOL_COLLAPSE_LINES])
                body = f"{body}\n\n{preview}"
                collapsed_hint = f"… 共 {len(lines)} 行，点击展开/收起"
            else:
                body = full_body
                full_body = None
        if finished:
            # tool_started/tool_finished describe one operation. Updating the
            # latest matching card avoids doubling the DOM during long runs.
            for candidate in reversed(self._messages.get(session_id, [])):
                if (
                    isinstance(candidate, ToolCard)
                    and candidate._tool == tool
                    and not candidate._finished
                ):
                    candidate.finish(
                        body,
                        collapsed_hint=collapsed_hint,
                        full_body=full_body,
                    )
                    return
        widget = ToolCard(
            tool,
            body,
            finished,
            collapsed_hint=collapsed_hint,
            full_body=full_body,
        )
        self._add_widget(session_id, widget)

    def append_file_change(
        self,
        session_id: str,
        path: str,
        status: str,
        diff: str | None = None,
    ) -> None:
        """追加文件变更卡片。"""
        self.ensure_session(session_id)
        style = {
            "applied": "green",
            "proposed": "yellow",
            "declined": "dim",
            "failed": "red",
        }.get(status, "blue")
        icon = {
            "applied": "√",
            "proposed": "※",
            "declined": "○",
            "failed": "×",
        }.get(status, "•")
        body = diff or f"状态: {status}"
        widget = Static(Panel(body, title=f"{icon} {path}", border_style=style))
        self._add_widget(session_id, widget)

    def append_supervisor_review(self, session_id: str, conclusion: str, reason: str) -> None:
        """追加 Supervisor 审查结论。"""
        self.ensure_session(session_id)
        body = f"结论: {conclusion}\n理由: {reason}"
        widget = Static(Panel(body, title="Supervisor 审查", border_style="magenta"))
        self._add_widget(session_id, widget)

    def refresh_view(self) -> None:
        """按当前视图过滤器切换各消息的可见性（display，而非摘挂 DOM）。

        用 display 切换而不是 remove+mount：后者是异步的，同一批 widget
        先摘再挂会因为父节点尚未清理而静默丢失。
        """
        any_visible = False
        for sid, widget in self._order:
            visible = self._is_visible(sid)
            widget.display = visible
            any_visible = any_visible or visible
            if visible and widget is self._stream_widget.get(sid):
                widget.update(self._combined_stream_text(sid))
        if not self._order:
            self._show_welcome_if_empty()
        self.scroll_end(animate=False)

    def show_session(self, session_id: str | None) -> None:
        """切换到指定 session 视图；None 表示显示全部。"""
        if session_id is not None:
            self.ensure_session(session_id)
        self._view_session_id = session_id
        self._view_agent_prefix = None
        self.refresh_view()

    def show_agent(self, agent_id: str | None) -> None:
        """按 agent 过滤视图：只显示该 agent 的所有 session；None 显示全部。"""
        self._view_agent_prefix = agent_id
        self._view_session_id = None
        self.refresh_view()

    def rename_session(self, old_id: str, new_id: str) -> None:
        """把某 session 的消息整体改名（用于 pending → 真实 session_id）。"""
        if old_id == new_id or old_id not in self._messages:
            return
        self.ensure_session(new_id)
        self._messages[new_id] = self._messages.pop(old_id) + self._messages[new_id]
        self._order = [
            (new_id if sid == old_id else sid, w) for sid, w in self._order
        ]
        self._stream_widget[new_id] = self._stream_widget.pop(old_id, None)
        self._stream_content[new_id] = self._stream_content.pop(old_id, [])
        self._stream_reasoning[new_id] = self._stream_reasoning.pop(old_id, [])
        if self._view_session_id == old_id:
            self._view_session_id = new_id
            self.refresh_view()

    def clear_session(self, session_id: str) -> None:
        """清空某 session 的消息。"""
        self._messages.pop(session_id, None)
        self._order = [(sid, w) for sid, w in self._order if sid != session_id]
        self._stream_widget.pop(session_id, None)
        self._stream_content.pop(session_id, None)
        self._stream_reasoning.pop(session_id, None)
        self._user_message_widgets = {
            key: value
            for key, value in self._user_message_widgets.items()
            if value[0] != session_id
        }

    def clear_all(self) -> None:
        """清空所有 session 的消息（切换对话时用）。"""
        self._messages.clear()
        self._order.clear()
        self._stream_widget.clear()
        self._stream_content.clear()
        self._stream_reasoning.clear()
        self._dirty_streams.clear()
        self._user_message_widgets.clear()
        self._view_session_id = None
        self._view_agent_prefix = None
        self.remove_children()
        self._show_welcome_if_empty()

    def _add_widget(self, session_id: str, widget) -> None:
        self._messages[session_id].append(widget)
        self._order.append((session_id, widget))
        self._remove_welcome()
        widget.display = self._is_visible(session_id)
        self.mount(widget)
        self._prune_widgets()
        if widget.display:
            self._maybe_scroll_end()

    def _prune_widgets(self) -> None:
        """Keep Textual's live DOM bounded during long multi-Agent runs."""
        while len(self._order) > self.MAX_WIDGETS:
            remove_idx = next(
                (
                    index
                    for index, (sid, candidate) in enumerate(self._order)
                    if candidate is not self._stream_widget.get(sid)
                ),
                None,
            )
            if remove_idx is None:
                return
            sid, candidate = self._order.pop(remove_idx)
            messages = self._messages.get(sid, [])
            if candidate in messages:
                messages.remove(candidate)
            self._user_message_widgets = {
                key: value
                for key, value in self._user_message_widgets.items()
                if value[1] is not candidate
            }
            if candidate in self.children:
                candidate.remove()

    def _maybe_scroll_end(self) -> None:
        """用户已上翻时不追尾；连续更新只安排一次滚动。"""
        try:
            should_follow = self.scroll_y >= self.max_scroll_y - 2
        except Exception:
            should_follow = True
        if not should_follow or self._scroll_scheduled:
            return
        self._scroll_scheduled = True

        def scroll_once() -> None:
            self._scroll_scheduled = False
            self.scroll_end(animate=False)

        self.set_timer(self.SCROLL_FLUSH_INTERVAL, scroll_once)

    def _show_welcome_if_empty(self) -> None:
        if self._order:
            return
        if self.query("#welcome"):
            return
        self.mount(Static(_WELCOME_TEXT, id="welcome"))

    def _remove_welcome(self) -> None:
        for widget in self.query("#welcome"):
            widget.remove()

    @staticmethod
    def _looks_like_markdown(text: str) -> bool:
        """轻量 Markdown 探测。"""
        markers = ["#", "```", "- ", "* ", "> ", "| ", "[", "**", "__"]
        return any(marker in text for marker in markers)
