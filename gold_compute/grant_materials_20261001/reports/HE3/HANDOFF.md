# HE3 HANDOFF

## Goal
Hard gold backfill HE3: simplified (S)-CBS-catalyzed acetophenone reduction by BH3.
Two enantioselective hydride-delivery channels (Si favored -> (R); Re minor -> (S)).
Deliverable: ORCA 5.0.2 B3LYP-D3BJ/def2-SVP CPCM(THF) electronic barriers dE# = E(TS)-E(RC),
each with a normal unconstrained TS (exactly 1 relevant imag), IRC both ways, optimized endpoints,
RC minimum validated. mechanism_graph.json per HE3 TaskSpec shape.

## TaskSpec source
/public/home/yyywaa/cloudra/ideapool/tasks/hard/HE3.json  (tier hard, family E)
Allowed methods: xtb / pm7 / b3lyp/def2svp. Only ORCA/Gaussian logs scorable.
Conditions: THF, -20C to rt, catalytic (S)-oxazaborolidine + BH3.

## Atom map (1-based, TaskSpec atom-mapped reactant SMILES)
1=B(borane) 2=H(hydride) 3=CH3 4=C(carbonyl) 5=O(carbonyl) 6..11=phenyl
12=CH3(C5) 13=C@H(C5) 14=CH2(C4) 15=O(ring) 16=B(catalyst) 17=N(ring)
Gold bond_changes E1/EM1: break [1,2],[4,5]; form [1,5],[2,4].
Mechanism: BH3 N-coordinated; ketone B(cat)-coordinated; six-membered chair TS
B5-O5-C4-H2-B16-N15 (built 1-based index map below).

## Built 35-atom RC order (HE3_gold_20260929/build/rcv2_art/prepared.xyz)
1=C(CH3,C5) 2=C13 3=C14 4=O15 5=B16(catalyst B) 6=O5 7=C4(carbonyl C) 8=C3(methyl)
9-14=phenyl C 15=N17 16=B1(borane B); H: 17-19(C1) 20(C2) 21-22(C3) 23-25(C8)
26-30(phenyl) 31(N17-H) 32(B16-H) 33,34,35(B1-H3). Transferring hydride = H34.

## WARNING (fixed bug)
First RC SMILES omitted the catalyst B-H (must be [BH-], not [B-]): gave wrong formula
C11H18B2NO2 and nonsense energetics. Corrected RC C11H19B2NO2 build E(xTB)=-46.8585 Eh,
27.3 kcal below separated reactants. Reference xTB (GFN2/ALPB-THF): catalyst -18.810910,
acetophenone -25.261122, BH3 -2.742955, alkoxyborane(C[C@@H](O[BH2])c1ccccc1) -28.085691.

## Environment / route
ts_prepare BUILD FAILS for this B system (MMFF94 cannot construct assembled complex; ts_0001
blocked assembly_failed). => MANUAL CHAIN (documented). ORCA !XTB broken; CREST absent;
standalone xtb v6.7.1 works. ORCA 5.0.2 at /public/software/apps/orca/5.0.2/.../orca.
Slurm via submit_compute_job (cpus=4, memory_mb=14000, is_async=true). Max 5 concurrent HE3 jobs.

## Jobs
- 598 HE3_RC_optfreq (Opt Freq, B3LYP-D3BJ/def2-SVP CPCM(THF) TightSCF def2/J RIJCOSX) [running]
- 599 HE3_TS_A_optfreq (OptTS Freq + Calc_Hess) from xTB seed distBC/opt_3.100.xyz [running]

## xTB exploration (GFN2/ALPB-THF, exploratory seeds only)
- RC open minimum: rcv2/xtbopt.xyz  E=-46.8585; angle C4-N15-B16=116 deg (BH3 points away).
- Forcing angle C4-N15-B16 down BREAKS the catalyst B5-N15 ring (artifact; not usable).
- Scanning d(B16-C4) from 4.6->2.5 A: smooth rise 0->16.5 kcal; at 3.1 A the geometry has
  B5-N15 intact (1.58), B16-H34=1.23, C4-H34=2.25 -> used as TS-A seed (opt_3.100.xyz).
  Below ~2.8 A the catalyst B5-N15 stretches (decomposition) => hand off to DFT.
- Channel B: ketone rotated 180 deg about O5-B5 (build/RC_B_rot.xyz), xTB opt E=-46.8555;
  scanning d(B16-C4) for its TS seed (xtb/distBC_B).

