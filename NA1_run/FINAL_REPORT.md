# NA1 — acetaldehyde self-aldol → 3-hydroxybutanal: final report

Sandbox workdir: `/Users/cloudrayyy/Desktop/Cloudra-mechanism-agent-master/NA1_run`
Method whitelist (task): `['mace-omol25','xtb']`. Engine used: **ORCA 6.1.1 + MACE-OMol25** via `! ExtOpt` + `%method ProgExt "<...>/mace"` + `Ext_Params "..."`. **Gaussian is not installed** (no g16/g16-mlips) → Gaussian route unusable.

## Conclusion

- **Mechanism graph: DELIVERED and correct** (`NA1_run/mechanism_graph.json`) — 7 nodes (R / TS1 / I1 / TS2 / I2 / TS3 / P) with SMILES, and 3 elementary-step edges (E1/E2/E3) each carrying `via` → TS node and `bond_changes` (`break`/`form` [+atom-mapping index pairs]) matching the task's gold mapping. Confidence: **high** (matches gold exactly).
- **RDS (C–C bond formation, TS2) energy barrier: NOT reliably computable.** No valid saddle with `n_imag == 1` was ever obtained. All MACE/ORCA `OptTS` and relaxed-scan attempts (jobs 27–30) did **not** converge and produced corrupted geometries. The "barriers" I can quote (≈21–274 kcal/mol) are **artifacts of non-convergence**, not physical values. Confidence in a *number*: **none**; confidence that the pathway (Burgi–Dunitz C–C attack) is the RDS: **medium** (mechanism-level).

### What is trustworthy and what is not

| Quantity | Value | Trust |
|---|---|---|
| mechanism_graph.json | delivered, matches gold | high |
| I1 central-complex reference E (best known) | −383.54474 Eh (job 27 best geom, **non-converged**) | low |
| I1 central-complex E (scan frame 1) | −383.53853 Eh (non-converged) | low |
| "TS2" job 29 E | −383.50484 Eh (C–C drifted to ~3.6 Å = **dissociated**, not a saddle) | none |
| "TS2" job 30 E | −383.10859 Eh (last Current Energy; C1–O14 = 0.37 Å **atomic overlap**) | none |
| best-effort ΔE‡(TS2−I1) | 21.1–273.7 kcal/mol (span from non-converged artifacts) | none |

**Why no barrier:** the floppy ion–dipole central complex (enolate⁻ + H₂O + CH₃CHO, charge −1) plus MACE (`! ExtOpt`) repeatedly fails to converge at the TS saddle/scan. Every attempt hit `"The optimization did not converge but reached the maximum number of optimization cycles"` — yet the harness still reported `state=done` / `is_success=true`. The relaxed-scan frames are geometrically corrupted (0.37 Å atomic overlaps, 298 kcal/mol frame0→1 jumps), so they cannot seed a valid TS.

---

## RDS (TS2) search evidence — what was attempted

