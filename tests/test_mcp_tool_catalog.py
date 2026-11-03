"""External tools share native discovery, policies and invocation results."""
import asyncio

import pytest

from cloudra.runtime_v2.adapters import LegacyToolExecutor, legacy_tool_schemas
from cloudra.runtime_v2.core import RuntimeCore
from cloudra.runtime_v2.invocation import InvocationService
from cloudra.runtime_v2.policies.base import PipelineContext, ToolCall, ToolResult
from cloudra.runtime_v2.policies.permission import PermissionStage
from cloudra.runtime_v2.schemas import Project, RuntimeSettings
from cloudra.tools import ToolEntry
from cloudra.tools.registry import ToolRegistration


def external_entry(name="mcp__lab__echo", callback=None):
    async def echo(arguments):
        return ToolResult(True, "echo", {"structuredContent": arguments})

    return ToolEntry(
        cls=None, tool_name=name, tool_id=name,
        input_schema={"type": "object", "properties": {"value": {"type": "integer"}}, "required": ["value"]},
        output_schema={"type": "object"}, summary="Echo external input", tool_description="Echo external input",
        external_call=callback or echo,
        registration=ToolRegistration(module="mcp", class_name="", tool_name=name),
    )


def test_external_directory_is_scoped_and_preserves_schema():
    from cloudra.tools import get_tools_lst, use_tool_entries

    first, second = external_entry(), external_entry("mcp__other__echo")
    assert first.tool_name not in {entry.tool_name for entry in get_tools_lst()}
    with use_tool_entries([first]):
        assert first in get_tools_lst()
        assert legacy_tool_schemas([first.tool_name])[0]["function"]["parameters"] == first.input_schema
        with use_tool_entries([second]):
            assert first not in get_tools_lst()
            assert second in get_tools_lst()
        assert first in get_tools_lst()
    assert first not in get_tools_lst()


def test_external_metadata_uses_the_common_policy_projection():
    from cloudra.tools import use_tool_entries
    from cloudra.tools.capabilities import is_dag_observable, is_direct_only, role_hidden_tools, supervisor_access_for

    entry = external_entry()
    entry.registration = ToolRegistration(module="mcp", class_name="", tool_name=entry.tool_name,
        role_allowlist=frozenset({"coordinator"}))
    with use_tool_entries([entry]):
        assert entry.tool_name in role_hidden_tools("explorer")
        assert not is_direct_only(entry.tool_name)
        assert is_dag_observable(entry.tool_name)
        assert supervisor_access_for(entry.tool_name) == "none"


def test_new_agents_receive_only_their_cores_external_tools(tmp_path):
    first, second = RuntimeCore(), RuntimeCore()
    entry = external_entry()
    first.external_tools.append(entry)
    project = Project(id="p", name="p", workspace_dir=str(tmp_path))
    for core, expected in ((first, True), (second, False)):
        agent = core.agent_host.build(project=project, role=core.roles.require("coordinator"),
            parent_session_id=None, display_name=None, settings=RuntimeSettings())
        assert (entry.tool_name in agent.capabilities.tools) is expected


@pytest.mark.asyncio
async def test_external_call_keeps_permissions_and_durable_invocation(tmp_path):
    core = RuntimeCore(strict_events=True)
    core.projects["p"] = Project(id="p", name="p", workspace_dir=str(tmp_path))
    calls = []

    async def echo(arguments):
        calls.append(arguments)
        return ToolResult(True, "done", {"structuredContent": arguments})

    entry = external_entry(callback=echo)
    core.external_tools.append(entry)
    executor = LegacyToolExecutor(core)
    agent = core.agent_host.build(project=core.projects["p"], role=core.roles.require("coordinator"),
        parent_session_id=None, display_name=None, settings=RuntimeSettings())
    core.agents[agent.id] = agent
    service = InvocationService(event_writer=core.event_writer, stages=[PermissionStage()], tools=executor)
    ctx = PipelineContext(agent=agent, run_id="run", settings_snapshot=agent.settings,
        capabilities=agent.capabilities, inbox_messages=[], emit=lambda *args: None, workspace_dir=str(tmp_path))
    outcome = await service.invoke(ctx, ToolCall("one", entry.tool_name, {"value": 7}))
    assert outcome.result.is_success
    assert outcome.result.data["structuredContent"] == {"value": 7}
    assert calls == [{"value": 7}]
    types = [event.type for event in core.event_log]
    assert types.index("tool.requested") < types.index("tool.started") < types.index("tool.result_recorded") < types.index("tool.finished")
    agent.capabilities.permissions = agent.capabilities.permissions.model_copy(update={"script": False})
    blocked = await service.invoke(ctx, ToolCall("two", entry.tool_name, {"value": 8}))
    assert not blocked.result.is_success
    assert calls == [{"value": 7}]
    await core.aclose()