## Next steps
1. Read job 598/599 results; log_parser for convergence + imag freqs.
2. If TS-A has exactly 1 relevant imag -> IRC both ways -> re-opt endpoints -> dE#.
3. Channel B: get seed, OptTS+freq, IRC, endpoints, dE#.
4. Minimal-pair test the two RCs at DFT; build mechanism_graph.json; REPORT.md.
5. Update source + TaskSpec; tests; push.

## Constraints (do not change without asking user)
mechanism graph / solvent (THF) / reference state / method / acceptance / node config.
## UPDATE 2026-09-29 ~07:55 (jobs 598-601 done; scans 612/613 running)
### 598-601 results (log_parser)
- 598 RC_A opt+freq: normal, converged, 0 imag -> minimum; E=-684.744885326 (geom orca/geom/rcA.xyz).
- 599 TS_A opt+freq: normal, converged, 1 imag = -104.01 cm-1 BUT the mode is a phenyl/methyl torsion
  (heavy_atom_fraction 0.004; C4-H34 contribution 2.5%). NOT the hydride-transfer TS. E=-684.743219773.
- 600 TS_B opt+freq: normal, converged, 1 imag = -83.11 cm-1, same torsional character. E=-684.743131966.
- 601 RC_B opt+freq: normal, converged, 0 imag -> minimum; E=-684.743432825.
- Geometry check (DFT): rcA B16-C4=4.70; tsA B16-C4=4.08; rcB B16-C4=4.06; tsB B16-C4=4.01.
  => OptTS from the xTB d(B16-C4)=3.1 seeds relaxed AWAY to torsional saddles; the hydride never left B16.
  DIAGNOSIS: the xTB-3.1 seed is not on the DFT hydride-transfer valley; a torsional saddle is nearby.

### 612/613 DFT relaxed scans (running; ~15 min/point)
- 612 scan d(C4-H34): 'Scan B 6 33 = 4.2, 1.0, 12'. Partial: 4.2=-684.744803; 3.909=-684.743892;
  3.618=-684.741944. Rising (barrier forming).
- 613 scan d(B16-C4): 'Scan B 15 6 = 4.7, 2.4, 9'. Partial: 4.7=-684.744886; 4.4125=-684.743646;
  4.125=-684.743357. Rising.
- Plan: on completion, take the max-energy converged point as TS seed -> new OptTS+freq -> IRC.

### Scientific-failure diagnosis
The catalyst B5-N15 ring did NOT break in the DFT OptTS jobs (B5-N15 stays ~1.6 A); the failure is that
OptTS found a low-mode torsional saddle instead of the hydride-transfer saddle. No ring-breaking at DFT.
## UPDATE ~08:55 (NEB-TS route added)
- 612/613 ORCA relaxed scans still running (~2h, ~20-25 min/point; partial profiles oscillate ~0-2 kcal
  at d(C4-H34)=3.0-4.2 and d(B16-C4)=3.8-4.7 -> the low-d barrier region is still not reached).
- Product endpoint built (constrained xTB from DFT rcA, same atom order); free xTB product
  E=-46.9044, connectivity: B16-O5 1.31, C4-H34 1.10, B5-O5 3.97, N15-B16 3.77 (catalyst separated).
- 619 HE3_PROD_optfreq: DFT optimize the product endpoint.
- 620 HE3_NEB_A: ORCA NEB-TS (8 images, IDPP) from DFT rcA.xyz to the product; the standard
  route to the saddle. Syntax copied from working M8/G2/NY3 NEB inputs.
- On NEB completion: read the TS candidate -> OptTS+freq -> IRC both ways -> barriers.
- Do NOT resubmit 598-601.
## NEB-TS initial IDPP path check (~09:05)
The 10-image IDPP path RC->P (HE3_NEB_A_initial_path_trj.xyz) evolves smoothly through the intended
chemistry (indices 0-based: B16=15, C4=6, O5=5, N15=14, B5=4, H34=33):
  img0  B5O5=1.60 B5N15=1.57 N15B16=1.61 C4O5=1.26 B16C4=4.70 C4H34=4.35 B16H34=1.24 B16O5=3.50
  img9  B5O5=3.97 B5N15=1.39 N15B16=3.77 C4O5=1.42 B16C4=2.43 C4H34=1.10 B16H34=2.54 B16O5=1.31
=> hydride transfer + B16 migration N->O5 + catalyst decomplexation, i.e. the gold bond_changes
break [B-H],[C=O pi]; form [B-O],[C-H]. Reaction coordinate confirmed.

