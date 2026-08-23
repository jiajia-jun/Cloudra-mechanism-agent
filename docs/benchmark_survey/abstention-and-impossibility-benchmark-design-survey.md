# Direction C Survey: Abstention / Out-of-Scope ("Impossible") Task Evaluation in AI Benchmarks

**Purpose**: Extract reusable design patterns from high-quality benchmarks that evaluate whether a model/agent recognizes tasks beyond its capability and correctly abstains. Target application: Cloudra's four-tier (Easy/Normal/Hard/Impossible) validation test set for autonomous reaction-mechanism discovery, where the Impossible tier uses multireference (MR) systems and the desired behavior is a correct refusal ("cannot compute reliably at current level").

**Survey date**: 2026-08. Author: literature-survey sub-agent (Direction C).
**Local copies**: PDFs in `docs/benchmark_survey/pdfs/`, converted markdown in `docs/benchmark_survey/md/` (abstentionbench, simpleqa, rtuning, duan2020_mr).

---

## 1. Papers covered (deep-read = methods/evaluation sections read in full text)

| # | Paper | Year | Venue | Deep-read | Source |
|---|-------|------|-------|-----------|--------|
| 1 | AbstentionBench: Reasoning LLMs Fail on Unanswerable Questions (Kirichenko, Ibrahim, Chaudhuri, Bell; FAIR at Meta) | 2025 | arXiv 2506.09038 | Yes | https://arxiv.org/abs/2506.09038 |
| 2 | Measuring short-form factuality in large language models (SimpleQA; Wei et al., OpenAI) | 2024 | arXiv 2411.04368 | Yes | https://arxiv.org/abs/2411.04368 |
| 3 | R-Tuning: Instructing Large Language Models to Say "I Don't Know" (Zhang, Diao, Lin et al., HKUST/UIUC) | 2023/2024 | AAAI 2024; arXiv 2311.09677 | Yes | https://arxiv.org/abs/2311.09677 |
| 4 | Semi-Supervised Machine Learning Enables the Robust Detection of Multireference Character at Low Cost (Duan, Liu, Nandy, Kulik) | 2020 | J. Phys. Chem. Lett. 11, 6640 | Yes | DOI 10.1021/acs.jpclett.0c02018; accepted ms. at MIT DSpace handle 1721.1/136080 |
| 5 | Learning from Failure: Predicting Electronic Structure Calculation Outcomes with Machine Learning Models (Duan, Janet, Liu, Nandy, Kulik) | 2019 | J. Chem. Theory Comput. 15, 2331 | Abstract + S2 record | DOI 10.1021/acs.jctc.9b00057; ChemRxiv 10.26434/chemrxiv.7616009 |
| 6 | Exploiting Ligand Additivity for Transferable Machine Learning of Multireference Character across Known TMC Ligands (Duan et al., Kulik) | 2022 | J. Chem. Theory Comput. 18 | Abstract | DOI 10.1021/acs.jctc.2c00468 |
| 7 | Can AI Assistants Know What They Don't Know? (Cheng et al., "Idk" dataset) | 2024 | ICML 2024 | Abstract | https://arxiv.org/abs/2401.13275 |
| 8 | Know What You Don't Know: Unanswerable Questions for SQuAD (Rajpurkar, Jia, Liang) | 2018 | ACL 2018 | Secondary (via #1) | https://arxiv.org/abs/1806.03822 |
| 9 | Large Language Models Must Be Taught to Know What They Don't Know (R-Tuning*NeurIPS variant; Zhang et al.) | 2024 | NeurIPS 2024 | Abstract-level (via search) | https://arxiv.org/abs/2405.16830 |

(Note: papers 3 and 9 share the "R-Tuning" name from the same group; 9 is the uncertainty-aware-instruction-tuning variant published at NeurIPS 2024 with the "Uncertainty-Aware Accuracy" metric.)

---

## 2. Per-paper design takeaways

