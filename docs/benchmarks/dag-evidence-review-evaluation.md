# DAG Evidence & Scientific Review Evaluation

Status: **offline implementation checkpoint**. This document records the
planned controlled evaluation for the DAG evidence/review work. Real paired
benchmark runs require the separately authorized compute budget and are not
claimed as complete here.

## Reproducibility metadata

Each controlled run should record:
- code SHA and workspace patch hash
- model/sampling parameters
- method policy
- task id
- resource caps
- prompt/skill content hashes
- contract version
- time window

## Correctness scenarios

The Task 0 fixture classes are the fixed gate:
1. constrained Opt + single imaginary frequency
2. wrong product identity mismatch
3. symmetric mapping ambiguity
4. converged short IRC
5. out-of-order evidence permutation
6. mid-swarm alert

## Fault injection coverage

- request saved then process crash
- review interrupted
- decision saved before notification loss
- Hub consumption before restart
- launch group spawn crash
- evidence file unavailable

## Success criteria

- No mis-acceptance or evidence loss in fixed cases
- Ordinary evidence does not trigger automatic review
- Non-blocking dispatch does not exceed concurrency limits
- Partial/method-limited exits require approval
- Benchmark scoring formulas remain unchanged