### Running jobs: 612 (scan d(C4-H34)), 613 (scan d(B16-C4)), 619 (PROD opt+freq), 620 (NEB-TS).
## UPDATE ~09:40 (job 619 product done)
- 619 HE3_PROD_optfreq: normal, converged, 99 freqs, 0 imag -> VALID product minimum.
  E=-684.771345140. Formula C11H19B2NO2. 16.6 kcal below RC_A (-684.744885).
  Connectivity (prodA.xyz): B16-O5=1.35, C4-O5=1.43, C4-H34=1.10 (hydride ON C4),
  B16-H33/H35=1.21 (BH2), B5-N15=1.40 (catalyst ring intact), B5-H=1.20, N15-H=1.01,
  B5-O5=4.05 and B16-N15=3.99 (dissociated). => catalyst regenerated + alkoxyborane = gold product.
  NOTE on built H order: 0-based 22=B5-H, 31=N15-H, 32/33/34=B16-H3 (transferring = 0-based 33).
- 612 scanC4H profile so far (constrained d(C4-H34)):
  d=4.2 0.00 | 3.91 0.57 | 3.62 1.79 | 3.33 0.74 | 3.04 1.32 | 2.75 2.38 | 2.46 4.05 |
  2.16 5.39 | 1.87 7.53 | 1.58 7.59 kcal (points 11-12 pending). The single H coordinate does NOT
  allow the boron-swap rearrangement to relax, so this is not the correct overall coordinate; NEB-TS
  (620) is the reliable route.
- 620 NEB-TS running: iteration 6; initial barrier estimate 0.176 Eh (unrelaxed IDPP); energy at image6
  still high -> must wait for CI-NEB convergence (barrier must fall).
## UPDATE ~09:50 (parallel channel-B NEB launched)
Running HE3 jobs: 612 scanC4H, 613 scanBC, 620 NEB-TS channel A, 622 NEB-TS channel B (ketone flipped).
- 622 NEB-TS: reactant rcB.xyz (DFT min, job 601, E=-684.743433) -> product xtb/prodDFT_B/free_opt.xyz
  (B16-O5 1.31, C4-H34 1.10, catalyst separated). Channel-B enantiomeric product.

### Post-NEB workflow (prepared; run when 620/622 converge)
1. Take HE3_NEB_{A,B}_NEB-TS_converged.xyz (or NEB-CI_converged.xyz) as the TS candidate.
2. Re-run OptTS+Freq with gold settings (B3LYP D3BJ def2-SVP def2/J RIJCOSX CPCM(THF) TightSCF
   + %geom Calc_Hess true) to confirm exactly 1 imaginary mode on the hydride-transfer coordinate.
3. IRC both directions (Extrema / MaxIter by remaining uncertainty), then re-optimise both outer frames
   to minima; require 0 imag and correct identities (RC = ternary complex; product = alkoxyborane +
   catalyst). NOTE: two product minima possible (channels differ at C4 stereo).
4. dE# = E(TS) - E(RC) at this level; declare on the channel edges; record the difference.

### Confirmed DFT energies (Hartree)
- RC_A (598) -684.744885326 (0 imag)
- RC_B (601) -684.743432825 (0 imag)
- PROD_A (619) -684.771345140 (0 imag; alkoxyborane + regenerated catalyst)
- (transient) TS_A(599)/TS_B(600) were TORSIONAL saddles, discarded.
## UPDATE (NEB timeout; ~24h elapsed)
- 620/622 NEB-TS FAILED: Slurm walltime limit ('CANCELLED DUE TO TIME LIMIT'). The wrapper's walltime is
  ~24h; 8-image DFT NEB needs far more. NEB is NOT viable at this level for this system.
- NEB-A reached iteration 72 (climbing image on); best barrier estimate 0.0674 Eh (~42 kcal) at image 3,
  still NOT converged (perp forces ~0.02-0.05). NEB-A MEP max image (im3) has B5-O5=2.50, N15-B16=2.96,
  B16-C4=4.40, C4-H34=3.53 -> the high point is a coordination/reorganisation shoulder (B16-N15 and
  B5-O5 stretched), NOT the hydride transfer. This is likely an artefact of the fully-separated product
  endpoint; the true elementary hydride transfer may be lower and occur with the six-membered ring.
- 612 scanC4H COMPLETE (12 pts). Relative to the d=4.2 start: rises ~ +7.6 kcal at d=1.58 then collapses
  (d=1.29 -> -17.9, d=1.0 -> -21.9) to the rearranged product. Noisy (dip at d=3.33).
- 613 scanBC COMPLETE (9 pts): noisy (min at d=2.91 then up).

