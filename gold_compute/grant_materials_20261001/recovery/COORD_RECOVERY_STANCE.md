# HI1 — COORDINATOR RECOVERY SCIENCE STANCE (2026-10-01, post power-cut resume)

Author: coordinator (owner of scientific review / comparison / resource coordination).
This file is coordinator-owned; branch files (major_spec/, minor_spec/) are NOT edited here.

## 1. LEDGER / PROCESS RECONCILIATION (anti-duplication, done before any submission)
- Compute queue: 0 running, 0 queued. Node paratera-cpu online, free 32 CPU / 56000 MB.
- ps: no orca/mpirun/xtb/crest process alive.
- jobs 64 / 65 / 14 all ended EXACTLY 2026-10-01T16:52:49 with no 'ORCA TERMINATED NORMALLY'
  => external kill (power/funds), NOT chemistry. job 14 is from the invalid geometry -> not recovered.
- Recovery runtime: /data/cloudra/runtime/recovery_20261001/runtime-v2.db (persistent, enabled);
  original API port 8420 untouched; recovery entry on 8422. Project prj_a15fc9525cbf4572.

## 2. VERIFIED EVIDENCE (coordinator re-checked this session)
- job 51 = COMMON LOWEST correct RC baseline. log_parser: normal=True, opt=True, 123 freqs, 0 imag,
  E = -938.760019066499 Ha. Gate PASS (3 fragments, rings only proline-5 + phenyl-6, Ca-Cc=4.354).
- job 54 = minor-face precomplex minimum, E = -938.756427155377 Ha, 0 imag. (+2.25397 kcal vs 51)
- job 52 = intermediate RC conformer, E = -938.75604349106 Ha, 0 imag. (+2.49472 kcal vs 51)
- RC ladder (kcal/mol vs 51): 51 = 0 (LOWEST) | 54 = +2.254 | 52 = +2.495. No third RC.
- Rejected / never reused: job 15 (-938.716973, wrong species), job 27 (not I2), job 45 (broken seed),
  job 36/50 (invalid). Old ORCA 5.0.2 energies: context only.

## 3. WHY THERE IS NO TS YET (job 64 deeper finding, coordinator-corroborated)
- job 64 (major E2 OptTS from major_spec/ts2_seed.xyz) was externally killed mid-optimization (cycle 95).
  INDEPENDENT of the kill it was ill-posed: cycle-1 exact Hessian had 0 NEGATIVE eigenvalues (log line 5801)
  => the seed is MINIMUM-like, not a saddle; the followed TS mode was a WATER O-H torsion (B(H26-O24)=0.50,
  D(H26,O24,O9,C8)=0.43), Ca-Cc carried no TS-mode component and moved AWAY (2.950 -> 3.540 A). 0 imag.
- Root cause: the 1D relaxed scan over d(Ca-Cc) (job 58) is DISCONTINUOUS — the O-H...O=C H-bond survives
  only while d(Ca-Cc) >= 2.95 A and BREAKS at d=2.61 A. The C-C formation is COUPLED to the proton
  transfer / H-bond, so the 1D crest (frame 5, d=2.95) is NOT the saddle.
- job 65 (minor continuation scan 2.4->1.6) reached step 1 (2.4 A, E=-938.7413) and was killed mid-step 2
  (~2.2 A, E=-938.7339); energy still RISING, no internal maximum yet. job 59 (6.0->2.4) monotonic, no peak.

## 4. RECOVERY SCIENCE REQUIREMENT (口径) — what 'necessary' means here
A. Deliverable unchanged: headline barriers vs RC51 for BOTH faces, each a VERIFIED first-order saddle:
   exactly 1 imaginary mode ALIGNED with Ca-Cc (watch_pairs=[[1,29]] 1-based) + IRC both directions +
   frequency-verified endpoint identities (0 imag). dE# = E(TS) - E(RC51); each channel's own IRC-returned
   reactant conformer reported as a DIAGNOSTIC only.
