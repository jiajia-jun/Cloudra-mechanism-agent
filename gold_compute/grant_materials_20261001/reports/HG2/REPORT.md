# HG2 — hard-gold backfill REPORT (pass 1: audit + syn-channel search)

**Task**: (E,E)-crotyl propenyl ether Claisen rearrangement — stereochemical outcome (hard, family G).
**Spec**: /public/home/yyywaa/cloudra/ideapool/tasks/hard/HG2.json (NOT edited)
**Computed record**: /public/home/yyywaa/cloudra/gold_compute/edge_barriers/computed/HG2.json
**Work dir**: HG2_gold_20260929/
**State**: audit complete; syn-channel DFT search RUNNING. No gold change proposed.

## 1. Inventory (before any submission)
- Gold graph (spec): HG2_E1 = R->HG2_P(syn, "minor") channel boat_ts, barrier 29.67, favored=false;
  HG2_EM1 = R->HG2_M1(anti, "major") channel chair_ts, barrier 26.39, favored=true; spread 3.28.
- Computed record (authoritative evidence as recorded by the earlier partner session):
  * R_ext global min E = -348.8919489935882 Ha (frame own_min).
  * chair HG2_E1_ts3 E = -348.8426388277555 Ha, 1 imag -406.94, IRC verified -> ANTI product; barrier 30.943.
  * boat  HG2_EM1_bC E = -348.83656658 Ha,   1 imag -349.03, IRC verified -> ANTI product; barrier 34.753.
  * P_syn  HG2_P_opt  E = -348.9070340429252 Ha (2S,3S).
  * M1_anti HG2_M1_opt E = -348.9066045219441 Ha (2R,3S)/(2S,3R).
- Raw Gaussian logs/geometries of the earlier session are NOT on this filesystem (cited as
  gold_compute/jobs/...; no such tree here). Slurm/WSL records likewise unavailable locally.
  Audit therefore rests on the JSON record + independent re-derivation below.

## 2. Audit findings
1. **Atom mapping** (reaction_mapping R->syn-P and R->anti-P): identical connectivity.
   break [4,5] (C-O); form [2,7] (C-C); order changes 2-3 (2->1), 3-4 (1->2), 5-6 (1->2), 6-7 (2->1).
   Consistent with the gold bond_changes. watch pairs forming (2,7), breaking (4,5).
2. **Stereochemistry** (RDKit CIP): syn "C=C[C@H](C)[C@H](C)C=O" = (2S,3S);
   anti "C=C[C@H](C)[C@@H](C)C=O" = (2R,3S)/(2S,3R). Matches the record. Product = 2,3-dimethylpent-4-enal.
3. **Channel labels**: chair_ts->anti (gold favored) is CONSISTENT with the verified chair saddle -> ANTI.
   boat_ts->syn is INCONSISTENT: the verified boat saddle -> ANTI (it is an anti-channel boat).
   => the syn diastereomer's own saddle is genuinely missing (the open item).
4. **Reference minimum**: recorded frame = own_min = R_ext global min. Rebuilt R reproduces the extended
   E,E ether (r(C4-O5)=1.427, r(C2..C7)=5.318; record 5.048). Conformer caveat unchanged.
5. **METHOD NOTE (audit flag)**: the two verified anti saddles are Gaussian b3lyp/def2svp WITHOUT explicit
   D3BJ; this session's fixed method is ORCA B3LYP D3BJ def2-SVP def2/J RIJCOSX. Syn value and existing
   anti values therefore differ by dispersion treatment. Flagged, NOT changed.

## 3. Cheap cross-checks (this session)
- xTB GFN2 single points on MMFF-built geometries: R -25.1149, Psyn -25.1172, Manti -25.1186 Eh
  (reaction exothermic; Manti marginally below Psyn; consistent with record order). NOT a gold value.
- xTB path search (metadynamics) R->syn-P: unusable (path barriers 121-395 kcal/mol; timed out at 900 s).
- IDPP interpolation R->syn-P: not synchronous (C-O breaks far before C-C forms) -> poor TS guess.
- Product-anchored constrained 2D xTB grid (C2-C7 x C4-O5): monotonic, no internal saddle in window.

