# Event-driven JavaScript Runtime Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (controller) or superpowers:executing-plans (Luna worker) to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Luna must not delegate or redesign; unresolved conflicts go to the controller.

**Goal:** Add a run-fixed JavaScript invocation runtime while preserving a single event-driven, policy-controlled tool backend and an auditable UI.

**Architecture:** Traditional calls and QuickJS programs both enter InvocationService. The service durably records requests before effects and raw results before postprocessing; the existing policy/tool/DAG implementations remain authoritative. JavaScript is a short-lived capability-limited execution shell, not an alternative tool system.

**Tech Stack:** Python >=3.11, asyncio, existing Pydantic/SQLite/event system, optional Node >=22, quickjs-emscripten 0.32.0, ESM JavaScript, existing React/TypeScript frontend.

**Spec:** `docs/superpowers/specs/2026-09-05-event-driven-js-runtime-design.md` (binding; read before coding).

## Global Constraints

- Baseline: `322a389`; preserve its DAG-guided review, stop, worker, mailbox and launch-group behavior.
- Protocol values: `traditional` and `javascript`; default javascript; frozen at run start, never silently switched.
- Existing Python >=3.11/POSIX requirements remain unchanged; optional JS host requires Node >=22.
- The only new third-party dependency is optional npm `quickjs-emscripten` exactly `0.32.0`; no Python or frontend dependency additions.
- All model-facing descriptions, prompts, errors and tool feedback are English.
- Authority changes are applied only by `apply_event`; no effects on event replay.
- Every tool request must be durable before any tool/policy side effect when a RuntimeStore is attached.
- No scientific-policy, scoring-threshold, chemistry-method, scheduler/guard/QM process-lifecycle changes.
- No arbitrary JS access to Node, network, filesystem, environment, process, event log or package loading.
- One active actual tool per agent/program; FIFO queues, bounded calls and pending requests. No true backend parallelism in this release.
- No automatic replay of a program or already-executed tool batch after an execution failure.
- No commits, pushes, merges or branch deletion without explicit user authorization. Skill instructions to commit are replaced by diff inspection and report checkpoints.
- Worktree/branch location is supplied by the controller after user consent. Do not create worktrees or switch branches yourself.
- Do not run real LLM requests, QM calculations or user-data mutations to validate this feature.

## Environment and handoff

The planning checkout is `/Users/cloudrayyy/Desktop/Cloudra-mechanism-agent-master`. It was clean at the start. Node is v26.7.0; npm is 11.19.0. `uv` is not on PATH, but `.venv/bin/python` is Python 3.11.16 with the current test dependencies. Use the controller-supplied absolute interpreter when working from a linked worktree; verify imports resolve to the worktree (`python -c 'import cloudra; print(cloudra.__file__)'`). Do not install a new global Python environment.

Baseline command already passed: `.venv/bin/python -m pytest -q tests/test_runtime_v2_pipeline.py tests/test_runtime_v2_adapters.py tests/test_runtime_v2_replay_equivalence.py` (31 tests; existing SWIG deprecation warnings only). Re-run as appropriate against your checkout. Use the existing repository test fixtures to isolate CLOUDRA_DATA_DIR.

Luna owns implementation and must send a report at each task boundary. Parent owns architecture rulings and independent review. Do not guess missing semantics. Do not stop for routine progress approval, but stop for a missing prerequisite, new dependency, safety-model change or contradictory contract. If the plan needs a change, provide the exact conflict and smallest candidate correction to the controller before writing it.

## File map

New Python files:

- `cloudra/runtime_v2/event_writer.py`: append/ordered persistence/publication shell shared by current writers.
- `cloudra/runtime_v2/invocation.py`: single tool lifecycle; no model/JS imports.
- `cloudra/runtime_v2/invocation_types.py`: immutable request/effect/outcome/error contracts and pure planners.
- `cloudra/runtime_v2/tool_catalog.py`: registry-based schemas, deterministic JS declarations, protocol wire exposure.
- `cloudra/runtime_v2/js_runtime.py`: Python process supervisor, RPC validation, program lifecycle and aggregate feedback.
- `cloudra/runtime_v2/js_protocol.py`: constants, bounded JSON frame validation, pure frame/result helpers.
- `cloudra/runtime_v2/invocation_context.py`: host-only ContextVar carrying active call/execution identity.

