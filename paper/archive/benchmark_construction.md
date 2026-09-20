# Benchmark construction: how the reaction set is built and how it is scored

> Read directly into the paper's Methods / Benchmark section. Written as narrative,
> not as a technical manual. All facts below are pulled from `cloudra/benchmark/`
> (schema.py, gen_*_tasks.py, graph_similarity.py, integrity.py, selfconsistency.py,
> accuracy.py, runner.py, refusal.py), `ideapool/tasks/`, and the candidate pools in
> `ideapool/reaction_candidates/{easy,normal,hard,impossible}.md`.

---

## 1. The question the benchmark asks

Existing computational-chemistry benchmark suites answer one question: *how accurate
is a given electronic-structure method on a defined family of reactions?* GMTKN55,
BH9, and the RDB7/Transition1x family are repositories of reference energies and
geometries against which density functionals and machine-learned potentials are
validated. They are method benchmarks, and they are scored on a single axis — a
distance to a reference number.

Cloudra's benchmark asks a different question: *can an autonomous agent discover,
and defend, a reaction mechanism end-to-end?* A mechanism is not a single number.
It is a claim about which species appear, in what order, through which transition
states, which bonds break and which form — a claim that must be backed by evidence
rather than asserted. This reframing has three consequences for how the task set is
scored.

First, correctness is *structural*, not merely energetic: the agent must reproduce
the topology of a mechanism graph, not just a barrier height. Second, every claim
must be *verified*, not asserted: a transition state must be a genuine first-order
saddle, its intrinsic reaction coordinate must connect the stated reactants and
products, and each species must be a real minimum. Third, every claim must be
*grounded*: each node and step in the delivered graph must be bound to a concrete
quantum-chemistry input/output file on disk, so that "I found this mechanism" is
backed by a traceable artifact rather than by the agent's own prose. The benchmark
therefore measures a mechanism in the same gradeable units a human reviewer would
use.

It also asks a second question that no chemistry benchmark we are aware of poses:
*does the agent know where its allowed level of theory stops being reliable?* Every
task in the set is deliberately restricted to a single-reference level of theory
(MACE-OMol25 / xTB). A substantial class of chemically important systems — singlet
biradicaloid transition states, near-degenerate diradicals, bond-breaking
dissociation curves — lies beyond this boundary, where single-reference methods
return qualitatively wrong answers (wrong level ordering, spurious symmetry
breaking, barriers off by tens of kcal/mol). The correct behaviour there is not a
number but a scientifically grounded refusal that names the multi-reference
diagnostics (T1, D1, %TAE[(T)], C0², diradical index) and the treatment that would
be required (CASSCF / CASPT2 / MRCI). The benchmark thus measures not only
competence but epistemic honesty at the boundary of method validity.

---

## 2. The reaction set: a taxonomy over mechanism type and electronic complexity

The task set is organised into four tiers. Unlike a single difficulty ladder, the
tiers are defined by a combination of (a) mechanism / electronic-complexity type,
(b) a heavy-atom size budget, and (c) whether the allowed single-reference level of
theory can treat the state at all. Tier membership is therefore a statement about
method accessibility, mirroring how semi-empirical papers designate which GMTKN55
subsets fall inside a method's comfort zone. In total the set holds **100 reaction
tasks** across the four tiers — 30 Easy, 30 Normal, 20 Hard, 20 Impossible —
together with 20 "sibling" control tasks that pair with the Impossible set (120 task
specifications in all).

**Easy — textbook single-step processes.** These are reference-grade, closed-shell,
single-step gas-phase reactions and intramolecular processes: pericyclic reactions
(Diels–Alder, Cope, Claisen, electrocyclic), SN2/E2 substitutions and eliminations,
carbonyl addition/reduction, proton transfer and tautomerisation, and
conformational/rotational interconversions (atropisomeric rotation, pyramidal
inversion, torsion). The selection criterion is a "comfort zone" heuristic anchored
to the allowed surrogate (MACE-OMol25): main-group CHNO archetypes with a few
F/Cl/Br/S/B, closed-shell singlet, and at most ~7 heavy atoms (the two bimolecular
Diels–Alder partners and one axial-chirality case are explicitly relaxed). The
tier is calibrational: these are the reactions whose mechanisms are textbook
certain, so a correct answer means the agent has run a clean, self-consistent
single-step mechanism rather than a hard one.

