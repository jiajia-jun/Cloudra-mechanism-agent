# Event-driven invocation and JavaScript runtime design

Status: implementation specification, based on the user-approved discussion. Baseline: `322a389` (`fix: complete DAG-guided review flow and update research artifacts`). This document fixes engineering choices for Luna; it does not change scientific policy.

## 1. Objective and boundaries

Cloudra remains a Python, append-only, event-sourced research runtime with FP decisions and imperative effects. Introduce a JavaScript execution shell that submits tool requests to the same event-driven invocation service as traditional tool calls. Do not introduce a second tool implementation, policy engine, DAG engine, scheduler, or generic protocol-plugin framework.

Two invocation protocols: `traditional` (default) and `javascript`. Resolve the configured protocol when `run.started` is produced and project it into `CurrentRun.invocation_protocol`. Changing settings affects the next run only. Waiting/resuming, compaction, retries, and multiple programs within the same run retain that protocol. Only this field is frozen; permissions and safety settings must still be checked at each actual call. No silent protocol fallback.

The model writes ECMAScript JavaScript with top-level await. The optional JS host is Node >=22 and `quickjs-emscripten` exactly `0.32.0`, using QuickJS compiled to WASM. Host code is ESM `.mjs` with JSDoc; no TypeScript transpilation/build stage. TypeScript-like tool declarations are generated documentation, not executable user input. Existing Python >=3.11/POSIX requirements remain unchanged. The new npm package is optional and separate from the frontend and Python dependencies.

## 2. Invocation service, not passive audit hooks

`InvocationService.invoke(ctx, call, *, execution_id=None)` is the sole live entry for actual tool calls. It owns request recording, policy stages, the underlying `ToolExecutor`, result recording, post-tool stages and image artifacts. Traditional dispatch and JS RPC both await this method. No raw `LegacyToolExecutor.execute` calls from the JS host, no direct execution from event subscribers, and no execution during `apply_event`/replay.

Lifecycle:

1. Append `tool.requested` with host-bound project/session/run/call identity and a detached JSON arguments snapshot; durably flush before policy or tool effects.
2. Run existing `before_tool` stages in their existing order. Preserve their current intentional IO exemptions; this change does not purify the entire DAG subsystem.
3. On block or ask: append the existing diagnostic event and `tool.finished(status=blocked|waiting, effect_state=not_started)`; do not emit `tool.started` and do not execute the tool. Traditional `ask` preserves `wait_approval`, including DAG review-worker semantics.
4. On allow: durably append `tool.started`, then invoke the existing executor once. Existing schema validation in the executor must remain before the actual tool implementation.
5. On normal return: durably append `tool.result_recorded` with a detached structured result before post-tool hooks. A tool returning `is_success=false` is a normal result, not an interpreter exception.
6. Run all existing `after_tool` hooks and artifact registration exactly once; durably append `tool.finished` with final summary/metadata, then resolve the caller.
7. Executor exceptions produce terminal failure with `effect_state=unknown`; postprocessing failures use `effect_state=completed` and retain the raw-result event reference. Failures before entry have `not_started`. Never claim rollback or exactly-once external execution.

Use a small pure `decide_invocation` function to freeze/validate the request envelope and produce the request event plus an `InvokeTool` effect description. The imperative service commits the event before executing this effect. An effect is data, not an event subscriber that runs on replay. Keep invocation effects in the invocation subsystem; do not put an awaited multi-hour tool operation inside CommandBus's command-response path.

Event flushing is a shared infrastructure operation: append in memory, explicitly persist with `RuntimeStore` when present, then publish for visibility. A failing database write must stop dispatch; EventHub's swallowed observer exceptions cannot be the persistence guarantee. Persist preceding unflushed log entries in order, so a durable tool request cannot be restored without its project/run ancestors. Share the writer between CommandBus, pipeline/runner and pending broker. Do not hold a flush lock across subscriber callbacks (callbacks may submit commands). Hub publication is idempotent for persistent event IDs; seq=0 streaming chunks are never deduplicated. Replay does not publish.

Do not add an unbounded second authoritative invocation-state table. UI and recovery derive lifecycle from events. Futures/queues/cursors are explicitly ephemeral. On restore, append terminal interruption facts for unfinished programs/calls without retrying side effects, then retain the existing failed-run/pending-expiration behavior. A raw result proves tool completion even if postprocessing was interrupted.

## 3. JS API and transport

