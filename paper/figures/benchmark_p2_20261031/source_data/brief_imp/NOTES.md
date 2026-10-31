# IMP findings for the manuscript

The brief-errors arm's higher IMP mean is a concentrated change in final target judgments, not uniformly better evidence organization. All figures below use the package's official convention: `repaired_final` when present, otherwise `fair_final`. Original scores and both repairs remain explicit in the CSV.

## Findings to foreground

- Brief-errors: **0.48294**; guided: **0.44506**; official standard/backbone: **0.24733**; record: **0.23250**.
- Brief minus guided is **+0.03788**, while guided wins **5** tasks, brief wins **3**, and **2** tie. The existing paired task bootstrap interval, reused without resampling, is **[−0.18822, +0.28397]** for brief minus guided. This is not evidence that brief is generally superior.
- Weighted mean component differences are **Accuracy +0.06000**, **Graph −0.006607**, and **SC −0.015500**. Their sum is +0.037893; the approximately 0.000013 difference from +0.037880 is rounding in the saved final scores.
- The accuracy difference is concentrated in **IA1** and **IA9** (brief accuracy=1, guided=0), opposed by **IG8** (guided=1, brief=0). Both score accuracy=0.7 on IB9. On the remaining **7 tasks with equal accuracy**, guided wins 4, brief wins 1, and 2 tie; brief minus guided averages **−0.05000**.
- Brief's two large score gains are IA1 **+0.8283** and IA9 **+0.5666**. Guided's IG8 gain is **+0.6661**. Brief's remaining positive difference is IF3 **+0.0333**, solely a Graph difference. The other differences favor guided or tie.
- The hindsight maximum of guided and brief is **0.58788**, identical here to the four-arm hindsight maximum. This demonstrates crossed outcomes only; it is not an implemented selection policy, deployable performance estimate, or additional experiment.

## Ten-task comparison

Triples are official **Graph / SC / Accuracy**; the number after the semicolon is composite. An asterisk denotes an audit repair. Actual chart data retain the individual precision in `imp_40_matrix.csv`.

| Task | guided | standard/backbone | record | brief-errors |
|---|---|---|---|---|
| IA1 | .667/.350/.000; .1717 | .667/.350/.000; .1717 | .667/.350/.000; .1717 | 1/1/1; 1.0000 |
| IA5 | 1/1/0; .4000 | .667/.250/0; .1417 | 1/1/0; .4000 | .667/1/0; .3667 |
| IA7 | .333/.750/0; .2583 | .333/.350/0; .1383 | .333/.750/0; .2583 | .333/.750/0; .2583 |
| IA9 | .667/1/0; .3667 | .333/.750/0; .2583* | .667/1/0; .3667 | .333/1/1; .9333 |
| IB9 | 1/1/.700; .8200 | .750/.350/0; .1800 | .200/.750/.500; .5450 | 1/.833/.700; .7700 |
| IC3 | 1/1/0; .4000 | .333/.500/0; .1833 | .667/.500/0; .2167 | 1/1/0; .4000* |
| ID2 | .339/1/0; .3339 | 0/0/0; .0000 | 0/0/0; .0000 | .339/.500/0; .1839 |
| IE2 | .333/1/0; .3333 | .333/0/0; .0333 | .333/0/0; .0333 | .333/.500/0; .1833 |
| IF3 | .667/1/0; .3667 | .667/1/0; .3667 | .333/1/0; .3333 | 1/1/0; .4000 |
| IG8 | 1/1/1; 1.0000 | 1/1/1; 1.0000 | 0/0/0; .0000 | .339/1/0; .3339 |

The standard IA9 triple is explicitly documented by `reconstructions/standard/IA9/provenance.md`, section 8; it replaces the no-graph component row only in the official plotting columns. The brief IC3 triple includes the hand-corrected evidence references. Its .4 is already folded into the supplied `fair_final` column, despite the repair document saying repaired track only. Neither correction is hidden in this analysis.

## What the archived claims actually establish

**IA1:** Brief's accepted negative target is a score-level observation; its final refusal narrative is absent locally. By contrast, the standard archive contains a concrete overcommitment example: its own report identifies an electronically degenerate square structure, considers withholding the barrier, and nevertheless declares 22.5 kcal/mol. The record catalog declares 23.10. This supports the distinction between obtaining a stationary point and deciding whether that point supports the requested claim. It does not establish how brief reached its decision.

**IA5:** Record correctly marks the requested disrotatory edge inaccessible and treats the allowed conrotatory path separately (33.57 kcal/mol). The archive says the duplicate-endpoint matcher selected the positive edge, leaving accuracy=0. Guided's matching 1/1/0 does not establish an identical final claim: its final graph is not in this package. Brief's final claim is also absent. Do not recode these unknowns from their numbers.

**IA7:** The record and standard catalogs declare accessible barriers 31.19 and 31.20 kcal/mol. Guided/brief share their component profile with record but have no final claim text locally. This is a score agreement, not independently verified agreement of reasoning.

**IA9:** Brief's negative target is accepted by the accuracy rubric despite Graph=.333, while guided has accuracy=0 and SC=1. Standard's reconstructed graph faithfully retains its original positive 46.73-kcal/mol claim; its report called the PM7 saddle trustworthy even while admitting that the target biradical cannot be represented through the permitted route. The product-complex minimum was not verified. This gives a concrete positive-claim overreach example but no trace of brief's decision chronology.

