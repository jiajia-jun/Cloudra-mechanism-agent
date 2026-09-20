---
name: dft-calculation
description: Use when planning or running molecular/cluster mechanism calculations, TS searches, relaxed scans (1D/2D), NEB paths, frequencies, IRC, or barrier calculations with Gaussian/ORCA, including external MLIP potentials; also for method selection and calculation failures. For periodic solids use first-principles-calculation.
---

# Molecular mechanism calculations

Choose the next calculation by the scientific question it resolves. A completed job is evidence about its actual input, not automatically proof of the intended species or transition state. Invest in the model and the initial guess — never in optimizer-parameter heroics.

## Start here

1. Record the requested quantity and reference: mechanism/connectivity, electronic barrier ΔE‡, free-energy barrier ΔG‡, selectivity, or another property. Record composition, charge/multiplicity, conditions (solvent, counterions, temperature), allowed methods and budget. Decide what validation that claim needs **before** computing, and run the modeling self-audit in [modeling sanity](references/modeling-sanity.md): solvent/ions, conformer sampling, spin states, standard state — a model that fails the audit is not worth a single core-hour.
   **Honor the project/session method policy first** (`MethodPolicy` / allowed methods, e.g. production `xtb`+`b3lyp/def2svp` — combo entries pin the basis; `b3lyp` with any other basis or none is blocked). Do not pick a freer functional from [method selection](references/method-selection.md) when the policy already constrains the choice; freer candidates apply only when policy and budget allow a justified comparison.
   Use `agent_hub(action="search", keyword="<reaction or concrete calculation problem>")` early to reuse local chemical knowledge and project findings. Search again when an unfamiliar engine setting or a new failure needs diagnosis, before guessing parameters or repeating calculations. Inspect both `library` and `posts`; `browse` alone does not search the knowledge library. **When the scientific call needs external grounding** (standard-state/quasi-harmonic protocol, functional applicability, whether a literature barrier is trustworthy), also use the researcher role / `literature-search` skill — do not invent numbers from memory.
2. For mechanism work, read [the mechanism SOP](references/mechanism-elucidation-sop.md). When candidate pathways are unknown, generate hypotheses first with `mechanism_predict` (FlowER ML elementary-step network search from reactant SMILES; on by default via `flower.enabled`) — **verifying or ruling out a predicted step is far cheaper than inventing the mechanism from scratch**. Its network is **reference-only**: the per-step probabilities are beam-search scores, not calibrated confidence — a high-probability edge can be wrong and a missing edge means nothing. Nothing from it may be reported as a finding; every edge still goes through the TS/IRC validation below. **First reaction to any structure is `internal_coordinates`** — read forming/breaking pairs, dihedrals and anomalies from its report, never parse coordinates by hand.
3. TS seeds, in order of reliability (details and per-engine recipes in [the TS playbook](references/ts-search-playbook.md)):
   1. **`ts_prepare`** — declare endpoints (SMILES + `atom_map` + `reaction_center`); the process builds, maps, assembles, guesses, validates, submits, refines and judges autonomously; when it stops `blocked` it names the offending declaration, fix that and `ts_resume` (do not poll).
   2. **Mapped interpolation → NEB** — `ts_guess mode=interpolate` (IDPP preferred) or an ORCA `NEB-TS` job; the strongest agent-side lever when endpoints and the all-atom map are known. **NEB is the ceiling of sophistication: QST2/QST3 are banned outright** (see red lines).
   3. **Relaxed scan (1D or 2D)** — `ts_guess scan_prepare` / `scan_parse`, then a fresh unconstrained TS refine from the peak frame. Scans are a normal research-group workflow, not a last resort: use 2D when two coordinates move concertedly or a 1D profile jumps/discontinues. The peak is a seed, never a deliverable.
   Never blind-OptTS from a minimum or from a SMILES embedding. A manual chain (direct OptTS/IRC submission) is a sanctioned exception, but it must leave a one-line justification in the trajectory — the harness pins this reminder when it sees a TS/IRC submission.
4. Before writing inputs, read **only the active engine's recipe**: [ORCA](references/orca-inputs.md) or [Gaussian](references/gaussian-inputs.md). External potentials additionally need [MLIP interface and limits](references/mlip-gaussian-external.md). Inspect generated inputs: the shared writer does not translate all engine options.

