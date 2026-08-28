# Supplementary Information

## Supplementary Information for: Cloudra: An Autonomous Multi-Agent Research Runtime for Quantum-Chemical Organic Reaction Mechanism Elucidation

---

### Section S1: System Architecture, Delivery DAG, and Knowledge Graph Implementation Details
- **S1.1 Event-Sourced Kernel (Runtime v2) Specification:**
  - Event types (`agent.thinking`, `tool.finished`, `hub.posted`, `dag.mutation`, etc.).
  - Deterministic state replay and session persistence.
- **S1.2 Peer-to-Peer AgentHub Protocol:**
  - Broadcast, direct call, and subscription schema.
  - Sub-agent specialization prompts and capability mappings (Coordinator, small_mol, researcher, explorer, Supervisor).
- **S1.3 Delivery DAG Formal Specification:**
  - Node schema (`OccurrenceNode`) and Edge schema (`ElementaryStepEdge`).
  - Stage contracts ($s_1 \rightarrow s_8$) and Allowed Stage Sequences.
  - Mathematical definition of Delivery Coverage:

$$\mathcal{C}(\mathcal{G}) = \prod_{e \in \mathcal{E}} \mathbb{I}\left( \forall s \in \mathcal{S}_\mathrm{req}(e), \text{status}(s) \in \{\text{supported}, \text{skipped\_with\_reason}\} \right)$$

- **S1.4 Computational Chemistry Knowledge Graph (GraphRAG) Ontology & Decision Trees:**
  - Decision DAG schema (Symptom, Diagnostic Criterion, Mitigation Action, Fallback Escalation).
  - $L_0/L_1/L_2$ tiered evidence validation and falsified entry penalty weighting.
  - Formatted examples of injected Decision Tree Walks for multi-imaginary TS, SCF divergence, spin contamination, and solvent cluster selection.
- **S1.5 Policy Guards & Security:**
  - `coord_guard` regex patterns and AST inspection blocking manual coordinate blocks.
  - Substantive compute entry gate specifications.

---

### Section S2: Quantum-Chemical Calculation Details
- **S2.1 Software and Computational Levels:**
  - Semi-empirical & Machine Learning Potentials: GFN2-xTB / CREST v2.12, MACE-OMol25 foundation model.
  - Density Functional Theory: Gaussian 16 Rev C.01 / ORCA 5.0.4.
  - Functionals and Basis Sets: $\omega\text{B97X-D}/\text{def2-TZVP}$, $\text{B3LYP-D3(BJ)}/\text{def2-SVP}$, etc.
  - Solvation Models: SMD (Solvation Model based on Density) with specified solvent parameters.
- **S2.2 Vibrational and Thermochemical Protocols:**
  - GoodVibes quasi-harmonic corrections ($T = 298.15\ \mathrm{K}$, $P = 1.0\ \mathrm{atm}$, concentration $1.0\ \mathrm{M}$).
  - Low-frequency vibrational cutoff criteria ($100\ \mathrm{cm^{-1}}$).
  - Intrinsic Reaction Coordinate (IRC) integration steps and convergence thresholds.

---

### Section S3: 100-Reaction Benchmark Test Set and Two-Stage Serial Ablation
- **S3.1 Curated 100-Reaction Benchmark Test Set Specification:**
  - **Easy Tier (30 reactions):** Textbook classic single-step reactions (Diels-Alder, Claisen, SN2, E2, keto-enol tautomerism).
  - **Normal Tier (30 reactions):** Multi-step named transformations (Robinson, Beckmann, Fischer indole, HWE, Biginelli).
  - **Hard Tier (20 reactions):** Stereochemical / asymmetric reactions, dynamic kinetic resolution, explicit $(\mathrm{HFIP})_n$ solvent cluster catalysis.
  - **Impossible Tier (20 reactions):** Pathological electronic systems (strong multireference, diradicals, spin-forbidden) testing early justified refusal.
  - Standardized reactant/product SMILES, ground-truth reference DAGs, and literature free-energy barriers.
- **S3.2 Trajectory-Level Multi-Dimensional Metrics and Progress-Cost Curve Calculation:**
  - Graph Edit Distance (GED) formulation with chemistry-aware edge and node pricing.
  - Physical self-consistency validation criteria.
  - Progress-Cost Curve AUC, inflection point cost (90% completion), and wasted compute ratio calculations.
- **S3.3 Two-Stage Serial Ablation Protocols:**
  - Stage 1: Detailed run logs, tool call distributions, and failure mode analysis for `standard`, `dag_record`, and `dag_guided` modes.
  - Stage 2: Knowledge Graph augmentation (`dag_guided` vs. `dag_guided + GraphRAG`) measuring error-recovery acceleration and compute waste reduction.

---

### Section S4: Real-World Frontier Research Case Studies Details
- **S4.1 HFIP Solvent-Cluster Mediated Quinone Formation Case Study (Prof. Jun Zhou):**
  - $(\mathrm{HFIP})_n$ cluster binding energies and optimized hydrogen-bonding geometries.
  - IRC path coordinates verifying explicit proton-shuttle mechanism.
  - Interaction region indicator (IRI) / Independent Gradient Model (IGM) analysis of non-covalent interactions.
- **S4.2 Axial-Chiral Atropisomeric Benchmark (Prof. Weiwei Luo):**
  - Competing $(R)$- and $(S)$-forming transition state geometries and imaginary mode vectors.
  - Torsional potential energy scan of biaryl rotation.
  - Boltzmann-weighted enantiomeric excess ($\%ee$) and thermal racemization half-life ($t_{1/2}$) calculations.
- **S4.3 Open-Shell Small-Molecule Radical Reaction (Prof. Wenkun Luo):**
  - Broken-symmetry DFT calculation logs, spin density distributions, and $\langle S^2 \rangle$ diagnostic outputs across all radical intermediates and transition states.
  - Full reactant, intermediate, TS, and product Cartesian geometries (.xyz) across all elementary steps.

---

### Section S5: Complete Agent Prompts and Tool Specifications
- Full system prompts for Coordinator, Supervisor, small_mol, researcher, and explorer.
- Tool schemas and JSON specifications for all 18+ integrated tools.
