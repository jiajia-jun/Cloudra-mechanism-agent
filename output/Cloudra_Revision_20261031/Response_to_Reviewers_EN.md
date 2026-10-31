# Response to reviewers

We have revised the manuscript and Supplementary Information (SI) to clarify the experimental model and settings, distinguish the causes of the inspected Easy-task outcomes, and examine the sensitivity of Impossible-task scores to target-object assignment. The title is now **“Cloudra: Geometric Reasoning and Scientific Validation for Autonomous Reaction Mechanism Exploration.”** Scientific validation is the objective; geometries, calculation logs, and their recorded associations provide the basis for the physical acceptance checks.

The published 200-run score table is unchanged. The two Impossible-task assignment corrections below are explicitly conditional sensitivity scenarios. We have not introduced new scientific thresholds, changed the scoring weights, or represented the scenarios as additional experiments. Locations below refer to section titles and LaTeX labels so that they remain usable during final typesetting.

## Major comment 1: Identify the backbone and call configuration used in P2

**Concern.** The full-benchmark experiment needs an explicit model identity and reproducible call settings, separate from the repeated-task study and the local diagnostic model.

**Response.** We have expanded the experimental-design description and SI model metadata. The authors have confirmed that the P2 backbone was **DeepSeek-v4.1-flash (1017)**. We distinguish this deployment version from the API alias preserved in the run records: all four P2 configurations called `deepseek-v4-flash` through `https://api.deepseek.com`. Both coordinator and follower slots have that alias in all eight frozen configuration snapshots, covering the four configurations in P2b and P2c. Request-start and completion records in all eight runtime archives independently confirm the same call alias.

The recovered configuration requested `reasoning_effort=minimal`; the run-start records specify temperature 1.0. The configured context window was 400,000 tokens, and the archived spawned-agent setting was `max_tokens=32768`. We describe these as harness/request settings, not as measured context capacity or consumed token totals. The campaign-era routing implementation, together with `native_search=auto`, identifies the streaming OpenAI-compatible chat-completions route and the JavaScript tool-invocation protocol. The deployment designation DeepSeek-v4.1-flash (1017) comes from the authors' confirmation; the archive independently verifies the API alias and recorded call settings. We state these sources separately, without presenting the full deployment designation as a field recovered from telemetry.

We have also separated the experiment versions from the implementation and evaluator versions. P2b and P2c used campaign base `53309d0e`, with configuration commits Guided `6e89d20c`, Record `746c33f0`, Standard `c7fc94a1`, and Brief-errors `3b9831bb`. Both campaigns used two concurrent task runs per configuration. The final P2 sample contains three retained P2b runs and 197 P2c runs. Cancelled P2b attempts in the raw archive are not counted as extra benchmark observations. The previously cited implementation revision and later evaluator fixes retain their own descriptions.

The local Qwen3.8:27b diagnostics are now identified separately from this API-based workflow comparison. Standard is the actual comparison branch using the same DeepSeek-v4.1-flash (1017) backbone throughout the primary comparison; Record and Brief-errors are workflow ablations.

**Location.** Main Methods, “Repeated-task study, primary comparison, and workflow ablations” (Section 2.6.4); SI “Benchmark design and experimental protocol” (`sec:si-protocol`), “Layered scoring and scientific completion” (`sec:si-scoring`), and “P2 model configuration and campaign versions” (`sec:si-p2-model-metadata`; `tab:si-p2-model-metadata`). The companion `p2_model_metadata.json` supplies configuration and telemetry sources.

## Major comment 2: Separate repeat-run variation from task variation, and explain the Easy-task outcomes

**Concern.** P2 has one retained run per task and configuration. The bootstrap intervals therefore need an appropriate interpretation, and the lower Guided Easy mean needs a case-based account rather than a general explanation based on stricter checks or integrity failures.

**Response.** We now state the study units explicitly. P2 contains one retained run for each of 50 tasks under each of four configurations. Its paired task-cluster bootstrap resamples tasks while keeping their configuration results together. These intervals describe variation in the task mix; they do not estimate independent repeat-run variability for each P2 task. P1b separately contains three runs for each of four tasks under each configuration, giving 48 runs. The Discussion distinguishes these sources of variation and the role of further repeated evaluation.

The released Easy means are Guided 0.880940, Standard 0.730485, Record 0.944335, and Brief-errors 0.905370. We have retained those results and added an inspection of F4, G2, D1, D3, and L2 using original graphs, native logs, evaluation notes, and runtime records. The cases identify different mechanisms:

