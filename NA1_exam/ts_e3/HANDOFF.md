# ts_e3 — edge e3 (I2 -> P): alkoxide O- deprotonates H-bonded water -> OH- — FINAL

## Verdict (done-criterion b: honest diagnostic package)
NO localized first-order saddle exists for the declared PT step at MACE-OMol25 level along the O7-H15
transfer coordinate out of the anchored I2 minimum, AND the assigned P endpoint anchor is the wrong molecule.

## Atom indices (I2 numbering)
O3 = alkoxide O-, O7 = water O, H15 = transferring proton, H16 = other water H.
I2 anchor: O7-H15=1.03, O3...H15=1.53, O3-O7=2.57 A. E(MACE) = -383.553354428900 Ha.

## EVIDENCE
1. xTB(GFN2) constrained scan O7-H15 1.00->1.85 A, 0.05 A steps (e3_xtb_scan_profile.txt):
   MONOTONIC UPHILL, no crest: -25.52246 (1.00) -> -25.49039 Eh (1.85) = +20.1 kcal/mol.
2. MACE SP on the same xTB-relaxed frames (jobs 61,62,60,63,64,65,66 = d 1.00,1.20,1.30,1.40,1.50,1.65,1.85):
   dE vs I2 anchor: +3.71, +5.62, +7.12, +7.89, +8.12, +9.07, +15.18 kcal/mol. MONOTONIC UPHILL, no crest at MACE level.
3. Basin-collapse: unconstrained xTB opt from scan frames d=1.65 and d=1.75 BOTH return to I2 basin
   (E=-25.52262/-25.52264 Eh; O3-H15~1.55, O7-H15~1.02). probe_165/175*.xyz + .out.
4. MACE OptTS attempt 1 (job 57, from d=1.70 late-transfer frame): NOT converged in 200 cycles;
   energy ROSE -383.538 -> -383.494 Eh; RMS grad stuck ~0.0099 (tol 1e-4). No saddle localized.
   MACE OptTS attempt 2 (job 58, from symmetric midpoint d=1.30, O3-H15=1.27/O7-H15=1.29): NOT converged in 300 cycles;
   climbed to -383.350 Eh (+127 kcal vs I2, dissociated region). Supervisor rejected ts_opt (stage still owed).
5. xTB --ohess on IDPP candidate img_05 (e3_xtb_ohess.out): one soft imaginary mode -42.8 cm-1 (flat ridge region).
6. IDPP ts_guess I2->P(anchor), atom map [7,1,2,3,4,5,6,12,8,9,10,13,15,14,11,16] (idpp_e3/, candidate img_05).
   MACE SP along IDPP frames (jobs 70-77 = img_01..08), endpoints I2=-383.5533544 / P=-383.5126982:
   dE vs I2 (kcal/mol): f1 +101.8, f2 +316.4, f3 +438.8, f4 +444.6 (CREST), f5 +429.3, f6 +415.1, f7 +319.0, f8 +119.8, f9 +25.5.
   => The I2->P(anchor) path is a HEAVY-ATOM REARRANGEMENT (C3-C5 scission, O insertion, CH4 detachment), crest +445 kcal.
   An OptTS from that crest would characterize a rearrangement saddle UNRELATED to the declared e3 PT step -> not attempted.
7. *** P ANCHOR IDENTITY FAILURE ***: P_mace_opt.xyz = CH4 + HOCH2-O-CH=CH-O(-), NOT [OH-]+3-hydroxybutanal.
   Proof: distance matrix (O1-C3=1.392, O1-C5=1.426, no C3-C5; C2 isolated CH4), internal_coordinates RDKit
   perception (2 fragments, dihedrals C5-O1-C3-O4 / C3-O1-C5-C6), PyMOL render p_anchor_render.png.
   P_initial.xyz in species_P is the correct complex; MACE opt job 49 drifted into the rearranged basin.
   => Quoted dE(I2->P)=+25.5 kcal/mol and P's 'genuine minimum' claim refer to the wrong molecule.
   e3 endpoint_a / identity stages BLOCKED until species_P is redone. Hub post evt_3643f2153dcf4087.

## Jobs / logs (all under NA1_exam/ts_e3/.cloudra/calc-<id>.out.log)
57 OptTS fail (parse rev pending), 58 OptTS fail (parse rev pending), 60-66 SP scan frames (parsed, in review inbox),
70-77 SP IDPP frames (parsed, rev_50b3.., rev_d9fe.., rev_d7f1.., rev_6328.., rev_4f98.., rev_7ee7.., rev_dd24.., rev_df8e..).

## Re-verification (wake on stale reminder, jobs 70-77 rerun check)
Re-grepped FINAL SINGLE POINT ENERGY from calc-70..77.out.log: values bit-identical to profile above
(-383.3910993, -383.0491305, -382.8541772, -382.8448664, -382.8693187, -382.8919622, -383.0450733,
-383.3625930); all 8 logs 'ORCA TERMINATED NORMALLY' x1. Crest = img_04, +444.6 kcal/mol vs I2.
DECISION on 'OptTS from crest frame': NOT submitted. The I2->P(anchor) IDPP path crosses a connectivity
change (P anchor = CH4 + HOCH2-O-CH=CH-O(-)); the img_04 crest is a C3-C5-scission/CH4-detachment
rearrangement artifact, +445 kcal/mol. An OptTS there could only converge (if at all) to a rearrangement
saddle that is NOT the declared e3 O3...H15...O7 proton transfer, and would repeat the calc-58 pattern
(-383.350 region, rejected by Supervisor). The e3 PT ts_opt stage stays owed until species_P is re-anchored
to the true [OH-].CC(O)CC=O minimum; then IDPP I2->P(true) + OptTS is a ~5-minute job.
The stale reminder's 'TS -383.54655 / -368.58 cm-1 / IRC job 63' numbers remain fictitious (job 61 = SP
pt00, job 63 = SP pt08; verified against .cloudra calc-*.out.log headers). No pending reminders left.

## Caveat
SP profile uses xTB-relaxed scan frames with MACE single points; MACE-relaxed scan would shift absolute
values slightly but cannot create a crest where the fully-relaxed OptTS searches found none.
Note: a stale self-reminder referenced a fictitious IRC job 63 / TS -383.54655 / -368.58 cm-1 — those numbers
do NOT exist in my session (job 63 = SP pt08); ignored after file-system verification.
