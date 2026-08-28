# 2. System Architecture and Methodology

Cloudra is organized as an anarchic peer collective rather than a hierarchical agent tree: all agents share equal standing and differ only in their division of labor. Four core pillars uphold this design:
1. **`AgentHub`:** The peer-to-peer collaboration fabric connecting all agents directly;
2. **Event-Sourced Runtime v2:** Underpinning the collective with immutable event sourcing, command buses, and asynchronous task resumption;
3. **Delivery DAG Evidence Engine:** Enforcing ordered stage contracts $s_1 \rightarrow s_8$ with deterministic gating, monitored by an independent scientific `Supervisor`;
4. **Computational Chemistry Knowledge Graph (GraphRAG):** Providing structured diagnostic decision trees and cross-task troubleshooting heuristics.

```
+-----------------------------------------------------------------------------+
|                     CLOUDRA PEER-COLLECTIVE ARCHITECTURE                    |
+-----------------------------------------------------------------------------+
|                                                                             |
|      [Coordinator] <-----> [AgentHub Forum] <-----> [small_mol (QC)]        |
|      (Architect)                    |               (Quantum Chemist)       |
|                                     |                                       |
|      [researcher]  <--------->      |      <---------> [dft / md]           |
|      (Literature)                   |               (Specialist Compute)    |
|                                     |                                       |
|      [explorer]    <--------->      |      <---------> [writer]             |
|      (Auditor)                      |               (Reporting)             |
|                                     v                                       |
|                      +-----------------------------+                        |
|                      |  Knowledge Graph (GraphRAG) |                        |
|                      |  (Methodology & Diagnostics)|                        |
|                      +-----------------------------+                        |
|                                     |                                       |
|      [Supervisor] ------------------+ (Scientific Gatekeeper / Auditor)     |
|                                     |                                       |
|                                     v                                       |
|  +-----------------------------------------------------------------------+  |
|  |  Delivery DAG Engine: Ordered Stage Contracts (s1 -> s8), Gate, Proof |  |
|  +-----------------------------------------------------------------------+  |
|  |  Event-Sourced Runtime v2: Immutable Log, Mailbox, Reminders, State    |  |
|  +-----------------------------------------------------------------------+  |
|  |  Execution Plane: Gaussian 16, ORCA 5.0, CREST/xTB, MACE-OMol25, ASE   |  |
|  +-----------------------------------------------------------------------+  |
+-----------------------------------------------------------------------------+
```

### 2.1 Event-Driven Runtime and Agent Roles
Unlike conventional synchronous conversational loops, Cloudra operates on an asynchronous event-driven core (`Runtime v2`). State transitions, tool invocations, and agent dialogues are logged as immutable events within an event log. This design ensures that every computational conclusion is fully reproducible and replayable across interrupted execution runs.

Cloudra organizes research workflows through specialized agent roles rather than a single monolithic LLM prompt:
- **Coordinator:** The mechanism architect role---a peer among equals, not a superior of other agents. It decomposes overall objectives, proposes reaction networks, designs stage contracts, and synthesizes intermediate findings; coordination itself emerges through `AgentHub` rather than through centralized command.
- **small_mol (Quantum Chemist):** Specializes in molecular quantum mechanics, orchestrating conformer generation, coordinate scans, transition state optimizations, vibrational analyses, and electronic structure diagnostics.
- **researcher (Literature Specialist):** Queries bibliographic databases (OpenAlex, arXiv) to extract reported reaction conditions, analogous mechanisms, and kinetic parameters.
- **explorer (Code & Workspace Auditor):** Performs read-only inspection of trajectory logs, output files, and data structures.
- **Supervisor (Scientific Auditor):** A dedicated evaluation agent operating under `dag_guided` mode. The Supervisor independently audits proposed mechanism drafts, reviews incoming computational evidence from `CallReview` queues, and enforces adherence to peer-review quantum-chemical standards.

### 2.2 Peer-to-Peer Collaboration via AgentHub
To avoid communication bottlenecks inherent in strictly centralized hierarchical agent trees, Cloudra features **AgentHub**, an open peer-to-peer forum that functions as the glue of the system. Every agent---including the Coordinator---communicates through AgentHub directly: parallel sub-agents broadcast reusable computational findings (such as discovered low-energy conformers, optimized basis set parameters, or spin-contamination warnings), pose cross-domain queries, and conduct direct peer calls. Because all shared knowledge is posted as addressable, threaded artifacts, AgentHub's post/topic structure enables seamless real-time horizontal information exchange.

When a specialized agent identifies an electronic structure anomaly (e.g., severe spin contamination $\langle S^2 \rangle > 0.85$ on a nominally doublet intermediate), it posts a finding to AgentHub, enabling parallel workers to immediately adapt their functional or basis set configurations without waiting for global round-trip orchestration.