### New jobs (concurrency <=5)
- 667 OptTS+freq from scanC4H peak frame (d=1.58 A; HE3_scan_C4H.010.xyz).
- 668 OptTS+freq from NEB-A MEP image 7 (HE3_NEB_A_im7.xyz; mid-transfer).
Goal: obtain ONE first-order saddle whose imaginary mode is the C4-H34/B16-H34 hydride transfer.
On success: IRC both ways -> re-opt outer frames -> dE# = E(TS)-E(RC_A). Then channel B.
## UPDATE (TS found!)
### job 667 -> genuine hydride-transfer TS (channel from RC_A)
- HE3_tsA_seed_scan OptTS+freq: normal, CONVERGED, 98 freqs, exactly 1 imag = -415.08 cm-1.
  Imaginary mode dominated by the C4-H34 pair (watch projection 7-34 = 0.912; 16-34 = 0.293;
  heavy-atom fraction 0.094) => it IS the hydride transfer.
- Geometry (geom/tsA667.xyz): B5-O5=1.52, B5-N15=1.60, N15-B16=1.55 (catalyst + amine-borane INTACT),
  C4-O5=1.29, B16-C4=2.81, C4-H34=1.71, B16-H34=1.30 -> classic six-membered CBS chair TS.
- E(TS667) = -684.731935339  vs E(RC_A) = -684.744885326
  => dE# = 0.012949988 Eh = 8.13 kcal/mol (provisional; pending IRC endpoint identity).

### job 668 failed (OptTS from NEB image 7 did not converge, max cycles) - discarded.
### NEB 620/622: both reached ~iter 60-72, barrier estimate ~0.070 Eh (~44 kcal) image 3, NOT converged;
    the high point is a dative-bond-reorganisation shoulder (B5-O5 / N15-B16 stretched), i.e. NEB is
    tracing the dissociative route, not the low hydride-transfer route. NOT used for any number.

### Running: 684 HE3_IRC_A (from TS667, InitHess default) ; 686 HE3_tsB_seed (OptTS, ketone-flipped seed).
Next: IRC-A endpoints -> confirm RC identity + product enantiomer (channel assignment Si/Re);
then channel-B TS dE#; then declare barriers.

## UPDATE 2026-09-30 (paratera-cpu, ORCA 6.1.1) — new server resume
Engine provenance: OLD campaign = ORCA 5.0.2 (retired Slurm). NEW jobs = ORCA 6.1.1 at
/opt/cloudra/software/orca-6.1.1. Never mix energies across versions. Old energies = context only.
New subdir: HE3_gold_20260929/paratera_20260930/ (does not overwrite old evidence).
Budget per topic: 2 active jobs, cpus=4, memory_mb=7000, %pal nprocs 4, %maxcore 1536 (~6GB).

### Submitted (ORCA 6.1.1, B3LYP-D3BJ/def2-SVP def2/J RIJCOSX CPCM(THF) TightSCF)
- job 1 HE3_tsA_ORCA6: OptTS+Freq from geom/tsA667.xyz (genuine ORCA5 hydride TS, -415 cm-1)
- job 2 HE3_tsB_ORCA6: OptTS+Freq from geom/tsB_seed.xyz (ketone-flipped channel-B seed)
Prepared (not yet submitted, pending free slot): rcA_ref, rcB_ref (Opt+Freq new-version references).

### BLOCKER: ORCA 6.1.1 CPCM + MPI crashes
Jobs 1 & 2 FAILED in LEANSCF at "Performing Cholesky decomposition & store" (CPCM surface setup):
MPI_Type_match_size -> MPI_ERR_ARG. Same failure in HI1 CPCM(DMSO) jobs (calc-5/6). HG2 solvent-free
jobs run FINE. => CPCM/CPSCF parallel path in this ORCA6 build is broken, not our input.
System mpirun OpenMPI 4.1.8 (/opt/openmpi-4.1.8); ORCA links libmpi.so.40 -> 4.1.8.
Diagnostics running: job 11 (water CPCM(THF) SP nprocs 1), job 12 (same nprocs 4).
If np1 works -> run CPCM jobs at nprocs 1 (slow) until env fixes MPI; else need OpenMPI 5 / ORCA rebuild.
Posted to agent_hub for env + other topics.

## UPDATE 2026-09-30 ~23:20 (WORKAROUND FOUND: CPCM needs nprocs=1)
Diagnosis complete (minimal):
- ORCA 6.1.1 CPCM surface "Cholesky decomposition & store" crashes with MPI_Type_match_size ONLY when
  nprocs>1 AND the cavity is large. Measured: acetone (984 surface pts) np4 = OK; HE3 35-atom system
  (2840 pts) np1 = OK, np4 = CRASH (jobs 1,2). Confirm np2 with job 18 (pending).
