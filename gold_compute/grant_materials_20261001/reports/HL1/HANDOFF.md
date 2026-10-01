# HL1 HANDOFF (final — this pass)

## Goal
Hard-gold audit/backfill of **HL1 = acid-catalyzed Beckmann rearrangement of (E)-butanone oxime** (gas phase).
Spec: `/public/home/yyywaa/cloudra/ideapool/tasks/hard/HL1.json`. Fixed method: ORCA 5.0.2 gas
`! B3LYP D3BJ def2-SVP def2/J RIJCOSX` (+TightSCF; TS + %geom Calc_Hess true); ΔE‡ pure electronic, ×627.5095.

## Outcome (one line)
Audit complete; the ONE still-scoring edge that can be resolved independently, **E5 (imidic-acid -> amide 1,3-H shift)**,
was resolved: **ΔE‡ = 28.46 kcal/mol** (isolated imidic-acid frame, 1-imag TS, IRC both ways, endpoint minima freq-verified).
E1/E2/E3/E4 documented; the graph's I3/I4 are non-existent minima -> a graph decision is required (see REPORT §4).
**No benchmark source edited / committed / pushed.**

## Key numbers (fixed method, gas phase)
- E5 reactant minimum (imidic acid, pre-organized O-H...N): **E = -287.449228685 Ha, 0 imag**  [job 640]
- E5 product minimum (amide global): **E = -287.474105508 Ha, 0 imag**  [job 629]; IRC-side amide conformer [job 642] -287.471026078
- **E5 TS: E = -287.403878135 Ha, exactly 1 imag = -1878.54 cm-1** (H-transfer mode O3-H10/N4-H10)  [job 637]
- **ΔE‡(E5) = 0.045350550 Ha = 28.46 kcal/mol** ; reverse = 44.07 ; tautomerization exothermic 15.61
- E5(28.46) > E2(23.13): if adopted, RDS moves from E2 to E5.
- NB: an earlier anti-OH local minimum (-287.44576, jobs 628/633/636) is 2.18 kcal HIGHER; the correct reference is the IRC-verified -287.44923.

## Edge verdicts
E1 = barrierless PT (0.0 honest, NOT a saddle). E2 = 23.13, TS 1-imag -304.17 but IRC connectivity only partial;
raw log GONE -> not re-run. E3/E4 = declared I3/I4 are not minima at this level -> not resolvable as declared.
E5 = RESOLVED (above).

