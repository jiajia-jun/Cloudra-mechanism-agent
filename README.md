# Cloudra

**Autonomous Agent System for Organic Small-Molecule Mechanism Computation**  
*Geometric & Electronic Perception · DAG Delivery Contracts · Anarchist Peer-to-Peer Agent Architecture*

[![CI](https://github.com/yyywaa/Cloudra-mechanism-agent/actions/workflows/ci.yml/badge.svg)](https://github.com/yyywaa/Cloudra-mechanism-agent/actions/workflows/ci.yml)
[![Python ≥ 3.11](https://img.shields.io/badge/python-%E2%89%A53.11-blue)](pyproject.toml)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](pyproject.toml)

[中文文档](README_CN.md) · [Documentation](docs/README.md) · [DAG Orchestration Spec](docs/DAG_ORCHESTRATION.md)

> Cloudra is an autonomous research agent system for computational organic chemistry. It does not claim to replace human insight with absolute truth, nor does it aim for superficial benchmark numbers. Its purpose is to provide a rigorous, non-hallucinatory, and deterministically auditable foundation for long-horizon mechanistic elucidation.

---

## Quick Start

### 1. Requirements & Installation

Requires Python ≥ 3.11, Node.js ≥ 18, and access to any OpenAI-compatible LLM endpoint.

```bash
# Clone the repository
git clone https://github.com/yyywaa/Cloudra-mechanism-agent.git
cd Cloudra-mechanism-agent

# Run the all-in-one setup script (virtual environment + dependencies)
./install.sh                 # Linux / macOS
# .\install.ps1              # Windows PowerShell

# Initialize default configuration
cloudra config init
```

### 2. Launch the Full-Stack Web Console

Cloudra features a unified, single-port web interface (FastAPI control plane + React/Vite SPA):

```bash
cloudra                      # Builds the frontend and starts the server, opening your browser
cloudra web --skip-build     # Fast restart using pre-built assets
```

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
- **Ordered Stage Locks**: An elementary step must satisfy its stage contract in strict sequential order: `ts_guess` → `ts_opt` → `frequency` (with exactly one imaginary frequency) → `short_irc` → `endpoints` → `direction` → `thermochemistry`. Later stages cannot be bound until preceding requirements are verified.
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
- **Autonomous Schedule Guard**: When schedule mode is enabled, attempts to stop without an active wake-up timer are automatically intercepted by `ScheduleStage`, allowing agents to sleep during long calculations and awaken automatically when jobs conclude.

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

## Quantum Chemistry & HPC Integration

Cloudra seamlessly bridges local exploratory modeling and remote cluster computing:

- **Electronic Structure Engines**: Integrates with Gaussian, ORCA, xTB, CREST, VASP, and CP2K for automated input preparation, local process execution, and Slurm batch submission.
- **Cheminformatics & Property Analysis**: Connects with RDKit, OpenBabel, Multiwfn, and Molli for 3D geometry manipulation, NMR/IR spectral simulation, stoichiometry verification, and high-fidelity CDXML reaction parsing (stereochemistry, connectivity, charge, and multiplicity preserved).
- **Literature & Academic Authoring**: Direct integration with OpenAlex for literature search and automated Markdown/LaTeX report generation with full level-of-theory annotations.

---

## Repository Layout

```text
cloudra/
├── core/                        Agent base types and scientific supervision (Supervisor)
├── services/                    Control plane API service (FastAPI routing)
├── persistence/                 SQLite store, immutable artifacts, long-term memory, paths
├── base/                        Data classes and tool/skill loading contracts
├── infra/                       Cluster node profiles, LLM transports, event bus, platform tools
├── dag/                         Mechanism evidence graph subsystem (Engine, Store, Controller)
├── runtime/                     Deterministic prompt assembly, workspace observer, compute monitoring
├── runtime_v2/                  Event-driven reasoning kernel (Pipeline, Commands, PolicyStages, Bridges)
├── tools/, subagents/           Perception toolboxes and specialized domain roles (dft, md, explorer, etc.)
├── skills/, prompts/            Domain methodology skills and version-controlled role prompts
└── frontend/                    Modern React + TypeScript + Vite web console
```

---

## Development & Testing

Run the full automated test suite and style checks:

```bash
uv run pytest -q tests/            # Run the complete test suite (700+ tests)
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

This project is licensed under the [MIT License](pyproject.toml).
