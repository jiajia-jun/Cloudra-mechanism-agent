"""AgentHub's model-visible contract matches native input and receipt validation."""

import pytest
from pydantic import ValidationError

from cloudra.runtime_v2.tool_catalog import _render_tool_types
from cloudra.tools.Managetool.agent_hub import (
    AgentHub,
    AgentHub_input_schema,
    AgentHub_output_schema,
)


@pytest.mark.parametrize("arguments,field", [
    ({"action": "post", "content": "finding"}, "topic"),
    ({"action": "post", "topic": "results", "content": " \t\n"}, "content"),
    ({"action": "read", "topic": " \t"}, "topic"),
    ({"action": "search"}, "keyword"),
    ({"action": "search", "keyword": "\n"}, "keyword"),
    ({"action": "call", "to": "small_mol"}, "message"),
    ({"action": "call", "message": "check results", "to": " "}, "to"),
    ({"action": "post", "topic": "results", "content": "check", "kind": "message"}, "to_agent"),
    ({"action": "post", "topic": "results", "content": "check", "kind": "message", "to_agent": "\t"}, "to_agent"),
])
def test_hub_schema_rejects_missing_or_whitespace_action_fields(arguments, field):
    with pytest.raises(ValidationError, match=field):
        AgentHub_input_schema.model_validate(arguments)


@pytest.mark.parametrize("arguments", [
    {"action": "post", "topic": "results", "content": "finding"},
    {"action": "post", "topic": "results", "content": "check", "kind": "message", "to_agent": "small_mol"},
    {"action": "read", "topic": "results"},
    {"action": "search", "keyword": "water"},
    {"action": "call", "to": "small_mol", "message": "check results"},
    {"action": "browse"},
    {"action": "directory", "topic": "ignored optional context"},
])
def test_hub_schema_preserves_flat_calls_and_defaults(arguments):
    parsed = AgentHub_input_schema.model_validate(arguments)
    assert parsed.model_dump(include=set(arguments)) == arguments
    assert parsed.limit == 20


def test_hub_wire_schema_keeps_shared_fields_and_narrow_action_conditions():
    schema = AgentHub_input_schema.to_parameters_schema()
    branches = schema["oneOf"]
    assert len(branches) == 7
    required = {
        "post": {"action", "topic", "content"},
        "read": {"action", "topic"},
        "search": {"action", "keyword"},
        "call": {"action", "to", "message"},
        "browse": {"action"},
        "directory": {"action"},
    }
    for branch in branches:
        action = branch["properties"]["action"]["const"]
        assert required[action] <= set(branch["required"])
        expected_fields = required[action] | ({"kind"} if action == "post" else set())
        if branch["properties"].get("kind", {}).get("const") == "message":
            expected_fields.add("to_agent")
        assert set(branch["properties"]) == expected_fields
        assert "additionalProperties" not in branch
    assert schema["additionalProperties"] is False
    assert "limit" in schema["properties"]
    message = next(branch for branch in branches if branch["properties"].get("kind", {}).get("const") == "message")
    assert {"kind", "to_agent"} <= set(message["required"])
    assert message["properties"]["to_agent"]["minLength"] == 1


@pytest.mark.parametrize("arguments,valid", [
    ({"action": "post", "topic": "results", "content": "finding"}, True),
    ({"action": "post", "topic": "results", "content": "notice", "kind": "broadcast", "limit": 4}, True),
    ({"action": "post", "topic": "results", "content": "message", "kind": "message", "to_agent": "small_mol"}, True),
    ({"action": "read", "topic": "results", "limit": 4}, True),
    ({"action": "search", "keyword": "water", "limit": 4}, True),
    ({"action": "call", "to": "small_mol", "message": "review", "post_id": "evt_1"}, True),
    ({"action": "browse", "cursor": "evt_1"}, True),
    ({"action": "directory", "topic": "optional context"}, True),
    ({"action": "post", "content": "finding"}, False),
    ({"action": "post", "topic": "results", "content": ""}, False),
    ({"action": "post", "topic": "results", "content": "message", "kind": "message"}, False),
    ({"action": "read"}, False),
    ({"action": "search", "keyword": ""}, False),
    ({"action": "call", "to": "small_mol"}, False),
    ({"action": "browse", "unexpected": 4}, False),
])
def test_hub_wire_json_schema_accepts_flat_calls_and_rejects_missing_conditions(arguments, valid):
    jsonschema = pytest.importorskip("jsonschema")
    schema = AgentHub_input_schema.to_parameters_schema()
    jsonschema.Draft202012Validator.check_schema(schema)
    assert jsonschema.Draft202012Validator(schema).is_valid(arguments) is valid


def test_hub_js_declaration_exposes_action_required_fields_and_receipt_types():
    declarations, args_type, data_type = _render_tool_types("agent_hub", AgentHub())
    args = next(item for item in declarations if item.startswith(f"type {args_type} ="))
    assert '"limit"?: number;' in args
    assert '"cursor"?: string | null;' in args
    for action, fields in (("read", ("topic",)), ("search", ("keyword",)), ("call", ("to", "message"))):
        before, after = args.split(f'"action": "{action}";', 1)
        branch = before.rsplit("{\n", 1)[1] + after.split("\n}", 1)[0]
        assert all(f'"{field}": string;' in branch for field in fields)
    output = next(item for item in declarations if item.startswith(f"type {data_type} ="))
    for field in ("notifications", "library", "skills", "settings"):
        assert f'"{field}"' in output
    assert any('"wake_status": "requested" | "already_running" | "parked";' in item for item in declarations)


@pytest.mark.parametrize("payload", [
    {"is_success": True, "sessions": [{"session_id": 42}]},
    {"is_success": True, "posts": [{"topic": 42}]},
    {"is_success": True, "notifications": [{"session_id": "as_peer", "wake_status": "done"}]},
    {"is_success": True, "library": [{"title": "water", "score": "not-a-number"}]},
    {"is_success": True, "skills": [{"name": 42}]},
    {"is_success": True, "settings": {"session_id": "as_peer", "yolo": "yes"}},
])
def test_hub_receipt_schema_rejects_malformed_common_fields(payload):
    with pytest.raises(ValidationError):
        AgentHub_output_schema.model_validate(payload)


def test_hub_receipt_schema_preserves_extension_metadata():
    parsed = AgentHub_output_schema.model_validate({
        "is_success": True,
        "metadata": {"trace_id": "trace-1"},
        "skills": [{"name": "water", "description": "water workflow", "metadata": {"version": 1}}],
    })
    dumped = parsed.model_dump(exclude_unset=True)
    assert dumped["metadata"] == {"trace_id": "trace-1"}
    assert dumped["skills"][0]["metadata"] == {"version": 1}