## 4. Active jobs (fixed method, ORCA B3LYP D3BJ def2-SVP def2/J RIJCOSX, gas, 4 cores)
| job | tag | what | state |
|---|---|---|---|
| 630 | HG2_syn_neb | ORCA NEB-TS, mapped endpoints R_ext (reactant.xyz) <-> syn-P (product.xyz, atom-map reordered), NImages 8 | submitted |
| 631 | HG2_R_min | R_ext opt+freq (ORCA frame minimum) | submitted |
| 632 | HG2_P_syn_min | syn-P opt+freq (ORCA frame minimum) | submitted |

Justification for the manual chain (sanctioned exception): the ts_prepare automated guess
(xTB metadynamics path, then IDPP) does not yield a usable guess for this conformational+pericyclic
change; NEB-TS on the mapped endpoints is the ceiling lever.

## 5. Next gates (when jobs return)
- Parse 630: a first-order TS from NEB-TS (1 imag, aligned to C-O/C-C), then IRC both ways +
  endpoint re-opts (0 imag), confirming R and syn-P identities.
- Delta-E-ddagger(syn) = E(syn-TS) - E(R_min, job 631); compare with the anti chair 30.943 (record).
- Do NOT resubmit the two existing anti jobs; do NOT fit 29.67/26.39; no graph/source/acceptance change.
## 6. Update (NEB failed; OptTS guesses launched)
- Job 631 R_ext: E = -348.690242425215 Ha, 0 imag, opt converged (ORCA frame minimum). 
- Job 632 syn-P : E = -348.710857182109 Ha, 0 imag, opt converged (ORCA frame minimum).
  => Delta-E(reaction) = -0.0206 Ha = -12.94 kcal/mol at the fixed method.
- Job 630 NEB-TS: FAILED. Ran 18 h then Slurm CANCELLED (walltime). The final NEB path is UNPHYSICAL:
  barrier ~0.160 Ha (~100 kcal/mol) at image 7 and an oscillating image profile (im3 dips back to the
  reactant energy). Cause: IDPP/linear interpolation between the EXTENDED reactant and the COMPACT
  product cannot represent the fold-then-react path. NEB from extended endpoints is ABANDONED.
- Cheap PES maps (xTB constrained 2D grids, reactant-anchored and product-anchored) give TS-like
  geometries with C2-C7 ~2.1-2.6 and C4-O5 ~1.9-2.4; used as OptTS guesses.
- New jobs (fixed method, 4 cores): 687 g1 (syn-grid 2.3/2.3), 688 g2 (syn-grid 2.6/2.3),
  689 g3 (reactant-grid 2.2/2.2) — ORCA OptTS+freq, to see which saddle each converges to and,
  via IRC, which diastereomer it produces.

## 7. Pass 2 (2026-09-30, NEW server paratera-cpu, ORCA 6.1.1)
Environment change: computation moved to a newly rented cloud node (paratera-cpu, LOCAL backend),
with human-deployed ORCA 6.1.1 / xTB 6.7.1 / CREST 3.0.2. The fixed scientific model is UNCHANGED
(gas B3LYP D3BJ def2-SVP def2/J RIJCOSX TightSCF); ONLY the engine version changed, so all new
energies are ORCA 6.1.1 and must not be differenced against old ORCA 5.0.2 / Gaussian numbers.
Old Slurm jobs belong to the retired server and were NOT polled/resubmitted.

Submitted (budget = 2 active jobs, cpus=4, memory_mb=7000, %maxcore 1536):
- job 3  HG2_syn_ts_g1 : ORCA 6.1.1 OptTS+Freq (Calc_Hess true) from scan/syn_grid/opt_2.3_2.3.xyz
- job 4  HG2_syn_ts_g2 : ORCA 6.1.1 OptTS+Freq (Calc_Hess true) from scan/syn_grid/opt_2.6_2.3.xyz
All under HG2_gold_20260929/paratera_20260930/<tag>/<tag>.inp.

Prepared for the next free slots (not yet submitted):
- HG2_syn_ts_g3 (react_grid/opt_2.2_2.2.xyz) — third candidate near-TS seed
- HG2_R_ref, HG2_P_syn_ref — recomputed reactant/product minima at ORCA 6.1.1 for a consistent
  Delta-E(reaction) and Delta-E-ddagger reference.

