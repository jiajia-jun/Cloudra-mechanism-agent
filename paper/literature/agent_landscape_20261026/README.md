# Computational chemistry / atomistic agent landscape (26 October 2026)

**Status: source-coded, structured literature sample; not an exhaustive review or estimate of field prevalence.**

The figure and its denominator were finalized after screening the primary sources below. Cloudra is shown only as the present work's design focus and is not in the denominator. No Cloudra benchmark outcome is encoded.

## Deliverables and reproduction

- `systems.json` and `systems/*.json`: one record per included system, with physical targets, separate boundary-condition facts, positive task codes, primary URL, source locator and limitations.
- `source_index.csv`: human-readable source/evidence table, one row per system.
- `screening.json`: exclusions, adjacent systems and candidates not fully screened.
- `counts.json`: machine-derived counts, independently reconciled by `verify_counts.py`.
- `build_dataset.py`: explicit source coding; `plot_landscape.py`: reproducible vector/raster exports.
- `../../figures/agent_landscape.svg`, `.pdf`, `.png` (400 dpi).

Run from repository root:

```sh
MPLCONFIGDIR=/private/tmp/cloudra-agent-plot-cache .venv/bin/python paper/literature/agent_landscape_20261026/build_dataset.py
MPLCONFIGDIR=/private/tmp/cloudra-agent-plot-cache .venv/bin/python paper/literature/agent_landscape_20261026/plot_landscape.py
.venv/bin/python paper/literature/agent_landscape_20261026/verify_counts.py
```

The main figure is 180 mm wide × 270 mm high, intended as a full-width portrait page; the smallest font is 7 pt at that size. Use the SVG/PDF at 180 mm without further reduction. PNG is a 400-dpi preview/export, not an AI-generated figure.

Matplotlib 3.11.1 in the repository environment was used. The bundled document Python runtime had no matplotlib; no packages were installed.

## Scope and coding protocol

**Window:** first public reports from 1 January 2023 through 26 October 2026. The sample happens to have no eligible 2023 report; this is not evidence that no such work existed.

**Unit:** a separately described computational agent system, not each LLM backend, benchmark task, article version or ablation. Inclusion requires an LLM to plan, invoke, modify or make feedback decisions in an actual computational chemistry/atomistic simulation workflow. Full autonomy is not required. Thus MDAgent's human assistance and Agent-MD's selective LLM placement are retained and disclosed.

Pure QA, property prediction without running an atomistic calculation, generative molecular design alone, wet-experiment orchestration alone, and non-LLM deterministic automation are outside the main denominator. Estructural is included because the inspected examples invoke constrained xTB relaxation; calling it only molecular generation would misclassify actual computation. TS-like geometry generation does not receive the reaction-path/TS task mark when the later DFT validation was performed independently.

**Discovery:** supplied seed list spanning molecular and materials systems, targeted web searches for LLM quantum-chemistry and molecular-dynamics agents, and one-hop citation/reference checks. Search phrases included `LLM agent molecular dynamics simulations MDCrow autonomous 2024 2025`, `LLM agent quantum chemistry simulations 2023 2024 2025 automation computational chemistry`, and `LLM agent molecular dynamics autonomous simulation 2024 2026`. Primary arXiv, journal and author/project pages were read; search/review pages served only as discovery leads. This is a structured convenience sample, without a database-complete or PRISMA-style search. Unfinished leads are retained in `screening.json` rather than silently disappearing.

**Physical target** and **boundary conditions** are separate fields. Main object classes are (i) extended atomic materials/surfaces, (ii) finite molecules/coordination complexes, and (iii) polymer/biomolecular/host–guest soft-matter systems. `cross_domain` and `unresolved` are permitted but have no cases in this coding. A solvated protein or polymer does not move to the materials class because its simulation box is periodic. Conversely, a general ASE/ORCA interface does not establish demonstrated cross-domain coverage. Quntur/Forjador span calculation types; their demonstrated targets remain finite molecular examples.

**Tasks:** T structure construction/editing; E energy/electronic/material properties; O geometry relaxation; F vibrations/thermochemistry; R transition pathways/TS (including nonreactive dislocation migration); D MD or quantum dynamics. These six bins overlap. Marks reflect positive evidence from inspected reports, not a comprehensive assessment of the software. Blank cells explicitly mean **not encoded from reviewed evidence**, never “not supported.” A system's operation can be demonstrated even when a particular attempted calculation fails; marks are not scientific pass rates. Coverage is not task difficulty, end-to-end completion or scientific acceptance: an R square can represent an isolated path-search task, a multistage study, or an algorithm-evolution experiment, and cannot equate those task units to a complete mechanism-delivery benchmark. Conventional operators are not credited as newly invented algorithms.

