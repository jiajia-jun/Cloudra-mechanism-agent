"""新 Textual TUI 的基础测试。"""

import pytest
from textual.app import App
from textual.css.query import NoMatches

from cloudra.tui.new.app import CloudraTextualApp
from cloudra.tui.new.screens.main_screen import MainScreen
from cloudra.tui.new.widgets.chat_log import ChatLog
from cloudra.tui.new.widgets.input_bar import InputBar
from cloudra.tui.new.widgets.status_bar import StatusBar


@pytest.mark.asyncio
async def test_main_screen_composes_widgets(tmp_path, monkeypatch):
    """MainScreen 能正确组合所有基础 widgets；session 侧栏已从 UI 移除。"""
    from cloudra.config import get_config, reload_config

    data_dir = tmp_path / "data"
    monkeypatch.setenv("CLOUDRA_DATA_DIR", str(data_dir))
    reload_config()
    get_config()._ensure_dirs()

    app = CloudraTextualApp()
    async with app.run_test():
        assert isinstance(app.screen, MainScreen)
        assert app.screen.query_one("#chat-log", ChatLog)
        assert app.screen.query_one("#input-bar", InputBar)
        assert app.screen.query_one("#status-bar", StatusBar)
        with pytest.raises(NoMatches):
            app.screen.query_one("#session-tree")


@pytest.mark.asyncio
async def test_input_bar_enter_sends_message():
    """Enter 键直接发送消息（回归：TextArea 默认 Enter 只是换行）。"""
    from textual.app import App
    from textual.widgets import TextArea

    sent = []

    class TestApp(App):
        def compose(self):
            yield InputBar(id="input-bar")

        def on_input_bar_send_message(self, event: InputBar.SendMessage) -> None:
            sent.append(event.content)

    app = TestApp()
    async with app.run_test() as pilot:
        input_bar = app.query_one("#input-bar", InputBar)
        input_bar.focus_input()
        await pilot.pause()
        textarea = app.query_one("#message-input", TextArea)
        assert app.focused is textarea

        textarea.text = "hello world"
        await pilot.press("enter")
        await pilot.pause()

        assert sent == ["hello world"]
        assert textarea.text == ""


@pytest.mark.asyncio
async def test_input_bar_ctrl_enter_inserts_newline():
    """Ctrl+Enter 换行而不是发送。"""
    from textual.app import App
    from textual.widgets import TextArea

    sent = []

    class TestApp(App):
        def compose(self):
            yield InputBar(id="input-bar")

        def on_input_bar_send_message(self, event: InputBar.SendMessage) -> None:
            sent.append(event.content)

    app = TestApp()
    async with app.run_test() as pilot:
        input_bar = app.query_one("#input-bar", InputBar)
        input_bar.focus_input()
        await pilot.pause()
        textarea = app.query_one("#message-input", TextArea)
        textarea.text = "line1"
        await pilot.press("ctrl+enter")
        await pilot.pause()

        assert sent == []
        assert "\n" in textarea.text


@pytest.mark.asyncio
async def test_chat_log_switches_sessions():
    """ChatLog 能按 session 切换显示。"""
    from textual.app import App

    class TestApp(App):
        def compose(self):
            yield ChatLog(id="chat-log")

    app = TestApp()
    async with app.run_test():
        chat_log = app.query_one("#chat-log", ChatLog)
        chat_log.append_user("s1", "hello s1")
        chat_log.append_user("s2", "hello s2")

        chat_log.current_session_id = "s1"
        assert chat_log.current_session_id == "s1"

        chat_log.current_session_id = "s2"
        assert chat_log.current_session_id == "s2"


@pytest.mark.asyncio
async def test_chat_log_renders_code_block():
    """ChatLog 能解析并高亮代码块。"""
    from textual.app import App

    class TestApp(App):
        def compose(self):
            yield ChatLog(id="chat-log")

    app = TestApp()
    async with app.run_test():
        chat_log = app.query_one("#chat-log", ChatLog)
        chat_log.current_session_id = "s1"
        chat_log.start_stream("s1", "Agent")
        chat_log.append_stream_chunk("s1", "```python\nprint('hi')\n```", "Agent")
        chat_log.end_stream("s1")

        from cloudra.tui.new.widgets.code_block import CodeBlock
        code_blocks = list(app.query(CodeBlock))
        assert len(code_blocks) == 1


@pytest.mark.asyncio
async def test_approval_modal_returns_decision():
    """ApprovalModal 返回用户审批决定。"""
    from cloudra.tui.new.screens.approval_modal import ApprovalModal

    results = []

    class TestApp(App):
        def on_mount(self):
            self.push_screen(
                ApprovalModal(1, "a-1", "rm -rf /"),
                callback=lambda d: results.append(d),
            )

    app = TestApp()
    async with app.run_test() as pilot:
        await pilot.click("#approve")

    assert results == ["approved"]


@pytest.mark.asyncio
async def test_help_screen_dismisses():
    """HelpScreen 可以关闭。"""
    from cloudra.tui.new.screens.help_screen import HelpScreen

    class TestApp(App):
        def on_mount(self):
            self.push_screen(HelpScreen())

    app = TestApp()
    async with app.run_test() as pilot:
        assert isinstance(app.screen, HelpScreen)
        await pilot.press("escape")
        assert not isinstance(app.screen, HelpScreen)


def _widget_text(w) -> str:
    """提取 widget 的纯文本（拆 RichVisual 包装；Panel 取标题+正文）。"""
    r = w.render()
    inner = getattr(r, "_renderable", r)  # Textual 8: Static.render() 外包一层 RichVisual
    if hasattr(inner, "renderable"):  # rich Panel
        return f"{getattr(inner, 'title', '') or ''}\n{inner.renderable}"
    return str(inner)


