# HE3 — hard-gold backfill REPORT (ORCA 6.1.1 resume, 2026-10-01)

**Task**: simplified (S)-CBS-catalyzed acetophenone reduction by BH3; attempted two enantioselective
hydride-delivery channels (Si-favoured -> (R), Re -> (S)).
**Spec**: /public/home/yyywaa/cloudra/ideapool/tasks/hard/HE3.json (tier hard, family E).
**Work dir**: HE3_gold_20260929/ ; new jobs under HE3_gold_20260929/paratera_20260930/ .
**Engine provenance**: this resume uses **ORCA 6.1.1** (/opt/cloudra/software/orca-6.1.1) ONLY.
The old campaign used ORCA 5.0.2 (retired Slurm). ORCA5 values are context only and are NEVER mixed
into a 6.1.1 arithmetic chain.
**Method (fixed)**: B3LYP-D3BJ/def2-SVP, RIJCOSX + def2/J, TightSCF, CPCM(THF); charge 0, mult 1.
dE# = E(TS) - E(RC), pure electronic (kcal/mol, x627.5095).

## VERIFIED RESULT (ORCA 6.1.1)
| species | E (Eh) | imag | identity |
|---|---|---|---|
| RC_A (job 25) | -684.745389244764 | 0 | ternary pre-complex minimum (global min of the constructed set) |
| RC_B (job 26) | -684.743918222978 | 0 | **conformer** of the same ternary complex, +0.92 kcal/mol |
| TS_A (job 23) | -684.732199242842 | 1 / -419.08 cm-1 | hydride-transfer saddle (C4-H34 projection 0.913) |
| TS_B (job 62) | -684.732238989422 | 1 / -416.12 cm-1 | **same saddle** (E diff -0.025 kcal/mol; RMSD 0.015 A) |
| PROD_A intact-ring (job 39) | -684.776275499364 | 0 | alkoxyborane + regenerated catalyst (B5-N15 1.385) |
| PROD_A/B ring-opened (job 49) | -684.786033727921 | 0 | hydride on C7, catalyst ring OPEN (B5-N15 3.981); C7 = R |
| PROD_B (job 34) | -684.771718122240 | 0 | product min from an independent seed; C7 = R |

**dE# (forward) = E(TS) - E(RC_A) = +0.013190002 Eh = +8.28 kcal/mol** (using TS_A; +8.25 using TS_B).
Relative to the RC_B conformer it is +7.33 kcal/mol, but RC_B is not a distinct channel (see below), so the
common-reference value **+8.28 kcal/mol** is the reported barrier.

## KEY FINDINGS / HONEST CAVEATS
K1. **One shared hydride-transfer saddle, not two channels.** The d(C7-H34) relaxed scan on the RC_B
    minimum collapsed back to the channel-A ketone orientation at its first constrained frame; the
    resulting saddle (job 62) is the same stationary point as TS_A (energy within 0.025 kcal/mol, mode
    within 3 cm-1). RC_A and RC_B are two conformers of the same ternary complex (RC_B = channel A's own
    IRC reactant endpoint job 48, to 3e-6 Eh). => the constructed endpoints give ONE TS.
K2. **Connectivity caveat (channel A, owner-corrected).** Across the 12 IRC_A frames the hydride transfers
    (C7-H34 1.459->1.176) with the catalyst ring INTACT (B5-N15 1.61->1.67); ring opening (B5-N15 3.981)
    appears only after the 64-cycle full Opt (job 49). An additional B5-N15 cleavage therefore occurs
    downstream; **no barrier was computed for it**, so it is NOT a "low-barrier isomerisation", and the
    declared catalyst-regeneration endpoint (job 39) is **not proven connected** to the IRC branch.
    Two distinct products are retained: job 39 (intact ring) and job 49 (ring-opened), 6.12 kcal/mol apart.
K3. **Enantioselectivity open item (escalated).** Both IRC product endpoints and both product minima give
    C7 = R; the intended Re -> (S) channel is not reproduced by either constructed endpoint. The task's
    two-face model is not supported by the current evidence.

## Evidence chain
- TS character: ORCA freq gives exactly 1 imaginary mode dominated by the transferring C4-H34 pair.
- IRC_A (job 35) and IRC_B (job 63): both directions converged; reactant ends return to the ternary
  complex; product ends are hydride-transferred with the ring essentially intact and C7 = R.
- Endpoint identities established by unconstrained Opt+Freq (jobs 48/49 for A; mirrored by B).
- Unsafe routes explicitly NOT used: the dissociative NEB (old jobs 620/622) and the ORCA5 torsional-seed
  dead ends (jobs 599/600/668) were not retried.

## Constraints respected
No changes to mechanism graph / solvent (THF) / reference state / method / acceptance. The task-source
graph and mechanism_graph.json were NOT edited. No old-server jobs polled or resubmitted. All compute on
the paratera-cpu cloud node (ORCA 6.1.1; CPCM jobs required %pal nprocs 1 until root fixed the MPI build).

## Execution / delegation
Topic owner: coordinator. Execution specialists (small_mol): channel A as_19aee01c357c4bfc,
channel B as_0af3d08a16c94d6a. Adopted jobs 23/25/33/35 (A) and 24/26/34 + new scan/TS/IRC (B);
owner independently re-parsed every terminal log and corrected unsupported report claims.