# HL1 — hard-gold audit / backfill REPORT

**Task**: Beckmann rearrangement of (E)-butanone oxime, acid-catalyzed, gas phase (spec `ideapool/tasks/hard/HL1.json`).
**Work dir**: `HL1_gold_20260929/`  (read-only copies of all benchmark sources under `_src/`).
**State**: audit COMPLETE; **one still-scoring edge (E5) independently resolved**; E3/E4/E1/E2 documented, not re-run; **no benchmark source edited**.

---

## 1. INVENTORY (task-required, before any submission)

| Item | Location | Notes |
|---|---|---|
| TaskSpec | `/public/home/yyywaa/cloudra/ideapool/tasks/hard/HL1.json` (copy `_src/task_HL1.json`) | gold mechanism_graph embedded |
| gold graph | R=[OH3+].CC/C(=N/O)/C ->I1->I2->I3->I4->P; barriers **E1=0.0, E2=23.13, E3=null, E4=0.0, E5=null** |
| gold nodes | I1=`O.CC/C(C)=N/[OH2+]`; I2=`O.O.CC#[N+]CC`; I3=`CCN=C(C)[OH2+].O`; I4=`CCN=C(C)O.[OH3+]`; P=`[OH3+].CCNC(C)=O` |
| literature ledger | `_src/edge_barriers_HL1.json` | E2 39.9 (Yamabe05); E3 18 (Ronchin08, analogue); E5 30.5 (Kerkeni&Simmie23); E1/E4 null "compute" |
| self-computed json | `_src/computed_HL1.json` | only E1=0.0 + E4=0.0 (constrained monotonic PT scans); R,I1 strict 0-imag minima; **I3,I4 have NO free stationary point** -> collapse to nitrilium+2H2O (I2) |
| reviews | `_src/REVIEW_chem_HL1.md`, `_src/REVIEW_modes_HL1.md` | TS mode-identity audit of the prior campaign |
| **prior compute IDs** | calc-528 (E2 TS -304.17, E -364.0453), calc-531 (E1 "TS" -1791.63, rejected: oxime O->N PT), calc-529 (E5 "TS" -653.06, rejected: spurious H3O+ proton soft mode), calc-645 (E3m "TS" -63.55, rejected) |
| **prior raw logs** | referenced at `gold_compute/campaign/runs/HL1/**/.cloudra/calc-*.out.log` -> **DIRECTORY ABSENT** | confirmed absent on disk and never committed (`git ls-files/log` show no campaign/runs); only `archive/*.md` summaries survive. The calc-5xx/645 job records are not in this session's DB. |

