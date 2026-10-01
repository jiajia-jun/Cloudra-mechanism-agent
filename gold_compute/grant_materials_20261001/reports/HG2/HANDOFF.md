# HG2 HANDOFF

## Goal
Hard-gold backfill HG2 = (E,E)-crotyl propenyl ether Claisen stereochemical outcome. Locate an
independent gas-phase saddle leading to the SYN diastereomer (2S,3S), verified by freq + IRC + endpoint opts.
Gold precomputation, not a formal benchmark. Benchmark sources NOT edited.


## RESOURCE POLICY (supersedes earlier 4-core default)
For all NEW ORCA production jobs: submit_compute_job cpus=8, memory_mb=14000; input %pal nprocs 8, %maxcore 1500.
Server = 32 logical CPUs / 56000 MB => ~4 concurrent 8-core jobs; queue the rest (admission enforces CPU+mem).
Existing RUNNING jobs (3,4) and already-QUEUED nprocs-4 jobs (19,20,22,28,29,32) are LEFT UNCHANGED (no
cancel/restart/resize; no duplicate work). Never claim 8 CPUs for an nprocs-1 input. Once root confirms MPI
repaired, prioritize real 8-core productive CPCM tasks. Method/solvent/graph/reference/acceptance unchanged.

## ENV (new server, 2026-09-30)
- Node: paratera-cpu (LOCAL), 32 CPU / 56000 MB, max 8 concurrent jobs.
- Engine: ORCA 6.1.1 (NEW). Standalone xTB 6.7.1, CREST 3.0.2 available.
- Per-topic budget: TWO active jobs, cpus=4 / memory_mb=7000 (%pal nprocs 4, %maxcore <=1536).
- All jobs submitted via submit_compute_job(node_id="paratera-cpu", execution_backend="local").
- Old Slurm IDs (630-632, 687-689) = RETIRED server; NOT polled, NOT resubmitted as same job.

## HARD CONSTRAINTS
- Do NOT resubmit the two existing verified anti-channel saddles.
- Do NOT fit the historical 29.67/26.39; no graph/source/acceptance/ref-frame change without user decision.
- Fixed model: gas B3LYP D3BJ def2-SVP def2/J RIJCOSX TightSCF (same as prior session), now ORCA 6.1.1.
- NEVER subtract an ORCA 5.0.2 / Gaussian energy from an ORCA 6.1.1 energy. Old energies = context only.

## Atom map (product order, ORCA 0-based reactant values)
[3,2,6,7,1,0,5,4,13,14,12,16,17,18,19,11,8,9,10,15].
Reaction center built-order (0-based): breaking (3,4)=C4-O5, forming (1,6)=C2-C7.
syn=(2S,3S) RDKit CIP "C=C[C@H](C)[C@H](C)C=O"; anti=(2R,3S).

## Files
- AUDIT_NOTES.md, REPORT.md   — audit + status.
- build/                      — R, Psyn, Manti MMFF 3D builds.
- ts/ts_0001/                 — ts_prepare run (blocked at guess).
- scan/syn_grid/, scan/react_grid/ — product-/reactant-anchored constrained xTB 2D grids (no saddle).
- dft/neb_syn/                — ORCA NEB-TS input + endpoints (old job 630, ABANDONED).
- dft/R_min/, dft/P_syn_min/  — old ORCA 5.0.2 endpoint opt+freq (context only).
- paratera_20260930/          — NEW ORCA 6.1.1 jobs (this pass).

