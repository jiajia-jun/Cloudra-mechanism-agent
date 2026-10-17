# MLIP via Gaussian External or ORCA ExtOpt

Read the active engine recipe (`gaussian-inputs.md` / `orca-inputs.md`) for task parameters. This file adds external-provider capability and scientific limits. The filename is retained for existing skill links; both engines are supported.

## Choose the installed route

| Host interface | `qm_input_writer` fields | Generated route |
| --- | --- | --- |
| Gaussian + a configured g16-mlips command | `engine="gaussian"`, `method="external"`, `basis_set=""`, `external_program="mace"` (actual installed command; may include arguments) | `external="mace"`; no DFT method/basis |
| ORCA + an ORCA-compatible executable | `engine="orca"`, `method="ExtOpt"`, `basis_set=""`, absolute `external_program`, `external_params` for model/device/dtype | `ExtOpt` and `%method ProgExt/Ext_Params` |

The declared `method` records the chosen external interface. Put its executable in `external_program`, not a duplicate `keywords='external=...'`. `external_params` is ORCA-only. An arbitrary MACE Python module or Gaussian external wrapper is not automatically compatible with ORCA's file protocol. Resolve the executable/model on the actual compute host. Interface sources: [g16-mlips](https://github.com/t-0hmura/g16-mlips), [ORCA external-method tutorial](https://www.faccts.de/docs/orca/6.1/tutorials/workflows/extopt.html).

`ts_guess scan_prepare` shares explicit calculation field meanings, including `basis_set=""`: ORCA uses `method="ExtOpt"` with raw `%method` in `orca_blocks`; Gaussian uses `method="external"` with `keywords='external="mace"'`. Standalone scans do not expose writer `external_program`/`external_params`. The engine recipes describe atom indices and memory handling; preparation returns the declared configuration and does not run the calculation.

## Check capabilities once, then reuse

Record engine/wrapper versions, executable, checkpoint identity, charge/multiplicity, device, precision and available derivative orders. Consult existing deployment probes first. If a capability is unverified, run the smallest relevant probe within authorization and budget; an optimization probe does not establish TS/IRC/Hessian capability.

- ORCA `ExtOpt` selects the provider; `Opt`, `OptTS`, `NumFreq`, `IRC` select the operation. For a provider supplying energy/gradients but no analytic Hessian, use a numerical initial Hessian for TS refinement and `NumFreq` for final frequencies. Reuse a same-geometry compatible Hessian for IRC. Avoid routine repeated numerical Hessians without a diagnosed need.
- Gaussian requests derivative orders through External. Check what its installed wrapper returns before using force-constant/frequency options; failure to supply derivatives is an interface problem, not evidence that the reaction is impossible.
- Use the wrapper's documented precision/device options; the MACE examples use float64 for numerical derivative work. The external process may load a large model or start once per displacement. Do not increase ORCA processes before checking total memory and startup cost.
- Verify the external executable and model on the compute host before submitting. Cloudra's ORCA job wrapper handles the configured OpenMP environment for external jobs; submit through `submit_compute_job` instead of assembling a new launch environment per job. Treat host-specific paths and probe results as local operational notes, not as universally available capabilities.

## Charge, spin and evidence

Set `charge` and `multiplicity` explicitly on every generated input, including scans. They are not inferred from XYZ. Scans share the writer's `nproc` and total-job `mem` fields; an existing TS run supplies its own electronic state and execution resources. Confirm that the wrapper/model consumes them with the intended convention. MACE-OMol's charge/spin embedding is documented by the [MACE maintainers](https://github.com/ACEsuit/mace/discussions/1206); accepting these fields does not certify a particular electronic state or barrier.

An external energy/gradient calculation generally does not produce a Gaussian/ORCA wavefunction. Do not require Mulliken/NBO/IBO, SCF stability, or spin contamination from nonexistent orbitals. If the scientific question requires those observables, obtain them with a permitted appropriate method or report the limitation. Missing SCF blocks in an otherwise successful external log are expected.

## Accuracy and stopping

A model name is not an accuracy guarantee. Use the exact checkpoint's documented element, charge/spin and configuration coverage; do not infer that every anion or transition metal is either covered or excluded. Long-range charge separation, reactive geometries and electronic-state changes deserve model-specific scrutiny. A model trained against single-reference labels does not solve their multi-reference limitations.

If a search collapses or gradients are noisy, separate input/interface errors from initial-path problems and model limitations. Change only something justified by that diagnosis. A higher-level fallback is available only if allowed and appropriate. In MACE/xTB-only work, neither poor convergence nor Supervisor pressure authorizes DFT.

A monotonic 1D scan or repeated OptTS failure supports “no validated saddle found on the sampled search”, not “the reaction is barrierless”. Stop when the remaining budget cannot test a meaningfully different hypothesis or when the requested quantity is unsupported by all permitted methods. Preserve trajectories, failed calculations and unresolved stages; explain whether this is a search/budget failure or a scientifically justified refusal.

For an explicitly MLIP-level benchmark, report validated results at that level without silently relabeling them as DFT. For a DFT-quality scientific claim, use permitted independent validation justified by the target and system; do not equate training-set reference quality with demonstrated TS accuracy.
