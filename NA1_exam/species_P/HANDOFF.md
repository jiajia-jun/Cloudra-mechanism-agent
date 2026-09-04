# Species P — product complex [OH-]·CH3CH(OH)CH2CHO — FINAL RESULTS

## Status: COMPLETE — genuine bound complex minimum (MACE-OMol25)

## Results (charge -1, singlet, 16 atoms)
- MACE-OMol25 total energy (opt, job 49): **-383.512698220700 Eh**
- MACE-OMol25 energy (freq job 50, same geometry): -383.512698220800 Eh
- Imaginary frequencies (NumFreq): **0** (all 42 modes real)
- Lowest 3 real frequencies: 27.53, 31.80, 40.67 cm-1
- ZPE correction: 0.12656569 Eh
- Thermal Gibbs correction (298.15 K): 0.09048307 Eh; Total Gibbs: -383.42221515 Eh
- Thermal enthalpy correction: 0.00094421 Eh; Total enthalpy: -383.37428874 Eh
- Both jobs: ORCA TERMINATED NORMALLY; opt converged (THE OPTIMIZATION HAS CONVERGED; RMS grad 6.0e-5)

## Binding geometry (MACE opt)
- Complex stays bound: OH- H-bonded to the aldol hydroxyl
- r(O1[OH-]...O4[aldol OH]) = 2.340 A; r(O1...H13[OH]) = 2.423 A
- r(O4-H13) = 0.972 A (covalent, NO proton transfer)
- r(O1...O7[carbonyl]) = 3.635 A (far); r(O1...C2) = 4.927 A
- No bond/angle anomalies; 2 fragments preserved

## xTB pre-opt
- Scheduler job_type='xtb' unsupported (job 47 failed); ran GFN2-xTB directly
- Gas-phase SCF failed; converged with --etemp 500 --alpb water: E = -25.6137177 Eh

## Files (all absolute under /Users/cloudrayyy/Desktop/Cloudra-mechanism-agent-master/NA1_exam/species_P/)
- Final optimized xyz: P_mace_opt.xyz (extracted from job-49 log, coordinates verified vs log block)
- ORCA inp (opt+freq): P_mace.inp; parsed log: .cloudra/calc-49.out.log (job_id 49)
- ORCA inp (NumFreq): P_mace_freq.inp; parsed log: .cloudra/calc-50.out.log (job_id 50)
- xTB: P_initial.xyz, xtb_preopt.log, xtbopt.xyz
- Initial build: P_initial.mol

## Notes for Supervisor/Coordinator
- ORCA ExtOpt ignores the Freq keyword in a combined opt+freq run -> frequencies must be a separate NumFreq job (job 50).
- log_parser call on calc-49.out.log submitted earlier as review rev_e101e25208294493817b89eb13cafe94.
