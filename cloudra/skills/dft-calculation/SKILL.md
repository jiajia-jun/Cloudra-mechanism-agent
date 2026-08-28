---
name: dft-calculation
description: Provide domain expertise for DFT (Density Functional Theory) quantum chemistry calculations on molecules and clusters using Gaussian/ORCA. Use when selecting functionals/basis sets, planning transition state workflows, and troubleshooting input errors. For periodic solids, see first-principles-calculation.
---

# 1. Local toolchain mapping (Toolchain Mapping)
When running molecular/cluster DFT, bind actions tightly to the `CLOUDRA` local toolchain:
- **Obtaining molecular structure and modeling**: SMILES is the core of molecular structure. When a ready 3D coordinate file is missing, prefer local SMILES tools:
  - If the user only gives a compound name (common name / IUPAC / CAS), call `name_to_structure` to resolve SMILES (you may set `generate_3d=True` to emit xyz directly). Chinese vernacular names hit poorly; on failure, ask the user for an English name or CAS number.
  - If the user only gives a chemical structure drawing, prefer `image_to_smiles` to recover SMILES.
  - To convert SMILES to 3D coordinates, call `smiles_to_mol` with `generate_3d=True`.
  - If you only need a Gaussian input file, you may call `qm_input_writer` with `source_type="smiles"` directly.  - **Never hand-write coordinates**: do not type Cartesian coordinates atom by atom from scratch, and do not build a molecule from remembered bond lengths/angles — **no exceptions**, even for “tweaking a few atoms” or thinking you are faster than the tools. Coordinates may only come from the tools above, from a database, or from existing logs via `format_converter`/`log_parser`. Manual intervention is limited to numerical tweaks of a Z-matrix from `internal_coordinates`, then converting back to Cartesian.
- **Ground-state minima vs TS initial guess tiering (Pragmatic Modeling)**:
  - **For ground-state minima (reactants, intermediates, products)**: **do not overthink or over-refine initial geometries**. The PES around a local minimum is bowl-shaped and modern DFT optimizers (Berny, GEDIIS) have powerful centripetal convergence. As long as the 3D structure from `smiles_to_mol(generate_3d=True)` has correct connectivity and reasonable hybridization without severe atomic clashes, **submit directly to `opt freq`**. Do not waste time, steps, or tokens manually tweaking bond lengths or checking stability on ordinary ground states. If conformation is slightly ambiguous, either let the optimizer relax to the nearest minimum or run a fast 1D scan; do not hesitate at the modeling step.
  - **Wavefunction stability exemption for standard closed-shell systems**: for ordinary closed-shell organic reactions (no unpaired electrons, no radical initiators, no open-shell 3d metals), assume standard R-DFT stability by default. `stable=opt` and FOD checks are **strictly exempted** unless explicit warning signs (open-shell diradicals, low-spin/high-spin degeneracies, homolysis) are present.
  - **Reserve precision for Transition States (saddle points)**: only TS searches need meticulous initial-guess preparation (IDPP interpolation, constrained scans, or reactive conformer distance filters).