- => WORKAROUND = run all CPCM(THF) HE3 jobs at %pal nprocs 1 (see HI1 which also created *_np1 variants).
- System mpirun = OpenMPI 4.1.8 (/opt/openmpi-4.1.8); ORCA links libmpi.so.40->4.1.8. Env fix (OpenMPI 5
  or ORCA build matched to MPI) needed to recover 4-core CPCM.

### SUBMITTED (ORCA 6.1.1, B3LYP-D3BJ/def2-SVP def2/J RIJCOSX CPCM(THF) TightSCF, nprocs=1)
- job 13 _diag_real_np1: SP rcA np1 (diagnostic; CPCM passed, SCF running) [confirmed np1 works]
- job 18 _diag_real_np2: SP rcA np2 (diagnostic, pending)
- job 23 tsA_ORCA6_np1 : OptTS+Freq from geom/tsA667.xyz  (genuine -415 cm-1 hydride TS, channel Si)
- job 24 tsB_ORCA6_np1 : OptTS+Freq from geom/tsB_seed.xyz (ketone-flipped channel-B/Re seed)
- job 25 rcA_ref_np1   : Opt+Freq rcA.xyz  -> new-version E(RC_A)
- job 26 rcB_ref_np1   : Opt+Freq rcB.xyz  -> new-version E(RC_B)
FAILED (np4, must not retry): jobs 1 (tsA_ORCA6), 2 (tsB_ORCA6).
Next: on each terminal -> log_parser (convergence, imag freqs). If TS_A/B give exactly 1 hydride imag
-> IRC both ways (np1) -> endpoint Opt/Freq -> dE#=E(TS)-E(RC) at ORCA6.1.1 only. Never mix ORCA5 energies.

## UPDATE 2026-09-30 ~23:45 (root cause confirmed by root; np2 also fails)
- np2 also FAILS (job 18) => any nprocs>1 crashes for the large cavity. ROOT CAUSE (from root): the
  installed OpenMPI 4.1.8 build lacks the Fortran INTEGER/COMPLEX predefined datatypes, so
  MPI_Type_match_size(INTEGER,8) returns MPI_ERR_ARG in the CPCM surface Cholesky. Root is building a
  full Fortran-enabled MPI at a separate prefix (existing jobs untouched). Await "repair-ready".
- DIRECTIVE: no more MPI diagnostics; do not cancel running serial chemistry; after repair use
  default 4 CPU / 7000 MB (%pal nprocs 4, %maxcore 1500) for CPCM jobs.

