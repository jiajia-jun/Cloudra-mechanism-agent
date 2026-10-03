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
