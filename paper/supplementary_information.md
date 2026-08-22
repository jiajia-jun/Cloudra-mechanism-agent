# Supplementary Information

## Supplementary Information for: Autonomous Elucidation of Homogeneous Organic Reaction Mechanisms through Directed Acyclic Graph Evidence Delivery and Peer-to-Peer Agent Orchestration

---

### Section S1: System Architecture and Runtime Implementation Details
- **S1.1 Event-Sourced Kernel (Runtime v2) Specification:**
  - Event types (`agent.thinking`, `tool.finished`, `hub.posted`, `dag.mutation`, etc.).
  - Deterministic state replay and session persistence.
- **S1.2 Peer-to-Peer AgentHub Protocol:**
  - Broadcast, direct call, and subscription schema.
  - Sub-agent specialization prompts and capability mappings (Coordinator, small_mol, researcher, explorer, Supervisor).
- **S1.3 Delivery DAG Formal Specification:**
  - Node schema (`OccurrenceNode`) and Edge schema (`ElementaryStepEdge`).
  - Stage contracts and Allowed Stage Sequences.
  - Mathematical definition of Delivery Coverage:

$$\mathcal{C}(\mathcal{G}) = \prod_{e \in \mathcal{E}} \mathbb{I}\left( \forall s \in \mathcal{S}_\mathrm{req}(e), \text{status}(s) \in \{\text{supported}, \text{skipped\_with\_reason}\} \right)$$

- **S1.4 Policy Guards & Security:**
  - `coord_guard` regex patterns and AST inspection blocking manual coordinate blocks.
  - Substantive compute entry gate specifications.

---

### Section S2: Quantum-Chemical Calculation Details
- **S2.1 Software and Computational Levels:**
  - Semi-empirical: GFN2-xTB / CREST v2.12.
  - Density Functional Theory: Gaussian 16 Rev C.01 / ORCA 5.0.4.
  - Functionals and Basis Sets: $\omega\text{B97X-D}/\text{def2-TZVP}$, $\text{B3LYP-D3(BJ)}/\text{def2-SVP}$, etc.
  - Solvation Models: SMD (Solvation Model based on Density) with specified solvent parameters.
- **S2.2 Vibrational and Thermochemical Protocols:**
  - GoodVibes quasi-harmonic corrections ($T = 298.15\ \mathrm{K}$, $P = 1.0\ \mathrm{atm}$, concentration $1.0\ \mathrm{M}$).
  - Low-frequency vibrational cutoff criteria ($100\ \mathrm{cm^{-1}}$).
  - Intrinsic Reaction Coordinate (IRC) integration steps and convergence thresholds.

---

### Section S3: Benchmark Case Studies (Placeholders & Data Schemas)
- **S3.1 HFIP Solvent-Cluster Case Study:**
  - (HFIP)$_n$ cluster binding energies and optimized hydrogen-bonding geometries.
  - IRC path coordinates verifying explicit proton-shuttle mechanism.
  - Interaction region indicator (IRI) / Independent Gradient Model (IGM) analysis of non-covalent interactions.
- **S3.2 Complex Multi-Step Small-Molecule Mechanism Case Study (Fully Automated):**
  - Full reactant, intermediate, TS, and product Cartesian geometries (.xyz) across all elementary steps.
  - Complete IRC trajectories and forward/backward energy profiles for every Delivery DAG edge.
  - Absolute energies (Hartree), thermal corrections, and quasi-harmonic Gibbs free energies (kcal/mol).
  - End-to-end run logs: Delivery DAG mutation history, stage-contract bindings, and CallReview audit trail.
- **S3.3 Axial-Chiral Atropisomeric Benchmark:**
  - Competing $(R)$- and $(S)$-forming transition state geometries and imaginary mode vectors.
  - Torsional potential energy scan of biaryl rotation.
  - Boltzmann-weighted enantiomeric excess calculation details.

---

### Section S4: Multi-Mode Ablation and Benchmark Details
- **S4.1 Curated Mechanism Benchmark Test Set (xTB / DFT Level):**
  - Test set selection criteria: well-established homogeneous organic reactions with experimentally validated mechanisms, spanning common reaction types (pericyclic, ionic, organocatalytic, radical).
  - Per-task scoring: mechanistic recall, barrier agreement with literature, hallucinated completion rate, token/wall-clock cost.
  - Failure mode breakdown: coordinate corruption, spurious stationary points, disconnected IRCs, hallucinated completions.
- **S4.2 LLM Resource and Token Consumption:**
  - Token counts, tool call distributions, wall-clock timing, and financial cost comparisons across `standard`, `dag_record`, and `dag_guided` modes, plus the optional GraphRAG-augmented variant on top of the best-performing mode.

---

### Section S5: Complete Agent Prompts and Tool Specifications
- Full system prompts for Coordinator, Supervisor, small_mol, researcher, and explorer.
- Tool schemas and JSON specifications for all 18+ integrated tools.
