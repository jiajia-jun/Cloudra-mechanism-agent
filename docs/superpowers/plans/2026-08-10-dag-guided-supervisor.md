# DAG-Guided Supervisor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the default periodic advice Supervisor with an opt-in, persistent two-DAG orchestration system for small-molecule mechanism studies, including an ablation-ready session mode and a Claisen worked SOP example.

**Architecture:** A new `cloudra.dag` package owns typed graph models, transactional SQLite persistence, mutation validation, delivery coverage, projections, and the runtime controller. Sessions select `standard`, `dag_record`, or `dag_guided`; only DAG modes load the conversation-scoped graph pair, and only `dag_guided` runs the event-driven Supervisor. Chemistry tools stay stateless: the harness snapshots full structured tool results as durable evidence and stores only typed references in graph nodes and edges.

**Tech Stack:** Python 3.12, Pydantic v2, SQLite/aiosqlite, existing `ConversationDB`, existing OpenAI-compatible `LLMClient`, pytest/pytest-asyncio.

## Global Constraints

- Canonical state is exactly two DAGs: `process` and `delivery`; delivery is the mechanism graph.
- Delivery nodes are pathway occurrences pointing to canonical species/evidence records; delivery edges point to TS and IRC evidence.
- Catalytic cycles use repeated occurrence nodes with one `species_ref`; reversibility is edge metadata, not a reverse edge.
- Mode is fixed per session and defaults to `standard`; the graph pair persists per conversation.
- `standard` does not read/write graph storage or call Supervisor. `dag_record` records without Supervisor influence. `dag_guided` permits validated Supervisor mutations.
- `session_events` remains best-effort telemetry and is never canonical graph state or delivery evidence.
- Chemistry tools remain stateless.
- Preserve unrelated dirty changes, especially `cloudra/tui/new/screens/main_screen.py`, `cloudra/tui/new/widgets/side_panel.py`, and `tests/test_textual_tui.py`.
- Do not run the full repository suite. Run only the focused commands below.

## File map

- `cloudra/dag/models.py`: shared enums and Pydantic wire/storage models.
- `cloudra/dag/store.py`: graph/evidence persistence.
- `cloudra/dag/engine.py`: atomic mutations, permissions, revisions, and cycle checks.
- `cloudra/dag/completion.py`: delivery coverage and projections.
- `cloudra/dag/controller.py`: mode behavior, evidence adapters, prompt projection, stop audit, and Supervisor triggers.
- `cloudra/tools/Plantool/dag_graph.py`: mode-gated agent graph interface.
- `cloudra/supervisor.py`: event-driven graph mutation proposer.

---

### Task 1: Session-level orchestration mode

**Files:**
- Create: `cloudra/dag/__init__.py`
- Create: `cloudra/dag/models.py`
- Modify: `cloudra/database.py`
- Modify: `cloudra/session_store.py`
- Modify: `cloudra/service.py`
- Modify: `cloudra/runtime/runner.py`
- Modify: `cloudra/api.py`
- Modify: `cloudra/backends.py`
- Modify: `cloudra/cli.py`
- Modify: `cloudra/agent.py`
- Modify: `cloudra/react.py`
- Test: `tests/test_dag_mode.py`
- Test: `tests/test_frontend_parity.py`

**Interfaces:**
- Produces: `OrchestrationMode`, `normalize_orchestration_mode(value)`, `Agent.orchestration_mode`, `SessionRecord.orchestration_mode`, and `SessionRecord.orchestration_config`.
- Consumes: current session service/runner/API/backend entry points.

- [ ] **Step 1: Write failing enum, default, migration, and API propagation tests**

```python
def test_orchestration_mode_is_explicit_enum():
    assert normalize_orchestration_mode(None) is OrchestrationMode.STANDARD
    assert normalize_orchestration_mode("dag_record") is OrchestrationMode.DAG_RECORD
    assert normalize_orchestration_mode("dag_guided") is OrchestrationMode.DAG_GUIDED
    with pytest.raises(ValueError):
        normalize_orchestration_mode("on")


async def test_api_persists_dag_guided_mode(client, fake_service):
    response = await client.post(
        "/api/conversations/conv_1/sessions",
        json={"query": "study Claisen", "orchestration_mode": "dag_guided"},
    )
    assert response.status_code == 202
    assert fake_service.submitted[-1]["orchestration_mode"] == "dag_guided"


def test_running_session_mode_is_immutable(session_store, db):
    session_store.insert_queued_session(
        db, session_id="s1", agent_id="a-0", agent_type="coordinator",
        query="study", orchestration_mode="dag_record",
        orchestration_config={"graph_policy_revision": "sha256:policy"},
    )
    with pytest.raises(ValueError):
        session_store.set_orchestration_mode(db, "s1", "standard")
```

