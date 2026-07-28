"""Android single-process runtime capability tests."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any

import pytest

from cloudra import session_store
from cloudra.database import ConversationDB
from cloudra.runtime_profile import filter_tools_for_runtime, is_mobile_runtime
from cloudra.tools import ToolEntry
from cloudra.tools_class import Tool, input_schema, output_schema


class _NoArgs(input_schema):
    pass


class _Result(output_schema):
    message: str


class _ForbiddenBash(Tool):
    tool_id: str = "mobile-forbidden"
    tool_name: str = "bashtools"
    tool_description: str = "test-only forbidden tool"
    input_schema: Any = _NoArgs
    output_schema: Any = _Result
    called: bool = False

    async def tool_call(self, user_input, session):
        self.called = True
        return _Result(message="must not run")


def _entry(tool_cls: type[Tool]) -> ToolEntry:
    return ToolEntry(
        cls=tool_cls,
        tool_name=tool_cls._get_field_default("tool_name") or "",
        tool_id=tool_cls._get_field_default("tool_id") or "",
        input_schema=tool_cls._get_field_default("input_schema"),
    )


def test_mobile_runtime_can_be_exercised_on_desktop(monkeypatch):
    monkeypatch.setenv("CLOUDRA_MOBILE_MODE", "true")
    assert is_mobile_runtime() is True

    entries = [
        SimpleNamespace(tool_name="edit_file"),
        SimpleNamespace(tool_name="SubAgentLauncher"),
        SimpleNamespace(tool_name="schedule"),
        SimpleNamespace(tool_name="bashtools"),
        SimpleNamespace(tool_name="submit_compute_job"),
    ]
    assert [entry.tool_name for entry in filter_tools_for_runtime(entries)] == [
        "edit_file",
        "SubAgentLauncher",
        "schedule",
    ]


def test_desktop_runtime_keeps_registered_tools(monkeypatch):
    monkeypatch.setenv("CLOUDRA_MOBILE_MODE", "false")
    entries = [
        SimpleNamespace(tool_name="edit_file"),
        SimpleNamespace(tool_name="bashtools"),
    ]
    assert filter_tools_for_runtime(entries) == entries


def test_packaged_app_uses_durable_flet_storage(tmp_path, monkeypatch):
    from cloudra.config import get_config
    from cloudra.mobile_storage import configure_app_storage

    monkeypatch.setenv("FLET_APP_STORAGE_DATA", str(tmp_path))
    storage = configure_app_storage()

    assert storage.packaged is True
    assert storage.workspace == (tmp_path / "workspace").resolve()
    assert storage.workspace.is_dir()
    assert get_config().data_dir == (tmp_path / "cloudra-data").resolve()
    assert get_config().config_file == (tmp_path / "config.yaml").resolve()


@pytest.mark.asyncio
async def test_dispatcher_cannot_execute_mobile_hidden_tool(tmp_path, monkeypatch):
    """Hiding a schema is insufficient: the dispatcher must reject it too."""

    from cloudra.agent import Follower
    from cloudra.config import get_config
    from cloudra.react import reAct

    monkeypatch.setenv("CLOUDRA_MOBILE_MODE", "true")
    db_path = str(tmp_path / "mobile.db")
    ConversationDB.from_path(db_path).init()
    monkeypatch.setattr("cloudra.react.get_database_path", lambda _cid: db_path)
    monkeypatch.setattr("cloudra.react.get_tools_lst", lambda: [_entry(_ForbiddenBash)])
    monkeypatch.setattr(get_config(), "data_dir", tmp_path)

    agent = Follower(
        id="a-mobile",
        name="mobile",
        prompt="test",
        query="test",
        conversation_id="mobile-dispatch",
    )
    react = reAct(agent)
    stopped = await react.act_result(
        [
            {
                "id": "call-1",
                "type": "function",
                "function": {"name": "bashtools", "arguments": "{}"},
            }
        ]
    )

    assert stopped is False
    context = await agent.get_context()
    tool_messages = [block for block in context if block.get("role") == "tool"]
    assert len(tool_messages) == 1
    assert "找不到工具: bashtools" in tool_messages[0]["content"]
    assert "must not run" not in json.dumps(tool_messages, ensure_ascii=False)


@pytest.mark.asyncio
async def test_waiting_subagent_runs_in_current_process(tmp_path, monkeypatch):
    """The Android launcher directly awaits run_executor; it never calls subprocess."""

    from cloudra.config import get_config
    from cloudra.tools.Managetool.subagent_launcher import (
        SubAgentLauncher,
        SubAgentLauncher_input_schema,
    )

    monkeypatch.setenv("CLOUDRA_MOBILE_MODE", "true")
    cfg = get_config()
    monkeypatch.setattr(cfg, "data_dir", tmp_path)
    cfg._ensure_dirs()
    ConversationDB("mobile-parent").init()

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
            query="inspect the mobile workspace",
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        await session_store.afinalize_session(
            db, session_id, "completed", result="mobile child result"
        )
        await session_store.afinalize_task(db, task_id, session_id, "done")

    monkeypatch.setattr("cloudra.runtime.executor.run_executor", fake_run_executor)

    tool = SubAgentLauncher()
    tool.subagent = SimpleNamespace(
        conversation_id="mobile-parent",
        working_directory=str(tmp_path),
    )
    result = await tool.tool_call(
        SubAgentLauncher_input_schema(
            agent_id="a-1",
            query="inspect the mobile workspace",
            is_wait=True,
        ),
        session=None,
    )

    assert len(calls) == 1
    assert calls[0][2] == result.session_id
    assert result.result == "mobile child result"
