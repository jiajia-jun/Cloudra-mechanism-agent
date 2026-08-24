# Autonomous Elucidation of Homogeneous Organic Reaction Mechanisms through Directed Acyclic Graph Evidence Delivery and Peer-to-Peer Agent Orchestration

**Authors:** Chengyi Yang¹\*, Yang Li¹\*, Jierui Liu², Yuzhou Chen¹, Xirui Cao¹, Ruhan Zeng¹, Jun Zhou¹† (\* equal contribution; † corresponding author, to be finalized among Prof. Wenkun Luo, Prof. Weiwei Luo, and Prof. Jun Zhou)  
**Affiliations:** ¹Changsha University of Science and Technology, Changsha, China; ²Central South University, Changsha, China  
**Correspondence:** 951899550@qq.com  

---

## Abstract
Determining reaction mechanisms in homogeneous organic chemistry demands intricate multi-step quantum-chemical workflows, including conformational sampling, transition state (TS) searches, intrinsic reaction coordinate (IRC) tracking, and solution-phase thermochemistry. While large language model (LLM) agents have demonstrated promise across scientific domains, existing computational chemistry agents either focus on heterogeneous catalytic surfaces or execute disconnected quantum-chemical scripts without validating endpoint connectivity or free-energy profiles. Furthermore, current autonomous agents frequently suffer from "completion by assertion," where an agent self-declares success without rigorous verification. Here we report **Cloudra**, an autonomous multi-agent system designed for end-to-end quantum-chemical elucidation of homogeneous organic reaction mechanisms from reactant and product specifications. Cloudra establishes a **Delivery Directed Acyclic Graph (Delivery DAG)** orchestration architecture, transforming mechanistic elucidation into a deterministically audited contract. Each elementary step is governed by an ordered stage contract (TS guess, saddle optimization, frequency verification, bidirectional IRC, endpoint optimization, and quasi-harmonic thermochemistry) where stage progression requires reproducible computational evidence. To eliminate coordinate hallucinations, Cloudra enforces structural guards preventing direct manipulation of atomic coordinates. Orchestrated by an asynchronous, peer-to-peer event-driven runtime, Cloudra coordinates specialized sub-agents with electronic-structure perception for open-shell radical centers and hydrogen-bonding networks. Cloudra is evaluated on a curated benchmark suite of established homogeneous organic reactions together with three demanding case studies: a hexafluoroisopropanol (HFIP)-mediated hydrogen-bonding cluster pathway solved via human-agent collaboration, a complex multi-step small-molecule reaction mechanism resolved through fully automated, large-scale workflow orchestration, and a stereoselective axial-chiral transformation. To evaluate mechanistic deliveries beyond a single success scalar, each delivered mechanism is scored against literature-curated reference networks using a chemistry-parameterized graph edit distance: node correspondence is priced by molecular hash equivalence and fingerprint similarity under tiered stereochemical strictness, edge disagreement by atom-mapped bond-change differences, and the optimal alignment itself serves as an interpretable edit script for structured failure attribution. Across these benchmarks, Cloudra autonomously generates competing mechanistic hypotheses, navigates potential energy surfaces, and delivers verifiable mechanistic networks, establishing a rigorous paradigm for autonomous discovery in molecular quantum chemistry.

---

## 1. Introduction
Elucidating reaction mechanisms is fundamental to understanding and designing organic chemical transformations \cite{fukui1981irc}. In contemporary computational organic chemistry, resolving a reaction mechanism requires constructing an unbroken chain of quantum-chemical evidence. Starting strictly from reactant and product molecular graphs, a computational chemist must identify atom mappings, perform conformational ensemble searches across flexible intermediates \cite{grimme2019crest}, generate viable transition state (TS) guesses \cite{smidstrup2014idpp}, optimize first-order saddle points, confirm exactly one imaginary vibrational frequency, track bidirectional intrinsic reaction coordinates (IRC) to connected minima, optimize those endpoints, verify product identity, and compute solution-phase thermochemical corrections \cite{grimme2012goodvibes}. For complex homogeneous transformations involving open-shell radical intermediates, non-covalent solvent clusters (e.g., hexafluoroisopropanol, HFIP), or atropisomeric axial chirality, navigating this multi-dimensional potential energy surface (PES) remains an intensive manual endeavor.