@pytest.mark.asyncio
async def test_render_bridge_dispatches_session_events():
    """RenderBridge 能把 IPC 事件正确分发到 ChatLog（含终态事件）。"""
    from textual.app import App

    from cloudra.tui.new.render_bridge import RenderBridge

    class TestApp(App):
        def compose(self):
            yield ChatLog(id="chat-log")

    app = TestApp()
    async with app.run_test():
        chat_log = app.query_one("#chat-log", ChatLog)
        chat_log.current_session_id = "s1"

        bridge = RenderBridge("conv-test", chat_log)

        # 模拟 llm_chunk 事件
        bridge._dispatch({
            "kind": "session_event",
            "session_id": "s1",
            "event_type": "llm_chunk",
            "data": {"agent_name": "coordinator", "stream": "content", "delta": "你好"},
        })
        bridge._dispatch({
            "kind": "session_event",
            "session_id": "s1",
            "event_type": "llm_stream_end",
            "data": {},
        })
        # 模拟 tool_started / tool_finished
        bridge._dispatch({
            "kind": "session_event",
            "session_id": "s1",
            "event_type": "tool_started",
            "data": {"tool": "Bash", "arguments": "ls -l"},
        })
        bridge._dispatch({
            "kind": "session_event",
            "session_id": "s1",
            "event_type": "tool_finished",
            "data": {"tool": "Bash", "arguments": "ls -l", "result": "file.txt"},
        })
        # completed：已有流式正文 → 不重复显示 result
        bridge._dispatch({
            "kind": "session_event",
            "session_id": "s1",
            "event_type": "completed",
            "data": {"result": "你好"},
        })

        # ChatLog 中至少有两个 session s1 的消息（assistant + tool）
        s1_texts = [_widget_text(w) for w in chat_log._messages.get("s1", [])]
        assert len(s1_texts) >= 2
        assert sum("你好" in t for t in s1_texts) == 1  # result 未重复显示

        # 无流式输出的 completed：补显示 result
        bridge._dispatch({
            "kind": "session_event",
            "session_id": "s2",
            "event_type": "completed",
            "data": {"result": "纯结果答案"},
        })
        s2_texts = [_widget_text(w) for w in chat_log._messages.get("s2", [])]
        assert any("纯结果答案" in t for t in s2_texts)

        # failed：错误必须上屏（否则用户看到的是"agent 不回答"）
        bridge._dispatch({
            "kind": "session_event",
            "session_id": "s3",
            "event_type": "failed",
            "data": {"error": "Error code: 400"},
        })
        s3_texts = [_widget_text(w) for w in chat_log._messages.get("s3", [])]
        assert any("Error code: 400" in t for t in s3_texts)

        # cancelled：提示上屏
        bridge._dispatch({
            "kind": "session_event",
            "session_id": "s4",
            "event_type": "cancelled",
            "data": {},
        })
        s4_texts = [_widget_text(w) for w in chat_log._messages.get("s4", [])]
        assert any("已取消" in t for t in s4_texts)





# ------------------------------------------------------------------
# 斜杠命令解析
# ------------------------------------------------------------------


def test_parse_command_basic():
    from cloudra.tui.new.commands import parse_command

    assert parse_command("/help") == ("help", "")
    assert parse_command("/use abc123") == ("use", "abc123")
    assert parse_command("/compact 6") == ("compact", "6")
    assert parse_command("/yolo on") == ("yolo", "on")
    # 别名归一化
    assert parse_command("/compress") == ("compact", "")
    assert parse_command("/exit") == ("quit", "")
    # 非命令输入
    assert parse_command("hello") is None
    assert parse_command("") is None
    assert parse_command("/") is None


# ------------------------------------------------------------------
# MainScreen 命令与交互
# ------------------------------------------------------------------


def _make_app(tmp_path, monkeypatch):
    from cloudra.config import get_config, reload_config

    data_dir = tmp_path / "data"
    monkeypatch.setenv("CLOUDRA_DATA_DIR", str(data_dir))
    reload_config()
    # YAML 配置优先级高于环境变量，必须显式覆盖，否则测试会写进真实数据目录
    get_config().data_dir = data_dir
    # 不恢复用户真实的上次对话（可能有运行中的 session，干扰命令类测试）
    get_config().last_conversation_id = None
    get_config()._ensure_dirs()
    return CloudraTextualApp()


@pytest.mark.asyncio
async def test_session_commands_removed(tmp_path, monkeypatch):
    """/sessions 与 /use 已移除（session 是内部概念），按未知命令处理且不发送。"""
    app = _make_app(tmp_path, monkeypatch)
    async with app.run_test() as pilot:
        screen = app.screen
        called = []

        async def fake_send(content):
            called.append(content)

        screen._handle_send = fake_send
        await screen.on_input_bar_send_message(InputBar.SendMessage("/sessions"))
        await screen.on_input_bar_send_message(InputBar.SendMessage("/use abc"))
        await pilot.pause()
        assert called == []


@pytest.mark.asyncio
async def test_yolo_command_toggles_mode(tmp_path, monkeypatch):
    """/yolo on 切换模式并同步状态栏。"""
    app = _make_app(tmp_path, monkeypatch)
    async with app.run_test() as pilot:
        screen = app.screen
        assert screen.yolo is False
        await screen._run_command("yolo", "on")
        await pilot.pause()
        assert screen.yolo is True
        status_bar = screen.query_one("#status-bar", StatusBar)
        assert status_bar.yolo is True

        await screen._run_command("yolo", "off")
        await pilot.pause()
        assert screen.yolo is False


