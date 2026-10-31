# Speed, effort and delivery evidence for the manuscript update

## Controlling sources and grains

P2 final source is `/Users/cloudrayyy/Desktop/Cloudra实验数据/Cloudra-P2-final-20261031/tables/final_scores_per_run.csv`, 200 unique arm/task rows (50 tasks × four arms, one retained run per pair). Its `repaired_final` overrides `fair_final` for the released official total. The main comparison is standard/backbone versus guided; record and brief-errors are ablations.

P2 final CSV has **no run start, end or walltime**. A targeted local inventory found no P2 campaign summary or original sandbox; `/home/ly/cloudra-p2{b,c}-20261025` paths do not exist on this machine. Thus P2 run speed cannot be reconstructed from the supplied final bundle.

P1b root SUMMARY and runs CSV were streamed out of the 2.4 GB tar; neither contains run elapsed times. Twelve small `benchmark.db` files were then streamed out (under 4.5 MB combined), with no calculation sandboxes extracted. Their `batches.started_at` and `finished_at` are true start/end timestamps. **The available speed grain is a four-task batch at concurrency two: 3 batches per arm, 12 batches total, containing 48 task-runs.** `runs.ts` is a scoring timestamp, so adjacent run timestamps cannot recover individual latency when tasks overlap.

P2 effort comes from `reports/flex_table.csv`: 63 older deep-dive snapshots covering 16 selected tasks (guided/record/standard 16 each, brief 15; brief/HH1 absent). Pair all arms on the common 15 tasks / 60 observations. The source report defines job-hours as sum of QM process end−start, **not run elapsed, core-hours, monetary cost, or a full-200-run estimate**. There is one stated exception: standard/M1 ran outside the compute ledger; its 25 jobs and 5.1 job-hours were reconstructed from native logs' Job CPU time divided by four. This exception is marked row by row in the output.

## True elapsed time: pilot only

| arm | n batches | mean four-task batch h | median h | range h |
|---|---:|---:|---:|---:|
| standard/backbone | 3 | 3.958 | 4.031 | 2.504–5.338 |
| guided | 3 | 4.451 | 4.238 | 3.867–5.249 |
| record | 3 | 3.894 | 3.643 | 2.620–5.419 |
| brief-errors | 3 | 4.827 | 3.648 | 3.566–7.269 |

The guided pilot batches took 12.5% longer than standard on average and 7.8% less time than brief. These are elapsed time to batch completion including the batch's original failures. Do not call the result "time to a scientifically accepted solution." With only three repeats, show all 12 points; do not imply a universal speed ranking. The campaign itself ran from 2026-10-24 03:42:31+08 to18:11:33+08 (14 h 29 min 02 s), with the arms progressing concurrently.

Files: `p1b_batch_elapsed.csv` (12 real start/end rows), `p1b_batch_elapsed_arm_summary.csv`, `p1b_batch_time_paired_deltas.csv`. `p1b_original_run_records.csv` preserves the original 48 rows and full scoring notes for lineage; those raw scores are not the P2 official scores. Extraction manifests name exact tar members.

## P2 investment and outcome on common tasks

| arm | n task-runs | mean job-h | mean QM jobs | done / total | failed+cancelled / total | official final mean |
|---|---:|---:|---:|---:|---:|---:|
| standard/backbone | 15 | 7.555 | 27.93 | 324/419 | 95/419 (22.7%) | .64948 |
| guided | 15 | 11.079 | 52.60 | 581/789 | 208/789 (26.4%) | .81241 |
| record | 15 | 7.877 | 28.73 | 331/431 | 100/431 (23.2%) | .73595 |
| brief-errors | 15 | 15.590 | 58.87 | 596/883 | 287/883 (32.5%) | .72733 |

Within this selected cohort, guided uses 46.7% more recorded job-hours than standard and gains .16293 official score. Guided uses 28.9% fewer job-hours than brief and gains .08508. These numbers show different compute-to-delivery behavior; they do not measure P2 run speed. The inputs and attempts are different grains: `n_ts_jobs=0` does not mean no TS calculation occurred, and TS/IRC job categories overlap. Use `n_qm_jobs` and terminal counts for total work.

`p2_effort_common15.csv` contains the 60 aligned observations, old input counts and final scores. `p2_effort_paired_deltas.csv` keeps per-task comparisons. Standard manual graph reconstructions are flagged, because comparing official scores on repaired standard cases is not the same as autonomous delivery.

## Delivery is separate from both runtime status and continuous SC scores

The final adjudication records seven genuinely absent root graphs, all standard: F1, M17, P3, NR1, HA1, HF1, IA9. The root graph counts are therefore standard 43/50, guided/record/brief 50/50; these are package-adjudication facts, not a new scan of omitted sandboxes. The seven subsequent standard graphs are audit reconstructions, not agent-delivered graphs. Brief/IC3 had a root graph but one prose evidence reference was manually corrected; count it as a packaging repair, not a missing graph.

