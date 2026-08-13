---
name: dag-operations
description: How to use dag_graph in dag_record/dag_guided sessions — design the mechanism (mutate), bind evidence to delivery nodes (bind_evidence), report status, and what to do when a call is rejected. Use when composing dag_graph calls.
---

# dag_graph intent handbook

The intents you use most in a DAG session: **build the skeleton, design the mechanism, bind evidence, leave a note for Supervisor, and (optionally) report status**.
Revision numbers, evidence ids, and internal process-graph bookkeeping are managed by the system; you do not need to track them.

- `init_from_template`: first step at kickoff; seeds the mechanism-study skeleton when both graphs are empty.
- `mutate`: the only entry point for designing the mechanism (see below).
- `bind_evidence`: attach a successful calculation result to a mechanism-graph element (see below).
- `message_supervisor`: Coordinator leaves a note for Supervisor (nudge scheduling, explain a blocker, request review). Does not change the graph. Not available to sub-agents.
- `update_node` (one `mutate` op): change **allowed fields** of an existing node (see below); on process, mainly to add status notes on nodes assigned to you.
- `delivery_report` / `view`: delivery self-check and graph inspection.

## dag_guided workflow

Advance in this order (the harness hard-blocks skipping ahead; error messages name the next step):

1. **User submits a task** → Coordinator is woken.
2. **Initial research**: read skills, search literature / field consensus; dispatch `explorer(a-1)` /
   `researcher(a-3)` when needed. Writing files, starting calculations, and dispatching compute sub-agents are still blocked at this stage.
3. **Submit a preliminary mechanism**: `mutate` writes the hypothesis into delivery (not template placeholders); rationale
   must spell out the computational plan.
4. **Supervisor review and scheduling**: after a mechanism change is accepted, Supervisor is woken automatically and
   schedules non-template planned work on process (it need not add a new node every time; if existing coverage already
   schedules the work, it may only comment).
   The supervisor conclusion is pinned into your context (`[Supervisor]`); when Coordinator needs to reply, use
   `dag_graph(action="message_supervisor", message="...")` (not available to sub-agents).
5. **Decompose from process**: look at **frontier** in the default `view` projection (planned nodes whose
   dependencies are satisfied and whose status is `proposed` or `ready` — do not rely only on
   `status_filter=ready`). Dispatch `small_mol` / `dft` (etc.) sub-agents by node `assignee` (legal ids such as `a-4`),
   or execute already-scheduled tool-level work yourself.
6. **Evidence return**: tool results such as `log_parser` are maintained on the graph by the harness; if something
   unexpected happens (calculate-before-graph, a missed binding), claim it yourself with `bind_evidence`.
7. **Delivery**: only `stop` for delivery after `delivery_report` confirms coverage; if there are gaps, keep
   filling evidence or state partial / ask the user for a waiver.

Any substantive operation is blocked on an empty graph — `init_from_template` first (or `mutate` to add nodes).
The template skeleton alone does not count as “mechanism submitted” or “Supervisor has scheduled work”.

## Designing the mechanism: mutate

Each operation is a named command discriminated by `op`; arguments are explicit schema fields (errors on a bad shape
include the correct shape). A batch is applied in order, validated as a whole, and committed atomically; edges may
reference nodes created earlier in the same batch. On rejection, the error includes the correct format and the next
step; fix as instructed and resend the same batch of operations.

Call shape: `dag_graph(action="mutate", rationale="...", operations=[...])`.
`operations` must be an **array of objects** (do not wrap the whole JSON as a string).

### add_node vs update_node (easy to mix up)

| | `add_node` | `update_node` |
|---|---|---|
| Use | **Create** a node that does not yet exist | **Change some fields** of an existing node |
| Payload | nested full `node: {...}` | top-level `node_id` + partial `changes: {...}` |
| `role` / `smiles` / `metadata` / `assignee` / `node_type` | written once into `node` at creation | **cannot** be changed (raises `model update exceeds its mutable fields`) |
| Template placeholders `occ_reactants` / `occ_products` | already exist → do not add the same id again | only change `label` / `annotations` / `reason` etc.; express species SMILES with a **new** `add_node`, or put SMILES in `annotations` |

**Fields writable in `changes`** (model side): `label`, `annotations`, `reason`, `blocked_reason`,
`status`, `priority`, `evidence_level`, `required`, `supersedes`.
For `evidence_level` the model may only set `proposed` / `rejected` / `inconclusive` (higher levels are derived from bound evidence).

### Example schema (write a full delivery mechanism in one batch)

Correct shape for “relabel template placeholders + add an intermediate + two elementary-step edges” (replace ids with your mechanism):