B. Seed rule: the recovery OptTS seed MUST be a genuine Ca-Cc saddle candidate. The killed 1D-scan crest
   is not one. Obtain the seed by ONE informative route only (pick the cheapest that works):
   (i) a 2D relaxed scan coupling d(Ca-Cc) with the proton-transfer / H-bond coordinate
       (e.g. d(H24...O28) or d(O11-H24)), so the path stays continuous; or
   (ii) interpolation between RC51 and a C-C-bonded estimate (job 58 frames 8/9) then relaxed refinement.
   FORBIDDEN: repeating the same 1D d(Ca-Cc) scan; long uninformative NEB; blind resubmission of the
   failing ts2_seed; opening a third common RC; recomputing any rejected job.
C. Budget / policy: one recovery seed step + one OptTS+Freq per face. New jobs 8 CPU; memory consistent
   with the input's own ledger (per-rank maxcore x nprocs). NO agent-set MaxIter/MaxSteps/timeouts.
   Method/graph/atom-map/CPCM(DMSO)/q0 m1/explicit water UNCHANGED.
D. Provenance + preservation: original job 64 / 65 inputs and geometries are NOT overwritten; recovery
   runs go in NEW dirs and carry source input SHA, seed-geometry SHA and the interruption reason.
   Reference SHAs (recorded now):
     job64 input  major_spec/ts2_orca6/ts2_np8.inp        sha256 4bc23077cbbaf9b3d5872aa4357b5932c00136974d8a5eb68a86b765e0ebacf9
     job64 seed   major_spec/ts2_seed.xyz                 sha256 8cb24ddd0e91025ebc73f632a9e046c51b2bfa7529e6d74d4fa5323fe16c2249
     job65 input  minor_spec/scan_minor_cont/scan_minor_cont.inp  sha256 2fff4be4f657ef000e1929ad971ba344d7378ddce2b5b6fcc035e658a530548a
     job65 seed   minor_spec/scan_minor_clean/scan_minor_clean.010.xyz  sha256 858435aaafb7d69f45406ba872d110f5eee2322ec9b14ba629c5638d27c7d3e5
E. Cross-channel efficiency: EM1 is the same C-C addition on the OPPOSITE aldehyde face of the same
   reactive complex. If the major-face saddle is obtained, the minor-face seed may be taken as its
   rigid aldehyde-face flip (validate with internal_coordinates) instead of a second independent scan.

## 5. ROLES
- child A (as_c627b84dbfa14bf7) = major/E2 channel, owns major_spec/.
- child B (as_ce8beb1a7405450f) = minor/EM1 channel, owns minor_spec/.
- Coordinator: independent review, comparison, resource coordination, final REPORT/HANDOFF. Does NOT
  submit for the children and does NOT edit branch files.


## 6. RECOVERY LOG (append-only)

- 2026-10-01 ~17:15 SUPERVISOR DIRECTIVE (binding): job 58 frame6 H-bond jumps to ~5.16 A => the 1D d(Ca-Cc)
  curve is DISCONTINUOUS; frame8 (=seed of job 67) must NOT be called a continuous-MEP barrier-top or gold;
  an internal energy peak alone does NOT prove a relevant TS. Job 67 = exploratory candidate. Terminal must
  prove the actual forming-bond/original-mechanism 1st-order saddle + IRC direction + correct covalent endpoints;
  if skeleton/face/proton path mismatches, HONESTLY REJECT. Forbid backfilling dE# with raw scan numbers and
  forbid unlimited same-type candidates.
- 2026-10-01: job 67 (major_spec/ts2_recovery/orca_ts/ts2r_major_np8.inp) RUNNING from 17:12:59, 8 MPI,
  maxcore1536, no MaxIter, OptTS calc_Hess. NOT killed/changed/resubmitted. Child A's README records frame8
  provenance (seed sha 6c924573...). Coordinator independent review of frame8: 2 fragments, rings only
  proline-5+phenyl-6, C1-C29=1.938 (elongated), face -21.1 deg (major, no flip), BUT carboxyl O-H swung away
  (H24...O28=5.192, O11...O28=5.078) and the WATER mediates (O10-H26=1.945, H27-O28=1.680), carboxyl proton
  NOT transferred => frame8's proton path is water-mediated; child A must state whether that is the declared E2.
- 2026-10-01 ~17:15: job 66 (minor_spec/scan_minor_cont2) SUBMITTED and RUNNING: minor-face relaxed scan
  B 0 28 = 2.2, 1.6, 4 (4 pts; d=2.4 NOT recomputed = not a repeat of job65 step1). Input has NO MaxIter/MaxSteps
  (complies); route/runtime monitor shows a --timeout 1800 wrapper (flagged; not an agent input cap; job not
  touched). Owner child B. Purpose: test for a GENUINE internal maximum in the C-C bond-forming window.
