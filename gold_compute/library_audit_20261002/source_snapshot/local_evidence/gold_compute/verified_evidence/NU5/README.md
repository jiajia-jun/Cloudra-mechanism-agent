# NU5 — HCOOH + HCHO + CH3NC (Mumm rearrangement)

**Method** B3LYP-D3(BJ)/def2-SVP, ORCA 6.1.1, CPCM(DCM), nproc=1.
**Source JSON** `edge_barriers/computed/NU5.json` → copied to `NU5.json`.
**Schema** NEW (species_minima + endpoint_logs) → all paths taken directly from the JSON.

## Edges
| Edge | ΔE‡ (kcal/mol) | n_imag | imag (cm⁻¹) | IRC | validation | solvent |
|------|---------------:|:------:|------------:|-----|------------|---------|
| NU5_E1 (RC → I1, PT)      | 11.9 | – | – | – | **unresolved** (constrained-scan upper bound) | CPCM(DCM) |
| NU5_E2 (I1 → I2, nitrilium)| 8.20 | 1 | -351.3 | converged | verified | CPCM(DCM) |
| NU5_E3 (I2 → I3)          | 0 | – | – | – | verified barrierless | CPCM(DCM) |
| NU5_E4 (I3 → P, Mumm)     | 31.7 | 1 | -153.44 | endpoint-opt connectivity | verified (medium) | CPCM(DCM) |

## Files
- `edges/NU5_E1/scan_01..06.log` — 1-D/2-D constrained relaxed scans (jobs 475,476,477,492,493,494). **No TS log** (upper bound only).
- `edges/NU5_E2/TS.log` — OptTS (job 467), 1 imag -351.3 cm⁻¹.
- `edges/NU5_E2/IRC.log` — IRC (job 474).
- `edges/NU5_E3/` — barrierless step; **no TS log** by construction (OptTS collapsed to I2 / an I3 conformer).
- `edges/NU5_E4/TS.log` — OptTS (job 469), 1 imag -153.44 cm⁻¹.
- `edges/NU5_E4/IRC.log` — IRC (job 480).
- `edges/NU5_E4/min_product_side.log` — IRC product-side outer frame opt (job 496) → P.
- `edges/NU5_E4/min_reactant_side.log` — IRC reactant-side outer frame opt (job 497) → I3 conformer.
- `species/RC.log`, `species/I1.log`, `species/I2.log`, `species/I3.log`, `species/P.log` — species minima (jobs 442, 451, 454, 436, 437).
- `notes/HANDOFF.md` — task handoff (verbatim).

## Old → new mapping
| New file | Source (job) | Note |
|----------|--------------|------|
| NU5.json | edge_barriers/computed/NU5.json | verbatim copy |
| edges/NU5_E1/scan_01.log | runs/NU5/E1/1/.cloudra/calc-475.out.log (job 475) | JSON scan_logs[0] |
| edges/NU5_E1/scan_02.log | runs/NU5/E1/1/.cloudra/calc-476.out.log (job 476) | JSON scan_logs[1] |
| edges/NU5_E1/scan_03.log | runs/NU5/E1/1/.cloudra/calc-477.out.log (job 477) | JSON scan_logs[2] |
| edges/NU5_E1/scan_04.log | runs/NU5/E1/1/.cloudra/calc-492.out.log (job 492) | JSON scan_logs[3] |
| edges/NU5_E1/scan_05.log | runs/NU5/E1/1/.cloudra/calc-493.out.log (job 493) | JSON scan_logs[4] |
| edges/NU5_E1/scan_06.log | runs/NU5/E1/1/.cloudra/calc-494.out.log (job 494) | JSON scan_logs[5] |
| edges/NU5_E2/TS.log | runs/NU5/E2/1/.cloudra/calc-467.out.log (job 467) | JSON ts_log |
| edges/NU5_E2/IRC.log | runs/NU5/E2/1/.cloudra/calc-474.out.log (job 474) | JSON irc_log |
| edges/NU5_E4/TS.log | runs/NU5/E4/1/.cloudra/calc-469.out.log (job 469) | JSON ts_log |
| edges/NU5_E4/IRC.log | runs/NU5/E4/1/.cloudra/calc-480.out.log (job 480) | JSON irc_log |
| edges/NU5_E4/min_product_side.log | runs/NU5/E4/1/.cloudra/calc-496.out.log (job 496) | JSON endpoint_logs.product_side |
| edges/NU5_E4/min_reactant_side.log | runs/NU5/E4/1/.cloudra/calc-497.out.log (job 497) | JSON endpoint_logs.reactant_side |
| species/RC.log | runs/NU5/E1/1/.cloudra/calc-442.out.log (job 442) | species_minima.RC |
| species/I1.log | runs/NU5/E1/1/.cloudra/calc-451.out.log (job 451) | species_minima.I1 |
| species/I2.log | runs/NU5/E2/1/.cloudra/calc-454.out.log (job 454) | species_minima.I2 |
| species/I3.log | runs/NU5/E3/1/.cloudra/calc-436.out.log (job 436) | species_minima.I3 |
| species/P.log | runs/NU5/E4/1/.cloudra/calc-437.out.log (job 437) | species_minima.P |
| notes/HANDOFF.md | runs/NU5/HANDOFF.md | verbatim |

## Notes / caveats
- **NU5_E1 unresolved**: value 11.9 kcal is a constrained-scan **upper bound**, not a verified barrier. No isolated
  proton-transfer saddle could be located; the true intrinsic barrier is likely smaller (LOW confidence).
- **NU5_E4 medium confidence**: connectivity proven by endpoint optimization, not by IRC convergence (IRC flat, MaxIter).
  The 31.7 kcal value deviates ~2.3× from the literature anchor 13.8 kcal (deviation retained, not adjusted).
- **RC is not a clean minimum** (3 low-frequency imaginary modes).
- Job 495 (E4 long IRC) is redundant/ignored per method correction.
- No source path was missing for this task.
