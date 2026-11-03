"""MCP configuration and shared transport behavior, without third-party services."""

import asyncio
import builtins
import importlib.util
import json
import socket
import sys
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
import yaml
from pydantic import TypeAdapter

from cloudra.infra.config import CloudraConfig, _model_to_yaml_data
from cloudra.tools.core.permission_model import Permission

FIXTURE = Path(__file__).parent / "fixtures" / "mcp_server.py"


def test_mcp_configuration_validates_and_roundtrips(tmp_path):
    config_file = tmp_path / "mcp-config.yaml"
    servers = {
        "local": {"command": sys.executable, "args": ["server.py"], "env": {"TOKEN": "private-env"}},
        "remote": {"url": "https://example.org/mcp", "headers": {"Authorization": "private-header"}},
    }
    config_file.write_text(yaml.safe_dump({"mcp_servers": servers}))
    cfg = CloudraConfig(config_file=config_file, data_dir=tmp_path / "data")
    assert set(cfg.mcp_servers) == {"local", "remote"}
    assert cfg.mcp_servers["local"].permissions.script
    assert cfg.mcp_servers["remote"].headers == {"Authorization": "private-header"}
    config_file.write_text(yaml.safe_dump(_model_to_yaml_data(cfg)))
    reloaded = CloudraConfig(config_file=config_file, data_dir=tmp_path / "data")
    assert reloaded.mcp_servers == cfg.mcp_servers
    assert "private-env" not in repr(cfg)
    assert "private-header" not in json.dumps(cfg.to_display_dict())


@pytest.mark.parametrize("server", [
    {"command": "python", "url": "https://example.org/mcp"},
    {"url": "https://example.org/mcp", "args": []},
    {"command": "python", "permissions": {"invented": True}},
    {"url": "file:///tmp/mcp"},
])
def test_invalid_mcp_yaml_fails_loudly(tmp_path, server):
    config_file = tmp_path / "mcp-config.yaml"
    config_file.write_text(yaml.safe_dump({"mcp_servers": {"broken": server}}))
    with pytest.raises(ValueError, match="mcp_servers.*broken"):
        CloudraConfig(config_file=config_file, data_dir=tmp_path / "data")


def test_mcp_assignment_validates_before_persisting(tmp_path, monkeypatch):
    from cloudra.infra.config import get_config, set_config_value

    cfg = get_config()
    monkeypatch.setattr(cfg, "config_file", tmp_path / "mcp-config.yaml")
    set_config_value("mcp_servers", '{"lab": {"command": "python"}}')
    assert cfg.mcp_servers["lab"].command == "python"
    saved = cfg.config_file.read_text()
    with pytest.raises(ValueError):
        set_config_value("mcp_servers", '{"bad": {"command": "python", "url": "https://example.org"}}')
    assert cfg.config_file.read_text() == saved


@pytest.mark.parametrize("value", [
    '{"remote": {"url": "PRIVATE-URL", "headers": {"Authorization": "PRIVATE-TOKEN"}}}',
    '{"remote": {"url": "https://example.org/PRIVATE-URL", "headers": {"Authorization": ["PRIVATE-TOKEN"]}}}',
    '{"remote": PRIVATE-TOKEN}',
])
def test_invalid_mcp_cli_input_omits_credentials_and_keeps_disk(tmp_path, monkeypatch, value):
    from click.testing import CliRunner

    from cloudra.cli import cli
    from cloudra.infra.config import get_config, set_config_value

    cfg = get_config()
    monkeypatch.setattr(cfg, "config_file", tmp_path / "mcp-config.yaml")
    set_config_value("mcp_servers", '{"lab": {"command": "python"}}')
    saved = cfg.config_file.read_text()
    result = CliRunner().invoke(cli, ["config", "set", "mcp_servers", value])
    assert result.exit_code == 1
    assert "PRIVATE" not in result.output
    assert cfg.config_file.read_text() == saved


