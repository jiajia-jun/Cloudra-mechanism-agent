"""Cloudra 交互式 TUI：prompt_toolkit 底部输入框 + 事件驱动渲染。

设计要点：
- 输入框常驻底部（运行中也保持激活），用户随时可打字：空闲时提交新任务，
  运行中则作为补充信息注入 Agent 上下文（ContextManager.inject_event）。
- Esc 中途打断：第一次置 cancel_requested（Agent 优雅退出），3 秒内再按强制取消协程。
- 审批（approval_pending）与 ask_user 提问统一收口到同一个输入框，
  不再使用裸 input()，避免与 prompt_toolkit 争抢 stdin。
- 输出渲染全部来自 IPC 事件（见 render.py）；Log 的终端 print 在 TUI 期间关闭。
"""

from __future__ import annotations

import asyncio
import contextlib
import re
import time
from datetime import datetime

from prompt_toolkit import PromptSession
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.patch_stdout import patch_stdout
from prompt_toolkit.styles import Style
from rich.console import Console
from rich.panel import Panel

from cloudra import __version__, session_store
from cloudra.context_manager import ContextManager
from cloudra.database import ConversationDB
from cloudra.events import shutdown_all_listeners
from cloudra.log_class import Log
from cloudra.react import AgentCancelled
from cloudra.service import CloudraService
from cloudra.tools.Interactool import ask_user
from cloudra.tui.render import EventRenderer

_COORDINATOR_AGENT_ID = "a-0"  # 与 email_listener 的注入先例一致
_FORCE_CANCEL_WINDOW = 3.0     # 第一次 Esc 后，该时间窗内再按即强制取消


