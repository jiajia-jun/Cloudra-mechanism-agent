# Tool Protocols

[Documentation](README_EN.md) · [Architecture](ARCHITECTURE.md)

This page is for developers working on tool integration or agent execution. For normal installation, see the [README](../README.md).

## `javascript` vs `traditional` Invocation

Cloudra defaults to the **`javascript`** protocol; **`traditional`** is available per agent in settings.

- **`javascript` (default)**: In each model turn, the agent sends one bounded JavaScript snippet (`js_exec`) that calls permitted tools and returns output with `text(value)`:

```js
const result = await tools.log_parser({log_path: '/absolute/path/calculation.out'});
text({call_id: result.call_id, ok: result.is_success, data: result.data});
```

- **`traditional`**: Classic one-tool-call-per-turn wire format, with no JS host required.

Both protocols enforce the exact same permissions, policy pipeline, and event recording—only the wire format differs:

- Every `tools.*` call inside JS still goes through the full durable `request → policy → executor → raw result` pipeline. Top-level control tools (`stop`, `ask_user`, `schedule`) stay top-level only.
- Each nested call resolves to `{call_id, is_success, summary, data, duration_ms}`. Normal tool failures resolve with `is_success: false`; policy blocks reject with a catchable `ToolCallError` (catching it never grants permission).
- Protocol choice is frozen for the duration of a run; changing it takes effect on the next run.
- Tool calls execute serially per agent even if the script uses `Promise.all`.
- Every call receipt is persisted in `program.finished`, and the UI program card renders from those events. The JS heap is never checkpointed—if the server restarts mid-script, unfinished programs are marked interrupted and never auto-replayed.

## On-Demand Tool Documentation Loading

JavaScript agents always see a short directory of permitted tools plus the full schemas for `get_tool_docs` and `update_memory` (when permitted). Before the first real task in a fresh context, Cloudra runs one lightweight selection pass to preload the full docs for the most relevant tools; any other tool's current contract can be fetched on demand via `tools.get_tool_docs({names: ['...']})`. Loading docs never changes permissions. Traditional agents always receive full wire schemas.

In **Global Settings → Tool Documentation Loading**, you can choose between **Existing Model** (default, reuses the agent's current model) and **Semantic Selection** (calls a configured Jev endpoint or a local Reranker service such as BGE). Cloudra does not download or manage those services. API keys are write-only, and clearing a key atomically switches back to the existing model.

If pre-selection fails, the error is surfaced in context and the agent simply continues using the directory and `get_tool_docs`. To benchmark selection quality and token cost offline, run `PYTHONPATH=. python scripts/benchmarks/tool_document_selection.py --output /tmp/tool-documents.json` (add `--run llm`, `--run jev`, or `--run reranker` to test live backends).

## JS Host Setup & Security Boundary

The JS runner executes generated code inside QuickJS-WASM hosted by a separate Node ≥ 22 process. Install its pinned dependencies once:

```bash
npm ci --prefix cloudra/runtime_v2/js_host --ignore-scripts --no-audit --no-fund
```

Cloudra never runs `npm` at runtime. If Node or the host package is missing, `javascript` runs fail loudly with `runtime_unavailable` instead of falling back silently.

The threat model is a **single-user local workstation**: QuickJS-WASM, a killable child process, 64 KiB source cap, 1 MiB tool-result cap, CPU interrupts, a 15 s idle watchdog, `--max-old-space-size=128`, minimal env, and a fixed cwd outside workspaces. It is **not** a multi-tenant OS sandbox—do not run untrusted code on a machine you need isolated at the OS level.

## Codex Account Transport

ChatGPT / Codex OAuth tokens are stored separately in `<data_dir>/.codex_oauth.json` with owner-only permissions (`0600`), refreshed under a file lock, and never exposed to the Web UI or mixed with normal API keys.

Requests go to `https://chatgpt.com/backend-api/codex/responses` with `store=false` (shared across agent turns, compaction, and helper calls). The endpoint always streams; Cloudra assembles a standard response when callers request non-streaming output, and omits unsupported sampling parameters (`temperature`, `top_p`, max output tokens).
