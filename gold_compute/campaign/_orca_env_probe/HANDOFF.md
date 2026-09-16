# HANDOFF — ORCA 6.1.1 arm64 crash diagnosis (env specialist)

## Goal
Diagnose & (best-effort) fix two ORCA 6.1.1 crashes so Hessian-class jobs (OptTS/Freq/IRC) can run stably with nproc>1.
If unfixable: give firm conclusion + recommended config.

## Environment facts
- Apple M5 Pro / arm64, macOS 26.3.2 (25D2150), 18 cores, 48 GB (51539607552 B).
- ORCA: /Users/cloudrayyy/opt/orca_6_1_1/  (self-compiled arm64; NO official version file; writes main output to STDOUT, not .out -> non-standard build).
- OpenMPI 4.1.8: /Users/cloudrayyy/opt/openmpi-4.1.8 ; libmpi.40.dylib linked.
- env: OMPI_MCA_btl=vader,self ; OPENMPI_DIR, ORCA_DIR set; PATH has orca + openmpi first.
- ORCA needs FULL PATH invocation for parallel runs ("ERROR (ORCA_MAIN) ... call with full pathname").

## Evidence collected (crash reports, ~/Library/Logs/DiagnosticReports)
5 DISTINCT signatures (see analysis):
1. orca (parent, single-proc) SIGSEGV @0x38 in VIB_PrintSpectra <- ORCA_AnalyticalFrequencies <- ORCA_GeometryOptimization  [09-10 x2]
2. orca_scfgrad_mpi SIGABRT (PAL_Abort) in GRAD_CalcXCGradient_2 <- SHARK_DRIVER_SCF_Gradient  [09-12 x8, 09-13 x4]
3. orca_util_mpi SIGABRT (PAL_Abort) at main  [09-10 x4]
4. orca SIGSEGV @0x68 in HenkelmanJonssonIntp <- NEB  [09-11] (fprintf on NULL FILE*)
5. orterun (HNP) SIGSEGV @0x0 in _platform_memmove <- orte_rml_oob_send_buffer_nb <- pmix_server_log_fn (OpenMPI PMIx log path) [09-12, 09-16]

## Symptom B (relaxed scan) reproduced inputs
Campaign scan jobs that crashed: NU3 calc-E1-scan (nproc=4), F1 scan (nproc=4). Logs: ".../NU3/NU3_E1/1/.cloudra/calc-349.out.log", ".../F1/F1_E1/3/.cloudra/calc-347.out.log".
Message chain: "Storing optimized geometry ... failed!" -> "ERROR (SHARK): Failed to read input file (...SHARKINP.tmp)" xNP -> "ORCA finished by error termination in PROPERTIES".

## Probe dir
/tmp/orca_mpi_probe/  (scratch); workspace copy: gold_compute/campaign/_orca_env_probe/
- w_freq_np4.inp  : water ! Freq nproc=4  -> OK rc=0 3s (SCF Response in-proc)
- ha1ts_freq_np4.inp : HA1 TS geom (13 atoms) ! Freq nproc=4 -> OK rc=0 23s
- nusc_scan.inp  : campaign NU3 relaxed scan nproc=4  [RUNNING -> nusc_scan_np4.out / .rc]
- f1_scan.inp    : campaign F1 relaxed scan nproc=4

## Next steps
- [ ] collect nusc_scan_np4 result (reproduce symptom B?)
- [ ] run nproc=1 variant of scan
- [ ] stress Freq/Opt+Freq np4 x3-5 to catch intermittent symptom A
- [ ] env matrix: VECLIB_MAXIMUM_THREADS=1(+OMP_NUM_THREADS=1); OMPI_MCA_btl variants; nproc 2 vs 4
- [ ] conclude root-cause level + recommend config + injection point (cloudra launch layer)

## Constraint
Do NOT touch gold_compute/campaign/runs/NU3/** or jobs 416-421.