New host files under `cloudra/runtime_v2/js_host/`:

- `package.json`, `package-lock.json`: optional host package with exact dependency.
- `host.mjs`: trusted stdio transport, program setup/teardown and QuickJS scheduling.
- `sandbox.mjs`: guest capability setup, JSON cloning, promises, interrupt/memory limits.
- `host.test.mjs`: real interpreter tests using node:test and assert/strict.

New frontend files: `frontend/src/ProgramCard.tsx`, `frontend/src/ToolRow.tsx` (move the existing ToolRowView without altering behavior).

Modify existing wiring only where listed below. Do not split unrelated modules. The spec's excluded features must not appear as dormant scaffolding.

## Fixed shared contracts

Put these shapes in `invocation_types.py`; names are binding (annotations can use forward references to avoid cycles):

```python
@dataclass(frozen=True)
class InvocationError:
    code: str
    message: str
    effect_state: Literal["not_started", "completed", "unknown"]
    stage: str | None = None

@dataclass(frozen=True)
class InvocationOutcome:
    call: ToolCall
    result: ToolResult | None
    decision: Literal["continue", "wait_approval"] = "continue"
    error: InvocationError | None = None
    raw_result_event_id: str | None = None

@dataclass(frozen=True)
class InvokeTool:
    call: ToolCall
    execution_id: str | None = None

def decide_invocation(ctx: PipelineContext, call: ToolCall,
                      *, execution_id: str | None = None
                      ) -> tuple[EventDraft, InvokeTool]:
    # Freeze arguments with a JSON round-trip; bind scope from ctx, not args.
    frozen_call = ToolCall(call.id, call.name,
                          json.loads(json.dumps(call.arguments, allow_nan=False)))
    return EventDraft(
        "tool.requested", "agent", ctx.agent.project_id,
        ctx.agent.id, ctx.run_id,
        {"tool_call_id": frozen_call.id, "tool_name": frozen_call.name,
         "arguments_summary": frozen_call.arguments, "execution_id": execution_id},
    ), InvokeTool(frozen_call, execution_id)
```

Actual helpers must also reject non-dictionary arguments and missing/non-string IDs/names before construction. Exceptions at this boundary are `ValueError` with stable English messages and no side effects. The tool request itself is a fact, not authorization.

```python
EventWriter(event_log, event_hub=None, store_provider=None)
EventWriter.flush() -> Awaitable[None]
EventWriter.commit(draft: EventDraft) -> Awaitable[EventEnvelope]
EventWriter.mark_restored() -> None

InvocationService(*, event_writer: EventWriter, stages, tools,
                  artifact_registrar=register_workspace_image_artifact)
InvocationService.invoke(ctx: PipelineContext, call: ToolCall,
                         *, execution_id: str | None = None) -> Awaitable[InvocationOutcome]

JavaScriptRuntime(*, event_writer: EventWriter, invocations: InvocationService,
                  host_path: Path | None = None, limits: ProgramLimits | None = None)
JavaScriptRuntime.execute(ctx: PipelineContext, call: ToolCall) -> Awaitable[ToolResult]
```

The block above is interface notation, not a Python module to copy. Tasks below specify the algorithms and tests. `JavaScriptRuntime.execute` consumes the outer `js_exec` ToolCall, including its wire ID; nested IDs are separately host-generated. It returns one ToolResult for that wire exchange. It never re-enters run_turn or calls the model.

### Task 1: Durable run protocol and ordered event writer

**Files:** create event_writer.py; modify schemas.py, agent_host.py, apply.py, core.py, events.py, commands.py, pending.py, agent_runner.py; tests/test_runtime_v2_invocation_protocol.py and tests/test_runtime_v2_event_writer.py.

**Produces:** `InvocationProtocol`, `CurrentRun.invocation_protocol`, `configured_invocation_protocol(agent)` and `effective_invocation_protocol(agent)` in schemas.py; `core.event_writer`; EventWriter contract above. The configured helper reads agent.settings; effective reads current_run when present, otherwise configured for nonrunning agents.

