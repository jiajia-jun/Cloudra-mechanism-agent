---
name: molecular-dynamics-simulation
description: Domain expertise for classical molecular dynamics (MD) simulations (OpenMM, GROMACS, AMBER). Use when selecting biomolecular/small-molecule force fields (AMBER ff14SB/ff19SB, CHARMM36m, GAFF2, OpenFF), parameterizing ligands (Antechamber, AM1-BCC), configuring equilibration protocols (EM -> NVT heating -> NPT density equilibration -> Production), and analyzing trajectories (RMSD, RMSF, Gromos clustering, MM-PBSA/MM-GBSA binding free energies).
license: MIT
metadata:
  original-skill: "molecular-dynamics"
  source: "https://github.com/K-Dense-AI/scientific-agent-skills"
  adapted-by: "Cloudra"
  upstream-license: "MIT, Copyright (c) 2025 K-Dense Inc."
---

# Molecular Dynamics Simulation Standard Operating Procedure (SOP)

This skill provides comprehensive methodology for classical molecular dynamics (MD) simulations across biomolecular, protein-ligand, and condensed-matter systems using OpenMM and GROMACS.

> **Provenance**: adapted from the `molecular-dynamics` skill of [K-Dense-AI/scientific-agent-skills](https://github.com/K-Dense-AI/scientific-agent-skills) (MIT License, Copyright (c) 2025 K-Dense Inc.), then substantially extended for the Cloudra toolchain. The OpenMM and MDAnalysis implementations in sections 4 and 5 derive from that upstream skill; the remainder is Cloudra's own methodology. The upstream permission notice is preserved in [docs/licenses/k-dense-scientific-agent-skills.md](../../../docs/licenses/k-dense-scientific-agent-skills.md).

---

## 1. Local Toolchain Mapping

Anchor MD simulation stages in the `CLOUDRA` toolchain and Python ecosystem:

- **System Preparation & Solvation**: Use `PDBFixer` to repair crystal structures and OpenMM `Modeller` or GROMACS `gmx solvate` / `gmx genion` to add explicit solvent boxes and neutralizing salt (0.15 M NaCl).
- **Small-Molecule Parameterization**: For non-standard ligands and organic molecules, parameterize using AmberTools (`antechamber` for AM1-BCC charge calculation + `parmchk2` for GAFF2 force fields) or `openff-toolkit` / `openff-interchange`.
- **Job Execution**: Run GROMACS, LAMMPS, or OpenMM workflows with the available command or script tools. `submit_compute_job` accepts Gaussian, VASP, ORCA, CP2K, and xTB inputs; it cannot schedule an arbitrary MD script. For an unavailable compute route, coordinate with the Coordinator or environment specialist.
- **Trajectory Processing & Analysis**: Process trajectories using `MDAnalysis` or GROMACS tools (`gmx rms`, `gmx rmsf`, `gmx cluster`). Extract thermodynamic stability and compute binding free energies using **MM-GBSA / MM-PBSA** (`gmx_MMPBSA` or `MMPBSA.py`).

---

## 2. Force Field & Parameter Selection Matrix

### 2.1 Force Field & Water Model Pairings

| System Archetype | Recommended Force Field | Compatible Water Model | Parameterization Tool for Ligands |
| :--- | :--- | :--- | :--- |
| **Standard Soluble Proteins** | AMBER ff14SB / ff19SB | TIP3P-FB / OPC | — |
| **Protein-Ligand Complexes** | AMBER ff14SB + GAFF2 | TIP3P-FB / OPC | Antechamber (AM1-BCC) / OpenFF |
| **Membrane Proteins & Lipids** | CHARMM36m | CHARMM-modified TIP3P (mTIP3P) | CGenFF / CHARMM-GUI |
| **Nucleic Acids (DNA/RNA)** | AMBER OL15 (DNA) / OL3 (RNA) | TIP3P / OPC | — |
| **Intrinsically Disordered Proteins** | ff19SB or CHARMM36m | OPC / TIP4P-D | — |

> **Critical Force-Field Pairing Rule**:
> - Never mix water models arbitrarily: AMBER ff14SB pairs best with **TIP3P-FB**; AMBER ff19SB strictly requires **OPC**; CHARMM36m strictly requires **mTIP3P**.
> - Incompatible water models distort hydration free energies, secondary structure propensities, and protein folding equilibria.

---

### 2.2 Electrostatics, Cutoffs & Ensembles

1. **Electrostatics (PME)**: Particle Mesh Ewald is mandatory for all periodic solvated systems. Set grid spacing $\le 0.1\text{ nm}$ with 4th-order B-splines.
2. **Cutoff Distances**:
   - AMBER family: $0.9 \sim 1.0\text{ nm}$ direct space cutoff.
   - CHARMM family: $1.2\text{ nm}$ with force-switch modifier (`vdw-modifier = Force-switch`, `rvdw-switch = 1.0 nm`).
3. **Thermostat & Barostat Choices**:
   - **Production Ensembles**: Thermostat: `Nosé-Hoover` or `v-rescale` ($300\text{ K}$). Barostat: `Parrinello-Rahman`, `C-rescale`, or Monte Carlo Barostat ($1.0\text{ bar}$).
   - **Pre-equilibration**: Use `Berendsen` or `Langevin` for initial thermalization and volume relaxation; do **not** use Berendsen in production runs (it does not generate a true thermodynamic ensemble).
4. **Ion Parameters**:
   - Monovalent ions: Standard 12-6 Lennard-Jones parameters.
   - Highly charged transition metals ($\text{Zn}^{2+}, \text{Mg}^{2+}, \text{Fe}^{2+/3+}$): Standard 12-6 models underestimate charge transfer and coordination geometry. Use **12-6-4 LJ models** or bonded dummy atom parameters.

---

## 3. Small-Molecule Ligand Parameterization SOP

When simulating protein-ligand complexes, parameterize the ligand into AMBER GAFF2 format:

```bash
# 1. Add hydrogens and assign physiological protonation (pH 7.4) in RDKit / obabel
obabel ligand.sdf -O ligand_h.mol2 -p 7.4

# 2. Run Antechamber for AM1-BCC charge calculation and atom typing (GAFF2)
antechamber -i ligand_h.mol2 -fi mol2 -o ligand_gaff2.mol2 -fo mol2 \
            -c bcc -nc 0 -at gaff2 -rn LIG

# 3. Generate missing force-field parameters using parmchk2
parmchk2 -i ligand_gaff2.mol2 -f mol2 -o ligand.frcmod -s gaff2

# 4. Combine protein and ligand in tleap
tleap -f - <<_EOF
source leaprc.protein.ff14SB
source leaprc.gaff2
source leaprc.water.tip3pfb
loadamberparams ligand.frcmod
LIG = loadmol2 ligand_gaff2.mol2
PROT = loadpdb cleaned_protein.pdb
COMPLEX = combine {PROT LIG}
solvatebox COMPLEX TIP3PBOX 10.0
addions COMPLEX Na+ 0
addions COMPLEX Cl- 0
saveamberparm COMPLEX system.prmtop system.inpcrd
quit
_EOF
```

---

## 4. Multi-Stage Equilibration & Production Workflow

```
[1. Energy Minimization (EM)] ──> 5000 steps Steepest Descent, eliminate steric clashes
            │
            ▼
[2. NVT Heating (100 ps)]    ──> Heat 0 -> 300 K, position restraints on heavy atoms (1000 kJ/mol/nm^2)
            │
            ▼
[3. NPT Equilibration (1 ns)]──> Relax solvent density, step-down restraints (1000 -> 500 -> 100 -> 0)
            │
            ▼
[4. Production NPT (100+ ns)]──> Unrestrained run, 2 fs timestep (HBonds), save coords every 10-50 ps
            │
            ▼
[5. Trajectory & Free Energy]──> RMSD/RMSF, Gromos clustering, MM-PBSA / MM-GBSA binding free energy
```

### 4.1 Production OpenMM Python Implementation

```python
from openmm.app import *
from openmm import *
from openmm.unit import *

# 1. Load Parameterized System
prmtop = AmberPrmtopFile('system.prmtop')
inpcrd = AmberInpcrdFile('system.inpcrd')

system = prmtop.createSystem(
    nonbondedMethod=PME,
    nonbondedCutoff=1.0 * nanometer,
    constraints=HBonds,
    rigidWater=True,
    ewaldErrorTolerance=0.0005
)

# 2. Select Platform (CUDA -> CPU fallback)
try:
    platform = Platform.getPlatformByName('CUDA')
    properties = {'Precision': 'mixed', 'DeviceIndex': '0'}
except Exception:
    platform = Platform.getPlatformByName('CPU')
    properties = {}

# 3. Energy Minimization
integrator = LangevinMiddleIntegrator(300 * kelvin, 1.0 / picosecond, 0.002 * picoseconds)
simulation = Simulation(prmtop.topology, system, integrator, platform, properties)
simulation.context.setPositions(inpcrd.positions)
if inpcrd.boxVectors is not None:
    simulation.context.setPeriodicBoxVectors(*inpcrd.boxVectors)

print("Starting energy minimization...")
simulation.minimizeEnergy(maxIterations=2000, tolerance=10.0 * kilojoule / mole)

# 4. NVT Thermalization (100 ps)
print("Running NVT heating...")
simulation.context.setVelocitiesToTemperature(300 * kelvin)
simulation.step(50000)  # 100 ps

# 5. Add Monte Carlo Barostat for NPT Production
system.addForce(MonteCarloBarostat(1.0 * bar, 300 * kelvin, 25))
simulation.context.reinitialize(preserveState=True)

# 6. Production Reporters
simulation.reporters = [
    StateDataReporter('production.log', 5000, step=True, time=True,
                      potentialEnergy=True, temperature=True, density=True, speed=True),
    DCDReporter('production.dcd', 5000),  # Save every 10 ps
    CheckpointReporter('checkpoint.chk', 50000)
]

print("Running production MD...")
simulation.step(5000000)  # 10 ns (expand to 100 ns for production)
```

---

## 5. Trajectory & Free Energy Analysis

### 5.1 RMSD, RMSF, and Gromos Clustering (MDAnalysis)

```python
import MDAnalysis as mda
from MDAnalysis.analysis import rms, align
import numpy as np

u = mda.Universe('system.prmtop', 'production.dcd')

# 1. Align on protein backbone
align.AlignTraj(u, u, select='backbone', in_memory=True).run()

# 2. Compute Backbone RMSD
R = rms.RMSD(u, select='backbone', ref_frame=0)
R.run()
rmsd_time = R.results.rmsd[:, 1]  # ps
rmsd_val = R.results.rmsd[:, 2]   # Angstrom

# 3. Compute Residue-Averaged RMSF (discard first 20% equilibration)
n_frames = len(u.trajectory)
start_frame = int(0.2 * n_frames)
protein = u.select_atoms('protein and name CA')
rmsf_calc = rms.RMSF(protein).run(start=start_frame)
rmsf_per_residue = rmsf_calc.results.rmsf
```

### 5.2 Binding Free Energy: MM-GBSA Protocol

The binding free energy is computed across equilibrated snapshots ($N \ge 100 \sim 500$ frames):
$$\Delta G_{\text{bind}} = \langle G_{\text{complex}} \rangle - \langle G_{\text{protein}} \rangle - \langle G_{\text{ligand}} \rangle$$
$$\Delta G = \Delta E_{\text{MM}} + \Delta G_{\text{solv}} - T \Delta S$$
$$\Delta E_{\text{MM}} = \Delta E_{\text{vdw}} + \Delta E_{\text{elec}}, \quad \Delta G_{\text{solv}} = \Delta G_{\text{GB/PB}} + \Delta G_{\text{nonpolar}}$$

- **Per-Residue Energy Decomposition**: Run `gmx_MMPBSA` with `idecomp=1` to identify key hotspot residues ($\Delta G_{\text{contrib}} < -1.0\text{ kcal/mol}$).

---

## 6. Diagnostics & Troubleshooting

1. **"Flying Ice Cube" Effect**:
   - *Symptom*: System translationally freezes while kinetic energy accumulates in center-of-mass drift.
   - *Fix*: Remove center-of-mass motion every 100 steps (`comm-mode = Linear`, `nstcomm = 100` in GROMACS; or `system.addForce(CMMotionRemover(100))` in OpenMM).
2. **LINCS Warnings & Box Explosion**:
   - *Symptom*: Simulation crashes during early NPT with bond constraint errors.
   - *Fix*: Insufficient solvent padding or severe steric overlap. Rerun minimization with smaller step size, verify box dimensions ($\ge 1.0\text{ nm}$ padding), or reduce timestep to $0.5 \sim 1.0\text{ fs}$ for initial NPT.
3. **Ligand Disassociating in < 5 ns**:
   - *Symptom*: Ligand spontaneously leaves binding pocket.
   - *Fix*: Check partial charge assignment in `antechamber`. An incorrect net charge or reversed dipole generates strong repulsive forces.
