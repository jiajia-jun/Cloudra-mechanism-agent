# Post-hoc reconstruction - standard/F1 (easy task)

> **POST-HOC RECONSTRUCTION BY AUDIT, NOT AGENT-DELIVERED.** This `mechanism_graph.json` was reconstructed after the fact by the std-auditor from the run's own preserved artifacts. It was never written by the agent, was never present in the original sandbox when scoring ran, and does not change the raw benchmark row.

- Campaign / arm: `/home/ly/cloudra-p2c-20261025/standard/r1` (arm `standard`, batch `batch_8b2051b670f348ba`)
- Original sandbox (never modified): `/home/ly/cloudra-p2c-20261025/standard/r1/sandboxes/F1/batch_8b2051b670f348ba`
- Original benchmark row: `benchmark.db.runs` final_score = -1.0 (integrity no-evidence penalty; no mechanism_graph.json in sandbox at scoring time)
- Reconstructed file: `/home/ly/adjudication/reconstructed/standard/F1/mechanism_graph.json`
- Reconstruction date: 2026-10-29 19:31 +08:00
- Track: separate `repaired` track (scored by teammate fair-scorer from shadow copies); raw/offline score rows are untouched.

## 1. Why the graph is missing

Run was finalised at 2026-10-25T18:57:51Z (runtime run.finished seq 456) while every Gaussian job needed for the mechanism was still running: the agent called stop() with an empty final answer to wait for jobs 67 (TS opt), 68/69 (RC conformers) and 70 (product). The late job notifications (job 68 failed 19:12, job 70 done 19:15, job 67 failed 19:15, job 69 failed 20:53) were injected after the run had already been scored, so no mechanism_graph.json was ever written.

## 2. Sources used (only this run's own artifacts)

- PROCESS.md (mechanistic hypothesis and the exact bond-change enumeration)
- runs/p_opt.log (only normally terminated job: product minimum)
- runs/rc_opt.log, runs/rc2_opt.log, ts/ts_0001/jobs/declaration_0002/ts_opt/refine.log (all error-terminated; not usable as evidence)

## 3. Reconstructed nodes

| node | role | SMILES | E / Hartree (declared, from log) | evidence log (sandbox-relative) | notes |
|---|---|---|---|---|---|
| RC | reactant | `[BH4-].C=O` | - | `(none)` | All RС optimisations error-terminated (l103 / l9999). No valid minimum or energy exists; deliberately left without evidence instead of inventing one. |
| TS1 | transition_state | `[]` | - | `(none)` | TS job error-terminated (l9999, 03:15 local); no frequency log exists. |
| P | product | `CO[BH3-]` | -141.7207586 | `runs/p_opt.log` | Product minimum: 0 imaginary frequencies, optimization completed, Normal termination. |

## 4. Reconstructed edges

| edge | from -> to | via | barrier (kcal/mol) | bond_changes | derivation / notes |
|---|---|---|---|---|---|
| e1 | RC -> P | TS1 | none (no saddle log) | break [[1,2]]; form [[2,3],[1,4]] | PROCESS.md hypothesis: B(1)-H(2) breaks, H(2)-C(3) and B(1)-O(4) form. The agent's written enumeration omits the C=O order change (gold also lists break [[3,4]]); the reconstruction keeps the run's own enumeration and does NOT import the gold pair. |

## 5. Barrier arithmetic (native log energies, 627.5094740631 kcal/mol per Hartree)

- e1: none (no saddle log) (see evidence logs above; declared value equals the log-derived SCF difference rounded to 2 decimals).
- No edge carries a barrier: no frequency-verified first-order saddle exists anywhere in this run's sandbox, so none could be derived from the artifacts.

## 6. What could NOT be reconstructed

RC minimum/energy, TS geometry/frequency/barrier, IRC and endpoint checks. The scan/TS stage never produced a usable result.

## 7. Accessible-flag justification

Accessible task: all nodes are left accessible (default). No negative claim is supported by the run's artifacts.

## 8. Local validation (stock scoring pipeline on a hardlink shadow copy)

- Replay location: hardlink shadow of the original sandbox under `/home/ly/adjudication/audit-shadow/F1/` with the reconstructed graph written only into that shadow root (this directory was removed after validation; the original sandbox was never written).
- Component scores: graph = 0.33333333333333337, self-consistency = 0.0, accuracy = 0.0, final (repaired) = **0.0333** (composite).
- Node bindings: [["RC", false, 0.0, []], ["TS1", false, 0.0, []], ["P", true, 1.0, ["runs/p_opt.log"]]]
- Expected effect vs -1.0: graph=0.3333, selfc=0.0000, accuracy=0.0000 -> repaired_final=0.0333 (the product node binds; RC/TS cannot bind and cost graph score).

## 9. Confidence

**LOW** - Only the product minimum is evidenced; the reactant complex and the transition state exist only as hypotheses in PROCESS.md, and every attempt to compute them error-terminated. The graph structure is therefore a hypothesis-reconstruction, not a data-reconstruction.

## 10. Integrity statement

Original sandboxes, campaign databases (`benchmark.db`), runtime databases, the task bank and all product code were read only. No file outside `/home/ly/adjudication/` was created or modified. The reconstruction is an adjudication artefact for the `repaired` track only; it must never be presented as the agent's delivered result.
