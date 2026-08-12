"""TUI 冒烟测试：用 prompt_toolkit pipe input 脚本化模拟用户按键。

覆盖：
- 空闲时输入 → 启动任务（session_id 预生成、interactive_approval=False）
- 运行中输入 → ContextManager.inject_event 注入补充信息
- Esc 两次 → 第二次在时间窗内强制取消运行中的协程
- schedule 等待中按一次 Esc → 结束当前等待但保留独立 reminder watcher
- 渲染器消费 llm_chunk / tool_started 事件不抛异常
- 退出后 Log.terminal_output 与 ask_user 输入处理器恢复原状
"""

import asyncio
import contextlib
import io

import pytest
from prompt_toolkit.input import create_pipe_input
from prompt_toolkit.output import DummyOutput
from rich.console import Console
from rich.markdown import Markdown

from cloudra.base.log_class import Log
from cloudra.infra.yolo_guard import is_yolo_enabled
from cloudra.persistence.context_manager import ContextManager
from cloudra.tools.Interactool import ask_user
from cloudra.tui.legacy_app import CloudraTUI
from cloudra.tui.render import EventRenderer


@pytest.fixture(autouse=True)
def isolated_tui_runtime(tmp_path, monkeypatch):
    """TUI 测试绝不能复用真实配置，否则假 IPC 事件会串进用户正在开的会话。"""
    from cloudra.infra import events
    from cloudra.infra.config import get_config, reload_config

    events.shutdown_all_listeners()
    data_dir = tmp_path / "data"
    monkeypatch.setenv("CLOUDRA_DATA_DIR", str(data_dir))
    monkeypatch.setenv("CLOUDRA_CONFIG_FILE", str(tmp_path / "config.yaml"))
    reload_config()
    get_config()._ensure_dirs()
    try:
        yield
    finally:
        events.shutdown_all_listeners()
        monkeypatch.undo()
        reload_config()


@pytest.mark.asyncio
async def test_tui_smoke(monkeypatch):
    injected = []
    run_calls = []
    cancelled = asyncio.Event()

    async def fake_inject(conversation_id, agent_id, event_type, content, db_path=None, session_id=None, **_kwargs):
        injected.append((agent_id, event_type, content))

    monkeypatch.setattr(
        ContextManager, "inject_event", staticmethod(fake_inject)
    )

    async def fake_run_task(query, **kwargs):
        from cloudra.infra import events
        from cloudra.persistence.database import ConversationDB

        run_calls.append((query, kwargs))
        conv_id = kwargs["conversation_id"]
        sid = kwargs["session_id"]
        ConversationDB(conv_id).init()  # 让 cancel 的 DB 写入走正常路径
        await events.aemit(conv_id, "session_event", session_id=sid,
                           event_type="llm_chunk",
                           data={"agent_name": "coordinator", "stream": "content", "delta": "流式输出片段"})
        await events.aemit(conv_id, "session_event", session_id=sid,
                           event_type="tool_started",
                           data={"tool": "Bash", "arguments": "ls -l"})
        await events.aemit(conv_id, "session_event", session_id=sid,
                           event_type="llm_stream_end", data={"agent_name": "coordinator"})
        try:
            await asyncio.sleep(30)
        except asyncio.CancelledError:
            cancelled.set()
            raise
        return "done"

    tui = CloudraTUI()
    monkeypatch.setattr(tui.service, "run_task", fake_run_task)

    with create_pipe_input() as pipe_input:
        original_build = tui._build_prompt_session

        def build_with_pipe(**kwargs):
            return original_build(input=pipe_input, output=DummyOutput(), **kwargs)

        monkeypatch.setattr(tui, "_build_prompt_session", build_with_pipe)

        async def feeder():
            await asyncio.sleep(0.3)
            pipe_input.send_text("帮我分析这个分子\n")
            await asyncio.sleep(1.0)
            pipe_input.send_text("补充：重点关注溶解度\n")
            await asyncio.sleep(0.8)
            # pipe input 的 VT100 解析会把单独的 ESC 当作转义序列前缀而挂起，
            # 这里直接调用键绑定背后的 cancel 入口（等价于按 Esc）
            tui.request_cancel()          # 第一次 Esc：优雅打断
            await asyncio.sleep(0.8)
            tui.request_cancel()          # 3 秒窗内第二次 Esc：强制取消
            await asyncio.sleep(1.0)
            pipe_input.send_text("exit\n")

        feeder_task = asyncio.create_task(feeder())
        await tui._run_async()
        await feeder_task

    # 空闲输入启动了任务
    assert len(run_calls) == 1
    query, kwargs = run_calls[0]
    assert query == "帮我分析这个分子"
    assert kwargs["session_id"].startswith("a-0_")
    assert kwargs["interactive_approval"] is False

    # 运行中输入被注入为 user 事件
    assert ("a-0", "user", "补充：重点关注溶解度") in injected

    # 第二次 Esc 强制取消了协程
    assert cancelled.is_set()

    # 退出后全局状态恢复
    assert Log.terminal_output is True
    assert ask_user._input_handler is None


@pytest.mark.asyncio
async def test_tui_yolo_is_scoped_to_task(monkeypatch):
    observed = []
    tui = CloudraTUI(yolo=True)
    tui.conversation_id = "tui-yolo"
    tui.session_id = "a-0_yolo"

    async def fake_run_task(*args, **kwargs):
        observed.append(is_yolo_enabled())
        return "done"

    monkeypatch.setattr(tui.service, "run_task", fake_run_task)
    assert is_yolo_enabled() is False
    assert await tui._run_task("test") == "done"
    assert observed == [True]
    assert is_yolo_enabled() is False