- **F4: historical reference identity.** Guided delivered a 16.02-kcal/mol hydride-transfer barrier from the borane/formaldehyde Lewis adduct. The native energies give 16.01572 kcal/mol, and the retained saddle, frequency, bidirectional IRC, and endpoint optimization/frequency records support that pathway. The campaign reference nevertheless encoded its reactant as separated `[BH3].C=O`, although its step description and 16.02 reference concerned the bonded adduct. The original evaluation note explicitly reports that no delivered step matched the reference endpoint species. A later task correction, `0b7b5e5b`, changed the reference node to `[BH3-][O+]=C`; the released offline evaluation retained the earlier campaign taskbank. We therefore identify a reference-object mismatch, rather than attributing this zero Accuracy to rejection of a valid frequency or IRC. The published component profile is Graph 0.6009, SC_all 1, Accuracy 0, Composite 0.3601. It retains the SC contribution and is not an Accuracy integrity-short-circuit result, which would leave only the Graph-weighted contribution of approximately 0.0601.

- **G2: loss of computed quantities during final delivery.** Guided's native logs support a double-H-transfer barrier of approximately 0.845 kcal/mol, close to the 0.87 reference. Runtime records show four rejections of numerical declarations on a companion complex-product edge, an attempted restoration, and a subsequent saddle-artifact rejection. The following recorded graph edits removed numerical barriers and saddle energy/log bindings. Descriptive text still contained the result, but the final structured graph lacked the numerical declaration required for Accuracy. Brief retained the approximately 0.844 result and received near-unit Accuracy. Standard and Record used a lower-energy reactant reference and declared approximately 3.4. This trajectory identifies an interaction between scientific-check status and exported numerical claims. It does not show that the native calculation failed to find the low-barrier pathway. Guided's released Graph 0.8889, SC 0.5, Accuracy 0, and Composite 0.2389 likewise retain the graded SC contribution.

- **D1: reactant-conformer reference.** Guided and Standard obtained nearly identical saddle energies. Their reactant energies differ by 3.11859 kcal/mol, with butadiene dihedrals of approximately 26.33° and -179.93°, corresponding to reactive s-cis and lower s-trans references. Guided's 15.738 versus the 18.830 reference produces an underlying Gaussian score of 0.5880; the specified maximum numerical-deviation penalty gives final Accuracy 0.7.

- **D3: saddle-energy difference.** Guided and Standard barriers are 18.14687 and 14.55472 kcal/mol. Their reactant energies differ by only 0.09899 kcal/mol, whereas the saddle energies differ by 3.69113 kcal/mol. Both saddle logs contain one imaginary frequency. The numerical comparison produces the capped Accuracy 0.7, while separate product-endpoint association warnings account for the SC 0.75 component. We do not merge those two effects into a single failure explanation.

- **L2: reference choice and comparison-edge selection.** Guided used the reactive cZc minimum and obtained 18.98740 kcal/mol; Record and Brief used the lower tZt reference, giving approximately 28.275. The conformer energy difference is 9.28761 kcal/mol. Standard actually delivered both barriers, 18.99 on `e1` and 28.28 on `e2`. The reference's unspecified stereochemistry gives the candidates equal endpoint costs, and the edge-identifier tie-break selects `e1`. The released Accuracy 0.7 therefore concerns the selected local-reference value. We have corrected the account so that it does not imply that Standard never computed the stable-reference barrier.

These observations separate the calculation performed, its reference state, its final structured declaration, and the object selected by evaluation. The revised Discussion uses them to identify where those relations need to persist across the workflow. We have not assigned a single cause to all lower Easy scores or selectively increased the released scores.

**Location.** Main Results, Easy-task interpretation within “End-to-end benchmark evaluation”; Main Discussion, “Workflow guidance, scientific judgment, and outlook”; SI “Easy-tier energy references and delivery trajectories” (`sec:si-easy-case-audit`; `tab:si-easy-case-audit`) and “Paired statistical analysis and time measurements” within `sec:si-protocol`.

## Major comment 3: Test the Impossible ranking against target-object calibration

**Concern.** Record/IA5 and Brief/IC3 contain negative target claims that may have been matched to positive alternatives. Would target-aware assignment change the Impossible-tier ranking?

**Response.** We inspected both original final graphs and their final process statements from the FULL archive. Record/IA5 marks the requested disrotatory edge and its TS inaccessible and declares no disrotatory barrier. Its separate positive conrotatory edge carries 33.57 kcal/mol. Brief/IC3 explicitly distinguishes the characterized closed-shell singlet from the requested lowest open-shell singlet, marks the latter and its state-change edge inaccessible, and withholds the numerical singlet-triplet gap. It also states that the closed-shell branch's relative energies are not that gap.

In both cases the current matcher selects the positive alternative because the candidates share endpoint connectivity and bond-change signatures. The intended negative edge passes the existing negative-claim predicate when assigned to the requested target. Target-aware calibration must distinguish pathway or electronic-state identity before evaluating the claim. We do not propose a rule that simply prefers a negative edge, because that could hide a contradictory positive claim about the same target.

