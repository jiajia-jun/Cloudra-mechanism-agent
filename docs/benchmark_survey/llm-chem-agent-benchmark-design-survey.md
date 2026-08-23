# LLM/AI-Agent Chemistry Benchmarks — Test-set & Scoring Design Survey

**Scope**: How recent high-quality LLM chemistry-agent benchmarks design their test sets and scoring, to inform the Cloudra four-tier (Easy / Normal / Hard / Impossible) validation set for autonomous reaction-mechanism discovery.
**Date**: 2026-08-23. **Author**: literature-survey sub-agent (a-3).
**Local copies**: PDFs in `docs/benchmark_survey/pdfs/`, converted Markdown in `docs/benchmark_survey/md/`.

---

## 1. Papers surveyed

| # | Paper | Venue / Year | ID |
|---|-------|--------------|----|
| 1 | ChemBench — "Are large language models superhuman chemists?" | Nat. Chem. 2025 (arXiv 2024) | arXiv:2404.01475, DOI 10.1038/s41557-025-01815-x |
| 2 | ChemGraph — "ChemGraph: An Agentic Framework for Computational Chemistry Workflows" | arXiv 2025 | arXiv:2506.06363 |
| 3 | TSAgent — "TSAgent: An Agentic Workflow for Autonomous Transition State Search" | arXiv 2026 | arXiv:2605.14154 |
| 4 | ScienceAgentBench — "Toward Rigorous Assessment of Language Agents for Data-Driven Scientific Discovery" | ICLR 2025 | arXiv:2410.05080 |
| 5 | MaCBench — "Probing the limitations of multimodal language models for chemistry and materials research" | Nat. Comput. Sci. 2025 | arXiv:2411.16955, DOI 10.1038/s43588-025-00836-3 |

All five were read beyond the abstract (Methods/Evaluation sections; papers 1–5 converted with pdf2md and read in the methods sections).

---

## 2. Per-paper design points

### 2.1 ChemBench (knowledge-QA benchmark, 2788 QA pairs)
- **Task taxonomy (multi-axis, not one difficulty scale)**: each question annotated along *topic* (organic, physical, analytical, safety, …), *required skill* (knowledge / reasoning / calculation / intuition), and *difficulty* (basic vs advanced). Difficulty rubric is operational: "basic = high-school level skills; advanced = an expert needs minutes to hours to answer" (Sec. 4.5). → Lesson: annotate difficulty with an *operational* definition, not vibes.
- **Question sources**: mixed — 1039 manually curated (university exams, exercise sheets, IChO, textbooks, from scratch) + 1749 semi-programmatically generated from curated database subsets (ZINC, PubChem, Cameo, cheminfo.org; ground truth computed by tools, e.g. MAYGEN for isomer counts, OpenChemLib for NMR signal counts). (Sec. 4.1, Tables 1–2.)
- **Ground truth**: every question reviewed by ≥2 scientists besides the curator + automated schema checks; canary string (BigBench-style) to keep questions out of training corpora.
- **Scoring**: strict binary (partially correct = incorrect); text-completion-based so tool-augmented/black-box systems can be evaluated; regex parsing with LLM-fallback parser; greedy decoding.
- **Refusal / uncertainty**: refusal statistics reported per model (safety refusals under-estimate some topic scores, Table A7); verbalized confidence on a 1–5 ordinal scale elicited and calibration analyzed — models are systematically *overconfident* (Fig. 5). → Direct precedent for scoring calibration/abstention.
- **Human baseline**: 19 experts answer ChemBench-Mini (236 questions) via a web app; humans treated as "models" in the same metric; subset with tool use allowed vs not.
- **Practical economy**: ChemBench-Mini curated as a diverse, balanced subset to cut API cost (HELM-style full runs too expensive).

