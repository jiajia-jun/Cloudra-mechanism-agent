# IDPP Path Interpolation

`ts_guess(mode="interpolate", interp_method="idpp")` defaults to `idpp_mode="standard"`. Set `idpp_mode="light"` only if you need to reproduce the older per-image Adam approximation. (This option is unrelated to the `standard` agent mode, and `interp_method="linear"` does not use it.)

- **`standard` (default)**: Uses ASE's `idpp_interpolate` with coupled NEB springs (`improvedtangent`, `k=0.1`, fixed endpoints, no climbing image, non-periodic distances) and `MDMin` (`fmax=0.1`, max 100 steps). These thresholds are IDPP geometric pseudo-forces, not quantum-chemical energies or forces.
- **`light`**: Keeps the legacy uncoupled target-distance⁻⁴ weighting with per-image Adam optimization (lr `0.02`, up to 4000 steps, tolerance `1e-7`). It is a fast approximation rather than full coupled IDPP.

Atom mapping, Kabsch alignment, frame count, and midpoint candidate selection behave identically across modes.

## Interpreting Output

- `is_success=true` only means the interpolated path files were written—it does **not** mean relaxation converged or that the midpoint is a valid transition state.
- Full metadata (mode, optimizer, steps, final residual, convergence, and termination reason) is returned in `interpolation` and saved to `interpolation.json` alongside `img_*.xyz`.
- `termination="max_steps"` means the band hit its step limit before converging, though the frames are still inspectable. `termination="not_required"` applies to linear paths, endpoint-only bands, or identical images.
- In `standard` mode, overlapping atoms are rejected outright. In `light` mode, if any intermediate image has atoms closer than `1e-8` Å, it is flagged as `termination="degenerate_geometry"` with `converged=null` so an unreliable residual is never mistaken for convergence.

Neither a converged IDPP band nor its midpoint is a verified transition state—always follow up with unconstrained TS optimization, frequency verification, and IRC.

References: [Smidstrup et al. (2014)](https://arxiv.org/abs/1406.1512) · [ASE `idpp_interpolate`](https://docs.ase-lib.org/_modules/ase/mep/neb.html#idpp_interpolate).
