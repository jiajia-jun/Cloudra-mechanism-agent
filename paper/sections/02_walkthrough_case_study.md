# 2. System Architecture and PES Exploration: An End-to-End Walkthrough

To move beyond abstract architectural schematics, we ground the design of Cloudra in a concrete, representative chemical investigation: the thermal ring-opening of 3-methylcyclobutene into 1,3-pentadiene (Benchmark Task `HA1`). This classical pericyclic transformation, governed by the Woodward--Hoffmann rules of orbital symmetry, exhibits intrinsic stereochemical competition. Thermal electrocyclization requires a conrotatory ($C_2$-symmetric) pathway, which inherently bifurcates into two distinct channels: an *outward* rotation of the methyl group yielding $(1E,3E)$-penta-1,3-diene, and an *inward* rotation yielding $(1Z,3E)$-penta-1,3-diene. The inward transition state incurs substantial steric clash between the inward-pointing methyl moiety and the opposite methylene group, leading to an experimental and computational activation barrier gap of $\sim 5.7\text{ kcal/mol}$.

Navigating this competitive potential energy surface (PES) requires an autonomous agent to demonstrate spatial awareness, correct atom numbering correspondence, precise saddle-point localization, and rigorous verification of imaginary-mode vibrational vectors. Crucially, **the Delivery Evidence Directed Acyclic Graph (DAG) functions as the foremost architectural carrier and semantic scaffold**. Before executing any quantum-chemical calculation, the agent must formalize chemical hypotheses into a DAG topology, establishing explicit stage contracts and evidence slots. Only once this primary scaffold is instantiated do subsequent physical verification technologies—the Hessian spectral condition, normal-mode projection, and bidirectional IRC continuity—possess an immutable structural anchor to latch onto. Below, we trace the full lifecycle of this exploration, interleaving scaffold construction, physical operators, multi-layered gating, and self-healing.

---