- **Multi-molecule complexes / bimolecular modeling**: when assembling two (or more) molecules into a reaction complex, **do not hand-place relative orientation** — it is slow and almost always unreasonable. Correct path: place them roughly close (centroid distance slightly larger than a bonding distance), then use `conformer_search` with `distance_filters` to lock the reactive atom pair while sampling orientation, or pre-optimize the complex with xtb/force field to a reasonable geometry, then hand it to the DFT level. Preorganized orientation strongly affects bimolecular TS-search success; spend compute here rather than time on hand-placed coordinates.
- **Reaction atom mapping**: after obtaining reactant/product SMILES, call `reaction_mapping` before generating an interpolated path. Unlabeled SMILES may yield several near-equivalent candidates; when `ambiguous`, choose using the mechanism — do not treat rank-1 as ground-truth atom identity. The tool also keeps SMILES-index `graph_watch_pairs`, and after a concrete structure binds successfully it translates top-level `watch_pairs` into reactant coordinate indices. Existing mol/sdf/xyz require `binding_status=complete` and `binding_source=concrete` before passing the all-atom `atom_map` to `ts_guess interpolate`; a `binding_source=internal_generated` map only matches the tool’s internal RDKit `AddHs` order and must not be applied to an arbitrary external XYZ.
- **Generating input files**: prefer `qm_input_writer` to produce the input and reduce handwritten format errors — `engine='gaussian'` (default) writes a `.gjf`, `engine='orca'` writes a `.inp` (`method`/`basis_set`/`task_type`/`charge`/`multiplicity` map onto each program's syntax automatically; `{"opt":"ts,calcfc,noeigen"}` becomes `OptTS` for ORCA). Submit with `submit_compute_job` using the **matching `job_type`** ('gaussian' or 'orca'). Avoid comments in the input body to reduce parse risk.
- **chk/fchk placement (Gaussian only)**: always set `chk_name` (and `fchk_name` when downstream analysis needs it) so the checkpoint lands in the **same directory as the `.gjf`** — an absolute path built from `output_dir` (e.g. `/path/to/job.gjf` → `/path/to/job.chk`) is safest; a bare filename also works because `calculator.sh` cd's into the input's directory before running. Without `%chk`, the checkpoint survives only inside the per-task `GAUSS_SCRDIR`, which Cloudra deletes when the job ends — follow-up jobs that read the checkpoint (`geom=allcheck`, `guess=read`, freq-from-chk) and tools like `formchk`/`cubegen` then have nothing to work with. Keep the basename identical to the .gjf so the chk/log/fchk triple is easy to match. (ORCA has no equivalent directive — its `.gbw` lands next to the input automatically.)
- **Structural insight and fine-tuning**: call `internal_coordinates` as your “eyes” and “hands”. `mode=analyze` returns a bond-order-aware structure report (anomalous bond lengths/angles, rotatable-dihedral classification, stereochemistry R/S and E/Z, rings and Cremer–Pople puckering, equivalent atoms). Use `reactive_atoms`/`watch_pairs` to focus the reactive center (e.g. forming-bond distance and attack angle). The full Z-matrix is written automatically to a `.zmat` file and does not enter context. When you need GaussView-style “hand dragging”, you may still edit the Z-matrix text and convert back with `mode=zmatrix_to_cartesian`.
- **Conformer search**: call `conformer_search` for a conformational ensemble (energy window + RMSD clustering + Boltzmann populations). In mechanism work, use `distance_filters` to lock reactive atom pairs and keep preorganized reactive conformers — do not default to the lowest-energy conformer (Curtin–Hammett). The tool also keeps the lowest-energy reactive conformer outside the energy window and its conformational penalty relative to the global minimum; it is only a candidate, not automatically a viable TS precursor.
- **Transition-state guess and verification**: call `ts_guess`. `mode=interpolate` does IDPP interpolation of reactant/product and emits candidate coordinates (also usable as an NEB initial path); `mode=scan_prepare` generates Gaussian modredundant / ORCA scan input; `mode=scan_parse` parses the scan profile and extracts a TS guess, but it is an exploration tool and its output is not SI-grade validation. `mode=verify` by default only gives `candidate/unlikely/inconclusive` direction advice; only when you already have one imaginary frequency, bidirectional partial IRC, and intermediates from unconstrained optimization of each outer frame, use `strict=True` to check that each outer frame lies between the TS and the corresponding intermediate. A strict `pass` only proves that this path segment is directionally self-consistent, not that the TS is absolutely correct. Leave log parsing and criteria to the tools; do not write regex by hand.
- **Electronic-structure awareness**: call `electronic_analysis` for single-point electronic-structure checks — atomic charges (Mulliken/meta-Löwdin), Mayer bond orders (partial bond / incipient bond), IBO Lewis picture. For radical systems set `spin>1` (automatic UHF/UKS), locate the radical center from spin populations, and check `<S^2>` spin contamination.
- **Job submission**: always call `submit_compute_job`. For long jobs, set `is_async=True`.
- **MLIP engine via Gaussian**: when the task calls for a machine-learned potential (e.g. MACE-OMol25) instead of DFT — fast pre-screening, MLIP-level benchmarks — read `getskill("dft-calculation", other="mlip-gaussian-external.md")` for the `external="mace"` route, charge/multiplicity pass-through, and accuracy/fallback discipline.
- **Result parsing and thermochemistry**: prefer `log_parser` and related tools to extract energies, frequencies, and convergence; it auto-detects Gaussian vs ORCA logs (reported in the `engine` field) and returns the same field semantics for both — thermal corrections and total H/G separately, do not mix them. For multi-species ΔE/ΔH/ΔG use `thermo_analysis` with signed stoichiometric coefficients: `raw_rrho` is the log’s original RRHO; `goodvibes` is the explicit quasi-harmonic / low-frequency correction. Temperature, concentration, standard state, and single-point energy source must be reported with the result. Avoid `cat` on giant logs. For IRC/scan curves, use `format_converter` to turn the log into csv and read it programmatically (pandas/csv); do not hand-write regex against the log. **ORCA note**: IRC point counts, bidirectional convergence, and endpoint energies are extracted from the main output (the FORWARD/BACKWARD IRC iteration blocks and the IRC PATH SUMMARY) and feed the `short_irc` stage like Gaussian; only per-point *coordinates* live in the `*_trj.xyz` side files and are not extracted.

# 2. Constraints and exceptions (Constraints & Exceptions)
The following are common best practices with reasonable exceptions. When they conflict, prefer **the specific system, the target property, and the latest literature**.

1. **Input-file comments**: Gaussian’s official docs allow `!` comments, but in practice comments/blank lines in `.gjf` often break jobs across versions or parsers. Prefer no comments in the route section; put notes outside the file or in the title line, and always test on a small system first. [Gaussian Input Format](https://gaussian.com/input/)
2. **HF (Hartree–Fock)**: for most quantitative work, plain HF is not recommended because it lacks electron correlation. It still has value when:
   - used as a reference for DFT / post-SCF methods;
   - HF orbitals are needed as a guess for multi-reference, EOM, or strongly spin-contaminated open-shell systems (e.g. in Q-Chem, DFT orbitals can replace HF orbitals and vice versa);
   - dispersion-corrected HF (HFLD) is used specifically to analyze non-covalent interaction energies. [HFLD paper](https://pmc.ncbi.nlm.nih.gov/articles/PMC9009084/)
3. **MP2**: plain MP2 often performs poorly for weak interactions and transition metals; do not use it blindly. Variants such as MP2.5 and SCS-MP2 can still serve as comparison methods on some weak-interaction benchmarks.
4. **M06-2X and transition metals**: M06-2X was parameterized mainly for main-group thermochemistry, kinetics, and non-covalent interactions; risk is high for transition-metal systems (especially open-shell / strongly correlated). Prefer M06, PBE0-D3(BJ), TPSSh-D3(BJ), etc. If the system is dominated by light metals or main-group coordination and the property is sensitive to exchange–correlation, M06-2X may be used with benchmark validation. [M06 Suite](https://comp.chem.umn.edu/truhlar/docs/773fin_plus_supp_info.pdf)
5. **QST2 / QST3 (disabled)**: this project does not use Gaussian `Opt=QST2/QST3`. TS guesses go through a constrained scan (`ts_guess` scan_prepare generating modredundant input) or IDPP interpolation (`ts_guess` interpolate), then `Opt=(TS,noeigen,calcfc)`.
6. **Basis-set consistency**: IRC and vibrational analysis should in principle use the same basis as the geometry optimization so the PES is consistent; single-point energies may use a larger basis for extrapolation or energy correction.
7. **Diffuse functions**:
   - Polarizability, dipole moment, Rydberg states, or anions usually need diffuse functions (e.g. `def2-TZVPD`, `aug-cc-pVDZ`).
   - Bond-order analysis, population analysis, and NMR usually avoid diffuse functions, because diffuse primitives delocalize and dilute local analysis; if the object of study is itself a diffuse state (e.g. a weakly coordinating anion), keep diffuse functions and interpret cautiously.

# 3. Scientific knowledge base: functional and basis-set selection (Scientific Knowledge Base)
When setting `method` and `basis_set` in `qm_input_writer`, treat this section as general factual grounding; the final choice should combine system character and recent benchmarks.

## 3.1 Functional selection guide
*   **Typical accuracy order**: CCSD(T) > double-hybrid functionals > a well-chosen ordinary functional > MP2 > HF > semi-empirical methods.
*   **High/low pairing**: optimize and run frequencies with an ordinary functional (e.g. `B3LYP-D3(BJ)` for large systems), then compute single-point energies with a double hybrid (e.g. `wB97M(2)` or `PWPB95-D3(BJ)`).

| Task / system | Preferred / recommended functional | Alternative or special-case functional |
| :--- | :--- | :--- |
| **Main-group geometry and frequencies** | `B3LYP-D3(BJ)` | `wB97XD` for strongly conjugated systems |
| **Organic thermochemistry** (reaction energies, etc.) | `wB97M-V` | `M06-2X` |
| **Weak interactions of all kinds** | `wB97M-V`, `wB97X-V` | `PW6B95-D3(BJ)`, `M06-2X` |
| **Local excitations and general excited states** | `PBE0` (with TDDFT) | `CAM-B3LYP`, `wB97XD` (large conjugation / CT) |
| **Polarizability / dipole and other electrical properties** | `PBE0`, `wB97M-V` | `BHandHLYP` (large conjugation), `LC-wPBE` |
| **Strong multi-reference character / clusters** | `r2SCAN`, `TPSS` | `PBE0`, `MN15L` |
| **Transition metals (closed-shell reactions)** | `wB97X-V`, `wB97M-V` | `PBE0-D3(BJ)`, `TPSSh-D3(BJ)` |
| **Transition metals (open-shell reactions)** | `TPSS0-D4` | `PBE0-D4` |
| **NMR chemical shifts** | `B3LYP` (with scaling) | `revTPSS` (with pcSseg-1 basis) |

### 3.1.1 Multi-reference diagnosis and boundaries (keep r2SCAN/TPSS; do not switch to CAS on your own)
The table’s “strong multi-reference → `r2SCAN`/`TPSS`” is the **best mitigation inside a DFT framework**, not bad advice. The agent does not unilaterally switch to a full CASSCF workflow; the job is to **diagnose first, then annotate uncertainty**.

*   **When to suspect strong multi-reference**: ozone / Criegee intermediates; diradical borderline (some cycloaddition TSs); mid-homolysis; low-spin transition-metal polymorphism / near-degeneracy.
*   **Cheap diagnostics (may go in job keywords)**:
    *   xTB FOD: `xtb --fod` (fractional occupation density, Grimme 2015) — local FOD hotspots flag multi-reference regions;
    *   UDFT broken-symmetry + ⟨S²⟩ + Yamaguchi spin-projection correction;
    *   Wavefunction stability: `stable=opt` (Gaussian) / equivalent ORCA stability check;
    *   When a CCSD(T) single point exists, inspect the T1 diagnostic (main-group rule of thumb: T1 > 0.02 is a warning).
*   **If diagnostics are positive**: switch to / recheck `r2SCAN` or TPSS-class functionals; **explicitly annotate method uncertainty** in the conclusion; downgrade quantitative barrier claims to qualitative ranking; if needed, **recommend that the user** recheck with NEVPT2/CASPT2 single points — the agent **must not** declare quantitative reliability on its own.

## 3.2 Basis-set selection guide
Theoretical methods depend on basis sets in fundamentally different ways; do not mix evaluation standards. Pople (6-31G* family) and Karlsruhe def2 are **both usable**; keep one family consistent within a study — do not mix them and then compare barriers.

*   **Pople family (currently common)**: opt/freq `6-31G*` / `6-311G**`; anions and weak interactions add `+` / `++` diffuse.
*   **def2 family (recommended modern default)**:
    *   Pre-opt / coarse scan: `def2-SVP`
    *   Refined geometry and frequencies / routine single points: `def2-TZVP` (or `def2-TZVPP`)
    *   Anions, weak interactions, H-bonds / ion pairs: add diffuse `def2-TZVPD` or `ma-def2-SVP` / `ma-def2-TZVP`
*   **pcseg etc.**: high-accuracy single points may use `pcseg-2`.
*   **Task-specific basis advice**:
    *   **Weak-interaction energies**: the dominant system must add diffuse functions; BSSE correction is recommended.
    *   **Barrier calculations**: if compute allows, add a little diffuse (e.g. `ma-` / `def2-TZVPD`) or raise the zeta.
    *   **Relativistic calculations**: all-electron relativistic work must use dedicated bases (e.g. `cc-pVnZ-DK`); for 4th-period and heavier elements, strongly prefer ECP bases (def2-ECP paired with def2 valence bases).

## 3.3 Solvation decision tree
Write the solvent model into the condition assumptions, then choose a computational strategy (aligned with SMD hints in the mechanism files; this is the overall decision entry).

| Scenario | Recommendation | Keywords / action |
| :--- | :--- | :--- |
| Nonpolar, gas-phase experiment or control | Gas-phase geometry + gas-phase energy | do not set scrf |
| Need ΔG_solv / solution free-energy profile | **SMD** (preferred) | `scrf=(smd,solvent=...)`; report 1 M standard state |
| Geometry weakly solvent-dependent; only qualitative solvent effects | CPCM/PCM opt, or gas-phase opt then solvent single point | `scrf=(cpcm/pcm,solvent=...)` |
| Proton transfer, strong H-bonds on the reaction coordinate, tight ion pairs | Implicit + **1–3 explicit solvent molecules** | put explicit molecules in `distance_filters` / the reaction coordinate; do not rely on implicit only |
| Ionic mechanisms (SN1/E1, onium ions, bare charged intermediates) | **Must solvate** (at least SMD) | gas-phase profiles are badly distorted; do not report gas-phase ΔG‡ as a solution conclusion |

## 3.4 Fast methods tier: force field / xTB / MLP — when each is accurate enough
The accuracy ladder is not "DFT or nothing". For organic main-group systems the practical ordering is **MLP (foundation-model class) ≥ GFN2-xTB > classical force fields**, and each tier has a legitimate role — the skill is knowing where each one stops being trustworthy. Treat the table below as factual grounding; for the mechanics of driving an MLP through Gaussian (`external="mace"`, charge pass-through) see `getskill("dft-calculation", other="mlip-gaussian-external.md")`.

| Tier | Typical use where it is *reliable* | Where it breaks down |
| :--- | :--- | :--- |
| **Classical FF** (MMFF94/UFF, GAFF) | Generating clash-free 3D starting structures; coarse conformer pools on drug-like closed-shell neutrals | Any energy ranking that matters (no electronic structure); charged/TS/reactive systems |
| **GFN2-xTB** | Conformer ensembles + Boltzmann ranking of minima; pre-optimization before DFT; 1D pre-scans to locate a TS region; FOD multi-reference screening; implicit-solvent (ALPB) qualitative trends | **TS barriers quantitatively** (mean unsigned error vs DFT commonly 3–6 kcal/mol on organic barrier sets; larger for strained/element-rich TSs); larger or flexible TSs; strongly charged/zwitterionic profiles; halogen bonding & unusual bonding motifs |
| **MLP, foundation-model class** (MACE-OMol25, UMA, ORB, AIMNet2) | TS guess generation and pre-screening at near-DFT geometry quality (typical barrier errors ~1–3 kcal/mol on in-distribution closed-shell organics — roughly ωB97M-V/def2-TZVPD fidelity for OMol25); high-throughput geometry optimization; NEB/IRC-path pre-relaxation; conformer ranking when xTB errors matter but DFT is too slow; **charged species within the training charge range** (OMol25 covers anions with diffuse-function reference data) | Out-of-distribution chemistry: elements/bonding absent from training (many transition metals, exotic oxidation states); strongly multi-reference systems (inherits single-determinant reference limits); long-range charge transfer / large delocalized anions (short-range models); anything needing wavefunction analysis (no orbitals) |

Decision rules of thumb:

- **Geometry quality**: MLP ≥ DFT-pre-opt quality for in-distribution organics — an MLP-refined TS guess is usually a *better* DFT starting point than an xTB one, and dramatically cheaper.
- **Energies/barriers**: never report an xTB ΔG‡ as quantitative; an MLP barrier may anchor a *fast* conclusion or a benchmark data point, but the production barrier table still closes at DFT single points unless the study is explicitly about the MLP.
- **Charged systems**: prefer MLP over xTB for anion barriers when charge matters — GFN2-xTB handles atomic charges reasonably for minima but its error grows along ionic reaction coordinates; OMol25-class models were trained on charged species with diffuse functions.
- **Metals / open shells / MR**: none of the fast tiers is safe — xTB (GFN2 parametrization thin for many metals), MLPs (training coverage), so default to the DFT guidance in §3.1/§3.1.1.
- **Exploration discipline**: use the cheapest tier that can answer the *current* question — xTB to find *where* the TS region is, MLP to get a *good* guess, DFT to *prove* it.

*   **Opt vs single point**: if geometry is solvent-sensitive (ions, H-bond networks, polar TSs) → optimize + frequencies in implicit solvent; if sensitivity is low, gas-phase opt/freq then SMD single points on key structures is allowed (must be stated in the report).
*   Solution thermochemistry uses `thermo_analysis` `solution_1m` / `solution_custom`, aligned with experimental concentration.

# 4. Agent workflow: transition-state (TS) search (Workflow State Machine)
When the task is “transition-state search”, follow these procedural steps.
**For a full mechanism task (hypothesis → validation → barriers → report), you must read the extended material**: `getskill("dft-calculation", other="mechanism-elucidation-sop.md")` (end-to-end SOP, mechanism-hypothesis graph management, failure-diagnosis decision table); for modeling ideas and reaction assignment see `getskill("dft-calculation", other="reaction-class-geometry.md")` (five-question framework + reaction-outcome class index), then follow the index and load only the matching domain file `getskill("dft-calculation", other="mechanisms/<domain>.md")` (substitution/addition/carbonyl/elimination/pericyclic/radical/rearrangement/redox/coupling; each has that domain’s mechanism-hypothesis space, geometric predicates, and traps). Do not load every domain file at once.

If the current session is `dag_record` or `dag_guided`, you must also follow that SOP’s delivery-graph contract: the delivery DAG is the only persistent graph — the mechanism itself, whose elements owe ordered evidence **stages** (a TS edge owes `ts_opt` + `frequency` + short IRC + optimized endpoints + direction + identity; thermochemistry when required). Coordinator designs the mechanism and chooses stage contracts (`dag_propose_mechanism`, then `dag_add_species` / `dag_add_step` / `dag_update_delivery_element`); there is no process graph and no scheduling frontier. In `dag_guided` the Supervisor accepts the draft (`dag_accept_mechanism`) and reviews each finished delivery-relevant call (`dag_review_call`) to bind stages; in `dag_record` the proposal is auto-accepted and Coordinator self-binds with `dag_bind_evidence` + `stage_kind`. The SOP’s `C=COCC=C` → `C=CCCC=O` Claisen segment is a DAG-guided worked example of how stages fill step by step, not a generic reaction script. Neither `ts_guess`, a scan, nor a Supervisor suggestion can replace the independent TS, short IRC, optimized endpoints, direction check, and endpoint-identity-match stages required for endpoint-supported.

**Step 1: Modeling and a precise initial guess (Modeling & Initial Guess)**
- TS search is strict about the initial guess. Prefer SMILES of the core molecule from the web or a database, then convert to coordinates with system tools.
- If reactant/product SMILES are given, first use `reaction_mapping` to determine or explicitly choose an atom-mapping candidate, then pass the all-atom `atom_map` from concrete-structure binding to interpolation; mapping ambiguity itself is mechanism uncertainty that must be kept.
- **Structural insight and dragging**: call `internal_coordinates` (mode=analyze) as your “eyes”: anomalous bonds in the structure report (elongated / forming_candidate / clash), rotatable dihedrals, and the Reactive Center block point directly at breaking/forming sites; you may also edit Z-matrix numbers with `mode=zmatrix_to_cartesian` and convert back — lengthen the bond that will break, shorten the bond that will form, and sculpt a high-quality TS guess.
- Two main guess routes (see mechanism-elucidation-sop.md): ① when endpoints are known, use `ts_guess` interpolate for IDPP interpolation and take a candidate frame; ② use `ts_guess` scan_prepare to generate constrained-scan input (coordinate choice: reaction-class-geometry.md), submit, then scan_parse the profile and auto-extract a TS guess. To save compute, scan first at a semi-empirical level (e.g. xtb). **Note: xtb accuracy can be poor for TSs of larger molecules; if the scan looks pathological, rescan at the optimization level.**
- **Scan-cost discipline**: a scan is an exploration tool; cost explodes with dimension — a 1D scan is ~10–30 single points; a 2D scan is N×M (easily hundreds of single points). Default to 1D along the most critical reaction coordinate; use 2D only when two coordinates are confirmed to be strongly coupled and 1D cannot answer, and pre-scan with xtb before deciding on a DFT-level scan; state the reason and cost estimate in the report.
- Take a high-energy, small-gradient point as the TS guess. After finding a guess, show the structure to the user for confirmation before starting the formal search.

**Step 2: Build and submit (Build & Submit)**
- Call `qm_input_writer` to generate input.
- **Compute resources**: DFT itself is not extremely memory-hungry; for small molecules prefer more cores rather than more memory. For large molecules, Hessian memory use rises sharply and memory becomes the bottleneck.
- **Recommended keyword combination**: `opt=(ts,noeigen,calcfc)`. Adjust for convergence, e.g. add `maxstep=10` or `int=ultrafine`.
- `opt` and `freq` may be combined; that is standard Gaussian practice. A TS needs a unique imaginary frequency; include `freq` for verification.
- Call `submit_compute_job`. After there are no syntax errors, submit asynchronously (`is_async=True`).
- The system does not schedule jobs; multiple submissions default to async compute — be aware of the risk. For serial submission, submit one job at a time.
- For larger molecules (>=30 atoms), prefer serial submission; an ideal setup is cores per job not greater than 32, with essentially no upper bound on memory demand.

**Step 3: Run and validate IRC (IRC Validation)**
- The computational level should match the TS search. Keyword example: `irc=(lqa,calcfc,maxpoint=80)`.
- **Point-count threshold (aligned with evidence)**: bidirectional IRC needs **at least 50 valid points per direction**; `maxpoint=80` is a common start. If one side has fewer than 50 valid points or stalls early, increase `maxpoint` (or shrink the step) and rerun that direction; do not pass off an overly short IRC as endpoint-supported.
- *Logical validation*: plot the IRC curve. If it is not smooth (plateaus or noise), the TS is not accurate enough or is in the wrong place. You need not insist that the full IRC converge to minima: unconstrained-optimize the outermost valid frame on each side to get intermediates, then call `ts_guess mode=verify strict=True` to show that each partial endpoint lies between the TS and the corresponding optimized intermediate.
- *Endpoint identity*: then pass the two optimized intermediates as concrete structures to `reaction_mapping` and check molecular graphs against the elementary step’s expected endpoint SMILES. A `strict pass` and endpoint-graph match are two independent pieces of evidence; neither replaces the other.
- *Re-search strategy*: at this point add not only `maxstep=10` but also a finer integration grid (e.g. `int=ultrafine` or `int=superfine`) and recompute the TS.

**Step 4: Single-point energy (Single Point Energy)**
- **Finish Step 3 path/endpoint validation before expensive single points** (consistent with the SOP: do not waste high-level compute on the wrong saddle).
- Keep the geometry-optimization basis or upgrade per §3.2, drop `opt` and `freq`, raise the functional for the single-point energy; thermal corrections still come from the frequency-level log and are combined with `thermo_analysis`.

A TS-search task usually comes with mechanism finding. The general strategy: **center on the TS, run bidirectional partial IRC, unconstrained-optimize the outer frames on both sides to get intermediates, then assemble a full barrier from those structures**. Tools do not store task state such as “already validated”; they only judge the geometries passed in this call.

# 5. Diagnostics and circuit breakers (Circuit Breakers)
If `submit_compute_job` fails, or `log_parser` returns a parse anomaly, compare against these errors before retrying:

1. **Dispersion-conflict diagnosis**: check whether the current functional supports the chosen dispersion correction (e.g. M06-2X does not support GD3BJ).
2. **Pathological geometry**: if the Hessian cannot be computed, check for an obviously linear bond angle. If so, switch to Cartesian coordinates for geometry optimization.
3. **IRC step-size divergence**: if the step fails to converge, switch the algorithm to `lqa`.
4. **Abnormal IRC termination**: if it normal-terminates after only a few steps:
   - TS not smooth enough: raise precision and recompute a high-quality TS (see Step 4 re-search strategy).
   - Barrier too flat: try appending `extra_keywords="IOp(1/108=-1)"` in qm_input_writer to disable the convergence test.
5. **freq numerical crash**: sometimes freq crashes without a physical cause; after ruling out unreasonable distances, consider reading frequencies from an already-computed geometry-optimization file: geom=allcheck guess=read freq
6. **Suspected strong multi-reference**: see §3.1.1; do not silently write a single-reference DFT barrier as a quantitative conclusion.

# 6. Thermochemistry details and testable predictions
Before sending frequency-level results into `thermo_analysis`, align the following conventions (they may go in report assumptions).

*   **Frequency scale factors**: scale harmonic frequencies by functional/basis table values before computing thermal corrections. Typical magnitudes (starting points only; tables win): B3LYP/6-31G* ≈ 0.960; M06-2X commonly ≈ 0.97. See [NIST CCCBDB](https://cccbdb.nist.gov/vibscalejust.asp) or Truhlar harm_fac; GoodVibes can use `-v` / autodetection (see `thermo_analysis` `frequency_scale_factor`).
*   **Multi-conformer Boltzmann weighting**: when ΔG‡ has several accessible TS conformers, Boltzmann-weight the free energy, or at least report the lowest, next-lowest, and ΔΔG. Do not report only conf0.
*   **Eyring rate constant** (transition-state theory): `k = (k_B T / h) * exp(-ΔG‡ / RT)`. The standard state must match ΔG‡ (1 atm vs 1 M); for bimolecular steps state concentration units; this is classical TST and **does not include tunneling**.
*   **Tunneling**: hydrogen (deuterium) transfer and HAT/proton transfer with a significant imaginary frequency should note possible Wigner / Eckart corrections; enable them when a quantitative k or primary KIE is needed, and annotate the conclusion.
*   **One-sentence KIE protocol**: predicted kinetic isotope effects can use frequency data + the Bigeleisen–Mayer equation (tools such as Kinisot); treat computed KIE as a testable mechanism prediction to compare with experiment, not a post-hoc gloss.
*   **ΔΔG‡ → selectivity**: see `reaction-class-geometry.md` §3.3 (e.g. at 298 K, ≈1.4 / 2.7 kcal/mol corresponds to about 10:1 / 100:1).
