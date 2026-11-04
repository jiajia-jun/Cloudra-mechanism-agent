import json

import httpx
import pytest

pytest.importorskip("mcp.server")

from cloudra.services.subagent_mcp import build_server, resolve_connection


@pytest.mark.asyncio
async def test_discovery_exposes_flat_strict_tool_arguments():
    async with httpx.AsyncClient() as client:
        tools = {tool.name: tool for tool in await build_server(client).list_tools()}

    assert set(tools) == {
        "list_projects", "start_task", "send_message", "answer_question",
        "get_progress", "get_agent_progress", "get_result",
    }
    schema = tools["get_agent_progress"].input_schema
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == {"project_id", "session_id"}
    assert schema["properties"]["limit"]["maximum"] == 50
    assert schema["properties"]["include_reasoning"]["default"] is False
    assert schema["properties"]["filter"]["anyOf"][0]["maxLength"] == 4000
    assert "entry.tool_name" in schema["properties"]["filter"]["description"]
    assert len(tools["start_task"].input_schema["oneOf"]) == 2
    assert set(tools["start_task"].output_schema["required"]) == {"project_id", "session_id"}
    assert {"agents", "pending", "process"} <= set(tools["get_progress"].output_schema["required"])
    assert set(tools["get_result"].output_schema["$defs"]["Outcome"]["required"]) == {
        "terminal_event_id", "run_outcome", "summary", "verification_label",
        "completion_basis", "unresolved", "artifacts",
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("tool", "arguments"),
    [
        ("list_projects", {"sensitive-input": "sensitive-input"}),
        ("get_result", {"project_id": "P", "session_id": "S", "wait_seconds": "10"}),
        ("get_progress", {"project_id": "P", "include_process": "true"}),
        ("send_message", {"project_id": "P", "recipients": '["S"]', "content": "check"}),
        ("start_task", {"name": "new", "project_id": "P", "task": "study"}),
    ],
)
async def test_invalid_tool_arguments_fail_before_http_without_echoing_values(tool, arguments):
    def respond(_request):
        pytest.fail("invalid tool arguments reached the HTTP service")

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        result = await build_server(client).call_tool(tool, arguments)

    assert result.is_error
    assert result.structured_content["code"] == "invalid_request"
    assert "sensitive-input" not in result.content[0].text


@pytest.mark.asyncio
async def test_read_and_message_tools_route_to_existing_service():
    requests = []
    agent = {
        "session_id": "S", "name": "Coordinator", "role_id": "coordinator", "parent_session_id": None,
        "activity": "running", "detail": None, "updated_at": "2026-11-05T06:00:00Z", "active_job_ids": [],
    }

    def respond(request):
        requests.append((request.method, str(request.url), json.loads(request.content or "null")))
        if request.url.path.endswith("/api/v2/projects"):
            return httpx.Response(200, json=[{
                "id": "P", "name": "research", "created_at": "2026-11-05T06:00:00Z",
                "workspace_dir": "/private/project",
            }])
        if request.url.path.endswith("/messages"):
            return httpx.Response(200, json={"deliveries": [
                {"session_id": "S", "message_event_id": "message"},
                {"session_id": "U", "error": {"code": "not_found", "message": "not found"}},
            ]})
        if request.url.path.endswith("/response"):
            return httpx.Response(200, json={"interaction_id": "Q", "status": "responded"})
        if request.url.path.endswith("/agents/S/progress"):
            return httpx.Response(200, json={
                "agent": agent, "pending": [], "messages": [], "history_truncated": False,
            })
        if request.url.path.endswith("/progress"):
            return httpx.Response(200, json={
                "project_id": "P", "observed_at": "2026-11-05T06:00:00Z",
                "agents": [agent], "pending": [], "process": None,
            })
        return httpx.Response(200, json={"status": "pending", "agent": agent, "pending": []})

    async with httpx.AsyncClient(
        base_url="http://127.0.0.1:8000", transport=httpx.MockTransport(respond)
    ) as client:
        server = build_server(client)
        projects = await server.call_tool("list_projects", {})
        progress = await server.call_tool("get_progress", {"project_id": "P", "include_process": False})
        agent_progress = await server.call_tool("get_agent_progress", {
            "project_id": "P", "session_id": "S", "filter": "entry.kind === 'tool'",
        })
        outcome = await server.call_tool("get_result", {"project_id": "P", "session_id": "S", "wait_seconds": 20})
        message = await server.call_tool("send_message", {
            "project_id": "P", "recipients": ["S", "U"], "content": "  check the output  ",
        })
        answer = await server.call_tool("answer_question", {
            "project_id": "P", "interaction_id": "Q", "response": "  user confirmed  ",
        })

    assert projects.structured_content == {
        "projects": [{"project_id": "P", "name": "research", "created_at": "2026-11-05T06:00:00Z"}],
    }
    assert progress.structured_content["agents"] == [agent]
    assert agent_progress.structured_content["messages"] == []
    assert outcome.structured_content["status"] == "pending"
    assert not message.is_error
    assert message.structured_content["deliveries"][1]["error"]["code"] == "not_found"
    assert answer.structured_content == {"accepted": True}
    base = "http://127.0.0.1:8000/api/v2/projects"
    assert requests == [
        ("GET", base, None),
        ("GET", f"{base}/P/subagent/progress?include_process=false", None),
        ("POST", f"{base}/P/subagent/agents/S/progress", {
            "limit": 1, "filter": "entry.kind === 'tool'", "include_reasoning": False,
        }),
        ("GET", f"{base}/P/subagent/agents/S/result?wait_seconds=20", None),
        ("POST", f"{base}/P/subagent/messages", {"recipients": ["S", "U"], "content": "check the output"}),
        ("POST", f"{base}/P/interactions/Q/response", {"response": "user confirmed"}),
    ]


