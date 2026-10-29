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