## JOBS (this pass, ORCA 6.1.1)
| job | tag | seed | what | state |
|---|---|---|---|---|
| 3 | syn_ts_g1 | scan/syn_grid/opt_2.3_2.3.xyz | OptTS+Freq (Calc_Hess) | RUNNING |
| 4 | syn_ts_g2 | scan/syn_grid/opt_2.6_2.3.xyz | OptTS+Freq (Calc_Hess) | RUNNING |
| 19 | syn_ts_g3 | scan/react_grid/opt_2.2_2.2.xyz | OptTS+Freq (Calc_Hess) | QUEUED |
| 20 | syn_ts_g4 | scan/syn_grid/opt_2.0_2.0.xyz | OptTS+Freq (Calc_Hess) | QUEUED |
| 21 | R_ref | dft/R_min/R_min.xyz | Opt+Freq (ORCA 6.1.1 reference minimum) | QUEUED |
| 22 | P_syn_ref | dft/P_syn_min/P_syn_min.xyz | Opt+Freq (ORCA 6.1.1 reference minimum) | QUEUED |
| 28 | syn_ts_g5 | scan/syn_grid/opt_2.6_2.6.xyz | OptTS+Freq (Calc_Hess) | QUEUED |
| 29 | syn_ts_g6 | scan/react_grid/opt_2.4_2.2.xyz | OptTS+Freq (Calc_Hess) | QUEUED |

NOTE 2026-09-30: pool saturated (8 slots). Other topics' PARALLEL CPCM jobs (jobs 1,2,5,6,7,8,18) failed with
MPI_ERR_ARG (Fortran datatype bug in MPI 4.1.8); root is rebuilding MPI at a separate prefix. My HG2 jobs are
RIJCOSX (no CPCM) and unaffected. Do NOT resubmit those MPI jobs; await root repair-ready. No more MPI diagnostics.

Reactive pairs on the SYN-GRID seed order (1-based, as ORCA preserves it): breaking C1-O8 (2.30 A),
forming C3-C5 (2.09 A) -> use as log_parser watch_pairs = [[1,8],[3,5]] and for IRC direction check.

## RESULTS (ORCA 6.1.1, gas B3LYP D3BJ def2-SVP def2/J RIJCOSX TightSCF)
- job 21 R_ref: E = -348.690242146502 Ha, 0 imag, opt converged. (Reproduces old ORCA5 -348.690242425215 to ~3e-7 Ha.)
- job 4 syn_ts_g2: E = -348.648414103477 Ha, 1 imag = -403.47 cm^-1, opt converged (jobtype ts).
  Imaginary-mode top displaced pairs (1-based): (1,8)=0.781 breaking C1-O8, (3,5)=0.697 forming C3-C5,
  (3,16)=0.665, (8,10)=0.616. => REACTIVE C-O/C-C mode, NOT torsional. heavy_atom_fraction 0.58.
  Preliminary Delta-E-ddagger(g2 - R_ref) = +0.041828 Ha = +26.25 kcal/mol (electronic; context only, NOT fitted).
- job 3 syn_ts_g1: still optimizing (Calc_Hess TS opt in progress).
- Now submitted: job 32 irc_g2 (IRC both directions from syn_ts_g2.hess). Next: Opt+Freq both IRC endpoints;
  assign product CIP -> prove SYN (2S,3S) vs anti.
- job 22 P_syn_ref: E = -348.710860856473 Ha, 0 imag, opt converged (matches old ORCA5 to ~4e-6 Ha).

## CONSISTENT ORCA 6.1.1 GAS REFERENCE ENERGIES
  R_ref(j21) = -348.690242146502 Ha ; P_syn_ref(j22) = -348.710860856473 Ha
  Delta-E(reaction,syn) = -0.02061871 Ha = -12.94 kcal/mol
  Delta-E-ddagger(syn cand g2, j4) = +0.04182804 Ha = +26.25 kcal/mol (electronic; context only, NOT fitted)

## JOB LEDGER (HG2, 2026-09-30)
RUNNING: 3 g1(c4), 19 g3(c4), 20 g4(c4) | QUEUED: 28 g5(c4), 29 g6(c4), 32 irc_g2(c4)
DONE: 4 g2 saddle, 21 R_ref, 22 P_syn_ref. All NEW jobs = 8-core/nprocs8.
MPI REPAIR READY (root): full OpenMPI 4.1.8 Fortran datatypes at /opt/openmpi-4.1.8-full.
HG2 is GAS-PHASE (no CPCM): no CPCM resubmission here; do not duplicate others' active jobs.
(NOTE: different order in react_grid seeds; verify with internal_coordinates before reusing indices.)

