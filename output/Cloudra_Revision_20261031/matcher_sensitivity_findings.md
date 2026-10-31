# IMP target-object matching: case audit and conditional ranking sensitivity

Date: 31 October 2026. **Status: reviewable attribution proposal and conditional mathematical sensitivity, not a replacement score table.** The original 200 publication scores and all components remain untouched.

## Main result

Both questioned runs currently have Graph = 1, Self-consistency = 1, Accuracy = 0, and Composite = 0.4. If an adjudication assigns the explicitly rejected scientific target to the appropriate delivered object, the existing negative-credit rule gives that target Accuracy = 1. Holding the published Graph and SC components fixed changes the case composite from 0.4 to 1.0, i.e. +0.6; over a ten-task IMP tier this is +0.06000 in that configuration's mean.

- **Record/IA5 only:** Record IMP mean 0.23250 -> 0.29250, moving above Standard (0.24733). The top two remain Brief and Guided.
- **Brief/IC3 only:** Brief IMP mean 0.48294 -> 0.54294; it remains first.
- **Both:** Brief 0.54294 > Guided 0.44506 > Record 0.29250 > Standard 0.24733.

The complete four-scenario, four-configuration table is [matcher_sensitivity_scenarios.csv](matcher_sensitivity_scenarios.csv). Every conditional row is explicitly labelled; the P0 rows reproduce the original publication track.

| Scenario | Guided | Standard | Record | Brief | IMP order |
|---|---:|---:|---:|---:|---|
| P0_original | 0.44506 | 0.24733 | 0.23250 | 0.48294 | Brief > Guided > Standard > Record |
| S1_Record_IA5_target_credit | 0.44506 | 0.24733 | 0.29250 | 0.48294 | Brief > Guided > Record > Standard |
| S2_Brief_IC3_target_credit | 0.44506 | 0.24733 | 0.23250 | 0.54294 | Brief > Guided > Standard > Record |
| S3_both_target_credits | 0.44506 | 0.24733 | 0.29250 | 0.54294 | Brief > Guided > Record > Standard |

## Why this is an attribution question

The final-claim rule is already specified: a correctly denied Gold-negative target receives Accuracy 1; a positive claim, missing claim, or trustworthy numeric answer for that target receives 0. The issue is deciding **which delivered object answers the requested target** before applying that rule. Two different pathways can have the same atom-connectivity endpoints, and two different electronic states can share exactly the same SMILES and bond-change signature.

The current matcher first ranks endpoint species and bond-change similarity. Among candidates with the same best bond-change difference, it deliberately prefers a positive claim over a negative one. That policy detects contradictory claims about the same object, but it currently lacks a prior separation of distinct stereochemical pathways or electronic-state targets. Merely changing the rule to “prefer any negative edge” would be inappropriate: a duplicate refusal must not hide a positive claim about the very same target.

**Reviewable correction proposal:** identify the requested reaction channel or electronic state using the original task and the run's own explicit final graph/annotations; form the candidate set for that object; retain the existing contradiction/negative-credit rule within that object. Do not infer identity from Gold accessibility, from whichever choice earns credit, or from run score alone. Do not edit the delivered scientific claims or introduce a new chemical threshold.

## Record/IA5: disrotatory versus conrotatory ring opening

The task asks specifically for **thermal disrotatory** cyclobutene ring opening. Its reference edge and TS are inaccessible; the reference carries no barrier. The Desktop package's per-run catalogue reports that Record delivered an inaccessible `e_dis` and `TS_dis`, with no barrier for that target, and separately delivered an accessible conrotatory `e_con` with barrier 33.57 kcal/mol. Its original catalogue explicitly attributes Accuracy 0 to the duplicate-endpoint matcher selecting the positive alternative.

