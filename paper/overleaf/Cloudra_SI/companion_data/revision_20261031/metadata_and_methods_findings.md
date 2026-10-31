# P2 model metadata, imaginary-mode diagnostics, and conformational search

Distribution copy: local workspace paths use archive-relative or repository-relative source locators. Raw configurations and databases are not bundled.

Read-only source investigation, 31 October 2026. No scientific calculations, rescoring, code changes, or new scientific thresholds were introduced. The FULL archive was read with one successful targeted extraction shared with the case-analysis agents; extracted files remain in `Cloudra-P2-final-20261031/campaign_data/` and are not publication attachments.

## 1. Model and experiment metadata recovered from the FULL P2 archive

Author clarification (31 October 2026): the deployment was **deepseek-v4.1-flash, version 1017** (`deepseek-v4.1-flash1017`). The archived API alias is **deepseek-v4-flash**. The deployment identification comes from the author; the alias, settings, and telemetry below come from the execution archive. Both are recorded separately in `p2_model_metadata.json`.

### Primary source and campaign membership

- Original archive: `Cloudra-P2-final-20261031-FULL.tar.gz` (14 GB compressed).
- Its campaign layout is `Cloudra-P2-final-20261031/campaign_data/cloudra-p2[b|c]-20261025/{guided,record,standard,brief-errors}/r1/`.
- The final 200-run table retains **three P2b runs and 197 P2c runs**. Its `campaign`, `arm`, `task`, and `sandbox` columns identify those runs. The three retained P2b combinations are Guided/D3, Record/D1, and Standard/D3. The original 397-row raw table also contains cancelled P2b attempts and is not a second 397-run benchmark sample.
- Local publication source: `paper/figures/benchmark_p2_20261031/source_data/source_final_scores_per_run.csv`; lighter package overview: `output/Cloudra_Benchmark_Mining_20261031/evidence/source_package_readme.md`.

### Campaign manifests (actual run versions)

Recovered manifests:

- `Cloudra-P2-final-20261031/campaign_data/cloudra-p2b-20261025/MANIFEST.txt`
- `Cloudra-P2-final-20261031/campaign_data/cloudra-p2c-20261025/MANIFEST.txt`

P2b records:

```text
campaign=p2b-formal
started=2026-10-25T18:01:17+08:00
commit_guided=6e89d20c13c29d2036f8be2dd08f421682286d09
commit_record=746c33f0ae0e7c6da3b174b6b3ef039dc59272d1
commit_standard=c7fc94a1299575f4a00d1f33f40865a2cb146636
commit_brief-errors=3b9831bb6465c0f211117dcc0ad0a072b7be0fa3
master_base=53309d0e require-basic-delivery-across-modes
repeats=1
concurrency_per_arm=2 (total 8)
isolation=masked mount namespace v3 (sibling arms masked)
scoring=trajectories saved; scores computed offline
```

P2c records the same four per-arm commits and:

```text
campaign=p2c-resume
started=2026-10-25T22:18:45+08:00
reason=continue remaining tasks after P2b stop; same 8-concurrency config
completed_in_p2b: guided=1 record=1 standard=1 brief-errors=0
```

These are the experiment versions. `70daa5a` is the implementation reference used in the earlier manuscript, while `0961d9ab` and the PR #246/#247 fixes concern later evaluator maintenance. They must not replace the actual campaign commit identifiers above.

### Model configuration and actual call evidence

The four P2b `config.snapshot.yaml` files were recovered directly from the archive. Both configured slots, `llm.coordinator` and `llm.follower`, have the same nonsecret fields:

```yaml
provider: deepseek
model: deepseek-v4-flash
url: https://api.deepseek.com
supports_vision: true
native_search: auto
context_window: 400000
timeout: 300
reasoning_effort: minimal
```

Credentials in the archived files are already redacted; no credentials are included here. The model name and setting are an **archived API identifier and declared request setting**, not a pinned provider weight/build identifier.

Actual P2b Guided runtime telemetry independently confirms the model rather than merely documenting a plan. In `Cloudra-P2-final-20261031/campaign_data/cloudra-p2b-20261025/guided/r1/runtime/runtime-v2.db`, table `events` contains:

