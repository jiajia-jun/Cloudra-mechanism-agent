# Tool protocols

[Documentation](README_EN.md) · [Architecture](ARCHITECTURE.md)

For developers integrating tools or changing agent execution. Installation requirements for users are in the [README](../README.md).

## Invocation

The default protocol is `javascript`; `traditional` is a per-agent opt-in. With the default, the model submits one bounded JavaScript program (`js_exec`) per wire exchange that orchestrates capability-permitted tools and reports results with `text(value)`:

```js
const result = await tools.log_parser({log_path: '/absolute/path/calculation.out'});
text({call_id: result.call_id, ok: result.is_success, data: result.data});
```

With `invocation_protocol: traditional` (Web UI agent settings, or the same field in a settings patch) the model instead issues one tool call per wire exchange and needs no JS host at all. Both protocols share the lifecycle and authority rules below; only the dispatch shape differs.

### Tool documentation loading

JavaScript agents retain a short directory of every permitted tool. The complete `get_tool_docs` and `update_memory` contracts are always included when those tools are available. Before the first real task in a new context, one temporary selection request chooses which additional complete contracts to preload. Selection considers relevant workflow guidance, planning, existing calculation or graph state, delivery checks and delegated results alongside execution tools; these are not all loaded by default. The default reuses the agent's effective model and credentials; it creates no additional agent. Read another current contract with `const r = await tools.get_tool_docs({names: ['log_parser']}); text(r.data.documents);`. Loading documentation does not grant permissions or limit calls to the initially selected tools. Traditional agents keep their full wire schemas.

In **Global config → 工具说明加载**, choose **现有模型** or **语义筛选**. Semantic selection supports a configured Jev endpoint (per-tool probability) or an already deployed local Reranker endpoint (indexed relevance scores, such as a BGE service). Set each backend's own boundary and optional maximum number of documents. Jev requires its own credential; Reranker credentials are optional. Cloudra does not download models or manage these services. Keys are write-only: leaving a field blank preserves its stored value, while the clear button atomically switches to the existing model and clears that backend's key.

Selection failure is recorded and shown in context; the main task can continue using the directory and on-demand reader. It does not switch backends automatically. Ordinary tasks, wakeups, approvals and process restores retain the initial selection; an explicit context reset selects again. Repeated contracts fold into name/version/reload references during context compaction. Changed contracts supersede older versions and must be reread. Settings apply to the first task of a new context, so changing them does not retrigger an existing selection.

Use `PYTHONPATH=. python scripts/benchmarks/tool_document_selection.py --output /tmp/tool-documents.json` for document-token estimates without network calls. Add `--run llm`, `--run jev` or `--run reranker` to explicitly evaluate configured services on eight fixed tasks. The report accepts alternative useful tool sets and records missing/unrelated documents, service status, selection usage and latency. Token estimates exclude the rest of the agent prompt; this script executes no scientific tools and cannot establish task completion or scientific acceptance.

- **Same lifecycle, same authority**: nested `tools.*` calls are real invocations through the same durable request → policy → executor → durable raw result pipeline as traditional calls. The protocol grants no extra authority — capabilities are rechecked at admission — and direct controls (`stop`, `ask_user`, `schedule`) remain top-level only.
- **Uniform ToolResponse**: every nested call resolves `{call_id, is_success, summary, data, duration_ms}`. Business failures resolve with `is_success: false`; policy denials reject with a catchable `ToolCallError` (`code` such as `policy_blocked`, plus `stage` and host call id) — catching it grants no authority.
- **Run-fixed setting**: the protocol is frozen when a run starts; changing the setting applies to the next run and never restarts or converts the active run.
- **Serial backend**: the full tool lifecycle runs one call at a time per agent, even if the program uses `Promise.all`. No tool parallelism is claimed.
- **Receipts, not hidden state**: `program.finished` records per-call receipts (`status`, `effect_state`, `raw_result_event_id`), program outputs and the sanitized error. The UI program card renders these events, and its source download is a snapshot of the durable `program.submitted` event.
- **No heap recovery, no auto-rerun**: the JS process/heap is never checkpointed. A restart marks unfinished programs and calls interrupted without retrying side effects; a failed program returns one ordinary failed exchange, and a later model turn may submit a repaired program.

### Installation

The guest runs in QuickJS-WASM inside a separate Node ≥ 22 process. Install the pinned host dependency once:

```bash
npm ci --prefix cloudra/runtime_v2/js_host --ignore-scripts --no-audit --no-fund
```

Cloudra never runs npm during execution or server startup. Missing Node or dependency makes `javascript` runs (the default protocol) report `runtime_unavailable` with no silent fallback; `traditional` runs need no JS dependency at all. For an installed (pip) package, run the same command against `<site-packages>/cloudra/runtime_v2/js_host`.

### Security boundary

The supported threat model is a **local single-user runtime** containing untrusted generated JS within QuickJS-WASM, a killable process, and a hostile-input-checked bridge: 64 KiB source cap, bounded JSON-lines transport, 1 MiB tool-result cap, CPU interrupt checks, a 15 s idle watchdog, `--max-old-space-size=128` (a V8 heap hint, not an OS RSS limit), minimal environment, and a fixed cwd outside user workspaces. This is **not a hardened multi-tenant OS sandbox**: Node/engine vulnerabilities are residual risk, and minimal cwd/env cannot stop a compromised host from reading files. OS-level sandboxes/containers are explicitly out of scope — do not run programs you would not trust on this machine.

## Codex account transport

Cloudra stores its independent OAuth session in `.codex_oauth.json` under its configured data directory, with owner-only permissions. It refreshes expiring access tokens and saves rotated refresh tokens under a process lock. Status queries are read-only. Login credentials are never returned to the Web UI or saved as model API keys.

Codex requests use the dedicated `https://chatgpt.com/backend-api/codex/responses` endpoint with `store=false`. Agent, compaction and auxiliary calls share this transport. The endpoint requires streaming; Cloudra also assembles a normal response for callers using `stream=false`. Generic sampling parameters (`temperature`, `top_p`) and output-token limits are omitted on this route.
