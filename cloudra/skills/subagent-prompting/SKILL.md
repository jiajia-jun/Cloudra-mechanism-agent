---
name: subagent-prompting
description: Best practices, contracts, and templates for dispatching specialized sub-agents in Cloudra runtime_v2 (e.g. explorer, researcher, small_mol, dft, md, writer, experiment, env). Use when composing instructions for subagent_launcher or subagent_swarm, coordinating via agent_hub, isolating concurrent task directories, preventing hallucinations, and enforcing circuit breakers.
---

# Sub-Agent Prompting & Multi-Agent Coordination Guide

This skill establishes operational contracts, prompt engineering templates, and safety guardrails when delegating tasks to sub-agents via `subagent_launcher`, `subagent_swarm`, and the `agent_hub` forum in Cloudra runtime_v2.

---

## 1. Built-in Sub-Agent Roles & Scope Boundaries

Cloudra provides 8 specialized sub-agent roles (registered as `a-1` through `a-8`). When launching a sub-agent, select the role that strictly matches the task domain:

| Role Identifier | Role Name | Domain & Tooling Boundary | Primary Use Cases |
| :--- | :--- | :--- | :--- |
| **a-1** | `explorer` | Read-only file discovery, codebase grepping, workspace mapping | Quick reconnaissance, locating log files, scanning directory trees |
| **a-2** | `writer` | Writing/editing documents, formatting reports, Markdown | Drafting research reports, formatting summaries, organizing SI text |
| **a-3** | `researcher` | Deep literature search (`search` with `source=openalex`/`arxiv`, `read`) | Paper retrieval, DOI extraction, surveying methodology, SI data lookup |
| **a-4** | `small_mol` | Molecular/cluster QM (Gaussian, ORCA): conformers, TS, reaction mechanisms, spectra | Ligand preparation, atom mapping, TS search, IRC verification, barrier calculations |
| **a-5** | `md` | Molecular dynamics setup, OpenMM, GROMACS, trajectory parsing | System solvation, topology generation, equilibration, MM-GBSA |
| **a-6** | `dft` | Periodic first-principles (VASP, CP2K): bulk, surfaces, interfaces, defects | Submitting periodic compute jobs, band structure, adsorption energies |
| **a-7** | `experiment` | Wet-lab protocols, synthetic routes, reagents, reaction safety | Designing experimental procedures, screening reagents, yield optimization |
| **a-8** | `env` | Environment inspection, shell commands, dependency installation | Checking CLI binaries (`xtb`, `crest`, `vina`), setting environment paths |

---

## 2. Dispatch Mechanisms: Launcher, Swarm, & Agent Hub

### 2.1 Single Dispatch (`subagent_launcher`)
Use for linear prerequisites or domain-specific sub-tasks:
- **`is_wait=True` (Synchronous)**: Blocks until the sub-agent completes. Use when the parent agent strictly depends on the sub-agent's return value (e.g. checking whether a toolchain binary exists).
- **`is_wait=False` (Asynchronous)**: Sub-agent runs concurrently in the background. Use for compute-heavy calculations or broad literature surveys. When it finishes, the harness delivers `[Sub-agent finished]` into the parent's mailbox and wakes the parent; `get_subagent_report` remains available for an explicit pull.

### 2.2 Parallel Swarm Dispatch (`subagent_swarm`)
Use when executing homogeneous parallel workloads (e.g. scoring 10 different conformers, screening 20 ligands, or evaluating multiple adsorption sites):
- **Template Parameter `{{item}}`**: Embed `{{item}}` into the prompt template; `subagent_swarm` automatically expands each entry in the items list into an independent sub-agent.
- **Concurrency & Resource Limits**: Swarm caps maximum parallel runs to prevent resource starvation.

### 2.3 Forum Collaboration (`agent_hub`)
Use for asynchronous communication, sharing intermediate discoveries, and collaborative peer reviews:
- **`post`**: Publish findings under a designated `topic` with structured tags.
- **`browse` / `read` / `search`**: Inspect peer agent findings without polluting the current LLM context window with raw conversation histories.
- **Direct Calling**: Passing `to_agent` or calling by role name wakes the recipient agent via internal mailbox delivery.

---

## 3. The S.C.A.R.F. Prompt Engineering Standard

When delegating complex tasks, structure the prompt using the **S.C.A.R.F.** framework:

- **(S) System Role & Scope**: Define task scope and boundaries; the runtime already injects role identity.
  *(e.g., "Locate and validate transition state TS1 from the supplied molecular endpoints; report the evidence and any unresolved gap.")*
- **(C) Context & Established Facts**: Provide verified ground truth (molecular SMILES, working directory, previous calculation energies) so the sub-agent does not re-compute or guess.
  *(e.g., "The reactant complex energy is -450.2134 Hartree. The optimized coordinates are stored at /abs/path/to/reactant.xyz.")*
- **(A) Actionable Atomic Goal**: Define unambiguous, verifiable goals as objectives with acceptance criteria.
  *(e.g., "Locate the TS for step R→P and verify it: exactly one imaginary frequency whose mode matches the target bond rearrangement, and IRC connectivity back to the declared endpoints.")*
- **(R) Restrictions & Workspace Isolation**:
  - **Absolute file paths**: Always specify absolute paths (e.g. `/home/user/project/.cloudra/tasks/<uuid>/output.log`).
  - **Isolated output directory**: Each async task must write to a unique path (`task_<uuid>/`) to prevent dirty writes and race conditions.
  - **Log size guardrails**: Forbid dumping raw logs ($> 500$ lines) into conversation context; require parsing tools (`log_parser`).
- **(F) Format Contract**: Specify exact return schema (Markdown table, JSON, or key metrics).
  *(e.g., "Return: | Conformers | Final Energy (kcal/mol) | Imaginary Freq (cm^-1) |")*

**S.C.A.R.F. defines goals and contracts, not tool whitelists.** Never enumerate the tools a specialist "may use" or prescribe a step-by-step method chain in the assignment — each role's prompt and mandatory skill already define its SOP, and a caller-supplied recipe silently overrides it (e.g. TS searches default to the durable `ts_prepare`/`ts_resume` process; a hand-written scan→OptTS chain demotes it to a manual run). Scope red lines ("do not do X") are for out-of-domain work, not for restricting in-domain tool choice.

---

## 4. Anti-Hallucination & Verification Guardrails

1. **Trust But Verify**: Never accept a sub-agent's self-declaration that "the calculation converged" or "the structure is optimized" without concrete evidence. Require the sub-agent to invoke a parsing/reading tool (`log_parser`, `read`) and include parsed numbers (e.g., SCF energy, RMS force, single imaginary frequency) in its reply.
2. **Atomic Failure Circuit Breaker**:
   - If a tool fails with the same error twice in a row, the sub-agent must immediately abort that tool.
   - The sub-agent must report to the Coordinator with:
     - The exact error stderr / exception.
     - The parameter set attempted.
     - Actionable suggestions for fallback.
3. **No Unbounded Retries**: Maximum automatic retry count for a sub-agent task is 2. If it still fails, escalate to the Coordinator or user.
