# Post-hoc reconstruction - standard/NR1 (normal task)

> **POST-HOC RECONSTRUCTION BY AUDIT, NOT AGENT-DELIVERED.** This `mechanism_graph.json` was reconstructed after the fact by the std-auditor from the run's own preserved artifacts. It was never written by the agent, was never present in the original sandbox when scoring ran, and does not change the raw benchmark row.

- Campaign / arm: `/home/ly/cloudra-p2c-20261025/standard/r1` (arm `standard`, batch `batch_8b2051b670f348ba`)
- Original sandbox (never modified): `/home/ly/cloudra-p2c-20261025/standard/r1/sandboxes/NR1/batch_8b2051b670f348ba`
- Original benchmark row: `benchmark.db.runs` final_score = -1.0 (integrity no-evidence penalty; no mechanism_graph.json in sandbox at scoring time)
- Reconstructed file: `/home/ly/adjudication/reconstructed/standard/NR1/mechanism_graph.json`
- Reconstruction date: 2026-10-29 19:31 +08:00
- Track: separate `repaired` track (scored by teammate fair-scorer from shadow copies); raw/offline score rows are untouched.

## 1. Why the graph is missing

Run was finalised at 2026-10-26T17:24:29Z (run.finished seq 474) while exploratory TS probes 521 (TS1, 1,3-H shift) and 522 (TS3, water elimination) were still running; the agent called stop() to await them. Both probes finished shortly after scoring (17:25 and 17:27) and were never inspected.

## 2. Sources used (only this run's own artifacts)

- PROCESS.md (three-step hypothesis: 1,3-H shift -> formimidic acid; N-inversion/conformer step; concerted water elimination)
- calc/g_formamide_optfreq.log (formamide minimum)
- calc/g_ts1.log (TS1 probe: exactly 1 imaginary frequency, -991.6125 cm-1, Normal termination)
- calc/g_formimidic_A_optfreq.log (formimidic-acid conformer minimum)
- calc/g_ts2.log (0 imaginary frequencies: the TS2 probe collapsed to a formimidic-acid conformer minimum, used as I2)
- calc/g_prod_complex_optfreq.log (HCN + H2O product complex minimum)

## 3. Reconstructed nodes

| node | role | SMILES | E / Hartree (declared, from log) | evidence log (sandbox-relative) | notes |
|---|---|---|---|---|---|
| RC | reactant | `NC=O` | -169.772982771 | `calc/g_formamide_optfreq.log` | Minimum, 0 imaginary frequencies. |
| TS1 | transition_state | `[]` | -169.71475543 | `calc/g_ts1.log` | First-order saddle: exactly 1 imaginary frequency (-991.6125 cm-1), Normal termination. |
| I1 | intermediate | `N=CO` | -169.745424093 | `calc/g_formimidic_A_optfreq.log` | Verified formimidic-acid minimum (0 imaginary). |
| TS2 | transition_state | `[]` | - | `(none)` | No TS2 log exists; the probe collapsed to a minimum (I2). Node kept as the hypothesis's conformational step placeholder. |
| I2 | intermediate | `N=CO` | -169.7448448 | `calc/g_ts2.log` | Second formimidic-acid conformer minimum (0 imaginary), reached by the TS2 probe. |
| TS3 | transition_state | `[]` | - | `(none)` | No saddle for water elimination was found (the TS3 probe finished after scoring and its product-side result was not obtained). Node kept as a hypothesis placeholder. |
| P | product | `C#N.O` | -169.720742486 | `calc/g_prod_complex_optfreq.log` | Product complex minimum, 0 imaginary frequencies. |

## 4. Reconstructed edges

| edge | from -> to | via | barrier (kcal/mol) | bond_changes | derivation / notes |
|---|---|---|---|---|---|
| e1 | RC -> I1 | TS1 | 36.54 kcal/mol | break [[1,4],[2,3]]; form [[1,2],[3,4]] | 1,3-H shift as described in PROCESS.md (H4 migrates from N1 to O3; C2=O3 becomes C2=N1). Computed from native logs: (-169.71475543 - (-169.772982771)) x 627.5094740631 = 36.538 kcal/mol. This is the only barrier the run's evidence supports; gold reference for this step is 46.32 kcal/mol (Delta = -9.78). |
| e2 | I1 -> I2 | TS2 | none | break []; form [] | Conformational/inversion step from the PROCESS.md hypothesis. No TS log exists; empty bond-change set per contract for a conformational step. |
| e3 | I2 -> P | TS3 | none | break [[1,5],[2,3]]; form [[1,2],[3,5]] | Concerted water elimination from the PROCESS.md hypothesis (N1-H5 -> O3, C2-O3 breaks, C2=N1 becomes C#N). No TS log exists. |

## 5. Barrier arithmetic (native log energies, 627.5094740631 kcal/mol per Hartree)

- e1: 36.54 kcal/mol (see evidence logs above; declared value equals the log-derived SCF difference rounded to 2 decimals).

## 6. What could NOT be reconstructed

TS2 and TS3 saddles, IRC and endpoint verification; only the first of the four reference elementary steps has any saddle evidence (1 of 4 gold edges), and the gold network contains one more formimidic-acid intermediate (I3) than this run ever characterized. The 36.54 barrier also differs from the 46.32 reference by ~9.8 kcal/mol.

## 7. Accessible-flag justification

Accessible task: all nodes left accessible.

## 8. Local validation (stock scoring pipeline on a hardlink shadow copy)

- Replay location: hardlink shadow of the original sandbox under `/home/ly/adjudication/audit-shadow/NR1/` with the reconstructed graph written only into that shadow root (this directory was removed after validation; the original sandbox was never written).
- Component scores: graph = 0.5925925925925926, self-consistency = 0.3499999999999999, accuracy = 1.5980508470958554e-06, final (repaired) = **0.1643** (composite).
- Derived barrier steps: [["e1", 36.538, 36.54, "calc/g_ts1.log", "calc/g_formamide_optfreq.log"]]
- Node bindings: [["RC", true, 1.0, ["calc/g_formamide_optfreq.log"]], ["TS1", true, 1.0, ["calc/g_ts1.log"]], ["I1", true, 1.0, ["calc/g_formimidic_A_optfreq.log"]], ["TS2", true, 1.0, []], ["I2", true, 1.0, ["calc/g_ts2.log"]], ["TS3", true, 1.0, []], ["P", true, 1.0, ["calc/g_prod_complex_optfreq.log"]]]
- Expected effect vs -1.0: graph=0.5926, selfc=0.3500, accuracy~0.0000 -> repaired_final=0.1643.

## 9. Confidence

**MEDIUM** - Every node and the one barrier are native Gaussian logs with exact energies; the three-step topology and e2/e3 bond changes are the run's own hypotheses, and two of three TS nodes have no evidence at all. The graph is a truthful partial reconstruction, not a complete mechanism.

## 10. Integrity statement

Original sandboxes, campaign databases (`benchmark.db`), runtime databases, the task bank and all product code were read only. No file outside `/home/ly/adjudication/` was created or modified. The reconstruction is an adjudication artefact for the `repaired` track only; it must never be presented as the agent's delivered result.
