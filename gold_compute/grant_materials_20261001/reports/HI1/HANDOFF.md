# HI1 HANDOFF (paratera-cpu resume)

Working dir: /data/cloudra/workspace/hard_resume_20260930
Topic dir: HI1_gold_20260929 ; NEW jobs under HI1_gold_20260929/paratera_20260930/
Engine: ORCA 6.1.1 /opt/cloudra/software/orca-6.1.1 (xtb 6.7.1, CREST 3.0.2 available).
Node: paratera-cpu. Submission: submit_compute_job(job_type='orca', node_id='paratera-cpu', execution_backend='local').

## MPI STATUS (updated)
Root repaired MPI: full OpenMPI 4.1.8 with Fortran datatypes now at /opt/openmpi-4.1.8-full; the inherited
mpirun dispatches there. Earlier nprocs>=2 CPCM crashes (MPI_Type_match_size on INTEGER,8) are fixed.
NEW preference: productive ORCA jobs use cpus=8, memory_mb=14000, %pal nprocs 8, %maxcore 1500.
Existing serial jobs (below) finish as declared; do not resize/duplicate them.

## MODEL (unchanged)
41-atom RC = enamine(C=C(C)N1CCC[C@@H]1C(=O)O) + H2O + PhCHO, q0 m1, explicit water retained.
! B3LYP def2-SVP D3BJ def2/J RIJCOSX TightSCF CPCM(DMSO), Calc_Hess for TS.
0-based order (dft/rc/final.xyz): 0=Ca 1=Cb 3=N 7=Cring 8=Ccooh 9=OdO 10=Oh 23=OhH 24-26=water
27=Od 28=Cc 29-40=benzaldehyde. Reaction center (0,28); atom_map in ts/ts_0001/declare.json.

## INCIDENT / ENV NOTE (2026-10-01) — job 38 failed at start; retried as job 45
Job 38 (minor branch, READY) FAILED at start: the supervisor's in-place resource sync left the job
dir's .cloudra as root:root 0755, so the uid-998 compute executor could not write .cloudra/guard-38.log
(Errno 13). Child B recovered WITHOUT duplicating live work: renamed the root-owned .cloudra aside and
resubmitted the SAME current input (maxcore512, no MaxIter, constraint {B 0 28 4.2 C}) as JOB 45
(now RUNNING, 8 cpu / 5000 MB). Two-way audit: minor_spec/rc_minor_prep/.cloudra.pre_retry_root_owned/
and minor_spec/rc_minor_prep_audit_job38/. Decision: proceed with job 45 (do not re-run under 38).
REQUIREMENT (accepted): any future resource sync on a READY job must leave the job dir's .cloudra
created/chowned to uid 998 (the executor). Verified job 36's .cloudra is cloudra(998)-owned 0700 -> safe.

### Verified evidence so far (coordinator-checked)
- job 45 (minor rc_minor_prep, constrained Opt d(Ca-Cc)=4.2 A): normal, opt converged, E=-938.507655544 Ha
  (CONSTRAINED prep, not a reference minimum). log minor_spec/rc_minor_prep/.cloudra/calc-45.out.log;
  geometry minor_spec/rc_minor/rc_minor_prep_final.xyz. Child=B, verified by coordinator.
- job 50 (minor RC_minor Opt+Freq from that geometry): QUEUED, no MaxIter, nprocs8/maxcore512.

### job 27 (I2) VERIFIED — NOT the I2 adduct (reject as I2 evidence)
i2_min_np1/.cloudra/calc-27.out.log: normal, opt converged, 123 freqs, 0 imag, E=-938.752378808174 Ha.
internal_coordinates on i2_min_np1.xyz: 3 FRAGMENTS (enamine + water + benzaldehyde), rings only proline-5 +
phenyl-6 -> the C-C adduct did NOT form; it relaxed to a non-covalent complex 4.8 kcal ABOVE RC51.
=> job 27 is NOT usable as the HI1_I2 (iminium-aldolate) node. Affects only the later E3/hydrolysis edge
(secondary); does NOT block E2/EM1. If I2 is needed, build it deliberately (zwitterionic adduct does not
survive unconstrained relaxation from the MMFF seed). Recorded; child A notified.

