# Post-hoc reconstruction - standard/HF1 (hard task)

> **POST-HOC RECONSTRUCTION BY AUDIT, NOT AGENT-DELIVERED.** This `mechanism_graph.json` was reconstructed after the fact by the std-auditor from the run's own preserved artifacts. It was never written by the agent, was never present in the original sandbox when scoring ran, and does not change the raw benchmark row.

- Campaign / arm: `/home/ly/cloudra-p2c-20261025/standard/r1` (arm `standard`, batch `batch_8b2051b670f348ba`)
- Original sandbox (never modified): `/home/ly/cloudra-p2c-20261025/standard/r1/sandboxes/HF1/batch_8b2051b670f348ba`
- Original benchmark row: `benchmark.db.runs` final_score = -1.0 (integrity no-evidence penalty; no mechanism_graph.json in sandbox at scoring time)
- Reconstructed file: `/home/ly/adjudication/reconstructed/standard/HF1/mechanism_graph.json`
- Reconstruction date: 2026-10-29 19:31 +08:00
- Track: separate `repaired` track (scored by teammate fair-scorer from shadow copies); raw/offline score rows are untouched.

## 1. Why the graph is missing

Run was finalised at 2026-10-28T06:07:45Z (run.finished seq 6081): the agent called stop() to wait for two exploratory syn-TS H-bond probes (jobs 962/963). The probes' terminal notifications arrived at 07:10 and 07:45, after the sandbox had been scored. mechanism_graph.json was never written, although both diastereofacial channels were already fully characterized.

## 2. Sources used (only this run's own artifacts)

- The run's delivered report and follow-up messages (barrier table, per-channel IRC/endpoint verification, CIP assignments, directed-syn-saddle negative search)
- PROCESS.md (barriers table and the same evidence paths)
- rc/rc_optfreq.log (common reference: lowest H-bonded syn precursor complex)
- ts/ts_0001/jobs/declaration_0005/frequency/frequency.log (syn TS, 1 imag -435.8562 cm-1)
- ts/ts_0002/jobs/declaration_0003/frequency/frequency.log (anti TS, 1 imag -437.2726 cm-1)
- ts/ts_0001/jobs/declaration_0007/irc/irc.log (syn IRC, Normal termination)
- ts/ts_0002/jobs/declaration_0004/irc/irc.log (anti IRC, Normal termination)
- ts/ts_0001/jobs/declaration_0008/{reactant_frequency,product_frequency} and ts/ts_0002/jobs/declaration_0004/{reactant_frequency,product_frequency} (four reoptimized 0-imag endpoint minima)

## 3. Reconstructed nodes

| node | role | SMILES | E / Hartree (declared, from log) | evidence log (sandbox-relative) | notes |
|---|---|---|---|---|---|
| RC | reactant | `OC1C=CCCC1.O=COO` | -574.387607001 | `rc/rc_optfreq.log` | Lowest verified reactant-complex minimum (H-bonded OH...O=C); used as the common barrier reference, as the run's report requires. |
| C_syn | intermediate | `OC1C=CCCC1.O=COO` | -574.379378259 | `ts/ts_0001/jobs/declaration_0008/reactant_frequency/reactant_frequency.log` | Syn-channel IRC reactant-side endpoint, reoptimized + frequency verified as a minimum (0 imaginary). Same species as RC, different conformer (5.16 kcal/mol above the reference); kept as its own conformer node so the actual IRC connection is preserved, per the task contract. |
| C_anti | intermediate | `OC1C=CCCC1.O=COO` | -574.374940338 | `ts/ts_0002/jobs/declaration_0004/reactant_frequency/reactant_frequency.log` | Anti-channel IRC reactant-side endpoint, reoptimized + frequency verified as a minimum (0 imaginary). |
| TS_syn | transition_state | `[]` | -574.35273718 | `ts/ts_0001/jobs/declaration_0005/frequency/frequency.log` | Syn (undirected) TS: exactly 1 imaginary frequency (-435.8562 cm-1), Normal termination. |
| P_syn | product | `O[C@@H]1CCC[C@@H]2O[C@H]12.O=CO` | -574.469344692 | `ts/ts_0001/jobs/declaration_0008/product_frequency/product_frequency.log` | Syn product-side IRC endpoint, reoptimized + frequency verified as a minimum (0 imaginary); cis epoxide, CIP (1R,2R,3S). The independent minimum qm/prod_syn_optfreq.log (-574.472215277, 0 imag) is listed as a fallback evidence path. |
| TS_anti | transition_state | `[]` | -574.353416361 | `ts/ts_0002/jobs/declaration_0003/frequency/frequency.log` | Anti TS: exactly 1 imaginary frequency (-437.2726 cm-1), Normal termination. |
| P_anti | product | `O[C@@H]1CCC[C@H]2O[C@@H]12.O=CO` | -574.469276858 | `ts/ts_0002/jobs/declaration_0004/product_frequency/product_frequency.log` | Anti product-side IRC endpoint, reoptimized + frequency verified as a minimum (0 imaginary); trans epoxide, CIP (1R,2S,3R). |

## 4. Reconstructed edges

