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

## Assignments (dispatched)
- S1 small_mol (as_63de2ab4d28941b5): primary durable ts_prepare/ts_resume run at B3LYP-D3(BJ)/def2-SVP, both IRC directions + both endpoint minima; verdict H1/H2. Logs under runs/.
- S2 small_mol (as_7473bc09bc2a47e2): independent semiempirical (GFN2-xTB / PM7) path mapping, betaine test and TS guess. Logs under runs/explore/.

## Computed / submitted / reviewed
- Nothing computed yet. (inputs/ logs are copies of an earlier run, not evidence of the new step.)

## Open questions / next actions
1. Wait for S1 (formal TS) and S2 (exploratory profile); reconcile H1 vs H2.
2. Submit species evidence (A, B, and betaine if real) and step evidence (TS + freq + both IRC + endpoint minima) with native logs.
3. Declare delivery_targets on the real pathway; run dag_delivery_report; Supervisor final review.