Load a reference with `get_skill(skill_name="dft-calculation", reference="ts-search-playbook.md")`, replacing the reference name as needed.

## Red lines (hard stops, no exceptions)

- **No QST2/QST3, ever.** Their synchronous transit interpolation fails systematically when the averaged endpoint geometry is unphysical, and they offer no path correction — NEB or scans dominate them on every axis. The ceiling is NEB.
- **No bare ions in vacuum.** Any mechanism containing ions, zwitterions, or strong charge separation runs in implicit solvent from the start (geometry, frequencies, TS, IRC) — gas-phase bare-ion PESs are artifacts (barrierless proton slides, runaway charge separation, unstable anions). See [modeling sanity](references/modeling-sanity.md) for counterion/explicit-water and standard-state rules.
- **No single-conformer barriers.** Conformational neglect gives qualitatively wrong activation energies, and TS-conformer cherry-picking can manufacture any selectivity conclusion. Sample with `conformer_search` before barrier claims; verify poses with `internal_coordinates`.
- **No TS delivery without the three-part check**: optimization converged (engine's own marker, never exit code 0) + exactly one imaginary frequency at the **same level** + that mode's displacement lives on the reacting heavy atoms + IRC connectivity to both endpoints. An imaginary mode carried by methyl rotation, loose torsions, or proton wobbles on a floppy ion–molecule complex is a **pseudo-saddle** — treat as unresolved, not as a TS. Judge the mode by its composition, not its number: `log_parser`'s `imaginary_modes` (pass the step's bond-change pairs as `watch_pairs`) shows where the displacement lives.
- **Soft modes are a convergence warning, not a detail.** H-bonded/ion–molecule complexes and floppy chains poison the Hessian with near-zero eigenvalues; TS optimizations on them often cannot converge. Pre-organize, constrain irrelevant floppy modes, use wall potentials or fragment constraints, and expect loose-TS/ensemble questions instead of forcing a single-structure answer (playbook §Soft modes).
- **Constrained optimization converged ≠ stationary point; scan peak ≠ TS; exit code 0 ≠ valid job.** Evidence comes only from engine convergence markers, frequencies, and parsed logs.
- **No parameter-tuning loops.** After a failed TS attempt, the next move is a better guess (new conformer/path/endpoint geometry), not `MaxStep`/iop fiddling stacked onto every retry. Change the physics, not the knobs.
- **xTB energies never enter a delivered barrier.** GFNn-xTB underestimates barriers by ~12 kcal/mol MAE; it is a geometry/sampling layer only — every reported energy is DFT-level.

## Decisions that prevent wasted work

| Observation | Next action |
| --- | --- |
| Constrained optimization converged; frequency has one imaginary mode | Treat as a seed. Remove constraints, refine the TS and check the full gradient. |
| No TS seed yet | `ts_prepare` first; then mapped interpolation/NEB; then 1D/2D relaxed scan from `internal_coordinates` indices. Never blind-OptTS from a minimum. |
| TS optimization repeatedly enters the same minimum | Change the conformer/path/coordinate based on evidence, or stop with the unresolved claim. More iterations alone do not change the search. |
| TS optimization oscillates on a floppy/ionic complex (energy and RMS force not falling, steps pinned at trust radius) | Soft-mode regime: pre-organize the complex, constrain or freeze irrelevant floppy modes, consider a wall potential, cheap-level Hessian (`InHess XTB2`), small fixed trust radius. Expect a possible no-convergence outcome and record it as such. |
| A relaxed scan is monotonic | Re-check atom indices and preorganization with `internal_coordinates`. It neither proves barrierlessness nor makes every method unusable. |
| A 1D scan jumps/discontinues between points | The true coordinate is higher-dimensional: go 2D or switch to NEB. |
| Mechanism step involves ions/zwitterions and the model is gas-phase | Remodel with implicit solvent before any further compute; check whether a counterion or 2–3 explicit waters belong in the system. |
| Barrier/selectivity claim on a flexible molecule without conformer sampling | Run `conformer_search` first; re-rank at DFT level before quoting numbers. |
| Concrete endpoint identity mismatches | Preserve the intended species and the observed structure; stop dependent claims. Mapping ambiguity with matching identities is a separate issue. |
| Both IRC directions actually converged | Check optimized endpoint identities and path continuity; do not rerun just to reach 50 points. |
| Allowed methods cannot support the requested claim | State the specific limitation and preserve evidence. Do not silently switch methods or fabricate a completed stage. |

