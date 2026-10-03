# Cloudra: An Evidence-Gated Harness for Autonomous Organic Reaction Mechanism Elucidation

**Authors:** Cloudra Team
**Affiliation:** Changsha University of Science and Technology, Changsha, China
**Correspondence:** 951899550@qq.com
**Version:** 3 October 2026; methods and benchmark-construction draft

## Abstract

Autonomous reaction mechanism elucidation requires more than executing quantum-chemical calculations: the resulting structures, pathways, and energies must support the mechanism being claimed. We present Cloudra, a multi-agent harness for homogeneous organic chemistry that separates mechanistic judgment from reproducible computational procedures and evidence acceptance. Its design combines three elements. A persistent transition-state process delegates routine preparation, calculation, and verification to explicit method-bound stages, returning unresolved decisions to the agent. A delivery evidence directed acyclic graph records chemical species and transformations, with evidence levels derived by the harness rather than assigned through conversational assertions. An independent benchmark evaluates delivered graphs and computational artifacts through structural agreement, physical self-consistency, and quantitative accuracy, including explicit declarations of method-limited inaccessibility. Event-driven execution and durable calculation records support this contract across asynchronous jobs and revisions. We describe the implemented architecture and the current benchmark construction status: a dated repository audit covers 52 tasks and 81 edges, with 57 populated numerical references and remaining evidence limitations. These counts characterize reference construction, not autonomous-agent performance. The contribution is a testable division of responsibility between model reasoning, numerical computation, and scientific acceptance; comparative performance and complete native-engine validation remain to be established.

## 1. Introduction and Related Work

### 1.1 From plausible explanations to accepted evidence

A molecular mechanism is a claim about chemical states and the pathways connecting them. Establishing such a claim requires structures with consistent identities, appropriate stationary-point character, evidence for reaction direction, and energies expressed against a defined reference. An optimizer terminating successfully does not establish a minimum; a single imaginary frequency does not by itself establish the intended elementary transformation. An autonomous system must preserve these distinctions throughout exploration and in its final deliverable.

Language models can formulate hypotheses and interpret failures, but the validity of a calculation does not follow from the fluency of its explanation. Repeatedly asking a model to remember every acceptance condition leaves scientific completion dependent on conversational behavior. Cloudra instead assigns routine execution and explicit acceptance predicates to a persistent harness. The model remains responsible for proposing and revising the research strategy, while the harness records which claims the available artifacts actually support.

### 1.2 Position relative to prior work

El Agente establishes an important reference for autonomous quantum-chemistry workflows [1]. Cloudra adopts the general separation between reasoning, external computation, and verification, while centering its deliverable on a chemical mechanism and its supporting evidence. This is a difference in task contract, not a claim that general quantum-chemistry agents lack useful verification.

Automated reaction exploration also predates language-model agents. YARP develops efficient reaction enumeration and transition-state characterization [2], and autodE automates reaction-energy profiles for organic and organometallic systems [3]. Cloudra therefore does not claim the invention of automated transition-state search or reaction-network discovery. Such methods motivate the numerical capabilities that a research harness should invoke and audit.

ARCHE is a direct task-level neighbor: it combines general reasoning, a specialized computational-chemistry model, and tools in an iterative hypothesis–calculation–validation loop, illustrated through three mechanistic applications [4]. Its existence rules out describing homogeneous mechanistic discovery as an untouched application. Cloudra's proposed distinction is the coupling of a persistent computational contract, a chemical evidence graph, and an independently scored delivery protocol. Whether that coupling improves reliability or cost is an empirical question, not a conclusion inferred from architectural differences.

### 1.3 Contributions and scope

First, Cloudra exposes transition-state work as a persistent process with explicit inputs, stage-specific methods, and recoverable revisions. Routine successful transitions are delegated to the harness; incomplete evidence or failed attempts create an explicit decision point.

Second, the delivery DAG binds chemical claims to computational evidence. It distinguishes a proposed structure, a computed structure, and a verified stationary point, preventing those states from being collapsed into a model-generated declaration of completion.

