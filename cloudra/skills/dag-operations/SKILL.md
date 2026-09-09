---
name: dag-operations
description: How to use the dag_* tool family in dag_record/dag_guided sessions — propose the mechanism (dag_propose_mechanism), submit file evidence (dag_submit_step_evidence / dag_submit_species_evidence), review items (dag_review_step / dag_review_species), and inspect delivery coverage. Use when composing DAG tool calls.
---

# dag_* tool-family handbook

The intents you use most in a DAG session: **propose the mechanism, submit file evidence, review evidence items, and report delivery coverage**.
There is exactly one persistent graph — the delivery (mechanism) graph. There is no process graph, no scheduling queue, no complex occurrence/role taxonomy, and no manual stage arrays: after the mechanism is accepted, everyone works at their own pace. Internal IDs, basis fingerprints, and revision numbers are managed by the harness.

## Core Tool Inventory

- `dag_propose_mechanism`: Coordinator's initial delivery proposal — declarative species list, transformation steps, and scientific rationale. No compute is unlocked until the draft is accepted.
- `dag_accept_mechanism`: Supervisor only (`dag_guided`): accept commits the proposal (all elements start `pending`) and unlocks compute; reject returns it with a mandatory reason. In `dag_record` the harness auto-accepts on proposal.
- `dag_add_species`: Add a new complex species (`name`, `smiles`). Species name must be unique within the graph.
- `dag_add_step`: Add a new elementary step (`name`, `from`, `to`). Step name must be unique; `from` and `to` refer to existing species names.
- `dag_remove_edge`: Delete an elementary step (`step`, mandatory `rationale`). Deletions are permanently recorded in the change log.
- `dag_remove_node`: Delete a species node (`name` or id, mandatory `reason`). A node that still has incoming/outgoing steps is refused with the linked step names — remove those steps first, then delete the node (no implicit cascade).
- `dag_update_delivery_element`: Update metadata or disposition (`status`, `reason`, `annotations`, `required`). Does not rename elements or change SMILES.
- `dag_submit_step_evidence`: Explicitly submit finished QM logs for a step (`step`, `ts_log`, `summary`, optional `irc_log`). The harness checks the workspace sandbox, computes sha256, snapshots into `.cloudra/evidence/`, verifies TS mode (exactly 1 imaginary frequency), and enqueues the item for review.
- `dag_submit_species_evidence`: Explicitly submit finished QM logs for a species (`species`, `log_path`, `summary`). The harness snapshots evidence and verifies ground-state minimum mode (0 imaginary frequencies).
- `dag_review_step` / `dag_review_species`: Supervisor only (`dag_guided`): Adjudicate the current active review item with `verdict` (`agree`, `disagree`, `skip`, `not_applicable`, `needs_evidence`) and `reason`.
- `dag_review_evidence`: Supervisor only (`dag_guided`): Resolve a queued structured review request with a basis-matched decision.
- `dag_review_call`: Supervisor lower-level review interface (adjudicates a CallReview by `stage_kind` and verdict).
- `dag_bind_evidence`: Lower-level evidence binding interface.
- `dag_set_coverage_contract`: Supervisor only (`dag_guided`): Strengthen delivery coverage requirements.
- `dag_message_supervisor`: Send a structured review request (appeals, blockers, notes) to the Supervisor.
- `dag_delivery_report` / `dag_view`: Inspect graph topology, review status, and element delivery coverage.

## The Element Lifecycle

Each species and step element has a single authoritative delivery status:
- `pending`: Waiting for calculations and evidence submission.
- `supported`: Verified and approved by the harness/Supervisor as scientifically sound with matching physical checks (e.g. 1 imaginary freq for TS, 0 for minima).
- `rejected`: Disapproved by the Supervisor with a mandatory reason. **An open gap that is still owed**, not a disposal.
- `skipped`: Element could be computed but is deliberately abandoned (mandatory `reason`, e.g. branch ruled out by mapping or multi-reference character). Counts as disposed.
- `not_applicable`: Element does not apply to this system (mandatory `reason`, e.g. barrierless path). Counts as complete — not owed.
- `needs_evidence`: Review requested more data; closes the review item without changing element status until new logs are submitted.

