# IDPP path interpolation

`ts_guess(mode="interpolate", interp_method="idpp")` now defaults to
`idpp_mode="standard"`. Choose `idpp_mode="light"` to reproduce the previous
fixed-target-weight, independent-image Adam path. This option is unrelated to
any `standard` agent/ablation arm. `interp_method="linear"` is unchanged and does
not use `idpp_mode`.

- **standard** uses the existing ASE dependency's `idpp_interpolate`, with its
  current-distance^-4 pair potential and full derivatives, coupled NEB springs,
  and MDMin optimizer. NEB uses explicit `improvedtangent`, k=0.1, fixed endpoints,
  no climbing image, and non-periodic distances. MDMin uses ASE's interpolation
  defaults: fmax=0.1 and at most 100 steps. These are IDPP pseudo-force criteria,
  not electronic energies/forces or a QM accuracy threshold. The NEB method is
  pinned explicitly rather than following version-dependent ASE defaults.
- **light** retains the old target-distance^-4 weights (target distances clipped
  at 0.1 Å), per-image Adam updates, learning rate 0.02, 4000-step ceiling and
  max-absolute-gradient-component tolerance 1e-7. It is an approximation, not
  the original coupled IDPP method. Recording the final gradient does not add
  optimizer steps or change coordinates.

Mapping, Kabsch endpoint alignment, total frame count including both endpoints,
watch-pair selection and the distance-midpoint TS candidate rule are unchanged.
The independent `xtb_path` missing-executable fallback also honors `idpp_mode`.
Run-based interpolation uses the same implementation and includes its metadata
file in the provided candidate's evidence references. Run-based xTB does not
silently switch to interpolation.

## Results and old data

`is_success=true` means files were generated, not that relaxation converged or a
TS was verified. `interpolation` in the result and `interpolation.json` beside
`img_*.xyz` record the method, mode, optimizer, stopping criterion, threshold,
step budget, actual steps, final residual, convergence and termination. Standard
also records ASE version, NEB method and spring constant. XYZ comments record
mode and termination.

`termination="max_steps"` means the criterion was not met, even though finite
candidate files can still be inspected. `termination="not_required"` with
`converged=null` applies to linear interpolation, endpoint-only paths, and a
standard band with all images identical. Standard rejects coincident atoms
rather than jittering the path or claiming convergence after non-finite forces.
Old saved outputs without `interpolation` remain readable as null; their method
and convergence are unknown and are not retroactively labeled standard.

For light, `legacy_stopping_criterion_met` records whether the old clipped
max-gradient test was satisfied. If any final intermediate-image atom pair is
closer than the existing 1e-8 Å gradient denominator floor (including exact
overlap), `termination="degenerate_geometry"` and `converged=null`: the reported
legacy residual cannot establish convergence. This assessment does not alter
coordinates, stopping tests or Adam updates. A finite path may still be generated
successfully. Endpoint-only paths have no relaxation or legacy stopping test.
Older metadata without this field remains readable; do not infer that historical
`converged=true` rules out this degeneracy. Standard behavior is unchanged.

Neither a converged IDPP band nor its midpoint candidate is a transition state.
Subsequent TS optimization, frequency and IRC evidence are still required.

References: [Smidstrup et al. (2014)](https://arxiv.org/abs/1406.1512),
[ASE IDPP implementation](https://docs.ase-lib.org/_modules/ase/mep/neb.html#idpp_interpolate).