These reported claims support the following proposed mapping: Gold disrotatory target -> Record `e_dis` / `TS_dis`; the conrotatory edge is a distinct investigated alternative, not a positive assertion about the forbidden disrotatory target. On that assignment the existing binary negative rule gives Accuracy 1. The original FULL graph now independently confirms this assignment: `e_dis` has `channel="disrotatory"`, `accessible=false`, `via="TS_dis"`, and no barrier; `e_con` has `channel="conrotatory"`, `via="TS_con"`, and barrier 33.57. The original final PROCESS decision (lines 85--90) explicitly states that the requested disrotatory pathway is refused and that the sole verified barrier belongs to the conrotatory alternative. This confirms the audit catalogue against the actual final delivery.

A read-only Accuracy replay on the FULL Record graph selects `e_con` and returns 0. Both channel edges have endpoint cost 0 and bond-change difference 0. The unchanged negative predicate accepts `e_dis`; limiting the in-memory candidate graph to that target gives Accuracy 1. No delivered file was edited.

Original package anchors:

- `Cloudra-P2-final-20261031/reports/catalog.csv`, Record/IA5 row: “TS_dis + e_dis declared accessible=false, no barrier (correct refusal); allowed conrotatory channel computed separately (33.57); accuracy 0 because duplicate endpoints matched the positive edge”.
- FULL `cloudra-p2c-20261025/record/r1/sandboxes/IA5/batch_76e567788441411d/mechanism_graph.json`; final `PROCESS.md`, lines 85--90.
- `reports/divergence_report.md`, Q3, explicitly distinguishes the disrotatory refusal from the conrotatory calculation.
- Formal task: `ideapool/tasks/impossible/IA5.json` (task query; Gold `IA5_E1`, `IA5_TS1`).

## Brief/IC3: lowest open-shell singlet versus a characterized closed-shell branch

The requested target is the lowest singlet of phenylnitrene and its singlet--triplet gap. The preserved graph distinguishes:

| Delivered object | Scientific identity in the saved graph | Final claim |
|---|---|---|
| `T1_3A2` | Triplet ground-state reference | Characterized reference state |
| `S1_1A1`, reached by `e1_T1_to_S1` | Closed-shell singlet, explicitly “NOT the lowest singlet” | Characterized alternative branch; relative energies are explicitly not the requested gap |
| `S2_1A2`, reached by `e2_T1_to_S2` | Open-shell singlet, explicitly “the true lowest singlet, declared but NOT computed” | Node and edge `accessible=false`; no barrier or target gap declared |

The graph's `singlet_triplet_gap_kcal_mol` is a **string explicitly refusing the requested number**, not a numeric gap. Its PM7 +45.9 and GFN2-xTB -1.7 kcal/mol descriptions are explicitly restricted to the closed-shell branch and excluded from the target gap. Whether the qualitative electronic-state explanation is chemically correct is a separate scientific question; this audit does not change the task's existing acceptance standard. It verifies which target the saved final claim addresses.

The proposed mapping is Gold lowest-singlet target -> `S2_1A2` and `e2_T1_to_S2`, retaining `S1_1A1` as a different characterized state. A read-only replay of the actual current Accuracy code on the preserved graph gives:

- Both edges have endpoint species cost 0 and bond-change difference 0.
- Current selection: `e1_T1_to_S1`; it is effectively accessible and fails the existing negative predicate -> Accuracy 0.
- `e2_T1_to_S2` is effectively inaccessible, has no barrier, and its target endpoint is explicitly inaccessible; no trusted numeric target property is present -> it **passes the unchanged negative predicate**.
- Restricting the in-memory candidate graph to this target edge, without changing any node, claim, or numeric value, gives Accuracy 1. This is an assignment sensitivity replay, not a saved graph correction or a full rescore.

The preserved IC3 graph is the documented evidence-reference repair. Its provenance states that only prose reference paths were converted to path lists; no SMILES, state, edge, energy, or scientific claim changed. A direct comparison with the original FULL graph confirms that the only six changed JSON paths are `evidence_log` and the added `evidence_log_original` fields on the three nodes. Every scientific state, edge, energy, accessibility flag, and target claim is identical. The original final PROCESS text (lines 107--123) explicitly reports a partial delivery, three distinct electronic states, an inaccessible 1A2 target, and no numeric singlet--triplet gap.