- [ ] **Step 2: Run RED**

Run: `uv run pytest -s tests/test_dag_mode.py tests/test_frontend_parity.py -k 'orchestration or dag_guided'`

Expected: missing enum/fields/signatures.

- [ ] **Step 3: Add the mode type and session columns**

```python
class OrchestrationMode(str, Enum):
    STANDARD = "standard"
    DAG_RECORD = "dag_record"
    DAG_GUIDED = "dag_guided"


def normalize_orchestration_mode(value: str | OrchestrationMode | None) -> OrchestrationMode:
    if value is None:
        return OrchestrationMode.STANDARD
    return value if isinstance(value, OrchestrationMode) else OrchestrationMode(value)
```

Increment `SCHEMA_VERSION`; add `orchestration_mode TEXT NOT NULL DEFAULT
'standard'` and `orchestration_config TEXT NOT NULL DEFAULT '{}'` to the session
schema and migration map. Extend queued/running session writes so claiming a row
does not replace either value.

- [ ] **Step 4: Thread the value through API, service, runner, Agent, and backends**

Add `orchestration_mode: OrchestrationMode = OrchestrationMode.STANDARD` to
`SessionCreate`, `SessionRecord`, `SessionRunner.submit[_async]`, `_execute`,
`CloudraService.submit_session[_async]`, `CloudraService.run_task`, and
`run_task_async`. Construct the Coordinator with the same value. Add CLI
`--orchestration-mode` with the three exact choices. Existing TUI calls omit it
and therefore remain standard. Serialize `orchestration_config` at submission
with the Supervisor model (guided only), Supervisor prompt SHA-256, graph-policy
revision, and relevant runtime configuration; return the same snapshot in the
session record. Reject mode/config changes after the queued row is claimed.

- [ ] **Step 5: Remove default periodic Supervisor activation**

```python
self.orchestration_mode = normalize_orchestration_mode(agent.orchestration_mode)
self.supervisor = (
    get_supervisor()
    if self.orchestration_mode is OrchestrationMode.DAG_GUIDED
    else None
)
```

Remove the every-15-ReAct-step call. Event triggers arrive in Task 7.

- [ ] **Step 6: Run GREEN**

Run: `uv run pytest -s tests/test_dag_mode.py tests/test_frontend_parity.py tests/test_backends.py -k 'orchestration or session_create or submit_session'`

---

### Task 2: Durable graph and evidence store

**Files:**
- Modify: `cloudra/database.py`
- Expand: `cloudra/dag/models.py`
- Create: `cloudra/dag/store.py`
- Test: `tests/test_dag_store.py`

**Interfaces:**
- Produces: `GraphKind`, `GraphRef`, `SpeciesRecord`, `DagNode`, `DagEdge`, `GraphBundle`, `GraphSnapshot`, `DagStore.ensure_bundle`, `DagStore.load_snapshot`, `DagStore.upsert_species`, `DagStore.register_evidence`, and `DagStore.rebuild_materialized`.
- Consumes: `ConversationDB` and `OrchestrationMode`.

- [ ] **Step 1: Write failing restart and pointer tests**

```python
def test_graph_pair_survives_store_restart(tmp_path):
    db = ConversationDB("mechanism", data_dir=tmp_path).init()
    first = DagStore(db).ensure_bundle(session_id="s1")
    second = DagStore(ConversationDB.from_path(db.path)).load_bundle()
    assert first.process_graph_id == second.process_graph_id
    assert first.delivery_graph_id == second.delivery_graph_id


def test_tool_evidence_is_content_addressed(store):
    a = store.register_evidence("s1", "reaction_mapping", {"mapping_status": "unique"})
    b = store.register_evidence("s1", "reaction_mapping", {"mapping_status": "unique"})
    assert a.ref_type == "tool_result"
    assert a.ref_id == b.ref_id
    assert a.content_hash == b.content_hash


def test_delivery_occurrence_points_to_species_record(store, engine):
    species = store.upsert_species(
        canonical_key="smiles:C=COCC=C|charge:0|multiplicity:1",
        identifiers={"smiles": "C=COCC=C"}, charge=0, multiplicity=1,
    )
    result = engine.apply_batch(add_occurrence(species_ref=species.species_id))
    assert result.accepted
```