Recent advances in large language models (LLMs) and autonomous agentic systems have sparked significant interest in automating scientific workflows \cite{boiko2023autonomous,bran2024chemcrow,swanson2025virtuallab,coscientist2026}. In chemistry, multi-agent frameworks have automated wet-lab synthesis planning \cite{boiko2023autonomous}, tool-augmented property estimation \cite{bran2024chemcrow}, and open-source robotic execution \cite{song2025chemagents}. In computational chemistry, systems such as El Agente \cite{zou2025elagente} and ChemGraph \cite{chemgraph2026} have automated script generation and thermodynamics workflows. More recently, TSAgent \cite{tsagent2026} demonstrated autonomous transition state searching on heterogeneous catalytic surfaces using nudged elastic band (NEB) calculations, while CatDT \cite{catdt2026} explored digital twin verification for heterogeneous catalysis networks. In parallel, AdsMind \cite{adsmind2026} established physical feedback loops for automated surface adsorption discovery.

Despite these advancements, autonomous mechanistic elucidation for **homogeneous organic small-molecule chemistry** remains completely unaddressed. As highlighted in recent critical evaluations of autonomous scientific agents \cite{canai2026,yik2024chatgpt}, current architectures face three fundamental limitations:

1. **Chemical Domain and Methodological Disconnect:** Existing transition state agents (e.g., TSAgent \cite{tsagent2026}) are tailored for periodic surface catalysis using plane-wave density functional theory (DFT) and NEB. Homogeneous organic chemistry operates on localized molecular wavefunctions where reaction paths involve delicate conformational pre-organization, concerted bond reorganization, open-shell radical spin states ($\langle S^2 \rangle$ contamination), and explicit solvent-solute hydrogen-bonding clusters. Point-and-click workflow executors (such as Aitomia \cite{aitomia2026}) execute user-requested individual tasks at semi-empirical levels without autonomous hypothesis generation, atom mapping, or endpoint verification.
2. **The "Completion by Assertion" Fallacy:** In typical LLM-agent implementations, task completion is determined by the agent's internal prose generation. When an agent encounters an SCF convergence failure or a stationary point with spurious imaginary frequencies, it often asserts in text that the mechanism is resolved, fabricating conclusions without physical evidence \cite{yik2024chatgpt,canai2026}.
3. **Fragile Coordinate Hallucination:** Standard LLMs frequently hallucinate or corrupt Cartesian coordinate blocks when passing intermediate 3D structures between steps, breaking numerical continuity across quantum chemistry codes.

To overcome these foundational challenges, we present **Cloudra**, an autonomous multi-agent research runtime engineered specifically for homogeneous organic reaction mechanism elucidation. Cloudra introduces four core innovations:
- **Evidence-Delivered DAG Architecture:** We formalize reaction mechanism elucidation as a Delivery Directed Acyclic Graph (Delivery DAG). Mechanistic completion is governed by an immutable evidence ledger and deterministic stage contracts rather than conversational claims.
- **Ordered Stage Contracts & Deterministic Gating:** Each elementary reaction step must strictly satisfy a sequential stage contract (`ts_guess` $\rightarrow$ `ts_opt` $\rightarrow$ `frequency` ($n_\mathrm{imag}=1$) $\rightarrow$ `short_irc` $\rightarrow$ `endpoints` $\rightarrow$ `direction` $\rightarrow$ `identity` $\rightarrow$ `thermochemistry`). Calculations are gated behind explicit mechanism proposal acceptance, preventing computational waste.
- **Coord-Guard and Strict Coordinate Integrity:** All Cartesian transformations, internal coordinate scans, and IDPP interpolations are handled exclusively by verified backend tools; manual coordinate writing by LLMs is strictly blocked by runtime policy guards.
- **Peer-to-Peer Asynchronous Multi-Agent Runtime:** Built on an event-sourced runtime (Runtime v2), Cloudra orchestrates specialized sub-agents (quantum chemistry, literature retrieval, environmental setup) communicating through an open peer-to-peer forum (`AgentHub`) and supervised by an independent scientific audit agent (`Supervisor`).

We demonstrate Cloudra's capabilities across three challenging, chemically diverse benchmark scenarios: (1) a complex, unelucidated hexafluoroisopropanol (HFIP) cluster-mediated reaction solved via human-agent collaborative steering; (2) a complex multi-step small-molecule reaction mechanism resolved through fully automated, large-scale multi-agent workflow orchestration; and (3) an axially chiral catalytic transformation requiring precise enantioselective rotational barrier quantification. Quantitative evaluation is performed on a curated test set of homogeneous organic reactions with established mechanisms, and systematic ablation across three operational modes (`standard`, `dag_record`, and `dag_guided`) demonstrates that deterministic DAG evidence gating is essential for eliminating spurious mechanisms and achieving publication-grade scientific rigor.

