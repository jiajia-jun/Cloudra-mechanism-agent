# Guided Cyclic Preorganization — Design

**Date:** 2026-09-24
**Status:** Design for review; implementation has not started.

## Intent and success criteria

The problem is generating a reactant or reactant complex that already has the spatial arrangement needed for a cyclic transition-state guess. The user wants an Agent to name the atoms **in ring order**, and to keep the prospective ring contacts inside Agent-specified distance windows *throughout* conformer search. The same search may also guide an unrelated atom-pair distance through the existing `distance_filters` list. Both intramolecular folding and multicomponent assembly must work. `ts_prepare` must use the guided reactant candidate when the declaration includes it. The public schema must remain small enough for an Agent to use reliably.

Success means a caller can request, for example, a six-atom prospective cycle and one additional donor–acceptor distance, receive candidate geometries whose declared distances meet the requested windows, and see an explicit failure with atom-level diagnostics when no candidate qualifies. The output is a **TS seed**, not an optimized reactant minimum or evidence of a transition state.

## Current behavior and why it is insufficient

- `conformer_search.distance_filters` runs after RDKit/CREST generation and optimization. It labels passing candidates and rescues one from energy/window clustering, but does not guide sampling; zero matches can still yield `is_success=True`.
- RDKit single-component sampling embeds by ETKDGv3 and then runs unconstrained MMFF/UFF optimization. A high-strain ring-like arrangement can therefore be absent or relax away.
- The shared multicomponent builder uses `complex_assembly`, which can guide placement by `reaction_center`, but `conformer_search` does not expose a durable ring-order declaration. Its present reaction-mode constraint is conditionally released.
- `ts_prepare` builds the endpoints independently and does not consume the `conformer_search` ensemble. A conformer-tool change alone would not affect its default TS path.
- CREST supports an xTB-format constraint file (`--cinp`) for its search, but the current runner does not stage one for this use. Its topology-change report is observational and cannot serve as a requested-cycle predicate.

## Approach

Reuse `distance_filters` as the **single atom-pair distance declaration**. Add only one public field, `ring_order`. Its presence asks the search to use the existing distance windows as soft guidance as well as final checks. `mode` continues to choose the CREST run type (`conformers`, `nci`, etc.), so `mode="nci"`, a target ring, and any extra atom-pair windows can coexist. There is no second pair-constraint schema, guidance switch, or CREST run type.

Increasing the number of unconstrained trials or tightening a post-search filter cannot guarantee that a ring-like candidate is generated. A full Cartesian template would freeze the very torsions that need to vary and would require a separate template library. The selected approach adds soft, atom-pair distance restraints during generation and local relaxation, then checks actual output geometry.

## Public declaration and atom identity

`conformer_search` keeps its existing `distance_filters` field and gains one optional field:

```json
{
  "ring_order": [1, 2, 3, 4, 5, 6],
  "distance_filters": [
    {"atoms": [6, 1], "min_ang": 1.9, "max_ang": 2.5},
    {"atoms": [2, 9], "min_ang": 2.6, "max_ang": 3.0}
  ]
}
```

The example numbers illustrate the shape of the input, **not** default chemical windows. `ring_order` is one ordered simple cycle (at least three unique atoms); the last atom is adjacent to the first. The tool checks the reactant graph and requires a `distance_filters` entry for **each** consecutive pair that is not already covalently bonded. The same list can include unrelated distances, such as the second pair in the example. Bonded consecutive pairs retain their ordinary covalent geometry without a redundant filter. Duplicate windows for one pair must agree; incompatible or physically invalid windows fail before launching a search. There are no tool-chosen closure distances.

`ring_order` and `distance_filters` use the **same existing convention**: 1-based indices in the shared builder's resolved full atom order, including hydrogens. The tool validates them against `PreparedStructure.atom_identities` and returns the indexed element sequence in an error so the Agent can correct the declaration without guessing. The parser and builder may reorder components and add hydrogens; no new source-versus-output numbering system is introduced.

`TsDeclaration` and `TsAdjustment` use the **same `ring_order` and `distance_filters` fields** for the reactant side. `ts_prepare` resolves the reactant graph and complete atom numbering without optimizing its final geometry, validates the ring and windows, then begins guided geometry generation. An Agent that does not yet know the resolved order can first use the existing structure/mapping tools; the TS process must also report the resolved numbered atoms when it blocks on invalid guidance. The missing consecutive ring edges are converted internally to the existing 0-based `reaction_center` convention and reconciled with any explicitly declared centre; the Agent need not duplicate them. A correction via `ts_resume` reruns the dependent reactant build, assembly, guess and validation while retaining the previous attempt's artifacts. It never silently reuses a seed built under old guidance.

Without `ring_order`, `conformer_search` keeps the current post-search `distance_filters` behavior. With `ring_order`, every listed window is used as a soft search restraint **and** as a strict output qualification check. The ring needs at least one missing edge and every missing edge needs a distance-filter window. These rules preserve existing callers while keeping the new call shape to two fields. `ts_prepare` uses the same conditional semantics.

## Search behavior

### Single connected component