- `llm.request_started`: 794 rows, all `data.model = deepseek-v4-flash`;
- `llm.completed`: 806 rows, all `data.model = deepseek-v4-flash`.

These event counts include the retained runtime archive's various LLM activities and are not counts of benchmark runs or independently repeated tasks. `run.started` records the JavaScript invocation protocol and temperature 1.0; a representative spawned-agent setting carries `max_tokens=32768`. Model settings can be inherited from the frozen coordinator/follower configuration when the per-session `model` field is empty; an empty session field is not an unknown model once the applicable frozen slot and actual call records are present.

All four P2c configurations have now been recovered and checked. The eight configuration files (four P2b and four P2c) agree exactly on the nonsecret coordinator/follower model settings above. All eight runtime databases were cross-checked for their request/completion model identifiers, as summarized below.

### Call route supported by the campaign-era source

At campaign base `53309d0e`, `cloudra/runtime_v2/adapters.py` fills absent model/base URL/reasoning effort from the coordinator/follower configuration. The request includes `model`, messages, temperature, token budget, `stream=True`, and the configured `reasoning_effort`. It uses the chat-completions client unless the selected native-search adapter explicitly requests the Responses transport.

The campaign-era `cloudra/infra/web_search_native.py` deliberately skips the DeepSeek Responses adapter in `native_search="auto"`; DeepSeek Responses requires explicit `native_search="deepseek"`. Therefore the recovered configuration (`url=https://api.deepseek.com`, `native_search=auto`) selects the official DeepSeek API through the OpenAI-compatible chat-completions route. This is supported by the archived configuration plus the documented campaign-era routing implementation; it is not an archived HTTP packet capture. Do not invent an exact provider-side immutable model snapshot or undocumented sampling parameter.

## 2. Imaginary-mode alignment: the value exists, but is advisory

### Current and described implementation

- `cloudra/tools/Chemtool/ts_guess.py:71`: `_IMAG_MODE_WATCH_RATIO = 0.5`.
- The same constant and advisory wording exist both at campaign base `53309d0e` and in the manuscript's cited implementation `70daa5a` (checked with `git show <commit>:cloudra/tools/Chemtool/ts_guess.py`).
- `cloudra/tools/Chemtool/ts_guess.py:1138-1286`: `_assess_imag_mode_alignment` computes relative displacement magnitudes, selects the lowest-frequency imaginary mode, and compares the largest monitored-pair magnitude to the global largest pair magnitude.

The dimensionless diagnostic is

\[
\eta=\frac{\max_{(i,j)\in W}\|u_i-u_j\|}{\max_{i<j}\|u_i-u_j\|}.
\]

The configured comparison ratio is **0.5**, not an unknown tunable `eta_threshold`. The implementation treats equality conservatively when the global maximum pair is not among the monitored pairs: that branch requires the monitored maximum to be strictly greater than the 0.5 ratio. A monitored global-maximum pair is aligned. Missing displacement data produces `missing`; for a nonbonded dominant pair in a torsion/angle-dominated mode, the diagnosis can be `undecidable` rather than a binary reaction-mode rejection.

This diagnostic uses the norm of the relative displacements, not their projection onto the bond direction. It should be called a reaction-center participation/alignment diagnostic. A distinct summary in `cloudra/tools/core/mode_analysis.py:17-117` reports actual bond-direction projections `|(u_i-u_j) dot rhat_ij|`, unweighted squared-displacement atom fractions, and monitored-pair projection fractions. That summary explicitly does not establish qualification by itself.

### Acceptance behavior and wording that should change

`cloudra/tools/Chemtool/ts_guess.py:2450-2468` appends the exact warning:

> Imaginary-mode alignment is advisory; strict verification uses actual IRC endpoint proof.

After recording this warning, the strict branch calls `_strict_path_verdict` rather than turning the alignment flag into a failure. `cloudra/tools/core/ts_process.py:1745-1773` records the frequency analysis “for Agent judgement; no additional scientific qualification threshold”; `ts_process.py:2602-2617` blocks IRC admission on missing frequency evidence or an imaginary-frequency count other than one, not on the alignment warning.

