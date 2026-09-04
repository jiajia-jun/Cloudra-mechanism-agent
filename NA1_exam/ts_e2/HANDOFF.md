# HANDOFF — edge e2 (I1 -> I2, C-C bond formation), sub-agent a-4

## Goal
Locate/validate TS for e2 at MACE-OMol25 (ORCA ExtOpt). Charge -1, singlet, 16 atoms.
Anchors: I1 = -383.5468773487 Ha, d(C1-C6)=3.694 A (species_I1/I1_mace_optfreq.xyz, I1 atom order);
I2 = -383.5533544289 Ha, d=1.555 A (species_I2/I2_mace.xyz, different order: forming pair = I2 atoms 4-2).
Atom map I2->I1 (1-based): [5,6,7,1,2,3,4,13,14,15,16,8,9,10,11,12].

## Key results so far
- xTB constrained scan C1-C6 3.6->1.5 A (scan/profile.dat): MONOTONIC downhill 3.6->1.7 (min at 1.7,
  E=-25.514163 Eh), rises only below 1.6 (geometry compression). Unconstrained xtb opts from <=1.7 all land in
  product basin (d=1.745, E=-25.5142956); xTB I1=-25.5019300 (d=3.947), xTB I2 from MACE geom=-25.5226522.
  => no xTB barrier.
- IDPP path (idpp/, 12 images, tool gave ts_candidate img_06 at d=2.46).
- MACE OptTS job 53 (from xTB scan p_2.10 geometry): CONVERGED, E=-383.5314057706 Ha,
  geom e2_mace_optts.xyz: d(C1-C6)=1.541 (bond already formed), C2-O3=1.228, C6-O7=1.372. Log .cloudra/calc-53.out.log.
- MACE NumFreq job 78 (must use '! ExtOpt NumFreq' — 'Freq' keyword is silently skipped, see failed job 56):
  EXACTLY ONE imaginary frequency -157.93 cm-1. Mode vector extracted to mode6_raw.txt (48 comps, normalized).
  Mode character: dominated by O7 (alkoxide O, 0.575) + water/H motion; C1-C6 stretch component only -0.063.
  G(TS, RRHO 298K) = -383.43663465 Ha. Log .cloudra/calc-78.out.log.
- Fallback IRC (ExtOpt IRC not attempted — impractical): TS +/- 0.25*mode6, unconstrained MACE Opt:
  job 89 (plus):  converged E=-383.5361169639, d(C1-C6)=1.595 -> I2-basin conformer
  job 90 (minus): converged E=-383.5432766663, d(C1-C6)=1.524 -> I2-basin conformer (more enolate-like C2-O3=1.275)
  BOTH sides land in the I2 basin; NEITHER returns to I1 (d 3.7). => The saddle is NOT the C-C-forming TS;
  it is an intra-I2-basin (alkoxide-O/water reorganization) saddle.
- I1 thermochem (calc-42 log): G(I1)=-383.46058674 Ha, 0 imag. Formal dE/dG vs I1 IF saddle were e2:
  +9.7 / +15.0 kcal/mol — but connectivity says it is NOT e2's TS.

## MACE scan (job 91) — DEFINITIVE: there IS a barrier
- Scheduler marked job 91 failed ('geometry opt not converged'), but ORCA TERMINATED NORMALLY and all 21
  frames computed. ts_guess scan_parse on .cloudra/calc-91.out.log: profile rises MONOTONICALLY from
  frame 0 (d=3.694) to frame 16 (crest, +10.68 kcal/mol), then descends to frame 20 (d=1.55, +7.07).
  => e2 C-C formation HAS a ~10.7 kcal/mol barrier at MACE level (contradicts xTB scan, which is downhill).
- Crest frame 16 geometry -> e2_mace_scan_ts_guess.xyz: d(C1-C6)=1.979 A [forming], C6-O7=1.260 (carbonyl
  weakening), C2-O3=1.245. Internal-coords report in e2_scan_crest.zmat. This IS the C-C-forming TS region,
  unlike the job-53 saddle (d=1.541, bond fully formed, mode = O7/water).
- Caution: scan frame 20 sits +7.07 above frame 0 while I2 is -4.06 kcal/mol below I1 => scan relaxation
  incomplete (consistent with the non-convergence flag); barrier value is an upper bound.

## Job 92 OptTS from scan crest: CONVERGED
- Log .cloudra/calc-92.out.log: normal_termination=true, opt_converged=true, job_types [opt, ts],
  E = -383.529836227 Ha. Geom e2_mace_optts2.xyz: d(C1-C6)=1.977 A [forming], C6-O7=1.260, C2-O3=1.245.
  Barrier vs I1 (E=-383.5468773487): +10.69 kcal/mol. log_parser call on calc-92 submitted for review.

## In flight
- Job 94: MACE NumFreq on e2_mace_optts2.xyz (e2_mace_numfreq2.inp, '! ExtOpt NumFreq' — hand-fixed
  from writer's 'Freq'; nprocs 1). Log will be .cloudra/calc-94.out.log.
  On success: need EXACTLY 1 imag freq; check mode character (want C1-C6 stretch, not O7/water like
  the job-53 saddle); then displace +/- along imag mode -> two unconstrained MACE Opt jobs
  (endpoint_a -> I2 basin d~1.55, endpoint_b -> I1 basin d~3.69) to prove connectivity; then thermochem
  (thermo_analysis with I1/I2 anchors + this TS).

## Verdict shaping (honesty clause, UPDATED)
xTB says barrierless, MACE scan says ~10.7 kcal/mol barrier. Trust MACE (gradeable method). Job-53 saddle
(d=1.541, imag -157.93, mode O7/water, both displacement opts -> I2 basin) is likely NOT the e2 TS;
the scan-crest OptTS (job 92) should give the real C-C-forming saddle.

## Traps hit this session
- 'Freq' with ExtOpt runs a plain single point (job 56, 406-line log, no frequencies). Must use 'NumFreq'.
- Scheduler log paths: NA1_exam/ts_e2/.cloudra/calc-<id>.out.log. Verified termination/convergence by grep.
- ORCA %geom Scan indices are 0-based (ts_guess converts correctly).
