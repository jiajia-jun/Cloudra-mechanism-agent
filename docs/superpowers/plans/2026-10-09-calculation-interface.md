# Calculation Interface Implementation Plan

> **For agentic workers:** Use the assigned parallel tasks below, then independently review the integrated change.

**Goal:** Repair the confirmed method-entry, configuration-reuse, revision and feedback traps without choosing scientific methods or adding approval policies.

**Architecture:** One shared `QmCalculation` uses explicit `engine`, one-token `method`, explicit `basis_set` (empty for no basis), `keywords`, `frequency_mode`, `orca_blocks` and `end_setting`. Writer and standalone scan tools expose these same field meanings. TS inputs may explicitly reference named complete calculations; each stage still explicitly selects its configuration. Partial revisions retain omissions; deliberate replacements and engine/method changes are explicit.

**Tech Stack:** Python 3.11+, Pydantic, existing TS ledger and input writers.

## Constraints

- Keep ordinary projects free of Benchmark whitelists; no new scientific thresholds, method defaults, approval mechanisms, or automatic exploration/formal-method choices.
- No regex input validation, synchronous blocking on async loops, or production quantum-computation interruption.
- No compatibility aliases for old method/basis or keyword spellings. Preserve historical inputs and jobs; old TS records remain read-only and cannot silently resume under the new format.
- Preserve unrelated dirty files. Compile, Ruff and focused tests only; mask real engines during unit/integration tests.

## Interfaces

- `cloudra/tools/core/qm_calculation.py`: `QmCalculation` is the shared complete configuration; no method/basis inference from a full route string. `method` contains only a native method token; basis-family slash suffixes and inline whitespace are rejected with actionable field errors.
- `cloudra/tools/core/ts_inputs.py`: `CalculationRef(ref)` and `TsInput.calculations: dict[str, QmCalculation]`; `resolve_calculation(value, definitions)` returns the complete configuration or raises for an unknown reference. Existing per-stage calculation fields accept complete configurations or references. Named configurations are local to a TS input, not a global registry.
- Revisions: calculation objects merge partial fields within the same method; `{"replace": complete_configuration}` performs an explicit replacement. Changing engine/method/basis without replacement fails loudly. Reference replacements are explicit; profile-map omissions remain unchanged and null removes an unused definition. Scan-coordinate revisions do not require copying its calculation.
- Runtime: `stage_calculation` resolves current references once for each stage; job steps retain complete actual calculation snapshots. Revision invalidation compares resolved before/after calculations so changing a referenced profile invalidates only dependent stages.
- New TS format 5 isolates old format 4 records without touching their calculation processes, locks, inputs or evidence.

## Tasks

- [x] Shared calculation schema, precise field validation, named TS references and omission-safe revisions. RED regressions cover keyword/native-block loss, coordinate-only patches, unknown references and incompatible engine changes; GREEN tests cover explicit clearing/replacement and explicit stage differences.
- [x] Align writer and standalone scan field meanings and descriptions; remove successful-input hints that reselect methods. Reject irrelevant operation fields, preserve explicit native input settings, and update their existing consumers/tests.
- [x] Resolve runtime configurations, comparison checks and selective evidence invalidation; retain immutable actual-job snapshots and format isolation. Migrate repository fixtures to the new public contract without changing scientific values.
- [x] Fix scan actual-method/contract projection and scan artifact visibility. Correct resume/recovery descriptions and update task-facing examples, keeping recovery gates intact.
- [x] Refresh existing TS-SOP and physical-thinking pins before model calls after event-log restoration; retain other pins and avoid creating guidance for uninvolved agents. Regressions cover fresh/incremental notice batches, scope and idempotence.
- [x] Compile, Ruff, focused regressions and zero-key Agent scenarios; independent review. Final focused suite in the primary workspace: 1100 passed, 10 optional-engine skips. Safe-restart boundary suite: 92 passed, 1 optional-engine skip.

## Delivery

Integrate only the task-owned files, safely restart the local service as authorized, then commit/push and verify the remote ref. Preserve all unrelated working-tree changes.

## Review Focus

1. Re-entering the same method with omitted keywords must preserve all prior settings.
2. A changed profile must not retroactively change historical job snapshots or invalidate unrelated stages.
3. Cross-engine replacements must not retain incompatible native blocks.
4. No-basis methods and explicit external engines must retain their actual requested method identity.
5. Scan preparation/inspection must report its real configuration and require the existing evidence-bound failed-scan recovery.
