# DAG efficiency diagnostic fixtures

Minimal, sanitized excerpts used by `scripts/analyze_dag_efficiency.py` regression
tests and by the DAG evidence/review work (plan `docs/superpowers/plans/2026-09-04-dag-evidence-review.md`).
The raw run directory and `session.db` are intentionally **not** committed.

## Provenance

| Fixture | Source (original, sanitized) | Source SHA-256 | Extraction |
| --- | --- | --- | --- |
| `na1_constrained_opt.inp` | `NA1_exam/ts_e1/e1_c130.inp`（原始运行目录已随工作区清理删除） | `b6b8646c0515eed0818b25d58bc317ba37eeafd0080f9202b08bd478244bbc22` | full file; absolute machine paths replaced by `<sanitized>`/`<repo>` |
| `na1_constrained_opt.out` | `NA1_exam/ts_e1/.cloudra/calc-82.out.log`（原始运行目录已随工作区清理删除） | `07b6ee2541282e0faf9499acd1a8272fa1fe69f76ee0413c7fd4f7f8a469b13f` | 1-based line ranges 202-237 (input echo incl. Constraints), 574-590 (mid geometry-convergence block), 23121-23145 (final convergence), 23314-23320 (final single point energy), 23428-23433 (termination tail); concatenated verbatim, paths sanitized |
| `na1_identity_mismatch.json` | NA1 snapshot `session.db`（快照已随工作区清理删除）, table `dag_call_reviews`, row `rev_7e536dfb36c0441a819c4ee88b3b197a` (`reaction_mapping`) | result_summary SHA-256 `c0bce39c5bcb33f2c30b71325a0d582f4170de89964661de1193ce0d1f52e7ec` | full `result_summary` JSON, keys sorted |

Fixture file hashes (this repo): see `cases.json` consumers; current values recorded at
extraction time: inp `b0a40c8b…`, out `0bb9ec7b…`, json `8903074d…` (SHA-256, truncated here).

## Snapshot baseline

- Event window: 2026-09-04 04:38:33–08:14:13 UTC (single run snapshot, **not** the whole benchmark).
- Baseline counts: 63 jobs (47 done / 16 failed), 88 CallReviews (62 ignored / 22 reviewed / 4 pending),
  74 supervisor runs (identified via `agent.spawned` with `role_id=supervisor`, `run.started` pairs).

## Cases

`cases.json` fixes six diagnostic case classes. Each case lists conclusions that the
evidence may establish (`provable`) and conclusions it must **not** be taken to establish
(`not_provable`):

1. `constrained_opt_single_imag` — constrained Opt + exactly one imaginary frequency does not prove a full TS.
2. `wrong_product_identity_mismatch` — graph mismatch with declared SMILES is counterevidence.
3. `symmetric_mapping_ambiguity` — symmetry-driven mapping ambiguity is inconclusive mapping, not identity mismatch.
4. `converged_short_irc` — converged short IRC must not demand a fixed point count.
5. `out_of_order_evidence` — permutation of binding order must not change final conclusions.
6. `mid_swarm_alert` — coordinator must process mid-swarm alerts without cancelling valid background work.