Gate: a computed saddle counts only if it is first-order (1 imag), the imaginary mode matches the
C-O/C-C reactive coordinate (not a torsional mode), and IRC both ways + frequency-verified endpoint
minima prove the SYN (2S,3S) product configuration. Scan peaks are never labeled gold.

## 8. Pass 3 — SYN channel VERIFIED (ORCA 6.1.1, gas). Coordinator's independent review.
Model fixed: gas B3LYP D3BJ def2-SVP def2/J RIJCOSX TightSCF, charge 0, mult 1. Engine = ORCA 6.1.1.
All energies below are ORCA 6.1.1 and mutually consistent; NEVER differenced against ORCA 5.0.2 / Gaussian.

Self-consistent energy set (Ha):
- R_ref (job 21)                = -348.690242146502  (0 imag)   [extended (E,E) ether min]
- P_syn_ref (job 22)            = -348.710860856473  (0 imag)   [syn (2S,3S) reference min]
- TS (jobs 4/3/28, SAME saddle) = -348.648414103477  (1 imag, -403.47 cm^-1; jobs 3 and 28 within 0.006 A)
- IRC forward endpoint (job 40, irc_g2_ep_F)  = -348.689907922178  (0 imag)  -> REACTANT, C1-O8 intact 1.42 A, C3-C5 4.93 A
- IRC backward endpoint (job 41, irc_g2_ep_B) = -348.712340359576  (0 imag)  -> PRODUCT, C1-O8 broken 4.20 A, C3-C5 formed 1.56 A

Atomic-mapping / CIP review (independent, done by the coordinator on raw ORCA outputs):
- IRC job 32 gave 30 forward + 30 backward frames (ORCA IRC hit MaxIter=30; irc_both_directions_converged=false),
  then the endpoint frames were optimized: both give 60 real freqs, 0 imaginary, normal termination.
- ep_F is the reactant (ether intact, no C-C formed). ep_B is the product.
- Product stereochemistry: RDKit CIP on ep_B assigns BOTH stereocentres = S. Since the syn diastereomer is
  "both centres same" ((2S,3S)/(2R,3R)) and anti is mixed ((2R,3S)/(2S,3R)), ep_B is the SYN diastereomer,
  and it matches the syn reference P_syn_ref (also both-S). [CIP descriptor is intrinsic; file atom-index
  labels differ between files, so only the descriptor identity, not the index, was used.]
- Connectivity argument: first-order saddle + reactive (C1-O8/C3-C5) imaginary mode + bidirectional IRC
  interval evidence + frequency-verified endpoint minima with the intended identities = verified connectivity
  (IRC itself did not reach the minima within 30 steps).

Barriers (electronic, 0 K, gas; kcal/mol):
- Delta-E-ddagger (TS - R_ref21) = +26.25   [the "same-version 26.25" reviewed here]
- Delta-E-ddagger (TS - ep_F40)  = +26.04   [ep_F is the IRC-connected reactive conformer, 0.21 above R_ref]
- Delta-E(reaction) (ep_B40 - ep_F40) = -14.08

SELECTIVITY-CONFLICT REVIEW (no graph/source change made):
- Gold source: syn channel E1 "boat_ts" barrier 29.67, favored=false; anti channel EM1 "chair_ts" barrier 26.39,
  favored=true. The old verified anti saddles in the record (chair 30.943, boat 34.753) were computed with
  Gaussian b3lyp/def2svp WITHOUT explicit D3BJ -> a DIFFERENT method AND a different reference frame
  (record R_ext -348.89195). They therefore CANNOT be compared numerically to the ORCA 6.1.1 results.
- Consequently the new syn value (26.04-26.25) must NOT be read against the historical 29.67/26.39 or against
  the old 30.943 anti value: no same-method anti number exists on this filesystem (old Gaussian geometries absent).
- Handling proposed (NOT executed): (a) record the new syn saddle as an independent ORCA 6.1.1 gas-phase result;
  (b) make NO change to the task-source graph/favored flags; (c) a valid syn-vs-anti selectivity statement
  requires re-deriving the anti saddle at ORCA 6.1.1 - a new calculation and a scope decision for the human.
Reported to hub; escalated to the human for the selectivity/scope decision.

