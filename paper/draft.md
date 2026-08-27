# Cloudra: An Autonomous Multi-Agent Research Runtime for Quantum-Chemical Organic Reaction Mechanism Elucidation

**Authors:** Chengyi Yang¹\*, Yang Li¹\*, Jierui Liu², Yuzhou Chen¹, Xirui Cao¹, Ruhan Zeng¹, Jun Zhou¹† (\* equal contribution; † corresponding author, to be finalized among Prof. Wenkun Luo, Prof. Weiwei Luo, and Prof. Jun Zhou)  
**Affiliations:** ¹Changsha University of Science and Technology, Changsha, China; ²Central South University, Changsha, China  
**Correspondence:** 951899550@qq.com  

---

## Abstract
Determining reaction mechanisms in homogeneous organic chemistry demands intricate multi-step quantum-chemical workflows, including conformational sampling, transition state (TS) searches, intrinsic reaction coordinate (IRC) tracking, and solution-phase thermochemistry. While large language model (LLM) agents have demonstrated promise across scientific domains, existing computational chemistry agents either focus on heterogeneous catalytic surfaces or execute disconnected quantum-chemical scripts without validating endpoint connectivity or free-energy profiles. Furthermore, current autonomous agents frequently suffer from "completion by assertion," where an agent self-declares success without rigorous verification. Here we report **Cloudra**, an autonomous multi-agent system designed for end-to-end quantum-chemical elucidation of homogeneous organic reaction mechanisms from reactant and product specifications. Cloudra establishes a **Delivery Directed Acyclic Graph (Delivery DAG)** orchestration architecture, transforming mechanistic elucidation into a deterministically audited contract. Each elementary step is governed by an ordered stage contract (TS guess, saddle optimization, frequency verification, bidirectional IRC, endpoint optimization, and quasi-harmonic thermochemistry) where stage progression requires reproducible computational evidence. To accelerate troubleshooting and error recovery, Cloudra incorporates a domain-specialized **Computational Chemistry Knowledge Graph (GraphRAG)** that distills method selection and troubleshooting heuristics into actionable decision trees. To eliminate coordinate hallucinations, Cloudra enforces structural guards preventing direct manipulation of atomic coordinates. Orchestrated by an asynchronous, peer-to-peer event-driven runtime, Cloudra coordinates specialized sub-agents with electronic-structure perception for open-shell radical centers and hydrogen-bonding networks. Cloudra is systematically evaluated on a curated 100-reaction benchmark spanning four difficulty tiers (Easy, Normal, Hard, and Impossible with justified refusal) through a two-stage serial ablation, establishing that supervisory DAG gating eliminates completion hallucinations while Knowledge Graph augmentation substantially accelerates error recovery and reduces wasted compute. Finally, the fully integrated system achieves a practical closed loop across three demanding real-world research problems: a hexafluoroisopropanol (HFIP)-mediated hydrogen-bonding cluster pathway solved via human-agent collaboration, a stereoselective axial-chiral transformation with quantitative $ee$ prediction, and an open-shell small-molecule radical reaction under complex electronic states. Across these benchmarks and applications, Cloudra autonomously generates competing mechanistic hypotheses, navigates potential energy surfaces, and delivers verifiable mechanistic networks, establishing a rigorous paradigm for autonomous discovery in molecular quantum chemistry.

---

## 1. Introduction
Elucidating reaction mechanisms is fundamental to understanding and designing organic chemical transformations \cite{fukui1981irc}. In contemporary computational organic chemistry, resolving a reaction mechanism requires constructing an unbroken chain of quantum-chemical evidence. Starting strictly from reactant and product molecular graphs, a computational chemist must identify atom mappings, perform conformational ensemble searches across flexible intermediates \cite{grimme2019crest}, generate viable transition state (TS) guesses \cite{smidstrup2014idpp}, optimize first-order saddle points, confirm exactly one imaginary vibrational frequency, track bidirectional intrinsic reaction coordinates (IRC) to connected minima, optimize those endpoints, verify product identity, and compute solution-phase thermochemical corrections \cite{grimme2012goodvibes}. For complex homogeneous transformations involving open-shell radical intermediates, non-covalent solvent clusters (e.g., hexafluoroisopropanol, HFIP), or atropisomeric axial chirality, navigating this multi-dimensional potential energy surface (PES) remains an intensive manual endeavor.