Assert graph refs do not embed the registered payload and that `session_event`
is rejected as an evidence ref type.

- [ ] **Step 2: Run RED**

Run: `uv run pytest -s tests/test_dag_store.py`

- [ ] **Step 3: Add graph/evidence/mutation tables**

Create `dag_graphs`, `dag_species`, `dag_nodes`, `dag_edges`, `dag_links`, `dag_evidence`,
`dag_mutations`, and `dag_coverage`. Use composite primary keys for graph rows,
unique `graph_kind` so each conversation has exactly one process/delivery pair,
JSON text for small refs/payloads, and a unique evidence key over source type,
source name, and content hash. `dag_species` stores a stable identity key,
charge, multiplicity, identifiers, and small metadata; repeated occurrence nodes
refer to its `species_id`.

- [ ] **Step 4: Implement durable typed reads and content-addressed evidence**

Canonicalize JSON with sorted keys and compact separators, reject non-finite
values, hash SHA-256, and return:

```python
GraphRef(
    ref_type="tool_result",
    ref_id=f"ev_{digest}",
    content_hash=f"sha256:{digest}",
)
```

The full result is stored only in `dag_evidence.payload`.

- [ ] **Step 5: Implement journal replay and corruption recovery**

`rebuild_materialized()` creates a temporary set of graph/species/link rows,
replays accepted operations in mutation order, validates final revisions and
acyclicity, and replaces materialized rows in one transaction. Add a test that
deletes/corrupts a materialized node, rebuilds from the journal, and obtains the
same snapshot digest. If replay cannot validate, raise `DagCorruptionError`
without inventing an empty graph.

- [ ] **Step 6: Run GREEN**

Run: `uv run pytest -s tests/test_dag_store.py`

---

### Task 3: Atomic mutation engine and permissions

**Files:**
- Create: `cloudra/dag/engine.py`
- Expand: `cloudra/dag/models.py`
- Expand: `cloudra/dag/store.py`
- Test: `tests/test_dag_engine.py`

**Interfaces:**
- Produces: `GraphActor`, `GraphOperation`, `MutationBatch`, `MutationResult`, `DagEngine.apply_batch`, `DagEngine.snapshot`, and `DagEngine.history`.

- [ ] **Step 1: Write failing atomicity, cycle, revision, and actor-policy tests**

```python
def test_cycle_rejects_entire_batch(engine):
    result = engine.apply_batch(batch([
        add_node("process", "a"), add_node("process", "b"),
        add_edge("process", "ab", "a", "b"),
        add_edge("process", "ba", "b", "a"),
    ]))
    assert not result.accepted
    assert engine.snapshot().process.nodes == []


def test_supervisor_cannot_waive_gate(engine):
    result = engine.apply_batch(batch([waive_gate("endpoint")], actor="supervisor"))
    assert not result.accepted
    assert result.rejection_code == "actor_forbidden"
```

Add tests for stale base revisions, dangling refs, duplicate IDs, immutable
evidence refs, and an acyclic catalytic cycle expansion where `Cat@entry` and
`Cat@return` share one `species_ref`. Validate `species`, `artifact`,
`compute_job`, and `tool_result` references against canonical tables in the same
conversation.

- [ ] **Step 2: Run RED**

Run: `uv run pytest -s tests/test_dag_engine.py`

- [ ] **Step 3: Implement explicit mutation types**

```python
OperationName = Literal[
    "add_node", "add_edge", "update_node", "update_edge",
    "attach_ref", "add_link", "set_coverage_contract", "waive_gate",
]
```

There is no delete operation. Supervisor may change status, priority, label,
annotations, and additive evidence/requirements; it cannot waive gates, lower
requirements, or set overall completion.

- [ ] **Step 4: Validate and write one batch in `BEGIN IMMEDIATE`**

Load both revisions/graphs, compare base revisions, simulate all operations,
validate references and acyclicity with Kahn traversal, then write materialized
rows, increment touched graph revisions once, and append one journal row. Roll
back every materialized change on failure; persist the rejection separately.