- [x] Write protocol tests through real CommandBus: traditional default, reject unknown enum, start javascript run, change setting to traditional, active run stays javascript, finish/start uses traditional, waiting/resume keeps mode, replay and snapshot-tail equivalence keep mode, no API key enters run.started. Use the existing `_spawn_agent` fixture pattern, not direct state assignment for the path under test.
- [x] Run those tests red, then add `invocation_protocol: Optional[InvocationProtocol]` to RuntimeSettingsPatch, concrete default to RuntimeSettings and CurrentRun, include the selected string in run.started data and settings summary, and read it in `_apply_run_started`. Keep the existing synchronous pure planners; never copy all RuntimeSettings into CurrentRun.

```python
def test_protocol_is_frozen_only_on_run_start():
    agent = AgentSession(id="a", project_id="p", role_id="explorer")
    agent.settings.invocation_protocol = InvocationProtocol.JAVASCRIPT
    _, drafts = plan_start_run(agent)
    started = next(d for d in drafts if d.type == "run.started")
    assert started.data["invocation_protocol"] == "javascript"
    assert "api_key" not in started.data
```

- [x] Write EventWriter tests using a recording store and hub. Assert unflushed ancestors precede a request in storage, persistence failure propagates before any consumer/effect, and nested subscriber commands do not deadlock. Use an asyncio.Event barrier, not sleeps, for ordering assertions.
- [x] Implement `flush`: under one asyncio.Lock capture the unflushed event-log prefix; append each to current store via `asyncio.to_thread`; advance the persisted cursor only on success. Release lock before publishing. Track persistence and publication separately so a change from no store to an attached store persists earlier events without republishing them. `commit` appends one detached EventDraft then awaits flush and returns that envelope. Resolve store dynamically through `lambda: core.store` because API wiring attaches store later. Set core.event_writer during core construction. `mark_restored()` advances cursors to len(log) and marks historical event IDs as already published; call immediately after backfill, before adding recovery events. Test fresh store attachment after earlier memory-only events.
- [x] Make persistent EventHub publication idempotent by event_id while leaving seq=0 streaming unchanged. Track only ephemeral in-memory delivered IDs; mark before callbacks to prevent reentrant duplication. Keep observer exceptions diagnostic/non-authoritative. No lock held across callbacks. CommandBus `_flush`, PendingBroker live emissions and Runner flushing use the shared EventWriter; requests and approval decisions persist before future resolution. Existing store subscriber INSERT OR IGNORE can remain; it is no longer the write-ahead guarantee. Flush before CommandBus captures snapshot high-watermarks, preventing snapshots from referring to unpersisted events. Tests must cover reentrant subscriber commands with asyncio.wait_for as a deadlock guard.
- [x] Run task tests and existing command/pending/replay tests. Inspect `git diff --check`; record red/green commands and results. Do not commit.

### Task 2: Single event-driven tool invocation lifecycle

**Files:** create invocation.py, invocation_types.py, invocation_context.py; modify turn_pipeline.py, adapters.py, policies/base.py, pending.py, services/api_v2/app.py, benchmark/backend.py; tests/test_runtime_v2_invocation.py and existing pipeline/runner tests.

**Consumes:** EventWriter; **produces:** InvocationService and InvocationOutcome; traditional pipeline becomes its first caller.

- [x] Write tests asserting this exact successful sequence relative to fake hooks/executor: requested persisted → before → started persisted → executor → result_recorded persisted → after → finished persisted → return. Verify `after` sees structured raw data and a mutation of result.summary cannot mutate the earlier stored event.

