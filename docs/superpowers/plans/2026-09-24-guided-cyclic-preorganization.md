# Guided Cyclic Preorganization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let an Agent declare the atoms of a prospective cycle in order, use existing distance filters and visible fallback windows to generate and retain qualified reactant geometries, and feed a selected geometry into `ts_prepare`.

**Architecture:** A core preorganization service resolves the complete builder atom order once, validates the ring graph and pair windows, and owns guided candidate qualification. RDKit and the existing complex assembler generate soft-restrained seeds; CREST receives a run-local xTB constraint file. `conformer_search` and `ts_process` call the same service, while calls without `ring_order` continue down their existing paths.

**Tech Stack:** Python 3.11+, Pydantic, RDKit ETKDG/MMFF, NumPy, CREST/xTB subprocess runner, pytest, Ruff.

**Spec:** `docs/superpowers/specs/2026-09-24-guided-cyclic-preorganization-design.md`

## Global Constraints

- Add only one Agent-facing field, `ring_order`; reuse the existing `distance_filters` shape for all pair windows. `ring_order` and `distance_filters` use 1-based indices in the builder's complete resolved atom order, including hydrogens.
- The cycle has at least three distinct atoms and at least one consecutive pair without a covalent bond. Every missing ring-edge window absent from `distance_filters` gets `AssemblyParameters.reaction_center_window` (currently 1.8–2.6 Å) from that single source and is reported with `source="fallback"`; an explicit entry wins.
- Invalid, contradictory, nonfinite, nonpositive or geometrically impossible explicit windows fail loudly before sampling. Fallback never repairs one. No candidate meeting *all* effective windows is a reported search failure, never success.
- Guidance is soft during embedding, relaxation and CREST sampling, and strict when qualifying output. Preserve ring atom flexibility. Check element order, clashes and unexpected covalent connectivity for every returned frame.
- Guided candidates are TS seeds with `seed_kind="constrained_preorganization"`; do not assign Boltzmann populations, apply the ordinary equilibrium energy cutoff, or call biased energies equilibrium conformer energies.
- Support guided `conformers` and CREST `nci`. Explicitly reject guided `qcg`, `protonate`, `deprotonate` and `tautomerize`; keep all existing unguided mode behavior.
- `ts_prepare` and `ts_resume` use the same declaration fields. Missing ring edges augment the internal 0-based reaction centre. A guidance correction rebuilds dependent stages without reading stale seed or TS files; old artifacts remain inspectable.
- Preserve un-guided tool semantics. Use focused tests, syntax checks and Ruff locally; the repository leaves the full Python suite to CI unless the user requests it. Do not touch unrelated dirty files.

## Review Focus

1. A multi-component graph-only build reports `assembly_failed` because no coordinates were requested, yet its complete atom identities must still permit ring validation; Task 1 tests this distinction.
2. A malformed explicit window on a missing ring edge must fail, rather than silently receive the fallback; Task 1 tests this separately from a genuinely omitted edge.
3. A CREST run can exit successfully while returning frames with the wrong atom sequence or no window match; Task 5 tests that neither outcome becomes a usable seed.
4. `ts_resume` after changing guidance must select new attempt files and must not recover an older `xtbpath_ts.xyz` through a directory glob; Task 6 tests both readers.
5. `ts_resume` must not rewrite guidance after a refinement job is submitted, since that job still refers to the old seed; Task 6 tests the rejection.

---

## File responsibilities

| File | Responsibility |
| --- | --- |
| `cloudra/tools/core/preorganization.py` (new) | Resolve graph and windows, qualify geometry, run guided RDKit/assembly/CREST search, persist the candidate/constraint manifest. It contains no Agent tool wrapper or TS stage logic. |
| `cloudra/tools/core/complex_assembly.py` | Score and relax multicomponent placements against supplied per-pair windows while leaving the existing reaction and complex paths unchanged. |
| `cloudra/tools/core/structure_builder.py` | Carry optional internal guided windows from `BuildStrategy` to `assemble`; preserve complete atom identities. |
| `cloudra/tools/core/crest_runner.py` | Stage an internal xTB constraint file beside each CREST run, pass its relative path via `--cinp`, and list it among run artifacts. |
| `cloudra/tools/Chemtool/conformer_search.py` | Expose `ring_order`; route only guided calls to the core service and render qualified TS-seed results. |
| `cloudra/tools/core/ts_process.py` | Declare guidance, choose the guided reactant seed, persist active paths, augment the effective reaction centre, and rebuild safely on a guidance correction. |
| `cloudra/tools/Chemtool/ts_search_process.py` | Describe the two TS tool fields and their correction semantics in the Agent-visible tool text. |
| `tests/test_preorganization.py` (new) | Contract, RDKit seed, qualification and manifest tests. |
| `tests/test_complex_assembly.py`, `tests/test_crest_runner.py`, `tests/test_conformer_search.py`, `tests/test_ts_process.py`, `tests/test_ts_search_process_tools.py` | Focused tests at each existing boundary. |
| `cloudra/skills/dft-calculation/SKILL.md`, `docs/TS_PROCESS_SOP.md`, `AGENTS.md` | Agent instructions, SOP and repository map for the new core service. |

