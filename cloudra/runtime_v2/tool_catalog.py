"""Tool catalog: registry schemas, JS declarations and protocol wire exposure.

Single source for the invocation-protocol-aware tool surface:

- ``wire_tool_schemas(agent, tool_names)`` — what the model *sees*:
  traditional runs get the permitted business schemas; javascript runs get
  ``js_exec`` plus the permitted direct tools (stop / ask_user /
  schedule / agent_hub). This is not a privilege grant: js_exec runs pure guest logic
  and every actual tool call rechecks capabilities at admission, so a
  read-only role may select the JS protocol without gaining bash.
- ``tool_declarations(tool_names, *, visual_mode)`` — deterministic
  TypeScript-like declarations of the guest-callable tools, generated from
  the loaded ToolEntry JSON Schemas.  Declarations are model
  instructions (documentation); the guest receives only names, never a
  typechecker.  Unknown JSON-schema constructs render as ``unknown`` — never
  silently widened to ``any`` and never invented.
- ``validate_wire_route`` — stable protocol errors for misrouted calls
  (js_exec in traditional mode, top-level business calls in JS mode, direct
  tools inside a guest program). Misrouted calls are never executed.
"""

from __future__ import annotations

import json
from typing import Any, Iterable

from cloudra.runtime_v2.schemas import (
    AgentSession,
    InvocationProtocol,
    OrchestrationMode,
    effective_invocation_protocol,
)
from cloudra.tools import _json_schema
from cloudra.tools.capabilities import (
    config_disabled_tools,
    dag_review_decision_tools,
    dag_tools,
    is_direct_only,
    role_hidden_tools,
    visual_tools,
)

JS_EXEC_NAME = "js_exec"


def _mode_hidden_tools(orchestration_mode: OrchestrationMode | str) -> frozenset[str]:
    """Tools hidden from the wire under one orchestration mode.

    dag_* tools hard-fail in standard mode and the Supervisor verdict tools
    hard-fail outside dag_guided (the Supervisor is offline in dag_record), so
    projecting them would only teach the model to call dead tools.  Mode is
    per-agent (``agent.settings.orchestration_mode``), exactly like the visual
    gate; execution-layer mode checks stay as the second line of defense.
    """
    mode = OrchestrationMode(orchestration_mode)
    if mode is OrchestrationMode.STANDARD:
        return dag_tools()
    if mode is OrchestrationMode.DAG_RECORD:
        return dag_review_decision_tools()
    return frozenset()


# 无人值守（benchmark）下没有可对话的人：ask_user 投影出来只会教模型调一个
# 必然失败的交互工具（GH #31）。执行层 UnattendedStage 是 fail-closed 兜底。
_UNATTENDED_HIDDEN_TOOLS = frozenset({"ask_user"})


def _settings_hidden_tools(agent: AgentSession) -> frozenset[str]:
    """Tools hidden from the wire by agent settings (not orchestration mode)."""
    if getattr(agent.settings, "unattended", False):
        return _UNATTENDED_HIDDEN_TOOLS
    return frozenset()


def js_exec_schema():
    return {"type": "function", "function": {
        "name": "js_exec",
        "description": "Run one bounded JavaScript program to orchestrate available tools. "
                       "The program is the only tool call in this response; use await tools.NAME(args), "
                       "then text(value). Backend calls execute serially. Direct tools, including agent_hub, stay top-level.",
        "parameters": {"type": "object", "properties": {
            "code": {"type": "string", "description": "JavaScript with top-level await."}},
            "required": ["code"], "additionalProperties": False}}}


# --------------------------------------------------------------------- routing