```
                       [ Unlabeled SMILES / Conditions ]
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 1. The Primary Architectural Carrier (DAG Framework & Stage Contracts)      │
│    • Instantiating the semantic scaffold: species nodes & transformation edges│
│    • Declarative Stage Requirement Contracts: mandatory set {ts_opt, freq, irc}│
│    • Pre-allocated statutory evidence slots for deterministic verification   │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 2. PES Geometric Perception & Path Interpolation (reaction_mapping, ts_guess)│
│    • Maximum Common Subgraph (MCS) isomorphism & topological atom mapping   │
│    • Distance-decayed steric BFS: w_i = r_vdw(A_i) * rho^d                  │
│    • Automated Watch-Pair detection: (C3, C4) bond-breaking coordinate      │
│    • SVD-based Kabsch rigid-body alignment: R = V diag(1, 1, det(VU^T)) U^T │
│    • Coupled NEB-IDPP interpolation: V_IDPP = sum (r_ij - r_ij^*)^2 / r_ij^4│
│    • Branching: (E)-conrotatory (outward) vs (Z)-conrotatory (inward) paths │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 3. Integrated Scientific Verification Mounted on the DAG (ts_guess, irc)    │
│    • Exact Hessian Spectral Condition: strictly 1 imaginary frequency        │
│    • Normal-Mode Projection: Delta_pq = ||v_p - v_q|| on Watch-Pairs        │
│    • Dual-direction Short-IRC stepping & unconstrained minimum re-relaxation│
│    • Binding native Opt, Frequency, and IRC logs directly to DAG contracts  │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 4. Multi-Layered Gating, Interception, and Self-Healing                     │
│    • Four defensive layers: QM engine, physical tool, DAG, and Supervisor   │
│    • Real-world interception: rejecting spurious methyl wagging modes       │
│    • Diagnostic self-healing: adjusting dihedral angle & recovering true TS │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 5. Formal Delivery and Quantitative Energetics                              │
│    • Binding native logs: Outward (33.1 kcal/mol) vs Inward (38.8 kcal/mol)  │
│    • Favored Channel Attribution: favored: true on E-channel                │
│    • Independent Supervisor Acceptance -> Verified Final Settlement         │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 2.1 The Primary Carrier: Delivery Evidence DAG Framework and Stage Contracts

No rigorous mechanistic investigation can proceed in an unanchored computational vacuum. In Cloudra, **the Delivery Evidence Directed Acyclic Graph (DAG) is an independent, foundational architectural carrier and semantic coordination hub**. It is neither a post-hoc summary visualization nor a passive benchmark artifact; rather, it represents the primary ontological scaffold that must be established at the very outset of any research task.

Upon receiving the initial task input, the agent's primary technical action is constructing the DAG topology in the workspace:
1. **Species Node Instantiation**: The agent formalizes prospective chemical states into uniquely identified persistent nodes, distinguishing the reactant complex ($RC$), prospective transition states ($\text{TS}$), intermediate structures ($\text{INT}$), and target product isomers ($P$). Each node strictly encapsulates chemical state, charge, and spin multiplicity.
2. **Elementary Edges and Declarative Stage Requirement Contracts**: Directed edges define elementary transformation steps. The core architectural feature is embedding a **declarative, unordered physical evidence contract set** within each edge, rather than enforcing a rigid procedural pipeline. For a canonical elementary reaction step, the system mandates a closed set of statutory evidence:
   $$\mathcal{S}_{\text{req}} = \{\text{ts\_opt}, \text{frequency}, \text{short\_irc}\}$$
   Here, $\text{ts\_guess}$ serves strictly as an advisory initial geometric hypothesis and never acts as a blocking prerequisite, while thermochemical corrections ($\text{thermochemistry}$) are declared on-demand. Departing from traditional workflow orchestrators that hardcode procedural order, Cloudra completely abandons centralized process scheduling (No Process DAG), allowing evidence artifacts to arrive and bind out of order (`allow_out_of_order = True`). An agent can autonomously launch combined opt-plus-freq jobs or verify IRC endpoints at its own pace. The rigidity of the contract is enforced not through micromanaging procedural execution, but through **strict all-or-nothing completeness and physical immutability at settlement**: so long as any slot in $\mathcal{S}_{\text{req}}$ remains pending or fails physical validation, the reaction step is strictly blocked from advancing to `supported`, entirely eliminating natural-language hallucination.

Establishing this primary carrier anchors the stochastic language model onto an auditable finite state machine, guaranteeing that subsequent geometric algorithms, quantum-chemical calculations, and verification predicates possess a deterministic physical host and rigorous acceptance boundaries.

---

## 2.2 PES Geometric Perception and Path Interpolation Algorithms

Once the primary DAG scaffold is erected, the agent receives unlabelled molecular representations: reactant SMILES `CC1CC=C1` (3-methylcyclobutene) and product connectivity `C=CC=CC` (penta-1,3-diene), together with gas-phase thermal conditions. Because stereochemical resolution is unassigned in the initial prompt, direct coordinate generation by a language model frequently yields atom collisions or invalid chiral inversions.

Cloudra offloads coordinate perception to deterministic chemical graph operators:

### 1. Boundary Alignment and Reaction Center Perception (Watch-Pairs)
1. **Topological Correspondence and Subgraph Isomorphism**: The `reaction_mapping` module executes maximum common subgraph (MCS) matching between reactant and product graphs. When constitutional symmetry permits ambiguous candidate mappings, each candidate is scored through an edit-distance matrix.
2. **Steric Bulk Graph Traversal ($\rho^d$)**: To handle hindered rotational axes and stereocenters, the tool computes a graph-distance-decayed steric hindrance score for any candidate axis $(i, j)$:
   $$w_{\text{bulk}}(i, j) = \sum_{k \in \text{subgraph}(i)} r_{\text{vdW}}(A_k) \cdot \rho^{d(i, k)}$$
   where $r_{\text{vdW}}(A_k)$ is the Bondi van der Waals radius of atom $k$, $d(i, k)$ is the shortest topological path from the root atom $i$, and the decay factor is pinned to $\rho = 0.5$. This isolates the methyl substituent at C3 as the stereochemically differentiating pivot.
3. **Automated Reaction Center (Watch-Pair) Detection**: By computing the interatomic distance variance between aligned initial conformers:
   $$\Delta D_{ij} = |d_{ij}^{(\text{prod})} - d_{ij}^{(\text{react})}|$$
   the algorithm automatically detects the reacting bond pair without human annotation. For 3-methylcyclobutene, the distance between C3 and C4 elongates from $1.54\text{ \AA}$ (single bond) to $> 2.8\text{ \AA}$ (scission), registering $(C3, C4)$ as the dominant reaction watch-pair.

### 2. Preorganization and Path Interpolation (IDPP Guesses)
Transition-state optimization via quasi-Newton or rational function optimization (RFO) techniques is notoriously sensitive to initial geometries. Linear interpolation in Cartesian space causes unphysical bond contractions and optimizer divergence. Cloudra resolves this via a multi-stage geometric pipeline:
1. **Kabsch Rigid-Body SVD Alignment**: The mobile product frame $\mathbf{P}$ is centered and aligned with the stationary reactant frame $\mathbf{R}$ by solving the orthogonal Procrustes problem:
   $$\mathbf{H} = \mathbf{P}^T \mathbf{R}, \quad \mathbf{U} \mathbf{\Sigma} \mathbf{V}^T = \text{SVD}(\mathbf{H})$$
   $$\mathbf{R}_{\text{rot}} = \mathbf{V} \begin{pmatrix} 1 & 0 & 0 \\ 0 & 1 & 0 \\ 0 & 0 & \det(\mathbf{V} \mathbf{U}^T) \end{pmatrix} \mathbf{U}^T$$
   eliminating non-physical artificial torque arising from arbitrary frame orientation.
2. **Coupled NEB-IDPP Path Generation**: Between the aligned endpoints, the system relaxes an objective pseudo-potential in internal coordinates:
   $$V_{\text{IDPP}}(\mathbf{R}) = \sum_{i < j} \frac{\left(r_{ij} - r_{ij}^{\text{target}}(\lambda)\right)^2}{r_{ij}^4}$$
   where $r_{ij}^{\text{target}}(\lambda) = (1-\lambda)r_{ij}^{(R)} + \lambda r_{ij}^{(P)}$ interpolates pairwise distances. The implementation supports a coupled NEB **Standard Mode** ($k = 0.1\text{ a.u.}$, improved tangent, MDMin optimizer) and an independent Adam **Light Mode** ($\alpha = 0.02$).

Seeding the terminal images with $(1E,3E)$- and $(1Z,3E)$-conformations, the IDPP optimizer extracts two distinct midpoint structures: $\text{TS}_{\text{out}}^{\text{guess}}$ and $\text{TS}_{\text{in}}^{\text{guess}}$. The agent binds these initial guess geometries to the corresponding edges as advisory evidence and autonomously launches high-level quantum-chemical saddle-point optimization jobs.

---

## 2.3 Integrated Scientific Verification for Transition States

A pervasive defect in contemporary computational chemistry agents is the conflation of a successful execution code (`exit 0`) or isolated energy parsing with transition-state validation. In rigorous physical chemistry, gradient convergence is merely the preliminary precondition for an extensive evidentiary audit. Cloudra's theoretical contribution lies in **synthesizing the Hessian spectral condition, reaction-center vibrational mode projection, intrinsic reaction coordinate (IRC) directional continuity, and endpoint stationary-minimum qualification into an unforgeable, physically coupled verification harness**.

Any candidate transition state must satisfy four interlocking physical criteria before acceptance:

### 1. Exact Hessian Spectral Condition
Diagonalization of the mass-weighted Cartesian Hessian $\mathbf{H}_M = \mathbf{M}^{-1/2} \nabla^2 V \mathbf{M}^{-1/2}$ must yield **strictly one negative eigenvalue** (corresponding to exactly one imaginary frequency):
$$\text{card}(\{\nu_k \in \operatorname{spec}(\mathbf{H}_M) \mid \operatorname{Im}(\nu_k) \neq 0\}) = 1$$
Structures exhibiting zero imaginary frequencies (local minima), multiple imaginary frequencies (higher-order saddle points), or uncalculated frequencies are immediately rejected.

### 2. Normal-Mode Algebraic Projection on Reaction Centers (`_assess_imag_mode_alignment`)
A single imaginary frequency does not establish that the vibrational eigenvector drives the target transformation. In flexible systems, spectator modes—such as unhindered methyl rotation, skeletal ring puckering, or solvent reorientation—routinely produce spurious imaginary frequencies of tens to hundreds of $\text{cm}^{-1}$.

Cloudra enforces an algebraic displacement projection metric. Let $\mathbf{v}^{(k)} \in \mathbb{R}^{3N}$ denote the displacement eigenvector of the imaginary mode. The relative Cartesian displacement between any pair of atoms $(i, j)$ is:
$$\vec{\delta}_{ij} = \vec{v}_i^{(k)} - \vec{v}_j^{(k)}, \quad \Delta_{ij} = \|\vec{\delta}_{ij}\|_2$$
Evaluating $\Delta_{\max} = \max_{i < j} \Delta_{ij}$ across all $N(N-1)/2$ pairs, the verification requires at least one reaction watch-pair $(p, q) \in \text{watch\_pairs}$ (identified in Section 2.1 via topological distance variance) to satisfy:
$$\Delta_{pq} \ge \alpha \cdot \Delta_{\max}$$
with the sensitivity threshold pinned to $\alpha = 0.40$. In our 3-methylcyclobutene outward electrocyclization trajectory, the C3--C4 scission pair achieves $\Delta_{3,4} = 0.82 \cdot \Delta_{\max}$, directly demonstrating that the negative curvature drives ring cleavage rather than peripheral conformational rattling.

### 3. Directional Continuity and Endpoint Minimum Isomorphism
A genuine transition state must function as the col connecting reactant and product valleys. Crucially, **integrating finite gradient steps followed by endpoint re-optimization (Short-IRC) is an engineering compromise adopted to circumvent the prohibitive cost and asymptotic flat-valley stalling of full-length DFT IRC integration; it is not presented as an algorithmic novelty**. The substantive scientific constraint lies in the rigorous criteria enforced on the resulting endpoints:
- Stepping along the forward and reverse gradient directions ($\mathbf{x}_{\text{fwd}}, \mathbf{x}_{\text{rev}}$), the terminal frames are released from IRC constraints and optimized to stationary states.
- Both relaxed endpoints must be verified as **strict local minima with zero imaginary frequencies**.
- Both relaxed endpoints must match the declared reactant ($RC$) and product ($P$) structures under complete topological graph isomorphism.

Only when the imaginary mode projects onto the active bonds and the bifurcated paths relax to genuine zero-frequency minima matching target species is directional continuity certified.

### 4. DAG-Bound Evidence and External Supervisor Gating
Verification is never established by natural-language self-declaration. The harness binds all raw execution logs (optimization, harmonic frequency, IRC stepping, and endpoint relaxations) to the Delivery Evidence DAG. An independent Supervisor agent inspects the raw log provenance before granting settlement. This multi-layered coupling constitutes Cloudra's core defense against hallucinated or unphysical mechanistic claims.

---

## 2.4 Multi-Layered Gating, Interception, and Self-Healing

The defining power of Cloudra is demonstrated not when calculations succeed on the first attempt, but when physical failures are intercepted and remediated without human intervention. During the parallel exploration of the inward conrotatory channel ($e_{\text{in}}$), the initial geometry optimization hit an unphysical saddle point:

```
[Agent Action] Proposes inward guess via linear heuristic
     │
     ▼