@pytest.mark.asyncio
async def test_empty_manager_never_imports_sdk(monkeypatch):
    from cloudra.tools.mcp import MCPToolManager

    original = builtins.__import__

    def no_sdk(name, *args, **kwargs):
        if name == "mcp" or name.startswith("mcp."):
            raise AssertionError("empty configuration must not import SDK")
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", no_sdk)
    entries = []
    async with MCPToolManager({}).lifespan(entries):
        assert entries == []


@pytest.mark.asyncio
async def test_configured_manager_explains_missing_sdk(monkeypatch):
    from cloudra.infra.config import MCPServerConfig
    from cloudra.tools.mcp import MCPToolManager

    original = builtins.__import__

    def missing_sdk(name, *args, **kwargs):
        if name == "mcp":
            raise ModuleNotFoundError("missing", name="mcp")
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", missing_sdk)
    server = TypeAdapter(MCPServerConfig).validate_python({"command": "unused"})
    with pytest.raises(RuntimeError, match=r"cloudra\[mcp\]"):
        async with MCPToolManager({"local": server}).lifespan([]):
            pytest.fail("configured SDK absence must stop startup")


@pytest.mark.asyncio
async def test_cancelled_discovery_closes_client_in_its_opening_task(monkeypatch):
    sdk = pytest.importorskip("mcp", reason="requires the optional mcp extra")
    from cloudra.infra.config import MCPStdioServerConfig
    from cloudra.tools.mcp import MCPToolManager

    opened, closed = [], []

    class CancelledClient:
        def __init__(self, transport):
            pass

        async def __aenter__(self):
            opened.append(asyncio.current_task())
            return self

        async def __aexit__(self, *exc):
            closed.append(asyncio.current_task())

        async def list_tools(self, *, cursor):
            raise asyncio.CancelledError

    monkeypatch.setattr(sdk, "Client", CancelledClient)
    with pytest.raises(asyncio.CancelledError):
        async with MCPToolManager({"lab": MCPStdioServerConfig(command="unused")}).lifespan([]):
            pytest.fail("discovery was cancelled")
    assert opened == closed
    assert len(opened) == 1
    assert opened[0] is not asyncio.current_task()


@asynccontextmanager
async def fixture_config(transport, tmp_path, *, http_control=None):
    pytest.importorskip("mcp", reason="requires the optional mcp extra")
    from cloudra.infra.config import MCPServerConfig

    if transport == "stdio":
        yield TypeAdapter(MCPServerConfig).validate_python({
            "command": sys.executable,
            "args": [str(FIXTURE)],
            "env": {"MCP_FIXTURE_TOKEN": "fixture-token"},
            "cwd": str(tmp_path),
        })
        return
    import uvicorn

    spec = importlib.util.spec_from_file_location("cloudra_mcp_fixture", FIXTURE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    sock.listen()
    port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(module.http_app(), log_level="error", lifespan="on"))
    task = asyncio.create_task(server.serve(sockets=[sock]))
    try:
        async with asyncio.timeout(5):
            while not server.started:
                if task.done():
                    await task
                await asyncio.sleep(0.01)
        if http_control is not None:
            http_control.append((server, task))
        yield TypeAdapter(MCPServerConfig).validate_python({
            "url": f"http://127.0.0.1:{port}/mcp",
            "headers": {"Authorization": "Bearer fixture-token"},
        })
    finally:
        server.should_exit = True
        await task
        sock.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("transport", ["stdio", "http"])