@pytest.mark.asyncio
async def test_unknown_command_warns(tmp_path, monkeypatch):
    """未知命令给出提示而不发送给 agent。"""
    app = _make_app(tmp_path, monkeypatch)
    async with app.run_test() as pilot:
        screen = app.screen
        called = []

        async def fake_send(content):
            called.append(content)

        screen._handle_send = fake_send
        await screen.on_input_bar_send_message(InputBar.SendMessage("/nosuchcmd"))
        await pilot.pause()
        assert called == []


@pytest.mark.asyncio
async def test_send_echoes_user_message_before_submit(tmp_path, monkeypatch):
    """发送后用户消息立即上屏（先于 submit_session 调用），返回后归入真实 session。"""
    app = _make_app(tmp_path, monkeypatch)
    async with app.run_test():
        screen = app.screen
        chat_log = screen.query_one("#chat-log", ChatLog)

        echoed_at_submit = []

        class FakeRecord:
            session_id = "a-0_run_test123"
            state = "queued"

            def to_dict(self):
                return {"session_id": self.session_id, "state": self.state}

        def checking_submit(*args, **kwargs):
            # submit 被调用时，用户消息必须已经上屏到 pending 组
            echoed_at_submit.append(len(chat_log._messages.get("_pending", [])))
            return screen.conversation_id, FakeRecord()

        screen.service.submit_session = checking_submit

        await screen._handle_send("我的任务")

        assert echoed_at_submit == [1]
        # submit 返回后 pending 消息归到真实 session
        assert "_pending" not in chat_log._messages
        assert len(chat_log._messages.get("a-0_run_test123", [])) >= 1
        assert screen.current_session_id == "a-0_run_test123"


@pytest.mark.asyncio
async def test_phase_event_updates_status_bar(tmp_path, monkeypatch):
    """phase 事件经 RenderBridge 更新状态栏文案。"""
    app = _make_app(tmp_path, monkeypatch)
    async with app.run_test() as pilot:
        screen = app.screen
        status_bar = screen.query_one("#status-bar", StatusBar)
        bridge = screen._render_bridge
        status_bar.session_id = "s1"
        status_bar.session_state = "running"

        bridge._dispatch({
            "kind": "session_event",
            "session_id": "s1",
            "event_type": "phase",
            "data": {"phase": "thinking"},
        })
        await pilot.pause()
        assert status_bar.phase == "thinking"


@pytest.mark.asyncio
async def test_compact_command_outputs_result(tmp_path, monkeypatch):
    """/compact 调用 ContextManager.compact 并把结果输出到聊天区。"""
    app = _make_app(tmp_path, monkeypatch)
    async with app.run_test() as pilot:
        screen = app.screen
        chat_log = screen.query_one("#chat-log", ChatLog)

        class FakeCM:
            def __init__(self, **kwargs):
                pass

            async def compact(self, keep_recent=4):
                return {
                    "compressed": True,
                    "original_count": 20,
                    "new_count": 5,
                    "summary_length": 300,
                }

        monkeypatch.setattr(
            "cloudra.tui.new.screens.main_screen.ContextManager", FakeCM
        )
        await screen._run_command("compact", "")
        await pilot.pause()

        msgs = chat_log._messages.get("_system", [])
        assert len(msgs) == 1


@pytest.mark.asyncio
async def test_smart_scroll_not_forced_when_scrolled_up():
    """用户上翻后新消息不强制滚到底。"""
    from textual.app import App

    class TestApp(App):
        def compose(self):
            yield ChatLog(id="chat-log")

    app = TestApp()
    async with app.run_test():
        chat_log = app.query_one("#chat-log", ChatLog)
        chat_log.current_session_id = "s1"

        scroll_calls = []
        original = chat_log.scroll_end

        def counting_scroll_end(*args, **kwargs):
            scroll_calls.append(1)
            return original(*args, **kwargs)

        chat_log.scroll_end = counting_scroll_end

        # 模拟用户上翻：scroll_y 远离底部
        chat_log.scroll_y = 0
        # max_scroll_y 是类级 property，patch 后必须恢复
        original_prop = type(chat_log).max_scroll_y
        type(chat_log).max_scroll_y = property(lambda self: 100)
        try:
            chat_log.append_user("s1", "新消息")
            assert scroll_calls == []
        finally:
            type(chat_log).max_scroll_y = original_prop


@pytest.mark.asyncio
async def test_followup_send_stays_in_same_conversation(tmp_path, monkeypatch):
    """任务完成后再次输入：同一对话里开新任务（不新建对话），并有分隔线提示。"""
    app = _make_app(tmp_path, monkeypatch)
    async with app.run_test():
        screen = app.screen
        chat_log = screen.query_one("#chat-log", ChatLog)

        create_calls = []
        orig_create = screen.service.create_conversation
        screen.service.create_conversation = (
            lambda: (create_calls.append(1) or orig_create())
        )

        class FakeRecord:
            def __init__(self, sid, state):
                self.session_id = sid
                self.state = state

        conv_at_start = screen.conversation_id

        # 第一次发送 → 任务1
        r1 = FakeRecord("a-0_run_001", "queued")
        screen.service.submit_session = (
            lambda q, conversation_id=None, yolo=False: (conversation_id, r1)
        )
        await screen._handle_send("第一条消息")
        assert screen.conversation_id == conv_at_start

        # 任务1结束后第二次发送 → 任务2，仍同一对话
        r2 = FakeRecord("a-0_run_002", "queued")
        screen.service.submit_session = (
            lambda q, conversation_id=None, yolo=False: (conversation_id, r2)
        )
        await screen._handle_send("第二条消息")

        assert screen.conversation_id == conv_at_start
        assert create_calls == []  # 发送期间没有新建对话
        assert screen.current_session_id == "a-0_run_002"
        # 出现了"新任务（同一对话）"分隔线
        divider_texts = [
            w for sid, w in chat_log._order if sid == "a-0_run_002"
        ]
        assert len(divider_texts) >= 2  # 分隔线 + 用户消息

        # 状态栏显示对话；内部跟踪当前任务（不在 UI 显示 session）
        status_bar = screen.query_one("#status-bar", StatusBar)
        assert status_bar.conversation_id == conv_at_start
        assert status_bar.session_id == "a-0_run_002"