```python
@pytest.mark.asyncio
async def test_effect_waits_for_durable_request():
    from cloudra.runtime_v2.core import RuntimeCore
    from cloudra.runtime_v2.event_writer import EventWriter
    from cloudra.runtime_v2.invocation import InvocationService
    from cloudra.runtime_v2.policies.base import PipelineContext, ToolCall, ToolResult
    from cloudra.runtime_v2.schemas import AgentSession, AgentCapabilities, PermissionSet, RuntimeSettings

    core = RuntimeCore(strict_events=True)
    agent = AgentSession(id="a", project_id="p", role_id="explorer")
    caps = AgentCapabilities(permissions=PermissionSet(read=True), tools=["echo"])
    ctx = PipelineContext(agent=agent, run_id="r", settings_snapshot=RuntimeSettings(),
                          capabilities=caps, inbox_messages=[], emit=lambda *args: None)
    observations = []
    class Store:
        def append_event(self, event):
            observations.append(event.type)
    class Executor:
        async def execute(self, agent, call):
            assert "tool.requested" in observations
            assert "tool.started" in observations
            return ToolResult(True, "ok", {"value": 7})
    store = Store()
    writer = EventWriter(core.event_log, store_provider=lambda: store)
    service = InvocationService(event_writer=writer, stages=[], tools=Executor())
    outcome = await service.invoke(ctx, ToolCall("tc1", "echo", {}))
    assert outcome.result.data == {"value": 7}
    assert observations == ["tool.requested", "tool.started", "tool.result_recorded", "tool.finished"]
```

- [x] Add tests for policy block and ask (no executor, no started); normal is_success=false; executor raising; after_tool raising; cancellation; store failure before execution; store failure after raw execution; two queued invocations serialize; arguments are detached; each call gets exactly one terminal event.
- [x] Implement the spec lifecycle. Move the existing loop guard and artifact-registration helpers into invocation.py, retaining any public helper imports by updating consumers, not adding compatibility shims. Keep ToolCall/ToolResult core contracts in policies/base.py. Add `error: InvocationError | None = None` to ToolResult only if needed to distinguish caught executor faults in LegacyToolExecutor, using TYPE_CHECKING to avoid import cycles; do not turn explicit tool business failures into exceptions.
- [x] Preserve LegacyToolExecutor's native bridges, YOLO context and Pydantic validation. Its unexpected safe_call exception becomes a ToolResult with structured `tool_exception` metadata; validation errors remain ordinary unsuccessful results. InvocationService converts that metadata into InvocationOutcome.error and terminal unknown effects. Existing providers/direct callers are adjusted explicitly rather than swallowing metadata.
- [x] Use a per-agent async lock around the whole lifecycle. While queued, no authorization is cached. At actual admission, derive current settings/capabilities from the trusted agent for real running sessions; refresh ctx settings but retain current_run protocol. Standalone pipeline tests pass explicit contexts. Set active call metadata via `ContextVar` with token reset in finally. PendingBroker adds that metadata to request events/list projections. Do not alter its approval or interaction decision mechanisms.
- [x] TurnPipeline receives optional `event_writer` and `invocations` dependencies, constructs a memory-only writer/service in standalone tests, and uses shared core writer in real API/benchmark wiring. Remove duplicated before/execute/after code. Convert InvocationOutcome to existing TurnOutcome, preserving stop content and DAG wait_approval handling. Executor/postprocessing errors must not trigger retry of completed prior calls: return structured feedback, never throw a generic retryable exception after a side effect. Storage errors use a dedicated non-retryable error checked by AgentRunner.
- [x] Update event-order tests intentionally for requested/result_recorded and started semantics; preserve scientific assertions. Test existing DAG-guided stop/review fixtures, method policy, permissions, images and notices. Diff-check and report; do not commit.

### Task 3: Catalog, routing and generated tool declarations

**Files:** create tool_catalog.py; modify tools/registry.py, tools/capabilities.py, tools/__init__.py if output_schema exposure needs a field, adapters.py; tests/test_runtime_v2_tool_catalog.py.

**Produces:** `JS_EXEC_NAME="js_exec"`, `js_exec_schema()`, `tool_declarations(tool_names, *, visual_mode) -> str`, `wire_tool_schemas(agent, tool_names) -> list[dict]`, `is_direct_only(tool_name)` capability projection. Native-search schema adjustments still happen in LegacyLLMProvider after protocol projection.

- [x] Write tests for empty capability list exposing no business tools, wildcard resolution, visual gating, generated required/optional args, output data field declarations, enum/array/nullable/refs, deterministic ordering and escaped descriptions/property names. No silent conversion of unknown JSON-schema constructs to permissive `any`.
- [x] Add `invocation_direct_only: bool=False` to ToolRegistration; mark stop, ask_user and schedule there (ensure their explicit tool_name is populated). All downstream decisions use capabilities.is_direct_only. No separate list in the JS runtime. These controls retain existing schemas, descriptions and authorization.