- 2026-10-01: major scan re-analysis (child A, accepted): the 1D d(Ca-Cc) profile has TWO features -- the 2.95 A
  crest is an H-bond-REORGANIZATION feature (carboxyl O-H hands the H-bond to the water), while the actual
  C-C formation barrier is at d~1.9-2.3 (constrained energies: 2.95 -938.750117 | 2.61 -938.754713 |
  2.28 -938.745329 | 1.94 -938.734979 | 1.60 -938.736002). E2 saddle = the LATTER. Constrained-scan image
  energies are DIAGNOSTIC ceilings, NOT dE#.
- Major recovery plan (approved): interpolate RC51 (job51_final.xyz) <-> scan_clean_np8.008.xyz (C-C bonded),
  relaxed refinement, barrier-top image as the Ca-Cc saddle seed, then ONE OptTS+Freq. Or a coupled 2D scan.
- Minor decision: let job 66 finish; if a genuine crest at ~1.9-2.0 -> OptTS seed; if monotonic -> coupled 2D
  scan OR child A's major saddle + rigid aldehyde-face flip. No OptTS without coordinator go-ahead.
- Cross-channel: child B requested child A's major-face saddle geometry (+log+SHA) when it exists, for the
  face-flip fallback; child B messaged child A directly. Coordinator endorses the share to avoid a duplicate scan.
- EVIDENCE PRESERVATION: scan_minor_clean frames 001-010 (.xyz/.gbw) verified ALL PRESENT now; transient
  delete/create churn observed but no loss. Backups: minor_spec/scan_minor_cont2/job59_frames/.

## 6. AMENDMENT (2026-10-01 eve) — 1D-scan crest INADMISSIBLE as a seed; use a continuous-path route
(coordinator-owned; supersedes the blanket reading of 4.B for the 'run vs seed' distinction)
- CONFIRMED (child A, job 64 reanalysis): the 1D relaxed scan over d(Ca-Cc) is DISCONTINUOUS, not merely
  noisy. In scan_clean (major) the carboxyl O-H donates to the aldehyde O while d(Ca-Cc) >= ~2.95 A; at
  ~2.61 A the H-bond REORGANIZES to the WATER and a SECOND barrier appears near d ~ 1.94-2.28 (water-bound
  C-C formation). The 'crest' at the reorganization distance is an artifact of the constraint, NOT the E2
  saddle. => No OptTS may be SEEDED from a 1D-scan crest. A 1D scan is at most a MAP of the pathway.
- DECISION: a 1D d(Ca-Cc) scan may be RUN to map the barrier region, but the resulting crest is a SEED
  CANDIDATE ONLY and carries NO saddle evidence; it must still pass the genuine-Ca-Cc-saddle identity gate
  (exactly 1 imaginary mode aligned with Ca-Cc, watch_pairs=[[1,29]] 1-based) before any acceptance.
- Admissible SEED routes: (i) 2D coupled relaxed scan (d(Ca-Cc) + the proton-transfer / H-bond coordinate);
  or (ii) interpolate RC51 <-> a C-C-bonded frame, relax, use the barrier-top image. Cross-channel
  preference (4.E): once ONE face's saddle is VERIFIED, the other face's seed is its rigid aldehyde-face
  flip (validate with internal_coordinates). ONE seed step + ONE OptTS+Freq per face. No second submission
  per face without coordinator notice. Method / graph / atom-map / CPCM(DMSO) / q0 m1 / explicit water
  UNCHANGED; no agent-set MaxIter.
- SCAN LEDGER: child B job 66 (minor 1D continuation 2.2->1.6, user-authorized) = the minor barrier-region
  MAP (new ground: the previously-unscanned 2.2-1.6 window is where the barrier lies); it is NOT a seed source.
- FILE-DELETION FLAG (child B): coordinator checked 2026-10-01 — no cron and no active deletion process;
  scan_minor_clean frames 001-010 are all PRESENT with intact sizes. Treat as unconfirmed; keep the
  job59_frames/ provenance copy and re-verify if it recurs.