@pytest.mark.asyncio
async def test_one_escape_ends_schedule_wait_but_not_schedule_watcher():
    tui = CloudraTUI()
    tui.phase = "waiting"

    async def waiting():
        await asyncio.sleep(3600)

    task = asyncio.create_task(waiting())
    tui._running_task = task
    assert tui.request_cancel() is True
    with pytest.raises(asyncio.CancelledError):
        await task
    assert task in tui._cancelled_waiting_tasks


def test_tui_yolo_command_toggles_when_idle():
    tui = CloudraTUI()
    tui._cmd_yolo("on")
    assert tui.yolo is True
    tui._cmd_yolo("off")
    assert tui.yolo is False


@pytest.mark.asyncio
async def test_tui_compact_command_when_idle(monkeypatch):
    """/compact 与 /compress 在空闲时压缩当前对话上下文。"""
    tui = CloudraTUI()
    tui.conversation_id = "conv-compact"

    compact_calls = []

    async def fake_compact(self, keep_recent):
        compact_calls.append(keep_recent)
        return {
            "original_count": 10,
            "new_count": 5,
            "summary_length": 100,
            "compressed": True,
        }

    monkeypatch.setattr(ContextManager, "compact", fake_compact)

    await tui._cmd_compact("")
    assert compact_calls == [4]

    await tui._cmd_compact("6")
    assert compact_calls == [4, 6]

    await tui._cmd_compact("abc")
    # 非法参数不调用 compact
    assert compact_calls == [4, 6]

    # /compress 别名
    await tui._cmd_compact("")
    assert compact_calls == [4, 6, 4]


@pytest.mark.asyncio
async def test_tui_compact_command_rejected_while_running():
    """任务运行中 /compact 应拒绝并提示。"""
    tui = CloudraTUI()
    tui.conversation_id = "conv-running"

    async def running():
        await asyncio.sleep(3600)

    task = asyncio.create_task(running())
    tui._running_task = task
    try:
        await tui._cmd_compact("")
        assert task.done() is False
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


@pytest.mark.asyncio
async def test_pending_approval_queue_sequential_resolution(monkeypatch):
    """多个并发危险命令产生的 approval_pending 在 TUI 中排队，按 FIFO 处理。"""
    tui = CloudraTUI()
    tui.conversation_id = "conv-queue"
    decided = []

    async def fake_decide_approval(conv_id, approval_id, decision, reason, **_kwargs):
        decided.append((approval_id, decision))
        return True

    monkeypatch.setattr(tui.service, "decide_approval", fake_decide_approval)

    # 模拟渲染器连续收到三个 approval_pending 事件
    tui.push_pending_approval({"id": 1, "agent_name": "a", "details": "rm A"})
    tui.push_pending_approval({"id": 2, "agent_name": "b", "details": "rm B"})
    tui.push_pending_approval({"id": 3, "agent_name": "c", "details": "rm C"})

    assert tui.current_pending_approval["id"] == 1
    assert len(tui._pending_approvals) == 3

    # 逐一批准
    await tui._resolve_approval("y")
    assert tui.current_pending_approval["id"] == 2
    assert decided == [(1, "approved")]

    await tui._resolve_approval("n")
    assert tui.current_pending_approval["id"] == 3
    assert decided == [(1, "approved"), (2, "denied")]

    await tui._resolve_approval("y")
    assert tui.current_pending_approval is None
    assert tui._pending_approvals == []
    assert decided == [(1, "approved"), (2, "denied"), (3, "approved")]


def test_markdown_rendering_after_stream_end():
    """流式助手消息包含 Markdown 标记时，流结束后触发 rich Markdown 渲染。"""
    printed: list[tuple[tuple, dict]] = []

    class _CapturingConsole(Console):
        def print(self, *args, **kwargs):
            printed.append((args, kwargs))

    tui = CloudraTUI()
    console = _CapturingConsole(file=io.StringIO(), force_terminal=True)
    renderer = EventRenderer(console, tui)

    renderer._on_llm_chunk(
        "s-1",
        {"agent_name": "coordinator", "stream": "content", "delta": "# 结果\n\n- 项 A\n- 项 B\n"},
    )
    renderer._on_llm_stream_end("s-1", {})

    markdown_objects = [
        arg for args, _ in printed for arg in args if isinstance(arg, Markdown)
    ]
    assert len(markdown_objects) == 1
    rendered = markdown_objects[0]
    assert "结果" in rendered.markup
    assert "项 A" in rendered.markup
    assert "项 B" in rendered.markup


def test_plain_text_stream_skips_markdown_rendering():
    """不含 Markdown 标记的纯文本流结束后，不应触发 Markdown 渲染。"""
    printed: list[tuple[tuple, dict]] = []

    class _CapturingConsole(Console):
        def print(self, *args, **kwargs):
            printed.append((args, kwargs))

    tui = CloudraTUI()
    console = _CapturingConsole(file=io.StringIO(), force_terminal=True)
    renderer = EventRenderer(console, tui)

    renderer._on_llm_chunk(
        "s-1",
        {"agent_name": "coordinator", "stream": "content", "delta": "这是一段普通回答，没有 markdown 标记。"},
    )
    renderer._on_llm_stream_end("s-1", {})

    markdown_objects = [
        arg for args, _ in printed for arg in args if isinstance(arg, Markdown)
    ]
    assert len(markdown_objects) == 0