JS-mode model wire tools are `js_exec({code:string})` plus the existing direct-only controls `stop`, `ask_user`, `schedule`, subject to capability/visual filtering. Declare direct-only semantics once in `ToolRegistration` and expose them through `tools/capabilities.py`; never scatter a new tool-name set. Other tools are callable only inside JS in JS mode. Traditional mode does not expose `js_exec`. These routing rules must be enforced by the host, not only by hiding schemas.

`js_exec` is a protocol execution request, not a chemical tool and not DAG evidence. Do not register it as a normal tool implementation. A protocol policy stage may reject incorrect top-level routes before execution; `tools.*` requests are always real calls through InvocationService. `stop` inside JS is rejected as direct-only, with no stop effect. Script completion is not run completion.

The sandbox exports a null-prototype, frozen `tools` object of capability-filtered functions and `text(value)`. It exposes no filesystem, network, Node globals, module loader, package installer, timers, or event appender. Standard objects, JSON, arrays, Promise, conditionals, loops and try/catch are available. `tools[name](args)` returns this uniform envelope:

```ts
interface ToolResponse<T> {
  call_id: string;
  is_success: boolean;
  summary: string;
  data: T;
  duration_ms: number;
}
```

Expose input and output schema from the existing tool class via the catalog. Generate deterministic declarations (including `$defs`/`$ref`, enums, required properties, arrays, nullable types, unions and additionalProperties; unknown forms become `unknown`, never invented types). Known functions get typed `data`; undeclared extra/test tools use `Record<string, unknown>`.

Use a separate Node process per program. Python launches a fixed absolute packaged entrypoint with `asyncio.create_subprocess_exec`, never a shell. Model source travels over stdin, never argv, `NODE_OPTIONS` or a temporary executable script. stdin/stdout carry one bounded JSON object per line; stderr is separately drained with a cap. Python binds all authority to the process/session handle; host messages cannot choose project/run identity or mint event IDs.

Protocol version is 1. Python sends `{type:"start",version:1,execution_id,code,tools:[names],limits}` and `{type:"tool_result",request_id,result}` or `{type:"tool_error",request_id,error}`. Node sends `{type:"ready",version:1}`, `{type:"tool_call",request_id,name,arguments}`, `{type:"output",value}`, and exactly one `{type:"finished",status,error?}`. Request IDs are unique per program, maximum 128 characters, local correlation only. Python assigns `new_id("tc")` for actual call identity and rejects duplicate IDs. Unknown message types, malformed messages, oversized lines, unknown reply IDs, duplicate finish, and messages after finish are protocol errors.

Guest/host crossings clone JSON data; never expose host object or Promise references. Host owns QuickJS deferred promises and pumps pending jobs explicitly. After the program's top-level promise settles, any unawaited pending tool promises mean `unawaited_tool_calls`, not silent success; stop accepting new calls and account for all accepted calls.

Exact event payload additions (existing standard envelope scope fields are unchanged):

- Every child lifecycle event: `tool_call_id`, `tool_name`, `execution_id` (nullable).
- `tool.requested`: additionally `arguments_summary` (detached argument object).
- `tool.started`: same arguments and correlation fields; the event means policy admitted, executor is about to be entered.
- `tool.result_recorded`: additionally `result={is_success,summary,data,duration_ms}` (immutable raw snapshot).
- `tool.finished`: additionally `status` (`completed|failed|blocked|waiting|cancelled|interrupted`), `effect_state` (`not_started|completed|unknown`), `is_success`, `result_summary`, `duration_ms`, nullable `raw_result_event_id`, nullable `error={code,message,stage?}`; existing image artifact fields stay intact. A normal unsuccessful business result has status failed and effect_state completed.
- `program.submitted`: `execution_id`, `outer_tool_call_id`, `code`, `source_hash` (lowercase SHA-256 of original UTF-8 bytes).
- `program.started`: `execution_id`, `outer_tool_call_id`.
- `program.output`: `execution_id`, `output_index` (zero based), `value` (JSON).
- `program.finished`: `execution_id`, `outer_tool_call_id`, `status`, `duration_ms`, nullable `error={code,message,call_id?,tool_name?,line?,column?,effect_state?}`, `calls` (receipt array), optional `control_decision="wait_approval"`.
- Each receipt: `call_id`, `tool_name`, `status`, `effect_state`, nullable `raw_result_event_id`; no invented result references. Aggregate result data uses the same fields plus `outputs` (JSON array), `image_paths` when available. Outer is_success reflects program completion, not a claim that all business calls succeeded; UI shows failed child count independently.