## 9. Pass 4 — ANTI channel at the SAME method (ORCA 6.1.1). Coordinator's independent review.
Model fixed & unchanged: gas, charge 0, mult 1, B3LYP D3BJ def2-SVP def2/J RIJCOSX TightSCF, ORCA 6.1.1.
Legacy anti-TS geometries (from the local gold archive) were reused as GEOMETRY seeds only; no Gaussian energies mixed.

Self-consistent ORCA 6.1.1 energies (Ha):
- R_ref (job 21)                       = -348.690242146502   (reactant global min, 0 imag)
- syn TS (jobs 4/3/28, one saddle)     = -348.648414103477   (1 imag -403.5; syn channel)
- anti TS (job 53, legacy chair seed)  = -348.648202350340   (1 imag -403.27; anti channel)
- syn endpoints: reactant (job 40) -348.689907922178 ; product (job 41) -348.712340359576
- anti endpoints: reactant (job 57) -348.688498440674 ; product (job 56) -348.710408259292

Independent checks performed by the coordinator (raw logs + geometries):
1) Reaction centre identical, same species: syn TS breaks C1-O8 / forms C3-C5 (syn-grid order) = anti TS breaks C4-O5 /
   forms C2-C7 (R order) — same two carbons/oxygen, same [3,3]-Claisen. Anti TS imaginary mode top pairs (1-based):
   (4,5)=0.853 breaking, (2,7)=0.739 forming -> REACTIVE mode, not torsional.
2) Ring conformation (6-membered pseudo-ring torsions):
   anti TS ring O5-C4-C3-C2-C7-C6: [+70.9, -71.2, +54.1, -71.5, +78.4, -55.1]
   syn  TS ring O8-C1-C2-C3-C5-C7: [+68.2, -72.5, +60.2, -78.4, +81.1, -50.0]
   BOTH are alternating => BOTH are CHAIR-like. The source descriptors syn=boat_ts / anti=chair_ts are NOT supported.
3) Product CIP (RDKit on optimized endpoints): syn product both centres SAME (S,S) = syn; anti product MIXED (S,R) = anti.
   Reactant endpoints achiral. Confirms the two channels are the two diastereomers, NOT chair-vs-boat.

Barriers (electronic, 0 K, gas; kcal/mol) — reference-dependent:
- vs common R_ref:  syn 26.25  vs  anti 26.38  => |Delta| 0.13 (syn marginally lower)
- vs each channel's own IRC reactant conformer: syn 26.04 (ep40) vs anti 25.29 (ep57) => anti marginally lower
  (the two IRC reactant endpoints differ by 0.88 kcal/mol; the anti one is higher). => near-degenerate, NO selectivity claim.

Channel/label correction (per actual geometry; graph EDGES/CONNECTIVITY UNCHANGED):
- Both existing edges (R->syn and R->anti) stand. Correct TEXT/labels only: the two saddles are
  "chair-like TS (syn channel)" and "chair-like TS (anti channel)"; the old chair/boat wording is contradicted.
- Source barriers 29.67 (syn) / 26.39 (anti), spread 3.28, were a different method/frame; superseded by the
  same-method 26.25 / 26.38 (spread 0.13, context only). At this method the two channels are near-degenerate;
  do NOT assert anti favoured.