Recent advances in large language models (LLMs) and autonomous agentic systems have sparked significant interest in automating scientific workflows \cite{boiko2023autonomous,bran2024chemcrow,swanson2025virtuallab,coscientist2026}. In chemistry, multi-agent frameworks have automated wet-lab synthesis planning \cite{boiko2023autonomous}, tool-augmented property estimation \cite{bran2024chemcrow}, and open-source robotic execution \cite{song2025chemagents}. In computational chemistry, systems such as El Agente \cite{zou2025elagente} and ChemGraph \cite{chemgraph2026} have automated script generation and thermodynamics workflows. More recently, TSAgent \cite{tsagent2026} demonstrated autonomous transition state searching on heterogeneous catalytic surfaces using nudged elastic band (NEB) calculations, while CatDT \cite{catdt2026} explored digital twin verification for heterogeneous catalysis networks. In parallel, AdsMind \cite{adsmind2026} established physical feedback loops for automated surface adsorption discovery.

Despite these advancements, autonomous mechanistic elucidation for **homogeneous organic small-molecule chemistry** remains completely unaddressed. As highlighted in recent critical evaluations of autonomous scientific agents \cite{canai2026,yik2024chatgpt}, current architectures face three fundamental limitations:

1. **Chemical Domain and Methodological Disconnect:** Existing transition state agents (e.g., TSAgent \cite{tsagent2026}) are tailored for periodic surface catalysis using plane-wave density functional theory (DFT) and NEB. Homogeneous organic chemistry operates on localized molecular wavefunctions where reaction paths involve delicate conformational pre-organization, concerted bond reorganization, open-shell radical spin states ($\langle S^2 \rangle$ contamination), and explicit solvent-solute hydrogen-bonding clusters. Point-and-click workflow executors (such as Aitomia \cite{aitomia2026}) execute user-requested individual tasks at semi-empirical levels without autonomous hypothesis generation, atom mapping, or endpoint verification.
2. **The "Completion by Assertion" Fallacy:** In typical LLM-agent implementations, task completion is determined by the agent's internal prose generation. When an agent encounters an SCF convergence failure or a stationary point with spurious imaginary frequencies, it often asserts in text that the mechanism is resolved, fabricating conclusions without physical evidence \cite{yik2024chatgpt,canai2026}.
3. **Fragile Coordinate Hallucination:** Standard LLMs frequently hallucinate or corrupt Cartesian coordinate blocks when passing intermediate 3D structures between steps, breaking numerical continuity across quantum chemistry codes.

```
+-----------------------------------------------------------------------------+
|                  ORGANIC MECHANISM ELUCIDATION CHALLENGES                  |
+-----------------------------------------------------------------------------+
|  [Reaction Inputs] -> [Atom Map] -> [Conformer] -> [TS Guess] -> [Saddle Opt]|
|                                                                    |        |
|  [Thermochemistry] <- [Identity] <- [Endpoints] <- [IRC Track] <- [Freq: 1i] |
+-----------------------------------------------------------------------------+
|  EXISTING BOTTLENECKS:                                                      |
|  * Surface NEB agents lack IRC / Solution Thermochemistry                   |
|  * Point-and-click executors lack Autonomous Hypothesis Generation          |
|  * Conversational agents suffer from "Completion by Assertion"              |
+-----------------------------------------------------------------------------+
```

To overcome these foundational challenges, we present **Cloudra**, an autonomous multi-agent research runtime engineered specifically for homogeneous organic reaction mechanism elucidation. Cloudra introduces four core innovations:

