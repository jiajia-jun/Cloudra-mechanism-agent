# Compile, check and continue an MD run

## Before using the production inputs

Use `read` on the stage-specific file written by `gmx grompp -po`. Check the actual integrator, `dt` and `nsteps`, temperature/pressure coupling, nonbonded settings, constraints, active restraints and output cadence against the selected protocol. Read the corresponding `-pp` topology for the effective includes. With position restraints, supply the selected reference coordinates through `grompp -r`. In NPT also check the chosen `refcoord-scaling`. For a planar bilayer check lateral versus normal coupling, leaflet composition, area per lipid and thickness before production. [AI-Computational-Chemist GROMACS validation](https://github.com/JCLiuGroup/AI-Computational-Chemist/blob/main/tools/gromacs/references/validation.md) · [GROMACS `.mdp` options](https://manual.gromacs.org/current/user-guide/mdp-options.html)

For a new topology or an unfamiliar execution setup, use `write` to create a short dynamics job with its own `.mdp`, `.tpr` and output prefix. Use the intended node and exercise neighbor-list updates, the selected constraints and coupling, and the requested trajectory writes. Submit it with `submit_compute_job` as a `shell` job as shown in the main skill. Open the native log and run `gmx check` on the output. Inspect the first LINCS/SETTLE warning or nonfinite value and the associated atoms in the preceding configuration before changing settings. A clean pilot tests the setup, and equilibration needs the longer time series from the actual run. [AI-Computational-Chemist GROMACS validation](https://github.com/JCLiuGroup/AI-Computational-Chemist/blob/main/tools/gromacs/references/validation.md) · [GROMACS run-time errors](https://manual.gromacs.org/current/user-guide/run-time-errors.html)

## Choose the command from the checkpoint and the requested change

Use these blocks in a Bash script that starts with `set -euo pipefail`, so a missing or empty checkpoint stops the script.

**New stage from the previous stage.** For example, to carry NVT coordinates and velocities into an approved NPT stage, set `gen_vel = no` and `continuation = yes` in `npt.mdp`, then verify both in `npt.effective.mdp`. If this stage uses position restraints, add `-r` with the approved reference file. Use a fresh prefix for the NPT outputs and check the new time origin in the `grompp` output. [GROMACS pressure equilibration tutorial](https://tutorials.gromacs.org/docs/md-intro-tutorial.html#equilibration-run-pressure) · [GROMACS `grompp`](https://manual.gromacs.org/current/onlinehelp/gmx-grompp.html)

```bash
test -s nvt.cpt
gmx grompp -f npt.mdp -c nvt.gro -t nvt.cpt -p topol.top -pp npt.expanded.top -po npt.effective.mdp -o npt.tpr
```

**Resume an interrupted stage.** Confirm the previous Cloudra job has stopped and use its actual checkpoint and run input. `mdrun -cpi` starts at the first TPR step when the checkpoint is absent. Make the script check for the file and verify the resumed step in `md.log`. To append, use the original prefix and matching output files. [GROMACS `mdrun`](https://manual.gromacs.org/current/onlinehelp/gmx-mdrun.html)

```bash
test -s md.cpt
gmx mdrun -s md.tpr -deffnm md -cpi md.cpt
```

If the old outputs cannot be appended, retain them and write numbered parts. Use a separate output checkpoint to retain the original one. Check frame times on both parts for gaps or a shared checkpoint frame before combining them for analysis. For a duration-only extension, generate a longer TPR with `gmx convert-tpr -s md.tpr -extend "$EXTRA_PS" -o md-extended.tpr`, then substitute `md-extended.tpr` in the resume command. Set `EXTRA_PS` to the approved extra time in ps. [GROMACS long simulations](https://manual.gromacs.org/current/user-guide/managing-simulations.html)

```bash
test -s md.cpt
gmx mdrun -s md.tpr -deffnm md -cpi md.cpt -noappend -cpo md-next.cpt
```

**OpenMM restart.** Keep the serialized `System`, integrator and matching topology. Use `CheckpointReporter` during the run and `Simulation.loadCheckpoint()` on a compatible installation with the same System, platform, version and hardware. For moving between platforms, save an XML state with `saveState()` and load it with `loadState()` in a matching simulation. The XML preserves positions and velocities, while the binary checkpoint also preserves internal state such as RNG state. Open new trajectory/report files when starting a new output part. [K-Dense MD skill](https://github.com/K-Dense-AI/scientific-agent-skills/blob/main/skills/molecular-dynamics/SKILL.md) · [OpenMM `Simulation`](https://docs.openmm.org/latest/api-python/generated/openmm.app.simulation.Simulation.html)

## Before interpreting the observable

For a single protein in solution, run `gmx mindist -s md.tpr -f whole.xtc -pi -od protein-image.xvg` and select `Protein` to check its distance from its periodic images. Inspect the closest frames against the intended image separation and short-range cutoffs. [GROMACS `mindist`](https://manual.gromacs.org/current/onlinehelp/gmx-mindist.html) · [Knowledge card `kb:627`](https://www.umsyar.com/627)

Compare the slow observable across retained time blocks or independent runs. An RMSD plateau can coexist with drift in the observable of interest. For local mixing in bulk water–ethanol, use `md_rdf` with `start_ps` and `end_ps` for each block as shown in the main skill. The example below creates the index and shows the native `-cn` option for cumulative coordination, which counts ethanol oxygens around each water oxygen. Use the residue and atom names in the actual topology. Retain the intervals and groups with the outputs. [GROMACS `select`](https://manual.gromacs.org/current/onlinehelp/gmx-select.html) · [GROMACS `rdf`](https://manual.gromacs.org/current/onlinehelp/gmx-rdf.html)

```bash
gmx select -s md.tpr -on mixture.ndx -select '"Water_O" resname SOL and name OW; "Ethanol_O" resname ETO and name O1'
gmx rdf -s md.tpr -f md.xtc -n mixture.ndx -ref 'group "Water_O"' -sel 'group "Ethanol_O"' -o water-ethanol-rdf.xvg -cn water-ethanol-cn.xvg
```
