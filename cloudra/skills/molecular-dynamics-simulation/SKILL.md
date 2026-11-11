---
name: molecular-dynamics-simulation
description: Use when a task involves packing solvent boxes, preparing biomolecular or small-molecule MD inputs, running GROMACS or OpenMM, or checking minimization, equilibration, and trajectory analysis.
license: MIT
metadata:
  original-skill: "molecular-dynamics"
  source: "https://github.com/K-Dense-AI/scientific-agent-skills"
  adapted-by: "Cloudra"
  upstream-license: "MIT, Copyright (c) 2025 K-Dense Inc."
---

# Molecular dynamics in Cloudra

The calls below use the JavaScript tool protocol. In traditional mode, call the same tool with the same arguments. Load the current schemas when needed.

```javascript
const docs = await tools.get_tool_docs({names: ["md_box", "format_converter", "submit_compute_job", "query_compute_job"]})
text(docs.data.documents)
```

## 1. Prepare coordinates and topology

For a mixed-solvent or reaction box, provide one explicit coordinate template per component and integer copy counts. Set `initial_density_g_cm3` for a starting cubic box, or set `box_lengths_angstrom` for explicit orthogonal dimensions. `min_distance_angstrom` defaults to 2.0 Å between atoms in different copies, including across periodic boundaries. Load `gromacs-smoke.md` below for the calls that create the two SDF files in this water–ethanol example.

```javascript
const box = await tools.md_box({
  components: [
    {structure_path: "water.sdf", count: 100},
    {structure_path: "ethanol.sdf", count: 100}
  ],
  box_lengths_angstrom: [24, 24, 24],
  output_dir: "water-ethanol-box",
  seed: 42
})
text(box.data)
```

On success, open the file at `data.report_path`. This example writes `water-ethanol-box/box.json`.

```javascript
const report = await tools.read({path: "water-ethanol-box/box.json"})
text(report.data.content)
```

Check the component counts, `box_lengths_angstrom`, `initial_density_g_cm3`, `minimum_observed_distance_angstrom` and `warnings` against the requested recipe. `density_reference` identifies the liquid reference and its temperature and pressure when available. Use the initial density to check the packing recipe. If the protocol includes NPT, examine the density time series from that stage. A warning can accompany a successful build. If the build fails, read `data.message` and address the named input, dependency or packing conflict.

For GROMACS, convert the periodic coordinates through PDB, then run `gmx editconf`.

```javascript
const converted = await tools.format_converter({
  input_path: "water-ethanol-box/box.xyz", input_format: "xyz",
  output_path: "water-ethanol-box/box.pdb", output_format: "pdb"
})
text(converted.data)
```

```javascript
const conversion = await tools.bash({
  command: "gmx editconf -f water-ethanol-box/box.pdb -o water-ethanol-box/box.gro && sed -n '2p' water-ethanol-box/box.gro && tail -n 1 water-ethanol-box/box.gro"
})
text(conversion.data)
```