### Task 1: Resolve the prospective cycle and its effective windows

**Files:**
- Create: `cloudra/tools/core/preorganization.py`
- Create: `tests/test_preorganization.py`

**Interfaces:**
- Produces `DistanceWindow(atoms: tuple[int, int], min_ang: float, max_ang: float, source: Literal["explicit", "fallback"])`, with internal 0-based sorted atoms.
- Produces `GuidancePlan(ring_order: tuple[int, ...], windows: tuple[DistanceWindow, ...], forming_pairs: tuple[tuple[int, int], ...], bonded_pairs: tuple[tuple[int, int], ...])` with internal 0-based indices.
- Produces `load_resolved_graph(prepared: PreparedStructure) -> Chem.Mol`, `resolve_explicit_filters(prepared: PreparedStructure, distance_filters: Sequence[Mapping[str, object]]) -> tuple[DistanceWindow, ...]`, `resolve_guidance(prepared: PreparedStructure, ring_order: Sequence[int], distance_filters: Sequence[Mapping[str, object]], *, assembly_parameters: AssemblyParameters | None = None) -> GuidancePlan`, `effective_window_rows(plan: GuidancePlan) -> list[dict]`, `measure_windows(plan: GuidancePlan, positions: Sequence[Sequence[float]]) -> dict[str, float]`, and `qualify_geometry(plan: GuidancePlan, graph: Chem.Mol, symbols: Sequence[str], positions: Sequence[Sequence[float]]) -> tuple[bool, list[str], dict[str, float]]`. `resolve_explicit_filters` validates without inserting fallbacks, so TS can use a filter-only declaration without guiding generation. Window rows have `atoms: [i,j]` (1-based), `min_ang`, `max_ang` and `source`; distance dictionary keys are public `"i-j"` pairs (1-based).

- [ ] **Step 1: Add failing contract tests.** Use the graph-only helper below. For `StructureInput(kind="smiles", value="CCO.O")`, assert `status == "assembly_failed"`, `len(atom_identities) == 12`, and that `resolve_guidance(prepared, [1, 2, 3, 10], [{"atoms": [3, 10], "min_ang": 2.5, "max_ang": 3.8}])` yields explicit `(2, 9)` plus fallback `(0, 9)` at `AssemblyParameters().reaction_center_window`. Assert `forming_pairs == ((2, 9), (0, 9))` in ring traversal order and that `effective_window_rows` contains `{"atoms": [1, 10], "min_ang": 1.8, "max_ang": 2.6, "source": "fallback"}`. Parameterize invalid `ring_order=[1,2,1]`, out-of-range `[1,2,99]`, a fully bonded cycle, a malformed explicit filter on missing edge `[10,1]` (`min_ang=0`, `min_ang > max_ang` or `NaN`), and conflicting duplicate filters; each must raise `ValueError` with the complete 1-based numbered element sequence and offending pair.

```python
def _graph_only(smiles, tmp_path):
    return prepare_structure(PreparationRequest(
        structure=StructureInput(kind="smiles", value=smiles),
        output_dir=str(tmp_path / "resolved"),
        strategy=BuildStrategy(embed=False, optimize=False),
    ))

def test_missing_ring_edge_uses_visible_single_source_fallback(tmp_path):
    prepared = _graph_only("CCO.O", tmp_path)
    assert prepared.status == "assembly_failed"  # graph-only, not a failed parse
    plan = resolve_guidance(prepared, [1, 2, 3, 10], [
        {"atoms": [3, 10], "min_ang": 2.5, "max_ang": 3.8},
    ])
    assert [(w.atoms, w.source) for w in plan.windows] == [
        ((2, 9), "explicit"), ((0, 9), "fallback"),
    ]
    assert (plan.windows[1].min_ang, plan.windows[1].max_ang) == (
        AssemblyParameters().reaction_center_window
    )
    assert {"atoms": [1, 10], "min_ang": 1.8, "max_ang": 2.6,
            "source": "fallback"} in effective_window_rows(plan)
```

- [ ] **Step 2: Run the focused red tests.** Run `uv run pytest -q tests/test_preorganization.py`; expect import failure for the new module.

