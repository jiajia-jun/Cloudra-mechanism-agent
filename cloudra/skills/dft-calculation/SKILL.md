---
name: dft-calculation
description: Use when planning or running molecular/cluster mechanism calculations, TS searches, relaxed scans, frequencies, IRC, or barrier calculations with Gaussian/ORCA, including external MLIP potentials; also for method selection and calculation failures. For periodic solids use first-principles-calculation.
---

# Molecular mechanism calculations

Choose the next calculation by the scientific question it resolves. A completed job is evidence about its actual input, not automatically proof of the intended species or transition state.

## Start here

1. Record the requested quantity and reference: mechanism/connectivity, electronic barrier ΔE‡, free-energy barrier ΔG‡, selectivity, or another property. Record composition, charge/multiplicity, conditions, allowed methods and budget. Decide what validation that claim needs before computing.
   Use `agent_hub(action="search", keyword="<reaction or concrete calculation problem>")` early to reuse local chemical knowledge and project findings. Search again when an unfamiliar engine setting or a new failure needs diagnosis, before guessing parameters or repeating calculations. Inspect both `library` and `posts`; `browse` alone does not search the knowledge library. See the SOP's AgentHub guidance.
2. For mechanism work, read [the mechanism SOP](references/mechanism-elucidation-sop.md). Check concrete endpoint identities; prepare a reactive conformer, relaxed scan or mapped interpolation; refine a candidate without constraints; check stationarity and its imaginary mode; establish connectivity; calculate the requested energy difference.
3. Before writing inputs, read **only the active engine's recipe**: [ORCA](references/orca-inputs.md) or [Gaussian](references/gaussian-inputs.md). External potentials additionally need [MLIP interface and limits](references/mlip-gaussian-external.md). Inspect generated inputs: the shared writer does not translate all engine options.

Load a reference with `get_skill(skill_name="dft-calculation", reference="orca-inputs.md")`, replacing the reference name as needed.

## Decisions that prevent wasted work

| Observation | Next action |
| --- | --- |
| Constrained optimization converged; frequency has one imaginary mode | Treat as a seed. Remove constraints, refine the TS and check the full gradient. |
| TS optimization repeatedly enters the same minimum | Change the conformer/path/coordinate based on evidence, or stop with the unresolved claim. More iterations alone do not change the search. |
| A relaxed scan is monotonic | Inspect the sampled coordinates and structures. It neither proves barrierlessness nor makes every method unusable. |
| Concrete endpoint identity mismatches | Preserve the intended species and the observed structure; stop dependent claims. Mapping ambiguity with matching identities is a separate issue. |
| Both IRC directions actually converged | Check optimized endpoint identities and path continuity; do not rerun just to reach 50 points. |
| Allowed methods cannot support the requested claim | State the specific limitation and preserve evidence. Do not silently switch methods or fabricate a completed stage. |

## Tools and working rules

- Obtain coordinates from `name_to_structure`, `image_to_smiles`, `smiles_to_mol`, existing files or logs. Never invent Cartesian coordinates; use `internal_coordinates` for analysis and Z-matrix edits. A SMILES-generated minimum is not a TS seed.
- Use `reaction_mapping` on concrete structures. Interpolation needs `binding_status=complete`, `binding_source=concrete` and the all-atom map. `internal_generated` maps do not index arbitrary XYZ files.
- Use `conformer_search` when conformational alternatives matter. Its `distance_filters` select candidates; they do not freeze distances during later optimization.
- Generate with `qm_input_writer` / `ts_guess scan_prepare`; submit with `submit_compute_job`, matching engine, CPUs and memory. The scheduler handles capacity. Use asynchronous work when other useful work remains; existing authorization does not require another seed-approval checkpoint.
- Parse with `log_parser`, `ts_guess` and `format_converter`. Keep full files and stable evidence pointers; pass compact findings and paths between agents. Record failures as well as successes.
- Share reusable findings and failed approaches through `agent_hub(action="post", kind="finding", topic=..., content=...)`, including conditions, conclusion, limits and evidence paths. Notify the affected agent with `to_agent` when the finding changes their next action. Reuse existing search results while the question is unchanged.

## Read when needed

- [Reaction-class geometry](references/reaction-class-geometry.md): hypothesis and coordinate selection; then load only the relevant `mechanisms/<domain>.md` reference.
- [Method selection](references/method-selection.md): functionals, bases, solvent, method limits and thermochemistry conventions.
- [Supervisor review](references/supervisor-review.md): how the scientific Supervisor adjudicates drafts, evidence, and exit requests; what a contract requires and what it must not add.
- DAG-guided / DAG-record sessions: SOP §3 and the `dag-operations` skill for current permissions and bindings. Evidence may be computed independently; current stage binding is still ordered. Graph completion does not establish scientific validity.