**Normal — competing routes and multi-step networks.** The increment is not simply
"bigger molecules." It is the appearance of *mechanism choice*. Three layers stack:
route-competition discrimination on a single substrate (SN2 versus E2, Zaitsev
versus Hofmann, spiro versus planar), simple multi-step networks (2–3 elementary
steps with a capturable intermediate), and fully named-reaction networks (3–4
steps). The chemistry is deliberately classic — aldol/enolate condensation,
carbonyl–amine condensation, acyl transfer (AAC2/BAC2), oxygenation and epoxide
chemistry — but the task is now to generate a multi-step hypothesis, capture the
intermediate, rank competing pathway barriers, and *prune* a reaction network DAG
down to the operative branch. The heavy-atom budget rises to ≤12 (catalysts and
water are written explicitly into the reactant/product SMILES), which keeps the
surrogate inside, or just at the edge of, its high-density region while admitting
the named reactions.

**Hard — stereochemistry.** Here the mechanism is no longer determined by
connectivity alone but by *three-dimensional* selectivity. Three kinds of question
are included: stereospecificity (a substrate configuration or alkene geometry maps
deterministically to a product configuration — Woodward–Hoffmann torquoselection,
syn/anti addition, SN2 inversion); stereoselective competition (a barrier difference
between two diastereomeric transition states sets an endo:exo, dr, or ee); and
configurational-stability barriers (atropisomer racemisation). The gold graph for
each hard task therefore contains both competing pathways — the operative and the
suppressed — and the energetic anchor is the *selectivity spread* (ΔΔG‡/ΔΔE‡
between the two), not an absolute barrier. This tier is the one that stresses the
agent's ability to reason about a potential-energy surface in full three dimensions
and to discriminate between near-degenerate transition states.

**Impossible — beyond single-reference validity, and the correct call is to refuse.**
These are strong-static-correlation and near-degenerate diradical systems:
biradicaloid transition states (cyclobutadiene automerisation, Dewar-benzene ring
opening, disrotatory electrocyclisation), twisted/near-degenerate diradicals,
open-shell singlet states (singlet oxygen, methylene, benzyne), anomalous-bond
molecules (O3, FOOF), and bond-breaking dissociation curves (C2, N2). They are
selected not because they are hard to compute but because the allowed single-reference
level of theory is *methodologically invalid* there — and this invalidity is
established a priori by offline multi-reference diagnostics (consensus over T1, D1,
%TAE[(T)], C0², and natural-orbital diradical indices), not by "the job failed at
runtime." Each sample is paired with a **sibling** control: the same reaction family,
single-reference-solvable, so that a correct refusal is attributable specifically to
the multi-reference character of the problem rather than to generic difficulty.

---

## 3. How the score is computed

The scorer never trusts the delivered claim. It audits the agent's sandbox and grades
the mechanism through a layered pipeline; a single scalar is the composite of three
components scaled by how well the mechanism is grounded in evidence.

**Layer 1 — integrity (evidence binding).** The pipeline recursively scans the agent's
working directory, loads the delivered `mechanism_graph.json`, and binds every graph
node to concrete computational evidence files. Binding uses the `smiles:` annotation
line that the task contract requires every evidence file to carry; because Gaussian
and ORCA echo their input title/comment lines into their output logs, this annotation
propagates into the QM results, so the binding is to a *parseable quantum-chemistry
artifact*, not to a file name. Matching is graded: an exact fingerprint/hash match
gives full quality; a protonation- or charge-state-only variant gives partial credit;
no match gives zero. A transition state, which carries no SMILES, is counted as
evidenced only when a step routes through it and both endpoints are themselves bound.
The output is `binding_quality` — the average quality over the graph's claims. A
mechanism graph that is missing, unparseable, or bound to no evidence at all is
*penalised*, not merely unscored: an unsupported mechanism is treated as worse than
no mechanism, because it asserts a result without supporting it.

