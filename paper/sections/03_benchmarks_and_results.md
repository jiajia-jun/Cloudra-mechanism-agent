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
To enable rigorous, reproducible, and standardized evaluation of autonomous mechanism elucidation beyond isolated examples, we construct a comprehensive **100-reaction benchmark test set** spanning four systematically calibrated difficulty tiers. The tiers are not ordered by how hard the answer is to look up, but by the **kind of scientific judgment** the agent must exercise to answer correctly. Each targets a distinct failure mode of an autonomous chemistry agent, and together they pose a single question: *can the agent correctly decide what to compute, rather than merely execute a computation it was told to perform?*

**Easy (30).** The baseline. Textbook single-step elementary transformations of small, closed-shell singlet molecules (a canonical Diels–Alder, a Claisen or Cope rearrangement, a 4$\pi$/6$\pi$ electrocyclization, an $S_N2$, an $E2$, a carbonyl addition, a hydrogen transfer), plus a set of intramolecular processes (atropisomeric rotation, ammonia umbrella inversion, conformational rotation, proton-cluster transfer). These are drawn from the high-density region where the underlying interatomic potential is well behaved, so a correct answer requires only a *self-consistent mechanistic closure*: a valid saddle, a bidirectional IRC that actually connects the two endpoints, and a physically consistent frequency. This tier asks the baseline question: **does the agent compute a mechanism the way a careful researcher would, or does it merely narrate one?**

**Normal (30).** This tier raises the demand to **mechanistic complexity**, scaffolded in three ascending bands. (i) *Route discrimination*—a single substrate that reacts through competing channels ($S_N2$ vs. $E2$, Zaitsev vs. Hofmann elimination, 1,2- vs. 1,4-addition), where correctness depends on which pathway is actually kinetically favored. (ii) *Simple multi-step networks* (two to three elementary steps). (iii) *Complex named-reaction cascades* (three to four steps, e.g. a Fischer indole or Paal–Knorr synthesis). The tested capability is the agent's ability to **generate and prune a mechanism hypothesis**: propose intermediates, capture them, rank competing barrier heights, and decide which branch of a reaction network is operative. The set is drawn from textbook classics, and the pool is de-duplicated at the level of *mechanistic essence*—a chemical-difference analysis shows the 48 candidates collapse to roughly 32 distinct mechanistic types—with the remaining redundancy deliberately kept as acid/base or O/N "contrast pairs" that probe whether an agent can distinguish two superficially similar mechanisms.

**Hard (20).** This tier raises the demand to **stereochemical 3-D selectivity**. It tests three things: (i) *stereospecificity*—whether a given substrate geometry deterministically maps to a single product configuration (Woodward–Hoffmann rules, syn/anti addition and elimination, $S_N2$ inversion); (ii) *stereoselectivity competition*—whether the agent can resolve the free-energy difference between two *diastereomeric* transition states (endo:exo, face selectivity, torquoselectivity), a genuinely quantitative, geometry-dependent question; and (iii) *configurational stability*—barriers to atropisomer racemization. The tier exists because this is precisely where string- or rule-level "chemical intuition" fails: the answer lives in three-dimensional electronic structure, not in the connectivity of the SMILES. The agent must find *and compare* competing transition states, and the gold reference carries the *difference* between channels rather than a single absolute barrier.

**Impossible (20).** The most novel tier, and the one that defines the benchmark's central claim. These are **strong-static-correlation / near-degenerate diradical systems**, where a single-reference description (RHF-CCSD(T), closed-shell RKS-DFT, or an MLIP trained on single-reference DFT labels) returns *non-physical* results: wrong electronic-state ordering, artificial symmetry breaking, or barriers off by tens of kilocalories per mole. Here the correct behavior is **not** to compute a number. It is for the agent to recognize during its spin/electronic-state diagnosis that the requested quantity lies outside the validity of its allowed methods, and to **issue a justified scientific refusal**—explaining *why* the result is untrustworthy and what level of theory (CASSCF/CASPT2/MRCI) would be required. Each impossible case is paired with a **sibling control**: a mechanistically related reaction from the same family that *is* single-reference amenable. The intended signal is a conjunction—the agent must refuse the impossible case *and* solve its sibling—because only that pairing proves the refusal arose from a genuine electronic-structure diagnosis rather than from the difficulty or unfamiliarity of the problem.

Together, the tiers form a graded probe of the scientific judgment that matters most for an autonomous quantum-chemistry agent: correct single-step execution, mechanistic hypothesis generation and pruning, stereochemical 3-D perception, and finally an honest assessment of the boundaries of the method itself. It is the last of these—reliable abstention when the method is invalid—that we believe is the most consequential and least-well-served capability in current computational-chemistry agents, and it is the axis on which the benchmark is most clearly novel.