### 6a. REFINEMENT (2026-10-01 eve, after child B rebuttal) — the disqualifier is the H-bond REORGANIZATION, not '1D' per se
- Child B (accepted): in the MINOR channel the acid-OH...Od H-bond opens EARLIER (H24...O28 > 2.6 A from d~2.8);
  job 59 shows NO 2.95-type crest; the 2.2-1.6 window (job 66) is therefore on a CONTINUOUS stretch of the
  minor path, and a constrained maximum there at d~1.9-2.0 would be a real Ca-Cc saddle candidate, not an artifact.
- CRITERION (supersedes the blanket wording of 6 for the seed decision): a constrained 1D-scan crest is an
  ADMISSIBLE SEED when the scanned window is CONTINUOUS (no H-bond reorganization / no basin jump between
  consecutive points) AND the crest passes the genuine-Ca-Cc-saddle identity gate (exactly 1 imaginary mode
  aligned with Ca-Cc, watch_pairs=[[1,29]]; a minimum-like seed with 0 negative eigenvalues is rejected, cf job 64).
  If the scan is monotonic or shows a basin jump, the crest is inadmissible -> route (i)/(ii) or the 4.E face-flip.
- EM1 PLAN (child B): (a) let job 66 finish; continuous crest ~1.9-2.0 -> gate -> ONE OptTS+Freq; (b) else fall
  back to the major-face saddle's rigid aldehyde-face flip. FALLBACK DEPENDENCY: child A shares the verified E2
  saddle geometry + log path + SHA with child B.

### 6b. CORRECTION recorded (2026-10-01 eve, child A) — the RC51->frame8 scan is NOT a continuous MEP
- job 58 switch frames 5->6: the H-bond NETWORK switches DISCONTINUOUSLY (H23...O27 1.893 -> 5.159 A; the
  water inserts and takes over the Od H-bond). Frames 6-9 are a DIFFERENT H-bonded state from the RC (1-5).
  => the frame-8 energy maximum is a CANDIDATE on the RC51 relaxed path, NOT a proven MEP barrier top.
- The earlier 'face continuous' shorthand meant the ALDEHYDE FACE ONLY (D(Cb-Ca-Cc-Od) 58.3 -> -36.3, no 180 flip).
- frame8 CANDIDATE justification (kept): same 3-molecule complex on the RC51 path; Ca-Cc forming (1.938 A,
  partial/elongated); rings only proline-5 + benzene; carboxyl O-H intact (no proton transfer); C8=R, C29=R;
  water retained + H-bonded. Coordinator re-verified via internal_coordinates.
- ACCEPTANCE unchanged and STRICT: accept ONLY on 1 imaginary mode aligned with Ca-Cc + bidirectional IRC to
  the correct covalent endpoints (frequency-verified 0-imag minima) + consistent skeleton/face/proton.
  Otherwise REJECT honestly — no backfill from the job-58 scan energies and no endless same-family candidates.
  If job 67 rejects, the next route is (i) a 2D coupled scan (C-C + H-bond/proton coordinate), coordinator-approved.

### 6c. STATUS checkpoint (2026-10-01 eve): job 67 first Hessian OK
- calc-67 cycle 1: 'Lowest eigenvalues of the Hessian: -0.026750432 ...' -> 1 NEGATIVE eigenvalue; TS mode is
  mode 0 (eigenvalue -0.02675043); internal-coordinate comp.(TS mode) = the single entry 30.B(C28,C0)=0.80,
  i.e. the Ca-Cc FORMING bond (0-based C0=Ca, C28=Cc). This is the mode job 64 wrongly followed as a water
  mode -> the route-(ii) seed is behaving as intended. Job continues; full acceptance (1 imag + IRC both ways
  + frequency-verified endpoints) still PENDING.
- FILE-CHURN NOTE (supersedes the 6 sentence above): authenticated as PLATFORM WORKSPACE RE-SYNC, not a local
  deletion: no cron/systemd-tmpfiles rule matches the workspace, no process holds cwd there, and scan_minor_clean
  inventory is STABLE (43 entries / 13 xyz) across a 12 s watch while originals remain readable. Treat the
  change-stream's 'deleted' reports as sync churn (atomic rewrite); keep independent backups of key frames.

