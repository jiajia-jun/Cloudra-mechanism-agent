# Cloudra

**Autonomous Agent System for Organic Small-Molecule Mechanism Computation**  
*Geometric & Electronic Tools · Evidence-Based DAG Delivery · Event-Driven Agent Collaboration*

[![CI](https://github.com/yyywaa/Cloudra-mechanism-agent/actions/workflows/ci.yml/badge.svg)](https://github.com/yyywaa/Cloudra-mechanism-agent/actions/workflows/ci.yml)
[![Python ≥ 3.11](https://img.shields.io/badge/python-%E2%89%A53.11-blue)](pyproject.toml)
[![License: AGPL v3](https://img.shields.io/badge/license-AGPL--3.0-blue)](LICENSE)

[中文文档](README_CN.md) · [Documentation Hub](docs/README.md) · [Core Novelty](docs/novelty.md) · [DAG Orchestration Spec](docs/DAG_ORCHESTRATION.md) · [TS Process SOP](docs/TS_PROCESS_SOP.md) · [Plugin Guide](docs/PLUGINS.md)

> Cloudra supports computational organic chemistry research through structured chemistry tools, durable agent execution, and an evidence-backed mechanism graph. Calculation completion, scientific acceptance, and benchmark scores are recorded separately. Human review remains part of interpreting a mechanistic result.

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
- `/yolo [on|off]`: Toggle automated policy review (YOLO mode). Permission and scientific evidence requirements still apply.
- `/compact`: Trigger structured context compaction, archiving past trajectory turns and emitting handover summaries.
- `/help`: Display slash command usage and syntax.

### 4. Web Search Configuration

The existing `search` tool uses DeepSeek Search by default. The existing `browser`
tool uses DeepSeek Fetch for page text and returns Markdown; screenshots and
explicit page waits still use the browser. Search and Fetch share one API key,
independent of the selected language model. Configure both in Global Settings or:

```bash
cloudra config set search_provider deepseek
cloudra config set deepseek_api_key YOUR_DEEPSEEK_API_KEY
```

Environment variables `CLOUDRA_SEARCH_PROVIDER` and `CLOUDRA_DEEPSEEK_API_KEY` are
also supported. Provider choices are `deepseek` (default), `auto`, `tavily`,
`brave`, `bing`, and `duckduckgo`. A selected provider reports missing credentials
or request failures directly. `auto` tries DeepSeek, Tavily, Brave, Bing, then
DuckDuckGo; Tavily and Brave use `TAVILY_API_KEY` and `BRAVE_SEARCH_API_KEY`.
Non-DeepSeek providers keep the existing browser path for page text.

DeepSeek model-native search is opt-in; `native_search=auto` keeps the independent
search tool for DeepSeek. To explicitly enable its model-native search:

```bash
cloudra config set coordinator.native_search deepseek
```

Other model providers retain their existing native-search behavior. Use
`native_search=off` on a model slot to use the independent search tool instead.

### 5. ChatGPT / Codex OAuth

Select **OpenAI Codex (ChatGPT account)** in Global Settings, click the ChatGPT / Codex login button, open the authorization page and enter the displayed device code. After authorization, save the coordinator and/or follower model configuration. Both slots share the Cloudra account login.

The same flow is available from the CLI:

```bash
cloudra auth codex login
cloudra config set coordinator.provider openai-codex
cloudra config set coordinator.model gpt-6-sol
cloudra config set follower.provider openai-codex
cloudra config set follower.model gpt-6-sol
cloudra auth codex status
# Sign out of the Cloudra account session:
cloudra auth codex logout
```

The provider accepts the aliases `codex` and `openai_codex`. Model access depends on your ChatGPT account. Device authorization may need to be enabled in your ChatGPT account or workspace security settings; see [OpenAI authentication guidance](https://developers.openai.com/codex/auth/).

Cloudra stores its independent OAuth session in `.codex_oauth.json` under its configured data directory, with owner-only permissions. It refreshes expiring access tokens and saves rotated refresh tokens under a process lock. Status queries are read-only. Login credentials are never returned to the Web UI or saved as model API keys.

Codex requests use the dedicated `https://chatgpt.com/backend-api/codex/responses` endpoint with `store=false`. Agent, compaction and auxiliary calls share this transport. The endpoint requires streaming; Cloudra also assembles a normal response for callers using `stream=false`. Generic sampling parameters (`temperature`, `top_p`) and output-token limits are omitted on this route.

---

## Current Benchmark and Reference Evidence

The formal bank contains **50 tasks: 20 easy, 10 normal, 10 hard and 10 impossible (IMP)**. Its versioned definitions are in `ideapool/tasks/{easy,normal,hard,impossible}/`; generated JSON and their registry sources are maintained together.

- [Run the current 50-task benchmark](cloudra/benchmark/README.md): the Web Benchmark panel or the CLI with all four task directories and `--backend runtime_v2`. The default CLI is a no-op run of the easy tier, not a real 50-task evaluation.
- [Download the curated evidence from Google Drive](https://drive.google.com/file/d/15YDa_ycWoLUANPsDdQ1rUOiNp_-wqOs5/view?usp=drivesdk) · [Version and checksum](gold_compute/evidence/DELIVERY.md) · [Reproduction instructions](gold_compute/evidence/REPRODUCE.md).
- [Download the P1b four-arm experiment data](https://drive.google.com/file/d/1EFYWbJFuDSSgHv12yGF0ntHIxoIaSwSU/view?usp=drivesdk) · [Rescoring results and scripts](https://drive.google.com/file/d/12JdoiLjiUpSlpRPu0P9Sl2nor6XLv16N/view?usp=drivesdk) · [Packages, checksums and extraction](docs/benchmarks/P1B_DELIVERY.md): 48 pilot runs, separate from the Gold reference evidence. Access requires file permission.
- [P1b Standard offline reconstruction and reassessment, 2026-10-25](docs/benchmarks/p1b_offline_20261025/README.md): reconstructing the missing HA1/r2 graph from its own run records yields 0.805 and a Standard mean of 0.6848833. Full IRC connectivity remains unverified; the earlier four-arm scores are retained as historical snapshots.
- The repository holds task definitions, evidence indexes and instructions. Original calculation inputs/logs, geometries and Hessians are distributed through Drive. The Gold release contains 886 curated evidence files and the formal 50-task snapshot; trial archives and runtime caches are excluded.
- [Current reference status and limitations](gold_compute/queue_20261018/REFERENCE_STATUS.md): missing originals and manual acceptance exceptions are explicit. A loadable/scorable task bank is not a claim that all 50 tasks have complete independent native-evidence reproduction.

The score remains `0.1 × graph + 0.3 × self-consistency + 0.6 × accuracy`. Reaction barriers use the agreed stable reactant/intermediate energy reference; actual IRC connectivity is documented separately. For IMP targets, an attempted calculation followed by a correct final rejection is not penalized; a final false claim of accessibility or a trusted numerical result is penalized.

---

## Evidence-Based Reaction Mechanism Research

### From a Proposed Mechanism to Computational Evidence

A mechanistic study can involve **atom mapping → conformational sampling → evidence-backed TS seed preparation → saddle-point optimization → frequency and imaginary-mode inspection → bidirectional IRC → endpoint optimization and identity checks → energy or thermochemical analysis**, as required by the study. A generated seed or a completed tool call does not establish a transition state.

Two recurring failure modes motivate explicit evidence handling:

1. **Unverified structures and numbers**: plausible coordinates, frequencies or energies may be reported without an identifiable computational source.
2. **Unsupported completion claims**: a summary can omit a failed IRC, an incorrect endpoint or an unverified stationary point. Claims need durable links to the native outputs that support them.

### Chemistry Tools and Delivery DAG Contracts

Cloudra addresses these challenges through two interlocking pillars:

```
                    ┌─────────────────────────────────────────┐
                    │       Coordinator / Specialist Agents   │
                    └────────────────────┬────────────────────┘
                                         │  Propose Mechanism / Bind Evidence
                                         ▼
┌─────────────────────────┐      ┌─────────────────────────┐      ┌─────────────────────────┐
│  Perception Layer       │ ───► │  Delivery Evidence DAG  │ ◄─── │  Scientific Supervisor  │
│  · Geometry provenance  │      │  · Immutable Artifacts  │      │  · Durable Review Inbox │
│  · Reaction Mapping     │      │  · Ordered Stage Locks  │      │  · Claim Adjudication   │
│  · CREST / xTB Ensemble │      │  · Deterministic Audit  │      │  · Read-only Graph Audit│
│  · Mayer / IBO Analysis │      └─────────────────────────┘      └─────────────────────────┘
└─────────────────────────┘
```

#### 1. Geometric & Electronic Perception Layer
Structured tools prepare and inspect geometries, while native calculation records provide energies and frequencies:
- **Geometry provenance (`coord_guard`)**: the coordinate guard checks hand-crafted coordinate writes; format conversion, structure builders and QM relaxation provide traceable geometry sources.
- **Reaction Atom Mapping**: Tracks atom conservation, breaking/forming bonds, and reacting center pairs across 3D conformations.
- **Orientation & Conformer Sampling**: Employs CREST and xTB dynamic relaxation within constrained distance envelopes to determine bimolecular approach pathways rather than guessing orientations.
- **Electronic Structure Analysis**: Provides atomic charges, Mayer bond orders (capturing partially formed transition-state bonds), IBO Lewis representations, and open-shell spin contamination checks ($\langle S^2 \rangle$).
- **Reaction Pathway Tooling**: TS preparation and refinement, relaxed potential-energy scans, IRC endpoint provenance, and native-output parsers for energies, frequencies and convergence. The appropriate seed and search route depend on the chemistry; endpoint interpolation is not a required workflow step.

#### 2. Delivery-Only Evidence DAG Harness
Mechanistic completion is determined strictly by the state of an immutable, context-independent **Delivery DAG**:
- **Graph Elements as Evidence Debt**: Nodes represent the appearance of intermediate species along a reaction coordinate (acyclic structure is preserved by assigning entry and return states of catalysts to distinct nodes sharing canonical species metadata). Edges represent elementary reaction steps. Each element carries a stage contract.
- **Stage Evidence Dependencies**: each element owes the stages in its active contract. Default mechanism drafts and newly added steps require `ts_opt` + `frequency` + `short_irc`; `ts_guess` is advisory and never substitutes for a verified saddle. Direction proof accepts native optimizations from both real IRC outer frames of the same TS to the correct zero-imaginary-frequency minima; the IRC itself need not converge to those minima. Geometry-interval checks are advisory when this endpoint provenance is established. Thermochemistry and other stages follow the declared contract.
- **Deterministic Coverage Audit**: Graph elements accept only typed references to immutable calculation artifacts and job records. Study delivery is evaluated by deterministic algorithms; any unfulfilled or rejected stage remains an open gap blocking completion.

#### 3. Validation and Scientific Scope
Regression tests exercise runtime recovery, evidence binding, native-output parsing and benchmark scoring. Curated native-log replay checks selected reference values. These checks are distinct from a new real Agent run or a complete scientific validation of every benchmark task; the evidence index records the remaining gaps.

---

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

### Tool documentation loading

JavaScript agents retain a short directory of every permitted tool. Before the first real task in a new context, one temporary selection request chooses which complete contracts to preload. The default reuses the agent's effective model and credentials; it creates no additional agent. Read another current contract with `const r = await tools.get_tool_docs({names: ['log_parser']}); text(r.data.documents);`. Loading documentation does not grant permissions or limit calls to the initially selected tools. Traditional agents keep their full wire schemas.

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
gold_compute/                    Gold status, evidence indexes, Drive delivery/reproduction guides and archives
kg_data/, vector_store/          Knowledge graph inputs and vector metadata
知识卡片/                       Knowledge-card source archive
```

See the [documentation hub](docs/README.md), [script index](scripts/README.md) and [literature index](paper/literature/README.md) for details. Root configuration, license/citation files, `install.sh` and `web.sh` remain in place; temporary runtime and build outputs are ignored. Application deliverables and presentation workspaces are no longer tracked; earlier copies remain in Git history.

---

## Development & Testing

Run syntax and lint checks, then the tests for the changed modules. The complete suite runs in CI; do not run it routinely for a local change.

```bash
uv run python -m compileall -q cloudra tests
uv run ruff check cloudra tests
uv run pytest -q tests/test_dag_engine.py        # Example: DAG engine changes
uv run pytest -q tests/test_runtime_v2_replay_equivalence.py  # Example: recovery changes
```

Benchmark verification and native-evidence replay are described in the [benchmark guide](cloudra/benchmark/README.md). Native evidence must first be restored from the [Drive release](gold_compute/evidence/DELIVERY.md) for log replay; ordinary source/unit checks do not require an automatic cloud download.

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