### RESULT (ORCA 6.1.1, first new number)
- job 13 diag_real_np1 (SP @ rcA geom, np1): E = -684.745386188 Eh (normal termination).
  ORCA5 job598 E(RC_A opt) = -684.744885326 -> ORCA6 - ORCA5 = -0.000501 Eh = -0.31 kcal/mol.
  (engine-consistency, same order as HL1's 0.003 kcal/mol; still keep versions separate in any ladder)

### QUEUED / RUNNING (HE3)
Running/queued HE3: 23 tsA_ORCA6_np1, 24 tsB_ORCA6_np1, 25 rcA_ref_np1, 26 rcB_ref_np1 (all np1 serial).
PREPARED, submit only AFTER repair-ready (np4/maxcore1500):
- prodA_ref/HE3_prodA_ref.inp : Opt+Freq prodA.xyz  -> E(PROD_A)_ORCA6
- ircA_np4/HE3_ircA_np4.inp   : IRC from tsA667 (both directions) -> run after TS_A ORCA6 confirmed
Plan after repair: finish TS_A/TS_B OptTS+Freq at np4 if the np1 runs are too slow (do NOT duplicate);
IRC both ways -> endpoint Opt/Freq -> dE# = E(TS)-E(RC) at ORCA 6.1.1 ONLY; then channel B.

## UPDATE 2026-10-01 (HUMAN DIRECTIVE: 8-core default)
New default for HE3 CPCM production jobs once MPI repaired: submit_compute_job cpus=8 memory_mb=14000,
input %pal nprocs 8 and %maxcore 1500 (mem '12GB'). 4 concurrent 8-core jobs fill the 32-CPU pool.
Existing queued/running np1 jobs 23-26 left UNCHANGED (not cancelled/restarted). Do not claim 8 CPU for a
serial nprocs1 input. Never change method/solvent/graph/reference/acceptance.
Prepare (np8) for post-repair submit:
- prodA_ref/HE3_prodA_ref_np8.inp : Opt+Freq prodA.xyz -> E(PROD_A)_ORCA6
- ircA_np4/HE3_ircA_np8.inp      : IRC from tsA667 (both directions)
Submit these at np8 (cpus=8, mem=14000) once root confirms the MPI build is repaired.

## UPDATE 2026-10-01 (MPI REPAIRED -> 8-core production submitted)
Root: full OpenMPI 4.1.8 with Fortran datatypes now at /opt/openmpi-4.1.8-full, dispatch fixed; probe
MPI_Type_match_size(INTEGER,8)/REAL4/COMPLEX16 now succeed. Resume 8-core CPCM production.
SUBMITTED at cpus=8, memory_mb=14000, %pal nprocs 8, %maxcore 1500 (mem '12GB'):
- job 33 prodA_ref/HE3_prodA_ref_np8.inp : Opt+Freq prodA.xyz -> E(PROD_A)_ORCA6  [channel A product]
- job 34 prodB_ref/HE3_prodB_ref_np8.inp : Opt+Freq xtb/prodDFT_B/free_opt.xyz -> E(PROD_B)_ORCA6 [channel B product]
- job 35 ircA_np4/HE3_ircA_np8.inp        : IRC from tsA667 (both directions) -> channel-A IRC
Still running/queued from before (left unchanged): 23 tsA_ORCA6_np1 (RUNNING OptTS+Freq),
24 tsB_ORCA6_np1 (RUNNING), 25 rcA_ref_np1, 26 rcB_ref_np1 (queued np1).
On terminal notifications: log_parser each; then TS_B IRC (np8) and RC references; assemble consistent
ORCA 6.1.1 ladder RC_A/RC_B -> TS_A/TS_B -> PROD_A/PROD_B (engine 6.1.1 ONLY; old 5.0.2 = context).

## RESOURCE FACT (2026-10-01)
- job 33 (PROD_A Opt+Freq) was adjusted by root while READY: 8 ranks, %maxcore 512, req_memory_mb=5000
  (was 14000/maxcore1536). jobID/path/geometry/method/solvent unchanged; NOT resubmitted. Original input
  kept at prodA_ref/.cloudra/job33-input-before-memory-adjustment.inp + job33-memory-adjustment.json.
  Its 8-rank CPCM files (gpot0..7/grho0..7/exc0..7) confirm repaired MPI working in real production.
- Do not overwrite job33 input or resubmit it; monitor for the real error if it fails.

## DELEGATION (2026-10-01) - owner=coordinator; execution specialists small_mol
Coordinator owns: scientific review (true hydride mode, channel consistency), cross-channel comparison,
graph ambiguity escalation, resource coordination, final REPORT/HANDOFF. Execution delegated:
- CHANNEL A specialist session as_19aee01c357c4bfc (small_mol): owns jobs 23 (tsA OptTS+Freq), 25 (rcA Opt+Freq),
  33 (prodA Opt+Freq), 35 (IRC_A) + IRC endpoint Opt/Freq. Deliver E(TS_A), E(RC_A), E(PROD_A) at ORCA 6.1.1,
  dE#, imag-mode check, endpoint identities. Report: paratera_20260930/chanA_owner/REPORT.md
- CHANNEL B specialist session as_0af3d08a16c94d6a (small_mol): owns jobs 24 (tsB OptTS+Freq), 26 (rcB Opt+Freq),
  34 (prodB Opt+Freq) + TS_B IRC + endpoint Opt/Freq. Deliver E(TS_B), E(RC_B), E(PROD_B) at ORCA 6.1.1, dE#.
  Report: paratera_20260930/chanB_owner/REPORT.md
Rules given to children: adopt/parse jobs 23-26,33-35 (do NOT resubmit/kill); fixed method/solvent/charge/version
(ORCA 6.1.1 only, never mix ORCA5); 8-core preferred (cpus=8, mem=14000, nprocs8, maxcore1500); work only in
HE3 paratera dir; no other topics, no old-server SSH, no method/graph/acceptance changes. Shared 32CPU/56000MB.
Owner will verify manifests/results (not assume success = chemical success).

## VERIFIED ORCA 6.1.1 numbers (owner-parsed, 2026-10-01)
- E(RC_A)_ORCA6 (job 25, Opt+Freq, 0 imag, 105 freqs, converged) = -684.745389244764 Eh
- E(RC_B)_ORCA6 (job 26, Opt+Freq, 0 imag, 105 freqs, converged) = -684.743918222978 Eh
- E(RC_A) SP on ORCA5 geom (job 13) = -684.745386188 Eh (matches job 25 to 3e-6 Eh -> min is flat, good)
- RC_B - RC_A = 0.001471 Eh = 0.92 kcal/mol (channel-B pre-complex slightly higher).
Still running: 23 (TS_A OptTS+Freq), 24 (TS_B OptTS+Freq), 33 (PROD_A), 34 (PROD_B, started). Queued: 35 (IRC_A).
GATES: job 23 and 24 must each show exactly ONE imaginary mode = the hydride transfer (C4-H34/B16-H34);
if torsional, that channel's TS is invalid and needs a new seed.

## TS_A CONFIRMED at ORCA 6.1.1 (job 23) + PROD_A issue (job 33)
- job 23 tsA_ORCA6_np1: E(TS_A)_ORCA6 = -684.732199242842 Eh, normal, converged, 104 freqs, EXACTLY
  1 imag = -419.08 cm-1. Imaginary mode dominated by C4-H34 (watch 7-34 projection 0.9127; 16-34 0.2970;
  heavy_atom_fraction 0.094) => GENUINE six-membered CBS hydride-transfer TS (channel A / Si -> (R)).
- dE#(channel A) = E(TS_A)-E(RC_A) = 0.013190002 Eh = 8.277 kcal/mol (ORCA 6.1.1 only;
  ORCA5 provisional was 8.13 kcal/mol -> engine-consistent, ~0.15 kcal/mol shift).
