# DAG-Guided Supervisor Design

## Goal

Replace the current periodic, advice-only Supervisor with an opt-in graph-guided
orchestrator for mechanism studies. DAG guidance is disabled by default and is
selected per task/session so ordinary work pays no graph or Supervisor cost.
When enabled, the harness persists two related DAGs for the conversation: a
process DAG that answers "what should be done next?" and a delivery DAG that is
the investigated chemical mechanism itself and answers "what has actually been
established?"

The graph store is authoritative. Neither graph lives only in model context or
process memory, and graph nodes contain stable references to records and
artifacts rather than embedding geometries, logs, or tool output bodies.

## Modes and ablation boundary

`orchestration_mode` is a session-level enum, not a boolean:

- `standard`: do not load or mutate either DAG and do not run the Supervisor;
- `dag_record`: the deterministic harness records both DAGs, but the Supervisor
  cannot influence the agent or mutate a graph;
- `dag_guided`: record both DAGs and allow the Supervisor to submit constrained
  graph mutations and frontier changes.

The user-facing default is `standard`. The main UI may expose Standard and
DAG-guided as the ordinary choices while CLI/API and experiment configuration
also expose `dag_record`. This permits three-way ablations that separate the
effect of graph bookkeeping from the effect of Supervisor control.

The mode is chosen when a session is created and is immutable after execution
starts. It is stored with the session together with a reproducibility snapshot:
Supervisor model, prompt revision, graph-policy revision, and relevant runtime
configuration. The two graphs are conversation-scoped and survive session and
process restarts. A standard session neither reads nor writes an existing graph;
a later DAG session resumes it.

## The two DAGs

### Process DAG

The process DAG represents planned and completed work. Its nodes point to work
items or immutable outputs such as a mapping result, conformer search, TS guess,
optimization job, frequency analysis, short IRC, endpoint optimization, or
thermochemistry analysis. Dependency edges determine readiness. A separate
`produces_evidence_for` reference links a process node to a delivery node or
delivery edge; this cross-reference is not a third graph.

Process-node states are `proposed`, `ready`, `running`, `succeeded`, `failed`,
`blocked`, `skipped`, and `superseded`. Failure is evidence, not deletion. A
replacement calculation supersedes an earlier node while preserving the full
audit chain.

The process frontier is derived from dependency satisfaction, status, priority,
and the unresolved gaps in the delivery graph. The agent receives a bounded
projection containing the ready frontier, active blockers, recent changes, and
the delivery gaps affected by those tasks; it does not receive the full graph on
every turn.

### Delivery DAG / mechanism graph

The delivery DAG is the mechanism graph; no third canonical chemical graph is
introduced. A node is an occurrence of an intermediate in a proposed pathway.
It contains a `species_ref` plus references to identity, optimized-geometry,
frequency, charge/multiplicity, and other evidence. A directed edge is an
elementary-step occurrence and contains references to its TS optimization,
imaginary-mode assessment, short or full IRC, optimized IRC endpoints, endpoint
matching, and energy evidence.

The referenced species, calculations, logs, and structures remain immutable
records or `ArtifactService` snapshots. The graph stores typed IDs and small
annotations only; a filesystem path by itself is not durable evidence.

Real chemistry can contain catalytic cycles and reversible steps. The delivery
representation remains acyclic by using occurrence nodes: `Cat@entry` and
`Cat@return` are distinct DAG nodes that point to the same canonical
`species_ref`. Reversibility is an edge annotation rather than a reverse edge.
Parallel mechanisms remain parallel branches. This makes the graph an auditable
pathway expansion rather than a claim that the underlying reaction network is
acyclic.

Delivery nodes and edges carry evidence levels, not truth labels. Suggested
levels include `proposed`, `structure_supported`, `saddle_supported`,
`endpoint_supported`, `thermo_annotated`, `rejected`, and `inconclusive`.
Evidence levels are derived from referenced structured results. Passing
`ts_guess`, a scan, or any other advisory tool cannot by itself promote an edge
to `saddle_supported` or `endpoint_supported`.

## Delivery completeness

Whether a reaction is "studied clearly enough" is computed from a graph-level
coverage contract, not from a third checklist DAG. The contract is initialized
from the user's goal and the selected mechanism SOP and is stored with its own
revision. It can require, for example, that claimed intermediates have optimized
minimum evidence, claimed elementary steps have a suitable saddle and endpoint
evidence, relevant competing branches have an explicit disposition, and all
reported energies share documented conditions and energy provenance.

The harness produces a completion report containing satisfied gates, unresolved
gaps, inconclusive gates, and user-waived gates. Completion is deterministic and
evidence-derived. A model statement cannot mark the root deliverable complete.
The user may explicitly accept partial delivery or waive a gate; both actions
are persisted and shown in the report.

## Persistence model

The existing per-conversation SQLite database is the natural persistence
boundary. `session_events` remains best-effort telemetry and is not reused as
canonical graph storage. The graph subsystem owns durable tables for graph
metadata, nodes, dependency edges, cross-graph evidence links, coverage
contracts, and an append-only mutation journal. Current node/edge rows form a
materialized view of that journal so loading does not require replaying the
entire history.

Every mutation records graph revision, session, actor (`harness`, `supervisor`,
`agent`, or `user`), operation, rationale, and timestamp. Mutations use
optimistic revision checks and a transaction. A failed operation leaves both
graphs unchanged. Restart recovery reads the durable materialized state and
verifies that its revision agrees with the mutation journal.