### 2.3 Delivery DAG Formalism and Ordered Stage Contracts
The defining formal mechanism in Cloudra is the **Delivery Directed Acyclic Graph (Delivery DAG)**. In Cloudra, a proposed reaction mechanism is represented as a typed directed graph $\mathcal{G} = (\mathcal{V}, \mathcal{E})$:
- **Occurrence Nodes ($v \in \mathcal{V}$):** Represent distinct chemical species (reactants, intermediates, products, and non-covalent solvent complexes) assigned with canonical SMILES representations and formal roles.
- **Elementary Step Edges ($e \in \mathcal{E}$):** Represent elementary chemical transformations connecting source and target species nodes.

Crucially, Cloudra eliminates "completion by assertion" by binding every graph element to an immutable **Stage Contract**. An elementary step edge $e_{ij}$ is required to pass through a strictly ordered sequence of physical verification stages:

$$\text{Stage Sequence: } s_1 \rightarrow s_2 \rightarrow s_3 \rightarrow s_4 \rightarrow s_5 \rightarrow s_6 \rightarrow s_7 \rightarrow s_8$$

Where:
1. $s_1 = \texttt{ts\_guess}$: Preliminary transition state geometric hypothesis generated via IDPP interpolation or relaxed coordinate scan (advisory).
2. $s_2 = \texttt{ts\_opt}$: First-order saddle point optimization convergence under quantum-chemical electronic structure methods (e.g., DFT / MLIP).
3. $s_3 = \texttt{frequency}$: Harmonic vibrational analysis verifying exactly one imaginary vibrational frequency ($n_\mathrm{imag} = 1$) corresponding to the target reaction vector.
4. $s_4 = \texttt{short\_irc}$: Initial bidirectional steepest-descent displacement along the transition vector ($\Delta s > 0$ and $\Delta s < 0$) confirming exit from the saddle region.
5. $s_5 = \texttt{endpoint\_a}$: Full gradient relaxation of the forward trajectory to a stationary intermediate, confirming connectivity to target species $v_j$.
6. $s_6 = \texttt{endpoint\_b}$: Full gradient relaxation of the backward trajectory, confirming connectivity to source species $v_i$.
7. $s_7 = \texttt{direction}$: Verification of geometric and reaction coordinate orientation consistency between endpoints and the transition state.
8. $s_8 = \texttt{thermochemistry}$: Quasi-harmonic free energy evaluation (including solvent corrections and low-frequency entropy damping) at standard state.

A stage $s_k$ cannot be bound until all antecedent required stages $s_{1 \dots k-1}$ are either fully supported by parsed computational artifacts or explicitly waived with scientific justification.

```
+-----------------------------------------------------------------------------+
|                     ORDERED STAGE CONTRACT STATE MACHINE                    |
+-----------------------------------------------------------------------------+
|  [ts_guess]      (Advisory TS Guess from IDPP / Relaxed Scan)               |
|      |                                                                      |
|      v                                                                      |
|  [ts_opt]        (Saddle Point Optimization: Grad Conv = OK)                |
|      |                                                                      |
|      v                                                                      |
|  [frequency]     (Harmonic Hessian: Exact n_imag == 1, Vector Matches)       |
|      |                                                                      |
|      v                                                                      |
|  [short_irc]     (Bidirectional Descent: rx_coord displacement > 0)         |
|      |                                                                      |
|      v                                                                      |
|  [endpoint_a/b]  (Endpoint Optimizations -> Structure Matches Graph Node)   |
|      |                                                                      |
|      v                                                                      |
|  [direction]     (Reaction Coordinate Continuity & Path Direction Proof)    |
|      |                                                                      |
|      v                                                                      |
|  [thermochem]    (Quasi-harmonic Solution Free Energies: dG_act, dG_rxn)    |
+-----------------------------------------------------------------------------+
```

### 2.4 Deterministic Gating, coord_guard, and Three-Mode Ablation
To guarantee that neither LLM hallucinations nor unverified claims bypass scientific verification, Cloudra embeds deterministic runtime policies directly into the tool-execution pipeline:

