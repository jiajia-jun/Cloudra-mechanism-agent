# ORCA inputs for mechanism work

Use with the mechanism SOP. These recipes target ORCA 6.1 and the current Cloudra writer; check the installed version before using additional native options. Paths and the method/model are examples, not deployment defaults. Read generated inputs before submission.

## 1. What the writer actually translates

| Intent | `qm_input_writer` arguments | Expected ORCA content |
| --- | --- | --- |
| Minimum optimization | `task_type=[{"opt":null}]` | `Opt` |
| TS optimization | `task_type=[{"opt":"ts"}]` | `OptTS` |
| Analytical frequencies, when supported | `task_type=[{"freq":null}]` | `Freq` |
| Numerical frequencies | `task_type=[{"freq":null}]`, `frequency_mode="numeric"` | `NumFreq`, no `Opt` or `Freq` |
| IRC | `task_type=[{"irc":null}]`, native `%irc` in `orca_blocks` | `IRC` and explicit IRC settings |
| Single point | `task_type=[{"sp":null}]` | `SP`; no geometry optimization |
| External energy/gradient provider | `method="ExtOpt"`, `basis_set=""`, `external_program`, `external_params` | `ExtOpt` + `%method ProgExt/Ext_Params`; no DFT method/basis |

The writer preserves explicit native options and returns model-visible `warnings` for questionable, conflicting or unrecognized parameters. Gaussian sub-options on an ORCA task are retained with advice about native alternatives; unknown task keys are retained without guessing a single-point task. No `Calc_Hess`, `Direction`, `InitHess` or `Hess_Filename` setting is added automatically. Put explicitly chosen TS Hessian control in `orca_blocks`; `keywords` goes on the `!` line. Supply explicit `engine`, `method` and `basis_set`, including `""` when there is no basis. A standalone frequency/SP is declared explicitly (`[{"freq":null}]` / `[{"sp":null}]`), never inferred from an empty task list. Successful writes return `interpreted_intent` re-inspected from the generated text, `warnings`, an empty `unapplied_options`, and the generation path. Actual renderer data loss, required structural fields, file integrity and resource capacity remain errors; writing an input does not verify scientific evidence.

`end_setting` is a Gaussian field; on ORCA its text is preserved after the coordinate block with a warning. Native ORCA constraints/scans belong in `orca_blocks`. A non-default `title` becomes an ORCA `#` comment; SMILES sources add an `expected_smiles:` comment marking a user-declared expectation — never label an unverified structure as identity-matched. Add any input annotation before submission. Bind the original native log through DAG and the delivery's `properties.evidence_log`; never append annotations to or rewrite a completed evidence log. `mem` is the job total; ORCA `%maxcore` is written as integer MB per core (`mem/nproc`) without a minimum-memory override; fractional conversion produces a warning. Match the scheduler reservation to the generated resources.

## 2. Complete external TS example

Assume a checked singlet anion candidate and an installed external program/model. Use the actual candidate XYZ, not a new SMILES embedding. A fresh input avoids inheriting scan constraints.

```json
{
  "engine": "orca",
  "source_type": "xyz_file",
  "source_value": "/work/e1/candidate.xyz",
  "method": "ExtOpt",
  "basis_set": "",
  "external_program": "/opt/chem/bin/mace",
  "external_params": "--model /opt/models/mace.model --device cpu --dtype float64",
  "task_type": [{"opt": "ts"}],
  "charge": -1,
  "multiplicity": 1,
  "nproc": 1,
  "mem": "3GB",
  "orca_blocks": "%geom\n  Calc_Hess true\n  NumHess true\n  MaxIter 100\nend",
  "output_path": "/work/e1/ts.inp"
}
```

Expected controls: `! ExtOpt OptTS`, `%pal nprocs 1 end`, `%maxcore 3072`, the `%method` block, the `%geom` block, and `* xyz -1 1`. There must be no `Scan`/`Constraints`, `Freq`, or default DFT method/basis in this external TS job. The 100-cycle limit is an example budget ceiling, not permission to remain in a wrong basin for 100 steps.