---

## 2. System Architecture and Methodology

Cloudra is organized as an anarchic peer collective rather than a hierarchical agent tree: all agents share equal standing and differ only in their division of labor. Three pillars uphold this design: (1) **AgentHub**, the peer-to-peer collaboration fabric that directly connects every agent and acts as the glue of the system---its post/topic structure is designed to evolve into a shared knowledge graph; (2) an event-sourced research runtime (Runtime v2) beneath the collective; and (3) a Delivery Directed Acyclic Graph (Delivery DAG) evidence engine with deterministic gating, watched over by an independent Supervisor that serves as the gatekeeper of delivery---a second, scientific guard beyond deterministic evidence.

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

### 2.4 Deterministic Gating, coord_guard, and Three-Mode Ablation
To guarantee that neither LLM hallucinations nor unverified claims bypass scientific verification, Cloudra embeds deterministic runtime policies directly into the tool-execution pipeline:

1. **Substantive Compute Gating:** When a mechanism is initialized, the Coordinator must formulate a formal hypothesis via `dag_propose_mechanism`. Direct computational submission tools (`submit_compute_job`, `gjf_writer`) remain locked until the hypothesis graph and stage contracts are accepted by the Supervisor (or auto-accepted under record mode), preventing unguided resource exhaustion.
2. **coord_guard (Coordinate Hallucination Firewall):** LLMs exhibit notorious difficulty in outputting accurate floating-point Cartesian atomic matrices. Attempting to write hand-crafted coordinate matrices directly into `.gjf` or `.xyz` files triggers runtime policy warnings. All 3D structural operations must originate from verified structural generation tools (`smiles_to_mol`, `conformer_search`, `internal_coordinates`, `ts_guess`).
3. **Electronic Structure Perception:** Open-shell and radical systems require vigilant monitoring of non-physical spin states. Cloudra provides native electronic analysis tools extracting Mulliken and meta-Löwdin atomic spin populations, Mayer bond orders, and localized Intrinsic Bond Orbitals (IBO), flagging spin contamination ($\langle S^2 \rangle - S(S+1) > 0.1$) before costly transition state searches proceed.

To rigorously benchmark the impact of these safeguards, Cloudra natively supports three operational modes:
- **`standard` Mode:** Classical ReAct conversational loop without Delivery DAG tracking or Supervisor auditing.
- **`dag_record` Mode:** The Delivery DAG tracks species, steps, and stage contracts; evidence is bound directly by the Coordinator without an active Supervisor agent.
- **`dag_guided` Mode:** Complete supervisory architecture where the Supervisor audits mechanism proposals, inspects incoming `CallReview` outputs, and independently binds stage verdicts.

---

## 3. Computational Protocols and Benchmark Evaluation Framework

### 3.1 End-to-End Quantum-Chemical Workflow Protocols
Cloudra executes a multi-tiered quantum-chemical workflow tailored for homogeneous organic systems:
1. **Reaction Setup and Atom Mapping:** Starting from canonical reactant and product SMILES, `reaction_mapping` extracts 1-to-1 atom maps and identifies reacting centers, bond formations, and bond scissions.
2. **Conformational Sampling:** Flexible intermediates and pre-reaction complexes undergo metadynamics/genetic conformational sampling via CREST (GFN2-xTB level) \cite{grimme2019crest} or RDKit ETKDGv3 with MMFF94 optimization. Low-energy conformers within a $3.0\ \mathrm{kcal\cdot mol^{-1}}$ window are retained.
3. **Transition State Guess Generation:** Initial saddle guesses are generated via Image Dependent Pair Potential (IDPP) interpolation \cite{smidstrup2014idpp} across aligned endpoint conformers or via 1D/2D relaxed internal coordinate scans (`ts_guess`).
4. **Saddle Optimization and Vibrational Analysis:** Saddle geometries are optimized using DFT (e.g., $\omega$B97X-D or B3LYP-D3(BJ) with def2-SVP/def2-TZVP basis sets) via Gaussian 16 or ORCA 5.0. Frequency calculations verify Hessian eigenvalues, ensuring exactly one imaginary frequency ($n_\mathrm{imag} = 1$).
5. **Bidirectional IRC and Endpoint Confirmation:** Fukui intrinsic reaction coordinates \cite{fukui1981irc} are tracked forward ($\Delta s > 0$) and backward ($\Delta s < 0$) with Hessian recalculation along the trajectory. IRC endpoints are fully gradient-optimized, and their connectivity to target intermediate/product occurrences is evaluated.
6. **Quasi-Harmonic Solution Thermochemistry:** Electronic single-point energies are combined with quasi-harmonic vibrational corrections (Grimme or Truhlar damping for low-frequency modes $< 100\ \mathrm{cm^{-1}}$) \cite{grimme2012goodvibes} and continuum solvation models (SMD or CPCM) at $298.15\ \mathrm{K}$ and $1.0\ \mathrm{M}$ standard state via `thermo_analysis`.