Third, an artifact-based benchmark separates graph agreement, physical validity, and accuracy. It represents inaccessible elements within the requested mechanism instead of accepting a conversational refusal as delivery. These contributions concern the organization and auditability of autonomous research. Peer communication, retrieval, and execution infrastructure support them but are not presented as independent proofs of scientific novelty.

## 2. Architecture and Methods

### 2.1 The division of responsibility

Cloudra separates three responsibilities: agents propose chemical hypotheses and authorized revisions; numerical tools generate structures and computational artifacts; the harness governs state transitions and evidence acceptance. A proposed hypothesis is consequently allowed to be wrong without being recorded as a verified result. Conversely, a successful tool call is not sufficient to upgrade the associated chemical claim.

Specialized roles exchange findings through AgentHub. A supervisory role can examine the pending review work recorded in the DAG and request additional evidence. Scientific review complements the deterministic predicates; it does not turn missing frequency or direction evidence into a passed calculation. Knowledge retrieval supplies methodological context, but retrieved advice is not a substitute for an artifact generated for the particular structure and method under investigation.

### 2.2 Persistent transition-state procedures

The current interface provides three operations: ts_prepare creates a run from explicit inputs, ts_inspect reads its authoritative state, and ts_resume revises that run with a reason and an expected revision. Inputs separately describe the reaction, conformers, guess strategy, saddle optimization, verification calculations, and execution resources. The method for one group is not silently inherited by another. This separation matters when an inexpensive exploratory path provides a candidate for a different, formally declared refinement method.

The process advances through preparation, structural binding, mapping, assembly, candidate generation, validation, submission, refinement, and verdict. Candidate generation can draw on the supported path, scan, or supplied-geometry routes. A peak on a scan or an exploratory trajectory remains a candidate until the formal saddle and direction checks succeed. Successful calculation notifications advance the process without requiring the agent to restate the next routine instruction.

A failed or inconclusive attempt preserves its inputs, artifacts, and costs. Revisions invalidate the affected downstream results while retaining independently valid upstream evidence. A change to one endpoint calculation therefore need not erase the saddle calculation or the other endpoint. Stable request identifiers and persisted receipts support deduplication and recovery around submission. These are execution guarantees; they do not guarantee that a suitable transition state exists or will be found.

Scientific method selection remains explicit. The manuscript does not prescribe a universal functional, basis set, solvent model, conformer window, or barrier cutoff. Those choices belong to the authorized task protocol and must remain attached to the corresponding evidence.

### 2.3 Chemical evidence graphs and stage contracts

The delivery graph represents chemical occurrences and elementary transformations rather than a list of tool calls. Occurrences reference species identity and state; elementary-step records connect occurrences and bind the relevant evidence. The runtime delivery schema and the exported benchmark schema serve different purposes and should not be conflated: a benchmark graph may represent a transition state as a node referenced by an edge, while a runtime edge carries its own stage contract.

At the scientific level, an elementary transformation proceeds from a transition-state guess to saddle optimization and frequency qualification, short-IRC direction evidence, and thermochemical annotation. The implementation retains more granular stage kinds, including frequency, endpoint, direction, and identity checks, selected by the relevant contract. This is not an unconditional eight-step chain imposed on every graph element. The guess stage is advisory and cannot replace evidence for a saddle.

For a species claimed as a verified minimum, bound frequency evidence must establish zero imaginary frequencies. A transition state requires exactly one imaginary frequency together with evidence for the intended reaction direction. Missing frequency analysis remains missing evidence, even if geometry optimization reports success. The evidence level is derived by the harness; the agent cannot promote its own claim merely by changing the language used to describe it.

Short-IRC verification requires usable frames on both sides of the saddle and geometric direction consistency with the corresponding verified minima. The IRC trajectories themselves need not converge all the way to those minima. This allowance does not waive the independent requirement that the endpoint minima be verified. The current TS process additionally retains endpoint optimization, frequency, identity, and stereochemical checks before its verified verdict.

A DAG is a representation of the delivered exploration, not a claim that all chemistry is acyclic. Repeated occurrences can describe a finite unfolding of a catalytic sequence; representation choices and coverage limits must be stated when comparing such a delivery with a reference graph.

### 2.4 Asynchronous execution and evidence provenance