## OLD JOBS (context only, do not reuse energies across versions)
- 630 HG2_syn_neb : NEB-TS FAILED (18h walltime; unphysical ~100 kcal path). ABANDONED.
- 631 HG2_R_min   : ORCA5 E=-348.690242425215 Ha, 0 imag.
- 632 HG2_P_syn_min: ORCA5 E=-348.710857182109 Ha, 0 imag.
- 687/688/689 : OptTS seeds, no local output (retired server).

## NEXT ACTIONS on wake (job 3/4 notification)
1. log_parser jobs 3/4: opt converged? n_imag? If 1 imag, check the imaginary mode composition
   (log_parser watch_pairs (1,6) forming / (3,4) breaking, 1-based) — reject a PURELY torsional mode.
2. If 1 imag aligned to the C-O/C-C reactive coordinate: IRC both directions (qm_input_writer !IRC),
   then endpoint Opt+Freq; determine product configuration (syn vs anti) from IRC endpoints.
   "Prove the SYN endpoint configuration, not just a torsional imaginary mode."
3. Submit R_ref + P_syn_ref (ORCA 6.1.1) when slots free -> consistent Delta-E(reaction) and Delta-E-ddagger.
4. If a saddle gives anti -> try g3 / other candidate; do NOT resubmit NEB.
5. Update REPORT.md + HANDOFF.md with exact job IDs and energies; report to parent via agent_hub.

## STATUS UPDATE 2026-09-30 (job 3 done)
- job 3 syn_ts_g1: E = -348.648444691032 Ha, 1 imag = -404.28 cm^-1, opt converged (ts).
  vs job 4 syn_ts_g2 E = -348.648414103477 Ha, 1 imag = -403.47 cm^-1.
  Same saddle confirmed (rotation-invariant heavy-atom distance-matrix max |delta| = 0.0072 A;
  key C1-O8 1.994 vs 1.996 A, C3-C5 2.427 vs 2.428 A; imag modes identical). => NO separate IRC for g1;
  the queued IRC 32 (from g2) covers this saddle.
- ONE distinct validated syn-candidate saddle so far: E = -348.64843(2) Ha, 1 imag ~ -404 cm^-1,
  reactive C1-O8/C3-C5 mode, Delta-E-ddagger = +26.25 kcal/mol (electronic, context only).
- CORRECTED JOB STATES: DONE: 3 g1, 4 g2, 21 R_ref, 22 P_syn_ref. RUNNING: 19 g3, 20 g4.
  QUEUED: 28 g5, 29 g6, 32 irc_g2. (jobs 19/20 still running; 28/29/32 awaiting resources.)
- Gate remains: IRC 32 must connect R and SYN-P; then Opt+Freq both endpoints, assign CIP = (2S,3S).
  No gold fill until endpoint stereochemistry is proven.

## STATUS UPDATE #2 2026-09-30 (g3 failed, g4 done)
- job 19 syn_ts_g3: FAILED — ORCA TS opt hit max steps (unconverged; untrustworthy). Reactant-anchored seed; NOT resubmitted.
- job 20 syn_ts_g4: DONE but NOT the reactive saddle. E = -348.700209839681 Ha, 1 imag = -75 cm^-1,
  heavy_atom_fraction = 0.19, top displaced pairs all H (14-20,11-18,14-19,15-18,10-18), watch-pair fraction ~0.003.
  Geometry C1-O8 = 3.98 A (broken), C3-C5 = 1.59 A (formed) => product-region TORSIONAL saddle. REJECTED for syn channel.
  (distance-matrix vs g2: max delta 1.99 A -> different geometry entirely.)
- Therefore the ONLY validated reactive syn-candidate saddle remains g1==g2:
  E = -348.64843(2) Ha, 1 imag ~ -404 cm^-1, reactive C1-O8/C3-C5 mode, Delta-E-ddagger = +26.25 kcal/mol.