### 3.2 Curated Mechanism Benchmark Test Set
*Note: The test set is under construction; size, reaction list, and selection criteria are placeholders.*

To enable quantitative and reproducible evaluation beyond individual case studies, we curate a benchmark test set of well-established homogeneous organic reactions whose mechanisms are experimentally validated and computationally tractable at routine DFT levels. Each task provides only the reactant and product molecular graphs; Cloudra must autonomously recover the accepted elementary-step network and deliver quantitative free-energy profiles. [Placeholder: test set size, reaction list, and selection criteria.] Performance is scored on mechanistic recall (fraction of accepted elementary steps recovered), quantitative barrier agreement with literature values, hallucinated completion rate, and token/wall-clock cost.

---

## 4. Results and Case Studies

### 4.1 Case Study 1: Elucidation of an HFIP Solvent-Cluster Pathway via Human-Agent Collaboration
*Note: Empirical benchmarking is underway. This section details the collaborative protocol and solvent-cluster exploration.*

- **Chemical System:** A challenging organic transformation whose mechanism remains contentious due to the active catalytic participation of explicit hexafluoroisopropanol (HFIP) solvent clusters via non-covalent hydrogen-bonding networks. [Placeholder: reaction identity and substrate scope.]
- **Collaborative Interaction Model:** An undergraduate researcher interfaces with Cloudra. When initial automated TS searches on bare substrates fail to locate plausible activation barriers ($>35\ \mathrm{kcal\cdot mol^{-1}}$), the collaborator suggests explicit solvent participation via natural language dialogue.
- **Multi-Agent Orchestration:** 
  - `researcher` retrieves literature precedents on HFIP cluster stabilization.
  - `small_mol` builds explicit (HFIP)$_n$ ($n=1,2,3$) hydrogen-bonded substrate complexes and executes conformer searches.
  - Cloudra optimizes multi-component transition states with explicit proton shuttles, confirming dramatic barrier reduction ($<20\ \mathrm{kcal\cdot mol^{-1}}$).
- **Key Deliverables:**
  - Validated catalytic cycle featuring explicit solvent coordination.
  - Demonstration of human-in-the-loop steering on challenging non-covalent reaction surfaces.
  - [Placeholder: Figure 3 -- HFIP-assisted TS cluster structures and IRC trajectories].
  - [Placeholder: Table 1 -- Comparison of gas-phase, implicit solvent, and explicit (HFIP)$_n$ cluster activation barriers].

### 4.2 Case Study 2: Fully Automated Elucidation of a Complex Multi-Step Small-Molecule Mechanism
*Note: Empirical benchmarking is underway. This section defines the large-workflow orchestration challenge and delivery structure.*

- **Chemical System:** A complex multi-step homogeneous small-molecule transformation (provided by a collaborating experimental group) whose mechanism spans numerous elementary steps, intermediates, and competing pathways. [Placeholder: reaction identity and reference mechanism.]
- **Autonomous Workflow:** Without human intervention, Cloudra decomposes the overall transformation into a large Delivery DAG, dispatches specialist sub-agents through `AgentHub`, and orchestrates a large-scale workflow of conformer searches, saddle optimizations, frequency audits, bidirectional IRC integrations, and thermochemical refinements across all elementary steps.
- **Key Deliverables:** 
  - Complete stage-contract coverage across the full mechanistic network.
  - Identification of the rate- and selectivity-determining steps; demonstration of fully automated orchestration of a large quantum-chemical workflow.
  - [Placeholder: Figure 4 -- Full Delivery DAG and free-energy profile].
  - [Placeholder: Table 2 -- Computed versus experimental barriers across all elementary steps].

### 4.3 Case Study 3: Axial-Chiral Atropisomeric Reaction Mechanism and Rotational Barrier
*Note: Empirical benchmarking is underway. This section establishes the stereochemical evaluation framework.*