**IB9:** Guided/brief both have partial accuracy=.7, record=.5, standard=0. Record explicitly rejects its second target edge but has a numerical first-edge error (21.20 vs Gold 5.65). This is a mixed positive/negative task; .7 must not be counted as one complete correct refusal. Final guided/brief edgewise claim details are absent.

**IC3:** The preserved brief graph is stronger evidence than its accuracy=0 label. It explicitly marks the requested lowest open-shell singlet **1A2** and the corresponding transition edge inaccessible. It refuses a numerical singlet–triplet gap. It separately keeps a closed-shell **1A1** branch, labels it as not the lowest singlet, and records PM7 +45.9 and GFN2-xTB −1.7 kcal/mol as method-dependent exploratory state energies, explicitly not the target gap. The graph records that a restricted `guess=mix` run cannot test the missing unrestricted state. The audit says only evidence reference formatting changed, so this distinction was already present in the run's scientific claims. The provenance commentary calls its zero accuracy a positive claim on an inaccessible edge, which does not capture this state distinction. Treat this as a documented ambiguity between scientific content and assigned edge identity, not a newly proven matcher bug or grounds to change the score.

**ID2/IE2:** Guided's gains over brief are entirely SC (.3339 vs .1839 and .3333 vs .1833). Neither gains accuracy. Final guided/brief target statements are absent. Record/standard's catalogs contain positive property/path claims on the negative targets.

**IF3:** Brief gains .0333 over guided through Graph alone; both have SC=1 and accuracy=0. The available standard/record claims are positive or mixed spin-state claims. Brief/guided final state distinctions are absent, so do not assume the same scientific error.

**IG8:** Guided and standard obtain accuracy=1; brief=0. Standard's archived graph explicitly refuses the Cr2 states and both dissociation edges. Its prior raw −1 arose from ignored nested inaccessible flags and binding. Guided's detailed negative statement and brief's claimed property are absent locally. The fact that this reverses IA1/IA9 is direct evidence against a universally helpful effect of abbreviated diagnostics.

## Discussion interpretation

The scientific issue is the boundary between **repairing a calculation** and **reconsidering whether the calculation can answer the question**. The detailed-guidance arm is stronger on graph/evidence organization in the paired IMP data, yet that alone does not decide when to withhold a method-limited conclusion. IA1/IA9 show that an agent can recognize a limitation in prose and still promote an internally organized calculation into a positive final claim. Brief/IC3 shows the converse scientific behavior: retain the characterized branch, explicitly separate it from the target electronic state, and refuse the requested number. This is a concrete research-policy distinction worth discussing.

A possible mechanism is that diagnostic detail affects the next research action: a long repair explanation can concentrate attention on completing the current local proof, whereas short feedback may allow a broader reconsideration of the method or target. The reverse cost is also plausible: abbreviated feedback can remove actionable information needed to complete a valid proof. The crossed IA1/IA9/IG8 outcomes fit a task-dependent tradeoff. The final local package does not include brief/guided IMP dialogue or complete final graphs, so it cannot establish feedback-driven causality, refusal timing, or LLM internal attention. Keep that mechanism as a Discussion hypothesis, not a Results finding.

## Figure recommendations

1. **IMP evidence/claim matrix:** rows=10 tasks; four arms in consistent order; three aligned heatmaps for Graph, SC, Accuracy (all fixed 0–1 scale). Mark standard/IA9 and brief/IC3 with stars. Group the A=1 cells visually without renaming them scientific passes. Add explicit IC3 and IA5 footnote markers to accuracy-zero cells.
2. **Paired IMP difference:** horizontal bars for brief−guided composite by task, with IA1/IA9/IG8 labeled; three colored stacked signed component contributions show why the means cross. Put the 3/5/2 win count and reused CI in the caption, not a single “brief wins” banner.
3. **SC versus target correctness:** 40-point or count plot of exact SC against accuracy, highlighting the **14/40** rows with SC=1 and accuracy=0. The point is separation of evidential organization and target-claim acceptance, not that all 14 are chemically false. In negative tasks SC=1 may also follow the rule for inaccessible edges and need not mean a complete positive TS/IRC chain.

Do not map scalar SC values directly to completed calculation stages. Scores average multiple edges and include negative-edge treatment; the same .75 or 1.0 can have different physical provenance. The exact level distribution is provided without invented stage labels.

## Files

- `analyze_brief_imp.py`: read-only reproduction, no external packages.
- `imp_40_matrix.csv`: 40 runs; official/raw/fair scores, all components, repairs, exact source lines, archived claim summaries and raw truncated notes.
- `imp_components_long.csv`: 160 rows for three component heatmaps plus final-score heatmap.
- `imp_brief_minus_guided.csv`: 10 paired signed component decompositions.
- `imp_arm_summary.csv`: four-arm mean/component/disposition counts.
- `imp_selfc_score_distribution.csv`: exact score-level frequencies (no stage inference).
- `imp_summary.json`: exact findings and reused CI.
- `source_sha256.json`: hashes of the six input artifacts used.
- `manuscript_en.md`, `manuscript_zh.md`: ready-to-integrate Results and Discussion paragraphs.

Reproduce: `python analyze_brief_imp.py` (use `--help` for source/repo/output overrides). The script reuses `/private/tmp/cloudra_mining/paired/tier_pairwise.csv` by default; supply `--paired` for a copied evidence directory.
