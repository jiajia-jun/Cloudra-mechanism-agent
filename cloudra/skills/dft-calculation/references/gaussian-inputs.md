# Gaussian inputs for mechanism work

Use with the mechanism SOP; these are Gaussian routes, not ORCA syntax. Set `engine="gaussian"`, one-token `method`, and `basis_set` explicitly, and submit with the same `job_type`. Select a method suited to the user's current requirements and budget. Only active Benchmark projects apply their actual task MethodPolicy; ordinary research projects have no default method/basis whitelist. Examples do not establish method restrictions or override the user's requirements.

## 1. Task recipes

| Purpose | `task_type` | Additional input / acceptance |
| --- | --- | --- |
| Minimum | `[{"opt":null},{"freq":null}]` | No frozen coordinates; actual convergence, minimum frequencies, identity |
| TS from a prepared XYZ | `[{"opt":"ts,calcfc"},{"freq":null}]` | Initial force constants; full stationarity and one relevant imaginary mode |
| Frequency at a finished geometry | `[{"freq":null}]` | Read its actual optimized XYZ; same geometry-level method/conditions |
| Short IRC with a newly calculated Hessian | `[{"irc":"calcfc"}]` | Both directions by default; choose any path-length setting for the task's evidence need, then optimize outer frames and check minima, identity and direction |
| Single point | `[]` | Explicit empty list prevents the default optimization |

`NoEigenTest` suppresses an optimizer curvature test; it does not establish that a saddle is valid — it transfers all saddle validation to the final freq, which then becomes mandatory. Add it only when a diagnosed early curvature rejection warrants continuing from a credible guess. `MaxStep=10` or a tighter grid may address a specific step-size/numerical problem; do not stack them onto every failed job. **QST2/QST3 are banned** (synchronous-transit interpolation fails systematically and has no path correction); the ceiling is mapped interpolation/NEB, with relaxed scans as the workhorse — see `ts-search-playbook.md`.

## 2. Complete TS example

An illustrative closed-shell neutral DFT candidate, with a chosen gas-phase method:

```json
{
  "engine": "gaussian",
  "source_type": "xyz_file",
  "source_value": "/work/step/candidate.xyz",
  "method": "b3lyp",
  "basis_set": "def2svp",
  "task_type": [{"opt": "ts,calcfc"}, {"freq": null}],
  "keywords": "empiricaldispersion=gd3bj scf=tight int=ultrafine",
  "charge": 0,
  "multiplicity": 1,
  "nproc": 4,
  "mem": "3GB",
  "title": "TS candidate; identity and connectivity pending",
  "chk_name": "/work/step/ts.chk",
  "output_path": "/work/step/ts.gjf"
}
```

The route should contain `opt=(ts,calcfc) freq b3lyp/def2svp` and the explicit numerical/dispersion settings. Read the resulting file to verify charge, multiplicity, resource headers and absence of old modredundant freezes. Use actual candidate coordinates: generating from reactant SMILES starts from a minimum, not the TS region.

Submit with `submit_compute_job`, `job_type="gaussian"`, `memory_mb=4096`, `is_async=true`, matching CPU allocation to the workflow type: for high-throughput batches (conformer sweeps, scan points, batch SP), allocate `cpus=2~4` to maximize aggregate throughput; for sequential blocking critical paths (reaction mechanism paths where downstream steps await this geometry/TS), allocate up to `cpus=32` (within node capacity) to rapidly unblock progress. Keep `%chk` in the input directory; Gaussian scratch is removed after completion. Separate jobs need separate basenames/checkpoints unless intentionally restarting.

## 3. Scans and constraints

**TS-seed hierarchy:** `ts_prepare` first; the relaxed scan below is the agent-side fallback when the process cannot take the case. Either way, read real atom indices with `internal_coordinates` first — do not start from a SMILES minimum and hope OptTS finds a saddle.

