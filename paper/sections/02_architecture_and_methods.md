## 2. System Architecture and Methodology

Cloudra is organized as an anarchic peer collective rather than a hierarchical agent tree: all agents share equal standing and differ only in their division of labor. Three pillars uphold this design: (1) **AgentHub**, the peer-to-peer collaboration fabric that directly connects every agent and acts as the glue of the system---its post/topic structure is designed to evolve into a shared knowledge graph; (2) an event-sourced research runtime (Runtime v2) beneath the collective; and (3) a Delivery Directed Acyclic Graph (Delivery DAG) evidence engine with deterministic gating, watched over by an independent Supervisor that serves as the gatekeeper of delivery---a second, scientific guard beyond deterministic evidence.

```
+------------------------------------------------------------------------------------+
|                                 CLOUDRA ARCHITECTURE                                |
+------------------------------------------------------------------------------------+
|  ANARCHIC PEER COLLECTIVE (equal standing; different division of labor)             |
|                                                                                     |
|    [Coordinator]  [small_mol]  [researcher]  [explorer]  [dft/md]  [writer]         |
|          \            |             |            |           |         /            |
|           +-----------v-------------v------------v-----------v--------+             |
|           |                     AgentHub                              |             |
|           |  peer-to-peer forum connecting all agents directly;       |             |
|           |  glue of the system; future knowledge-graph carrier       |             |
|           +-----------------------------------------------------------+             |
|                                                                                     |
|  [Supervisor]  independent of all agents; gatekeeper of the Delivery DAG            |
|       |        (second guard: mechanism acceptance, CallReview, stage verdicts)     |
|       v                                                                             |
|  +--------------------------------------------------------------------------------+ |
|  |  DELIVERY DAG EVIDENCE ENGINE (deterministic first guard)                      | |
|  |  immutable evidence ledger; ordered stage contracts s1 -> s8;                  | |
|  |  substantive compute gate; coverage audit                                      | |
|  +------|-------------------------------------------------------------------------+ |
|         v                                                                          |
|  [EVENT-SOURCED RUNTIME v2: event log / command bus / mailbox / reminders]         |
|         v                                                                          |
|  [EXECUTION PLANE: Gaussian / ORCA / PySCF / CREST / xTB / GoodVibes / RDKit/ASE]  |
+------------------------------------------------------------------------------------+
|  Agent behavior norms (coord_guard, command grading, approvals) constrain           |
|  individual agent actions; they are not an architectural tier.                      |
+------------------------------------------------------------------------------------+
```

### 2.1 Event-Driven Runtime (Runtime v2) and Agent Roles
Unlike conventional synchronous conversational loops, Cloudra operates on an asynchronous event-driven core (`Runtime v2`). State transitions, tool invocations, and agent dialogues are logged as immutable events within an event log. This design ensures that every computational conclusion is fully reproducible and replayable across interrupted execution runs.

Cloudra organizes research workflows through specialized agent roles rather than a single monolithic LLM prompt:
- **Coordinator:** The mechanism architect role---a peer among equals, not a superior of other agents. It decomposes overall objectives, proposes reaction networks, designs stage contracts, and synthesizes intermediate findings; coordination itself emerges through `AgentHub` rather than through command.
- **small_mol (Quantum Chemist):** Specializes in molecular quantum mechanics, orchestrating conformer generation, coordinate scans, transition state optimizations, vibrational analyses, and electronic structure diagnostics.
- **researcher (Literature Specialist):** Queries bibliographic databases (OpenAlex, arXiv) to extract reported reaction conditions, analogous mechanisms, and kinetic parameters.
- **explorer (Code & Workspace Auditor):** Performs read-only inspection of trajectory logs, output files, and data structures.
- **Supervisor (Scientific Auditor):** A dedicated evaluation agent operating under `dag_guided` mode. The Supervisor independently audits proposed mechanism drafts, reviews incoming computational evidence from `CallReview` queues, and enforces adherence to peer-review quantum-chemical standards.