- [ ] **Step 3: Implement resolution and qualification.** Read each component MOL with `removeHs=False`, combine them in builder order, and assert atom count and symbol sequence equal `PreparedStructure.atom_identities`. Accept `status="assembly_failed"` only when the requested graph-only build left every component without a coordinate path; reject genuine failed builds. Put unordered pair normalization, integer/bool checks, nonfinite/nonpositive bound checks and identical-only deduplication in `resolve_explicit_filters`; `resolve_guidance` reuses it, derives consecutive ring pairs including last-to-first, and inserts a fallback only for an absent nonbonded pair. Reuse `AssemblyParameters().reaction_center_window` instead of a copied constant. `qualify_geometry` compares every actual distance, element sequence and unchanged covalent edges; allow only the declared prospective edges to appear in the distance-based connectivity report. Use `topology_change.default_connectivity()` and the existing `AssemblyParameters.min_interfragment_distance` for nonbonded clash screening, excluding covalently bonded/one-three and declared prospective pairs.

```python
@dataclass(frozen=True)
class DistanceWindow:
    atoms: tuple[int, int]  # internal 0-based pair
    min_ang: float
    max_ang: float
    source: Literal["explicit", "fallback"]

fallback = (assembly_parameters or AssemblyParameters()).reaction_center_window
for pair in forming_pairs:
    if pair not in explicit_by_pair:
        windows.append(DistanceWindow(pair, fallback[0], fallback[1], "fallback"))
```

- [ ] **Step 4: Run the contract tests and syntax check.** Run `uv run pytest -q tests/test_preorganization.py` and `uv run python -m compileall -q cloudra/tools/core/preorganization.py`; expect both to pass.

- [ ] **Step 5: Commit only Task 1 files.** `git add cloudra/tools/core/preorganization.py tests/test_preorganization.py && git commit -m "feat: resolve cyclic guidance with visible fallback windows"`.

### Task 2: Generate and qualify intramolecular RDKit seeds

**Files:**
- Modify: `cloudra/tools/core/preorganization.py`
- Modify: `tests/test_preorganization.py`

**Interfaces:**
- Consumes `GuidancePlan`, `resolve_guidance`, `qualify_geometry` from Task 1.
- Produces `GuidedCandidate(xyz_path: str, mol_path: str, achieved_distances: dict[str, float], max_deviation_ang: float, seed_kind: str = "constrained_preorganization")`, `GuidedSearchResult(status: Literal["ok", "no_candidate", "build_failed", "engine_failed"], message: str, candidates: list[GuidedCandidate], effective_windows: list[dict], forming_pairs: list[tuple[int, int]], prepared_path: str, counts: dict[str, int], manifest_path: str, closest_path: str, diagnostics: list[str])`, and `search_guided(*, structure: StructureInput, output_dir: str, ring_order: Sequence[int], distance_filters: Sequence[Mapping[str, object]], charge: int = 0, multiplicity: int = 1, backend: Literal["rdkit", "crest"] = "rdkit", mode: Literal["conformers", "nci"] = "conformers", num_confs: int = 50, random_seed: int = 42, rmsd_threshold: float = 0.5, timeout: int = 600) -> GuidedSearchResult`. `forming_pairs` are 0-based and `prepared_path` points to the graph-only builder's `prepared_structure.json`.

- [ ] **Step 1: Add failing RDKit tests.** With fixed seed 42, `CCCCCC`, `ring_order=[1,2,3,4,5,6]`, explicit `[1,6] 2.8–3.2 Å` and extra `[2,5] 3.0–3.6 Å`, assert at least one candidate, every emitted candidate passes `qualify_geometry`, each has paired XYZ/MOL paths and achieved distances, `seed_kind` is set, the manifest has both `source="explicit"` windows and MMFF force constant from `complex_assembly.MMFF_CONSTRAINT_FORCE_CONSTANT`, and no population or equilibrium relative-energy fields occur. Add a deterministic no-match test by monkeypatching `qualify_geometry` to reject every candidate and assert `status="no_candidate"`, `closest_path` exists, rejection counts and achieved distances are present, and `candidates == []`. Add a bounds-conflict test using mutually incompatible valid pair ranges and assert a pair-specific failure before `EmbedMultipleConfs` runs.

```python
result = search_guided(
    structure=StructureInput(kind="smiles", value="CCCCCC"),
    output_dir=str(tmp_path), ring_order=[1, 2, 3, 4, 5, 6],
    distance_filters=[
        {"atoms": [1, 6], "min_ang": 2.8, "max_ang": 3.2},
        {"atoms": [2, 5], "min_ang": 3.0, "max_ang": 3.6},
    ], num_confs=50, random_seed=42,
)
assert result.status == "ok" and result.candidates
assert all(candidate.seed_kind == "constrained_preorganization" for candidate in result.candidates)
```

- [ ] **Step 2: Run the focused red tests.** Run `uv run pytest -q tests/test_preorganization.py`; expect missing `search_guided`/guided result interfaces or unsuccessful seed assertions.