Anchors: `reconstructions/brief-errors/IC3/mechanism_graph.json`; `reconstructions/brief-errors/IC3/provenance.md`; `ideapool/tasks/impossible/IC3.json`. FULL raw-graph Accuracy replay details for both cases are saved in `/private/tmp/ia5_ic3_full_match_replay.json`.

## Original scoring records and raw-source verification

The FULL `benchmark.db` records were opened read-only. Record/IA5 has Graph 1, SC component 1, Accuracy 0, final 0.4; its note says Gold IA5_E1 received zero for a positive or missing negative claim. Brief/IC3 has raw Graph 0.33333333333333337, SC component 0.5, Accuracy 0, and final -1, with unbound-node/evidence-reference notes. The published IC3 evidence-reference repair restores Graph and SC to 1 and the composite to 0.4 while leaving Accuracy 0. These raw diagnostics and the publication baseline are different tracks; the sensitivity starts from the latter.

| FULL original file | SHA-256 |
|---|---|
| Record/IA5 `mechanism_graph.json` | `83fb2f1fd1e2e2c2ee31ef61e4c1260d350c7a5e93c4196c5b44f225873668d1` |
| Record/IA5 `PROCESS.md` | `67d78c568ec7d6eb25b4098cf0ccce846fe68db1ea8926959c6b2fa568dede13` |
| Brief/IC3 `mechanism_graph.json` | `6949b205c40752fd82067532f9eabed1a53e0ac612b3c4992e9817dbde2b0040` |
| Brief/IC3 `PROCESS.md` | `4b7586ab12d18182ab734bd3a713798bf5d0b74f3523bc35565c14270dc377ef` |

The extracted files are under `/private/tmp/cloudra_revision_full/cloudra-p2c-20261025/{arm}/r1/sandboxes/{task}/{batch}/`. They were read without alteration. The object-assignment proposal is now supported by both original final graphs and final process statements, rather than by the lightweight audit notes alone. Applying an official score change remains an explicit adjudication decision; this report does not apply it.

## Graph and Self-consistency are not re-adjudicated here

Both published cases already have Graph = 1 and SC = 1. The conditional calculation changes **only the Accuracy target assignment**. Correcting which graph object answers a task does not itself supply, remove, or validate TS/IRC/frequency evidence. Consequently there is no basis in this sensitivity calculation to increase, decrease, or relabel Graph or SC. A future state-aware graph comparison or complete scorer rerun could have separate effects, but those effects are not inferred here. The table's “frozen original” treatment is an explicit arithmetic condition, not a prediction of a new full scoring run.

## Unresolved-adjudication bounds

Under the existing binary negative-credit rule each questioned target is assigned either 0 or 1; no new fractional score is proposed. If adjudication remains unresolved, the two-case sensitivity envelope is:

- Record IMP mean: **[0.23250, 0.29250]**, possible rank 4 or 3.
- Brief IMP mean: **[0.48294, 0.54294]**, rank 1 in every listed scenario.
- Guided: 0.44506, rank 2 throughout; Standard: 0.24733, rank 3 or 4.

Thus the two-case calibration can swap Record and Standard in IMP, but cannot change the top two IMP positions. For the full 50-task means, each single case's +0.6 composite contributes +0.01200 to its configuration's mean; the overall arm order remains Guided > Brief > Record > Standard in all four scenarios.

## Source integrity and scope

The arithmetic starts from the 200-row publication score table, not the raw -1 diagnostic snapshots. It adds only the applicable case delta, preserving all other reported values and rounding conventions. It does not recompute all composites from rounded components.

- Publication source: `paper/figures/benchmark_p2_20261031/source_data/publication_scores_per_run.csv`.
- Source SHA-256: `3a211750e47ee5fb291e8d1699c16a6bec1a8dec31e8a2a0483605e4b5b6faec`.
- 200 task/configuration pairs; 10 IMP tasks per configuration.
- Weights remain 0.1 Graph + 0.3 SC + 0.6 Accuracy.
- No code, Gold, delivered graph, source score CSV, or published figure was changed.
- This report and its scenario CSV are analytical proposals for review; no formal score correction has been applied.
