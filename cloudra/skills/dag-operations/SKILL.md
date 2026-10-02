---
name: dag-operations
description: How to use the dag_* tool family in dag_record/dag_guided sessions — propose the mechanism (dag_propose_mechanism), submit file evidence (dag_submit_step_evidence / dag_submit_species_evidence), review items (dag_review_step / dag_review_species), and inspect delivery coverage. Use when composing DAG tool calls.
license: MIT
---

# dag_* tool-family handbook

The intents you use most in a DAG session: **propose the mechanism, submit file evidence, review evidence items, and report delivery coverage**.
There is exactly one persistent graph — the delivery (mechanism) graph. A guided proposal immediately adds candidate species and steps to that graph, so exploration and computation can continue while the Supervisor reviews it. Internal IDs, basis fingerprints, and revision numbers are managed by the harness.

## Core Tool Inventory

- `dag_propose_mechanism`: Coordinator's initial or incremental candidate proposal — declarative species list, transformation steps, scientific rationale, and optional `delivery_targets`. The target list declares the current delivery scope; proposals without it can remain exploratory.
- `dag_accept_mechanism`: Supervisor only (`dag_guided`): accept records the proposal as the current working hypothesis; computation is available before and after review. Reject returns it with a mandatory reason. In `dag_record` the harness auto-accepts on proposal.
- `dag_add_species`: Add a new complex species (`name`, `smiles`). Species name must be unique within the graph.
- `dag_add_step`: Add a new elementary step (`name`, `from`, `to`). Step name must be unique; `from` and `to` refer to existing species names.
- `dag_remove_edge`: Delete an elementary step (`step`, mandatory `rationale`). Deletions are permanently recorded in the change log.
- `dag_remove_node`: Delete a species node (`name` or id, mandatory `reason`). A node that still has incoming/outgoing steps is refused with the linked step names — remove those steps first, then delete the node (no implicit cascade).
- `dag_update_delivery_element`: Update metadata or disposition (`status`, `reason`, `annotations`, `required`). Does not rename elements or change SMILES.
- `dag_submit_step_evidence`: Explicitly submit finished QM logs for a step (`step_name`, `ts_file`, optional IRC files, `reaction_coordinate_description`). The harness snapshots the files into `.cloudra/evidence/`, checks TS frequencies when available, attaches every submitted file to the step, and queues a guided review.
- `dag_submit_species_evidence`: Explicitly submit finished QM logs for a species (`species_name`, `opt_file`, optional `freq_file`, `description`). The harness snapshots both files, checks minimum frequencies when available, and queues a guided review.
- `dag_review_step` / `dag_review_species`: Supervisor only (`dag_guided`): adjudicate the active item with `step_name` or `species_name`, `verdict` (`supported` or `rejected`), and `rationale`.
- `dag_review_evidence`: Supervisor only (`dag_guided`): Resolve a queued structured review request with a basis-matched decision.
- `dag_review_call`: Supervisor lower-level review interface (adjudicates a CallReview by `stage_kind` and verdict).
- `dag_bind_evidence`: Bind finished calls using `attachments: [{tool_call_id, bind_target, stage_kind, claim, rationale}]`. Each claim and rationale belongs to its attachment; use a one-element list for a single bind. In `dag_guided`, each attachment needs a claim and enters the Supervisor's review queue.
- `dag_set_coverage_contract`: Supervisor only (`dag_guided`): Strengthen delivery coverage requirements.
- `dag_message_supervisor`: Send a structured review request (appeals, blockers, notes) to the Supervisor.
- `dag_delivery_report` / `dag_view`: Inspect graph topology, review status, and element delivery coverage.

## The Element Lifecycle

The graph keeps machine-derived stage states separate from Supervisor file-review decisions. Accepting a file can support a pending delivery requirement without rewriting its machine state. `rejected` and `needs_evidence` remain open gaps until addressed. A required element can also be explicitly `skipped` or `not_applicable` with a reason when the contract permits it. `dag_delivery_report` evaluates the currently declared delivery targets and unresolved relevant reviews; unrelated exploratory branches remain in the graph without becoming delivery debt. A complete report is a workflow judgement, not scientific truth; benchmark scoring is independent.

## dag_guided workflow

Advance through these activities as evidence becomes available:

1. **User submits a task** → Coordinator is woken.
2. **Initial research**: read skills, search literature, and run exploratory calculations as needed.
3. **Propose candidates and scope**: `dag_propose_mechanism` with `species`, `steps`, `rationale`, and `delivery_targets` when declaring the work to deliver. Candidate graph changes take effect immediately.
4. **Supervisor review**: Supervisor is woken (`mechanism_proposed`) and calls `dag_accept_mechanism`. Accept records the draft review state; computation and branching do not wait for that decision. Reject returns the draft with a reason for revision.
5. **Compute & Advance**: sub-agents run calculations and report outputs.
6. **Explicit evidence submission**: submit finished outputs with `dag_submit_step_evidence` and `dag_submit_species_evidence`. Only submitted logs enter the Supervisor's active review queue.
7. **Supervisor adjudication**: Supervisor reviews the active item via `dag_review_step` / `dag_review_species` with `verdict` and `rationale`. Verdict notifications arrive in the submitter's mailbox.
8. **Delivery**: verify with `dag_delivery_report` before calling `stop`.

## dag_record workflow

Same declarative discipline without the Supervisor: proposals, including scope updates, are auto-accepted by the harness on submission. File submissions still need their deterministic checks and stage bindings for machine-backed delivery.


## Proposing the mechanism: dag_propose_mechanism

Coordinator-only. Input structure:

