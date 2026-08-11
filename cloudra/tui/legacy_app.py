"""Cloudra 交互式 TUI：prompt_toolkit 底部输入框 + 事件驱动渲染。

设计要点：
- 输入框常驻底部（运行中也保持激活），用户随时可打字：空闲时提交新任务，
  运行中则作为补充信息注入 Agent 上下文（ContextManager.inject_event）。
- Esc 中途打断：推理中第一次请求优雅退出、3 秒内再按强制取消；等待提醒时
  一次即可结束当前等待，独立 watcher 会保留并继续触发 reminder。
- 审批（approval_pending）与 ask_user 提问统一收口到同一个输入框，
  不再使用裸 input()，避免与 prompt_toolkit 争抢 stdin。
- 输出渲染全部来自 IPC 事件（见 render.py）；Log 的终端 print 在 TUI 期间关闭。
- 启动时自动恢复上次对话（/new 新建 · /conv <id> 切换 · /list 查看列表）。
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
from rich.markup import escape
from rich.panel import Panel

from cloudra import __version__
from cloudra.base.conversation_class import Conversation
from cloudra.base.log_class import Log
from cloudra.core.react import AgentCancelled
from cloudra.infra.config import get_config
from cloudra.infra.events import shutdown_all_listeners, subscribe_async
from cloudra.persistence.context_manager import ContextManager
from cloudra.persistence.conversation_repo import list_conversations
from cloudra.persistence.database import ConversationDB
from cloudra.services import session_store
from cloudra.services.service import CloudraService
from cloudra.tools.Interactool import ask_user
from cloudra.tui.render import EventRenderer, _strip_ansi

_COORDINATOR_AGENT_ID = "a-0"  # 与 email_listener 的注入先例一致
_FORCE_CANCEL_WINDOW = 3.0     # 第一次 Esc 后，该时间窗内再按即强制取消


class CloudraTUI:
    """Cloudra 终端交互界面主类。"""

    def __init__(self, yolo: bool = False) -> None:
        # rich 输出经 PromptToolkitWriter 走 prompt_toolkit 渲染管线：
        # patch_stdout 会把 ESC 转义成 '?'，直接写会丢全部颜色
        import shutil

        from cloudra.tui.pt_writer import PromptToolkitWriter

        self.console = Console(
            file=PromptToolkitWriter(),
            force_terminal=True,
            width=shutil.get_terminal_size((100, 24)).columns,
        )
        self.service = CloudraService()
        self.conversation_id: str = ""
        self.session_id: str | None = None
        self.phase: str = ""
        self._pending_approvals: list[dict] = []
        self._pending_questions: list[asyncio.Future] = []
        self._running_task: asyncio.Task | None = None
        self._renderer_task: asyncio.Task | None = None
        self._schedule_task: asyncio.Task | None = None
        self._cancel_at: float | None = None
        self._cancelled_waiting_tasks: set[asyncio.Task] = set()
        self._prompt: PromptSession | None = None
        self.yolo = yolo

    # ---- 生命周期 ----

    def run(self) -> None:
        asyncio.run(self._run_async())

    async def _run_async(self) -> None:
        Log.terminal_output = False
        ask_user.set_input_handler(self._ask_user_handler)
        try:
            with patch_stdout():
                self._startup_conversation()
                self._print_banner()
                self._prompt = self._build_prompt_session()
                await self._input_loop()
        finally:
            ask_user.set_input_handler(None)
            Log.terminal_output = True
            await self._shutdown()

    async def _shutdown(self) -> None:
        if self._schedule_task is not None:
            self._schedule_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._schedule_task
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

    def _startup_conversation(self) -> None:
        config = get_config()
        if config.last_conversation_id:
            try:
                self._load_conversation(config.last_conversation_id)
                return
            except Exception:
                pass
        self._new_conversation()

    def _new_conversation(self) -> None:
        conversation = self.service.create_conversation()
        self._activate_conversation(conversation.id)

    def _load_conversation(self, conv_id: str) -> None:
        Conversation(conv_id)
        self._activate_conversation(conv_id)

    def _activate_conversation(self, conv_id: str) -> None:
        self.conversation_id = conv_id
        if self._renderer_task is not None:
            self._renderer_task.cancel()
        if self._schedule_task is not None:
            self._schedule_task.cancel()
        renderer = EventRenderer(self.console, self)
        self._renderer_task = asyncio.create_task(renderer.run(self.conversation_id))
        self._schedule_task = asyncio.create_task(self._watch_schedules(self.conversation_id))
        self.session_id = None
        self.phase = ""
        self._pending_approvals.clear()
        self._pending_questions.clear()

    # ---- 界面 ----

    _PHASE_LABELS = {
        "starting": "启动中",
        "thinking": "思考中",
        "acting": "执行中",
        "waiting": "等待提醒",
    }

    def _print_banner(self) -> None:
        self.console.print(Panel(
            "[bold green]Cloudra[/bold green]  [dim]AI 化学科研助手"
            f" · v{__version__} · 对话 {self.conversation_id}[/dim]\n\n"
            "输入任务回车执行 · 运行中可直接输入补充信息\n"
            f"[dim]当前模式: {'YOLO' if self.yolo else '审批'} · "
            "Esc 打断 · Ctrl+C 退出 · /yolo on|off · /compact · /new · /list · /conv <id> · exit[/dim]",
            border_style="green",
            padding=(0, 2),
        ))

    def _toolbar(self):
        from prompt_toolkit.formatted_text import FormattedText

        if self._pending_approvals:
            count = len(self._pending_approvals)
            queue_hint = f"（还有 {count - 1} 个待审批）" if count > 1 else ""
            dot, dot_style, text = "※", "fg:ansired", f"待审批 — y 允许 · n 拒绝（可 n:原因）{queue_hint}"
        elif self._pending_questions:
            dot, dot_style, text = "?", "fg:ansiyellow", "请回答上方 Agent 的提问"
        elif self._running():
            label = self._PHASE_LABELS.get(self.phase, "运行中")
            dot, dot_style, text = "●", "fg:ansigreen", f"{label} — Esc 打断 · 可直接输入补充"
            if self.phase == "waiting":
                text = f"{label} — 输入可立即唤醒 · Esc 结束等待（提醒保留）"
        else:
            dot, dot_style, text = "○", "fg:ansigreen", "空闲 — 输入任务开始 · /new /list /conv /compact · exit 退出"
        mode = "YOLO" if self.yolo else "审批"
        right = f"cloudra · {mode} · {self.conversation_id}"
        # prompt_toolkit 会裁剪片段尾部空格，因此把 padding 放在左右两段之间
        try:
            from prompt_toolkit.application import get_app_or_none
            from prompt_toolkit.utils import get_cwidth
            app = get_app_or_none()
            width = app.output.get_size().columns if app else 100
            pad = max(1, width - get_cwidth(f" {dot} {text} {right} "))
        except Exception:
            pad = 4
        return FormattedText([
            ("class:bottom-toolbar", " "),
            (f"class:bottom-toolbar {dot_style}", dot),
            ("class:bottom-toolbar", f" {text}" + " " * pad + right + " "),
        ])

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
            message=HTML("<prompt>» </prompt>"),
            key_bindings=kb,
            style=Style.from_dict({
                "prompt": "ansigreen bold",
                "bottom-toolbar": "bg:ansibrightblack ansiwhite",
            }),
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
            if text == "/list":
                self._cmd_list()
                continue
            if text == "/yolo" or text.startswith("/yolo "):
                self._cmd_yolo(text[5:].strip())
                continue
            if text.startswith("/conv "):
                self._cmd_conv(text[6:].strip())
                continue
            if text in ("/compact", "/compress") or text.startswith("/compact ") or text.startswith("/compress "):
                value = text.split(" ", 1)[1].strip() if " " in text else ""
                await self._cmd_compact(value)
                continue
            await self._dispatch(text)

    def _cmd_list(self) -> None:
        convs = list_conversations()
        if not convs:
            self.console.print("[yellow]暂无历史对话。[/yellow]")
            return
        self.console.print(f"\n[bold]历史对话列表 (共 {len(convs)} 个):[/bold]")
        for conv in convs[:20]:
            cid = conv.get("id", "?")
            state = conv.get("state", "?")
            last = (conv.get("last_active", "") or "")[:19]
            marker = " [dim]← 当前[/dim]" if cid == self.conversation_id else ""
            self.console.print(f"  [cyan]{cid}[/cyan]{marker}  {state}  {last}")
        if len(convs) > 20:
            self.console.print(f"  [dim]... 还有 {len(convs) - 20} 条，使用 /conv <id> 切换[/dim]")

    def _cmd_conv(self, conv_id: str) -> None:
        if not conv_id:
            self.console.print("[yellow]用法: /conv <对话ID>  示例: /conv conv_20250101_120000_abc123[/yellow]")
            return
        if self._running():
            self.console.print("[yellow]任务运行中，请先 Esc 打断再切换对话。[/yellow]")
            return
        convs = list_conversations()
        matched = [c for c in convs if c.get("id", "").startswith(conv_id)]
        if len(matched) == 1:
            try:
                self._load_conversation(matched[0]["id"])
                self.console.print(f"[green]已切换到对话: {self.conversation_id}[/green]")
            except Exception as e:
                self.console.print(f"[red]无法加载对话 {matched[0]['id']}: {e}[/red]")
        elif len(matched) > 1:
            self.console.print("[yellow]多个匹配的对话，请输入更完整的 ID:[/yellow]")
            for c in matched:
                self.console.print(f"  [cyan]{c['id']}[/cyan]")
        else:
            self.console.print(f"[yellow]未找到对话: {conv_id}，使用 /list 查看所有对话。[/yellow]")

    def _cmd_yolo(self, value: str) -> None:
        """查看或切换后续 Session 的 YOLO 自动审批模式。"""
        normalized = value.lower()
        if not normalized or normalized == "status":
            state = "已开启" if self.yolo else "未开启"
            self.console.print(f"[yellow]YOLO 模式{state}。[/yellow]")
            return
        if normalized not in ("on", "off"):
            self.console.print("[yellow]用法: /yolo on、/yolo off 或 /yolo status[/yellow]")
            return
        if self._running():
            self.console.print("[yellow]任务运行中不能切换 YOLO；请先等待完成或 Esc 打断。[/yellow]")
            return
        self.yolo = normalized == "on"
        if self.yolo:
            self.console.print(
                "[bold yellow]YOLO 已开启：后续任务的危险操作将由 LLM 自动审批。[/bold yellow]"
            )
        else:
            self.console.print("[green]YOLO 已关闭：后续任务恢复人工审批。[/green]")
        self.invalidate()

    async def _cmd_compact(self, value: str) -> None:
        """手动压缩当前对话的 Coordinator 上下文。"""
        if self._running():
            self.console.print("[yellow]任务运行中，请先 Esc 打断再压缩上下文。[/yellow]")
            return

        keep_recent = 4
        if value:
            try:
                keep_recent = int(value)
                if keep_recent < 1:
                    raise ValueError
            except ValueError:
                self.console.print(
                    "[yellow]用法: /compact [保留最近N条消息，默认4]  示例: /compact 6[/yellow]"
                )
                return

        if not self.conversation_id:
            self.console.print("[yellow]当前没有激活的对话。[/yellow]")
            return

        cm = ContextManager(
            agent_id=_COORDINATOR_AGENT_ID,
            conversation_id=self.conversation_id,
            prompt=None,
            query="",
        )
        try:
            result = await cm.compact(keep_recent=keep_recent)
        except Exception as e:
            self.console.print(f"[red]上下文压缩失败: {e}[/red]")
            return

        if result["compressed"]:
            self.console.print(
                f"[green]√ 上下文已压缩: {result['original_count']} 条 → {result['new_count']} 条 "
                f"(梗概 {result['summary_length']} 字符)[/green]"
            )
        else:
            self.console.print(f"[yellow]{result['reason']}[/yellow]")

    async def _dispatch(self, text: str) -> None:
        if self._pending_approvals:
            await self._resolve_approval(text)
        elif self._pending_questions:
            future = self._pending_questions.pop(0)
            if not future.done():
                future.set_result(text)
        elif self._running():
            await ContextManager.inject_event(
                self.conversation_id, _COORDINATOR_AGENT_ID, "user", text,
            )
            self.console.print("\n[dim]» 已补充给 Agent（下一轮推理生效）[/dim]")
        else:
            self._start_task(text)

    def _running(self) -> bool:
        return self._running_task is not None and not self._running_task.done()

    # ---- 任务执行 ----

    def _start_task(self, query: str) -> None:
        self.session_id = f"{_COORDINATOR_AGENT_ID}_{datetime.now().isoformat()}"
        self._cancel_at = None
        self.phase = "starting"
        task = asyncio.create_task(self._run_task(query))
        task.add_done_callback(self._on_task_done)
        self._running_task = task

    async def _run_task(self, query: str) -> str:
        """在当前 TUI Session 的独立 context 中运行，避免 YOLO 状态串到其他任务。"""
        from cloudra.infra.yolo_guard import reset_session_yolo, set_session_yolo

        token = set_session_yolo(self.yolo)
        try:
            return await self.service.run_task(
                query,
                conversation_id=self.conversation_id,
                session_id=self.session_id,
                verbose=False,
                interactive_approval=False,
            )
        finally:
            reset_session_yolo(token)

    def _on_task_done(self, task: asyncio.Task) -> None:
        cancelled_waiting = task in self._cancelled_waiting_tasks
        self._cancelled_waiting_tasks.discard(task)
        if self._running_task is task:
            self._running_task = None
            self._cancel_at = None
            self.phase = ""
            for future in self._pending_questions:
                if not future.done():
                    future.cancel()
            self._pending_questions.clear()
            self._pending_approvals.clear()
        if task.cancelled():
            if cancelled_waiting:
                self.console.print("[yellow]■ 已结束当前等待；定时提醒仍会按时触发。[/yellow]")
            else:
                self.console.print("[yellow]■ 任务已强制终止。[/yellow]")
        elif (exc := task.exception()) is not None:
            if isinstance(exc, AgentCancelled):
                self.console.print("[yellow]■ 任务已打断。[/yellow]")
            else:
                self.console.print(f"[red]× 任务失败: {exc}[/red]")
        else:
            self.console.print("[green]√ 任务完成。[/green]")
        config = get_config()
        config.last_conversation_id = self.conversation_id
        config.save()
        self.invalidate()

    async def _watch_schedules(self, conversation_id: str) -> None:
        """独立守候当前对话的 reminder，避免顶层任务被打断后提醒失去执行者。"""
        from cloudra.runtime.runner import _fire_due_reminders, _seconds_until_next_reminder

        db = ConversationDB(conversation_id)
        await db.ainit()
        changed = await subscribe_async(conversation_id, "schedule_changed")
        while conversation_id == self.conversation_id:
            fired = await _fire_due_reminders(db, conversation_id)
            if fired and not self._running():
                self._start_task("处理刚刚到期的定时提醒。")

            delay = await _seconds_until_next_reminder(db, conversation_id)
            if delay is None:
                await changed.get()
                continue
            try:
                await asyncio.wait_for(changed.get(), timeout=max(0.01, delay))
            except asyncio.TimeoutError:
                pass

    # ---- 打断 ----

    def request_cancel(self) -> bool:
        """Esc/Ctrl+C 入口：运行中请求打断；返回 False 表示当前空闲。"""
        task = self._running_task
        if task is None or task.done():
            return False
        if self.phase == "waiting":
            self._cancelled_waiting_tasks.add(task)
            task.cancel()
            return True
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

    @property
    def current_pending_approval(self) -> dict | None:
        """当前需要用户处理的审批请求。"""
        return self._pending_approvals[0] if self._pending_approvals else None

    def push_pending_approval(self, approval: dict) -> None:
        """由渲染器调用：将新的审批请求加入 FIFO 队列，并在成为当前审批时展示。"""
        is_first = not self._pending_approvals
        self._pending_approvals.append(approval)
        if is_first:
            self._show_current_approval()
        self.invalidate()

    def _show_current_approval(self) -> None:
        """打印当前审批面板；队列非空时才应调用。"""
        approval = self.current_pending_approval
        if approval is None:
            return
        count = len(self._pending_approvals)
        title = "[bold yellow]※ 安全审批[/bold yellow]"
        if count > 1:
            title = f"[bold yellow]※ 安全审批 ({count})[/bold yellow]"
        self.console.print(Panel(
            f"[bold]{escape(_strip_ansi(approval.get('details', '')))}[/bold]\n"
            f"[dim]来自 {escape(_strip_ansi(approval.get('agent_name', 'agent')))} · "
            f"输入 y 允许，n 拒绝（可 n:原因）[/dim]",
            title=title,
            title_align="left",
            border_style="yellow",
            padding=(0, 1),
        ))

    def _advance_approval(self) -> None:
        """处理完当前审批后前进到下一个；若队列空则仅刷新 toolbar。"""
        if self._pending_approvals:
            self._pending_approvals.pop(0)
        if self._pending_approvals:
            self._show_current_approval()
        self.invalidate()

    async def _resolve_approval(self, text: str) -> None:
        """处理队列首个审批请求；完成后自动展示下一个。"""
        approval = self.current_pending_approval
        if approval is None:
            return
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
            msg = "[green]√ 已允许执行。[/green]" if decision == "approved" else "[yellow]■ 已拒绝。[/yellow]"
            self.console.print(msg)
        else:
            self.console.print("[dim]该审批已在其他端处理，本次输入忽略。[/dim]")
        self._advance_approval()

    async def _ask_user_handler(self, prompt_text: str) -> str:
        """ask_user 工具的输入处理器：展示问题并挂起，等待主输入框的答案。"""
        future = asyncio.get_running_loop().create_future()
        self._pending_questions.append(future)
        self.console.print(Panel(
            escape(_strip_ansi(prompt_text)),
            title="[bold yellow]? Agent 提问[/bold yellow]",
            title_align="left",
            border_style="yellow",
            padding=(0, 1),
        ))
        self.invalidate()
        return await future


def run_tui(yolo: bool = False) -> None:
    """TUI 入口（由 cli._interactive_tui 调用）。"""
    CloudraTUI(yolo=yolo).run()
