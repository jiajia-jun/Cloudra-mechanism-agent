# Post-hoc reconstruction - standard/M17 (easy task)

> **POST-HOC RECONSTRUCTION BY AUDIT, NOT AGENT-DELIVERED.** This `mechanism_graph.json` was reconstructed after the fact by the std-auditor from the run's own preserved artifacts. It was never written by the agent, was never present in the original sandbox when scoring ran, and does not change the raw benchmark row.

- Campaign / arm: `/home/ly/cloudra-p2c-20261025/standard/r1` (arm `standard`, batch `batch_8b2051b670f348ba`)
- Original sandbox (never modified): `/home/ly/cloudra-p2c-20261025/standard/r1/sandboxes/M17/batch_8b2051b670f348ba`
- Original benchmark row: `benchmark.db.runs` final_score = -1.0 (integrity no-evidence penalty; no mechanism_graph.json in sandbox at scoring time)
- Reconstructed file: `/home/ly/adjudication/reconstructed/standard/M17/mechanism_graph.json`
- Reconstruction date: 2026-10-29 19:31 +08:00
- Track: separate `repaired` track (scored by teammate fair-scorer from shadow copies); raw/offline score rows are untouched.

## 1. Why the graph is missing

Run was finalised at 2026-10-26T03:49:09Z (run.finished seq 545) while the C1-C3 relaxed scan (job 274) was still running. The agent ended its turn with plain text to wait for the notification; the scan then error-terminated (l9999) at 03:49:20, after the sandbox had been scored.

## 2. Sources used (only this run's own artifacts)

- PROCESS.md (single-step 1,2-methyl migration hypothesis and its bond-change enumeration)
- calc/rc_optfreq.log (reactant minimum)
- calc/p_optfreq.log (product minimum)
- calc/scan_c1c3.log (error-terminated scan; not usable)

## 3. Reconstructed nodes

| node | role | SMILES | E / Hartree (declared, from log) | evidence log (sandbox-relative) | notes |
|---|---|---|---|---|---|
| RC | reactant | `C[N+]#[C-]` | -132.624289833 | `calc/rc_optfreq.log` | Minimum, 0 imaginary frequencies, Normal termination. |
| TS1 | transition_state | `[]` | - | `(none)` | The relaxed scan that was meant to provide the TS guess error-terminated; no saddle log exists. |
| P | product | `CC#N` | -132.659619573 | `calc/p_optfreq.log` | Minimum, 0 imaginary frequencies, Normal termination (reaction DeltaE = -22.2 kcal/mol). |

## 4. Reconstructed edges

| edge | from -> to | via | barrier (kcal/mol) | bond_changes | derivation / notes |
|---|---|---|---|---|---|
| e1 | RC -> P | TS1 | none (no saddle log) | break [[2,3]]; form [[1,3]] | PROCESS.md hypothesis: 'N2-C3 triple bond is lost (break [2,3]), C1-C3 is formed (form [1,3])'. Gold lists break [[1,2]] instead; the run's own written mapping is retained and the discrepancy is documented rather than silently corrected from gold. |

## 5. Barrier arithmetic (native log energies, 627.5094740631 kcal/mol per Hartree)

- e1: none (no saddle log) (see evidence logs above; declared value equals the log-derived SCF difference rounded to 2 decimals).
- No edge carries a barrier: no frequency-verified first-order saddle exists anywhere in this run's sandbox, so none could be derived from the artifacts.

## 6. What could NOT be reconstructed

TS geometry/frequency and barrier; the scan never terminated normally.

## 7. Accessible-flag justification

Accessible task: all nodes left accessible.

## 8. Local validation (stock scoring pipeline on a hardlink shadow copy)

- Replay location: hardlink shadow of the original sandbox under `/home/ly/adjudication/audit-shadow/M17/` with the reconstructed graph written only into that shadow root (this directory was removed after validation; the original sandbox was never written).
- Component scores: graph = 0.7777777777777778, self-consistency = 0.0, accuracy = 0.0, final (repaired) = **0.0778** (composite).
- Node bindings: [["RC", true, 1.0, ["calc/rc_optfreq.log"]], ["TS1", true, 1.0, []], ["P", true, 1.0, ["calc/p_optfreq.log"]]]
- Expected effect vs -1.0: graph=0.7778, selfc=0.0000, accuracy=0.0000 -> repaired_final=0.0778.

## 9. Confidence

**MEDIUM** - Both minima are verified native Gaussian logs; the mechanistic edge and its bond changes are quoted from the run's own PROCESS.md. The missing TS is the only unsupported part.

## 10. Integrity statement

Original sandboxes, campaign databases (`benchmark.db`), runtime databases, the task bank and all product code were read only. No file outside `/home/ly/adjudication/` was created or modified. The reconstruction is an adjudication artefact for the `repaired` track only; it must never be presented as the agent's delivered result.