### 2.2 ChemGraph (agentic computational-chemistry workflows, 13 task templates / 260 instances)
- **Task difficulty = number of tool calls (structural complexity)**: 13 benchmark experiments organized by input type (molecule name / SMILES / reaction); simple tasks need 1–4 tool calls, the two reaction-thermochemistry tasks (react2enthalpy/react2gibbs) need 9–12. Difficulty is *quantified* by chain length, not declared ad hoc (Table 2, Fig. 4).
- **Instance generation**: template prompts with variable slots; molecules randomly sampled from PubChem with max-atom cutoffs scaled to task cost; fixed small-molecule list where DFT cost demands it.
- **Ground truth**: for every experiment×instance a *reference answer in structured JSON* — both the expected tool-call sequence and expected results, written as "how a domain expert would solve it". → Ground truth = expert trace + expected output, not just a final number.
- **Scoring**: two metrics — final-answer accuracy + number of tool calls used (efficiency vs human-manual baseline); structured-output mode (JSON schema) of the agent used for scoring; temperature 0, yet non-determinism across runs observed → repeated runs.
- **Single-turn vs multi-turn**: deliberate choice of *single-turn* evaluation because multi-turn correction paths differ per model and are not reproducible — a documented methodological trade-off.
- **Ablation**: single-agent vs multi-agent (Planner/Executor/Aggregator) on the two hardest tasks — task decomposition lifted GPT-4o-mini 17%→77%, Claude-3.5-haiku 57%→90%, matching/exceeding single-agent GPT-4o. → This is exactly the kind of "orchestration-mode" ablation Cloudra plans (DAG three-mode ablation).
- **Failure taxonomy reported**: wrong tool args, summarization/extraction errors (nested dicts, float vs complex), refusal-to-call-tool, hallucinated outputs. Refusals counted as incorrect under strict single-turn scoring.

### 2.3 TSAgent (autonomous TS search at DFT level — closest analog to Cloudra)
- **Benchmark source**: stratified subset (100) of an existing expert-built benchmark (OC20NEB: 600 reactions), filtered by reaction class — desorption excluded *because most are barrierless (no TS exists)* → explicit negative-class curation. Subset spans 100 surfaces, 51 elements, 29 adsorbates, 8 bond-breaking types; stratification documented in appendix.
- **Ground-truth philosophy (most important for Cloudra)**: they *deliberately do NOT compare absolute TS energies to the dataset*, because DFT energies depend on functional/k-points/settings and they cannot reproduce the dataset's exact settings. Instead success = **physics-based structural criteria**: (i) TS algorithm converged to threshold, (ii) exactly one significant imaginary frequency along the reaction coordinate (VFA), (iii) barrier height energetically consistent with endpoints. All three jointly required. → When ground truth is level-of-theory-sensitive, score *physics-validity criteria*, not numeric match. This directly supports Cloudra's "0/1 imaginary frequency + IRC connectivity" verification chain.
- **Budget-limited agentic evaluation**: fixed replan/debug budget (5 rounds per TS search); success declared only after validation; escalation to user when budget exhausted. Compute budget as a first-class experimental variable.
- **Scaling curve as evidence**: success rate vs replan budget (one-shot = 40%, grows with rounds) — proves gains come from iterative adaptation, not luck. Also distribution of replan *action types* to show policy diversity. → Cloudra analog: success vs DAG-replan/tool-call budget.
- **Human comparison**: 3 experts (3–5 yr DFT experience) on 10 held-out reactions, identical DFT settings and *pre-defined success criteria* for both sides; metrics = success rate, cpu-hours, operator effort (min). Agent 70% vs human 73±12%; agent uses ~3100 more cpu-hours/case but zero operator time. Wilson-score 95% CIs reported for all success rates (n=100). → Statistical rigor: CI on success rates, matched conditions, cost + human-effort as co-metrics.
- **Beyond-benchmark validation**: reproduce a published scientific result (BEP scaling relations for NH3 dissociation, 12 surfaces) — a "real investigation" tier beyond curated tasks.
- **Limitations honestly stated**: assumes reasonable reactant/product geometries given; LLM-based verification is not a physical guarantee.