## REFERENCE-STATE RULING (2026-10-01, human/supervisor)
COMMON LOWEST correct RC baseline = JOB 51, E=-938.760019066499 Ha (coordinator-verified: normal, opt
converged, 123 freqs, 0 imag; rc_clean_np8.xyz = Fragments: 3, rings ["5-membered ring: N4-C5-C6-C7-C8\n  6-membered ring: C30-C31-C32-C33-C34-C35  "], r(C1-C29)=4.354).
Use this SINGLE common baseline for the E2/EM1 barriers and the selectivity comparison. Each channel's own
IRC-returned conformer may be reported as a DIAGNOSTIC only (with the TaskSpec per-step wording). NEVER use
job 15 (rejected adduct) as reference. RC candidate ladder (kcal/mol vs job 51, x627.5095): 51 = 0 (lowest, -938.7600191); 54 = +2.254 (-938.7564272); 52 = +2.495 (-938.7560435); 52 is +0.241 above 54. Caveat any case where the IRC endpoints are a different species/conformer. No new jobs.

### job 54 VERIFIED (minor-face precomplex, gate PASS)
minor_spec/minor_rc/.cloudra/calc-54.out.log: normal, opt converged, 123 freqs, 0 imag, E=-938.756427155377 Ha.
internal_coordinates on minor_rc_opt.xyz: 3 fragments, rings only proline-5 + phenyl-6, Ca-Cc=7.346 A.
2.25 kcal/mol ABOVE job 51 (and 0.24 above job 52) -> distinct minor-face minimum, not a collapse. Child B approved to proceed to minor OptTS.
RC-REFERENCE RULING: report BOTH (a) per-spec: each dE# vs that step's own IRC-reactant conformer; (b) alternative:
both vs the common global-minimum precomplex. Note the 0.24 kcal shift; spread is reference-independent under a common reference.
### Minor RC (child B, job 54) + job 36 failed
- Literal 180-deg spin about Ca-Cc FAILS at the relaxed RC (Ca-Cc=6.8 A; phenyl sweeps through the
  carboxyl -> 31 bond anomalies) -> rejected. SUBSTITUTE: 180-deg rotation of the aldehyde about the
  O-H...O=C H-bond axis (Oh11...Od28); validated 3 fragments, rings only proline-5+phenyl-6, H-bond
  intact (1.696/2.677), 0 angle anomalies; face flipped (dih Cb-Ca-Cc-Od major -129.9 vs minor +116.1).
- job 54 = minor RC Opt+Freq (8cpu/4800MB/%maxcore512, no MaxIter) from
  minor_spec/minor_rc/minor_rc_seed_hbaxis.xyz. Caveat: may relax back to the common RC minimum ->
  acceptable (E2/EM1 share the RC frame; the minor channel is a TS-face distinction). Approved.
