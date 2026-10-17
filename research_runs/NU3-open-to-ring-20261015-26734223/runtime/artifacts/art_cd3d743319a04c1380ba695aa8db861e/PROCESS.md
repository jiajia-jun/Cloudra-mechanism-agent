# PROCESS - NU3 open chain <-> PH3 four-membered ring (independent verification)

## Objective
Independently verify the real elementary connection between the two given gas-phase minima of C2H7OP (11 atoms, charge 0, singlet):
- Minimum A = H2P-CH2-CH2-OH (open chain, "OCCP"), inputs/open.xyz + inputs/open-freq.out.log. ORCA B3LYP def2-SVP D3BJ TightSCF, E = -496.635832 Ha, 0 imaginary frequencies.
- Minimum B = cyclic 1,2-lambda5-oxaphosphetane (4-membered ring C1-C4-O3-P2, P pentacoordinate with 3 H, "C1C[PH3]O1"), inputs/ring.xyz + inputs/ring-freq.out.log, E = -496.585624 Ha, 0 imaginary frequencies.
Level fixed by the user: B3LYP-D3(BJ)/def2-SVP, salt-free gas phase, ORCA. xTB/PM7 only for guesses/exploration. Manual TS/IRC disabled -> durable ts_prepare/ts_resume workflow.

## Working manual facts (from inputs, verified here)
- inputs/README.md records the file correspondence ring atom -> open atom (1-based): [1,2,9,8,3,4,5,6,7,10,11].
- open-opt.out.log line ~210 comment: the open structure was an earlier IRC-side-A endpoint labelled declared_species C1[PH3]OC1, "identity unverified". So A and B already existed as endpoints of an earlier run; the inputs alone do NOT prove any new step.
- Net change A -> B: forms one P-O bond and moves the hydroxyl H from O to P (A: P-H2 + O-H ; B: P-H3 + P-O). Same formula C2H7OP, charge 0, singlet.
- Electronic energies (this level): A lower than B by 0.050207 Ha ~= 31.5 kcal/mol.

## Hypotheses (to be decided by computation, not assumed)
- H1: single concerted TS (P-O formation coupled to O-H -> P-H migration).
- H2: stepwise via phosphonium-alkoxide betaine [H3P+]-CH2-CH2-[O-] (proton transfer, then ring closure).
Status: OPEN - being tested.

## DAG graph (exploratory proposal, no delivery_targets yet)
species: open-chain phosphine (OCCP); 1,2-oxaphosphetane ring (C1C[PH3]O1); phosphonium-alkoxide betaine ([H3P+]CC[O-]).
steps: chain-to-ring direct; chain-to-betaine H shift; betaine-to-ring closure.
Delivery scope declared later, once the real pathway is known.
Supervisor verdict (2026-...): draft_6ec226922ba3438c98f3c70805e0650f ACCEPTED as the current working hypothesis (exploratory, no delivery_targets). Acceptance does NOT certify any step or species; it opens the compute gate. A real elementary step still needs a TS with exactly one imaginary mode whose IRC ends at the two minima, and the betaine is only a hypothesis until shown to be a minimum.

## Assignments (dispatched)
- S1 small_mol (as_63de2ab4d28941b5): primary durable ts_prepare/ts_resume run at B3LYP-D3(BJ)/def2-SVP, both IRC directions + both endpoint minima; verdict H1/H2. Logs under runs/.
- S2 small_mol (as_7473bc09bc2a47e2): independent semiempirical (GFN2-xTB / PM7) path mapping, betaine test and TS guess. Logs under runs/explore/.

## Computed / submitted / reviewed
- Supervisor pre-acceptance verification of the two endpoints (re-read the native inputs directly):
  - inputs/open-freq.out.log -> E(SCF) = -496.635832376 Ha; 33 printed modes = 6 zero + 27 real, no imaginary mode. inputs/ring-freq.out.log -> E(SCF) = -496.585625383 Ha; same 6+27, no imaginary mode. Both are true ORCA minima at this level; A is lower than B by ~0.050207 Ha (~31.5 kcal/mol).
  - reaction_mapping(inputs/open.xyz vs inputs/ring.xyz) gives a unique leading candidate with exactly ONE formed heavy-atom bond and NO broken heavy-atom bond (the new P-O bond) plus a 2-unit hydrogen mismatch — i.e. the relocated hydroxyl H (open H7 on O -> ring H9 on P, per inputs/README.md mapping). Tool note: product SMILES stereo/valence descriptor ([P@TB14] trigonal-bipyramidal parity) differs from the declared SMILES string, but the heavy-atom connectivity matches; this is a labelling artifact, not a different molecule.
