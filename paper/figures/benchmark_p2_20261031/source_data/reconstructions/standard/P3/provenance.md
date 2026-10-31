# Post-hoc reconstruction - standard/P3 (easy task)

> **POST-HOC RECONSTRUCTION BY AUDIT, NOT AGENT-DELIVERED.** This `mechanism_graph.json` was reconstructed after the fact by the std-auditor from the run's own preserved artifacts. It was never written by the agent, was never present in the original sandbox when scoring ran, and does not change the raw benchmark row.

- Campaign / arm: `/home/ly/cloudra-p2c-20261025/standard/r1` (arm `standard`, batch `batch_8b2051b670f348ba`)
- Original sandbox (never modified): `/home/ly/cloudra-p2c-20261025/standard/r1/sandboxes/P3/batch_8b2051b670f348ba`
- Original benchmark row: `benchmark.db.runs` final_score = -1.0 (integrity no-evidence penalty; no mechanism_graph.json in sandbox at scoring time)
- Reconstructed file: `/home/ly/adjudication/reconstructed/standard/P3/mechanism_graph.json`
- Reconstruction date: 2026-10-29 19:31 +08:00
- Track: separate `repaired` track (scored by teammate fair-scorer from shadow copies); raw/offline score rows are untouched.

## 1. Why the graph is missing

Run was finalised at 2026-10-26T05:13:51Z (run.finished seq 763) while the formal ts_0002 relaxed scan (job 342) and four conformer jobs were running. The scan actually terminated normally at 05:22:54 - about nine minutes after the sandbox had been scored - and was never parsed; no TS optimisation, frequency or IRC job was ever submitted.

## 2. Sources used (only this run's own artifacts)

- PROCESS.md (single concerted [3,3] Claisen step and bond changes)
- runs/conf0_optfreq.log, runs/conf1_optfreq.log, runs/conf3_optfreq.log, runs/rc_optfreq.log (four verified reactant conformer minima)
- runs/p_optfreq.log (product minimum)
- ts/ts_0002/jobs/declaration_0003/scan/scan.log (scan finished normally after scoring, but a scan profile is not a saddle/frequency log)

## 3. Reconstructed nodes

| node | role | SMILES | E / Hartree (declared, from log) | evidence log (sandbox-relative) | notes |
|---|---|---|---|---|---|
| RC | reactant | `C=CCOC=C` | -270.330333496 | `runs/conf1_optfreq.log` | Lowest-energy verified reactant conformer (conf1; conf0 = -270.329089709, conf3 = -270.32647888, rc_optfreq = -270.326478755). The task requires the lowest verified minimum as the barrier reference. |
| TS1 | transition_state | `[]` | - | `(none)` | No saddle was ever computed; the completed scan was never converted into a TS guess. |
| P | product | `O=CCCC=C` | -270.355290283 | `runs/p_optfreq.log` | Minimum, 0 imaginary frequencies (reaction DeltaE = -15.6 kcal/mol). |

## 4. Reconstructed edges

| edge | from -> to | via | barrier (kcal/mol) | bond_changes | derivation / notes |
|---|---|---|---|---|---|
| e1 | RC -> P | TS1 | none (no saddle log) | break [[3,4],[1,2],[5,6]]; form [[4,5],[1,6],[2,3]] | PROCESS.md hypothesis; this enumeration matches the gold reference bond-change set. No barrier is declared because no frequency-verified saddle exists (the completed scan profile is deliberately not converted into a declared barrier). |

## 5. Barrier arithmetic (native log energies, 627.5094740631 kcal/mol per Hartree)

- e1: none (no saddle log) (see evidence logs above; declared value equals the log-derived SCF difference rounded to 2 decimals).
- No edge carries a barrier: no frequency-verified first-order saddle exists anywhere in this run's sandbox, so none could be derived from the artifacts.

## 6. What could NOT be reconstructed

TS geometry/frequency, IRC, endpoint minima and barrier. The scan profile is documented as available-but-unparsed evidence.

## 7. Accessible-flag justification

Accessible task: all nodes left accessible.

## 8. Local validation (stock scoring pipeline on a hardlink shadow copy)

- Replay location: hardlink shadow of the original sandbox under `/home/ly/adjudication/audit-shadow/P3/` with the reconstructed graph written only into that shadow root (this directory was removed after validation; the original sandbox was never written).
- Component scores: graph = 1.0, self-consistency = 0.0, accuracy = 0.0, final (repaired) = **0.1** (composite).
- Node bindings: [["RC", true, 1.0, ["runs/conf1_optfreq.log"]], ["TS1", true, 1.0, []], ["P", true, 1.0, ["runs/p_optfreq.log"]]]
- Expected effect vs -1.0: graph=1.0000, selfc=0.0000, accuracy=0.0000 -> repaired_final=0.1000.

## 9. Confidence

**MEDIUM** - Five verified minima from native Gaussian logs; the reaction graph and bond changes are the run's own PROCESS.md hypothesis and match the reference. Missing: the TS and its barrier.

## 10. Integrity statement

Original sandboxes, campaign databases (`benchmark.db`), runtime databases, the task bank and all product code were read only. No file outside `/home/ly/adjudication/` was created or modified. The reconstruction is an adjudication artefact for the `repaired` track only; it must never be presented as the agent's delivered result.
