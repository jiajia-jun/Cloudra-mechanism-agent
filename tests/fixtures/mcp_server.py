"""A real two-page MCP server used through both SDK transports."""

import os

import anyio
from mcp import types
from mcp.server import Server
from mcp.server.stdio import stdio_server

INPUT_SCHEMA = {
    "type": "object",
    "properties": {"payload": {"$ref": "#/$defs/Payload"}},
    "required": ["payload"],
    "additionalProperties": False,
    "$defs": {"Payload": {
        "type": "object",
        "properties": {
            "text": {"type": "string"}, "repeat": {"type": "integer", "default": 1},
            "delay": {"type": "number", "default": 0},
        },
        "required": ["text"],
        "additionalProperties": False,
    }},
}
OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {"value": {"$ref": "#/$defs/Value"}},
    "required": ["value"],
    "$defs": {"Value": {"type": "string"}},
}


async def list_tools(ctx, params):
    if params and params.cursor == "second":
        return types.ListToolsResult(tools=[types.Tool(
            name="echo" if os.getenv("MCP_FIXTURE_DUPLICATE") else "fail",
            description="Return a business failure.", input_schema={"type": "object"},
        )])
    return types.ListToolsResult(tools=[types.Tool(
        name="echo", description="Echo a nested payload.", input_schema=INPUT_SCHEMA, output_schema=OUTPUT_SCHEMA,
    )], next_cursor="second")


async def call_tool(ctx, params):
    if params.name == "fail":
        return types.CallToolResult(content=[types.TextContent(type="text", text="fixture failure")], is_error=True)
    payload = params.arguments["payload"]
    if "text" not in payload:
        return types.CallToolResult(content=[types.TextContent(type="text", text="payload.text is required")], is_error=True)
    await anyio.sleep(payload.get("delay", 0))
    value = payload["text"] * payload.get("repeat", 1)
    return types.CallToolResult(
        content=[
            types.TextContent(type="text", text=value),
            types.ImageContent(type="image", data="aW1hZ2U=", mime_type="image/png"),
            types.ResourceLink(type="resource_link", name="fixture", uri="https://example.org/resource"),
        ],
        structured_content={"value": value},
    )


server = Server("cloudra-fixture", on_list_tools=list_tools, on_call_tool=call_tool)


def http_app():
    app = server.streamable_http_app(json_response=True, stateless_http=True)

    async def authenticated(scope, receive, send):
        if scope["type"] == "http" and dict(scope["headers"]).get(b"authorization") != b"Bearer fixture-token":
            await send({"type": "http.response.start", "status": 401, "headers": []})
            await send({"type": "http.response.body", "body": b""})
            return
        await app(scope, receive, send)

    return authenticated


async def main():
    assert os.environ["MCP_FIXTURE_TOKEN"] == "fixture-token"
    async with stdio_server() as streams:
        await server.run(*streams, server.create_initialization_options())


if __name__ == "__main__":
    anyio.run(main)
