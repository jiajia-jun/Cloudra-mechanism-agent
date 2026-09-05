# Full campaign dispatch — NA1 acetaldehyde self-aldol -> 3-hydroxybutanal (xtb + MACE-OMol25 only)

You are small_mol quantum-chemistry specialist (a-4). FIRST tool call MUST be: load the `dft-calculation` skill and follow its SOP (use get_skill with the skill name).

Work directory (create it, work ONLY here):
  /Users/cloudrayyy/Desktop/Cloudra-mechanism-agent-master/NA1_sim_20260905/campaign_xtb/
Do NOT create/modify files under ../evidence/ and do NOT touch workspace-root HARNESS_NOTES.md / mechanism_graph.json.

SYSTEM:
  reactant SMILES: [OH-].CC=O.CC=O   (charge -1, multiplicity 1)
  product SMILES:  [OH-].CC(O)CC=O   (charge -1, multiplicity 1)
  atom mapping (1-based): [OH-:1].[CH2:2]([H:8])[CH:3]=[O:4].[CH3:5][CH:6]=[O:7]
  conditions: dilute NaOH, water, 0-25 C.

METHOD HARD CONSTRAINT (task rule): ONLY GFN2-xTB and MACE-OMol25 are allowed.
  - Gaussian/B3LYP/any other functional/basis set is FORBIDDEN.
  - xtb: no scheduler job_type exists (GH#26) -> run via bash heredoc/xyz with absolute binary
        ~/miniconda3/envs/chemai/bin/xtb (or `which xtb`), capture stdout to <tag>.xtb_opt.log.
  - MACE-OMol25: electronic single points only, at xtb stationary geometries, via ORCA ! ExtOpt SP
        external-program route: %method ProgExt "<mace exe>" (find exe with `which mace`; consult
        /Users/cloudrayyy/Desktop/Cloudra-mechanism-agent-master/deploy/mace_omol25_orca_external_setup.md
        for the working template + KMP_DUPLICATE_LIB_OK). Prefer the official channel
        (qm_input_writer single_point + submit_compute_job job_type=orca); if the scheduler/gate blocks,
        run orca directly and SERIAL (no %pal): ~/opt/orca_6_1_1/orca in.inp > <tag>.mace_sp.out.log.
        Parse energy from the LAST line matching: FINAL SINGLE POINT ENERGY (From external program).
        NEVER use ORCA ExtOpt Opt/OptTS for geometry (unconverged-but-done traps GH#21/#22).

WORKING HYPOTHESIS of the network (VERIFY with computation; if evidence contradicts, follow the evidence and report):
  rc -> ts1 -> i1 -> ts2 -> i2 -> ts3 -> p
  rc  = pre-reaction complex: hydroxide + 2 acetaldehyde.
  i1  = acetaldehyde enolate: O1 abstracts H8 from C2  -> bond_changes rc->i1: break [2,8], form [1,8].
  i2  = aldol-addition alkoxide: enolate C2 attacks C6=O7 -> bond_changes i1->i2: form [2,6].
  p   = 3-hydroxybutanal + regenerated OH- via proton shuttle O1-H8 onto O7 -> bond_changes i2->p: form [7,8], break [1,8].
  Net charge -1, singlet for every species. O1 is the hydroxide oxygen throughout; H8 is the acidic methyl H of C2.
  If the real mechanism differs (water-mediated proton relay, O-protonated enol, different connectivity),
  determine it with evidence (RDKit bond perception on optimized frames to verify species identity!) and report honestly.

PER-SPECIES / PER-STEP PROTOCOL:
 1) xtb opt: xtb <tag>.xyz --gfn 2 --alpb water --opt tight --chrg -1 --uhf 0
      Confirm BOTH "normal termination of xtb" AND the opt-converged marker before trusting geometry.
 2) xtb numerical Hessian at the stationary geometry (re-run `--ohess` on the final xyz is fine, it re-opts fast):
      minima must have n_imag=0; TS exactly n_imag=1. Record lowest real/imag frequencies.
 3) MACE-OMol25 single point at the optimized xtb geometry (SP only).
 4) TS search (ts1, ts2, ts3): prefer xtb relaxed scans along the hypothesis bond coordinates; on flat anionic
      surfaces prefer IDPP interpolation between relaxed minima then xtb TS opt; always verify saddle with freq
      (n_imag=1) + imaginary-mode displacement matching the expected bond changes. If xtb rolls to product/
      reactant instead of a saddle, record "barrierless / no saddle on xtb" with scan diagnostics - DO NOT fabricate.
      xtb barriers on this charged floppy system are approximate: label them approximate in every quoted number.
      Never use a scan-crest frame as a converged TS without freq verification.
 5) smiles annotation on EVERY evidence file: for xtb .xyz put `smiles: <SMILES>` as the comment line;
      for ORCA inputs put a `smiles: <SMILES>` comment in the file.
      Suggested tags/SMILES (verify protonation/connectivity with RDKit against the mapping):
        rc  : [OH-].CC=O.CC=O
        i1  : enolate complex, e.g. [OH2].CC=O.C=C[O-]  (net -1; verify)
        i2  : aldol alkoxide, e.g. [OH2].C[CH]([O-])CC=O (net -1; verify)
        p   : [OH-].CC(O)CC=O
 6) Energy definitions: E_xtb = final xtb total energy (Eh); E_MACE = ORCA external SP energy (Eh).
      dE_barrier = E(TS) - E(reference stationary minimum on the SAME method PES). A frozen scan frame is NOT
      a valid reference. If MACE PES does not bind the reactant complex, state that the MACE barrier is not
      computable rather than quoting a number against a non-stationary frame.
      1 Eh = 627.5095 kcal/mol. State the energy definition beside every barrier.
 7) RDS: rank elementary barriers and name the rate-determining step with its barrier (kcal/mol + definition).
      Cross-check against known base-catalyzed aldol chemistry but let your computed numbers decide.

OUTPUTS (all inside campaign_xtb/):
  - per species: <tag>.xyz, <tag>.xtb_opt.log, <tag>.xtb_freq.log, <tag>.mace_sp.out.log (if obtained)
  - energies.md : energy bookkeeping (xtb E, MACE E, n_imag, convergence, evidence file per species)
  - CAMPAIGN_REPORT.md : species table; per-step barriers (kcal/mol + definition + evidence file); RDS
      conclusion; and a list of every failed attempt / tool / scheduler / parser anomaly encountered
      (reproduction + log path) so the coordinator can mirror them into HARNESS_NOTES.md.

Convergence discipline: never use an unconverged energy as a barrier (diagnostic only).
Job hygiene: unique <tag> per job, no two jobs with the same input basename in one directory, ORCA serial.

When finished: write CAMPAIGN_REPORT.md AND put a concise final message in your session report: RDS barrier
kcal/mol + energy definition, converged-species list, and anomalies.