- [ ] **Step 5: Run GREEN**

Run: `uv run pytest -s tests/test_dag_engine.py`

---

### Task 4: Delivery coverage and bounded projection

**Files:**
- Create: `cloudra/dag/completion.py`
- Expand: `cloudra/dag/models.py`
- Expand: `cloudra/dag/engine.py`
- Test: `tests/test_dag_completion.py`

**Interfaces:**
- Produces: `CoverageContract`, `CoverageGateResult`, `DeliveryReport`, `DagProjection`, `evaluate_delivery`, and `build_projection`.

- [ ] **Step 1: Write failing coverage and frontier tests**

```python
def test_endpoint_supported_path_satisfies_default_contract(snapshot_factory):
    snapshot = snapshot_factory(
        node_levels=["structure_supported", "structure_supported"],
        edge_levels=["endpoint_supported"],
    )
    report = evaluate_delivery(snapshot.delivery, CoverageContract.mechanism_default())
    assert report.complete


def test_saddle_without_endpoints_is_not_complete(snapshot_factory):
    snapshot = snapshot_factory(edge_levels=["saddle_supported"])
    report = evaluate_delivery(snapshot.delivery, CoverageContract.mechanism_default())
    assert not report.complete
    assert "missing_endpoint_evidence" in {gap.code for gap in report.unresolved}
```

Also test rejected-branch disposition, explicit user waivers, and deterministic
projection bounds.

- [ ] **Step 2: Run RED**

Run: `uv run pytest -s tests/test_dag_completion.py`

- [ ] **Step 3: Implement deterministic coverage**

Default active intermediates require `structure_supported`; active elementary
steps require `endpoint_supported`; rejected/inconclusive branches require a
reason. Thermochemistry is required only when
`require_thermochemistry=True`. Waivers retain the original gate plus user,
session, and rationale.

- [ ] **Step 4: Implement frontier/projection limits**

Ready process nodes have all live dependencies succeeded/skipped and sort by
`priority DESC, created_at, node_id`. Include at most 12 frontier nodes, 12
blockers/gaps, and 8 recent mutations. `to_prompt_text()` includes mode, both
revisions, frontier, blockers, and delivery gaps, never full evidence payloads.

- [ ] **Step 5: Run GREEN**

Run: `uv run pytest -s tests/test_dag_completion.py`

---

### Task 5: Agent-facing DAG tool

**Files:**
- Create: `cloudra/tools/Plantool/dag_graph.py`
- Modify: `cloudra/tools/registry.py`
- Modify: `cloudra/agent.py`
- Test: `tests/test_dag_tool.py`
- Test: `tests/test_tools_core.py`

**Interfaces:**
- Produces tool `dag_graph` actions `view`, `mutate`, and `delivery_report`.
- Consumes: `DagEngine`, shared mutation models, current Agent mode and Session.

- [ ] **Step 1: Write failing visibility and mutation tests**

```python
def test_dag_tool_hidden_in_standard(agent_factory):
    agent = agent_factory(orchestration_mode="standard")
    assert "dag_graph" not in {entry.tool_name for entry in agent.get_available_tools()}


@pytest.mark.asyncio
async def test_dag_record_agent_can_mutate(dag_agent, session):
    result = await DagGraph(subagent=dag_agent).tool_call(
        DagGraphInput(action="mutate", base_revisions={"process": 0, "delivery": 0},
                      rationale="Claisen path", operations=claisen_occurrence_ops()),
        session,
    )
    assert result.accepted
```

- [ ] **Step 2: Run RED**

Run: `uv run pytest -s tests/test_dag_tool.py tests/test_tools_core.py -k dag`

- [ ] **Step 3: Implement the typed tool and direct standard-mode guard**

`view` returns the bounded projection or a targeted bounded subgraph. `mutate`
applies one actor=`agent` batch. `delivery_report` is read-only. Direct
instantiation in standard mode returns an explicit failure and does not
initialize graph storage.

- [ ] **Step 4: Register and mode-filter**

Add `DagGraph` to the explicit registry. Filter it from
`Agent.get_available_tools` before schema caching when mode is standard. Existing
permissions restrict it to the Coordinator.

- [ ] **Step 5: Run GREEN**