async def test_real_transport_discovery_call_and_cleanup(transport, tmp_path):
    from jsonschema import Draft202012Validator

    from cloudra.tools.mcp import MCPToolManager

    async with fixture_config(transport, tmp_path) as config:
        entries = []
        async with MCPToolManager({"lab": config}).lifespan(entries):
            assert {entry.tool_name for entry in entries} == {"mcp__lab__echo", "mcp__lab__fail"}
            echo = next(entry for entry in entries if entry.tool_name.endswith("__echo"))
            assert echo.input_json_schema()["$defs"]["Payload"]["properties"]["repeat"]["default"] == 1
            assert echo.required_permissions == Permission.READ | Permission.SCRIPT
            assert echo.registration.supervisor_access == "none"
            result = await echo.external_call({"payload": {"text": "hello", "repeat": 2}})
            assert result.is_success
            assert result.summary == "hellohello"
            assert result.data["structuredContent"] == {"value": "hellohello"}
            assert result.data["content"][1]["type"] == "image"
            assert result.data["content"][2]["type"] == "resource_link"
            assert result.data["isError"] is False
            Draft202012Validator(echo.output_json_schema()).validate(result.data)
            failed = next(entry for entry in entries if entry.tool_name.endswith("__fail"))
            result = await failed.external_call({})
            assert not result.is_success
            assert result.data["isError"] is True
            assert result.summary == "fixture failure"
            invalid = await echo.external_call({"payload": {"repeat": 2}})
            assert not invalid.is_success
            assert invalid.data["isError"] is True
        assert entries == []


@pytest.mark.asyncio
async def test_server_failure_does_not_remove_other_servers_or_leak_credentials(tmp_path, caplog):
    from cloudra.infra.config import MCPServerConfig
    from cloudra.tools.mcp import MCPToolManager

    async with fixture_config("stdio", tmp_path) as config:
        broken = TypeAdapter(MCPServerConfig).validate_python({
            "url": "http://127.0.0.1:1/private-url-token",
            "headers": {"Authorization": "private-header-token"},
        })
        entries = []
        async with MCPToolManager({"working": config, "broken": broken}).lifespan(entries):
            assert len(entries) == 2
            assert all(entry.tool_name.startswith("mcp__working__") for entry in entries)
        assert "broken" in caplog.text
        assert "private-url-token" not in caplog.text
        assert "private-header-token" not in caplog.text


@pytest.mark.asyncio
async def test_duplicate_discovery_closes_only_the_failed_server(tmp_path, caplog):
    from cloudra.tools.mcp import MCPToolManager

    async with fixture_config("stdio", tmp_path) as config:
        duplicate = config.model_copy(update={"env": {**config.env, "MCP_FIXTURE_DUPLICATE": "1"}})
        entries = []
        async with MCPToolManager({"working": config, "duplicate": duplicate}).lifespan(entries):
            assert len(entries) == 2
            assert all(entry.tool_name.startswith("mcp__working__") for entry in entries)
        assert "duplicate MCP tool name" in caplog.text


@pytest.mark.asyncio
async def test_managers_keep_independent_connections_and_entry_ownership(tmp_path):
    from cloudra.tools.mcp import MCPToolManager

    async with fixture_config("stdio", tmp_path) as config:
        outer, inner = [], []
        async with MCPToolManager({"lab": config}).lifespan(outer):
            async with MCPToolManager({"lab": config}).lifespan(inner):
                assert outer[0] is not inner[0]
                assert outer[0].external_call is not inner[0].external_call
            assert inner == []
            result = await outer[0].external_call({"payload": {"text": "still connected"}})
            assert result.is_success
        assert outer == []


@pytest.mark.asyncio
async def test_http_allows_tool_results_after_default_http_client_timeout(tmp_path):
    from cloudra.tools.mcp import MCPToolManager

    async with fixture_config("http", tmp_path) as config:
        entries = []
        async with MCPToolManager({"lab": config}).lifespan(entries):
            result = await entries[0].external_call({"payload": {"text": "completed", "delay": 5.1}})
            assert result.is_success
            assert result.data["structuredContent"]["value"] == "completed"


@pytest.mark.asyncio
async def test_http_disconnect_does_not_cancel_manager_or_healthy_stdio(tmp_path):
    from cloudra.tools.mcp import MCPToolManager

    control = []
    async with fixture_config("stdio", tmp_path) as stdio:
        async with fixture_config("http", tmp_path, http_control=control) as http:
            entries = []
            async with MCPToolManager({"healthy": stdio, "disconnecting": http}).lifespan(entries):
                server, task = control[0]
                server.should_exit = True
                await task
                broken = next(entry for entry in entries if entry.tool_name == "mcp__disconnecting__echo")
                call = asyncio.create_task(broken.external_call({"payload": {"text": "connection lost"}}))
                outcome, = await asyncio.gather(call, return_exceptions=True)
                assert isinstance(outcome, BaseException)
                assert not asyncio.current_task().cancelling()
                healthy = next(entry for entry in entries if entry.tool_name == "mcp__healthy__echo")
                result = await healthy.external_call({"payload": {"text": "still connected"}})
                assert result.is_success
                assert result.data["structuredContent"] == {"value": "still connected"}
            assert entries == []


