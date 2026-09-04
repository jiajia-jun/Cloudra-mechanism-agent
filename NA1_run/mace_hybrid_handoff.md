# NA1 / xtb-geometry + MACE-energy hybrid — TS2 barrier estimate

Session: 2026-09-04, small_mol (a-4). Continuation of xtb diagnostic (NA1_run/xtb_diagnostic_report.md).

## Computed MACE single-point energies (ORCA `! ExtOpt`, MACE-omol-0-extra-large-1024, charge=-1, singlet, gas-phase)
- E(central_complex reactant, xtb geo) = -383.537453142600  Eh   [job 31, calc-31.out.log]
- E(TS2, xtb geo)                       = -383.532477279800  Eh   [job 32, calc-32.out.log]
- E(product I2, xtb geo)                = -383.544252824700  Eh   [job 33, calc-33.out.log]

## Derived (1 Eh = 627.509 kcal/mol)
- dE** (TS2 - complex)   = +0.004976 Eh = **+3.122 kcal/mol**
- dE   (product - complex) = -0.006800 Eh = **-4.267 kcal/mol** (exothermic)
- dE   (product - TS2)   = -0.011776 Eh = -7.389 kcal/mol

## Comparison
- gold dE** ≈ 5 kcal/mol → MACE +3.12 is within **1.9 kcal/mol** of gold (vs xtb's +63.4, i.e. ~13x off).
- Resolves the xtb artifact: xtb +63 was a single-coordinate constraint artifact; MACE recovers a small positive barrier close to gold.
- Caveat: geometries are xtb (xtb-PES stationary points / constrained-scan frames); MACE is only a single point, NOT a MACE stationary point/saddle. Value is an estimate, not a variational MACE barrier.

## Trust ratings
- MACE energies: HIGH (normal_termination=true, job_types=["sp"], exactly 1 FINAL SP line per log matching manual grep, charge -1 verified).
- dE** = +3.12 kcal/mol: MEDIUM-HIGH as a single-point estimate; MEDIUM as a "true" barrier (geometry not MACE-optimized).
- dE = -4.27 kcal/mol: MEDIUM (MACE PES differs strongly from xtb here; xtb gave -35.5).
- Comparison to gold: MEDIUM-HIGH (strongly supports xtb artefact, but not a closed quantitative barrier).
