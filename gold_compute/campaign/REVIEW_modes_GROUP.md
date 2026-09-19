# REVIEW — Transition-state imaginary-mode identity (independent audit)
Group: **HA6, HG2** (small_mol / a-4, independent reviewer; item0 = HA6)
Reviewer remit: confirm that each edge's UNIQUE imaginary frequency is the declared reaction coordinate
(forming/breaking **heavy-atom** motion), NOT a soft spectator mode (lattice/solvent/ion libration) or an
isolated-proton mode. Read-only audit of existing ORCA logs; no QM was run and no computed/*.json was modified.

## Method
1. Edge list + declared bond changes taken verbatim from `gold_compute/edge_barriers/computed/HA6.json` and `HG2.json`.
2. Imaginary frequency read from the **final** `VIBRATIONAL FREQUENCIES` block only (the block immediately before
   `****ORCA TERMINATED NORMALLY****`). ORCA also prints an initial-Hessian block (and intermediate Hessians during
   OptTS) with several spurious imaginary modes; those were explicitly excluded. See per-edge note.
3. Atomic displacements for the first imaginary mode (mode index 6) parsed from the **final** `NORMAL MODES` block of the
   same log. ORCA prints **mass-weighted** Cartesian displacements (M(i,i)=1/sqrt(m_i)), which inflate H; therefore both
   the raw mass-weighted ranking and a mass-corrected ("physical") ranking (multiply by sqrt(m)) are reported.
4. Atom indices follow the TS `.xyz` (and the `.json` heavy-atom labels); declared bond distances were re-measured
   from the TS xyz to confirm the index convention before judging the mode.

## Per-edge verdicts

| TASK/EDGE | imag (cm-1) [final block] | dominant displacement atoms | on declared reaction center? | confidence | note |
|---|---|---|---|---|---|
| HA6/HA6_E1 | **-520.96** (n_imag=1) | mass-wtd: H10 .468, H13 .467, H11 .378, H12 .378, **C2 .228, C5 .228** / mass-corrected: **C2 .790, C5 .790**, H10/H13 .47, C1/C6 .41, C3/C4 .36 | **YES** | high | Declared = conrotatory ring opening, C2–C5 breaking (r(C2–C5)=2.164 Å at TS, re-measured). C2 and C5 are the two largest physical displacements; methyl C1/C6 rotate in phase. No water/ion in system. |
| HA6/HA6_EM1 | **-631.01** (n_imag=1) | mass-wtd: H10 .530, H13 .530, H12 .356, H11 .356, **C2 .237, C5 .237** / mass-corrected: **C2 .823, C5 .822**, H10/H13 .53, C3/C4 .34 | **YES** | high | Inward-rotation conrotatory channel; declared C2–C5 breaking (r=2.235 Å at TS). Same reaction-coordinate character as HA6_E1 (mode is ring-opening, not methyl libration: C2/C5 move more than the methyl H's once mass weighting is removed). |
| HG2/HG2_E1 | **-355.71** (n_imag=1) | mass-wtd: **C4 .492, C2 .361, O5 .361, C7 .347**, H15 .386(on C4) / (all heavy) | **YES** | high | Declared concerted [3,3]: C2–C7 forming (2.486 Å), C4–O5 breaking (2.067 Å), both re-measured. Top heavy-atom displacements are exactly {C4, C2, O5, C7} = the four reaction-center atoms. |
| HG2/HG2_EM1 | **-402.62** (n_imag=1) | mass-wtd: **C4 .499, C2 .391, C7 .360, O5 .358**, H15 .361 / mass-corrected: **C4 1.73, O5 1.43, C2 1.35, C7 1.25** | **YES** | high | Declared concerted [3,3]: C2–C7 forming (2.392 Å), C4–O5 breaking (1.995 Å). Same four heavy atoms dominate. |

## 重点复核 (previously questioned edges) — within this group
- **HG2_E1 (-355.71)** and **HG2_E1/EM1 (-402.62)**: both re-checked as above — the imaginary mode is the concerted
  [3,3] C2–C7 / C4–O5 heavy-atom rearrangement, NOT a soft spectator mode. **Both pass.**
- HL1_e2, NA5_E2/E3/E4 are **outside this reviewer's assigned pair (HA6, HG2)** and were not audited here; they belong to
  the reviewers covering HL1 / NA5.

## 软旁观模 sweep within this group
No soft-spectator-mode masquerade found in HA6 or HG2. Both systems are neutral, gas-phase, solvent-free C/H/O
molecules — there is no counter-ion, water, or lattice to contribute a libration. In every edge the imaginary mode's
dominant (mass-corrected) displacement lies on the heavy atoms of the declared bond change, and the lowest real modes
after it (e.g. 62.5 / 72.3 cm-1 skeletal) are ordinary low-frequency framework modes, not the saddle.

## Initial-Hessian vs final-block contamination check (explicitly excluded)
- HA6_E1: earlier block (line 1598) imag -294.36; final block (line 10492) **only** -520.96. Used final.
- HA6_EM1: earlier block (line 1601) imag -666.20 / -334.11 / -318.62; final block (line 17035) **only** -631.01. Used final.
- HG2_E1: earlier block (line 1786) imag -616.32 / -560.40 / -202.70 / -158.87 / -136.10; final block (line 25286) **only** -355.71. Used final.
- HG2_EM1: earlier block (line 1766) imag -722.87 / -601.68 / -367.47 / -179.14 / -124.87; final block (line 42228) **only** -402.62. Used final.
The multi-imaginary entries are the ORCA initial/working Hessians during OptTS, not saddle-point results.

## Connectivity / IRC (context for the mode assignment)
- HA6_E1: IRC calc-462 bidirectional; reactant-side outer frame -> reactant min (calc-508, 0 imag), product-side -> (E,E)-2,4-hexadiene (calc-490, 0 imag). PASS.
- HA6_EM1: IRC calc-489 bidirectional; reactant-side -> reactant min methyl rotamer (calc-526, 0 imag), product-side -> (Z,Z)-2,4-hexadiene (calc-527, 0 imag). PASS.
- HG2_E1: IRC calc-584 aborted in LEANSCF after the forward direction hit MaxIter, but **both** outer frames were produced and independently re-optimized (calc-587 reactant-side 0 imag; calc-588 syn-product-side 0 imag). Connectivity established; note the truncation as a minor caveat but it does not affect the mode-identity verdict.
- HG2_EM1: IRC calc-532 converged/outer-frame endpoints re-optimized (calc-547 reactant-side, calc-548 anti-product-side, both 0 imag). PASS.

## Overall
**All 4 edges in this group (HA6_E1, HA6_EM1, HG2_E1, HG2_EM1) PASS the mode-identity check.** Each has exactly one
imaginary frequency in the final block, and that mode's dominant displacement is the declared forming/breaking
heavy-atom coordinate. No soft-spectator or isolated-proton mode was found. Confidence: high (mode vectors parsed
directly from the final ORCA blocks; declared bond lengths re-measured on the TS xyz).

### Artifact paths (read-only)
- HA6.json: /Users/cloudrayyy/Desktop/Cloudra-mechanism-agent-master/gold_compute/edge_barriers/computed/HA6.json
- HG2.json: /Users/cloudrayyy/Desktop/Cloudra-mechanism-agent-master/gold_compute/edge_barriers/computed/HG2.json
- HA6_E1 TS freq log: .../campaign/runs/HA6/HA6_E1/.cloudra/calc-452.out.log (final block line 10492)
- HA6_EM1 TS freq log: .../campaign/runs/HA6/HA6_EM1/.cloudra/calc-463.out.log (final block line 17035)
- HG2_E1 TS freq log: .../campaign/runs/HG2/HG2_E1/.cloudra/calc-582.out.log (final block line 25286)
- HG2_EM1 TS freq log: .../campaign/runs/HG2/HG2_E1/.cloudra/calc-520.out.log (final block line 42228)
- TS geoms: .../runs/HA6/HA6_E1/ts_optfreq.xyz, .../runs/HA6/HA6_EM1/ts_optfreq.xyz, .../runs/HG2/HG2_E1/chair_tsF.xyz, .../runs/HG2/HG2_E1/chair_tsB.xyz