| edge | from -> to | via | barrier (kcal/mol) | bond_changes | derivation / notes |
|---|---|---|---|---|---|
| conf_syn | RC -> C_syn | - | none | break []; form [] | Conformational connection between the lowest reactant-complex minimum and the IRC-reached syn precursor (empty bond-change set per contract for a conformational step; no TS node). |
| conf_anti | RC -> C_anti | - | none | break []; form [] | Conformational connection between the lowest reactant-complex minimum and the IRC-reached anti precursor. |
| e1 | C_syn -> P_syn | TS_syn | 21.88 kcal/mol | break [[3,4],[10,11],[11,12]]; form [[3,11],[4,11],[10,12]] | Syn diastereofacial channel. Barrier from native logs vs the common lowest reference: 627.5094740631 x (-574.35273718 - (-574.387607001)) = 21.881 kcal/mol. Channel label 'syn_cis'; favored=false, following the run's own delivered conclusion. |
| e2 | C_anti -> P_anti | TS_anti | 21.46 kcal/mol | break [[3,4],[10,11],[11,12]]; form [[3,11],[4,11],[10,12]] | Anti diastereofacial channel. Barrier: 627.5094740631 x (-574.353416361 - (-574.387607001)) = 21.455 kcal/mol. Channel label 'anti_trans'; favored=true, following the run's own delivered conclusion ('the two barriers are essentially degenerate: 0.43 kcal/mol ... nominally in favor of the ANTI (trans) channel ... No significant Henbest syn preference is reproduced'). |

## 5. Barrier arithmetic (native log energies, 627.5094740631 kcal/mol per Hartree)

- e1: 21.88 kcal/mol (see evidence logs above; declared value equals the log-derived SCF difference rounded to 2 decimals).
- e2: 21.46 kcal/mol (see evidence logs above; declared value equals the log-derived SCF difference rounded to 2 decimals).

## 6. What could NOT be reconstructed

Nothing material is missing from the reaction evidence: both TSs, both IRCs and all four endpoint minima exist. What is NOT reproduced is the gold-expected selectivity: the reconstruction keeps the run's own conclusion (anti/trans nominally favored, anti - syn = -0.43 kcal/mol) rather than the reference's directed_face (syn) preference. The run's extra negative search for an H-bonded directed syn saddle and the rotated-peracid anti control (TS -574.352908967, 1 imag -439.6142, 21.77 kcal/mol) are documented but not included as graph edges; the control is the same saddle region as the anti TS and the directed-syn search found no saddle.

## 7. Accessible-flag justification

Accessible hard task: all nodes/edges left accessible. The only qualitative claim (favored=true on the anti edge) is taken from the run's own delivered report and is expected to score 0 against the gold favored channel 'directed_face'.

## 8. Local validation (stock scoring pipeline on a hardlink shadow copy)

- Replay location: hardlink shadow of the original sandbox under `/home/ly/adjudication/audit-shadow/HF1/` with the reconstructed graph written only into that shadow root (this directory was removed after validation; the original sandbox was never written).
- Component scores: graph = 0.799505475368673, self-consistency = 0.875, accuracy = 0.0, final (repaired) = **0.3425** (composite).
- Derived barrier steps: [["e1", 21.881, 21.88, "ts/ts_0001/jobs/declaration_0005/frequency/frequency.log", "rc/rc_optfreq.log"], ["e2", 21.455, 21.45, "ts/ts_0002/jobs/declaration_0003/frequency/frequency.log", "rc/rc_optfreq.log"]]
- Node bindings: [["RC", true, 1.0, ["rc/rc_optfreq.log"]], ["C_syn", true, 1.0, ["ts/ts_0001/jobs/declaration_0008/reactant_frequency/reactant_frequency.log"]], ["C_anti", true, 1.0, ["ts/ts_0002/jobs/declaration_0004/reactant_frequency/reactant_frequency.log"]], ["TS_syn", true, 1.0, ["ts/ts_0001/jobs/declaration_0005/frequency/frequency.log"]], ["P_syn", true, 1.0, ["ts/ts_0001/jobs/declaration_0008/product_frequency/product_frequency.log"]], ["TS_anti", true, 1.0, ["ts/ts_0002/jobs/declaration_0003/frequency/frequency.log"]], ["P_anti", true, 1.0, ["ts/ts_0002/jobs/declaration_0004/product_frequency/product_frequency.log"]]]
- Expected effect vs -1.0: graph=0.7995, selfc=0.8750, accuracy=0.0000 -> repaired_final=0.3425 (local stock-pipeline replay in a hardlink shadow copy; fair-scorer's independent repaired-track value is authoritative).

## 9. Confidence

**HIGH** - All seven nodes and both barriers are backed by exact native Gaussian frequency/IRC/optimization logs, and the graph follows the run's own delivered barrier table and stereo assignments. The only judgement call is the reconstruction choice to add the two IRC-precursor conformer nodes (required by the task contract to preserve the actual IRC connection; their energies and frequencies are direct log values).

## 10. Integrity statement

Original sandboxes, campaign databases (`benchmark.db`), runtime databases, the task bank and all product code were read only. No file outside `/home/ly/adjudication/` was created or modified. The reconstruction is an adjudication artefact for the `repaired` track only; it must never be presented as the agent's delivered result.
