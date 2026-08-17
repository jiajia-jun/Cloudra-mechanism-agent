---
name: dag-operations
description: How to use the dag_* tool family in dag_record/dag_guided sessions — propose the mechanism (dag_propose_mechanism), choose stage contracts, review or bind calls (dag_review_call / dag_bind_evidence), and what to do when a call is rejected. Use when composing DAG tool calls.
---

# dag_* tool-family handbook

The intents you use most in a DAG session: **propose the mechanism, choose stage contracts, work, get each delivery-relevant call reviewed, and report coverage**.
There is exactly one persistent graph — the delivery (mechanism) graph. There is no process graph, no frontier, no scheduling: after the mechanism is accepted, everyone works at their own pace. Revision numbers and review ids are managed by the system; you do not need to track them.

- `dag_propose_mechanism`: Coordinator's first delivery artifact — a delivery-graph draft (occurrences + elementary-step edges) plus per-element stage contracts and a rationale. No compute is unlocked until the draft is accepted.
- `dag_accept_mechanism`: Supervisor only (`dag_guided`): accept commits the draft (all stages start `pending`) and unlocks compute; reject returns it with a mandatory reason. In `dag_record` the harness auto-accepts on proposal.
- `dag_add_species` / `dag_add_step` / `dag_update_delivery_element`: Coordinator adjusts the accepted mechanism. Each change wakes the Supervisor for audit in `dag_guided`.
- `dag_review_call`: Supervisor only (`dag_guided`): adjudicate one finished call from the review inbox and bind its stage verdict.
- `dag_bind_evidence`: Coordinator binds a finished call to a declared stage. In `dag_record` it binds
  directly; in `dag_guided` it **submits the call's result into the review inbox** for the Supervisor to
  adjudicate — use it for evidence-bearing tools that do not auto-review (e.g. `format_converter`,
  `internal_coordinates`), passing `tool_call_id`, `bind_target`, and `stage_kind`.
- `dag_message_supervisor`: Coordinator leaves a note for Supervisor (appeal a verdict, explain a contract choice, report a blocker). Does not change the graph. Not available to sub-agents.
- `dag_remove_edge`: delete a delivery edge; `rationale` is required (deletions stay in the change log). Supervisor is read-only on delivery, so structural cleanup is the Coordinator's job.
- `dag_set_coverage_contract`: Supervisor only; strengthen the coverage contract (never weaken — waivers are user-only).
- `dag_delivery_report` / `dag_view`: coverage self-check and graph/review-inbox inspection.
- `dag_view_evidence`: read the full source arguments + parsed result behind one review (or evidence id) —
  use it to distinguish a broken parser from a genuinely missing source file before appealing.

## The stage model

Every delivery element carries an ordered **stage contract**, chosen by the Coordinator at proposal time. The harness never infers a chain the Coordinator did not declare.

- Occurrence stages: `geometry`, `frequency`, `single_point`.
- Elementary-step stages: `ts_guess` (advisory; can never satisfy `ts_opt`/`frequency`), `ts_opt`, `frequency`, `short_irc`, `endpoint_a`, `endpoint_b`, `direction`, `identity`, `thermochemistry`.

Endpoint convention (read this before naming endpoints): **`endpoint_a` is the step's target-node side (the product); `endpoint_b` is the source-node side (the reactant complex).** For a Diels-Alder step that is "reactant complex → product", `endpoint_a` = the product (e.g. cyclohexene) and `endpoint_b` = the reactant complex (e.g. s-cis-butadiene + ethylene). Do not guess — check the edge's source/target nodes with `dag_view`.

Stage status: `pending` → `supported` (bound to a successful call), `skipped` (reason required — the only non-success disposal), or `rejected` (reason required — **an open gap that is still owed**, not a disposal; the only exits are a later re-bind or an explicit skip-with-reason).