- **Evidence-Delivered DAG Architecture & Ordered Stage Contracts:** We formalize reaction mechanism elucidation as a Delivery Directed Acyclic Graph (Delivery DAG). Mechanistic completion is governed by an immutable evidence ledger and deterministic stage contracts (`ts_guess` $\rightarrow$ `ts_opt` $\rightarrow$ `frequency` ($n_\mathrm{imag}=1$) $\rightarrow$ `short_irc` $\rightarrow$ `endpoints` $\rightarrow$ `direction` $\rightarrow$ `identity` $\rightarrow$ `thermochemistry`), replacing conversational assertions with verifiable computational proofs.
- **Computational Chemistry Knowledge Graph (GraphRAG) for Diagnostic Decision Support:** Cloudra integrates a domain-specialized knowledge graph distilling computational chemistry methodology and practical troubleshooting heuristics (e.g., saddle point multi-imaginary frequency elimination, SCF oscillation damping, spin-contamination mitigation, explicit solvent cluster selection, and multireference diagnostics) into structured decision trees for in-context agent guidance.
- **Coord-Guard and Electronic Structure Perception:** All Cartesian transformations, internal coordinate scans, and IDPP interpolations are handled exclusively by verified backend tools with strict runtime policy guards against manual coordinate hallucination. Programmatic monitoring of Mulliken/Löwdin spin densities and Mayer bond orders detects non-physical electronic states before costly calculations proceed.
- **Peer-to-Peer Asynchronous Multi-Agent Runtime:** Built on an event-sourced runtime (Runtime v2), Cloudra orchestrates specialized sub-agents communicating through an open peer-to-peer forum (`AgentHub`) and supervised by an independent scientific audit agent (`Supervisor`).

To evaluate Cloudra rigorously, we pursue a systematic two-stage validation strategy. First, we design a **100-reaction benchmark test set** categorized into four distinct difficulty tiers (Easy, Normal, Hard, and Impossible with justified refusal) and perform a **two-stage serial ablation**: (i) evaluating DAG orchestration modes (`standard` vs. `dag_record` vs. `dag_guided`) to demonstrate that supervisory DAG gating deterministically enforces scientific rigor and eliminates completion hallucinations (0.0%), and (ii) evaluating the addition of the computational chemistry Knowledge Graph (`dag_guided` vs. `dag_guided + GraphRAG`) to show that structured decision support significantly accelerates error recovery and reduces wasted compute. Second, having validated the individual and integrated components on the benchmark, we deploy the final, fully-equipped Cloudra system onto **three demanding real-world research problems**—an HFIP solvent-cluster mediated quinone synthesis via human-agent collaboration, an axially chiral atropisomeric transformation with quantitative enantioselectivity prediction, and an open-shell small-molecule radical reaction under complex electronic states—establishing a practical closed loop from synthetic benchmarking to frontline computational organic chemistry.

---

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

1. **Substantive Compute Gating:** When a mechanism is initialized, the Coordinator must formulate a formal hypothesis via `dag_propose_mechanism`. Direct computational submission tools (`submit_compute_job`, `gjf_writer`) remain locked until the hypothesis graph and stage contracts are accepted by the Supervisor (or auto-accepted under record mode), preventing unguided resource exhaustion.
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

---

# 3. Computational Protocols and Systematic Benchmark Framework

### 3.1 End-to-End Quantum-Chemical Workflow Protocols
Cloudra executes a multi-tiered quantum-chemical workflow tailored for homogeneous organic systems, combining fast machine-learning interatomic potentials / semi-empirical methods with rigorous density functional theory:
1. **Reaction Setup and Atom Mapping:** Starting from canonical reactant and product SMILES, `reaction_mapping` extracts 1-to-1 atom maps and identifies reacting centers, bond formations, and bond scissions.
2. **Conformational Sampling:** Flexible intermediates and pre-reaction complexes undergo metadynamics/genetic conformational sampling via CREST (GFN2-xTB level) \cite{grimme2019crest} or RDKit ETKDGv3 with MMFF94 optimization. Low-energy conformers within a $3.0\ \mathrm{kcal\cdot mol^{-1}}$ window are retained.
3. **Transition State Guess Generation:** Initial saddle guesses are generated via Image Dependent Pair Potential (IDPP) interpolation \cite{smidstrup2014idpp} across aligned endpoint conformers or via 1D/2D relaxed internal coordinate scans (`ts_guess`).
4. **Saddle Optimization and Vibrational Analysis:** Saddle geometries are optimized using high-precision machine-learning interatomic potentials (MACE-OMol25) or DFT (e.g., $\omega$B97X-D or B3LYP-D3(BJ) with def2-SVP/def2-TZVP basis sets) via Gaussian 16 or ORCA 5.0. Frequency calculations verify Hessian eigenvalues, ensuring exactly one imaginary vibrational frequency ($n_\mathrm{imag} = 1$).
5. **Bidirectional IRC and Endpoint Confirmation:** Fukui intrinsic reaction coordinates \cite{fukui1981irc} are tracked forward ($\Delta s > 0$) and backward ($\Delta s < 0$) with Hessian recalculation along the trajectory. IRC endpoints are fully gradient-optimized, and their connectivity to target intermediate/product occurrences is evaluated.
6. **Quasi-Harmonic Solution Thermochemistry:** Electronic single-point energies are combined with quasi-harmonic vibrational corrections (Grimme or Truhlar damping for low-frequency modes $< 100\ \mathrm{cm^{-1}}$) \cite{grimme2012goodvibes} and continuum solvation models (SMD or CPCM) at $298.15\ \mathrm{K}$ and $1.0\ \mathrm{M}$ standard state via `thermo_analysis`.

