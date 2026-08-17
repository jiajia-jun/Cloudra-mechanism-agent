# Delivery-only orchestration (delete process DAG) — v2

> This revision incorporates the postmortem of **prj_d6212be8a2934e80** (`ablation-da-dag_guided`,
> 2026-08-16T18:53–20:09Z, data dir `/tmp/cloudra-ablation-da-guided/`). That run
> CONFIRMED the coverage loophole — in a sharper form than originally stated — plus
> several new failure modes. See "Evidence" below. (An earlier audit claimed the loophole
> did not exist; it had looked at the wrong data dir, `~/.local/share/cloudra`. Corrected.)
>
> Implementation state: **Phases 0–6 are implemented and verified** (full suite green,
> frontend `npm run build` green). Phase 7 (same-cell ablation rerun) is pending.

**Goal:** Remove the process DAG. Delivery is the only graph. The loop:

```
user request
  → Coordinator investigates / plans
  → Coordinator dag_propose_mechanism (draft delivery graph + per-element stage contracts)
  → Supervisor reviews draft (dag_guided) / harness auto-accepts (dag_record)
  → harness commits graph → mechanism_accepted → compute/write tools unlock
  → Coordinator (and children) work at their own pace
  → each delivery-relevant tool.finished / compute-job completion
      → CallReview inbox + (coalesced) wake of Supervisor (dag_guided)
  → Supervisor dag_review_call: target element + stage + agree|disagree|skip + reason
       (old assignee/a-N/tool-name/args-digest ride along as sidecar data for the
        Supervisor's judgement — they are NOT an auto-bind authority)
  → harness validates (order, tool success, ref exists and is result-not-submit,
    deriver checks) → stage supported
  → stop / coverage: every required stage is supported OR explicitly skipped with reason
```

Evidence binds are strictly sequential per element (e.g. ts_guess → ts_opt → frequency →
short_irc → endpoints → direction/identity → thermochemistry). No one-shot "success".
The Coordinator decides which stages each element needs when proposing the mechanism.
Final coverage tolerates incomplete computation, but every uncomputed required stage
must be `skipped` with a non-empty reason. `rejected` is NOT a disposal — it is an open
gap that must be re-bound or explicitly skipped (D10).

**Tech stack:** existing `cloudra.dag` + `runtime_v2` + Electron `DagPanel`. No new dependencies.

## Evidence from prj_d6212be8a2934e80 (why each decision exists)

- **(f) The loophole, real form:** Supervisor correctly vetoed an auto-bound `ts_guess`
  (advisory) as `ts_optimization_frequency` evidence → edge written `inconclusive` WITH a
  long reason (`controller.py:1015-1021`). Reason non-empty ⇒ `completion.py:120-140`
  records `branch_disposed` ⇒ satisfied ⇒ `complete=true`. Coordinator's 19:17:06 stop was
  audited, passed, and **permanently recorded disposition='complete'** — while TS opt, IRC,
  endpoints, direction, identity were all still undone (they finished AFTER the 'complete'
  record). A veto became a terminal disposal with no way back even after real evidence
  arrived. ⇒ D10 (rejected never disposes; re-bind allowed D2), D8.
- **(f2) Contract strengthening was a no-op:** Supervisor set `require_thermochemistry=true`
  explicitly "so the report can no longer claim completion off an inconclusive" — but
  `completion.py:140`'s `continue` skips the thermo check for disposition-level edges.
  Report still said complete. ⇒ per-stage coverage must not skip contract checks.
- **(e) Suspend bypass is deeper than the default:** all 19 stops omitted
  `delivery_disposition` → defaulted `"complete"` (`dag_stage.py:164`). And
  `controller.py:246-268 _has_pending_background` reads three LEGACY tables —
  `scheduled_reminders` and `subagent_requests` are always empty under v2 (reminders live
  in `runtime_v2/reminders.py` events; children in core.agents), so a pending 120s reminder
  and running children were invisible to the suspend check. Also: the run's actual end was
  a final message with NO stop call → zero audit. ⇒ D8 (three-part fix).
- **(a) One-shot success:** Supervisor's scheduling spec itself wrote
  `p_ts_guess_da: evidence_role=ts_optimization_frequency`; harness auto-bound on tool
  finish and auto-marked the node succeeded — the subagent was surprised. ⇒ stage model,
  ts_guess advisory stage can never satisfy ts_opt/frequency.