@pytest.mark.asyncio
async def test_status_bar_shows_shared_context_info(tmp_path, monkeypatch):
    """状态栏常驻显示对话级共享上下文规模（记忆 N条≈Tk）。"""
    import asyncio as _asyncio

    app = _make_app(tmp_path, monkeypatch)
    async with app.run_test() as pilot:
        screen = app.screen
        status_bar = screen.query_one("#status-bar", StatusBar)

        # on_mount 已刷新过一次
        assert "条≈" in status_bar.context_info

        # Coordinator 流式结束 → 触发再次刷新
        bridge = screen._render_bridge
        bridge._dispatch({
            "kind": "session_event",
            "session_id": "a-0_run_ctx1",
            "event_type": "llm_stream_end",
            "data": {},
        })
        await _asyncio.sleep(0.2)
        await pilot.pause()
        assert "条≈" in status_bar.context_info


# ------------------------------------------------------------------
# 历史回放
# ------------------------------------------------------------------


def _seed_history_conversation(monkeypatch, tmp_path, conv_id=None):
    """造一个带历史任务的对话，返回 conversation_id。"""
    from cloudra import session_store
    from cloudra.config import get_config, reload_config
    from cloudra.database import ConversationDB
    from cloudra.service import CloudraService

    data_dir = tmp_path / "data"
    monkeypatch.setenv("CLOUDRA_DATA_DIR", str(data_dir))
    reload_config()
    get_config().last_conversation_id = None
    get_config()._ensure_dirs()

    if conv_id is None:
        conv_id = CloudraService().create_conversation().id
    db = ConversationDB(conv_id).init()

    # 根任务：用户提问 + agent 流式回答 + 工具卡片
    session_store.insert_queued_session(
        db,
        session_id="a-0_run_h1",
        agent_id="a-0",
        agent_type="coordinator",
        query="历史问题",
    )
    session_store.insert_session_event(
        db, "a-0_run_h1", "llm_chunk",
        {"agent_name": "coordinator", "stream": "content", "delta": "历史回答"},
    )
    session_store.insert_session_event(
        db, "a-0_run_h1", "llm_stream_end", {"agent_name": "coordinator"},
    )
    session_store.insert_session_event(
        db, "a-0_run_h1", "tool_finished",
        {"tool": "read_file", "arguments": "a.py", "result": "ok"},
    )

    # 子 agent：query 是委派任务，不应渲染为用户消息
    session_store.insert_queued_session(
        db,
        session_id="a-1_run_h1",
        agent_id="a-1",
        agent_type="executor",
        query="委派的子任务",
    )
    with db.connect() as con:
        con.execute(
            "UPDATE session SET parent_session_id = ? WHERE session_id = ?",
            ("a-0_run_h1", "a-1_run_h1"),
        )
        con.commit()
    session_store.insert_session_event(
        db, "a-1_run_h1", "llm_chunk",
        {"agent_name": "executor", "stream": "content", "delta": "子agent输出"},
    )
    session_store.insert_session_event(
        db, "a-1_run_h1", "llm_stream_end", {"agent_name": "executor"},
    )
    return conv_id


def _rendered_texts(chat_log, session_id):
    """提取某 session 组里所有 widget 的纯文本。"""
    return [_widget_text(w) for w in chat_log._messages.get(session_id, [])]


@pytest.mark.asyncio
async def test_history_replay_on_startup(tmp_path, monkeypatch):
    """启动时回放当前对话的历史任务：分隔线 + 用户提问 + agent 回答重新上屏。"""
    from cloudra.config import get_config

    conv_id = _seed_history_conversation(monkeypatch, tmp_path)
    get_config().last_conversation_id = conv_id

    app = CloudraTextualApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = app.screen
        assert screen.conversation_id == conv_id
        chat_log = screen.query_one("#chat-log", ChatLog)

        root_texts = _rendered_texts(chat_log, "a-0_run_h1")
        # 分隔线 + 用户消息 + 流式回答 + 工具卡片
        assert len(root_texts) >= 3
        assert any("历史任务" in t and "[queued]" in t for t in root_texts)
        # 分隔线不暴露内部 session id
        assert not any("a-0_run_h1" in t and "历史任务" in t for t in root_texts)
        assert any("历史问题" in t for t in root_texts)
        assert any("历史回答" in t for t in root_texts)

        child_texts = _rendered_texts(chat_log, "a-1_run_h1")
        assert any("子agent输出" in t for t in child_texts)
        # 子 agent 的委派 query 不渲染为用户消息
        assert not any("委派的子任务" in t for t in child_texts)


