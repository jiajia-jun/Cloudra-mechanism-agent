# Easy replacement candidates (screening, 2026-09-24)

This is a **new literature-led curation queue**, not a list copied from the
historical `ideapool/reaction_candidates/easy.md`. The old IDs in the table
identify slots to retire; a replacement must receive a **new task ID** so completed
benchmark runs continue to mean the same reaction. None of these candidates
is admitted to the default Easy set yet. Literature establishes a plausible
path, not a Gold-method barrier or a five-hour runtime.

## Why these slots

The Gold compute ledger for project `prj_e4c506da72a0417c` gives these spans
from first submitted job to last terminal job, including retries and parallel
jobs: D3 8.06 h, D4 7.75 h, F1 5.31 h, G2 19.83 h, M1 18.09 h, M8
22.98 h, P3 10.67 h. G3 exceeded 23 h and still had live calculations at
the last check. C1 and C3 produced no usable fixed-method Gold jobs. These
figures describe this campaign, not intrinsic molecular cost or agent-only
runtime. **G3 remains in Easy by user decision**: its bottleneck is to be
addressed through better reaction-coordinate and initial-guess construction,
not by replacing the ene reaction. D1 (4.99 h, IRC endpoint still partial)
stays on a watchlist.

## One-for-one screening queue

All SMILES below were checked with RDKit for formula and charge balance. The
"change" column records benchmark coverage lost or gained; it must be stated
in the eventual TaskSpec. Candidate IDs are provisional and never reuse the
old task IDs.