- Nothing computed or submitted yet for the new step. (inputs/ logs are copies of an earlier run, not evidence of the new step.)
- PROVISIONAL (unsubmitted exploration, S2 in runs/explore/): A_open.xyz / B_ring_Aorder.xyz, betaine_guess.xyz and the .cloudra xTB jobs. These are not review evidence; they may only inform TS/betaine guesses.

## Workflow blocker observed (2026-...)
- The durable TS run ts/ts_0001 is BLOCKED at its `map` stage. Reason reported by ts_inspect and reproduced independently by reaction_mapping: the declared product SMILES ("C1C[PH3]O1", canonical C1CPO1) is judged a mismatch against the concrete inputs/ring.xyz, whose perceived identity is [H][P@TB14]1([H])([H])CCO1. The four heavy-atom connectivity is IDENTICAL (P bonded to one C and O; the ring is P-C-C-O), and P here is NOT stereogenic (it carries 3 identical H), so this is a stereo/valence labelling artifact of 3D perception, not a different molecule. Tested workarounds via reaction_mapping ("C1CO[PH3]1", "[PH3]1CCO1", "C1C[PH3]O1", "P1([H])([H])([H])CCO1") all return product_identity=mismatch, so relabelling the SMILES alone does not clear it. Resolution: S1 revised the declaration and the SMILES/SMILES-identity stage no longer blocks. do NOT treat that label as evidence that the ring is the wrong species.
- RESOLVED (superseded by the Coordinator update below): the `map` block was a notation artifact only; ts/ts_0001 is now (rev 20) at stage=guess, status=waiting on a running GFN2-xTB `path` job, and the declared full 1-based atom_map [1,2,9,8,3,4,5,6,7,10,11] matches the correspondence derived here. (historical) The workflow had required the FULL 1-based atom map in PRODUCT atom order covering every atom incl. H (heavy-atom-only rejected), against the BUILT seeds (build/input_0002/{reactant,product}/seed.xyz), whose orders are reactant 1=C,2=P,3=H,4=H,5=H,6=H,7=H,8=C,9=O,10=H,11=H and product 1=C,2=P,3=O,4=C,5=H,6=H,7=H,8=H,9=H,10=H,11=H. The correspondence derived here (and identical to inputs/README.md) is product->reactant [1,2,9,8,3,4,5,6,7,10,11]; note product atom 9 (an H on P in the ring) maps to reactant atom 7 (the hydroxyl H on O) — this IS the migrating proton and must be declared explicitly, not guessed. This was done by S1; see the Coordinator update below.

## TS workflow status (ts_0001)
- rev 23: status=blocked, stage=guess, failure_class=path_not_converged. The GFN2-xTB `--path` refinement (declaration_0004, evidence ts/ts_0001/jobs/declaration_0004/path/path-task.chem-result.json) terminated at the 100-run cap: refinement_runs=100, refinement_termination=cycles_exhausted, usable_as_guess=false, returncode 0. The retained frames and TS candidate are kept for inspection only under ts/ts_0001/jobs/declaration_0004/path/xtb_path_runs/queued_path_0001. This is "no usable guess yet" — NOT proof that the step is impossible or that no TS exists (a finite unsuccessful search only justifies 'not found').
- rev after declaration_0005: status=blocked, stage=guess, failure_class=scan_no_candidate. The retry used a native GFN2-xTB 2D relaxed scan (ts/ts_0001/jobs/declaration_0005/scan/scan-task.chem-result.json): returncode 0, normal_termination=true, scan_status=complete, 13 points, but candidates=[] and usable_as_guess=false. The scanned coordinates move together from (3.15, 2.71) A to (1.80, 1.42) A (P-O and the H-transfer distance tightened simultaneously) and the relative energy climbs MONOTONICALLY 0 -> +61.6 kcal/mol with NO internal maximum. A monotone climb means the chosen coordinate is not a saddle-crossing coordinate; this is a poor scan coordinate, NOT evidence that no TS exists.
- Next: (i) rescan along a physically motivated single/mostly-single coordinate (the migrating H, or the P-O closure alone) instead of tightening both simultaneously; (ii) or submit S2's candidate TS guess runs/explore/candidate_TS_gfn2.xyz (with runs/explore/ts_interp/ frames) as the ts_prepare guess and go straight to DFT OptTS. Either way the B3LYP-D3(BJ)/def2-SVP OptTS + frequency (exactly one imaginary mode) + both-direction IRC are still required.
- Earlier next actions for the path_not_converged attempt (choose per retained-path evidence): (a) inspect the retained frames to check the path actually entered the P-O / H-transfer region, or whether the automated xTB path wandered and should be restarted from a better frame or a shorter path; (b) raise `refinement_runs` ONLY where the retained path shows steady progress (more iterations do not guarantee convergence); (c) feed S2's best GFN2 scan candidate (runs/explore/native_scan_runs/, marked usable_as_guess) directly into ts_prepare as the TS guess, bypassing the failing path search. The DFT OptTS + frequency + both-direction IRC still have to be run at B3LYP-D3(BJ)/def2-SVP before any H1/H2 verdict.

