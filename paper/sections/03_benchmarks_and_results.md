## 3. Benchmark Protocol and Current Evidence

### 3.1 Delivery as the unit of evaluation

Evaluation consumes the delivered mechanism graph and bound computational artifacts, independently of the conversation. A task specifies the chemical problem, allowed methodology, expected delivery, and reference information. Repeated runs retain separate provenance and artifacts so that a later attempt does not overwrite an earlier outcome.

The four tiers probe complementary demands. Easy tasks emphasize elementary transformations; Normal tasks emphasize multistep mechanism construction; Hard tasks emphasize stereochemical alternatives and competing channels; Impossible tasks probe whether the requested chemical claims are supportable within the allowed methodological domain. Difficulty labels do not replace the explicit contract for an individual task.

An inaccessible element remains in the delivered graph with accessible=false and an appropriate account of the limitation. Computational failure, insufficient budget, and a scientifically justified accessibility judgment are different outcomes. No successful calculation is fabricated for an element whose meaning under the allowed method is disputed, and a refusal paragraph alone does not satisfy graph delivery.

### 3.2 Three scoring components and integrity gates

The specified composite is S = 0.1 G + 0.3 C + 0.6 A, where G is chemical graph agreement, C is binary physical self-consistency, and A is the task's accuracy component. Binding quality contributes to graph assessment rather than multiplying the whole composite. Graph assessment rewards coverage of the reference mechanism without penalizing additional exploration merely for being additional. Extra delivered claims remain subject to physical self-consistency checks.

Self-consistency evaluates the evidence bound to each required accessible element. A qualifying artifact can support an element despite the presence of superseded failed attempts; unrelated files in the workspace do not establish or invalidate that element. Missing required evidence prevents a global self-consistency pass. When a delivered step matched to a reference edge fails these checks, its structural coverage is withdrawn and graph agreement is recomputed. An independently valid covering step can preserve the reference edge's contribution.

For a reference-bearing barrier, the evaluator compares the declared value with the value derived from bound ORCA or Gaussian output, then compares the supported value with the reference. The Gaussian comparison kernel is a_e = exp[-(b_e - b_e_ref)^2 / (2 sigma_e^2)]. Its width belongs to the task rubric; this paper introduces no new tolerance. The implementation also applies rubric-specific penalty caps and reference-definition handling, so A must not be represented as an unconditional arithmetic mean of these kernels. Tasks with favored-channel references use the configured qualitative selectivity component, while property tasks use their corresponding reference quantities.

A missing required declaration or an unsupported or inconsistent numerical claim triggers the accuracy integrity failure: the self-consistency and accuracy contributions are set to zero, leaving 0.1 G. Missing or unparseable graphs and unsupported accessible-species deliveries can instead incur the configured no-evidence penalty. These outcomes must be reported separately from infrastructure failures.

Two implementation details limit the interpretation of aggregate scores. An accessible edge without a numerical reference currently receives nominal accuracy credit; that credit does not demonstrate numerical agreement. In addition, the current evaluator assigns zero barrier-accuracy credit to reference-inaccessible edges without barriers, whereas the project-level specification intends fully correct inaccessible deliveries to be eligible for full credit. This discrepancy remains unresolved in this manuscript. Cross-tier performance claims require a frozen, reconciled scoring specification, and component scores and numerical-reference coverage must accompany the composite.

### 3.3 Reference construction: a dated audit

The 2 October 2026 repository audit records 52 active tasks containing 81 edges. The tier counts are 20 Easy tasks with 20 edges, 10 Normal tasks with 26 edges, 10 Hard tasks with 22 edges, and 12 Impossible tasks with 13 edges. A pure-property task is included in the task count without introducing an artificial barrier edge.

Of the 81 edges, 57 have populated numerical values, 10 lack values without an explicit final exemption, two have an explicit proton-transfer reference exemption, eight pass through transition states declared inaccessible, and four concern properties or state changes. Ten of the 57 populated entries retain recorded evidence or mechanistic limitations. Populated values therefore cannot be equated with 57 fully validated reference pathways.

This inventory is tied to the audit's named reference snapshot. It is not a live claim about subsequently running calculations, and the audit itself did not recompute all paths or reparse all raw logs. The distinctions among missing reference, approved exemption, inaccessible transformation, and property-only quantity are necessary for interpreting benchmark coverage. A historical target of 100 reactions is not evidence of a completed 100-task benchmark.

### 3.4 Validation status and comparative study

The current TS-process documentation reports interface and state-machine checks using substitute calculators and explicitly states that the full native ORCA/Gaussian chain has not yet been accepted. Such checks support software behavior under the tested conditions; they do not establish physical success rates on real reactions. The reference-construction audit likewise does not measure autonomous-agent performance.

A comparative study should isolate three questions: whether evidence-gated delivery reduces unsupported completion claims; whether automatic progression reduces repeated model interventions and failed work; and whether diagnostic retrieval improves recovery once a pipeline reaches a genuine decision point. These are proposed evaluation questions, not completed ablations. Existing standard, DAG-recording, and supervisor-guided modes can support part of the study after their exact configurations are fixed. Their differences do not by themselves isolate every contribution of the TS process.

Matched tasks should use the same authorized scientific protocol and comparable resource constraints. Reporting should retain graph, self-consistency, and accuracy components, reference coverage, false completion, method-limitation judgments, intervention counts, and measured resource use. Allocated CPU-hours and measured CPU-hours must be distinguished. Model versions, repetitions, uncertainty estimates, and exclusions must accompany any performance table. No numerical improvement, zero-hallucination rate, or completed research application is asserted here without the corresponding run artifacts.
