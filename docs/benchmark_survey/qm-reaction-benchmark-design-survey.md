# QM Reaction Benchmark Design Survey (Direction B)

**Scope**: How the computational-chemistry community builds and tiers reaction-barrier / thermochemistry
benchmark sets, with focus on GMTKN55, BH9, and the RDB7 / reaction-database family (Grambow 2020,
Transition1x). Goal: extract reusable design patterns for Cloudra's four-tier (Easy / Normal / Hard /
Impossible) validation set for autonomous organic-mechanism discovery, where the first three tiers must be
computable with xTB and the Impossible tier tests correct refusal on multireference problems.

**Retrieval trace & access barriers** (important for reproducibility):
- Full text read: RDB7 (Nature Sci Data PDF), Grambow 2020 (Nature Sci Data PDF), Transition1x (Nature Sci
  Data PDF), BH9 Supporting Information (ACS figshare SI PDF, ct1c00694_si_002.pdf).
- Abstract + verified metadata only (publisher 403 from this network: RSC, ACS, Wiley, ChemRxiv):
  GMTKN55 main text, BH9 main text, GFN2-xTB, MGCDB84, Good-Practices review, GSCDB137, ChemBench.
  Claims from these are flagged "[abstract]" or "[metadata]".
- Converted markdowns live in `docs/benchmark_survey/md/`; PDFs in `docs/benchmark_survey/pdfs/`.

---

## 1. GMTKN55 — category taxonomy + weighting instead of explicit difficulty tiers

Goerigk, Hansen, Bauer, Ehrlich, Najibi, Grimme, *Phys. Chem. Chem. Phys.* 2017, 19, 32184–32215.
DOI: 10.1039/C7CP04913G. Citations ~1960 (OpenAlex). CC-BY-NC.

- **Composition** [abstract]: 55 subsets, 1505 relative energies from 2462 single-point calculations;
  13 new subsets vs GMTKN30; reference values of "significantly higher quality" for most sets.
- **Taxonomy** (documented structure of the database; flagged as not re-read in full text here): five
  top-level categories — (1) basic properties & reaction energies of small systems, (2) reaction energies
  of large systems & isomerisation, (3) reaction barrier heights (incl. BH76, BHPERI, PX13, WCPT18,
  INV24), (4) intermolecular noncovalent interactions, (5) conformers & intramolecular NCI.
- **Reference values**: predominantly high-level WFT (W1/W2-type, CCSD(T)/CBS-quality), experiment only
  where sufficiently accurate. Paper emphasizes that *reference quality changes method rankings*.
- **Statistics**: per-subset MAD combined into weighted total MADs (WTMAD1/WTMAD2) with subset weights
  inversely proportional to mean |reference energy| — prevents large-magnitude sets dominating.
- **Robustness probes**: includes "mindless molecules" (MB16-43) to stress-test methods outside normal
  chemical space — an early example of an OOD/robustness tier.
- **xTB connection** [abstracts]: GFN2-xTB (Bannwarth, Ehlert, Grimme, *JCTC* 2019, DOI
  10.1021/acs.jctc.8b01176) benchmarks against GMTKN55-family data but parameterized on geometries,
  frequencies, NCI; the g-xTB preprint (ChemRxiv 2025, DOI 10.26434/chemrxiv-2025-bjxvt) reports
  WTMAD-2 = 9.3 kcal/mol on the full GMTKN55 — i.e., SQM-level methods sit at ~9 kcal/mol overall,
  implying xTB barrier errors of several kcal/mol must inform tolerance bands.

**Design lessons**: taxonomy by *property type*; weighted aggregation; reference-value quality > dataset
size; include an explicit robustness/OOD probe set; distribute geometries + references on a dedicated
website.

## 2. BH9 — modern barrier set: reaction-type taxonomy, DLPNO focal-point references, conformer-exhaustive TS protocol

Prasad, Pei, Edelmann, Otero-de-la-Roza, DiLabio, *J. Chem. Theory Comput.* 2022, 18, 151–166.
DOI: 10.1021/acs.jctc.1c00694. Preprint: ChemRxiv 2021, DOI 10.33774/chemrxiv-2021-mdjwx.
SI (computational details) read in full: ACS figshare, https://doi.org/10.1021/acs.jctc.1c00694 (files
ct1c00694_si_001.zip / si_002.pdf via api.figshare.com article 17211791/17211794).

- **Composition** [abstract]: 449 reactions, 9 reaction types common in organic/biochemistry; larger
  reactant molecules than previous barrier sets; "most comprehensive thermochemical benchmark set to date".
  SI shows the type-dependent treatment: radical addition, pericyclic, halogen-atom transfer, nucleophilic
  substitution, nucleophilic addition, H-atom transfer, hydride transfer, proton transfer, B/Si-containing.
