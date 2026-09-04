# TASK C report — edge e1 frequency arbitration (R -> I1 proton transfer)

Date: 2026-09-04. Level: MACE-OMol25 (extra-large-1024, cpu, float64) via ORCA 6.1.1 ExtOpt, charge -1, mult 1, serial.
SMILES annotation carried in input: `# smiles: [OH-].CC=O.CC=O`.

## 1. Geometry provenance
- calc-82 (TS opt) converged: log `/Users/cloudrayyy/Desktop/Cloudra-mechanism-agent-master/NA1_exam/ts_e1/.cloudra/calc-82.out.log`
  shows `*** THE OPTIMIZATION HAS CONVERGED ***` (line 23138), final SP -383.5195555244 Eh,
  `ORCA TERMINATED NORMALLY`. Input was `e1_c130.inp`.
- `e1_c130.xyz` is bit-identical to the last `CARTESIAN COORDINATES (ANGSTROEM)` frame of the
  calc-82 log (verified diff of all 16 atoms). **e1_c130.xyz IS the calc-82 endpoint.**
- Key distances at the endpoint: O1-H9 = 1.3000 A, C2-H9 = 1.4015 A, O1-H8 = 0.9625 A,
  C2-C3 = 1.4236 A, C3-O4 = 1.2332 A (proton mid-transfer).

## 2. Frequency job
- Input: `/Users/cloudrayyy/Desktop/Cloudra-mechanism-agent-master/NA1_exam/ts_e1/freq82/e1_freq82nf.inp`
  (`! ExtOpt NumFreq`; coordinates copied from tool-generated e1_freq82.inp).
  NOTE: a first attempt (job 96, `! ExtOpt Freq`) terminated "normally" in 5 s having silently
  skipped the frequency run — trap #3 confirmed for standalone freq too. That log (calc-96)
  contains NO vibrational data; its parse was correctly rejected (rev_b1e8f00a...).
- Job 98 (async, cpus=1): DONE, `ORCA TERMINATED NORMALLY`, 90/90 displacements, 55 s wall.
  Log: `/Users/cloudrayyy/Desktop/Cloudra-mechanism-agent-master/NA1_exam/ts_e1/freq82/.cloudra/calc-98.out.log`
- log_parser on calc-98: normal_termination=true, E = -383.5195555243 Eh
  (bit-identical to the calc-82 opt endpoint), ZPE = 0.11852205 Eh (74.37 kcal/mol),
  G-E(el, 298.15 K) = 0.08218383 Eh.

## 3. Frequencies — full imaginary-mode list
- **Exactly ONE imaginary frequency: -1347.12 cm^-1 (mode 6).**
- All other 41 modes real; lowest real modes 35.32, 55.03, 76.94, 95.25, 105.53 cm^-1
  (intermolecular cluster modes, all real — no contamination).
- 6 null modes (0.00 cm^-1, translation/rotation) as expected.

## 4. Imaginary-mode character (NORMAL MODES block, mass-weighted)
Per-atom displacement magnitudes for mode 6:
  H9 = 0.9880 (dominant); next: H11 = 0.1023, H10 = 0.0655, C2 = 0.0473, O1 = 0.0451, H8 = 0.0360;
  all others <= 0.035.
Direction: |dot(H9 displacement, O1->H9 axis)| = 0.999; |dot(H9 disp, H9->C2 axis)| = 1.000.
=> The imaginary mode is the O1-H9...C2 proton-shuttle stretch: largest displacement on the
   transferring alpha-H (H9), moving along the hydroxide-O -> alpha-C transfer axis. Minor H10/H11
   admixture is the methyl-group relaxation accompanying deprotonation — chemically consistent.

## 5. VERDICT
**TRUE SADDLE (first-order TS) for edge e1, R -> I1 alpha-proton transfer.**
n_imag = 1 with clean O-H...C proton-transfer character on the MACE-OMol25 PES.

Caveat (unchanged, for the record): the TS electronic energy -383.519556 Eh sits 1.86 kcal/mol
BELOW the R minimum (-383.5165907222 Eh) and 17.15 kcal/mol ABOVE I1 (-383.5468773487 Eh).
The negative electronic-energy "barrier" vs R is a property of the flat MACE PES in the
reactant-complex region; it does not contradict saddle character (curvature is negative along the
PT coordinate and positive along all 41 others). Any quantitative barrier for e1 must use
ZPE/thermal corrections (R-side ZPE/G not yet computed at this level) and, for production
numbers, DFT confirmation — MACE-only.

## 6. Artifacts
- Freq input: NA1_exam/ts_e1/freq82/e1_freq82nf.inp (also e1_freq82.inp = tool-generated Freq variant, superseded)
- Freq log:   NA1_exam/ts_e1/freq82/.cloudra/calc-98.out.log (job_id 98) — EVIDENCE LOG
- Hessian:    NA1_exam/ts_e1/freq82/e1_freq82nf.hess
- Geometry:   NA1_exam/ts_e1/e1_c130.xyz (= calc-82 converged endpoint)
- Opt log:    NA1_exam/ts_e1/.cloudra/calc-82.out.log (job_id 82)
- Superseded: NA1_exam/ts_e1/freq82/.cloudra/calc-96.out.log (job 96, Freq silently skipped, no vibrational data)
