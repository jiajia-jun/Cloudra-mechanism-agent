# ORCA 6.1.1 (arm64, self-built) crash diagnosis — Env specialist report

Date: 2026-09-16. Machine: Apple M5 Pro / arm64, macOS 26.3.2 (25D2150), 18 cores, 48 GB.
ORCA: /Users/cloudrayyy/opt/orca_6_1_1/  — **Program Version 6.1.1 RELEASE (GIT: $487d211cc3$), build 2025-11-21 10:33:24**.
MPI: OpenMPI 4.1.8 (/Users/cloudrayyy/opt/openmpi-4.1.8, built from source 2026-09-02 19:41).

## 0. Deliverable summary
- **Symptom B**: ROOT-CAUSED and **deterministically reproduced in 10 s**. It is an ORCA-internal bug in the
  relaxed-scan path when a scan point's optimisation hits MaxIter (nproc-independent). Firm workaround available.
- **Symptom A**: real (5 crash signatures on disk) but **NOT reproducible on demand** (~69 clean nproc>=2 runs,
  0 crashes, 0 new crash reports). Judged a rare latent bug of this self-built arm64 binary / its OpenMPI relink.
  No env variable was shown to fix it; recommend a stability strategy instead.

## 1. ORCA parallel architecture (confirmed by live ps)
The serial driver `orca` (no MPI linkage of its own) spawns, per module:
  mpirun -np N orca_startup_mpi / orca_leanscf_mpi / orca_scfresp_mpi / orca_scfgrad_mpi / orca_prop_mpi / orca_util_mpi
So "the parallel Hessian path" is `mpirun -np N orca_scfresp_mpi`; gradients are `orca_scfgrad_mpi`.
NOTE: ORCA must be invoked by **absolute path** for parallel runs ("ERROR (ORCA_MAIN): ... full pathname").
`calculator.sh` already resolves this via PATH; a bare `orca file.inp` fails.

## 2. Crash evidence (macOS DiagnosticReports, exact stacks)
Five DISTINCT signatures (parent process in brackets):
1. **[orca, serial]** SIGSEGV @0x38: VIB_PrintSpectra <- ORCA_AnalyticalFrequencies <- ORCA_GeometryOptimization
   (2x, 2026-09-10) — null-deref while PRINTING an analytic-frequency spectrum (Opt+Freq path).