- [ ] **Step 3: Implement the single-component path.** Resolve with `prepare_structure` and `BuildStrategy(embed=False, optimize=False)` as in the Task 1 helper; load the component MOL. Start from `rdDistGeom.GetMoleculeBoundsMatrix(mol)`, set upper/lower triangular bounds for every effective window, require triangle smoothing, and fail with pair names if inconsistent. Install the bounds in `ETKDGv3` before `EmbedMultipleConfs`. For each embedded conformer, build MMFF94 with `ignoreInterfragInteractions=True`, add `MMFFAddDistanceConstraint(i, j, False, low, high, MMFF_CONSTRAINT_FORCE_CONSTANT)` for every window, minimize, and keep the restraint active through delivery. Qualify every converged geometry, cluster only qualified candidates by heavy-atom RMSD, and write one XYZ/MOL pair per retained seed plus a JSON manifest. For failed output retain the closest attempted XYZ and rejection histogram; never populate the ordinary energy/Boltzmann fields. Use atomic writes.

```python
bounds = rdDistGeom.GetMoleculeBoundsMatrix(mol)
for window in plan.windows:
    i, j = window.atoms
    bounds[min(i, j), max(i, j)] = window.max_ang
    bounds[max(i, j), min(i, j)] = window.min_ang
if not DistanceGeometry.DoTriangleSmoothing(bounds):
    raise ValueError(f"incompatible guided bounds for {public_pair_list(plan.windows)}")
params = AllChem.ETKDGv3()
params.randomSeed = random_seed
params.SetBoundsMat(bounds)
```

- [ ] **Step 4: Run focused green tests and check the outputs.** Run `uv run pytest -q tests/test_preorganization.py`; expect pass. Open the test manifest and one XYZ/MOL pair in the test, then independently recompute the two declared distances from the persisted XYZ so that a stale in-memory conformer cannot pass the test.

- [ ] **Step 5: Commit only Task 2 files.** `git add cloudra/tools/core/preorganization.py tests/test_preorganization.py && git commit -m "feat: generate restrained intramolecular TS seeds"`.

### Task 3: Guide multicomponent placement and preserve its restraints

**Files:**
- Modify: `cloudra/tools/core/complex_assembly.py`
- Modify: `cloudra/tools/core/structure_builder.py`
- Modify: `cloudra/tools/core/preorganization.py`
- Modify: `tests/test_complex_assembly.py`
- Modify: `tests/test_preorganization.py`

**Interfaces:**
- Consumes `DistanceWindow` in Task 1 and `search_guided` in Task 2.
- Produces optional internal `BuildStrategy.guided_windows: list[tuple[int, int, float, float]]` and `assemble(*, components, output_dir: str, parameters: Optional[AssemblyParameters] = None, reaction_center: Optional[list[tuple[int, int]]] = None, guided_windows: Optional[list[tuple[int, int, float, float]]] = None, seed: int = 42) -> AssemblyResult`; tuples are 0-based `(i,j,min_ang,max_ang)`. The old arguments and default path retain their meaning.

- [ ] **Step 1: Add failing assembler and service tests.** A unit test spies on `_relax_with_trajectory` to verify three distinct windows are passed and that `release_when_in_window` is `None` on the guided path; an unguided reaction-centre test still observes the old conditional-release window. A real focused search uses `CCO.O`, `ring_order=[1,2,3,10]`, explicit `[3,10]`, `[10,1]`, `[2,10]` all at 2.5–3.8 Å, seed 42; assert at least one qualified output and three achieved distances. A separate omission case with `[10,1]` absent asserts the visible 1.8–2.6 Å fallback, accepting either a qualified seed or `no_candidate` with closest distances; the fallback must never be widened silently. Assert guided assembly bypasses the ordinary energy-window trim but still deduplicates qualified geometries.

```python
result = search_guided(
    structure=StructureInput(kind="smiles", value="CCO.O"),
    output_dir=str(tmp_path), ring_order=[1, 2, 3, 10],
    distance_filters=[
        {"atoms": [3, 10], "min_ang": 2.5, "max_ang": 3.8},
        {"atoms": [10, 1], "min_ang": 2.5, "max_ang": 3.8},
        {"atoms": [2, 10], "min_ang": 2.5, "max_ang": 3.8},
    ], random_seed=42,
)
assert result.status == "ok" and result.candidates
assert len(result.candidates[0].achieved_distances) == 3
```

- [ ] **Step 2: Run the focused red tests.** Run `uv run pytest -q tests/test_complex_assembly.py tests/test_preorganization.py`; expect missing `guided_windows` forwarding and failing multi search.

- [ ] **Step 3: Implement the internal guided assembly branch.** Forward `BuildStrategy.guided_windows` into `assemble`. Score sampled orientations by the maximum deviation over *all* effective windows, not the single shared reaction-centre window. Feed each individual low/high into MMFF; do not enter the conditional-release/unconstrained-minimization branch for guided calls. Keep the collision, convergence, dissociation, trajectory and heavy-atom clustering gates; skip only the ordinary equilibrium energy-window cutoff. In `search_guided`, parse the graph first, then call embedded `prepare_structure` with the effective windows and derived missing-edge reaction centres, and apply Task 1 qualification to each assembled candidate. Keep the existing unguided assembly path byte-for-byte semantically equivalent.