Coverage `complete` ⇔ every required element is in `supported` status, or `skipped`/`not_applicable` with a non-empty reason. `pending` and `rejected` are both open gaps.

## dag_guided workflow

Advance in this order (the harness blocks compute until draft acceptance):

1. **User submits a task** → Coordinator is woken.
2. **Initial research**: read skills, search literature; compute entry points are gated until the mechanism is accepted.
3. **Propose the mechanism**: `dag_propose_mechanism` with `species`, `steps`, and `rationale`.
4. **Supervisor review**: Supervisor is woken (`mechanism_proposed`) and calls `dag_accept_mechanism`. Accept unlocks compute; reject returns the draft with a reason for revision.
5. **Compute & Advance**: sub-agents run calculations and report outputs.
6. **Explicit evidence submission**: submit finished outputs with `dag_submit_step_evidence` and `dag_submit_species_evidence`. Only submitted logs enter the Supervisor's active review queue.
7. **Supervisor adjudication**: Supervisor reviews the active item via `dag_review_step` / `dag_review_species` with `verdict` and `reason`. Verdict notifications arrive in the submitter's mailbox.
8. **Delivery**: verify with `dag_delivery_report` before calling `stop`.

## dag_record workflow

Same declarative discipline without the Supervisor: the proposal is auto-accepted by the harness on submission, and evidence is verified and recorded deterministically upon submission.


## Proposing the mechanism: dag_propose_mechanism

Coordinator-only. Input structure:

```json
{
  "rationale": "Mapping and scientific basis for the proposed reaction pathway.",
  "species": [
    {"name": "Reactant Complex", "smiles": "C=C.C=CC=C"},
    {"name": "Product Complex", "smiles": "C1=CCCCC1"}
  ],
  "steps": [
    {"name": "Diels-Alder Cycloaddition", "from": "Reactant Complex", "to": "Product Complex"}
  ]
}
```

- Each species represents the complete chemical system/complex state.
- Names are unique within species and within steps.
- No `occurrence`, `role`, or stage arrays are required.
- `rationale` is mandatory.

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
    "step": "Diels-Alder Cycloaddition",
    "ts_log": "runs/ts_freq.out",
    "irc_log": "runs/irc.out",
    "summary": "TS saddle point located with single imaginary frequency (-485 cm^-1) connecting reactants to product."
  }
  ```
  The harness verifies that the TS calculation contains exactly 1 imaginary frequency (`n_imag == 1`).
- `dag_submit_species_evidence`:
  ```json
  {
    "species": "Reactant Complex",
    "log_path": "runs/reactant_opt.out",
    "summary": "Optimized ground state confirmed with zero imaginary frequencies."
  }
  ```
  The harness verifies that the species calculation contains 0 imaginary frequencies (`n_imag == 0`).

Files are snapshotted into `.cloudra/evidence/` with their sha256 hashes, ensuring evidence immutability.

## Reviewing Evidence: dag_review_step / dag_review_species (Supervisor, dag_guided)

The Supervisor reviews the active review item bound in its execution context:
```json
{
  "verdict": "agree",
  "reason": "TS mode cleanly verifies the concerted C-C bond formation with exactly one imaginary frequency at -485 cm^-1."
}
```

Allowed verdicts:
- `agree`: Evidence supports the element. Status becomes `supported`.
- `disagree`: Evidence does not support the element (reason required). Status becomes `rejected`: **still owed work**, an open coverage gap.
- `skip`: Element deliberately abandoned (reason required, e.g. severe multi-reference character). Counts as disposed.
- `not_applicable`: Element does not apply to this system (reason required). Counts as complete — not owed.
- `needs_evidence`: Evidence snapshot is insufficient (reason required). Closes the review item without changing element status; submitter re-submits once new data is available.

## Inspection & Delivery Audit

- `dag_view`: Inspect current graph topology, pending review items, and open gaps.
- `dag_delivery_report`: Full coverage report across all species and steps.
- Delivery complete requires all required species and steps to be `supported` or explicitly disposed with reason (`skipped` / `not_applicable`).

