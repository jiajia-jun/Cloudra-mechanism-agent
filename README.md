# Cloudra

**Autonomous Agent System for Organic Small-Molecule Mechanism Computation**  
*Geometric & Electronic Perception · DAG Delivery Contracts · Anarchist Peer-to-Peer Agent Architecture*

[![CI](https://github.com/yyywaa/Cloudra-mechanism-agent/actions/workflows/ci.yml/badge.svg)](https://github.com/yyywaa/Cloudra-mechanism-agent/actions/workflows/ci.yml)
[![Python ≥ 3.11](https://img.shields.io/badge/python-%E2%89%A53.11-blue)](pyproject.toml)
[![License: AGPL v3](https://img.shields.io/badge/license-AGPL--3.0-blue)](LICENSE)

[中文文档](README_CN.md) · [Documentation Hub](docs/README.md) · [Core Novelty](docs/novelty.md) · [DAG Orchestration Spec](docs/DAG_ORCHESTRATION.md) · [TS Process SOP](docs/TS_PROCESS_SOP.md) · [Plugin Guide](docs/PLUGINS.md)

> Cloudra is an autonomous research agent system for computational organic chemistry. It does not claim to replace human insight with absolute truth, nor does it aim for superficial benchmark numbers. Its purpose is to provide a rigorous, non-hallucinatory, and deterministically auditable foundation for long-horizon mechanistic elucidation.

---

## Quick Start

### 1. Requirements & Installation

Requires Python ≥ 3.11, Node.js ≥ 22 (both the JS host used by the default `javascript` protocol and the frontend test runner require ≥ 22), a POSIX environment (Linux/macOS — the execution plane relies on `flock`/`nice` semantics), and access to any OpenAI-compatible LLM endpoint.

```bash
# Clone the repository
git clone https://github.com/yyywaa/Cloudra-mechanism-agent.git
cd Cloudra-mechanism-agent

# Run the all-in-one setup script (virtual environment + dependencies)
./install.sh

# Initialize default configuration
cloudra config init
```

### 2. Launch the Full-Stack Web Console

Cloudra features a unified, single-port web interface (FastAPI control plane + React/Vite SPA):

```bash
cloudra                      # Builds the frontend and starts the server, opening your browser
cloudra web --skip-build     # Fast restart using pre-built assets
cloudra web --host 0.0.0.0   # Bind a custom address/port (LAN / remote UI)
```

> Access control is the bearer token only: `Authorization: Bearer …` and `?token=`
> are equivalent, any HTTP method, no Host check. Open the printed `#token=` URL
> from any machine that can reach the bind address. Default bind is
> `127.0.0.1:8000`. Do not use `CLOUDRA_API_TOKEN=off` on a non-loopback bind.

### 3. Geek-Friendly Slash Commands

Type `/` directly in the chat composer to open the sleek, keyboard-navigable autocomplete menu:

- `/schedule [on|off]`: Toggle autonomous schedule mode. When active, stopping without an active self-wake reminder is intercepted, protecting long unattended computational runs.
- `/goal <description>`: Pin the primary research objective for the active agent, preserved even across aggressive context compactions.
- `/yolo [on|off]`: Toggle automated safety approval (YOLO mode) to bypass manual confirmations on destructive actions and compute submissions.
- `/compact`: Trigger structured context compaction, archiving past trajectory turns and emitting handover summaries.
- `/help`: Display slash command usage and syntax.

### 4. Web Search Configuration (Optional)

Cloudra natively supports provider-side web search with external tool fallback:

```bash
export CLOUDRA_COORDINATOR__NATIVE_SEARCH=auto        # off / auto / openai / openrouter / deepseek / gemini / custom
export CLOUDRA_COORDINATOR__NATIVE_SEARCH_PARAMS='{}' # Custom provider parameter injection
```

When native search is not enabled, the system automatically falls back to external search tools (Tavily, Brave, Bing, or DuckDuckGo).

---

## Core Novelty: DAG-Driven Reaction Mechanism Elucidation

### The Pitfall: Why Conventional LLM Agents Fail at Reaction Mechanisms

Elucidating organic reaction mechanisms requires an exacting, interdependent computational pipeline: **Atom Mapping → Conformation Sampling → TS Guess Interpolation → Saddle-Point Optimization → Frequency & Solitary Imaginary Mode Verification → Bidirectional IRC Path Integration → Endpoint Geometry Optimization → Product Isomorphism Matching → Thermochemistry & Barrier Annotation**.

Generic LLM agents invariably treat chemistry as "calling tools + writing summaries", leading to two severe vulnerabilities:

1. **Microscopic Spatial Blindness & Coordinate Hallucination**: Language models cannot directly "see" 3D Euclidean space. Without hard physical constraints, agents make up atomic coordinates, guess collision orientations, and misremember numerical frequencies and energies across drifting conversation turns.
2. **"Completion by Assertion" vs. "Completion by Evidence"**: Whether a mechanism is truly established is conventionally decided by the agent itself in a closing paragraph. Smooth scientific prose regularly disguises broken IRC paths, mismatched endpoints, or spurious imaginary frequencies, with no durable evidence tying claims to verifiable quantum chemistry outputs.

### The Cloudra Solution: Perception Layer + Delivery DAG Contracts

Cloudra addresses these challenges through two interlocking pillars:

```
                    ┌─────────────────────────────────────────┐
                    │       Coordinator / Peer Sub-Agents     │
                    └────────────────────┬────────────────────┘
                                         │  Propose Mechanism / Bind Evidence
                                         ▼
┌─────────────────────────┐      ┌─────────────────────────┐      ┌─────────────────────────┐
│  Perception Layer       │ ───► │  Delivery Evidence DAG  │ ◄─── │  Scientific Supervisor  │
│  · No hand-written xyz  │      │  · Immutable Artifacts  │      │  · Review Call Inbox    │
│  · Reaction Mapping     │      │  · Ordered Stage Locks  │      │  · Gate Unlocking       │
│  · CREST / xTB Ensemble │      │  · Deterministic Audit  │      │  · Non-modifying Audit  │
│  · Mayer / IBO Analysis │      └─────────────────────────┘      └─────────────────────────┘
└─────────────────────────┘
```

#### 1. Geometric & Electronic Perception Layer
Agents never hand-write Cartesian coordinates or transcribe floating-point energies from memory; they perceive molecules strictly through structured tools:
- **Zero Hand-Written Coordinates (`coord_guard`)**: A physical safety guard intercepts hand-crafted `.gjf` or `.xyz` coordinate blocks. All geometries must originate from deterministic format conversion, SMILES 3D builders, or QM relaxation.
- **Reaction Atom Mapping**: Tracks atom conservation, breaking/forming bonds, and reacting center pairs across 3D conformations.
- **Orientation & Conformer Sampling**: Employs CREST and xTB dynamic relaxation within constrained distance envelopes to determine bimolecular approach pathways rather than guessing orientations.
- **Electronic Structure Analysis**: Provides atomic charges, Mayer bond orders (capturing partially formed transition-state bonds), IBO Lewis representations, and open-shell spin contamination checks ($\langle S^2 \rangle$).
- **Full Reaction Pathway Tooling**: IDPP saddle-point interpolation, flexible potential energy surface scans, rigorous bidirectional IRC trajectory validation, and log parsers that extract structured energies, frequencies, and convergence metrics.

#### 2. Delivery-Only Evidence DAG Harness
Mechanistic completion is determined strictly by the state of an immutable, context-independent **Delivery DAG**:
- **Graph Elements as Evidence Debt**: Nodes represent the appearance of intermediate species along a reaction coordinate (acyclic structure is preserved by assigning entry and return states of catalysts to distinct nodes sharing canonical species metadata). Edges represent elementary reaction steps. Each element carries a stage contract.
- **Ordered Stage Locks**: Each element only owes the stages declared on its contract; later stages cannot be bound until preceding *required* stages on that same element are verified. Default mechanism drafts require a first-order saddle (`ts_opt` + `frequency` with exactly one imaginary frequency); `ts_guess` is advisory. IRC, endpoint minima, direction, identity, and thermochemistry are optional extras when that step's chemistry needs a path proof — they are not the live completion bar.
- **Deterministic Coverage Audit**: Graph elements accept only typed references to immutable calculation artifacts and job records. Study delivery is evaluated by deterministic algorithms; any unfulfilled or rejected stage remains an open gap blocking completion.

#### 3. End-to-End Experimental Demonstration
Cloudra has fully and autonomously executed an **end-to-end Diels-Alder cycloaddition mechanism study** under guided supervision: from precursor mapping to transition-state search, solitary imaginary frequency validation, bidirectional IRC integration, endpoint optimization, and thermochemical barrier derivation. The entire trajectory is fully preserved and auditable in the database.

---

## Architecture: Anarchist Peer-to-Peer Topology & Event-Sourced Kernel

### Anarchist Design Philosophy

Traditional multi-agent frameworks tend to replicate bureaucratic corporate hierarchies, enforcing rigid master-slave command chains that create cognitive bottlenecks and information loss.

Cloudra is built on an **Anarchist Peer-to-Peer Philosophy**:
- **Equal Standing with Specialized Division of Labor**: There are no master or subordinate agents in Cloudra. The `coordinator`, `dft` specialist, reaction `explorer`, literature `researcher`, `md` modeler, `experiment` designer, and scientific `writer` share the exact same structural standing and independent lifecycles.
- **Asynchronous Forum & Peer Collaboration (`agent_hub`)**: Agents share discoveries, post experimental notes, and notify peers via a decentralized topic forum (`agent_hub`). Any agent can autonomously claim tasks or use the `call` verb to invite specific skill profiles to collaborate without centralized bottleneck dispatchers.

### Event-Driven Runtime with Declarative Notice Injection (S1 Kernel)

The runtime (`runtime_v2`) is engineered for deterministic execution and crash resilience:
- **Append-Only Event Sourcing (`EventLog` & `EventHub`)**: Every tool execution, thinking step (`agent.thinking`), state transition, and graph mutation is logged as an immutable, typed event. Sessions can be replayed, audited, and seamlessly restored across server restarts or power failures.
- **Declarative Notice Injection**: Instead of fragile manual prompt concatenations, the engine uses `notices.pin` to deterministically assemble DAG gaps, active research goals, and schedule alerts into LLM turns.
- **Autonomous Schedule Guard**: When schedule mode is enabled, attempts to stop without an active wake-up (timer or read-only `check_command` poll) are intercepted by `ScheduleStage`, so agents can sleep during long calculations and wake when a check succeeds or the timeout hits.
- **Functional Core with Externalized State**: Command handling is split into pure, IO-free deciders that emit event drafts and effects, a single guard-free `apply_event` applier shared by the online path and crash-recovery replay, and a thin shell that executes the effects. Snapshots are only throttled caches — recovery replays events after per-project high-water marks. Nothing durable lives in process memory: approvals, compaction requests, and agent state are all event projections, explicitly expired (`approval.expired` / `interaction.expired`) on restart rather than silently dropped.

### Process Topology: A Crash-Isolated Execution Plane

A running Cloudra deployment is three deliberately separate OS processes:

- **Web process** (`api_v2` + SPA, single port): the control plane. It may crash or restart at any time — no computation dies with it.
- **Compute scheduler daemon** (`cloudra scheduler`, auto-spawned detached): claims queued jobs under capacity accounting and launches detached `guard` processes. Cloudra never kills a compute process; liveness is judged exclusively by `flock` probing. Terminal states are CAS-written to the central `compute.db`, and completion notifications reach the control plane through fine-grained DB polling — notifications are never lost across API downtime.
- **Knowledge vector service** (`kg_vec_service.py`, auto-spawned when the chem-kb plugin is installed): runs under a separate interpreter so that torch/sentence-transformers stay out of the main environment.

State synchronization between processes goes through SQLite (WAL) and file locks — never through in-memory channels.

`cloudra stop` is the explicit full-stop entry: it writes the `daemons.stop` marker (auto-spawn is disabled and the daemons exit on their own self-check), asks the API to shut down gracefully (cancelling and awaiting all agent runs and finalization tasks, closing streams/clients, reaping owned JS hosts), and re-checks within a bounded wait. Per-agent cancel (`POST /api/v2/agents/{id}/cancel`) stops that agent's reasoning work without touching compute jobs; requests already sent to the LLM provider cannot be revoked remotely — locally no further reads/retries/new requests are issued.

---

## Three Orchestration Modes: Ablation Boundaries for Research

To enable rigorous ablation studies on the exact impact of evidence graphs and scientific supervision, Cloudra provides three switchable modes:

| Mode | Behavior | Scientific Role |
| :--- | :--- | :--- |
| `standard` (Default) | No graph overhead; operates as a standard high-capability chemistry agent | Baseline Control |
| `dag_record` | Auto-accepts mechanism drafts; agent self-binds evidence without supervisor | Evidence Graph Ablation |
| `dag_guided` | Independent scientific supervisor reviews drafts and audits call evidence | Full Supervised Protocol |

Modes can be toggled dynamically in the project settings UI.

---

## Tool Invocation Protocols

The default protocol is `javascript`; `traditional` is a per-agent opt-in. With the default, the model submits one bounded JavaScript program (`js_exec`) per wire exchange that orchestrates capability-permitted tools and reports results with `text(value)`:

```js
const result = await tools.log_parser({log_path: '/absolute/path/calculation.out'});
text({call_id: result.call_id, ok: result.is_success, data: result.data});
```

With `invocation_protocol: traditional` (Web UI agent settings, or the same field in a settings patch) the model instead issues one tool call per wire exchange and needs no JS host at all. Both protocols share the lifecycle and authority rules below; only the dispatch shape differs.

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

---

## Quantum Chemistry & HPC Integration

Cloudra seamlessly bridges local exploratory modeling and remote cluster computing:

- **Electronic Structure Engines**: Integrates with Gaussian, ORCA, xTB, CREST, VASP, and CP2K for automated input preparation, local process execution, and Slurm batch submission.
- **Cheminformatics & Property Analysis**: Connects with RDKit, OpenBabel, Multiwfn, and Molli for 3D geometry manipulation, NMR/IR spectral simulation, stoichiometry verification, and high-fidelity CDXML reaction parsing (stereochemistry, connectivity, charge, and multiplicity preserved).
- **Literature & Academic Authoring**: Direct integration with OpenAlex for literature search and automated Markdown/LaTeX report generation with full level-of-theory annotations.

---

## Repository Layout

```text
cloudra/                         Python package: runtime, services, tools, benchmark, prompts and skills
frontend/                        React + TypeScript + Vite web console
scripts/                         Setup, runtime/data helpers and application_docs/ one-off editors
deploy/                          Deployment and remote-compute guides
tests/                           Regression tests and scientific fixtures
docs/                            Current architecture/SOPs, evidence, licenses, assets and archive/
paper/                           Manuscripts, literature/ sources and archive/ research snapshots
ideapool/                        Versioned task sources, generated tasks and historical research
gold_compute/                    Gold methodology, scientific records and archived handoffs
kg_data/, vector_store/          Knowledge graph inputs and vector metadata
知识卡片/                       Knowledge-card source archive
申请材料/, 软著申请材料/        External application deliverables (existing paths preserved)
archive/                         Local experiment remnants (ignored; tracked README exception)
```

See the [documentation hub](docs/README.md), [script index](scripts/README.md) and [literature index](paper/literature/README.md) for details. Root configuration, license/citation files, `install.sh` and `web.sh` remain in place; temporary runtime and build outputs are ignored.

---

## Development & Testing

Run the full automated test suite and style checks:

```bash
uv run pytest -q tests/            # Run the complete test suite (2300+ tests)
uv run pytest -q tests/test_dag*   # Focus on DAG orchestration
uv run pytest -q tests/test_runtime_v2* # Focus on runtime_v2 kernel and policy stages
uv run ruff check cloudra tests    # Lint check (line-length 120)
```

---

## Citation

If you use or reference Cloudra in your scientific research, please cite the repository with the commit hash:

```bibtex
@misc{cloudra2026,
  title  = {Cloudra: An Autonomous Agent for Organic Small-Molecule Mechanism Computation},
  author = {{Cloudra Developers}},
  year   = {2026},
  url    = {https://github.com/yyywaa/Cloudra-mechanism-agent},
  note   = {Commit-pinned research software for mechanistic organic chemistry}
}
```

## License

Copyright (C) 2026 Cloudra Team.

Cloudra is free software: you can redistribute it and/or modify it under the terms of the
[GNU Affero General Public License](LICENSE) as published by the Free Software Foundation,
either version 3 of the License, or (at your option) any later version.

Cloudra is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without
even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
[GNU Affero General Public License](LICENSE) for more details.

Third-party components bundled in this repository keep their own licenses — see
[docs/licenses/](docs/licenses/README.md).

The skills under `cloudra/skills/` are a deliberate exception: each declares `license: MIT`
and is MIT licensed, so the knowledge stays portable across agent harnesses. The engine,
the DAG, the tools and the scheduler remain AGPL.

Contributions are accepted under the Developer Certificate of Origin; sign your commits with
`git commit -s`. See [CONTRIBUTING.md](CONTRIBUTING.md).
