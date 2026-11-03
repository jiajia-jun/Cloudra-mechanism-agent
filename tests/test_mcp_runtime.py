"""Real MCP tools traverse API startup and both Agent invocation protocols."""
import asyncio
import gc
import sys
import weakref
from pathlib import Path

import pytest

from cloudra.infra.config import MCPStdioServerConfig, get_config
from cloudra.runtime_v2.adapters import legacy_tool_schemas
from cloudra.runtime_v2.core import RuntimeCore
from cloudra.runtime_v2.schemas import Command, Project, RuntimeSettings
from cloudra.runtime_v2.turn_pipeline import LLMResponse
from cloudra.services.api_v2.app import create_v2_app
from cloudra.tools import ToolEntry, external_tool_entries, get_tools_lst, use_tool_entries
from cloudra.tools.mcp import MCPToolManager
from tests.agent_scenarios import ScenarioHarness, ScriptedProvider, Step

FIXTURE = Path(__file__).parent / "fixtures" / "mcp_server.py"


def config():
    return MCPStdioServerConfig(command=sys.executable, args=[str(FIXTURE)],
        env={"MCP_FIXTURE_TOKEN": "fixture-token"})


@pytest.mark.asyncio
async def test_runner_catalog_is_inherited_without_cross_context_finalizer_errors(tmp_path, monkeypatch):
    """Collect an abandoned live runner from a different task's Context."""
    cleanup_errors = []
    original_unraisablehook = sys.unraisablehook
    target_coroutine_id = None

    def record_cleanup_error(error):
        if id(error.object) == target_coroutine_id:
            cleanup_errors.append(error.exc_value)
        else:
            original_unraisablehook(error)

    monkeypatch.setattr(sys, "unraisablehook", record_cleanup_error)
    observed_catalogs = []
    destroyed_tasks = []
    target_task_name = None
    loop = asyncio.get_running_loop()
    original_handler = loop.get_exception_handler()

    def record_destroyed_task(loop, context):
        if (context.get("message") == "Task was destroyed but it is pending!"
                and context["task"].get_name() == target_task_name):
            destroyed_tasks.append(context["task"].get_name())
        elif original_handler is not None:
            original_handler(loop, context)
        else:
            loop.default_exception_handler(context)

    class WaitingProvider(ScriptedProvider):
        async def complete(self, agent, messages, tools, **kwargs):
            observed_catalogs.append(tuple(entry.tool_name for entry in external_tool_entries()))
            await asyncio.Event().wait()

    async def start_abandoned_runner():
        harness = await ScenarioHarness.start(tmp_path, provider=WaitingProvider(), attach_store=False)
        harness.core.external_tools.append(ToolEntry(None, "mcp__owner__echo", "mcp__owner__echo", {}))
        agent = await harness.spawn("coordinator", protocol="traditional")
        await harness.wait_for(lambda: bool(observed_catalogs), "runner waiting in provider")
        task = harness.runner.task_for(agent.id)
        return weakref.ref(task), task.get_name(), id(task.get_coro())

    loop.set_exception_handler(record_destroyed_task)
    try:
        caller_entries = [ToolEntry(None, "mcp__caller__echo", "mcp__caller__echo", {})]
        with use_tool_entries(caller_entries):
            task_ref, target_task_name, target_coroutine_id = await start_abandoned_runner()
            assert external_tool_entries() is caller_entries
            gc.collect()
            assert external_tool_entries() is caller_entries
        assert task_ref() is None
        assert observed_catalogs == [("mcp__owner__echo",)]
        assert len(destroyed_tasks) == 1
        assert cleanup_errors == []
    finally:
        loop.set_exception_handler(original_handler)