### 2.4 ScienceAgentBench (ICLR 2025; 102 tasks from 44 peer-reviewed papers)
- **Task source = literature extraction with expert validation**: tasks extracted from peer-reviewed publications (code+data, permissive licenses); 9 subject-matter experts validate realism of each task; 110→106→103→102 tasks after multi-round filtering (annotator verification round re-executes programs to reproduce results; tasks with irreproducible/random results discarded). → Multi-stage QC funnel with explicit discard counts.
- **Ground truth**: annotated reference program adapted from the paper's released code, made self-contained; task-specific *executable* success-criteria scripts (e.g. ROC-AUC ≥ 0.77, math.isclose to gold answer) + GPT-4o-drafted, expert-refined rubrics (5 stages: data loading / processing / modeling / output formatting / saving).
- **Scoring**: array of metrics — Valid Execution Rate, binary Success Rate (conditioned on execution), CodeBERTScore (forced to 1.0 if SR=1), API cost; figure outputs judged by GPT-4o (3 samples averaged); rubric-based *human* evaluation complements outcome metrics to avoid under-rating near-misses.
- **Anti-contamination / anti-shortcut (directly relevant)**: (1) remove 5 random test-set points per dataset so memorized data loaders fail; (2) re-split data and replace test labels with dummies so agents that read ground-truth labels instead of computing fail. Preliminary study caught agents *cheating* by reporting test labels. → For Cloudra: guard against agents that "recall" literature barriers instead of computing them.
- **Repetition protocol**: 3 independent runs per task; best-run selection with explicit tie-break order (SR > VER > CBS > cost); mean±std reported in appendix. temperature/top-p fixed across models.
- **Expert-knowledge ablation**: same tasks with/without expert-provided knowledge pieces (32.4% → 34.3% SR).

### 2.5 MaCBench (multimodal; 9 task families over the scientific workflow)
- **Benchmark organized by workflow pillars** (information extraction / experiments / data interpretation), each with task families spanning the real research life-cycle — mirrors "agent must handle the whole pipeline" idea.
- **Curation workflow is a closed loop**: manual task selection → domain-expert validation → corpus → leaderboard → *ablation-driven manual error analysis feeds back into curation* (Fig. 6).
- **Ground truth & scoring**: MCQ scored by zero Hamming loss; numeric answers correct if MAE within tolerance (default 1%, up to 5% for some task types — tolerance fixed at curation time). → Numeric tolerance must be pre-registered per task type.
- **Random baseline normalization**: performance reported as gain over a random/MCQ baseline (accrel = acc − acc_baseline); numeric baseline = topic mean. → Always report a trivial baseline.
- **Refusal handling**: automated refusal detection (regex + fine-tuned BERT), retry up to 5 times, refusal counts reported per model. → Refusals are measured, not silently treated as errors.
- **Ablation suite (four controlled dimensions)**: modality (same info as image vs text), reasoning steps (same input, 1-step vs multi-step variants), terminology (with/without jargon), guidance (with/without step-by-step instructions). Plus prompt-wording sensitivity (Appendix A.7) and a *data-provenance probe*: performance vs Google hit count of the structure → evidence of pattern matching vs reasoning. → Ablations isolate *one factor at a time with otherwise identical inputs*.
- **Statistics**: entire benchmark run 5 times; std over runs as error bars; two-step averaging for combined tasks documented.

---

## 3. Design patterns transferable to the Cloudra four-tier test set