- **Reference energies** [SI]: focal-point scheme — HF/a{T,Q}Z CBS extrapolation (alpha=5.79) +
  RI-MP2/a{T,Q}Z CBS (beta=3.05) + [DLPNO-CCSD(T) − MP2]/aTZ (TightPNO, frozen core). DLPNO error vs
  canonical CCSD(T) validated on a subset [abstract].
- **TS location protocol** [SI]: preliminary TS at B3LYP-D3(BJ) with Pople basis + basis-set
  incompleteness potentials (basis chosen per reaction type: 6-31G*-BSIP, 6-31+G*-BSIP, 6-31+G**-BSIP);
  CAM-B3LYP when B3LYP unstable (zwitterions); **constrained TS conformer search** (MacroModel,
  break/form bond distances frozen; up to 100 structures → ≤9 lowest → unconstrained re-optimization);
  final TS at CAM-B3LYP-D3(BJ)/6-311++G**; **verification gates**: exactly one imaginary frequency and
  eigenvector oriented along the reaction coordinate; TSs failing optimization or direction discarded.
- **Reactants/products** [SI]: built from TS, MCMM 100-step conformer search + PM6-DH2 prescreen,
  10 lowest re-optimized, final CAM-B3LYP-D3(BJ)/6-311++G**.
- **Assessment** [abstract]: used to rank common DFAs and to test BSIPs.

**Design lessons**: reaction-type taxonomy is the natural unit for difficulty/scope control; a level ladder
(cheap guess → mid-level TS → high-level focal-point SP); explicit conformer treatment *at the TS*, not
just minima; verification gates (1 imag freq, eigenvector direction) as acceptance criteria.

## 3. Grambow 2020 — exhaustive reaction enumeration under size/valence caps, with verification gates

Grambow, Pattanaik, Green, *Sci Data* 2020, 7:137. DOI: 10.1038/s41597-020-0460-4. Full text read.

- **Reaction selection**: all molecules ≤6 heavy atoms from GDB-7 (~770) + ~430 random 7-heavy-atom
  molecules (C,H,N,O only); unimolecular reactants. **Size cap ≤7 heavy atoms** chosen for tractability.
- **Driving-coordinate enumeration**: ≤2 bonds broken, ≤2 formed, ≤3 total changed (connectivity only,
  bond order ignored); valence caps per element; single-bond changes excluded (barrierless); equivalent-H
  duplicates removed; → several hundred driving-coordinate sets per reactant.
- **TS finding**: single-ended growing string method (GSM) at B97-D3/def2-mSVP; path truncated if >1 TS
  detected (enforces *elementarity*); up to 4 duplicate reactions retained for TS re-optimization, then
  lowest-barrier kept (TS conformers explicitly handled); refined at ωB97X-D3/def2-TZVP.
- **Verification gates (Technical Validation)**: exactly one imaginary frequency; imaginary-mode
  displacements must be largest along the bonds that change (mode-alignment check); reactions removed if
  TS-optimization energy changed >3 kcal/mol from string maximum; |imag freq| < 100 cm⁻¹ removed
  (conformational, not chemical, TS).
- **Diversity metrics published**: distribution of barrier heights (up to 200 kcal/mol deliberately kept —
  "not to bias models towards low-energy regions"), #bond changes, bond-change element pairs, and
  auto-extracted reaction templates (RDKit GetReactingAtoms; most templates have a single example →
  evidence of diversity).
- Deliverables: atom-mapped reaction SMILES + log files for reactant/product/TS at two levels of theory.

**Design lessons**: size cap + valence rules make enumeration reproducible; elementarity enforced
algorithmically; publish diversity metrics; keep high-barrier reactions to avoid distribution bias;
ship machine-readable atom maps as ground truth.

## 4. RDB7 — curated upgrade with CCSD(T)-F12 references, per-level error quantification, and validity subsetting

Spiekermann, Pattanaik, Green, *Sci Data* 2022, 9:417. DOI: 10.1038/s41597-022-01529-6. Full text read.
("RDB7" = the community name for this ≤7-heavy-atom reaction database; used e.g. in
*Digital Discovery* 2025, DOI 10.1039/d5dd00240k.)

- **Ground truth**: CCSD(T)-F12a/cc-pVDZ-F12//ωB97X-D3/def2-TZVP single points for ~22,000 species/TSs;
  ~11,926 reactions; 15 reactions re-run at cc-pVTZ-F12 to validate double-zeta. Barrier = ZPE-corrected
  TS − reactant (ZPE scale factors 1.014 / 0.984 per level).