```python
guided = list(guided_windows or [])
_set_positions(mol, conf_id, positions)
scored_windows = guided or [
    (i, j, *params.reaction_center_window) for i, j in (reaction_center or [])
]
deviations = []
for i, j, low, high in scored_windows:
    actual = _distance(mol, conf_id, i, j)
    deviations.append(max(low - actual, 0.0, actual - high))
score = max(deviations, default=0.0)
release_when_in_window = (
    params.reaction_center_window if reaction_center and not guided else None
)
```

- [ ] **Step 4: Run focused green tests and syntax checks.** Run `uv run pytest -q tests/test_complex_assembly.py tests/test_preorganization.py` and `uv run python -m compileall -q cloudra/tools/core/complex_assembly.py cloudra/tools/core/structure_builder.py cloudra/tools/core/preorganization.py`; expect pass.

- [ ] **Step 5: Commit only Task 3 files.** `git add cloudra/tools/core/complex_assembly.py cloudra/tools/core/structure_builder.py cloudra/tools/core/preorganization.py tests/test_complex_assembly.py tests/test_preorganization.py && git commit -m "feat: guide multicomponent cyclic placement"`.

### Task 4: Stage CREST constraints inside each run

**Files:**
- Modify: `cloudra/tools/core/crest_runner.py`
- Modify: `tests/test_crest_runner.py`

**Interfaces:**
- Produces `CrestRunRequest.constraint_text: str = ""`. The runner accepts only the internally generated xTB text, writes `constraints.inp` under its new `run_dir`, and adds `--cinp constraints.inp` to the command when nonempty. `CrestRunResult.artifacts` lists the file even on engine failure.

- [ ] **Step 1: Add failing fake-CREST tests.** Use the existing `fake_crest` fixture and `WATER_XYZ`. Pass `constraint_text="$constrain\n  force constant=0.02\n  distance: 1, 2, 1.00\n$end\n"`; assert `result.command[-2:] == ["--cinp", "constraints.inp"]`, file content at `Path(result.run_dir)/"constraints.inp"`, and the artifact list contain the same file. Repeat with `fake_crest("search_failed")`: `scientific_success` stays false and the staged file remains. Existing no-constraint command test must stay unchanged.

```python
request = _request(tmp_path, constraint_text=(
    "$constrain\n  force constant=0.02\n  distance: 1, 2, 1.00\n$end\n"
))
result = run_crest(request)
assert result.command[-2:] == ["--cinp", "constraints.inp"]
assert (Path(result.run_dir) / "constraints.inp").read_text() == request.constraint_text
```

- [ ] **Step 2: Run the focused red tests.** Run `uv run pytest -q tests/test_crest_runner.py`; expect `constraint_text` schema/command assertion failure.

- [ ] **Step 3: Implement run-local staging.** Extend the Pydantic request, append `--cinp constraints.inp` in `build_crest_command` when nonempty, write `constraints.inp` with `atomic_write_text` before starting the subprocess, and let the existing artifact scan collect it. Reject a nonempty constraint file for `qcg`/species-changing run types at this internal boundary; do not make a caller's arbitrary file path part of the command.

```python
if request.constraint_text:
    command.extend(["--cinp", "constraints.inp"])
# after next_run_dir, before Popen:
if request.constraint_text:
    atomic_write_text(os.path.join(run_dir, "constraints.inp"), request.constraint_text)
```

- [ ] **Step 4: Run focused green tests and syntax check.** Run `uv run pytest -q tests/test_crest_runner.py` and `uv run python -m compileall -q cloudra/tools/core/crest_runner.py`; expect pass.

- [ ] **Step 5: Commit only Task 4 files.** `git add cloudra/tools/core/crest_runner.py tests/test_crest_runner.py && git commit -m "feat: stage CREST distance constraints per run"`.

### Task 5: Expose the small guided search in `conformer_search`

**Files:**
- Modify: `cloudra/tools/core/preorganization.py`
- Modify: `cloudra/tools/Chemtool/conformer_search.py`
- Modify: `tests/test_preorganization.py`
- Modify: `tests/test_conformer_search.py`
- Modify: `cloudra/skills/dft-calculation/SKILL.md`

**Interfaces:**
- Consumes `search_guided`, `GuidedSearchResult` from Task 2 and `CrestRunRequest.constraint_text` from Task 4.
- Completes `search_guided(backend="crest", mode="conformers" | "nci")`. `ConformerSearch_input_schema.ring_order: list[int]` is the sole new public input; `distance_filters` keeps its present shape. Output adds optional `seed_kind`, `effective_windows`, `diagnostic_paths`, `constraint_manifest_path`; for guided output, each `conformers` row contains `xyz_path` and `achieved_distances`, without Boltzmann or equilibrium energy columns.

