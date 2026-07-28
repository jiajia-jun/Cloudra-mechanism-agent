"""TUI 事件渲染器：订阅 IPC 事件总线，把 Agent 运行过程渲染到终端。

替代旧的 Log 终端 print（TUI 模式下由 ``Log.terminal_output = False`` 关闭），
消费的事件与 Web/API 前端一致：session_event（llm_chunk/tool_*/phase/...）、
session_state、approval_pending。

字形约定：只用 CJK 等宽字体普遍覆盖的符号（» ● ○ ▶ √ × ※ ─），
避免用户终端字体缺字时出现豆腐块。
"""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING

from rich.console import Console
from rich.markup import escape
from rich.panel import Panel

from cloudra import session_store
from cloudra.database import ConversationDB
from cloudra.events import subscribe_async

if TYPE_CHECKING:
    from cloudra.tui.app import CloudraTUI

_TERMINAL_STATES = {"completed", "failed", "cancelled", "interrupted", "killed"}

_ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[a-zA-Z]")
# 兜底：ESC 字节已被 prompt_toolkit 的 patch_stdout 或 ANSI parser 吃掉，
# 残留下的裸 [XXm / [XX;XXm 这样的颜色码片段。
_BARE_ANSI_FRAG_RE = re.compile(r"(?<!\x1b)\[[0-9][0-9;]*[a-zA-Z]")


def _strip_ansi(text: str) -> str:
    """剥离嵌入文本的 ANSI 转义序列（含 ESC 丢失后的裸 [XXm 残片）。"""
    text = _ANSI_RE.sub("", text)
    text = _BARE_ANSI_FRAG_RE.sub("", text)
    return text


def _truncate(text: str, limit: int) -> str:
    text = (text or "").strip()
    return text if len(text) <= limit else text[:limit] + " …"


def _format_args(raw: str) -> str:
    """工具参数：JSON 字符串转成 `key: value` 形式，解析失败回退原文。"""
    raw = _strip_ansi((raw or "").strip())
    if not raw:
        return ""
    try:
        data = json.loads(raw)
    except Exception:
        return _truncate(raw, 100)
    if isinstance(data, dict):
        parts = [f"{k}: {_truncate(str(v), 60)}" for k, v in data.items()]
        return _truncate(", ".join(parts), 100)
    return _truncate(str(data), 100)


def _format_result_lines(raw: str, max_lines: int = 4) -> list[str]:
    """工具结果：尝试 JSON 解析以解码 \\uXXXX 转义并按键展开，否则原样截断。"""
    raw = (raw or "").strip()
    if not raw:
        return []
    text = raw
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            lines = []
            for k, v in data.items():
                # 值本身可能还是一段 JSON（二次编码），尽量再解一层
                if isinstance(v, str) and v[:1] in "{[":
                    try:
                        v = json.dumps(json.loads(v), ensure_ascii=False)
                    except Exception:
                        pass
                lines.append(f"{k}: {v}")
            text = "\n".join(lines)
        else:
            text = json.dumps(data, ensure_ascii=False)
    except Exception:
        pass
    return [_truncate(_strip_ansi(line), 100) for line in text.splitlines()[:max_lines]]


def _diff_preview_lines(diff: str, max_lines: int = 160) -> tuple[list[str], bool]:
    lines = (diff or "").splitlines()
    return lines[:max_lines], len(lines) > max_lines