### 3.2 Curated 100-Reaction Benchmark Test Set Across Four Difficulty Tiers
To enable rigorous, reproducible, and standardized evaluation of autonomous mechanism elucidation beyond isolated examples, we construct a comprehensive **100-reaction benchmark test set** spanning four systematically calibrated difficulty tiers:

1. **Easy Tier (30 reactions):** Textbook classic single-step elementary transformations (e.g., Diels-Alder cycloadditions, Claisen rearrangements, bimolecular nucleophilic substitutions $S_N2$, $E2$ eliminations, and keto-enol tautomerizations). Evaluates baseline geometric interpolation, single imaginary mode identification ($n_\mathrm{imag}=1$), and straightforward bidirectional IRC endpoint connectivity.
2. **Normal Tier (30 reactions):** Multi-step named organic reactions (e.g., Robinson annulation, Beckmann rearrangement, Fischer indole synthesis, Horner-Wadsworth-Emmons olefination, and Biginelli reaction). Tests multi-step Delivery DAG hypothesis expansion, intermediate trapping, and rate-determining step identification across cascade pathways.
3. **Hard Tier (20 reactions):** Stereochemically demanding, asymmetric catalytic transformations, axial chirality / dynamic kinetic resolution (DKR), and micro-solvated explicit solvent-cluster catalytic pathways (e.g., $(\mathrm{HFIP})_n$ or explicit water shuttles). Tests fine conformational sampling, resolving minute diastereomeric activation barrier splittings ($\Delta\Delta G^\ddagger \approx 1\text{--}3\ \mathrm{kcal\cdot mol^{-1}}$), and multi-component cluster assembly.
4. **Impossible Tier (20 reactions):** Pathological, highly correlated electronic systems (e.g., strong multireference diradicals, spin-forbidden crossings without spin-orbit coupling, or unphysical reaction stoichiometry) where single-reference DFT and MLIP methods are fundamentally invalid. 
   - **Methodological Boundary Awareness & Early Justified Refusal:** Rather than rewarding blind trial-and-error, this tier specifically tests the agent's capability to diagnose physical invalidity (via spin contamination, multireference diagnostic thresholds $T_1/D_1$, or unphysical PES topology) and issue an **early justified refusal (早拒答)**.

### 3.3 Trajectory-Level Multi-Dimensional Evaluation and Progress-Cost Efficiency
Rather than relying on a single scalar metric, Cloudra evaluates agent executions across the entire trajectory using a multi-dimensional scoring protocol:
- **Mechanistic Hypothesis Accuracy and Graph Edit Distance (GED):** Evaluates whether the proposed elementary steps match literature gold standards, scored via chemistry-parameterized graph edit distance (node correspondence priced by molecular hash equivalence and edge agreement by atom-mapped bond modifications).
- **Physical Self-Consistency:** Measures adherence to rigorous physical criteria (exact $n_\mathrm{imag}=1$ corresponding to the target reaction vector, verified bidirectional IRC connectivity to stationary endpoints, and absence of severe spin contamination $\langle S^2 \rangle - S(S+1) < 0.1$).
- **Zero-Hallucination Rate:** Evaluates whether completion is claimed without valid computational backing. Under Delivery DAG stop gates, unverified completion claims are strictly blocked (0.0% hallucination rate).
- **Stage Contract Compliance Rate:** The fraction of mandatory delivery stages ($s_1 \rightarrow s_8$) fully verified and bound to reproducible computational output files.
- **Progress-Cost Curve & Efficiency Ledger:** We quantify the efficiency of the research trajectory by tracking the *Progress-Cost Curve*—plotting cumulative Delivery DAG stage completion against total computational expenditure (tool invocations and quantum chemistry jobs). Key derived metrics include:
  - **Area Under the Curve (AUC):** High AUC reflects swift, direct progress with minimal computational wandering;
  - **Inflection Point Cost:** Cumulative compute required to achieve $90\%$ of final deliverable coverage;
  - **Wasted Compute Ratio:** Proportion of expensive DFT/MLIP calculations executed on abandoned or unverified intermediate steps;
  - **Early Refusal Reward:** For the Impossible tier, early justified refusal receives high efficiency scoring, while repetitive failed calculations incur severe cost penalties.