def validate_wire_route(
    protocol: InvocationProtocol | str,
    tool_name: str,
    *,
    origin: str = "wire",
) -> str | None:
    """Return a stable protocol error for a misrouted call, else None.

    ``origin`` is "wire" (a top-level model tool call) or "guest" (a call
    from inside a JS program).  A returned string is feedback to the model;
    the call must not execute.
    """
    javascript = InvocationProtocol(protocol) is InvocationProtocol.JAVASCRIPT
    if not javascript:
        if tool_name == JS_EXEC_NAME:
            return (
                "protocol_error[js_exec_in_traditional]: js_exec is only available "
                "when the run's invocation protocol is javascript"
            )
        return None
    if origin == "guest":
        if tool_name == JS_EXEC_NAME or is_direct_only(tool_name):
            return (
                f"protocol_error[direct_only_in_guest]: {tool_name!r} is a direct "
                "tool and cannot be called from inside a JavaScript program; "
                "return it as a top-level tool call instead"
            )
        return None
    if tool_name == JS_EXEC_NAME or is_direct_only(tool_name):
        return None
    return (
        f"protocol_error[business_call_outside_program]: {tool_name!r} is a "
        "business tool and must be invoked through js_exec while the run's "
        "invocation protocol is javascript"
    )


# --------------------------------------------------------------- wire exposure


def _resolve_names(tool_names: Iterable[str] | None) -> list[str]:
    """Capability-list resolution: wildcard expands over the registry."""
    supplied = {str(n) for n in (tool_names or []) if n}
    names = supplied - {"*"}
    if "*" in supplied:
        from cloudra.tools import get_tools_lst

        names |= {entry.tool_name for entry in get_tools_lst() if entry.tool_name}
    return sorted(names)


def guest_tool_names(
    tool_names: Iterable[str] | None,
    *,
    visual_mode: bool = True,
    orchestration_mode: OrchestrationMode | str = OrchestrationMode.STANDARD,
    role_id: str | None = None,
) -> list[str]:
    """Names callable inside a JS program: no direct tools, visual-gated,
    gated by the run's orchestration mode (dag_* tools are hidden in standard
    mode; Supervisor verdict tools outside dag_guided), and filtered by the
    agent's role allowlist projection when role_id is given. Saved MCP names
    are visible only while their external service supplies the tool."""
    names = _resolve_names(tool_names)
    gated = frozenset() if visual_mode else visual_tools()
    hidden = _mode_hidden_tools(orchestration_mode) | config_disabled_tools()
    if role_id is not None:
        hidden = hidden | role_hidden_tools(role_id)
    mcp_names = {name for name in names if name.startswith("mcp__")}
    if mcp_names:
        from cloudra.tools import get_tools_lst

        hidden = hidden | (mcp_names - {entry.tool_name for entry in get_tools_lst()})
    return [
        name
        for name in names
        if not is_direct_only(name) and name not in gated and name not in hidden
    ]


def wire_tool_schemas(agent: AgentSession, tool_names: list[str] | None) -> list[dict]:
    """Protocol- and orchestration-mode-aware wire projection for one LLM request.

    Traditional: the permitted business schemas (unchanged legacy surface).
    Javascript: ``js_exec`` plus the permitted direct tools only. Tools
    that hard-fail under the agent's orchestration mode are never projected.
    """
    from cloudra.runtime_v2.adapters import legacy_tool_schemas  # lazy: import cycle

    if effective_invocation_protocol(agent) is not InvocationProtocol.JAVASCRIPT:
        schemas = legacy_tool_schemas(tool_names)
    else:
        schemas = [js_exec_schema()]
        direct = [name for name in _resolve_names(tool_names) if is_direct_only(name)]
        if direct:
            schemas.extend(legacy_tool_schemas(direct))
    hidden = (
        _mode_hidden_tools(agent.settings.orchestration_mode)
        | _settings_hidden_tools(agent)
        | config_disabled_tools()
        | role_hidden_tools(agent.role_id)
    )
    if not hidden:
        return schemas
    return [
        schema
        for schema in schemas
        if (schema.get("function") or {}).get("name") not in hidden
    ]


# ----------------------------------------------------------------- declarations

_DECLARATION_HEADER = """interface ToolResponse<T> {
  call_id: string;
  is_success: boolean;
  summary: string;
  data: T;
  duration_ms: number;
}"""

_DECLARATION_FOOTER = "declare function text(value: unknown): void;"