Stable reference types are explicit, for example `artifact`, `compute_job`,
`tool_result`, and `species`. Best-effort `session_events` are never accepted as
delivery evidence. Evidence resolution validates that the target exists in the
same conversation and records a content hash or target revision where
applicable.

## Supervisor responsibility and flexibility

The legacy "review every 15 ReAct steps and inject free-text advice" path is
retired from ordinary execution. In `dag_guided`, the Supervisor receives a
bounded graph projection and returns typed mutation proposals rather than an
unstructured verdict. It is invoked by meaningful events: graph initialization,
new evidence, a failed or repeatedly retried process node, an empty process
frontier while delivery remains incomplete, a user request to replan, or a
pre-delivery audit.

Permitted process-DAG operations include adding and splitting work, adding or
removing non-executed dependencies, changing priority, blocking, reopening,
skipping with a reason, and superseding obsolete work. Permitted delivery-DAG
operations include adding pathway occurrences or alternative elementary steps,
linking existing evidence, marking a hypothesis unsupported or stale, and
requesting evidence that creates process work.

Flexibility is bounded by invariants. The Supervisor cannot delete evidence,
rewrite immutable artifacts or tool results, create a dangling reference,
introduce a cycle, lower a user-defined coverage requirement, remove a user
requirement, waive a gate, or directly mark overall delivery complete. It may add
stricter checks. Changes to the user's top-level goal or acceptance boundary are
returned as proposals requiring user approval.

Mutation proposals are batches with a base graph revision. The graph engine
validates the entire batch before applying it atomically. Rejected proposals are
recorded with a machine-readable reason and may be revised once; repeated
rejection falls back to the existing valid frontier instead of entering a repair
loop.

## Harness data flow

On DAG-session creation, the harness loads or initializes both graphs and the
coverage contract, then derives a compact initial frontier. Tool execution
remains stateless. When a tool or compute job finishes, a deterministic adapter
registers immutable outputs, emits evidence references, updates affected process
nodes, and recomputes delivery evidence levels. In `dag_record` this deterministic
path is the whole graph behavior. In `dag_guided`, qualifying changes may also
trigger a Supervisor mutation proposal before the next agent turn.

The prompt assembler injects only the current mode, graph revisions, process
frontier, blockers, delivery gaps, and recent accepted graph changes. The agent
can request a larger subgraph explicitly. Graph mutations and mode metadata are
shown to the UI as reliable graph events distinct from best-effort telemetry.

Before normal completion in a DAG mode, the harness computes the delivery
report. A complete report permits normal delivery. An incomplete report does not
trap the task indefinitely: the agent must either continue from the generated
frontier, deliver an explicitly partial result, or ask the user to waive/stop.

## Interfaces

Session creation gains
`orchestration_mode: "standard" | "dag_record" | "dag_guided"`, defaulting to
`standard`, across service, runner, API, CLI, backend clients, and TUI submission.
The chosen value is returned in session records and cannot be changed after the
session starts.

The graph engine exposes typed application methods rather than a general SQL or
JSON-edit tool. Read interfaces support a compact projection, a targeted
subgraph, a delivery report, and the mutation history. Write interfaces accept
validated operation batches and require actor identity plus a base revision.

The Supervisor is the primary adaptive writer in `dag_guided`; deterministic
harness adapters remain responsible for attaching actual execution evidence.
The main agent may request graph changes, but those requests pass through the
same validation and audit path.

## Failure and recovery behavior

Unrecognized tool results are attached as unclassified evidence and cannot
satisfy a coverage gate. Missing artifacts, hash mismatches, or broken references
make the affected evidence stale or inconclusive rather than silently complete.
An invalid Supervisor batch is rejected atomically. Concurrent mutations with a
stale base revision are re-read and reconsidered; they are never last-write-wins.

If graph storage is unavailable, `dag_record` and `dag_guided` fail closed with a
clear task error rather than degrading silently to standard mode. Standard mode
is independent of graph storage. A corrupted materialized view is reconstructed
from the mutation journal when possible and otherwise requires explicit repair.

## Compatibility and migration

Existing sessions are treated as `standard`. Existing graphs are not inferred
retroactively from arbitrary conversation text. The old periodic Supervisor
advice injection is disabled when the new mode field is present and ultimately
removed after compatibility tests are updated. Case-bank extraction, if kept,
is a separate post-run concern and has no graph mutation authority.

No chemistry tool gains persistent state. Existing tool schemas remain usable;
adapters interpret their structured outputs and create references in the graph
layer.

## Verification scope

This change requires focused tests, not a full repository suite. Unit tests cover
acyclicity, occurrence-node handling of catalytic cycles, immutable evidence
references, atomic mutation batches, optimistic revisions, Supervisor permission
boundaries, and deterministic delivery completion. Mode tests prove that
`standard` neither reads nor writes graphs, `dag_record` records without
Supervisor influence, and `dag_guided` applies valid Supervisor proposals.

Integration tests cover session-mode propagation, restart persistence, bounded
prompt projection, tool-result evidence attachment, event-driven Supervisor
triggers, incomplete delivery handling, and a Claisen example from mapping
through endpoint-supported delivery. The verification command targets only the
new graph, Supervisor, service/API propagation, and affected prompt tests unless
the user later requests a full-suite run.

## Considered alternatives

A single mutable JSON graph per conversation is easy to prototype but has weak
concurrency, audit, and recovery semantics. Reconstructing graphs only from
`session_events` would reuse existing infrastructure, but those events are
explicitly best-effort and may be dropped. A fully event-sourced graph with no
materialized state is maximally auditable but makes every load and query more
complex. The selected design uses a durable mutation journal plus transactional
materialized graph tables, preserving auditability without making replay the hot
path.
