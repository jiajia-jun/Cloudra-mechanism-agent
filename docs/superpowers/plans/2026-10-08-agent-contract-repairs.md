# Agent contract repairs implementation plan

**Goal:** Repair the approved interface defects so model-visible contracts match execution and scientific verdicts remain independent.

**Architecture:** Reuse the existing Pydantic tool schemas, invocation lifecycle, atom identities and event delivery. Repair each contract at its source; do not add a second waiting system or universal state framework.

**Spec:** Findings approved in this chat on 2026-10-08.

## Constraints

- Preserve unrelated application materials and running calculations; no commit or push requested.
- No scientific thresholds, methods, scoring or wake policies change.
- No regex validation, legacy aliases or new synchronous operations inside async code.
- Verify syntax, lint and only affected test modules; use temporary data directories.

## Tasks

### 1. Operational success and common result types

- [x] Reproduce write/edit conflicts through the real executor in failing regression tests.
- [x] Make declined/conflict/failed writes report outer failure and applied writes report success.
- [x] Type actual todo/search result records and the TS scientific verdict without changing JSON behavior.
- [x] Run affected adapter, workspace, planning, search and TS tests.

### 2. Chemistry input contracts

- [x] Require explicit ts_guess mode and validate existing required inputs before effects.
- [x] Preserve automatic verify-engine detection and incomplete scientific evidence outcomes.
- [x] Rename qm_input_writer output_dir to output_path and update actual callers/examples without an alias.
- [x] Correct multi-component and computational-side-effect descriptions; clarify atom-reference sources.
- [x] Run affected TS-guess, QM-writer and conformer tests.

### 3. AgentHub model and execution contracts

- [x] Test missing/blank action-dependent inputs through the native bridge before mutation.
- [x] Express action-specific requirements in Pydantic validation and generated model declarations.
- [x] Type common posts, sessions and actual delivery receipts; validate the native output against its declared model.
- [x] Preserve retry, permissions, persistence and parked-notification behavior; run hub tests.

### 4. Declaration rendering and waiting explanations

- [x] Add a failing test for fixed-length tuple declarations becoming unknown.
- [x] Render prefixItems as typed tuples, including nested atom pairs.
- [x] Align compute-query, stop and autonomous-schedule explanations with existing event wake behavior.
- [x] Clarify concrete structure/digest/index provenance in existing TS inputs.
- [x] Run declaration, TS-input, schedule and async-loop guard tests.

## Final review

- [x] Inspect combined diff and have an independent agent review the completed changes.
- [x] Verify unchanged scientific outcomes, no hidden effect changes and no stale in-scope call sites.
- [x] Run compileall, ruff and the relevant test modules; report actual results.

## Validation results

- Syntax and lint checks passed for cloudra and tests.
- Final affected-module run: 772 passed, 5 skipped, 1 failed (778 collected).
- The failing real CREST/QCG integration invokes the local xTB binary, which exits with a segmentation fault. The same case loaded from the unchanged HEAD conformer module fails identically; no scientific parameters or success criteria were changed.
- Four skips are missing ORCA fixtures; one skip is the unavailable missing-xtb-IFF scenario because xtb-IFF is installed.
- Independent review found no remaining implementation blockers. Failure and baseline logs are retained in /private/tmp/cloudra_contracts_qcg_failure.
