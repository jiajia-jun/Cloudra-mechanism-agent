---
name: dft-calculation
description: Use when planning or running molecular/cluster mechanism calculations, TS searches, relaxed scans, frequencies, IRC, or barrier calculations with Gaussian/ORCA, including external MLIP potentials; also for method selection and calculation failures. For periodic solids use first-principles-calculation.
---

# Molecular mechanism calculations

Choose the next calculation by the scientific question it resolves. A completed job is evidence about its actual input, not automatically proof of the intended species or transition state.

## Start here

1. Record the requested quantity and reference: mechanism/connectivity, electronic barrier ΔE‡, free-energy barrier ΔG‡, selectivity, or another property. Record composition, charge/multiplicity, conditions, allowed methods and budget. Decide what validation that claim needs before computing.
   **Honor the project/session method policy first** (`MethodPolicy` / allowed methods, e.g. production `xtb`+`b3lyp/def2svp` — combo entries pin the basis; `b3lyp` with any other basis or none is blocked). Do not pick a freer functional from [method selection](references/method-selection.md) when the policy already constrains the choice; freer candidates apply only when policy and budget allow a justified comparison.
   Use `agent_hub(action="search", keyword="<reaction or concrete calculation problem>")` early to reuse local chemical knowledge and project findings. Search again when an unfamiliar engine setting or a new failure needs diagnosis, before guessing parameters or repeating calculations. Inspect both `library` and `posts`; `browse` alone does not search the knowledge library. **When the scientific call needs external grounding** (standard-state/quasi-harmonic protocol, functional applicability, whether a literature barrier is trustworthy), also use the researcher role / `literature-search` skill — do not invent numbers from memory. See the SOP's AgentHub guidance.
2. For mechanism work, read [the mechanism SOP](references/mechanism-elucidation-sop.md). When candidate pathways are unknown, generate hypotheses first with `mechanism_predict` (FlowER ML elementary-step network search from reactant SMILES; requires `flower.enabled`, hidden when disabled) — **verifying or ruling out a predicted step is far cheaper than inventing the mechanism from scratch**. Its network is hypotheses, not computational evidence: every edge still goes through the TS/IRC validation below. **First reaction to any structure is `internal_coordinates`** — read forming/breaking pairs, dihedrals and anomalies from its report, never parse coordinates by hand. **Default TS search: declare the endpoints (SMILES + `atom_map` + `reaction_center`) and call `ts_prepare`** — the process builds, maps, assembles, guesses, validates, submits, refines and judges autonomously; when it stops `blocked` it names the offending declaration, fix that and `ts_resume` (do not poll). A **relaxed scan** (`ts_guess scan_prepare` / `scan_parse` → unconstrained TS refine from the peak) is the fallback for cases the process cannot take — and scanning is precisely the lever the process does not have. Then check stationarity and its imaginary mode; establish connectivity; calculate the requested energy difference.
3. Before writing inputs, read **only the active engine's recipe**: [ORCA](references/orca-inputs.md) or [Gaussian](references/gaussian-inputs.md). External potentials additionally need [MLIP interface and limits](references/mlip-gaussian-external.md). Inspect generated inputs: the shared writer does not translate all engine options.

Load a reference with `get_skill(skill_name="dft-calculation", reference="orca-inputs.md")`, replacing the reference name as needed.

## Decisions that prevent wasted work

| Observation | Next action |
| --- | --- |
| Constrained optimization converged; frequency has one imaginary mode | Treat as a seed. Remove constraints, refine the TS and check the full gradient. |
| No TS seed yet | Declare endpoints and start `ts_prepare`; fall back to a **relaxed scan** from `internal_coordinates` indices when the process cannot take the case. Never blind-OptTS from a minimum. |
| TS optimization repeatedly enters the same minimum | Change the conformer/path/coordinate based on evidence, or stop with the unresolved claim. More iterations alone do not change the search. |
| A relaxed scan is monotonic | Re-check atom indices and preorganization with `internal_coordinates`. It neither proves barrierlessness nor makes every method unusable. |
| Concrete endpoint identity mismatches | Preserve the intended species and the observed structure; stop dependent claims. Mapping ambiguity with matching identities is a separate issue. |
| Both IRC directions actually converged | Check optimized endpoint identities and path continuity; do not rerun just to reach 50 points. |
| Allowed methods cannot support the requested claim | State the specific limitation and preserve evidence. Do not silently switch methods or fabricate a completed stage. |

## Tools and working rules

- Obtain coordinates from `name_to_structure`, `image_to_smiles`, `smiles_to_mol`, existing files or logs. Never invent Cartesian coordinates. **Use `internal_coordinates` before TS work**: read out forming/breaking pairs and dihedrals, flag clashes/anomalies, and drive geometry edits from there — Z-matrix flow, or `mode="transform"` for internal-coordinate-style edits (rotate a group about an axis, stretch/compress a bond, invert a chiral center) with automatic post-edit clash/angle validation; see the SOP for the operations JSON. A SMILES-generated minimum is not a TS seed.
- TS seeds come from `ts_prepare` first; a **relaxed scan** is the agent-side fallback (the process does not scan). Scan peak → fresh unconstrained TS job; never blind-OptTS from a non-TS geometry. Use `reaction_mapping` on concrete structures. Interpolation needs `binding_status=complete`, `binding_source=concrete` and the all-atom map. `internal_generated` maps do not index arbitrary XYZ files.
- Use `conformer_search` when conformational alternatives matter. Its `distance_filters` select candidates; they do not freeze distances during later optimization. Dihedral/angle preorganization is not expressible in `distance_filters` — screen by distance, then **verify with `internal_coordinates`** and discard non-reactive poses before scanning.
- Generate with `qm_input_writer` / `ts_guess scan_prepare`; submit with `submit_compute_job`, matching engine, CPUs and memory. The scheduler handles capacity. Use asynchronous work when other useful work remains; existing authorization does not require another seed-approval checkpoint.
- When delivery/benchmark evidence binding requires it, ensure generated inputs/logs carry a `smiles: <SMILES>` annotation line (canonical delivery form). A writer `expected_smiles:` comment on SMILES-sourced jobs is a declaration of intent, not proof of identity.
- Parse with `log_parser`, `ts_guess` and `format_converter`. Keep full files and stable evidence pointers; pass compact findings and paths between agents. Record failures as well as successes.
- Share reusable findings and failed approaches through `agent_hub(action="post", kind="finding", topic=..., content=...)`, including conditions, conclusion, limits and evidence paths. Notify the affected agent with `to_agent` when the finding changes their next action. Reuse existing search results while the question is unchanged.

## Read when needed

- [Reaction-class geometry](references/reaction-class-geometry.md): hypothesis and coordinate selection; then load only the relevant `mechanisms/<domain>.md` reference.
- [Method selection](references/method-selection.md): functionals, bases, solvent, method limits; **§4.1 is the mandatory ΔG‡/ΔΔG‡ checklist** (standard state, quasi-harmonic, Boltzmann, cross-engine ban).
- [Supervisor review](references/supervisor-review.md): how the scientific Supervisor adjudicates drafts, evidence, and exit requests; what a contract requires and what it must not add.
- DAG-guided / DAG-record sessions: SOP §3 and the `dag-operations` skill for current permissions and bindings. Evidence may be computed independently; current stage binding is still ordered. Graph completion does not establish scientific validity.