For DFT, omit `external_program/external_params`, supply the chosen ORCA method/basis (e.g. `PBE0`, `def2-SVP`), and use `TightSCF` plus a suitable DFT grid when needed. `Calc_Hess true` requests the initial Hessian; add `NumHess true` when an analytical Hessian is unavailable. Existing compatible Hessians can instead be read with `%geom InHess Read InHessName "...hess" end`. Check geometry, atom ordering and model provenance first. `Recalc_Hess` is a targeted response to a diagnosed Hessian problem, not a routine expensive addition. See [ORCA TS controls](https://www.faccts.de/docs/orca/6.1/manual/contents/structurereactivity/optimizations_TS.html).

## 3. Frequency and IRC follow-ups

After unconstrained convergence, use the final optimized XYZ. For an external provider without an analytical Hessian:

```json
{
  "engine": "orca",
  "source_type": "xyz_file",
  "source_value": "/work/e1/ts.xyz",
  "method": "ExtOpt",
  "basis_set": "",
  "external_program": "/opt/chem/bin/mace",
  "external_params": "--model /opt/models/mace.model --device cpu --dtype float64",
  "task_type": [{"freq": null}],
  "frequency_mode": "numeric",
  "charge": -1,
  "multiplicity": 1,
  "nproc": 1,
  "mem": "3GB",
  "output_path": "/work/e1/ts_freq.inp"
}
```

Expect `! ExtOpt NumFreq`. No optimization or old constraint block is needed. Inspect the full gradient and the displacement of the imaginary mode, not just its count. A prior Hessian at a different geometry is not final frequency evidence. Numerical differentiation requires smooth, reproducible gradients; retain native defaults until noise is diagnosed. Restart data must match the geometry and all model settings. See [ORCA frequencies](https://www.faccts.de/docs/orca/6.1/manual/contents/structurereactivity/frequencies.html).

Once that TS is validated, reuse its same-geometry frequency Hessian for both IRC directions:

```json
{
  "engine": "orca",
  "source_type": "xyz_file",
  "source_value": "/work/e1/ts.xyz",
  "method": "ExtOpt",
  "basis_set": "",
  "external_program": "/opt/chem/bin/mace",
  "external_params": "--model /opt/models/mace.model --device cpu --dtype float64",
  "task_type": [{"irc": null}],
  "charge": -1,
  "multiplicity": 1,
  "nproc": 1,
  "mem": "3GB",
  "orca_blocks": "%irc\n  Direction both\n  InitHess read\n  Hess_Filename \"/work/e1/ts_freq.hess\"\nend",
  "output_path": "/work/e1/ts_irc.inp"
}
```

The example leaves `MaxIter` unspecified; do not accept an engine default blindly. Choose any setting for the current direction evidence, path topology and coupling, and compute cost; there is no universal step count. Keep native convergence checks enabled and record partial status honestly. Without a reusable Hessian, `InitHess calc_numfreq` requests numerical evaluation; do not inadvertently request an analytical external Hessian. Native files include `ts_irc_IRC_F_trj.xyz`, `ts_irc_IRC_B_trj.xyz` and the final `ts_irc_IRC_F.xyz` / `ts_irc_IRC_B.xyz`. Preserve them with the main log. See [ORCA IRC options](https://www.faccts.de/docs/orca/6.1/manual/contents/structurereactivity/irc.html).

For each outer frame, use the same agreed model with `task_type=[{"opt":null}]`, no constraints, then check minimum frequencies, identity, and direction. Forward/backward are trajectory labels, not guaranteed reactant/product assignments. `log_parser` reads native ORCA IRC counts/convergence; `ts_guess strict=True` extracts path endpoints from the native `*_IRC_F.xyz` / `*_IRC_B.xyz` final endpoint files (falling back to the last frame of `*_IRC_F_trj.xyz` / `*_IRC_B_trj.xyz`). An unconverged IRC flag or reached step ceiling alone does not require a longer run when the optimized outer frames establish direction and endpoint identity. Extend only the unresolved side if partial geometry cannot establish them. The short IRC alone does not prove a full path or dynamics.

`Freq` / `AnFreq` declare analytic frequencies and `NumFreq` declares numeric frequencies in native task recognition. An explicit frequency task is preserved when preparing a TS stage; it does not cause an extra `OptTS` task to be added. Questionable native task parameters remain in the input and produce visible warnings.

For free energies, read `method-selection.md` §4: `thermo_analysis backend="raw_rrho"` supports native ORCA and Gaussian thermochemistry at the recorded conditions. Corrections and totals come from the same thermal block; a partial final block does not borrow earlier values or a later SP energy. For a requested electronic barrier, use the validated `electronic_energy_hartree`; SCF fields remain the actual SCF quantity.

## 4. Relaxed scan example

`ts_guess mode=scan_prepare` uses the same calculation fields as `qm_input_writer`: explicit `engine`, one-token `method`, `basis_set`, `keywords`, `frequency_mode`, `orca_blocks` and `end_setting`. Electronic-state and resource fields are `charge`, `multiplicity`, `nproc` and total-job `mem`; coordinate-only XYZ input requires an explicit total charge. Standalone external scans use raw `%method` rather than writer `external_program`. With `engine="orca"`, its public atom indices are **0-based**, in the exact input XYZ order including explicit H. The example scans the atoms labeled 1 and 9 by `internal_coordinates`, passed as `[0, 8]`; choose real indices/range from the structure.

**Index check before every scan:** `internal_coordinates` and concrete `reaction_mapping.concrete_watch_pairs` use 1-based labels. Run-based `ts_guess` owns endpoint correspondence internally and does not accept an `atom_map`. Native ORCA scan/freeze coordinates use 0-based indices: convert each concrete label `i` to `i-1` in scan arguments and `%geom Scan` blocks (bond 1–6 → `Scan B 0 5`, dihedral 3–8–9–10 → `Scan D 2 7 8 9`). Gaussian/xTB scan arguments remain 1-based. Use current concrete atom tables; heavy-atom SMILES indices do not identify explicit-H coordinate rows. Check the element and position of each referenced atom, then compare the scan's starting coordinate with the intended bond, angle, or dihedral. A valid but shifted index can run to completion while scanning a different coordinate.

```json
{
  "mode": "scan_prepare",
  "engine": "orca",
  "input_path": "/work/e1/reactive.xyz",
  "scans": [{"coord_type": "bond", "atoms": [0, 8], "scan_end": 1.30, "scan_steps": 16}],
  "method": "ExtOpt",
  "basis_set": "",
  "charge": -1,
  "multiplicity": 1,
  "nproc": 1,
  "mem": "3GB",
  "orca_blocks": "%method\n  ProgExt \"/opt/chem/bin/mace\"\n  Ext_Params \"--model /opt/models/mace.model --device cpu --dtype float64\"\nend",
  "output_path": "/work/e1/scan.inp"
}
```

Expect `! Opt ExtOpt`, `%pal nprocs 1 end`, `%maxcore 3072` and `%geom Scan B 0 8 = <current>, 1.30, 16 ...`. The tool supplies `%geom`, `%pal` and `%maxcore`; do not append duplicate scan, constraint or resource blocks. ORCA supports one coordinate, or two typed coordinates with explicit `scan_mode="grid"` (independent surface) or `scan_mode="concerted"` (coupled path with equal step counts). A grid retains the surface without automatically selecting a TS candidate. Use `scans` and `freeze` for these coordinates, not raw `%geom` in `orca_blocks`. For DFT split the chosen level into `method="PBE0"`, `basis_set="def2-SVP"`, without the external block. The shared writer divides total `mem` across `nproc` for `%maxcore`; match the scheduler reservation to the job total. For an existing run, supply `run_id` and scan intent; the run supplies its charge, multiplicity and execution resources. Its calculation snapshot describes the prepared input; preparation does not run the scan or select a different method.

Keep `<stem>.relaxscanact.dat` and per-point `<stem>.NNN.xyz` files for `scan_parse`. Its native sidecar path pairs energies with the correct frame and reports the peak as a `candidate` with `scan_index`/`energy`/`geometry_ref`/`source`. If the peak frame file is missing, the tool returns `candidate_unavailable=true` and never substitutes the last frame; recover or re-run the missing frame before extracting a TS guess. The text-only fallback is best-effort: inspect the returned notes before using it as a peak candidate. Export the chosen seed into a fresh unconstrained TS input.

## 5. Submission and failure checks

For submission, match CPU allocation to the workflow: for high-throughput or parallel batches (conformer sweeps, scan points, independent single points), submit with `cpus=2` to `cpus=4` (QM parallel efficiency drops sharply on single jobs; aggregate throughput across concurrent 2–4 core jobs is far superior). For sequential blocking workflows (reaction mechanism paths where each intermediate/TS blocks downstream steps), allocate more cores — up to 32 cores maximum (`cpus` up to 32, within node capacity) to unblock the critical path quickly. Writer `mem="3GB"` is a total budget divided by `nproc`; ORCA `%maxcore` is per process. Reserve memory for all processes plus overhead. `%maxcore` does not cap the external ML model's memory. Use the node's real capacity, not a fixed atom-count/core rule.

Use separate basenames/directories for independent jobs to avoid scratch/Hessian collisions. Check the original input and final geometry alongside `log_parser`: `ORCA TERMINATED NORMALLY` can also appear after an optimization reaches its iteration limit. For `ExtOpt`, absent SCF blocks are expected; lack of cclib SCF data is not by itself a failed external job.

`ExtOpt` replaces the energy/gradient provider; it does not select a TS task and does not expose DFT orbitals. Do not add `SCF=...`, Gaussian `Int=UltraFine`, `NoEigen`, `LQA`, or `Geom=AllCheck`. Native DFT controls cannot repair a rough external potential. See [ORCA external interface](https://www.faccts.de/docs/orca/6.1/manual/contents/structurereactivity/optimizations.html#external-programs).