- **Cleaning**: fixed Open-Babel SMILES resonance/charge errors (representative examples in Figs. 1–2);
  separated product complexes (30% two-product, 2% three-product) into individually re-optimized species;
  conserved charge/multiplicity; removed reactions where CCSD(T) enthalpy exceeded the barrier by
  >10 kcal/mol (suspicious submerged/negative reverse barriers).
- **Electronic-state control**: all singlet unrestricted; 49 radical-pair product sets treated as doublets
  with <S²> verified (0.75–0.77); <S²>=0 elsewhere.
- **Thermo corrections**: atom energy corrections + Petersson-type BACs fitted on ~400 well-known
  species (ATcT/CCCBDB, median experimental uncertainty 0.14 kcal/mol); validated on external Pedley
  test set (459 species; MAE 0.8, RMSE 1.2 kcal/mol); training species excluded from test.
- **Error quantification across levels** (Table 4): barrier RMSE vs CCSD(T)-F12a = 8.5 kcal/mol
  (B97-D3/def2-mSVP) and 5.0 kcal/mol (ωB97X-D3/def2-TZVP) → DFT-level "ground truth" is not gold;
  also shows RMSE is much larger on 10k diverse reactions than on the 206-reaction subset of ref. 57 —
  benchmark conclusions depend on dataset diversity.
- **Validity subsetting / designed abstention**: TST rate coefficients + Arrhenius parameters reported
  **only for a rigid-species subset** (RRHO + Eckart valid); explicitly *not* reported for flexible
  reactants/TSs where RRHO TST is inaccurate — a literature precedent for "refuse where the method is
  invalid".
- **Classification**: RMG reaction-family templates (keto-enol most frequent; majority match no template).

**Design lessons**: ship multi-level values (cheap → gold) so users can benchmark any method; quantify and
publish the cheap-vs-gold gap; define validity subsets instead of silently reporting everywhere; use
suspicious-physics filters (negative reverse barriers) as data-quality gates.

## 5. Transition1x — workflow thresholds, discard rules, leakage-free splits, ablation-style evidence

Schreiner, Bhowmik, Vegge, Busk, Winther, *Sci Data* 2022, 9:779. DOI: 10.1038/s41597-022-01870-w.
Full text read.

- Built on Grambow's 11,961 reactions; NEB (10 images, k=0.1 eV/Å²) then CI-NEB at ωB97x/6-31G(d)
  (chosen for ANI1x interoperability); 9.6M energy/force calculations, 10,073 converged reactions.
- **Convergence/discard rules**: endpoints relaxed to F<0.01 eV/Å; NEB to Fmax<0.5 eV/Å then CI-NEB to
  <0.05 eV/Å; **entire reaction discarded if CI-NEB not converged within 500 iterations** (unphysical
  configurations pollute training); path snapshots included only when cumulative Fmax since last inclusion
  >0.1 eV/Å (spread criterion).
- **Splits**: stratified by molecular formula — no formula appears in two splits (leakage control);
  test/val 5% each, must contain all heavy-atom types; molecules with <3 heavy-atom types kept in train.
- **Statistics**: report mean ± std of RMSE/MAE over repeated trainings.
- **Evidence-of-necessity ablation**: models trained on ANI1x/QM9 (near-equilibrium) fail in TS regions —
  used to prove the dataset fills a gap; directly analogous to Cloudra's planned "with/without DAG
  orchestration" and "with/without knowledge graph" ablations.

**Design lessons**: explicit numeric workflow thresholds; discard-and-document over ship-and-hope;
formula-disjoint splits; mean±std over seeds; cross-validation against popular datasets as an ablation.

## 6. Context papers (abstract/metadata level)

- **GFN2-xTB** — Bannwarth, Ehlert, Grimme, *JCTC* 2019, 10.1021/acs.jctc.8b01176: SQM method
  parameterized on accurate gas-phase reference geometries/frequencies/NCI; benchmarked on GMTKN55-type
  data. [abstract]
- **xTB review** — Bannwarth et al., *WIREs Comput. Mol. Sci.* 2021, 10.1002/wcms.1493: parameter
  availability Z≤86; cost-accuracy positioning. [abstract]
- **MGCDB84** — Mardirossian & Head-Gordon, *Mol. Phys.* 2017, 115, 2315–2372,
  10.1080/00268976.2017.1333644: 84 datasets / 200 DFAs; includes difficult/multireference-type subsets;
  OA copy at osti.gov/biblio/1477255. [metadata verified]
- **Good Practices in Database Generation for Benchmarking DFT** — Karton & de Oliveira, *WIREs CMS*
  2025, 10.1002/wcms.1737: best practices on reference quality, dataset size, geometries, basis sets,
  statistics, data availability; includes a decision flowchart. [abstract]
