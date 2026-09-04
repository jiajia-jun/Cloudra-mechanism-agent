# HANDOFF — edge e1 TS search (R -> I1, OH- alpha-proton abstraction)

Sub-agent task dir: /Users/cloudrayyy/Desktop/Cloudra-mechanism-agent-master/NA1_exam/ts_e1/
Do NOT read NA1_run/, ideapool/, other mechanism_graph.json.

## Atom indexing (1-based, R frame ordering, all files in this dir)
O1 = hydroxide O; C2 = alpha-C; C3 = carbonyl C; O4 = carbonyl O; C5/C6/O7 = spectator CH3CHO;
H8 = hydroxide proton; **H9 = transferring alpha-H**; H10,H11 = other alpha H; H12 = aldehyde H; H13-16 spectator H.
Scan coordinate: bond O1-H9.

## Completed
1. xTB GFN2 relaxed scan (20 pts, d(O1-H9) 1.75 -> 0.95 A) from R MACE minimum.
   - Files: xtb_scan/xtb_scan.out, xtb_scan/xtbscan.log, scan.xcontrol
   - Profile (Eh): f1 -25.488318 (d=1.75) ... f7 -25.489970 (d=1.497, = free R xtb min -25.489961)
     -> rises to CREST f14 -25.487906 (d=1.203) -> f15 -25.488096 (enolate flip) ... f20 -25.487350 (d=0.95)
   - xTB apparent barrier vs R min: +1.30 kcal/mol. Very low, hysteresis jump at f14->f15.
2. TS guess geometry: ts_crest_xtb.xyz (scan frame 14, d(O1-H9)=1.203 A).
3. xTB --ohess on crest: re-optimized -> COLLAPSED BACK TO R BASIN (O1-H9=1.503, C2-H9=1.197,
   E=-25.489988 Eh), 0 imaginary freqs. xTB crest is not a stable saddle region.
4. MACE-OMol25 OptTS via ORCA ExtOpt: input e1_mace_optts.inp (Calc_Hess+NumHess, MaxIter 200, MaxStep 0.1),
   submitted as job_id 52 (async, cpus=1) -> FAILED: hit MaxIter 200, not converged.
   TRAJECTORY DIAGNOSIS (e1_mace_optts_trj.xyz, 200 frames): start O1-H9=1.226/C2-H9=1.393 (TS region),
   by frame ~40 proton fully transferred (O1-H9=0.998, C2-H9=1.978, C2-C3=1.387, C3-O4=1.255 = enolate+H2O),
   then wandered flat product basin for 160 frames (RMS grad ~0.002, MAX ~0.007, never converged).
   => On the MACE surface the xTB crest geometry is NOT a saddle; gradient drives proton transfer downhill
      toward I1 from O1-H9=1.23 onward. Barrier (if any) lies between R (1.75) and 1.23 A.
5. MACE relaxed scan along O1-H9 (16 steps, 1.75 -> 0.95 A) from R MACE minimum:
   input e1_mace_scan.inp (ORCA ExtOpt, %geom Scan B 0 8).
   - job 54: FAILED 13:26 — [ERROR] extinp file not found. Root cause: jobs 54 and 55 (same .inp basename)
     ran CONCURRENTLY in ts_e1/ (both started ~13:24-13:25); they shared e1_mace_scan_EXT.extinp.tmp and
     raced. 54's log is contaminated — DISCARD it entirely. Lesson: never run two ORCA jobs with the same
     basename in one directory.
   - job 55 (async, cpus=1): RUNNING, authoritative. At 13:27 it was in scan step 8/16.
     CAVEAT for audit: 55's step 1 overlapped with 54's life; 55's log line 3804 shows
     'Error: can not compute RMSD between geometries with different number of atoms!' (collision artifact
     at end of step 1). After completion, VERIFY per-step energies for continuity; if step 1 is corrupt
     rerun that point alone in a clean subdir. Steps >=2 ran after 54 died and should be clean.
   Log: .cloudra/calc-55.out.log. This is the DECISIVE MACE-level evidence for barrier vs barrierless.