Accordingly, the main-text phrase grouping `eta < eta_thresh` with physical acceptance defects needs correction. A numerical eta diagnostic can help detect spectator motion, but it is not an extra hard acceptance gate that can veto a verified same-TS bidirectional IRC/endpoint chain.

### Suggested English insertion

> The reaction-center participation ratio, \(\eta=\max_{(i,j)\in W}\|u_i-u_j\|/\max_{i<j}\|u_i-u_j\|\), is reported with a diagnostic comparison ratio of 0.5. The resulting alignment flag is advisory; missing or geometrically undecidable modes remain explicitly identified. Scientific acceptance is determined by the first-order-saddle requirement and the same-TS bidirectional IRC–endpoint optimization/frequency evidence, rather than by this diagnostic flag.

For the diagnostics paragraph:

> Frequency-mode participation and geometric interval checks provide diagnostic warnings that guide revision. Native calculation status, stationary-point curvature, and the required IRC/endpoint evidence determine scientific acceptance.

## 3. CREST is an available search tool; it is not the default placement sampler

### Public tool and dispatch

`cloudra/tools/registry.py:98-105` registers `conformer_search` for the scientific roles. In `cloudra/tools/Chemtool/conformer_search.py:208-217`, its actual public schema contains:

```python
backend: Literal["rdkit", "crest"] = Field(default="rdkit", ...)
mode: Literal["conformers", "nci", "qcg", "protonate", "deprotonate", "tautomerize"] = Field(default="conformers", ...)
```

The same `rdkit`/`conformers` defaults are present at campaign base `53309d0e`. The RDKit route uses ETKDGv3 embedding and force-field relaxation. The CREST route invokes the external executable with default GFN2-xTB and `--quick`; supported modes include ordinary conformer sampling, noncovalent-complex sampling (`--nci`), quantum cluster growth, and protomer/tautomer exploration. In `conformer_search.py:1287-1314`, declared ring/distance guidance dispatches through the shared guided-search core, with backend selection retained. Otherwise `backend="crest"` dispatches to `_run_crest`.

Relevant native command construction is in `cloudra/tools/core/crest_runner.py:225-263`; charge and multiplicity are explicitly passed as `--chrg` and `--uhf=multiplicity-1`. Search artifacts, versions, command and output paths are persistent. A returned ensemble is a candidate set, not proof of an electronic-structure minimum or TS/IRC validity. The current CREST interface explicitly declines a declared open-shell singlet rather than treating `--uhf 0` as a broken-symmetry calculation.

### Default multicomponent preorganization

The paper's default 32-orientation, up-to-eight-guided-placement scheme is the separate topology-aware multicomponent assembly/preorganization route. In `cloudra/tools/core/complex_assembly.py:84-113`, the approved defaults are:

- 32 Fibonacci-sphere relative orientations;
- minimum interfragment separation 1.0 Å;
- up to eight reaction-center candidates;
- 1.7 vdW contact multiplier;
- 6.0 kcal/mol candidate energy window;
- 0.5 Å heavy-atom RMSD clustering;
- 2000 relaxation iterations per stage and MMFF94 constraint force constant 100.0.

`complex_assembly.py:488-489` explicitly states that rigid orientation sampling is deterministic (Fibonacci directions) and independent of the random seed; the seed still affects component conformer embedding. `cloudra/tools/core/preorganization.py:771-834` first generates guided single- or multicomponent seeds and optionally passes them to CREST when that backend is requested.

Thus, adding a sentence acknowledging the CREST entry point is accurate. Claiming that all runs underwent exhaustive CREST sampling, or that the 32-orientation default itself constitutes exhaustive conformer exploration, would require the individual execution records. No claim of universal campaign CREST use is made in this investigation.

### Suggested English insertion

> Cloudra also exposes a conformer-search tool with RDKit and external CREST backends. The default preorganization described here uses topology-aware rigid placements, guided MMFF94 relaxation, and clustering; CREST can be requested for additional conformer or noncovalent-complex sampling. Candidate generation is followed by the task-specific quantum-chemical optimization and physical validation requirements.

