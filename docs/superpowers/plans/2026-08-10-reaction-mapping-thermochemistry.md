# Reaction Mapping and Thermochemistry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add inspectable reaction atom mapping, preserve reactive conformers, and produce correctly labelled relative thermochemistry for autonomous organic-mechanism calculations.

**Architecture:** A focused `reaction_mapping.py` owns graph mapping and concrete atom-order binding. `conformer_search.py` changes only representative selection, while `log_parser.py` fixes parsing semantics and a separate `thermo_analysis.py` owns multi-species arithmetic and optional GoodVibes orchestration. Existing TS verification remains stateless and consumes mapping outputs without absorbing their responsibilities.

**Tech Stack:** Python 3.12, Pydantic, RDKit, cclib, ASE, pytest; optional GoodVibes CLI.

## Global Constraints

- Scientific ambiguity is returned as `ambiguous` or `inconclusive`, never hidden behind `pass`.
- `reaction_mapping.atom_map` uses the existing `ts_guess` convention: product atom k maps to the returned 1-based reactant atom index.
- No persistent task/workflow state is added.
- `scan_parse` remains exploratory and unchanged.
- Existing untracked and modified user files are preserved; implementation changes are not committed without explicit authorization.

---

### Task 1: Graph-level mapping candidates

**Files:**
- Create: `cloudra/tools/Chemtool/reaction_mapping.py`
- Create: `tests/test_reaction_mapping.py`

**Interfaces:**
- Consumes: `reactant_smiles: str`, `product_smiles: str`, optional `selected_candidate: int`.
- Produces: `_enumerate_mapping_candidates(reactant, product) -> list[dict]` and tool output fields `mapping_status`, `candidates`, `heavy_atom_map`, `formed_bonds`, `broken_bonds`, `order_changes`, `watch_pairs`.

- [ ] Write real-RDKit tests with hand-derived mappings for identity, mapped-SMILES authority, Claisen candidate coverage, and symmetric ambiguity.
- [ ] Run `uv run pytest -s tests/test_reaction_mapping.py` and confirm import/behavior failures.
- [ ] Implement balanced-input validation, mapped-label validation, MCS-seeded candidate completion, scoring, edit extraction, ranking, and candidate selection.
- [ ] Run the focused tests and retain all scientifically tied candidates.

### Task 2: Bind mapping to concrete explicit-atom structures

**Files:**
- Modify: `cloudra/tools/Chemtool/reaction_mapping.py`
- Modify: `tests/test_reaction_mapping.py`
- Modify: `cloudra/tools/registry.py`
- Modify: `tests/test_tools_core.py` only if registry behavior needs an explicit assertion.

**Interfaces:**
- Consumes: optional `reactant_path/text`, `product_path/text`, `reactant_format/product_format`, charges, and selected heavy mapping.
- Produces: `atom_map: list[int]`, `reactant_identity`, `product_identity`, and concrete-structure diagnostics.

- [ ] Add failing tests for MOL→XYZ-preserved explicit-H order, endpoint identity mismatch, proton-transfer ambiguity, and registry discovery.
- [ ] Parse MOL/SDF/XYZ with RDKit, infer XYZ bonds safely, bind SMILES atoms by substructure match, and deterministically expand hydrogens attached to mapped heavy atoms.
- [ ] Return a heavy-only result with `inconclusive` full-map diagnostics whenever concrete binding is unsafe.
- [ ] Run `uv run pytest -s tests/test_reaction_mapping.py tests/test_tools_core.py tests/test_ts_guess.py -k 'reaction_mapping or interpolate'`.

### Task 3: Preserve reactive conformers

**Files:**
- Modify: `cloudra/tools/Chemtool/conformer_search.py`
- Modify: `tests/test_conformer_search.py`

**Interfaces:**
- Consumes: existing `distance_filters`, energy window, and RMSD threshold.
- Produces: ordinary lowest-energy cluster representatives plus the lowest-energy filter-passing member of mixed clusters; global relative energies remain unchanged.

- [ ] Add a failing deterministic clustering test where the lowest-energy representative fails the filter but a same-cluster member passes.
- [ ] Add a failing test where every ordinary conformer lies outside the window but one reactive conformer must remain visible with its conformational penalty.
- [ ] Refactor representative selection into a pure helper and use it from RDKit and CREST paths.
- [ ] Run `uv run pytest -s tests/test_conformer_search.py`.

### Task 4: Correct Gaussian thermochemistry fields

**Files:**
- Modify: `cloudra/tools/Chemtool/log_parser.py`
- Modify: `tests/test_log_parser.py` or the existing parser test module that owns Gaussian fixture assertions.

**Interfaces:**
- Produces: `total_enthalpy_hartree`, `total_gibbs_free_energy_hartree`, correctly parsed correction fields, and deprecated aliases with non-misleading descriptions.

- [ ] Add failing fixture assertions against the literal Gaussian values in `water_opt_freq_g16.out`.
- [ ] Separate total values from corrections and remove the `thermal_energy -> enthalpy` alias.
- [ ] Run the focused log-parser and Gaussian-frame tests.

### Task 5: Relative thermochemistry tool

**Files:**
- Create: `cloudra/tools/Chemtool/thermo_analysis.py`
- Create: `tests/test_thermo_analysis.py`
- Modify: `cloudra/tools/registry.py`

**Interfaces:**
- Consumes: named species logs, optional single-point energies and coefficients, temperature, standard-state/concentration settings, backend `raw_rrho|goodvibes`.
- Produces: absolute component table, relative/reaction `delta_e`, `delta_h`, and `delta_g` in Hartree and kcal/mol, assumptions, backend provenance, and `complete|inconclusive` status.

- [ ] Add failing raw-RRHO arithmetic, stoichiometry, mixed-level single-point, missing-data, and missing-GoodVibes tests.
- [ ] Implement pure arithmetic first, then cclib-backed log loading and optional subprocess execution with exact provenance.
- [ ] Register the tool and run `uv run pytest -s tests/test_thermo_analysis.py tests/test_tools_core.py`.

### Task 6: Agent guidance and Claisen workflow regression

**Files:**
- Modify: `cloudra/skills/dft-calculation/SKILL.md`
- Modify: `cloudra/skills/dft-calculation/references/mechanism-elucidation-sop.md`
- Modify: `cloudra/skills/dft-calculation/references/mechanisms/pericyclic.md`
- Modify: `tests/test_reaction_mapping.py`

**Interfaces:**
- Documents conditions as an explicit Phase-0 assumption, mapping before path construction, endpoint graph identity after IRC optimization, and the difference between raw RRHO and corrected thermochemistry.

- [ ] Add the complete Claisen heavy/full-map → `ts_guess(interpolate)` behavioral regression.
- [ ] Update agent-facing prose without turning advisory evidence into a mechanism verdict.
- [ ] Run `uv run pytest -s tests/test_reaction_mapping.py tests/test_conformer_search.py tests/test_ts_guess.py tests/test_thermo_analysis.py tests/test_gaussian_frames.py tests/test_tools_core.py`.
- [ ] Run `uv run python -m py_compile` on changed Python files and `git diff --check`; inspect the final working-tree diff without reverting unrelated user edits.