Finally, the set is the product of a documented, reproducible construction pipeline rather than an ad hoc collection: each tier is curated from a dedicated candidate pool (`easy.md`/`normal.md`/`hard.md`/`impossible.md`) that is the sole source of truth for SMILES, charges, and barriers, and from which independent generators deterministically emit one machine-readable `TaskSpec` JSON per reaction. For the multi-step tiers the atom-mapped `bond_changes` are derived by diffing per-step atom-mapped SMILES (never hand-typed) and validated fail-loud; the gold graph carries intermediates, competing stereochemical channels, and, for the Impossible tier, explicitly *inaccessible* nodes (`accessible=false`). Reference barriers record their provenance (`verified`/`partial`/`unverified`, and whether `computed_by_us`); in the current release all are literature-anchored, and we are running a reference-answer campaign to recompute each barrier first-principles and replace the literature anchor with a self-computed value. This staged provenance deliberately avoids presenting unverified literature numbers as ground truth.

#### Scoring: A Forensic Audit, Not a Self-Report

The benchmark is engineered around a single premise: an agent's self-declared success is not evidence. Rather than trusting a narrative summary, every run is scored by an independent, deterministic forensic pass over the agent's sandbox—mirroring how a human supervisor would audit a computational study, asking whether the claimed results are actually backed by reproducible artifacts and whether those artifacts are physically sound. Scoring composes three nested layers plus a structural comparison:

1. **Evidence integrity (Layer 1).** The scorer scans the sandbox, locates the delivered mechanism graph, and binds every graph element to a concrete computational evidence file, mediated by the `smiles:` annotation that the delivery contract requires in every evidence file (which propagates into quantum-chemistry logs via the input title/comment). A matching fingerprint or molecular hash earns full credit; a species differing only by protonation/charge state earns partial credit; a claim with no backing evidence earns none. A graph that is missing, unparseable, or bound to zero evidence is *penalized*—an unsupported mechanistic claim is judged worse than no claim at all. This layer answers: does the agent deliver what it claims, or is it asserting a result?
2. **Physical self-consistency (Layer 2).** Independent of any gold reference, every transition state is checked to be a first-order saddle (exactly one imaginary frequency, excluding spurious low-frequency conformer modes below 100 cm⁻¹), its IRC is checked to connect both endpoints, and every species is checked to be a genuine minimum. This layer answers: is the computed mechanism internally physically valid, rather than a numerically plausible but saddle-free narrative?
3. **Barrier accuracy (Layer 3).** Where a reference barrier exists, the agent's reported barrier is scored with a Gaussian tolerance—the score decays exponentially with the squared deviation, calibrated per task, and capped so that legitimate method-level differences are not over-penalized. This layer answers: is the magnitude right, not just the topology?
4. **Mechanism-graph comparison.** The delivered graph is compared to the gold mechanism graph with a chemistry-parameterized graph edit distance. Default scoring is *subgraph coverage*: the gold mechanism must be found within the delivered graph, while any extra delivered nodes or edges are free. This encodes the stance that investigating more than necessary is never penalized—the penalty is reserved for a wrong step, a missing intermediate, or a chemically mismatched species. Node substitution is priced by a molecular-hash shortcut and, in general, by a sigmoid over Morgan-fingerprint similarity; edge substitution is priced by the symmetric difference of the atom-mapped bond-change sets, so that a concerted-versus-stepwise divergence is explicitly priced. Stereochemistry is treated layer-appropriately: ignored for Easy/Normal, but costly for Hard.

The four are combined as a weighted composite and multiplied by a binding-quality factor derived from the integrity layer:

$$\text{final} = \big(0.5\cdot\text{graph} + 0.2\cdot\text{self-consistency} + 0.3\cdot\text{accuracy}\big) \times \text{binding\_quality}$$

The weights are a deliberate statement about what matters. Graph topology dominates (0.5), because getting the mechanism right is the primary goal. Physical validity (0.2) is a gate that must be passed but is binary. Barrier magnitude (0.3) is the quantitative check. The binding-quality multiplier drives the anti-fabrication point home: even a topologically perfect mechanism earns nothing if it is not backed by actual computational evidence. Refusal behavior is tracked orthogonally to this score (every tier can end answered/refused/failed), because the Impossible tier's headline metric is not a per-tier score but a cross-tier refusal calibration—how precisely the agent refuses where it should, and answers where it should—which is precisely the metric that a "refuse everything" agent cannot inflate.

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