- CRITICAL PATH: job 32 irc_g2 (queued) -> IRC both directions. Then Opt+Freq both endpoints, assign CIP.
- States: DONE 3,4,20,21,22. FAILED 19. QUEUED 28 g5, 29 g6, 32 irc_g2.

## STATUS UPDATE #3 2026-09-30 (g5 done)
- job 28 syn_ts_g5: E = -348.648436400306 Ha, 1 imag = -403.92 cm^-1, reactive C1-O8/C3-C5 mode.
  distance-matrix vs g2 max |delta| = 0.0058 A; key C1-O8 1.995/1.996, C3-C5 2.427/2.428. => SAME saddle as g1/g2.
  Independent seeds g1(2.3/2.3), g2(2.6/2.3), g5(2.6/2.6) all converge to this ONE reactive saddle -> robust.
  g5 adds NO distinct candidate; no extra IRC.
- States: DONE 3,4,20,21,22,28. FAILED 19. RUNNING 29 g6. QUEUED 32 irc_g2.
- DECISIVE REMAINING STEP: job 32 irc_g2 IRC both directions -> does it reach SYN-P (2S,3S) or ANTI?
  Then Opt+Freq both endpoints + CIP assignment. No gold fill before that.

## STATUS UPDATE #4 2026-09-30 (g6 failed; IRC running)
- job 29 syn_ts_g6: FAILED same way as g3 — ORCA TS opt hit max steps (unconverged, untrustworthy). Both reactant-anchored
  react_grid seeds (g3 2.2/2.2, g6 2.4/2.2) fail to converge; the product-anchored syn_grid seeds (g1,g2,g5) all converge
  to the SAME reactive saddle. => reactant-anchored seeding is the worse route for this TS; no resubmission (would repeat).
- States: DONE 3,4,20,21,22,28. FAILED 19,29. RUNNING 32 irc_g2. (All 6 seeds spent; no further seed submissions.)
- Awaiting IRC 32 terminal: parse BOTH geometric directions, assign endpoint stereochemistry (SYN 2S,3S vs anti),
  then Opt+Freq the IRC endpoints. No gold fill before the endpoint CIP is proven.

## FINAL RESULT (2026-09-30) — SYN channel VERIFIED at ORCA 6.1.1
- IRC 32 done (30 F + 30 B frames; MaxIter cap) -> jobs 40 (rc, -348.689907922178, 0 imag, ether intact)
  and 41 (product, -348.712340359576, 0 imag, C1-O8 broken / C3-C5 formed). Both RDKit CIP = both centres S
  => SYN (matches P_syn_ref). Jobs 40/41 were run by child small_mol as_cba0d6a330004abc; coordinator re-verified
  the raw logs and CIP.
- Delta-E-ddagger: 26.25 (TS - R_ref21) / 26.04 (TS - rc ep_F40) kcal/mol; Delta-E(reaction) = -14.08 kcal/mol.
- Selectivity: gold favored=anti(26.39) vs syn 29.67; old verified anti (30.943/34.753) used Gaussian w/o D3BJ
  -> NOT comparable. NO same-method anti number exists. Graph/source NOT changed. Escalated to human.
- No duplicate HG2 calculations remain. See REPORT.md section 8 for the full review.

## 2026-10-01 AUTHORIZED FOLLOW-UP: same-method ANTI re-derivation (human decided option (b))
- Decision: re-derive the anti saddle at ORCA 6.1.1 (same fixed gas model) so syn-vs-anti is comparable at ONE method;
  keep R_ref (job 21) as reference; no Gaussian/D3BJ-less numbers mixed; no graph edit; no fitting to old favored/3.28.
- AUDIT: the old anti saddle GEOMETRY is NOT on this filesystem. Only the anti PRODUCT build exists
  (HG2_gold_20260929/build/structure_build_Manti/). Old anti energies (30.943/34.753) were Gaussian w/o D3BJ.