- **(b) Telemetry flood:** 601 `observed_tool_call` nodes vs 15 planned; process graph
  reached revision 1266 vs delivery 30; agents paged `dag_view` 8+ times then gave up and
  read the events table with sqlite3; endpoint "evidence" ended up being two
  `submit_compute_job` SUBMIT calls (rev 29/30). ⇒ delete telemetry-to-graph entirely;
  CallReview is a table, not a graph (D12); submit is never evidence (D11).
- **(h) Submit ≠ result; self-reported success:** `p_ts_opt_freq_da` was marked `succeeded`
  ("submitted async") while job 4 had already FAILED; `p_irc_short_da` likewise while
  job 6 was running (failed 40s later). Zero harness reconciliation. ⇒ D11; process
  self-report disappears with the process graph.
- **(i-1) stale_revision storm:** 39 rejected harness telemetry mutations + 1 crashed agent
  turn (`run.retry`) — revisioned concurrent graph writes by the harness itself.
  ⇒ D12 (append-only inbox, no revisions).
- **(i-2) First-swarm identity bug:** the first swarm's mutations carried actor=session id
  instead of `a-4` → 2 `actor_forbidden` rejections + auto-claim failures. Later agents
  were fine — two different identity paths. ⇒ D13.
- **(g) Wake storm:** ~19 supervisor runs, 4 full LLM runs within one minute each concluding
  "still placeholders" — one wake per delivery mutation is too fine. ⇒ D14 (coalesce) + D5.
- **(d) The substantive gate was never needed and never bypassed** (zero `dag.gate_blocked`
  events; mechanism designed 18:55:53, first compute 18:58:04). Gate design proceeds as
  planned but is not the urgent hole.
- **Out-of-scope bugs found (file separately, do NOT fix in this plan):** `gjf_writer`
  emits an illegal `%fchk=` percent card (G16 Link-0 abort, ~25 min of agent diagnosis);
  `text_writer`/`text_reader` refuse absolute paths (4+ agents tripped); after the 19:04:52
  process restart, reminder-woken runs lost lifecycle events (no `run.started` —
  `runtime_v2/reminders.py` rearm path); duplicate IRC jobs 7/8 from concurrent
  Supervisor-redispatch vs Coordinator-fix.

## Global constraints

- Python >= 3.11; no new libraries; no sync SQLite on the event loop (`asyncio.to_thread` / `a*` APIs). New tables go in BOTH `init()` and `ainit()` in `persistence/database.py`; new columns follow the `_RELATED_EXTRA_COLUMNS` pattern.
- Tool success field is `is_success`; model-facing tool errors stay English.
- Tool names and DAG semantics stay declared in `cloudra/tools/registry.py`, queried only via `cloudra/tools/capabilities.py`. No new tool-name sets anywhere else.
- Ablation independent variable remains `orchestration_mode` only (`standard` / `dag_record` / `dag_guided`).
- Event loop, CommandBus, EventLog/EventHub, ComputeBroker stay as they are.
- Do not git commit.
- Old process-graph journals must remain readable (replay no-ops process ops); new writes never create process nodes/edges/links.
- Schema: `SCHEMA_VERSION` 12 → 13; keep DDL idempotent.

## Locked decisions (do not reopen)