Run: `uv run pytest -s tests/test_dag_tool.py tests/test_tools_core.py -k 'dag or registry'`

---

### Task 6: Harness controller, durable tool evidence, and prompt projection

**Files:**
- Create: `cloudra/dag/controller.py`
- Modify: `cloudra/react.py`
- Modify: `cloudra/agent.py`
- Test: `tests/test_dag_controller.py`
- Test: `tests/test_prompt_assembler.py`

**Interfaces:**
- Produces: `DagController.initialize`, `on_tool_started`, `on_tool_finished`, `prompt_projection`, and `audit_stop`.
- Consumes: `DagEngine`, full tool argument/result dictionaries, session ID, and mode.

- [ ] **Step 1: Write failing standard/record evidence tests**

```python
@pytest.mark.asyncio
async def test_standard_controller_does_not_initialize_graph(db):
    controller = DagController(db, "s1", OrchestrationMode.STANDARD)
    await controller.on_tool_finished("tc1", "reaction_mapping", {}, {"mapping_status": "unique"})
    assert graph_row_count(db) == 0


@pytest.mark.asyncio
async def test_record_mode_persists_full_result(controller):
    ref = await controller.on_tool_finished(
        "tc1", "reaction_mapping", {"reactant_smiles": "C=COCC=C"},
        {"mapping_status": "unique", "heavy_atom_map": [1, 2, 3, 4, 5, 6]},
    )
    node = controller.engine.find_process_node_by_call("tc1")
    assert ref in node.refs
    assert controller.store.resolve_evidence(ref)["heavy_atom_map"][-1] == 6


@pytest.mark.asyncio
async def test_output_file_becomes_artifact_pointer(controller, tmp_path):
    xyz = tmp_path / "ts.xyz"
    xyz.write_text("1\nTS\nH 0 0 0\n", encoding="utf-8")
    ref = await controller.on_tool_finished(
        "tc2", "ts_guess", {}, {"is_success": True, "output_path": str(xyz)},
    )
    assert controller.store.refs_for_evidence(ref, ref_type="artifact")
```

Add prompt tests proving standard has no DAG marker and DAG prompts contain a
bounded projection but not full tool payloads.

- [ ] **Step 2: Run RED**

Run: `uv run pytest -s tests/test_dag_controller.py tests/test_prompt_assembler.py -k dag`

- [ ] **Step 3: Implement controller initialization and adapters**

Standard methods are strict no-ops. DAG initialization loads/creates both graphs
and the default coverage contract. `on_tool_started` matches a unique ready node
whose `payload.tool_name` equals the call, otherwise creates an observed process
node. `on_tool_finished` registers the complete JSON result, attaches its ref,
and derives succeeded/failed from structured success fields.

Add adapters for `reaction_mapping`, `conformer_search`, `ts_guess`,
`gaussian_log_parser`, and `thermo_analysis`. `ts_guess` and scan evidence remain
advisory. Endpoint support requires linked TS, IRC endpoint, optimized endpoint,
and endpoint-match evidence. For known output-path fields, register regular files
inside the session working directory through `ArtifactService`; the graph points
to the artifact ID and hash. Raw paths may remain annotations but never satisfy
a delivery gate.

- [ ] **Step 4: Hook full results before telemetry truncation**

In `reAct.act_result`, retain `tool_call_id -> arguments`, call
`on_tool_started` before execution, and call `on_tool_finished` with
`result_dict` before JSON context conversion or 800-character telemetry
truncation. DAG controller failures fail closed; standard remains independent.
Add a test that an unavailable/corrupt graph store fails a DAG session clearly
instead of silently switching it to standard.

- [ ] **Step 5: Inject a fresh projection per model request**

```python
projection = await self._dag_projection_provider()
if projection:
    messages = [*messages, {"role": "system", "content": projection}]
```

Attach the provider when ReAct initializes the controller. It returns empty text
in standard mode.

- [ ] **Step 6: Run GREEN**

Run: `uv run pytest -s tests/test_dag_controller.py tests/test_prompt_assembler.py -k 'dag or supervisor_advice_revision'`

---

### Task 7: Event-driven graph Supervisor

**Files:**
- Modify: `cloudra/supervisor.py`
- Modify: `cloudra/prompts/supervisor.md`
- Modify: `cloudra/dag/controller.py`
- Modify: `cloudra/react.py`
- Test: `tests/test_dag_supervisor.py`
- Modify: `tests/test_memory_and_supervisor.py`

