# NU3 — ylide/PH3 stepwise oxaphosphetane route to C2H4 + H3P=O

**Method** B3LYP-D3(BJ)/def2-SVP, ORCA 6.1.1, gas phase, pure electronic ΔE‡.
**Source JSON** `edge_barriers/computed/NU3.json` → copied to `NU3.json`.
**Schema** NEW edges (no species_minima block) → TS/IRC paths from JSON; species-minimum logs
**inferred from `NU3/HANDOFF.md`** (marked *handoff* below).

## Edges
| Edge | ΔE‡ (kcal/mol) | n_imag | imag (cm⁻¹) | IRC | validation | solvent |
|------|---------------:|:------:|------------:|-----|------------|---------|
| NU3_E1  (RC → adduct)              | 1.70  | 1 | -279.0  | 1 dir converged + endpoint opt | verified | gas |
| NU3_E2a (adduct → oxaphosphetane)  | 55.81 | 1 | -1021.6 | 1 dir converged + endpoint opt | verified | gas |
| NU3_E2b (oxaphosphetane → products)| 23.76 | 1 | -624.8  | 1 dir converged + endpoint opt | verified | gas |

## Files
- `edges/NU3_E1/TS.log` — OptTS (job 382), 1 imag -279.0 cm⁻¹.
- `edges/NU3_E1/IRC.log` — IRC (job 387).
- `edges/NU3_E2a/TS.log` — OptTS (job 418), 1 imag -1021.6 cm⁻¹ (rate-determining step).
- `edges/NU3_E2a/IRC.log` — IRC (job 422).
- `edges/NU3_E2b/TS.log` — OptTS (job 424), 1 imag -624.8 cm⁻¹ (cycloreversion).
- `edges/NU3_E2b/IRC.log` — IRC (job 425).
- `species/RC.log` — RC minimum (job 361), E=-496.541090 Ha.
- `species/I1_adduct.log` — H2P–CH2–CH2–OH adduct (job 416), E=-496.635831 Ha.
- `species/I2_oxaphosphetane.log` — oxaphosphetane (job 362), E=-496.585627 Ha.
- `species/P_C2H4.log` / `species/P_H3P_O.log` — separated products (jobs 419 / 420).
- `notes/HANDOFF.md` — task handoff (verbatim).

## Old → new mapping
| New file | Source (job) | Note |
|----------|--------------|------|
| NU3.json | edge_barriers/computed/NU3.json | verbatim copy |
| edges/NU3_E1/TS.log | runs/NU3/NU3_E1/1/calc-382.out.log (job 382) | JSON ts_log |
| edges/NU3_E1/IRC.log | runs/NU3/NU3_E1/1/calc-387.out.log (job 387) | JSON irc_log |
| edges/NU3_E2a/TS.log | runs/NU3/NU3_E1/1/calc-418.out.log (job 418) | JSON ts_log |
| edges/NU3_E2a/IRC.log | runs/NU3/NU3_E1/1/calc-422.out.log (job 422) | JSON irc_log |
| edges/NU3_E2b/TS.log | runs/NU3/NU3_E1/1/calc-424.out.log (job 424) | JSON ts_log |
| edges/NU3_E2b/IRC.log | runs/NU3/NU3_E1/1/calc-425.out.log (job 425) | JSON irc_log |
| species/RC.log | runs/NU3/NU3_E1/1/calc-361.out.log (job 361) | *handoff* |
| species/I1_adduct.log | runs/NU3/NU3_E1/1/calc-416.out.log (job 416) | *handoff* |
| species/I2_oxaphosphetane.log | runs/NU3/NU3_E1/1/calc-362.out.log (job 362) | *handoff* |
| species/P_C2H4.log | runs/NU3/NU3_E1/1/calc-419.out.log (job 419) | *handoff* |
| species/P_H3P_O.log | runs/NU3/NU3_E1/1/calc-420.out.log (job 420) | *handoff* |
| notes/HANDOFF.md | runs/NU3/HANDOFF.md | verbatim |

## Notes / caveats
- IRC wording: per TS only **one** direction converged; the other was truncated at MaxIter=30 and connectivity is
  established by independently relaxing the truncated outer frame (strict verify permits partially converged IRC).
- Energy ladder rel. RC: 0 / -59.45 / -27.95 / -32.21 kcal; closure check exact.
- Jobs 426/427/428 (MaxIter=600 IRC reruns) are supplementary and **not** part of the delivery.
- Old task logs live directly in `NU3/NU3_E1/1/` (no `.cloudra/`) — note the path difference vs other tasks.
- No source path was missing for this task.