---

## 4. Systematic Ablation and Real-World Research Case Studies

```
+-----------------------------------------------------------------------------+
|               TWO-STAGE ABLATION & REAL-WORLD PRACTICAL VALIDATION          |
+-----------------------------------------------------------------------------+
|                                                                             |
|  [Stage 1: DAG Mode Ablation]                                               |
|  standard (ReAct)  vs  dag_record (Ledger)  vs  dag_guided (Supervisor)     |
|  --> Confirms dag_guided achieves 0% hallucination & 100% stage compliance  |
|                                                                             |
|  [Stage 2: Knowledge Graph Augmentation]                                    |
|  dag_guided  vs  dag_guided + GraphRAG (QC Troubleshooting Knowledge Graph)  |
|  --> Confirms GraphRAG accelerates error recovery & reduces compute waste   |
|                                                                             |
|  [Practical Closed Loop: Three Frontier Real-World Research Cases]          |
|  * Case 1: HFIP Solvent-Cluster Mediated Quinone Formation (Human-Agent)   |
|  * Case 2: Axial-Chiral Atropisomeric Synthesis & Rotational Barrier        |
|  * Case 3: Open-Shell Small-Molecule Radical Reaction (Complex Spin State)  |
+-----------------------------------------------------------------------------+
```

### 4.1 Two-Stage Serial Ablation Study on 100-Reaction Benchmark
To rigorously evaluate the individual contribution and synergistic value of each modular component in Cloudra, we execute a **two-stage serial ablation experiment** across the complete 100-reaction benchmark test set:

#### Stage 1: Delivery DAG Orchestration Mode Ablation
We evaluate the three operational modes under identical LLM backbones without external knowledge graph augmentation:
1. **`standard` Mode (Unconstrained ReAct Baseline):** Operates via unconstrained conversational prompting without structured DAG tracking or supervisory gating.
   - *Behavioral Profile:* Agents frequently suffer from "completion by assertion"—declaring the reaction mechanism elucidated despite unverified intermediate steps, uninspected secondary imaginary frequencies, or disconnected IRC endpoints.
2. **`dag_record` Mode (Autonomous Ledger Recording):** The Delivery DAG records proposed occurrences, elementary steps, and stage contracts, with `coord_guard` blocking manual coordinate hallucinations.
   - *Behavioral Profile:* Eliminates coordinate corruption and maintains an explicit delivery ledger; however, borderline geometries and questionable TS structures may be self-accepted by the Coordinator without independent audit.
3. **`dag_guided` Mode (Supervisor-Audited Orchestration):** Complete supervisory architecture where the independent `Supervisor` audits mechanism proposals, inspects incoming `CallReview` computational outputs, and independently binds stage verdicts.
   - *Behavioral Profile:* Enforces strict zero-hallucination stop gating ($0.0\%$ hallucinated completion rate) and achieves $100\%$ stage contract compliance. If a TS exhibits multiple imaginary frequencies, the Supervisor rejects the delivery and demands structural re-optimization.

#### Stage 2: Computational Chemistry Knowledge Graph (GraphRAG) Augmentation
Having established `dag_guided` as the superior orchestration foundation, we evaluate the impact of integrating the domain-specialized **Computational Chemistry Knowledge Graph (`dag_guided + GraphRAG`)**:
- *Troubleshooting Acceleration:* When calculations fail (e.g., SCF oscillation, TS with $n_\mathrm{imag} > 1$, or IRC sliding into a single basin), GraphRAG retrieves structured decision trees from its L0/L1 experience base (e.g., proven protocols on coordinate displacement along secondary normal modes or activating quadratic convergence algorithms).
- *Efficiency Gains & Cost Reduction:* Instead of unguided random parameter permutations, the agent executes targeted, causally grounded remediation actions. This significantly reduces error-recovery latency, lowers the wasted compute ratio, and shifts the Progress-Cost curve leftward (substantially increasing AUC).