Suggested SI detail:

> For the external CREST route, the interface records the native command, software-version output, returned structures, and charge/spin settings. The default search uses GFN2-xTB with the quick setting; an ensemble returned by the search is treated as candidate geometries and does not independently establish stationary-point or pathway acceptance.

## 4. Completed all-arm P2 cross-check

All counts below are runtime telemetry events, not benchmark run counts. P2b includes cancelled attempts as well as its three retained runs; the final analysis still uses only three P2b and 197 P2c task/configuration records. The frozen configuration and actual model identifier checks are concordant for every arm.

|Campaign|Arm|Request-start model / events|Completed model / events|Run-start temperatures|Spawned-agent token budget|
|---|---|---|---|---|---|
|cloudra-p2b-20261025|brief-errors|deepseek-v4-flash: 872|deepseek-v4-flash: 880|1.0: 112|32768: 7|
|cloudra-p2b-20261025|guided|deepseek-v4-flash: 794|deepseek-v4-flash: 806|1.0: 65|32768: 11|
|cloudra-p2b-20261025|record|deepseek-v4-flash: 420|deepseek-v4-flash: 425|1.0: 48|32768: 5|
|cloudra-p2b-20261025|standard|deepseek-v4-flash: 645|deepseek-v4-flash: 651|1.0: 95|32768: 6|
|cloudra-p2c-20261025|brief-errors|deepseek-v4-flash: 35917|deepseek-v4-flash: 36224|1.0: 4187|32768: 203|
|cloudra-p2c-20261025|guided|deepseek-v4-flash: 35430|deepseek-v4-flash: 35861|1.0: 3917|32768: 307|
|cloudra-p2c-20261025|record|deepseek-v4-flash: 8559|deepseek-v4-flash: 8648|1.0: 835|32768: 84|
|cloudra-p2c-20261025|standard|deepseek-v4-flash: 8651|deepseek-v4-flash: 8747|1.0: 841|32768: 88|

### Manuscript-ready P2 model paragraph

> The full-benchmark study used the DeepSeek API model identifier `deepseek-v4-flash` through `https://api.deepseek.com` in all four workflow configurations. Frozen coordinator and follower configurations set `reasoning_effort=minimal` and a 400,000-token context window; the archived runtime records use temperature 1.0. The runtime invoked the model through the streaming OpenAI-compatible chat-completions route, with the JavaScript tool-invocation protocol. The same model identifier is recorded in the request-start and completion telemetry of all four arms in both P2b and P2c. The final 200-run set consists of three completed P2b runs and 197 resumed P2c runs.

The archived model identifier is a provider API name. The author separately identified the deployment as deepseek-v4.1-flash, version 1017; the configuration and telemetry retain the archived alias deepseek-v4-flash. The configured context window is a harness setting, not an independently measured context-limit benchmark. Include a token budget only as the recorded runtime setting; it is not the consumed token count.

### SI version table wording

> P2b started on 25 October 2026 at 18:01:17 UTC+8, and P2c resumed the remaining tasks at 22:18:45 UTC+8. Both campaigns used the same per-configuration commits: Guided `6e89d20c`, Record `746c33f0`, Standard `c7fc94a1`, and Brief-errors `3b9831bb`, based on master `53309d0e`. There were two concurrent task runs per configuration, eight in total. Experiment execution, later evaluator fixes, and publication-table reproduction are identified by their own versions.

### Extraction note (internal only)

The direct Python 3.14 `tarfile` `r|gz` path stalled when this concatenated-gzip archive crossed its first member, consuming CPU in `zlib` unconsumed-input copying. Only the self-owned archive reader was stopped; no Cloudra or quantum-chemical process was touched. A `gzip.GzipFile` reader feeding `tarfile` `r|` with zero-block continuation scanned 48 GB of expanded tar data in 45.7 s and selected 10,729 files (5.956GB), including only the requested five chemistry cases, Record/IA5, Brief/IC3 and campaign metadata/databases. Files already fully recovered were retained. The extraction manifest remains at `Cloudra-P2-final-20261031/campaign_data/selected_extraction_manifest.json`; these raw artifacts are not placed in Git.
