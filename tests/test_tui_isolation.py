"""TUI 进程隔离：runtime 元数据、SessionRecord 还原、假死只重启界面。"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from cloudra.tui.new.control import (
    IsolatedControlService,
    create_tui_service,
    session_record_from_dict,
)
from cloudra.tui.new.runtime_proc import (
    clear_runtime_meta,
    health_url,
    inline_mode,
    runtime_pid_path,
    runtime_url_path,
    write_runtime_meta,
)


def test_inline_mode_env(monkeypatch):
    monkeypatch.delenv("CLOUDRA_TUI_INLINE", raising=False)
    assert inline_mode() is False
    monkeypatch.setenv("CLOUDRA_TUI_INLINE", "1")
    assert inline_mode() is True


def test_runtime_meta_roundtrip(tmp_path: Path):
    write_runtime_meta(tmp_path, url="http://127.0.0.1:9876", pid=4242)
    assert runtime_url_path(tmp_path).read_text(encoding="utf-8").strip() == (
        "http://127.0.0.1:9876"
    )
    assert runtime_pid_path(tmp_path).read_text(encoding="utf-8").strip() == "4242"
    clear_runtime_meta(tmp_path)
    assert not runtime_url_path(tmp_path).exists()
    assert health_url("http://127.0.0.1:9876/") == "http://127.0.0.1:9876/api/health"


def test_session_record_from_dict_fills_required():
    record = session_record_from_dict(
        {
            "session_id": "a-0_run_abc",
            "state": "running",
            "agent_id": "a-0",
            "agent_type": "coordinator",
        }
    )
    assert record.session_id == "a-0_run_abc"
    assert record.state == "running"
    assert record.orchestration_mode  # default present


def test_create_tui_service_inline_ignores_url(monkeypatch):
    monkeypatch.setenv("CLOUDRA_TUI_INLINE", "1")
    monkeypatch.setenv("CLOUDRA_TUI_RUNTIME_URL", "http://127.0.0.1:1")
    service = create_tui_service()
    assert not isinstance(service, IsolatedControlService)


def test_create_tui_service_isolated(monkeypatch):
    monkeypatch.delenv("CLOUDRA_TUI_INLINE", raising=False)
    monkeypatch.setenv("CLOUDRA_TUI_RUNTIME_URL", "http://127.0.0.1:18000")
    service = create_tui_service()
    assert isinstance(service, IsolatedControlService)
    assert service._base_url == "http://127.0.0.1:18000"


@pytest.mark.asyncio
async def test_isolated_submit_posts_to_runtime(monkeypatch):
    monkeypatch.delenv("CLOUDRA_TUI_INLINE", raising=False)
    service = IsolatedControlService("http://127.0.0.1:18000")
    fake_resp = MagicMock()
    fake_resp.status_code = 202
    fake_resp.content = b'{"session_id":"a-0_run_x","state":"queued"}'
    fake_resp.json.return_value = {"session_id": "a-0_run_x", "state": "queued"}
    fake_resp.raise_for_status = MagicMock()
    client = MagicMock()
    client.is_closed = False
    client.request = AsyncMock(return_value=fake_resp)
    service._client = client

    conv_id, record = await service.submit_session_async(
        "hello",
        conversation_id="c" + "0" * 31,
        yolo=True,
        orchestration_mode="dag_guided",
    )
    assert conv_id.startswith("c")
    assert record.session_id == "a-0_run_x"
    assert record.state == "queued"
    client.request.assert_awaited()
    args, kwargs = client.request.await_args
    assert args[0] == "POST"
    assert "sessions" in args[1]
    assert kwargs["json"]["yolo"] is True
    assert kwargs["json"]["orchestration_mode"] == "dag_guided"
    assert "working_directory" in kwargs["json"]

    with pytest.raises(RuntimeError, match="隔离"):
        service.session_runner.submit("x", conv_id)


@pytest.mark.asyncio
async def test_isolated_submit_defaults_working_directory_to_tui_cwd(tmp_path, monkeypatch):
    """隔离控制面缺省应发送 TUI 进程 cwd，而不是把空值交给 runtime。"""
    monkeypatch.delenv("CLOUDRA_TUI_INLINE", raising=False)
    monkeypatch.chdir(tmp_path)
    service = IsolatedControlService("http://127.0.0.1:18000")
    fake_resp = MagicMock()
    fake_resp.status_code = 202
    fake_resp.content = b'{"session_id":"a-0_run_x","state":"queued"}'
    fake_resp.json.return_value = {"session_id": "a-0_run_x", "state": "queued"}
    fake_resp.raise_for_status = MagicMock()
    client = MagicMock()
    client.is_closed = False
    client.request = AsyncMock(return_value=fake_resp)
    service._client = client

    await service.submit_session_async(
        "hello",
        conversation_id="c" + "0" * 31,
    )
    body = client.request.await_args.kwargs["json"]
    assert body["working_directory"] == str(tmp_path.resolve())


@pytest.mark.asyncio
async def test_isolated_append_forwards_working_directory(tmp_path, monkeypatch):
    """追问 JSON 必须带 working_directory，resume 才能补上空的 session 目录。"""
    monkeypatch.delenv("CLOUDRA_TUI_INLINE", raising=False)
    service = IsolatedControlService("http://127.0.0.1:18000")
    fake_resp = MagicMock()
    fake_resp.status_code = 200
    fake_resp.content = b'{"command_id":"cmd","state":"applied","session":{"session_id":"a-4_task1","state":"running"}}'
    fake_resp.json.return_value = {
        "command_id": "cmd",
        "state": "applied",
        "session": {"session_id": "a-4_task1", "state": "running"},
    }
    fake_resp.raise_for_status = MagicMock()
    client = MagicMock()
    client.is_closed = False
    client.post = AsyncMock(return_value=fake_resp)
    service._client = client

    workspace = str(tmp_path.resolve())
    await service.append_session_message_command(
        command_id="cmd",
        conversation_id="c" + "0" * 31,
        session_id="a-4_task1",
        content="继续",
        working_directory=workspace,
    )
    body = client.post.await_args.kwargs["json"]
    assert body["content"] == "继续"
    assert body["working_directory"] == workspace


@pytest.mark.asyncio
async def test_isolated_cancel_signals_locally_when_http_hangs(tmp_path, monkeypatch):
    """runtime 事件循环卡死时 Esc 仍应先落 cancel_requested（经 IPC 可打断 Agent）。"""
    import asyncio as _asyncio

    from cloudra.persistence.database import ConversationDB
    from cloudra.services import session_store

    monkeypatch.delenv("CLOUDRA_TUI_INLINE", raising=False)
    conv_id = "conv_iso_cancel_test"
    session_id = "a-0_run_iso_cancel"
    db = ConversationDB(conv_id).init()
    session_store.insert_queued_session(
        db,
        session_id=session_id,
        agent_id="a-0",
        agent_type="coordinator",
        query="q",
    )
    session_store.update_session_fields(db, session_id, {"state": "running"})

    service = IsolatedControlService("http://127.0.0.1:18000")

    async def hang(*_a, **_k):
        await _asyncio.sleep(30)
        return None

    service._request_json = hang  # type: ignore[method-assign]

    t0 = _asyncio.get_event_loop().time()
    record = await service.session_runner.cancel(conv_id, session_id)
    elapsed = _asyncio.get_event_loop().time() - t0
    assert elapsed < 5.0  # 不能干等 HTTP
    assert record is not None
    assert record.state == "cancel_requested"
    assert service.session_runner.get(conv_id, session_id).state == "cancel_requested"


@pytest.mark.asyncio
async def test_isolated_force_cancel_marks_killed_without_hanging(tmp_path, monkeypatch):
    import asyncio as _asyncio

    from cloudra.persistence.database import ConversationDB
    from cloudra.services import session_store

    monkeypatch.delenv("CLOUDRA_TUI_INLINE", raising=False)
    conv_id = "conv_iso_force_cancel"
    session_id = "a-0_run_iso_force"
    db = ConversationDB(conv_id).init()
    session_store.insert_queued_session(
        db,
        session_id=session_id,
        agent_id="a-0",
        agent_type="coordinator",
        query="q",
    )
    session_store.update_session_fields(db, session_id, {"state": "cancel_requested"})

    service = IsolatedControlService("http://127.0.0.1:18000")

    async def hang_post(*_a, **_k):
        await _asyncio.sleep(30)
        raise AssertionError("should be timed out")

    client = MagicMock()
    client.is_closed = False
    client.post = hang_post
    service._client = client

    t0 = _asyncio.get_event_loop().time()
    record = await service.session_runner.force_cancel(conv_id, session_id)
    elapsed = _asyncio.get_event_loop().time() - t0
    assert elapsed < 5.0
    assert record is not None
    assert record.state == "killed"


@pytest.mark.asyncio
async def test_double_esc_force_cancel_window(tmp_path, monkeypatch):
    """3 秒内第二次 Esc 走 force_cancel。"""
    import asyncio as _asyncio

    from cloudra.tui.new.screens.main_screen import MainScreen

    screen = object.__new__(MainScreen)
    screen.conversation_id = "conv_force_esc"
    screen.current_session_id = "a-0_run_f"
    screen._cancel_at = None
    screen._cancel_session_id = None
    calls: list[tuple[str, str]] = []

    class Runner:
        async def cancel(self, conv, sid):
            calls.append(("cancel", sid))

        async def force_cancel(self, conv, sid):
            calls.append(("force", sid))

    class Svc:
        session_runner = Runner()

    screen.service = Svc()

    class FakeActive:
        session_id = "a-0_run_f"
        state = "running"
        parent_session_id = None

    async def fake_active(**_k):
        return FakeActive()

    screen._find_active_record = fake_active
    notified: list[str] = []
    screen.notify = lambda msg, severity="information": notified.append(msg)

    await screen.action_cancel_current()
    await _asyncio.sleep(0.05)
    assert calls == [("cancel", "a-0_run_f")]
    assert "再按 Esc 强制终止" in notified[-1]

    await screen.action_cancel_current()
    await _asyncio.sleep(0.05)
    assert calls[-1] == ("force", "a-0_run_f")
    assert notified[-1] == "已强制终止任务"


def test_sigquit_exit_detection():
    import signal

    from cloudra.tui.new.watchdog import _is_sigquit_exit

    assert _is_sigquit_exit(-signal.SIGQUIT)
    assert _is_sigquit_exit(128 + signal.SIGQUIT)
    assert not _is_sigquit_exit(0)
    assert not _is_sigquit_exit(1)
