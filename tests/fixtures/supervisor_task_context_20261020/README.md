# HB10 Supervisor task-context regression

This is a small, verbatim event excerpt from the real DeepSeek V4 Flash HB10
run in `batch_159a23ad57b64073` on 2026-10-20. It contains no Gold, credentials,
model configuration, or quantum-calculation logs.

The complete blind task told the coordinator to report electronic barriers
“without ZPE or thermal corrections.” The initial task was historically stored
with `sender=system`; this fixture preserves that original value. The first
Supervisor received only a generic supervision notice. The actual pre-contract
input export contains 34 messages and does not contain the electronic-barrier
clause or the complete original request. The full input export is not duplicated
here; its SHA256 and the independently retrieved source archive SHA256 are in
`manifest.json`.

The Supervisor then called `dag_set_coverage_contract` with
`require_thermochemistry=true`. The exact arguments and successful tool receipt
are retained, along with their original event ids and timestamps. This excerpt
establishes the information gap; it does not by itself prove why the model made
that scientific choice, change the task contract, or declare a scientific result.

The regression reads the unchanged historical excerpt, then replays its complete
blind request through a **new** user-origin `CommandBus` spawn. The corrected
entry point creates a new event with trustworthy user provenance. Existing
Supervisor task pins must deliver that full scope to both a process Supervisor
and an independent final-review session. The old notification remains a system
notice, not a new human constraint. No past event is rewritten or relabelled, no
external model runs, and no QM job is launched.