**Version handling:** preprint/journal counterparts of AtomAgents, ChemGraph, MASTER and El Agente Q count once. DREAMS and Aitomia revisions count once. Each source URL identifies the version used where available; `first_public_date` does not imply the cited latest version existed on that initial date. ARCHE's full PDF exceeded the web reader's size limit; abstract-level inclusion and the independent parent researcher's SI check are distinguished. Dates for non-arXiv systems use the inspected journal publication date, not an unverified earliest-preprint claim. Aitomia's current repository TS/IRC support is not used as proof of an inspected-preprint benchmark result.

El Agente Q, Quntur, Estructural and Forjador are separate in the main analysis because they present distinct architectures/evaluations and tasks; the family-level sensitivity merges all four. This is a choice of counting unit, not four independent research groups.

## Count reconciliation and interpretation

| Physical target | n | Share of this sample |
|---|---:|---:|
| Extended atomic materials / surfaces | 14 | 53.8% |
| Finite molecules / coordination complexes | 9 | 34.6% |
| Polymer / biomolecular / host–guest soft matter | 3 | 11.5% |
| Cross-domain / unresolved physical target | 0 | 0.0% |
| **Total** | **26** | **100%** |

R is broader than chemical reaction mechanisms: AtomAgents contributes a dislocation-migration NEB example. Therefore R=6 must not be described as six mechanism-discovery agents.

Positive task counts are T=18, E=17, O=18, F=9, R=6, D=8; their sum exceeds 26 because tasks overlap. These are lower bounds on documented coverage within the inspected evidence, not total capability counts.

The defensible finding is **“extended-materials and surface systems account for about half of this structured sample.”** Although 14/26 is a bare numerical majority, the sample does not support a general claim that computational chemistry agents are predominantly periodic-material systems. Molecular mechanism agents and geometry-oriented agents are substantive near neighbours, and sensitivity to discovery/coding makes a broad prevalence claim unjustified.

## Sensitivity analyses

- Merge the four El Agente systems into one family: **N=23**, materials/surfaces 14, finite molecules 6, soft matter 3 (60.9% materials).
- Add TSBench's benchmark-contained agent environment as a separately counted system: **N=27**, materials 14, finite molecules 10, soft matter 3 (51.9% materials). It is excluded from the main system-development denominator to avoid conflating a benchmark environment with an independently proposed general research system.
- Restrict to materials/surfaces and finite molecular QC (remove the three soft/biomolecular systems): **N=23**, materials 14, finite molecules 9 (60.9%). This answers a narrower question and must not replace the full-scope denominator without disclosure.
- Merge the El Agente family and include TSBench: **N=24**, materials 14, finite molecules 7, soft matter 3 (58.3%).

No confidence intervals are reported: these are coded sample counts, not a probability sample. Unknown PBC is preserved in text rather than filled as nonperiodic.

## Cloudra and nearest-neighbour limits

Cloudra is positioned here as **organic small-molecule mechanism exploration**, with chemistry-aware perception and geometry operators supporting geometric reasoning, and an evidence DAG carrying scientific validation. Restraint and guided diagnosis connect these design choices. This is a positive design description, not an absence/presence ranking against other systems.

Estructural already exposes geometry operators, fragment binding and xTB constrained optimization; Quntur already demonstrates reaction-path work and discusses geometric bottlenecks; ARCHE already couples mechanism hypotheses with computed validation and has mapping/TS/frequency/IRC/endpoint components. ChemGraph's graph is an agent/workflow architecture, not automatically the same as a mechanism evidence DAG. These distinctions require architecture-level reading; the coverage matrix alone cannot establish novelty, superiority, benchmark success or exclusivity.

## Suggested figure caption

**Computational chemistry and atomistic simulation agents in a structured literature sample.** (a) Physical targets demonstrated by 26 separately described systems reported from 2023 to 26 October 2026. Extended materials and surface models are distinguished from finite molecules/complexes and polymer/biomolecular systems; simulation boundary conditions are recorded separately. (b) Positive task evidence in inspected primary reports. Tasks overlap, and blank cells denote unencoded evidence rather than absent capabilities. Coverage does not measure task difficulty, end-to-end completion or scientific acceptance. Preprint and journal versions are deduplicated; the four El Agente systems are separately counted, with family-level sensitivity provided in the accompanying dataset. This non-exhaustive sample does not estimate field prevalence. Cloudra's design focus is shown separately and is excluded from the counts.

## Verification

The PNG was actually opened and inspected. The initial render revealed clipped physical-target labels and crowded task headers; both were corrected before export. Count totals and matrix column totals were recomputed from JSON, and every exported row has a primary URL and source locator. No full Cloudra test suite, live calculation or benchmark was run for this figure.