- job 33 prodA_ref_np8: E = -684.776224108725 Eh, converged, but 1 imag = -6.55 cm-1 (ORCA5 had 0 imag).
  => NOT yet a clean minimum; channel-A specialist to re-opt with TightOpt/larger grid and characterize the
  soft mode. E(PROD_A)-E(RC_A) = -0.030835 Eh = -19.35 kcal/mol (provisional, pending clean product min).
- job 24 TS_B still running; job 34 PROD_B DONE; job 35 IRC_A running.
- job 34 prodB_ref_np8: E(PROD_B)_ORCA6 = -684.771718122240 Eh, normal, converged, 0 imag, 105 freqs
  (valid product min: alkoxyborane + regenerated catalyst, 2 fragments).
- OPEN ITEM (enantiomer anomaly, flagged by channel-B specialist): PROD_B seed (xtb/prodDFT_B/free_opt.xyz)
  has the SAME carbinol configuration (R) as PROD_A, not the expected (S) for the Re channel. This is a
  property of the independently-built xtb product seed (can lose facial memory), NOT of the barrier:
  dE#=E(TS_B)-E(RC_B) is unaffected. Per owner decision, the enantiomer identity will be taken from the
  TS_B IRC product endpoint (C7 R/S), not the seed. If that IRC product is also (R), escalate as an open
  channel-assignment question -- do not force a number.
- E(PROD_B)-E(RC_B) = -0.027799899 Eh = -17.44 kcal/mol (provisional).

## OWNER REVIEW of channel A (2026-10-01, overnight checkpoint) - CORRECTION APPLIED
Verified independently (job 35 IRC log + endpoint Opt jobs 48/49 + internal_coordinates):
- job 35 IRC: normal, 12 fwd / 5 bwd points, both directions converged. F-side endpoint energies ~ -684.7341..-684.7421.
- job 48 (reactant-endpoint Opt): ternary-complex conformer of RC_A, connectivity same, E = -684.743913186714 Eh, 0 imag, +0.93 kcal/mol vs RC_A.
- job 49 (product-endpoint Opt): E = -684.786033727921 Eh, 0 imag; C7-H34 = 1.104 (hydride transferred, C7 = R);
  catalyst 5-ring OPENED B5-N15 = 3.981 A; B5 chelates O4/O6 (1.355/1.358); B16 still on N15 (1.387).
- job 39 (prodA_tight): E = -684.776275499364 Eh, 0 imag; intact-ring catalyst-regenerated product (B5-N15 1.385, O6-B16 1.410).
- KEY: through the 12 IRC frames the hydride transfers (C7-H34 1.459->1.176) while B5-N15 stays ~1.61->1.67 (ring intact);
  the ring opening appears only under FULL opt (job 49). => an ADDITIONAL B5-N15 cleavage occurs downstream.