**Layer 2 — self-consistency (physical validity, independent of the gold).** This
layer checks that the delivered evidence describes a physically admissible surface.
A transition state must be a first-order saddle — exactly one imaginary frequency,
and with |ν_imag| ≥ 100 cm⁻¹ to exclude conformational rotation masquerading as a
reaction coordinate. Its IRC must connect the two stated endpoints. Every species
must be a true minimum (no imaginary frequency). Files without a frequency block
yield no verdict rather than a spurious failure. This is the layer that detects the
"completion by assertion" failure mode: a mechanism whose transition state is merely
a minimum, or whose IRC runs off to the wrong species, is rejected regardless of
whether it happens to match a literature barrier.

**Layer 3 — accuracy (energetics).** The agent's reported barrier is compared to the
reference under a Gaussian tolerance, score = exp(−(agent − gold)² / 2σ²), where σ is
per-task. Because the reference itself carries method-level uncertainty, the penalty
is capped (each component can cost at most 0.3) so that a legitimate level-of-theory
difference is not mistaken for a mechanistic error. σ is tighter on the Normal and
Hard tiers (2.0 kcal/mol) than on Easy (3.0 kcal/mol).

**Graph similarity — structural correctness.** Parallel to the three layers, the
delivered graph is compared to the gold graph by a chemical-parameterised edit
distance. Default scoring is *subgraph coverage*: the gold graph must embed into the
delivered graph, and any extra nodes or steps the agent proposes are free ("thinking
more is never punished"); only missing or chemically mismatched gold elements cost.
Node substitution costs use a canonical-SMILES shortcut first and fall back to a
sigmoid of Morgan-fingerprint Tanimoto distance, with stereochemistry layered in —
ignored on Easy/Normal, costly on Hard. Edge substitution cost is the symmetric
difference of the two steps' atom-mapped bond-change sets (which bonds break and
form), with a penalty for a missing transition state. Transition states are folded
into the elementary-step edges of a lifted graph, so a missing TS, a wrong TS, or a
wrong connectivity all surface as an edge edit. The score is 1.0 when the gold graph
is fully covered.

**Composite.** The final score is a weighted blend of the three layers
(graph 0.5, self-consistency 0.2, accuracy 0.3) **multiplied** by the Layer-1
`binding_quality`. The multiplicative form encodes a key design principle: superior
chemistry with unsupported evidence is not worth a full score, because an
evidence-free mechanism assertion is exactly what the system is designed to prevent.
Separately, every run is classified into one of three outcomes — answered, refused,
or failed — which is orthogonal to the numeric score and is what the Impossible tier
is principally measured on.

**The refusal metric is cross-tier.** Because an agent can always "solve" the
Impossible tier by refusing everything, the refusal score is a two-dimensional
precision/recall computed *across all tiers*: a blanket refusal earns perfect
Impossible recall but collapses precision on the answerable tiers, and vice versa.
This is the standard abstention-benchmark guard against gaming, and it is the reason
the Impossible tier is paired with answerable siblings and measured against the
Easy/Normal/Hard refusal baseline.

---

## 4. Reference values and honest accounting

Where a reference barrier exists, it is a human-curated literature anchor recorded
with its *verification status* (verified, partially verified, unverified — or
computed by us) and its *frame of reference* (a barrier relative to a reactant
complex versus relative to separated reactants is a different number, and the two
must not be conflated, especially for the double-well ion–molecule surfaces). Many
anchors are still unverified literature transcriptions; the design explicitly allows
a reference to be marked `computed_by_us`, meaning we compute the reference with our
own controlled calculation and replace the literature value. This last point is where
the benchmark's own rigor is exercised: the gold references are themselves to be
re-derived in-house, tier by tier, and the set is frozen only after each answerable
task is confirmed solvable at the allowed level of theory.
