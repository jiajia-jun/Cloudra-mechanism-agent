# NU6 — ketene + methanimine → 2-azetidinone

**Method** B3LYP-D3(BJ)/def2-SVP, ORCA, CPCM(DCM), q=0 mult=1.
**Source JSON** `edge_barriers/computed/NU6.json` → copied to `NU6.json`.
**Schema** OLD. TS/IRC paths from JSON; species & endpoint logs **inferred from `NU6/HANDOFF.md`** (marked *handoff*).

## Edges
| Edge | ΔE‡ (kcal/mol) | n_imag | imag (cm⁻¹) | IRC | validation | solvent |
|------|---------------:|:------:|------------:|-----|------------|---------|
| NU6_E1 (RC → I1, N-attack) | 2.66  | 1 | -159.63 | ok | verified | CPCM(DCM) |
| NU6_E2 (I1 → P, ring closure)| 15.72 | 1 | -526.2  | ok | verified | CPCM(DCM) |

## Files
- `edges/NU6_E1/TS.log` — OptTS (job 355), E=-246.9243447 Ha, 1 imag -159.63 cm⁻¹.
- `edges/NU6_E1/IRC.log` — IRC (job 366).
- `edges/NU6_E2/TS.log` — OptTS (job 367), E=-246.9049609 Ha, 1 imag -526.2 cm⁻¹ (rate-determining step).
- `edges/NU6_E2/IRC.log` — IRC (job 383).
- `edges/NU6_E2/min_product_side.log` — E2 IRC product-side endpoint opt (job 414) → P.
- `edges/NU6_E2/min_reactant_side.log` — E2 IRC reactant-side endpoint opt (job 415) → I1.
- `species/RC.log` — reactant complex (job 334), E=-246.9285768 Ha.
- `species/I1.log` — intermediate I1 (job 335), E=-246.9300050 Ha.
- `species/P.log` — product 2-azetidinone (job 336), E=-246.9890584 Ha.
- `notes/HANDOFF.md` — task handoff (verbatim).

## Old → new mapping
| New file | Source (job) | Note |
|----------|--------------|------|
| NU6.json | edge_barriers/computed/NU6.json | verbatim copy |
| edges/NU6_E1/TS.log | runs/NU6/E1_ts/2/.cloudra/calc-355.out.log (job 355) | JSON ts_log |
| edges/NU6_E1/IRC.log | runs/NU6/E1_ts/2/.cloudra/calc-366.out.log (job 366) | JSON irc_log |
| edges/NU6_E2/TS.log | runs/NU6/E2_ts/2/.cloudra/calc-367.out.log (job 367) | JSON ts_log |
| edges/NU6_E2/IRC.log | runs/NU6/E2_ts/2/.cloudra/calc-383.out.log (job 383) | JSON irc_log |
| edges/NU6_E2/min_product_side.log | runs/NU6/E2_ts/2/epopt_a/.cloudra/calc-414.out.log (job 414) | *handoff* |
| edges/NU6_E2/min_reactant_side.log | runs/NU6/E2_ts/2/epopt_b/.cloudra/calc-415.out.log (job 415) | *handoff* |
| species/RC.log | runs/NU6/E1_rc/1/.cloudra/calc-334.out.log (job 334) | *handoff* |
| species/I1.log | runs/NU6/E1_i1/1/.cloudra/calc-335.out.log (job 335) | *handoff* |
| species/P.log | runs/NU6/E2_p/1/.cloudra/calc-336.out.log (job 336) | *handoff* |
| notes/HANDOFF.md | runs/NU6/HANDOFF.md | verbatim |

## Notes / caveats
- RC has a floppy imaginary mode (-24.32 cm⁻¹); it drifted to C2–N7 = 4.035 Å but was retained as the step-start minimum.
- Monomers (for reference): ketene -152.4138766, methanimine -94.5081295 (sum -246.9220061).
- First attempts (jobs 330/331) failed on a TIGHTSCF-inside-%scf input bug; superseded by 334/335/336.
- No source path was missing for this task.
