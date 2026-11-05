# Molecular Workbench Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Deliver the approved independent molecular editor and real calculation viewer, with one combined DAG/chemical-products page.

**Architecture:** Reuse native RDKit molecular state, existing geometry operations, native result parsers, workspace writes and persistent Agent messages. The frontend keeps an editable draft; saved structures and settings live in project `.cloudra`, while the fragment history is shared across projects. Chemical associations come only from recorded references.

**Tech Stack:** React/TypeScript, 3Dmol WebGL viewer, Python 3.11+, FastAPI, Pydantic, RDKit, ASE, existing Gaussian/ORCA parsers.

**Spec:** `docs/superpowers/specs/2026-11-05-molecular-workbench-design.md` (approved by user: “好，按这个实现”).

## Global Constraints

- No automatic method/basis/barrier choices; preserve native scientific facts and unknowns.
- No new regular expressions except inside native QM log parsers.
- All filesystem, parsing, RDKit and SQLite work runs off the async event loop.
- User and Agent share molecular/geometry authority; do not build a second frontend chemistry engine.
- New edited structures keep provenance, not inferred species identity or inherited scientific acceptance.
- Work in the current checkout on `codex/molecular-workbench`; preserve and deliver all existing workspace changes. No merge to master.
- Independent tasks may run concurrently with disjoint file ownership; root owns API/integration, agents own their named modules. This is the execution choice for speed under the user's existing authorization.
- Run compileall, ruff and affected tests only, plus frontend typecheck/build and focused UI checks.

## Review Focus

- Selecting a historical frame and editing it must save that frame as provenance, not the newest frame.
- Topology edits must not reuse deleted atom indices in scan/freeze settings.
- Gaussian/ORCA point energies, RMS forces and coordinates must be genuinely paired; unavailable facts remain absent.
- Unknown chemical association must remain unknown even when opened from a selected DAG object.
- Project switching and window reopening must not leak drafts or shared-library project use counts.

## Shared UI/API contract

All new routes are under `/api/v2/projects/{project_id}/workbench` except the shared fragment collection, which is still accessed with project context.

- `GeometryView`: `molecule` (program-produced native serialized molecule), `xyz`, `atoms` (`index` 1-based, `symbol`, `x/y/z`), `bonds` (`atom1/atom2` 1-based, numeric `order`).
- `DocumentView`: `document_id`, `title`, `source_path`, `task_type`, `frames` (scalar metadata only), `selected_frame` (zero-based array index), `geometry`, `modes`, `settings`, `warnings`.
- A frame summary has `index`, `step`, optional `energy_hartree`, `rms_force`, `max_force`, `force_unit`, `reaction_coordinate`, `scan_coordinates`, `path_number`, `converged`.
- Mode entries have signed `frequency_cm` and `displacements` (N by 3), bound to their actual reference geometry.
- `POST /open`: `{path?, artifact_id?, input_text?, input_format?, smiles?}` selects one source; text/SMILES creates a draft.
- `GET /documents/{document_id}/frames/{index}` returns a `GeometryView`; frame coordinates stay on disk until requested.
- `GET /documents/{document_id}/csv` exports scalar observations and units.
- `POST /edit`: receives `molecule` plus a validated domain edit and returns `GeometryView`.
- `GET /fragments`, `POST /fragments`, `DELETE /fragments/{id}` manage one cross-project library; confirmed use updates global and project counts. Project-used entries first, each group by total use descending.
- `POST /save`: `{title, molecule, source_path?, source_frame?, settings, frozen_coordinates, scan_coordinates, generate_input}`. Save complete state/XYZ/MOL/config and optional native input; return `{path, files, geometry, message}`. Generate-input requires explicit method, basis and electronic-state inputs. No automatic compute submission.
- `GET /products`: returns saved structures and registered artifacts with exact recorded chemical references and readable calculation/source context; no inferred chemical identity.

## Task 1: Real result documents and frame data

**Files:** Create `cloudra/tools/core/workbench_results.py`, `tests/test_workbench_results.py`; modify native frame parsers only where necessary.

**Interfaces:** Export `open_document(source_path: Path, cache_root: Path, frame_index: int | None = None) -> dict`, `document_frame(cache_root: Path, document_id: str, index: int) -> dict`, `document_csv(cache_root: Path, document_id: str) -> str`. Use `geometry_view(mol)` from Task 2 for the shared geometry representation. Cache scalar metadata separately from frame geometries under project `.cloudra`.

- [x] Write and run failing tests for multi-frame XYZ, Gaussian/ORCA optimization, real modes, IRC sidecars, scan coordinates and RMS-force facts.
- [x] Implement using existing authoritative native parsers, extending shared frame facts rather than parsing logs in API/UI.
- [x] Preserve all actual frames, unknowns and units; latest frame default; incremental source changes invalidate derived cache without altering original sources.
- [x] Verify compileall, ruff and affected frame/result tests.