2. **[orca_scfgrad_mpi]** SIGABRT (PAL_Abort, ORCA's own abort): GRAD_CalcXCGradient_2 <- SHARK_DRIVER_SCF_Gradient
   (12x: 09-12 x8, 09-13 x4) — collective abort of all 4 ranks inside ORCA gradient code.
3. **[orca_util_mpi]** SIGABRT (PAL_Abort) at main (4x, 09-10) — per-rank abort at startup/utility stage.
4. **[orca, serial]** SIGSEGV @0x68: HenkelmanJonssonIntp <- NEB — fprintf on a NULL FILE* (09-11).
5. **[orterun / HNP]** SIGSEGV @0x0: _platform_memmove <- orte_rml_oob_send_buffer_nb <- pmix_server_log_fn
   (09-12, and 09-16 04:26, parentProc=orca) — **OpenMPI HNP crashes while logging a child's message**.
Correction to the task brief: there is **no `orca_scfresp_mpi`** crash report; the MPI crashes on disk are in
`orca_scfgrad_mpi` / `orca_util_mpi`. Signature 1 (VIB_PrintSpectra, analytic-freq printing) is the only
fault that matches "解析 Hessian ... SEGFAULT", and it is **in the serial parent, not in an _mpi module**.

## 3. Build-provenance skew (observed, treated as a risk factor not a proven cause)
- serial binaries + `lib/liborca_tools_6_1_1{,_mpi}.6.dylib`: **2025-11-25** (build id 2025-11-21).
- **all 232 `*_mpi` executables: 2026-09-02 19:45** — 4 minutes AFTER openmpi-4.1.8 finished installing (19:41).
=> the _mpi executables were (re)linked in a separate operation against the freshly built OpenMPI, while the rest
of ORCA is from the Nov-2025 build. Every MPI crash is in those relinked _mpi binaries (or in OpenMPI itself).
This is consistent with — but does not by itself prove — a build/relink-level defect.

## 4. Symptom B — ROOT CAUSE (reproduced, deterministic)
Campaign logs: `.../runs/NU3/NU3_E1/1/.cloudra/calc-349.out.log`, `.../runs/F1/F1_E1/3/.cloudra/calc-347.out.log`.
In BOTH, the failure follows exactly:
  WARNING "The optimization did not converge but reached the maximum number of optimization cycles."
  -> "Storing optimized geometry in <stem>.NNN.xyz ... failed!"
  -> "ERROR (SHARK): Failed to read input file (<stem>.SHARKINP.tmp)" x(N ranks)
  -> "ORCA finished by error termination in PROPERTIES"
Fast reproduction (probe /tmp/orca_mpi_probe, input scan_maxiter*.inp): take the campaign NU3 relaxed scan
(`! OPT b3lyp def2-SVP D3BJ def2/J RIJCOSX` + `%geom Scan B 0 7 = ... end`) and force non-convergence with
`%geom MaxIter 2 end`. Result: **crashes in ~10 s at nproc=4 AND nproc=1** (identical message chain).
CONTROL: a plain `! OPT` with the same MaxIter=2 (no Scan) only warns and **terminates normally**; a relaxed
scan whose points DO converge (HA1 scan_C2C3, 14 points) completes normally.
=> The defect is **specific to the relaxed-scan driver's handling of a non-converged scan point**; MPI is irrelevant.
Also note the misleading detail: the `.NNN.xyz` file is actually written (887 B) while ORCA reports "failed!";
SHARKINP.tmp is never produced, so the PROPERTIES step aborts. ORCA's driver still exits **0**, so the harness
must detect this by log parsing (it already does).
**Conclusion: ORCA-build defect, not an environment/dependency problem.** No env change can fix it.
Alternatives: (a) constrained optimisation (steer with `%geom Constraints` at fixed scan values),
(b) double-ended **NEB-TS** / OptTS (F1 succeeded this way: OptTS job 408 + NEB-TS 409 + freq 410 + IRC 411),
(c) if a scan is unavoidable, make every point converge (raise MaxIter, gentler steps) and retry.

## 5. Symptom A — experiment matrix (all runs in /tmp/orca_mpi_probe)
| config | job (nproc) | runs | failed | notes |
|---|---|---|---|---|
| btl=vader,self (current) | water Freq (4) | 25 | 0 | scfresp_mpi exercised; VIB printing OK |
| btl=vader,self | HA1 TS Freq (4) | 10 | 0 | 13-atom, VIBRATIONAL FREQUENCIES printed each time |
| btl=vader,self | HA1 Opt+Freq (4) | 3 | 0 | the crashed job class |
| btl=vader,self | naphthalene Freq (4) | 1 | 0 | 18-atom, 69 s |
| btl=vader,self | HA1 TS Freq (2) | 5 | 0 | nproc 2 vs 4 — no difference |
| VECLIB_MAXIMUM_THREADS=1 | HA1 TS Freq (4) | 5 | 0 | |
| VECLIB=1 + OMP_NUM_THREADS=1 | HA1 TS Freq (4) | 5 | 0 | |
| OMPI_MCA_btl=sm,vader,self | HA1 TS Freq (4) | 5 | **5** | INVALID: OpenMPI 4.1.8 removed the 'sm' BTL -> MPI_INIT fails |
| btl=self,vader + pml=ob1 | HA1 TS Freq (4) | 5 | 0 | |
| 2 concurrent jobs/two dirs (8 cores) | HA1 TS Freq (4) | 6 | 0 | production-like |
Total: ~69 valid runs, **0 genuine crashes**, 0 new DiagnosticReports. (The 8 "term=0" rows are the 5 invalid-sm
runs + 3 runs that early-aborted because two jobs shared one scratch dir.)
=> **Symptom A is real but essentially unreproducible on demand** with small/medium closed-shell substrates at
nproc 1/2/4, single or concurrent; env tweaks neither reproduce nor remove it.

## 6. Root-cause judgement
- The fault LOCALISES to ORCA's own code (PAL_Abort inside GRAD_CalcXCGradient_2; NULL-deref inside VIB_PrintSpectra
  and NEB's fprintf) and to OpenMPI's HNP (signature 5). It is **not** a missing library / ABI-mismatch symptom
  (otool shows consistent links to libmpi.40 and Accelerate) and **not** an Accelerate-thread issue (VECLIB=1
  changed nothing).
- The most probable layer is **this self-compiled arm64 ORCA build + its separately-relinked _mpi binaries**
  interacting with OpenMPI 4.1.8. Official ORCA does not ship a validated Apple-Silicon-native build; hand-built
  arm64 ORCA is a known-tricky target.
- It is a **rare latent defect**, manifested intermittently and substrate-dependently. It is not economical to
  chase further on this build.

## 7. Recommended configuration & injection point
ENV (safe, additive; inject in `cloudra/calculator.sh` -> `run_orca()`, right before `"$orca_bin" "$input_arg"`,
so blast radius = only Cloudra-launched ORCA jobs; rollback = delete the lines):
  export VECLIB_MAXIMUM_THREADS=1      # avoid Apple-Accelerate thread-pool interaction (harmless)
  export OMPI_MCA_btl=vader,self       # keep as-is; NEVER 'sm' (removed in OpenMPI 4.1.8)
(These do not demonstrably fix Symptom A; they remove whole classes of known macOS/OpenMPI foot-guns.)
STABILITY STRATEGY (the real fix for reliability):
  1. Treat Hessian-class jobs (Opt/Freq/OptTS/IRC/NEB) as "nproc=1 recommended". This is what the campaign already
     reverted to for HA1/NU3 TS work (saved inputs are `%pal nprocs 1`). Accept the speed loss.
  2. If nproc>1 is needed for speed, use **nproc<=4 only for SP/Opt**, and keep Hessian steps at 1, OR add an
     automatic retry ladder (4 -> 1) driven by LOG PARSING ("error termination", "Failed to read input file",
     missing "TERMINATED NORMALLY") — do NOT trust the exit code (ORCA returns 0 on sub-job error termination).
  3. Do not share one scratch directory between concurrent ORCA jobs (they overwrite <stem>.* files).
  4. Longer term: replace the build — official x86-64 ORCA under Rosetta (rosetta/oahd is available), or a clean
     arm64 build linked once against a single matching OpenMPI. Keep the serial path (works) and treat _mpi as
     suspect.
For batch throughput (18 cores): with Hessian jobs pinned to nproc=1, run ~8-10 concurrent single-core ORCA jobs
(leave ~2 cores for the monitors/UI). If you instead keep nproc=4, keep 2 concurrent jobs (as now) and rely on
log-parse + retry. Hard rule: total ORCA cores <= 16 to leave headroom.

## 8. Files / artifacts
- Probe scratch: /tmp/orca_mpi_probe/ (inputs: w_freq_np4.inp, ha1ts_freq_np{2,4}.inp, ha1_optfreq_np4.inp,
  naph_freq_np4.inp, scan_maxiter{,_np1}.inp, opt_maxiter.inp; results: matrix_results.csv, matrix_dir.csv,
  *.out). Workspace copy: gold_compute/campaign/_orca_env_probe/ (inputs + run_matrix*.sh + HANDOFF.md).
- Crash reports: ~/Library/Logs/DiagnosticReports/{orterun-2026-09-16-042641.ips, Retired/orca_*.ips, Retired/orterun-*.ips}.
- Constraint honoured: gold_compute/campaign/runs/NU3/** and jobs 416-421 were never touched; all probe processes cleaned.