- Delegated to the SAME small_mol session as_cba0d6a330004abc (not a new owner): locate anti saddle via
  ts_prepare/ts_resume (R = E,E-crotyl propenyl ether; anti product from build_Manti), then Freq + IRC +
  Opt/Freq endpoints + CIP (expect MIXED = anti). 8 cores, %maxcore ~1000, memory_mb ~8000 (do NOT default 14 GB).
- Coordinator will verify the returned logs before accepting any selectivity statement.

## 2026-10-01 SEED ARRIVED (legacy anti TS geometry)
- legacy_anti_seed_from_local/ now holds: HG2_E1_ts3_final.xyz (ANTI-CHAIR TS, use this), HG2_EM1_bC_final.xyz (boat TS),
  HG2_M1_min.xyz (anti product), HG2_R_ext_min.xyz (reactant), HG2_E1_ts3.log (Gaussian log = evidence only),
  HG2.json (historical record = context only). Element order = ORIGINAL R numbering: C C C C O C C C H x12.
- Reaction-center watch pairs in THIS order (1-based): forming (2,7) C2-C7, breaking (4,5) C4-O5. (Do NOT reuse old
  Gaussian watch-pair indices blindly.) 
- Re-messaged small_mol as_cba0d6a330004abc to run ORCA 6.1.1 OptTS+Freq from HG2_E1_ts3_final.xyz (gas B3LYP D3BJ
  def2-SVP def2/J RIJCOSX TightSCF) into anti_ts_legacy/, with explicit R-order mapping, then Freq+IRC+endpoint CIP
  (expect MIXED = anti). Reuse GEOMETRY ONLY; never mix Gaussian energies. 8 cores / %maxcore~1000 / memory_mb~8000.
- Goal: same-method (ORCA 6.1.1) syn-vs-anti comparison. syn reference: TS -348.648414103477, dE‡ 26.25 vs R_ref (job 21).
- Coordinator will verify the child's logs/CIP before any selectivity conclusion or graph discussion.

## FINAL (2026-10-01) — BOTH channels at ORCA 6.1.1; chair/boat labels corrected
- anti TS job 53 = -348.648202350340 (1 imag -403.27, reactive C4-O5/C2-C7 mode). anti endpoints: rc job57
  -348.688498440674 (achiral), product job56 -348.710408259292 (CIP S,R = ANTI). syn endpoints: rc job40, product job41 (both-S = SYN).
- INDEPENDENT REVIEW (coordinator): ring torsions show BOTH TS are CHAIR-like (anti +71/-71/+54/-71/+78/-55;
  syn +68/-73/+60/-78/+81/-50) -> source syn=boat/anti=chair labels are WRONG. Reaction centre/species identical.
- Barriers (electronic, vs R_ref21): syn 26.25 vs anti 26.38 kcal/mol -> |Delta| 0.13, near-degenerate. vs own
  IRC reactant conformers: syn 26.04 vs anti 25.29 (anti conformer is 0.88 higher). No selectivity claim.
- ACTION: graph EDGES unchanged; correct text/labels to chair-like (syn) / chair-like (anti); source 29.67/26.39/3.28
  superseded by same-method 26.25/26.38. See REPORT.md section 9 for full review + caveats. No new QM submitted.

## CRITICAL CORRECTION (2026-10-01, pending) — syn channel is on the WRONG substrate (E,Z)
- Independent E/Z check (coords; matches supervisor RDKit): R_ref21 = (E,E); anti rc57 = (E,E); anti TS53 = (E,E);
  syn rc40 = (E,Z) [C2=C3 E, C5=C7 Z]; syn TS4 = (E,Z); syn IRC frame0 already Z.
- => RETRACT 26.25 as the (E,E)-syn barrier and the 0.13 near-degeneracy/reversed-favoured comparison.
  KEEP anti 26.38 (E,E) as valid; KEEP the (E,Z)->syn saddle (jobs 4/40/41) as a separate E,Z-substrate result.
- NEXT: executor to seek a true (E,E)->syn saddle with both alkenes pinned E/E, same skeleton/atom map; verify
  both-side TS geometry before any formal 8-core job; honest GAP if none found. No re-run of anti; no filler boat.
