# NA1 MACE TS2 variational barrier - run handoff (2026-09-04, round 7+)

Goal: get a genuinely converged MACE TS2 first-order saddle (n_imag==1) on NA1
(enolate + water + acetaldehyde -> alkoxide, charge -1, singlet, gas) so we can
give a VARIATIONAL MACE dE†(TS2 - I1 central_complex), replacing the previous
xtb-geometry + MACE single-point +3.12 kcal/mol estimate.

## Confirmed baseline (from prior rounds, do NOT recompute)
- I1 central_complex geometry = NA1_run/scanframe_2.75.xyz (C1-C8 = 2.822 A)
- I1 MACE single-point energy = -383.5374531426 Eh (job31 / .cloudra/calc-31.out.log)  [high confidence]
- TS2 xtb saddle guess = NA1_run/ts2_xtb_guess.xyz (C1-C8 = 2.439 A, xtb n_imag=1, -127.21 cm^-1)
- TS2 MACE single-point on xtb geometry = -383.5324772798 Eh (job32)
- product I2 xtb geometry = NA1_run/product_i2.xyz (C1-C8 = 1.668 A)
- product MACE single-point = -383.5442528247 Eh (job33)
- Previous hybrid dE† = E(TS2)-E(complex) = +0.004976 Eh = +3.122 kcal/mol  (single-point, NOT variational)

## Reactive-center atom indexing (1-based, in these xyz files)
- C1 = enolate alpha-CH2 carbon (nucleophile)  -> xyz line 1
- C2 = enolate alpha=C carbon (C1=C2 is the enolate C=C) -> line 2
- O3 = enolate O-  -> line 3
- C8 = acetaldehyde carbonyl C (electrophile)  -> line 8
- O9 = acetaldehyde carbonyl O (C8=O9 is the carbonyl) -> line 9
- forming C-C bond = C1-C8; distort C1=C2 (donor) and C8=O9 (acceptor)
- (the "C2-C6" label in earlier reports = same physical bond, different index convention.)

## This round's compute jobs
- job 34: MACE OptTS from xtb saddle guess (ts2_mace_optts.inp). => FAILED.
  * Harness correctly marked it FAILED (GH#21 fix CONFIRMED live; not misjudged as done).
  * Energy drifted down then up over 60 cycles; RMS grad never < 1e-4; hit max cycles.
  * Final frame unravelled: C1-C8 = 5.617 A (ion-dipole complex blew apart). Confirms
    MACE has NO stable barrier stationary point at the xtb saddle geometry.
- job 35 (RUNNING): MACE 1D relaxed scan along C1-C8 (mace_ts2_scan.inp),
  B 0 7 = 2.822 -> 1.55, 14 steps, ORCA ! OPT ExtOpt + %method ProgExt MACE.
  Purpose: map the actual MACE PES barrier; find the MACE-surface energy maximum frame
  as a MACE-consistent TS guess.

## Next steps
1. On job35 completion: ts_guess(mode=scan_parse, engine='orca', log_path='.cloudra/calc-35.out.log')
   -> MACE barrier profile + max-energy frame as TS guess (mace_ts2_scan_ts_guess.xyz).
2. MACE OptTS from that scan-max frame (with %geom MaxIter, NumFreq). Verify opt_converged
   (GH#21), normal_termination, final_energy_hartree (GH#22). Then n_imag==1 via freq.
   If n_imag != 1 -> NOT a valid saddle, annotate, do not force.
3. variational dE† = MACE_E(converged TS2) - MACE_E(MACE-optimized I1).
   NOTE: for a fully variational dE both reference must be MACE-optimized. If only the
   TS converges, we may need a MACE Opt of I1 (scanframe_2.75 start) for the true baseline.
4. Write NA1_run/mace_ts2_variational_report.md + update progress.md.

## If MACE still cannot converge a saddle
Report honestly: "further progress blocked by MACE convergence on this floppy ion-dipole
system" + reasons (monotonic drift, no stable stationary point, PES flatness). Fallback:
give the MACE single-point estimate on best geometry, clearly labeled NON-variational.

## Tooling notes for this session
- internal_coordinates / format_converter need ABSOLUTE paths (relative NA1_run/... failed).
- read/write/edit accept NA1_run/ relative prefix.
- GH#26: xtb has no scheduler channel; xtb geometry files are from prior bash runs.