- **GSCDB137** — *JCTC* 2025, 10.1021/acs.jctc.5c01380: GMTKN55+MGCDB84 legacy sets re-referenced to
  today's best values; redundant/low-quality points removed. [abstract]
- **BHPERI cautionary tale** — Karton & Goerigk, *J. Comput. Chem.* 2015, 10.1002/jcc.23837: CBS-QB3
  references had RMSD ~2.5 kcal/mol vs Wn-F12; DFT rankings changed when references were upgraded.
  [abstract via Minerva Access record]
- **Enzyme-model benchmarking guide** — Wappett & Goerigk, *Theor. Chem. Acc.* 2021,
  10.1007/s00214-021-02770-9: reference level AND model size both change benchmark conclusions.
  [abstract via Minerva record]
- **Post-CCSD(T) barrier references** — Karton, *JPCA* 2019, 10.1021/acs.jpca.9b04611: CCSDT(Q)/CBS
  barrier heights; cost-effective post-CCSD(T) estimation. [abstract]
- **ChemBench** — Mirza et al., *Nature Chemistry* 2025, 10.1038/s41557-025-01815-x: framework for
  evaluating LLM chemical knowledge/reasoning vs human-chemist baseline — relevant precedent for
  agent-level evaluation, human baselines, and question-tiering. [abstract]
- **Graph/coordinate barrier prediction using RDB7 & RGD1** — *Digital Discovery* 2025,
  10.1039/d5dd00240k: confirms "RDB7" naming and its use as a standard test set. [abstract]

## 7. Distilled patterns for Cloudra's four-tier test set

1. **Tier axes**: combine (a) property/mechanism type (GMTKN55/BH9 taxonomy), (b) size cap (≤7–10 heavy
   atoms, Grambow/RDB7), (c) electronic-state complexity (closed-shell singlet → open-shell/radical pairs
   → multireference). Tiers should be *defined by method accessibility*, mirroring how SQM papers mark
   which GMTKN55 subsets are in-domain for xTB.
2. **Easy**: closed-shell, single-step, ≤7 heavy atoms, from RDB7/Grambow verified sets (ground truth
   includes TS + atom-mapped SMILES + CCSD(T)-F12 barrier). **Normal**: add conformational complexity
   (BH9-style TS conformer search) or two-product reactions. **Hard**: radical/open-shell, charged,
   or larger systems — still xTB-feasible (GFN2-xTB supports Z≤86, open shell) but with known accuracy
   degradation. **Impossible**: genuine multireference cases (MGCDB84 MR-type chemistry: e.g., singlet
   biradical TSs, O2 chemistry, C2/N2 bond-breaking) where xTB is *methodologically* invalid, not just
   inaccurate → the correct agent behavior is documented refusal with a diagnostic (e.g., MR character
   flags), following the RDB7 validity-subsetting precedent.
3. **Ground truth**: reuse published verified structures/references; record the level of theory of every
   reference value; keep uncertainty bands in mind (CCSD(T)-F12/DZ ~1–2 kcal/mol; DFT-level ~5 kcal/mol;
   xTB ~5–9 kcal/mol) — score barrier accuracy with tolerances ≥ the method's intrinsic error, and score
   *workflow success* (converged TS, 1 imag freq, IRC connectivity) separately from *energetic accuracy*.
4. **Verification gates as scoring criteria** (all from the surveyed sets): exactly one imaginary
   frequency; |ν_imag| ≥ 100 cm⁻¹ to exclude conformational TSs; imaginary-mode displacement aligned
   with the reacting bonds; endpoint/IRC connectivity (Grambow mode-alignment + BH9 eigenvector
   inspection); suspicious-physics filters (negative reverse barrier >10 kcal/mol → flag).
5. **Refusal/OOD design**: precedent = RDB7 reports rates only for the rigid subset; Transition1x discards
   non-converged reactions. For Impossible tier, ground truth = "system must abstain/flag", scored as
   correct abstention; also add GMTKN55-style robustness probes (outside normal chemical space).
6. **Statistics**: per-tier success rates with binomial CIs; mean ± std over repeated agent runs
   (Transition1x practice); stratified, leakage-free task splits; publish a failure taxonomy (Grambow's
   diversity/bond-change analysis is a template).
7. **Ablations**: Transition1x's cross-dataset validation is the model for "evidence-of-necessity"
   ablations — Cloudra's DAG-mode (3 modes) and graph/no-graph ablations should each show a metric that
   *degrades measurably* when the component is removed, with the same fixed task list and seeds.
8. **Data hygiene**: atom-mapped SMILES ground truth (Grambow); SMILES resonance/charge cleaning
   (RDB7); versioned, machine-readable manifests; keep high-barrier/hard cases in (don't truncate the
   difficulty distribution).
