# HANDOFF — NA1 species R (reactant complex [OH-].CC=O.CC=O)

STATUS: COMPLETE. Genuine bound-complex minimum confirmed at MACE-OMol25 level.

## Final deliverables (all absolute)
- Optimized geometry: /Users/cloudrayyy/Desktop/Cloudra-mechanism-agent-master/NA1_exam/species_R/R_mace_optfreq3.xyz
- ORCA input (opt, smiles-annotated): .../NA1_exam/species_R/R_mace_optfreq3.inp  — job_id 48
- ORCA log (opt): .../NA1_exam/species_R/.cloudra/calc-48.out.log
- ORCA input (NumFreq, smiles-annotated): .../NA1_exam/species_R/R_mace_freq.inp  — job_id 51
- ORCA log (freq): .../NA1_exam/species_R/.cloudra/calc-51.out.log
- xTB pre-opt: .../NA1_exam/species_R/R_xtb_opt.out, xtbopt.xyz (E = -25.4898918287 Eh)
- Full numbers: .../NA1_exam/species_R/RESULTS.md

## Key numbers
E = -383.5165908052 Ha; 0 imaginary frequencies (lowest 20.22, 22.33, 32.92 cm-1);
G(298) = -383.43367931 Ha; H(298) = -383.38291534 Ha.
Motif: bifurcated OH-...H-C(alpha) H-bonds to both acetaldehydes (O1...H 1.754/1.766 A);
no covalent addition (O1...C= 3.617/3.643 A); C=O intact.

## Lessons for other species in this exam
1. Scheduler rejects job_type=xtb → run xTB via direct CLI (bash) and keep stdout log + xtbopt.xyz.
2. ORCA ExtOpt: use `! ExtOpt Opt NumFreq` — the `Freq` keyword is silently SKIPPED with external
   programs (job 48 lost its freq step this way; job 51 redid it with NumFreq).
3. qm_input_writer drops the title for ORCA → add `# smiles: <SMILES>` comment line manually
   at the top of the .inp so the log is bindable evidence.
4. Default %geom MaxIter 50 may not converge even when gradients are tiny → MaxIter 200.
5. Real captured log is .cloudra/calc-<job_id>.out.log under the JOB directory, and it can lag
   behind the 'done' notification — re-check before parsing.
6. Scheduler mislabels: job 45 was marked failed (non-converged opt from job 43's state) but the
   log shows convergence; always verify markers in the log text yourself.