@pytest.mark.asyncio
async def test_api_startup_discovers_before_new_agents_and_closes_its_entries(tmp_path, monkeypatch):
    pytest.importorskip("mcp")
    monkeypatch.setattr(get_config(), "mcp_servers", {"lab": config()})
    core = RuntimeCore()
    project = Project(id="p", name="p", workspace_dir=str(tmp_path))
    old = core.agent_host.build(project=project, role=core.roles.require("coordinator"),
        parent_session_id=None, display_name=None, settings=RuntimeSettings())
    app = await asyncio.to_thread(create_v2_app, core)
    async with app.router.lifespan_context(app):
        assert len(core.external_tools) == 2
        agent = core.agent_host.build(project=project, role=core.roles.require("coordinator"),
            parent_session_id=None, display_name=None, settings=RuntimeSettings())
        assert "mcp__lab__echo" in agent.capabilities.tools
        assert "mcp__lab__echo" not in old.capabilities.tools
        with use_tool_entries(core.external_tools):
            assert legacy_tool_schemas(["mcp__lab__echo"])[0]["function"]["parameters"]["$defs"]
    assert core.external_tools == []
    assert "mcp__lab__echo" not in {entry.tool_name for entry in get_tools_lst()}


@pytest.mark.asyncio
@pytest.mark.parametrize("protocol", ["traditional", "javascript"])
async def test_real_mcp_tool_runs_through_agent_scenario(protocol, tmp_path):
    pytest.importorskip("mcp")
    args = {"payload": {"text": "scenario", "repeat": 2}}
    if protocol == "traditional":
        steps = [Step(tools=[("mcp__lab__echo", args)]), Step(stop=True)]
    else:
        steps = [Step(tools=[("js_exec", {"code":
            'const r = await tools.mcp__lab__echo({payload:{text:"scenario",repeat:2}}); text(r.data.structuredContent);'
        })]), Step(stop=True)]
    harness = await ScenarioHarness.start(tmp_path, provider=ScriptedProvider(default=steps), workspace_dir=tmp_path)
    try:
        async with MCPToolManager({"lab": config()}).lifespan(harness.core.external_tools):
            agent = await harness.spawn("coordinator", protocol=protocol)
            await harness.wait_terminal(agent)
            results = [event for event in harness.core.event_log if event.type == "tool.result_recorded"
                and event.data.get("tool_name") == "mcp__lab__echo"]
            assert len(results) == 1
            assert results[0].data["result"]["data"]["structuredContent"] == {"value": "scenarioscenario"}
            assert results[0].data["result"]["is_success"] is True
    finally:
        await harness.aclose()


@pytest.mark.asyncio
async def test_restored_agent_continues_native_tools_when_mcp_server_is_removed(tmp_path):
    pytest.importorskip("mcp")

    class ChooseMCP(ScriptedProvider):
        async def select_tool_names(self, agent, messages, *, resolved_settings):
            return LLMResponse(content='["mcp__lab__echo"]')

    harness = await ScenarioHarness.start(tmp_path, provider=ChooseMCP(default=[Step(stop=True)]), workspace_dir=tmp_path)
    async with MCPToolManager({"lab": config()}).lifespan(harness.core.external_tools):
        agent = await harness.spawn("coordinator", protocol="javascript")
        await harness.wait_terminal(agent)
        assert "mcp__lab__echo" in harness.core.contexts.prefix_state(agent.id)["meta"]["tool_document_revisions"]
        await harness.aclose()
    evidence = tmp_path / "evidence.txt"
    evidence.write_text("evidence")
    provider = ScriptedProvider(default=[Step(tools=[("js_exec", {"code":
        'const r = await tools.read({path:' + repr(str(evidence)) + '}); text(r.is_success);'
    })]), Step(stop=True)])
    restored = await ScenarioHarness.restore(tmp_path, provider=provider)
    try:
        resumed = restored.core.agents[agent.id]
        assert "mcp__lab__echo" in resumed.capabilities.tools
        await restored.bus.execute(Command(type="agent.message", target={"session_id": resumed.id},
            payload={"content": "Read the evidence file"}))
        await restored.wait_for(lambda: provider.call_count() >= 2, "native tools after MCP removal")
        await restored.wait_terminal(resumed)
        results = [event for event in restored.core.event_log if event.type == "tool.result_recorded"
            and event.data.get("tool_name") == "read"]
        assert results[-1].data["result"]["is_success"]
        assert "mcp__lab__echo" in resumed.capabilities.tools
    finally:
        await restored.aclose()
