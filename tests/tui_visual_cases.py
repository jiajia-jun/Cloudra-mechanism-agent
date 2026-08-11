"""Deterministic legacy Textual cases used to freeze the current UI contract."""

from __future__ import annotations

import asyncio
import inspect
import json
import os
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.segment import Segment
from textual.app import App, ComposeResult
from textual.widgets import Button, Input, Label, Static

from cloudra.tui.new.screens.approval_modal import ApprovalModal
from cloudra.tui.new.screens.ask_user_modal import AskUserModal
from cloudra.tui.new.transcript_render import InteractionAction, RenderContext, compile_record
from cloudra.tui.new.widgets.chat_log import ChatLog
from cloudra.tui.new.widgets.side_panel import SidePanel
from cloudra.tui.new.widgets.status_bar import StatusBar

_FIXTURE = Path(__file__).parent / "fixtures" / "tui_visual_baseline.json"
_STYLES = Path(__file__).parents[1] / "cloudra" / "tui" / "new" / "styles.tcss"
CaseBuilder = Callable[["VisualCaseApp"], Awaitable[None] | None]


class VisualCaseApp(App[None]):
    """Small in-memory app that exercises the widgets without services or IPC."""

    CSS_PATH = _STYLES

    def __init__(self, build: CaseBuilder) -> None:
        super().__init__()
        self._build = build
        self._capture_roots: list[Any] = []
        self._capture_screen = False

    def compose(self) -> ComposeResult:
        yield ChatLog(id="chat-log")
        yield SidePanel(id="side-panel")
        yield StatusBar(id="status-bar")

    async def on_mount(self) -> None:
        result = self._build(self)
        if inspect.isawaitable(result):
            await result

    def capture(self, *widgets: Any) -> None:
        self._capture_roots.extend(widgets)

    def capture_modal(self) -> None:
        self._capture_screen = True


def _chat(app: VisualCaseApp) -> ChatLog:
    return app.query_one("#chat-log", ChatLog)


def _welcome(app: VisualCaseApp) -> None:
    app.capture(_chat(app))


def _user(app: VisualCaseApp) -> None:
    chat = _chat(app)
    chat.append_user("s1", "请计算乙醇的构象。")
    app.capture(chat)


async def _failed_user(app: VisualCaseApp) -> None:
    chat = _chat(app)
    handle = chat.append_user("s1", "这条消息发送失败。")
    chat.mark_send_failed(handle)
    app.capture(chat)


def _assistant_plain(app: VisualCaseApp) -> None:
    chat = _chat(app)
    chat.append_stream_chunk("s1", "普通 assistant 回复。", "coordinator")
    chat.end_stream("s1")
    app.capture(chat)


def _markdown(app: VisualCaseApp) -> None:
    chat = _chat(app)
    chat.append_stream_chunk("s1", "# 结果\n\n- 能量降低\n- 构象稳定", "coordinator")
    chat.end_stream("s1")
    app.capture(chat)


def _reasoning(app: VisualCaseApp) -> None:
    chat = _chat(app)
    chat.append_reasoning_chunk("s1", "先检查收敛条件。", "coordinator")
    chat.append_stream_chunk("s1", "计算已完成。", "coordinator")
    chat.end_stream("s1")
    app.capture(chat)


def _tool_running(app: VisualCaseApp) -> None:
    chat = _chat(app)
    chat.append_tool("s1", "Bash", "pwd")
    app.capture(chat)


def _tool_finished(app: VisualCaseApp) -> None:
    chat = _chat(app)
    chat.append_tool("s1", "Bash", "pwd", finished=True, result="/tmp/project")
    app.capture(chat)


def _tool_collapsed(app: VisualCaseApp) -> None:
    chat = _chat(app)
    result = "\n".join(f"line {index}" for index in range(12))
    chat.append_tool("s1", "Bash", "pytest", finished=True, result=result)
    app.capture(chat)


async def _tool_expanded(app: VisualCaseApp) -> None:
    chat = _chat(app)
    result = "\n".join(f"line {index}" for index in range(12))
    handle = chat.append_tool("s1", "Bash", "pytest", finished=True, result=result)
    await chat.activate_region(handle, InteractionAction.TOGGLE_TOOL)
    app.capture(chat)


def _decoded_json(app: VisualCaseApp) -> None:
    chat = _chat(app)
    chat.append_stream_chunk("s1", '{"energy": -154.23, "unit": "kcal/mol"}', "coordinator")
    chat.end_stream("s1")
    app.capture(chat)


def _code_copy(app: VisualCaseApp) -> None:
    chat = _chat(app)
    chat.append_stream_chunk("s1", "```python\nprint('hello cloudra')\n```", "coordinator")
    chat.end_stream("s1")
    app.capture(chat)


def _file_states(app: VisualCaseApp) -> None:
    chat = _chat(app)
    for status in ("applied", "proposed", "declined", "failed"):
        chat.append_file_change("s1", f"calc/{status}.py", status)
    app.capture(chat)


def _supervisor(app: VisualCaseApp) -> None:
    chat = _chat(app)
    chat.append_supervisor_review("s1", "通过", "计算设置与结果一致。")
    app.capture(chat)


def _alert(app: VisualCaseApp) -> None:
    chat = _chat(app)
    chat.append_alert("s1", "任务失败", "Gaussian 未收敛。")
    app.capture(chat)


def _stream_preview(app: VisualCaseApp) -> None:
    chat = _chat(app)
    # 超过流式窗口阈值即可触发预览裁剪，无需手动 flush
    chat.append_reasoning_chunk("s1", "r" * 3000, "coordinator")
    chat.append_stream_chunk("s1", "c" * 5000, "coordinator")
    app.capture(chat)