def javascript_instructions(
    tool_names: Iterable[str] | None,
    *,
    visual_mode: bool = True,
    orchestration_mode: OrchestrationMode | str = OrchestrationMode.STANDARD,
    role_id: str | None = None,
) -> str:
    """Deterministic JS-mode instructions appended to the model request.

    Describes the execution envelope, JSON serialization, explicit output,
    the serial backend, the fixed limits and the direct-only tools; the
    generated declarations are documentation, not executable guest input.
    """
    names = guest_tool_names(tool_names, visual_mode=visual_mode,
        orchestration_mode=orchestration_mode, role_id=role_id)
    declarations = tool_declarations([name for name in ('get_tool_docs', 'update_memory') if name in names],
        visual_mode=visual_mode, orchestration_mode=orchestration_mode, role_id=role_id)
    manifest = tool_capability_manifest(names, visual_mode=visual_mode,
        orchestration_mode=orchestration_mode, role_id=role_id)
    return (
        "This run uses the JavaScript invocation protocol. To use tools, call "
        "js_exec({code}) with an ECMAScript program that uses top-level await.\n"
        "Inside a program:\n"
        "- `await tools.NAME(args)` executes one backend tool and resolves to "
        "a ToolResponse {call_id, is_success, summary, data, duration_ms}. "
        "Arguments and results cross the bridge as plain JSON (no functions, "
        "no undefined, no class instances).\n"
        "- Check r.is_success even when await succeeds: a tool can return a "
        "business failure without throwing. Read r.data for structured results "
        "(for get_skill: text(r.data.content)); use text(r.summary) for a readable "
        "summary. Do not stringify the whole response and slice it: that duplicates "
        "content and can hide fields.\n"
        "- A rejected call raises a ToolCallError with {code, message, "
        "call_id, tool_name, effect_state}; catching it grants no authority.\n"
        "- `text(value)` records an explicit program output. Only these "
        "outputs and an aggregate receipt are returned to you; there is no "
        "console.log.\n"
        "- Use the declared function names and argument fields below. Do not "
        "probe tools by trial calls or inspect application source to discover schemas.\n"
        "- Backend calls execute serially, one at a time, even under "
        "Promise.all.\n"
        "- Direct tools (stop, ask_user, schedule, agent_hub) are NOT callable inside "
        "a program; return them as top-level tool calls instead, and never "
        "call js_exec recursively. Send exactly one js_exec per response and "
        "do not combine it with other tool calls.\n"
        "- Fixed limits: 64 KiB source, 64 tool requests, 16 pending "
        "requests, 5 s guest evaluation time, 64 KiB / 256 output entries, "
        "1 MiB per tool result. A failed program keeps its earlier outputs "
        "and child receipts; nothing is retried automatically — repair the "
        "program in a later js_exec call.\n"
        "- Program output is not scientific evidence; completed child call "
        "results are recorded as tool.result_recorded events.\n"
        "Bootstrap tool contracts:\n"
        f"{declarations}\n\n"
        "Current capability directory (names and purposes, not argument contracts):\n"
        f"{manifest}\n"
        "For a business tool whose detailed contract is absent, first call tools.get_tool_docs({names: [name]}), "
        "then text(r.summary). Loaded contracts are supplied automatically in the next model request. "
        "Do not print full document batches: they can exceed the 64 KiB program output limit. "
        "Load a small set for the next action; request additional contracts when needed. "
        "Only documentation is loaded; all calls retain their existing permission checks."
    )


def tool_capability_manifest(tool_names, *, visual_mode=True,
        orchestration_mode=OrchestrationMode.STANDARD, role_id=None) -> str:
    from cloudra.tools import get_tools_lst
    from cloudra.tools.documentation import tool_capability_summaries

    names = guest_tool_names(tool_names, visual_mode=visual_mode,
        orchestration_mode=orchestration_mode, role_id=role_id)
    summaries = tool_capability_summaries(names, entries=get_tools_lst())
    return "\n".join(f"- {item.name}: {item.summary}" for item in summaries)


def _function_declaration(name, entry, args_type, data_type):
    description = str(getattr(entry, "tool_description", "") or "").strip()
    if not description:
        description = _schema_description(_schema_of(entry, "input"))
    description = description.replace("*/", "* /")
    comment = f"  /** {description} */\n" if description else ""
    return f"{comment}  {_js_ident(name)}(args: {args_type}): Promise<ToolResponse<{data_type}>>;"