### CORRECTED CONCLUSIONS (chanA_owner/REPORT.md edited)
- VERIFIED: dE#(channel A) = E(TS_A)-E(RC_A) = +0.013190002 Eh = +8.277 kcal/mol = the hydride-transfer saddle barrier.
- VERIFIED: TS_A has exactly 1 imag (-419.08 cm-1) dominated by C4-H34 (projection 0.913) => hydride transfer.
- CAVEAT: the declared catalyst-regeneration endpoint (job 39) is NOT proven connected to the IRC branch. NO barrier
  was computed for the extra B5-N15 cleavage, so it must NOT be called a low-barrier isomerisation.
- TWO DISTINCT PRODUCTS retained: job 39 (intact-ring) and job 49 (ring-opened), 6.12 kcal/mol apart. No graph edit.
- Limited plan: freeze dE#(A)=+8.28; run nothing new to "close" the ring-opening; only revisit 49<->39 with a
  separately-authorized scan if the human asks. Channel B: job 24 FAILED (2026-10-01): OptTS+Freq from tsB_seed, normal termination but opt NOT converged
  (max cycles ~9.5 h); only the initial Calc_Hess block has 2 imag (-71.71/-41.89 cm-1), both TORSIONAL
  (heavy-atom frac 0.084/0.198; C7-H34 watch proj 0.02/0.22); final C7-H34=4.163 (hydride never left B16).
  => NO valid channel-B TS, so dE#(channel B) CANNOT be quoted. Same failure mode as ORCA5 job 600.
Valid channel-B anchors at ORCA 6.1.1: E(RC_B)=-684.743918222978 (job 26, 0 imag);
  E(PROD_B)=-684.771718122240 (job 34, 0 imag; seed enantiomer anomaly flagged - C7=R vs expected S).
OWNER DECISION: approved channel-B specialist's remedy - relaxed scan of d(C7-H34) on the job-26 RC_B minimum
  (mirrors the channel-A route that gave TS_A via job 667), highest converged point -> OptTS+Freq np8 ->
  require 1 hydride imag mode -> IRC both ways -> endpoint Opt+Freq + C7 R/S from the IRC product endpoint.
  If it again gives a torsional saddle: stop, report, no dE#. No long DFT NEB. New input dir under chanB_owner.
### RESULT (2026-10-01): the d(C7-H34) scan on RC_B gave a genuine hydride saddle = THE SAME SADDLE AS CHANNEL A
- job 62 (chanB_owner/tsB_scanseed): E = -684.732238989422 Eh, converged, 1 imag = -416.12 cm-1, C7-H34 projection
  0.9132 (genuine hydride). E(TS_B)-E(TS_A) = -0.025 kcal/mol; specialist reports RMSD(TS_B, tsA667) = 0.015 A.
- The scan collapsed RC_B back to the channel-A ketone orientation at its first constrained frame; channel A's IRC
  reactant endpoint (job 48, -684.743913) equals RC_B (-684.743918) => RC_A and RC_B are two CONFORMERS of the same
  ternary complex (RC_B = +0.92 kcal/mol), not two stereochemical channels.
- Therefore at ORCA 6.1.1/B3LYP-D3BJ/def2-SVP CPCM(THF) the constructed endpoints give ONE hydride-transfer saddle.
  dE# vs the common global-minimum reference RC_A = +8.28 kcal/mol; vs the RC_B conformer = +7.33 kcal/mol
  (difference is reference-only). Do NOT declare two independent channel barriers.
- OPEN ITEM (ESCALATED to human): the intended two-face model (Si->R, Re->S) is NOT reproduced; both products give
  C7 = R. Mechanism/graph ambiguity - do NOT edit the task-source graph or invent a second channel.
- job 63 (IRC_B) DONE (2026-10-01): both directions converged (11 fwd / 5 bwd). Product-side endpoint
  E = -684.733671 Eh, hydride on C7 (C7-H34 1.178), ring essentially INTACT (B5-N15 1.668), C7 = R
  (RDKit CIP + signed volume +2.022). Reactant-side endpoint E = -684.741982, hydride still on B16 ->
  RC_B-type ternary complex. Mirrors IRC_A.
- FINAL (topic REPORT.md written, HE3_gold_20260929/REPORT.md): ONE shared hydride-transfer saddle,
  dE# = +8.28 kcal/mol vs the common reference RC_A (8.25 via TS_B; 7.33 vs the RC_B conformer).
  Open items escalated to the human: (i) 39<->49 ring-opening connectivity unproven (no barrier);
  (ii) intended Re->(S) channel not reproduced - both products C7 = R. No graph/mechanism_graph edits.
  Authorized HE3 scope is complete; no HE3 jobs running or queued.