1. **Operational difficulty definitions.** ChemBench (expert-time rubric), ChemGraph (tool-call count), TSAgent (reaction class / replan budget) all *operationalize* difficulty. For Cloudra: define Easy/Normal/Hard by measurable proxies — # elementary steps, # required replans, conformer complexity, spin/charge — and Impossible by an *a priori decidable* physics criterion (multi-reference diagnostics, e.g. T1/D1 diagnostic, %TAE, or known requirement of CASSCF), so "impossibility" is itself ground-truth-labeled, not subjective.
2. **Mixed task provenance.** Combine (a) literature-extracted reactions (ScienceAgentBench: peer-reviewed sources + expert validation funnel with logged discard counts) and (b) programmatically generated instances (ChemBench semi-automatic, ChemGraph template×PubChem sampling) and (c) a few handcrafted adversarial/edge cases. Document the curation funnel and per-item source.
3. **Ground truth = physics-validity criteria when numbers are level-of-theory-sensitive** (TSAgent). For xTB-tier tasks, ground truth should be: optimized minima have 0 imaginary frequencies; TS has exactly 1; IRC connects declared endpoints; barrier consistent in sign/magnitude window. Numeric ground truth (barrier heights) only against values computed at a *documented identical* level of theory, or literature experimental barriers with a stated tolerance (MaCBench: pre-registered 1–5% tolerance per task type).
4. **Strict binary primary metric + complementary soft metrics.** All five papers use binary success as the headline; add (a) efficiency (tool calls / cpu-hours / wall time — ChemGraph, TSAgent), (b) stage-level credit (ScienceAgentBench rubrics; Cloudra's per-stage DAG evidence is a natural rubric), (c) cost.
5. **Refusal/abstention as a scored behavior.** MaCBench detects and counts refusals; ChemBench analyzes miscalibration; TSAgent escalates when budget exhausted. For Cloudra's Impossible tier: score *correct refusal* as success, *hallucinated success* as the worst outcome — i.e. a 2×2 (computed/refused × possible/impossible) with asymmetric penalties. Also elicit verbalized confidence and report calibration (ChemBench Fig. 5).
6. **Budget-limited evaluation + scaling curves.** Fix a compute/replan budget per tier (TSAgent: 5 replans); report success vs budget curves and one-shot vs iterated success to show the value of the orchestration loop rather than lucky first guesses.
7. **Anti-shortcut / anti-contamination.** ScienceAgentBench's two mitigations (perturb test data; dummy labels) map to Cloudra as: hold out reactions published after the model cutoff or from SI-only sources; require the DAG evidence trail (logs, job IDs) so a "memorized barrier" cannot pass — success must bind to executed computations, which Cloudra's DAG harness natively enforces. Consider canary strings (ChemBench) if the test set is published.
8. **Human-expert reference.** TSAgent and ChemBench both benchmark against domain experts under *identical inputs and pre-registered success criteria*, reporting both success and effort (operator minutes). Even a small (n≈10) expert set with CIs is publishable.
9. **Statistical rigor.** Wilson-score CIs on success rates (TSAgent); 3–5 repeated runs with mean±std (ScienceAgentBench, MaCBench, ChemGraph); fixed decoding settings; best-of-n selection with a *pre-declared* tie-break order; trivial-baseline normalization (MaCBench random baseline).
10. **Ablation design = one factor at a time, otherwise-identical inputs.** MaCBench's four ablation axes and ChemGraph's single-vs-multi-agent ablation are the template for Cloudra's DAG three-mode ablation and graph/no-graph ablation: same reactions, same budget, same models; vary only the orchestration mode / KG availability. Report per-tier (not just aggregate) effects — ChemGraph shows ablation benefits concentrated in the hardest tasks.
11. **Stratification and reporting by subgroup.** TSAgent stratifies by reaction type and reports per-class success (dissociation 90% vs H-transfer 76%); ChemBench reports per-topic. Cloudra should pre-register reaction classes (e.g. pericyclic, SN2, E2, proton transfer, radical) and report per-class and per-tier.
12. **Beyond-benchmark "real investigation" tier.** TSAgent's BEP-reproduction study and ChemBench's leaderboard framing suggest a final validation: pick 1–2 published mechanistic studies and reproduce their full mechanism end-to-end, as a qualitative capstone beyond the graded set.

## 4. Gaps / things none of the surveyed papers do (Cloudra novelty opportunities)
- None has a benchmark tier whose *label* is "not computable at this level of theory, correct answer = refuse" — Cloudra's Impossible tier with multi-reference systems is, to our knowledge, novel. Closest are refusal-counting (MaCBench) and confidence calibration (ChemBench), but neither ties abstention to a physics-decidable ground truth.
- None verifies mechanism *paths* (IRC connectivity) as scoring criteria except TSAgent's endpoint-consistency check — and TSAgent does it agent-side, not benchmark-side. Cloudra's DAG stage-contract scoring (geometry→frequency→TS→IRC→identity→thermo) is more fine-grained than any surveyed benchmark.
- Only ChemGraph ablates orchestration topology; none ablates a knowledge graph.

## 5. Blockers / caveats of this survey
- ChemGraph and TSAgent are arXiv preprints (not yet peer-reviewed at survey date); treat their protocols as emerging practice.
- ChemBench v2 (Nov 2024) was read; the published Nat. Chem. 2025 version may differ slightly in numbers.
- MaCBench SI task table (Table A.1) only partially read; per-task question counts not exhaustively extracted.
- All claims above were taken from the converted Markdown of the actual PDFs (paths in §1); line-level quotes available in `md/` files.