def render_tool_declaration(entry) -> str:
    """Render one actual contract without a second availability projection."""
    decls, args_type, data_type = _render_tool_types(entry.tool_name, entry)
    function = _function_declaration(entry.tool_name, entry, args_type, data_type)
    return "\n\n".join([_DECLARATION_HEADER, *decls,
        "declare const tools: {\n" + function + "\n};", _DECLARATION_FOOTER])


def tool_declarations(
    tool_names: Iterable[str] | None,
    *,
    visual_mode: bool = True,
    entries: list | None = None,
    orchestration_mode: OrchestrationMode | str = OrchestrationMode.STANDARD,
    role_id: str | None = None,
) -> str:
    """Deterministic TypeScript-like declarations for guest-callable tools."""
    names = guest_tool_names(
        tool_names,
        visual_mode=visual_mode,
        orchestration_mode=orchestration_mode,
        role_id=role_id,
    )
    if entries is None:
        from cloudra.tools import get_tools_lst

        entries = get_tools_lst()
    by_name = {entry.tool_name: entry for entry in entries}
    sections = [_DECLARATION_HEADER]
    functions: list[str] = []
    for name in names:
        entry = by_name.get(name)
        decls, args_type, data_type = _render_tool_types(name, entry)
        sections.extend(decls)
        functions.append(_function_declaration(name, entry, args_type, data_type))
    sections.append("declare const tools: {\n" + "\n".join(functions) + "\n};" if functions
                    else "declare const tools: Record<string, never>;")
    sections.append(_DECLARATION_FOOTER)
    return "\n\n".join(sections)


def _schema_of(entry, direction: str) -> dict:
    accessor = getattr(entry, f"{direction}_json_schema", None)
    if accessor is not None:
        return accessor()
    return _json_schema(getattr(entry, f"{direction}_schema", None))


def _render_tool_types(name: str, entry) -> tuple[list[str], str, str]:
    """Render one tool's input/output schemas; returns (decls, args_type, data_type)."""
    if entry is None:
        record = "Record<string, unknown>"
        return [], record, record
    alias = _alias_base(name)
    decls: list[str] = []
    args_type = f"{alias}Args"
    data_type = f"{alias}Data"
    decls.extend(_render_alias(args_type, _schema_of(entry, "input")))
    decls.extend(_render_alias(data_type, _schema_of(entry, "output")))
    return decls, args_type, data_type


def _render_alias(alias: str, schema: dict) -> list[str]:
    """Render ``type Alias = ...`` for one root schema plus its $defs."""
    defs = schema.get("$defs") or {}
    decls = []
    for def_name in sorted(defs):
        rendered = _ts(defs[def_name], defs, alias, decls)
        decls.append(f"type {_def_name(alias, def_name)} = {rendered};")
    body = {k: v for k, v in schema.items() if k not in {"$defs", "$id"}}
    decls.append(f"type {alias} = {_ts(body, defs, alias, decls)};")
    return decls


def _ts(schema: Any, defs: dict, prefix: str, decls: list[str]) -> str:
    if not isinstance(schema, dict):
        return "unknown"
    if "$id" in schema:
        # An embedded schema resource owns its fragment references. Give its
        # definitions separate aliases, including recursive references.
        nested = f"{prefix}Nested{len(decls) + 1}"
        decls.extend(_render_alias(nested, schema))
        return nested
    if "$ref" in schema:
        ref = str(schema["$ref"])
        if ref.startswith("#/$defs/") and ref[len("#/$defs/"):] in defs:
            return _def_name(prefix, ref[len("#/$defs/"):])
        return "unknown"
    if "const" in schema:
        return json.dumps(schema["const"], ensure_ascii=False)
    if "enum" in schema:
        values = [json.dumps(v, ensure_ascii=False) for v in schema["enum"]]
        return " | ".join(values) if values else "unknown"
    for key in ("anyOf", "oneOf"):
        if key in schema:
            parts = [_ts(part, defs, prefix, decls) for part in schema[key]]
            union = " | ".join(parts) if parts else "unknown"
            if schema.get("properties"):
                # Conditions refine the shared object, rather than replacing
                # its sibling properties (for example a tool's common fields).
                return f"({_object_ts(schema, defs, prefix, decls)}) & ({union})"
            return union
    if "allOf" in schema:
        parts = [_ts(part, defs, prefix, decls) for part in schema["allOf"]]
        if schema.get("properties"):
            parts.insert(0, _object_ts(schema, defs, prefix, decls))
        return " & ".join(f"({part})" for part in parts) if parts else "unknown"
    type_ = schema.get("type")
    if isinstance(type_, list):
        parts = [_ts({**schema, "type": item}, defs, prefix, decls) for item in type_]
        return " | ".join(parts) if parts else "unknown"
    if type_ == "string":
        return "string"
    if type_ in ("number", "integer"):
        return "number"
    if type_ == "boolean":
        return "boolean"
    if type_ == "null":
        return "null"
    if type_ == "array":
        prefix_items = schema.get("prefixItems")
        if (
            isinstance(prefix_items, list)
            and schema.get("minItems") == len(prefix_items)
            and schema.get("maxItems") == len(prefix_items)
        ):
            # Pydantic fixed tuples use prefixItems rather than items. Preserve
            # each member and the tuple length instead of exposing unknown[].
            members = [_ts(item, defs, prefix, decls) for item in prefix_items]
            return "[" + ", ".join(members) + "]"
        items = schema.get("items")
        inner = _ts(items, defs, prefix, decls) if items is not None else "unknown"
        return f"Array<{inner}>"
    if type_ == "object" or "properties" in schema:
        return _object_ts(schema, defs, prefix, decls)
    return "unknown"