[Quantum Engine Gate] Geometry optimization completes (exit 0)
     │
     ▼
[Physical Tool Gate: ts_guess] Frequency analysis returns nu_1 = -86.4 cm^-1
     │
     ├─-> Normal-Mode Projection: Delta_{3,4} / Delta_max = 0.08 (< 0.40 threshold)
     ├─-> Root Cause: Imaginary frequency is an out-of-plane methyl wagging mode!
     └─-> Interception: Return structured error code `IMAG_MODE_MISALIGNED`
     │
     ▼
[Agent Self-Correction] Reads diagnostic error -> adjusts dihedral -> re-seeds IDPP
     │
     ▼
[Convergence] Re-optimization converges to true inward TS (nu_1 = -512.1 cm^-1)
```

The system partitions verification into four distinct architectural layers, ensuring that no false-positive result slips through:

| Interception Layer | Triggering Condition | Diagnostic Feedback Returned | Recovery Action |
| :--- | :--- | :--- | :--- |
| **1. QM Engine Guard** | SCF non-convergence; optimization MaxCycles exceeded | Compact status code: `SCF_CONVERGENCE_FAIL` | Switches to quadratically convergent SCF (`qc`), adjusts initial damping. |
| **2. Physical Tool Guard** | Multiple imaginary frequencies; normal mode $\Delta_{pq} < \alpha \Delta_{\max}$ | Physical diagnosis: `IMAG_MODE_MISALIGNED` with offending atom indices | Re-interpolates reaction path; twists initial dihedral angle away from spectator mode. |
| **3. DAG Stage Contract** | Missing IRC proof; endpoint unverified | Contract violation: `UNSATISFIED_STAGE_CONTRACT [short_irc]` | Prohibits edge promotion; triggers automated directional IRC run. |
| **4. Supervisor Gate** | Agent attempts premature settlement without complete evidence graph | External veto: `SETTLEMENT_REJECTED: Unbound transition state node` | Blocks session exit; forces agent to complete evidence binding or declare partial. |

---

## 2.5 Formal Delivery and Quantitative Energetics

Once both pathways are rigorously characterized, the agent records the complete quantitative evidence on the delivery DAG:

- **Channel $e_{\text{out}}$ (Outward Rotation)**: Bound to `TS_E_optfreq.log` and associated IRC endpoint logs. The electronic activation barrier is computed relative to the lowest verified reactant minimum:
  $$\Delta E_{\text{out}}^\ddagger = E(\text{TS}_{\text{out}}) - E(RC) = -195.4218 - (-195.4745) = 0.0527\text{ a.u.} = 33.09\text{ kcal/mol}$$
  Tagged with `channel: "outward_rotation"` and `favored: true`.
- **Channel $e_{\text{in}}$ (Inward Rotation)**: Bound to `TS_Z_optfreq.log`. The electronic activation barrier is:
  $$\Delta E_{\text{in}}^\ddagger = E(\text{TS}_{\text{in}}) - E(RC) = -195.4127 - (-195.4745) = 0.0618\text{ a.u.} = 38.81\text{ kcal/mol}$$
  Tagged with `channel: "inward_rotation"` and `favored: false`.

The resulting quantitative energy difference of $\Delta \Delta E^\ddagger = 5.72\text{ kcal/mol}$ perfectly replicates the gold reference value ($5.7\text{ kcal/mol}$). The Supervisor agent inspects the final DAG, verifies that all terminal nodes are supported by native Gaussian logs with complete frequency and IRC lineage, and formally signs off on task settlement.

By grounding the exposition in this complete, verified chemical trajectory, we establish that Cloudra's capabilities stem not from prompt engineering or model hallucination, but from the tight, deterministic coupling of domain-specific PES operators, formal evidence contracts, and unrelenting physical gating.