@pytest.mark.asyncio
async def test_partial_start_retains_recovery_project_without_repeating_the_write():
    attempts = []

    def respond(request):
        attempts.append(json.loads(request.content))
        return httpx.Response(409, json={"detail": {
            "code": "state_conflict",
            "message": "Coordinator startup failed with private-api-token",
            "project_id": "P",
        }})

    async with httpx.AsyncClient(
        base_url="http://127.0.0.1:8000",
        headers={"Authorization": "Bearer private-api-token"},
        transport=httpx.MockTransport(respond),
    ) as client:
        result = await build_server(client).call_tool("start_task", {"name": "study", "task": "explore"})

    assert attempts == [{"name": "study", "task": "explore"}]
    assert result.is_error
    assert result.structured_content["code"] == "state_conflict"
    assert result.structured_content["project_id"] == "P"
    assert "private-api-token" not in result.content[0].text
    assert "private-api-token" not in result.structured_content["message"]


@pytest.mark.asyncio
async def test_artifact_resource_download_uses_project_scope_and_preserves_content():
    def respond(request):
        assert request.url.path == "/api/v2/artifacts/A/download"
        assert request.url.params["project_id"] == "P"
        return httpx.Response(200, content=b'{"nodes":[]}', headers={"Content-Type": "application/json"})

    async with httpx.AsyncClient(
        base_url="http://127.0.0.1:8000", transport=httpx.MockTransport(respond)
    ) as client:
        server = build_server(client)
        templates = await server.list_resource_templates()
        assert [template.uri_template for template in templates] == [
            "cloudra://projects/{project_id}/artifacts/{artifact_id}",
        ]
        (contents,) = await server.read_resource("cloudra://projects/P/artifacts/A")

    assert contents.content == '{"nodes":[]}'
    assert contents.mime_type == "application/json"


def test_remote_connection_never_uses_installation_token(monkeypatch):
    monkeypatch.setenv("CLOUDRA_API_TOKEN", "private-local-token")
    monkeypatch.delenv("CLOUDRA_MCP_API_TOKEN", raising=False)
    with pytest.raises(RuntimeError, match="CLOUDRA_MCP_API_TOKEN"):
        resolve_connection("https://cloudra.example")
    monkeypatch.setenv("CLOUDRA_MCP_API_TOKEN", "remote-token")
    with pytest.raises(RuntimeError, match="HTTPS"):
        resolve_connection("http://cloudra.example")
    assert resolve_connection("https://cloudra.example") == ("https://cloudra.example", "remote-token")
    assert resolve_connection("http://127.0.0.1:9000") == ("http://127.0.0.1:9000", "private-local-token")


def test_missing_local_owner_does_not_fall_back_to_a_guessed_address(monkeypatch):
    from cloudra.services import subagent_mcp

    monkeypatch.setattr(subagent_mcp, "find_store_owner", lambda _: None)
    with pytest.raises(RuntimeError, match="running Cloudra"):
        resolve_connection(None)


def test_adapter_reads_existing_installation_token_without_creating_a_token(monkeypatch, tmp_path):
    from cloudra.services import subagent_mcp
    from cloudra.services.runtime_ownership import StoreOwner

    token_path = tmp_path / ".api_token"
    monkeypatch.delenv("CLOUDRA_API_TOKEN", raising=False)
    monkeypatch.setattr(subagent_mcp.paths, "api_token_path", lambda: token_path)
    monkeypatch.setattr(subagent_mcp, "find_store_owner", lambda _: StoreOwner(123, 8765, False))

    assert resolve_connection(None) == ("http://127.0.0.1:8765", None)
    assert not token_path.exists()

    token_path.write_text("test-token\n", encoding="utf-8")
    assert resolve_connection(None) == ("http://127.0.0.1:8765", "test-token")
