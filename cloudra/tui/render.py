"""TUI 事件渲染器：订阅 IPC 事件总线，把 Agent 运行过程渲染到终端。

替代旧的 Log 终端 print（TUI 模式下由 ``Log.terminal_output = False`` 关闭），
消费的事件与 Web/API 前端一致：session_event（llm_chunk/tool_*/phase/...）、
session_state、approval_pending。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from rich.console import Console
from rich.panel import Panel

from cloudra import session_store
from cloudra.database import ConversationDB
from cloudra.events import subscribe_async

if TYPE_CHECKING:
    from cloudra.tui.app import CloudraTUI

_TERMINAL_STATES = {"completed", "failed", "cancelled", "interrupted", "killed"}


def _truncate(text: str, limit: int) -> str:
    text = (text or "").strip()
    return text if len(text) <= limit else text[:limit] + " …"


class EventRenderer:
    """消费一个 conversation 的事件队列并渲染；渲染异常绝不上抛。"""

    def __init__(self, console: Console, app: "CloudraTUI") -> None:
        self.console = console
        self.app = app
        self._stream_agent: str | None = None  # 当前正在流式输出的 agent

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

    def _end_stream_line(self) -> None:
        if self._stream_agent is not None:
            self.console.print()
            self._stream_agent = None

    def _on_llm_chunk(self, session_id: str, data: dict) -> None:
        agent = data.get("agent_name") or "agent"
        delta = data.get("delta") or ""
        if not delta:
            return
        if agent != self._stream_agent:
            self._end_stream_line()
            self.console.print(f"\n[bold cyan]● {agent}[/bold cyan]")
            self._stream_agent = agent
        if data.get("stream") == "reasoning":
            self.console.print(delta, end="", style="dim italic", markup=False, highlight=False)
        else:
            self.console.print(delta, end="", markup=False, highlight=False)

    def _on_llm_stream_end(self, session_id: str, data: dict) -> None:
        self._end_stream_line()

    def _on_tool_started(self, session_id: str, data: dict) -> None:
        self._end_stream_line()
        tool = data.get("tool", "?")
        args = _truncate(data.get("arguments", ""), 120)
        suffix = f" [dim]{args}[/dim]" if args else ""
        self.console.print(f"[cyan]▸ {tool}[/cyan]{suffix}")

    def _on_tool_finished(self, session_id: str, data: dict) -> None:
        self._end_stream_line()
        tool = data.get("tool", "?")
        result = _truncate(data.get("result", ""), 300)
        self.console.print(f"[green]✓ {tool}[/green]")
        if result:
            for line in result.splitlines()[:6]:
                self.console.print(f"  {line}", style="dim", markup=False, highlight=False)

    def _on_phase(self, session_id: str, data: dict) -> None:
        self.app.phase = data.get("phase", "")
        self.app.invalidate()

    def _on_supervisor_review(self, session_id: str, data: dict) -> None:
        self._end_stream_line()
        verdict = data.get("verdict", "")
        reasoning = _truncate(data.get("reasoning", ""), 400)
        self.console.print(Panel(
            f"[bold]{verdict}[/bold]\n{reasoning}",
            title="[bold yellow]Supervisor[/bold yellow]",
            border_style="yellow",
            padding=(0, 1),
        ))

    # ---- 顶层事件 ----

    def _on_session_state(self, session_id: str, state: str) -> None:
        if session_id != self.app.session_id:
            return
        if state == "cancel_requested":
            self._end_stream_line()
            self.console.print("[yellow]⏹ 正在打断任务…（再按一次 Esc 强制终止）[/yellow]")
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
            f"来自: [bold]{agent_name}[/bold]\n[bold yellow]{details}[/bold yellow]\n\n"
            "输入 [bold green]y[/bold green] 允许，[bold red]n[/bold red] 拒绝（可用 n:原因 说明）",
            title="[bold red]安全审批请求[/bold red]",
            border_style="red",
        ))
        self.app.invalidate()