### 2.2 Peer-to-Peer Collaboration via AgentHub
To avoid communication bottlenecks inherent in strictly centralized hierarchical agent trees, Cloudra features **AgentHub**, an open peer-to-peer forum that functions as the glue of the system. Every agent---including the Coordinator---communicates through AgentHub directly: parallel sub-agents broadcast reusable computational findings (such as discovered low-energy conformers, optimized basis set parameters, or spin-contamination warnings), pose cross-domain queries, and conduct direct peer calls. Because all shared knowledge is posted as addressable, threaded artifacts, AgentHub's post/topic structure is designed to evolve into a shared knowledge graph over mechanisms and computed precedents.

When a specialized agent identifies an electronic structure anomaly (e.g., severe spin contamination $\langle S^2 \rangle > 0.85$ on a nominally doublet intermediate), it posts a finding to AgentHub, enabling parallel workers to immediately adapt their functional or basis set configurations without waiting for global round-trip orchestration.

### 2.3 Delivery DAG Formalism and Ordered Stage Contracts
The defining formal mechanism in Cloudra is the **Delivery Directed Acyclic Graph (Delivery DAG)**. In Cloudra, a proposed reaction mechanism is represented as a typed directed graph $\mathcal{G} = (\mathcal{V}, \mathcal{E})$:
- **Occurrence Nodes ($v \in \mathcal{V}$):** Represent distinct chemical species (reactants, intermediates, products, and non-covalent solvent complexes) assigned with canonical SMILES representations and formal roles.
- **Elementary Step Edges ($e \in \mathcal{E}$):** Represent elementary chemical transformations connecting source and target species nodes.

Crucially, Cloudra eliminates "completion by assertion" by binding every graph element to an immutable **Stage Contract**. An elementary step edge $e_{ij}$ is required to pass through a strictly ordered sequence of physical verification stages:

$$\text{Stage Sequence: } s_1 \rightarrow s_2 \rightarrow s_3 \rightarrow s_4 \rightarrow s_5 \rightarrow s_6 \rightarrow s_7 \rightarrow s_8$$

Where:
1. $s_1 = \texttt{ts\_guess}$: Preliminary transition state geometric hypothesis generated via IDPP interpolation or relaxed coordinate scan (advisory).
2. $s_2 = \texttt{ts\_opt}$: First-order saddle point optimization convergence under quantum-chemical electronic structure methods (e.g., DFT).
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
|  [ts_opt]        (DFT Saddle Point Optimization: Grad Conv = OK)            |
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

1. **Substantive Compute Gating:** When a mechanism is initialized, the Coordinator must formulate a formal hypothesis via `dag_propose_mechanism`. Direct computational submission tools (`submit_compute_job`, `gjf_writer`) remain locked until the hypothesis graph and stage contracts are accepted by the Supervisor (or auto-accepted under record mode), preventing unguided resource exhaustion.
2. **coord_guard (Coordinate Hallucination Firewall):** LLMs exhibit notorious difficulty in outputting accurate floating-point Cartesian atomic matrices. Attempting to write hand-crafted coordinate matrices directly into `.gjf` or `.xyz` files triggers runtime policy warnings. All 3D structural operations must originate from verified structural generation tools (`smiles_to_mol`, `conformer_search`, `internal_coordinates`, `ts_guess`).
3. **Electronic Structure Perception:** Open-shell and radical systems require vigilant monitoring of non-physical spin states. Cloudra provides native electronic analysis tools extracting Mulliken and meta-Löwdin atomic spin populations, Mayer bond orders, and localized Intrinsic Bond Orbitals (IBO), flagging spin contamination ($\langle S^2 \rangle - S(S+1) > 0.1$) before costly transition state searches proceed.

To rigorously benchmark the impact of these safeguards, Cloudra natively supports three operational modes:
- **`standard` Mode:** Classical ReAct conversational loop without Delivery DAG tracking or Supervisor auditing.
- **`dag_record` Mode:** The Delivery DAG tracks species, steps, and stage contracts; evidence is bound directly by the Coordinator without an active Supervisor agent.
- **`dag_guided` Mode:** Complete supervisory architecture where the Supervisor audits mechanism proposals, inspects incoming `CallReview` outputs, and independently binds stage verdicts.
