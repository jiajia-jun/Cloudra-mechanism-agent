# D1 evidence and review repair plan

> Execution: implement the already-authorized fixes in this session, with independent runtime and parsing tasks in parallel under dispatching-parallel-agents. Review the combined diff before completion.

**Goal:** prevent unrelated molecular evidence from satisfying delivery, make review outcomes and wake receipts truthful, and remove the reproduced QM parsing failures.

**Architecture:** retain the simple file submission tools. Validate the submitted evidence set against the declared species, and evaluate approved sets rather than borrowing arbitrary historical files. Use existing geometry/connectivity criteria and immutable snapshots. Keep administrative review acceptance distinct from scientific acceptance.

**Spec:** the D1 diagnosis in this conversation and repository AGENTS.md.

**Constraints:** no new scientific thresholds, no automatic IRC waiver or barrier-reference change, no compatibility shims; no live calculation mutation; preserve unrelated work; run only affected tests. No commit or push requested.

## Tasks

- [x] Evidence: add failing real-log regressions for a fragment standing in for a complex, mismatched optimization/frequency, incomplete component coverage and stale evidence borrowing. Implement checks in `cloudra/dag/file_science.py` and file submission/review callers; allow complete component submissions without new public tools.
- [x] Benchmark: require every represented component to have minimum evidence in `cloudra/benchmark/selfconsistency.py`, retaining existing scientific criteria and no scoring weight changes. Add focused regression.
- [x] Review: use the same scoped review basis for creation and resolution; show remaining stages only in `cloudra/dag/controller.py`; return explicit unresolved scientific checks and no implied stage waiver for exception decisions. Add public-tool regressions.
- [x] Notifications (delegated): distinguish trusted system Supervisor feedback from privilege-expanding delegation in `hub_bridge.py`; truthful receipts and event/state scenario regression. Preserve failed/cancelled and ordinary permission boundaries.
- [x] Parsing (delegated): recognize DefGrid3 as an ORCA control token; verify logs with detected engine, fail loud on conflicts. Test ORCA/Gaussian and unknown methods/logs.
- [x] Guidance: explain that unsuccessful searches do not prove nonexistence, and component evidence cannot by itself waive IRC or certify a complex minimum. Do not alter live benchmark conclusions or results.
- [x] Validation: compileall, ruff, affected DAG/benchmark/runtime/parser tests and scenario regressions. Review the diff and report remaining scientific decisions separately.

## Review focus

Wrong species with the same atom count; only one component frequency verified; newer failed evidence borrowing an older passing log; typed exceptions with no scientific effect; messages delivered without wake; unknown methods still blocked; no agent-facing mandatory bookkeeping fields.

## Verification result

- Syntax compilation and Ruff checks passed for `cloudra` and `tests`.
- The 19 affected test modules passed: **613 passed, 4 skipped**. Existing dependency deprecation and degenerate-rotation warnings remain.
- Cross-review added geometry regressions for unspecified versus explicit stereochemistry, rigid motion, atom order, reflections, distortion, and native xTB final structures; all passed.
- Read-only D1 log replay: ethylene alone leaves the reactant evidence incomplete; butadiene plus ethylene satisfies component coverage only; the one-imaginary-frequency complex remains incomplete.
- The existing missing-IRC agent scenario now asserts partial stage credit while preserving incomplete delivery and the IRC gap.
- No production data, running calculation, or live benchmark process was changed. Changes are not committed or pushed. Unrelated authentication and application-document work remains untouched.
