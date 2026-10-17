# S2 exploratory cross-check (GFN2-xTB / GFN1-xTB) - runs/explore/

Scope: exploratory semiempirical mapping only (NOT deliverable evidence). Task: decide concerted vs
stepwise for the C2H7OP open-chain (A) -> 1,2-oxaphosphetane ring (B) connection, test the
phosphonium-alkoxide betaine [H3P+]-CH2-CH2-[O-], and produce a candidate TS geometry in A atom order.

## Atom order used everywhere
All files below are in A's atom order (== inputs/open.xyz): 1 C, 2 P, 3,4 H(C1), 5,6 H(P), 7 H(hydroxyl, on O9),
8 C, 9 O, 10,11 H(C8). inputs/ring.xyz was reordered to A order with the mapping
ring->open [1,2,9,8,3,4,5,6,7,10,11] => runs/explore/B_ring_Aorder.xyz.
Reaction: form P2-O9 and move H7 from O9 to P2.

## 1) Re-optimization + frequencies (GFN2-xTB, gas phase, charge 0, singlet)
| file | job | log | result |
|---|---|---|---|
| A_open.xyz | 1 (ohess) | runs/explore/A_open.out | converged, 33 modes, 0 imaginary, E = -14.411391933741 Ha |
| B_ring_Aorder.xyz | 2 (ohess) | runs/explore/B_ring_Aorder.out | converged, 33 modes, 0 imaginary, E = -14.407101864335 Ha |
| betaine_guess.xyz | 3 (ohess) | runs/explore/betaine_guess.out | converged, 0 imaginary, E = -14.40710604499 Ha -> COLLAPSED TO RING B |

Betaine test: inputs/runs/explore/betaine_guess.xyz (P-H7 1.413, P-O 3.207, no ring, i.e. a real
zwitterion seed) optimized UNCONSTRAINED to the ring (final P-O 1.608, P-H7 1.443, 4-membered ring);
its atom-pair distance matrix equals ring B up to a permutation of the three equivalent P-H hydrogens
(max difference after relabelling ~0.01 A). => no betaine minimum found in GFN2 gas phase.

## 2) Relaxed scans (native GFN2-xTB, force constant 0.5 a.u.)
- scan1 (job 4)  d(O9-H7) 0.97 -> 2.60 A, 12 pts, from A: runs/explore/scan1_proton_transfer.chem-result.json
  Profile rises to ONE peak then collapses straight into the ring:
  pt1 0.969 A 0.00 | pt2 1.086 +5.06 | pt3 1.225 +17.0 | pt4 1.380 +30.4 (peak) | pt5 1.600 +21.5 (P-O already 1.58 = ring) ... 
  At pt4 P-O is still 2.88 A with H mid-transfer (O-H 1.38 / P-H 1.92); at pt5 the P-O bond has formed (1.58 A)
  and H is on P. Single maximum, no intervening minimum -> concerted.
- scan5 (job 9) same coordinate, finer (1.15 -> 1.75 A, 13 pts): runs/explore/scan5_fine_proton.chem-result.json
  Peak at O-H 1.479 A, E = -14.353495 Ha (+36.3 kcal vs A), where H is bridging (O-H 1.48 / P-H 1.56, P-O 2.62);
  next point already the ring. Same conclusion, better-resolved TS region.
- scan2 (job 5) d(P2-O9) 3.15 -> 1.70 A from A (H left on O): runs/explore/scan2_PO_fromA.chem-result.json
  monotone climb to +37.4 kcal, NO ring formed. A single P-O coordinate is a poor reaction coordinate
  (the H does not follow); this is a coordinate artifact, not a second barrier.
- scan3 (job 6) d(P2-O9) 3.20 -> 1.70 A from the betaine seed: runs/explore/scan3_PO_fromBetaine.chem-result.json
  The constrained zwitterion is unstable: pts 1-3 stay charge-separated (E ~ -14.32 Ha, +58 kcal vs A) and
  actually fragment (C1-C8 = 2.04 A => CH2=PH3 + CH2=O), then pts 4-16 jump back to the open-chain basin.
  No smooth betaine -> ring path: no betaine stationary region on this surface.
- scan4 (job 8) reverse, d(P2-H7) 1.40 -> 2.80 A from B: runs/explore/scan4_reverse_fromB.chem-result.json
  monotone rise (+63.6 kcal at 2.78 A), no transfer back to O; also a poor coordinate (kept for completeness).

## 3) Candidate TS
runs/explore/candidate_TS_gfn2.xyz  (scanned frame runs/explore/native_scan_runs/native_scan_0005/point_0008.xyz, A atom order)
Key distances: P-O 2.675 | O-H7 1.479 | P-H7 1.562 | C1-C8 1.552 | P-C1 1.829 | O-C8 1.364 A
(H bridging O and P, P-O partially formed - the barrier-top frame of the fine scan).
Independent IDPP interpolation A->B: runs/explore/ts_interp/ (15 images, TS candidate img_08.xyz, P-O 2.25).

## 4) Relative energies (semiempirical, gas phase, charge 0 singlet; 1 Ha = 627.509 kcal/mol)
| species | GFN2-xTB E/Ha | GFN2 dE/kcal | GFN1-xTB (ORCA XTB1) E/Ha | GFN1 dE/kcal |
|---|---|---|---|---|
| A open chain (min) | -14.411392 | 0.00 | -15.325274 | 0.00 |
| B ring (min)       | -14.407102 | +2.69 | -15.321066 | +2.64 |
| candidate TS       | -14.353495 | +36.3 | -15.272378 | +33.2 |
| scan1 peak frame   | -14.362982 | +30.4 | (not run) | - |
| betaine (constrained, fragmented) | -14.318441 | +58.3 | (not run) | - |
GFN1-xTB single points (ORCA 6.1.1 keyword XTB1): runs/explore/gfn1_{A,B,TS}.inp, logs runs/explore/.cloudra/calc-1{5,6,7}.out.log
PM7: NOT available in this ORCA 6.1.1 build ("PM7" keyword rejected as unrecognized); GFN1-xTB used as the second semiempirical level instead.

## 5) Verdict (exploratory, semiempirical only)
CONCERTED. One barrier, no betaine intermediate:
- GFN2 and GFN1 both put B only ~2.6-2.7 kcal above A - very different from B3LYP-D3(BJ)/def2-SVP (+31.5 kcal),
  so the semiempirical numbers are geometry/qualitative guidance only and MUST NOT be quoted as the barrier.
- The relaxed reaction-coordinate scans show a single maximum (A -> TS -> B) with the P-O bond closing
  immediately after the proton-transfer barrier; the betaine zwitterion is not a minimum (unconstrained
  optimization gives the ring; constrained optimization fragments or reverts).
- Recommended TS seed for the DFT (B3LYP-D3(BJ)/def2-SVP) OptTS: runs/explore/candidate_TS_gfn2.xyz
  (with runs/explore/ts_interp/img_08.xyz as an independent geometric alternative).

Provisional / not review evidence. A formal verdict requires the DFT TS + frequency (1 imaginary) + IRC.