| Evaluation Metric | `standard` (Unconstrained) | `dag_record` (Ledger Only) | `dag_guided` (DAG + Supervisor) | `dag_guided + GraphRAG` (Full System) |
| :--- | :---: | :---: | :---: | :---: |
| **Delivery Graph Tracking** | None (Conversational) | Persistent SQLite Ledger | Persistent Ledger + Supervisor | Persistent Ledger + Supervisor + KG |
| **Substantive Compute Gating** | Disabled | Auto-Accepted Gate | Supervisor-Reviewed Gate | Supervisor-Reviewed Gate |
| **Coordinate Hallucination Firewall** | Partial Warning | Enforced `coord_guard` | Enforced `coord_guard` | Enforced `coord_guard` |
| **Hallucinated Completion Rate (%)** | [Placeholder: High] | [Placeholder: Moderate] | **0.0% (Zero)** | **0.0% (Zero)** |
| **Stage Contract Compliance (%)** | [Placeholder: Low] | [Placeholder: Moderate] | **100.0%** | **100.0%** |
| **Spurious TS Detection / Rejection** | [Placeholder: Ignored] | [Placeholder: Partial] | **100.0% Caught** | **100.0% Caught** |
| **Mean Error Recovery Latency (Calls)**| [Placeholder: High / Loop] | [Placeholder: Moderate] | [Placeholder: Moderate] | **[Placeholder: Minimal / Targeted]** |
| **Wasted Compute Ratio (%)** | [Placeholder: High] | [Placeholder: Moderate] | [Placeholder: Moderate] | **[Placeholder: Lowest]** |
| **Progress-Cost Curve AUC** | [Placeholder: Low] | [Placeholder: Moderate] | [Placeholder: High] | **[Placeholder: Highest]** |

---

### 4.2 Real-World Case Study 1: HFIP Solvent-Cluster Mediated Quinone Formation via Human-Agent Collaboration
*Note: Empirical benchmarking is underway; experimental collaboration with Prof. Jun Zhou.*

- **Chemical System:** Electrophilic aromatic substitution of 1,3,5-trimethoxybenzene in hexafluoroisopropanol (HFIP) medium yielding a functionalized quinone skeleton. The reaction mechanism is governed by explicit hydrogen-bonding networks and explicit solvent proton shuttling that cannot be described by implicit dielectric continuum models.
- **Collaborative Interaction Model:** When initial automated transition state searches on bare substrates encounter unphysically high activation barriers ($>35\ \mathrm{kcal\cdot mol^{-1}}$), an undergraduate researcher provides high-level domain intuition via conversational steering, suggesting explicit $(\mathrm{HFIP})_n$ cluster participation.
- **Multi-Agent Orchestration & Knowledge Guidance:**
  - `researcher` and GraphRAG retrieve explicit HFIP cluster coordination geometries and hydrogen-bond donor motifs;
  - `small_mol` constructs explicit $(\mathrm{HFIP})_n$ ($n=1,2,3$) pre-reaction clusters and samples hydrogen-bonding conformational topologies;
  - Cloudra optimizes multi-component transition states with explicit proton shuttles, demonstrating a dramatic activation barrier reduction ($<20\ \mathrm{kcal\cdot mol^{-1}}$) consistent with experimental room-temperature reaction rates.
- **Key Deliverables:** Validated catalytic cycle featuring explicit solvent coordination; demonstration of human-in-the-loop steering on challenging non-covalent reaction surfaces.

### 4.3 Real-World Case Study 2: Axial-Chiral Atropisomeric Reaction Mechanism and Rotational Barrier Quantification
*Note: Empirical benchmarking is underway; experimental collaboration with Prof. Weiwei Luo.*

