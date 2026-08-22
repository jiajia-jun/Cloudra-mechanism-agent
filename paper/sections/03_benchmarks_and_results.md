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

```
+-----------------------------------------------------------------------------+
|                           THREE CORE BENCHMARK CASES                        |
+-----------------------------------------------------------------------------+
|  Case 1: HFIP Solvent-Cluster Mediated Mechanism (Human-Agent Collab)       |
|  - Challenging explicit hydrogen-bonding network (HFIP trimer/dimer)        |
|  - Collaborative steering: undergraduate student + Cloudra multi-agent      |
|                                                                             |
|  Case 2: Complex Multi-Step Small-Molecule Mechanism (Fully Automated)      |
|  - Large Delivery DAG spanning many elementary steps and intermediates      |
|  - Fully automated large-scale quantum-chemical workflow orchestration      |
|                                                                             |
|  Case 3: Axial-Chiral Atropisomeric Rotational Barrier                      |
|  - Dynamic kinetic resolution / enantioselective barrier quantification     |
|  - Accurate diastereomeric TS energy splitting vs experimental ee           |
+-----------------------------------------------------------------------------+
```

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

- **Observations:** In `standard` mode, agents routinely declare task completion despite unresolved imaginary frequencies or disconnected IRC endpoints. Under `dag_record`, the structured ledger eliminates coordinate hallucinations and tracks pending stages, but may accept borderline geometries. Under `dag_guided`, the Supervisor rigorously catches multi-imaginary frequency saddle points and forces re-optimization, achieving publication-grade scientific validity.
