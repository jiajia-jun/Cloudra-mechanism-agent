"""Cloudra Textual TUI 主屏幕。"""

from __future__ import annotations

import asyncio
import json
from uuid import uuid4

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Footer, Header

from cloudra.config import get_config
from cloudra.context_manager import ContextManager
from cloudra.conversation_class import Conversation
from cloudra.conversation_repo import list_conversations
from cloudra.service import CloudraService
from cloudra.token_estimator import TokenEstimator
from cloudra.tui.new.commands import KNOWN_COMMANDS, parse_command
from cloudra.tui.new.render_bridge import RenderBridge
from cloudra.tui.new.screens.approval_modal import ApprovalModal
from cloudra.tui.new.screens.ask_user_modal import AskUserModal
from cloudra.tui.new.screens.context_screen import ContextScreen
from cloudra.tui.new.screens.dag_screen import DagScreen, format_dag_summary
from cloudra.tui.new.screens.help_screen import HelpScreen
from cloudra.tui.new.transcript import TranscriptHandle
from cloudra.tui.new.widgets.chat_log import ChatLog
from cloudra.tui.new.widgets.input_bar import InputBar
from cloudra.tui.new.widgets.side_panel import SidePanel
from cloudra.tui.new.widgets.status_bar import StatusBar

_ACTIVE_STATES = {"queued", "running"}

# Coordinator 的 agent_id（与 legacy TUI / email_listener 的注入先例一致）
_COORDINATOR_AGENT_ID = "a-0"

# 发送后、真实 session_id 返回前的临时消息分组
_PENDING_SESSION = "_pending"

# /mode 命令的编排模式别名与展示名（session 创建时生效，创建后不可变）
_MODE_ALIASES = {
    "off": "standard",
    "standard": "standard",
    "record": "dag_record",
    "dag_record": "dag_record",
    "guided": "dag_guided",
    "dag_guided": "dag_guided",
}
_MODE_LABELS = {
    "standard": "标准（DAG 关闭）",
    "dag_record": "DAG 记录（只记录图，Supervisor 不干预）",
    "dag_guided": "DAG 引导（记录 + Supervisor 引导）",
}

# 历史回放上限：最近 N 个任务、每个 session 最多 M 条事件
_HISTORY_TASK_LIMIT = 5
_HISTORY_EVENT_LIMIT = 120
_HISTORY_TOTAL_EVENT_LIMIT = 480


def _format_tokens(n: int) -> str:
    if n >= 1000:
        return f"{n / 1000:.1f}k"
    return str(n)