`PolicyResult.ask` is currently needed by direct stop/review control. If a future non-control guest tool produces ask, terminate that execution unit with `policy_wait`, set `control_decision="wait_approval"`, and have TurnPipeline return wait_approval with the completed outer exchange. Do not rerun it or keep a second in-memory interpreter continuation; the existing broker/worker notification wakes the run. This control handoff is host-owned and cannot be swallowed by guest catch. PendingBroker approvals inside a tool, in contrast, keep that tool and its guest Promise genuinely awaiting the user as today.

## 4. Safety limits and deployment

Fixed first-release limits (engineering limits, not scientific thresholds): source 64 KiB UTF-8; arguments 64 KiB UTF-8; RPC line 2 MiB; tool-result data delivered into guest 1 MiB; cumulative explicit program output 64 KiB / 256 entries; 64 total tool requests; 16 pending requests; one active tool per agent/program FIFO; QuickJS heap 64 MiB; guest stack 512 KiB; cumulative active guest-evaluation time 5 seconds; host startup timeout 10 seconds; watchdog stale-host timeout 15 seconds when no tool is outstanding; Python kill/reap grace 2 seconds. All limits are code constants with injectable smaller values in tests, not user-editable LLM arguments.

CPU/evaluation timing covers initial evaluation and each microtask pump; it excludes waiting for tools/approvals. Use QuickJS interrupt checks plus Python external supervision; do not rely solely on a Node timer. Pending tool requests retain existing tool and PendingBroker lifecycles. A long active tool is not killed by the JS idle watchdog. A permanently pending JS promise with no outstanding external operation fails `unresolved_promise`.

First release serializes the entire before/execute/after lifecycle for an agent, even if JS uses Promise.all. This preserves current DAG/pending semantics. Queue admission limits still apply. Do not silently claim tool parallelism; prompt and UI explain serial execution. Future audited parallelism is not part of this change.

Node receives only a minimal environment (PATH plus locale/timezone values when needed), fixed cwd outside the user's workspace, no inherited secrets and no extra file descriptors. QuickJS has no imported FS/network capabilities. Node heap is additionally bounded with `--max-old-space-size=128`; document that this is not an OS RSS limit. No `node:vm`, direct eval of guest code in Node, `vm2`, guest npm, or `--permission` as the claimed security boundary.

The supported first-release threat model is a local single-user runtime containing untrusted generated JS within QuickJS-WASM plus a killable process and a hostile-input-checked bridge. This is not a hardened multi-tenant OS sandbox. Node/engine vulnerabilities are residual risk. Do not pretend minimal cwd/env prevents a compromised host from reading files. OS sandbox/containers are explicitly out of scope, not silently implemented differently on macOS/Linux.

Install is explicit: `npm ci --prefix cloudra/runtime_v2/js_host --ignore-scripts --no-audit --no-fund`. Commit a lockfile when commits are authorized; include it as a normal deliverable otherwise. Never auto-install during execution or server startup. Missing Node/dependency reports `runtime_unavailable`, keeps the chosen protocol, and never falls back to unsafe evaluation/traditional mode. Existing traditional installs require no JS dependency. Include `.mjs`, manifests, tests as appropriate in package data, never `node_modules`; document the corresponding command for the installed package directory. No changes to frontend npm dependencies.

## 5. Failures, cancellation and retry

Business failure and argument validation: resolve `ToolResponse(is_success=false)`. Policy denial: reject a guest `ToolCallError` with code `policy_blocked`, stage and host call ID; catching it does not grant authority. Unexpected executor failure: reject with `tool_exception`, `effect_state=unknown`. Post-hook failure: reject `postprocessing_failed`, `effect_state=completed`, with raw-result reference. Sanitized guest errors include code, message, call_id, tool_name, effect_state and optional source location. Never inject a Python traceback or secrets into guest output.

Uncaught JS errors end that program and return an ordinary failed `js_exec` exchange to the model, preserving preceding outputs, child-call statuses and event references. A new model turn can repair the program. Do not raise a retryable generic exception into AgentRunner after program execution started. Interpreter startup failures are similarly reported explicitly; persistent storage failures must fail the run, not continue after an unaudited effect. Unexpected ordinary-tool infrastructure exceptions also must not cause automatic replay of completed earlier calls in a batch.