def _object_ts(schema: dict, defs: dict, prefix: str, decls: list[str]) -> str:
    props = schema.get("properties") or {}
    required = set(schema.get("required") or [])
    lines: list[str] = []
    for key, subschema in props.items():
        description = _schema_description(subschema)
        constraints = _schema_constraints(subschema)
        if constraints:
            description = f"{description} ({constraints})" if description else constraints
        if description:
            lines.append(f"  /** {description} */")
        optional = "" if key in required else "?"
        lines.append(f"  {json.dumps(key, ensure_ascii=False)}{optional}: {_ts(subschema, defs, prefix, decls)};")
    additional = schema.get("additionalProperties")
    if additional:
        value = _ts(additional, defs, prefix, decls) if isinstance(additional, dict) else "unknown"
        lines.append(f"  [key: string]: {value};")
    if not lines:
        return "Record<string, unknown>"
    return "{\n" + "\n".join(lines) + "\n}"


def _schema_description(schema: Any) -> str:
    if not isinstance(schema, dict):
        return ""
    return _escape_comment(str(schema.get("description") or ""))


def _schema_constraints(schema: Any) -> str:
    """Render compact JSON-schema defaults and bounds for JS callers."""
    if not isinstance(schema, dict):
        return ""
    parts: list[str] = []
    if "default" in schema:
        parts.append(f"default={json.dumps(schema['default'], ensure_ascii=False)}")
    for key, label in (("minimum", "min"), ("exclusiveMinimum", "min>"),
                       ("maximum", "max"), ("exclusiveMaximum", "max<")):
        if key in schema:
            parts.append(f"{label} {schema[key]}")
    return _escape_comment("; ".join(parts))


def _escape_comment(text: str) -> str:
    """Escape a schema description for safe inclusion in a block comment."""
    return text.replace("*/", "*\\/").replace("/*", "/\\*").strip()


def _alias_base(name: str) -> str:
    words = "".join(char if char.isascii() and char.isalnum() else " " for char in name).split()
    alias = "".join(word[:1].upper() + word[1:] for word in words) or "Tool"
    if alias[0].isdigit():
        alias = f"T{alias}"
    return alias


def _def_name(prefix: str, def_name: str) -> str:
    cleaned = "".join(
        char if char.isascii() and (char.isalnum() or char == "_") else "_"
        for char in def_name
    )
    if cleaned[:1].isdigit():
        cleaned = f"T{cleaned}"
    return f"{prefix}_{cleaned}"


def _js_ident(name: str) -> str:
    """Guest functions are called as tools.NAME(args); quote exotic names."""
    if (
        name
        and name[0].isascii()
        and (name[0].isalpha() or name[0] in "_$")
        and all(char.isascii() and (char.isalnum() or char in "_$") for char in name[1:])
    ):
        return name
    return json.dumps(name, ensure_ascii=False)