class MainScreen(Screen):
    """主界面：对话式聊天区 + 底部输入栏。

    用户面对的是「对话（conversation）」；session 只是内部执行单位，
    不出现在 UI 上（发送时自动挂到当前运行中的任务，否则开新任务）。
    """

    BINDINGS = [
        ("escape", "cancel_current", "取消当前任务"),
        ("q", "quit", "退出"),
        ("?", "show_help", "帮助"),
        ("ctrl+t", "show_context", "上下文统计"),
        ("ctrl+g", "show_dag", "DAG 编排"),
        ("ctrl+b", "toggle_sidebar", "侧栏"),
    ]

    def __init__(self, yolo: bool = False, conversation_id: str | None = None) -> None:
        super().__init__()
        self.yolo = yolo
        # 编排模式：standard / dag_record / dag_guided，对下一个新任务生效
        self.orchestration_mode = "standard"
        self.service = CloudraService()
        self.conversation_id = conversation_id or self._startup_conversation()
        self.current_session_id: str | None = None
        self._render_bridge: RenderBridge | None = None
        # 输入定向：None = 自动（主 Agent）；否则为选中实例的 session_id / agent_id
        # （同角色并行实例按 session_id 区分）
        self._target_session_id: str | None = None
        self._target_agent_id: str | None = None
        self._view_generation = 0
        self._sidebar_refresh_task: asyncio.Task | None = None
        # 各 session 的累计 token usage（token_usage 事件驱动），计划面板展示用
        self._token_by_session: dict[str, dict] = {}
        self._plan_refresh_task: asyncio.Task | None = None
        self._compact_task: asyncio.Task | None = None
        self._compactions: dict[str, str] = {}

    def _startup_conversation(self) -> str:
        """恢复上次对话或新建。"""
        config = get_config()
        if config.last_conversation_id:
            try:
                Conversation(config.last_conversation_id)
                return config.last_conversation_id
            except Exception:
                pass
        return self.service.create_conversation().id

    def compose(self) -> ComposeResult:
        # StatusBar already owns the only useful periodic refresh.  A second
        # clock timer keeps remote/WSL terminals repainting while otherwise idle.
        yield Header(show_clock=False)
        with Horizontal(id="main-body"):
            with Vertical(id="chat-area"):
                yield ChatLog(id="chat-log")
                yield InputBar(id="input-bar")
            yield SidePanel(id="side-panel")
        yield StatusBar(id="status-bar")
        yield Footer()

    async def on_mount(self) -> None:
        chat_log = self.query_one("#chat-log", ChatLog)
        input_bar = self.query_one("#input-bar", InputBar)

        # 启动 IPC 事件桥
        status_bar = self.query_one("#status-bar", StatusBar)
        status_bar.yolo = self.yolo
        status_bar.orch_mode = self.orchestration_mode
        status_bar.native_search = self._native_search_label()
        status_bar.conversation_id = self.conversation_id
        self._render_bridge = RenderBridge(
            self.conversation_id,
            chat_log,
            status_bar=status_bar,
            on_approval=self._on_approval,
            on_ask_user=self._on_ask_user,
            on_context_dirty=self._on_context_dirty,
            on_session_state=self._on_session_state_update,
            on_token_usage=self._on_token_usage,
            on_plan_dirty=self._on_plan_dirty,
            on_compaction_progress=self._on_compaction_progress,
        )
        await self._render_bridge.start()

        # 回放本对话的历史任务，让之前的对话内容在 UI 中延续
        await self._load_history()

        # 填充侧栏（Agent 列表 + 对话列表）
        await self._refresh_agents()

        # 显示对话级共享上下文规模（记忆 N条≈Tk）
        await self._refresh_context_info()

        # 恢复仍有运行中任务时，状态栏继续跟踪它
        active = await self._find_active_record()
        if active is not None:
            self._track_session(active.session_id, active.state)

        # 启动后焦点放到输入框，避免用户打字无反应
        input_bar.focus_input()

    async def on_unmount(self) -> None:
        if self._compact_task is not None and not self._compact_task.done():
            self._compact_task.cancel()
            try:
                await self._compact_task
            except asyncio.CancelledError:
                pass
        if self._sidebar_refresh_task is not None and not self._sidebar_refresh_task.done():
            self._sidebar_refresh_task.cancel()
        if self._plan_refresh_task is not None and not self._plan_refresh_task.done():
            self._plan_refresh_task.cancel()
        if self._render_bridge is not None:
            await self._render_bridge.stop()

    def _on_compaction_progress(self, progress: dict) -> None:
        """Render bounded map/reduce progress without adding chat messages."""
        status_bar = self.query_one("#status-bar", StatusBar)
        key = str(
            progress.get("session_id")
            or progress.get("agent_id")
            or "manual"
        )
        stage = progress.get("stage")
        if stage in ("completed", "failed"):
            self._compactions.pop(key, None)
        else:
            level = int(progress.get("level") or 1)
            completed = int(progress.get("completed") or 0)
            total = int(progress.get("total") or 0)
            label = f"压缩上下文 L{level}"
            if total:
                label += f" {completed}/{total}"
            self._compactions[key] = label
        if not self._compactions:
            status_bar.compaction_info = ""
        elif len(self._compactions) == 1:
            status_bar.compaction_info = next(iter(self._compactions.values()))
        else:
            status_bar.compaction_info = f"{len(self._compactions)} 个 Agent 正在压缩"

    def _track_session(self, session_id: str, state: str = "") -> None:
        """内部跟踪当前任务（不向用户暴露 session id）。

        状态栏据此显示 spinner/phase；Esc 取消与 /context 也以它为目标。
        """
        self.current_session_id = session_id
        status_bar = self.query_one("#status-bar", StatusBar)
        status_bar.session_id = session_id
        if state:
            status_bar.session_state = state
        self.query_one("#input-bar", InputBar).follow_up = True

    @staticmethod
    def _native_search_label() -> str:
        """解析 Coordinator 是否启用了模型原生网页搜索，返回适配器名或空串。

        空串 = 未启用（传统 web_search 工具仍然可用）；否则状态栏显示「联网」。
        """
        try:
            cfg = get_config().coordinator
            if not cfg.native_search or cfg.native_search == "off":
                return ""
            from cloudra.web_search_native import resolve_native_search

            adapter = resolve_native_search(
                base_url=cfg.url,
                model=cfg.model,
                mode=cfg.native_search,
                params=cfg.native_search_params,
            )
            return adapter.name if adapter is not None else ""
        except Exception:
            return ""

    async def _find_active_record(
        self, agent_id: str | None = None, session_id: str | None = None
    ):
        """当前对话中最新一个运行中的任务；没有则 None。

        session_id 指定时按实例精确定位（并行实例各自独立）；agent_id 指定时
        找该角色的运行中 session；都为 None 时只找根任务（Coordinator）。
        """
        records = await asyncio.to_thread(
            self.service.session_runner.list, self.conversation_id
        )
        for record in records:  # list() 按 created_at DESC
            if record.state not in _ACTIVE_STATES:
                continue
            if session_id is not None:
                if record.session_id == session_id:
                    return record
            elif agent_id is None:
                if record.parent_session_id is None:
                    return record
            elif record.agent_id == agent_id:
                return record
        return None

    # ------------------------------------------------------------------
    # 输入发送
    # ------------------------------------------------------------------

    async def on_input_bar_send_message(self, event: InputBar.SendMessage) -> None:
        """用户提交输入：斜杠命令走命令路由，否则发送给 agent。"""
        content = event.content
        parsed = parse_command(content)
        if parsed is not None:
            cmd, arg = parsed
            try:
                await self._run_command(cmd, arg)
            except Exception as exc:
                self.notify(f"命令执行失败: {exc}", severity="error")
            return
        try:
            await self._handle_send(content)
        except Exception as exc:
            self.notify(f"发送失败: {exc}", severity="error")

    async def _handle_send(self, content: str) -> None:
        chat_log = self.query_one("#chat-log", ChatLog)
        input_bar = self.query_one("#input-bar", InputBar)

        if self._compact_task is not None and not self._compact_task.done():
            self.notify("上下文正在压缩，请等待完成后再发送任务", severity="warning")
            return

        # 定向到指定子 Agent 实例：注入它（按 session 精确定位）的运行中 session
        target = self._target_session_id
        if target and self._target_agent_id != _COORDINATOR_AGENT_ID:
            record = await self._find_active_record(session_id=target)
            if record is None:
                self.notify(
                    "该 Agent 当前没有运行中的任务，无法插入指令", severity="warning"
                )
                return
            command_id = f"tui-msg-{uuid4().hex}"
            handle = chat_log.append_user(
                record.session_id, content, message_id=command_id
            )
            await self._present_user_echo(chat_log, handle)
            try:
                await self._append_message(
                    record.session_id, content, command_id=command_id
                )
            except Exception:
                chat_log.mark_send_failed(handle)
                raise
            return

        record = await self._find_active_record()

        if record is not None:
            # 运行中任务：先上屏再注入，用户立刻看到自己发了什么
            command_id = f"tui-msg-{uuid4().hex}"
            handle = chat_log.append_user(
                record.session_id, content, message_id=command_id
            )
            await self._present_user_echo(chat_log, handle)
            try:
                await self._append_message(
                    record.session_id, content, command_id=command_id
                )
            except Exception:
                chat_log.mark_send_failed(handle)
                raise
            return

        # 无运行中任务：启动新 Coordinator 任务，消息先上屏到 pending 组
        input_bar.follow_up = False
        if chat_log.has_records:
            # 同一对话里开启新任务，加分隔线避免误认为切换了对话
            chat_log.append_divider(
                _PENDING_SESSION,
                f"── 新任务（同一对话 …{self.conversation_id[-6:]}，上下文延续）──",
            )
        handle = chat_log.append_user(_PENDING_SESSION, content)
        await self._present_user_echo(chat_log, handle)
        try:
            await self._start_coordinator_task(content)
        except Exception:
            chat_log.mark_send_failed(handle)
            raise

    async def _start_coordinator_task(self, query: str) -> None:
        """启动新的 Coordinator Session。"""
        # 注意：submit_async 内部用 asyncio.create_task 调度执行任务，
        # 必须在主事件循环线程调用；同步 DB 写入已 offload 到线程，不阻塞 UI。
        _, record = await self.service.submit_session_async(
            query,
            conversation_id=self.conversation_id,
            yolo=self.yolo,
            orchestration_mode=self.orchestration_mode,
        )
        chat_log = self.query_one("#chat-log", ChatLog)
        # 把 pending 消息归到真实 session，再切换视图
        chat_log.rename_session(_PENDING_SESSION, record.session_id)
        self._track_session(record.session_id, record.state)
        # 保存当前对话
        config = get_config()
        config.last_conversation_id = self.conversation_id
        await asyncio.to_thread(config.save)
        # 刷新状态栏记忆指示
        await self._refresh_context_info()
        # 发送后焦点回到输入框
        self.query_one("#input-bar", InputBar).focus_input()

    def _on_context_dirty(self) -> None:
        """Coordinator 上下文有变化时（流式结束/任务终态）刷新状态栏记忆指示。"""
        try:
            asyncio.create_task(self._refresh_context_info())
        except RuntimeError:
            pass

    async def _refresh_context_info(self) -> None:
        """刷新状态栏的对话级共享上下文摘要。

        Coordinator（a-0）的上下文是对话级的，跨任务延续——这个指示让用户
        能直接看到"记忆"在增长/被压缩。
        """
        status_bar = self.query_one("#status-bar", StatusBar)
        try:
            cm = ContextManager(
                agent_id=_COORDINATOR_AGENT_ID,
                conversation_id=self.conversation_id,
                prompt=None,
                query="",
            )
            context = await cm.load()
            tokens = TokenEstimator.estimate_messages(context)
            status_bar.context_info = f"{len(context)}条消息≈{_format_tokens(tokens)} tokens"
        except Exception:
            status_bar.context_info = ""

    async def _load_history(self) -> None:
        """回放当前对话的历史任务：把之前 session 的消息重新渲染进聊天区。

        按任务分组（根 session + 其子 agent），每个任务画一条分隔线，
        根任务的 query 渲染为用户消息，然后回放各 session 的事件流。
        历史加载失败不应影响启动，故整体吞掉异常。
        """
        chat_log = self.query_one("#chat-log", ChatLog)
        try:
            records = await asyncio.to_thread(
                self.service.session_runner.list, self.conversation_id
            )
        except Exception:
            return
        if not records:
            return
        records = list(reversed(records))  # list() 按 created_at DESC，反转为时间升序

        # 按任务分组：根 session 开启新组，其后的子 agent 归入当前组
        tasks: list[list] = []
        for rec in records:
            if rec.parent_session_id is None:
                tasks.append([rec])
            elif tasks:
                tasks[-1].append(rec)

        hidden = max(0, len(tasks) - _HISTORY_TASK_LIMIT)
        tasks = tasks[-_HISTORY_TASK_LIMIT:]
        if hidden:
            chat_log.append_system(
                "_history",
                f"…… 仅显示最近 {len(tasks)} 个任务，共 {len(tasks) + hidden} 个",
            )

        # 先读取、再从最旧端裁掉。仅有 per-session 上限仍可能在多 Agent
        # 对话中挂载几千个控件，启动阶段就把 Textual 主线程压死。
        history: list[tuple[list, list[tuple[str, dict]]]] = []
        for task in tasks:
            entries: list[tuple[str, dict]] = []
            for rec in task:
                try:
                    session_events = await asyncio.to_thread(
                        self.service.session_runner.events,
                        self.conversation_id,
                        rec.session_id,
                    )
                except Exception:
                    continue
                entries.extend(
                    (rec.session_id, ev)
                    for ev in session_events[-_HISTORY_EVENT_LIMIT:]
                )
            history.append((task, entries))

        overflow = max(
            0,
            sum(len(entries) for _, entries in history)
            - _HISTORY_TOTAL_EVENT_LIMIT,
        )
        for _, entries in history:
            if overflow <= 0:
                break
            drop = min(overflow, len(entries))
            del entries[:drop]
            overflow -= drop

        with chat_log.batch_update():
            for task, entries in history:
                root = task[0]
                # 分隔线只展示任务状态和时间，不暴露内部 session id
                when = (root.created_at or "")[5:16].replace("T", " ")
                label = f"── 历史任务 [{root.state or '?'}]"
                if when:
                    label += f" · {when}"
                label += " ──"
                chat_log.append_divider(root.session_id, label)
                if root.query:
                    chat_log.append_user(root.session_id, root.query)
                for session_id, ev in entries:
                    self._render_bridge.replay_event(
                        session_id, ev["event_type"], ev["data"] or {}
                    )

        chat_log.request_frame(immediate=True)
        chat_log.scroll_end(animate=False, immediate=True, x_axis=False)

    @staticmethod
    async def _present_user_echo(
        chat_log: ChatLog, handle: TranscriptHandle
    ) -> None:
        """Reveal local input before backend/SQLite command work."""
        await asyncio.sleep(0)
        # The user's own message is explicitly revealed; this is intentionally
        # stronger than the smart follow-scroll used for background Agent output.
        await chat_log.reveal(handle.record_id, force=True)
        await asyncio.sleep(0)

    async def _append_message(
        self,
        session_id: str,
        content: str,
        *,
        command_id: str | None = None,
    ) -> None:
        """向运行中的任务追加用户补充消息。"""
        command_id = command_id or f"tui-msg-{uuid4().hex}"
        await self.service.append_session_message_command(
            command_id=command_id,
            conversation_id=self.conversation_id,
            session_id=session_id,
            content=content,
        )
        await self._refresh_context_info()

    # ------------------------------------------------------------------
    # 斜杠命令
    # ------------------------------------------------------------------

    async def _run_command(self, cmd: str, arg: str) -> None:
        if cmd not in KNOWN_COMMANDS:
            self.notify(f"未知命令: /{cmd}，输入 /help 查看可用命令", severity="warning")
            return

        if cmd == "help":
            self.action_show_help()
        elif cmd == "new":
            await self._cmd_new()
        elif cmd == "list":
            await self._cmd_list()
        elif cmd == "conv":
            if arg:
                await self._cmd_conv(arg)
            else:
                self.action_toggle_sidebar()
        elif cmd == "agents":
            self.action_toggle_sidebar()
        elif cmd == "yolo":
            await self._cmd_yolo(arg)
        elif cmd == "mode":
            await self._cmd_mode(arg)
        elif cmd == "goal":
            await self._cmd_goal(arg)
        elif cmd == "compact":
            await self._cmd_compact(arg)
        elif cmd in ("context", "tokens"):
            await self.action_show_context()
        elif cmd == "dag":
            self.action_show_dag()
        elif cmd == "cancel":
            await self.action_cancel_current()
        elif cmd == "quit":
            self.app.exit()

    async def _has_active_session(self) -> bool:
        records = await asyncio.to_thread(
            self.service.session_runner.list, self.conversation_id
        )
        return any(r.state in _ACTIVE_STATES for r in records)

    async def _cmd_new(self) -> None:
        if await self._has_active_session():
            self.notify("任务运行中，请先 Esc 打断再开新对话", severity="warning")
            return
        conversation = await asyncio.to_thread(self.service.create_conversation)
        await self._activate_conversation(conversation.id)
        self.notify(f"已开启新对话: {conversation.id}", severity="information")

    async def _cmd_list(self) -> None:
        convs = await asyncio.to_thread(list_conversations)
        chat_log = self.query_one("#chat-log", ChatLog)
        if not convs:
            chat_log.append_system(self.current_session_id or "_system", "暂无历史对话")
            return
        lines = [f"历史对话 (共 {len(convs)} 个，最多显示 20):"]
        for conv in convs[:20]:
            cid = conv.get("id", "?")
            state = conv.get("state", "?")
            last = (conv.get("last_active", "") or "")[:19]
            marker = " ← 当前" if cid == self.conversation_id else ""
            lines.append(f"  {cid}{marker}  {state}  {last}")
        chat_log.append_system(
            self.current_session_id or "_system", "\n".join(lines)
        )

    async def _cmd_conv(self, arg: str) -> None:
        if not arg:
            self.notify("用法: /conv <对话ID>", severity="warning")
            return
        if await self._has_active_session():
            self.notify("任务运行中，请先 Esc 打断再切换对话", severity="warning")
            return
        convs = await asyncio.to_thread(list_conversations)
        matched = [c for c in convs if c.get("id", "").startswith(arg)]
        if len(matched) == 1:
            await self._activate_conversation(matched[0]["id"])
            self.notify(f"已切换到对话: {matched[0]['id']}", severity="information")
        elif not matched:
            self.notify(f"未找到对话: {arg}，用 /list 查看", severity="warning")
        else:
            ids = ", ".join(c["id"] for c in matched)
            self.notify(f"多个匹配，请输入更完整的 ID: {ids}", severity="warning")

    async def _cmd_yolo(self, arg: str) -> None:
        normalized = arg.lower()
        status_bar = self.query_one("#status-bar", StatusBar)
        if not normalized or normalized == "status":
            state = "已开启" if self.yolo else "未开启"
            self.notify(f"YOLO 模式{state}", severity="information")
            return
        if normalized not in ("on", "off"):
            self.notify("用法: /yolo on、/yolo off 或 /yolo status", severity="warning")
            return
        if await self._has_active_session():
            self.notify("任务运行中不能切换 YOLO；请先等待完成或 Esc 打断", severity="warning")
            return
        self.yolo = normalized == "on"
        status_bar.yolo = self.yolo
        if self.yolo:
            self.notify("YOLO 已开启：危险操作将由 LLM 自动审批", severity="warning")
        else:
            self.notify("YOLO 已关闭：恢复人工审批", severity="information")

    async def _cmd_mode(self, arg: str) -> None:
        """/mode off|record|guided：切换下一个新任务的编排模式（消融开关）。

        模式在 session 创建时写入、创建后不可变，因此运行中的任务不受影响，
        切换只作用于之后启动的任务。
        """
        normalized = arg.lower()
        if not normalized or normalized == "status":
            self.notify(
                f"当前编排模式: {_MODE_LABELS[self.orchestration_mode]}",
                severity="information",
            )
            return
        target = _MODE_ALIASES.get(normalized)
        if target is None:
            self.notify(
                "用法: /mode off（标准）、/mode record（只记录）、/mode guided（引导）或 /mode status",
                severity="warning",
            )
            return
        if await self._has_active_session():
            self.notify(
                "任务运行中不能切换编排模式；请先等待完成或 Esc 打断", severity="warning"
            )
            return
        self.orchestration_mode = target
        self.query_one("#status-bar", StatusBar).orch_mode = target
        self.notify(
            f"编排模式已切换: {_MODE_LABELS[target]}（对下一个新任务生效）",
            severity="information",
        )

    async def _cmd_goal(self, arg: str) -> None:
        """/goal <目标文本>：为 Coordinator 设置目标锚点；/goal pause：暂停当前任务；
        /goal（无参）：显示当前目标与用法。"""
        if arg.lower() == "pause":
            await self.action_cancel_current()
            return
        if not arg:
            await self._show_goal()
            return

        from types import SimpleNamespace

        from cloudra.tools.Plantool._store import agent_store_path, save_json
        from cloudra.tools.Plantool.goal import GOAL_MARKER, GoalSet

        agent = SimpleNamespace(
            id=_COORDINATOR_AGENT_ID, conversation_id=self.conversation_id
        )
        goal = {"objective": arg, "completion_criteria": "", "current_focus": ""}
        save_json(agent_store_path(agent, "goal.json"), goal)

        # 固定到 Coordinator 上下文：让运行中的/后续任务都能看到目标
        try:
            cm = ContextManager(
                agent_id=_COORDINATOR_AGENT_ID,
                conversation_id=self.conversation_id,
                prompt=None,
                query="",
            )
            context = await cm.load()
            context = [
                msg
                for msg in context
                if not (
                    msg.get("role") == "system"
                    and str(msg.get("content", "")).startswith(GOAL_MARKER)
                )
            ]
            context.append({"role": "system", "content": GoalSet._format(goal)})
            await cm.replace(context)
        except Exception as exc:
            self.notify(f"目标已保存但注入上下文失败: {exc}", severity="warning")

        asyncio.create_task(self._refresh_plan())
        self.notify(f"目标已设置: {arg}", severity="information")

    async def _show_goal(self) -> None:
        """在聊天区展示当前 Coordinator 目标锚点。"""
        from types import SimpleNamespace

        from cloudra.tools.Plantool._store import agent_store_path, load_json
        from cloudra.tools.Plantool.goal import GoalSet

        agent = SimpleNamespace(
            id=_COORDINATOR_AGENT_ID, conversation_id=self.conversation_id
        )
        goal = load_json(agent_store_path(agent, "goal.json"), default={})
        chat_log = self.query_one("#chat-log", ChatLog)
        target = self.current_session_id or "_system"
        if goal:
            chat_log.append_system(target, GoalSet._format(goal))
        else:
            chat_log.append_system(
                target,
                "当前未设置目标。\n用法: /goal <目标文本> 设置目标；/goal pause 暂停当前任务。",
            )

    async def _cmd_compact(self, arg: str) -> None:
        """手动压缩当前对话的 Coordinator 上下文。"""
        if await self._has_active_session():
            self.notify("任务运行中，请先 Esc 打断再压缩上下文", severity="warning")
            return
        if self._compact_task is not None and not self._compact_task.done():
            self.notify("上下文压缩已经在进行中", severity="information")
            return
        keep_recent = 4
        if arg:
            try:
                keep_recent = int(arg)
                if keep_recent < 1:
                    raise ValueError
            except ValueError:
                self.notify("用法: /compact [保留最近N条消息，默认4]", severity="warning")
                return

        cm = ContextManager(
            agent_id=_COORDINATOR_AGENT_ID,
            conversation_id=self.conversation_id,
            prompt=None,
            query="",
            on_compaction_progress=lambda progress: self._on_compaction_progress(
                {"agent_id": _COORDINATOR_AGENT_ID, **progress}
            ),
        )
        self._on_compaction_progress(
            {
                "agent_id": _COORDINATOR_AGENT_ID,
                "stage": "started",
                "level": 1,
                "completed": 0,
                "total": 0,
            }
        )
        # Return control to Textual immediately.  The model request remains
        # asynchronous, while large pre-processing/file work is offloaded by
        # ContextManager, so keyboard input and rendering keep moving.
        self._compact_task = asyncio.create_task(
            self._run_manual_compact(cm, keep_recent=keep_recent)
        )

    async def _run_manual_compact(
        self,
        cm: ContextManager,
        *,
        keep_recent: int,
    ) -> None:
        chat_log = self.query_one("#chat-log", ChatLog)
        target = self.current_session_id or "_system"
        try:
            result = await cm.compact(keep_recent=keep_recent)
        except Exception as exc:
            self.notify(f"上下文压缩失败: {exc}", severity="error")
            return
        finally:
            self._compactions.pop(_COORDINATOR_AGENT_ID, None)
            self.query_one("#status-bar", StatusBar).compaction_info = ""
            self._compact_task = None

        if result.get("compressed"):
            chat_log.append_system(
                target,
                f"√ 上下文已压缩: {result['original_count']} 条 → {result['new_count']} 条 "
                f"(梗概 {result['summary_length']} 字符)",
            )
        else:
            chat_log.append_system(target, result.get("reason", "无需压缩"))
        await self._refresh_context_info()

    async def _activate_conversation(self, conv_id: str) -> None:
        """切换到另一个对话：重建事件桥和聊天区。"""
        if self._render_bridge is not None:
            await self._render_bridge.stop()
        self._view_generation += 1
        if self._sidebar_refresh_task is not None and not self._sidebar_refresh_task.done():
            self._sidebar_refresh_task.cancel()
        if self._plan_refresh_task is not None and not self._plan_refresh_task.done():
            self._plan_refresh_task.cancel()
        self.conversation_id = conv_id
        self.current_session_id = None
        self._target_session_id = None
        self._target_agent_id = None
        # token 统计按对话隔离；回放历史时会从事件重建
        self._token_by_session = {}

        chat_log = self.query_one("#chat-log", ChatLog)
        chat_log.clear_all()

        input_bar = self.query_one("#input-bar", InputBar)
        input_bar.follow_up = False
        input_bar.target_name = None

        status_bar = self.query_one("#status-bar", StatusBar)
        status_bar.conversation_id = conv_id
        status_bar.session_id = ""
        status_bar.session_state = ""
        status_bar.phase = ""
        status_bar.pending = 0

        self._render_bridge = RenderBridge(
            conv_id,
            chat_log,
            status_bar=status_bar,
            on_approval=self._on_approval,
            on_ask_user=self._on_ask_user,
            on_context_dirty=self._on_context_dirty,
            on_session_state=self._on_session_state_update,
            on_token_usage=self._on_token_usage,
            on_plan_dirty=self._on_plan_dirty,
        )
        await self._render_bridge.start()

        # 回放目标对话的历史任务
        await self._load_history()

        await self._refresh_agents()

        config = get_config()
        config.last_conversation_id = conv_id
        await asyncio.to_thread(config.save)

        await self._refresh_context_info()

        # 目标对话仍有运行中任务时，状态栏继续跟踪
        active = await self._find_active_record()
        if active is not None:
            self._track_session(active.session_id, active.state)

    # ------------------------------------------------------------------
    # 侧栏（Agent / 对话列表）
    # ------------------------------------------------------------------

    def action_copy_text(self) -> None:
        """复制当前文本选择（Screen 内建 ctrl+c），给出反馈并清除高亮。"""
        selection = self.get_selected_text()
        super().action_copy_text()
        if not selection:
            return
        self.clear_selection()
        self.notify(f"已复制 {len(selection)} 个字符", severity="information", timeout=2)

    def action_toggle_sidebar(self) -> None:
        """打开/收起侧栏；打开时刷新数据。"""
        panel = self.query_one("#side-panel", SidePanel)
        panel.display = not panel.display
        if panel.display:
            asyncio.create_task(self._refresh_agents())

    def _on_session_state_update(self, session_id: str, state: str | None) -> None:
        """session 状态变化/新 session 出现时，节流刷新侧栏 Agent 列表。"""
        if self._sidebar_refresh_task is not None and not self._sidebar_refresh_task.done():
            return
        generation = self._view_generation

        async def _later() -> None:
            await asyncio.sleep(0.3)
            if generation != self._view_generation or not self.is_mounted:
                return
            await self._refresh_agents()

        self._sidebar_refresh_task = asyncio.create_task(_later())

    async def _refresh_agents(self) -> None:
        """从 session 记录重建侧栏的 Agent 与对话列表。"""
        try:
            records = await asyncio.to_thread(
                self.service.session_runner.list, self.conversation_id
            )
        except Exception:
            records = []
        agents: list[dict] = []
        for rec in records:  # 按 created_at DESC；同角色并行实例各占一行（按 session 区分）
            agents.append(
                {
                    "agent_id": rec.agent_id,
                    "session_id": rec.session_id,
                    "name": self._agent_display_name(rec.agent_id, rec.agent_type),
                    "state": rec.state or "",
                }
            )
        agents.sort(key=lambda a: (a["agent_id"], a["session_id"] or ""))
        panel = self.query_one("#side-panel", SidePanel)
        panel.set_agents(agents, selected=self._target_session_id)
        try:
            convs = await asyncio.to_thread(list_conversations)
        except Exception:
            convs = []
        panel.set_conversations(convs, self.conversation_id)
        await self._refresh_plan()

    # ------------------------------------------------------------------
    # 计划面板（目标锚点 + todo 清单 + token 用量）
    # ------------------------------------------------------------------

    def _on_token_usage(self, session_id: str, data: dict) -> None:
        """累计各 session 的 token usage 并刷新计划面板。"""
        total = data.get("total")
        if isinstance(total, dict):
            # 按 session_id 键控：同角色并行实例各自累计，互不覆盖
            self._token_by_session[session_id] = total
        self._schedule_plan_refresh()

    def _on_plan_dirty(self) -> None:
        """todo_write / goal_set 更新了计划文件，刷新面板。"""
        self._schedule_plan_refresh()

    def _schedule_plan_refresh(self) -> None:
        """节流刷新计划面板（token 事件每轮一次，避免频繁 IO）。"""
        if self._plan_refresh_task is not None and not self._plan_refresh_task.done():
            return
        generation = self._view_generation

        async def _later() -> None:
            await asyncio.sleep(0.3)
            if generation != self._view_generation or not self.is_mounted:
                return
            await self._refresh_plan()

        self._plan_refresh_task = asyncio.create_task(_later())

    def _load_plan_files(
        self, agent_id: str, session_id: str | None = None
    ) -> tuple[list, dict]:
        """读取当前选中 agent 实例的 todo/goal 存储文件（同步，供 to_thread 调用）。

        键控镜像写侧（tools/Plantool/_store.py）：有 session_id 时读
        ``{agent_id}_{session_id}_*.json``（并行实例各自独立）；无 session_id
        （Coordinator / 旧行为）保持 ``{agent_id}_*.json``。
        """
        base = get_config().data_dir / "conversations" / self.conversation_id / "plan"
        key = f"{agent_id}_{session_id}" if session_id else agent_id

        def _read(name: str):
            try:
                with open(base / name, encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return None

        return _read(f"{key}_todos.json") or [], _read(f"{key}_goal.json") or {}

    def _format_plan(
        self, todos: list, goal: dict, session_id: str | None
    ) -> str:
        """把目标锚点、todo 清单、token 用量渲染成面板文本。"""
        lines: list[str] = []
        objective = (goal or {}).get("objective") or ""
        if objective:
            lines.append(f"目标: {objective}")
            criteria = goal.get("completion_criteria") or ""
            if criteria:
                lines.append(f"判据: {criteria}")
        if todos:
            icon = {"pending": "○", "in_progress": "◐", "done": "●"}
            for todo in todos:
                lines.append(
                    f"{icon.get(todo.get('status'), '?')} {todo.get('content', '')}"
                )
            done = sum(1 for t in todos if t.get("status") == "done")
            lines.append(f"进度: {done}/{len(todos)}")
        usage = self._token_by_session.get(session_id) if session_id else None
        if usage:
            lines.append(
                f"Token: {_format_tokens(usage.get('total_tokens', 0))}"
                f" (入 {_format_tokens(usage.get('prompt_tokens', 0))}"
                f" / 出 {_format_tokens(usage.get('completion_tokens', 0))})"
            )
        return "\n".join(lines) if lines else "（暂无计划）"

    async def _refresh_plan(self) -> None:
        """重建侧栏「计划」区：显示当前选中实例（默认主 Agent）的计划。"""
        try:
            panel = self.query_one("#side-panel", SidePanel)
        except Exception:
            return
        if not panel.is_mounted or not panel.display:
            return
        agent_id = self._target_agent_id or _COORDINATOR_AGENT_ID
        # 计划文件键控镜像写侧：只有子 Agent 实例按 session 键控；
        # Coordinator（无 session_id 注入）保持 agent_id 旧路径
        plan_session = (
            self._target_session_id
            if self._target_agent_id and self._target_agent_id != _COORDINATOR_AGENT_ID
            else None
        )
        try:
            todos, goal = await asyncio.to_thread(
                self._load_plan_files, agent_id, plan_session
            )
        except Exception:
            todos, goal = [], {}
        # token 用量按 session 键控；未选中实例时回退到当前跟踪的根 session
        token_session = self._target_session_id or self.current_session_id
        try:
            panel.set_plan(self._format_plan(todos, goal, token_session))
        except Exception:
            pass
        await self._refresh_dag()

    async def _refresh_dag(self) -> None:
        """重建侧栏「DAG」区：双图 revision、frontier、阻塞与机理缺口计数。"""
        try:
            panel = self.query_one("#side-panel", SidePanel)
        except Exception:
            return
        if not panel.is_mounted or not panel.display:
            return
        try:
            projection = await asyncio.to_thread(
                self.service.dag_projection, self.conversation_id
            )
        except Exception:
            projection = None
        try:
            panel.set_dag(format_dag_summary(projection))
        except Exception:
            pass

    @staticmethod
    def _agent_display_name(agent_id: str, agent_type: str) -> str:
        """session 记录里的 agent_type 只有 coordinator/follower，友好名从注册表取。"""
        if agent_id == _COORDINATOR_AGENT_ID or agent_type == "coordinator":
            return "coordinator"
        try:
            from cloudra.subagents import _get_model_default, get_subagent_classes

            cls = get_subagent_classes().get(agent_id)
            if cls is not None:
                return _get_model_default(cls, "name") or agent_id
        except Exception:
            pass
        return agent_type or agent_id

    def on_side_panel_agent_selected(self, event: SidePanel.AgentSelected) -> None:
        """切换聊天区视图与输入定向到选中的 Agent 实例（按 session 过滤）。"""
        self._target_session_id = event.session_id
        self._target_agent_id = event.agent_id
        chat_log = self.query_one("#chat-log", ChatLog)
        chat_log.show_session(event.session_id)
        input_bar = self.query_one("#input-bar", InputBar)
        if event.session_id is None:
            input_bar.target_name = None
            input_bar.follow_up = self.current_session_id is not None
        else:
            input_bar.target_name = event.label
        input_bar.focus_input()
        # 计划面板跟随选中实例切换
        asyncio.create_task(self._refresh_plan())

    async def on_side_panel_conversation_selected(
        self, event: SidePanel.ConversationSelected
    ) -> None:
        """切换对话；任务运行中拒绝。"""
        if event.conversation_id == self.conversation_id:
            return
        if await self._has_active_session():
            self.notify("任务运行中，请先 Esc 打断再切换对话", severity="warning")
            return
        await self._activate_conversation(event.conversation_id)
        self.query_one("#side-panel", SidePanel).display = False
        self.notify(f"已切换到对话: {event.conversation_id}", severity="information")

    async def on_side_panel_new_conversation_requested(self) -> None:
        await self._cmd_new()

    # ------------------------------------------------------------------
    # 动作
    # ------------------------------------------------------------------

    async def action_cancel_current(self) -> None:
        """取消当前运行中的任务（立即反馈，取消过程在后台进行）。

        cancel() 内部会等任务落终态（最长 3s+），不能阻塞在 UI 动作里——
        否则按 Esc 后要卡半天才有反应。任务真正停止时会通过事件桥
        渲染"已取消"卡片。
        """
        active = await self._find_active_record()
        if active is None:
            self.notify("没有运行中的任务", severity="warning")
            return
        asyncio.create_task(self._cancel_in_background(active.session_id))
        self.notify("已请求取消，任务将在当前步骤结束后停止", severity="information")

    async def _cancel_in_background(self, session_id: str) -> None:
        try:
            await self.service.session_runner.cancel(self.conversation_id, session_id)
        except Exception as exc:
            self.notify(f"取消失败: {exc}", severity="error")

    def action_show_help(self) -> None:
        """显示帮助页面。"""
        self.app.push_screen(HelpScreen())

    async def action_show_context(self) -> None:
        """显示对话级共享上下文（Coordinator 记忆）的统计。"""
        self.app.push_screen(
            ContextScreen(
                conversation_id=self.conversation_id,
                session_id=None,
                agent_id=_COORDINATOR_AGENT_ID,
            )
        )

    def action_show_dag(self) -> None:
        """打开 DAG 编排查看/编辑页面。"""
        self.app.push_screen(
            DagScreen(self.service, conversation_id=self.conversation_id)
        )

    # ------------------------------------------------------------------
    # 审批 / 提问
    # ------------------------------------------------------------------

    def _on_approval(self, msg: dict) -> None:
        """弹出审批弹窗并提交决定。"""
        approval_id = msg.get("approval_id")
        if approval_id is None:
            return
        status_bar = self.query_one("#status-bar", StatusBar)
        status_bar.pending += 1

        def on_decision(decision: str | None) -> None:
            status_bar.pending = max(0, status_bar.pending - 1)
            if decision is None:
                return
            asyncio.create_task(
                self._submit_approval(approval_id, decision)
            )

        self.app.push_screen(
            ApprovalModal(
                approval_id=approval_id,
                agent_name=msg.get("agent_name", "Agent"),
                details=msg.get("details", ""),
                tool_name=msg.get("tool_name"),
                arguments=str(msg.get("normalized_arguments", "")),
                risk_summary=msg.get("risk_summary"),
            ),
            callback=on_decision,
        )

    async def _submit_approval(self, approval_id: int, decision: str) -> None:
        """向后端提交审批决定。"""
        try:
            await self.service.decide_approval(
                self.conversation_id,
                approval_id,
                decision,
                "",
            )
            self.notify(f"已{decision}: 审批 {approval_id}", severity="information")
        except Exception as exc:
            self.notify(f"审批提交失败: {exc}", severity="error")

    def _on_ask_user(self, msg: dict) -> None:
        """弹出 Agent 提问弹窗并提交回答。"""
        interaction_id = msg.get("interaction_id")
        if interaction_id is None:
            return
        status_bar = self.query_one("#status-bar", StatusBar)
        status_bar.pending += 1

        def on_answer(answer: str | None) -> None:
            status_bar.pending = max(0, status_bar.pending - 1)
            if answer is None:
                return
            asyncio.create_task(
                self._submit_interaction_answer(interaction_id, answer)
            )

        self.app.push_screen(
            AskUserModal(
                interaction_id=interaction_id,
                agent_name=msg.get("agent_name") or msg.get("agent_id") or "Agent",
                prompt=msg.get("prompt", ""),
            ),
            callback=on_answer,
        )

    async def _submit_interaction_answer(
        self, interaction_id: str, answer: str
    ) -> None:
        """向后端提交 ask_user 回答。"""
        try:
            command_id = f"tui-ia-{asyncio.get_event_loop().time()}"
            await self.service.respond_interaction_command(
                command_id=command_id,
                conversation_id=self.conversation_id,
                interaction_id=interaction_id,
                response=answer,
            )
            self.notify("回答已提交", severity="information")
        except Exception as exc:
            self.notify(f"回答提交失败: {exc}", severity="error")