LIMITED-EVIDENCE CAVEATS (for the supervisor's backfill summary):
- Barriers are electronic only (no ZPE/thermal Gibbs); with a ~0.1 kcal/mol electronic gap, ZPE/entropy could flip the order.
- IRC jobs terminated normally but hit their native iteration caps (syn 30 steps each way; anti default cap);
  connectivity rests on first-order TS + reactive mode + bidirectional IRC interval + frequency-verified endpoint minima.
- Legacy seed reused as geometry only; original Gaussian numbers (30.943/34.753) are not comparable and were not used.
- Not a benchmark; task-source graph/spec not edited here (handled by the isolated copy).

## 10. CRITICAL CORRECTION (2026-10-01) — substrate alkene E/Z; the "E,E syn" claim is RETRACTED
Independent coordinate-based E/Z assignment (C=C bond lengths + heavy-substituent dihedrals), consistent with the
supervisor's RDKit C/C=C... canonical SMILES:
- job21 R_ref:  C2=C3 178 deg E ; C6=C7 -180 deg E  -> (E,E)  [declared substrate]
- job57 anti rc: both E -> (E,E)
- job53 anti TS: both E -> (E,E)
- job40 syn rc (IRC forward endpoint): C2=C3 179 deg E ; C5=C7 -2 deg Z -> (E,Z)   <-- NOT E,E
- job4 syn TS: C2=C3 -179 deg E ; C5=C7 21 deg Z -> built on the (E,Z) substrate
- syn-channel IRC forward frames already show C5=C7 ~16-18 deg (Z) from the first frame.
CONSEQUENCE:
- RETRACTED: (i) TS4 - R_ref21 = 26.25 kcal/mol as the (E,E)-syn gold barrier; (ii) the syn-vs-anti 0.13 kcal/mol
  near-degeneracy and any reversed-favoured statement (they compared an (E,Z)-syn TS against an (E,E)-anti TS).
- RETAINED & comparable: the ANTI channel is (E,E) throughout: TS53 (E,E) - R_ref21 (E,E) = 26.38 kcal/mol.
- RETAINED as a SEPARATE result (not gold): the (E,Z)-substrate syn saddle + endpoints (jobs 4/40/41) = "E,Z -> syn" evidence.
- Root cause: the syn seeds came from constrained xTB scans that altered the vinyl C=C geometry (E -> Z); substrate E/Z
  was not validated at seed time. LESSON: validate BOTH alkene E/Z at seed AND at each endpoint, per channel.
NEXT (authorized scope): look for a genuine (E,E)-substrate saddle leading to syn, seeded from existing constrained
geometries with BOTH alkenes pinned E/E and the same covalent skeleton/atom mapping; verify both-side TS geometry
before any formal 8-core submission; if no valid candidate exists in scope, report a GAP rather than mix substrates
or fit the old 29.67. No re-run of the (correct) anti channel; no filler boat.
NOTE: section 9's near-degeneracy wording is superseded by this section.

## 11. (E,E)->syn search — RESULT: HONEST GAP (2026-10-01). Coordinator's independent review.
Executor artifact: paratera_20260930/HG2_EE_to_syn_GAP.md (+ ee_syn_explore/xtb_ee_scan/).
Policy-compliant: standalone xTB (GFN2), xtb --opt engine defaults, NO self-set timeout/iteration; raw logs kept.

Independent verification (coordinator):
- ts/interp_syn/img_00.xyz = (E,E) [dih 1-2-3-4 = -180, 5-6-7-8 = 180; d(C2..C7)=5.32 A]; img_16 = syn product CIP (S,S).
  So the IDPP ENDPOINTS are E,E(reactant) -> syn(product), but the raw IDPP path is unphysical (~+300 kcal/mol mid-path).
- Constrained xTB scan from img_00 holding BOTH E dihedrals (1-2-3-4=180, 5-6-7-8=180) and driving d(C2-C7) 3.4->1.9 A:
  frames 3.4/2.0 A re-verified E,E (dihedrals ~180; C=C ~1.32-1.36 A), energy rises monotonically to a max near 2.0 A
  (~+21.7 kcal/mol vs 3.4 A). The final frame (1.9 A) has C=C relaxed to 1.49 A (alkenes no longer intact) and
  RDKit CIP C2:R, C7:S = MIXED = ANTI.
=> Driving the (E,E) substrate along this coordinate collapses to ANTI, consistent with the verified (E,E) chair
   saddle (job53 -> job57 -> job56 anti). No (E,E)->syn saddle was found.

FINAL STATUS (this scope/method):
- valid: anti 26.38 kcal/mol (E,E -> anti; TS53 - R_ref21, both E,E).
- syn = NULL (missing measurement): no located E,E->syn saddle at ORCA 6.1.1 gas in this scope.
- the only located syn saddle (job4) is on the (E,Z) substrate -> retained ONLY as separate-substrate supporting evidence.
CAVEATS (must travel with any use of this result):
- A single constrained 1D closure (and the chair outcome) does NOT prove that an (E,E)->syn saddle is mathematically
  absent; the source expects syn via a BOAT TS, and a boat-region E,E search was not performed in this scope.
- All numbers are electronic (no ZPE/G), gas, single method; not a benchmark; source/TaskSpec handled elsewhere.
=> Close this round with the honest GAP; no endless scanning, no re-run of the correct anti channel, no filler jobs.