- [ ] **Step 1: Add failing tool and CREST tests.** A guided RDKit call with the Task 2 hexane fixture must return only passing seed rows, effective explicit windows, manifest path and no Boltzmann table; a call omitting one ring-edge filter must display its fallback pair and source in `effective_windows` and the message even if the search finds no seed. The existing `test_distance_filters` without `ring_order` must still retain both passing and failing conformers with its old table. A guided `mode="nci", backend="crest"` call with the existing fake runner must pass a qualified seed and a nonempty xTB constraint file. Extend the fake runner with `wrong_symbol` (replace its first output atom symbol with `F`) and `out_of_window` (translate one constrained atom by 20 Å in every output frame); assert `is_success=False`, `candidates == []` and diagnostic paths for both. Parameterize guided `qcg`, `protonate`, `deprotonate`, `tautomerize` and assert explicit unsupported-mode failures. A normal engine failure remains failure even if the guided seed succeeded.

```python
result = await tool.safe_call(ConformerSearch_input_schema(
    smiles="CCCCCC", ring_order=[1, 2, 3, 4, 5, 6],
    distance_filters=[{"atoms": [1, 6], "min_ang": 2.8, "max_ang": 3.2}],
    num_confs=50, output_dir=str(tmp_path / "guided"),
), mock_session)
assert result.is_success and result.seed_kind == "constrained_preorganization"
assert all(row["passes_filters"] for row in result.conformers)
assert "Boltzmann" not in result.table
```

- [ ] **Step 2: Run focused red tests.** Run `uv run pytest -q tests/test_conformer_search.py tests/test_preorganization.py`; expect missing input field/guided output and CREST service failure.

- [ ] **Step 3: Complete guided CREST and tool routing.** For CREST, call the guided RDKit/assembly path first; use its first qualified seed. Render one `$constrain` block with `force constant=0.02`, each effective window's midpoint as an xTB `distance: i, j, target` line, and each already-bonded cycle edge at its seed length unless the pair already has an explicit window; convert internal 0-based indices to xTB 1-based. Persist targets and force in the manifest. Run CREST via Task 4 with `--cinp`, then call `qualify_geometry` on every returned frame; do not promote a failed/partial run. For the tool, branch on nonempty `ring_order` before existing `_run_rdkit`/`_run_crest`, catch `ValueError` from invalid declarations as an explicit `is_success=False` message containing the offending pair and numbered atoms, map `GuidedSearchResult` to the output with visible explicit/fallback sources and closest-geometry diagnostics, and keep the old path intact when absent. Add the Agent-facing examples and the two-stage `distance_filters` semantics to the dft-calculation skill.

```python
if user_input.ring_order:
    if user_input.mode not in ("conformers", "nci"):
        return ConformerSearch_output_schema(
            is_success=False, message=f"ring_order is unsupported with mode={user_input.mode!r}"
        )
    guided = await asyncio.to_thread(search_guided, structure=self._structure_input(user_input),
        output_dir=user_input.output_dir, ring_order=user_input.ring_order,
        distance_filters=user_input.distance_filters, charge=user_input.charge,
        multiplicity=user_input.multiplicity, backend=user_input.backend,
        mode=user_input.mode, num_confs=user_input.num_confs,
        random_seed=user_input.random_seed, rmsd_threshold=user_input.rmsd_threshold,
        timeout=user_input.timeout)
    return self._guided_output(guided)
```

- [ ] **Step 4: Run focused green tests and syntax check.** Run `uv run pytest -q tests/test_conformer_search.py tests/test_preorganization.py tests/test_crest_runner.py` and `uv run python -m compileall -q cloudra/tools/Chemtool/conformer_search.py cloudra/tools/core/preorganization.py`; expect pass.

- [ ] **Step 5: Commit only Task 5 files.** `git add cloudra/tools/core/preorganization.py cloudra/tools/Chemtool/conformer_search.py tests/test_preorganization.py tests/test_conformer_search.py cloudra/skills/dft-calculation/SKILL.md && git commit -m "feat: expose guided cyclic conformer search"`.

### Task 6: Feed and safely revise the TS reactant seed

**Files:**
- Modify: `cloudra/tools/core/ts_process.py`
- Modify: `cloudra/tools/Chemtool/ts_search_process.py`
- Modify: `tests/test_ts_process.py`
- Modify: `tests/test_ts_search_process_tools.py`
- Modify: `docs/TS_PROCESS_SOP.md`
- Modify: `AGENTS.md`

