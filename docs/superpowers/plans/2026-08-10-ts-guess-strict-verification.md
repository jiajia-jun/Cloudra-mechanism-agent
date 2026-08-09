# `ts_guess` Strict Verification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an optional, stateless strict mode to `ts_guess(mode="verify")` that proves each partial IRC endpoint lies geometrically between the TS and one of two optimized intermediates without requiring a complete IRC.

**Architecture:** Keep all exploratory modes unchanged. Add small pure geometry helpers in `ts_guess.py`, then compose them inside `_verify`; non-strict verification remains advisory, while strict verification returns human-readable `pass`/`fail`/`inconclusive` verdicts through the existing output schema.

**Tech Stack:** Python 3.11+, Pydantic v2, NumPy, ASE, cclib, pytest/pytest-asyncio.

## Global Constraints

`strict` defaults to `False` and only affects `mode="verify"`.

`scan_parse`, `scan_prepare`, and `interpolate` behavior and outputs must not change.

Strict verification does not require IRC endpoint convergence and does not persist workflow state.

Strict verification accepts optimized intermediate XYZ structures through the existing reactant/product inputs; it does not accept or manage endpoint optimization logs.

No implementation commits: `cloudra/tools/Chemtool/ts_guess.py`, its tests, and the chemistry skill files already contain user-owned uncommitted work. Preserve that work and report only the final diff.

---

### Task 1: Pure IRC endpoint geometry check

**Files:**
- Modify: `cloudra/tools/Chemtool/ts_guess.py`
- Test: `tests/test_ts_guess.py`

**Interfaces:**
- Consumes: atom symbols plus NumPy coordinate arrays for TS, one IRC endpoint, and one optimized intermediate; optional 1-based `watch_pairs`.
- Produces: `_evaluate_endpoint_between(symbols, ts_pos, end_pos, intermediate_pos, watch_pairs) -> dict` with `is_decidable`, `is_between`, `score`, `pairs`, and `details`; `_assign_irc_endpoints(...) -> dict` with `is_decidable`, `is_match`, `assignment`, and `details`.

- [ ] **Step 1: Write failing unit tests for the geometry helper**

Add tests that use a three-atom synthetic reaction coordinate. The TS has `H3` midway between `C1` and `N2`; negative and positive IRC endpoints move it partway toward the corresponding optimized intermediates.

```python
def test_strict_endpoint_between_uses_pair_distances():
    result = _evaluate_endpoint_between(
        ["C", "N", "H"],
        np.array([[0, 0, 0], [0, 0, 2], [0, 0, 1]]),
        np.array([[0, 0, 0], [0, 0, 2], [0, 0, 0.7]]),
        np.array([[0, 0, 0], [0, 0, 2], [0, 0, 0.1]]),
        [[1, 3], [2, 3]],
    )
    assert result["is_decidable"] is True
    assert result["is_between"] is True
```

Add a mirror test whose endpoint moves away from the optimized intermediate and assert `is_between is False`. Add tests for swapped endpoint/intermediate order and for no informative pairs returning `is_decidable is False`.

- [ ] **Step 2: Run the helper tests and verify they fail**

Run: `uv run pytest -q tests/test_ts_guess.py -k 'strict_endpoint or strict_assignment'`

Expected: collection/import failure because `_evaluate_endpoint_between` and `_assign_irc_endpoints` do not exist.

- [ ] **Step 3: Implement pair selection and interval checks**

Add module constants and pure helpers near the existing geometry functions:

```python
_STRICT_PAIR_DELTA_MIN_ANG = 0.15
_STRICT_INTERVAL_TOL_ANG = 0.10
_STRICT_MAX_AUTO_PAIRS = 5

def _evaluate_endpoint_between(symbols, ts_pos, end_pos, intermediate_pos, watch_pairs):
    # Validate equal shapes and 1-based watch-pair bounds.
    # If watch_pairs is empty, rank all pairs by abs(q_intermediate - q_ts),
    # retain at most five with delta >= 0.15 Å.
    # Expand [q_ts, q_intermediate] by 0.10 Å and require q_end inside it.
    # Require ||q_end-q_intermediate|| < ||q_ts-q_intermediate||.
    # Return a finite score used to compare the two endpoint assignments.
```

`_assign_irc_endpoints` must evaluate direct and swapped assignments, accept either one-to-one mapping when both sides are between, choose the lower score if both pass, and return undecidable when either side lacks information.

- [ ] **Step 4: Run the helper tests and verify they pass**

Run: `uv run pytest -q tests/test_ts_guess.py -k 'strict_endpoint or strict_assignment'`

Expected: all selected tests pass.

### Task 2: Integrate `strict` into public verification

**Files:**
- Modify: `cloudra/tools/Chemtool/ts_guess.py`
- Test: `tests/test_ts_guess.py`

