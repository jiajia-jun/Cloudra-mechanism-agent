# Post-hoc reconstruction - standard/HA1 (hard task)

> **POST-HOC RECONSTRUCTION BY AUDIT, NOT AGENT-DELIVERED.** This `mechanism_graph.json` was reconstructed after the fact by the std-auditor from the run's own preserved artifacts. It was never written by the agent, was never present in the original sandbox when scoring ran, and does not change the raw benchmark row.

- Campaign / arm: `/home/ly/cloudra-p2c-20261025/standard/r1` (arm `standard`, batch `batch_8b2051b670f348ba`)
- Original sandbox (never modified): `/home/ly/cloudra-p2c-20261025/standard/r1/sandboxes/HA1/batch_8b2051b670f348ba`
- Original benchmark row: `benchmark.db.runs` final_score = -1.0 (integrity no-evidence penalty; no mechanism_graph.json in sandbox at scoring time)
- Reconstructed file: `/home/ly/adjudication/reconstructed/standard/HA1/mechanism_graph.json`
- Reconstruction date: 2026-10-29 19:31 +08:00
- Track: separate `repaired` track (scored by teammate fair-scorer from shadow copies); raw/offline score rows are untouched.

## 1. Why the graph is missing

Run was finalised at 2026-10-26T23:50:02Z (run.finished seq 494): the agent called stop() while scan job 676 and minima jobs 677-679 were still running. A scheduled reminder later restarted the session (seq 501/502, 23:53:07) but the batch had already advanced to HA6, so no further work happened. Both TS channels were still unconverged.

## 2. Sources used (only this run's own artifacts)

- PROCESS.md (two conrotatory channels: outward -> (E)-penta-1,3-diene; inward -> (Z)-penta-1,3-diene; shared bond-change set)
- jobs/reactant_min.log (reactant minimum)
- jobs/prodE_min.log ((E)-product minimum)
- jobs/prodZ_min.log ((Z)-product minimum)
- ts/ts_0001/jobs/declaration_0003/ts_opt/refine.log (Normal termination after 16 s, no stationary point; pipeline reported 'optimization did not prove normal termination')

## 3. Reconstructed nodes

| node | role | SMILES | E / Hartree (declared, from log) | evidence log (sandbox-relative) | notes |
|---|---|---|---|---|---|
| RC | reactant | `CC1CC=C1` | -195.165893758 | `jobs/reactant_min.log` | Minimum, 0 imaginary frequencies, Normal termination. |
| TS1 | transition_state | `[]` | - | `(none)` | Outward-rotation saddle never converged. |
| P | product | `C=C/C=C/C` | -195.187896036 | `jobs/prodE_min.log` | (E)-penta-1,3-diene minimum, 0 imaginary frequencies. |
| TSM1 | transition_state | `[]` | - | `(none)` | Inward-rotation saddle never converged. |
| M1 | product | `C=C/C=C\C` | -195.186154811 | `jobs/prodZ_min.log` | (Z)-penta-1,3-diene minimum, 0 imaginary frequencies. |

## 4. Reconstructed edges

| edge | from -> to | via | barrier (kcal/mol) | bond_changes | derivation / notes |
|---|---|---|---|---|---|
| e1 | RC -> P | TS1 | none | break [[2,3],[4,5]]; form [[2,5],[3,4]] | Outward-rotation channel from PROCESS.md (conrotatory ring opening, methyl outward); channel label 'outward_rotation'. No barrier computed. No favored flag: the run's own PROCESS.md marks H1/H2 as 'to be decided by computed barriers', and no computed barriers exist, so a favored declaration cannot be stood behind. |
| e2 | RC -> M1 | TSM1 | none | break [[2,3],[4,5]]; form [[2,5],[3,4]] | Inward-rotation channel from PROCESS.md; channel label 'inward_rotation'. No barrier, no favored flag. |

## 5. Barrier arithmetic (native log energies, 627.5094740631 kcal/mol per Hartree)

- No edge carries a barrier: no frequency-verified first-order saddle exists anywhere in this run's sandbox, so none could be derived from the artifacts.

## 6. What could NOT be reconstructed

Both saddle geometries/frequencies, both barriers, IRC/endpoint verification, and the qualitative favored-channel assignment. The channel topology and bond changes come from the run's written hypothesis.

## 7. Accessible-flag justification

Accessible hard task: all nodes left accessible; no favored flag is declared (see e1/e2 notes).

## 8. Local validation (stock scoring pipeline on a hardlink shadow copy)

- Replay location: hardlink shadow of the original sandbox under `/home/ly/adjudication/audit-shadow/HA1/` with the reconstructed graph written only into that shadow root (this directory was removed after validation; the original sandbox was never written).
- Component scores: graph = 1.0, self-consistency = 0.0, accuracy = 0.0, final (repaired) = **0.1** (composite).
- Node bindings: [["RC", true, 1.0, ["jobs/reactant_min.log"]], ["TS1", true, 1.0, []], ["P", true, 1.0, ["jobs/prodE_min.log"]], ["TSM1", true, 1.0, []], ["M1", true, 1.0, ["jobs/prodZ_min.log"]]]
- Expected effect vs -1.0: graph=1.0000, selfc=0.0000, accuracy=0.0000 (no favored channel declared; selectivity slot scores 0) -> repaired_final=0.1000.

## 9. Confidence

**MEDIUM** - All three species minima are verified native Gaussian logs; the two-channel reaction graph is the run's own hypothesis. No TS or barrier evidence exists at all, so the selectivity question the task asks is not reconstructable - only the structure is.

## 10. Integrity statement

Original sandboxes, campaign databases (`benchmark.db`), runtime databases, the task bank and all product code were read only. No file outside `/home/ly/adjudication/` was created or modified. The reconstruction is an adjudication artefact for the `repaired` track only; it must never be presented as the agent's delivered result.
