"""Cloudra Textual TUI 主屏幕。"""

from __future__ import annotations

import asyncio
import json

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
from cloudra.tui.new.screens.help_screen import HelpScreen
from cloudra.tui.new.widgets.chat_log import ChatLog
from cloudra.tui.new.widgets.input_bar import InputBar
from cloudra.tui.new.widgets.side_panel import SidePanel
from cloudra.tui.new.widgets.status_bar import StatusBar

_ACTIVE_STATES = {"queued", "running"}

# Coordinator 的 agent_id（与 legacy TUI / email_listener 的注入先例一致）
_COORDINATOR_AGENT_ID = "a-0"

# 发送后、真实 session_id 返回前的临时消息分组
_PENDING_SESSION = "_pending"

# 历史回放上限：最近 N 个任务、每个 session 最多 M 条事件
_HISTORY_TASK_LIMIT = 10
_HISTORY_EVENT_LIMIT = 300


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
        ("ctrl+b", "toggle_sidebar", "侧栏"),
    ]

    def __init__(self, yolo: bool = False, conversation_id: str | None = None) -> None:
        super().__init__()
        self.yolo = yolo
        self.service = CloudraService()
        self.conversation_id = conversation_id or self._startup_conversation()
        self.current_session_id: str | None = None
        self._render_bridge: RenderBridge | None = None
        # 输入定向：None = 自动（主 Agent）；否则为选中的 agent_id
        self._target_agent_id: str | None = None
        self._sidebar_refresh_scheduled = False
        # 各 agent 的累计 token usage（token_usage 事件驱动），计划面板展示用
        self._token_by_agent: dict[str, dict] = {}
        self._plan_refresh_scheduled = False

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
        yield Header(show_clock=True)
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
        if self._render_bridge is not None:
            await self._render_bridge.stop()

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

    async def _find_active_record(self, agent_id: str | None = None):
        """当前对话中最新一个运行中的任务；没有则 None。

        agent_id 为 None 时只找根任务（Coordinator）；指定时找该 agent
        的运行中 session（含子 agent）。
        """
        records = await asyncio.to_thread(
            self.service.session_runner.list, self.conversation_id
        )
        for record in records:  # list() 按 created_at DESC
            if record.state not in _ACTIVE_STATES:
                continue
            if agent_id is None:
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

        # 定向到指定子 Agent：注入它的运行中 session
        target = self._target_agent_id
        if target and target != _COORDINATOR_AGENT_ID:
            record = await self._find_active_record(agent_id=target)
            if record is None:
                self.notify(
                    "该 Agent 当前没有运行中的任务，无法插入指令", severity="warning"
                )
                return
            widget = chat_log.append_user(record.session_id, content)
            try:
                await self._append_message(record.session_id, content)
            except Exception:
                widget.add_class("send-failed")
                raise
            return

        record = await self._find_active_record()

        if record is not None:
            # 运行中任务：先上屏再注入，用户立刻看到自己发了什么
            widget = chat_log.append_user(record.session_id, content)
            try:
                await self._append_message(record.session_id, content)
            except Exception:
                widget.add_class("send-failed")
                raise
            return

        # 无运行中任务：启动新 Coordinator 任务，消息先上屏到 pending 组
        input_bar.follow_up = False
        if chat_log._order:
            # 同一对话里开启新任务，加分隔线避免误认为切换了对话
            chat_log.append_divider(
                _PENDING_SESSION,
                f"── 新任务（同一对话 …{self.conversation_id[-6:]}，上下文延续）──",
            )
        widget = chat_log.append_user(_PENDING_SESSION, content)
        try:
            await self._start_coordinator_task(content)
        except Exception:
            widget.add_class("send-failed")
            raise

    async def _start_coordinator_task(self, query: str) -> None:
        """启动新的 Coordinator Session。"""
        # 注意：submit 内部用 asyncio.create_task 调度执行任务，
        # 必须在主事件循环线程调用；它本身只有轻量 DB 写入，不会阻塞 UI。
        _, record = self.service.submit_session(
            query,
            conversation_id=self.conversation_id,
            yolo=self.yolo,
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
            status_bar.context_info = f"{len(context)}条≈{_format_tokens(tokens)}"
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

        for task in tasks:
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
            for rec in task:
                try:
                    events = await asyncio.to_thread(
                        self.service.session_runner.events,
                        self.conversation_id,
                        rec.session_id,
                    )
                except Exception:
                    continue
                for ev in events[-_HISTORY_EVENT_LIMIT:]:
                    self._render_bridge.replay_event(
                        rec.session_id, ev["event_type"], ev["data"] or {}
                    )

        chat_log.scroll_end(animate=False)

    async def _append_message(self, session_id: str, content: str) -> None:
        """向运行中的任务追加用户补充消息。"""
        command_id = f"tui-msg-{asyncio.get_event_loop().time()}"
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
            self._cmd_list()
        elif cmd == "conv":
            if arg:
                await self._cmd_conv(arg)
            else:
                self.action_toggle_sidebar()
        elif cmd == "agents":
            self.action_toggle_sidebar()
        elif cmd == "yolo":
            self._cmd_yolo(arg)
        elif cmd == "compact":
            await self._cmd_compact(arg)
        elif cmd in ("context", "tokens"):
            await self.action_show_context()
        elif cmd == "cancel":
            await self.action_cancel_current()
        elif cmd == "quit":
            self.app.exit()

    def _has_active_session(self) -> bool:
        records = self.service.session_runner.list(self.conversation_id)
        return any(r.state in _ACTIVE_STATES for r in records)

    async def _cmd_new(self) -> None:
        if self._has_active_session():
            self.notify("任务运行中，请先 Esc 打断再开新对话", severity="warning")
            return
        conversation = await asyncio.to_thread(self.service.create_conversation)
        await self._activate_conversation(conversation.id)
        self.notify(f"已开启新对话: {conversation.id}", severity="information")

    def _cmd_list(self) -> None:
        convs = list_conversations()
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
        if self._has_active_session():
            self.notify("任务运行中，请先 Esc 打断再切换对话", severity="warning")
            return
        convs = list_conversations()
        matched = [c for c in convs if c.get("id", "").startswith(arg)]
        if len(matched) == 1:
            await self._activate_conversation(matched[0]["id"])
            self.notify(f"已切换到对话: {matched[0]['id']}", severity="information")
        elif not matched:
            self.notify(f"未找到对话: {arg}，用 /list 查看", severity="warning")
        else:
            ids = ", ".join(c["id"] for c in matched)
            self.notify(f"多个匹配，请输入更完整的 ID: {ids}", severity="warning")

    def _cmd_yolo(self, arg: str) -> None:
        normalized = arg.lower()
        status_bar = self.query_one("#status-bar", StatusBar)
        if not normalized or normalized == "status":
            state = "已开启" if self.yolo else "未开启"
            self.notify(f"YOLO 模式{state}", severity="information")
            return
        if normalized not in ("on", "off"):
            self.notify("用法: /yolo on、/yolo off 或 /yolo status", severity="warning")
            return
        if self._has_active_session():
            self.notify("任务运行中不能切换 YOLO；请先等待完成或 Esc 打断", severity="warning")
            return
        self.yolo = normalized == "on"
        status_bar.yolo = self.yolo
        if self.yolo:
            self.notify("YOLO 已开启：危险操作将由 LLM 自动审批", severity="warning")
        else:
            self.notify("YOLO 已关闭：恢复人工审批", severity="information")

    async def _cmd_compact(self, arg: str) -> None:
        """手动压缩当前对话的 Coordinator 上下文。"""
        chat_log = self.query_one("#chat-log", ChatLog)
        target = self.current_session_id or "_system"
        if self._has_active_session():
            self.notify("任务运行中，请先 Esc 打断再压缩上下文", severity="warning")
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
        )
        try:
            result = await cm.compact(keep_recent=keep_recent)
        except Exception as exc:
            self.notify(f"上下文压缩失败: {exc}", severity="error")
            return

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
        self.conversation_id = conv_id
        self.current_session_id = None
        self._target_agent_id = None
        # token 统计按对话隔离；回放历史时会从事件重建
        self._token_by_agent = {}

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

    def action_toggle_sidebar(self) -> None:
        """打开/收起侧栏；打开时刷新数据。"""
        panel = self.query_one("#side-panel", SidePanel)
        panel.display = not panel.display
        if panel.display:
            asyncio.create_task(self._refresh_agents())

    def _on_session_state_update(self, session_id: str, state: str | None) -> None:
        """session 状态变化/新 session 出现时，节流刷新侧栏 Agent 列表。"""
        if self._sidebar_refresh_scheduled:
            return
        self._sidebar_refresh_scheduled = True

        async def _later() -> None:
            await asyncio.sleep(0.3)
            self._sidebar_refresh_scheduled = False
            await self._refresh_agents()

        asyncio.create_task(_later())

    async def _refresh_agents(self) -> None:
        """从 session 记录重建侧栏的 Agent 与对话列表。"""
        try:
            records = await asyncio.to_thread(
                self.service.session_runner.list, self.conversation_id
            )
        except Exception:
            records = []
        agents: list[dict] = []
        seen: set[str] = set()
        for rec in records:  # 按 created_at DESC，首个即为该 agent 最新状态
            if rec.agent_id in seen:
                continue
            seen.add(rec.agent_id)
            agents.append(
                {
                    "agent_id": rec.agent_id,
                    "name": self._agent_display_name(rec.agent_id, rec.agent_type),
                    "state": rec.state or "",
                }
            )
        agents.sort(key=lambda a: a["agent_id"])
        panel = self.query_one("#side-panel", SidePanel)
        panel.set_agents(agents, selected=self._target_agent_id)
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
        """累计各 agent 的 token usage 并刷新计划面板。"""
        total = data.get("total")
        if isinstance(total, dict):
            agent_id = data.get("agent_id") or _COORDINATOR_AGENT_ID
            self._token_by_agent[agent_id] = total
        self._schedule_plan_refresh()

    def _on_plan_dirty(self) -> None:
        """todo_write / goal_set 更新了计划文件，刷新面板。"""
        self._schedule_plan_refresh()

    def _schedule_plan_refresh(self) -> None:
        """节流刷新计划面板（token 事件每轮一次，避免频繁 IO）。"""
        if self._plan_refresh_scheduled:
            return
        self._plan_refresh_scheduled = True

        async def _later() -> None:
            await asyncio.sleep(0.3)
            self._plan_refresh_scheduled = False
            await self._refresh_plan()

        asyncio.create_task(_later())

    def _load_plan_files(self, agent_id: str) -> tuple[list, dict]:
        """读取当前选中 agent 的 todo/goal 存储文件（同步，供 to_thread 调用）。"""
        base = get_config().data_dir / "conversations" / self.conversation_id / "plan"

        def _read(name: str):
            try:
                with open(base / name, encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return None

        return _read(f"{agent_id}_todos.json") or [], _read(f"{agent_id}_goal.json") or {}

    def _format_plan(self, agent_id: str, todos: list, goal: dict) -> str:
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
        usage = self._token_by_agent.get(agent_id)
        if usage:
            lines.append(
                f"Token: {_format_tokens(usage.get('total_tokens', 0))}"
                f" (入 {_format_tokens(usage.get('prompt_tokens', 0))}"
                f" / 出 {_format_tokens(usage.get('completion_tokens', 0))})"
            )
        return "\n".join(lines) if lines else "（暂无计划）"

    async def _refresh_plan(self) -> None:
        """重建侧栏「计划」区：显示当前选中 agent（默认主 Agent）的计划。"""
        panel = self.query_one("#side-panel", SidePanel)
        if not panel.display:
            return
        agent_id = self._target_agent_id or _COORDINATOR_AGENT_ID
        try:
            todos, goal = await asyncio.to_thread(self._load_plan_files, agent_id)
        except Exception:
            todos, goal = [], {}
        panel.set_plan(self._format_plan(agent_id, todos, goal))

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
        """切换聊天区视图与输入定向到选中的 Agent。"""
        self._target_agent_id = event.agent_id
        chat_log = self.query_one("#chat-log", ChatLog)
        chat_log.show_agent(event.agent_id)
        input_bar = self.query_one("#input-bar", InputBar)
        if event.agent_id is None:
            input_bar.target_name = None
            input_bar.follow_up = self.current_session_id is not None
        else:
            input_bar.target_name = event.label
        input_bar.focus_input()
        # 计划面板跟随选中 agent 切换
        asyncio.create_task(self._refresh_plan())

    async def on_side_panel_conversation_selected(
        self, event: SidePanel.ConversationSelected
    ) -> None:
        """切换对话；任务运行中拒绝。"""
        if event.conversation_id == self.conversation_id:
            return
        if self._has_active_session():
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
                agent_name=msg.get("agent_name", "Agent"),
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