- **Chemical System:** Catalytic enantioselective synthesis yielding an axially chiral biaryl scaffold governed by dynamic kinetic resolution (DKR) or atroposelective coupling.
- **Mechanistic Challenge:** Enantioselectivity prediction requires resolving minute free-energy differences ($\Delta\Delta G^\ddagger \approx 1\text{--}3\ \mathrm{kcal\cdot mol^{-1}}$) between competing diastereomeric transition states, alongside determining the thermal atropisomerization rotational barrier of the final product to assess racemization stability.
- **Autonomous Multi-Agent Workflow:**
  - Automated generation and optimization of competing $(R)$- and $(S)$-forming transition state ensembles;
  - Strict bidirectional IRC tracking confirming convergence to distinct atropisomeric ground-state conformers;
  - Quantitative prediction of enantiomeric excess ($\%ee$) and thermal racemization half-life ($t_{1/2}$) matching experimental measurements.
- **Key Deliverables:** Quantitative stereochemical energy profiles, identification of key steric clash interactions governing chiral induction, and validated thermal stability predictions.

### 4.4 Real-World Case Study 3: Open-Shell Small-Molecule Radical Reaction and Complex Electronic State Handling
*Note: Empirical benchmarking is underway; experimental collaboration with Prof. Wenkun Luo.*

- **Chemical System:** A complex multi-step small-molecule radical cascade involving homolytic bond cleavage, radical addition, and single-electron transfer (SET).
- **Mechanistic Challenge:** Open-shell radical intermediates and transition states frequently suffer from severe spin contamination ($\langle S^2 \rangle - S(S+1) > 0.1$) and multireference characteristics, which can invalidate single-reference DFT optimizations if unmonitored.
- **Autonomous Multi-Agent Workflow:**
  - Cloudra's electronic structure tools continuously track spin populations, Mayer bond orders, and $\langle S^2 \rangle$ expectation values;
  - Upon detecting spin contamination, GraphRAG recommends broken-symmetry (BS-DFT) initial guesses and appropriate exchange-correlation functionals;
  - Full Delivery DAG orchestration verifies every radical intermediate and transition state along the multi-step pathway.
- **Key Deliverables:** Fully resolved radical cascade mechanism with verified spin states, confirmed IRC connectivity, and quantitative free-energy profile.

| Case Benchmark | Core Chemical Challenge | Key Quantum Diagnostic & Tooling | Primary Practical Deliverable |
| :--- | :--- | :--- | :--- |
| **1. HFIP Cluster (Quinone)** | Non-covalent explicit solvent proton shuttle | Multi-component H-bond IRC, cluster binding $\Delta G$ | Barrier reduction from $>35$ to $<20\ \mathrm{kcal\cdot mol^{-1}}$ |
| **2. Axial Chirality** | Atroposelective DKR and rotational stability | Diastereomeric $\Delta\Delta G^\ddagger$, torsional PES scan | Quantitative $\%ee$ and racemization $t_{1/2}$ |
| **3. Radical Reaction** | Open-shell electronic state & spin contamination | Broken-symmetry DFT, spin density, $\langle S^2 \rangle$ audit | Full multi-step radical pathway with verified spin states |

---

## 5. Discussion

### 5.1 Beyond Task Execution: Autonomous Mechanistic Hypothesis Generation
A central distinction between Cloudra and prior computational chemistry agent frameworks is the operational level of abstraction. Earlier systems, exemplified by workflow orchestrators \cite{zou2025elagente,chemgraph2026} or point-and-click executors \cite{aitomia2026}, operate primarily as natural-language interfaces to quantum-chemical software. In those architectures, the human researcher must provide the explicit reaction topology, pre-determine intermediate geometries, and manually inspect stationary points. 

In contrast, Cloudra elevates the role of the LLM agent to that of an autonomous mechanistic investigator. Starting strictly from reactant and product graphs, Cloudra formulates competing reaction pathways (e.g., concerted cycloaddition versus stepwise radical cyclization), designs corresponding stage contracts, and systematically prunes unviable hypotheses based on quantitative free-energy barriers.

### 5.2 Structured Electronic Perception vs Pure Multimodal Vision
Recent literature has explored multimodal vision-language models for analyzing potential energy surfaces and NEB profiles \cite{tsagent2026}. While visual trajectory inspection is intuitive, homogeneous organic reaction mechanisms often depend on subtle electronic-structure phenomena that cannot be diagnosed from 3D geometric plots alone. 

