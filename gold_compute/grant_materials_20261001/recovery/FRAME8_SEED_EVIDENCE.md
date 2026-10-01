# FRAME 8 SEED — EVIDENCE FOR REUSE + CAVEATS (major/E2; child A file)

Purpose: document exactly WHY major_spec/scan_clean/scan_clean_np8.008.xyz (job 58 scan frame 8,
d(Ca-Cc)=1.938) is being used as the single recovery OptTS seed (job 67), and what it is NOT.
Owner: major/E2 channel. (Coordinator-owned files are NOT edited here.)

## 0. CORRECTION to earlier shorthand (important)
Earlier I wrote that the RC51->frame8 path was "face continuous". That claim is about the ALDEHYDE FACE
ONLY. The scan is NOT a continuous MEP and frame 8 is NOT a "barrier-top" in any MEP sense:
the O-H...O=C HYDROGEN-BOND NETWORK SWITCHES DISCONTINUOUSLY between frame 5 and frame 6.

## 1. H-BOND DISCONTINUITY (0-based: 9=OdO,10=Oh,23=OhH,24=Ow,25/26=Hw,27=Od,28=Cc)
distances (Angstrom) along job 58 relaxed scan frames 1-9:
 fr  d(Ca-Cc)  Oh-H23   H23...Od   OdO...H26   Od...H25   (water)
  1   4.300     1.001     1.680      1.895       3.310
  2   3.963     0.998     1.692      1.933       3.324
  3   3.625     0.993     1.744      1.925       3.413
  4   3.287     0.988     1.825      1.947       3.380
  5   2.950     0.985     1.893      1.959       3.331
  6   2.612     0.978     5.159  <--JUMP     1.893       2.807   <-- water H25 moves in
  7   2.275     0.979     5.018      1.915       2.757
  8   1.938     0.979     5.192      1.945       2.675
  9   1.600     0.977     5.642      1.960       2.626
=> The carboxyl O-H...Od(aldehyde) H-bond (H23...Od = 1.68-1.89) BREAKS at frame 6 (5.16 A) and does not
   return; the WATER inserts itself (carboxyl C=O...H26-O24-H25...Od aldehyde). So frames 6-9 are a
   DIFFERENT H-bonded state from the RC (frames 1-5). The energy 'crest' at d=2.95 is this switch, and the
   later maximum (d=1.94) lies on the water-bridged state. CONSEQUENCE: frame 8 is NOT a continuous MEP
   barrier-top and the internal energy maximum alone does NOT prove a relevant TS.

## 2. PROTON STATE (no proton transfer anywhere)
Oh-H23 = 0.977-1.001 A across all frames 1-9: the carboxyl O-H proton stays ON the carboxyl O10.
No O-H .. -> .. O transfer, no zwitterion formed. Charge 0, multiplicity 1, 41 atoms throughout.

## 3. CONNECTIVITY / STEREO / FACE / WATER of frame 8 (internal_coordinates, validated)
- Formula C15H21NO4, 41 atoms, 41 bonds, 2 FRAGMENTS (C-C adduct + one explicit water). q=0.
- Rings: ONLY proline-5 (N4-C5-C6-C7-C8) + benzene-6 (C30..C35) -> skeleton intact, NO spurious ring.
- Bond anomalies: C1-C29 = 1.938 A, bond order 1, ratio 1.258 (elongated = the forming/partial C-C bond);
  O10-H26 = 1.945 and H27-O28 = 1.680 are the retained WATER H-bonds. No atomic overlap / heavy clash.
- Stereo: C8 = R (same as RC51); C29 = R (the new C-C stereocentre).
- Face (D(Cb-Ca-Cc-Od) = 1-based C2-C1-C29-O28):
  RC51 +58.3 | fr1 +58.3 | fr2 +64.7 | fr3 +58.9 | fr4 +47.9 | fr5 +50.0 | fr6 -7.0 | fr7 -7.7 | fr8 -21.1 | fr9 -36.3
  -> a monotone aldehyde rotation about the forming C-C axis through the reorganization; NO ~180 deg
     jump, i.e. the MOLECULE stays on the RC51 (major) face family. (Face continuity, not MEP continuity.)
- Explicit water: retained (1 water) and H-bonded throughout (it becomes the bridge at fr6-9).

## 4. WHY IT IS STILL A SAME-MECHANISM (major C-C addition) CANDIDATE
- It lies on the RC51-derived relaxed scan of the SAME 3-molecule complex (enamine + water + benzaldehyde);
  no bond other than the forming Ca-Cc changes; the carboxyl O-H is intact; the water is retained.
- The C-C bond is forming on the MAJOR-face approach direction inherited from RC51 (no face flip).
- It is the only point on any existing path with a partial/elongated Ca-Cc bond on the major face.
=> It is a legitimate CANDIDATE seed for a same-mechanism TS search, NOT a demonstrated saddle.

## 4b. PROTON-PATH DETERMINATION vs THE DECLARED E2 (answers the coordinator's question)
The DECLARED E2 target (HI1_gold_20260929/ts/ts_0001/declare.json) is:
  reactant: C=C(C)N1CCC[C@@H]1C(=O)O.O.O=Cc1ccccc1      (enamine + water + benzaldehyde)
  product : CC(C[C@H]([O-])c1ccccc1)=[N+]1CCC[C@@H]1C(=O)O.O
i.e. the C-C addition gives the IMINIUM-ALKOxide ZWITTERION: the aldehyde O is [O-], the proline N is
[N+], and the CARBOXYL O-H IS INTACT (C(=O)O, not C(=O)[O-]). The water is retained as a separate
molecule (.O). => The declared E2 elementary step requires NO carboxyl-O-H -> aldehyde-O proton transfer;
the carboxyl proton must STAY on the carboxyl.
Frame 8 is fully consistent with that: Oh-H23 = 0.979 A (proton on the carboxyl, never transferred in any
frame 1-9), the aldehyde O is not protonated, and the water only H-BONDS (O10-H26 = 1.945, H27-O28 = 1.680)
as a spectator/mediator. So the water-mediated H-bond in frame 8 is NOT an alternative "water proton
transfer" mechanism - it is the same non-transferring reactant state, and it is CHEMICALLY CONSISTENT with
the declared E2.
=> A frame-8-rooted saddle CAN be the declared E2 TS. The requirement that decides it is NOT the proton
   path but whether the actual saddle's mode is the Ca-Cc forming mode and the IRC endpoints are the RC
   complex (one side) and the C-C adduct (other side) with skeleton/face consistent.
CAVEAT (kept): the declared E2 product is a zwitterion; job 27 showed a zwitterionic C-C adduct does not
survive unconstrained relaxation from an MMFF seed. That affects the ENDPOINT identity/regeneration, not
the identification of the C-C forming saddle.

## 5. ACCEPTANCE / REJECTION CRITERIA for job 67 (no backfilling)
ACCEPT only if: exactly 1 imaginary mode whose displacement is ALIGNED with Ca-Cc (watch_pairs=[[1,29]]),
AND IRC in both directions reaches the correct covalent endpoints (one = the reactant complex / reorganized
H-bonded complex, the other = the C-C adduct) with frequency-verified (0 imag) minima, AND skeleton/face/
proton are consistent. dE#(E2) = E(TS2) - E(RC51 = -938.760019066499).
REJECT honestly (do not backfill with the job 58 constrained-scan numbers, do not loop over similar candidates)
if the skeleton / aldehyde face / proton path does not match, or if it is not a genuine first-order relevant
saddle. STOP-AND-ASK if the cycle-1 Hessian has 0 negative eigenvalues or the followed mode is not Ca-Cc.
