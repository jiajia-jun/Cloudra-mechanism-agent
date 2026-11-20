# Architecture

[Documentation](README_EN.md) · [Contributing](../CONTRIBUTING.md)

Cloudra connects three pieces: a shared event-sourced agent runtime, a chemistry/QM toolset, and a detached compute scheduler. In graph modes (`dag_record` and `dag_guided`), every species and reaction step in the mechanism graph links back to immutable calculation logs. See the [DAG guide](DAG_ORCHESTRATION.md) for mechanism-graph contracts and the [TS guide](TS_PROCESS_SOP.md) for transition-state workflow and scientific acceptance rules.

## How Agents Work Together

Every agent role runs on the same `runtime_v2` loop, separated by explicit permissions:

- **Coordinator** plans the investigation, delegates calculations or literature tasks, and owns the mechanism graph.
- **Specialists** handle focused work (DFT, MD, literature, writing, etc.) and return concrete files and tool receipts. Subagents and AgentHub peer calls follow the same lifecycle and permission checks.
- **Supervisor** (active in `dag_guided` mode) reviews mechanism drafts and submitted calculation evidence from its persisted mailbox. It has read-only access to the graph, and a supervisor approval never overrides missing or failed physics checks.
- **AgentHub** is the shared persisted forum and mailbox where agents post findings and exchange messages asynchronously.

## Event-Sourced Runtime (`runtime_v2`)

`runtime_v2` is built so that restarts, crashes, and long calculations never leave silent half-state behind:

- **Append-only event log (`EventLog` & `EventHub`)**: Every model turn, thinking block (`agent.thinking`), tool call, state change, and graph edit is recorded as an immutable typed event. Sessions can be replayed, audited, and resumed after a server restart.
- **Declarative notices (`notices.pin`)**: Instead of ad-hoc prompt string stitching, active research goals, DAG gaps, and schedule reminders are injected deterministically into each turn.
- **Autonomous schedule guard (`ScheduleStage`)**: When `/schedule` mode is on, an agent cannot silently stop while long calculations are still running unless it sets a wake-up timer or read-only `check_command` poll.
- **Pure core, externalized state**: Commands run through IO-free deciders that emit event drafts and effects, one shared guard-free `apply_event` applier used by both live execution and crash replay, and a thin effect runner. Snapshots are only caches; recovery replays events past each project's high-water mark. Approvals, compaction requests, and agent state all live in the event log—orphaned prompts expire explicitly (`approval.expired` / `interaction.expired`) on restart rather than vanishing.

## Crash-Isolated Process Layout

The web interface and actual quantum-chemistry jobs live in separate processes so a UI crash never kills a calculation:

- **Web API & UI (`api_v2` + SPA, single port)** is the control plane. You can restart it anytime without touching running QM jobs.
- **Compute scheduler (`cloudra scheduler`)** claims queued jobs within configured node capacity and spawns detached `guard` processes. The desktop app starts and stops the scheduler alongside the API, or you can run it standalone. Even if the scheduler exits, already-running detached guards and remote Slurm/SSH jobs keep running.
- **Safe cancellation**: Cancelling a job writes `cancel_requested` into `compute.db` rather than killing processes blindly. A native guard signals its own process group, waits for the child to exit and release its exclusive file lock, and only then records `cancelled` and frees capacity.
- **Clean shutdown**: `cloudra stop` writes `daemons.stop`, asks the API to exit gracefully, cancels in-flight agent reasoning, closes streams and JS hosts, and confirms exit. Cancelling a single agent (`POST /api/v2/agents/{id}/cancel`) stops its LLM loop while leaving its compute jobs alive.

All durable state sync between the API, scheduler, and guards goes through SQLite (WAL mode) and POSIX file locks.

The `chem-kb` knowledge plugin retrieves full reference cards by matching graph keywords in AgentHub—it does not run a background vector service or guess matches via embedding search.

## Repository Map

| Directory | What lives here |
| --- | --- |
| `cloudra/runtime_v2/` | Agent loop, roles, policies, event log, crash recovery, and JS tool host. |
| `cloudra/dag/` | Mechanism graph, stage contracts, and evidence review. |
| `cloudra/tools/` | Chemistry, QM, file, search, and management tools with capability gates. |
| `cloudra/scheduler/`, `cloudra/runtime/` | Compute job scheduling, monitoring, and detached guards. |
| `cloudra/services/`, `frontend/` | FastAPI v2 backend and React/TypeScript web UI. |
| `cloudra/persistence/` | SQLite stores and canonical path helpers (`paths.py`). |
| `cloudra/infra/` | YAML config (`config.py`), file locks (`flocks.py`), diagnostics, and SSH/Slurm transport. |
| `cloudra/knowledge/`, `kg_data/`, `知识卡片/` | Graph-indexed chemistry knowledge base and source cards (`vector_store/` is a legacy offline artifact). |
| `cloudra/benchmark/`, `ideapool/` | Benchmark harness and versioned problem sets. |
| `gold_compute/` | Reference evidence indexes and reproduction guides. |
| `paper/` | Manuscript assets and reproduction scripts. |
| `deploy/`, `scripts/`, `tests/` | Deployment templates, helper scripts, and test suites. |

## Maintenance Notes

- Always resolve data paths via `persistence/paths.py` and write config changes through `infra/config.py` (`mutate_config`).
- Roles live in `runtime_v2/roles.py`, tool registration in `tools/registry.py`, and policy ordering in `runtime_v2/policies/__init__.py`.
- Local compute liveness relies exclusively on POSIX file locks (`infra/flocks.py`). A job stays on its assigned node—see [Node registry](NODE_REGISTRY.md) for local, SSH, and Slurm setup.
- Watch atom indexing: Gaussian and structure tools are **1-based**, while ORCA is **0-based**. Never convert indices by guesswork; follow the tool schema and [TS guide](TS_PROCESS_SOP.md).
- For tool invocation protocols and document loading, see [Tool protocols](TOOL_PROTOCOLS.md). Engineering rules live in [AGENTS.md](../AGENTS.md).
