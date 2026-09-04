# HANDOFF — NA1 species I1 (enolate intermediate complex)

## Task
Characterize ONE stationary point (minimum) for I1: `C=C[O-].O.CC=O` (acetaldehyde enolate + H2O + acetaldehyde, 16 atoms incl. H; charge -1, singlet). Methods whitelist: MACE-OMol25 via ORCA ExtOpt (evidence), xTB (pre-opt only). Work ONLY in NA1_exam/species_I1/. Do NOT read NA1_run/, ideapool/, mechanism_graph.json.

## Atom order (1-based, from smiles_to_mol / xyz)
- Enolate: C1(=CH2), C2(=CH), O3(O-), H8,H9,H10
- Water: O4, H11, H12
- Acetaldehyde: C5(CH3), C6(C=O), O7, H13-16

## Completed
1. smiles_to_mol(generate_3d=True) → I1.mol (fragments clashed; not used directly).
2. conformer_search (MMFF, charge -1, filters O3-O4 2.4-3.2 / C1-C6 2.8-3.6) → confs/confs.sdf; no conf passed both filters; conf0 clash-free with O3-O4=2.744 Å, C1-C6=4.04 Å → used as start.
3. format_converter sdf→xyz → I1_start.xyz (comment line: smiles: C=C[O-].O.CC=O).
4. xTB pre-opt: scheduler job_type='xtb' UNSUPPORTED (job 40 failed). Fallback: ran xtb CLI directly:
   `/Users/cloudrayyy/miniconda3/envs/chemai/bin/xtb I1_start.xyz --opt --chrg -1 --uhf 0` → converged (exit 0).
   - xTB E = -25.501346783981 Eh; log: xtb_opt.log; optimized geom: xtbopt.xyz
   - Bound: O3-O4=2.639, O3-H12=1.645, O3-H14=1.710, C1-C6=4.571 Å (enolate O H-bonded to water; also weak contact to acetaldehyde methyl H). 3 fragments, no rearrangement.
5. MACE ORCA input: I1_mace_optfreq.inp — `! ExtOpt Opt NumFreq` + `# smiles: C=C[O-].O.CC=O` comment, %method ProgExt /Users/cloudrayyy/miniconda3/envs/chemai/bin/mace, Ext_Params "--model /Users/cloudrayyy/opt/mace-omol25/MACE-omol-0-extra-large-1024.model --device cpu --dtype float64", charge -1 mult 1, %pal nprocs 1, %maxcore 4096. (Freq→NumFreq edit was required: MACE has no analytic Hessian.)
6. Submitted: job_id=42 (orca, cpus=1, async).

## Status: COMPLETE
- MACE job 42 DONE and verified in log text: 'ORCA TERMINATED NORMALLY', opt HURRAY-converged, 0 imaginary frequencies (42 real modes for 16 atoms).
- E = -383.5468773487 Ha; G(298.15K) = -383.46058674 Ha; H = -383.41042982 Ha; ZPE corr = 0.12365567 Ha; thermal Gibbs corr = 0.0862906 Ha.
- Lowest 3 real freqs: 15.51, 55.85, 58.45 cm-1.
- Bound complex at MACE minimum: O3...O4 = 2.672 A, O3...H12 = 1.671 A (strong H-bond, H12 stays on water: O4-H12 = 1.003 A — no proton transfer), C1...C6 = 3.694 A, C2...O7 = 5.047 A. Enolate C=C 1.365 A, C2-O3 1.282 A; acetaldehyde C=O 1.213 A intact. No dissociation, no covalent rearrangement.
- Final xyz: I1_mace_optfreq.xyz; real log: species_I1/.cloudra/calc-42.out.log (log_parser succeeded).

## Next steps
- None. Report delivered to Coordinator.
