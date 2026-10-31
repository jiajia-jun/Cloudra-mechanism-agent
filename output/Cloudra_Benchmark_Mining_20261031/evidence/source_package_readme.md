# Cloudra P2 benchmark — final results

Four-arm ablation of the Cloudra mechanism-discovery agent (guided / record / standard / brief-errors)
on a 50-task benchmark (20 easy, 10 normal, 10 hard, 10 impossible; 200 runs total).

## Official result

**Overall score: 0.705** (200/200 runs, equal weight; the 50 tasks are equally
weighted across arms).

| arm | easy | normal | hard | impossible | overall |
|---|---|---|---|---|---|
| guided | +0.881 | +0.737 | +0.958 | +0.445 | **+0.780** |
| record | +0.944 | +0.529 | +0.872 | +0.233 | **+0.704** |
| standard | +0.730 | +0.573 | +0.689 | +0.247 | **+0.594** |
| brief-errors | +0.905 | +0.586 | +0.828 | +0.483 | **+0.742** |

How the official score is defined: every run's saved sandbox was re-scored offline with the fixed
scorer (merged PR #246 + #247). Raw `benchmark.db` values are **not** the official numbers; they are
kept only for audit. Two documented repairs are included in the official numbers:
7 standard-arm runs had no delivered graph (harness finalised them early) and were reconstructed
post-hoc from their own logs, and 1 brief-arm run had a prose evidence reference hand-corrected.
Both are labelled and carry provenance under `reconstructions/`.

## What went wrong (short version)

The campaign finished 200/200, but several harness/scorer defects affected raw scores. Full details
and evidence are in `docs/KNOWN_ISSUES.md` (K1-K10). In brief:

- **Scorer defects (fixed, merged):** nested `accessible` flags, radical/non-Kekule species binding,
  and native xTB/`.xyz` evidence references were mishandled -> some correct deliveries were floored to -1.
  Fixed in PR #246 / PR #247 and applied in the official re-score.
- **7 standard-arm runs were finalised before their jobs finished** ("stop to wait" behaviour), so the
  sandbox had no `mechanism_graph.json` at scoring time. Their graphs were reconstructed afterwards from
  their own logs; these runs use the reconstructed score only in the `repaired` track and are marked.
- **guided/HF1 crashed** (supervisor exit-review race); sandbox complete, offline re-score 0.974.
- **guided/HI1 hibernated ~1h49m** after its last job (runtime notification did not wake the session;
  GitHub issue #248). It later completed and delivered 0.9999.
- **brief/HL1 could not register its IRC evidence** because the archived `irc_endpoints.json` had null
  endpoint filenames (K8); the agent refused to hand-edit evidence, so the DAG delivery was marked
  failed, but the sandbox was still scored (0.925).
- **No raw data were modified.** Sandboxes, DBs and logs remain on the host.

## Package contents

- `tables/FINAL_TABLES.md` - per-arm and per-tier tables (official track).
- `tables/final_scores_per_run.csv` - one row per run with the final score and its track/provenance.
- `tables/summary.json` - aggregates used for this report.
- `runs/raw_scores_p2.csv` - raw `benchmark.db` scores, for audit only.
- `reports/` - chemistry divergence analysis, flexibility analysis, TS-workflow statistics.
- `reconstructions/` - the 8 post-hoc repairs (graphs + provenance + index).
- `docs/` - known issues (K1-K10), scorer-fix PR description and patch, methodology notes.
- `MANIFEST.txt`, `SHA256SUMS` - package inventory and checksums.

## Where the raw campaign data lives

`/home/ly/cloudra-p2b-20261025` (3 pilot runs) and `/home/ly/cloudra-p2c-20261025` (197 runs):
per-arm `r1/benchmark.db`, sandboxes, runtime DBs and compute logs. Not included in this package
(too large).

Generated 2026-10-31T16:33:30.
