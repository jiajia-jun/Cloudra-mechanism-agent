# Guided Cyclic Preorganization — Design

**Date:** 2026-09-24
**Status:** Design for review; implementation has not started.

## Intent and success criteria

The problem is generating a reactant or reactant complex that already has the spatial arrangement needed for a cyclic transition-state guess. The user wants an Agent to name the atoms **in ring order**, and to keep the prospective ring contacts near Agent-specified distances *throughout* conformer search. The same search may also guide an unrelated atom-pair distance. Both intramolecular folding and multicomponent assembly must work. `ts_prepare` must use the guided reactant candidate when the declaration includes it.

Success means a caller can request, for example, a six-atom prospective cycle and one additional donor–acceptor distance, receive candidate geometries whose declared distances meet the requested windows, and see an explicit failure with atom-level diagnostics when no candidate qualifies. The output is a **TS seed**, not an optimized reactant minimum or evidence of a transition state.

## Current behavior and why it is insufficient

- `conformer_search.distance_filters` runs after RDKit/CREST generation and optimization. It labels passing candidates and rescues one from energy/window clustering, but does not guide sampling; zero matches can still yield `is_success=True`.
- RDKit single-component sampling embeds by ETKDGv3 and then runs unconstrained MMFF/UFF optimization. A high-strain ring-like arrangement can therefore be absent or relax away.
- The shared multicomponent builder uses `complex_assembly`, which can guide placement by `reaction_center`, but `conformer_search` does not expose a durable ring-order declaration. Its present reaction-mode constraint is conditionally released.
- `ts_prepare` builds the endpoints independently and does not consume the `conformer_search` ensemble. A conformer-tool change alone would not affect its default TS path.
- CREST supports an xTB-format constraint file (`--cinp`) for its search, but the current runner does not stage one for this use. Its topology-change report is observational and cannot serve as a requested-cycle predicate.

## Approach

Use **orthogonal guidance fields**, not a new value in the existing `mode` enum. `mode` continues to choose the CREST run type (`conformers`, `nci`, etc.); guidance determines the geometric bias within a supported run type. This lets `mode="nci"`, ring guidance, and an independent distance guide coexist.

Increasing the number of unconstrained trials or tightening a post-search filter cannot guarantee that a ring-like candidate is generated. A full Cartesian template would freeze the very torsions that need to vary and would require a separate template library. The selected approach adds soft, atom-pair distance restraints during generation and local relaxation, then checks actual output geometry.

## Public declaration and atom identity

`conformer_search` gains two optional fields:

```json
{
  "ring_guidance": {
    "atom_order": [1, 2, 3, 4, 5, 6],
    "forming_contacts": [
      {"atoms": [6, 1], "target_ang": 2.2, "tolerance_ang": 0.3}
    ]
  },
  "distance_guidance": [
    {"atoms": [2, 9], "target_ang": 2.8, "tolerance_ang": 0.2}
  ]
}
```

The example numbers illustrate the shape of the input, **not** default chemical targets. The Agent must set a target and tolerance for **each** nonbonded consecutive pair of `atom_order`, including the last-to-first pair. It may guide other atom pairs independently. A bonded consecutive pair has its ordinary covalent geometry and does not need a new target. The tool validates that the listed order is one simple cycle (at least three unique atoms), that every forming-contact pair is a missing consecutive edge, and that no missing edge is undeclared. Duplicate guidance on the same pair must agree on its target window; incompatible windows fail before launching a search. Targets/tolerances must be finite and positive.

The new guidance fields refer to **1-based source atom order before automatic hydrogen addition**. For SMILES this is the input molecule's parsed atom order; for MOL/SDF/XYZ it is the source atom order. The shared builder's `AtomIdentity` table translates these references into the complete generated structure, including component reordering and added hydrogens. An explicitly represented hydrogen can be selected; an automatically added hydrogen cannot be named by source index. The result reports both source and resolved output indices. Existing `distance_filters` retains its current 1-based resolved-output convention for compatibility; the tool description must state this difference plainly. `distance_guidance` also works without `ring_guidance`.

`TsDeclaration` and `TsAdjustment` gain the **same** guidance structure for the reactant side. The explicit source-index convention lets `ts_prepare` resolve guidance before choosing its first geometry. A correction via `ts_resume` reruns the dependent reactant build, assembly, guess and validation while retaining the previous attempt's artifacts. It never silently reuses a seed built under old guidance.

## Search behavior

### Single connected component

The shared structure parser resolves the graph and atom identity first. For a guided RDKit search, ETKDG's distance-bounds matrix is narrowed for the prospective contacts and any extra distance guides before embedding. An impossible bounds matrix fails with the offending atom pairs. Each embedded candidate is relaxed with *soft* MMFF distance restraints; the ring atoms are not frozen in Cartesian space, so torsions and ring puckering can still vary. The ordinary unrestrained MMFF optimization path remains unchanged when guidance is absent.