class CloudraTUI:
    """Cloudra 终端交互界面主类。"""

    def __init__(self) -> None:
        self.console = Console()
        self.service = CloudraService()
        self.conversation_id: str = ""
        self.session_id: str | None = None
        self.phase: str = ""
        self.pending_approval: dict | None = None
        self._pending_questions: list[asyncio.Future] = []
        self._running_task: asyncio.Task | None = None
        self._renderer_task: asyncio.Task | None = None
        self._cancel_at: float | None = None
        self._prompt: PromptSession | None = None

    # ---- 生命周期 ----

    def run(self) -> None:
        asyncio.run(self._run_async())

    async def _run_async(self) -> None:
        Log.terminal_output = False
        ask_user.set_input_handler(self._ask_user_handler)
        try:
            with patch_stdout():
                self._new_conversation()
                self._print_banner()
                self._prompt = self._build_prompt_session()
                await self._input_loop()
        finally:
            ask_user.set_input_handler(None)
            Log.terminal_output = True
            await self._shutdown()

    async def _shutdown(self) -> None:
        task = self._running_task
        if task is not None and not task.done():
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task
        if self._renderer_task is not None:
            self._renderer_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._renderer_task
        with contextlib.suppress(Exception):
            shutdown_all_listeners()

    def _new_conversation(self) -> None:
        conversation = self.service.create_conversation()
        self.conversation_id = conversation.id
        if self._renderer_task is not None:
            self._renderer_task.cancel()
        renderer = EventRenderer(self.console, self)
        self._renderer_task = asyncio.create_task(renderer.run(self.conversation_id))

    # ---- 界面 ----

    def _print_banner(self) -> None:
        self.console.print(Panel.fit(
            "[bold cyan]Cloudra[/bold cyan] AI 化学科研助手\n"
            f"[dim]v{__version__} · 对话 {self.conversation_id}[/dim]\n\n"
            "输入任务回车执行 · 运行中可直接输入补充信息\n"
            "[dim]Esc 打断 · Ctrl+C 退出 · /new 新对话 · exit 退出[/dim]",
            border_style="cyan",
        ))

    def _toolbar(self) -> HTML:
        if self.pending_approval is not None:
            left = " ⚠ 待审批：y 允许 / n 拒绝（可 n:原因） "
        elif self._pending_questions:
            left = " ✎ 请回答上方 Agent 的提问 "
        elif self._running():
            phase = f" · {self.phase}" if self.phase else ""
            left = f" ● 运行中{phase} — Esc 打断，可直接输入补充 "
        else:
            left = " ○ 空闲 — 输入任务开始 · /new 新对话 · exit 退出 "
        return HTML(f"<style bg='ansiblack' fg='ansicyan'>{left}</style>")

    def _build_prompt_session(self, **kwargs) -> PromptSession:
        kb = KeyBindings()

        @kb.add("escape")
        def _on_escape(event) -> None:
            if not self.request_cancel():
                event.app.current_buffer.reset()

        @kb.add("c-c")
        def _on_ctrl_c(event) -> None:
            if not self.request_cancel():
                event.app.exit(exception=KeyboardInterrupt())

        return PromptSession(
            message=HTML("<prompt>❯ </prompt>"),
            key_bindings=kb,
            style=Style.from_dict({"prompt": "ansicyan bold"}),
            bottom_toolbar=self._toolbar,
            multiline=False,
            **kwargs,
        )

    def invalidate(self) -> None:
        """刷新底部 toolbar（事件到达时由渲染器调用）。"""
        with contextlib.suppress(Exception):
            if self._prompt is not None:
                self._prompt.app.invalidate()

    # ---- 输入主循环与分派 ----

    async def _input_loop(self) -> None:
        while True:
            try:
                text = await self._prompt.prompt_async()
            except (KeyboardInterrupt, EOFError):
                break
            text = text.strip()
            if not text:
                continue
            if text.lower() in ("exit", "quit"):
                break
            if text == "/new":
                if self._running():
                    self.console.print("[yellow]任务运行中，请先 Esc 打断再开新对话。[/yellow]")
                    continue
                self._new_conversation()
                self.console.print(f"[green]已开启新对话: {self.conversation_id}[/green]")
                continue
            await self._dispatch(text)

    async def _dispatch(self, text: str) -> None:
        if self.pending_approval is not None:
            await self._resolve_approval(text)
        elif self._pending_questions:
            future = self._pending_questions.pop(0)
            if not future.done():
                future.set_result(text)
        elif self._running():
            await ContextManager.inject_event(
                self.conversation_id, _COORDINATOR_AGENT_ID, "user", text,
            )
            self.console.print(f"[dim]↪ 已补充给 Agent（下一轮推理生效）: {text}[/dim]")
        else:
            self._start_task(text)

    def _running(self) -> bool:
        return self._running_task is not None and not self._running_task.done()

    # ---- 任务执行 ----

    def _start_task(self, query: str) -> None:
        self.session_id = f"{_COORDINATOR_AGENT_ID}_{datetime.now().isoformat()}"
        self._cancel_at = None
        self.phase = "starting"
        task = asyncio.create_task(self.service.run_task(
            query,
            conversation_id=self.conversation_id,
            session_id=self.session_id,
            verbose=False,
            interactive_approval=False,
        ))
        task.add_done_callback(self._on_task_done)
        self._running_task = task

    def _on_task_done(self, task: asyncio.Task) -> None:
        self._running_task = None
        self._cancel_at = None
        self.phase = ""
        for future in self._pending_questions:
            if not future.done():
                future.cancel()
        self._pending_questions.clear()
        self.pending_approval = None
        if task.cancelled():
            self.console.print("[yellow]⏹ 任务已强制终止。[/yellow]")
        elif (exc := task.exception()) is not None:
            if isinstance(exc, AgentCancelled):
                self.console.print("[yellow]⏹ 任务已打断。[/yellow]")
            else:
                self.console.print(f"[red]✗ 任务失败: {exc}[/red]")
        else:
            self.console.print("[green]✓ 任务完成。[/green]")
        self.invalidate()

    # ---- 打断 ----

    def request_cancel(self) -> bool:
        """Esc/Ctrl+C 入口：运行中请求打断；返回 False 表示当前空闲。"""
        task = self._running_task
        if task is None or task.done():
            return False
        now = time.monotonic()
        if self._cancel_at is not None and now - self._cancel_at < _FORCE_CANCEL_WINDOW:
            task.cancel()  # 时间窗内再次按下：强制取消协程
            return True
        self._cancel_at = now
        try:
            db = ConversationDB(self.conversation_id)
            # 置 cancel_requested 即会经 IPC 广播，reAct 每个循环/chunk 都会检查
            session_store.update_session_fields(db, self.session_id, {"state": "cancel_requested"})
            # 级联打断子 Agent / 计算任务（复用 SessionRunner 的实现）
            self.service.session_runner._cancel_descendants(self.conversation_id, self.session_id)
        except Exception:
            task.cancel()
        return True

    # ---- 审批与提问 ----

    async def _resolve_approval(self, text: str) -> None:
        approval = self.pending_approval
        decision, reason = None, ""
        low = text.strip().lower()
        if low in ("y", "yes"):
            decision = "approved"
        elif low in ("n", "no"):
            decision = "denied"
        else:
            match = re.match(r"^(?:n|no|拒绝|reject)\s*[:：]\s*(.+)$", text.strip(), re.IGNORECASE)
            if match:
                decision, reason = "denied", match.group(1).strip()
        if decision is None:
            self.console.print("[yellow]请输入 y（允许）或 n（拒绝，可用 n:原因 说明）。[/yellow]")
            return
        ok = await self.service.decide_approval(
            self.conversation_id, approval["id"], decision, reason,
        )
        if ok:
            msg = "[green]已允许执行。[/green]" if decision == "approved" else "[yellow]已拒绝。[/yellow]"
            self.console.print(msg)
        else:
            self.console.print("[dim]该审批已在其他端处理，本次输入忽略。[/dim]")
        self.pending_approval = None
        self.invalidate()

    async def _ask_user_handler(self, prompt_text: str) -> str:
        """ask_user 工具的输入处理器：展示问题并挂起，等待主输入框的答案。"""
        future = asyncio.get_running_loop().create_future()
        self._pending_questions.append(future)
        self.console.print(Panel(
            prompt_text,
            title="[bold yellow]Agent 提问[/bold yellow]",
            border_style="yellow",
            padding=(0, 1),
        ))
        self.invalidate()
        return await future


def run_tui() -> None:
    """TUI 入口（由 cli._interactive_tui 调用）。"""
    CloudraTUI().run()