The sensitivity uses the published baseline, where both questioned cases have Graph 1, SC 1, Accuracy 0, and Composite 0.4. Brief/IC3's raw diagnostic -1 is an earlier evidence-reference failure; it is not the baseline for this calculation. The documented reference-formatting repair changes no scientific state, edge, energy, or claim.

We hold Graph and SC fixed for the two cases and retain the other 198 runs and their components. Conditional Accuracy 0-to-1 target credit adds 0.6 to the corresponding case composite and 0.06000 to its ten-task Impossible mean:

| Scenario | Guided | Standard | Record | Brief |
|---|---:|---:|---:|---:|
| Original published values | 0.44506 | 0.24733 | 0.23250 | 0.48294 |
| Record/IA5 target credit | 0.44506 | 0.24733 | 0.29250 | 0.48294 |
| Brief/IC3 target credit | 0.44506 | 0.24733 | 0.23250 | 0.54294 |
| Both target credits | 0.44506 | 0.24733 | 0.29250 | 0.54294 |

The ordering Brief > Guided > Record is stable in these two-case scenarios. Record moves above Standard when its IA5 target receives credit. The Guided-Standard comparison is unchanged because none of their scores changes. These results are reported as conditional arithmetic, not an adopted score revision or a complete rerun of scientific validation.

**Location.** SI “Sensitivity to target-object assignment in Impossible tasks” (`sec:matcher-sensitivity`; `tab:matcher-sensitivity`), accompanying the Impossible-tier analysis; Main Discussion's target-identity paragraph. `matcher_sensitivity_scenarios.csv` supplies all four scenarios, means, and ranks.

## Major comment 4: Clarify conformer references, conformational sampling, and the energy quantity being evaluated

**Concern.** The manuscript should distinguish the lowest reference found from a global-minimum claim, explain the role of CREST, and separate electronic barriers from thermochemical and solvent-dependent activation free energies.

**Response.** We have clarified that a bond-changing step uses the lowest-energy verified minimum found for the corresponding reactant or intermediate state, including its connected conformers. The actual IRC endpoint is retained separately. A conformational-transition barrier uses its own initial conformer, and separate stereochemical substrates or channel-specific contact complexes retain their own references. We do not equate the default candidate-generation budget with exhaustive global-minimum identification.

The default preorganization procedure uses topology-aware rigid placements, guided MMFF94 relaxation, and energy/RMSD selection, with 32 relative orientations and up to eight guided placements. The separate conformer-search interface defaults to RDKit and also exposes an external CREST backend. CREST can be requested for additional conformer or noncovalent-complex sampling; its default route uses GFN2-xTB with the quick setting. A returned ensemble supplies candidate geometries for subsequent quantum-chemical optimization and physical checks. We have not stated that every benchmark run used CREST or that all conformers were exhausted.

The benchmark barrier is the electronic energy difference ΔE‡, without ZPE or thermal corrections. The manuscript retains that definition and separates it from enthalpy and Gibbs free-energy calculations. The Discussion now addresses what finite conformational sampling, entropy, ZPE, and solvent treatment mean for extending the benchmark conclusions to experimental activation free energies. NI5 and NU5 retain their stated aqueous/weakly acidic and dichloromethane reaction conditions in the task catalogue; the Discussion distinguishes those task conditions from the actual molecular models and allowed computational methods. No unperformed free-energy, solvation, or exhaustive-search calculation has been added to the Results.

**Location.** Main Methods, “Branch Crowding and Reactant Preorganization,” “Evidence Aggregation and Energies,” and “Reference answers and evaluation protocol”; SI “Allowed calculations and reference definitions” and “Conformational sampling”; Main Discussion, “Workflow guidance, scientific judgment, and outlook.”

## Minor comments

### 1. Explain the mapping coefficients, ambiguity window, and crowding settings

We now identify these values as fixed implementation heuristics, held constant across the workflow configurations. The atom-map ranking uses coefficients 2 for each formed or broken bond, 1 for bond-order changes, 4 for hydrogen-count mismatches, 8 for charge or radical-electron mismatches, and 2 for stereochemical mismatches. The J_min + 2 window reports near-optimal maps as ambiguous. The branch descriptor uses decay ρ = 0.5 through depth five and the cumulative B_s ≥ 9.0 congestion flag. These values rank or annotate candidate structures; they are not fitted energy barriers or independent physical acceptance criteria. We have not presented them as empirically optimized constants or introduced a new threshold-selection experiment.

**Location.** Main Methods, “Atom Correspondence and Reaction Centers,” “Branch Crowding and Reactant Preorganization,” and “Implementation Defaults”; SI “Fixed geometric heuristics” within `sec:si-p2-model-metadata`.