```json
{
  "action": "mutate",
  "rationale": "Brief mechanism hypothesis and computational plan (level; TS/IRC/endpoint checks per step, etc.)",
  "operations": [
    {
      "op": "update_node",
      "graph": "delivery",
      "node_id": "occ_reactants",
      "changes": {
        "label": "ethylene + ozone",
        "annotations": "smiles refs: C=C ; [O-][O+]=O"
      }
    },
    {
      "op": "update_node",
      "graph": "delivery",
      "node_id": "occ_products",
      "changes": {
        "label": "Criegee intermediate + formaldehyde",
        "annotations": "smiles refs: C=[O+][O-] ; C=O"
      }
    },
    {
      "op": "add_node",
      "graph": "delivery",
      "node": {
        "node_id": "occ_poz",
        "node_type": "occurrence",
        "label": "primary ozonide (POZ)",
        "role": "intermediate",
        "smiles": "C1COOO1",
        "evidence_level": "proposed"
      }
    },
    {
      "op": "add_edge",
      "graph": "delivery",
      "edge": {
        "edge_id": "e_step1",
        "edge_type": "elementary_step",
        "source_node_id": "occ_reactants",
        "target_node_id": "occ_poz",
        "label": "cycloaddition → POZ",
        "evidence_level": "proposed"
      }
    },
    {
      "op": "add_edge",
      "graph": "delivery",
      "edge": {
        "edge_id": "e_step2",
        "edge_type": "elementary_step",
        "source_node_id": "occ_poz",
        "target_node_id": "occ_products",
        "label": "cleavage → Criegee + HCHO",
        "evidence_level": "proposed"
      }
    }
  ]
}
```

### Wrong shapes (do not write these)

```json
{"op": "add_node", "graph": "delivery", "node_id": "occ_poz", "label": "...", "smiles": "..."}
```
↑ Missing nested `node`; flattening fields to the top level raises `Field required: node` / `graph`.

```json
{"op": "update_node", "graph": "delivery", "node_id": "occ_reactants",
 "changes": {"smiles": "C=C", "role": "reactant"}}
```
↑ `smiles`/`role` are not in the updatable set; template-node roles are fixed. Put species info in `label`/`annotations`, or `add_node` a new occurrence that carries smiles.

```json
{"op": "update_node", "graph": "delivery", "node": {"node_id": "occ_poz", "label": "..."}}
```
↑ `update_node` has no `node` field; use `node_id` + `changes`.

### add_node

`{"op": "add_node", "graph": "delivery", "node": {...}}`: `node` is a complete node object;
`node_id` / `node_type` / `label` are required; conventional attributes (`role`, `smiles`, `evidence_level`,
etc.) are named fields; unlisted custom attributes go in `metadata` (writable only at creation).

- delivery: `node_type="occurrence"`,
  `role="reactant"|"intermediate"|"product"`, `evidence_level="proposed"`.

### add_edge

`{"op": "add_edge", "graph": "delivery", "edge": {...}}`: `edge` is a complete edge object
(`edge_id` / `source_node_id` / `target_node_id` / `edge_type` required, `label` optional);
both endpoints must already exist (or have been created earlier in this batch).
delivery: `edge_type="elementary_step"`, `evidence_level="proposed"`.

### remove_edge

`{"op": "remove_edge", "graph": ..., "edge_id": ...}`. Allowed on both graphs, but
**the batch must include a rationale** (deletions stay in the change log for audit).
Process-graph edge removals are executed after Supervisor review — use rationale to make the case.

### update_node / update_edge (process status reports)

On process, only update nodes whose **`assignee` is you**, for example:

```json
{
  "op": "update_node",
  "graph": "process",
  "node_id": "p_ts_search_step1",
  "changes": {
    "status": "blocked",
    "blocked_reason": "No reasonable TS guess; need a relaxed scan first",
    "reason": "Wait for scan results before Opt=TS"
  }
}
```

Writing someone else's node or structural fields is rejected — the error names the current assignee and a suggested next step.

## Binding evidence: bind_evidence

Claim a calculation that “already existed before the plan” or that just finished as evidence for a mechanism-graph element:

```json
{"action": "bind_evidence",
 "tool_call_id": "<id of that tool call, or an observed_ node id>",
 "bind_target": "<delivery node or edge id>",
 "evidence_role": "<evidence role>"}
```

The harness resolves the evidence registered for that call, checks that the calculation actually succeeded, re-runs
deterministic derivation to upgrade `evidence_level`, and wakes Supervisor for review (Supervisor may veto; a veto
notifies you by event).
`evidence_role` vocabulary:

- `intermediate_optimization` (intermediate optimization; 0 imaginary frequencies → structure_supported)
- `ts_optimization_frequency` (TS optimization + frequency; exactly 1 imaginary frequency → saddle_supported)
- `short_irc`
- `endpoint_a_optimization` / `endpoint_b_optimization`
- `endpoint_direction_check` (ts_guess strict)
- `endpoint_identity_match` (reaction_mapping)
- `thermochemistry` (thermo_analysis)

## Reporting status (optional fallback)

Node success/failure and evidence return are handled automatically by the harness. When you need extra notes, use
`update_node` on process nodes whose `assignee` equals your agent id to write `status`/`reason`/`blocked_reason`/
`annotations`. Writing someone else's node or structural operations is rejected — the error tells you the node's
current assignee and a suggested approach.

## When a call is rejected

Every rejection is actionable: the error includes the correct format, current state, and next step. Fix as instructed
and resend; you do not need to look up revision numbers or ids again.