```python
def js_exec_schema():
    return {"type": "function", "function": {
        "name": "js_exec",
        "description": "Run bounded JavaScript to orchestrate available tools. "
                       "Use await tools.NAME(args), then text(value). "
                       "Backend calls execute serially. Use direct controls to stop or ask the user.",
        "parameters": {"type": "object", "properties": {
            "code": {"type": "string", "description": "JavaScript with top-level await."}},
            "required": ["code"], "additionalProperties": False}}}
```

- [x] Generate tool declarations from loaded ToolEntry input/output classes; use class model_json_schema and one deterministic schema renderer. Type aliases use sanitized stable names; actual property keys stay quoted. Render unknown forms as unknown and include schema descriptions as escaped comments. The guest receives only names; declarations go to model instructions, not a guest typechecker.
- [x] Traditional projection returns permitted normal schemas; JS projection returns js_exec and permitted direct controls. This is not a privilege grant: js_exec only executes pure guest logic and each actual tool rechecks capabilities. All roles may select JS even if their permission.script is false; that flag governs actual script-capable backend tools, which remain filtered. This avoids accidentally granting bash to read-only agents.
- [x] Add explicit routing validation helper `validate_wire_route(protocol, tool_name) -> str | None`. Traditional js_exec, JS top-level non-control business calls, and guest direct-only calls return stable protocol errors. Never execute hidden calls anyway. Add tests for each route. Run catalog and adapter tests and report.

### Task 4: Optional QuickJS host with bounded JSON bridge

**Files:** create js_protocol.py and all js_host files; modify pyproject.toml package-data and .gitignore; tests/test_runtime_v2_js_protocol.py.

**Consumes:** names and limits only; **produces:** validated protocol frames and host process from the spec, without Python tool execution yet.

- [x] Create package.json via apply_patch with type module, private true, engines node >=22, dependency quickjs-emscripten 0.32.0, script `test: node --test host.test.mjs`. Generate package-lock with npm (`npm install --package-lock-only --ignore-scripts --no-audit --no-fund`) and install locally with npm ci --ignore-scripts. Add the exact host node_modules directory to .gitignore; never commit/install global packages. Package .mjs and package manifests but not node_modules. No auto-install code.
- [x] Implement ProgramLimits as frozen dataclass in js_protocol.py with all numeric constants from spec; `to_wire()` emits snake_case JSON keys. Implement `decode_host_frame(line: bytes, *, limits: ProgramLimits) -> dict` with UTF-8, byte cap, object/type/field validation. Reject nonfinite JSON numbers, nested data beyond depth 64, duplicate object keys, unexpected top-level fields and identity claims. Nested business dictionaries may contain arbitrary schema-allowed string keys, including __proto__; clone them as data, never merge them into host objects or prototypes. Apply depth and size caps on both bridge directions before guest allocation.
- [x] Write real Node tests before sandbox implementation. Required programs include these exact probes:

```js
// Standard language works.
text([1, 2, 3].map(x => x * 2));
// Host globals are absent, including constructor-derived global access.
text([typeof process, typeof require, typeof fetch]);
text(({}).constructor.constructor('return typeof process')());
// Tool bridge, in the mock host, returns the documented envelope.
const r = await tools.echo({value: 7}); text(r.data.value);
// This must be interrupted by the external test timeout as a backup.
while (true) {}
// Pending jobs also consume the guest budget.
function again() { Promise.resolve().then(again); } again();
```

- [x] Implement sandbox.mjs with new QuickJS runtime/context per program, explicit heap/stack/interrupt limits and disabled module loader. Use evalCode as an ES module with filename `program-<execution_id>.js`, preserving original source line numbers. Inject frozen guest functions through vm.newFunction and vm.newPromise handles; convert values by JSON serialization, never export host objects. Return result/error handles through controlled helpers and dispose every handle/runtime in finally. All host callbacks reject use after program termination.
- [x] Implement host.mjs stdio parser and handshake. Queue result/error frames to settle the correct deferred promise; call executePendingJobs in bounded pumps. Count active evaluation time across pumps, not waiting time. Emit output and tool requests immediately; enforce total/pending quotas before accepting a callback. Drain microtasks before deciding success. Pending top-level promise with no outstanding tool means unresolved_promise. Top-level completion with outstanding tools means unawaited_tool_calls. Mark terminal before emitting finished; ignore late result frames only during teardown, otherwise protocol error.
- [x] Add tests for import('node:fs') rejection, no process.env, no console/process stdout escape, no cross-program variables, oversized args/results/output, circular text values, output count, 65th call, 17th pending request, syntax error location, unresolved promise and unawaited tool. Catching a limit error cannot allow another tool: host terminal flag must be checked independently of guest catches. Run Node tests and pure frame tests; report exact results.

