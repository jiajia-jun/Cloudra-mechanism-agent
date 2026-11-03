"""External JSON Schemas share the native protocol and document projections."""

from copy import deepcopy
from dataclasses import replace

import pytest

from cloudra.base.tools_class import input_schema, output_schema
from cloudra.runtime_v2.adapters import legacy_tool_schemas
from cloudra.runtime_v2.tool_catalog import guest_tool_names, javascript_instructions, render_tool_declaration
from cloudra.tools import ToolEntry
from cloudra.tools.documentation import build_tool_documents


async def external_call(arguments):
    raise AssertionError("Projecting a schema must not execute the external tool")


def external_entry(name="mcp__lab__inspect"):
    return ToolEntry(
        cls=None,
        tool_name=name,
        tool_id=name,
        summary="Inspect an external record.",
        tool_description="Read the external record using the supplied target.",
        external_call=external_call,
        input_schema={
            "type": "object",
            "properties": {
                "mode": {"enum": ["single", "batch"]},
                "target": {"$ref": "#/$defs/Target"},
                "limit": {"type": "integer", "default": 3, "minimum": 1},
                "path": {"type": "string"},
                "paths": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["mode", "target"],
            "additionalProperties": False,
            "$defs": {
                "Target": {
                    "type": "object",
                    "properties": {"id": {"type": "string"}},
                    "required": ["id"],
                    "additionalProperties": False,
                },
            },
            "oneOf": [
                {"properties": {"mode": {"const": "single"}, "path": {"type": "string"}},
                 "required": ["mode", "path"]},
                {"properties": {"mode": {"const": "batch"}, "paths": {"type": "array", "items": {"type": "string"}}},
                 "required": ["mode", "paths"]},
            ],
        },
        output_schema={
            "type": "object",
            "properties": {
                "content": {"type": "array", "items": {"type": "object", "additionalProperties": True}},
                "structured_content": {"$ref": "#/$defs/Record"},
                "is_error": {"type": "boolean"},
            },
            "required": ["content", "structured_content", "is_error"],
            "$defs": {"Record": {
                "type": "object", "properties": {"value": {"type": "number"}}, "required": ["value"],
            }},
        },
    )


def document(entry):
    return build_tool_documents([entry.tool_name], allowed_names={entry.tool_name}, entries=[entry])[0]


def test_native_and_raw_schemas_render_the_same_contract():
    class Args(input_schema):
        target: str
        limit: int = 3

    class Result(output_schema):
        value: float

    native = replace(external_entry(), input_schema=Args, output_schema=Result)
    raw = replace(native, input_schema=Args.model_json_schema(), output_schema=Result.model_json_schema())
    assert render_tool_declaration(native) == render_tool_declaration(raw)


def test_external_wire_schema_preserves_the_full_original_contract(monkeypatch):
    entry = external_entry()
    entry.input_schema["if"] = {"properties": {"mode": {"const": "batch"}}}
    entry.input_schema["then"] = {"properties": {"limit": {"minimum": 2}}}
    original = deepcopy(entry.input_schema)
    monkeypatch.setattr("cloudra.tools.get_tools_lst", lambda: [entry])
    schemas = legacy_tool_schemas([entry.tool_name])
    assert schemas == [{"type": "function", "function": {
        "name": entry.tool_name,
        "description": "Read the external record using the supplied target.",
        "parameters": original,
    }}]
    assert entry.input_schema == original


def test_external_js_declaration_keeps_required_defaults_definitions_and_conditions():
    rendered = render_tool_declaration(external_entry())
    assert '"mode": "single" | "batch";' in rendered
    assert '"target": McpLabInspectArgs_Target;' in rendered
    assert '"limit"?: number;' in rendered
    assert "default=3; min 1" in rendered
    assert "type McpLabInspectArgs_Target = {" in rendered
    assert '"id": string;' in rendered
    assert '"mode": "single";' in rendered
    assert '"path": string;' in rendered
    assert '"paths": Array<string>;' in rendered
    assert '"structured_content": McpLabInspectData_Record;' in rendered
    assert '"value": number;' in rendered
    assert "mcp__lab__inspect(args: McpLabInspectArgs)" in rendered


def test_embedded_mcp_output_definitions_use_their_own_schema_resource():
    entry = replace(external_entry(), output_schema={
        "type": "object",
        "properties": {
            "content": {"type": "array", "items": {"$ref": "#/$defs/Record"}},
            "structuredContent": {
                "$id": "urn:cloudra:mcp-output:mcp__lab__inspect",
                "type": "object",
                "properties": {"record": {"$ref": "#/$defs/Record"}},
                "required": ["record"],
                "$defs": {"Record": {
                    "type": "object",
                    "properties": {
                        "value": {"type": "number"},
                        "next": {"anyOf": [{"$ref": "#/$defs/Record"}, {"type": "null"}]},
                    },
                    "required": ["value"],
                }},
            },
        },
        "required": ["content", "structuredContent"],
        "$defs": {"Record": {
            "type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"],
        }},
    })
    original = deepcopy(entry.output_schema)
    rendered = render_tool_declaration(entry)
    assert '"content": Array<McpLabInspectData_Record>;' in rendered
    assert '"text": string;' in rendered
    assert '"value": number;' in rendered
    record_line = next(line for line in rendered.splitlines() if '"record":' in line)
    record_type = record_line.split(": ", 1)[1].removesuffix(";")
    assert record_type not in {"unknown", "McpLabInspectData_Record"}
    assert f"type {record_type} = {{" in rendered
    assert f'"next"?: {record_type} | null;' in rendered
    assert entry.output_schema == original


