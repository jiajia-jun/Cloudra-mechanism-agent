# Architecture

[Documentation](README_EN.md) · [Contributing](../CONTRIBUTING.md)

Cloudra connects a shared agent runtime, chemistry tools and a calculation scheduler. In graph modes, species and reaction steps carry links to calculation evidence. The [DAG guide](DAG_ORCHESTRATION.md) describes delivery contracts; the [TS guide](TS_PROCESS_SOP.md) owns transition-state workflow and scientific acceptance requirements.

## Architecture: Agent Collaboration and an Event-Sourced Kernel

### Roles and Responsibilities

All roles use the same `runtime_v2` execution kernel, with explicit permissions and responsibilities:

- **Coordinator** decomposes the research objective, delegates work and maintains the mechanism graph and delivery scope.
- **Specialists** perform their permitted research, computation or writing tasks and return concrete files and tool receipts. Hierarchical launcher/swarm dispatch and AgentHub peer calls share the project agent lifecycle; their permission checks still apply.
- **Supervisor** is a normal runtime agent in `dag_guided` mode. It reads pending reviews, drafts and queued requests from the persisted supervision mailbox and adjudicates submitted claims. It is read-only on the delivery graph; accepting a draft or claim cannot replace missing or failed scientific checks.
- **AgentHub** provides persisted forum posts, messages, search and peer calls so agents can exchange findings asynchronously.

### Event-Driven Runtime with Declarative Notice Injection (S1 Kernel)

The runtime (`runtime_v2`) is engineered for deterministic execution and crash resilience:
- **Append-Only Event Sourcing (`EventLog` & `EventHub`)**: Every tool execution, thinking step (`agent.thinking`), state transition, and graph mutation is logged as an immutable, typed event. Sessions can be replayed, audited, and seamlessly restored across server restarts or power failures.
- **Declarative Notice Injection**: Instead of fragile manual prompt concatenations, the engine uses `notices.pin` to deterministically assemble DAG gaps, active research goals, and schedule alerts into LLM turns.
- **Autonomous Schedule Guard**: When schedule mode is enabled, attempts to stop without an active wake-up (timer or read-only `check_command` poll) are intercepted by `ScheduleStage`, so agents can sleep during long calculations and wake when a check succeeds or the timeout hits.
- **Functional Core with Externalized State**: Command handling is split into pure, IO-free deciders that emit event drafts and effects, a single guard-free `apply_event` applier shared by the online path and crash-recovery replay, and a thin shell that executes the effects. Snapshots are only throttled caches — recovery replays events after per-project high-water marks. Nothing durable lives in process memory: approvals, compaction requests, and agent state are all event projections, explicitly expired (`approval.expired` / `interaction.expired`) on restart rather than silently dropped.

### Process Topology: A Crash-Isolated Execution Plane

The control plane and calculation execution run separately:

- **Web process** (`api_v2` + SPA, single port): the control plane. It may crash or restart at any time — no computation dies with it.
- **Compute scheduler daemon** (`cloudra scheduler`, auto-spawned detached): claims queued jobs under capacity accounting and launches detached `guard` processes. Failures, Agent cancellation, and service shutdown preserve computations. An explicit compute cancellation writes `cancel_requested`; a native guard signals only the process group it created, then confirms child exit and released `flock` before recording `cancelled` and releasing capacity. Terminal states are CAS-written to the central `compute.db`, and completion notifications reach the control plane through fine-grained DB polling — notifications are never lost across API downtime.

Durable state synchronization between the control plane, scheduler and guards uses SQLite (WAL) and file locks.

The `chem-kb` plugin retrieves complete source knowledge texts through graph-keyword matches exposed in AgentHub. The graph indexes sources; retrieved cards supply the content. It does not start a vector service or fill missing graph matches through vector search or content scanning. Knowledge health reports graph and source-content availability.

`cloudra stop` is the explicit full-stop entry: it writes the `daemons.stop` marker (auto-spawn is disabled and the daemons exit on their own self-check), asks the API to shut down gracefully (cancelling and awaiting all agent runs and finalization tasks, closing streams/clients, reaping owned JS hosts), and re-checks within a bounded wait. Per-agent cancel (`POST /api/v2/agents/{id}/cancel`) stops that agent's reasoning work without touching compute jobs; requests already sent to the LLM provider cannot be revoked remotely — locally no further reads/retries/new requests are issued.

## Repository map

| Directory | Responsibility |
| --- | --- |
| `cloudra/runtime_v2/` | Shared agent loop, roles, policies, events, recovery and JS host. |
| `cloudra/dag/` | Mechanism graph, stage contracts and evidence review. |
| `cloudra/tools/` | Registered chemistry, computation, file and search tools; capabilities restrict access. |
| `cloudra/scheduler/`, `cloudra/runtime/` | Job dispatch, monitoring and guards; native program termination is checked independently of parsed values. |
| `cloudra/services/`, `frontend/` | Web API and user interface. |
| `cloudra/persistence/` | Databases and the shared path definitions in `paths.py`. |
| `cloudra/infra/` | Configuration, file locks and SSH/Slurm transport. |
| `cloudra/knowledge/`, `kg_data/`, `知识卡片/` | Knowledge retrieval, graph inputs and source texts. `vector_store/` is a historical offline asset. |
| `cloudra/benchmark/`, `ideapool/` | Benchmark implementation and versioned task sources. |
| `gold_compute/` | Reference evidence indexes and reproduction instructions. |
| `paper/` | Research inputs, figure sources, and companion-data reproduction scripts. |
| `deploy/`, `scripts/`, `tests/` | Deployment guides, maintenance scripts and regression tests. |

## Maintenance pointers

Use `persistence/paths.py` for data paths and `infra/config.py` for configuration updates. Roles are defined in `runtime_v2/roles.py`; tool registration lives in `tools/registry.py`. Policies follow the order in `runtime_v2/policies/__init__.py`; context compaction is handled separately by the runtime. Model-generated predictions are hypotheses, not calculation evidence.

Local compute liveness and exclusive ownership use file locks. A job's assigned node does not change because another node has spare capacity. Node configuration and remote execution are documented in [Node registry](NODE_REGISTRY.md); SSH and Slurm have their own deployment instructions in the [documentation index](README_EN.md).

Atom indices depend on the interface: Gaussian uses 1-based indices and ORCA uses 0-based indices; structure-tool references are 1-based. Follow the actual tool contract and the [TS input guide](TS_PROCESS_SOP.md), rather than converting by guesswork.

Tool invocation and documentation loading are described in [Tool protocols](TOOL_PROTOCOLS.md). Rules for code changes remain in [AGENTS.md](../AGENTS.md).