### Task 5: Python program runtime and model-loop integration

**Files:** create js_runtime.py; modify turn_pipeline.py, adapters.py, services/api_v2/app.py, benchmark/backend.py, pending.py as necessary; tests/test_runtime_v2_js_runtime.py, tests/test_runtime_v2_js_pipeline.py.

**Consumes:** EventWriter, InvocationService, catalog, real host. **Produces:** JavaScriptRuntime.execute returning a single outer ToolResult; program lifecycle events and child receipts.

- [x] Write real-host integration tests with fake tools/no network: dependency chain, caught/uncaught exception, business failure, policy rejection, forbidden direct-control guest call, serial Promise.all, preserved output on failure, API identity forgery rejected, duplicate request ID rejected, output limits, cancellation and no whole-program retry.

```js
const first = await tools.echo({value: 3});
const second = await tools.echo({value: first.data.value + 1});
text(second.data.value);
```

Assert two distinct host call IDs, requested-before-effect for each, original code/hash in program.submitted, outputs == [4], and only the outer js_exec exchange in model history.

- [x] Implement execute admission: validate sole code field and UTF-8 length; generate execution_id in Python; append program.submitted before launch, capturing source/hash and outer_tool_call_id. Check Node version/entrypoint/dependency availability without running user code. Report runtime_unavailable on missing prerequisites, no fallback. Launch fixed argv with --max-old-space-size=128 and minimal env, temporary empty cwd, stdin/stdout/stderr pipes, start_new_session=True. Use async subprocess/readers, not sync subprocess calls in the event loop. Do not pass user code on argv.
- [x] Startup handshake uses 10-second timeout. Start the program only after program.started has been committed. Python validates frames independently of Node. A FIFO queue invokes one tool at a time through InvocationService; assign a new tc ID and host ContextVar correlation. Guest provided request ID is only a map key. Reject duplicate/request-after-terminal frames and enforce budgets again on Python side. Never trust host-provided scope or a guest result as a tool completion fact.
- [x] Send the documented ToolResponse envelope, JSON-cloned, only after the invocation's final event is durable. Convert InvocationOutcome.error into tool_error. Result >1MiB produces result_too_large with call ID and retained raw-result-event reference; do not rerun. Collect validated child images for outer ToolResult.data[image_paths]. Keep raw tool results out of outer aggregate except explicit text output. Use the spec's exact event payload and receipt names. An InvocationOutcome.decision=wait_approval becomes a host terminal policy_wait plus aggregate control_decision=wait_approval; run_turn returns that decision with the outer exchange and without adding the same outer call a second time as blocked_call. Test this with a fake asking stage; it is distinct from PendingBroker's live Promise pause inside an actual tool.
- [x] On guest failure close admissions, cancel queued not-started requests, let the single already-active tool settle, then commit program.finished with complete receipts. On explicit task cancellation stop/kill/reap the JS host (2-second grace), cancel bridge tasks, close pending approvals through existing cleanup and re-raise CancelledError. Do not kill compute jobs. Do not leave subprocesses/reader tasks behind on malformed output or database failure. Host watchdog is active only when no real tool is outstanding; no same-thread timer is the sole loop guard.
- [x] Integrate route validation before normal dispatch in run_turn. Process at most one js_exec per model response; reject additional program requests in that response with matching failed exchanges, without executing them. A response mixing js_exec and direct controls is rejected before any execution (all wire calls get matching feedback), preventing accidental stop after partial execution. Ordinary traditional multi-call responses remain serial. JS errors return failed ToolResult and decision continue; fatal persistence errors fail the run without retry. Preserve reasoning_content and exact outer wire tool ID.
- [x] In LegacyLLMProvider, use catalog schemas and append a deterministic JS instructions message describing the envelope, serialization, explicit output, serial backend calls, limits, no automatic retries and direct-only controls. Keep existing native-search transport and name mapping untouched; generated JS uses canonical local tool names. Add adapter tests with fake clients showing only the correct schemas and run-fixed mode after settings change.
- [x] Tests must verify policy changes between queued calls are rechecked; caught denial does not perform effects; latest DAG-guided review/stop remains direct and unchanged; PendingBroker approval pauses then resumes the same guest without duplicate submissions. Verify image paths and Knowledge/DAG notices survive aggregate filtering. Report task output and diff-check.