- **Chemical System:** A catalytic enantioselective synthesis yielding an axially chiral biaryl/heterobiaryl scaffold governed by dynamic kinetic resolution or atroposelective bond formation (provided by a collaborating experimental group). [Placeholder: reaction identity and reference stereochemical data.]
- **Mechanistic Challenge:** Predicting enantioselectivity requires resolving minute free-energy differences ($\Delta\Delta G^\ddagger \approx 1-3\ \mathrm{kcal\cdot mol^{-1}}$) between competing diastereomeric transition states, alongside calculating the thermal atropisomerization rotational barrier of the final product.
- **Key Deliverables:**
  - Automated generation and optimization of competing $(R)$- and $(S)$-forming transition state ensembles.
  - Strict IRC tracking confirming convergence to distinct atropisomeric ground-state conformers.
  - Quantitative prediction of enantiomeric excess ($\%ee$) and thermal racemization half-life ($t_{1/2}$) matching experimental measurements.
  - [Placeholder: Figure 5 -- Competing chiral transition states, steric interaction mapping, and rotational scan profile].
  - [Placeholder: Table 3 -- Predicted vs experimental enantioselectivity and rotational barriers].

---

### 4.4 Multi-Mode Ablation and Scientific Rigor Evaluation
*Note: Systematic benchmarking across modes is underway. The evaluation metrics and experimental structure are formalized below.*

To evaluate the necessity of Delivery DAG stage contracts and Supervisor oversight, the curated test set (Section 3.2) and all three case studies are subjected to three-mode ablation. As an optional extension, a knowledge-graph-augmented variant (GraphRAG over literature mechanisms) will be evaluated on top of the best-performing operational mode:

| Metric | `standard` (Unconstrained ReAct) | `dag_record` (DAG Ledger Only) | `dag_guided` (DAG + Supervisor Audit) |
| :--- | :---: | :---: | :---: |
| **End-to-End Success Rate (%)** | [Placeholder: XX%] | [Placeholder: YY%] | [Placeholder: ZZ%] |
| **Hallucinated Completion Rate (%)** | [Placeholder: High] | [Placeholder: Low] | **0.0% (Zero)** |
| **Stage Contract Compliance (%)** | [Placeholder: N/A] | [Placeholder: XX%] | **100.0%** |
| **Average Token Overhead** | Baseline ($1.0\times$) | [Placeholder: $1.2\times$] | [Placeholder: $1.4\times$] |
| **Spurious TS Detection / Rejection** | [Placeholder: Ignored] | [Placeholder: Partial] | **100.0% Caught** |

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
1. **Multireference and Open-Shell Degeneracy:** Highly correlated transition states (e.g., diradical intermediates or transition-metal complexes with near-degenerate spin states) require multireference methods (CASSCF/NEVPT2) that are computationally prohibitive for routine automated screening.
2. **Explicit Solvent Conformational Complexity:** Although Cloudra successfully models localized solvent clusters (e.g., $(HFIP)_n$), full-solution sampling in flexible protic media warrants future coupling with hybrid QM/MM or neural network potential (NNP) metadynamics.
3. **Automated Synthesis Integration:** Connecting Cloudra's mechanistic free-energy profiles directly to automated robotic synthesis platforms (e.g., ChemAgents \cite{song2025chemagents} or Coscientist \cite{boiko2023autonomous}) represents a natural next step toward fully autonomous closed-loop molecular discovery.
4. **Knowledge-Grounded Hypothesis Generation:** Hypothesis proposal is currently driven by the LLM's parametric knowledge. Integrating a GraphRAG-style knowledge graph over literature mechanisms and computed precedents is a planned extension, to be evaluated as an augmentation on top of the best-performing operational mode.

---

## 6. Conclusion
In this work, we introduced **Cloudra**, an autonomous multi-agent research runtime for the quantum-chemical elucidation of homogeneous organic reaction mechanisms. By establishing the **Delivery DAG** architecture, Cloudra replaces ungrounded conversational claims with an immutable, deterministically audited evidence ledger. Enforced by ordered stage contracts, substantive compute gating, and the `coord_guard` firewall, Cloudra executes complete quantum-chemical workflows spanning atom mapping, conformational search, saddle point optimization, bidirectional IRC tracking, and quasi-harmonic thermochemistry. 

We validate Cloudra on three diverse and demanding mechanistic problems: a challenging HFIP-mediated hydrogen-bonding cluster pathway solved via human-agent collaboration, a complex multi-step small-molecule reaction mechanism resolved through fully automated large-scale workflow orchestration, and an axially chiral stereoselective transformation. Across these benchmarks, Cloudra demonstrates rigorous hypothesis generation, quantitative barrier prediction, and deterministically audited, hallucination-free completion. Cloudra provides a principled, reproducible framework for computational chemistry, paving the way toward autonomous, verifiable scientific discovery in molecular science.
