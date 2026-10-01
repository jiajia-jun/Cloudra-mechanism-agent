# HI1 minor — RECOVERY of interrupted job 65 (scan_minor_cont2)

**RECOVERY JOB = 66** (orca, paratera-cpu, local, 8 cpu / 13000 MB), submitted 2026-10-01.
  dir minor_spec/scan_minor_cont2/ ; inp scan_minor_cont2.inp ; log .cloudra/calc-66.out.log (on terminal).

## Why a recovery job (interruption reason)
- Job 65 (`scan_minor_cont`) and job 64 (major E2) and job 14 all ended at **exactly 2026-10-01T16:52:49**
  with NO "ORCA TERMINATED NORMALLY". Simultaneous mass termination = external kill (migration/funds
  pause), NOT an input/chemistry error (see HI1_gold_20260929/HANDOFF.md, major_spec/FAILURE_job64.md).
- Job 65 log ends abruptly mid-line "COSX-gradient ..." (killed inside an SCF gradient; SHARK scratch
  gpot*/grho*/orho* files were still being written at 16:50). No ORCA error-termination message.
- **Do NOT treat the interrupted step-2 (d=2.2) energy/coords as a completed scan point.**

## What job 65 actually completed (verified from the raw log)
grep of `scan_minor_cont/.cloudra/calc-65.out.log`:
- "RELAXED SURFACE SCAN STEP 1" (d=2.4): **CONVERGED** — log line 12943 "THE OPTIMIZATION HAS CONVERGED";
  E = -938.741304445329 Ha (line 2310..12730 final SPE); frame `scan_minor_cont.001.xyz`.
- "RELAXED SURFACE SCAN STEP 2" (d=2.2): **NOT converged** — 17 geometry cycles (lines 17050..33982),
  last SPE -938.733946206762 Ha, killed at cycle 18; NO converged marker. Only 1 of 5 scan points done.
=> job 65 completed ONLY the d=2.4 point. Unfinished: 2.2, 2.0, 1.8, 1.6.

## Starting geometry (last FULLY CONVERGED point)
- source: `minor_spec/scan_minor_cont/scan_minor_cont.001.xyz`  sha256 058015688f610137dae37c9a7240c9bf22003b6f28be2b611e34f1c332283cc5
- copy  : `minor_spec/scan_minor_cont2/scan_minor_cont2_start.xyz` (identical sha256)
- identity/geometry check by internal_coordinates: 41 atoms, 40 bonds, **3 FRAGMENTS**, rings only
  proline-5 (N4-C5-C6-C7-C8) + phenyl-6 (C30..C35); C8 = R; d(Ca-Cc)=d(C1-C29)=**2.400 A**;
  COOH proton intact (O11-H24 = 0.976 A); water 25-27 intact; no spurious ring/angle anomaly beyond the
  expected forming-contact. Equivalent to job59 frame 010 (E -938.7413226 vs -938.7413044, 0.011 kcal).
- NB: the OH...Od H-bond that oriented the aldehyde at large d has weakened/opened by d=2.4 (the aldehyde
  is now poised over the enamine face); dih Cb-Ca-Cc-Od = +48.5 deg. This is the natural approach geometry.

## Recovery input (same declared method; only the unfinished part)
- input: `minor_spec/scan_minor_cont2/scan_minor_cont2.inp`
- `! Opt B3LYP def2-SVP D3BJ def2/J RIJCOSX TightSCF CPCM(DMSO) SlowConv`  (identical keywords/口径)
- `%pal nprocs 8 end` ; `%maxcore 1536` ; **NO MaxIter / no self-set cap**
- `%geom Scan B 0 28 = 2.2, 1.6, 4`  (ORCA 0-based: atom0=Ca, atom28=Cc) -> points 2.2, 2.0, 1.8, 1.6
- start xyz = the d=2.4 converged frame above. Combined profile = job65 d=2.4 + this job 2.2..1.6.
- submission: orca, node paratera-cpu, local, async, cpus=8, memory_mb=13000 (== %pal 8 x %maxcore 1536).

## Provenance SHAs
- original input `scan_minor_cont/scan_minor_cont.inp`            sha256 2fff4be4f657ef000e1929ad971ba344d7378ddce2b5b6fcc035e658a530548a
- original log   `scan_minor_cont/.cloudra/calc-65.out.log`      sha256 f24b6177d562269c41e511b0d7b808324c94cad57d06e5093820180da1ac5c54
- start geometry `scan_minor_cont2/scan_minor_cont2_start.xyz`   sha256 058015688f610137dae37c9a7240c9bf22003b6f28be2b611e34f1c332283cc5
- Original 64/65 files left in place, unmodified, not overwritten.