| New ID / old slot | Candidate reactants `>>` products | Why it might be easier; change in coverage | Primary source |
|---|---|---|---|
| R1 / C1 | `[O-]CCCl>>C1CO1.[Cl-]` (2-chloroethoxide cyclization) | Intramolecular SN2 avoids two-body approach geometry; still an anion and the chloride product may remain an ion pair. Eight atoms versus six in C1, so size alone does not guarantee speed. | [Kostal & Jorgensen, JACS 2010](https://doi.org/10.1021/ja1023755) |
| R2 / D3 | `C1=CC=CC1.C=C>>C1=CC2CCC1C2` (cyclopentadiene + ethylene → norbornene) | Same Diels–Alder class; one ethylene replaces the second cyclopentadiene, removing dimer channels and reducing 22 to 17 atoms. Reactant-complex orientation still needs proof. | [Walsh & Wells, gas kinetics](https://doi.org/10.1039/P29760000052); [Houk et al., computed saddles](https://pmc.ncbi.nlm.nih.gov/articles/PMC3420159/) |
| R3 / D4 | `C1=CC=CC1.C=O>>C1=CC2OCC1C2` (cyclopentadiene + formaldehyde hetero-Diels–Alder) | Retains an O-containing cycloaddition, uses 15 instead of 19 atoms, and removes endo/exo and acrolein-substituent alternatives. The published TS is nearly synchronous (forming-bond difference 0.04 Å), a useful seed but not proof of a quick fixed-method search. | [Jursic & Zdravkovski, J. Phys. Org. Chem. 1994](https://doi.org/10.1002/poc.610071109) |
| R4 / F1 | `[BH3].C=O>>COB` (borane reduction of formaldehyde) | Retains hydride transfer and B–O formation with a neutral, eight-atom system instead of charged borohydride. The Lewis adduct and hydride-transfer TS still need separate identification. | [Ab initio borane reductions, JOC 1996](https://doi.org/10.1021/jo961159q) |
| R5 / G2 | `NC=O>>N=CO` (formamide → formamidic acid) | Six-atom intramolecular H transfer avoids a two-molecule, two-H trajectory. **Changes coverage** from diimide hydrogenation to tautomerization; direct gas-phase transfer has a high barrier. | [Wang et al., JPC 1991](https://doi.org/10.1021/j100178a032) |
| R7 / M1 | `CNC=O>>CNC=O` (N-methylformamide cis/trans amide rotation) | Nine versus about 28 atoms; retains hindered bond rotation. **Changes coverage** from atropisomeric aryl–aryl rotation to amide rotation. Cis/trans require geometry-level evidence because both endpoints have the same unmarked SMILES. | [Shin et al., gas-phase conformers](https://doi.org/10.1016/j.molstruc.2006.01.005) |
| R8 / M8 | `C1OCOCO1>>C1OCOCO1` (1,3,5-trioxane chair inversion) | Same six-membered-ring inversion, 12 versus 18 atoms; high symmetry may help. The literature still finds envelope TSs and pseudorotation, so a smaller molecule does not prove an easier search. | [Ionescu et al., JPCA 2005](https://doi.org/10.1021/jp052197t) |
| R9 / P3 | `C[N+]#[C-]>>CC#N` (methyl isocyanide → acetonitrile) | Six versus 14 atoms, neutral single-molecule rearrangement with a published TS. **Changes coverage** from a Claisen [3,3] shift to methyl migration. | [Nguyen et al., JPCL 2018](https://doi.org/10.1021/acs.jpclett.8b01259) |

**C3 has no safe like-for-like Easy replacement.** Its double-inversion path
shares the same unmarked reactant/product SMILES as C1, and the methyl H atoms
are equivalent. That distinction needs atom-resolved TS/IRC evidence, not just
a graph comparison. Move the original stereochemical challenge to a later tier
or retire it; do not silently substitute a second ordinary SN2 problem.
[Original double-inversion study](https://doi.org/10.1038/ncomms6972).

**G3 is retained, not a replacement slot.** A propene + formaldehyde
carbonyl-ene reaction (`C=CC.C=O>>C=CCCO`) can be a diagnostic comparison
for seed construction, but it is not approved to displace the propene +
ethylene benchmark. [Original carbonyl-ene TS study](https://doi.org/10.1021/ja00257a008).

R5 and R9 change reaction class substantially. Their pilots may establish
independent Easy tasks, but a fast result alone does not make either a
one-for-one replacement for G2 hydrogenation or P3 Claisen rearrangement.
The original systems are already minimal examples of their classes, so
retaining them with better TS seeds may preserve more benchmark value than
substituting unrelated chemistry.

Alternates if the closest analogue fails: R7 can instead be
2,2'-difluorobiphenyl rotation (preserves the aryl axis but still has 22
atoms; [primary calculation](https://doi.org/10.1021/ja00037a053)); R8 can
instead be 1,4-dioxane chair inversion (14 atoms but ten characterized
stationary points; [primary calculation](https://doi.org/10.1021/jp962932o)).

## Admission gate

For each candidate, run the fixed gas-phase ORCA 5.0.2
B3LYP-D3(BJ)/def2-SVP/def2-J RIJCOSX method used by existing Easy Gold.
Retain all inputs, logs, job IDs, atom maps, and timestamps. Establish a
zero-imaginary-frequency reactant minimum, a one-imaginary-frequency TS with
the intended mode, a two-sided IRC with chemically correct atom-mapped
endpoints, and zero-imaginary-frequency endpoint optimizations. Compute the
electronic `barrier_kcal_mol` in the declared central-complex frame and do
not import a literature Ea, ΔH‡, or ΔG‡ as ΔE‡. Measure end-to-end pilot
time; the target is at most five hours including TS search and verification.
If a candidate misses this gate, keep the old slot out of the default Easy
set while screening its alternate. Only after a passing pilot should the new
curation source feed `gen_easy_tasks.py`, regenerate TaskSpec JSON, and pass
the deterministic regeneration test. Historical task IDs and batch snapshots
remain untouched.

First fixed-method pilot: R9 methyl isocyanide on isolated Gold project
`prj_a9403e0ecdb64ad9`. Both endpoint Opt+Freq jobs (300/301) finished as
zero-imaginary minima. Literature-seeded TS job 302 finished with normal
termination and one imaginary mode at −457.09 cm⁻¹. The provisional
electronic barrier is 44.50 kcal/mol from optimized CH3NC; two-sided IRC job
304 is still running, so the barrier and replacement decision are **not**
admitted Gold results. R2 pilot runs separately in project
`prj_7798fe5221974b05`; endpoint jobs 305/306 were submitted at
2026-09-24 15:07 UTC and are awaiting outcome.
