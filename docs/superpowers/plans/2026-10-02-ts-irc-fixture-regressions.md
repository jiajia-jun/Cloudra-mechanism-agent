# TS/IRC fixture regression plan

**Goal:** Exercise the existing TS pipeline with repository artifacts, real parsers,
immutable stage inputs, the temporary compute ledger, and the system driver.

**Scope:** Tests only unless a new test demonstrates a defect. No changes to chemistry
methods, thresholds, production state, or scheduler processes. Run focused tests only.
Synthetic benchmark fixtures remain explicitly labelled contract data.

- [x] Replay scan logs and sidecars through terminal events: internal peak versus
  monotonic scan, failed execution, duplicate notifications, unchanged resumes.
- [x] Replay frequency evidence through admission: zero, one, absent, and multiple
  imaginary modes; missing saved geometry; native Hessian present versus absent.
- [x] Replay IRC and endpoint artifacts: partial Gaussian paths, missing ORCA
  sidecars, converged minima, missing evidence, mismatched geometry, and wrong modes.
- [x] Add an Agent scenario using fixture artifacts with real persistence and driver.
- [x] Verify compileall, ruff, related tests; inspect meaningful failure mutations.

## Validation

- New fixture replay module: 38 cases passed, independently reviewed.
- Related parser, pipeline, recovery, scenario, input and async-guard tests:
  262 passed (no skips); compileall and ruff passed.
- Actual temporary source mutations were caught for zero-mode admission,
  stale IRC geometry, missing endpoint geometry validation and wrong Hessian
  source. Production source was restored byte-for-byte after each check.
- Native logs are reused unchanged except explicitly labelled contract fault
  injection. A Hessian placeholder checks routing only; it is never executed.