## Tools and working rules

- **Prefer the dedicated tools over `bash` everywhere.** Structure: `name_to_structure` / `smiles_to_mol` / `format_converter` / `internal_coordinates`; ensembles: `conformer_search`; TS: `ts_prepare` / `ts_guess`; inputs: `qm_input_writer`; execution: `submit_compute_job` / `query_compute_job` / `query_compute_queue`; results: `log_parser` / `thermo_analysis` / `electronic_analysis` / `irc` checks via `ts_guess strict`. Never hand-parse logs or coordinates with grep/awk/python one-liners — the dedicated parsers carry validated domain logic (frame extraction, frequency blocks, IRC endpoint proofs). Never invent Cartesian coordinates. Reach for `bash` only when no tool covers the action, and say why.
- **`internal_coordinates` before TS work**: read out forming/breaking pairs and dihedrals, flag clashes/anomalies, and drive geometry edits from there — Z-matrix flow, or `mode="transform"` for internal-coordinate-style edits (rotate a group about an axis, stretch/compress a bond, invert a chiral center, or replace a substituent with a SMILES-defined group — a topology edit where one `[*]` dummy marks the attachment point) with automatic post-edit clash/angle validation; see the SOP for the operations JSON. A SMILES-generated minimum is not a TS seed.
- Interpolation needs `binding_status=complete`, `binding_source=concrete` and the all-atom map. `internal_generated` maps do not index arbitrary XYZ files. Use `reaction_mapping` on concrete structures.
- Use `conformer_search` when conformational alternatives matter — which is always for flexible molecules. Its `distance_filters` select candidates; they do not freeze distances during later optimization. Dihedral/angle preorganization is not expressible in `distance_filters` — screen by distance, then **verify with `internal_coordinates`** and discard non-reactive poses before scanning.
- Generate with `qm_input_writer` / `ts_guess scan_prepare`; submit with `submit_compute_job`, matching engine, CPUs and memory. The scheduler handles capacity. Use asynchronous work when other useful work remains; existing authorization does not require another seed-approval checkpoint.
- When delivery/benchmark evidence binding requires it, ensure generated inputs/logs carry a `smiles: <SMILES>` annotation line (canonical delivery form). A writer `expected_smiles:` comment on SMILES-sourced jobs is a declaration of intent, not proof of identity.
- Parse with `log_parser`, `thermo_analysis`, `ts_guess` and `format_converter`. Keep full files and stable evidence pointers; pass compact findings and paths between agents. **Record failures with their diagnosis as faithfully as successes** — one-shot TS success is well under half in practice, and an undocumented failure guarantees the same machine time gets burned again.
- Share reusable findings and failed approaches through `agent_hub(action="post", kind="finding", topic=..., content=...)`, including conditions, conclusion, limits and evidence paths. Notify the affected agent with `to_agent` when the finding changes their next action. Reuse existing search results while the question is unchanged.

## Read when needed

- [TS search playbook](references/ts-search-playbook.md): seed hierarchy, QST ban rationale, NEB-TS workflow, 1D/2D scan practice, OptTS convergence ladder, soft-mode regimes, imaginary-mode chemical assignment — with per-engine templates.
- [Modeling sanity](references/modeling-sanity.md): the pre-compute self-audit — solvent/ions/counterions, conformer sampling, spin states, standard states, and the unreasonable-modeling blacklist.
- [Reaction-class geometry](references/reaction-class-geometry.md): hypothesis and coordinate selection; then load only the relevant `mechanisms/<domain>.md` reference.
- [Method selection](references/method-selection.md): functionals, bases, solvent, method limits; **§4.1 is the mandatory ΔG‡/ΔΔG‡ checklist** (standard state, quasi-harmonic, Boltzmann, cross-engine ban).
- [Supervisor review](references/supervisor-review.md): how the scientific Supervisor adjudicates drafts, evidence, and exit requests; what a contract requires and what it must not add.
- DAG-guided / DAG-record sessions: SOP §3 and the `dag-operations` skill for current permissions and bindings. Evidence may be computed independently; current stage binding is still ordered. Graph completion does not establish scientific validity.