On guest failure stop admission, cancel not-yet-started queue entries (`not_started`), and allow an already-active real tool to settle and record its outcome before closing the program. If a tool's own timeout fires, record `unknown` where appropriate. On explicit user/run cancellation kill/reap only the JS host, cancel the bridge waiters and propagate existing tool cancellation behavior. Never add a path killing scheduler/guard/QM jobs; their independently submitted lifecycle survives the program. Cancellation and runtime limits are host terminal conditions, not catchable authorization grants.

Durable storage failing after an external action leaves an uncertain action; do not fabricate a success event, retry, or issue more tools. Later restore marks the incomplete lifecycle with the known/unknown effect state. The JS process/heap is never checkpointed or restored across process restart.

## 6. Model feedback versus audit

Outer `js_exec` exchanges remain ordinary function-tool wire exchanges for current model providers; do not change to hosted OpenAI Programmatic Tool Calling or require an API migration. The model history includes original source and one aggregate result; inner tools are audit events, not extra fabricated assistant tool calls.

Aggregate result: execution_id, status, outputs, structured error if any, and child call receipts (call_id/name/status/effect_state/raw_result_event_id where available). Completed child result data lives in `tool.result_recorded`. Include small receipt summaries, not all raw results. Never truncate silently; report output/bridge limits explicitly. Existing tool image artifacts remain registered; propagate the validated child image paths through the outer ToolResult for the existing vision-gated history path. Program output itself is not scientific evidence.

Existing Knowledge/DAG notices still reach the next LLM turn; preserve them outside JS's text filtering. Programs are short deterministic blocks, not autonomous multi-hour research loops. No store/load cross-program state, arbitrary filesystem helpers, code step tracing, or tool search in this release.

## 7. Event/UI contract

New events: `tool.requested`, `tool.result_recorded`, `program.submitted`, `program.started`, `program.output`, `program.finished`. Existing tool terminal/diagnostic event names remain but their semantics are corrected (`started` only after admission). All program events have host execution_id; child tool events have execution_id or null. `program.submitted` carries original code (bounded 64 KiB) and SHA-256; no workspace JS file is authoritative. Append source once before launch. `program.output` entries have monotonically increasing output_index. `program.finished` status is completed/failed/cancelled/interrupted and contains error/receipts/duration; it occurs only after all accepted children have terminal accounting.

Timeline is a pure event projection: one ProgramItem containing actual child ToolItems; traditional calls stay top-level. Rows distinguish queued, running, waiting, completed, failed, blocked, interrupted. Show completed/actually-requested counts, never a predicted final number. Deduplicate event IDs and group by execution_id, independent of finish order. Retain a visible fallback item for incomplete paginated history, without losing orphan child calls. A finished JavaScript program with failed child calls displays their count instead of a misleading all-green success.

Render source as escaped text in a read-only code panel with line numbers, copy, and download as `execution_id.js` from the event snapshot (Blob/object URL is sufficient). No HTML execution, editable replay button, or automatic full-program retry. An error shows code/call ID and source line if verified by the engine; never invent one. No syntax-highlighter dependency is required in this first release.

Approval/interaction events acquire the active tool_call_id/execution_id through a host-only ContextVar set by InvocationService. PendingBroker passes this metadata to existing attention projections. Show waiting child in the card and let AttentionDock focus the corresponding agent; no second approval workflow. Protocol selector sits in active-agent settings, affects the next run, and displays both configured and active values when different. Project default uses existing ProjectSettings.defaults; do not add global YAML options or project-wide fanout UI in this task.

## 8. Acceptance and exclusions

All existing DAG-guided review-worker, delivery stop, run wakeup and replay equivalence tests must pass without weakening scientific assertions. Both invocation modes hit the same policy and executor; a database-write failure proves no tool runs. Security tests execute actual JS for escape attempts, loops, output floods and Promise misuse. Node absence is a named skip only for Node-dependent tests; CI/local acceptance must additionally run the real host tests with dependencies installed.

No commits, pushes, merges, branch deletion, or edits to scientific datasets, research artifacts, chem thresholds, scheduler job handling, provider transports or unrelated existing code. The repository's explicit no-commit rule overrides skill commit checklists. Worktree creation requires the user's consent; planning can proceed without it. Only the specifically chosen optional npm host dependency is part of the approved JS feature; no other new dependencies without returning to the controller.

References checked during design: Node VM https://nodejs.org/api/vm.html; Node permissions https://nodejs.org/api/permissions.html; QuickJS wrapper APIs https://github.com/justjake/quickjs-emscripten. These explain mechanisms, not a claim of complete sandbox security.