6. IDPP interpolation R->I1 (ts_guess mode=interpolate, manual 16-atom map
   [2,3,4,1,5,6,7,10,11,12,8,9,13,14,15,16]; reaction_mapping tool was ambiguous so map built by
   coordinate inspection): 12 images in idpp_e1/, smooth monotonic O1-H9 1.766->1.003, no geometric
   bottleneck; TS-candidate frame idpp_e1/img_06.xyz (O1-H9=1.346, C2-H9=2.071). ACCEPTED by Supervisor
   as e1 ts_guess.
7. MACE OptTS #2 (job 59, e1_mace_optts2.inp, seed = img_06, MaxIter 200): TERMINATED NORMALLY, not
   converged. Trajectory e1_mace_optts2_trj.xyz: proton fully transferred by frame ~40 (O1-H9=0.995,
   enolate C3-O4=1.22), then 160 frames flat-basin wandering; final E=-383.4951655 Eh. Second
   independent MACE collapse into I1 basin.
8. Supervisor REJECTED e1 ts_opt stage (disagree, not disposal): demands a CONVERGED OptTS
   (opt_converged=true). Response: MACE OptTS #3 (job 67, e1_mace_optts3.inp) seeded from R-side
   idpp_e1/img_03.xyz (O1-H9=1.541, C2-H9=1.581 - the xTB hysteresis region), %geom MaxIter 300
   MaxStep 0.05 Recalc_Hess 5 end. If this also collapses without converging, that is the third
   independent failure to locate a saddle -> report full barrierless package and ask Coordinator to
   request not_applicable disposal of e1 ts_opt/frequency/short_irc/direction from Supervisor.

9. TASK C (freq arbitration on calc-82 endpoint): CONVERGED NUMFREQ = TRUE SADDLE.
   - Verified e1_c130.xyz is bit-identical to the last Cartesian frame of calc-82 log (E=-383.5195555244).
   - Endpoint geometry: O1-H9=1.3000, C2-H9=1.4015, O1-H8=0.9625, C2-C3=1.4236, C3-O4=1.2332 A (mid-transfer).
   - job 96 (input e1_freq82.inp, '! ExtOpt Freq'): TERMINATED NORMALLY in 5 s, freq SILENTLY SKIPPED
     (trap #3 confirmed for standalone freq; parse rejected rev_b1e8f00a...). Log contains NO vib data.
   - job 98 (input freq82/e1_freq82nf.inp, '! ExtOpt NumFreq', smiles comment line): DONE, 90/90 displacements,
     55 s. Log: freq82/.cloudra/calc-98.out.log. log_parser: normal_termination=true, E=-383.5195555243 Eh
     (bit-identical to opt endpoint), ZPE=0.11852205 Eh, G-E(el,298K)=0.08218383 Eh.
   - Frequencies: EXACTLY ONE imaginary, -1347.12 cm^-1 (mode 6); 41 real (lowest 35.32, 55.03, 76.94 ...),
     6 null. Mode 6 character: H9 mass-weighted |disp| 0.988 (next H11 0.102, H10 0.066, C2 0.047, O1 0.045);
     |dot(H9disp, O1->H9)|=0.999, |dot(H9disp, H9->C2)|=1.000 => pure O1-H9...C2 proton-shuttle mode.
   - VERDICT: first-order saddle for e1 R->I1 proton transfer on the MACE-OMol25 PES. TS stage candidates:
     ts_opt = calc-82 parse; frequency = calc-98 parse (pending Supervisor review rev_3a23cb72...).
   - Caveat: E(TS) is 1.86 kcal/mol BELOW E(R) electronically; quantitative barrier needs ZPE/G on both
     sides + DFT confirmation. Full writeup: freq82/REPORT_freq82.md.

## Pending / next
- Await Supervisor adjudication of calc-98 log_parser (frequency stage). If agreed, e1 still owes:
  short_irc (from e1_c130.xyz along mode 6), endpoint opts, direction, identity, thermochemistry.
- Endpoint anchors: R E=-383.516590722200 Ha; I1 E=-383.546877348700 Ha; MACE dE_rxn = -19.1 kcal/mol.
- Parse every finished ORCA log with log_parser (feeds Supervisor review inbox). Report tool_call_ids.
- Tooling trap: ORCA Scan+ExtOpt intermittently loses the EXT.extinp.tmp file (jobs 54/55) - do NOT
  resubmit ExtOpt scans; also never run two ORCA jobs with same basename in one dir.