Use `ts_guess mode=scan_prepare` with `engine="gaussian"`, `input_path`, `scans`, `method="b3lyp"`, `basis_set="def2svp"`, `keywords`, `charge`, `multiplicity`, `nproc`, `mem` and `output_path`. These electronic-state and resource fields have the same meanings as `qm_input_writer`; coordinate-only XYZ input requires an explicit total charge. `mem` is total job memory (for example `"4GB"`), and the shared writer emits `%mem` and `%nproc`. The checkpoint defaults to the output file's basename with `.chk` in the same directory. Match the scheduler reservation to the generated resources. Each scan entry has `coord_type`, 1-based `atoms`, `scan_end` and `scan_steps`. **Omit `scan_start` for Gaussian** unless it matches the actual input coordinate: a mismatch is rejected, and the generator does not move the input geometry. To start elsewhere, prepare that geometry using the supported structure tools first. The tool handles modredundant formatting and supports one or two scan coordinates; two coordinates form an independent grid with `scan_mode` omitted, from which no TS candidate is selected automatically. Native trailing settings use `end_setting`; ORCA blocks do not belong in a Gaussian configuration. For an existing run, supply `run_id` and scan intent; the run supplies its charge, multiplicity and execution resources. Returned configuration describes a prepared input, not a completed scan.

For a relaxed scan, unscanned degrees of freedom optimize at each point. The resulting constrained maximum is a seed. Extract it, build a fresh TS job, and remove `Opt=ModRedundant`/freeze lines. Do not use the scan's convergence to claim an unconstrained stationary point. Read scan notes and structural continuity, not only the maximum energy.

## 4. Frequencies, checkpoints and IRC

A separate frequency job uses the final XYZ and the geometry method/settings. Reuse a valid, same-geometry frequency result instead of recomputing it to change a filename or stage order. Check `log_parser` for actual optimization convergence and use the normal-mode displacements for reaction assignment.

With a compatible same-geometry Hessian in the checkpoint, IRC can use `RCFC` instead of recomputing `CalcFC`; verify the checkpoint contains those force constants. Native checkpoint-only routes using `Geom=AllCheck`/`Guess=Read` have a different input layout. **The current writer always emits title, charge/multiplicity and coordinates**, so do not simply append `Geom=AllCheck` to a normal writer input. Use an explicitly supported checkpoint workflow or stay with explicit XYZ and `CalcFC`. A checkpoint holding only geometry does not contain a vibrational analysis.

The example leaves `MaxPoints` unspecified; do not accept an engine default blindly. If setting it, choose it for the current direction evidence, path topology and coupling, and compute cost; there is no universal point count. Keep native convergence tests enabled and report partial paths honestly. After the short bidirectional run, optimize both outer frames without constraints at the same agreed model; confirm minimum frequencies, endpoint identities and direction. Extend only if partial geometry still cannot resolve direction or identity, not merely because a chosen ceiling was reached or the IRC convergence flag is absent. A short IRC alone does not prove the full path or dynamics. Use an alternative IRC algorithm such as `LQA` only for a diagnosed integration problem. The SOP explains `ts_guess strict=True` and independent endpoint mapping.

Gaussian documentation entry points: [Opt](https://gaussian.com/opt/), [IRC](https://gaussian.com/irc/), [input layout](https://gaussian.com/input/). Check the installed release's manual for options unavailable through the shared writer.

## 5. External MLIP variant

Use `method="external"`, `external_program="mace"` (or the installed allowed command), and `basis_set=""`; omit DFT-specific dispersion, SCF, integration-grid and solvent keywords. The writer emits a single `external="..."` route and no DFT method/basis. Put command arguments inside `external_program`; `external_params` is ORCA-only.

External Hessian support depends on the wrapper. Check whether it returns the derivative order Gaussian requests; an energy/gradient-only wrapper needs a supported numerical-Hessian workflow. Do not assume a completed optimization proves `CalcFC`/frequency/IRC support. Read `mlip-gaussian-external.md` for deployment and method limits.