def _sidebar(app: VisualCaseApp) -> None:
    sidebar = app.query_one("#side-panel", SidePanel)
    sidebar.display = True
    sidebar.set_agents([{"agent_id": "a-0", "name": "coordinator", "state": "running"}])
    sidebar.set_conversations(
        [{"id": "conv-123456789012", "state": "idle", "last_active": "2026-08-02T10:30:00"}],
        "conv-123456789012",
    )
    sidebar.set_plan("目标：冻结 TUI 基线\n- 采集快照\n- 记录性能")
    app.capture(sidebar)


def _status(app: VisualCaseApp) -> None:
    status = app.query_one("#status-bar", StatusBar)
    status.conversation_id = "conv-123456"
    status.context_info = "42条消息≈8.2k tokens"
    status.yolo = True
    status.pending = 2
    status.session_state = "running"
    status.phase = "thinking"
    app.capture(status)


def _approval(app: VisualCaseApp) -> None:
    app.push_screen(ApprovalModal(1, "coordinator", "允许读取结果文件？", "Bash", "cat result.log", "只读操作"))
    app.capture_modal()


def _ask_user(app: VisualCaseApp) -> None:
    app.push_screen(AskUserModal("interaction-1", "coordinator", "要使用哪种溶剂？", "乙醇"))
    app.capture_modal()


VISUAL_CASES: dict[str, CaseBuilder] = {
    "welcome": _welcome,
    "user": _user,
    "failed_user": _failed_user,
    "assistant_plain": _assistant_plain,
    "markdown": _markdown,
    "reasoning": _reasoning,
    "tool_running": _tool_running,
    "tool_finished": _tool_finished,
    "tool_collapsed": _tool_collapsed,
    "tool_expanded": _tool_expanded,
    "decoded_json": _decoded_json,
    "code_copy": _code_copy,
    "file_states": _file_states,
    "supervisor": _supervisor,
    "alert": _alert,
    "stream_preview": _stream_preview,
    "sidebar": _sidebar,
    "status": _status,
    "approval": _approval,
    "ask_user": _ask_user,
}


def _leaf_widgets(root: Any) -> list[Any]:
    children = list(root.children)
    if not children and isinstance(root, (Static, Label, Button, Input)):
        return [root]
    leaves: list[Any] = []
    for child in children:
        leaves.extend(_leaf_widgets(child))
    return leaves


def _render_rows(widget: Any) -> list[dict[str, Any]]:
    console = Console(width=100, color_system=None, force_terminal=False)
    visual = widget.render()
    renderable = getattr(visual, "_renderable", visual)
    segments = list(console.render(renderable))
    rows = Segment.split_lines(segments)
    label = f"{widget.__class__.__name__}#{widget.id or ''}"
    return [
        {
            "widget": label,
            "segments": [
                {"text": segment.text, "style": str(segment.style or "")}
                for segment in row
                if segment.text
            ],
        }
        for row in rows
        if any(segment.text for segment in row)
    ]


def _chat_log_rows(chat_log: ChatLog) -> list[dict[str, Any]]:
    """Capture the virtual ChatLog as deterministic text/style rows."""
    # Use the same 100-column reference width as the compiled-semantics tests
    # so the visual baseline stays comparable across implementations.
    width = 100
    context = RenderContext(Console(width=width, force_terminal=False, color_system=None))
    label = f"ChatLog#{chat_log.id or ''}"
    rows: list[dict[str, Any]] = []
    for record_id in chat_log.visible_record_ids:
        record = chat_log.store.get(record_id)
        compiled = compile_record(record, width, context)
        for strip in compiled.strips:
            segments = [
                {"text": segment.text, "style": str(segment.style or "")}
                for segment in strip
                if segment.text
            ]
            if segments:
                rows.append({"widget": label, "segments": segments})
    return rows


def semantic_snapshot(app: VisualCaseApp) -> list[dict[str, Any]]:
    """Return deterministic text/style rows for the current visual case.

    The capture is semantic rather than pixel-based: it preserves the Rich text
    segments, including panel borders and syntax colours, while omitting terminal
    cursor and blink state.  ChatLog is virtual, so it is rendered through the
    transcript compiler instead of its child widget tree.
    """
    roots = [app.screen] if app._capture_screen else app._capture_roots
    snapshot: list[dict[str, Any]] = []
    for root in roots:
        if isinstance(root, ChatLog):
            snapshot.extend(_chat_log_rows(root))
        else:
            for widget in _leaf_widgets(root):
                snapshot.extend(_render_rows(widget))
    return snapshot


def write_snapshot(path: Path, snapshots: dict[str, list[dict[str, Any]]]) -> None:
    """Write a baseline only when the explicit update opt-in is present."""
    if os.environ.get("CLOUDRA_UPDATE_TUI_SNAPSHOT") != "1":
        raise PermissionError("Set CLOUDRA_UPDATE_TUI_SNAPSHOT=1 to update the visual baseline.")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(snapshots, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


async def _capture_all() -> dict[str, list[dict[str, Any]]]:
    snapshots: dict[str, list[dict[str, Any]]] = {}
    for name, build in VISUAL_CASES.items():
        app = VisualCaseApp(build)
        async with app.run_test(size=(100, 36)) as pilot:
            await pilot.pause()
            snapshots[name] = semantic_snapshot(app)
    return snapshots


def main() -> None:
    if os.environ.get("CLOUDRA_UPDATE_TUI_SNAPSHOT") != "1":
        raise SystemExit("Set CLOUDRA_UPDATE_TUI_SNAPSHOT=1 to update the visual baseline.")
    write_snapshot(_FIXTURE, asyncio.run(_capture_all()))


if __name__ == "__main__":
    main()