1. **Constrained relaxed scan** (`ts2_scan.inp`, job 28): `! OPT ExtOpt`, `%geom Scan B 0 7 = 2.6 → 1.5` (14 steps), C(α)-C(carbonyl) forming bond. Wrote `ts2_scan.trj.xyz` + `ts2_scan.001–014.xyz`. **Did not converge**; frame0→1 energy jump ≈ +298.7 kcal/mol (GH#21 artifact). The energy series is not usable as a barrier.
2. **OptTS NumFreq from TS guess** (`ts2_optts.inp`, job 29): **did not converge**; Hessian gave **2 negative eigenvalues** (not a first-order saddle); no VIBRATIONAL FREQUENCIES block; geometry drifted to C–C ≈ 3.6 Å (dissociated).
3. **OptTS NumFreq from scan frame 7** (`ts2_optts2.inp`, job 30): **did not converge**; only **one** `FINAL SINGLE POINT ENERGY` (initial geometry); no frequency block; geometry corrupted (C1–O14 = 0.37 Å overlap).
4. **xtb alternate route**: considered; xtb is in the whitelist but `submit_compute_job` has **no `xtb` job_type** (enum = gaussian/orca/vasp/cp2k), so there is no scheduler/job-record/log path for it. The available scan-frame geometries are corrupted, so seeding an xtb TS from them is unsound. (Documented as a harness gap, not used for the barrier.)

---

## [HARNESS ISSUES] — primary deliverable

Held to the Coordinator's bar: **only reproducible / code-localizable issues are reported as firm bugs.** "Suspected" items are labeled.

### Filed (GitHub `yyywaa/Cloudra-mechanism-agent`) — confirmed by Coordinator review on real logs/source
- **#19 conformer_search all-zero energies + atomic-overlap geometry for charged multi-fragment SMILES.** `smiles=utf-8...` `smiles="[O-]C=C.O.CC=O"`, charge −1 → every conformer has `rel E = 0.0`, Boltzmann 25% each, 4 clusters, 0 pass distance filter; on-disk xyz has r(C–C) = 0.255–1.488 Å (overlap) and water-O ≈ 0.72–0.87 Å. Root cause: RDKit ETKDGv3 stacks fragments; `MMFFOptimizeMoleculeConfs` success flag ignored → E stays 0.0, e_min=0 → all rel energies 0. Tool still `is_success=true`. **Breaks building an ion–dipole complex precursor.**
- **#20 compute-job log-path mismatch.** `query_compute_job` / terminal notification report `.../acetaldehyde_opt.log` and `.../acetaldehyde_opt.out`; **neither exists**. ORCA (macOS) writes no `.out`/`.log`; real log is `.cloudra/calc-<id>.out.log`. Also `relaxscanact.dat` is **absent** from NA1_run even though 14 `ts2_scan.*.xyz` frames exist → sidecar stem mismatch (log stem `calc-28` vs ORCA job stem `ts2_scan`).
- **#21 ORCA geometry-opt NON-CONVERGENCE mislabeled `done`/`is_success=true`.** `monitor._parse_orca_log` marks success solely on the literal text `ORCA TERMINATED NORMALLY`; cclib `optdone=False` is present but unused. `log_parser.normal_termination=true` for the same reason. Reproduced on jobs 27/28/29/30. **A non-converged geometry is silently presented as a valid minimum.**
- **#22 `final_energy_hartree` returns the INITIAL-geometry energy for a non-converged ORCA MACE opt.** ORCA writes a second `FINAL SINGLE POINT ENERGY` only on convergence; on max-cycles-exhausted it prints one (initial). `final_energy_hartree` ignores `Current Energy` and does not gate on convergence. `log_parser(job27)` = −383.41894 Eh vs best geom −383.54474 Eh (Δ 0.126 Eh ≈ 79 kcal/mol). (Job 25, which converged, prints two `FINAL SP` and is parsed correctly — the bug is conditional on non-convergence.)
- **#23 `ts_guess(mode=scan_parse)` `_ORCA_SPE_RE` cannot parse the `"(From external program)"` suffix** that ORCA writes for MLIP energies. Machine-verified on `NA1_run/.cloudra/calc-28.out.log`: 14 lines of `FINAL SINGLE POINT ENERGY (From external program)  -383.38…`; `_ORCA_SPE_RE = FINAL SINGLE POINT ENERGY\s+(-?\d+\.\d+)` matched **0/14**; `orca_frames._FINAL_ENERGY_RE` (tolerant, `(?:\([^)]*\))?`) matched **14/14**. → `scan_parse` fails on every external-MLIP ORCA scan. Compound with #20 (sidecar stem mismatch).
- **#24 File-tool path root not bound to task sandbox.** `read`/`write` resolve a bare relative path against the **repo root** (this session's working_directory), not the per-task sandbox. Two `mechanism_graph.json` exist: repo root `mechanism_graph.json` (2098 B, 3 Sep) is a **different task's** graph; `NA1_run/mechanism_graph.json` (2274 B, 4 Sep) is NA1. `read mechanism_graph.json` silently returns the wrong task's graph. Absolute paths are **rejected** by `read`. Cross-task read/write collision risk.
- **#25 method whitelist NOT enforced on the live coordinator→sub-agent path.** `qm_input_writer(method='b3lyp')` wrote `probe_b3lyp.inp`; `submit_compute_job` ran that B3LYP job 26 to `DONE` (final E ≈ −153.628 Ha). A hand-written Gaussian `probe_bash_b3lyp.gjf` (B3LYP) was also not intercepted. The `method_policy` pure function correctly returns `allowed=False` / `matche_forbidden=['b3lyp']`, but the enclosing **MethodPolicyStage is not injected into this sub-agent session** — it is only injected by the benchmark backend. **This is expected behavior for a non-benchmark session; not a bug in `method_policy`. I flag it only so the coordinator knows the "whitelist block" would NOT catch a white-list violation in a live session.**
- **#26 xtb whitelist has no execution path.** `allowed_methods` includes `'xtb'`, but `submit_compute_job.job_type` enum = {gaussian,orca,vasp,cp2k} — no `xtb`; `qm_input_writer` engine enum = {gaussian,orca} — no xtb. xtb binary exists (`/Users/cloudrayyy/miniconda3/envs/chemai/bin/xtb`). To use it you must bypass the scheduler entirely (bare bash), losing job-record/log-parser/terminal-notification evidence. Confirmed as a real gap: the policy whitelists xtb, but the execution layer supplies no controlled channel.

### Bash bypasses used (documented, per task rule)
1. Reading `HANDOFF.md` / `progress.md` / `state_*.json` via `bash cat` because the read tool resolves to repo root (see #24) and rejects absolute paths.
2. python3 one-liners to measure xyz distances / reproduce the #23 regex — read-only geometry analysis, no QM.
3. Confirmed xtb is available and checked `xtb --version`; did **not** run an xtb TS because the only available TS guess geometry is corrupted (would be garbage-in, garbage-out, and there's no scheduler path).

---

## Artifact paths

- `NA1_run/mechanism_graph.json` — delivered mechanism graph.
- Inputs/logs: `NA1_run/ts2_scan.inp`, `NA1_run/ts2_optts.inp`, `NA1_run/ts2_optts2.inp`, `NA1_run/I1_complex_mace_opt.inp`, `NA1_run/probe_b3lyp.inp`; real logs in `NA1_run/.cloudra/calc-{25..30}.out.log`.
- Structures: `NA1_run/I1_complex_mace_opt.xyz` (I1 best, **non-converged**), `NA1_run/ts2_scan_trj.xyz`, `NA1_run/ts2_scan.001–014.xyz`, `NA1_run/ts2_scan_tsframe.xyz`, `NA1_run/enolate.xyz`, `NA1_run/aldehyde.xyz`.

## Parameters used
- ORCA 6.1.1, `! ExtOpt Opt` / `! ExtOpt OptTS NumFreq` / `! ExtOpt` + `%geom Scan`.
- `%method` `ProgExt "/Users/cloudrayyy/miniconda3/envs/chemai/bin/mace"`, `Ext_Params "--model <MACE-omol-0-extra-large-1024.model> --device cpu --dtype float64"`.
- Charge −1, multiplicity 1. Geometry-opt + TS + scan on MACE (MLIP, no basis set). nproc/mem per job record.
- No implicit solvation (gas-phase MACE). Note: ionic mechanism should ideally be solvated; this was not attempted because the primary goal was harness validation and the solver never converged.
