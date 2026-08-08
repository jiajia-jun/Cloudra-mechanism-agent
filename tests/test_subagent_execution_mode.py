"""Sub-agent execution mode tests: desktop defaults to in-process, subprocess is opt-in."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from cloudra import session_store
from cloudra.database import ConversationDB
from cloudra.runtime_profile import subagent_execution_mode


@pytest.fixture
def isolated_runtime(tmp_path, monkeypatch):
    """隔离数据目录，并强制桌面 runtime（屏蔽外部环境变量）。"""
    from cloudra.config import get_config

    monkeypatch.setenv("CLOUDRA_MOBILE_MODE", "false")
    monkeypatch.delenv("CLOUDRA_SUBAGENT_MODE", raising=False)
    cfg = get_config()
    monkeypatch.setattr(cfg, "data_dir", tmp_path)
    cfg._ensure_dirs()
    ConversationDB("mode-parent").init()
    return tmp_path


def _make_tool():
    from cloudra.tools.Managetool.subagent_launcher import SubAgentLauncher

    tool = SubAgentLauncher()
    tool.subagent = SimpleNamespace(
        conversation_id="mode-parent",
        working_directory="/tmp",
    )
    return tool


def _request_state(session_id: str) -> str:
    db = ConversationDB("mode-parent")
    with db.connect() as con:
        row = con.execute(
            "SELECT state FROM subagent_requests WHERE session_id = ?",
            (session_id,),
        ).fetchone()
    return row[0] if row else None


def test_subagent_execution_mode_defaults_and_override(monkeypatch):
    monkeypatch.setenv("CLOUDRA_MOBILE_MODE", "false")
    monkeypatch.delenv("CLOUDRA_SUBAGENT_MODE", raising=False)
    assert subagent_execution_mode() == "inprocess"

    monkeypatch.setenv("CLOUDRA_SUBAGENT_MODE", "subprocess")
    assert subagent_execution_mode() == "subprocess"

    # mobile runtime 永远是进程内执行，环境变量不能强行切换。
    monkeypatch.setenv("CLOUDRA_MOBILE_MODE", "true")
    assert subagent_execution_mode() == "inprocess"


@pytest.mark.asyncio
async def test_desktop_waiting_subagent_defaults_to_in_process(isolated_runtime, monkeypatch):
    """桌面端默认与 Android 一致：同步子任务在当前进程内 await run_executor。"""
    from cloudra.tools.Managetool.subagent_launcher import SubAgentLauncher_input_schema

    calls: list[tuple[int, str, str]] = []

    async def fake_run_executor(task_id: int, database_path: str, session_id: str):
        calls.append((task_id, database_path, session_id))
        db = ConversationDB.from_path(database_path)
        session_store.create_session_record(
            db,
            session_id=session_id,
            agent_id="a-1",
            agent_type="explorer",
            parent_session_id=None,
            query="inspect the desktop workspace",
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        await session_store.afinalize_session(
            db, session_id, "completed", result="desktop in-process child result"
        )
        await session_store.afinalize_task(db, task_id, session_id, "done")

    monkeypatch.setattr("cloudra.runtime.executor.run_executor", fake_run_executor)

    tool = _make_tool()
    result = await tool.tool_call(
        SubAgentLauncher_input_schema(
            agent_id="a-1",
            query="inspect the desktop workspace",
            is_wait=True,
        ),
        session=None,
    )

    assert len(calls) == 1
    assert calls[0][2] == result.session_id
    assert result.result == "desktop in-process child result"


@pytest.mark.asyncio
async def test_waiting_subagent_subprocess_override_spawns_process(isolated_runtime, monkeypatch):
    """CLOUDRA_SUBAGENT_MODE=subprocess 是逃生通道：恢复每任务一个子进程。"""
    from cloudra.tools.Managetool.subagent_launcher import SubAgentLauncher_input_schema

    monkeypatch.setenv("CLOUDRA_SUBAGENT_MODE", "subprocess")

    spawn_calls: list[tuple] = []

    class _FakeStdout:
        async def readline(self) -> bytes:
            return b""

    class _FakeProcess:
        def __init__(self):
            self.stdout = _FakeStdout()

        async def wait(self) -> int:
            return 0

    async def fake_create_subprocess_exec(*args, **kwargs):
        spawn_calls.append((args, kwargs))
        return _FakeProcess()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

    async def fail_if_in_process(*_args, **_kwargs):
        raise AssertionError("subprocess 模式下不应进程内执行")

    monkeypatch.setattr("cloudra.runtime.executor.run_executor", fail_if_in_process)

    tool = _make_tool()
    result = await tool.tool_call(
        SubAgentLauncher_input_schema(
            agent_id="a-1",
            query="inspect the desktop workspace",
            is_wait=True,
        ),
        session=None,
    )

    assert len(spawn_calls) == 1
    args, kwargs = spawn_calls[0]
    assert "-m" in args
    assert "cloudra.runtime.executor" in args
    assert kwargs.get("env") is not None
    assert result.session_id != "error"


@pytest.mark.asyncio
async def test_desktop_async_subagent_defaults_to_in_process(isolated_runtime, monkeypatch):
    """桌面端异步子任务默认同进程协程调度（state=running），不再挂 ready 等 worker。"""
    from cloudra.tools.Managetool.subagent_launcher import SubAgentLauncher_input_schema

    scheduled: list = []

    def fake_create_mobile_task(coro):
        scheduled.append(coro)
        coro.close()  # 本测试不真正执行，避免 "never awaited" 警告
        return None

    monkeypatch.setattr(
        "cloudra.runtime.mobile_tasks.create_mobile_task", fake_create_mobile_task
    )

    tool = _make_tool()
    result = await tool.tool_call(
        SubAgentLauncher_input_schema(
            agent_id="a-1",
            query="background desktop task",
            is_wait=False,
        ),
        session=None,
    )

    assert len(scheduled) == 1
    assert result.session_id != "error"
    assert _request_state(result.session_id) == "running"


@pytest.mark.asyncio
async def test_async_subagent_subprocess_override_emits_ready(isolated_runtime, monkeypatch):
    """子进程模式下异步子任务保持旧行为：state=ready 并广播 subagent_request_ready。"""
    from cloudra.tools.Managetool.subagent_launcher import SubAgentLauncher_input_schema

    monkeypatch.setenv("CLOUDRA_SUBAGENT_MODE", "subprocess")

    emitted: list[tuple] = []

    async def fake_aemit(conversation_id, kind, **kwargs):
        emitted.append((conversation_id, kind, kwargs))

    monkeypatch.setattr("cloudra.events.aemit", fake_aemit)

    tool = _make_tool()
    result = await tool.tool_call(
        SubAgentLauncher_input_schema(
            agent_id="a-1",
            query="background desktop task",
            is_wait=False,
        ),
        session=None,
    )

    assert result.session_id != "error"
    assert _request_state(result.session_id) == "ready"
    assert any(kind == "subagent_request_ready" for _, kind, _ in emitted)
