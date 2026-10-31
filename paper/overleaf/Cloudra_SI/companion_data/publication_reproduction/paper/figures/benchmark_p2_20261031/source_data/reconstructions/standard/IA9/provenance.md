# Post-hoc reconstruction - standard/IA9 (impossible task)

> **POST-HOC RECONSTRUCTION BY AUDIT, NOT AGENT-DELIVERED.** This `mechanism_graph.json` was reconstructed after the fact by the std-auditor from the run's own preserved artifacts. It was never written by the agent, was never present in the original sandbox when scoring ran, and does not change the raw benchmark row.

- Campaign / arm: `/home/ly/cloudra-p2c-20261025/standard/r1` (arm `standard`, batch `batch_8b2051b670f348ba`)
- Original sandbox (never modified): `/home/ly/cloudra-p2c-20261025/standard/r1/sandboxes/IA9/batch_8b2051b670f348ba`
- Original benchmark row: `benchmark.db.runs` final_score = -1.0 (integrity no-evidence penalty; no mechanism_graph.json in sandbox at scoring time)
- Reconstructed file: `/home/ly/adjudication/reconstructed/standard/IA9/mechanism_graph.json`
- Reconstruction date: 2026-10-29 19:31 +08:00
- Track: separate `repaired` track (scored by teammate fair-scorer from shadow copies); raw/offline score rows are untouched.

## 1. Why the graph is missing

Run was finalised at 2026-10-28T09:21:26Z (run.finished seq 4467): the coordinator called stop() waiting for the formal ts_0001 frequency stage before IRC/endpoint verification and graph writing. The formal pipeline then reported 'outcome=verified; verified=true' for TS connectivity (job 1077, notification seq 4468 at 09:22:47) but the sandbox had already been scored, and mechanism_graph.json was never written.

## 2. Sources used (only this run's own artifacts)

- The specialist sub-agent's delivered report and RESULTS.md (saddle 46.73 kcal/mol, two independent TS optimisations, bidirectional IRC, endpoint A minimum, endpoint B unverified)
- work/rc_optfreq.log (dioxetane reactant minimum, 0 imaginary)
- ts_alt/freq_img03.log (primary saddle, exactly 1 imaginary frequency -2598.0537 cm-1)
- ts/ts_0001/jobs/declaration_0004/frequency/frequency.log (formal pipeline saddle, 1 imag -2603.1076 cm-1)
- ts_alt/irc_ts2.log + ts/ts_0001/jobs/declaration_0004/irc/irc.log (bidirectional IRC, Normal termination)
- ts_alt/optfreq_endA.log (reactant-side endpoint minimum, 0 imaginary)
- ts_alt/optfreq_endB.log (product-side endpoint optimisation ERROR-terminated; no frequency)
- work/hcho_a_optfreq.log / ts/ts_0001/verdict/components_0004/component_0000.log (one isolated HCHO minimum, 0 imaginary)

## 3. Reconstructed nodes

| node | role | SMILES | E / Hartree (declared, from log) | evidence log (sandbox-relative) | notes |
|---|---|---|---|---|---|
| RC | reactant | `C1COO1` | 0.00310190509259 | `work/rc_optfreq.log` | Dioxetane minimum, 0 imaginary frequencies. |
| TS1 | transition_state | `[]` | 0.0775707926563 | `ts_alt/freq_img03.log` | Primary saddle: exactly 1 imaginary frequency (-2598.0537 cm-1), Normal termination; independently reproduced at ts_alt/freq_img03_fresh.log (-2598.0355 cm-1). |
| P | product | `C=O.C=O` | - | `(none)` | No normally terminated minimum exists for the bound (HCHO)2 product complex: the IRC product-side endpoint optimisation ts_alt/optfreq_endB.log ERROR-terminated (no frequency) and only one isolated HCHO minimum is available. The node is deliberately left without a declared energy or evidence rather than inventing a product-complex minimum. |

## 4. Reconstructed edges

| edge | from -> to | via | barrier (kcal/mol) | bond_changes | derivation / notes |
|---|---|---|---|---|---|
| e1 | RC -> P | TS1 | 46.73 kcal/mol | break [[1,2],[3,4]]; form [[1,4],[2,3]] | Concerted (asynchronous) ring opening from the run's own analysis: C1-C2 and O3-O4 break, C1=O4 and C2=O3 form. Barrier: 627.5094740631 x (0.0775707926563 - 0.00310190509259) = 46.73 kcal/mol. The edge follows the run's own positive conclusion (TS accessible, barrier declared); see accessible-flag note. |

## 5. Barrier arithmetic (native log energies, 627.5094740631 kcal/mol per Hartree)

- e1: 46.73 kcal/mol (see evidence logs above; declared value equals the log-derived SCF difference rounded to 2 decimals).

## 6. What could NOT be reconstructed

The product-complex minimum/energy (product-side IRC endpoint unverified; formal pipeline: 'The bound complex C=O.C=O minimum remains UNVERIFIED') and the reverse-direction endpoint connectivity proof. The saddle, both IRC directions and the reactant endpoint minimum are all real log evidence.

## 7. Accessible-flag justification

IMPOSSIBLE-TASK FLAG DECISION: this reconstruction deliberately does NOT set accessible=false. The run's own artifacts and delivered conclusion claim 'one trustworthy PM7 first-order saddle' with a 46.73 kcal/mol barrier (positive claim), so the faithful reconstruction of what this run would have delivered keeps TS1/e1 accessible with a declared barrier. Gold marks this TS/edge inaccessible (O-O bond breaking enters a diradical region that single-reference PM7 cannot represent). A gold-conformant variant (TS1 and e1 accessible=false, no barrier, no product energy) would be the contract-correct delivery for this impossible task and would score near 1.0 on the negative-claim rule - but constructing it would import the gold answer, which the adjudication rules forbid. The rebuilt graph is therefore expected to be scored as a positive claim and to receive accuracy=0.

## 8. Local validation (stock scoring pipeline on a hardlink shadow copy)

- Replay location: hardlink shadow of the original sandbox under `/home/ly/adjudication/audit-shadow/IA9/` with the reconstructed graph written only into that shadow root (this directory was removed after validation; the original sandbox was never written).
- Component scores: graph = 0.33333333333333337, self-consistency = 0.75, accuracy = 0.0, final (repaired) = **0.2583** (composite).
- Derived barrier steps: [["e1", 46.73, 46.73, "ts_alt/freq_img03.log", "work/rc_optfreq.log"]]
- Node bindings: [["RC", true, 1.0, ["work/rc_optfreq.log"]], ["TS1", true, 0.0, ["ts_alt/freq_img03.log"]], ["P", false, 0.0, []]]
- Expected effect vs -1.0: graph=0.3333 (product node unbound), selfc=0.7500, accuracy=0.0000 (positive claim on a gold-inaccessible edge) -> repaired_final=0.2583.

## 9. Confidence

**MEDIUM** - Reactant minimum, saddle (two independent optimisations), both IRC directions and the reactant endpoint minimum are exact native Gaussian logs; the graph structure and barrier follow the run's own numbers. Missing: the product-complex minimum (endpoint B error-terminated). The accessible-flag choice is the run's conclusion rather than the gold expectation, which is the main interpretation risk.

## 10. Integrity statement

Original sandboxes, campaign databases (`benchmark.db`), runtime databases, the task bank and all product code were read only. No file outside `/home/ly/adjudication/` was created or modified. The reconstruction is an adjudication artefact for the `repaired` track only; it must never be presented as the agent's delivered result.