**Interfaces:**
- Consumes `search_guided -> GuidedSearchResult` from Tasks 2–5 and `resolve_explicit_filters` from Task 1.
- Adds `TsDeclaration.ring_order: list[int]`, `TsDeclaration.distance_filters: list[dict]` and corresponding optional `TsAdjustment` fields (`None` leaves unchanged; `[]` clears). Adds durable `TsProcessRecord` fields `guidance_attempt: int`, `active_attempt_dir: str`, `current_seed_xyz_path: str`, `current_seed_mol_path: str`, `current_reactant_prepared_path: str`, `current_ts_guess_path: str`, `guidance_manifest_path: str`, and `effective_reaction_center: list[tuple[int,int]]` (0-based).

- [ ] **Step 1: Add failing TS stage and resume tests.** Use a real guided search fixture or a service stub returning two distinct XYZ/MOL paths. Start a TS declaration with `ring_order` and no `reaction_center`; assert the selected reactant XYZ is the geometry read by `_read_built_xyz`, the derived missing edge appears in `effective_reaction_center`, and a multi-component declaration no longer blocks as `reaction_center_missing`. Make a guided failure return `status="no_candidate"`, pair diagnostics and closest path; assert `TsBlocked` names `ring_order`/`distance_filters` and its 1-based pairs. For a no-ring declaration with only `distance_filters`, assert the built candidates are checked after generation and a matching one selected or a pair-specific block returned, without invoking the guided search. At a map/guess block, call `resume` with changed filters; assert `guidance_attempt` increments, the old reactant/product/reordered-product files still exist, stage records from build onward refer only to the new attempt, and xTB request uses the new seed. Plant an old `path/xtb_path_runs/old/xtbpath_ts.xyz`, set the new attempt to IDPP/no TS candidate, and assert `_validate` and `_write_refinement_input` do not read it. Set `job_id` or a populated `job_steps` and assert a guidance edit raises before modifying the record. Keep no-ring regression assertions.

```python
old_artifacts = list(record.evidence_candidates)
old_attempt = record.guidance_attempt
old_seed = record.current_seed_xyz_path
updated = resume(record, TsAdjustment(distance_filters=[
    {"atoms": [1, 6], "min_ang": 2.8, "max_ang": 3.2},
]))
assert updated.guidance_attempt == old_attempt + 1
assert updated.current_seed_xyz_path != old_seed
assert Path(old_seed).exists()
assert all("guided_attempt_0002" not in path for path in old_artifacts)
```

- [ ] **Step 2: Run focused red tests.** Run `uv run pytest -q tests/test_ts_process.py tests/test_ts_search_process_tools.py`; expect absent declaration/record fields and stale path behavior.

- [ ] **Step 3: Implement TS build and path selection.** When `ring_order` is present, increment `guidance_attempt` and create `build/guided_attempt_NNNN/`; call `search_guided` for the reactant under its `reactant/` child and build the product under its `product/` child. Store the selected qualifying reactant XYZ/MOL, manifest, prepared JSON and effective derived reaction centre. The guided reactant must not first take the ordinary minimum. With only `distance_filters`, perform the ordinary build, validate filters with `resolve_explicit_filters`, then select a matching built candidate (or block with achieved pair distances); do not add soft guidance. Make `_read_built_xyz(record, "reactant")` prefer only the active recorded paths when one was selected, and make product lookup use `active_attempt_dir/product` on a guided run. Make `_assemble` read `current_reactant_prepared_path` when present. Define `_active_reaction_center(record)` to return `effective_reaction_center` for guided records and `declaration.reaction_center` otherwise; use it in `_assemble`, `_validate`, `_irc_interval_proof` and other reaction-centre readers so unguided records retain their old checks. On a guided run, `_guess` writes its reordered product and xTB run under `path/guided_attempt_NNNN/`, records the exact `run.ts_xyz_path` on success, and clears it on failure/IDPP; `_validate`/`_write_refinement_input` use that path exclusively instead of globbing old attempts. Block on no guided candidate with the service's per-pair distances and persistent diagnostic paths; never promote a constrained seed to verified TS evidence.

```python
if declaration.ring_order and role == "reactant":
    record.guidance_attempt += 1
    record.active_attempt_dir = os.path.join(
        out_dir, f"guided_attempt_{record.guidance_attempt:04d}"
    )
    try:
        guided = search_guided(
            structure=StructureInput(kind="smiles", value=smiles),
            output_dir=os.path.join(record.active_attempt_dir, "reactant"),
            ring_order=declaration.ring_order,
            distance_filters=declaration.distance_filters,
            charge=declaration.charge, multiplicity=declaration.multiplicity,
        )
    except ValueError as exc:
        return _block(record, "build", "invalid_ring_guidance", str(exc),
                      atom_details=[str(exc)], needs=["ring_order", "distance_filters"])
    if guided.status != "ok":
        return _block(record, "build", "guided_preorganization_failed", guided.message,
                      atom_details=guided.diagnostics, needs=["ring_order", "distance_filters"])
    record.current_seed_xyz_path = guided.candidates[0].xyz_path
    record.current_seed_mol_path = guided.candidates[0].mol_path
    record.current_reactant_prepared_path = guided.prepared_path
    record.guidance_manifest_path = guided.manifest_path
    record.effective_reaction_center = list(dict.fromkeys(
        tuple(sorted(pair)) for pair in [*declaration.reaction_center, *guided.forming_pairs]
    ))
```

