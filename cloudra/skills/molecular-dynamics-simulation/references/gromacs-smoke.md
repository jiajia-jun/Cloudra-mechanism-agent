# GROMACS geometry and scheduler checks

Run these examples in a fresh Agent workspace. The first uses RDKit (`cloudra[chem]`), Packmol 20.15.0 or later, and `gmx` on `PATH`. The second uses a local thread-MPI `gmx` with its bundled data files. Both examples were checked with GROMACS 2026.4. The first used Packmol 21.2.3.

## A. Convert a water–ethanol box to GROMACS coordinates

Call `smiles_to_mol` once per component to generate the explicit-hydrogen 3D templates.

```json
{"smiles":"O","generate_3d":true,"output_path":"water.mol"}
```

```json
{"smiles":"CCO","generate_3d":true,"output_path":"ethanol.mol"}
```

Call `format_converter` for each MOL file to keep the molecular graph in SDF.

```json
{"input_path":"water.mol","input_format":"mol","output_path":"water.sdf","output_format":"sdf"}
```

```json
{"input_path":"ethanol.mol","input_format":"mol","output_path":"ethanol.sdf","output_format":"sdf"}
```

Call `md_box` with water first. The order controls how the coordinate blocks are written.

```json
{
  "components":[{"structure_path":"water.sdf","count":100},{"structure_path":"ethanol.sdf","count":100}],
  "box_lengths_angstrom":[24,24,24],
  "seed":42,
  "output_dir":"water-ethanol-box"
}
```

Call `format_converter`, then run `gmx editconf` from the Agent workspace. [GROMACS `editconf`](https://manual.gromacs.org/current/onlinehelp/gmx-editconf.html)

```json
{"input_path":"water-ethanol-box/box.xyz","input_format":"xyz","output_path":"water-ethanol-box/box.pdb","output_format":"pdb"}
```

```bash
gmx editconf -f water-ethanol-box/box.pdb -o water-ethanol-box/box.gro
```

Check 1,200 atoms, the full element sequence and the 2.4 nm sides. The first 300 atoms are 100 water copies and the next 900 atoms are 100 ethanol copies.

```bash
python3 - <<'PY'
from pathlib import Path

box = Path('water-ethanol-box')
xyz = (box / 'box.xyz').read_text().splitlines()
gro = (box / 'box.gro').read_text().splitlines()
expected = 'O H H'.split() * 100 + 'C C O H H H H H H'.split() * 100
assert int(xyz[0]) == int(gro[1]) == 1200
assert [line.split()[0] for line in xyz[2:]] == expected
assert [line[10:15].strip() for line in gro[2:-1]] == expected
assert [float(edge) for edge in gro[-1].split()] == [2.4, 2.4, 2.4]
PY
```

The `.gro` residue name is the generic `MOL`, and its atom names are element labels. For a GROMACS simulation, map the atoms in each source SDF to the chosen topology's `[ atoms ]` and align the coordinate blocks with the expanded `[ molecules ]`. The two carbons of ethanol illustrate why matching only the element names is insufficient. Inspect all preprocessing warnings. [Cloudra knowledge card `kb:473`, section 24](https://sobereva.com/473) · [GROMACS `grompp`](https://manual.gromacs.org/current/onlinehelp/gmx-grompp.html)

## B. Run a water minimization probe through Cloudra

Use `write` three times with the arguments below. The bundled OPLS-AA/SPC files, cutoffs and two-step cap are specific to this probe. [GROMACS `solvate`](https://manual.gromacs.org/current/onlinehelp/gmx-solvate.html)

```json
{"path":"gmx-water/em.mdp","content":"integrator=steep\nnsteps=2\ncutoff-scheme=Verlet\nrlist=0.8\nrcoulomb=0.8\nrvdw=0.8\ncoulombtype=Cut-off\npbc=xyz\n"}
```

```json
{"path":"gmx-water/water.top","content":"#include \"oplsaa.ff/forcefield.itp\"\n#include \"oplsaa.ff/spc.itp\"\n[ system ]\nWater smoke test\n[ molecules ]\n"}
```

```json
{"path":"gmx-water/gmx-smoke.sh","content":"#!/bin/bash\nset -euo pipefail\ngmx solvate -cs spc216.gro -box 2.5 2.5 2.5 -p water.top -o packed.gro\ngmx grompp -f em.mdp -c packed.gro -p water.top -o em.tpr\ngmx mdrun -deffnm em -nt 1\n"}
```

Call `submit_compute_job`. The shell script runs from its own directory.

```json
{"input_file":"gmx-water/gmx-smoke.sh","job_type":"shell","execution_backend":"local","cpus":1,"is_async":false}
```

Use `query_compute_job` with the returned `job_id` to inspect the recorded `state`, `path`, `log_path`, and `last_error`. For example, if submission returned job ID 1, call it with these arguments.

```json
{"job_id":1}
```

The verified run reached `state="done"` with process exit code 0. `water.top` listed 510 `SOL` molecules and `em.gro` was present. Read `gmx-water/em.log` for the scientific result. The native log recorded the following.

```text
Energy minimization reached the maximum number of steps before the forces
reached the requested precision Fmax < 10.
Steepest Descents did not converge to Fmax < 10 in 3 steps.
Maximum force     =  1.7598590e+04 on atom 295
```

The scheduler ran the pipeline successfully. The minimization stopped at its step cap with a maximum force of about 17,599 kJ mol⁻¹ nm⁻¹, above the requested tolerance. Record the probe as executed and the minimization as unconverged. If submission fails, inspect the reported log and identify the first failing command. For preprocessing warnings, inspect the named atom or interaction and the effective `mdout.mdp` before changing settings. [GROMACS minimization options](https://manual.gromacs.org/current/user-guide/mdp-options.html#energy-minimization) · [Computational Chemistry Community glycerol warning case](https://bbs.keinsci.com/thread-9946-1-1.html)
