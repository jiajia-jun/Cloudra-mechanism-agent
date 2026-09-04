# Species I2 — HANDOFF (COMPLETE)

## Goal
Evidence-grade characterization of I2 (3-hydroxybutanal alkoxide + 1 explicit H2O) for NA1 self-aldol mechanism. dag_guided sub-agent; report tool_call_ids/paths to Coordinator.

## System
`CC([O-])CC=O.O` = CH3–CH(O⁻)–CH2–CHO + H2O; C4H9O3, 16 atoms, charge −1, singlet.

## Status: DONE
- xTB (GFN2) pre-opt converged (82 iterations): E = −25.520944528020 Eh. Log: `NA1_exam/species_I2/I2_xtb.out`. (Scheduler mislabeled job 44 "failed / Unsupported job_type: xtb" — the actual xTB stdout shows normal convergence.)
- MACE-OMol25 (ORCA ExtOpt) opt+freq = **job 46**, converged & terminated normally.
  - Input: `NA1_exam/species_I2/I2_mace.inp`; real log: `NA1_exam/species_I2/.cloudra/calc-46.out.log`
  - Final xyz: `NA1_exam/species_I2/I2_mace.xyz`; Z-matrix: `I2_mace.zmat`
  - E(MACE) = −383.5533544289 Ha; G = −383.46153003 Ha; H = −383.41578232 Ha; ZPE = 0.12669936 Ha
  - n_imag = 0; lowest 3 real freqs: 19.28, 64.36, 84.5 cm⁻¹
- Structure verdict: BOUND complex. Alkoxide O3···H15(water) = 1.530 Å (strong H-bond), O3···O7 = 2.563 Å, water O7–H = 1.035/0.960 Å, alkoxide C2–O3 = 1.355 Å, carbonyl C5=O6 = 1.215 Å (intact — no OH⁻ addition, no dissociation). C2 stereocenter = S.

## Evidence tool calls (for Supervisor review)
- log_parser on calc-46.out.log (energy/frequencies/thermochemistry, normal_termination=true, opt_converged=true)
- internal_coordinates on I2_mace.xyz (bond perception, H-bond distances)

## Blockers
None.
