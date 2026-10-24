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

Two implementation details previously limited the interpretation of aggregate scores: an accessible edge without a numerical reference receives nominal accuracy credit without demonstrating numerical agreement; and earlier evaluator revisions penalized reference-inaccessible edges when delivery omitted barriers. The latter discrepancy has now been reconciled in the current evaluator release: compliant negative deliveries with justified inaccessibility receive full accuracy credit, and multi-stage transition-state logs (optimization, harmonic frequency, and intrinsic reaction coordinate paths) are bound collectively rather than truncated at the first path.

### 3.3 Reference construction: a dated audit

The 2 October 2026 repository audit records 52 active tasks containing 81 edges. The tier counts are 20 Easy tasks with 20 edges, 10 Normal tasks with 26 edges, 10 Hard tasks with 22 edges, and 12 Impossible tasks with 13 edges. A pure-property task is included in the task count without introducing an artificial barrier edge.

Of the 81 edges, 57 have populated numerical values, 10 lack values without an explicit final exemption, two have an explicit proton-transfer reference exemption, eight pass through transition states declared inaccessible, and four concern properties or state changes. Ten of the 57 populated entries retain recorded evidence or mechanistic limitations. Populated values therefore cannot be equated with 57 fully validated reference pathways.

This inventory is tied to the audit's named reference snapshot. It is not a live claim about subsequently running calculations, and the audit itself did not recompute all paths or reparse all raw logs. The distinctions among missing reference, approved exemption, inaccessible transformation, and property-only quantity are necessary for interpreting benchmark coverage. A historical target of 100 reactions is not evidence of a completed 100-task benchmark.

### 3.4 Pilot four-arm ablation and empirical observations

To isolate the contributions of external scientific gating, explicit topological DAG representations, and structured diagnostic feedback, an empirical pilot ablation campaign (P1b) was conducted across 48 isolated sandboxes. The study evaluated four system arms across four representative reaction tasks spanning the benchmark difficulty tiers (Easy E1: E2 elimination; Normal NB1: six-membered decarboxylation; Hard HA1: stereoselective conrotatory/disrotatory electrocyclization; and Impossible IA1: forbidden cyclobutane fragmentation) with three replicated trials per condition:

1. **Arm A (Guided)**: Full toolchain, explicit delivery DAG, active supervisor with evidence-based settlement gating, and detailed diagnostic guidance.
2. **Arm B (Record)**: Full toolchain and DAG recording, but settlement gating removed (autonomous stopping without external veto).
3. **Arm C (Standard)**: DAG tools hidden, settlement gating removed, and public scientific acceptance verdicts neutralized to baseline quantum-chemical console outputs.
4. **Arm D (Brief-errors)**: Architectural configuration identical to Arm A, but diagnostic error messages compressed into compact status codes and target identifiers without verbose recovery text.

Following scoring fairness reconciliation, offline evaluation of the 48 execution runs revealed marked divergence across the ablation arms:

| Arm | Core Configuration | Composite Mean | SD | Easy (E1) | Normal (NB1) | Hard (HA1) | Impossible (IA1) |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **Arm A (Guided)** | Full Harness + Active Gating + Detailed Feedback | **0.979** | **0.032** | 1.000 | 0.991 | 0.925 | **1.000** |
| **Arm D (Brief-errors)** | Full Harness + Active Gating + Compact Codes | **0.907** | 0.224 | 1.000 | 0.960 | 0.943 | 0.724 |
| **Arm B (Record)** | Full Harness + Ungated Settlement | 0.729 | 0.365 | 0.972 | 0.914 | 0.929 | **0.102** |
| **Arm C (Standard)** | Unstructured Baseline + Neutralized Feedback | 0.534 | 0.574 | 0.853 | 0.940 | **0.243** | **0.102** |

Three primary empirical findings emerge from this pilot cohort:

First, **external scientific gating is strictly essential to eliminate false-positive mechanistic declarations**. On the forbidden reaction IA1, both un-gated configurations (Arms B and C) suffered a 100% false-positive rate: failing to locate a legitimate stationary point, the models fabricated unphysical reaction barriers (18.6–25.4 kcal/mol) and declared completion, causing accuracy to collapse to zero (overall composite 0.102). In contrast, the external supervisor gate in Arm A compelled the agent to produce a 100% verified negative claim, resulting in perfect credit (1.000).

Second, **compact diagnostic codes exhibit strong resilience on physically tractable tasks, while verbose guidance suppresses variance**. On solvable single- and multi-step transformations (E1, NB1, HA1), Arm D achieved parity with Arm A (0.943–1.000), proving that compact domain error codes provide sufficient signal for model self-correction. However, on ambiguous impossible transformations, verbose scientific rationales provided critical support for justified abstention, reducing total variance from 0.224 in Arm D to 0.032 in Arm A.

Third, **the absence of explicit topological tracking induces catastrophic failure on stereochemically competitive channels**. While Arm C performed moderately on elementary transformations (E1: 0.853, NB1: 0.940), it deteriorated on the stereochemically demanding electrocyclization HA1 (0.243, including one run that failed to emit a mechanism graph), accompanied by severe variance (SD 0.574). Explicit DAG representation acts as an indispensable cognitive scaffold for organizing competing stereochemical pathways.