- job 36 FAILED (SHARK failed to read SHARKINP.tmp) — bad-seed job, already excluded; no action.
### job 52 VERIFIED (RC candidate B, gate PASS)
shared_rc/.cloudra/calc-52.out.log: normal, opt converged, 123 freqs, 0 imag, E=-938.75604349106 Ha.
My internal_coordinates on rc_shared_opt.xyz: 3 fragments, rings only proline-5 + phenyl-6, H-bond
present (H24...O28 1.696 1-based), Ca-Cc relaxed to 6.800 A (loose H-bonded complex). GATE PASSES.
COMMON E(RC) = min(E52, E51 once child A's job 51 completes + passes gate). Child B approved to proceed
with the minor channel. NOTE: job 52's E is ~0.039 Ha (24 kcal) BELOW the rejected adduct (job 15),
consistent with a genuinely different (non-covalent) species.
### job 15 terminal (REJECTED as gold)
rc_min_np1 done: ORCA TERMINATED NORMALLY, opt_converged=true, 0 imag, E=-938.716972775 Ha
(rc_min_np1/.cloudra/calc-15.out.log). This is a clean minimum of the WRONG species (started from the
invalid dft/rc/final.xyz with the covalent C8-O9-C28 ring) -> recorded as CONTEXT ONLY, never used for
dE#(E2). Child A notified.
## RC CANDIDATES RULING (2026-10-01) — two independent conformers, not duplicates
- job 51 major_spec/rc_clean_orca6 (child A): geometry major_spec/clean_rc.xyz; coordinator-validated:
  41 atoms, 40 bonds, 3 fragments, rings only proline-5 + phenyl-6, Ca-Cc=4.597.
- job 52 shared_rc (child B): seed shared_rc/rc_shared_seed.xyz; 3 fragments, rings only, H-bond
  OhH..Od=1.70, Ca-Cc=5.01.
RULING: two legitimate independent conformer minima of the same 3-molecule complex -> keep BOTH, cap at
two, NO third RC. COMMON E(RC) for E2 and EM1 = the LOWER electronic energy among candidates passing the
gate (3 fragments, H-bond present, no spurious ring, 0 imaginary); the other is a cross-check.
Jobs 14/15/36 (bad initial guesses) -> await terminal, do NOT claim valid gold, reject the wrong species.

## CLEAN RC (2026-10-01) — single shared reference, child B submits
Clean non-covalent 3-fragment RC candidate built by child B via conformer_search:
minor_spec/clean_rc_build3/guided_assembly/assembly/complex_candidate_000.xyz
Coordinator-validated: 41 atoms, 40 bonds, 3 FRAGMENTS, rings ONLY proline-5 + phenyl-6, H-bond
OhH..Od=1.698 present, Ca-Cc=5.01, no spurious ring. => GREEN-LIGHT.
DECISION: E2 and EM1 share the SAME reactant complex, so ONE shared clean-RC Opt+Freq is submitted by
child B into paratera_20260930/shared_rc/ (not duplicated by A). A adopts the shared E(RC) for dE#(E2).
INVALID (discard results, cannot cancel): job 50 (queued) and job 36 (minor scan) - both from the broken
seed build/xtbopt.xyz; jobs 14/15 provisional (started from invalid dft/rc/final.xyz).

## CRITICAL: dft/rc/final.xyz is NOT the RC (both channels affected)
Independent audit (coordinator): dft/rc/final.xyz = 41 atoms, 42 bonds, 2 FRAGMENTS, covalent 3-ring
C8-O9-C28; C8-C28=1.482, C8-O9=1.436, O9-C28=1.443, C8-O10=1.375, O27=C28=1.375; Ca-Cc(0-28)=4.698
non-bonded. C8 has 4 heavy bonds (no longer a carboxyl C); C28 has 4 heavy bonds (no H). => a covalent
carboxyl-aldehyde (oxirane-like) adduct, NOT the declared non-covalent HI1_I1 complex
(C=C(C)N1CCC[C@@H]1C(=O)O.O.O=Cc1ccccc1). The element/role map is fine; the GEOMETRY is wrong.
Consequences: (a) jobs 14 (scan) and 15 (RC Opt+Freq) start from this geometry -> their E(RC) is NOT a
valid E2 reference (mark PROVISIONAL); (b) the minor seed build/xtbopt.xyz inherited it (job 45 E=-938.508
is ~131 kcal high, dissociated). DECISION (same model/graph/method): build a CLEAN 3-molecule non-covalent
RC (enamine + water + benzaldehyde, H-bond + Burgi-Dunitz Ca-Cc 3.5-4.7 A) and validate with
internal_coordinates (3 fragments, no spurious rings, no heavy contact <2.5 A beyond the H-bond) before
any RC/TS job. Instructed children A (as_c627b84dbfa14bf7) and B (as_ce8beb1a7405450f) accordingly.
FLAGGED to the human for veto.

## CONNECTIVITY AUDIT (2026-10-01) — minor RC NOT verified (human-flagged)
internal_coordinates(analyze) on minor_spec/rc_minor/rc_minor_prep_final.xyz: 41 atoms, 40 bonds,
4 FRAGMENTS; perceived 4-membered ring C8-C30-C9-C35 + 8-membered ring; 9 angle anomalies
(C8-C30-C9=89.4 vs 120; C8-C35-C9=84.9 vs 109.5). Watched pairs all far: 4.066/3.183/2.985/2.812 A
(reproduces the human's corrected numbers). The SEED build/xtbopt.xyz shows the SAME spurious 4-ring
(+ C8-C34 close contact 2.535 A) => the flaw originates in the coordinator-built seed (over-constrained
xTB relaxation of the reoriented benzaldehyde), not in job 45.
Consequence: job 45/50 must NOT be called a verified RC. Child B instructed to (1) internal_coordinates
review of job 50 input/final geometry requiring 3 fragments + no spurious ring + no clash, and (2) if it
fails, re-derive the minor RC from dft/rc/final.xyz with a rigid benzaldehyde reorientation only, then
verify connectivity before any DFT. Normal termination != verified RC.

## POLICY (human, 2026-10-01) — production input budget
No agent-set iteration caps: inputs must NOT contain '%geom ... MaxIter N' (or any agent-chosen
iteration limit). The native software default governs; a job must never be ended by a timeout/limit
chosen by the agent. Do NOT raise MaxIter and rerun.
- job 36 (scan_minor_np8, READY/queued): legacy 'MaxIter 300' removed by coordinator -> ORCA default.
  Backup scan_minor_np8/.cloudra/job36-input-before-maxiter-edit.inp (sha256 783ac19...), audit
  .cloudra/job36-maxiter-edit.json. Resources (8cpu/14000MB/%maxcore1536) and model unchanged; NOT resubmitted.
- job 38 (minor branch, READY): MaxIter removed by its executor; supervisor synced to 8cpu/5000MB/%maxcore512.
- Running jobs 14/15/27 keep their declared inputs as-is (do not modify running jobs).

## DELEGATED EXECUTION (coordinator -> specialists, 2026-09-30)
I own scientific review, cross-channel comparison, graph-ambiguity escalation, resource coordination and
final REPORT/HANDOFF. Execution of the two channels is delegated to two small_mol specialists
(non-overlapping ownership, separate output dirs). Children adopt existing jobs (never resubmit):
- child A (major/E2 channel): session as_c627b84dbfa14bf7 (agent small_mol)
  owns jobs 15 (RC Opt+Freq), 14 (major scan), 27 (I2) + follow-up OptTS/Freq/IRC in
  paratera_20260930/major_spec/  -> deliverable E(RC), E(TS2), IRC verdict, dE#(E2).
- child B (minor/EM1 channel): session as_ce8beb1a7405450f (agent small_mol)
  owns job 36 (minor scan, queued) + minor RC_minor Opt+Freq + OptTS/Freq/IRC in
  paratera_20260930/minor_spec/  -> deliverable E(RC_minor), E(TSM1), dE#(EM1).
Both share the 32CPU/56000MB pool; at most one 8-core active job per branch; extra work queues.
Coordinator verifies their manifests/logs before accepting any chemical conclusion.

## RUNNING (ORCA 6.1.1, serial, finish as declared)
- job 36 scan_minor_np8 : minor-channel relaxed scan d(Ca-Cc)=3.4->1.6 (6 pts), 8-core config (cpus=8/%pal nprocs 8/%maxcore 1500) -- QUEUED (needs 14000 MB; pool had ~5200 MB free)
- job 14 scan_major_np1 : relaxed scan d(Ca0-Cc28)=4.5->1.6 (8 pts)  [~1 scan step done]
- job 15 rc_min_np1    : RC Opt+Freq  (E so far ~ -938.71593 Ha)
- job 27 i2_min_np1    : I2 (iminium-aldolate + water) Opt+Freq
Old attempted jobs (do NOT resubmit): 650 (RC, done), 651 (bad OptTS), 685 (scan, artifacts lost);
new-server failed MPI jobs 5/6/7/8 (diagnostics only).

## MINOR-FACE (EM1) — seed NOW BUILT (audit resolution)
Audit of the earlier zero-placement result: it was an over-rigid placement assumption (the aldehyde O
forced exactly on the carboxyl O-H ray), NOT search exhaustion and NOT evidence the minor TS cannot
exist. Chemically the two Houk-List chair TSs share the same H-bond but differ in the aldehyde
prochiral face; the working construction is therefore a rigid 180-deg rotation of the benzaldehyde
about the forming Ca...Cc axis of the major RC (keeps d(Ca-Cc), flips the aldehyde H/Ph -> diastereomer),
followed by a cheap constrained xTB (GFN2/ALPB-DMSO) relaxation.
Result (HI1_gold_20260929/build/twoface_rot180.xyz -> xtbopt.xyz):
  d(Ca-Cc)=2.89 A, dih(Cb-Ca-Cc-Od)=-137 deg (major +82 deg -> opposite orientation),
  O-H...O=C H-bond intact: d(Oh..Od)=2.72, d(H..Od)=1.90, angle 137 deg. xTB E=-61.7713 Ha (context).
=> submitted job 36 = ORCA 6.1.1 minor-channel relaxed scan d(Ca-Cc)=3.4->1.6 (6 pts), 8 cores.

## NEXT STEPS
1. On job14 completion: log_parser(properties=['scan','energy']) -> highest converged frame ->
   OptTS+Freq (Calc_Hess true) at cpus=8/mem=14000/nprocs8 -> confirm 1 imag on the C-C mode.
2. IRC both ways -> re-opt/freq endpoints -> dE#(E2)=E(TS)-E(RC), all at ORCA 6.1.1.
3. Minor face EM1: resolve preorganization (ts_prepare / longer CREST) before any TS work.
4. Also queued: job 27 I2 intermediate. Keep REPORT.md/progress.md current.

========================================================================
## MIGRATION / RESUME PACKET (2026-10-01) — COMPUTE PAUSED (funds/migration)
No new QM/continuation may be submitted. Running jobs 14/64/65 keep inputs, are not killed. On their
terminal state ONLY parse existing results; no follow-ups.

### MODEL / ENVIRONMENT (unchanged; keep exactly)
HI1 = (S)-proline aldol (acetone + benzaldehyde). Resumed object = enamine(C=C(C)N1CCC[C@@H]1C(=O)O) +
H2O + PhCHO, 41 atoms, q=0 m=1, explicit water retained.
Method: ! Opt/OptTS b3lyp def2-SVP D3BJ def2/J RIJCOSX TightSCF CPCM(DMSO).
Engine: ORCA 6.1.1 /opt/cloudra/software/orca-6.1.1 ; node paratera-cpu (LOCAL backend).
Submit: submit_compute_job(job_type='orca', node_id='paratera-cpu', execution_backend='local', is_async=true);
useful jobs cpus=8, memory_mb=14000, %pal nprocs 8, %maxcore 1500. POLICY: NO agent-set MaxIter anywhere.
Atom order (0-based): 0=Ca 1=Cb 3=N 7=Cring 8=Ccooh 9=OdO 10=Oh 23=OhH 24-26=water 27=Od 28=Cc 29-40=phenyl.
Reaction center (0,28) = 1-based (1,29). Atom map: ts/ts_0001/declare.json.
NOTE (old server): ORCA 5.0.2 energies are CONTEXT ONLY; never subtract across versions.

### VERIFIED EVIDENCE (ORCA 6.1.1, coordinator-checked)
- job 51 = COMMON LOWEST correct RC baseline. major_spec/rc_clean_orca6/
  E=-938.760019066499 Ha ; 0 imag ; gate PASS (3 fragments, rings only proline-5 + phenyl-6, Ca-Cc=4.354 A).
  log major_spec/rc_clean_orca6/.cloudra/calc-51.out.log ; geom rc_clean_np8.xyz
- job 54 = minor-face precomplex minimum. minor_spec/minor_rc/
  E=-938.756427155377 Ha ; 0 imag ; gate PASS (3 frag, rings only, Ca-Cc=7.346). +2.254 kcal vs job51.
- job 52 = intermediate RC conformer. shared_rc/
  E=-938.75604349106 Ha ; 0 imag ; gate PASS (Ca-Cc=6.800). +2.495 kcal vs job51 (+0.241 vs job54).
- RC ladder (kcal/mol vs job51): 51 = 0 (LOWEST) ; 54 = +2.254 ; 52 = +2.495.

### REJECTED / INVALID (do NOT reuse as evidence)
- dft/rc/final.xyz : NOT the RC — covalent 3-membered ring C8-O9-C28 (C8-C28=1.482, C8-O9=1.436,
  O9-C28=1.443, C8-O10=1.375); 2 fragments. (Also dft/rc/rc.xyz.)
- job 15 rc_min_np1 : minimum of that WRONG species, E=-938.716972775 Ha, 0 imag -> context only.
- job 27 i2_min_np1 : NOT the iminium-aldolate I2 (3 fragments, no C-C bond), E=-938.752378808 Ha.
- job 45 minor rc_minor_prep : dissociated/broken seed, E=-938.507655544 Ha.
- build/xtbopt.xyz / twoface seeds : broken (spurious 4-ring / clash).
- job 36 scan_minor_np8 : FAILED (SHARK input read) ; job 50 : user-cancelled.
- jobs 5/6/7/8 : CPCM+MPI (nprocs>1) diagnostics — old broken MPI (now repaired).
- job 14 scan_major_np1 : started from the invalid dft/rc/final.xyz -> its profile is NOT usable for E2.

### SCAN STATUS
- job 59 minor_spec/scan_minor_clean (6.0->2.4 A, d(Ca-Cc), 12-pt plan): steps 1-10 completed, MONOTONIC rise
  after a shallow 5.2 A constrained minimum, NO internal peak -> no TS seed; FAILED ~2.0 A (SHARK/tmp).
- job 65 minor_spec/scan_minor_cont (2.4->1.6 A, 5 pts, SlowConv, maxcore1536): RUNNING. No new continuation beyond it.
- job 64 major_spec/ts2_orca6 (OptTS+Freq from the clean major scan peak): RUNNING.

### UN-VERIFIED / REMAINING (what migration must resume)
1. E2 (major): valid TS2 (exactly 1 imag aligned Ca-Cc [[1,29]]) + IRC both ways + endpoint re-opt/freq,
   then dE#(E2)=E(TS2)-E(RC51) (headline) + own-conformer diagnostic.
2. EM1 (minor): same, from the minor-face scan peak (needs job 65 to show a peak, else re-scan the TS region).
3. I2/E3 (secondary): the iminium-aldolate I2 does NOT survive unconstrained relaxation from the MMFF seed;
   needs a deliberate zwitterion-aware build.
4. mechanism_graph.json + REPORT.md declarations (edges E1/E2/E3/EM1, barriers vs RC51, channel/favored).

### RESUME PATHS (all under /data/cloudra/workspace/hard_resume_20260930)
HI1_gold_20260929/{HANDOFF.md, REPORT.md, progress.md, _src/, ts/ts_0001/}
HI1_gold_20260929/paratera_20260930/{major_spec/, minor_spec/, shared_rc/, scan_major_np1/, rc_min_np1/,
  i2_min_np1/, scan_minor_np8/}
Clean-RC seeds: major_spec/clean_rc.xyz ; major_spec/rc_clean_orca6/rc_clean_np8.xyz (job51 opt) ;
  minor_spec/clean_rc_build3/guided_assembly/assembly/complex_candidate_000.xyz ; minor_spec/minor_rc/minor_rc_opt.xyz.
=======================================================================