The shared structure parser resolves the graph and atom identity first. For a guided RDKit search, ETKDG's distance-bounds matrix is narrowed for all declared filters before embedding. An impossible bounds matrix fails with the offending atom pairs. Each embedded candidate is relaxed with *soft* MMFF distance restraints corresponding to those windows; the ring atoms are not frozen in Cartesian space, so torsions and ring puckering can still vary. The ordinary unrestrained MMFF optimization path remains unchanged when guidance is absent.

For a guided CREST search, generate a usable guided seed first and stage a run-local xTB constraint file. CREST receives it with `--cinp` so the distance filters remain active during optimization and sampling. CREST uses the midpoint of each Agent-provided window as the soft harmonic target; the original window still decides whether an output qualifies. Existing covalent ring-path edges are restrained around their seed lengths in CREST to guard against method-level topology changes. Constraint file, engine command, seed, and all returned frames remain inspectable. The MMFF path reuses the project's approved `MMFF_CONSTRAINT_FORCE_CONSTANT=100.0`; the CREST path uses its documented 0.02 Eh/Bohr^2 default. Both are soft restraints; the effective force and target are recorded, and neither fixes Cartesian coordinates.

### Multiple components

Resolve the cycle across components before placement. Extend the existing reaction-centre orientation scoring and constrained MMFF relaxation in `complex_assembly` to use **all** declared distance filters, including missing ring edges. The explicit guided path keeps those soft restraints through candidate delivery; it does not take the existing conditional-release branch. The normal assembly path retains its current behavior. If CREST `nci` is selected, pass a qualifying guided complex as its seed and apply the same run-local constraints through `--cinp`.

### Modes and unsupported combinations

Guidance is supported with ordinary `conformers` search and CREST `nci`. `qcg` creates new solvent atoms whose indices do not exist when the request is declared; a caller first grows the cluster, then runs guided `nci` on its fixed atom list. `protonate`, `deprotonate`, and `tautomerize` change species or atom identity and reject guided filters explicitly. Existing calls without guidance keep their current mode behavior.

## Candidate checks and outputs

Every generated frame is checked against all declared distance-filter windows, atom identity/order, clashes, and unexpected covalent connectivity changes. A window whose lower edge is nonpositive is rejected up front. Contact distances are geometric facts, not proof of a new bond or a saddle point. Guided output retains only qualifying candidates after diversity clustering; if none qualify, it returns `is_success=False`, counts by rejection reason, the closest attempted geometry when one exists, and persistent diagnostic paths. It does not turn a partial or failed CREST run into success.

Guided candidates are labeled `seed_kind="constrained_preorganization"`. Their restraint-biased energies are not reported as ordinary conformer energies or used for Boltzmann populations or the ordinary energy-window cutoff. The output lists achieved distances, deviations, constraint provenance and geometry paths. Any later unconstrained relaxation or electronic-structure ranking is a separate calculation with its own status.

## TS process integration

When `TsDeclaration.ring_order` is present, the reactant build uses the shared guided-search service and stores the selected qualifying candidate path and its constraint manifest in the process record. Product building and atom mapping continue under their existing scientific checks. The guess stage reads the selected guided reactant path in place of the ordinary minimum. A guided search with no qualifying candidate becomes a `TsBlocked` result naming the problematic 1-based atom pairs and the closest attempted distances. An absent ring declaration leaves the existing `ts_prepare` path unchanged. A constrained seed cannot by itself satisfy TS frequency, IRC, DAG evidence, or benchmark accuracy gates.

The reusable implementation belongs in a focused core preorganization module called by the `conformer_search` tool and `ts_process`, rather than calling the tool wrapper from the process. `crest_runner` only stages the declared constraint file and records it; `complex_assembly` only implements guided placement/relaxation. Each module keeps its current un-guided behavior by default.

## Verification and documentation

- RDKit intramolecular test with a fixed molecule and seed: guided sampling produces a conformer whose ring edges and extra distance lie inside their windows; the un-guided regression retains its old result shape.
- Multicomponent test: two or more prospective closure contacts guide relative placement; the constraints remain active to the delivered candidate.
- CREST command/fixture test: `--cinp` points to a run-local file with the correct resolved atoms; a failed engine or mismatching output is not accepted.
- Validation tests: repeated/out-of-range ring atoms, missing ring-edge filters, impossible and conflicting windows, unsupported run types, no qualifying candidate, resolved full-atom indexing, and the existing filter-only behavior when `ring_order` is absent.
- TS scenario test: guided declaration selects the seed for the guess; failure blocks with atom-level diagnostics; a corrected `ts_resume` keeps the previous attempt's artifacts and does not reuse its seed.
- Run syntax, focused tests, lint and the frontend build only if frontend files change; repository policy leaves the full Python suite to CI unless the user requests it.
- Update the tool descriptions, `cloudra/skills/dft-calculation/SKILL.md`, `docs/TS_PROCESS_SOP.md`, and repository navigation where responsibilities change.

## Sources

- [RDKit Book: conformer generation and embedding parameters](https://rdkit.org/docs/RDKit_Book.html)
- [RDKit Cookbook: custom bounds matrices](https://www.rdkit.org/docs/Cookbook.html)
- [RDKit force-field distance restraints](https://rdkit.org/docs/source/rdkit.ForceField.rdForceField.html)
- [CREST constrained sampling](https://crest-lab.github.io/crest-docs/page/examples/example_4.html)
- [CREST command-line constraint options](https://crest-lab.github.io/crest-docs/page/documentation/keywords.html)
