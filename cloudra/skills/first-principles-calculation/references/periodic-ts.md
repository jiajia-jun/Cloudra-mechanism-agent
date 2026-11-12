# Fixed-cell periodic transition states

Use `periodic_ts` for surface reactions, adsorbate or defect diffusion, and other fixed-cell events with explicit endpoints. Read its live contract with `get_tool_docs`. This workflow uses endpoint preflight and periodic unwrapping as in CatDT, and evaluates the native band before running a separate saddle check as in TSAgent. [CatDT paper](https://arxiv.org/abs/2606.05050) · [CatDT path preparation](https://github.com/AI4QC/catdt-gs/blob/main/core/pathway/neb_frame_prep.py) · [TSAgent, §3 and Appendix D.5](https://arxiv.org/html/2605.14154v1)

## Prepare the band

1. Relax both endpoints in the same cell with the same composition, substrate mask, electronic settings and relevant boundary conditions. Check that each is a minimum in the intended space. Use the staged adsorption workflow when a surface endpoint still needs relaxation. Record electronic state, charge, spin, smearing, basis or POTCAR, k-points, cutoffs and dispersion as applicable.
2. Use `periodic_ts` with `operation.type="prepare"`. Supply the number of **interior** images. The endpoints add two more. Use EXTXYZ to retain partial PBC for slabs. The tool requires whole-atom constraints and inherits the same frozen atoms at both ends. Give `fixed_atoms` to replace the input masks explicitly, including an empty list for an unconstrained band.
3. Review the unwrapped seed in `band.extxyz`. Atom row numbers define correspondence unless `atom_map` overrides them with 1-based `[initial, final]` pairs. Inspect equal-element assignments for atom exchange, proton transfer and vacancy hops. Each atom normally takes the shortest periodic displacement. For a particular route, use `image_shifts` with 1-based `atom_index` and integer `shift` in the input lattice basis relative to the supplied final position. A zero shift keeps that atom in the supplied final image. Use `waypoint_path` in the initial atom order for a curved seed or to avoid a collision. Inspect contiguous adsorbates and the closest contacts between images.
4. IDPP is the default geometric initializer. Choose `interpolation="linear"` to use a linear path through any waypoint exactly. For coincident atoms, inspect the mapping or give a waypoint. For large jumps, give more images or revise the route. The IDPP residual describes the seed interpolation.

```javascript
const seed = await tools.periodic_ts({
  operation: {
    type: "prepare", engine: "vasp",
    initial_path: "reactant.extxyz", final_path: "product.extxyz",
    intermediate_images: 4, output_dir: "reaction-neb"
  }
})
text(seed.data.engine_files)
```

## Run the engine

| Engine | Input and run |
| --- | --- |
| VASP | Combine the root `INCAR.neb` image count with the chosen NEB settings in `INCAR`. Supply matched `KPOINTS` and POTCAR in POSCAR species order. Keep the numbered image directories with their `POSCAR` files. VASP uses XYZ periodicity. Run a separate matched calculation at each prepared endpoint geometry and keep its `OUTCAR` in that endpoint directory. Stock VASP supports NEB through `IMAGES`. Check the installed build before using VTST-only climbing or optimizer tags. Use the site MPI launcher with ranks divisible by the number of interior images. [VASP NEB](https://vasp.at/wiki/Nudged_elastic_bands) · [VASP on VTST support](https://vasp.at/forum/viewtopic.php?p=33174#p33174) |
| CP2K | Set `GLOBAL/RUN_TYPE BAND`. Include `geometry.inc` in `FORCE_EVAL/SUBSYS`, `band.inc` in `MOTION/BAND`, `trajectory.inc` in `MOTION/PRINT`, and any `fixed-atoms.inc` in `MOTION/CONSTRAINT`. Retain the replica XYZ inputs and the stdout, energy and trajectory print keys. Keep `OPTIMIZE_END_POINTS FALSE` under `BAND/OPTIMIZE_BAND`. Choose `BAND_TYPE`, optimization, spring and parallel layout for the system. Match `CELL` and `POISSON` periodicity and choose a compatible solver. Keep the per-replica outputs with the main stdout and `band.ener`. [CP2K BAND](https://manual.cp2k.org/cp2k-2025_2-branch/CP2K_INPUT/MOTION/BAND.html) · [CP2K OPTIMIZE_BAND](https://manual.cp2k.org/cp2k-2025_2-branch/CP2K_INPUT/MOTION/BAND/OPTIMIZE_BAND.html) |

Use `submit_compute_job` for the run. For MPI, set `job_type="shell"` and pass a site launch script in the prepared run directory. Set `cpus` to match the allocated resources and capture engine stdout in a file. For CP2K in a configuration where the installed binary can run the requested band directly, submit the assembled `.inp` with `job_type="cp2k"`. Run long jobs asynchronously. Keep native outputs from one run together. For a revised seed, call `prepare` with a fresh directory.

When images have poor initial contacts or unstable tangents, inspect the failed image and repair the geometry, mapping or waypoint. A relaxed ordinary NEB can seed CI-NEB when the engine supports it. Verify the climbing phase from the run evidence. If the band finds an interior minimum, relax that configuration and examine the two elementary steps separately.

## Read the band and refine a candidate

```javascript
const band = await tools.periodic_ts({
  operation: {
    type: "analyze", run_dir: "reaction-neb",
    output_log: "reaction-neb/neb.out", dimer_dir: "reaction-dimer"
  }
})
text(band.data)
```

- Omit `dimer_dir` to inspect. Give `candidate_path` for a single new EXTXYZ instead of a dimer directory. A candidate requires a unique sampled interior peak above both matched endpoint energies, plus the native coordinates evaluated at that energy. `dimer_dir` also needs the two adjacent evaluated structures. Its Cartesian starting direction is the local band secant under PBC with zero components on frozen atoms.
- Read `band_complete` as evidence that the selected native band step can be compared across images. Read `native_converged` separately from the engine's stopping evidence. `null` means unknown. VASP uses the evaluated OUTCAR energy extrapolated to zero smearing. The VTST reader can compare synchronized steps and leaves VTST convergence unknown. CP2K uses the BAND replica energy converted from Hartree. Missing or contradictory native evidence can leave peak differences unset. Confirm the electronic settings for both endpoints independently, especially for separate VASP jobs.
- Report sampled `forward_peak_ev`, `reverse_peak_ev` and `reaction_energy_ev` as electronic energy differences with their energy convention. Preserve their signs. A peak image can seed a saddle search. A path with an endpoint above the interior samples or multiple competing peaks needs inspection.
- For VASP dimer refinement, use the written `POSCAR` including its Cartesian axis block and combine `INCAR.dimer` with the matched electronic and fixed-cell optimization settings. For CP2K, set `RUN_TYPE GEO_OPT`, include `dimer.inc` inside `MOTION/GEO_OPT` and retain the geometry and fixed-atom includes. Inspect dimer curvature and the final forces before running the frequency check. [VASP improved dimer](https://vasp.at/wiki/Improved_dimer_method) · [CP2K DIMER](https://manual.cp2k.org/cp2k-2025_2-branch/CP2K_INPUT/MOTION/GEO_OPT/TRANSITION_STATE/DIMER.html)

## Verify the saddle and both connections

1. Evaluate the stationary-point forces at the candidate or refined geometry and calculate its Hessian in the intended mobile space. Use VASP finite differences or CP2K vibrational analysis with the same electronic model. If using a partial Hessian, state which atoms and coordinates move. Include substrate motion that participates in the event. Check step-size and force precision for soft or ambiguous modes. [VASP IBRION](https://vasp.at/wiki/IBRION) · [CP2K vibrational analysis](https://manual.cp2k.org/cp2k-2025_2-branch/CP2K_INPUT/VIBRATIONAL_ANALYSIS.html)
2. Inspect the eigenvector of the single significant imaginary mode. It should move the atoms involved in the intended diffusion hop or bond changes. Distinguish significant modes from numerical noise with evidence for the specific calculation.
3. Follow both signs of that mode using a supported periodic IRC or relax geometries displaced in both directions. Confirm the two resulting minima match the intended identities, sites and periodic atom mapping. Report the numerical scope of the Hessian and the connection evidence. Use the verified saddle energy with matched endpoint references for the final electronic barriers.