The design mechanism behind standard's missing graphs is explicit in KNOWN_ISSUES K1: `stop` intended to wait for unfinished jobs was treated as final completion, so the run was scored before late results could be integrated. This is a completion-state error, not evidence that more compute would necessarily produce a correct mechanism. Its reconstructed scores range .0333–.3425 (mean .15374).

Other concrete runtime/contract cases stay distinct:

- guided/HF1 had a supervisor exit-review race crash, yet its preserved sandbox was complete and offline score .9742; it is not a missing-root-graph case.
- guided/HI1's terminal job notification was injected but did not wake the hibernating session; a reminder later resumed it, and it autonomously delivered .9999. The exact documented notification→reminder wake interval is 18:55:01.232Z→19:36:58.652Z, **41 min 57.420 s**. The stop→reminder interval is **1 h 49 min 11.581 s**, which should not be described as post-compute idle time. K2's early prose was corrected later in the same ledger.
- brief/HL1 hit the DAG-delivery gate after null endpoint filenames blocked short-IRC registration (K8/K9). The final raw/fair score is nevertheless .9250, not zero, with SC=.75; the sandbox was scored. Avoid reusing the earlier K9 expectation of a crash/0 row.

Final CSV continuous SC_all=1 observations are guided31, record19, standard8, brief26. Six rows have no SC component: guided3, standard1, brief2. This statistic is **score exactly one**, not the unavailable `selfconsistency_passed` boolean. Impossible tasks can receive SC=1 for explicit negative conclusions, so a mechanistic evidence panel should use the 40 non-impossible tasks separately:

| arm | mechanistic n | root graph present | SC=1 | SC<1 | SC missing |
|---|---:|---:|---:|---:|---:|
| standard/backbone | 40 | 34 | 6 | 33 | 1 |
| guided | 40 | 40 | 23 | 14 | 3 |
| record | 40 | 40 | 16 | 24 | 0 |
| brief-errors | 40 | 40 | 20 | 18 | 2 |

For standard's seven reconstructions, the CSV's graph/selfc/accuracy columns remain the original no-graph components (zeros) while `repaired_final` is a separate total. Never stack those components to depict the repaired composite. The corresponding repair components can only be taken separately from reconstruction INDEX/provenance.

Old `undelivered` records whether `.cloudra/mechanism_evidence.json` exists. It is neither root graph absence nor scientific acceptance. In the 63-row effort snapshot, manifest-present counts are guided10/16, record0/16, standard0/16, brief1/15; root graphs existed in many of those "undelivered" rows. Do not reproduce the old report's mislabeled verification-success rates.

## Why a 200-run TS / IRC / endpoint pass funnel is unavailable

The package's raw CSV exports only `notes_first`, capped at 220 characters, rather than complete stage results. `product_patch_validation.json` holds fuller notes for 10 selected defect cases only. `reports/evidence_notes.md` is a 63-case older analysis; its diagnostic counts are failure-message mentions, not stage acceptance. None of these can yield a defensible 200-run three-stage pass funnel. There is no need to invent a new threshold or infer passes from score fractions. A complete per-edge stage panel would require the preserved scorer stage results or original sandboxes.

## Recommended clear panels

1. **Pilot elapsed time (separate panel / pilot subsection).** Horizontal four-arm strip plot of the 12 `p1b_batch_elapsed.csv` values; primary standard and guided colored, ablations muted, three actual points and a short mean line. Label "P1b: four-task batch elapsed time (h); concurrency 2; n=3 batches/arm". No violin or fitted density for n=3. Never mix this x axis with P2 job-hours.
2. **P2 compute investment (main standard–guided comparison).** Align 15 tasks vertically. Left: paired standard/guided points on job-hours; right: the same tasks' official-score difference guided−standard with a zero reference. Mark standard manual reconstructions with an open symbol. Use `p2_effort_common15.csv` / paired deltas. This connects extra work to actual per-task outcome without hiding large cases in arm averages. Put four-arm mean+raw point overview in the ablation supplement if space is tight.
3. **P2 delivery completeness.** Root-graph delivery bars, n=50 per arm; show standard43/50 and a separately hatched audit-reconstruction segment7/50. Do not relabel the full bar "autonomous delivery 100%" after reconstruction.
4. **P2 scored evidence strength.** Three-state horizontal stacks SC=1 / SC<1 / missing for the 40 non-impossible tasks. Primary standard versus guided first, ablations below or in supplement. Caption explicitly identifies a continuous SC component, not scientific pass; this allows readable evidence comparison with exact known denominators and unknowns.

## Reproduction

`extract_pilot_sources.py` replays exact small-file streaming extraction from the supplied local archive. It is not needed when the supplied extracted copies are retained. Run `python reproduce_p1b_batch_time.py` and `python reproduce_speed_delivery.py` in this directory. Both read originals/copies only and write derivatives beside themselves. No scorer, model, QM calculation, or campaign is started.