@pytest.mark.asyncio
async def test_history_replay_on_conversation_switch(tmp_path, monkeypatch):
    """/conv 切换对话后，目标对话的历史也会回放进聊天区。"""
    from cloudra.config import get_config, reload_config

    data_dir = tmp_path / "data"
    monkeypatch.setenv("CLOUDRA_DATA_DIR", str(data_dir))
    reload_config()
    get_config().last_conversation_id = None
    get_config()._ensure_dirs()

    target_conv = _seed_history_conversation(monkeypatch, tmp_path)

    app = CloudraTextualApp()
    async with app.run_test() as pilot:
        screen = app.screen
        assert screen.conversation_id != target_conv
        await screen._run_command("conv", target_conv)
        await pilot.pause()

        assert screen.conversation_id == target_conv
        chat_log = screen.query_one("#chat-log", ChatLog)
        root_texts = _rendered_texts(chat_log, "a-0_run_h1")
        assert any("历史问题" in t for t in root_texts)
        assert any("历史回答" in t for t in root_texts)


# ------------------------------------------------------------------
# 按钮级交互（全部 mock，不触碰真实 LLM/DB 写路径）
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_send_button_click_sends_message():
    """点击"发送"按钮与 Enter 等效。"""
    from textual.app import App

    sent = []

    class TestApp(App):
        def compose(self):
            yield InputBar(id="input-bar")

        def on_input_bar_send_message(self, event: InputBar.SendMessage) -> None:
            sent.append(event.content)

    app = TestApp()
    async with app.run_test(size=(120, 40)) as pilot:
        from textual.widgets import Button, TextArea

        app.query_one("#message-input", TextArea).text = "按钮发送的消息"
        app.query_one("#send-button", Button).press()
        await pilot.pause()
        assert sent == ["按钮发送的消息"]
        # 发送后输入框清空
        assert app.query_one("#message-input", TextArea).text == ""


@pytest.mark.asyncio
async def test_main_screen_send_button_routes_to_handle_send(tmp_path, monkeypatch):
    """MainScreen 里点发送按钮 → 路由到 _handle_send（不发送斜杠命令）。"""
    app = _make_app(tmp_path, monkeypatch)
    async with app.run_test(size=(120, 40)) as pilot:
        from textual.widgets import Button, TextArea

        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, MainScreen)
        called = []

        async def fake_send(content):
            called.append(content)

        screen._handle_send = fake_send
        screen.query_one("#message-input", TextArea).text = "点击发送"
        screen.query_one("#send-button", Button).press()
        await pilot.pause()
        assert called == ["点击发送"]


@pytest.mark.asyncio
async def test_escape_cancel_returns_immediately(tmp_path, monkeypatch):
    """Esc 取消：立即反馈，不在 UI 动作里等任务落终态（回归：取消要等半天）。"""
    import asyncio as _asyncio
    import time as _time

    app = _make_app(tmp_path, monkeypatch)
    async with app.run_test():
        screen = app.screen

        class FakeActive:
            session_id = "a-0_run_slow"
            state = "running"
            parent_session_id = None

        async def fake_active():
            return FakeActive()

        screen._find_active_record = fake_active

        started = _asyncio.Event()
        release = _asyncio.Event()
        cancel_calls = []

        async def slow_cancel(conv_id, session_id):
            cancel_calls.append((conv_id, session_id))
            started.set()
            await release.wait()  # 模拟取消很慢（卡在线程/子进程）
            return None

        screen.service.session_runner.cancel = slow_cancel

        t0 = _time.monotonic()
        await screen.action_cancel_current()
        elapsed = _time.monotonic() - t0
        assert elapsed < 1.0  # UI 动作必须立即返回

        await _asyncio.sleep(0.2)
        assert started.is_set()  # 后台取消已发起
        assert cancel_calls == [(screen.conversation_id, "a-0_run_slow")]
        release.set()
        await _asyncio.sleep(0.1)


@pytest.mark.asyncio
async def test_send_not_blocked_by_cancel_requested(tmp_path, monkeypatch):
    """任务处于 cancel_requested 时不挡发送：直接开新任务（回归：消息发不出去）。"""
    app = _make_app(tmp_path, monkeypatch)
    async with app.run_test():
        screen = app.screen

        class CancellingRecord:
            session_id = "a-0_run_dying"
            state = "cancel_requested"
            parent_session_id = None

        screen.service.session_runner.list = lambda cid: [CancellingRecord()]

        submitted = []

        class FakeRecord:
            session_id = "a-0_run_new"
            state = "queued"

        def fake_submit(q, conversation_id=None, yolo=False):
            submitted.append(q)
            return conversation_id, FakeRecord()

        screen.service.submit_session = fake_submit
        await screen._handle_send("取消后的新消息")
        assert submitted == ["取消后的新消息"]
        assert screen.current_session_id == "a-0_run_new"


@pytest.mark.asyncio
async def test_cancel_without_active_task_notifies(tmp_path, monkeypatch):
    """没有运行中任务时 Esc/cancel：提示而不是报错。"""
    app = _make_app(tmp_path, monkeypatch)
    async with app.run_test() as pilot:
        screen = app.screen
        cancel_called = []

        async def fake_cancel(conv_id, session_id):
            cancel_called.append(session_id)

        screen.service.session_runner.cancel = fake_cancel
        await screen.action_cancel_current()
        await pilot.pause()
        assert cancel_called == []


@pytest.mark.asyncio
async def test_question_mark_binding_opens_help(tmp_path, monkeypatch):
    """按 ? 打开帮助页（输入框聚焦时 ? 是打字，需先 Tab 移出焦点）。"""
    from cloudra.tui.new.screens.help_screen import HelpScreen

    app = _make_app(tmp_path, monkeypatch)
    async with app.run_test() as pilot:
        await pilot.press("tab")
        await pilot.press("?")
        await pilot.pause()
        assert isinstance(app.screen, HelpScreen)


