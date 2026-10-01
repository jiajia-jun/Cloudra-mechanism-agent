# HG2: partial backfill after reactant stereochemistry audit

Reaction: (E,E)-crotyl propenyl ether Claisen rearrangement, with competing
syn and anti aldehyde products. Fixed model: gas-phase ORCA 6.1.1,
B3LYP-D3BJ/def2-SVP, RIJCOSX/def2-J, TightSCF; charge 0, singlet.
All reported barriers are electronic energies without ZPE or thermal corrections.
Historical Gaussian energies were not used in any subtraction.

## Accepted anti channel

| Structure | Job | Energy (Eh) | Frequency result |
| --- | ---: | ---: | --- |
| Lowest specified (E,E) reactant minimum | 21 | -348.690242146502 | zero imaginary |
| Anti reactive TS | 53 | -348.648202350340 | one imaginary, -403.27 cm⁻¹ |
| Anti IRC product minimum | 56 | -348.710408259292 | zero imaginary |
| Anti IRC reactant minimum | 57 | -348.688498440674 | zero imaginary |

The accepted forward barrier is **26.38 kcal/mol**, relative to job 21.
Job 57 is an (E,E) reactant conformer 1.09 kcal/mol above that reference;
the reference was not changed to the IRC-connected conformer. The reactive
mode involves original reactant atom pairs C4–O5 and C2–C7 (1-based).
Bidirectional IRC job 55 terminated normally at ORCA's native iteration
limit; it did not converge to both minima. Unconstrained Opt+Freq jobs
56/57 establish the endpoint identities. Job 56 has mixed CIP labels
(S,R), agreeing with the anti product in the existing graph.

The historical anti-chair geometry was reused as an initial guess only.
It came from the user's archived `HG2_E1_ts3_final.xyz`; its old Gaussian
energy was not combined with the new ORCA reference.

## Rejected syn value for the specified substrate

Syn TS job 4 has a relevant imaginary mode (-403.47 cm⁻¹), and its
optimized product endpoint job 41 is genuinely syn, with CIP (S,S).
However, independent reconstruction of the **reactant** endpoint job 40
from its final XYZ establishes an **(E,Z)** ether, not the specified (E,E)
substrate. Both connectivity and double-bond stereochemistry were checked
using RDKit DetermineBonds and stereochemistry assignment from the 3D
coordinates:

| Job | Canonical isomeric SMILES | Alkene stereochemistry |
| ---: | --- | --- |
| 21, intended reference | `C/C=C/CO/C=C/C` | E,E |
| 40, syn IRC reactant endpoint | `C/C=C\OC/C=C/C` | E,Z |
| 57, anti IRC reactant endpoint | `C/C=C/CO/C=C/C` | E,E |
| 41, syn product endpoint | `C=C[C@H](C)[C@H](C)C=O` | S,S |
| 56, anti product endpoint | `C=C[C@H](C)[C@@H](C)C=O` | S,R |

Thus the subtraction giving 26.25 kcal/mol combines an E,Z-connected
saddle with the E,E reference. It is **not** an accepted E,E→syn barrier.
The purported 0.13 kcal/mol syn–anti difference is also withdrawn.
The old 29.67 syn value is not retained as a calculated replacement:
the syn edge is `null` pending a saddle connected to the specified E,E
reactant. The existing graph and the historical literature selectivity
anchor remain; **3.28 kcal/mol is not a difference measured in this campaign**.
No new favored-channel claim follows from the invalid comparison.

The original specialist and coordinator were notified of the E/Z mismatch
on 2026-10-01. Further seed work must retain both reactant E configurations,
atom mapping and the covalent skeleton before any formal TS calculation.

## Evidence locations

Remote root: `/data/cloudra/workspace/hard_resume_20260930/HG2_gold_20260929/paratera_20260930/`.
Raw evidence: `R_ref/`, `syn_ts_g2/`, `irc_g2/`, `irc_g2_ep_F/`,
`irc_g2_ep_B/`, `anti_ts_legacy/`, `anti_irc/`, `anti_ep_F/`, `anti_ep_B/`.
Each compute log is in the corresponding `.cloudra/calc-<job>.out.log`.
The archived evidence is retained even for the rejected E,Z-connected syn
candidate. Reports written before the E/Z audit may incorrectly describe
job 40 as the intended reactant or claim a comparable 0.13 kcal/mol gap.

Final XYZ SHA256 checks:

- Job 21: `007a715d80939b8d55a70dd4d8e221ebb7dce64840c8a2b8f70bb367591ebcbe`
- Job 40: `dec09bcc7027c229402c2796fe3a13322c28dd9a9865398e69bc416b8839ac48`
- Job 41: `f0c3f9b4ed535341c1ae86587deda7f6eea0e773e237c20234f241ed1e4a9cc6`
- Job 56: `a246c8335421034739343a95c1054c9a3a9b62072d7806848a6243458cdba321`
- Job 57: `3e99ba56703f667544d06eb1b819ee040db6ad98fed4f2bbb12ca92867785417`
