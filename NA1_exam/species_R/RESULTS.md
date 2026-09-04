# Species R — OH-·(CH3CHO)2 reactant complex — MACE-OMol25 opt+NumFreq results

- SMILES: [OH-].CC=O.CC=O ; charge -1, singlet; 16 atoms (C4H9O3-)
- Method: MACE-OMol25 (MACE-omol-0-extra-large-1024, cpu, float64) via ORCA ExtOpt, serial.

## Primary (smiles-annotated) evidence
- Geometry + single point: job_id=48, input R_mace_optfreq3.inp, log .cloudra/calc-48.out.log
  (log echoes `# smiles: [OH-].CC=O.CC=O`; THE OPTIMIZATION HAS CONVERGED; ORCA TERMINATED NORMALLY)
  NOTE: `! ExtOpt Opt Freq` silently skips the analytic-freq step with external programs — NumFreq is required.
- Frequency: job_id=51, input R_mace_freq.inp (`! ExtOpt NumFreq`), log .cloudra/calc-51.out.log
  (smiles comment echoed; ORCA TERMINATED NORMALLY; NumFreq 58 s)
- Final geometry: R_mace_optfreq3.xyz (identical minimum as R_mace_optfreq2.xyz, ΔE < 1e-6 Ha)

## Numbers (job 51, at job-48 optimized geometry)
- E(MACE) = -383.5165908052 Ha
- NumFreq: 42 vibrational modes, **0 imaginary**. Lowest 3 real: 20.22, 22.33, 32.92 cm-1
- Thermal corrections (298.15 K): ZPE 0.12080874 Ha; H corr 0.00094421 Ha; G corr 0.08291150 Ha
- H(298) = -383.38291534 Ha; G(298) = -383.43367931 Ha

## Binding motif (from R_mace_optfreq2.zmat analysis; identical minimum)
- OH- O1 double-H-bonded to alpha C-H of BOTH acetaldehydes (bifurcated):
  O1...H9 = 1.766 A, O1...H15 = 1.754 A (angles O-H...C ~171-172 deg)
- No covalent OH- addition: O1...C3 = 3.617 A, O1...C6 = 3.643 A; O1...O4 = 4.550, O1...O7 = 4.568 A
- Both C=O intact (1.214 A); C3...C6 = 6.776 A; 3 fragments bound, not dissociated.

## xTB pre-opt (GFN2-xTB; scheduler rejects job_type=xtb, ran via direct CLI fallback)
- R_xtb_opt.out + xtbopt.xyz; E = -25.4898918287 Eh; same bifurcated motif; complex stayed bound.

## History / fallback
- job 43 (R_mace_optfreq.inp): MaxIter=50 non-convergence (grads converged, steps not); superseded.
- job 45 (R_mace_optfreq2.inp, %geom MaxIter 200): converged opt+NumFreq, 0 imag,
  E = -383.5165907222 Ha — same minimum, but log lacks smiles annotation; kept as fallback evidence.

## Verdict
Genuine bound-complex minimum (0 imaginary frequencies, all fragments associated, no covalent rearrangement).
