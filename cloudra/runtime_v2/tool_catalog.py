"""Tool catalog: registry schemas, JS declarations and protocol wire exposure.

Single source for the invocation-protocol-aware tool surface:

- ``wire_tool_schemas(agent, tool_names)`` — what the model *sees*:
  traditional runs get the permitted business schemas; javascript runs get
  ``js_exec`` plus the permitted direct controls (stop / ask_user /
  schedule).  This is not a privilege grant: js_exec runs pure guest logic
  and every actual tool call rechecks capabilities at admission, so a
  read-only role may select the JS protocol without gaining bash.
- ``tool_declarations(tool_names, *, visual_mode)`` — deterministic
  TypeScript-like declarations of the guest-callable tools, generated from
  the loaded ToolEntry input/output classes.  Declarations are model
  instructions (documentation); the guest receives only names, never a
  typechecker.  Unknown JSON-schema constructs render as ``unknown`` — never
  silently widened to ``any`` and never invented.
- ``validate_wire_route`` — stable protocol errors for misrouted calls
  (js_exec in traditional mode, top-level business calls in JS mode, direct
  controls inside a guest program).  Misrouted calls are never executed.
"""

from __future__ import annotations

import json
import re
from typing import Any, Iterable

from cloudra.runtime_v2.schemas import (
    AgentSession,
    InvocationProtocol,
    OrchestrationMode,
    effective_invocation_protocol,
)
from cloudra.tools.capabilities import (
    dag_review_decision_tools,
    dag_tools,
    is_direct_only,
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


def js_exec_schema():
    return {"type": "function", "function": {
        "name": "js_exec",
        "description": "Run one bounded JavaScript program to orchestrate available tools. "
                       "The program is the only tool call in this response; use await tools.NAME(args), "
                       "then text(value). Backend calls execute serially. Direct controls stay top-level.",
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
                "control and cannot be called from inside a JavaScript program; "
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
    names = {str(n) for n in (tool_names or []) if n and n != "*"}
    if tool_names and "*" in tool_names:
        from cloudra.tools import get_tools_lst

        names |= {entry.tool_name for entry in get_tools_lst() if entry.tool_name}
    return sorted(names)


def guest_tool_names(
    tool_names: Iterable[str] | None,
    *,
    visual_mode: bool = True,
    orchestration_mode: OrchestrationMode | str = OrchestrationMode.STANDARD,
) -> list[str]:
    """Names callable inside a JS program: no direct controls, visual-gated,
    and gated by the run's orchestration mode (dag_* tools are hidden in
    standard mode; Supervisor verdict tools outside dag_guided)."""
    gated = frozenset() if visual_mode else visual_tools()
    hidden = _mode_hidden_tools(orchestration_mode)
    return [
        name
        for name in _resolve_names(tool_names)
        if not is_direct_only(name) and name not in gated and name not in hidden
    ]


def wire_tool_schemas(agent: AgentSession, tool_names: list[str] | None) -> list[dict]:
    """Protocol- and orchestration-mode-aware wire projection for one LLM request.

    Traditional: the permitted business schemas (unchanged legacy surface).
    Javascript: ``js_exec`` plus the permitted direct controls only.  Tools
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
    hidden = _mode_hidden_tools(agent.settings.orchestration_mode)
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
) -> str:
    """Deterministic JS-mode instructions appended to the model request.

    Describes the execution envelope, JSON serialization, explicit output,
    the serial backend, the fixed limits and the direct-only controls; the
    generated declarations are documentation, not executable guest input.
    """
    declarations = tool_declarations(
        tool_names, visual_mode=visual_mode, orchestration_mode=orchestration_mode
    )
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
        "- Direct controls (stop, ask_user, schedule) are NOT callable inside "
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
        "Available tool functions and their argument/data types:\n"
        f"{declarations}"
    )


def tool_declarations(
    tool_names: Iterable[str] | None,
    *,
    visual_mode: bool = True,
    entries: list | None = None,
    orchestration_mode: OrchestrationMode | str = OrchestrationMode.STANDARD,
) -> str:
    """Deterministic TypeScript-like declarations for guest-callable tools."""
    names = guest_tool_names(
        tool_names, visual_mode=visual_mode, orchestration_mode=orchestration_mode
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
        # Tool descriptions carry workflow, permission and failure guidance
        # that input-schema docstrings often omit. Preserve that contract in
        # the JS declaration; the schema remains the source for argument types.
        description = str(getattr(entry, "tool_description", "") or "").strip()
        if not description:
            description = _schema_description(_input_schema_of(entry))
        # Keep generated comments valid even if a tool description contains a
        # comment terminator.
        description = description.replace("*/", "* /")
        comment = f"  /** {description} */\n" if description else ""
        functions.append(
            f"{comment}  {_js_ident(name)}(args: {args_type}): Promise<ToolResponse<{data_type}>>;"
        )
    sections.append("declare const tools: {\n" + "\n".join(functions) + "\n};" if functions
                    else "declare const tools: Record<string, never>;")
    sections.append(_DECLARATION_FOOTER)
    return "\n\n".join(sections)


def _input_schema_of(entry) -> Any:
    return getattr(entry, "input_schema", None) if entry is not None else None


def _render_tool_types(name: str, entry) -> tuple[list[str], str, str]:
    """Render one tool's input/output schemas; returns (decls, args_type, data_type)."""
    if entry is None:
        record = "Record<string, unknown>"
        return [], record, record
    alias = _alias_base(name)
    decls: list[str] = []
    args_type = f"{alias}Args"
    data_type = f"{alias}Data"
    input_schema = _input_schema_of(entry)
    output_schema = getattr(entry, "output_schema", None)
    decls.extend(_render_alias(args_type, _json_schema(input_schema)))
    decls.extend(_render_alias(data_type, _json_schema(output_schema)))
    return decls, args_type, data_type


def _json_schema(schema_cls) -> dict:
    if schema_cls is None or not hasattr(schema_cls, "model_json_schema"):
        return {}
    return schema_cls.model_json_schema()


def _render_alias(alias: str, schema: dict) -> list[str]:
    """Render ``type Alias = ...`` for one root schema plus its $defs."""
    defs = schema.get("$defs") or {}
    decls = []
    for def_name in sorted(defs):
        rendered = _ts(defs[def_name], defs, alias)
        decls.append(f"type {_def_name(alias, def_name)} = {rendered};")
    body = {k: v for k, v in schema.items() if k != "$defs"}
    decls.append(f"type {alias} = {_ts(body, defs, alias)};")
    return decls


def _ts(schema: Any, defs: dict, prefix: str) -> str:
    if not isinstance(schema, dict):
        return "unknown"
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
            parts = [_ts(part, defs, prefix) for part in schema[key]]
            return " | ".join(parts) if parts else "unknown"
    if "allOf" in schema:
        parts = [_ts(part, defs, prefix) for part in schema["allOf"]]
        return " & ".join(f"({part})" for part in parts) if parts else "unknown"
    type_ = schema.get("type")
    if isinstance(type_, list):
        parts = [_ts({**schema, "type": item}, defs, prefix) for item in type_]
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
        items = schema.get("items")
        inner = _ts(items, defs, prefix) if items is not None else "unknown"
        return f"Array<{inner}>"
    if type_ == "object" or "properties" in schema:
        return _object_ts(schema, defs, prefix)
    return "unknown"


def _object_ts(schema: dict, defs: dict, prefix: str) -> str:
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
        lines.append(f"  {json.dumps(key, ensure_ascii=False)}{optional}: {_ts(subschema, defs, prefix)};")
    additional = schema.get("additionalProperties")
    if additional:
        value = _ts(additional, defs, prefix) if isinstance(additional, dict) else "unknown"
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
    words = re.sub(r"[^0-9A-Za-z]+", " ", name).split()
    alias = "".join(word[:1].upper() + word[1:] for word in words) or "Tool"
    if alias[0].isdigit():
        alias = f"T{alias}"
    return alias


def _def_name(prefix: str, def_name: str) -> str:
    cleaned = re.sub(r"[^0-9A-Za-z_]", "_", def_name)
    if cleaned[:1].isdigit():
        cleaned = f"T{cleaned}"
    return f"{prefix}_{cleaned}"


def _js_ident(name: str) -> str:
    """Guest functions are called as tools.NAME(args); quote exotic names."""
    if re.fullmatch(r"[A-Za-z_$][0-9A-Za-z_$]*", name):
        return name
    return json.dumps(name, ensure_ascii=False)