## Acceptance criteria for this scan
- Energy must show a genuine internal maximum (rise then fall) over 2.4 -> 1.6 A. If monotonic or
  boundary-extremum, do NOT force a TS.
- A scan peak is only a SEED. Identity gate must pass before any unconstrained OptTS+Freq (+IRC/endpoints).
- References FIXED: common lowest RC = job 51 E=-938.760019066499. job54-51 = +2.254 kcal;
  job52-54 = +0.241; job52-51 = +2.495. Own-conformer (job54) is DIAGNOSTIC only.

## FALLBACK ROUTE (a2) — ORCA 2D relaxed scan mechanics (coordinator, evt_086875bad1704f79)
- ORCA %geom Scan SUPPORTS MULTIPLE coordinates = a true 2D relaxed scan: one "B i j = start, end, nsteps"
  line per coordinate inside a SINGLE Scan sub-block, close Scan with "end", close %geom with a second "end".
  Example (0-based, illustrative — remap via internal_coordinates and verify vs the input XYZ order):
      %geom
        Scan
          B 0 28 = 3.0, 1.6, 7
          B 22 26 = 1.6, 4.5, 6
        end
      end
  No agent-set MaxIter. Hand-verify the generated %geom block (writers have mangled scan/basis syntax before).
- For EM1 the coupled coordinate is d(Ca-Cc)=B 0 28 paired with the water/H-bond coordinate, e.g. d(H24...O28)
  or d(O11-H24) — pick from internal_coordinates on the actual minor frames and verify indices.
- Coordinator confirmed: the declared E2 product = iminium-alkoxide ZWITTERION with the carboxyl C(=O)O INTACT
  (CC(C[C@H]([O-])c1ccccc1)=[N+]1CCC[C@@H]1C(=O)O.O). So NO carboxyl-O-H -> aldehyde-O proton transfer is
  required; the water only mediates/H-bonds (consistent with frame-8 Oh-H intact 0.979).

## COORDINATOR DECISIONS (2026-10-01/02)
- Reconciled ledger: 0 running / 0 queued, 32 CPU / 56000 MB free, no live orca/xtb, before job 66.
- Coordinator APPROVED plan (a): let job 66 finish. Rationale: job 65's death = external mass kill (16:52:49,
  same instant as jobs 14/64), not chemistry; job 66 is the AUTHORIZED continuation of the unfinished part
  (2.2/2.0/1.8/1.6; d=2.4 NOT recomputed), and 2.4-1.6 is a CONTINUOUS minor stretch sitting in the real
  C-C bond-forming window (major analysis puts the true C-C crest at d~1.94, not the spurious 2.95 H-bond
  pre-reorganization crest). Disqualifier = H-bond REORGANIZATION discontinuity, not "1D" per se; the minor
  path has no such crest.
- On terminal: (a1) a CONTINUOUS constrained maximum at d~1.9-2.0 (no basin jump between consecutive points)
  IS an admissible minor SEED -> gate it (exactly 1 imag ALIGNED with Ca-Cc, watch_pairs=[[1,29]]; a
  minimum-like 0-negative-eigenvalue seed rejected, per the job-64 lesson) -> ONE OptTS+Freq (Calc_Hess,
  8 cpu, no MaxIter, same method/CPCM(DMSO), NEW dir). ASK coordinator before submitting.
  (a2) monotonic/boundary -> STOP the 1D route; use the coupled 2D relaxed scan d(Ca-Cc) x d(H24...O28) OR
  child A's verified major-face saddle + rigid aldehyde-face flip (validate with internal_coordinates).
- HARD RULE: never submit an OptTS or any second job without the coordinator's explicit go-ahead.
- Monitor "--timeout 1800" is a PLATFORM monitor parameter, uniform for all jobs, NOT a wall-clock cap
  (jobs 64 = 2h15m, 36 = 3h26m, 65 = 36.4 min all ran far beyond 1800 s under the same monitor).
  job 66 input carries NO agent MaxIter/MaxSteps/timeout (only ORCA's native scan-step default 123 cycles).
- job59 frame backups: scan_minor_cont2/job59_frames/scan_minor_clean.001..010.xyz retained.