**Interfaces:**
- Produces: `SupervisorMutationProposal`, `Supervisor.propose(projection, trigger)`, and `DagController.maybe_supervise(trigger)`.

- [ ] **Step 1: Write failing mode and permission tests**

```python
@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["standard", "dag_record"])
async def test_non_guided_never_calls_supervisor(mode, controller_factory, supervisor):
    controller = controller_factory(mode=mode, supervisor=supervisor)
    await controller.maybe_supervise("new_evidence")
    supervisor.propose.assert_not_awaited()


@pytest.mark.asyncio
async def test_supervisor_cannot_waive_delivery_gate(controller, supervisor):
    supervisor.propose.return_value = proposal([waive_gate("endpoint")])
    result = await controller.maybe_supervise("pre_delivery")
    assert not result.accepted
    assert result.rejection_code == "actor_forbidden"
```

Also cover allowed priority/reopen/alternative-path proposals, stale-revision
re-read, one repair attempt, absence of every-N-step calls, and rejection of any
proposal that removes or weakens a user-defined top-level coverage requirement.

- [ ] **Step 2: Run RED**

Run: `uv run pytest -s tests/test_dag_supervisor.py tests/test_memory_and_supervisor.py -k 'supervisor or guided'`

- [ ] **Step 3: Replace review JSON with typed mutation proposals**

Build the prompt from trigger, revisions, frontier, blockers, delivery gaps, and
the exact allowed-operation schema. Parse into `SupervisorMutationProposal` with
Pydantic; reject unknown fields. Keep case extraction isolated, remove case-bank
retrieval from the graph proposal path, and stop injecting free-text advice.

- [ ] **Step 4: Trigger only on graph events**

Trigger after initialization, accepted evidence, failed/retried process work,
empty frontier with incomplete delivery, explicit replan request, and
pre-delivery audit. Delete `should_review(step)` use from ReAct.

- [ ] **Step 5: Add bounded repair**

Return rejection code plus current revisions for one repair call. A second
rejection keeps the existing valid frontier. Both accepted and rejected batches
remain in the mutation journal.

- [ ] **Step 6: Run GREEN**

Run: `uv run pytest -s tests/test_dag_supervisor.py tests/test_memory_and_supervisor.py -k 'supervisor or guided'`

---

### Task 8: Delivery audit, stop semantics, and graph read API

**Files:**
- Modify: `cloudra/tools/Stoptool/stop_tool.py`
- Modify: `cloudra/react.py`
- Modify: `cloudra/service.py`
- Modify: `cloudra/api.py`
- Modify: `cloudra/backends.py`
- Test: `tests/test_dag_delivery.py`
- Modify: `tests/test_frontend_parity.py`

**Interfaces:**
- Adds `delivery_disposition: Literal["complete", "partial", "user_terminated"] = "complete"` to StopTool input.
- Adds read APIs for projection, graph snapshot, mutation history, and delivery report.

- [ ] **Step 1: Write failing stop and API tests**

```python
@pytest.mark.asyncio
async def test_incomplete_delivery_rejects_complete_stop(react):
    stopped = await react.act_result([stop_call(delivery_disposition="complete")])
    assert stopped is False
    assert react._continue is True
    assert "missing_endpoint_evidence" in await last_tool_message(react.agent)


@pytest.mark.asyncio
async def test_partial_stop_preserves_gaps(react):
    stopped = await react.act_result([stop_call(delivery_disposition="partial")])
    assert stopped is True
    assert not react.dag_controller.delivery_report().complete
```

- [ ] **Step 2: Run RED**

Run: `uv run pytest -s tests/test_dag_delivery.py tests/test_frontend_parity.py -k 'dag or delivery_disposition'`

- [ ] **Step 3: Audit before honoring stop**

Standard keeps existing behavior. In DAG modes, `complete` requires a complete
report. If incomplete, do not call StopTool or set `_continue=False`; return the
gaps and, in guided mode, trigger replanning. `partial` and `user_terminated`
append an audited disposition without waiving gates.

- [ ] **Step 4: Add read-only service/API/backend interfaces**