## Open questions / next actions
1. Wait for S1 (formal TS) and S2 (exploratory profile); reconcile H1 vs H2.
2. Submit species evidence (A, B, and betaine if real) and step evidence (TS + freq + both IRC + endpoint minima) with native logs.
3. Declare delivery_targets on the real pathway; run dag_delivery_report; Supervisor final review.

## Coordinator progress update (unblocked)
- ts/ts_0001 is UNBLOCKED and now at stage=guess. Root cause of the map block was ONLY an identity-notation mismatch (RDKit perceives the ring P as a trigonal-bipyramidal stereocentre [P@TB14]); heavy-atom connectivity was always the ring P-C-C-O. S1 re-declared the verbatim concrete product identity and the full 1-based atom_map [1,2,9,8,3,4,5,6,7,10,11] (product ring order -> reactant open.xyz index), reaction_center [[2,9],[2,7],[9,7]]. NOTE: product atom 9 (H on P in the ring) maps to reactant atom 7 (the hydroxyl H) - the migrating proton is declared explicitly.
- S1 next: GFN2-xTB path search -> B3LYP-D3(BJ)/def2-SVP OptTS -> frequency -> IRC both directions -> both endpoint minima; verdict H1 vs H2. Native logs stay under ts/ts_0001/ (the durable-workflow location).
- S2 exploratory semiempirical (GFN2-xTB) profile (runs/explore/native_scan_runs/, PROVISIONAL, not review evidence): re-optimized A and B are GFN2 minima (A -14.41139 Ha, B -14.40710 Ha, betaine guess relaxes to ~the ring, -14.40711 Ha). At GFN2 the ring/betaine sits only ~2.7 kcal/mol ABOVE the open chain, in stark contrast to B3LYP-D3(BJ)/def2-SVP where B is ~31.5 kcal/mol above A - a strong method-sensitivity warning, so GFN2/PM7 numbers must not be quoted as the barrier. Scan candidates for a proton-transfer TS were produced (usable_as_guess) for the DFT OptTS.
- Nothing submitted for review yet; evidence submission follows the DFT TS/freq/IRC stage.

## S1 primary TS run update (ts/ts_0001)
- Guess strategy (attempts retained): (1) GFN2-xTB xtb_path -> path_not_converged at the 100-run cap, no usable guess. (2) Concerted 2-coordinate xTB relaxed scan P-O(3.15->1.80 A)+P-H(2.71->1.42 A) -> monotonic strain wall, no peak (ts/ts_0001/jobs/declaration_0005/scan/scan-task.chem-result.json). (3) IDPP A->B interpolation (runs/ts_interp_ts0001/img_00..10.xyz); midpoint img_06.xyz used as provided guess (P-O 2.29, O-H 1.85, P-H 1.88 A; H bridging O and P).
- Inputs cleared: atom_map [1,2,9,8,3,4,5,6,7,10,11], reaction_center [[2,9],[2,7],[9,7]]; frequency_mode removed from the ts_opt profile.
- NOW RUNNING: B3LYP-D3(BJ)/def2-SVP OptTS (job_id 18) from img_06; native input ts/ts_0001/jobs/declaration_0008/ts_opt/refine.inp (route '! OptTS B3LYP def2-SVP D3BJ TightSCF'). Next: frequency -> IRC both directions -> both endpoint minima.