@pytest.mark.asyncio
async def test_context_command_pushes_context_screen(tmp_path, monkeypatch):
    """/context（Ctrl+T）打开对话级上下文统计页，无需选中任务。"""
    from cloudra.tui.new.screens.context_screen import ContextScreen

    app = _make_app(tmp_path, monkeypatch)
    async with app.run_test() as pilot:
        await app.screen._run_command("context", "")
        await pilot.pause()
        assert isinstance(app.screen, ContextScreen)
        await pilot.pause()  # on_mount 异步加载内容


@pytest.mark.asyncio
async def test_approval_deny_button_submits_decision(tmp_path, monkeypatch):
    """审批弹窗点"拒绝" → 向后端提交 denied。"""
    import asyncio as _asyncio

    app = _make_app(tmp_path, monkeypatch)
    async with app.run_test() as pilot:
        screen = app.screen
        decisions = []

        async def fake_decide(conv_id, approval_id, decision, reason):
            decisions.append((approval_id, decision))

        screen.service.decide_approval = fake_decide
        screen._on_approval({"approval_id": 7, "agent_name": "a-1", "details": "rm -rf /"})
        await pilot.pause()

        status_bar = screen.query_one("#status-bar", StatusBar)
        assert status_bar.pending == 1

        await pilot.click("#deny")
        await _asyncio.sleep(0.2)
        await pilot.pause()
        assert decisions == [(7, "denied")]
        assert status_bar.pending == 0  # 计数回落


@pytest.mark.asyncio
async def test_ask_user_modal_submit_sends_answer(tmp_path, monkeypatch):
    """Agent 提问弹窗：输入回答点提交 → 向后端提交回答。"""
    import asyncio as _asyncio

    from textual.widgets import Input

    app = _make_app(tmp_path, monkeypatch)
    async with app.run_test() as pilot:
        screen = app.screen
        answers = []

        async def fake_respond(**kwargs):
            answers.append(kwargs)

        screen.service.respond_interaction_command = fake_respond
        screen._on_ask_user({
            "interaction_id": "ia-1",
            "agent_name": "a-1",
            "prompt": "要用哪种溶剂？",
        })
        await pilot.pause()

        app.screen.query_one("#ask-input", Input).value = "乙醇"
        await pilot.click("#submit")
        await _asyncio.sleep(0.2)
        await pilot.pause()
        assert len(answers) == 1
        assert answers[0]["interaction_id"] == "ia-1"
        assert answers[0]["response"] == "乙醇"


@pytest.mark.asyncio
async def test_tool_card_click_toggles_collapse():
    """长结果工具卡片默认折叠，点击展开/收起。"""
    from textual.app import App

    class TestApp(App):
        def compose(self):
            yield ChatLog(id="chat-log")

    app = TestApp()
    async with app.run_test():
        chat_log = app.query_one("#chat-log", ChatLog)
        long_result = "\n".join(f"line{i}" for i in range(30))
        chat_log.append_tool("s1", "Bash", "ls", finished=True, result=long_result)
        card = chat_log._messages["s1"][-1]
        assert card._collapsed is True

        card.on_click()
        assert card._collapsed is False
        card.on_click()
        assert card._collapsed is True


@pytest.mark.asyncio
async def test_quit_command_exits_app(tmp_path, monkeypatch):
    """/quit 退出应用。"""
    app = _make_app(tmp_path, monkeypatch)
    async with app.run_test() as pilot:
        exits = []
        app.exit = lambda *a, **k: exits.append(1)
        await app.screen._run_command("quit", "")
        await pilot.pause()
        assert exits == [1]


# ------------------------------------------------------------------
# 侧栏（Agent / 对话列表）
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sidebar_hidden_by_default_and_toggles(tmp_path, monkeypatch):
    """侧栏默认隐藏，Ctrl+B 切换显示/收起。"""
    from cloudra.tui.new.widgets.side_panel import SidePanel

    app = _make_app(tmp_path, monkeypatch)
    async with app.run_test() as pilot:
        panel = app.screen.query_one("#side-panel", SidePanel)
        assert panel.display is False
        await pilot.press("ctrl+b")
        await pilot.pause()
        assert panel.display is True
        await pilot.press("ctrl+b")
        await pilot.pause()
        assert panel.display is False


@pytest.mark.asyncio
async def test_sidebar_conversation_click_switches(tmp_path, monkeypatch):
    """点击侧栏对话项切换到该对话（无运行中任务时）。"""
    import asyncio as _asyncio

    from textual.widgets import ListItem, ListView

    from cloudra.tui.new.widgets.side_panel import SidePanel

    app = _make_app(tmp_path, monkeypatch)
    async with app.run_test() as pilot:
        screen = app.screen
        other = await _asyncio.to_thread(screen.service.create_conversation)
        assert screen.conversation_id != other.id

        screen.action_toggle_sidebar()
        await screen._refresh_agents()
        await pilot.pause()

        panel = screen.query_one("#side-panel", SidePanel)
        conv_list = panel.query_one("#conv-list", ListView)
        items = list(conv_list.query(ListItem))
        target = next(
            (i for i in items if getattr(i, "conv_id", None) == other.id), None
        )
        assert target is not None, "侧栏应列出刚创建的对话"
        conv_list.index = items.index(target)
        conv_list.focus()
        await pilot.press("enter")
        await pilot.pause()

        assert screen.conversation_id == other.id
        assert panel.display is False, "切换对话后侧栏应收起"