Long-running calculations are managed outside the model's conversational lifetime. The event-driven runtime records state changes and reacts to calculation outcomes, while the scheduler maintains durable job records. Recovery can therefore resume research decisions without treating a disconnected conversation as evidence that a calculation has stopped.

Calculation liveness is determined through the project's exclusive-lock mechanism. Cancellation is requested through the ledger and handled by the execution side; a reasoning or review failure must not terminate a running quantum-chemical process. Native program termination markers are checked independently of numerical parsing. Reading an energy or geometry from a partial output does not establish that the underlying job finished normally.

Provenance connects the chemical claim, input revision, declared method, actual structure, job, and resulting artifacts. Geometry tools reduce dependence on model-written Cartesian coordinates, but guidance against manual coordinates is not described as a universal security guarantee. The stronger scientific requirement is that the geometry actually submitted and the evidence actually accepted correspond to the declared structure and method.

Event records improve traceability and recovery. They do not make stochastic model outputs or numerical searches exactly reproducible by themselves. Reproduction also requires model and software versions, seeds where applicable, calculation settings, and the relevant artifacts.

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

## 4. Discussion and Conclusion

### 4.1 What the harness contributes

The central design choice is where scientific responsibility resides. A model can suggest a different pathway when a search fails, but it should not silently change the criteria for accepting that pathway. A persistent process gives routine computation a stable contract; the evidence graph gives chemical claims durable meaning; the evaluator examines the resulting artifacts independently. Together, these mechanisms make the boundary between hypothesis and supported result inspectable.

This division does not remove scientific judgment. Deterministic acceptance is conditional on chosen methods, structural identity rules, and the adequacy of the evidence predicates. An incorrectly specified reference state or inappropriate electronic-structure approximation can still produce internally consistent but scientifically misleading results. Human-approved methodological choices and explicit limitations remain necessary, especially for multireference chemistry, competing spin states, and solvent-dependent pathways.

The same distinction applies to inaccessible mechanisms. Method-limited inaccessibility is not a universal statement that a reaction cannot occur, and failure to find a saddle is not proof of physical impossibility. A useful autonomous system preserves the proposed mechanism, records the disputed element, and exposes the evidence and assumptions that justify its status.

### 4.2 Limitations and next evidence required

The current evidence supports an architectural description and a transparent reference-construction report. It does not yet establish superior discovery coverage, lower cost, or higher accuracy than neighboring systems. Native-engine acceptance of the persistent TS process, resolution of the accessibility-scoring discrepancy, and a fixed benchmark release are prerequisites for the corresponding empirical claims.

Incomplete reference coverage and existing mechanistic caveats constrain quantitative comparisons. Parser behavior, geometry identity, direction tests, and provenance checks also require adversarial and realistic evaluation: formal structure alone cannot guarantee that every scientifically incorrect claim will be detected. Extending the approach beyond homogeneous molecular systems requires its own methods and validation, rather than assuming that a shared execution runtime transfers chemical validity.

Cloudra frames autonomous mechanism elucidation as evidence-governed research. Its proposed contribution is the integration of deterministic computational procedures, chemically meaningful delivery contracts, and independent artifact-based assessment. This provides a concrete basis for testing whether models can direct mechanistic exploration while the harness preserves the distinction between a plausible hypothesis, a completed calculation, and an accepted scientific result.

## References

1. [Y. Zou et al. El Agente: An autonomous agent for quantum chemistry. Matter 8, 102263 (2025).](https://doi.org/10.1016/j.matt.2025.102263)

2. [Q. Zhao and B. M. Savoie. Simultaneously improving reaction coverage and computational cost in automated reaction prediction tasks. Nature Computational Science 1, 479–490 (2021).](https://doi.org/10.1038/s43588-021-00101-3)

3. [T. A. Young, J. J. Silcock, A. J. Sterling, and F. Duarte. autodE: Automated Calculation of Reaction Energy Profiles—Application to Organic and Organometallic Reactions. Angewandte Chemie International Edition 60, 4266–4274 (2021).](https://doi.org/10.1002/anie.202011941)

4. [D. Li et al. Autonomous Chemical Mechanistic Discovery through Agentic Reasoning and Validation. arXiv:2609.11147 (2026).](https://arxiv.org/abs/2609.11147)