- **D1 — Who accepts in dag_record:** Supervisor never runs in `dag_record`. There, `dag_propose_mechanism` commits immediately (harness auto-accept, recorded as an accepted draft with `actor="harness:auto"`). In `dag_guided`, only Supervisor `dag_accept_mechanism` commits.
- **D2 — Rejected-stage retry:** a `rejected` stage may be re-bound (a later `agree` with a new valid ref flips it to `supported`). The order guard only inspects *previous* required stages (must be `supported` or `skipped`). A rejected previous stage blocks later stages until it is itself re-bound or explicitly skipped-with-reason. (In the observed run the veto was terminal and real evidence could never land — this is the fix.)
- **D3 — Review → ref resolution:** `dag_review_call` carries no ref. The harness resolves the ref from `review.tool_call_id` reusing the deterministic checks of `DagController.bind_evidence_for_call()` (`dag/controller.py:913-978`): evidence registered for that call, call succeeded, target exists — PLUS D11's not-a-submit rule.
- **D4 — mechanism_accepted persistence:** no separate flag. `mechanism_accepted = EXISTS(dag_drafts WHERE state='accepted')` in the session DB. Survives restart/replay naturally.
- **D5 — Review enqueue throttle:** CallReviews are enqueued ONLY for: (i) tools declared `dag_review=True` in `registry.py` (initially the four evidence-deriver tools `gaussian_log_parser`, `reaction_mapping`, `thermo_analysis`, `ts_guess`), queried via `capabilities.py`; (ii) compute-job completion/failure (D11). Plain bash/file reads/`submit_compute_job` calls do NOT create reviews and do NOT wake the Supervisor.
- **D6 — Skip authority:** both Coordinator (structural write, reason required) and Supervisor (review verdict `skip`, reason required) may skip; the journal records the actor. `skipped` is the ONLY non-success disposal (D10).
- **D7 — Derivers become checks:** existing `derive_delivery_changes` derivers no longer auto-promote anything. They supply harness *checks* on stage binds (e.g. TS `frequency` bind requires the parser's n_imag==1 finding; failure ⇒ bind rejected `saddle_check_failed`, stage stays `pending`). `evidence_level` is derived from stages only.
- **D8 — Stop/suspend seam (three-part fix, from evidence (e)):**
  1. `dag_stage.py:164` default `delivery_disposition` `"complete"` → `"partial"`; only an explicit `complete` claims completion.
  2. `_has_pending_background` (`controller.py:246-268`) must read v2-native signals: non-terminal children from the runtime_v2 agent projection (core.agents), pending reminders from `ReminderBroker`'s event projection, pending `compute_jobs`. Stop reading the legacy `scheduled_reminders`/`subagent_requests` tables (always empty under v2).
  3. A run that ends WITHOUT calling `stop` (final message path) records disposition `partial` automatically in dag modes — `complete` is only ever recorded by an audited explicit stop.
- **D9 — Waivers cannot excuse a missing reason:** USER waivers may waive coverage gates but never `missing_stage_reason`.
- **D10 — `rejected` is NOT a disposal (the core fix):** coverage `complete` ⇔ every required stage is `supported`, or `skipped` with non-empty reason. `pending` and `rejected` are BOTH open gaps; `rejected` gaps surface with their reason in the report. The only exits from `rejected` are re-bind (D2) or an explicit `skip`-with-reason decision (D6). This intentionally flips today's behavior where a reasoned `rejected`/`inconclusive` counts as `branch_disposed`; the existing test `test_rejected_branch_needs_a_persisted_disposition_reason` (tests/test_dag_completion.py:91-113) is rewritten accordingly (with-reason rejected ⇒ NOT complete; skipped-with-reason ⇒ complete).
- **D11 — Submit is never evidence:** compute-stage evidence may only come from post-completion artifacts (parser outputs on a finished job). Reviews for compute enqueue on job COMPLETION or FAILURE (ComputeBroker/monitor path), keyed by `compute_job_id`, carrying the job's terminal state — not on the `submit_compute_job` tool call. The harness rejects any stage bind whose resolved ref traces to a `submit_compute_job` call (`bind_target_is_submit`).
- **D12 — CallReview inbox is append-only:** enqueue is a direct INSERT into `dag_call_reviews` (via `asyncio.to_thread`), NOT a revisioned `DagEngine` mutation. No optimistic revisions on the inbox — the observed 39 `stale_revision` rejections and the crashed turn came from revisioned telemetry writes.
- **D13 — Single identity mapping:** CallReview sidecar identity uses the one existing mapping (`legacy_agent_id_for_role`, as in `dag_stage.py:106-112`) for every spawn path including `SubAgentSwarm`; add a regression test that swarm-spawned agents get the same legacy id as launcher-spawned ones (the first-swarm actor=session-id bug).
- **D14 — Wake coalescing:** Supervisor triggers merge — if a supervisor run is active or a wake is already queued, further triggers (`tool_call_review`, `delivery_updated`, …) fold into it instead of launching a new run per event. (Observed: 4 full LLM runs in one minute, each concluding "still placeholders".)

## Deleted vs kept (full inventory)

**Deleted (meaning and implementation):** process graph, `PlannedNode`/`ObservedNode` as writable graph elements, `dag_schedule_work`, `dag_update_process_node`, `assigned_to_me`/frontier-as-todo projection, unique auto-bind via tool_name + `delivery_target_*`, process `assignee` as mutation authority, `AddLink`/`dag_links` writes, `graph_initialization`/`process_node_failed` as Supervisor triggers, `process_has_supervisor_plan`/`workflow_ready` predicates, ALL harness telemetry writes to any graph (observed nodes, auto-claim, auto-bind — evidence (b)/(i-1)).

**Kept as CallReview sidecar (not a graph, not an authority):** caller `role_id` + legacy a-N (D13), parent session, tool name, arguments digest, `is_success`, compute job id + terminal state (D11).

**Kept and strengthened:** delivery occurrences + elementary-step edges; evidence refs; coverage report; stop audit (D8); Coordinator structural writes after accept (add species/step, labels, skip-with-reason); Supervisor-only evidence bind in `dag_guided`.

### dag tool disposition (all 13 existing + 3 new)

| Tool | After |
| --- | --- |
| `dag_schedule_work`, `dag_update_process_node` | **delete** |
| `dag_init_from_template` | **delete** (replaced by propose; replay no-ops old journals) |
| `dag_review_evidence` | **delete** (replaced by `dag_review_call`; `review_evidence`/downgrade ladder in controller goes too — veto semantics now live in stage `rejected` + D2 re-bind) |
| `dag_bind_evidence` | keep; requires `stage_kind`; Coordinator/record-mode only; disabled in `dag_guided` |
| `dag_add_species`, `dag_add_step`, `dag_update_delivery_element`, `dag_remove_edge`, `dag_set_coverage_contract`, `dag_message_supervisor`, `dag_delivery_report`, `dag_view` | keep; delivery-only |
| **new** `dag_propose_mechanism` (Coordinator) | draft + stage contracts |
| **new** `dag_accept_mechanism` (Supervisor, guided only; harness auto in record) | commit draft |
| **new** `dag_review_call` (Supervisor, guided only) | per-call stage bind verdict |

### HTTP route disposition

| Route | After |
| --- | --- |
| `GET /dag/process` | delete (410 one release, then gone) |
| `GET /dag/delivery`, `/dag/report`, `/dag/history` | keep |
| `GET /dag/projection` | keep, re-projected: delivery + pending reviews + coverage; no frontier/assigned_to_me |
| `POST /dag/mutations` | keep, delivery-only ops |
| `POST /dag/replan` | keep |
| **new** `GET /dag/reviews`, `GET /dag/draft` | inbox + current draft |

## File map

| File | After this work |
| --- | --- |
| `cloudra/dag/models.py` | `StageKind`, `StageStatus`, `StageState`, `StageContract`, `CallReview`, `MechanismDraft`; delivery-only writes; keep legacy read-compat aliases. |
| `cloudra/dag/store.py` | Single live graph; `dag_drafts`; `dag_call_reviews` (append-only); stop writing process rows; old rows still load. |
| `cloudra/dag/engine.py` | Remove `_check_agent_process_access`; stage-order guards + D10 semantics; Supervisor-bind vs Coordinator-structure split; replay no-ops process ops with `ignored_legacy_process_op`. |
| `cloudra/dag/completion.py` | Per-stage coverage (D10); contract checks apply per-stage, never skipped for disposed elements (evidence f2); drop process frontier projection. |
| `cloudra/dag/controller.py` | Enqueue CallReview (D5/D11/D12); coalesced Supervisor wake (D14); `accept_mechanism`; stage-bind validation (D3/D11); `_has_pending_background` reads v2-native signals (D8.2); delete process auto-bind, telemetry writes, and `review_evidence`. |
| `cloudra/dag/substantive_gate.py` | Gate = `mechanism_accepted` (D4); delete process-based predicates. |
| `cloudra/core/supervisor.py` | Triggers: `mechanism_proposed`, `tool_call_review`, `coordinator_message`, `delivery_updated`, `pre_delivery`. Drop process scheduling prompts. |
| `cloudra/runtime_v2/policies/dag_stage.py` | Stop gate on new coverage; sibling-running still suspends audit; **D8.1 default disposition `partial`**; **D8.3 non-stop run end records `partial`**; no process controller fields. |
| `cloudra/tools/Plantool/dag_tools/` | Per tool table above. |
| `cloudra/tools/registry.py`, `capabilities.py` | Re-register; add `dag_review` flag (D5); projection only. |
| `cloudra/prompts/supervisor.md`, `coordinator.md`, `small_mol.md`, … | New loop copy. |
| `cloudra/skills/dag-operations/SKILL.md`, `skills/dft-calculation/` SOP (`references/mechanism-elucidation-sop.md`) | Stages decided by Coordinator; no process SOP; Claisen example rewritten as delivery stages. |
| `frontend/src/DagPanel.tsx`, `frontend/src/api.ts` | One graph + review inbox + stage chips. |
| `cloudra/services/api_v2.py` | Per route table above. |
| `docs/DAG_ORCHESTRATION.md`, `AGENTS.md`, `README_CN.md` | Match this plan. |
| Tests | `tests/test_dag_*`, `tests/test_runtime_v2_dag_stage.py`, frontend build. |

## Stage vocabulary (locked)

Coordinator **chooses a subset** per element when proposing the mechanism. The harness never
infers a chain the Coordinator did not declare.

Occurrence stage kinds: `geometry`, `frequency`, `single_point`.
Elementary-step stage kinds: `ts_guess` (advisory; can never satisfy `ts_opt`/`frequency`),
`ts_opt`, `frequency` (TS edge: n_imag==1 harness check when required), `short_irc`,
`endpoint_a`, `endpoint_b`, `direction`, `identity`, `thermochemistry`.

```python
class StageStatus(str, Enum):
    PENDING = "pending"; SUPPORTED = "supported"; SKIPPED = "skipped"; REJECTED = "rejected"

class StageState(BaseModel):
    kind: StageKind
    required: bool = True
    status: StageStatus = StageStatus.PENDING
    reason: str = ""            # required non-empty for skipped/rejected
    ref: GraphRef | None = None

class StageContract(BaseModel):
    stages: list[StageState]    # list order IS the allowed bind order
```

Order rule: binding stage *k* requires every previous **required** stage `supported` or
`skipped` (else `stage_out_of_order`). A `rejected` stage may be re-bound (D2).
Non-required stages never block coverage.

Coverage (D10): `complete` ⇔ every required stage is `supported`, or `skipped` with a
non-empty reason. `pending` and `rejected` are open gaps. Contract-level requirements
(thermochemistry etc.) are evaluated per-stage and apply to every element regardless of
disposition — no `continue`-style skip (evidence f2). Waivers per D9.

Derived `evidence_level` (display/compat only, never model-written):

- occurrence: all required supported → `structure_supported` (`thermo_annotated` if a `single_point` stage exists and is supported)
- edge: `ts_opt`+`frequency` supported → `saddle_supported`; IRC+endpoints+direction+identity supported → `endpoint_supported`; `thermochemistry` supported → `thermo_annotated`
- any required stage `rejected` and none pending → element `rejected` (still an open gap per D10)
- any required `skipped` (reasoned), none `rejected`, not all supported → `inconclusive`
- otherwise → `proposed`

Old-row read mapping (`stages` empty ⇒ map once from stored `evidence_level`):
`structure_supported` ⇒ `[geometry: supported]`; `thermo_annotated` (occurrence) ⇒
`[geometry, single_point: supported]`; `saddle_supported` ⇒ `[ts_opt, frequency: supported]`;
`endpoint_supported` ⇒ `[ts_opt, frequency, short_irc, endpoint_a, endpoint_b, direction, identity: supported]`;
`thermo_annotated` (edge) ⇒ saddle set + `thermochemistry`; `rejected`/`inconclusive` ⇒
single synthetic stage `geometry`/`ts_opt` with that status + stored reason; `proposed` ⇒ `[]`.

## Phase 0 — Stage types, store, coverage rewrite (DONE)

**Files:** `dag/models.py`, `dag/store.py`, `dag/completion.py`, `persistence/database.py`, `tests/test_dag_completion.py`

Tree state: stage types, `stages` persistence (SCHEMA_VERSION 13, both init paths), and the
per-stage coverage rewrite are implemented, including the D10 semantics below.

- [ ] **0.5 (D10 delta)** Coverage: `rejected` (with or without reason) is an open gap, NOT disposed. Rewrite `test_rejected_branch_needs_a_persisted_disposition_reason` accordingly; add: rejected+reason ⇒ not complete; rejected ⇒ re-bind or explicit skip; skipped+reason ⇒ complete; contract checks (e.g. required thermochemistry stage) apply even to elements with disposed/skipped stages (no `continue` skip — evidence f2).
- [ ] **0.6** Re-run: `uv run pytest -q tests/test_dag_completion.py tests/test_dag_engine.py tests/test_dag_store.py tests/test_dag_evidence_bindings.py`

**Done when:** the prj_d6212be8a2934e80 shape (vetoed edge with reason, real stages pending) evaluates INCOMPLETE, and stays incomplete after a waiver that doesn't supply reasons.

## Phase 1 — Sequential stage binds (DONE)

**Files:** `dag/engine.py`, `dag/controller.py`, `tools/Plantool/dag_tools/dag_bind_evidence.py`, `tests/test_dag_engine.py`, `tests/test_dag_evidence_bindings.py`

Tree state: `apply_stage_bind` + order guards + `dag_bind_evidence` stage_kind wrapper done.

- [ ] **1.3** Remove unique auto-bind from planned process nodes (`on_tool_started` claim ~`controller.py:296-373`, `_adapt_delivery` ~745-805) and ALL harness telemetry graph writes (evidence b/i-1). Review enqueue stub only (D12 append-only; real table in Phase 2). Update tests that seeded PlannedNode claims.
- [ ] **1.5 (D11)** Harness rejects stage binds whose resolved ref traces to a `submit_compute_job` call (`bind_target_is_submit`); test it.
- [ ] **1.4** Full suite: `uv run pytest -q tests/` + `uv run ruff check cloudra tests` + compileall.

## Phase 2 — CallReview inbox + Supervisor `dag_review_call`

**Files:** `dag/models.py`, `dag/store.py`, `dag/controller.py`, `core/supervisor.py`, `tools/Plantool/dag_tools/dag_review_call.py` (new), `tools/registry.py`, `tools/capabilities.py`, `runtime_v2/policies/dag_stage.py`, `prompts/supervisor.md`, `tests/test_dag_supervisor.py`, `tests/test_runtime_v2_dag_stage.py`

```python
class CallReview(BaseModel):
    review_id: str
    tool_call_id: str
    tool_name: str
    is_success: bool               # for compute: the JOB's terminal state, not the submit's (D11)
    caller_session_id: str
    caller_role_id: str            # small_mol
    caller_legacy_id: str          # a-4  (sidecar only; single mapping path, D13)
    arguments_digest: str
    result_summary: str
    compute_job_id: str | None
    suggested_target_id: str | None   # optional Coordinator hint, sidecar only
    state: Literal["pending", "reviewed", "ignored"]
    created_at: datetime

class DagReviewCallInput(BaseModel):
    review_id: str
    target_id: str
    stage_kind: StageKind
    verdict: Literal["agree", "disagree", "skip", "ignore"]
    reason: str = ""
```

`ignore` = not delivery evidence; no stage change. Ref resolution per D3 (+D11). Enqueue per D5 (deriver tools + compute completion/failure), append-only per D12, in `asyncio.to_thread`.

Wake map (`dag_guided` only), coalesced per D14: `tool_call_review`, `mechanism_proposed`, `coordinator_message`, `delivery_updated`, `pre_delivery`. Drop `graph_initialization`, `process_node_failed`, `new_evidence` (subsumed). Keep `edge_removal_requested` only if `dag_remove_edge` keeps the Supervisor-review flow.

D8 in this phase: default disposition `partial` (dag_stage.py:164); `_has_pending_background` reads v2-native signals (core.agents projection, ReminderBroker projection, compute_jobs); non-stop run end records `partial` in dag modes.

- [ ] **2.1** Tests: successful `ts_guess` enqueues; Supervisor `agree` on `ts_guess`; subsequent `agree` on `ts_opt` without opt ⇒ `stage_out_of_order`; `ignore` leaves stages untouched; bash enqueues nothing; compute-job completion enqueues with terminal state; submit call itself enqueues nothing; **disagree-with-reason leaves coverage INCOMPLETE (the prj_d6212be8a2934e80 regression test)**.
- [ ] **2.2** `dag_call_reviews` table (both init paths); append-only enqueue; coalesced wake (D14).
- [ ] **2.3** `dag_review_call` tool; Supervisor-only in guided; disabled in record; `dag_bind_evidence` disabled in guided.
- [ ] **2.4** D8 three-part stop/suspend fix + regression tests (default partial; reminder-pending ⇒ suspend; non-stop end ⇒ partial).
- [ ] **2.5** D13 identity regression test (swarm vs launcher spawn).
- [ ] **2.6** Rewrite `prompts/supervisor.md`: no scheduling; review draft + calls; bind stages; ts_guess ≠ frequency; disagree means the stage is still owed.
- [ ] **2.7** `uv run pytest -q tests/test_dag_supervisor.py tests/test_runtime_v2_dag_stage.py tests/test_dag_tools.py`

**Done when:** the observed failure mode is impossible by construction — a Supervisor veto can no longer produce `complete`; a stop can no longer record `complete` while reminders/children/compute are pending.

## Phase 3 — Draft mechanism, accept, unlock

**Files:** `dag/controller.py`, `dag/store.py`, `dag/substantive_gate.py`, `tools/Plantool/dag_tools/dag_propose_mechanism.py` + `dag_accept_mechanism.py` (new), `runtime_v2/policies/dag_stage.py`, `tests/test_dag_tools.py`, `tests/test_runtime_v2_dag_stage.py`

```python
class MechanismDraft(BaseModel):
    operations: list[GraphOperation]          # delivery-only AddNode/AddEdge/Update*
    stage_contracts: dict[str, StageContract] # element id → stages; ids must resolve within the draft
    rationale: str
    state: Literal["open", "accepted", "rejected"]
```

Coordinator `dag_propose_mechanism` writes a draft (harness validates referential integrity of `stage_contracts` against draft ops). Guided: Supervisor `dag_accept_mechanism` applies ops + contracts; reject returns draft with reason. Record: harness auto-accepts on proposal (D1). `mechanism_accepted` per D4.

Gate (`check_substantive_gate`, dag modes): before accept, block `submit_compute_job`, `gjf_writer` (write), `ts_guess` scan_prepare, other compute entry points; allow search/read/mapping/`dag_view`/`dag_propose_mechanism`/`dag_message_supervisor`. Delete `process_has_supervisor_plan`/`workflow_ready`; replace both gate levels with `mechanism_accepted`. (Evidence (d): the old gate never fired and was never bypassed — the new gate exists to enforce "design before compute", not to fix an observed hole.)

After accept, Coordinator may still `dag_add_species`/`dag_add_step`/update contracts; each such mutation wakes Supervisor (`delivery_updated`, coalesced D14) for audit.

- [ ] **3.1** Tests: `submit_compute_job` before accept ⇒ blocked; after accept ⇒ allowed; accept persists `[ts_guess, ts_opt, frequency]` pending; record-mode proposal auto-accepts.
- [ ] **3.2** `dag_drafts` table + tools + gate rewrite.
- [ ] **3.3** Coordinator prompt: first delivery artifact is a proposal; no compute before accept; you choose stages.
- [ ] **3.4** `uv run pytest -q tests/test_dag_tools.py tests/test_runtime_v2_dag_stage.py tests/test_dag_substantive_gate.py`

**Done when:** no compute on an unaccepted mechanism in dag modes.

## Phase 4 — Delete the process graph

**Files:** `dag/models.py`, `dag/engine.py`, `dag/store.py`, `dag/completion.py`, `dag/controller.py`, delete `dag_schedule_work.py` / `dag_update_process_node.py` / `dag_init_from_template.py` / `dag_review_evidence.py`, `_common.py` (`template_operations` gone), `tools/registry.py`, `services/api_v2.py`, all tests seeding `PlannedNode`/`assigned_to_me`.

- `parse_graph_operation` still parses old process ops; replay no-ops them and journals `ignored_legacy_process_op` (revisions still advance). MUST replay prj_d6212be8a2934e80's own journal (1266 process revisions / 1325 mutations) as the acid test.
- `AddLink` op rejected on write; `dag_links` table read-only for old DBs.
- Engine: delete `_check_agent_process_access`, `_check_assignee`, `review_evidence` + downgrade ladder + `evidence_vetoed` chain.
- Registry: unregister the four deleted tools.

- [ ] **4.1** Grep-gate test scoped to `cloudra/` **code** (`*.py`, excluding tests): `dag_schedule_work` / `dag_update_process_node` / `dag_init_from_template` / `dag_review_evidence` must not appear.
- [ ] **4.2** Delete tools + process mutation paths; fix every test seeding `PlannedNode`.
- [ ] **4.3** Replay fixture: a v12 journal with process ops (ideally exported from prj_d6212be8a2934e80) loads delivery-only.
- [ ] **4.4** `uv run pytest -q tests/test_dag_*.py tests/test_runtime_v2_dag_stage.py tests/test_prompt_budget.py tests/test_no_sync_on_loop.py`

**Done when:** no runtime path creates process nodes/links; old DBs still open.

## Phase 5 — Frontend + HTTP

**Files:** `frontend/src/DagPanel.tsx`, `frontend/src/api.ts`, `frontend/src/App.tsx`, `services/api_v2.py`

- Remove process SVG, process add-forms, "link to delivery" form, process revision badge.
- Delivery graph with per-element stage chips (`pending`/`supported`/`skipped`/`rejected`).
- Pending CallReviews panel (read-only list + history; verdicts are Supervisor-only in product).
- Draft banner while `mechanism_accepted=false`.
- Routes per route table; `/dag/process` → 410.

- [ ] **5.1** TS client matches new JSON (no `process` required).
- [ ] **5.2** `npm run build` in `frontend/` passes.
- [ ] **5.3** Manual: open a dag_guided project; exactly one graph.

## Phase 6 — Prompts, SOP, docs

**Files:** `prompts/supervisor.md`, `coordinator.md`, `small_mol.md` (+ any follower mentioning process/frontier/graph-`assignee`; note: literal `assigned_to_me` appears in no prompt — search `assignee`, `frontier`, `dag_schedule_work`, `process graph` instead), `skills/dag-operations/SKILL.md`, `skills/dft-calculation/SKILL.md` + `references/mechanism-elucidation-sop.md`, `docs/DAG_ORCHESTRATION.md`, `AGENTS.md`, `README_CN.md`.

Copy rules: Coordinator designs delivery + stage contracts, no frontier waiting; children run tools, never update graphs (optional `suggested_target_id` hint); Supervisor = draft accept + per-call review, no scheduling; modes: `standard` zero graph, `dag_record` stages+self-bind without Supervisor, `dag_guided` Supervisor on every delivery-relevant call; Claisen SOP rewritten as delivery stages; prompts must say a `disagree`/`rejected` stage is still owed work — never a disposal.

- [ ] **6.1** Prompt/SOP edits.
- [ ] **6.2** `tests/test_prompt_budget.py` lists only existing dag tools.
- [ ] **6.3** Docs match the new module map.

## Phase 7 — Verification (same ablation cell)

Frozen query (verbatim, unchanged):

> 跑通一个最简单的DA反应的机理,用计算量最小的方法，不需要准确性，在harness层遇到问题马上停止工作（也和你的子agent说）并输出反馈，这是一次测验，不要去调用历史toolcall作弊，也不要跑到沙箱之外

Empty workspace; `dag_guided`; YOLO true; inherit model (deepseek-v4-flash); same isolated data dir pattern as `ablation-da-dag_guided`. Watch specifically (all observed broken in prj_d6212be8a2934e80):

1. draft accepted before any compute;
2. `ts_guess` review cannot support `frequency`/`ts_opt`;
3. a Supervisor `disagree` leaves coverage incomplete and CAN be recovered by re-bind;
4. stop with pending reminder/children/compute suspends (disposition `partial`); only an explicit audited stop with all stages supported/skipped-with-reason records `complete`;
5. no observed-node flood: `dag_nodes` stays at delivery elements only; inbox rows instead;
6. no stale_revision rejections from harness writes (inbox is append-only);
7. submit calls never appear as evidence refs.

**Pass:** three occurrences + one step; required stages supported with real refs (opt logs, TS freq, IRC, endpoints, direction/identity, thermo) or skipped with reasons; `complete` recorded only at the final audited stop.

## Implementation order

0.5 (D10 delta) → 1.3/1.5 → 2 → 3 → 4 strictly sequential; 5 + 6 may overlap after 4; then 7.
Each phase leaves the tree green (`uv run pytest -q tests/`, `ruff check cloudra tests`, `compileall`).

## Out of scope

- LLM providers, YOLO semantics, ComputeBroker, chemistry tool physics.
- Re-introducing a todo graph under another name.
- Supervisor auto-dispatching children.
- Supervisor running "a little bit" in `dag_record`.
- Bugs found in the postmortem that are independent of the DAG architecture (file separately): `gjf_writer` illegal `%fchk=` card; `text_writer`/`text_reader` absolute-path refusals; lost run-lifecycle events after process restart (`runtime_v2/reminders.py` rearm path); duplicate compute dispatch coordination.

## Self-review

- Real loophole (veto ⇒ disposed ⇒ complete): D10 + Phase 0.5 + Phase 2.1 regression test.
- Suspend/stop seams (default complete, legacy-table pending check, unaudited non-stop end): D8 + Phase 2.4.
- One-shot success / ts_guess as opt+freq: stage model + Phase 1; advisory stage can never satisfy.
- Submit-as-evidence / self-reported success: D11 + Phase 1.5/2.1.
- Telemetry flood + stale_revision storm: delete graph telemetry (Phase 1.3/4) + D12 append-only inbox.
- Identity bug: D13 + Phase 2.5. Wake storm: D5/D14.
- Draft → accept → unlock, both modes: Phase 3, D1/D4.
- Delete process incl. links; old journals replay (acid test: this very project's journal): Phase 4.
- UI: Phase 5. Prompts/docs: Phase 6. Same-task verify against the 7 observed failure modes: Phase 7.
- No TBD remaining.