## Prior inventory (for provenance)
- gold graph barriers: E1=0.0, E2=23.13, E3=null, E4=0.0, E5=null; nodes I1..I4 as in spec.
- prior compute IDs: calc-528(E2 TS -304.17), calc-531(E1 rejected), calc-529(E5 rejected), calc-645(E3m rejected).
- prior raw logs at gold_compute/campaign/runs/HL1/**/.cloudra/ -> **ABSENT** (never committed). Only archive/*.md survive.

## Jobs this pass (all ORCA gas fixed method; logs HL1_gold_20260929/dft/<name>/.cloudra/calc-<id>.out.log)
628 imidic(anti) -> 1 imag (superseded) | 629 amide min | 633 tightopt -> still 1 imag | 634 OptTS v1 FAILED (cap)
635 constrained bridged seed | 636 imidic rot+20 -> 0 imag (higher local min) | **637 E5 OptTS v2 -> 1 imag -1878.54**
638 IRC v1 FAILED (%irc syntax) | **639 IRC both converged** | **640 imidic min** | 641 ep_B FAILED (cap) | **642 amide**

## Environment lessons (reusable)
- ORCA %irc needs `InitHess read` + `Hess_Filename "<abs .hess>"` + `MaxIter N`; **`InitHess calc` is invalid** in ORCA 5.0.2.
- OptTS/opt can hit the default cycle cap; use `%geom MaxIter 300` (and/or a constrained bridged seed) — a plain IDPP peak
  seed walked downhill.
- A 1,3-H-shift TS seed is best made by constraining d(O-H) and d(N-H) equal and pre-relaxing, then unconstrained OptTS.
- floppy OH rotors give tiny imaginary modes even after TightOpt; the true minimum may need a rotated start.
- xtb (local `/public/home/yyywaa/.local/bin/xtb`) works for cheap rotamer/path profiling.

## Files
- REPORT.md (this pass, full), HANDOFF.md (this)


=====================================================================
## PHASE 2 (2026-09-30) — revised graph: E3 = I2 -> P, barrier null
=====================================================================
Graph revised at cloudra commit 77f671b (doc _src/hard_swap_2026-09-30.md). New nodes: R, I1, I2=O.O.CC#[N+]CC,
P=[OH3+].CCNC(C)=O. Edges: E1 null, E2 23.13 (kept), **E3 = I2->P net hydration/proton-relay, barrier null**.
Question: is there ONE physically meaningful unconstrained saddle I2->P at the fixed method, with E(I2) reference?

### Prior jobs inventory: my session jobs 628-642 (Phase 1, unchanged); old campaign logs absent. No duplicates used.

### Cheap path work (this phase)
- conformer_search assembled I2 (14 confs) and P (3 confs); GFN2 ohess -> both are GFN2 minima (0 imaginary).
  I2 GFN2 E=-25.124176 Eh; P GFN2 E=-25.307304 Eh (net exothermic ~115 kcal).
- ts_prepare run ts_0001 (workspace HL1_gold_20260929/tsprepare_E3): declared b3lyp/def2svp+orca gas.
  stage map blocked -> supplied FULL atom_map (product order, ORCA 0-based)
  [3,4,5,2,10,9,8,7,6,0,16,17,18,14,15,1,11,12,13] -> accepted ("19 atoms mapped, element-consistent").
  stage assemble blocked -> supplied reaction_center [[0,7],[1,8],[2,3],[7,8]] -> accepted.
  stage guess BLOCKED: xTB path search incomplete_artifacts (known env issue); 24 partial frames.
  xTB $path stdout: run1 barrier 13.76 kcal/dE -99.2 but later runs collapsed (barrier 0, "No product!").
- ts_guess interpolate (idpp, 15 frames) between the built endpoints: clean distance progression
  O1-C8 3.55->1.24, H2-N9 2.27->1.02, H3-O4 3.51->0.99, C8-N9 1.46->1.37. GFN2 SP profile peaks at img_08
  (barrier 179 kcal UNRELAXED -> upper bound only, not meaningful).

### DFT jobs (this phase): 643 = ORCA opt+freq I2 min, 644 = ORCA opt+freq P min (fixed method, charge +1).
NEXT: parse 643/644; then seed an unconstrained OptTS (IDPP midpoint/constrained bridge) at the fixed method;
IRC both ways; if OptTS falls to a minimum / no single saddle -> document multi-step evidence and ask adjudication.
DO NOT apply Phase-1 isolated-imidic-acid 28.46 to this edge.

### DFT endpoint minima (fixed method, charge +1) — PHASE 2
- I2 minimum: job 648 (E3_I2b), E=-364.137562560 Ha, **0 imag** (floppy; needed MaxIter 400). [643 first attempt hit cap, 648 ok]
- P minimum: job 644 (E3_P), E=-364.193809799 Ha, **0 imag**.
- Net dE(I2->P) = -0.056247239 Ha = **-35.3 kcal/mol** (gas, fixed method; GFN2 overestimated at ~-99).
- TS seed job 649 (constrained Opt: d(O1-C8)=2.0, d(H2-N9)=1.35, d(H3-O4)=1.35) -> opt hit cap but geometry held (seed.xyz).
### job 653 = ORCA OptTS + Freq (Calc_Hess, MaxIter 300) from that seed. RUNNING.
NEXT: parse 653 (expect 1 imag?); if 1 imag -> IRC both ways -> endpoint re-opts -> dE#=E(TS)-E(I2 min).
If it collapses to a minimum / multi-imag -> no single saddle -> document + adjudicate.

### PHASE 2b (2026-09-30, later) — status
- job 653 (OPTTS from constrained seed) FAILED: hit MaxIter 300, ORCA aborted (slurm FAILED).
  Final frame: O1-C8 opened back to 2.82 A, H transferred to N, 3 fragments -> non-productive drift,
  NOT a saddle. Seed had the C-O/H-N/H-O constraints on the *wrong* (far) water of the I2 minimum.
- IMPORTANT (P identity caveat): the geometry labelled "P minimum" (job 644, E3_P) is really the
  O-protonated amide + water ion pair ([CH3C(OH)(NH-Et)]+ ... OH2, O9-H1=1.015 A, O0-H1=1.56 A),
  NOT the declared P [OH3+].CCNC(C)=O. Its ORCA input already had the proton on the amide O.
  Need to test whether the declared H3O+ + amide arrangement is a minimum at the fixed method.
  Input prepared: dft/E3_Pdecl/E3_Pdecl.inp (from the true product assembly with H on the hydronium O),
  NOT yet submitted (waiting for a free 4-core slot).
- xTB GFN2 relaxed scan (xtb/scan_co, 1-based constraint "distance: 4, 8, v"): from the DFT I2 minimum,
  C8-O4 from 3.6 -> 1.3 A: energy falls to a plateau (-25.2841 at 2.6-2.8) then RISES as C-O is forced
  shorter (-25.2756 at 1.40, -25.2630 at 1.30); NO proton transfer (O1-H2 stays 0.96, N9-H2 stays ~4.9).
  => no barrier for the C-O approach, but also no stable covalent C-O intermediate without PT.
- xTB GFN2 2D grid (xtb/scan2d, C8-O4 x N9-H5): forcing the N-H transfer costs >= 40 kcal, proton
  never transfers -> no low-energy concerted path at GFN2.
- ORCA inputs/route for xTB scan: xTB 1-based indices; ORCA Scan syntax is "Scan B i j = start, end, nsteps end"
  (explicit value lists are REJECTED: "Expecting Coordinate type B(ond)..." -> job 662 failed).
- job 663 = ORCA constrained pre-opt from the DFT I2 minimum with the CORRECT water:
  {B 3 7 2.10 C} (O4-C8), {B 4 8 1.40 C} (H5-N9), {B 0 5 1.25 C} (H6-O1). RUNNING.
- job 664 = ORCA relaxed scan C8-O4 (3.10 -> 1.35, 9 pts) from the DFT I2 minimum (E3_scanCO2). RUNNING.
NEXT: parse 663/664; if the scan has an internal maximum -> OptTS from that frame.
Then submit E3_Pdecl to settle whether the declared P is a minimum.
### PHASE 2c - DFT results (fixed method, gas, ORCA 5.0.2 B3LYP-D3BJ/def2-SVP+def2/J RIJCOSX)
- **job 664 = ORCA RELAXED SCAN along d(C8-O4) from the I2 minimum (E3_scanCO2). NORMAL TERMINATION.**
  Actual-energy profile (Ha), scan coordinate C8-O4 (A):
    3.100 -364.13599 | 2.881 -364.13668 | 2.663 -364.13755 (MIN = job648 I2 min) | 2.444 -364.13675 |
    2.225 -364.13369 | 2.006 -364.12872 | 1.788 -364.12445 | 1.569 -364.12146 | 1.350 -364.10999
  => relative (kcal/mol vs 2.663): 0, +0.5, 0, +0.5, +2.4, +5.5, +8.2, +10.1, +17.3.
  **THE C8-O4 COORDINATE IS PURELY REPULSIVE FROM THE I2 MINIMUM: no maximum, no second well, no
  covalent C-O intermediate. The nitrilium-water C-O bond cannot form without coupled proton motion.**
  (ORCA log has no ts_guess-parseable Summary table; extract the table by hand.)
- job 663 = constrained pre-opt with THREE constraints {B 3 7 2.10},{B 4 8 1.40},{B 0 5 1.25} (the third
  forces H6 of the attacking water onto the spectator water): E = -364.048514626 Ha = **+55.9 kcal above I2**.
  Too strained to be a TS seed -> the third constraint was chemically unnecessary (see mechanism note).
- MECHANISM NOTE (corrected): the true minimum product we found (job 644) is the O-protonated amide +
  water; the net I2 -> that product needs only (i) C8-O4 bond formation and (ii) ONE proton transfer
  H5(O4) -> N9. The second water is a spectator. So a concerted TS should be seeded with only TWO
  constraints, not three.
- job 666 = ORCA constrained pre-opt with only {B 3 7 2.00 C},{B 4 8 1.45 C} (E3_seed3). RUNNING.
- job 665 = ORCA Opt+Freq of the TRUE product assembly [OH3+ ... amide] (E3_Pdecl) - tests whether the
  declared P [OH3+].CCNC(C)=O is a stationary minimum at the fixed method. RUNNING.
  (GFN2 preview: the H3O+ proton transfers to the amide O during optimization -> declared P not a
  GFN2 minimum either.)
### PHASE 2d - DECLARED P IS NOT A MINIMUM (key finding, fixed method)
- job 665 (E3_Pdecl) started from the TRUE product assembly [H3O+ ... amide] (O1-H2=1.012, O1...O10=2.433)
  and converged normally: **E = -364.193788877 Ha, 0 imaginary (51 freqs)**. BUT the optimized geometry
  has O1-H2 = 1.561 A and O2...H10 = 1.017 A, i.e. THE PROTON MOVED FROM THE HYDROXONIUM ONTO THE
  AMIDE OXYGEN. Same minimum as job 644 (-364.193809799, 0 imag), i.e. the O-protonated amide + water
  ion pair. => **the declared P node [OH3+].CCNC(C)=O is NOT a free stationary minimum at the fixed
  method; the true minimum is [CH3C(OH)(NH-Et)]+ ... OH2.** (GFN2 gives the same proton transfer.)
  Consequence: the E3 edge as declared (I2 -> P) has no valid free-minimum P endpoint.
  Working P reference used: E = -364.193788877 Ha (job 665, 0 imag) [= job 644 -364.193809799].
  dE(I2 -> P_true) = -364.193788877 - (-364.137562560) = -0.056226317 Ha = -35.28 kcal/mol.
- job 666 (E3_seed3, constrained {B 3 7 2.00},{B 4 8 1.45} only): E = -364.073000574956 Ha = +40.5 kcal
  above the I2 minimum. Geometry is a proper bridged motif: O4-C8 2.000, N9-H5 1.450, O4-H5 1.022,
  O1-H6 1.727 (spectator water H-bonded). Usable as a concerted-TS seed.
- job 669 = ORCA OptTS+Freq (Calc_Hess, MaxIter 300) from E3_seed3.xyz (E3_TS2). RUNNING.
- job 670 = ORCA relaxed scan along N9-H5 (3.20 -> 1.10, 8 pts) with C8-O4 held at 2.00 (E3_scanNH).
  RUNNING. Maps the proton-transfer cut at a plausible TS C-O distance.
### PHASE 2e - A REAL FIRST-ORDER SADDLE FOUND (job 669), but its identity is the question
- **job 669 = ORCA OptTS+Freq from E3_seed3: NORMAL TERMINATION, CONVERGED, exactly 1 imaginary
  frequency = -214.5 cm-1. E(TS) = -364.120930791701 Ha.**
  dE relative to the I2 minimum = -364.120930792 + 364.137562560 = +0.016631768 Ha = **+10.44 kcal/mol**.
  Lowest real frequencies +26.7, +38.2, +86.8 cm-1 (soft floppy modes, but only ONE imaginary).
  TS geometry (0-based labels of E3_I2b order): O4-C8 = 1.818 A (C-O forming), C8-N9 = 1.185,
  N9-H5 = 2.566 (H5 NOT transferred), O4-H5 = 0.972, O4-H6 = 1.010, O1-H6 = 1.590, O4...O1 = 2.589.
  => the imaginary mode is **C-O bond formation coupled with the H6 proton moving from the attacking
  water O4 toward the spectator water O1** (shared H6: 1.010 to O4 / 1.590 to O1). N9 does NOT gain
  an H at this saddle, so this saddle alone does not deliver the amide N-H.
  NOTE: the seed (job 666) had H5 constrained toward N9, yet the OptTS relaxed into the H6->O1 mode.
- job 670 = relaxed scan N9-H5 at C8-O4=2.00 FAILED: ORCA 'BLAS-ERROR / INCOMPATIBLE MATRICES' in
  orca_gstep (Scan + Constraints combined is not usable here). Do not retry that combination.
- job 671 = ORCA IRC (InitHess read from E3_TS2.hess, Direction both, MaxIter 40) from the 669 saddle. RUNNING.
  This is the decisive test of whether the saddle connects I2 to anything new.
- job 672 = ORCA constrained pre-opt with {B 3 7 2.00 C},{B 5 8 1.45 C} (H6 -> N9 instead of H5 -> N9). RUNNING.
### PHASE 2f - IRC of the 669 saddle (job 671) and seed4 (job 672)
- job 671 IRC (InitHess read, Direction both, MaxIter 40): NORMAL TERMINATION but hit the iteration cap
  (40 forward / 29 backward points, irc_both_directions_converged=false). Endpoint energies
  [-364.126076 (F), -364.125782 (B)] vs E(TS) = -364.120931 -> only ~3.2 kcal below the saddle;
  the path is flat and still far (10.4 kcal) above the I2 minimum. NOT a converged IRC.
  Endpoint geometries (0-based E3_I2b labelling):
    F: O4-C8 2.173, C8-N9 1.160, O1-H6 1.709, O4-H6 0.988  -> moving BACK toward the I2 minimum
       (I2 min: O4-C8 2.637, C8-N9 1.150, O1-H6 1.858).
    B: O4-C8 1.529, C8-N9 1.228, O1-H6 1.444, O4-H6 1.053  -> C-O formed further and H6 shared more
       with O1; NO N-H (N9-H5 2.252).
  => the 669 saddle is a **C8-O4 bond-formation saddle coupled to the H6 proton moving from the
     attacking water to the spectator water**; its product side is an imidic-acid/H3O+-like species,
     NOT the amide (no N-H). It may connect I2 only to a non-minimum (I4-like) region.
- job 672 seed4 {B 3 7 2.00},{B 5 8 1.45} (H6 -> N9): E = -364.072763334676 Ha = +40.7 kcal above I2.
  (seed3 with H5 -> N9 was +40.5 kcal.) Both H-transfer arrangements are equally strained -> not decisive.
- job 673 = ORCA Opt+Freq of the IRC forward frame (E3_epF) - expect the I2 minimum. RUNNING.
- job 674 = ORCA Opt+Freq of the IRC backward frame (E3_epB) - tells whether the saddle's product side
  is a genuine minimum and which one. RUNNING.
### PHASE 2g - INFRASTRUCTURE + endpoint re-opt
- **Slurm new-job submission is BROKEN for this session: `sbatch: error: Account has been disabled /
  Batch job submission failed: Operation not permitted`.** Affected: jobs 673,674,675,676,679. Retried
  several times over ~40 min - same error. Already-running jobs by the same user (630/651/668) continue.
  Reported to the coordinator: agent_hub post evt_6937db5b939647bf (topic 'gold compute - infrastructure').
- Workaround: `submit_compute_job(..., execution_backend='local')`. The login node has only 2 cores
  (`nproc` = 2), so: 4 cores -> 'not enough slots' (jobs 677,678); 2 cores -> also 'not enough slots'
  (job 680); **nprocs=1 serial works** (job 681).
- job 680 (epB, local, 2 cores) FAILED - OpenMPI slots, not ORCA.
- **job 681 = ORCA opt+freq of the IRC-B frame, %pal nprocs 1, local backend. RUNNING** (serial, slow).
  Purpose: determine whether the job-669 saddle's product side descends to the true product minimum
  (O-protonated amide + water, -364.193788877) or back to I2 / a non-minimum.
- epF (forward frame) NOT yet re-optimized - expected trivially to be the I2 minimum.

### STATUS OF THE DELIVERABLE
REPORT.md now carries the full PHASE 2 section (inventory, stationary points, evidence, verdict,
job ledger). The verdict as written: no validated single unconstrained saddle I2 -> declared P,
because (a) the declared P is not a free minimum and (b) the C8-O4 attack coordinate is repulsive;
one genuine first-order saddle was found (job 669, 1 imag -214.5 cm-1, +10.44 kcal/mol vs I2) whose
mode is C-O formation + a proton relay to the spectator water (no N-H), implying a further step.
Adjudication is requested from the graph owner; job 681 refines the product-side assignment.
### PHASE 2h - DECISIVE RESULT: the 669 saddle connects I2 to a NEW genuine intermediate I3'
- **job 681** (IRC-B frame re-opt, serial local, NORMAL TERMINATION, CONVERGED):
  **E = -364.128155679 Ha, 0 imaginary (51 freqs)** - a GENUINE MINIMUM.
  Geometry: O4-C8 = 1.493 (C-O formed), C8-N9 = 1.236, O4-H5 = 0.981, O4-H6 = 1.069,
  O1-H6 = 1.399, N9-H5 = 2.246 (NO N-H), O1...O4 shared proton.
  Identity: **[CH3-C(OH2+)=N-Et] ... OH2 = the O-protonated imidic acid + water, i.e. the graph's
  old I3 composition - and it IS a free minimum at the fixed method (contradicts the prior campaign's
  'I3 relaxes to I2' claim for this conformer).**
- Energy ladder vs the I2 minimum (job 648, -364.137562560):
    I2   -364.137562560   (0.0)         nitrilium + 2 H2O
    TS   -364.120930792   (+10.44)      1 imag -214.5 cm-1   (job 669)
    I3'  -364.128155679   ( +5.90)      O-protonated imidic acid + water, 0 imag  (job 681)
    P    -364.193788877   (-35.28)      O-protonated amide + water, 0 imag  (jobs 644/665)
  => the 669 saddle sits BETWEEN I2 and I3': forward dE# = +10.44 kcal/mol, reverse = +4.54 kcal/mol.
  The IRC-backward frame descended to I3'; the IRC-forward frame heads back toward I2.
- CONSEQUENCE FOR THE GRAPH: the net I2 -> P transformation is **NOT a single elementary step**:
  it passes through at least one genuine intermediate (I3', the O-protonated imidic acid + water),
  and the remaining I3' -> P part is a 1,3-H (O->N) tautomerization requiring a second saddle
  (the E5-analogue, cf. the 28.46 kcal/mol isolated-imidic-acid result of Phase 1).
- job 682 = ORCA opt+freq of the IRC-F frame (serial local) - should confirm the I2 minimum. RUNNING.
NEXT: parse 682; then (a) retry Slurm, (b) try the second saddle I3' -> P (1,3-H shift, H from O4 to N9).
IMPORTANT: prior-campaign Hartree values (computed_HL1.json: I2 basin -364.3293) are ~0.19 Ha BELOW our
ORCA fixed-method values (I2 -364.1376) — do NOT mix the two campaigns; use only this session's numbers.

, _src/ (read-only benchmark copies), build/, xtb/, dft/ (all inputs+logs).

=====================================================================
## PHASE 3 (2026-09-30) - new server paratera-cpu, ORCA 6.1.1; I3prime->P proton-transfer search
=====================================================================
Engine change: OLD = ORCA 5.0.2 (all Phase 1/2 numbers above). NEW = ORCA 6.1.1 on paratera-cpu
(LOCAL node, 32 cpu / 56000 MB, max 8 jobs). Model/route UNCHANGED: gas phase, B3LYP D3BJ def2-SVP
def2/J RIJCOSX TightSCF, charge +1, multiplicity 1. Do NOT mix ORCA5 and ORCA6 Hartree values;
all new barriers must be computed consistently at 6.1.1. Old numbers are context only.
Work dir for new jobs: HL1_gold_20260929/paratera_20260930/ (old evidence NOT overwritten).

### Target (unfinished search, per task)
I3prime (O-protonated imidic acid + water, job681 ORCA5) -> P (O-protonated amide + water, jobs644/665)
= O4-H5 -> N9 1,3-H (O->N) proton transfer. A SECOND saddle after the job669 I2->I3prime saddle.

### Substrate geometry reused (migrated, ORCA5 minimum, 0 imag)
I3prime = dft/E3_epB2/E3_epB2.xyz ; atom order (1-based): 4=O4, 5=H5(proton to move), 6=H6, 9=N9, 8=C8.
d(O4-H5)=0.981, d(N9-H5)=2.246, d(O4-C8)=1.493, d(C8-N9)=1.236.

### Jobs submitted this phase (all ORCA 6.1.1, gas, paratera-cpu, local backend, cpus=4, mem=7000)
- job 9  = I3p_min_ORCA6 : Opt+Freq from E3_epB2.xyz (new-version I3prime reference). RUNNING
- job 10 = I3p_hts_seed  : constrained Opt, {B 4 5 1.25 C},{B 5 9 1.25 C} (O4-H5...N9 seed). RUNNING

### Queued (inputs pre-built, submit on freed slots; 2-active-per-topic budget)
- Pmin_ORCA6  : Opt+Freq from dft/E3_P/E3_P.xyz (new-version P reference).
- TS669_ORCA6 : OptTS+Freq (Calc_Hess, MaxIter 300) from dft/E3_TS2/E3_TS2.xyz (I2->I3prime refine).
- I2min_ORCA6 : Opt+Freq from dft/E3_I2b/E3_I2b.xyz (new-version I2 reference).
NEXT after job 10: OptTS+Freq(I3prime->P) from the constrained seed -> 1 imag -> IRC both ways ->
endpoint re-opts (expect I3prime and P) -> dE# = E(TS)-E(I3prime) at 6.1.1.

### Infra notes (do not repeat)
- HE3 (solvated) jobs FAIL with ORCA6 MPI 'MPI_Type_match_size' in the CPCM Cholesky step; HL1 is GAS
  PHASE and does not hit that path (jobs 9/10 progressing normally, 4 MPI procs).
- Old Slurm IDs on the retired server are dead; never poll/resubmit them.
- Do NOT retry the combined Scan+Constraints ORCA setup (job670 BLAS error).
- All new inputs carry a smiles: comment line for scorer evidence binding.
- No mechanism_graph.json / task-source edits made (awaiting authorization).

### PHASE 3a - first ORCA 6.1.1 result (job 9 DONE)
**job 9 = I3prime minimum at ORCA 6.1.1: E = -364.128159827 Ha, NORMAL TERMINATION, CONVERGED, 0 imag (57 freqs).**
Engine-consistency check: ORCA5 job681 gave -364.128155679 -> difference 4e-6 Ha = 0.003 kcal/mol; the
engine upgrade is negligible for this minimum, so ORCA5 and ORCA6 references are numerically interchangeable
here. (Still record engine provenance explicitly; do not mix in one arithmetic chain without noting version.)

### PHASE 3b - slot refills (task wants the 8-job pool used)
- job 16 = Pmin_ORCA6  : Opt+Freq from dft/E3_P/E3_P.xyz (new-version P reference). SUBMITTED/RUNNING
- job 17 = TS669_ORCA6 : OptTS+Freq (Calc_Hess) from dft/E3_TS2/E3_TS2.xyz (I2->I3prime saddle refine). SUBMITTED/RUNNING
  (job 17 borrowed one global slot because the pool had a free slot; HL1 thus has 3 active - within the 8-cap.
   Will release back to <=2 as soon as the I3prime->P OptTS can start.)
- job 10 = I3p_hts_seed: still RUNNING (constrained seed for the I3prime->P 1,3-H transfer).

### NEXT on each terminal notification
1) job 10 done -> OptTS+Freq(I3prime->P) from the seed (new job), then IRC both ways + endpoint Opt/Freq.
2) job 16 done -> E(P)_ORCA6;  3) job 17 done -> E(TS669)_ORCA6 (+1 imag check).
4) Still queued: I2min_ORCA6 (from E3_I2b.xyz). Then assemble the full ORCA6 ladder
   I2 -> TS669 -> I3prime -> TS(I3prime->P) -> P with consistent 6.1.1 numbers.

### PHASE 3c - more ORCA 6.1.1 results (jobs 16, 17 DONE)
Both NORMAL TERMINATION + CONVERGED at ORCA 6.1.1:
- job 16 Pmin_ORCA6  : E = -364.193803774 Ha, 0 imag (57 freqs). ORCA5 job665 = -364.193788877 (delta 0.0093 kcal/mol).
- job 17 TS669_ORCA6 : E = -364.120933530 Ha, exactly 1 imag = -213.61 cm-1. ORCA5 job669 = -364.120930792, 1 imag -214.5
                      (delta 0.0017 kcal/mol). Saddle identity confirmed at 6.1.1 (C-O formation + proton relay).

ORCA 6.1.1 ladder so far (all gas, B3LYP-D3BJ/def2-SVP+def2/J RIJCOSX TightSCF, charge +1):
   I2   = PENDING (job 30)
   TS669= -364.120933530   (1 imag -213.61)
   I3p  = -364.128159827   (0 imag, job 9)
   P    = -364.193803774   (0 imag, job 16)
   DeltaE_rxn(I3p->P) = E(P)-E(I3p) = -0.065643947 Ha = -41.19 kcal/mol
        >>> THIS IS THE NET REACTION ENERGY, NOT AN ACTIVATION BARRIER. Do NOT put it in any barrier field.
            The I3p->P activation barrier is still UNSOUGHT (needs the OptTS+Freq from the job-10 seed).
            Only TS->reference electronic differences are barriers, e.g. the next line.
   TS669 vs I3p: E(TS)-E(I3p) = +0.007226297 Ha = +4.53 kcal/mol (reverse of the I2->I3p step)

### PHASE 3d - queued HL1 jobs (pool saturated 0/8; queued, not running yet)
- job 30 = I2min_ORCA6   : Opt+Freq from dft/E3_I2b.xyz (new-version I2 reference) - QUEUED
- job 31 = TS669_IRC_ORCA6: IRC Direction both, InitHess read (TS669_ORCA6.hess), MaxIter 40 - QUEUED
- job 10 = I3p_hts_seed   : STILL RUNNING (constrained seed; its final xyz -> I3prime->P OptTS when done)
Pipeline: on job 10 done -> build OptTS+Freq(I3prime->P) from the seed xyz, submit; on job 31 -> IRC
      endpoints -> Opt/Freq both to confirm I3prime / I2 connectivity at 6.1.1.

### RESOURCE POLICY UPDATE (2026-09-30, supersedes 4-core default for FUTURE jobs)
Human correction: future useful ORCA production jobs default submit_compute_job cpus=8, memory_mb=12000,
(MEMORY FIX 2026-09-30 later: reservation = ~1.5 GB/core, i.e. memory_mb = cpus*1500 -> 8 cores = 12000,
 4 cores = 6000; %maxcore stays 1500. Our system is tiny; do not over-reserve memory. 14000 is superseded.)
input %pal nprocs 8 and %maxcore 1500 (8*1500=12000 <= 14000). Server 32 cpu / 56000 MB => ordinarily FOUR
8-core jobs concurrently, rest queue (admission enforces cpu+memory). Existing RUNNING jobs (incl. job 10)
and already-QUEUED jobs (30, 31, both nprocs4) stay unchanged - no cancel/restart to resize. Do not claim 8
cpus for a serial nprocs1 input. Method/solvent/graph/reference/acceptance unchanged.
APPLY to: the I3prime->P OptTS+Freq and all later HL1 endpoint/IRC jobs (nprocs 8, mem 14000, maxcore 1500).

### PHASE 3e - job 30 DONE; full ORCA 6.1.1 ladder (gas, B3LYP-D3BJ/def2-SVP+def2/J RIJCOSX TightSCF, q=+1)
| species | E (Ha, ORCA 6.1.1) | imag | job |
|---------|--------------------|------|-----|
| I2 (nitrilium + 2 H2O) | -364.137564264 | 0 | 30 |
| TS669 (I2<->I3prime saddle) | -364.120933530 | 1 (-213.61 cm-1) | 17 |
| I3prime (O-protonated imidic acid + H2O) | -364.128159827 | 0 | 9 |
| P (O-protonated amide + H2O) | -364.193803774 | 0 | 16 |

CONSISTENT 6.1.1 ENERGETICS (electronic, gas):
- Barrier of the I2 -> I3prime step (via TS669): E(TS669)-E(I2) = +0.016630734 Ha = +10.44 kcal/mol.
- Reverse barrier of that step (I3prime -> TS669): E(TS669)-E(I3prime) = +0.007226297 Ha = +4.53 kcal/mol.
- DeltaE_rxn(I2 -> I3prime) = E(I3prime)-E(I2) = +0.009404437 Ha = +5.90 kcal/mol (net, endothermic).
- DeltaE_rxn(I3prime -> P) = E(P)-E(I3prime) = -0.065643947 Ha = -41.19 kcal/mol (NET REACTION ENERGY, NOT A BARRIER).
- **Barrier of the I3prime -> P step: STILL UNKNOWN** - needs the OptTS+Freq from the proton-transfer seed.
- Engine check: ORCA5 vs ORCA6 differences for I2/I3prime/TS669/P are all <= 0.01 kcal/mol.

### PHASE 3f - job 10 (constrained proton-transfer seed): NON-CONVERGENT GRIND (not killed)
status at inspection: GEOMETRY OPTIMIZATION CYCLE 149 (MaxIter 300), energy ~ -364.10 Eh, i.e. ~+15 kcal
ABOVE the I3prime minimum. Constraint echo confirms ORCA parsed {B 4 5 1.25 C} and {B 5 9 1.25 C}, but the
printed geometry has d(O4-H5)=1.014 and d(H5-N9)=2.266 (both ~unchanged from I3prime), so the H5 bridge is
NOT held at 1.25 A. Each cycle reports 'Imposing constraints ... CONVERGED' then only ~1.4% of the geometry
convergence check - the optimiser is stalling, not progressing to a bridged TS seed. Leaving it to reach its
own terminal state (do not kill/duplicate). If it exhausts MaxIter unconverged, the fallback seed route is an
IDPP interpolation between the I3prime and P minima (same 19 atoms) to place H5 between O4 and N9.
job 31 (TS669 IRC both ways) is RUNNING.

### PHASE 3g - OWNERSHIP HANDOFF to small_mol sub-agent (2026-09-30)
Per system convention (long/formal QM jobs belong to domain sub-agents), the remaining HL1 QM production is
delegated to a small_mol sub-agent (session as_b61637108f234ac4). Brief: finish the I3prime->P 1,3-H saddle
(OptTS+Freq, 1 imag aligned to O4-H5...N9), bidirectional IRC + endpoint Opt/Freq proving I3prime and P,
and report Ea(I3prime->P) / reverse at ORCA 6.1.1. Existing jobs 10 (seed) and 31 (TS669 IRC) are NOT to be
duplicated or killed. Resource rule for new jobs: node paratera-cpu/local, cpus=8, memory_mb=12000,
%pal nprocs 8, %maxcore 1500. No graph/task-source edits. I (coordinator) retain delivery oversight.

### PHASE 3h - job 10 TERMINAL (result) + DELEGATION LEDGER + a correction
job 10 (I3p_hts_seed) TERMINAL: normal_termination=true, opt_converged=true, E=-364.106271340124 Ha, no
frequencies (Opt only). Final geometry d(O4-H5)=1.016, d(H5-N9)=2.283, d(O4-C8)=1.475 -> H5 stayed on O4,
i.e. the {B 4 5 1.25}/{B 5 9 1.25} constraints were NOT honoured; this is NOT a usable bridged TS seed.
=> the constrained-pre-opt seed route for I3prime->P FAILED. Fallback: IDPP interpolation between the I3prime
and P minima (same 19 atoms) to place H5 between O4 and N9, then unconstrained OptTS+Freq.

DELEGATION LEDGER (coordinator = me; execution = specialist):
- small_mol child session as_b61637108f234ac4 (REUSED, not duplicated). Owns HL1 QM execution:
  I3prime->P OptTS+Freq (1 imag aligned to O4-H5...N9), bidirectional IRC, endpoint Opt/Freq proving
  I3prime and P; owns follow-up of job 10 (dead) and job 31 (TS669 IRC), and submitted job 37. Report to
  owner and post to agent_hub topic 'HL1 Beckmann resume'.
- Owner (me) retains: scientific review of I2->I3prime vs I3prime->P evidence, xTB-evidence audit, graph
  ambiguity escalation to the human, resource coordination across the 32CPU/56000MB pool, final REPORT/HANDOFF.

CORRECTION to prior handoff wording: the claim that ts_prepare xTB path is 'known-broken' was based on an
OLD-SERVER/original-campaign failure (xTB path search 'incomplete_artifacts' + 'No product!'). It is run- and
environment-specific, NOT a property of the newly deployed standalone xTB 6.7.1. Do not declare ts_prepare
globally unusable; a fresh test on this server is needed before any such statement.

### PHASE 3i - child status report (small_mol as_b61637108f234ac4), owner review
Child post evt_a39af152e77d4ceb (private progress file paratera_20260930/PROGRESS_smallmol.md):
- job 10 verified terminal: E=-364.106271340 Ha = +13.74 kcal vs I3'; H5 not bridged; NOT a seed. (Owner
  cross-check: -364.106271340-(-364.128159827)=0.021888487 Ha = 13.74 kcal - agrees.)
- IDPP fallback: I3' and P files have DIFFERENT atom orders; first map swapped methyls (bad), corrected map
  (product order, ORCA 0-based): [0,5,1,2,10,9,8,7,6,3,16,17,18,14,15,4,11,12,13]. Corrected path physical
  (O4-H5 0.98->3.17, H5-N9 2.25->1.02, C8-O4 1.49->1.29, C8-N9 1.24->1.31).
- JOB 37 = I3p_P_TS : ORCA6.1.1 OptTS+Freq, seed=IDPP midpoint img_06 (I3p_P_interp2/), Calc_Hess MaxIter 300,
  %pal nprocs 8 / %maxcore 1500, submitted paratera-cpu/local cpus=8 mem=12000 prio 2. STATE=QUEUED (mem full).
- job 31 TS669 IRC: RUNNING (forward converged in 10 iters, backward ~18). Child will opt+freq both endpoints.
- xTB re-audit: /opt/cloudra/software/xtb-dist/bin/xtb exists and prints a version -> the 'ts_prepare xTB
  path known-broken' claim is OLD-RUN/OLD-SERVER specific (matches PHASE 3h correction).
- Child caveat: IDPP midpoint H is off the O-N axis (O-H 2.06, H-N 1.57, O..N 2.21, H_perp ~1.3 A); if job 37
  collapses/multi-imag, fallback = pure ORCA relaxed scan along the H-transfer (NO constraints; Scan+Constraints
  is the job670 dead end) then unconstrained OptTS. No single saddle -> report honestly, no graph edits.
OWNER REVIEW: numbers consistent; delegation boundary respected (child executes, owner reviews). No action to
change the model/graph. Watch items: (1) does job 37 give exactly 1 imag aligned to O4-H5...N9, (2) does it
connect I3' and P by IRC, (3) keep barrier vs DeltaE_rxn separate, (4) graph decision (I3' as a real node)
remains with the human.

### PHASE 3j - job 31 (TS669 IRC, ORCA 6.1.1) terminal
job 31 = TS669_IRC_ORCA6: normal_termination=true, job type IRC only. Forward 40 pts, backward 36 pts,
irc_both_directions_converged=false. E(TS669) in this run = -364.120945329 (vs -364.120933530 in job17;
0.007 kcal difference, same saddle). Endpoint electronic energies: F=-364.126167, B=-364.124270 - both only
~1.2 / ~2.4 kcal below the saddle and still ABOVE the I3' minimum (-364.128160) and far above I2, i.e. the
IRC extent is short/flat (same flat-path behaviour seen on the ORCA5 run). Endpoint frames exist:
TS669_IRC_ORCA6_IRC_F.xyz / _IRC_B.xyz. Child (small_mol) owns the endpoint Opt+Freq to identify which
minimum each side belongs to; owner will review that the F side reaches I2 and the B side reaches I3'.
NOTE: this confirms TS669 as a genuine first-order saddle but by itself does not upgrade the graph; the
I3' node existence and any E3 edge split remain a human graph decision.

### PHASE 3l - infra hazard check (cross-topic warning from HI1)
HI1 reported: an in-place RESOURCE transaction on a READY job recreated <jobdir>/.cloudra as root:root 0755,
so the executor (uid 998) could not write guard logs -> job fails at start. Checked ALL HL1 paratera job dirs:
every .cloudra is cloudra:cloudra 700 -> HL1 is CLEAN, no root-owned dirs, no action needed. Warning passed to
the small_mol child. Rule: do not perform in-place resource resizes on READY jobs; if a .cloudra is ever
root-owned, rename it aside before the job starts. HL1 plan unchanged (job 42/43/44).

### PHASE 3m - IRC endpoint evidence for TS669 (jobs 42/43): I2<->I3prime CONNECTIVITY CONFIRMED
job 42 = TS669_IRC_epF -> optimized to I2: E = -364.137434628 Ha, 0 imag, O4-C8 2.626 / C8-N9 1.150.
   (vs I2 reference job30 -364.137564264 -> +0.000129636 Ha = +0.081 kcal; same species, tiny water-rotamer/
   numerical difference.)
job 43 = TS669_IRC_epB -> optimized to I3prime: E = -364.128154326 Ha, 0 imag, O4-C8 1.493 / C8-N9 1.236.
   (vs I3prime reference job9 -364.128159827 -> +0.000005501 Ha = +0.003 kcal; essentially identical.)
=> At ORCA 6.1.1 the job-17 saddle TS669 is confirmed as a genuine first-order saddle connecting I2 and
   I3prime, with both endpoints frequency-verified as minima of the intended identity.

REMAINING (child): job 44 = I3prime->P IRC from the job-37 TS -> Opt/Freq both endpoint frames; expect one end
I3prime and the other P. Once that lands, the two-saddle I2->I3prime->P picture is fully evidenced at 6.1.1.
The I3prime-node / E3-edge-split decision remains with the human (no graph edit).

=====================================================================
## PHASE 4 (FINAL) - HL1 I3prime->P STEP RESOLVED (ORCA 6.1.1); owner-verified
=====================================================================
DELIVERABLE: the previously unfinished I3prime -> P proton transfer is a SINGLE elementary 1,3-H (O4-H5->N9)
shift. job 37 (IDPP-midpoint OptTS+Freq) gives a genuine first-order saddle; job 44 IRC endpoints re-optimize
(jobs 46/47) to the intended minima. Owner independently re-parsed jobs 37/46/47 logs - numbers match.

| species | E (Ha, ORCA 6.1.1 gas) | imag | job |
|---------|------------------------|------|-----|
| I2 (nitrilium + 2 H2O) | -364.137564264 | 0 | 30 |
| TS669 (I2<->I3') | -364.120933530 | 1 (-213.61) | 17 |
| I3' (O-prot. imidic acid + H2O) | -364.128159827 | 0 | 9 |
| TS(I3'->P) (1,3-H shift) | -364.106714752931 | 1 (-1633.07) | 37 |
| P (O-prot. amide + H2O, ref) | -364.193803774 | 0 | 16 |
| P (lower conformer found by IRC) | -364.196816183201 | 0 | 46 |
| I3' (IRC endpoint re-opt) | -364.128100625008 | 0 | 47 |

ENERGETICS (electronic, kcal/mol):
- Ea(I2->I3') = +10.44 ; reverse +4.53 ; DeltaE_rxn(I2->I3') = +5.90 (net).
- Ea(I3'->P)  = +13.46 ; reverse vs P_ref +54.65 (vs lower P conf +56.54).
  DeltaE_rxn(I3'->P) = -41.19 (vs P_ref) / -43.09 (vs lower conformer) -> NET energies, NOT barriers.
- RDS: with both steps separate, the higher barrier is I3'->P (+19.4 above I2); I2->I3' is +10.4.

CAVEATS / OPEN FOR HUMAN:
1. The IRC product minimum (job 46) is a conformer 1.89 kcal BELOW the P reference (job 16). If the graph's P
   node is that lower conformer, reverse barrier +56.5 and net -43.1; forward barrier (+13.46 vs I3') unchanged.
2. IRC branches stopped at ORCA's DEFAULT iteration cap (no custom MaxIter by policy); connectivity is
   established by the frequency-verified endpoint re-optimizations (jobs 46/47), which is sufficient.
3. GRAPH DECISION still belongs to the human: the evidence now supports a genuine intermediate I3' with two
   distinct saddles (I2->I3' and I3'->P). NO graph / task-source edit was made.
4. Engine provenance: ALL numbers above are ORCA 6.1.1, gas, B3LYP-D3BJ/def2-SVP+def2/J RIJCOSX TightSCF, q=+1;
   do not mix with the earlier ORCA 5.0.2 campaign (differences were <=0.01 kcal/mol where compared).

EXECUTION: all HL1 QM done by small_mol child as_b61637108f234ac4 (jobs 9,10,16,17,30,31,37,42,43,44,46,47);
owner reviewed evidence and independently verified jobs 37/46/47. Owner-side work is complete pending the
human graph decision.

### PHASE 3k - job 37: I3prime->P SADDLE FOUND (ORCA 6.1.1); ladder complete except IRC connectivity
job 37 = I3p_P_TS (OptTS+Freq from IDPP midpoint img_06): NORMAL TERMINATION, CONVERGED,
E(TS) = -364.106714752931 Ha, exactly 1 imag = -1633.07 cm-1 (56 freqs). Imag mode = pure H motion
(heavy_atom_fraction 0.0053); watch-pair projection O4-H5 0.788 / H5-N9 0.817 (vs C8-O4 0.066, C8-N9 0.032)
=> mode IS the O4-H5...N9 proton transfer, ALIGNED. TS geometry O4-H5 1.205 / H5-N9 1.442 / C8-O4 1.404 /
C8-N9 1.269 (H bridging O4/N9).

BARRIERS (electronic, ORCA 6.1.1, gas):
- Ea(I3prime->P) = E(TS)-E(I3prime) = +0.021445074 Ha = +13.46 kcal/mol   <-- the sought second barrier
- Ea(P->TS)      = E(TS)-E(P)       = +0.087089021 Ha = +54.65 kcal/mol
- check: +13.46 - 54.65 = -41.19 = DeltaE_rxn(I3prime->P) NET (unchanged; not a barrier).
Owner arithmetic cross-check: 0.021445074*627.5095=13.46; 0.087089021*627.5095=54.65. Consistent.

FULL 6.1.1 LADDER (relative to I2 = -364.137564264, electronic):
  I2 (0.00) -> TS669 (+10.44, 1 imag) -> I3prime (+5.90, 0 imag) -> TS(I3'->P) (+19.36, 1 imag -1633) -> P (-35.28)
  i.e. if the graph carries I2->I3prime and I3prime->P as separate edges, the higher saddle is I3prime->P;
  the I2->I3prime step has the lower barrier (+10.44 forward, +4.53 reverse).

STATUS of remaining checks (child owns): job 42 = Opt+Freq of IRC-F frame (expect I2), RUNNING;
job 43 = Opt+Freq of IRC-B frame (expect I3prime), QUEUED; job 44 = bidirectional IRC from the job-37 TS
(Defaults, no MaxIter) then endpoint Opt+Freq -> the only open item is connectivity of the I3prime->P saddle.

NOTE (endpoint energy-list ordering): log_parser irc_endpoint_energies_hartree returned F/B as
[-364.126167, -364.124270], whereas the child's geometry-based assignment is F=-364.124270 (I2-like,
C8-O4 2.100) / B=-364.126167 (I3prime-like, C8-O4 1.527). The geometry assignment governs; the list order
is not guaranteed. Recorded so nobody rescues the wrong endpoint.

GRAPH: still a HUMAN decision. The evidence now supports a genuine intermediate I3prime with two distinct
saddles (I2->I3prime and I3prime->P). No graph edit made here; escalation stands.

=====================================================================
## PHASE 5 (CLOSURE) - HUMAN ADJUDICATION RECORDED (no new computation)
=====================================================================
HUMAN DECISION (approved): the HL1 downstream is SPLIT into two elementary edges:
  - I2 -> I3prime (water addition):      Ea = +10.44 kcal/mol
  - I3prime -> P (O->N proton transfer): Ea = +13.46 kcal/mol
and the LOWER P conformer from IRC endpoint job 46 (E = -364.196816183201) is ADOPTED as the P node.
With job 46 as P: forward Ea(I3prime->P) = +13.46 (unchanged, vs I3prime); reverse = +56.54 kcal/mol;
DeltaE_rxn(I3prime->P) = -43.09 kcal/mol (NET, not a barrier). I2->I3prime reverse = +4.53, net +5.90.

SUPERVISOR-SIDE (done outside this topic, per the human): registry, task source, TaskSpec updated; raw product
coordinates archived; generator check and benchmark tests PASS; commit 02128715 prepared for GitHub master.

OWNER ACTION HERE: adjudication written into HANDOFF/REPORT only. NO HL1 calculation started or repeated; no
mechanism_graph.json / task-source edit made by this topic.
RETAINED CAVEAT: the prior E2 = 23.13 kcal/mol entry keeps its partial-IRC caveat (not IRC-verified); the
I2->I3prime / I3prime->P barriers above are the graph's adopted E3 split.
HL1 STATUS: CLOSED (executor stood down; all jobs terminal; no HL1 jobs running/queued).


endpoints -> Opt/Freq both to confirm I3prime / I2 connectivity at 6.1.1.