- [ ] **Step 4: Implement safe guidance correction.** Compute a prospective declaration copy first. Before mutating a record with a submitted or waiting job, reject any change to ring guidance or, while guidance is active, `reaction_center`; leave `process.json` unchanged. Otherwise, when `ring_order`, `distance_filters`, or the guided `reaction_center` changes, clear active seed/guess paths and `path_kind`, reset `stage="build"`, remove stage records from build onward and all current-attempt evidence paths, retain old attempt directories, then run `advance`. An unchanged/empty `TsAdjustment()` keeps the existing local-resume behavior. Save the new declaration and revision before `advance` through the existing atomic `save_record`; a corrected `reaction_center` participates in the rebuilt effective centre without asking the Agent to repeat ring edges. Update tool descriptions and SOP with one minimal declaration example and the fallback/fail-loud behavior.

```python
proposed = record.declaration.model_copy(deep=True)
if adjustment.ring_order is not None:
    proposed.ring_order = list(adjustment.ring_order)
if adjustment.distance_filters is not None:
    proposed.distance_filters = list(adjustment.distance_filters)
if adjustment.reaction_center is not None:
    proposed.reaction_center = list(adjustment.reaction_center)
guidance_changed = (
    proposed.ring_order != record.declaration.ring_order
    or proposed.distance_filters != record.declaration.distance_filters
)
geometry_changed = guidance_changed or (
    bool(proposed.ring_order)
    and proposed.reaction_center != record.declaration.reaction_center
)
if geometry_changed and (record.job_id is not None or record.job_steps or record.waiting_for):
    raise ValueError("guidance cannot change after refinement was submitted in this run")
record.declaration = proposed
if geometry_changed:
    record.stage = "build"
    record.stage_records = [r for r in record.stage_records if STAGE_ORDER.index(r.stage) < STAGE_ORDER.index("build")]
    record.evidence_candidates = []
    record.active_attempt_dir = ""
    record.current_seed_xyz_path = record.current_seed_mol_path = ""
    record.current_reactant_prepared_path = ""
    record.current_ts_guess_path = record.guidance_manifest_path = ""
    record.effective_reaction_center = []
    record.path_kind = "not_attempted"
```

- [ ] **Step 5: Run focused green tests and syntax check.** Run `uv run pytest -q tests/test_ts_process.py tests/test_ts_search_process_tools.py tests/test_preorganization.py` and `uv run python -m compileall -q cloudra/tools/core/ts_process.py cloudra/tools/Chemtool/ts_search_process.py`; expect pass.

- [ ] **Step 6: Commit only Task 6 files.** `git add cloudra/tools/core/ts_process.py cloudra/tools/Chemtool/ts_search_process.py tests/test_ts_process.py tests/test_ts_search_process_tools.py docs/TS_PROCESS_SOP.md AGENTS.md && git commit -m "feat: use guided reactant seeds in TS preparation"`.

### Task 7: Cross-boundary verification and final documentation check

**Files:**
- Modify only a Task 1–6 file if a focused verification exposes an actual defect; do not broaden the change set.

**Interfaces:**
- No new interfaces. This task verifies the complete public flow and preserves the pre-existing un-guided paths.

- [ ] **Step 1: Run the focused combined test set.** Run `uv run pytest -q tests/test_preorganization.py tests/test_complex_assembly.py tests/test_crest_runner.py tests/test_conformer_search.py tests/test_ts_process.py tests/test_ts_search_process_tools.py`; expect pass, with optional real-engine cases skipped only by the existing environment gates.
- [ ] **Step 2: Run repository lint and syntax checks.** Run `uv run ruff check cloudra tests` and `uv run python -m compileall -q cloudra/tools/core/preorganization.py cloudra/tools/core/complex_assembly.py cloudra/tools/core/structure_builder.py cloudra/tools/core/crest_runner.py cloudra/tools/core/ts_process.py cloudra/tools/Chemtool/conformer_search.py cloudra/tools/Chemtool/ts_search_process.py`; expect zero failures. Do not run the full Python suite locally.
- [ ] **Step 3: Inspect evidence and diff.** Check one intramolecular and one multicomponent manifest for explicit/fallback source, achieved distances, constraint force, seed paths and `seed_kind`; inspect `git diff --check` and `git status --short` to ensure no unrelated dirty files are staged. If any check fails, fix the owning task's code and rerun only the failing focused command.
- [ ] **Step 4: Commit a verified correction only if needed.** Stage exact corrected files and commit with a message naming the fixed boundary; otherwise record the passing commands in the task handoff without an empty commit.