NOTE: the "section 9" wording above and the Pass-4 near-degeneracy are superseded by this correction.

## PRODUCTION POLICY (2026-10-01, from human) - no self-set timeouts
- NO timeout/deadline on ANY compute call, incl. semiempirical (no timeout=1200/600). If ts_guess(xtb_path) forces a
  hard timeout that cannot be disabled: let the current call finish, then stop using it (record the limitation); use
  the STANDALONE xTB binary directly under an explicit ledgered resource budget. Do NOT kill/restart running work/API.
- (E,E)->syn exploration must NOT reuse the old interp_syn img00/img16 path blindly: first verify BOTH C=C E/E + atom
  mapping, then use xTB NATIVE constraints holding both E dihedrals + full covalent skeleton, re-verifying at each
  build-stage geometry; the formal unconstrained TS must re-verify reactant-side E/E and product CIP.
- Only initial-guess constraint VALUES are self-settable; iteration counts / runtimes are not.
- Single submitter = small_mol as_cba0d6a330004abc. Coordinator does not submit HG2 QM.

## FINAL STATUS (2026-10-01) - honest GAP for (E,E)->syn
- anti 26.38 kcal/mol VALID: (E,E) chair saddle job53 -> job57 (E,E rc) -> job56 (CIP R,S = anti). TS53 - R_ref21.
- syn = NULL (GAP): no (E,E)->syn saddle found at ORCA 6.1.1 gas. Executor's constrained E,E xTB drive (both E dihedrals
  held; C2-C7 3.4->1.9 A) is monotonic to a max ~2.0 A then collapses to ANTI. Coordinator re-verified frames E,E to 2.0 A
  and frame_1.9 CIP R,S (anti). Artifact: HG2_EE_to_syn_GAP.md.
- E,Z->syn (jobs 4/40/41) retained ONLY as separate-substrate supporting evidence (not gold; 26.25 retracted).
- The interp ENDPOINTS img_00(E,E)->img_16(syn) exist, but the IDPP path is unphysical; no valid saddle/path found.
- CAVEAT: a single constrained closure does not prove non-existence; the source expects syn via a BOAT TS and a boat-region
  E,E search was out of this scope. Close with the GAP; no endless scanning, no anti re-run, no filler. Raw records kept.
- Source/TaskSpec already committed (72ac25b4) by the other thread - NOT re-pushed here.

## DELEGATION (coordinator, 2026-09-30)
- Child: small_mol, session_id = as_cba0d6a330004abc (launched by coordinator).
  Responsibility: ADOPT running IRC job 32 (dir paratera_20260930/irc_g2/) -> parse BOTH directions ->
  Opt+Freq both endpoints (new dirs irc_g2_ep_A/ , irc_g2_ep_B/) -> assign product CIP (syn 2S,3S vs anti)
  -> report energies + verdict. New jobs 8-core (cpus=8, mem=14000, nprocs 8, maxcore 1500).
  Forbidden: resubmitting jobs 3/4/19/20/21/22/28/29/32; new near-TS seed searches; other topics; method/graph changes.
- Coordinator keeps: scientific review (syn-vs-anti call), method-consistency review, cross-channel comparison,
  resource coordination, final REPORT/HANDOFF. Coordinator will VERIFY the child's manifests/results, not assume success.

## OWNER METHOD-CONSISTENCY REVIEW (anti references)
- The old verified anti saddles (chair barrier 30.943, boat 34.753) were computed with Gaussian b3lyp/def2svp
  WITHOUT explicit D3BJ (per REPORT audit note). The current fixed model is ORCA 6.1.1 B3LYP D3BJ def2-SVP
  def2/J RIJCOSX. => The old anti numbers do NOT share the current method and MUST NOT be used for a
  syn-vs-anti selectivity comparison. They are context only. Any selectivity statement requires the anti
  saddle re-derived at ORCA 6.1.1 (out of current scope unless requested).