### Task 6: Recovery, pure event projection and UI

**Files:** modify persistence.py, transcript.py, frontend/src/timeline.ts, timeline.test.ts, types.ts, App.tsx, styles.css, AttentionDock.tsx/attention.ts if metadata requires it; create ProgramCard.tsx and ToolRow.tsx; tests/test_runtime_v2_js_recovery.py and transcript tests.

**Consumes:** event contracts from spec. **Produces:** reproducible program cards/source download; no extra authoritative UI state.

- [x] Write recovery tests with interrupted event histories: requested-only call is not_started; started/no result is unknown; result_recorded/no finished is completed-but-postprocessing-interrupted; unfinished program closes interrupted; repeated restore creates no duplicate terminals. Assert no executor, JS process or scheduler job is invoked during restore. Close child lifecycle before program, then retain existing run-failed and orphan pending cleanup.
- [x] Implement recovery as a pure scan of full restored event history followed by appended terminal EventDrafts. No global mutable invocation state or snapshot schema for JS heaps. Reset EventWriter cursor after backfill, and ensure newly generated recovery events remain durable. Use synchronous store writes only inside existing synchronous restore context.
- [x] Extend transcript rendering with source fenced JS, program output/error, request/result/finish IDs and execution grouping metadata. Correctly fence source containing backticks (choose a longer fence or indent); never lose source/structured results through a display summary.
- [x] Extend frontend ToolItem with callId, executionId, status and effectState. Add ProgramItem with source/sourceHash/status/children/outputs/error; maintain TimelineItem union. Build all entries from events, deduplicating event_id. requested creates queued row; started updates it; raw-result event does not duplicate a row; finished settles it. Group child rows under execution_id. Handle missing submitted event by an explicit source-unavailable program shell; do not lose paginated orphan children. Program counts are completed/actually-requested, not expected program total.

```ts
// Fixture events use the EventEnvelope helper already used by timeline.test.ts.
const items = buildTimeline([
  submitted, requestedA, startedA, requestedB, finishedA, startedB,
  finishedB, programFinished, programFinished,
], []);
const program = items.find(item => item.kind === 'program');
assert.equal(program?.kind, 'program');
if (program?.kind === 'program') {
  assert.equal(program.children.length, 2);
  assert.deepEqual(program.children.map(child => child.callId), ['a', 'b']);
}
assert.equal(items.filter(item => item.kind === 'tool').length, 0);
```

- [x] Add projection tests for denied/no-start child, waiting approval, partial failure, orphan result, interleaved two executions, duplicate SSE, run termination, source missing from history and a completed program with unsuccessful children. Do not depend on React DOM tests to prove event projection.
- [x] Move ToolRowView unchanged into ToolRow.tsx and reuse it in existing rows and ProgramCard. ProgramCard shows state, actual call counts, child rows, escaped read-only code with line numbers, explicit outputs/error, copy button and Blob download. Revoke object URLs. No dangerouslySetInnerHTML, browser eval, new highlighting dependency, inline editing or retry button. Source unavailable disables download rather than generating fake code. Highlight error line only if the engine supplied a valid line number within the original source.
- [x] Add invocation_protocol selector to active-agent settings (existing patchSettings). Show active CurrentRun mode and configured-next-run mode if different; do not auto-cancel/restart. Add protocol to TS types and new-agent defaults propagation via existing defaults spread. Keep project mode selector dedicated to DAG orchestration.
- [x] Pass host call/execution correlation through pending projections. Program card shows which child is awaiting approval; existing AttentionDock still resolves same broker request and focuses same agent. Include nested active tool in current-working indicator and nested image children in artifact URL collection (currently these assume top-level ToolItem; update both traversals explicitly).
- [x] Run frontend timeline/attention tests, typecheck/build, recovery/transcript tests. Inspect a fixture-driven ProgramCard containing queued/running/failed/waiting/source/output states using the available browser tool if local preview is available; otherwise report the missing visual verification honestly. Do not start Cloudra against real data to get a screenshot.

