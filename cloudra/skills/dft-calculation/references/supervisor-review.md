# Supervisor review reference

How the scientific Supervisor adjudicates claims about molecular mechanism
calculations. Load this reference at the start of a review and keep using the
same loaded version for the whole review.

## Order of one review

1. State the question, the allowed methods, the requested quantity and its
   reference (reactants, central complex, another electronic state), and what
   must be decided this turn.
2. Read the evidence package and the deterministic checks first. Open raw
   inputs, logs and geometries only where a question is actually open; cite
   full paths and hashes when a reading matters.
3. For unfamiliar methods, input options, or failure patterns, search AgentHub
   before judging. Record what the library says about applicability; a
   knowledge entry is not project-verified evidence by itself.
4. Classify every blocker into exactly one bucket: input/tool fault, local
   search failure, method applicability limit, or evidence already sufficient.
5. Decide with evidence references. A demand for more work names the missing
   evidence, an executable next action, and the new information it adds.

## Judgment table

| Scenario | Judgment |
| --- | --- |
| Constrained Opt + one imaginary frequency | Check stationarity, constraint release, and mode character first; a single imaginary frequency at a constrained point never authorizes a TS claim. |
| OptTS repeatedly returns to the same basin | Read the attempt history; one purposeful change of conformer / coordinate / scan beats more iterations. |
| Monotonic 1-D scan | No peak along this coordinate; not a proof of barrierlessness. |
| Short bidirectional IRC, including a partial native path | Check both outer-frame unconstrained optimizations at the same agreed model, minimum frequencies, endpoint identities, and directions. Keep native convergence status visible; do not demand extension solely for a step ceiling or unconverged flag. |
| Endpoint identity mismatch | Counterevidence against the path; do not refine the wrong product into the target's name. |
| MLIP lacks the requested diagnostic | Check applicability and available evidence; do not demand impossible outputs or veto by method name. |
| Partial / method-limited exit requested | Distinguish "not found yet" from "not reliably answerable with allowed methods"; approve only with a scoped, cited reason. |
| Evidence already sufficient | Credit correct reuse; no recomputation for stage-slot bookkeeping. |

## What a contract requires (and what it must not add)

| Question | Contract focus | Do not mechanically add |
| --- | --- | --- |
| Structure / stable intermediate | Geometry provenance, minimum criteria, species identity, method applicability | IRC when no reaction channel is claimed |
| TS / connectivity | Stationary-point evidence, relevant imaginary mode, both path sides, optimized endpoint minima, identities and direction | Extending a partial path solely to reach intrinsic IRC convergence or a point count |
| Electronic barrier | The above plus same-footing electronic energy difference and reference state | RRHO free-energy corrections |
| Free-energy barrier | Temperature, standard state, thermal corrections and their applicability | Mixing references or passing ΔE off as ΔG |
| Selectivity | Two competing channels with comparable references and statistics | Claiming ΔΔG from a single TS |
| Method cannot be trusted | The specific conflict between the requested quantity and method capability, known applicability limits, existing diagnostics and gaps | Forcing wavefunction diagnostics an MLIP cannot emit; declaring a method dead after one non-convergence |

## Attempt records

Attempts in the workspace / evidence package follow: hypothesis, action,
result, and why the next attempt adds new information. A repetition count is a
trigger to re-diagnose, never a standalone refusal threshold.
