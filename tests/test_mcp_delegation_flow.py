from __future__ import annotations

import asyncio
import json
import os
import shutil
import socket
import sys
from pathlib import Path

import httpx
import pytest
import uvicorn
from click.testing import CliRunner

from cloudra.cli import cli
from cloudra.infra.flocks import locked
from cloudra.persistence.paths import runtime_api_lock_path
from cloudra.runtime_v2.schemas import Command
from cloudra.services.api_v2.app import create_v2_app
from tests.agent_scenarios import ScenarioHarness, ScriptedProvider, Step

ROOT = Path(__file__).resolve().parents[1]


def test_mcp_cli_command_is_registered():
    result = CliRunner().invoke(cli, ["mcp", "--help"])
    assert result.exit_code == 0, result.output
    assert "--api-url" in result.output


@pytest.mark.asyncio
async def test_batch_messages_return_scoped_durable_receipts(tmp_path):
    harness = await ScenarioHarness.start(tmp_path)
    local = await harness.spawn("coordinator", query="")
    other_project = (await harness.bus.execute(
        Command(type="project.create", payload={"name": "other"})
    )).data
    foreign = (await harness.bus.execute(Command(
        type="agent.spawn", target={"project_id": other_project.id},
        payload={"role_id": "coordinator"},
    ))).data
    app = create_v2_app(core=harness.core)
    transport = httpx.ASGITransport(app=app, client=("127.0.0.1", 4000))
    async with app.router.lifespan_context(app), httpx.AsyncClient(
        transport=transport, base_url="http://localhost",
    ) as http:
        response = await http.post(f"/api/v2/projects/{local.project_id}/messages", json={
            "recipients": [local.id, foreign.id, local.id],
            "content": "Consider the supplied structure.",
        })
        assert response.status_code == 200
        own, denied = response.json()["deliveries"]
        assert own["session_id"] == local.id
        assert denied["error"]["code"] == "not_found"
        event = harness.core.event_log.get(own["message_event_id"])
        assert event.session_id == local.id
        assert event.type == "agent.message_injected"
        assert not harness.core.event_log.query_session(foreign.id, types={"agent.message_injected"})


@pytest.mark.asyncio
async def test_mcp_plugin_stdio_delegates_to_live_cloudra(tmp_path, monkeypatch):
    pytest.importorskip("mcp")
    from mcp import Client, StdioServerParameters

    token = "local-test-token"
    monkeypatch.setenv("CLOUDRA_API_TOKEN", token)
    release = asyncio.Event()
    provider = ScriptedProvider(by_role={"coordinator": [
        Step(text="Scripted delivery.", stop=True, wait_for=release),
    ]})
    harness = await asyncio.to_thread(ScenarioHarness, tmp_path, provider=provider)
    app = create_v2_app(core=harness.core)
    config_path = ROOT / "plugins/cloudra-subagent/mcp.json"
    launch = json.loads(config_path.read_text())["mcpServers"]["cloudra"]

    lock_path = runtime_api_lock_path(harness.store.path)
    with locked(lock_path), socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        url = f"http://127.0.0.1:{listener.getsockname()[1]}"
        server = uvicorn.Server(uvicorn.Config(app, lifespan="on", log_level="error"))
        task = asyncio.create_task(server.serve(sockets=[listener]))
        try:
            async with asyncio.timeout(10):
                while not server.started:
                    if task.done():
                        await task
                    await asyncio.sleep(0.01)
            params = StdioServerParameters(
                command=sys.executable,
                args=["-c", "from cloudra.cli import main; main()", *launch["args"], "--api-url", url],
                env={
                    "CLOUDRA_API_TOKEN": token,
                    "CLOUDRA_CONFIG_FILE": os.environ["CLOUDRA_CONFIG_FILE"],
                    "CLOUDRA_RUNTIME_STORE": str(harness.store.path),
                    "PYTHONPATH": str(ROOT),
                },
                cwd=ROOT,
            )

            async def invoke(client, name, args=None):
                result = await client.call_tool(name, args)
                assert not result.is_error, result.content
                assert result.structured_content is not None, result.content
                return result.structured_content

            async with Client(params, mode="legacy", read_timeout_seconds=15) as client:
                assert {tool.name for tool in (await client.list_tools()).tools} >= {
                    "list_projects", "start_task", "get_progress", "get_agent_progress", "get_result",
                }
                assert await invoke(client, "list_projects") == {"projects": []}
                ref = await invoke(client, "start_task", {
                    "name": "Scripted mechanism study", "task": "Investigate the supplied structure.",
                })
                progress = await invoke(client, "get_progress", {"project_id": ref["project_id"]})
                assert progress["agents"][0]["session_id"] == ref["session_id"]
                assert (await invoke(client, "get_result", ref))["status"] == "pending"
                assert len((await invoke(client, "list_projects"))["projects"]) == 1

            release.set()
            if shutil.which("lsof"):
                params = params.model_copy(update={"args": params.args[:-2]})
            async with Client(params, read_timeout_seconds=15) as client:
                delivered = await invoke(client, "get_result", {**ref, "wait_seconds": 8})
                assert delivered["status"] == "finished"
                result = delivered["result"]
                assert result["run_outcome"] == "succeeded"
                assert result["verification_label"] == "unverified"
                assert result["terminal_event_id"]
                assert result["summary"]
                last = await invoke(client, "get_agent_progress", ref)
                assert last["messages"][0]["kind"] == "assistant"
                quickjs = ROOT / "cloudra/runtime_v2/js_host/node_modules/quickjs-emscripten"
                if shutil.which("node") and quickjs.is_dir():
                    filtered = await invoke(client, "get_agent_progress", {
                        **ref, "filter": "entry.kind === 'assistant' && entry.text.length > 0",
                    })
                    assert filtered["messages"] == last["messages"]
                assert len(provider.calls) == 1
        finally:
            release.set()
            server.should_exit = True
            await task