class EventRenderer:
    """消费一个 conversation 的事件队列并渲染；渲染异常绝不上抛。"""

    def __init__(self, console: Console, app: "CloudraTUI") -> None:
        self.console = console
        self.app = app
        self._stream_agent: str | None = None  # 当前正在流式输出的 agent
        self._stream_buf: str = ""             # 未凑满一行的流式文本
        self._stream_style: str | None = None  # 缓冲文本对应的样式

    # 流式文本按行缓冲再渲染：run_in_terminal 重绘会抹掉未换行的文本，
    # 因此只有凑满一行（或流结束）才输出，牺牲少量实时性换取稳定渲染。
    _STREAM_FLUSH_WIDTH = 88

    async def run(self, conversation_id: str) -> None:
        queue = await subscribe_async(
            conversation_id,
            ("session_event", "session_state", "approval_pending"),
        )
        while True:
            msg = await queue.get()
            try:
                self.dispatch(msg)
            except Exception:
                # 渲染是可丢弃的：任何样式/数据异常都不能影响 Agent 主流程
                continue

    def dispatch(self, msg: dict) -> None:
        kind = msg.get("kind")
        if kind == "session_event":
            handler = getattr(self, f"_on_{msg.get('event_type') or ''}", None)
            if handler is not None:
                handler(msg.get("session_id", ""), msg.get("data") or {})
        elif kind == "session_state":
            self._on_session_state(msg.get("session_id", ""), msg.get("state", ""))
        elif kind == "approval_pending":
            self._on_approval_pending(msg)

    # ---- session_event 子类型 ----

    def _flush_stream(self) -> None:
        """把缓冲的流式文本作为完整行输出。"""
        if self._stream_buf:
            self.console.print(
                _strip_ansi(self._stream_buf), style=self._stream_style, markup=False, highlight=False,
            )
            self._stream_buf = ""

    def _end_stream_line(self) -> None:
        if self._stream_agent is not None:
            self._flush_stream()
            self._stream_agent = None

    def _print_stream(self, text: str, style: str | None) -> None:
        if style != self._stream_style:
            self._flush_stream()
            self._stream_style = style
        self._stream_buf += text
        while "\n" in self._stream_buf:
            line, self._stream_buf = self._stream_buf.split("\n", 1)
            self.console.print(_strip_ansi(line), style=style, markup=False, highlight=False)
        if len(self._stream_buf) >= self._STREAM_FLUSH_WIDTH:
            self._flush_stream()

    def _on_llm_chunk(self, session_id: str, data: dict) -> None:
        agent = data.get("agent_name") or "agent"
        delta = data.get("delta") or ""
        if not delta:
            return
        if agent != self._stream_agent:
            self._end_stream_line()
            self.console.print(f"\n[bold green]● {escape(agent)}[/bold green]")
            self._stream_agent = agent
        if data.get("stream") == "reasoning":
            # prompt_toolkit 不支持 SGR dim，用亮黑色表达"暗化"
            self._print_stream(delta, "bright_black italic")
        else:
            self._print_stream(delta, None)

    def _on_llm_stream_end(self, session_id: str, data: dict) -> None:
        self._end_stream_line()

    def _on_tool_started(self, session_id: str, data: dict) -> None:
        self._end_stream_line()
        tool = data.get("tool", "?")
        args = _format_args(data.get("arguments", ""))
        suffix = f" [bright_black]{escape(_strip_ansi(args))}[/bright_black]" if args else ""
        self.console.print(f"[yellow]▶ [bold]{escape(_strip_ansi(tool))}[/bold][/yellow]{suffix}")

    def _on_tool_finished(self, session_id: str, data: dict) -> None:
        self._end_stream_line()
        tool = data.get("tool", "?")
        self.console.print(f"[green]√ {tool}[/green]")
        for line in _format_result_lines(data.get("result", "")):
            self.console.print(f"  {_strip_ansi(line)}", style="bright_black", markup=False, highlight=False)

    def _print_diff(self, diff: str) -> None:
        lines, truncated = _diff_preview_lines(diff)
        for line in lines:
            if line.startswith(("+++", "---")):
                style = "bold"
            elif line.startswith("+"):
                style = "green"
            elif line.startswith("-"):
                style = "red"
            elif line.startswith("@@"):
                style = "cyan"
            else:
                style = "bright_black"
            self.console.print(line, style=style, markup=False, highlight=False)
        if truncated:
            self.console.print("… 终端预览已截断，完整 diff 已保存在 Session 事件中", style="dim")

    def _on_file_change_proposed(self, session_id: str, data: dict) -> None:
        self._end_stream_line()
        path = escape(str(data.get("path", "?")))
        additions = data.get("additions", 0)
        deletions = data.get("deletions", 0)
        self.console.print(
            f"[yellow]※ 候选文件变更 [bold]{path}[/bold] "
            f"[green]+{additions}[/green] [red]-{deletions}[/red][/yellow]"
        )

    def _on_file_change_applied(self, session_id: str, data: dict) -> None:
        self._end_stream_line()
        path = escape(str(data.get("path", "?")))
        additions = data.get("additions", 0)
        deletions = data.get("deletions", 0)
        self.console.print(
            f"[green]√ 已写入 [bold]{path}[/bold] +{additions}[/green] "
            f"[red]-{deletions}[/red]"
        )

    def _on_file_change_declined(self, session_id: str, data: dict) -> None:
        self._end_stream_line()
        path = escape(str(data.get("path", "?")))
        message = escape(_truncate(str(data.get("message", "")), 200))
        self.console.print(f"[yellow]○ 已拒绝文件变更 {path}: {message}[/yellow]")

    def _on_file_change_failed(self, session_id: str, data: dict) -> None:
        self._end_stream_line()
        path = escape(str(data.get("path", "?")))
        message = escape(_truncate(str(data.get("message", "")), 200))
        self.console.print(f"[red]× 文件变更失败 {path}: {message}[/red]")

    def _on_turn_diff_updated(self, session_id: str, data: dict) -> None:
        self._end_stream_line()
        diff = data.get("diff", "")
        if not diff:
            return
        self.console.print("[bold cyan]本轮文件差异[/bold cyan]")
        self._print_diff(diff)

    def _on_phase(self, session_id: str, data: dict) -> None:
        self.app.phase = data.get("phase", "")
        self.app.invalidate()

    def _on_supervisor_review(self, session_id: str, data: dict) -> None:
        self._end_stream_line()
        verdict = escape(_strip_ansi(data.get("verdict", "")))
        reasoning = escape(_strip_ansi(_truncate(data.get("reasoning", ""), 400)))
        self.console.print(Panel(
            f"[bold]{verdict}[/bold]\n{reasoning}",
            title="[bold yellow]◆ Supervisor[/bold yellow]",
            title_align="left",
            border_style="yellow",
            padding=(0, 1),
        ))

    # ---- 顶层事件 ----

    def _on_session_state(self, session_id: str, state: str) -> None:
        if session_id != self.app.session_id:
            return
        if state == "cancel_requested":
            self._end_stream_line()
            self.console.print("[yellow]■ 正在打断任务…（再按一次 Esc 强制终止）[/yellow]")
        elif state in _TERMINAL_STATES:
            self._end_stream_line()
        self.app.invalidate()

    def _on_approval_pending(self, msg: dict) -> None:
        self._end_stream_line()
        approval_id = msg.get("approval_id")
        agent_name = msg.get("agent_name") or "agent"
        details = ""
        try:
            db = ConversationDB(self.app.conversation_id)
            for req_id, _sid, _name, req_details in session_store.list_pending_approvals(db):
                if req_id == approval_id:
                    details = req_details
                    break
        except Exception:
            pass
        self.app.pending_approval = {"id": approval_id, "agent_name": agent_name, "details": details}
        self.console.print(Panel(
            f"[bold]{escape(_strip_ansi(details))}[/bold]\n"
            f"[dim]来自 {escape(_strip_ansi(agent_name))} · 输入 y 允许，n 拒绝（可 n:原因）[/dim]",
            title="[bold yellow]※ 安全审批[/bold yellow]",
            title_align="left",
            border_style="yellow",
            padding=(0, 1),
        ))
        self.app.invalidate()