## Task 2: Shared geometry editing and fragment history

**Files:** Create `cloudra/tools/core/workbench_geometry.py`, `cloudra/persistence/fragment_library.py`, `tests/test_workbench_geometry.py`, `tests/test_fragment_library.py`; modify shared internal-coordinate implementation only to consolidate geometry responsibilities.

**Interfaces:** Export `geometry_view(mol) -> dict`, `create_geometry(input_text: str, input_format: str) -> dict`, `edit_geometry(request) -> dict` and a Pydantic `EditRequest` (native `molecule`, action and domain fields). Fragment store exports `list_fragments(project_id)`, `use_fragment(project_id, smiles, name='')`, `delete_fragment(fragment_id)`.

- [x] Write/run failing cases for ordered distances/angles/dihedrals, default moving last side, fixed-side switching, bond add/delete/order, mirror, fragment replacement and native state roundtrip.
- [x] Reuse existing graph/coordinate transforms; consolidate shared edits used by Agent and web. Do not introduce implicit whole-molecule reoptimization.
- [x] Implement validated SMILES library with connection point, preview support, shared persistence and project-first frequency ordering. No history entry for preview.
- [x] Verify stable surviving atom identity; expose changed/deleted atoms so caller can invalidate affected coordinate settings.
- [x] Run compileall, ruff and scoped geometry/library/internal-coordinate tests.

## Task 3: Independent frontend molecular window

**Files:** Create `frontend/src/MolecularWorkbench.tsx`, `frontend/src/workbenchApi.ts`, `frontend/src/workbenchTypes.ts`, `frontend/src/molecularWorkbench.ts`, `frontend/src/molecularWorkbench.test.ts`, `frontend/src/molecularWorkbench.css`; modify `frontend/src/Molecule3DViewer.tsx`.

**Interfaces:** Export `MolecularWorkbench({project, source, onClose, onSaved, onError})`; `source` matches `/open` input. Viewer accepts ordered selection and callback, explicit topology and actual mode displacements, retaining existing callers until root migrates DAG. `workbenchApi` handles these domain endpoints and exports types to root.

- [x] Add tests for ordered selection, coordinate interpretation, curve/frame identity, draft undo and settings validation.
- [x] Build modal with file/text/SMILES open/new, latest-frame default, frame slider, scalar SVG curves, CSV, signed mode selection/playback, RMS force and scan/PES view.
- [x] Add measured coordinates and edit/scan/freeze actions, fixed-side toggle, manual moving-group selection, labels/sidebar, topology and fragment-library controls, mirror and undo.
- [x] Save complete draft with explicit scientific settings, optional native input generation and visible success/error; use confirmed original frame for provenance.
- [x] Run scoped TS tests and frontend typecheck/build.

## Task 4: API, persistence, Agent notification and merged products/DAG

**Files:** Create `cloudra/services/workbench.py`, `cloudra/services/api_v2/routers/workbench.py`, `tests/test_workbench_api.py`, `frontend/src/ResearchPanel.tsx`, `frontend/src/researchProducts.ts`, `frontend/src/researchProducts.test.ts`; modify router assembly, `App.tsx`, `ConsoleIndexPage.tsx`, `DagPanel.tsx`, `ArtifactsPanel.tsx`, `api.ts` exports as needed, styles and docs.

- [x] Add API tests for project boundaries, source opening/frame fetch, complete save plus native input, exact provenance and persistent Agent notification, and no automatic chemical ownership.
- [x] Wire Tasks 1–2 through protected, nonblocking routes. Save via existing workspace/atomic writes and artifact registration; send saved-path/provenance through existing Agent message path.
- [x] Generate Gaussian/ORCA inputs with shared writer and exact freeze/scan numbering. Preserve native settings; no invented method/basis; multiple scans are independent PES coordinates.
- [x] Create one combined page. Standard has products and small previews; DAG has graph/explicit object filtering. Remove the two old nav entries and permanent large DAG viewer.
- [x] Mount one project-scoped independent window at app level, open via products/DAG/molecule actions and a non-typing shortcut. Standard works without DAG.
- [x] Test conservative grouping and source routing, saved draft reopening, no synthetic scientific result in previews.

## Task 5: Integration review, visual verification and PR

- [x] Run compileall, ruff, affected backend tests, scoped frontend tests, typecheck and build. Fix shared causes across backends.
- [x] Exercise actual UI against isolated temporary runtime: standard products, opening multi-frame result, selecting/editing atoms, freeze/scan, save/reopen, fragment history and merged DAG navigation.
- [x] Independent whole-change review against the approved spec; fix important findings and rerun only affected checks.
- [x] Update user docs with actual controls and supported data, record material limitations accurately.
- [ ] Commit/sign off all workspace changes, push feature branch, create PR to master, report checks and remaining external CI status. Do not merge.