@pytest.mark.asyncio
async def test_sidebar_new_conversation_button(tmp_path, monkeypatch):
    """点击「＋ 新建对话」开启新对话。"""
    from textual.widgets import ListItem, ListView

    from cloudra.tui.new.widgets.side_panel import SidePanel

    app = _make_app(tmp_path, monkeypatch)
    async with app.run_test() as pilot:
        screen = app.screen
        old_id = screen.conversation_id
        screen.action_toggle_sidebar()
        await screen._refresh_agents()
        await pilot.pause()

        panel = screen.query_one("#side-panel", SidePanel)
        conv_list = panel.query_one("#conv-list", ListView)
        items = list(conv_list.query(ListItem))
        new_item = next(
            (i for i in items if getattr(i, "conv_id", None) == "__new__"), None
        )
        assert new_item is not None
        conv_list.index = items.index(new_item)
        conv_list.focus()
        await pilot.press("enter")
        await pilot.pause()

        assert screen.conversation_id != old_id


@pytest.mark.asyncio
async def test_sidebar_agent_select_filters_chat_and_targets_input(tmp_path, monkeypatch):
    """选中子 Agent：聊天区只显示它的 session，输入定向注入它的运行上下文。"""
    from types import SimpleNamespace

    from cloudra.tui.new.widgets.side_panel import SidePanel

    app = _make_app(tmp_path, monkeypatch)
    async with app.run_test() as pilot:
        screen = app.screen
        chat_log = screen.query_one("#chat-log", ChatLog)
        chat_log.append_user("a-0_run_x", "主 agent 消息")
        chat_log.append_user("a-3_task1", "子 agent 消息")

        screen.on_side_panel_agent_selected(
            SidePanel.AgentSelected("a-3", "researcher (a-3)")
        )
        await pilot.pause()

        assert chat_log.view_agent_prefix == "a-3"
        texts = [_widget_text(w) for w in chat_log.children if w.display]
        assert any("子 agent 消息" in t for t in texts)
        assert not any("主 agent 消息" in t for t in texts)

        input_bar = screen.query_one("#input-bar", InputBar)
        assert input_bar.target_name == "researcher (a-3)"

        # 子 agent 无运行中任务：拒绝注入
        sent = []

        async def fake_append(session_id, content):
            sent.append((session_id, content))

        screen._append_message = fake_append

        async def find_none(agent_id=None):
            return None

        screen._find_active_record = find_none
        await screen._handle_send("加两篇近三年的")
        assert sent == []

        # 子 agent 有运行中任务：注入它的 session
        rec = SimpleNamespace(
            session_id="a-3_task1",
            agent_id="a-3",
            state="running",
            parent_session_id="a-0_run_x",
        )

        async def find_rec(agent_id=None):
            return rec if agent_id == "a-3" else None

        screen._find_active_record = find_rec
        await screen._handle_send("加两篇近三年的")
        assert sent == [("a-3_task1", "加两篇近三年的")]

        # 选回「全部」：视图与定向都复位
        screen.on_side_panel_agent_selected(SidePanel.AgentSelected(None, "全部"))
        await pilot.pause()
        assert chat_log.view_agent_prefix is None
        assert input_bar.target_name is None
        texts = [_widget_text(w) for w in chat_log.children]
        assert any("主 agent 消息" in t for t in texts)


# ------------------------------------------------------------------
# 斜杠命令补全
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_command_suggest_popup_and_tab_completion():
    """输入 / 弹出命令补全，Tab 确认高亮候选。"""
    from textual.app import App
    from textual.widgets import OptionList, TextArea

    class TestApp(App):
        def compose(self):
            yield InputBar(id="input-bar")

    app = TestApp()
    async with app.run_test() as pilot:
        input_bar = app.query_one("#input-bar", InputBar)
        input_bar.focus_input()
        await pilot.pause()

        suggest = app.query_one("#command-suggest", OptionList)
        assert suggest.display is False

        await pilot.press("slash", "c", "o")
        await pilot.pause()
        assert suggest.display is True
        cmds = input_bar._suggest_cmds
        assert "conv" in cmds and "compact" in cmds and "context" in cmds

        await pilot.press("tab")
        await pilot.pause()
        textarea = app.query_one("#message-input", TextArea)
        assert textarea.text == f"/{cmds[0]} "
        assert suggest.display is False


@pytest.mark.asyncio
async def test_command_suggest_escape_dismisses_without_sending():
    """Esc 关闭补全弹层，不发送也不清空输入。"""
    from textual.app import App
    from textual.widgets import OptionList, TextArea

    class TestApp(App):
        def compose(self):
            yield InputBar(id="input-bar")

    app = TestApp()
    async with app.run_test() as pilot:
        input_bar = app.query_one("#input-bar", InputBar)
        input_bar.focus_input()
        await pilot.pause()
        await pilot.press("slash", "y", "o")
        await pilot.pause()
        suggest = app.query_one("#command-suggest", OptionList)
        assert suggest.display is True

        await pilot.press("escape")
        await pilot.pause()
        assert suggest.display is False
        textarea = app.query_one("#message-input", TextArea)
        assert textarea.text == "/yo"


# ------------------------------------------------------------------
# 工具结果 JSON 渲染
# ------------------------------------------------------------------