@pytest.mark.asyncio
async def test_parallel_scopes_do_not_leak():
    from cloudra.tools import get_tools_lst, use_tool_entries

    async def observe(entry):
        with use_tool_entries([entry]):
            await asyncio.sleep(0)
            return {item.tool_name for item in get_tools_lst() if item.external_call is not None}

    a, b = external_entry(), external_entry("mcp__other__echo")
    assert await asyncio.gather(observe(a), observe(b)) == [{a.tool_name}, {b.tool_name}]


def test_duplicate_external_name_is_rejected():
    from cloudra.tools import get_tools_lst, use_tool_entries

    with use_tool_entries([external_entry("read")]):
        with pytest.raises(RuntimeError, match="重复"):
            get_tools_lst()


@pytest.mark.asyncio
async def test_destructive_external_call_uses_existing_approval(tmp_path, monkeypatch):
    from cloudra.tools.core.permission_model import Permission

    core = RuntimeCore()
    core.projects["p"] = Project(id="p", name="p", workspace_dir=str(tmp_path))
    calls = []

    async def call(arguments):
        calls.append(arguments)
        return ToolResult(True)

    async def deny(agent, **kwargs):
        assert kwargs["tool_name"] == "mcp__lab__echo"
        return False, "denied"

    monkeypatch.setattr(core.pending, "request_approval", deny)
    entry = external_entry(callback=call)
    entry.required_permissions |= Permission.DESTRUCTIVE
    core.external_tools.append(entry)
    agent = core.agent_host.build(project=core.projects["p"], role=core.roles.require("coordinator"),
        parent_session_id=None, display_name=None, settings=RuntimeSettings())
    outcome = await LegacyToolExecutor(core).execute(agent, ToolCall("deny", entry.tool_name, {"value": 7}))
    assert not outcome.is_success
    assert calls == []


@pytest.mark.asyncio
async def test_external_images_become_workspace_artifacts_without_losing_blocks(tmp_path):
    import base64
    from pathlib import Path

    core = RuntimeCore()
    core.projects["p"] = Project(id="p", name="p", workspace_dir=str(tmp_path))
    block = {"type": "image", "mimeType": "image/png", "data": base64.b64encode(b"image-data").decode()}

    async def call(arguments):
        return ToolResult(True, "image", {"content": [block]})

    entry = external_entry(callback=call)
    core.external_tools.append(entry)
    agent = core.agent_host.build(project=core.projects["p"], role=core.roles.require("coordinator"),
        parent_session_id=None, display_name=None, settings=RuntimeSettings())
    result = await LegacyToolExecutor(core).execute(agent, ToolCall("image", entry.tool_name, {}))
    assert result.data["content"] == [block]
    image = Path(result.data["image_paths"][0])
    image.relative_to(tmp_path)
    assert image.read_bytes() == b"image-data"


@pytest.mark.asyncio
async def test_external_transport_errors_do_not_expose_connection_credentials(tmp_path, caplog):
    async def broken(arguments):
        raise RuntimeError("https://example.org/mcp?token=private-token Authorization: private-header")

    core = RuntimeCore(strict_events=True)
    core.projects["p"] = Project(id="p", name="p", workspace_dir=str(tmp_path))
    entry = external_entry(callback=broken)
    core.external_tools.append(entry)
    agent = core.agent_host.build(project=core.projects["p"], role=core.roles.require("coordinator"),
        parent_session_id=None, display_name=None, settings=RuntimeSettings())
    service = InvocationService(event_writer=core.event_writer, stages=[], tools=LegacyToolExecutor(core))
    ctx = PipelineContext(agent=agent, run_id="run", settings_snapshot=agent.settings,
        capabilities=agent.capabilities, inbox_messages=[], emit=lambda *args: None)
    outcome = await service.invoke(ctx, ToolCall("failed", entry.tool_name, {}))
    assert outcome.error.effect_state == "unknown"
    assert "private-token" not in str(list(core.event_log)) + str(outcome) + caplog.text
    assert "private-header" not in str(list(core.event_log)) + str(outcome) + caplog.text