```text
GET /api/conversations/{conversation_id}/dag/projection
GET /api/conversations/{conversation_id}/dag/graphs/{graph_kind}
GET /api/conversations/{conversation_id}/dag/delivery-report
GET /api/conversations/{conversation_id}/dag/history?after_revision=...
```

Return 404 when no bundle exists and never initialize from a read endpoint. Add
matching local/remote backend methods. Do not modify protected TUI files.

- [ ] **Step 5: Run GREEN**

Run: `uv run pytest -s tests/test_dag_delivery.py tests/test_frontend_parity.py tests/test_backends.py -k 'dag or delivery_disposition or orchestration'`

---

### Task 9: Claisen DAG-guided SOP example

**Files:**
- Modify: `cloudra/skills/dft-calculation/SKILL.md`
- Modify: `cloudra/skills/dft-calculation/references/mechanism-elucidation-sop.md`
- Modify: `cloudra/skills/dft-calculation/references/mechanisms/pericyclic.md`
- Modify: `cloudra/prompts/coordinator.md`
- Test: `tests/test_dag_sop.py`

**Interfaces:**
- Documents mode selection, the two graph roles, evidence levels, and an end-to-end Claisen graph evolution.

- [ ] **Step 1: Write failing documentation contract**

```python
def test_claisen_sop_distinguishes_both_dags():
    text = SOP.read_text(encoding="utf-8")
    assert "C=COCC=C" in text and "C=CCCC=O" in text
    assert "process DAG" in text and "delivery DAG" in text
    assert "endpoint-supported" in text
    assert "standard" in text and "dag_record" in text and "dag_guided" in text
    assert "ts_guess" in text and "不能" in text
```

- [ ] **Step 2: Run RED**

Run: `uv run pytest -s tests/test_dag_sop.py`

- [ ] **Step 3: Add a worked example, not a universal script**

Walk through mapping, reactive conformers, parallel TS guesses,
optimization/frequency pruning, short bidirectional IRC, endpoint optimization,
endpoint matching, and thermochemistry. After each stage show process status and
delivery evidence references. Preserve the rule that advisory tools cannot close
a mechanistic claim.

- [ ] **Step 4: Document agent behavior per mode**

Standard uses no DAG operations. Record mode explicitly maintains both graphs.
Guided mode follows validated Supervisor frontier changes but may challenge them
with evidence. The agent never invents a reference or treats graph completeness
as a substitute for scientific judgment.

- [ ] **Step 5: Run GREEN**

Run: `uv run pytest -s tests/test_dag_sop.py`

---

### Task 10: Focused completion audit

**Files:**
- Review all files named above.
- Do not run the full repository suite.

**Interfaces:**
- Proves every design requirement with focused tests and direct persisted-state inspection.

- [ ] **Step 1: Run focused tests**

```bash
uv run pytest -s \
  tests/test_dag_mode.py tests/test_dag_store.py tests/test_dag_engine.py \
  tests/test_dag_completion.py tests/test_dag_tool.py \
  tests/test_dag_controller.py tests/test_dag_supervisor.py \
  tests/test_dag_delivery.py tests/test_dag_sop.py \
  tests/test_frontend_parity.py tests/test_backends.py \
  tests/test_prompt_assembler.py tests/test_memory_and_supervisor.py \
  tests/test_tools_core.py
```

Expected: all selected tests pass; do not infer full-repository health.

- [ ] **Step 2: Compile changed modules**

Run: `uv run python -m compileall -q cloudra/dag cloudra/supervisor.py cloudra/react.py cloudra/agent.py cloudra/service.py cloudra/api.py cloudra/backends.py cloudra/tools/Plantool/dag_graph.py`

- [ ] **Step 3: Inspect mode isolation directly**

Create one temporary session per mode and prove:

```text
standard: graph rows=0, supervisor calls=0
dag_record: graph rows=2, supervisor calls=0
dag_guided: graph rows=2, supervisor calls>=1 after a qualifying trigger
```

- [ ] **Step 4: Inspect persistence and chemistry semantics**

Reload through a new `DagStore` and compare revisions, species pointers, TS/IRC
edge pointers, history, and delivery gaps. Verify the catalytic-cycle fixture is
acyclic while entry/return occurrences share one `species_ref`.

- [ ] **Step 5: Run hygiene checks and report exact scope**

Run: `git diff --check`

Report focused pass/skip counts and explicitly state that the full suite was not
run, as requested.