def test_format_tool_payload_plain_and_json():
    """非 JSON 原样；JSON 摊平成 key: value；{result: ...} 包装提取核心文本。"""
    from cloudra.tui.new.widgets.chat_log import _format_tool_payload

    assert _format_tool_payload("plain text") == "plain text"
    assert _format_tool_payload('{"a": 1}') == "a: 1"
    wrapped = '{"session_id": "a-3_task2", "result": "我完成了调研"}'
    out = _format_tool_payload(wrapped, is_result=True)
    assert "我完成了调研" in out
    assert "session_id" in out  # 其余字段压成元信息行
    nested_json = '{"outer": {"inner": 1}}'
    assert "\n" in _format_tool_payload(nested_json)


@pytest.mark.asyncio
async def test_tool_card_renders_parsed_json_result():
    """工具卡片展示解析后的结果文本，而不是裸 JSON。"""
    from textual.app import App

    from cloudra.tui.new.widgets.chat_log import ToolCard

    class TestApp(App):
        def compose(self):
            yield ChatLog(id="chat-log")

    app = TestApp()
    async with app.run_test():
        chat_log = app.query_one("#chat-log", ChatLog)
        chat_log.append_tool(
            "s1",
            "SubAgentLauncher",
            '{"agent_id": "a-3", "query": "调研"}',
            finished=True,
            result='{"session_id": "a-3_task2", "result": "我完成了调研，共 8 篇文献"}',
        )
        card = chat_log._messages["s1"][-1]
        assert isinstance(card, ToolCard)
        text = _widget_text(card)
        assert "我完成了调研，共 8 篇文献" in text
        assert "\\u" not in text


# ------------------------------------------------------------------
# 计划面板（目标锚点 + todo 清单 + token 用量）
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_plan_panel_shows_goal_todos_and_tokens(tmp_path, monkeypatch):
    """侧栏「计划」区渲染当前 agent 的目标、清单进度与 token 用量。"""
    import json as _json

    from textual.widgets import Static

    app = _make_app(tmp_path, monkeypatch)
    async with app.run_test() as pilot:
        screen = app.screen
        from cloudra.config import get_config

        plan_dir = (
            get_config().data_dir / "conversations" / screen.conversation_id / "plan"
        )
        plan_dir.mkdir(parents=True, exist_ok=True)
        (plan_dir / "a-0_todos.json").write_text(_json.dumps([
            {"id": "t1", "content": "查文献", "status": "done"},
            {"id": "t2", "content": "跑计算", "status": "in_progress"},
        ]), encoding="utf-8")
        (plan_dir / "a-0_goal.json").write_text(_json.dumps({
            "objective": "完成 DFT 计算",
            "completion_criteria": "能量收敛",
            "current_focus": "",
        }), encoding="utf-8")

        screen._on_token_usage("sess1", {
            "agent_id": "a-0",
            "total": {"prompt_tokens": 8000, "completion_tokens": 2345, "total_tokens": 10345},
        })

        screen.action_toggle_sidebar()
        await screen._refresh_plan()
        await pilot.pause()

        text = _widget_text(screen.query_one("#plan-view", Static))
        assert "目标: 完成 DFT 计算" in text
        assert "判据: 能量收敛" in text
        assert "查文献" in text and "跑计算" in text
        assert "进度: 1/2" in text
        assert "Token: 10.3k" in text
        assert "入 8.0k" in text


@pytest.mark.asyncio
async def test_plan_panel_empty_state_and_agent_switch(tmp_path, monkeypatch):
    """无计划文件时显示空态；切换选中 agent 后面板读对应 agent 的文件。"""
    import json as _json

    from textual.widgets import Static

    app = _make_app(tmp_path, monkeypatch)
    async with app.run_test() as pilot:
        screen = app.screen
        from cloudra.config import get_config

        plan_dir = (
            get_config().data_dir / "conversations" / screen.conversation_id / "plan"
        )
        plan_dir.mkdir(parents=True, exist_ok=True)
        (plan_dir / "a-3_todos.json").write_text(_json.dumps([
            {"id": "t1", "content": "子 agent 的任务", "status": "in_progress"},
        ]), encoding="utf-8")

        screen.action_toggle_sidebar()
        await screen._refresh_plan()
        await pilot.pause()
        text = _widget_text(screen.query_one("#plan-view", Static))
        assert "暂无计划" in text

        screen._target_agent_id = "a-3"
        await screen._refresh_plan()
        await pilot.pause()
        text = _widget_text(screen.query_one("#plan-view", Static))
        assert "子 agent 的任务" in text
        assert "进度: 0/1" in text


@pytest.mark.asyncio
async def test_render_bridge_routes_token_and_plan_events():
    """RenderBridge 把 token_usage / todo_updated / goal_updated 事件路由给回调。"""
    from textual.app import App

    from cloudra.tui.new.render_bridge import RenderBridge

    class TestApp(App):
        def compose(self):
            yield ChatLog(id="chat-log")

    app = TestApp()
    async with app.run_test():
        chat_log = app.query_one("#chat-log", ChatLog)
        token_events, plan_dirty = [], []
        bridge = RenderBridge(
            "conv-test",
            chat_log,
            on_token_usage=lambda sid, data: token_events.append((sid, data)),
            on_plan_dirty=lambda: plan_dirty.append(1),
        )
        bridge._on_session_event({
            "session_id": "s1",
            "event_type": "token_usage",
            "data": {"agent_id": "a-0", "total": {"total_tokens": 100}},
        })
        bridge._on_session_event({"session_id": "s1", "event_type": "todo_updated", "data": {}})
        bridge._on_session_event({"session_id": "s1", "event_type": "goal_updated", "data": {}})

        assert token_events == [("s1", {"agent_id": "a-0", "total": {"total_tokens": 100}})]
        assert len(plan_dirty) == 2