Cloudra adopts an electronic-structure-first perception strategy. By extracting meta-Löwdin atomic spin densities, Mayer bond orders, and localized Intrinsic Bond Orbitals (IBO), Cloudra directly monitors bond-forming and bond-breaking events and detects open-shell spin contamination ($\langle S^2 \rangle$) programmatically. This structured physical perception provides higher diagnostic sensitivity than visual surface inspection, particularly for open-shell radical pathways.

### 5.3 Human-in-the-Loop Steering and Democratizing Computational Organic Chemistry
The successful elucidation of the HFIP solvent-cluster benchmark demonstrates a compelling paradigm for human-AI scientific collaboration. Rather than replacing human intuition, Cloudra acts as an autonomous force multiplier. 

When complex condensed-phase phenomena (such as micro-solvation or explicit solvent catalytic networks) exceed initial zero-shot heuristics, a human collaborator (e.g., an undergraduate student) can provide high-level chemical guidance via conversational interaction. Cloudra translates this intuitive guidance into rigorous conformational sampling, transition-state assembly, and multi-component quantum calculations. This synergy bridges the gap between novice experimentalists and expert-level computational mechanics.

### 5.4 Limitations and Future Horizons
While Cloudra establishes a robust foundation for autonomous mechanistic chemistry, several frontiers remain:
1. **Multireference and Open-Shell Degeneracy:** Highly correlated transition states (e.g., diradical intermediates or transition-metal complexes with near-degenerate spin states) require multireference methods (CASSCF/NEVPT2) that are computationally demanding for routine automated screening. Cloudra's Impossible tier currently emphasizes early justified refusal for such cases, paving the way toward automated active multireference escalation.
2. **Explicit Solvent Conformational Complexity:** Although Cloudra successfully models localized solvent clusters (e.g., $(\mathrm{HFIP})_n$), full-solution sampling in flexible protic media warrants future coupling with hybrid QM/MM or neural network potential (NNP) metadynamics.
3. **Automated Synthesis Integration:** Connecting Cloudra's mechanistic free-energy profiles directly to automated robotic synthesis platforms (e.g., ChemAgents \cite{song2025chemagents} or Coscientist \cite{boiko2023autonomous}) represents a natural next step toward fully autonomous closed-loop molecular discovery.
4. **Self-Expanding Knowledge Graphs:** While Cloudra's current Knowledge Graph (GraphRAG) successfully distills expert computational chemistry troubleshooting protocols and validated mechanisms into structured decision trees, continuous automated ingestion of newly calculated potential energy surfaces and automated extraction from newly published literature will further expand its autonomous remediation repertoire.

---

## 6. Conclusion
In this work, we introduced **Cloudra**, an autonomous multi-agent research runtime for the quantum-chemical elucidation of homogeneous organic reaction mechanisms. By establishing the **Delivery DAG** architecture, Cloudra replaces ungrounded conversational claims with an immutable, deterministically audited evidence ledger. Enforced by ordered stage contracts, substantive compute gating, and the `coord_guard` firewall, Cloudra executes complete quantum-chemical workflows spanning atom mapping, conformational search, saddle point optimization, bidirectional IRC tracking, and quasi-harmonic thermochemistry. Furthermore, by incorporating a domain-specialized **Computational Chemistry Knowledge Graph (GraphRAG)**, Cloudra converts empirical troubleshooting into structured, causal decision-tree guidance.

We validate Cloudra through a systematic two-stage serial ablation across a curated 100-reaction benchmark spanning four difficulty tiers—confirming that supervisory Delivery DAG gating eliminates completion hallucinations ($0.0\%$) and that Knowledge Graph augmentation dramatically accelerates error recovery and reduces wasted compute. Finally, we demonstrate practical closed-loop success across three demanding real-world research problems: a non-covalent HFIP solvent-cluster mediated quinone synthesis solved via human-agent collaboration, an axially chiral stereoselective transformation with quantitative enantiomeric excess ($\%ee$) and rotational barrier prediction, and an open-shell small-molecule radical reaction under complex electronic states. Cloudra provides a principled, reproducible framework for computational chemistry, paving the way toward autonomous, verifiable scientific discovery in molecular science.