@pytest.mark.parametrize("change", ["input_default", "input_condition", "output_definition"])
def test_external_document_revision_tracks_original_schemas(change):
    original = external_entry()
    changed = replace(original, input_schema=deepcopy(original.input_schema), output_schema=deepcopy(original.output_schema))
    if change == "input_default":
        changed.input_schema["properties"]["limit"]["default"] = 4
    elif change == "input_condition":
        changed.input_schema["if"] = {"properties": {"mode": {"const": "batch"}}}
        changed.input_schema["then"] = {"properties": {"limit": {"minimum": 2}}}
    else:
        changed.output_schema["$defs"]["Record"]["properties"]["value"]["type"] = "string"
    assert document(original).revision == document(original).revision
    assert document(original).revision != document(changed).revision


@pytest.mark.parametrize(("name", "call"), [
    ("mcp__lab__inspect", "tools.mcp__lab__inspect(args)"),
    ("mcp__lab__inspect-record", 'tools["mcp__lab__inspect-record"](args)'),
])
def test_external_document_uses_callable_javascript_property_syntax(name, call):
    result = document(external_entry(name))
    assert result.name == name
    assert f"const r = await {call};" in result.content
    assert '"target": McpLabInspect' in result.content


def test_missing_mcp_tool_is_hidden_without_changing_saved_capabilities(monkeypatch):
    available = external_entry()
    missing = "mcp__retired__inspect"
    capabilities = [available.tool_name, missing]
    monkeypatch.setattr("cloudra.tools.get_tools_lst", lambda: [available])
    assert guest_tool_names(capabilities) == [available.tool_name]
    instructions = javascript_instructions(capabilities)
    assert available.tool_name in instructions
    assert missing not in instructions
    with pytest.raises(ValueError, match=missing):
        build_tool_documents([missing], allowed_names=guest_tool_names(capabilities), entries=[available])
    assert capabilities == [available.tool_name, missing]


@pytest.mark.asyncio
async def test_loaded_mcp_documents_refresh_when_a_saved_tool_is_unavailable(monkeypatch):
    from cloudra.runtime_v2.core import RuntimeCore
    from cloudra.runtime_v2.schemas import AgentCapabilities, AgentSession, InvocationProtocol, PermissionSet
    from cloudra.runtime_v2.tool_selection import ToolSelectionRecord
    from cloudra.runtime_v2.turn_pipeline import TurnPipeline

    available = external_entry()
    retired = external_entry("mcp__retired__inspect")
    capabilities = [available.tool_name, retired.tool_name]
    versions = {entry.tool_name: document(entry).revision for entry in (available, retired)}
    core = RuntimeCore(strict_events=True)
    agent = AgentSession(id="restored-mcp", project_id="mcp-project", role_id="coordinator", display_name="MCP",
        capabilities=AgentCapabilities(permissions=PermissionSet(read=True), tools=capabilities))
    agent.settings.invocation_protocol = InvocationProtocol.JAVASCRIPT
    await core.contexts.record_tool_selection(agent=agent, run_id="before-restart", messages=[],
        record=ToolSelectionRecord(status="selected", source="llm", selection_id="saved", catalog_revision="saved",
            names=tuple(capabilities), document_revisions=versions))
    monkeypatch.setattr("cloudra.tools.get_tools_lst", lambda: [available])
    pipeline = TurnPipeline(event_log=core.event_log, stages=[], llm=None, tools=None)
    await pipeline._initial_tool_documents(agent, "restored", [], core.contexts, None)
    state = core.contexts.prefix_state(agent.id)
    assert state["meta"]["tool_document_revisions"] == {available.tool_name: versions[available.tool_name]}
    assert state["meta"]["tool_selection"]["document_revisions"] == {available.tool_name: versions[available.tool_name]}
    assert agent.capabilities.tools == capabilities