def test_wire_names_are_stable_js_identifiers_and_keep_distinct_raw_names():
    from cloudra.tools.mcp import mcp_tool_name

    names = [mcp_tool_name(server, tool) for server, tool in [
        ("lab", "echo"), ("lab-a", "echo/name"), ("lab_a", "echo_name"),
        ("lab", "a" * 100), ("a__b", "c"), ("a", "b__c"), ("化学", "工具"),
    ]]
    assert names[0] == "mcp__lab__echo"
    assert len(set(names)) == len(names)
    assert all(len(name) <= 64 and name.isascii() and name.isidentifier() for name in names)
    assert names[1] == mcp_tool_name("lab-a", "echo/name")


def test_structured_only_results_have_a_model_readable_summary():
    sdk = pytest.importorskip("mcp", reason="requires the optional mcp extra")
    from cloudra.tools.mcp import _tool_result

    result = _tool_result(sdk.types.CallToolResult(content=[], structured_content={"value": "中文", "count": 2}))
    assert json.loads(result.summary) == {"value": "中文", "count": 2}
    assert result.data["structuredContent"] == {"value": "中文", "count": 2}


def test_resource_only_results_summarize_readable_content():
    sdk = pytest.importorskip("mcp", reason="requires the optional mcp extra")
    from cloudra.tools.mcp import _tool_result

    result = _tool_result(sdk.types.CallToolResult(content=[
        sdk.types.ResourceLink(type="resource_link", name="spectrum", uri="https://example.org/spectrum"),
        sdk.types.EmbeddedResource(type="resource", resource=sdk.types.TextResourceContents(
            uri="file:///lab/notes.txt", text="Measured peak at 123.",
        )),
    ]))
    assert "spectrum" in result.summary
    assert "https://example.org/spectrum" in result.summary
    assert "Measured peak at 123." in result.summary
    assert len(result.data["content"]) == 2


def test_binary_only_results_have_hints_without_copying_base64():
    sdk = pytest.importorskip("mcp", reason="requires the optional mcp extra")
    from cloudra.tools.mcp import _tool_result

    encoded = "cHJpdmF0ZS1iaW5hcnk="
    result = _tool_result(sdk.types.CallToolResult(content=[
        sdk.types.ImageContent(type="image", data=encoded, mime_type="image/png"),
        sdk.types.AudioContent(type="audio", data=encoded, mime_type="audio/wav"),
        sdk.types.EmbeddedResource(type="resource", resource=sdk.types.BlobResourceContents(
            uri="file:///lab/blob.bin", blob=encoded, mime_type="application/octet-stream",
        )),
    ]))
    assert "image/png" in result.summary
    assert "audio/wav" in result.summary
    assert "file:///lab/blob.bin" in result.summary
    assert encoded not in result.summary
    assert result.data["content"][0]["data"] == encoded


def test_mcp_envelope_documents_optional_image_artifacts():
    sdk = pytest.importorskip("mcp", reason="requires the optional mcp extra")
    from cloudra.infra.config import MCPStdioServerConfig
    from cloudra.tools.mcp import _entry

    entry = _entry(
        "lab", MCPStdioServerConfig(command="unused"), None,
        sdk.types.Tool(name="echo", input_schema={"type": "object"}),
        sdk.types.CallToolResult.model_json_schema(by_alias=True),
    )
    schema = entry.output_json_schema()
    assert schema["properties"]["image_paths"]["type"] == "array"
    assert schema["properties"]["image_paths"]["items"] == {"type": "string"}
    assert "image_paths" not in schema.get("required", [])