Verify 1200 atoms and a 2.4 × 2.4 × 2.4 nm cell in this example. For the actual MD input, assign each copy the residue and atom names from its separately prepared topology and match the order of its atoms. Check `[molecules]` in the `.top` against the order of copies in the `.gro`, and each `[atoms]` list in the included `.itp` against the coordinates of that copy. For a cell whose vectors are already set, the conversion above retains them. `editconf -box` sets absolute lengths in nm, while `-d` sets a solute-to-box distance. [GROMACS editconf](https://manual.gromacs.org/current/onlinehelp/gmx-editconf.html) · [Cloudra knowledge card dyn07, §§7–9]

For protein, protein–ligand and metal-containing inputs, load the structure preparation and parameter notes before choosing a route.

```javascript
const guide = await tools.get_skill({skill_name: "molecular-dynamics-simulation", reference: "biomolecular-preparation.md"})
text(guide.data.content)
```

## 2. Submit the prepared calculation and read the engine output

Use `write` to create the Bash script in the directory containing its inputs. Make the script stop on a failed command with `set -euo pipefail`. For GROMACS, run `gmx grompp -f em.mdp -c system.gro -p topol.top -pp expanded.top -o em.tpr` with the selected protocol and named topology. Use `expanded.top` to inspect the included parameters and molecule list. Resolve atom-name, atom-order and parameter warnings before running `gmx mdrun -deffnm em -nt 4` for the four-CPU local thread-MPI example below.

```javascript
const job = await tools.submit_compute_job({
  input_file: "md/run.sh", job_type: "shell", execution_backend: "local",
  is_async: true, cpus: 4
})
text(job.data)
```

The job runs from the script's directory. Keep the returned `data.job_id`. For job 17, the MD agent can call the top-level `stop` with `{"reason":"Wait for MD job 17"}` and resume on its terminal notification. Use the actual job ID when querying.

```javascript
const job = await tools.query_compute_job({job_id: 17})
text(job.data)
```

When the query returns a job record, check its `state` and `last_error`. Pass its `log_path` to `read` for the scheduler log. Open the native `em.log` in the calculation directory for the GROMACS minimization result. Record the inputs, engine log and artifact passed to the next stage.

- **Minimization:** Read `em.log` and record the achieved maximum force and termination reason for GROMACS. OpenMM `Simulation.minimizeEnergy` takes a force tolerance in kJ/(mol·nm). Check the force and any iteration limit against the chosen criterion before starting dynamics.
- **Thermalization and equilibration:** Use the approved temperature, restraints and ensemble. NVT keeps the box fixed. NPT allows the box to relax under the chosen pressure. Use `gmx energy -f npt.edr -o equilibration.xvg` and select the relevant terms, such as Temperature, Density, Volume and Potential, when present. Check slow observables that matter to the system, such as local composition for a mixture or contacts in a binding pocket. Choose the analysis interval from the observed time series.
- **Production:** Use the actual end state from equilibration. For GROMACS, supply the checkpoint with `grompp -t` when preparing a new stage that continues from it. To resume the same interrupted run, use `mdrun -cpi` with its checkpoint and matching run files. Confirm trajectory times, output paths and requested steps in the native log. A shell job at `done` reports script completion.

Load the reference for the template creation calls, geometry check and complete local scheduler probe.

```javascript
const guide = await tools.get_skill({skill_name: "molecular-dynamics-simulation", reference: "gromacs-smoke.md"})
text(guide.data.content)
```

## 3. Prepare the trajectory for the observable

For structural analysis of a single protein chain, restore whole molecules before fitting.

```bash
printf '%s\n' System | gmx trjconv -s md.tpr -f md.xtc -o whole.xtc -pbc whole
gmx rms -s md.tpr -f whole.xtc -o backbone-rmsd.xvg
```

In this backbone RMSD example, choose `Backbone` for both fitting and measurement if that group is present. For a multichain complex, use the whole-molecule trajectory and an index containing the chains in the assembly. Run `gmx trjconv -s md.tpr -f whole.xtc -n complex.ndx -o assembly.xtc -pbc cluster`, select the assembly to cluster and `System` for output if present. Inspect representative frames and contacts before fitting `assembly.xtc`. For diffusion, preserve continuous unwrapped displacement. Record the actual selection, reference and frame/time interval for each reported observable. [Computational Chemistry Commune PBC example](https://bbs.keinsci.com/thread-53952-1-1.html) · [MDAnalysis RMSD/RMSF documentation](https://docs.mdanalysis.org/stable/documentation_pages/analysis/rms.html)

For MM-PBSA/GBSA, report the method, frame selection, entropy treatment and uncertainty. Treat residue decomposition as a model-dependent contribution and examine consistency across blocks or independent runs. For an unstable run, start with the first engine warning and its atom IDs. Check coordinates, topology, timestep, constraints and equilibration before changing the protocol. [GROMACS run-time errors](https://manual.gromacs.org/current/user-guide/run-time-errors.html) · [gmx_MMPBSA output](https://valdes-tresanco-ms.github.io/gmx_MMPBSA/dev/output/)

Use the top-level `agent_hub` search for a concrete chemistry question. Search with `{"action":"search","keyword":"GROMACS RMSD 周期性边界"}` for equilibration and PBC guidance (`kb:627`), or with `"蛋白 配体 脱离 原因"` for ligand dissociation (`kb:632`). For building and topology, see `kb:473` and `kb:dyn07`. Confirm command semantics against the current engine help. [Packmol forum thread](https://bbs.keinsci.com/thread-12549-1-1.html) · [Equilibration forum thread](https://bbs.keinsci.com/thread-27122-1-1.html) · [Ligand dissociation forum thread](https://bbs.keinsci.com/thread-27434-1-1.html)

Adapted from the MIT-licensed K-Dense scientific-agent-skills package. The repository retains its upstream permission notice in `docs/licenses/k-dense-scientific-agent-skills.md`.