**Interfaces:**
- Consumes: `TsGuess_input_schema.strict: bool`, existing `freq_log`, `irc_log`, reactant/product structures, and optional `watch_pairs`.
- Produces: existing `TsGuess_output_schema`; no new state fields. Non-strict positive verdict begins with `candidate`; strict verdict begins with `pass`, `fail`, or `inconclusive`.

- [ ] **Step 1: Write failing public-behavior tests**

Update the existing non-strict positive tests to assert `candidate` rather than `pass`. Add strict tests by monkeypatching `_parse_freq_log` and `gaussian_frames.extract_irc` with deterministic TS/path geometries:

```python
result = await tool.safe_call(TsGuess_input_schema(
    mode="verify",
    strict=True,
    freq_log=str(freq_log),
    irc_log=str(irc_log),
    reactant_text=left_intermediate_xyz,
    product_text=right_intermediate_xyz,
    watch_pairs=[[1, 3], [2, 3]],
), mock_session)
assert result.verdict.startswith("pass")
```

Cover strict missing IRC/intermediates → `inconclusive`, incomplete-but-bidirectional IRC → `pass`, swapped intermediates → `pass`, wrong-direction endpoint → `fail`, element mismatch/no informative coordinates → `inconclusive`, and normally completed zero/multiple-imaginary frequency jobs → `fail`.

- [ ] **Step 2: Run strict verification tests and verify they fail**

Run: `uv run pytest -q tests/test_ts_guess.py -k 'verify or strict'`

Expected: failures because `strict` and the new verdict semantics are absent.

- [ ] **Step 3: Extend schema, frequency geometry parsing, and `_verify`**

Add `strict: bool = False` to `TsGuess_input_schema`. Extend `_parse_freq_log` to return final symbols/coordinates when cclib exposes `atomnos` and `atomcoords`; if unavailable, strict mode may use the `rx=0` IRC frame as the TS geometry. In strict mode:

```python
if n_imag != 1 and freq["converged"]:
    verdict = "fail: ..."
elif required_geometry_or_inputs_are_missing:
    verdict = "inconclusive: ..."
else:
    assignment = _assign_irc_endpoints(...)
    verdict = "pass: ..." if assignment["is_match"] else "fail: ..."
```

Select the farthest valid negative- and positive-reaction-coordinate IRC frames; do not require `forward_converged` or `backward_converged`. Write those frames to the existing endpoint paths. Keep operational file/schema errors as `is_success=False` through `tool_call`.

In non-strict mode retain existing advisory checks but replace a positive `pass` verdict with `candidate`; zero or multiple imaginary frequencies use `unlikely`.

- [ ] **Step 4: Run verification tests and verify they pass**

Run: `uv run pytest -q tests/test_ts_guess.py -k 'verify or strict'`

Expected: all selected tests pass.

### Task 3: Agent-facing wording and regression verification

**Files:**
- Modify: `cloudra/tools/Chemtool/ts_guess.py`
- Modify: `cloudra/skills/dft-calculation/SKILL.md`
- Modify: `cloudra/skills/dft-calculation/references/mechanism-elucidation-sop.md`
- Test: `tests/test_ts_guess.py`
- Test: `tests/test_gaussian_frames.py`

**Interfaces:**
- Consumes: strict semantics implemented in Task 2.
- Produces: tool/schema descriptions that tell the agent strict mode proves path-direction consistency, not absolute TS correctness.

- [ ] **Step 1: Update descriptions without changing exploratory modes**

State that default `verify` is advisory. Document `strict=True` as requiring one imaginary frequency, two usable IRC directions, and two optimized intermediate structures whose pair-distance coordinates bracket the partial IRC endpoints. Explicitly state that incomplete IRC is acceptable and `scan_parse` remains exploratory.

- [ ] **Step 2: Run focused regression tests**

Run: `uv run pytest -q tests/test_ts_guess.py tests/test_gaussian_frames.py`

Expected: all tests pass; warnings from collinear Kabsch alignment are allowed if unchanged.

- [ ] **Step 3: Run chemistry-tool regression tests**

Run: `uv run pytest -q tests/test_conformer_search.py tests/test_ts_guess.py tests/test_electronic_analysis.py tests/test_internal_coordinates.py tests/test_compute.py tests/test_gaussian_frames.py`

Expected: all available tests pass; CREST/xTB integration tests may skip when binaries are unavailable.

- [ ] **Step 4: Inspect the final diff**

Run: `git diff --check` and `git diff -- cloudra/tools/Chemtool/ts_guess.py tests/test_ts_guess.py cloudra/skills/dft-calculation/SKILL.md cloudra/skills/dft-calculation/references/mechanism-elucidation-sop.md`

Expected: no whitespace errors; no changes to `scan_parse`, `scan_prepare`, or `interpolate`; no unrelated user-owned edits reverted.
