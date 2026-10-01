# HI1 E2 major recovery — seed provenance (route ii)

Created 2026-10-01 (post power-cut resume). Owner: major/E2 channel (child A).

## WHY (job 64 invalid)
job 64 (major_spec/ts2_orca6) was killed by a MASS external termination at 2026-10-01T16:52:49
(jobs 14/65 same second, all lack 'ORCA TERMINATED NORMALLY'). Independent of the kill it was ill-posed:
the seed ts2_seed.xyz (= scan_clean_np8.005.xyz, d(Ca-Cc)=2.95) is a MINIMUM, not a saddle (cycle-1 exact
Hessian: 0 negative eigenvalues, lowest eig ~7e-5 floored to 1e-4; 123 modes, 0 imaginary). The followed
'TS' mode was a WATER libration (B(H26-O24)=0.50, D(H26,O24,O9,C8)=0.43); Ca-Cc receded 2.950 -> 3.540 A
over 94 frames. Final frame = non-covalent 3-fragment precomplex, no C-C bond.
=> The 2.95 'crest' is the H-BOND-REORGANIZATION feature; the C-C FORMATION barrier is the LATER one.

## SEED (this job)
Scan job 58 (major_spec/scan_clean) relaxed profile, d(Ca-Cc) : E(Ha):
 4.30 -938.759999 | 3.96 -938.758857 | 3.63 -938.756074 | 3.29 -938.753652 | 2.95 -938.750117 |
 2.61 -938.754713 | 2.28 -938.745329 | 1.94 -938.734979 | 1.60 -938.736002
The C-C formation barrier top is the LATER feature (max at d=1.938, +15.7 kcal vs RC51); there the
Ca-Cc mode is the softest, and the water-mediated H-bond (O10...H26, H27...O28) is retained.
Seed used = major_spec/scan_clean/scan_clean_np8.008.xyz  sha256
  6c92457397e11cc1754774a34aabc25dc3b09fcec273bfbc3d7cd4704fdadb9e
Face check (D(Cb-Ca-Cc-Od), 1-based C2-C1-C29-O28): RC51 +58.3 -> scan 1..9 +58.3,+64.7,+58.9,+47.9,+50.0,
  -7.0,-7.7,-21.1,-36.3 -> smooth, NO ~180 deg flip => same (major) face throughout.
Seed validation (internal_coordinates, frame 8): C15H21NO4, 41 atoms, 2 fragments (C-C adduct + water),
rings only proline-5 + benzene (no spurious ring), C1-C29 = 1.938 A (elongated, bond order 1 = partial),
water H-bond retained (O10-H26=1.945, H27-O28=1.680), no heavy clash; proton: carboxyl O-H intact.
(Interpolation RC51 <-> frame8, IDPP, 12 images, for path continuity: ts2_recovery/interp/.)

## THIS JOB
ts2_recovery/orca_ts/ts2r_major_np8.inp — ONE unconstrained OptTS+Freq:
 ! OptTS Freq b3lyp def2-SVP D3BJ def2/J RIJCOSX TightSCF CPCM(DMSO) ; %pal nprocs 8 ; %maxcore 1536 ;
 %geom Calc_Hess true end. NO MaxIter/MaxSteps/timeout. q0 m1, explicit water, 41 atoms.

## REFERENCE SHAs
 RC51 baseline  major_spec/job51_final.xyz  85e4508dacbb0313a6d2c1003a7b8402e6e987db9c27c0a9c84ffa2902811465
                E = -938.760019066499 Ha (headline E(RC) for dE#(E2))
 job64 input    major_spec/ts2_orca6/ts2_np8.inp  4bc23077cbbaf9b3d5872aa4357b5932c00136974d8a5eb68a86b765e0ebacf9
 job64 seed     major_spec/ts2_seed.xyz            8cb24ddd0e91025ebc73f632a9e046c51b2bfa7529e6d74d4fa5323fe16c2249
 job64 log      major_spec/ts2_orca6/.cloudra/calc-64.out.log  ae092cce72c0a42f65cc50f696fa39dab4b9440b217aa12785fb83bd90b3b4a8
 job64 files PRESERVED (not overwritten).

## VERIFICATION TARGET
Exactly 1 imaginary mode ALIGNED with Ca-Cc (watch_pairs=[[1,29]] 1-based) -> IRC both ways ->
endpoint Opt/Freq (0 imag; one endpoint = RC complex, other = C-C adduct). dE#(E2)=E(TS2)-E(RC51).
Stop-and-ask if cycle-1 Hessian has 0 negative eigenvalues or the followed mode is not Ca-Cc.