### 2.1 AbstentionBench (arXiv 2506.09038) — the most complete abstention-benchmark template

**Sample construction ("what counts as truly unanswerable")**:
- Systematic review: shortlisted 82 candidate datasets on abstention/refusal/uncertainty; authors manually reviewed each and kept only datasets where abstention is the *desirable* response for at least some samples → 17 curated datasets + 3 self-created variants = 20 datasets, >35k prompts.
- Six explicitly named scenarios (non-exhaustive, non-mutually-exclusive), which double as a taxonomy of "impossible":
  1. **Answer Unknown** — no documented, agreed-upon answer exists even with more context (e.g. KUQ "unsolved questions", BIG-Bench Known-Unknowns).
  2. **False Premise** — question rests on an incorrect statement (FalseQA).
  3. **Stale** — answer changed after knowledge cutoff (FreshQA).
  4. **Subjective** — answer depends on viewpoint (MoralChoice).
  5. **Underspecified Context** — the *context* lacks a required detail (MediQ: "My dog was prescribed 5 mg/kg — how much?" without the dog's weight).
  6. **Underspecified Intent** — unclear what the user wants.
- **Key trick for reasoning domains**: to build GSM8K-Abstain / GPQA-Abstain / MMLU-Math-Abstain they duplicate original *answerable* questions and delete the context preceding the final question, creating a matched answerable/unanswerable pair differing only in information completeness. This gives a controlled within-domain contrast — the "impossible" sample is constructed by principled removal of required information, not by making things arbitrarily hard.
- **Lesson for "impossible vs merely hard"**: impossibility is defined *declaratively by scenario type* (missing info / no agreed answer / false premise / stale), not by difficulty of retrieval. Unanswerability must be a property of the (question, capability) pair, not of question hardness.

**Scoring**:
- Binary judge: Llama-3.1-8B-Instruct with a custom system prompt answers "yes/no" whether a response is an abstention; judge validated at **88% accuracy on a manually annotated sample** — judge validation against human labels is mandatory.
- Every sample carries a label "should abstain / should not". Metrics: **abstention recall** (fraction of should-abstain samples correctly abstained — the headline metric), **abstention precision** (guards over-abstention), **F1**, plus **response accuracy** on non-abstain samples. Separating recall (impossible caught) from precision (possible not refused) prevents gaming by blanket refusal.
- Correctness of non-abstention answers judged by a second LLM-judge prompt (from Thakur et al.).

**Key empirical findings relevant to Cloudra**:
- Abstention does **not** improve with model scale (Llama 8B≈405B).
- Reasoning fine-tuning **degrades** abstention by ~24% on average (DeepSeek-R1-distill, s1.1 vs their instruct bases) — reasoning models hallucinate missing context and give definitive answers even when their reasoning traces express uncertainty. RLVR (verifiable-reward RL) specifically hurts abstention; SFT/DPO help somewhat.
- Higher accuracy ≠ better abstention; on some datasets they anti-correlate.
- A carefully crafted system prompt boosts abstention in practice but doesn't fix the underlying inability to reason about uncertainty.

### 2.2 SimpleQA (arXiv 2411.04368) — cleanest scoring-function precedent

**Ground-truth construction**:
- 4,326 short fact-seeking questions, **adversarially collected against GPT-4** (a question is kept only if ≥1 of 4 model completions was wrong) — ensures difficulty for frontier models.
- Quality gates: each question created by one annotator, independently answered by a second; kept only if both answers match; required ≥2 unique source domains; ~3% residual error rate measured by a third-annotator audit of 1000 samples — **quantify and report your ground-truth error rate**.
- Criteria: single indisputable answer; answer time-invariant; answer supported by cited evidence; answerable as of 2023.

**Scoring (the part to copy)**:
- Three-way grading per response: **correct / incorrect / not attempted** (hedged-but-contradicting answers count as incorrect; partial answers without contradiction count as not attempted).
- Two base metrics: `overall correct` (recall-like) and `correct given attempted` (precision-like). Single number: **F-score = harmonic mean of the two**.
- Acknowledged loophole: under F-score, if accuracy <50% a model is incentivized to guess whenever ≥50% sure. **Loophole-free alternative: penalized average score — correct = +1, not attempted = 0, incorrect = −p**, with p set by use case (p=9 means a model scores >0 only if ≥90% of attempted answers are correct). This is the clean "abstention reward vs error penalty" knob.

**Calibration measurement**: two methods — (a) stated confidence vs actual accuracy (binning), (b) self-consistency: ask 100× at T=1, frequency of majority answer vs accuracy. Models systematically overstate confidence; larger models better calibrated.

### 2.3 R-Tuning (arXiv 2311.09677) — knowledge-boundary ground truth is *model-specific*

**How "unknown" is defined (most transferable idea)**:
- The boundary between known/unknown is defined **per model, empirically**: run the pre-trained model on training questions once; prediction matches label → certain set D1; mismatch → uncertain set D0. An unsupervised variant (R-Tuning-U) answers each question k=10 times at T=0.7 and labels the top-50% entropy questions as uncertain. → "Unknown" is not an absolute property of the question but of the (question, model) pair — directly analogous to Cloudra's "impossible = beyond *this* pipeline's level of theory".
- Refusal-aware training data: append "I am sure"/"I am unsure" after the gold answer; standard SFT on the answer+uncertainty part only.

**Scoring**:
- Accuracy computed **only on willingly answered questions** (selective accuracy).
- Threshold-free ranking metric: **Average Precision (AP)** — rank all predictions by confidence (weighted combination of answer probability and expressed-certainty probability); AP rewards models that put correct answers above hallucinated ones. AP penalizes a model that reports high confidence on everything.
- Generalization check: refusal trained on one task transfers OOD (HaluEval) → refusal is a "meta-skill". They also test on explicitly unanswerable datasets (SelfAware, FalseQA, NEC).

### 2.4 Duan et al. 2020 (JPCL, DOI 10.1021/acs.jpclett.0c02018) — how chemistry operationalizes "beyond single-reference capability"

**Ground truth for "impossible for SR methods"**:
- Dataset AD-3165: 3,165 small organic molecules in equilibrium + randomly/maximally distorted geometries; 15 MR diagnostics computed from DFT, MP2, CASSCF, CCSD(T) (e.g. **T1, D1, D2 amplitudes; %TAE[(T)]; IND/rND finite-T DFT occupations; MP2 and CASSCF natural-orbital occupations nHOMO/nLUMO; CASSCF leading weight C0²**).
- **Diagnostics disagree strongly** — e.g. most CCSD/CAS diagnostics flag >1/3 of molecules as MR (C0²<0.9) while MP2/DFT diagnostics flag ~1%. No single diagnostic is a gold standard.
- Solution 1 (label construction): **consensus labeling** — label a structure MR/SR only if it is in the top/bottom 10% of **≥8 of 15** diagnostics; use these extreme unambiguous cases as the supervised labels; semi-supervised VAT learns the rest.
- Solution 2 (gold-standard property): define a **property-based MR severity measure** %Ecorr[(T)] = 100×(E[CCSD]−E[HF])/(E[CCSD(T)]−E[HF]) — how much correlation energy the (T) term recovers; chosen for agreement with CCSDT−CCSD differences and weak size-dependence. A good classifier must map low %Ecorr[(T)] → MR with a smooth transition.
- Recommended literature cutoffs used as baseline: D1>0.05, T1>0.02, D2>0.18, %TAE[(T)]>5%, C0²<0.9 (any one exceeded → MR). Cutoffs are qualitatively consistent with VAT but misclassify known MR cases (N2, propyne, distorted conjugated molecules) that fall just below thresholds — **single-cutoff rules are brittle; consensus/property-based criteria are the defensible ground truth**.

**Lesson for Cloudra's Impossible tier**: a molecule is "impossible for the current single-reference pipeline" when (a) multiple independent MR diagnostics agree it is strongly correlated, and/or (b) a property-relevant severity measure (%Ecorr[(T)] analog) is beyond the SR regime. xTB/GFN-level methods cannot produce CCSD diagnostics, so the system must either run a cheap CCSD(T) diagnostic or use a learned/heuristic MR detector — and the benchmark ground truth should be fixed by *consensus diagnostics computed offline at labeling time*, not at eval time.

### 2.5 Supporting chemistry papers (abstract-level)

- **Learning from Failure (JCTC 2019, 10.1021/acs.jctc.9b00057)**: first ML models predicting *whether an electronic-structure calculation will succeed* (geometry optimization outcome, ⟨S²⟩ deviation) from composition alone (SVM/ANN, AUC≥0.95), plus a CNN "dynamic model" reading the SCF/optimization time series to predict failure mid-run; uncertainty estimated via latent-space point distribution → enables "autonomous job control" (kill/flag nonproductive simulations). Direct precedent for a compute agent that predicts "this job will not converge / is out of regime" before or during execution.
- **Ligand Additivity MR (JCTC 2022, 10.1021/acs.jctc.2c00468)**: MR diagnostics computed for >5,000 CSD ligands; MR character correlates linearly with inverse mean bond order and is **additive across ligands** → TMC MR character predictable from ligand-derived features; transfers to unseen ligand chemistry. Precedent for cheap *a priori* MR flags from structure alone.

### 2.6 LLM-side supporting papers (abstract-level)

- **Idk dataset / "Can AI Assistants Know What They Don't Know?" (ICML 2024, arXiv 2401.13275)**: builds a **model-specific** known/unknown split from existing open-domain QA (same model-relative boundary idea as R-Tuning); alignment on this Idk data lets assistants refuse most unknown questions and raises accuracy on attempted ones.
- **SQuAD 2.0 (ACL 2018, arXiv 1806.03822)**: canonical precedent — 50k+ unanswerable questions written adversarially to look answerable; evaluation scores both answerable accuracy and unanswerable detection (F1 on both classes). Established the "answerable/unanswerable pair in the same distribution" pattern.
- **NeurIPS 2024 "LLMs Must Be Taught to Know What They Don't Know" (arXiv 2405.16830)**: uncertainty-aware instruction tuning; proposes **Uncertainty-Aware Accuracy** — a scoring variant that only credits high-confidence correct answers, penalizing confident errors.

---

## 3. Transferable design patterns for Cloudra's Easy/Normal/Hard/Impossible test set

1. **Define "impossible" relative to capability, not absolutely.** Follow R-Tuning/Idk: a task is Impossible iff the *declared capability level* (xTB / single-reference DFT pipeline) is provably inadequate, established by an offline ground-truth procedure (here: MR diagnostic consensus), not by "the pipeline failed at runtime". Runtime failure is a symptom, not the label.
2. **Ground truth for the Impossible tier via multi-diagnostic consensus, not single cutoffs.** Follow Duan 2020: compute T1/D1/D2/%TAE[(T)]/C0²/nHOMO(MP2) etc. offline at CCSD(T)/CASSCF level for candidate molecules; label Impossible only when ≥k of n diagnostics agree (or %Ecorr[(T)]-analog below threshold). Single T1>0.02-style cutoffs misclassify borderline MR cases (N2, propyne precedents).
3. **Match each Impossible sample with a feasible sibling.** Follow GSM8K-Abstain/GPQA-Abstain pair construction: same reaction family, one variant SR-safe (Easy/Normal/Hard) and one MR-flagged (Impossible) → controls for domain difficulty and tests that refusals are *caused by the MR property*, not by generic hardness. Also guarantees the Impossible tier isn't learnable by superficial cues.
4. **Keep the answerable tiers explicitly feasible.** AbstentionBench keeps answerable samples in every dataset so over-refusal is measurable; SimpleQA requires every kept question to have a verified answer. Analog: verify Easy/Normal/Hard by actually completing them with xTB before freezing the set, and report residual ground-truth error rate (SimpleQA reports ~3%).
5. **Three-way outcome grading**: success / wrong-answer / abstained — not binary pass/fail. Grade "abstained" by an explicit, parseable refusal signal from the DAG (preferably a typed system state, not an LLM judge; if a judge is used, validate it on human-annotated samples and report agreement, cf. AbstentionBench's 88%).
6. **Score with recall/precision separation + penalized aggregate**:
   - Abstention recall on Impossible (catch rate), abstention precision / false-refusal rate on Easy–Hard (over-caution), and task accuracy on Easy–Hard.
   - Single number: SimpleQA-style penalized score: correct=+1, abstain=0 on feasible tasks; on Impossible tasks correct-refusal=+1, attempted-but-wrong=−p (p≈4–9), silence-without-flag lower than explicit refusal. Explicitly document the incentive structure implied by p (SimpleQA App. B precedent).
   - Optionally add AP/ranking over the agent's self-reported confidence (R-Tuning precedent) as a threshold-free secondary metric.
7. **Anti-gaming analysis**: report the blanket-refusal baseline (abstain on everything ⇒ perfect Impossible recall, zero feasible accuracy) and the never-refuse baseline; the penalized score must make both suboptimal. Report calibration (stated confidence vs success, or repeat-run self-consistency, SimpleQA §4).
8. **Where the refusal signal comes from matters**: precedents are (a) *a priori* composition-based predictors (Learning from Failure static model; ligand-additivity MR features), (b) *mid-run* monitors (dynamic CNN on SCF time series — analogous to watching xTB/SCF convergence, ⟨S²⟩, or DFT-level T1/D1 from a cheap single point), (c) *post-hoc* property checks. A strong Cloudra design uses (b): detect MR character from a cheap diagnostic before committing to TS search, and the benchmark should reward *early* correct refusal (less compute wasted) — cost-aware scoring is a defensible novelty.
9. **Expect reasoning to hurt abstention** (AbstentionBench headline): reasoning-fine-tuned LLMs hallucinate missing context and answer definitively. In Cloudra's DAG ablations, the DAG/KG grounding should be *evaluated as an abstention enabler*, not only as an accuracy enabler — i.e. include "Impossible-tier recall" as a primary ablation endpoint for DAG modes and graph/no-graph, which directly ties the abstention benchmark to the claimed novelty.
10. **Report per-scenario breakdowns**, not one aggregate: AbstentionBench's six scenarios show models can be near-perfect on "answer unknown" and near-zero on "underspecified context". For Cloudra, split Impossible by MR subtype (bond-breaking TS with strong correlation, open-shell singlet/ biradical, TM-containing, stretched-bond geometries along IRC) — refusals may be good for one subtype and absent for another.
11. **Statistical rigor**: freeze the labeled set; report n per tier and per scenario; use judge-vs-human agreement or deterministic checks; give run-to-run variance (SimpleQA: 4,326 items chosen partly for low variance); for agent systems report compute-cost-normalized metrics since refusal saves GPU-hours.
12. **Difficulty tiers must be difficulty-*verified*, not difficulty-*assumed***: SimpleQA adversarially verifies hardness (kept only if a frontier model errs); AbstentionBench verifies unanswerability by scenario definition + curation. For Cloudra: Easy/Normal/Hard tiers should be tiered by a measurable criterion (e.g. # of elementary steps, conformer count, TS-search effort, xTB success rate across seeds), with the criterion reported, and Hard must be confirmed *solvable* with xTB (not just believed solvable).

---

## 4. Open gaps / caveats

- No published benchmark was found that directly evaluates a *computational-chemistry agent's* refusal on MR grounds; Cloudra's Impossible tier appears genuinely novel in this niche. Closest: ChemBench (arXiv 2404.01475) has no abstention scoring; ScienceAgentBench (arXiv 2410.05080) scores task success only.
- Kulik-group papers give MR *detection* machinery but not agent *refusal scoring*; the scoring side must be borrowed from the LLM abstention literature (Sections 2.1–2.3).
- ChemRxiv preprints for papers 4–6 were 403-blocked; paper 4 was read via the MIT DSpace accepted manuscript; papers 5–6 covered at abstract level (flagged in Section 2.5).
- The classic diagnostic references behind the cutoffs: Lee & Taylor, Int. J. Quantum Chem. Symp. 23, 199 (1989) (T1); Janssen & Nielsen, Chem. Phys. Lett. 290, 423 (1998) (D1); Karton et al. %TAE[(T)] (W1/W2 theory lineage, JCP 2006–2008); Tishchenko, Zheng, Truhlar, JCTC 4, 1208 (2008) (M diagnostic). Cited here from the Duan 2020 paper's usage; primary texts not re-verified in this survey.

---

## 5. Full citations

1. Kirichenko, P.; Ibrahim, M.; Chaudhuri, K.; Bell, S. J. *AbstentionBench: Reasoning LLMs Fail on Unanswerable Questions.* arXiv:2506.09038 (2025). https://arxiv.org/abs/2506.09038 ; code: github.com/facebookresearch/AbstentionBench
2. Wei, J.; Karina, N.; Chung, H. W.; Jiao, Y. J.; Papay, S.; Glaese, A.; Schulman, J.; Fedus, W. *Measuring short-form factuality in large language models (SimpleQA).* arXiv:2411.04368 (2024). https://arxiv.org/abs/2411.04368
3. Zhang, H.; Diao, S.; Lin, Y.; Fung, Y. R.; Lian, Q.; Wang, X.; Chen, Y.; Ji, H.; Zhang, T. *R-Tuning: Instructing Large Language Models to Say "I Don't Know".* arXiv:2311.09677; AAAI 2024. https://arxiv.org/abs/2311.09677
4. Duan, C.; Liu, F.; Nandy, A.; Kulik, H. J. *Semi-Supervised Machine Learning Enables the Robust Detection of Multireference Character at Low Cost.* J. Phys. Chem. Lett. 11, 6640–6648 (2020). DOI 10.1021/acs.jpclett.0c02018 ; DSpace: https://dspace.mit.edu/handle/1721.1/136080
5. Duan, C.; Janet, J. P.; Liu, F.; Nandy, A.; Kulik, H. J. *Learning from Failure: Predicting Electronic Structure Calculation Outcomes with Machine Learning Models.* J. Chem. Theory Comput. 15, 2331–2345 (2019). DOI 10.1021/acs.jctc.9b00057
6. Duan, C.; Ladera, A.; Liu, J. C.-L.; Taylor, M. G.; Ariyarathna, I. R.; Kulik, H. J. *Exploiting Ligand Additivity for Transferable Machine Learning of Multireference Character across Known Transition Metal Complex Ligands.* J. Chem. Theory Comput. 18 (2022). DOI 10.1021/acs.jctc.2c00468
7. Cheng, Q.; Sun, T.; Zhang, W.; Wang, S.; Liu, X.; Zhang, M.; He, J.; Huang, M.; Yin, Z.; Chen, K.; Qiu, X. *Can AI Assistants Know What They Don't Know?* ICML 2024. arXiv:2401.13275. https://arxiv.org/abs/2401.13275
8. Rajpurkar, P.; Jia, R.; Liang, P. *Know What You Don't Know: Unanswerable Questions for SQuAD.* ACL 2018. arXiv:1806.03822. https://arxiv.org/abs/1806.03822
9. Zhang, H.; Diao, S.; Lin, Y.; Fung, Y. R.; Lian, Q.; Wang, X.; Chen, Y.; Ji, H.; Zhang, T. *Large Language Models Must Be Taught to Know What They Don't Know.* NeurIPS 2024. arXiv:2405.16830. https://arxiv.org/abs/2405.16830