```json
{
  "rationale": "Considered: concerted Diels-Alder vs stepwise diradical; endo vs exo approach. Observed: mechanism_predict on C=C.C=CC=C → C1=CCCCC1 returned the concerted cycloaddition as the only elementary edge to the cyclohexene complex; no stepwise intermediate appeared in the network. Chose: the single concerted step on the graph; diradical stepwise omitted because it was absent from the tool output; exo/endo are the same bond-change and will be distinguished at TS search, not as separate delivery steps.",
  "species": [
    {"name": "Reactant Complex", "smiles": "C=C.C=CC=C"},
    {"name": "Product Complex", "smiles": "C1=CCCCC1"}
  ],
  "steps": [
    {"name": "Diels-Alder Cycloaddition", "from": "Reactant Complex", "to": "Product Complex"}
  ],
  "delivery_targets": ["Diels-Alder Cycloaddition"]
}
```

- Each species represents the complete chemical system/complex state.
- Names are unique within species and within steps.
- Later proposals can refer to existing species by unique name or ID, so an A→B graph can grow by adding only C and B→C. A scope-only proposal can change `delivery_targets` without adding species or steps.
- `delivery_targets` declares the current delivery intent. Omit it for an exploratory branch that should not change the existing delivery scope. Expanding it immediately makes the added targets part of final-delivery checks even before guided review accepts the scope update.
- No `occurrence`, `role`, or stage arrays are required.
- `rationale` is mandatory. In `dag_guided` it is the Coordinator's message to the Supervisor: **Considered** / **Observed** / **Chose** (what was weighed, what the mechanism-inference tool actually showed or why it was not run, which steps are on the graph and why any other channel was left off). A single-path graph is allowed when Chose states that trade-off. The Supervisor rejects an unexplained omission, not a single path. `dag_record` auto-accepts and does not apply this dialogue.

Step stage contracts may include `ts_guess`, but it is an advisory stage: never `required`, and it never blocks binding `ts_opt`/`frequency` evidence. Default drafts and newly added steps require **ts_opt + frequency + short_irc**. Live `complete` requires the IRC direction proof as well as the saddle evidence; accepting TS/frequency evidence alone leaves the IRC gap open. The proof uses geometries from both IRC directions lying between the TS and the corresponding endpoint minima; full IRC convergence to the minima is not required.

## Adjusting an accepted mechanism

- `dag_add_species`: Add a new species (`name`, `smiles`).
- `dag_add_step`: Add a new elementary step (`name`, `from`, `to`).
- `dag_remove_edge`: Delete a step (`step`, `rationale`). Mandatory scientific rationale explaining the removal.
- `dag_remove_node`: Delete a species node (`name` or id, `reason`). If the node still has steps attached, the call is refused with those step names — delete the steps first, then the node.
- `dag_update_delivery_element`: Update metadata (`status`, `reason`, `annotations`, `required`).

## File Evidence Submission

Submit finished QM logs explicitly:

- `dag_submit_step_evidence`:
  ```json
  {
    "step_name": "Diels-Alder Cycloaddition",
    "ts_file": "runs/ts_freq.out",
    "irc_file": "runs/irc.out",
    "reaction_coordinate_description": "The unstable mode forms two carbon-carbon bonds."
  }
  ```
  In `dag_record`, the TS calculation must verify exactly 1 imaginary frequency (`n_imag == 1`). In `dag_guided`, an undecidable frequency result can still be submitted for the Supervisor's explicit judgement. Default steps require IRC evidence for final delivery. You may submit TS/frequency evidence first, then submit it again with a combined IRC log or both directional IRC logs when available.
- `dag_submit_species_evidence`:
  ```json
  {
    "species_name": "Reactant Complex",
    "opt_file": "runs/reactant_opt.out",
    "description": "Optimized reactant complex."
  }
  ```
  In `dag_record`, the calculation must verify 0 imaginary frequencies (`n_imag == 0`). In `dag_guided`, an undecidable result can be submitted for explicit review; the machine stage remains pending unless independently bound.

Files are snapshotted into `.cloudra/evidence/` with their sha256 hashes, ensuring evidence immutability.

## Reviewing Evidence: dag_review_step / dag_review_species (Supervisor, dag_guided)

The Supervisor reviews the active review item bound in its execution context. The
step/species tools use the target name plus a scientific verdict:
```json
{
  "step_name": "step1",
  "verdict": "supported",
  "rationale": "TS mode supports the proposed transformation."
}
```

Allowed verdicts:
- `supported`: Supervisor accepts the submitted file for the specified target. The durable review decision is kept separate from machine-derived evidence levels and does not assert scientific truth.
- `rejected`: Evidence does not support the element (rationale required). It remains an open coverage gap.

Use `species_name` instead of `step_name` for a species review. Structured
requests use `dag_review_evidence` with `accept`, `reject`, or `needs_evidence`.
Stage dispositions (`skipped` / `not_applicable`) belong to the graph contract;
they are not file-review verdicts.

## Inspection & Delivery Audit

- `dag_view`: Inspect current graph topology, pending review items, and open gaps.
- `dag_delivery_report`: Coverage report for the current declared delivery scope. It includes relevant unresolved reviews and pending scope decisions; exploratory graph branches outside that scope do not block delivery.
- In dag_guided, file delivery requires BOTH Supervisor acceptance and scientific checks. Review acceptance never fills a failed or incomplete science check. Read `scientific_checks` and its `next_action` in submission results or `dag_view_evidence(review_id)`; supply missing evidence and re-submit the same target. Exploration and review remain available during repair. Benchmark scoring is independent.
