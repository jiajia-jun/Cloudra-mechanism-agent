# MCP Tool Injection Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans for the shared integration and delegate the independent SDK/configuration component. Track the checkboxes below.

**Goal:** Allow configured external stdio and HTTP MCP services to contribute individual tools to Cloudra's existing tool surface.

**Architecture:** Keep built-in tool discovery cached. Scope an application's external entries through the existing async execution boundaries with a ContextVar; all existing catalog consumers continue to use one `get_tools_lst()` entry point. Add JSON Schema accessors and an external async callback to `ToolEntry`; local Pydantic validation stays local. The SDK manager owns connections for the API lifespan.

**Tech Stack:** Python 3.11+, Pydantic, official MCP SDK, pytest.

**Spec:** `docs/superpowers/specs/2026-11-03-mcp-tool-injection-design.md`

## Global Constraints

- Support stdio and Streamable HTTP with the same discovery/result adapter.
- Preserve native Pydantic validation, permissions, invocation events and scientific acceptance.
- No regular expressions for validation, no synchronous blocking inside async functions, no arbitrary QM process termination.
- External JSON Schema stays intact; the server validates its business inputs.
- Configuration is loaded at startup; existing Agent capability snapshots are preserved.
- Delivery is a PR to master; do not merge or push master without a new explicit instruction.

## Review Focus

- Two applications must never share external connections or entries.
- MCP names must not intercept native controls, and must remain valid in JS examples.
- Structured output schema must describe the actual result envelope.
- Missing SDK/config errors must be explicit without exposing credentials.
- Both transports must close in the same task that opened their SDK contexts.

## Task 1: Shared catalog and execution

Files: `cloudra/tools/__init__.py`, `cloudra/tools/capabilities.py`, `cloudra/runtime_v2/{agent_host,agent_runner,adapters,invocation}.py`, `tests/test_mcp_tool_catalog.py`.

Interfaces: `ToolEntry.input_json_schema()/output_json_schema()/wire_schema()`, optional `external_call(arguments)` and `required_permissions`; `use_tool_entries(entries)` scopes application-owned entries; `core.external_tools` holds only that core's external entries.

- [x] Write failing behavior tests for scoped discovery, JSON Schema preservation, policy defaults, native-name isolation and actual execution through the existing executor.
- [x] Run the new tests and observe missing-feature failures.
- [x] Implement the shared entry accessors and context scope; bind Agent creation, runner tasks and invocation/executor boundaries.
- [x] Keep built-in execution and Supervisor policy behavior intact; use the existing permission model for external calls.

## Task 2: SDK connections and configuration

Files: new `cloudra/tools/mcp.py`, configuration models/loading in `cloudra/infra/config.py`, `pyproject.toml`, `uv.lock`, `tests/test_mcp_tools.py`, `tests/fixtures/mcp_server.py`.

Interfaces: `MCPToolManager(servers).lifespan(entries)` opens SDK connections and populates the supplied external-entry list; context exits close connections. Server config uses `command/args/env/cwd` or `url/headers`, plus existing PermissionSet requirements. No SDK imports when no servers are configured.

- [x] Test configuration validation and round trips before implementation.
- [x] Test real fixture discovery/call/errors over stdio and loopback HTTP using one parametrized suite.
- [x] Implement SDK-only connection handling, pagination, deterministic names and a single result adapter.
- [x] Preserve content blocks and structured output; expose SDK absence and per-server failures clearly.

## Task 3: Protocols, startup, documentation and delivery

Files: `cloudra/runtime_v2/tool_catalog.py`, `cloudra/tools/documentation.py`, `cloudra/services/api_v2/app.py`, relevant tests and configuration docs, `AGENTS.md`.

- [x] Write failing tests showing an external raw JSON Schema survives traditional schemas, JS declarations and on-demand documentation.
- [x] Migrate schema consumers to shared entry accessors and integrate SDK manager with application lifespan.
- [x] Adapt MCP image blocks to existing workspace image artifacts without discarding the original result.
- [x] Run compileall, ruff, and the directly affected test modules; do not run the full suite.
- [x] Independent whole-change review; fix material findings and rerun affected checks.
- [ ] Update design status and usage docs; commit all workspace changes, push this branch and create a PR to master.

## Execution ledger

- User approved SDK, both transports, and individual injection; execution proceeds without another plan approval.
- Work stays in the existing workspace on `codex/mcp-tool-injection`; no selective checkout is created.
- User changed delivery to PR and requested the default delivery rule in AGENTS.md be updated.
- AGENTS.md was delivered separately in PR #252, containing only the delivery-rule change.
- Review fixes: isolated each SDK connection in its own owner task; sanitized configuration and transport failures; preserved readable structured-only results; hid missing MCP tools in current projections without changing saved Agent capabilities.
- Final validation: 21 changed Python files compile and pass Ruff; 283 relevant tests passed, 6 existing dependency deprecation warnings. No full suite or real QM jobs ran.