### 2. State the imaginary-mode diagnostic default and its role

The diagnostic comparison ratio is 0.5. The quantity compares relative-displacement norms on monitored atom pairs with the global maximum; it is a reaction-center participation/alignment diagnostic. We have removed the implication that an unspecified η threshold is a separate hard acceptance gate. The alignment flag is advisory. First-order-saddle character and the required same-TS bidirectional IRC and endpoint optimization/frequency records determine scientific acceptance. Missing or geometrically undecidable mode information remains identified in the diagnostic report.

**Location.** Main Methods, “Curvature and Reaction Mode Diagnostics” and “Diagnostics and Recovery”; SI “Fixed geometric heuristics.”

### 3. Define P1b/P2 and reconcile Standard with the figure label Backbone

P1b is defined as the four-task, four-configuration repeated-task study with three runs per combination, giving 48 runs. P2 is the four-configuration, 50-task study with 200 retained runs. P2b and P2c are the execution campaigns supplying that P2 sample, not additional experimental tiers. We also state that Backbone in the figures denotes Standard, the same-model comparison branch. The primary comparison is Guided versus that actual Standard branch; Record and Brief-errors are ablations.

**Location.** First study-design definitions in Main Methods; SI “Task specification and study units” and “Workflow configurations and primary comparison”; benchmark figure captions where the Backbone label is used.

### 4. Connect the static activation intervention to the dynamic workflow without overextending it

We have revised the transition after “Internal transfer of measured facts affects selection” (Section 3.2.4). The Qwen intervention tests how a supplied numerical fact affects a controlled local judgment. It does not establish the reliability of an entire research trajectory. The connection to Cloudra is the need to bind measured quantities to the intended molecule, atoms, and operational objective when subsequent calculations and decisions change the research state. A number appearing in free text does not preserve those associations by itself. The transition now states that design implication while retaining the reported probabilities, layer positions, controls, and option-order asymmetry.

**Location.** Main Results, “Internal transfer of measured facts affects selection”; the transition to “From local computational results to evidence-supported scientific delivery”; SI “Single-token transfer of a reported numerical fact” within `sec:si-behavioral`.

### 5. Check the author text, mathematical delimiters, SI notation, temperatures, and structural labels

We separated source errors from PDF extraction/OCR artifacts during this check:

- **Author token `YangList`.** The reported concatenated token is not the author name in the LaTeX/BibTeX source. We verified and retained the correct author names and source separators; no author has been renamed to match an extraction artifact.
- **Kabsch expression, Equation 2.7 (`eq:methods-07`).** The diagonal term has been retypeset with explicit paired delimiters around `(1, 1, det(UV^T))`. The rotation and determinant correction are unchanged.
- **Apparent SI `S->$` sequence.** The underlying SI source notation is correct. The source check does not support treating the extracted character sequence as a different scientific symbol or formula.
- **Temperatures.** We have genuinely retypeset the approximate positive temperatures and range, including P3 near 200 °C, X1 near 350 °C, NQ1 near 200 °C, HA1 around 150-200 °C, and HH1 near 50 °C. Approximation, range, and degree notation are now explicit so that they cannot be read as negative temperatures. These are the stated task conditions; their scientific values were not changed.
- **Structural strings in the chemical-identity figure.** The source is `CC1CC=C1` and C₅H₈, not the OCR strings `CC1CC-C1` and `C5HB`. We verified and retained the correct chemical source labels. The relevant figure is identified by `fig:06`, “Molecular-identity judgments under changes in molecular representation and option order,” whose displayed number is generated by LaTeX.

**Location.** Author/source lists; Main Methods `eq:methods-07`; SI task-catalogue tables; chemical-identity figure `fig:06` and the corresponding SI identity diagnostic.

## Title and prose revision

We have changed the title to emphasize **scientific validation**, following the latest editorial direction. The Introduction now presents the calculation records and their associations as the basis for physical acceptance checks, rather than as a second ultimate objective beside geometric reasoning.

We also edited Introduction Sections 1.1-1.3 and Results Sections 3.3.2-3.3.3 using the repository's humanizer workflow. The revision removes promotional descriptions, the hypothetical unconstrained opponent, and unsupported descriptions of internal model states. The HA1 retries, NB1 parameter changes, IA1 missing short_IRC requirement and empty waiver list, rejected completion request, subsequent partial submission, and the 12 local judgments remain. The text describes what those records show without claiming that a single case proves reliability for all agents. The numerical results, citations, figures, and scientific acceptance standards are retained. The Methods and Section 3.1 keep their scientific content, with the specific reporting clarifications addressed above.

**Location.** Manuscript and SI titles; Introduction; “Diagnostics turn evidence gaps into concrete research actions”; “Outstanding requirements must remain part of completion decisions.”