1. **Substantive Compute Gating:** When a mechanism is initialized, the Coordinator must formulate a formal hypothesis via `dag_propose_mechanism`. Direct computational submission tools (`submit_compute_job`, `qm_input_writer`) remain locked until the hypothesis graph and stage contracts are accepted by the Supervisor (or auto-accepted under record mode), preventing unguided resource exhaustion.
2. **coord_guard (Coordinate Hallucination Firewall):** LLMs exhibit notorious difficulty in outputting accurate floating-point Cartesian atomic matrices. Attempting to write hand-crafted coordinate matrices directly into `.gjf` or `.xyz` files triggers runtime policy warnings. All 3D structural operations must originate from verified structural generation tools (`smiles_to_mol`, `conformer_search`, `internal_coordinates`, `ts_guess`).
3. **Electronic Structure Perception:** Open-shell and radical systems require vigilant monitoring of non-physical spin states. Cloudra provides native electronic analysis tools extracting Mulliken and meta-Löwdin atomic spin populations, Mayer bond orders, and localized Intrinsic Bond Orbitals (IBO), flagging spin contamination ($\langle S^2 \rangle - S(S+1) > 0.1$) before costly transition state searches proceed.

To rigorously benchmark the impact of these safeguards, Cloudra natively supports three operational modes:
- **`standard` Mode:** Classical ReAct conversational loop without Delivery DAG tracking or Supervisor auditing.
- **`dag_record` Mode:** The Delivery DAG tracks species, steps, and stage contracts; evidence is bound directly by the Coordinator without an active Supervisor agent.
- **`dag_guided` Mode:** Complete supervisory architecture where the Supervisor audits mechanism proposals, inspects incoming `CallReview` outputs, and independently binds stage verdicts.

### 2.5 Computational Chemistry Knowledge Graph (GraphRAG) Layer
While pre-trained LLMs possess broad parametric chemistry knowledge, they frequently struggle when encountering domain-specific quantum-chemical execution failures—such as multi-imaginary frequency saddle points, oscillatory SCF non-convergence, disconnected IRC trajectories, severe spin contamination, or implicit solvation breakdowns in strong hydrogen-bonding media.

To empower agents with actionable troubleshooting expertise, Cloudra integrates a domain-specialized **Computational Chemistry Knowledge Graph (GraphRAG)**. Grounded in established computational chemistry methodology and expert troubleshooting protocols (distilled from canonical quantum-chemical guidelines and peer-reviewed literature), the knowledge graph is formulated as an actionable **Decision DAG** rather than a flat textual corpus:
- **Ontological Nodes:** Comprise *Symptom nodes* (e.g., $n_\mathrm{imag} > 1$, SCF energy divergence, IRC single-basin relapse, $\langle S^2 \rangle$ elevation), *Diagnostic Criteria nodes* (e.g., verifying whether secondary imaginary modes $< 50\ \mathrm{cm^{-1}}$ represent methyl rotations, evaluating $T_1 / D_1$ multireference diagnostics), *Mitigation Action nodes* (e.g., displacing along normal coordinates by $0.1\ \mathrm{\AA}$, applying quadratic convergence `scf(xqc)`, twisting dihedral angles to break spurious higher-order saddle symmetries, activating broken-symmetry guess), and *Fallback / Escalation nodes* (e.g., recomputing analytical Hessians with elevated basis sets or triggering justified rejection for multireference breakdown).
- **Relational Edges:** Link symptoms to diagnoses (`DIAGNOSED_BY`), conditional branches (`BRANCHES_IF`), actions (`RESOLVED_BY`), and hierarchical fallbacks (`FALLBACK_TO`).
- **Tiered Evidence Hierarchy:** Knowledge entities are stratified into $L_0$ (methodological guidelines and verified community troubleshooting protocols), $L_1$ (physically converged, IRC-validated calculations from prior tasks), and $L_2$ (provisional theoretical conjectures), with falsified records assigned negative retrieval weights.
- **Decision Tree Walk Retrieval:** When an agent encounters a calculation failure or requests method advice, GraphRAG performs node matching and traverses 1–2 hops along causal edges, injecting an indented, branch-structured decision tree directly into the LLM's context:

```text
[QC Troubleshooting Graph: TS Multi-Imaginary Frequency Mitigation]
Symptom: Transition state optimization converged with n_imag > 1
├─ Step 1: Inspect secondary imaginary mode (freq_2) magnitude & character
│  ├─ Branch A: freq_2 < 50 cm^-1 & corresponds to spectator side-chain / methyl rotation
│  │  └─ Action: Displace geometry 0.1 A along normal mode -> opt(ts,calcfc,noeigentest)
│  └─ Branch B: freq_2 is large and involves core bond-forming/breaking framework
│     ├─ Root Cause: Geometry is trapped at a higher-order symmetric saddle point
│     └─ Action: Manually distort key dihedral angle by 5-10 deg -> restart TS search
└─ Fallback: If 2 attempts fail -> recompute full initial Hessian with tighter grid/basis
```

By decoupling horizontal intra-task communication (`AgentHub`) from vertical cross-task knowledge retrieval (`GraphRAG`), Cloudra provides agents with immediate, structured diagnostic remediation, converting repetitive computational trial-and-error into targeted, physical error recovery.
