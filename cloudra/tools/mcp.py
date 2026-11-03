"""Application-owned MCP connections adapted into the ordinary tool catalog."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from contextlib import AsyncExitStack, asynccontextmanager
from copy import deepcopy
from typing import Any

from cloudra.infra.config import MCPServerConfig, MCPStdioServerConfig
from cloudra.runtime_v2.policies.base import ToolResult
from cloudra.tools import ToolEntry
from cloudra.tools.core.permission_model import Permission
from cloudra.tools.registry import ToolRegistration

logger = logging.getLogger(__name__)


def mcp_tool_name(server: str, tool: str) -> str:
    """Stable JS-safe provider names; raw server/tool identities stay in the callback."""
    raw = f"mcp__{server}__{tool}"
    safe = "".join(char if char.isascii() and (char.isalnum() or char == "_") else "_" for char in raw)
    if raw == safe and "__" not in server and "__" not in tool and len(raw) <= 64:
        return raw
    digest = hashlib.sha256(json.dumps([server, tool], ensure_ascii=False).encode()).hexdigest()[:12]
    return f"{safe[:50]}__{digest}"


def _tool_result(result: Any) -> ToolResult:
    data = result.model_dump(mode="json", by_alias=True, exclude_none=True)
    summary = "\n".join(block["text"] for block in data["content"] if block["type"] == "text")
    if not summary.strip():
        if "structuredContent" in data:
            summary = json.dumps(data["structuredContent"], ensure_ascii=False)
        else:
            hints = []
            for block in data["content"]:
                if block["type"] in ("image", "audio"):
                    hints.append(f"{block['type']} content ({block['mimeType']})")
                elif block["type"] == "resource_link":
                    hints.append(f"{block['name']}: {block['uri']}")
                elif block["type"] == "resource":
                    resource = block["resource"]
                    hints.append(f"{resource['uri']}: {resource.get('text') or resource.get('mimeType', 'binary resource')}")
            summary = "\n".join(hints) or "MCP tool returned no text content."
    return ToolResult(is_success=not result.is_error, summary=summary, data=data)


def _entry(server: str, config: MCPServerConfig, client: Any, tool: Any, result_schema: dict) -> ToolEntry:
    name = mcp_tool_name(server, tool.name)
    schema = deepcopy(result_schema)
    schema["properties"]["image_paths"] = {
        "type": "array", "items": {"type": "string"},
        "description": "Paths to images saved in the Cloudra workspace.",
    }
    if tool.output_schema is not None:
        structured = deepcopy(tool.output_schema)
        # A separate schema resource keeps #/$defs refs relative to the remote
        # output document after it is embedded in Cloudra's result envelope.
        structured.setdefault("$id", f"urn:cloudra:mcp-output:{name}")
        schema["properties"]["structuredContent"] = structured
    required = Permission.NONE
    for permission, enabled in config.permissions.model_dump().items():
        if enabled:
            required |= Permission[permission.upper()]

    async def call(arguments: dict[str, Any]) -> ToolResult:
        return _tool_result(await client.call_tool(tool.name, arguments))

    return ToolEntry(
        cls=None,
        tool_name=name,
        tool_id=name,
        input_schema=deepcopy(tool.input_schema),
        output_schema=schema,
        tool_description=tool.description or "",
        summary=tool.description or tool.title or tool.name,
        external_call=call,
        required_permissions=required,
        registration=ToolRegistration(module="mcp", class_name="", tool_name=name),
    )


class MCPToolManager:
    """Keep each server's SDK contexts and failure cancellation in its own task."""

    def __init__(self, servers: dict[str, MCPServerConfig]):
        self.servers = servers

    @asynccontextmanager
    async def lifespan(self, entries: list[ToolEntry]):
        if not self.servers:
            yield
            return
        try:
            from mcp import types
        except ImportError:
            raise RuntimeError('MCP servers are configured; install the SDK with pip install "cloudra[mcp]"') from None

        result_schema = types.CallToolResult.model_json_schema(by_alias=True)
        owned: list[ToolEntry] = []
        owners = []
        try:
            for server, config in self.servers.items():
                ready = asyncio.get_running_loop().create_future()
                stop = asyncio.Event()
                owner = asyncio.create_task(self._server_owner(
                    server, config, {entry.tool_name for entry in entries}, result_schema, ready, stop,
                ))
                owners.append((owner, ready, stop))
                discovered = await ready
                entries.extend(discovered)
                owned.extend(discovered)
            yield
        finally:
            for owner, ready, stop in owners:
                stop.set()
                if not ready.done() or ready.cancelled():
                    owner.cancel()
            await asyncio.gather(*(owner for owner, _, _ in owners), return_exceptions=True)
            owned_ids = {id(entry) for entry in owned}
            entries[:] = [entry for entry in entries if id(entry) not in owned_ids]

    async def _server_owner(self, server, config, names, result_schema, ready, stop):
        phase = "connection"
        try:
            from mcp import Client, StdioServerParameters

            async with AsyncExitStack() as stack:
                if isinstance(config, MCPStdioServerConfig):
                    transport = StdioServerParameters(
                        command=config.command, args=config.args, env=config.env, cwd=config.cwd,
                    )
                else:
                    from httpx2 import AsyncClient, Timeout
                    from mcp.client.streamable_http import streamable_http_client

                    http = await stack.enter_async_context(AsyncClient(
                        headers=config.headers, timeout=Timeout(30.0, read=300.0),
                    ))
                    transport = streamable_http_client(config.url, http_client=http)
                client = await stack.enter_async_context(Client(transport))
                phase = "tool discovery"
                discovered: list[ToolEntry] = []
                cursor = None
                while True:
                    page = await client.list_tools(cursor=cursor)
                    for tool in page.tools:
                        entry = _entry(server, config, client, tool, result_schema)
                        if entry.tool_name in names:
                            phase = "tool discovery: duplicate MCP tool name"
                            raise ValueError("duplicate MCP tool name")
                        names.add(entry.tool_name)
                        discovered.append(entry)
                    cursor = page.next_cursor
                    if cursor is None:
                        break
                ready.set_result(discovered)
                phase = "runtime connection"
                await stop.wait()
        except asyncio.CancelledError:
            if not ready.done():
                ready.cancel()
            raise
        except Exception as exc:
            # Exception strings may contain URLs, headers or process args.
            logger.warning("MCP server %r unavailable during %s (%s)", server, phase, type(exc).__name__)
            if not ready.done():
                ready.set_result([])