### Task 7: Integration acceptance, packaging and documentation

**Files:** tests/test_runtime_v2_js_acceptance.py; README.md, README_CN.md, AGENTS.md; host package data/lockfile from Task 4.

**Consumes:** all preceding tasks. **Produces:** verified deliverable and report; not a merged/pushed branch.

- [x] Add one parameterized harness test executing the same fake business operation in traditional and JS modes with real InvocationService/default policy stages, verifying identical allowed/blocked behavior and raw-result facts. Add a fake schema-validated compute submission showing method-policy denial reaches both paths without launching compute.
- [x] Add installed-resource test locating host.mjs and package.json via package path, proving launch is independent of cwd; traditional mode works with absent node/dependency, JS mode reports runtime_unavailable. Verify no startup npm invocation. Build a wheel if the existing environment has build tooling, inspect package data; if absent use existing setuptools wheel command rather than adding dependencies.
- [x] Documentation must include exact install command, setting name, run-fixed semantics, serial backend limitation, uniform ToolResponse sample, explicit errors/receipts, no restart recovery of JS heap, no automatic rerun, and security threat model. Explain code download is an event snapshot. Update AGENTS with file responsibilities and Node host test command. Do not say "secure sandbox" without the documented boundary and residual risk.

```js
const result = await tools.log_parser({log_path: '/absolute/path/calculation.out'});
text({call_id: result.call_id, ok: result.is_success, data: result.data});
```

- [x] Run syntax checks for changed Python and host files, focused suites, then full repository tests once. Use these commands with the controller-supplied interpreter prefix:

```bash
python -m compileall -q cloudra/runtime_v2 cloudra/tools
python -m pytest -q tests/test_runtime_v2_invocation_protocol.py tests/test_runtime_v2_event_writer.py tests/test_runtime_v2_invocation.py tests/test_runtime_v2_tool_catalog.py tests/test_runtime_v2_js_protocol.py tests/test_runtime_v2_js_runtime.py tests/test_runtime_v2_js_pipeline.py tests/test_runtime_v2_js_recovery.py tests/test_runtime_v2_js_acceptance.py
python -m pytest -q tests/
python -m ruff check cloudra tests
npm --prefix cloudra/runtime_v2/js_host test
npm --prefix frontend run test:timeline
npm --prefix frontend run test:attention
npm --prefix frontend run build
git diff --check
```

If a command fails because a preexisting optional tool/environment is absent, record exact output and scope; do not weaken or delete tests. If code regressed, repair and rerun the relevant suite before reporting. Tests relying on Node may skip only after explicit detection, but final host acceptance requires real Node runs, not all skipped.

- [x] Self-review against every spec section. Produce a report containing task status, changed files, red/green evidence, actual test counts, remaining risks and commands for the user. Mark any unverified claims explicitly. Do not stage/commit/push. Parent performs independent review; implementation is not accepted merely because the worker says done.

## Controller preflight / coverage checklist

- [x] Spec sections 1 and 8 → Tasks 1/7; sections 2 and 5 → Tasks 1/2/5/6; section 3 → Tasks 3/4/5; section 4 → Tasks 4/5/7; section 6 → Tasks 3/5; section 7 → Tasks 1/2/5/6.
- [x] Shared files: Task 1→2 writer/core; 2→5 InvocationOutcome/ContextVar; 3→5 catalog; 4→5 frames/limits; 1→6 restore cursor/protocol; 2/5→6 event shapes; 4→7 packaging. Compare exact signatures and strings before dispatch.
- [x] No commits authorized; no implementation before worktree choice is resolved; no new scientific decisions.
- [x] Record any approved plan correction in the controller ledger and worker brief, rather than silently changing requirements.