For a guided CREST search, generate a usable guided seed first and stage a run-local xTB constraint file. CREST receives it with `--cinp` so the declared contacts remain guided during its optimization and sampling. Existing covalent ring-path edges are restrained around their seed lengths in CREST to guard against method-level topology changes; prospective contacts use the Agent's explicit targets. Constraint file, engine command, seed, and all returned frames remain inspectable. The MMFF path reuses the project's approved `MMFF_CONSTRAINT_FORCE_CONSTANT=100.0`; the CREST path uses its documented 0.02 Eh/Bohr^2 default. Both are soft harmonic restraints; the effective force and target are recorded, and neither fixes Cartesian coordinates.

### Multiple components

Resolve the cycle across components before placement. Extend the existing reaction-centre orientation scoring and constrained MMFF relaxation in `complex_assembly` to use **all** missing consecutive ring edges and independent distance guides. The explicit guided path keeps those soft restraints through candidate delivery; it does not take the existing conditional-release branch. The normal assembly path retains its current behavior. If CREST `nci` is selected, pass a qualifying guided complex as its seed and apply the same run-local constraints through `--cinp`.

### Modes and unsupported combinations

Guidance is supported with ordinary `conformers` search and CREST `nci`. `qcg` creates new solvent atoms whose indices do not exist when the request is declared; a caller first grows the cluster, then runs guided `nci` on its fixed atom list. `protonate`, `deprotonate`, and `tautomerize` change species or atom identity and reject ring guidance explicitly. Existing calls without guidance keep their current mode behavior.

## Candidate checks and outputs

Every generated frame is checked against all declared contact windows, atom identity/order, clashes, and unexpected covalent connectivity changes. A target window whose lower edge is nonpositive is rejected up front. Contact distances are geometric facts, not proof of a new bond or a saddle point. Guided output retains only qualifying candidates after diversity clustering; if none qualify, it returns `is_success=False`, counts by rejection reason, the closest attempted geometry when one exists, and persistent diagnostic paths. It does not turn a partial or failed CREST run into success.

Guided candidates are labeled `seed_kind="constrained_preorganization"`. Their restraint-biased energies are not reported as ordinary conformer energies or used for Boltzmann populations or the ordinary energy-window cutoff. The output lists achieved distances, deviations, constraint provenance and geometry paths. Any later unconstrained relaxation or electronic-structure ranking is a separate calculation with its own status.

## TS process integration

When `TsDeclaration` includes guidance, the reactant build uses the shared guided-search service and stores the selected qualifying candidate path and its constraint manifest in the process record. Product building and atom mapping continue under their existing scientific checks. The guess stage reads the selected guided reactant path in place of the ordinary minimum. A guided search with no qualifying candidate becomes a `TsBlocked` result naming the problematic source/resolved atom pairs and the closest attempted distances. An absent guidance declaration leaves the existing `ts_prepare` path unchanged. A constrained seed cannot by itself satisfy TS frequency, IRC, DAG evidence, or benchmark accuracy gates.

The reusable implementation belongs in a focused core preorganization module called by the `conformer_search` tool and `ts_process`, rather than calling the tool wrapper from the process. `crest_runner` only stages the declared constraint file and records it; `complex_assembly` only implements guided placement/relaxation. Each module keeps its current un-guided behavior by default.

## Verification and documentation

- RDKit intramolecular test with a fixed molecule and seed: guided sampling produces a conformer whose ring edges and extra distance lie inside their windows; the un-guided regression retains its old result shape.
- Multicomponent test: two or more prospective closure contacts guide relative placement; the constraints remain active to the delivered candidate.
- CREST command/fixture test: `--cinp` points to a run-local file with the correct resolved atoms; a failed engine or mismatching output is not accepted.
- Validation tests: repeated/out-of-range atoms, missing/extra forming contacts, impossible and conflicting windows, unsupported run types, no qualifying candidate, added-H indexing and source-to-output translation.
- TS scenario test: guided declaration selects the seed for the guess; failure blocks with atom-level diagnostics; a corrected `ts_resume` keeps the previous attempt's artifacts and does not reuse its seed.
- Run syntax, focused tests, lint and the frontend build only if frontend files change; repository policy leaves the full Python suite to CI unless the user requests it.
- Update the tool descriptions, `cloudra/skills/dft-calculation/SKILL.md`, `docs/TS_PROCESS_SOP.md`, and repository navigation where responsibilities change.

## Sources

- [RDKit Book: conformer generation and embedding parameters](https://rdkit.org/docs/RDKit_Book.html)
- [RDKit Cookbook: custom bounds matrices](https://www.rdkit.org/docs/Cookbook.html)
- [RDKit force-field distance restraints](https://rdkit.org/docs/source/rdkit.ForceField.rdForceField.html)
- [CREST constrained sampling](https://crest-lab.github.io/crest-docs/page/examples/example_4.html)
- [CREST command-line constraint options](https://crest-lab.github.io/crest-docs/page/documentation/keywords.html)
