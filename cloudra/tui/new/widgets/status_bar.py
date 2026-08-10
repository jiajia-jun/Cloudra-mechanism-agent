"""底部状态栏 Widget。"""

from __future__ import annotations

import time

from rich.text import Text
from textual.reactive import reactive
from textual.widgets import Static

_PHASE_LABELS = {
    "starting": "启动中",
    "thinking": "思考中",
    "acting": "执行中",
    "waiting": "等待提醒",
}

_ACTIVE_STATES = {"queued", "running", "cancel_requested"}

_SPINNER_FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
# Elapsed time is displayed to whole seconds; refreshing the spinner four times
# per second only keeps WSL/terminal compositors busy without adding information.
_REFRESH_INTERVAL = 1.0


class StatusBar(Static):
    """显示对话 + 当前任务活动状态：spinner + phase + 计时 + 待处理计数。

    对话（conversation）是持久上下文，状态栏显示对话 id 与共享上下文规模；
    session_id 仅作内部响应目标（跟踪运行中任务的 phase/state），不在栏上显示。
    """

    conversation_id = reactive("")
    session_id = reactive("")
    session_state = reactive("")
    yolo = reactive(False)
    phase = reactive("")
    pending = reactive(0)
    # 对话级共享上下文的摘要，如 "42条≈8.2k"；空字符串表示未知
    context_info = reactive("")
    compaction_info = reactive("")
    # 模型原生网页搜索适配器名（空 = 未启用，走传统 web_search 工具）
    native_search = reactive("")
    # 编排模式：standard / dag_record / dag_guided（standard 不额外显示）
    orch_mode = reactive("standard")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._frame = 0
        self._started_at: float | None = None
        self._last_render_key: tuple | None = None
        self._timer = None

    def on_mount(self) -> None:
        self._timer = self.set_interval(_REFRESH_INTERVAL, self._tick, pause=True)
        self._sync_timer()
        self._refresh()

    def _sync_timer(self) -> None:
        if self._timer is None:
            return
        active = self.session_state in _ACTIVE_STATES or bool(self.compaction_info)
        (self._timer.resume if active else self._timer.pause)()

    def watch_conversation_id(self, conversation_id: str) -> None:
        self._refresh()

    def watch_session_id(self, session_id: str) -> None:
        self._refresh()

    def watch_session_state(self, state: str) -> None:
        if state in _ACTIVE_STATES and self._started_at is None:
            self._started_at = time.monotonic()
        elif state not in _ACTIVE_STATES:
            self._started_at = None
            self.phase = ""
        self._sync_timer()
        self._refresh()

    def watch_yolo(self, yolo: bool) -> None:
        self._refresh()

    def watch_phase(self, phase: str) -> None:
        self._refresh()

    def watch_pending(self, pending: int) -> None:
        self._refresh()

    def watch_context_info(self, context_info: str) -> None:
        self._refresh()

    def watch_compaction_info(self, compaction_info: str) -> None:
        self._sync_timer()
        self._refresh()

    def watch_native_search(self, native_search: str) -> None:
        self._refresh()

    def watch_orch_mode(self, orch_mode: str) -> None:
        self._refresh()

    def _tick(self) -> None:
        if self.session_state in _ACTIVE_STATES or self.compaction_info:
            self._frame += 1
            self._refresh()

    def _elapsed(self) -> str:
        if self._started_at is None:
            return ""
        seconds = int(time.monotonic() - self._started_at)
        return f"{seconds // 60:02d}:{seconds % 60:02d}"

    def _refresh(self) -> None:
        state = self.session_state
        elapsed = self._elapsed() if state in _ACTIVE_STATES else ""
        render_key = (
            state,
            self.phase,
            self._frame % len(_SPINNER_FRAMES) if state in _ACTIVE_STATES else -1,
            elapsed,
            self.conversation_id,
            self.context_info,
            self.yolo,
            self.pending,
            self.compaction_info,
            self.native_search,
            self.orch_mode,
        )
        if render_key == self._last_render_key:
            return
        self._last_render_key = render_key

        text = Text()
        if self.compaction_info:
            spinner = _SPINNER_FRAMES[self._frame % len(_SPINNER_FRAMES)]
            text.append(f"{spinner} {self.compaction_info}", style="bold magenta")
        elif state in _ACTIVE_STATES:
            spinner = _SPINNER_FRAMES[self._frame % len(_SPINNER_FRAMES)]
            label = _PHASE_LABELS.get(self.phase) or state
            text.append(f"{spinner} {label}", style="bold green")
            if elapsed:
                text.append(f" {elapsed}", style="green")
        else:
            text.append(f"○ {state or '空闲'}", style="bright_black")

        if self.conversation_id:
            text.append(f" | 对话 …{self.conversation_id[-6:]}", style="cyan")
        if self.context_info:
            text.append(f" | 上下文 {self.context_info}", style="magenta")
        if self.native_search:
            text.append(f" | 联网·{self.native_search}", style="bold yellow")
        if self.orch_mode != "standard":
            orch_label = {"dag_record": "DAG·记录", "dag_guided": "DAG·引导"}.get(
                self.orch_mode, self.orch_mode
            )
            text.append(f" | {orch_label}", style="bold cyan")
        mode = "YOLO" if self.yolo else "审批"
        text.append(f" | {mode}")
        if self.pending > 0:
            text.append(f" | ※ {self.pending} 待处理", style="bold red")
        self.update(text)