Method policy (allowed): xtb / pm7 / b3lyp-def2svp; only ORCA/Gaussian logs are scorable.
**Fixed method used**: ORCA 5.0.2 gas phase `! B3LYP D3BJ def2-SVP def2/J RIJCOSX` (+ TightSCF; TS + %geom Calc_Hess true). ΔE‡ = pure electronic E(TS) − E(step's own starting minimum), ×627.5095, no ZPE/thermo, charge +1 mult 1 for the graph; the isolated-tautomer calculations are neutral.

---

## 2. PER-EDGE VERDICT (which edges still score, and what we can/cannot do)

| Edge | declared | verdict this pass |
|---|---|---|
| **E1** R->I1 (H3O+->oxime-O PT) | 0.0 | **Barrierless PT, not a saddle** (prior: R and I1 are strict 0-imag minima; 13-pt constrained scan monotonic; the "peak" relaxes to R). 0.0 is honest as a *barrierless* edge but must **not** be called a verified saddle. Raw log gone -> no independent reparse. Did not duplicate. |
| **E2** I1->I2 (concerted Beckmann RDS) | 23.13 | TS 1-imag (−304.17) located previously, but **IRC backward did not return to I1** (landed ~17 kcal high) -> connectivity only partial. Raw log/geometry **gone**, so completing the IRC requires re-finding the saddle = duplicating calc-528. **Not re-run.** |
| **E3** I2->I3 (water attack on nitrilium) | null | Declared **I3 is not a minimum** at this level (slides to I2 basin). Gas-phase nitrilium+H2O is an ion-molecule addition (no conventional saddle). **Not resolvable as declared.** |
| **E4** I3->I4 (PT imidic-OH2+ -> water) | 0.0 | Declared **I3 and I4 are not minima**; the 0.0 is a constrained-scan span, **not a saddle**. **Not resolvable as declared.** |
| **E5** I4->P (imidic acid -> amide, 1,3-H shift) | null | **RESOLVED independently** — see §3. ΔE‡ = **28.46 kcal/mol**. |

**Still-scoring edge chosen for independent resolution = E5**, because its chemistry (an intramolecular O–H···N 1,3-H shift) is well-defined for the isolated neutral imidic acid; the H3O+ of the declared I4 complex is a spectator to the E5 bond changes (break O1–H10 / C4=N6 pi, form N6–H10 / C4=O1). E1/E2/E4 are barrierless/partial or require the vanished log; E3 is not resolvable as declared.

---

## 3. NEW INDEPENDENT RESULT — E5 (isolated imidic-acid frame)

Fixed method, gas phase, all jobs below submitted via `submit_compute_job` (ORCA, 4 cores / 8 GB each, ≤2 concurrent).

| Species | job | E (Hartree) | n(imag) | geometry evidence |
|---|---|---|---|---|
| **E5 reactant** — N-ethylacetimidic acid, pre-organized O–H···N minimum | **640** (IRC-F endpoint re-opt; from 639) | **−287.449228685** | **0** | O3–H10=0.973, N4···H10=2.224, C2–O3=1.355, C2=N4=1.268 |
| E5 product — N-ethylacetamide, global minimum | **629** | −287.474105508 | 0 | N4–H10 bonded, C2=O3=1.219, C2–N4=1.373 |
| E5 product — amide conformer reached by IRC | **642** | −287.471026078 | 0 | idem |
| **E5 TS** | **637** | **−287.403878135** | **1** (−1878.54 cm⁻¹) | H bridging O3–H10=1.317 / N4–H10=1.346; C2–O3=1.289, C2–N4=1.311; imag-mode displacement dominated by O3–H10 / N4–H10 |
| **E5 IRC** | **639** | — | — | Direction both, converged: 25 forward + 20 backward pts; endpoints −287.4682 / −287.4485 Ha |

**ΔE‡(E5) = E(637 TS) − E(640 imidic-acid minimum) = 0.045350550 Ha = 28.46 kcal/mol.**
Reverse barrier (vs amide global minimum, job 629) = 44.07 kcal/mol; overall tautomerization exothermic by 15.61 kcal/mol.
Connectivity: TS(637) -> IRC(639) -> {imidic acid (640, 0 imag) , amide (642, 0 imag)} — both endpoints are freq-verified minima of the intended species.

**Caveats (honest):**
- This is the **isolated imidic-acid frame** (neutral), NOT the graph's charged I4 complex. The declared I4 (`CCN=C(C)O.[OH3+]`) does not exist as a free minimum at this level; removing the spectator H3O+ is the only well-defined frame for the same intramolecular chemistry. The ΔE‡ therefore does **not** by itself replace the graph's I4-referenced value without a graph decision (§4).
- The imidic-acid reactant minimum found by the IRC (E=−287.44923, O–H···N pre-organized) is **2.18 kcal below** the plain anti-OH local minimum (E=−287.44576), so the correct reference is the lower, IRC-verified one; using the anti conformer would have given 26.28 kcal/mol.
- Value 28.46 sits close to the literature 30.5 (Kerkeni & Simmie 2023, isolated acetimidic acid, R=H analogue) — consistent, but ours is the N-ethyl substrate at the fixed method.
- **E5 (28.46) > E2 (23.13)**: if E5 is adopted with a valid reference, the RDS of HL1 moves from E2 to E5.

---

## 4. THE EXACT SCIENTIFIC CHOICE NEEDED (do NOT change the graph here)

The gold graph declares intermediates **I3** (`CCN=C(C)[OH2+].O`) and **I4** (`CCN=C(C)O.[OH3+]`) as species minima. At B3LYP-D3(BJ)/def2-SVP gas phase (confirmed by two prior independent campaigns, `computed_HL1.json` + the 2026-09-17 batch ruling) **neither is a free stationary point — both relax into the nitrilium+2H2O basin (I2 composition)**. Hence edges E3, E4 and the I4-reference of E5 are not defined on this PES. The owner must choose one of:

- **(A) Adopt the isolated-imidic-acid frame for E5**: keep the E5 chemistry, replace the I4 node reference by the isolated N-ethylacetimidic acid minimum, and use **ΔE‡(E5)=28.46 kcal/mol** (this pass). Smallest change; does not alter E5's chemistry, only the (non-existent) spectator complex.
- **(B) Redefine E4/E5 as a proton-transfer step with an explicit acid/water relay** (the real acid-catalyzed tautomerization), which requires a new model + new graph edges.
- **(C) Merge E3/E4/E5** into the single real PES step (as the prior 2026-09-17 ruling already considered), re-deriving the graph.

We did **not** edit `mechanism_graph.json`, the TaskSpec, the gold JSON, or any benchmark source. No commit/push.

---

## 5. JOB LEDGER (this pass; all ORCA, gas, fixed method)

| job | what | outcome |
|---|---|---|
| 628 | imidic acid (anti) opt+freq | −287.44576123, 1 imag −8.33 (superseded) |
| 629 | amide opt+freq | −287.47410551, **0 imag** (amide global min) |
| 633 | imidic acid TightOpt+freq | −287.44576177, 1 imag −8.44 (superseded) |
| 634 | OptTS v1 (IDPP img_03 seed) | FAILED — walked downhill, hit cycle cap |
| 635 | constrained pre-opt (H bridged O3/N4 at 1.30 Å) | seed geometry (opt hit cap but valid) |
| 636 | imidic acid rot+20 TightOpt+freq | −287.44576080, 0 imag (higher local min; superseded by 640) |
| **637** | **E5 OptTS v2 (Calc_Hess, MaxIter 300)** | **−287.403878135, 1 imag −1878.54 (the TS)** |
| 638 | IRC v1 | FAILED — bad %irc syntax (`InitHess calc`) |
| **639** | **IRC both directions** | **converged, 25 F / 20 B** |
| **640** | IRC-F endpoint re-opt+freq | **−287.449228685, 0 imag (imidic-acid minimum)** |
| 641 | IRC-B endpoint re-opt | FAILED — cycle cap |
| **642** | IRC-B endpoint re-opt (MaxIter 300) | **−287.471026078, 0 imag (amide)** |

Logs: `HL1_gold_20260929/dft/<name>/.cloudra/calc-<id>.out.log`; inputs alongside.

## 6. NOT DONE / BOUNDARIES
- E2/E1 not re-run (raw logs gone; re-running would duplicate calc-528/531). E3 not run (not resolvable as declared).
- I3/I4 non-minimum status is taken from prior documented evidence, not re-verified this pass.
- No benchmark source edited; no commit/push.
---

# PHASE 2 (2026-09-30) - REVISED GRAPH: E3 = I2 -> P (barrier null)

Graph revised at cloudra commit 77f671b (`_src/hard_swap_2026-09-30.md`): R -> I1 -> I2 -> P with
I2 = O.O.CC#[N+]CC (nitrilium + 2 H2O, +1), P = [OH3+].CCNC(C)=O, E1 = null, E2 = 23.13 (kept),
E3 = null (net hydration / proton relay). Ask: is there ONE physically meaningful **unconstrained**
saddle I2 -> P at the fixed method, with E(I2) as reference?

## 7. INVENTORY (Phase 2)
- No prior job was re-run. Prior campaign records (calc-528/531/529/645) and the old raw campaign logs
  remain absent from disk and uncommitted; only the archive .md summaries survive (`_src/`).
- CAUTION on cross-campaign numbers: the prior `computed_HL1.json` Hartree values (I2 basin
  -364.32933899) lie ~0.19 Ha BELOW this session's ORCA fixed-method values (I2 -364.137562560).
  The two campaigns must not be mixed; every number below is this session's fixed method
  (ORCA 5.0.2 gas, `! B3LYP D3BJ def2-SVP def2/J RIJCOSX TightSCF`, charge +1, mult 1).

## 8. STATIONARY POINTS (fixed method)
| species | job | E (Hartree) | n(imag) | note |
|---|---|---|---|---|
| **I2 minimum** (nitrilium + 2 H2O) | 648 | **-364.137562560** | **0** | floppy, needed MaxIter 400; O4-C8 2.637, O1-H6 1.858, C8-N9 1.150 |
| **P as declared** ([OH3+] + neutral amide) | 665 | -364.193788877 | 0 | **started from the true H3O+/amide assembly and the proton MOVED to the amide O (O1-H2 1.012 -> 1.561; amide O-H 1.017). The declared P is NOT a free minimum.** |
| true product minimum (O-protonated amide + water) | 644 / 665 | -364.193788877 | 0 | the real minimum of composition C4H12NO2+ on the product side |
| **first-order saddle** (C-O formation + H6 relay to the spectator water) | 669 | **-364.120930791701** | **1 (-214.5 cm-1)** | O4-C8 1.818, C8-N9 1.185, N9-H5 2.566 (no N-H), O4-H6 1.010 / O1-H6 1.590 |

- **dE(I2 -> P_true) = -0.056226317 Ha = -35.28 kcal/mol** (gas, fixed method, pure electronic).
- **dE(TS 669 - I2) = +0.016631768 Ha = +10.44 kcal/mol** (constrained-free saddle, 1 imag).

## 9. WHY A ONE-STEP SADDLE IS PROBLEMATIC (evidence)
1. **DFT relaxed scan C8-O4 (job 664, normal termination).** From the I2 minimum the C-O coordinate is
   PURELY REPULSIVE: relative energies vs the 2.663 A minimum are +0.5 (2.88), 0 (2.66), +0.5 (2.44),
   +2.4 (2.23), +5.5 (2.01), +8.2 (1.79), +10.1 (1.57), +17.3 (1.35) kcal/mol. No maximum, no second
   well, no covalent C-O intermediate: the nitrilium-water C-O bond cannot form without coupled PT.
2. **The saddle found (job 669)** is C-O formation coupled to the H6 proton moving from the attacking
   water to the spectator water; the nitrilium N does NOT gain an H at the saddle. Its IRC (job 671,
   MaxIter 40, NOT converged: endpoints only ~3.2 kcal below the TS) runs back to the I2 side forward,
   and to a C-O-bonded, still-H-less-on-N species backward. So this saddle alone does not deliver the
   amide N-H; a second elementary step (N-H formation) is implied.
3. An earlier OptTS from a bridged seed (job 653) failed to converge (hit MaxIter 300) and drifted to a
   3-fragment, proton-transferred structure - i.e. no single concerted saddle was found there either.
4. The declared P itself is not a minimum (see the table above): like the old I3/I4, the [OH3+] + neutral
   substrate arrangement relaxes by proton transfer (here to the amide oxygen).

## 10. VERDICT (Phase 2, as of this writing)
**A physically meaningful SINGLE unconstrained saddle connecting the I2 minimum to the declared P
minimum cannot be validated, because the declared P is not a free minimum at the fixed method and
because the C-O attack coordinate is repulsive in the I2 basin.** One genuine first-order saddle was
located (job 669, 1 imag, +10.44 kcal/mol vs I2), but its reaction mode is C-O formation plus a proton
relay to the spectator water, not the full nitrilium -> amide transformation. The net step therefore
appears to require at least one further elementary step (N-H formation) and, in the graph's own terms,
a corrected P node. **Adjudication requested from the graph owner** (see HANDOFF for the pending endpoint
job 680 that fixes the product-side basin of the 669 saddle).

## 11. JOB LEDGER (Phase 2)
| job | what | outcome |
|---|---|---|
| 643 | I2 opt+freq v1 | FAILED - cycle cap |
| **644** | P (as assembled) opt+freq | -364.193809799, 0 imag (proton on the amide O) |
| **648** | I2 minimum opt+freq (MaxIter 400) | **-364.137562560, 0 imag** |
| 649 | constrained E3 TS seed (3 constraints) | -364.010049746, opt hit cap |
| 653 | OptTS from that seed | FAILED - MaxIter 300, non-productive drift |
| 662 | relaxed scan C8-O4 v1 | FAILED - bad ORCA Scan syntax |
| 663 | constrained seed (3 constraints) | -364.048514626 (+55.9 kcal) - too strained |
| **664** | **relaxed scan C8-O4 (3.10->1.35, 9 pts)** | **repulsive profile, no barrier, no well** |
| **665** | **declared-P test (H3O+ + amide, true assembly)** | **-364.193788877, 0 imag, but the proton moved to the amide O -> declared P is not a minimum** |
| 666 | constrained seed (2 constraints, H5->N9) | -364.073000575 (+40.5 kcal) |
| **669** | **OptTS+Freq from seed3** | **-364.120930791701, exactly 1 imag -214.5 cm-1 CONVERGED** |
| 670 | scan N9-H5 with C8-O4 fixed | FAILED - ORCA BLAS error in GSTEP |
| 671 | IRC from 669 | ran, NOT converged (MaxIter 40) |
| 672 | constrained seed (H6->N9) | -364.072763335 (+40.7 kcal) |
| 673/674/675/676/679 | endpoint re-opts via Slurm | FAILED to submit - `sbatch: Account has been disabled` |
| 677/678 | endpoint re-opts, local backend 4 cores | FAILED - login node has only 2 slots |
| **680** | **IRC-B endpoint re-opt (local, 2 cores)** | RUNNING / see HANDOFF for the result |

Logs: `HL1_gold_20260929/dft/<name>/.cloudra/calc-<id>.out.log`; inputs alongside. No benchmark source
was edited, committed or pushed.

=====================================================================
## PHASE 3 (2026-09-30) - paratera-cpu / ORCA 6.1.1 (NEW ENGINE) - I3prime->P search
=====================================================================
Old campaign ran ORCA 5.0.2; the new server runs ORCA 6.1.1. Per instruction the fixed model/route/
solvent/charge/multiplicity are kept and only the ENGINE version changed; RC/TS energies will be
recomputed consistently at 6.1.1 (never subtract ORCA5 from ORCA6). Gas phase (no CPCM).

FOCUS (task): finish the I3prime -> P step = O4-H5 -> N9 1,3-H (O->N) proton transfer, i.e. the second
saddle after the I2->I3prime saddle found at job 669 (ORCA5).

New jobs (engine provenance: ORCA 6.1.1, paratera-cpu local, cpus=4, mem=7000, %pal nprocs 4, %maxcore 1536):
| job | name | task | input start |
|-----|------|------|-------------|
| 9  | I3p_min_ORCA6 | Opt+Freq, new-version I3prime reference | dft/E3_epB2/E3_epB2.xyz |
| 10 | I3p_hts_seed  | constrained Opt {B 4 5 1.25},{B 5 9 1.25} seed for O4-H5->N9 | dft/E3_epB2/E3_epB2.xyz |
Queued inputs (submit as slots free): Pmin_ORCA6 (from E3_P.xyz), TS669_ORCA6 (OptTS from E3_TS2.xyz),
I2min_ORCA6 (from E3_I2b.xyz).

Working dir: HL1_gold_20260929/paratera_20260930/. Status at submission: jobs 9,10 RUNNING.
No graph/task-source edits (awaiting authorization). Unsupported conclusions escalated to the human.

### PHASE 3a-3b update
- job 9 (I3prime Opt+Freq, ORCA6.1.1): E = -364.128159827 Ha, 0 imag, CONVERGED. ORCA5 job681 = -364.128155679
  (diff 0.003 kcal/mol) -> engine upgrade negligible for this minimum; provenance still recorded.
- job 16 (P min Opt+Freq) and job 17 (TS669 OptTS+Freq refine) SUBMITTED and RUNNING at ORCA 6.1.1.
- job 10 (I3prime->P constrained seed) still RUNNING; its product feeds the I3prime->P OptTS.

### PHASE 3c-3d update (ORCA 6.1.1 results)
- job 16 Pmin : E = -364.193803774 Ha, 0 imag (ORCA5 -364.193788877; delta 0.009 kcal/mol).
- job 17 TS669: E = -364.120933530 Ha, 1 imag -213.61 cm-1 (ORCA5 -364.120930792, -214.5; delta 0.002 kcal/mol).
- ORCA6.1.1 ladder: TS669 -364.120933530 | I3p -364.128159827 | P -364.193803774; I2 pending job 30.
  DeltaE_rxn(I3p->P) = -41.19 kcal/mol = NET REACTION ENERGY, NOT a barrier.
  I3p->P BARRIER (job 37, ORCA6.1.1): Ea(I3p->P) = +13.46 kcal/mol; reverse Ea(P->TS) = +54.65 kcal/mol.
  (check: 13.46 - 54.65 = -41.19 net.) TS(job37): E=-364.106714752931, 1 imag -1633.07 cm-1, mode aligned to O4-H5...N9.

### PHASE 4 (FINAL) - I3'->P RESOLVED (owner-verified)
- job 37 saddle confirmed: 1 imag -1633.07 cm-1 aligned to O4-H5...N9; job 44 IRC endpoints re-optimized:
  job 46 = P (O-protonated amide + water) E=-364.196816183201, 0 imag; job 47 = I3' E=-364.128100625008, 0 imag.
  => saddle CONNECTS I3' and P; single elementary 1,3-H shift, no multi-step.
- Ea(I3'->P)=+13.46 (forward, vs I3'); reverse +54.65 vs P_ref (+56.54 vs lower conformer job46);
  DeltaE_rxn = -41.19 (P_ref) / -43.09 (lower conformer) NET, NOT barriers.
- Full ORCA 6.1.1 ladder: I2 -364.137564264 | TS669 -364.120933530 | I3' -364.128159827 |
  TS(I3'->P) -364.106714752931 | P_ref -364.193803774.
- Open for human: product conformer choice (job46 1.89 kcal below P_ref); I3'/E3 graph split. No graph edits.

### PHASE 5 (CLOSURE) - HUMAN ADJUDICATION RECORDED (no new computation)
Human-approved: HL1 downstream SPLIT into I2->I3prime (water addition, Ea=+10.44) and I3prime->P (O->N proton
transfer, Ea=+13.46 kcal/mol); ADOPT the lower P conformer from IRC endpoint job 46 (E=-364.196816183201).
With job 46 as P: reverse Ea(I3prime->P)=+56.54; DeltaE_rxn=-43.09 NET (not a barrier). I2->I3prime reverse
+4.53, net +5.90. Supervisor updated registry/task source/TaskSpec, archived raw product coords; generator check
and benchmark tests PASS; commit 02128715 prepared for GitHub master. This is a RECORD ONLY for this topic -
no HL1 calculation started/repeated, no graph/task-source edit made here. RETAINED: old E2=23.13 partial-IRC
caveat stands. HL1 CLOSED.

  Barrier-type numbers only: TS669 is +4.53 kcal/mol above I3p (= reverse barrier of the I2->I3p step);
  TS669 is +10.44 kcal/mol above I2 (consistent ORCA 6.1.1 numbers, all four species recomputed).
- Queued (pool saturated): job 30 I2min_ORCA6 (I2 ORCA6 reference), job 31 TS669_IRC_ORCA6 (IRC both ways).
  job 10 (I3prime->P constrained seed) still RUNNING; its product feeds the I3prime->P OptTS.