Bind order is strict: binding stage *k* requires every previous **required** stage to be `supported` or `skipped`, else `stage_out_of_order`. A `rejected` previous stage blocks later stages until it is re-bound or skipped. The harness also validates tool success, that the resolved ref is a real post-completion result (a `submit_compute_job` call is never evidence — bind the finished job's parser output), and deriver checks (a TS `frequency` bind requires exactly one imaginary frequency in the parsed log, else `saddle_check_failed`).

Coverage `complete` ⇔ every required stage is `supported`, or `skipped` with a non-empty reason. `pending` and `rejected` are both open gaps. Derived display levels (`structure_supported` / `saddle_supported` / `endpoint_supported` / `thermo_annotated`) are computed from stages only — no one writes them by hand.

## dag_guided workflow

Advance in this order (the harness hard-blocks skipping ahead; error messages name the next step):

1. **User submits a task** → Coordinator is woken.
2. **Initial research**: read skills, search literature / field consensus; dispatch `explorer(a-1)` /
   `researcher(a-3)` when needed. Compute entry points (`submit_compute_job`, `gjf_writer` writes,
   compute-type `ts_guess` modes) are gated until the mechanism is accepted; search/read/mapping stay open.
3. **Propose the mechanism**: `dag_propose_mechanism` with the delivery draft, stage contracts, and rationale.
4. **Supervisor review**: Supervisor is woken (`mechanism_proposed`) and calls `dag_accept_mechanism`.
   Accept unlocks compute; reject sends the draft back with a reason — revise and re-propose.
   The supervisor conclusion is pinned into your context (`[Supervisor]`); to reply, use
   `dag_message_supervisor(message="...")` (Coordinator only).
5. **Work at your own pace**: dispatch `small_mol` / `dft` (etc.) sub-agents or execute yourself.
   Sub-agents run tools and report; they never write the graph.
6. **Review inbox**: each finished delivery-relevant call (`gaussian_log_parser`, `reaction_mapping`,
   `thermo_analysis`, `ts_guess`, plus compute-job completions/failures) lands in the CallReview inbox
   and wakes Supervisor (coalesced). Supervisor binds stages with `dag_review_call`; nothing auto-binds.
7. **Delivery**: only `stop` for delivery after `dag_delivery_report` confirms coverage; if there are gaps, keep
   filling evidence or state partial / ask the user for a waiver.

## dag_record workflow

Same discipline without the Supervisor: the proposal is auto-accepted by the harness on submission, and the
Coordinator binds stages itself with `dag_bind_evidence(tool_call_id, bind_target, stage_kind)` as results
land. Order, success, and deriver checks apply exactly as in guided mode. `dag_accept_mechanism`,
`dag_review_call`, and `dag_set_coverage_contract` are disabled in this mode.

## Proposing the mechanism: dag_propose_mechanism

Coordinator-only. Three arguments:

- `operations`: delivery-only graph operations — `add_node` (occurrence: `node_id`, `label`, `role` =
  reactant/intermediate/product, optional `smiles`), `add_edge` (elementary_step: `edge_id`,
  `source_node_id`, `target_node_id`), plus `update_node` / `update_edge`.
- `stage_contracts`: element id → ordered stage-kind list. Every id must resolve to an element the draft
  itself adds; list order IS the allowed bind order. A TS claim without `ts_opt`+`frequency`, or an IRC claim
  without endpoints/direction/identity, is an incomplete contract.
- `rationale`: why this mechanism (mapping/literature basis), mandatory.

All stages start `pending`; you cannot pre-declare stage states.

## Adjusting an accepted mechanism

- `dag_add_species`: new occurrence (`node_id`, `label`, `role`; optional `smiles`, `required`, `metadata`).
  Set identity at create time, then connect with `dag_add_step`.
- `dag_add_step`: new elementary-step edge between two existing occurrences.
- `dag_update_delivery_element`: `label` / `annotations` / `reason` / `required` / `supersedes` (and
  disposition-only `evidence_level`: `proposed` / `rejected` / `inconclusive`). `role` / `smiles` / stage
  states cannot change in place.

## Reviewing calls: dag_review_call (Supervisor, dag_guided)

One call per pending review: `review_id`, `target_id`, `stage_kind`, `verdict`, optional `reason`:

- `agree` — bind the call's evidence to this stage. The harness resolves the ref from the review's
  `tool_call_id` and enforces order, success, not-a-submit, and deriver checks.
- `disagree` — the evidence does not support the stage (reason required). The stage becomes `rejected`:
  **still owed work**, an open coverage gap — never a disposal.
- `skip` — deliberately abandon the stage (reason required); the only non-success disposal.
- `ignore` — the call is not delivery evidence; no stage change.

One call may support several stages of the same element (an opt+freq log can support `ts_opt` and
`frequency`) — judge each stage on the merits, in order. `ts_guess` output is advisory and never satisfies
`ts_opt`/`frequency`.

## dag_remove_edge

Delivery edge id + **required `rationale`** (deletions stay in the change log). Only Coordinator-side
actors can execute it — the Supervisor is read-only on delivery, so prune requests from a review go
through `dag_message_supervisor` and the Coordinator applies the deletion.

## Inspection

Prefer default `dag_view` (delivery gaps, pending call reviews, recent mutations). `graph_kind=delivery`
returns a compact paginated subgraph (`node_ids` / `status_filter` / `offset`); `graph_kind=process` is
removed and returns a deprecation note. Self-check coverage with `dag_delivery_report` before declaring delivery.

## When a call is rejected

Every rejection is actionable: the error includes the correct format, current state, and next step. Fix as instructed
and resend; you do not need to look up revision numbers or ids again. A `stage_out_of_order` or
`saddle_check_failed` rejection means the contract, not the tool call, is the constraint — bind the missing
earlier stage (or skip it with a reason) first.

Evidence timing is order-sensitive: a `frequency` bind is rejected until `ts_opt` is bound first. Land the
evidence in contract order (or bind the earlier stage in the same pass). Re-running the same tool on the same
unchanged source produces a **duplicate** — an already-queued review is not re-queued; if you are re-submitting
on purpose, say what changed (new log, re-run job). Only post-completion artifacts count: submit the finished
job's parser output, not the `submit_compute_job` call.
